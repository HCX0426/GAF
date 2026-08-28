"""设备发现注册表 — 统一接口 + 注册机制

提供 ``BaseDiscovery`` 抽象基类和 ``DeviceDiscoveryRegistry`` 注册表，
将分散的发现逻辑（模拟器、Windows 窗口、ADB 设备）统一为注册驱动模式。

Task 2.2 (2026-08-08): 从 spec 实现，替代 ``DeviceCenter`` 中直接实例化
``EmulatorDiscovery`` / ``WindowDiscovery`` 的硬编码方式。
"""

from devices.discovery.base import BaseDiscovery, DeviceInfo
from devices.discovery.registry import DeviceDiscoveryRegistry

__all__ = [
    "BaseDiscovery",
    "DeviceInfo",
    "DeviceDiscoveryRegistry",
]
