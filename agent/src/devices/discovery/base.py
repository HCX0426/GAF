"""设备发现抽象基类 — ``BaseDiscovery`` ABC 与 ``DeviceInfo`` 数据类。

Task 2.2 (2026-08-08): 所有发现器实现此接口，由 ``DeviceDiscoveryRegistry``
统一管理。取代 ``DeviceCenter`` 中直接 new 具体发现类的硬编码模式。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeviceInfo:
    """设备发现结果的数据类。

    Attributes:
        device_id: 唯一设备标识符（如 ADB serial、窗口句柄字符串）。
        name: 设备显示名称。
        device_type: 设备类型（如 ``"emulator"``、``"windows"``、``"adb"``）。
        connection_type: 连接方式（如 ``"adb"``、``"window"``）。
        address: 连接地址（ADB serial 或窗口标题）。
        extra: 额外信息（如 adb_port、install_path、hwnd 等）。
    """

    device_id: str
    name: str
    device_type: str
    connection_type: str
    address: str
    extra: dict[str, Any] = field(default_factory=dict)


class BaseDiscovery(ABC):
    """设备发现器抽象基类。

    所有设备发现器（模拟器、Windows 窗口、ADB 等）必须实现此接口。

    Example::

        class EmulatorDiscoveryAdapter(BaseDiscovery):
            @property
            def name(self) -> str:
                return "Emulator (ADB)"

            def discover(self) -> list[DeviceInfo]:
                raw = EmulatorDiscovery().discover_all()
                return [DeviceInfo(
                    device_id=e["adb_serial"],
                    name=e["name"],
                    device_type="emulator",
                    connection_type="adb",
                    address=e["adb_serial"],
                    extra=e,
                ) for e in raw]

            def is_available(self) -> bool:
                return True
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """发现器名称（用于日志和调试）。"""

    @abstractmethod
    def discover(self) -> list[DeviceInfo]:
        """执行设备扫描，返回发现的设备列表。

        Returns:
            发现的设备列表（空列表表示未发现任何设备）。

        Raises:
            DiscoveryError: 扫描过程中发生不可恢复的错误。
        """

    def is_available(self) -> bool:
        """检查该发现器所需的依赖/环境是否就绪。

        默认返回 ``True``。子类可覆盖以实现前置条件检查
        （如检查 ADB 是否在 PATH 中、是否有相应权限等）。

        Returns:
            ``True`` 表示环境就绪可以执行扫描。
        """
        return True


class DiscoveryError(Exception):
    """设备发现错误 — 发现器执行扫描时发生不可恢复的错误。"""
