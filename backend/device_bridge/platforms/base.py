"""
跨平台设备抽象接口
定义截图、输入、设备发现三个核心 ABC，所有平台实现必须继承这些接口
参考：MaaFramework 的平台抽象层设计（编译时平台选择 → GAF 改为运行时检测）
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ScreenshotResult:
    """截图操作结果"""
    image_bytes: bytes = b''
    latency_ms: float = 0.0
    fps: float = 0.0
    resolution: dict = field(default_factory=lambda: {'width': 0, 'height': 0})
    method: str = ''
    success: bool = False
    error: str | None = None


@dataclass
class InputResult:
    """输入操作结果"""
    success: bool = False
    latency_ms: float = 0.0
    method: str = ''
    error: str | None = None


@dataclass
class DeviceInfo:
    """发现的设备信息（统一格式，跨平台通用）"""
    name: str
    device_type: str  # 'window' | 'emulator' | 'adb'
    identifier: str   # hwnd / adb_serial / window_id
    resolution: dict = field(default_factory=lambda: {'width': 0, 'height': 0})
    platform: str = ''  # 'windows' | 'macos' | 'linux'
    extra: dict = field(default_factory=dict)


class PlatformScreenshotHandler(ABC):
    """截图处理器抽象基类"""

    @abstractmethod
    def available_methods(self) -> list[str]:
        """返回当前平台可用的截图方式列表（按推荐优先级排序）"""
        ...

    @abstractmethod
    def capture(self, target: str, method: str = '') -> ScreenshotResult:
        """
        执行截图

        Args:
            target: 截图目标标识（Windows=hwnd, ADB=serial, macOS=window_id）
            method: 截图方式，空字符串表示使用默认方式
        Returns:
            ScreenshotResult
        """
        ...

    @abstractmethod
    def benchmark(self, target: str, method: str, rounds: int = 10) -> dict:
        """
        对指定截图方式进行基准测试

        Returns:
            {'method': str, 'avg_ms': float, 'min_ms': float, 'max_ms': float, 'fps': float, 'success_rate': float}
        """
        ...


class PlatformInputHandler(ABC):
    """输入处理器抽象基类"""

    @abstractmethod
    def available_methods(self) -> list[str]:
        """返回当前平台可用的输入方式列表（按推荐优先级排序）"""
        ...

    @abstractmethod
    def click(self, target: str, x: int, y: int, method: str = '') -> InputResult:
        """
        执行点击

        Args:
            target: 输入目标标识（Windows=hwnd, ADB=serial）
            x: 点击 X 坐标
            y: 点击 Y 坐标
            method: 输入方式，空字符串表示使用默认方式
        Returns:
            InputResult
        """
        ...

    @abstractmethod
    def swipe(self, target: str, x1: int, y1: int, x2: int, y2: int,
              duration_ms: int = 300, method: str = '') -> InputResult:
        """
        执行滑动

        Args:
            target: 输入目标标识
            x1, y1: 起点坐标
            x2, y2: 终点坐标
            duration_ms: 滑动持续时间
            method: 输入方式
        Returns:
            InputResult
        """
        ...

    @abstractmethod
    def key_press(self, target: str, key: str, method: str = '') -> InputResult:
        """
        执行按键

        Args:
            target: 输入目标标识
            key: 按键名称（如 'enter', 'esc', 'a'）
            method: 输入方式
        Returns:
            InputResult
        """
        ...

    @abstractmethod
    def scroll(self, target: str, x: int, y: int, delta: int,
               method: str = '') -> InputResult:
        """
        执行滚轮滚动

        Args:
            target: 输入目标标识
            x: 滚动位置 X 坐标
            y: 滚动位置 Y 坐标
            delta: 滚动量（正值向上/正值向前，负值向下/负值向后）
            method: 输入方式
        Returns:
            InputResult
        """
        ...


class PlatformDeviceDiscoverer(ABC):
    """设备发现器抽象基类"""

    @abstractmethod
    def discover_windows(self) -> list[DeviceInfo]:
        """发现 PC 窗口设备"""
        ...

    @abstractmethod
    def discover_emulators(self) -> list[DeviceInfo]:
        """发现模拟器设备（通过进程扫描+ADB）"""
        ...

    @abstractmethod
    def discover_adb_devices(self) -> list[DeviceInfo]:
        """发现 ADB 连接的设备（adb devices）"""
        ...
