import contextlib
import logging
import os
import socket
import subprocess
from typing import Any

from core.exceptions import DeviceError
from devices.base import BaseDevice, DeviceStatus, require_operable

from .adb_constants import DROIDCAST_DEFAULT_PORT, HERMIT_DEFAULT_PORT, NEMU_DEFAULT_PORT, SCRCPY_DEFAULT_PORT
from .pool import get_adb_pool

logger = logging.getLogger(__name__)


class ADBLifecycleMixin(BaseDevice):
    """ADBDevice mixin — see devices/adb/device.py for full class (s36 split)."""

    def __init__(
        self,
        device_id: str = "adb-0",
        name: str = "ADB Device",
        serial: str = "",
        screenshot_method: str = "auto",
        input_method: str = "auto",
        droidcast_port: int = DROIDCAST_DEFAULT_PORT,
        scrcpy_port: int = SCRCPY_DEFAULT_PORT,
        nemu_port: int = NEMU_DEFAULT_PORT,
        hermit_port: int = HERMIT_DEFAULT_PORT,
        nemu_folder: str = "",
        nemu_instance_id: int = 0,
    ):
        super().__init__(device_id=device_id, name=name)
        self._serial = serial
        self._screenshot_method = screenshot_method
        self._input_method = input_method
        self._droidcast_port = droidcast_port
        self._scrcpy_port = scrcpy_port
        self._nemu_port = nemu_port
        self._hermit_port = hermit_port
        self._nemu_folder = nemu_folder
        self._nemu_instance_id = nemu_instance_id
        self._device: Any = None
        self._best_screenshot_method: str | None = None
        self._best_input_method: str | None = None
        # Per-operation best-method caches. click/swipe/key_press have
        # different fallback chains, so a single shared cache caused
        # cross-method contamination (e.g. click picks hermit, then swipe
        # silently falls back to adb while keeping hermit in the cache).
        self._best_click_method: str | None = None
        self._best_swipe_method: str | None = None
        self._best_key_method: str | None = None
        self._u2_device: Any = None
        self._scrcpy_client: Any = None
        self._maatouch_controller: Any = None
        self._minitouch_socket: socket.socket | None = None
        # Track adb forward local ports so we can remove them on disconnect.
        self._forwarded_local_ports: set[int] = set()
        # ascreencap state
        self._ascreencap_bytepointer = 0
        self._ascreencap_available = True
        # Hermit HTTP session (lazy init)
        self._hermit_session: Any = None
        # NemuIpc DLL handle and connection id (lazy init)
        self._nemu_ipc_lib: Any = None
        self._nemu_ipc_connect_id: int = 0
        self._nemu_ipc_width: int = 0
        self._nemu_ipc_height: int = 0
        # P1-3 NemuIpc keepalive controller (lazy init, started on connect)
        self._nemu_keepalive: Any = None

    def connect(self) -> None:
        """连接 ADB 设备（通过连接池复用）"""
        try:
            if self._serial:
                # 对 host:port 形式的 serial (如 127.0.0.1:5555) 先 adb connect
                # 注册 — 模拟器 adb 端口需 connect 后 adb devices 才会出现该
                # serial, 否则 adbutils adb.device() 抛 "device not found"
                # (2026-09-05 模拟器 task 按键失败根因).
                if self._is_network_serial(self._serial):
                    self._adb_connect(self._serial)
                device = get_adb_pool().get(self._serial)
                if device is None:
                    raise DeviceError(f"无法获取 ADB 设备: {self._serial}")
                self._device = device
            else:
                from adbutils import adb
                devices = adb.device_list()
                if not devices:
                    raise DeviceError("未发现 ADB 设备")
                self._device = devices[0]
                self._serial = self._device.serial

            self._status = DeviceStatus.CONNECTED
            logger.info("ADB 设备已连接: serial=%s", self._serial)
        except ImportError as exc:
            raise DeviceError("adbutils 库未安装") from exc
        except Exception as exc:
            self._status = DeviceStatus.ERROR
            raise DeviceError(f"ADB 设备连接失败: {exc}") from exc

    @staticmethod
    def _is_network_serial(serial: str) -> bool:
        """host:port 形式的网络 serial (非 emulator-N 本地别名)."""
        return ":" in serial and not serial.startswith("emulator-")

    @staticmethod
    def _adb_connect(serial: str) -> None:
        """adb connect <host:port> 注册 serial (幂等, 已连接则无副作用).

        用 emulator_discovery 发现的 adb 路径 (PATH 或模拟器安装目录), 确保
        adbutils adb.device() 能在 adb devices 列表里找到该网络 serial.
        """
        try:
            from devices.emulator_discovery import EmulatorDiscovery

            adb_path = EmulatorDiscovery._discover_adb_path() or "adb"
            result = subprocess.run(
                [adb_path, "connect", serial],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            logger.info("adb connect %s -> %s", serial, (result.stdout or result.stderr or "").strip()[:80])
        except Exception as exc:
            logger.warning("adb connect %s 失败(忽略, 继续尝试连接池): %s", serial, exc)

    def disconnect(self) -> None:
        """断开 ADB 设备连接"""
        self._cleanup_resources()
        self._device = None
        self._status = DeviceStatus.DISCONNECTED
        logger.info("ADB 设备已断开: serial=%s", self._serial)

    def _cleanup_resources(self) -> None:
        """清理所有资源连接"""
        if self._scrcpy_client is not None:
            with contextlib.suppress(Exception):
                self._scrcpy_client.stop()
            self._scrcpy_client = None

        if self._u2_device is not None:
            with contextlib.suppress(Exception):
                self._u2_device.close()
            self._u2_device = None

        if self._minitouch_socket is not None:
            with contextlib.suppress(Exception):
                self._minitouch_socket.close()
            self._minitouch_socket = None

        if self._hermit_session is not None:
            with contextlib.suppress(Exception):
                self._hermit_session.close()
            self._hermit_session = None

        # Disconnect NemuIpc DLL connection if active
        self._nemu_ipc_disconnect()

        self._maatouch_controller = None

        # Remove all adb forward port mappings we created.
        if self._device is not None and self._forwarded_local_ports:
            for port in list(self._forwarded_local_ports):
                try:
                    # adbutils Device has no direct remove_forward method;
                    # use adb forward --remove via shell.
                    self._device.shell(f"forward --remove tcp:{port}")
                except Exception as exc:
                    logger.debug("移除 forward tcp:%s 失败: %s", port, exc)
            self._forwarded_local_ports.clear()

    @require_operable
    def get_resolution(self) -> tuple[int, int]:
        """获取设备屏幕分辨率

        使用 adb shell wm size 获取当前分辨率

        Returns:
            (width, height) 元组
        """
        if not self._device:
            raise DeviceError("ADB 设备未连接")
        try:
            output = self._device.shell("wm size")
            for line in output.strip().splitlines():
                if "Physical size:" in line or "Override size:" in line:
                    parts = line.strip().split(":")[-1].strip().split("x")
                    if len(parts) == 2:
                        return (int(parts[0]), int(parts[1]))
            resolution_str = output.strip().split(":")[-1].strip().split("x")
            if len(resolution_str) == 2:
                return (int(resolution_str[0]), int(resolution_str[1]))
        except Exception as exc:
            logger.warning("获取分辨率失败: %s", exc)
        return (0, 0)

    def get_device_info(self) -> dict[str, Any]:
        """获取设备元信息"""
        info = super().get_device_info()
        info.update({
            "serial": self._serial,
            "screenshot_method": self._screenshot_method,
            "input_method": self._input_method,
            "best_screenshot_method": self._best_screenshot_method,
            "best_input_method": self._best_input_method,
            "best_click_method": self._best_click_method,
            "best_swipe_method": self._best_swipe_method,
            "best_key_method": self._best_key_method,
            "hermit_port": self._hermit_port,
            "nemu_folder": self._nemu_folder,
            "nemu_instance_id": self._nemu_instance_id,
            "nemu_ipc_connected": self._nemu_ipc_connect_id > 0,
            "nemu_keepalive_running": (
                self._nemu_keepalive.is_running
                if self._nemu_keepalive is not None
                else False
            ),
        })
        try:
            resolution = self.get_resolution()
            info["resolution"] = {"width": resolution[0], "height": resolution[1]}
        except Exception:
            info["resolution"] = None
        return info

    def reboot(self, wait_for_boot: bool = True, timeout: float = 120.0) -> bool:
        """Reboot the ADB device (soft reboot via ADB).

        Used by Layer 4 device-level recovery when emulator process is
        responsive but the Android system is in a bad state.

        Args:
            wait_for_boot: If True, wait for device to come back online
            timeout: Maximum seconds to wait for boot completion

        Returns:
            True if reboot succeeded and (optionally) boot completed
        """
        import subprocess
        import time as _time

        logger.info("Rebooting ADB device: %s", self._serial)

        # Step 1: Send reboot command
        try:
            cmd = ["adb", "-s", self._serial, "reboot"]
            subprocess.run(cmd, timeout=30, check=False, capture_output=True)
        except Exception as e:
            logger.error("ADB reboot command failed: %s", e)
            return False

        if not wait_for_boot:
            return True

        # Step 2: Wait for device to disappear then reappear
        _time.sleep(2.0)

        # Step 3: Wait for device to come back online
        try:
            cmd_wait = ["adb", "-s", self._serial, "wait-for-device"]
            subprocess.run(cmd_wait, timeout=timeout, check=False, capture_output=True)
        except subprocess.TimeoutExpired:
            logger.error("ADB wait-for-device timed out after %.0fs", timeout)
            return False
        except Exception as e:
            logger.error("ADB wait-for-device failed: %s", e)
            return False

        # Step 4: Poll for boot_completed property
        deadline = _time.time() + timeout
        cmd_getprop = ["adb", "-s", self._serial, "shell", "getprop", "sys.boot_completed"]

        while _time.time() < deadline:
            try:
                result = subprocess.run(
                    cmd_getprop,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if result.stdout.strip() == "1":
                    logger.info("ADB device %s rebooted and boot completed", self._serial)
                    return True
            except Exception:
                logger.debug("getprop sys.boot_completed probe failed, retrying", exc_info=True)
            _time.sleep(2.0)

        logger.error("ADB device %s boot did not complete within %.0fs", self._serial, timeout)
        return False
