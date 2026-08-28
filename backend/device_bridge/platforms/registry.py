"""
平台注册表与工厂函数
运行时检测当前操作系统，返回对应的平台实现实例
"""
from __future__ import annotations

import logging
import platform

from .base import (
    InputResult,
    PlatformDeviceDiscoverer,
    PlatformInputHandler,
    PlatformScreenshotHandler,
    ScreenshotResult,
)

logger = logging.getLogger(__name__)

_screenshot_handlers: dict[str, type[PlatformScreenshotHandler]] = {}
_input_handlers: dict[str, type[PlatformInputHandler]] = {}
_device_discoverers: dict[str, type[PlatformDeviceDiscoverer]] = {}


def get_current_platform() -> str:
    """检测当前操作系统，返回 'windows' | 'macos' | 'linux'"""
    system = platform.system().lower()
    if system == 'windows':  # noqa: SIM116
        return 'windows'
    elif system == 'darwin':
        return 'macos'
    elif system == 'linux':
        return 'linux'
    logger.warning('未知平台: %s，回退到 linux', system)
    return 'linux'


def register_screenshot_handler(platform_name: str, handler_cls: type[PlatformScreenshotHandler]) -> None:
    _screenshot_handlers[platform_name] = handler_cls


def register_input_handler(platform_name: str, handler_cls: type[PlatformInputHandler]) -> None:
    _input_handlers[platform_name] = handler_cls


def register_device_discoverer(platform_name: str, discoverer_cls: type[PlatformDeviceDiscoverer]) -> None:
    _device_discoverers[platform_name] = discoverer_cls


def get_screenshot_handler(method: str = '') -> PlatformScreenshotHandler:
    """获取当前平台的截图处理器实例"""
    platform_name = get_current_platform()
    handler_cls = _screenshot_handlers.get(platform_name)
    if handler_cls is None:
        logger.warning('平台 %s 无截图处理器注册，使用 Mock', platform_name)
        handler_cls = _MockScreenshotHandler
    return handler_cls(method=method)


def get_input_handler(method: str = '') -> PlatformInputHandler:
    """获取当前平台的输入处理器实例"""
    platform_name = get_current_platform()
    handler_cls = _input_handlers.get(platform_name)
    if handler_cls is None:
        logger.warning('平台 %s 无输入处理器注册，使用 Mock', platform_name)
        handler_cls = _MockInputHandler
    return handler_cls(method=method)


def get_device_discoverer() -> PlatformDeviceDiscoverer:
    """获取当前平台的设备发现器实例"""
    platform_name = get_current_platform()
    discoverer_cls = _device_discoverers.get(platform_name)
    if discoverer_cls is None:
        logger.warning('平台 %s 无设备发现器注册，使用 Mock', platform_name)
        discoverer_cls = _MockDeviceDiscoverer
    return discoverer_cls()


class _MockScreenshotHandler(PlatformScreenshotHandler):
    """无平台实现时的 Mock 截图处理器"""
    def __init__(self, method: str = ''):
        self.method = method or 'mock'

    def available_methods(self) -> list[str]:
        return ['mock']

    def capture(self, target: str, method: str = '') -> ScreenshotResult:
        import io

        from PIL import Image

        img = Image.new('RGB', (1920, 1080), color=(30, 30, 50))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return ScreenshotResult(
            image_bytes=buffer.getvalue(),
            latency_ms=0.0,
            resolution={'width': 1920, 'height': 1080},
            method='mock',
            success=True,
        )

    def benchmark(self, target: str, method: str, rounds: int = 10) -> dict:
        return {'method': 'mock', 'avg_ms': 0, 'min_ms': 0, 'max_ms': 0, 'fps': 0, 'success_rate': 1.0}


class _MockInputHandler(PlatformInputHandler):
    """无平台实现时的 Mock 输入处理器"""
    def __init__(self, method: str = ''):
        self.method = method or 'mock'

    def available_methods(self) -> list[str]:
        return ['mock']

    def click(self, target: str, x: int, y: int, method: str = '') -> InputResult:
        return InputResult(success=True, method='mock')

    def swipe(self, target: str, x1: int, y1: int, x2: int, y2: int,
              duration_ms: int = 300, method: str = '') -> InputResult:
        return InputResult(success=True, method='mock')

    def key_press(self, target: str, key: str, method: str = '') -> InputResult:
        return InputResult(success=True, method='mock')

    def scroll(self, target: str, x: int, y: int, delta: int, method: str = '') -> InputResult:
        return InputResult(success=True, method='mock')


class _MockDeviceDiscoverer(PlatformDeviceDiscoverer):
    """无平台实现时的 Mock 设备发现器"""
    def discover_windows(self) -> list:
        return []

    def discover_emulators(self) -> list:
        return []

    def discover_adb_devices(self) -> list:
        return []


def _auto_register() -> None:
    """启动时自动注册当前平台的实现"""
    platform_name = get_current_platform()

    if platform_name == 'windows':
        try:
            from device_bridge.platforms.windows import (
                WindowsDeviceDiscoverer,
                WindowsInputHandler,
                WindowsScreenshotHandler,
            )
            register_screenshot_handler('windows', WindowsScreenshotHandler)
            register_input_handler('windows', WindowsInputHandler)
            register_device_discoverer('windows', WindowsDeviceDiscoverer)
            logger.info('已注册 Windows 平台实现')
        except ImportError as e:
            logger.warning('Windows 平台实现导入失败: %s', e)

    elif platform_name == 'macos':
        try:
            from device_bridge.platforms.macos import (
                MacOSDeviceDiscoverer,
                MacOSInputHandler,
                MacOSScreenshotHandler,
            )
            register_screenshot_handler('macos', MacOSScreenshotHandler)
            register_input_handler('macos', MacOSInputHandler)
            register_device_discoverer('macos', MacOSDeviceDiscoverer)
            logger.info('已注册 macOS 平台实现')
        except ImportError as e:
            logger.warning('macOS 平台实现导入失败: %s', e)

    elif platform_name == 'linux':
        try:
            from device_bridge.platforms.linux import (
                LinuxDeviceDiscoverer,
                LinuxInputHandler,
                LinuxScreenshotHandler,
            )
            register_screenshot_handler('linux', LinuxScreenshotHandler)
            register_input_handler('linux', LinuxInputHandler)
            register_device_discoverer('linux', LinuxDeviceDiscoverer)
            logger.info('已注册 Linux 平台实现')
        except ImportError as e:
            logger.warning('Linux 平台实现导入失败: %s', e)


_auto_register()
