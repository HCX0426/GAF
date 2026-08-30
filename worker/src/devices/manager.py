"""设备管理器：多设备管理"""

import logging

from devices.base import BaseDevice

logger = logging.getLogger(__name__)


class DeviceManager:
    """多设备管理器：添加、移除、查询设备"""

    def __init__(self):
        self._devices: dict[str, BaseDevice] = {}
        self._active_device_id: str | None = None

    def add_device(self, device: BaseDevice) -> None:
        """添加设备到管理器"""
        self._devices[device.device_id] = device
        if self._active_device_id is None:
            self._active_device_id = device.device_id
        logger.info("已添加设备: id=%s, name=%s", device.device_id, device.name)

    def remove_device(self, device_id: str) -> None:
        """移除设备"""
        if device_id in self._devices:
            device = self._devices.pop(device_id)
            device.disconnect()
            if self._active_device_id == device_id:
                self._active_device_id = next(iter(self._devices), None)
            logger.info("已移除设备: id=%s", device_id)

    def get_device(self, device_id: str) -> BaseDevice | None:
        """根据 ID 获取设备"""
        return self._devices.get(device_id)

    def get_active_device(self) -> BaseDevice | None:
        """获取当前活跃设备"""
        if self._active_device_id:
            return self._devices.get(self._active_device_id)
        return None

    def get_active_device_id(self) -> str | None:
        """获取当前活跃设备的 device_id (用于多设备并发恢复)。

        Returns:
            当前 active device_id, 或 None (未设置)
        """
        return self._active_device_id

    def set_active_device(self, device_id: str) -> bool:
        """设置活跃设备"""
        if device_id in self._devices:
            self._active_device_id = device_id
            logger.info("活跃设备已切换: %s", device_id)
            return True
        logger.warning("设备不存在: %s", device_id)
        return False

    def list_devices(self) -> list[dict[str, str]]:
        """列出所有设备信息"""
        return [
            {
                "device_id": d.device_id,
                "name": d.name,
                "status": d.status.value,
            }
            for d in self._devices.values()
        ]

    @property
    def device_count(self) -> int:
        """获取设备数量"""
        return len(self._devices)
