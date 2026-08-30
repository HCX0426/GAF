"""设备发现注册表 — ``DeviceDiscoveryRegistry``

注册并管理多个 ``BaseDiscovery`` 实现，提供统一的 ``discover_all()`` 入口。
支持按需注册、批量发现、可用性检查。

Task 2.2 (2026-08-08): 替代 ``DeviceCenter`` 硬编码的发现实例化方式。
"""

import logging

from devices.discovery.base import BaseDiscovery, DeviceInfo, DiscoveryError

logger = logging.getLogger(__name__)


class DeviceDiscoveryRegistry:
    """设备发现注册表 — 注册多个发现器并统一执行发现。

    Usage::

        registry = DeviceDiscoveryRegistry()
        registry.register(EmulatorDiscoveryAdapter())
        registry.register(WindowDiscoveryAdapter())
        all_devices = registry.discover_all()
    """

    def __init__(self) -> None:
        self._discoveries: list[BaseDiscovery] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, discovery: BaseDiscovery) -> None:
        """注册一个发现器。

        Args:
            discovery: 实现了 ``BaseDiscovery`` 接口的实例。

        Raises:
            ValueError: 如果已注册同名的发现器。
        """
        for existing in self._discoveries:
            if existing.name == discovery.name:
                raise ValueError(
                    f"Discovery '{discovery.name}' is already registered"
                )
        self._discoveries.append(discovery)
        logger.info("Registered discovery: %s", discovery.name)

    def unregister(self, name: str) -> None:
        """按名称注销一个发现器。

        Args:
            name: 发现器名称（``BaseDiscovery.name``）。
        """
        before = len(self._discoveries)
        self._discoveries = [d for d in self._discoveries if d.name != name]
        after = len(self._discoveries)
        if before != after:
            logger.info("Unregistered discovery: %s", name)
        else:
            logger.warning("Discovery '%s' not found, nothing to unregister", name)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @property
    def discovery_names(self) -> list[str]:
        """返回所有已注册发现器的名称列表。"""
        return [d.name for d in self._discoveries]

    def __len__(self) -> int:
        return len(self._discoveries)

    def __iter__(self):
        return iter(self._discoveries)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_all(self) -> list[DeviceInfo]:
        """遍历所有已注册发现器，汇总发现的设备。

        规则：
            1. 跳过 ``is_available()`` 返回 ``False`` 的发现器。
            2. 捕获每个发现器的异常，不影响其他发现器继续执行。
            3. 按注册顺序返回设备列表（先注册的发现器优先）。

        Returns:
            所有发现的设备列表（可能包含重复 device_id，由调用方去重）。
        """
        all_devices: list[DeviceInfo] = []
        for discovery in self._discoveries:
            if not discovery.is_available():
                logger.info(
                    "Skipping discovery '%s' (not available)", discovery.name
                )
                continue

            try:
                devices = discovery.discover()
                logger.info(
                    "Discovery '%s' found %d device(s)",
                    discovery.name, len(devices),
                )
                all_devices.extend(devices)
            except DiscoveryError as exc:
                logger.error(
                    "Discovery '%s' failed: %s", discovery.name, exc,
                )
            except Exception as exc:
                logger.exception(
                    "Discovery '%s' unexpected error: %s", discovery.name, exc,
                )

        return all_devices

    def discover_by_name(self, name: str) -> list[DeviceInfo]:
        """按发现器名称执行单个发现器的扫描。

        Args:
            name: 发现器名称。

        Returns:
            发现的设备列表。

        Raises:
            ValueError: 如果未找到指定名称的发现器。
        """
        for discovery in self._discoveries:
            if discovery.name == name:
                if not discovery.is_available():
                    logger.info(
                        "Discovery '%s' is not available", name,
                    )
                    return []
                return discovery.discover()
        raise ValueError(f"Discovery '{name}' is not registered")
