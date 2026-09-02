"""Device health checker: auto-detect device online/offline status via polling.

Supports three detection strategies:
  - Windows devices: platforms.windows.window.is_window(hwnd) + psutil process check
  - ADB devices: adb devices command to verify serial connectivity
  - Emulators: combined window + process + ADB detection

Usage:
    checker = DeviceHealthChecker(interval=5.0)
    checker.add_windows_device("win-0", hwnd=123456, process_name="game.exe")
    checker.add_adb_device("adb-0", serial="127.0.0.1:7555")
    checker.start()
    status = checker.get_status("win-0")  # "online" or "offline"
    checker.on_status_change = lambda dev_id, old, new: print(f"{dev_id}: {old}->{new}")
    checker.stop()
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.constants import WorkerStatus

logger = logging.getLogger(__name__)

# Win32 window-handle check is provided by platforms.windows.window (a
# Windows-only module). On non-Windows platforms the import fails and
# _WIN32_AVAILABLE stays False, causing the hwnd check to be skipped.
# Per GAF backend-conventions §11, business code must not call
# ctypes.windll directly.
_WIN32_AVAILABLE = False
try:
    from platforms.windows.window import is_window as _is_window
    _WIN32_AVAILABLE = True
except (ImportError, AttributeError):
    logger.warning("Win32 API 不可用（非 Windows 平台），窗口句柄检测将受限")

# Type alias for status change callback
StatusChangeCallback = Callable[[str, str, str], None]


@dataclass
class DeviceHealthConfig:
    """Configuration for a single device's health check strategy."""

    device_id: str
    device_type: str  # "windows" | "emulator" | "adb"
    # Windows-specific
    hwnd: int | None = None
    process_name: str | None = None
    pid: int | None = None
    window_title: str | None = None
    # ADB-specific
    adb_serial: str | None = None
    adb_path: str | None = None  # Custom ADB executable path (overrides default)
    # Common
    extra_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthResult:
    """Result of a single health check cycle."""

    device_id: str
    is_online: bool
    status: str  # "online" | "offline" | "error"
    reason: str = ""
    latency_ms: float = 0.0
    checked_at: float = 0.0


