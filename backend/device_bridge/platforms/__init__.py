from .base import (
    DeviceInfo,
    InputResult,
    PlatformDeviceDiscoverer,
    PlatformInputHandler,
    PlatformScreenshotHandler,
    ScreenshotResult,
)
from .registry import (
    get_current_platform,
    get_device_discoverer,
    get_input_handler,
    get_screenshot_handler,
)

__all__ = [
    'ScreenshotResult',
    'InputResult',
    'DeviceInfo',
    'PlatformScreenshotHandler',
    'PlatformInputHandler',
    'PlatformDeviceDiscoverer',
    'get_screenshot_handler',
    'get_input_handler',
    'get_device_discoverer',
    'get_current_platform',
]
