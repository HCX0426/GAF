"""模拟器多实例同步：主控-镜像模式，一个模拟器操作同步到多个"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class EmulatorSync:
    """模拟器多实例同步控制器

    支持主控-镜像模式：在一个主模拟器上的操作（点击、按键、滑动）
    同步广播到所有已注册的镜像模拟器。

    Attributes:
        _master_device: 主控设备
        _mirrors: 镜像设备字典 {device_id: device}
        _enabled: 同步开关
    """

    def __init__(self, master_device=None):
        """初始化模拟器同步控制器

        Args:
            master_device: 主控设备实例（实现 BaseDevice 接口）
        """
        self._master_device = master_device
        self._mirrors: dict[str, object] = {}
        self._enabled = True
        self._lock = threading.Lock()
        logger.info("EmulatorSync 初始化完成")

    def set_master(self, master_device) -> None:
        """设置主控设备

        Args:
            master_device: 主控设备实例
        """
        self._master_device = master_device
        logger.info("EmulatorSync 主控设备已设置")

    def add_mirror(self, mirror_device) -> bool:
        """添加镜像设备

        Args:
            mirror_device: 镜像设备实例（实现 BaseDevice 接口）

        Returns:
            True 表示添加成功
        """
        with self._lock:
            device_id = getattr(mirror_device, 'device_id', str(id(mirror_device)))
            if device_id in self._mirrors:
                logger.warning("镜像设备已存在: %s", device_id)
                return False

            self._mirrors[device_id] = mirror_device
            logger.info("EmulatorSync 添加镜像设备: %s", device_id)
            return True

    def remove_mirror(self, device_id: str) -> bool:
        """移除镜像设备

        Args:
            device_id: 设备 ID

        Returns:
            True 表示移除成功
        """
        with self._lock:
            if device_id in self._mirrors:
                del self._mirrors[device_id]
                logger.info("EmulatorSync 移除镜像设备: %s", device_id)
                return True
            logger.warning("镜像设备不存在: %s", device_id)
            return False

    def get_mirrors(self) -> list[object]:
        """获取所有镜像设备列表

        Returns:
            镜像设备列表
        """
        with self._lock:
            return list(self._mirrors.values())

    def sync_click(self, x: int, y: int) -> None:
        """同步点击操作到所有镜像设备

        Args:
            x: 点击 X 坐标
            y: 点击 Y 坐标
        """
        if not self._enabled:
            return

        with self._lock:
            for device_id, device in self._mirrors.items():
                try:
                    if hasattr(device, 'click') and callable(device.click):
                        device.click(x, y)
                        logger.debug("sync_click -> %s: (%d, %d)", device_id, x, y)
                except Exception as exc:
                    logger.error("sync_click 失败 [%s]: %s", device_id, exc)

    def sync_key(self, key: str) -> None:
        """同步按键操作到所有镜像设备

        Args:
            key: 按键名称或键码
        """
        if not self._enabled:
            return

        with self._lock:
            for device_id, device in self._mirrors.items():
                try:
                    if hasattr(device, 'key_press') and callable(device.key_press):
                        device.key_press(key)
                        logger.debug("sync_key -> %s: %s", device_id, key)
                except Exception as exc:
                    logger.error("sync_key 失败 [%s]: %s", device_id, exc)

    def sync_swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> None:
        """同步滑动操作到所有镜像设备

        Args:
            x1: 起始 X 坐标
            y1: 起始 Y 坐标
            x2: 终止 X 坐标
            y2: 终止 Y 坐标
            duration: 滑动持续时间（毫秒）
        """
        if not self._enabled:
            return

        with self._lock:
            for device_id, device in self._mirrors.items():
                try:
                    if hasattr(device, 'swipe') and callable(device.swipe):
                        device.swipe(x1, y1, x2, y2, duration)
                        logger.debug(
                            "sync_swipe -> %s: (%d,%d)->(%d,%d) %dms",
                            device_id, x1, y1, x2, y2, duration,
                        )
                except Exception as exc:
                    logger.error("sync_swipe 失败 [%s]: %s", device_id, exc)

    def sync_text_input(self, text: str) -> None:
        """同步文本输入到所有镜像设备

        Args:
            text: 输入文本内容
        """
        if not self._enabled:
            return

        with self._lock:
            for device_id, device in self._mirrors.items():
                try:
                    if hasattr(device, 'text_input') and callable(device.text_input):
                        device.text_input(text)
                        logger.debug("sync_text_input -> %s", device_id)
                except Exception as exc:
                    logger.error("sync_text_input 失败 [%s]: %s", device_id, exc)

    def enable(self) -> None:
        """启用同步"""
        self._enabled = True
        logger.info("EmulatorSync 已启用")

    def disable(self) -> None:
        """禁用同步"""
        self._enabled = False
        logger.info("EmulatorSync 已禁用")

    @property
    def mirror_count(self) -> int:
        """获取镜像设备数量"""
        with self._lock:
            return len(self._mirrors)

    @property
    def is_enabled(self) -> bool:
        """检查同步是否启用"""
        return self._enabled

    def stop_all(self) -> None:
        """停止所有镜像设备的同步连接"""
        with self._lock:
            for device_id, device in list(self._mirrors.items()):
                try:
                    if hasattr(device, 'disconnect') and callable(device.disconnect):
                        device.disconnect()
                except Exception as exc:
                    logger.error("断开镜像设备失败 [%s]: %s", device_id, exc)
            self._mirrors.clear()
            logger.info("EmulatorSync 所有镜像设备已断开")
