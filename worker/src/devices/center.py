"""设备中心：统一设备管理中心，整合设备发现与管理

Task 2.2 (2026-08-08): 使用 ``DeviceDiscoveryRegistry`` 替代直接实例化
``EmulatorDiscovery`` / ``WindowDiscovery`` 的硬编码方式。新增发现器只需
注册到 registry 即可，无需修改 ``DeviceCenter`` 代码。
"""

import hashlib
import logging
import platform
from typing import Any

from devices.base import BaseDevice
from devices.discovery.adapters import create_default_registry
from devices.discovery.base import DeviceInfo
from devices.discovery.registry import DeviceDiscoveryRegistry
from devices.emulator_discovery import EmulatorDiscovery
from devices.manager import DeviceManager
from devices.plugin import DevicePluginRegistry

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == 'Windows'

if _IS_WINDOWS:
    from platforms.windows.discovery import WindowDiscovery


class DeviceCenter:
    """设备中心：统一设备管理、自动发现、插件注册

    整合 DeviceManager（设备生命周期）+ DeviceDiscoveryRegistry（设备发现注册表）
    + DevicePluginRegistry（插件注册）。提供一站式设备管理入口。

    Task 2.2: 新增发现器只需实现 ``BaseDiscovery`` 接口并注册到 registry，
    无需修改 ``DeviceCenter`` 代码。同时保留 ``_emulator_discovery`` 和
    ``_window_discovery`` 属性以兼容现有外部调用。
    """

    def __init__(self, discovery_registry: DeviceDiscoveryRegistry | None = None):
        self._manager = DeviceManager()
        self._plugin_registry = DevicePluginRegistry()

        # Use registry pattern (Task 2.2) — inject a custom registry or use default.
        self._discovery_registry = discovery_registry or create_default_registry()

        # Keep backward-compatible references for external callers that access
        # ``device_center._emulator_discovery`` or ``._window_discovery`` directly.
        self._emulator_discovery = EmulatorDiscovery()
        self._window_discovery = WindowDiscovery() if _IS_WINDOWS else None

    @property
    def manager(self) -> DeviceManager:
        """获取设备管理器"""
        return self._manager

    @property
    def plugin_registry(self) -> DevicePluginRegistry:
        """获取插件注册中心"""
        return self._plugin_registry

    @property
    def discovery_registry(self) -> DeviceDiscoveryRegistry:
        """获取设备发现注册表（Task 2.2）"""
        return self._discovery_registry

    def register_device(self, device: BaseDevice) -> None:
        """注册设备到管理器

        Args:
            device: 设备实例
        """
        self._manager.add_device(device)

    def get_device(self, device_id: str) -> BaseDevice | None:
        """根据 ID 获取设备

        Args:
            device_id: 设备 ID

        Returns:
            设备实例或 None
        """
        return self._manager.get_device(device_id)

    def list_devices(self) -> list[dict[str, str]]:
        """列出所有已注册设备"""
        return self._manager.list_devices()

    def auto_discover(self) -> list[BaseDevice]:
        """自动发现所有可用设备（模拟器 + Windows 窗口）

        使用 ``DeviceDiscoveryRegistry`` 遍历所有注册的发现器。
        去重策略：ADB 模拟器优先于 Windows 窗口设备。

        Returns:
            设备实例列表
        """
        discovered: list[BaseDevice] = []
        adb_device_names: set = set()
        emulator_types: set = set()

        # Emulator process name keywords mapping
        emulator_process_keywords = {
            "ldplayer": ["dnplayer", "leidian", "雷电"],
            "mumu": ["mumu", "nemu"],
            "bluestacks": ["bluestacks", "hd-player"],
            "nox": ["nox"],
            "memu": ["memu"],
            "xiaoyao": ["xiaoyao", "逍遥"],
        }

        # Phase 1: Discover via registry — all registered discovery adapters.
        all_devices = self._discovery_registry.discover_all()

        for dev_info in all_devices:
            try:
                if dev_info.device_type in ("emulator", "adb"):
                    device = self._create_adb_device_from_info(dev_info)
                    if device:
                        discovered.append(device)
                        self._manager.add_device(device)
                        adb_device_names.add(device.name)
                        emu_type = dev_info.extra.get("emulator_type", "adb").lower()
                        emulator_types.add(emu_type)
                        logger.info(
                            "发现 ADB 模拟器: name=%s, type=%s, serial=%s",
                            device.name, emu_type, dev_info.device_id,
                        )
                elif dev_info.device_type == "windows":
                    # Handled in Phase 2 (dedup against ADB devices)
                    pass
            except Exception as exc:
                logger.warning(
                    "创建设备失败: %s, err=%s", dev_info.name, exc,
                )

        # Phase 2: Discover Windows windows via registry, skip if covered by ADB
        if not _IS_WINDOWS:
            logger.info("非 Windows 系统，跳过窗口发现")
            return discovered

        try:
            windows_info = self._discovery_registry.discover_by_name("Windows (Window)")
        except ValueError:
            windows_info = []

        for dev_info in windows_info:
            try:
                win_title = dev_info.name
                proc_name = dev_info.extra.get("process_name", "").lower()

                if win_title in adb_device_names or any(
                    adb_name in win_title or win_title in adb_name
                    for adb_name in adb_device_names
                ):
                    logger.debug("跳过 Windows 窗口设备 '%s'（已有 ADB 设备）", win_title)
                    continue

                is_emulator_window = False
                for emu_type in emulator_types:
                    keywords = emulator_process_keywords.get(emu_type, [])
                    if any(kw in proc_name or kw in win_title.lower() for kw in keywords):
                        logger.debug("跳过模拟器窗口 '%s'（进程=%s，已有 ADB 模拟器 %s）",
                                     win_title, proc_name, emu_type)
                        is_emulator_window = True
                        break

                if is_emulator_window:
                    continue

                device = self._create_windows_device(
                    {"hwnd": dev_info.extra.get("hwnd"), "title": win_title},
                    index=len(discovered),
                )
                if device:
                    discovered.append(device)
                    self._manager.add_device(device)
                    logger.info("发现 Windows 窗口设备: name=%s", device.name)
            except Exception as exc:
                logger.warning("创建 Windows 窗口设备失败: title=%s, err=%s",
                               win_title, exc)

        logger.info("自动发现完成：共发现 %d 个设备", len(discovered))
        return discovered

    def discover_emulators(self) -> list[dict[str, Any]]:
        """发现所有模拟器（仅返回元信息，不创建设备实例）

        Returns:
            模拟器信息列表
        """
        return self._emulator_discovery.discover_all()

    def discover_windows(self) -> list[dict[str, Any]]:
        """发现所有游戏窗口（仅返回元信息，不创建设备实例）

        Returns:
            窗口信息列表
        """
        if not _IS_WINDOWS or self._window_discovery is None:
            return []
        return self._window_discovery.find_gaming_windows()

    def _create_adb_device_from_info(self, dev_info: DeviceInfo) -> BaseDevice | None:
        """根据 ``DeviceInfo`` 创建 ADBDevice 实例

        Args:
            dev_info: 发现器返回的标准化设备信息

        Returns:
            ADBDevice 实例或 None
        """
        from devices.adb.device import ADBDevice

        serial = dev_info.device_id
        if not serial:
            return None

        emu_type = dev_info.extra.get("emulator_type", "adb")
        serial_hash = hashlib.md5(serial.encode()).hexdigest()[:8]
        device = ADBDevice(
            device_id=f"adb-{emu_type}-{serial_hash}",
            name=dev_info.name,
            serial=serial,
        )
        return device

    def _create_adb_device(self, emu_info: dict[str, Any]) -> BaseDevice | None:
        """根据模拟器信息创建 ADBDevice 实例

        Args:
            emu_info: 模拟器发现返回的信息字典

        Returns:
            ADBDevice 实例或 None
        """
        from devices.adb.device import ADBDevice

        serial = emu_info.get("adb_serial", "")
        if not serial:
            return None

        # Derive stable device_id from serial hash so multi-instance emulators
        # (e.g. LDPlayer-0/1/2 with different serials) get unique IDs instead
        # of all colliding on "adb-{type}-0".
        emu_type = emu_info.get('type', 'unknown')
        serial_hash = hashlib.md5(serial.encode()).hexdigest()[:8]
        device = ADBDevice(
            device_id=f"adb-{emu_type}-{serial_hash}",
            name=emu_info.get("name", "ADB Device"),
            serial=serial,
        )
        return device

    def _create_windows_device(self, win_info: dict[str, Any], index: int = 0) -> BaseDevice | None:
        """根据窗口信息创建 WindowsDevice 实例

        Args:
            win_info: 窗口发现返回的信息字典
            index: 设备索引

        Returns:
            WindowsDevice 实例或 None
        """
        from platforms.windows.device import WindowsDevice

        title = win_info.get("title", "")
        if not title:
            return None

        # Derive stable device_id from hwnd so multi-window scenarios
        # (e.g. several game clients running simultaneously) get unique IDs
        # instead of colliding on "windows-{index}". Matches the id scheme
        # used in handler.py:521 for backend-discovered windows.
        hwnd = win_info.get("hwnd")
        if hwnd is not None:
            device_id = f"windows-hwnd-{hwnd}"
        else:
            # Fallback when hwnd unavailable (shouldn't happen for real windows)
            device_id = f"windows-title-{hashlib.md5(title.encode()).hexdigest()[:8]}"

        device = WindowsDevice(
            device_id=device_id,
            name=title,
            window_title=title,
        )
        return device
