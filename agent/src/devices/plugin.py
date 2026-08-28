"""设备插件注册机制：截图插件和输入插件可替换"""

import logging
from typing import Any, Protocol

import numpy as np

logger = logging.getLogger(__name__)


class CapturePlugin(Protocol):
    """截图插件接口协议"""

    def capture(self, device: Any) -> np.ndarray | None:
        """截取设备屏幕画面

        Args:
            device: 设备实例（WindowsDevice 或 ADBDevice）

        Returns:
            BGR 格式的 numpy 数组，失败返回 None
        """
        ...


class InputPlugin(Protocol):
    """输入插件接口协议"""

    def click(self, device: Any, x: int, y: int) -> None:
        """在设备上执行点击

        Args:
            device: 设备实例
            x: X 坐标
            y: Y 坐标
        """
        ...

    def key_press(self, device: Any, key: str) -> None:
        """在设备上执行按键

        Args:
            device: 设备实例
            key: 按键名称
        """
        ...

    def text_input(self, device: Any, text: str) -> None:
        """在设备上输入文本

        Args:
            device: 设备实例
            text: 文本内容
        """
        ...

    def swipe(self, device: Any, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> None:
        """在设备上执行滑动

        Args:
            device: 设备实例
            x1: 起始 X 坐标
            y1: 起始 Y 坐标
            x2: 终止 X 坐标
            y2: 终止 Y 坐标
            duration: 滑动持续时间（毫秒）
        """
        ...


class DevicePluginRegistry:
    """设备插件注册中心：管理截图和输入插件的注册与获取

    允许 WindowsDevice 和 ADBDevice 的截图/输入实现可替换。
    每个设备类型（如 'windows', 'adb'）可以注册专属的插件实例。
    """

    def __init__(self):
        self._capture_plugins: dict[str, CapturePlugin] = {}
        self._input_plugins: dict[str, InputPlugin] = {}

    def register_capture_plugin(self, device_type: str, plugin: CapturePlugin) -> None:
        """注册截图插件

        Args:
            device_type: 设备类型标识（如 'windows', 'adb', 'mumu'）
            plugin: 截图插件实例
        """
        self._capture_plugins[device_type] = plugin
        logger.info("已注册截图插件: device_type=%s, plugin=%s", device_type, type(plugin).__name__)

    def register_input_plugin(self, device_type: str, plugin: InputPlugin) -> None:
        """注册输入插件

        Args:
            device_type: 设备类型标识（如 'windows', 'adb', 'mumu'）
            plugin: 输入插件实例
        """
        self._input_plugins[device_type] = plugin
        logger.info("已注册输入插件: device_type=%s, plugin=%s", device_type, type(plugin).__name__)

    def get_capture_plugin(self, device_type: str) -> CapturePlugin | None:
        """获取截图插件

        Args:
            device_type: 设备类型标识

        Returns:
            截图插件实例，未注册返回 None
        """
        return self._capture_plugins.get(device_type)

    def get_input_plugin(self, device_type: str) -> InputPlugin | None:
        """获取输入插件

        Args:
            device_type: 设备类型标识

        Returns:
            输入插件实例，未注册返回 None
        """
        return self._input_plugins.get(device_type)

    def list_capture_plugins(self) -> list[str]:
        """列出所有注册的截图插件类型"""
        return list(self._capture_plugins.keys())

    def list_input_plugins(self) -> list[str]:
        """列出所有注册的输入插件类型"""
        return list(self._input_plugins.keys())

    def unregister_capture_plugin(self, device_type: str) -> bool:
        """注销截图插件

        Args:
            device_type: 设备类型标识

        Returns:
            是否成功注销
        """
        if device_type in self._capture_plugins:
            del self._capture_plugins[device_type]
            logger.info("已注销截图插件: device_type=%s", device_type)
            return True
        return False

    def unregister_input_plugin(self, device_type: str) -> bool:
        """注销输入插件

        Args:
            device_type: 设备类型标识

        Returns:
            是否成功注销
        """
        if device_type in self._input_plugins:
            del self._input_plugins[device_type]
            logger.info("已注销输入插件: device_type=%s", device_type)
            return True
        return False
