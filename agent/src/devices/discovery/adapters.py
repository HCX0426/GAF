"""设备发现适配器 — 包装现有发现逻辑为 ``BaseDiscovery`` 接口。

Task 2.2 (2026-08-08): 将 ``EmulatorDiscovery``、``WindowDiscovery`` 等现有
发现类包装为 ``BaseDiscovery`` 实现，注册到 ``DeviceDiscoveryRegistry``。

适配器本身不包含发现逻辑，只做接口适配和类型转换。
"""

import logging

from devices.discovery.base import BaseDiscovery, DeviceInfo
from devices.emulator_discovery import EmulatorDiscovery

logger = logging.getLogger(__name__)

# 尝试导入 Windows 相关模块（仅在 Windows 平台可用）
try:
    from platforms.windows.discovery import WindowDiscovery as _WindowDiscovery
    _HAS_WINDOWS = True
except ImportError:
    _HAS_WINDOWS = False


class EmulatorDiscoveryAdapter(BaseDiscovery):
    """模拟器发现适配器 — 包装 ``EmulatorDiscovery``。

    通过 ADB 端口扫描、注册表、进程检测等方式发现各类模拟器
    （LDPlayer、MuMu、BlueStacks、Nox、MEmu 等）。
    """

    def __init__(self) -> None:
        self._inner = EmulatorDiscovery()

    @property
    def name(self) -> str:
        return "Emulator (ADB)"

    def discover(self) -> list[DeviceInfo]:
        raw_devices = self._inner.discover_all()
        return [
            DeviceInfo(
                device_id=d["adb_serial"],
                name=d["name"],
                device_type="emulator",
                connection_type="adb",
                address=d["adb_serial"],
                extra={
                    "adb_port": d.get("adb_port", 0),
                    "install_path": d.get("install_path", ""),
                    "emulator_type": d.get("type", ""),
                    "discovery_source": d.get("discovery_source", ""),
                },
            )
            for d in raw_devices
        ]

    def is_available(self) -> bool:
        return True


class WindowDiscoveryAdapter(BaseDiscovery):
    """Windows 窗口发现适配器 — 包装 ``WindowDiscovery``。

    通过枚举 Windows 顶层窗口，按游戏关键词过滤发现游戏窗口。
    仅在 Windows 平台可用。
    """

    def __init__(self) -> None:
        if not _HAS_WINDOWS:
            self._inner = None
        else:
            self._inner = _WindowDiscovery()

    @property
    def name(self) -> str:
        return "Windows (Window)"

    def discover(self) -> list[DeviceInfo]:
        if self._inner is None:
            return []

        windows = self._inner.find_gaming_windows()
        return [
            DeviceInfo(
                device_id=str(w["hwnd"]),
                name=w.get("title", f"Window #{w.get('hwnd', 0)}"),
                device_type="windows",
                connection_type="window",
                address=w.get("title", ""),
                extra={
                    "hwnd": w.get("hwnd", 0),
                    "process_name": w.get("process_name", ""),
                    "rect": w.get("rect", {}),
                },
            )
            for w in windows
        ]

    def is_available(self) -> bool:
        return self._inner is not None


class ADBPortScanAdapter(BaseDiscovery):
    """ADB 端口扫描适配器 — 直接扫描 ADB 端口发现设备。

    作为模拟器发现的补充，当注册表/进程检测未发现设备时，
    通过扫描 ADB 端口范围（5554-5684）发现连接的 ADB 设备。
    """

    def __init__(self) -> None:
        self._inner = EmulatorDiscovery()

    @property
    def name(self) -> str:
        return "ADB (Port Scan)"

    def discover(self) -> list[DeviceInfo]:
        ports = self._inner.scan_adb_ports()
        return [
            DeviceInfo(
                device_id=serial,
                name=f"ADB Device ({serial})",
                device_type="adb",
                connection_type="adb",
                address=serial,
                extra={"adb_port": int(serial.split(":")[-1])},
            )
            for serial in ports
        ]

    def is_available(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# 工厂函数：创建预配置的注册表
# ---------------------------------------------------------------------------

def create_default_registry():
    """创建默认设备发现注册表，注册所有内置发现器。

    注册顺序（优先级）：
        1. ``EmulatorDiscoveryAdapter`` — 模拟器发现（ADB + 注册表 + 进程）
        2. ``WindowDiscoveryAdapter`` — Windows 窗口发现（仅在 Windows 可用）
        3. ``ADBPortScanAdapter`` — ADB 端口扫描补充

    Returns:
        配置好的 ``DeviceDiscoveryRegistry`` 实例。
    """
    from devices.discovery.registry import DeviceDiscoveryRegistry

    registry = DeviceDiscoveryRegistry()
    registry.register(EmulatorDiscoveryAdapter())
    if _HAS_WINDOWS:
        registry.register(WindowDiscoveryAdapter())
    registry.register(ADBPortScanAdapter())
    return registry