class DeviceHealthChecker:
    """Background service that polls device health at configurable intervals.

    Maintains an internal cache of last-known statuses and fires callbacks
    when a device transitions between online/offline states.
    """

    def __init__(self, interval: float = 30.0, adb_path: str | None = None):
        """Initialize health checker.

        Args:
            interval: Polling interval in seconds (default 30.0)

                Changed from 5.0 to 30.0 on 2026-07-11 (N154 black screen
                incident). The previous 5s interval, combined with per-device
                `adb devices` subprocess calls, caused adb.exe crash dialogs
                and GPU driver instability when multiple emulators were
                registered. 30s matches the backend heartbeat interval.

            adb_path: Custom ADB executable path. If None, auto-discovers
                      from common emulator install locations.
        """
        self._interval = interval
        self._adb_path = adb_path or self._discover_adb()
        self._devices: dict[str, DeviceHealthConfig] = {}
        self._status_cache: dict[str, HealthResult] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._psutil_available: bool | None = None
        # Callback fired on status transition: (device_id, old_status, new_status)
        self.on_status_change: StatusChangeCallback | None = None
        # Cached `adb devices -l` output to avoid spawning one subprocess per
        # device per polling cycle (N154 fix — same pattern as backend
        # DeviceViewSet._get_adb_devices_output).
        self._adb_devices_cache: str = ""
        self._adb_devices_cache_time: float = 0.0
        self._ADB_DEVICES_CACHE_TTL: float = 10.0

    @staticmethod
    def _discover_adb() -> str | None:
        """Auto-discover ADB executable from common emulator installations.

        Search order (changed 2026-07-11 — black screen incident):
        1. Emulator-bundled adb.exe (guaranteed protocol compatibility with adbd)
        2. System PATH fallback

        Previously system PATH was tried first, but a mismatched adb version
        (e.g. Android SDK platform-tools) could conflict with the emulator's
        adbd daemon, causing repeated adb.exe crash dialogs.
        """
        import os
        import shutil

        # Priority 1: emulator-bundled adb (protocol-compatible with adbd)
        candidates = [
            # LDPlayer 14 (current common install path)
            r"D:\game\leidian\LDPlayer14\adb.exe",
            r"E:\game\leidian\LDPlayer14\adb.exe",
            r"C:\game\leidian\LDPlayer14\adb.exe",
            r"D:\LDPlayer14\adb.exe",
            r"E:\LDPlayer14\adb.exe",
            r"C:\LDPlayer14\adb.exe",
            # LDPlayer 9
            r"E:\game\leidian\LDPlayer9\adb.exe",
            r"D:\leidian\LDPlayer9\adb.exe",
            r"C:\leidian\LDPlayer9\adb.exe",
            r"E:\LDPlayer\LDPlayer9\adb.exe",
            r"D:\LDPlayer\LDPlayer9\adb.exe",
            r"C:\LDPlayer\LDPlayer9\adb.exe",
            # LDPlayer older versions
            r"C:\leidian\LDPlayer4\adb.exe",
            r"D:\leidian\LDPlayer4\adb.exe",
            # MuMu 12
            r"C:\Program Files\Netease\MuMu Player 12\shell\adb.exe",
            r"D:\Program Files\Netease\MuMu Player 12\shell\adb.exe",
            # Nox
            r"C:\Program Files\Nox\bin\adb.exe",
            r"D:\Program Files\Nox\bin\adb.exe",
            # BlueStacks
            r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
        ]
        for candidate in candidates:
            expanded = os.path.expandvars(candidate)
            if os.path.isfile(expanded):
                logger.info("ADB found at: %s", expanded)
                return expanded

        # Priority 2: system PATH fallback
        system_adb = shutil.which('adb')
        if system_adb:
            logger.info("ADB found in PATH: %s", system_adb)
            return system_adb

        # Android SDK (last resort)
        sdk_path = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe")
        if os.path.isfile(sdk_path):
            logger.info("ADB found in Android SDK: %s", sdk_path)
            return sdk_path

        logger.warning("ADB not found in PATH or common emulator paths")
        return None

    def _check_psutil(self) -> bool:
        """Lazy-check psutil availability (cached after first call)."""
        if self._psutil_available is not None:
            return self._psutil_available
        try:
            import psutil  # noqa: F401
            self._psutil_available = True
            return True
        except ImportError:
            self._psutil_available = False
            logger.warning("psutil 未安装，进程检测功能将受限")
            return False

    def add_device(self, config: DeviceHealthConfig) -> None:
        """Register a device for health monitoring.

        Args:
            config: Device health configuration
        """
        with self._lock:
            self._devices[config.device_id] = config
            self._status_cache[config.device_id] = HealthResult(
                device_id=config.device_id,
                is_online=False,
                status="offline",
                reason="未检测",
            )
        logger.info("注册设备健康检查: id=%s, type=%s", config.device_id, config.device_type)

    def add_windows_device(
        self,
        device_id: str,
        hwnd: int | None = None,
        process_name: str | None = None,
        pid: int | None = None,
        window_title: str | None = None,
    ) -> None:
        """Convenience method to register a Windows device.

        Args:
            device_id: Unique device identifier
            hwnd: Window handle (int or hex string)
            process_name: Process name to check for liveness
            pid: Process ID to check directly
            window_title: Window title (for logging)
        """
        if isinstance(hwnd, str):
            try:
                hwnd = int(hwnd, 16) if hwnd.startswith("0x") else int(hwnd)
            except (ValueError, TypeError):
                hwnd = None
        config = DeviceHealthConfig(
            device_id=device_id,
            device_type="windows",
            hwnd=hwnd,
            process_name=process_name,
            pid=pid,
            window_title=window_title,
        )
        self.add_device(config)

    def add_adb_device(
        self,
        device_id: str,
        adb_serial: str,
        device_type: str = "adb",
        window_title: str | None = None,
    ) -> None:
        """Convenience method to register an ADB/emulator device.

        Args:
            device_id: Unique device identifier
            adb_serial: ADB serial string (e.g. "127.0.0.1:7555")
            device_type: Device subtype ("adb" or "emulator")
            window_title: Optional window title for emulator window
                existence check. When set, the health checker will also
                verify the emulator window is visible before reporting
                the device as online. N197: 雷电模拟器窗口关闭后,
                ADB 进程可能仍在运行, 需结合窗口存在性判断.
        """
        config = DeviceHealthConfig(
            device_id=device_id,
            device_type=device_type,
            adb_serial=adb_serial,
            window_title=window_title,
        )
        self.add_device(config)

    def remove_device(self, device_id: str) -> None:
        """Unregister a device from health monitoring.

        Args:
            device_id: Device identifier to remove
        """
        with self._lock:
            self._devices.pop(device_id, None)
            self._status_cache.pop(device_id, None)
        logger.info("移除设备健康检查: %s", device_id)

    def get_status(self, device_id: str) -> HealthResult | None:
        """Get cached health result for a device.

        Args:
            device_id: Device identifier

        Returns:
            Cached HealthResult or None if device not registered
        """
        with self._lock:
            return self._status_cache.get(device_id)

    def get_all_statuses(self) -> dict[str, HealthResult]:
        """Get all cached health results.

        Returns:
            Dict mapping device_id to HealthResult
        """
        with self._lock:
            return dict(self._status_cache)

    def start(self) -> None:
        """Start background polling thread."""
        if self._running:
            logger.warning("Health checker already running")
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("设备健康检查已启动，间隔=%.1fs，监控 %d 个设备", self._interval, len(self._devices))

    def stop(self) -> None:
        """Stop background polling thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._interval + 2)
        logger.info("设备健康检查已停止")

    def check_once(self, device_id: str) -> HealthResult | None:
        """Perform a single health check for one device (synchronous).

        Args:
            device_id: Device to check

        Returns:
            HealthResult or None if device not found
        """
        config = self._devices.get(device_id)
        if config is None:
            return None
        result = self._check_device(config)
        with self._lock:
            old_result = self._status_cache.get(device_id)
            self._status_cache[device_id] = result
        # Fire callback on status transition
        if old_result and old_result.status != result.status:
            self._fire_callback(device_id, old_result.status, result.status)
        return result

    def check_all(self) -> list[HealthResult]:
        """Perform a single health check for all registered devices.

        Returns:
            List of HealthResult for all devices
        """
        results = []
        with self._lock:
            devices_snapshot = dict(self._devices)
        for config in devices_snapshot.values():
            result = self._check_device(config)
            with self._lock:
                old_result = self._status_cache.get(config.device_id)
                self._status_cache[config.device_id] = result
            if old_result and old_result.status != result.status:
                self._fire_callback(config.device_id, old_result.status, result.status)
            results.append(result)
        return results

    def _poll_loop(self) -> None:
        """Background polling loop, runs in daemon thread."""
        while self._running:
            try:
                self.check_all()
            except Exception as exc:
                logger.exception("健康检查轮询异常: %s", exc)
            time.sleep(self._interval)

    def _get_adb_devices_output(self, adb_exe: str) -> str | None:
        """Return cached `adb devices -l` output, refreshing if stale.

        N154 fix: avoids spawning one subprocess per device per polling
        cycle. The TTL is 10s — long enough to cover a single check_all()
        sweep across multiple devices, short enough to detect newly
        connected devices.
        """
        now = time.monotonic()
        if self._adb_devices_cache and (now - self._adb_devices_cache_time) < self._ADB_DEVICES_CACHE_TTL:
            return self._adb_devices_cache

        try:
            proc = subprocess.run(
                [adb_exe, 'devices', '-l'],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self._adb_devices_cache = proc.stdout.strip()
            self._adb_devices_cache_time = now
            return self._adb_devices_cache
        except FileNotFoundError:
            return None
        except subprocess.TimeoutExpired:
            return None
        except Exception as exc:
            logger.warning("adb devices probe failed: %s", exc, exc_info=True)
            return None

    def _fire_callback(self, device_id: str, old_status: str, new_status: str) -> None:
        """Invoke status change callback if set."""
        if self.on_status_change:
            try:
                self.on_status_change(device_id, old_status, new_status)
            except Exception as exc:
                logger.error("状态变更回调异常: device=%s, err=%s", device_id, exc)

    def _check_device(self, config: DeviceHealthConfig) -> HealthResult:
        """Execute health check for a single device based on its type.

        Args:
            config: Device health configuration

        Returns:
            HealthResult with current status
        """
        start = time.monotonic()
        try:
            if config.device_type == "windows":
                result = self._check_windows_device(config)
            elif config.device_type in ("adb", "emulator"):
                result = self._check_adb_device(config)
            else:
                result = HealthResult(
                    device_id=config.device_id,
                    is_online=False,
                    status="error",
                    reason=f"未知设备类型: {config.device_type}",
                )
        except Exception as exc:
            result = HealthResult(
                device_id=config.device_id,
                is_online=False,
                status="error",
                reason=f"检查异常: {exc}",
            )
        result.latency_ms = (time.monotonic() - start) * 1000
        result.checked_at = time.time()
        return result

    def _check_windows_device(self, config: DeviceHealthConfig) -> HealthResult:
        """Check Windows device health via IsWindow + process liveness.

        A Windows device is considered ONLINE when:
        - Its window handle (hwnd) is valid (IsWindow returns True), OR
        - Its process is still running (pid or process_name match), OR
        - At least one check passes (window OR process)

        It is OFFLINE when both window AND process checks fail.
        """
        reasons = []
        window_ok = False
        process_ok = False

        # Check 1: Window handle validity (Windows-only)
        if config.hwnd is not None:
            if _WIN32_AVAILABLE:
                try:
                    window_ok = _is_window(config.hwnd)
                    if window_ok:
                        reasons.append(f"窗口句柄有效(hwnd={config.hwnd:#x})")
                    else:
                        reasons.append(f"窗口句柄无效(hwnd={config.hwnd:#x})")
                except Exception as exc:
                    reasons.append(f"窗口检查异常: {exc}")
            else:
                reasons.append("无法加载 user32（非 Windows）")

        # Check 2: Process liveness (cross-platform via psutil)
        if config.pid is not None:
            if self._check_psutil():
                import psutil
                try:
                    process_ok = psutil.pid_exists(config.pid)
                    if process_ok:
                        reasons.append(f"进程存活(pid={config.pid})")
                    else:
                        reasons.append(f"进程不存在(pid={config.pid})")
                except Exception as exc:
                    reasons.append(f"PID 检查异常: {exc}")
            else:
                reasons.append(f"psutil 不可用，跳过 PID 检查(pid={config.pid})")

        # Check 3: Process name search (fallback if no PID)
        if not process_ok and config.process_name and self._check_psutil():
            import psutil
            try:
                found = any(
                    config.process_name.lower() in p.name().lower()
                    for p in psutil.process_iter(['name'])
                )
                if found:
                    process_ok = True
                    reasons.append(f"进程名匹配('{config.process_name}')")
                else:
                    reasons.append(f"进程名未找到('{config.process_name}')")
            except Exception as exc:
                reasons.append(f"进程名搜索异常: {exc}")

        # Determine overall status
        is_online = window_ok or process_ok
        status = "online" if is_online else "offline"

        return HealthResult(
            device_id=config.device_id,
            is_online=is_online,
            status=status,
            reason="; ".join(reasons) if reasons else "无检查项",
        )

    def _check_adb_device(self, config: DeviceHealthConfig) -> HealthResult:
        """Check ADB/emulator device health via 'adb devices' command.

        An ADB device is considered ONLINE when its serial appears in
        'adb devices' output with status 'device'.
        For emulator types, also attempts supplementary checks.

        N154 fix: uses cached `adb devices` output to avoid spawning one
        subprocess per device per polling cycle. The cache TTL is 10s,
        shared across all devices in a single check_all() sweep.
        """
        if not config.adb_serial:
            return HealthResult(
                device_id=config.device_id,
                is_online=False,
                status="error",
                reason="缺少 ADB 序列号",
            )

        reasons = []

        # Resolve ADB executable: per-device override > class-level discovered > system PATH
        adb_exe = config.adb_path or self._adb_path or 'adb'

        # Primary check: adb devices command (cached to avoid subprocess storm)
        output = self._get_adb_devices_output(adb_exe)
        if output is not None:
            serial_online = False
            for line in output.split('\n')[1:]:
                line = line.strip()
                if not line or line.startswith('*'):
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[0] == config.adb_serial:
                    if parts[1] == 'device':
                        serial_online = True
                        reasons.append(f"ADB 在线({config.adb_serial})")
                    elif parts[1] == WorkerStatus.OFFLINE.value:
                        reasons.append(f"ADB 离线({config.adb_serial}={parts[1]})")
                    else:
                        reasons.append(f"ADB 异常状态({config.adb_serial}={parts[1]})")
                    break

            if not serial_online and not any('ADB' in r for r in reasons):
                reasons.append(f"ADB 设备未找到({config.adb_serial})")
        else:
            reasons.append(f"adb 命令执行失败({adb_exe})")

        # Supplementary check for emulator: process liveness
        if config.device_type == "emulator" and config.process_name and self._check_psutil():
            import psutil
            try:
                found = any(
                    config.process_name.lower() in p.name().lower()
                    for p in psutil.process_iter(['name'])
                )
                if found:
                    reasons.append(f"模拟器进程运行中('{config.process_name}')")
            except Exception as e:
                logger.debug("process_name check failed for %r: %r", config.process_name, e)

        # N197: 模拟器窗口存在性检查 — 窗口关闭后即使 ADB 进程仍在,
        # 设备也应标记为 offline (无法自动化操作).
        if config.device_type == "emulator" and config.window_title:
            if _WIN32_AVAILABLE:
                try:
                    from platforms.windows.window import find_window_by_title
                    hwnd = find_window_by_title(config.window_title)
                    window_ok = _is_window(hwnd) if hwnd else False
                    if window_ok:
                        reasons.append(f"模拟器窗口存在(title='{config.window_title}')")
                    else:
                        reasons.append(f"模拟器窗口不存在(title='{config.window_title}')")
                except Exception as exc:
                    reasons.append(f"模拟器窗口检查异常: {exc}")
            else:
                reasons.append("非 Windows 平台，跳过窗口检查")

        # 窗口存在性检查覆盖 ADB 在线状态:
        # 如果配置了 window_title 且窗口检查确定不存在, 即使 ADB 响应, 也判 offline.
        window_checked_and_gone = any("窗口不存在" in r for r in reasons)
        is_online = any('在线' in r or '运行中' in r for r in reasons) and not window_checked_and_gone
        status = "online" if is_online else "offline"

        return HealthResult(
            device_id=config.device_id,
            is_online=is_online,
            status=status,
            reason="; ".join(reasons) if reasons else "无检查结果",
        )

    @property
    def is_running(self) -> bool:
        """Whether the background poller is active."""
        return self._running

    @property
    def device_count(self) -> int:
        """Number of registered devices."""
        return len(self._devices)

    @property
    def interval(self) -> float:
        """Current polling interval."""
        return self._interval

    @interval.setter
    def interval(self, value: float) -> None:
        """Update polling interval (takes effect next cycle)."""
        if value > 0:
            self._interval = value
