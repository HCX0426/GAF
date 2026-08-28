"""Device service — single source of truth for device health, status, and
screenshot method management.

Phase 1 (2026-08-08): Extracted from ``agents/views.py`` module-level helpers
and ``DeviceViewSet`` health-check methods into a dedicated service class so
that business logic is testable independently of the HTTP layer.

All module-level functions are re-exported via ``services/__init__.py`` for
backward compatibility — existing views that import them directly from
``views.py`` continue to work after the import is updated to point here.
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import time

from django.utils import timezone

from agents.models import Device

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level helpers — screenshot methods, screen size, window handle
# ---------------------------------------------------------------------------

# Cache for Android physical screen size per device (expires in 60s).
# Resizing an emulator while it is running is rare; caching avoids an
# extra `adb shell wm size` round-trip for every tap/swipe.
_EMULATOR_SCREEN_SIZE_CACHE: dict[int, tuple[tuple[int, int], float]] = {}
_EMULATOR_SCREEN_SIZE_TTL = 60.0


def _get_or_cache_available_methods(device: Device) -> list[str]:
    """Return available screenshot methods for a device, using extra_info cache.

    First call detects methods via the platform handler / emulator chain and
    persists the result to ``device.extra_info['available_methods']`` so
    subsequent calls avoid repeated importlib probing. The cache is invalidated
    (by removing the key) when the screenshot method changes or the device is
    re-registered.
    """
    extra = device.extra_info or {}
    cached = extra.get("available_methods")
    if cached:
        return list(cached)

    # Detect real-time
    methods: list[str] = []
    if device.device_type == Device.DeviceType.EMULATOR:
        try:
            from device_bridge.platforms.windows._adb_screenshot import (
                get_available_methods as _get_available_methods,
            )

            methods = _get_available_methods(device.emulator or "")
        except Exception:
            logger.warning("available_methods: emulator methods probe failed", exc_info=True)
            methods = []
    elif device.device_type == Device.DeviceType.WINDOWS:
        try:
            from device_bridge.platforms import get_screenshot_handler

            handler = get_screenshot_handler()
            methods = handler.available_methods()
        except Exception:
            logger.warning("available_methods: windows methods probe failed", exc_info=True)
            methods = ["WGC", "BitBlt", "PrintWindow", "DXGI", "GDI"]

    # Persist to extra_info (fire-and-forget; failure is non-critical)
    if methods:
        try:
            extra = dict(device.extra_info or {})
            extra["available_methods"] = methods
            device.extra_info = extra
            device.save(update_fields=["extra_info"])
        except Exception as e:
            logger.warning(
                "Failed to cache available_methods for device %d: %s",
                device.id,
                e,
            )
    return methods


def _invalidate_available_methods_cache(device: Device) -> None:
    """Remove the cached available_methods so the next request redetects."""
    extra = device.extra_info or {}
    if "available_methods" not in extra:
        return
    try:
        extra = dict(extra)
        extra.pop("available_methods", None)
        device.extra_info = extra
        device.save(update_fields=["extra_info"])
    except Exception as e:
        logger.warning(
            "Failed to invalidate available_methods cache for device %d: %s",
            device.id,
            e,
        )


def _get_cached_emulator_screen_size(device_id: int) -> tuple[int, int] | None:
    cached = _EMULATOR_SCREEN_SIZE_CACHE.get(device_id)
    if cached and (time.time() - cached[1]) < _EMULATOR_SCREEN_SIZE_TTL:
        return cached[0]
    return None


def _set_cached_emulator_screen_size(device_id: int, size: tuple[int, int]) -> None:
    _EMULATOR_SCREEN_SIZE_CACHE[device_id] = (size, time.time())


def _get_emulator_native_resolution(
    device: Device,
    adb_exe: str,
) -> tuple[int, int]:
    """Query Android physical screen size via ADB ``wm size``.

    Falls back to the device's stored resolution if the ADB query fails.
    """
    device_id = device.id
    cached = _get_cached_emulator_screen_size(device_id)
    if cached:
        return cached

    serial = device.adb_serial or ""
    if not serial:
        fallback_w = device.resolution_width or 0
        fallback_h = device.resolution_height or 0
        return fallback_w, fallback_h

    try:
        proc = subprocess.run(
            [adb_exe, "-s", serial, "shell", "wm", "size"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0 and "Physical size:" in proc.stdout:
            size_str = proc.stdout.split("Physical size:")[1].strip().split()[0]
            w, h = size_str.split("x")
            size = (int(w), int(h))
            _set_cached_emulator_screen_size(device_id, size)
            return size
    except Exception as exc:
        logger.warning("Failed to query wm size for device %d: %s", device_id, exc)

    fallback_w = device.resolution_width or 0
    fallback_h = device.resolution_height or 0
    return fallback_w, fallback_h


def _scale_to_native(
    x: float,
    y: float,
    screenshot_w: int,
    screenshot_h: int,
    native_w: int,
    native_h: int,
) -> tuple[int, int]:
    """Scale screenshot coordinates to Android native screen coordinates.

    The screenshot returned by the capture pipeline may have a different
    resolution than the Android display (e.g. window client area vs.
    ``wm size``), so every coordinate sent to ADB must be scaled.
    """
    if screenshot_w > 0 and screenshot_h > 0 and native_w > 0 and native_h > 0:
        return int(x * native_w / screenshot_w), int(y * native_h / screenshot_h)
    return int(x), int(y)


def _refresh_window_handle(device: Device):
    """Find current HWND for a Windows device using stable identifiers.

    Matching priority:
      1. window_class (most stable, e.g. 'Chrome_WidgetWin_1')
      2. process_name + title substring
      3. title substring only (fallback)

    Returns refreshed hwnd (int) or None. Updates device.window_handle in DB.
    """
    from device_bridge.platforms.windows.window_info import (
        find_best_window_match,
        get_client_size,
    )

    try:
        extra = device.extra_info or {}
        target_class = extra.get("window_class", "")
        target_process = extra.get("process_name", "")
        title_keyword = extra.get("window_title", "") or device.name

        if not title_keyword:
            return None

        fresh_hwnd = find_best_window_match(
            title_keyword=title_keyword,
            target_class=target_class,
            target_process=target_process,
        )
        if not fresh_hwnd:
            return None

        def _parse_hwnd(value):
            if not value:
                return 0
            return int(value, 16) if isinstance(value, str) and value.startswith("0x") else int(value)

        if fresh_hwnd != _parse_hwnd(device.window_handle):
            device.window_handle = str(fresh_hwnd)
            size = get_client_size(fresh_hwnd)
            if size:
                device.resolution_width, device.resolution_height = size
            device.save(
                update_fields=[
                    "window_handle",
                    "resolution_width",
                    "resolution_height",
                    "updated_at",
                ]
            )
            logger.info(
                "Refreshed hwnd for device %d: %s (%dx%d)",
                device.id,
                fresh_hwnd,
                device.resolution_width,
                device.resolution_height,
            )
        return fresh_hwnd
    except Exception as e:
        logger.debug("Failed to refresh hwnd for device %d: %s", device.id, e)
        return None


# ---------------------------------------------------------------------------
# DeviceService — health check, status management
# ---------------------------------------------------------------------------

# Short-lived cache for ``adb devices`` output to avoid N subprocesses
# when the heartbeat loop checks N emulator devices in one cycle.
# TTL is 10 seconds — long enough to cover a single heartbeat sweep
# across multiple devices, short enough to detect newly connected devices.
_adb_devices_cache: str = ""
_adb_devices_cache_time: float = 0.0
_ADB_DEVICES_CACHE_TTL = 10.0


class DeviceService:
    """Device health-check and status management service.

    Encapsulates all device probing, status update, and ADB path discovery
    logic so that views (``DeviceViewSet``, etc.) only need to call service
    methods instead of duplicating the logic.
    """

    # Cached ADB path (class-level, shared across all instances).
    _cached_adb_path: str | None = None

    # ------------------------------------------------------------------
    # Health check — public API
    # ------------------------------------------------------------------

    def check_all_devices_health(self) -> list[dict]:
        """Run health checks on all devices and update DB statuses.

        Returns:
            List of per-device result dicts with keys: ``id``, ``name``,
            ``device_type``, ``old_status``, ``new_status``, ``is_online``,
            ``reason``.
        """
        results: list[dict] = []
        devices = Device.objects.select_related("agent").all()
        for device in devices:
            result = self.check_single_device_health(device)
            results.append(result)
        return results

    def check_single_device_health(self, device: Device) -> dict:
        """Run health check on a single device and update DB.

        The ``post_save`` signal (``agents.signals.broadcast_device_update``)
        automatically broadcasts ``device.updated`` when status changes, so
        we no longer need an explicit broadcast call.

        Returns:
            Dict with ``id``, ``name``, ``device_type``, ``old_status``,
            ``new_status``, ``is_online``, ``reason``.
        """
        old_status = device.status
        is_online, reason = self._probe_device(device)
        new_status = Device.Status.ONLINE if is_online else Device.Status.OFFLINE

        device.last_heartbeat = timezone.now()
        if old_status != new_status:
            device.status = new_status
        device.save(update_fields=["status", "last_heartbeat", "updated_at"])

        return {
            "id": device.id,
            "name": device.name,
            "device_type": device.device_type,
            "old_status": old_status,
            "new_status": new_status,
            "is_online": is_online,
            "reason": reason,
        }

    def update_device_status(self, device_id: int, status: str) -> Device:
        """Update a device's status directly.

        Args:
            device_id: Device primary key.
            status: One of ``Device.Status`` enum values.

        Returns:
            The updated ``Device`` instance.

        Raises:
            Device.DoesNotExist: If no device with the given ID exists.
        """
        device = Device.objects.get(pk=device_id)
        device.status = status
        device.last_heartbeat = timezone.now()
        device.save(update_fields=["status", "last_heartbeat", "updated_at"])
        return device

    # ------------------------------------------------------------------
    # Probe logic
    # ------------------------------------------------------------------

    def _probe_device(self, device: Device) -> tuple:
        """Probe a single device's actual connectivity.

        Returns:
            ``(is_online: bool, reason: str)``
        """
        reasons: list[str] = []

        if device.device_type == Device.DeviceType.WINDOWS:
            is_online, reason = self._probe_windows_device(device)
            reasons.append(reason)
        elif device.device_type == Device.DeviceType.EMULATOR:
            # Emulators: check both ADB connectivity and process
            adb_ok, adb_reason = self._probe_adb_device(device)
            reasons.append(adb_reason)
            if not adb_ok and device.extra_info:
                proc_name = device.extra_info.get("process_name", "")
                if proc_name:
                    proc_ok, proc_reason = self._probe_process(proc_name)
                    reasons.append(proc_reason)
                    if proc_ok:
                        return True, "; ".join(reasons)
            return adb_ok, "; ".join(reasons)
        else:
            return False, f"未知设备类型: {device.device_type}"

        return is_online, "; ".join(reasons)

    def _probe_windows_device(self, device: Device) -> tuple:
        """Check Windows device: IsWindow(hwnd) + process liveness."""
        from device_bridge.platforms.windows.window_info import is_window_handle_valid

        hwnd_str = device.window_handle or ""
        hwnd = None
        if hwnd_str:
            with contextlib.suppress(ValueError, TypeError):
                hwnd = int(hwnd_str, 16) if hwnd_str.startswith("0x") else int(hwnd_str)

        window_ok = False
        process_ok = False
        details: list[str] = []

        if hwnd is not None:
            window_ok = is_window_handle_valid(hwnd)
            if not window_ok:
                refreshed = _refresh_window_handle(device)
                if refreshed:
                    window_ok = True
                    hwnd = refreshed
                    hwnd_str = device.window_handle
            details.append(f"hwnd={hwnd_str}({'有效' if window_ok else '无效'})")

        extra = device.extra_info or {}
        pid = extra.get("pid")
        process_name = extra.get("process_name")

        if pid:
            process_ok = self._pid_exists(pid)
            details.append(f"pid={pid}({'存活' if process_ok else '不存在'})")
        elif process_name:
            process_ok = self._process_exists(process_name)
            details.append(f"proc='{process_name}'({'运行中' if process_ok else '未找到'})")

        is_online = window_ok or process_ok
        status_text = "在线" if is_online else "离线"
        return is_online, f"Windows {status_text}: {'; '.join(details) if details else '无检查项'}"

    def _probe_adb_device(self, device: Device) -> tuple:
        """Check ADB/emulator device via 'adb devices' command.

        Uses auto-discovered ADB path from common emulator installations,
        falling back to system PATH.
        """
        serial = device.adb_serial or ""
        if not serial:
            return False, "无 ADB 序列号"

        adb_exe = self.get_adb_path()
        output = self._get_adb_devices_output(adb_exe)
        if output is None:
            return False, "adb 命令执行失败"

        for line in output.split("\n")[1:]:
            line = line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                if parts[0] == serial:
                    state = parts[1]
                    if state == "device":
                        return True, f"ADB 在线({serial})"
                    return False, f"ADB {state}({serial})"
                if ":" in serial and parts[0].startswith("emulator-"):
                    try:
                        db_port = int(serial.split(":")[-1])
                        adb_port = int(parts[0].split("-")[-1])
                        if abs(db_port - adb_port) <= 1:
                            state = parts[1]
                            if state == "device":
                                return True, f"ADB 在线({parts[0]} ≈ {serial})"
                            return False, f"ADB {state}({parts[0]} ≈ {serial})"
                    except (ValueError, IndexError):
                        pass
        return False, f"ADB 未找到({serial})"

    def _probe_process(self, process_name: str) -> tuple[bool, str]:
        """Check whether an emulator process is still running.

        Returns:
            ``(is_running, reason)``
        """
        if self._process_exists(process_name):
            return True, f"process '{process_name}' is running"
        return False, f"process '{process_name}' not found"

    # ------------------------------------------------------------------
    # ADB path discovery
    # ------------------------------------------------------------------

    def get_adb_path(self) -> str:
        """Discover ADB executable with caching.

        Priority order:
        1. Emulator-bundled adb.exe (LDPlayer/MuMu/Nox/BlueStacks install dirs)
        2. System PATH fallback
        """
        if self._cached_adb_path:
            return self._cached_adb_path

        import shutil

        candidates = [
            r"D:\game\leidian\LDPlayer14\adb.exe",
            r"E:\game\leidian\LDPlayer14\adb.exe",
            r"C:\game\leidian\LDPlayer14\adb.exe",
            r"D:\LDPlayer14\adb.exe",
            r"E:\LDPlayer14\adb.exe",
            r"C:\LDPlayer14\adb.exe",
            r"E:\game\leidian\LDPlayer9\adb.exe",
            r"D:\leidian\LDPlayer9\adb.exe",
            r"C:\leidian\LDPlayer9\adb.exe",
            r"E:\LDPlayer\LDPlayer9\adb.exe",
            r"D:\LDPlayer\LDPlayer9\adb.exe",
            r"C:\LDPlayer\LDPlayer9\adb.exe",
            r"C:\leidian\LDPlayer4\adb.exe",
            r"D:\leidian\LDPlayer4\adb.exe",
            r"C:\Program Files\Netease\MuMu Player 12\shell\adb.exe",
            r"D:\Program Files\Netease\MuMu Player 12\shell\adb.exe",
            r"C:\Program Files\Nox\bin\adb.exe",
            r"D:\Program Files\Nox\bin\adb.exe",
            r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
        ]
        for candidate in candidates:
            expanded = os.path.expandvars(candidate)
            if os.path.isfile(expanded):
                type(self)._cached_adb_path = expanded
                return expanded

        system_adb = shutil.which("adb")
        if system_adb:
            type(self)._cached_adb_path = system_adb
            return system_adb

        type(self)._cached_adb_path = "adb"
        return "adb"

    # ------------------------------------------------------------------
    # ADB devices cache
    # ------------------------------------------------------------------

    def _get_adb_devices_output(self, adb_exe: str) -> str | None:
        """Return cached ``adb devices -l`` output, refreshing if stale.

        Returns None if the adb command fails.
        """
        global _adb_devices_cache, _adb_devices_cache_time

        now = time.monotonic()
        if _adb_devices_cache and (now - _adb_devices_cache_time) < _ADB_DEVICES_CACHE_TTL:
            return _adb_devices_cache

        try:
            proc = subprocess.run(
                [adb_exe, "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            _adb_devices_cache = proc.stdout.strip()
            _adb_devices_cache_time = now
            return _adb_devices_cache
        except FileNotFoundError:
            return None
        except subprocess.TimeoutExpired:
            return None
        except Exception:
            logger.warning("agents: _get_adb_devices unexpected error", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Process helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        """Check if a process with given PID exists."""
        try:
            import psutil

            return bool(psutil.pid_exists(pid))
        except ImportError:
            return False

    @staticmethod
    def _process_exists(name: str) -> bool:
        """Check if any process matching name exists."""
        try:
            import psutil

            name_lower = name.lower()
            return any(
                name_lower in getattr(p, "info", {}).get("name", "").lower()
                for p in psutil.process_iter(["name"])
            )
        except ImportError:
            return False
