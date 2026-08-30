"""设备抽象基类"""

import functools
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from core.exceptions import DeviceError

logger = logging.getLogger(__name__)


class DeviceStatus(Enum):
    """设备状态枚举"""
    IDLE = "idle"
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    BUSY = "busy"
    ERROR = "error"


def require_operable(func):
    """装饰器：确保设备处于可操作状态才执行方法"""
    @functools.wraps(func)
    def wrapper(self: "BaseDevice", *args, **kwargs):
        if self.status not in (DeviceStatus.CONNECTED, DeviceStatus.IDLE):
            raise DeviceError(
                f"设备不可操作，当前状态: {self.status.value}"
            )
        return func(self, *args, **kwargs)
    return wrapper


class BaseDevice(ABC):
    """设备抽象基类：定义所有设备必须实现的接口"""

    def __init__(self, device_id: str = "", name: str = ""):
        self._device_id = device_id
        self._name = name
        self._status = DeviceStatus.DISCONNECTED

    @property
    def device_id(self) -> str:
        """获取设备 ID"""
        return self._device_id

    @property
    def name(self) -> str:
        """获取设备名称"""
        return self._name

    @property
    def status(self) -> DeviceStatus:
        """获取设备状态"""
        return self._status

    @status.setter
    def status(self, value: DeviceStatus) -> None:
        """设置设备状态"""
        old = self._status
        self._status = value
        if old != value:
            logger.debug("设备 %s 状态变更: %s -> %s", self._device_id, old.value, value.value)

    @abstractmethod
    def connect(self) -> None:
        """连接设备"""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """断开设备连接"""
        ...

    @abstractmethod
    def capture_screen(self) -> Any:
        """截取屏幕画面"""
        ...

    @abstractmethod
    def click(self, x: int, y: int) -> None:
        """点击指定坐标。

        坐标系契约 (N191 系统性风险修复, 2026-07-27):
            子类必须在 docstring 中显式声明期望的坐标系。当前实现:
            - WindowsDevice.click: 期望 **logical** (client) 坐标。
              内部通过 `_logical_to_physical()` + `ClientToScreen()` 转 physical。
              `set_dpi_ratio()` 由 orchestrator 在构造 coord_transformer 后注入。
            - ADBDevice.click: 期望 **physical** (raw pixel) 坐标。
              无 DPI 转换,直接传给底层 ADB 命令 (MaaTouch/NemuIpc/u2/Hermit)。

            跨设备契约一致性:
            - Windows + coord_transformer 路径: publish_match_pos 输出 logical →
              WindowsDevice.click 期望 logical → ✅ 一致
            - Windows + legacy 路径 (无 transformer, DPI=100%): raw pixel ≈ logical →
              WindowsDevice.click (_dpi_ratio=1.0 不转换) → ✅ 一致
            - Windows + legacy 路径 (DPI>100%): raw physical → WindowsDevice.click
              (_dpi_ratio=1.0 不转换) → ❌ 偏移 (已知限制, legacy 模式假设 DPI=100%)
            - ADB + legacy 路径 (永远, ADB 不注入 transformer): raw physical →
              ADBDevice.click 期望 physical → ✅ 一致

            新 Device 实现必须:
            1. 在 docstring 声明期望坐标系 (logical / physical)
            2. 若期望 logical, 必须实现 `set_dpi_ratio()` 接受 orchestrator 注入
            3. 若期望 physical, 不得依赖 coord_transformer (transformer 是 Windows 专属)

        Args:
            x: X 坐标 (坐标系见上方契约)
            y: Y 坐标 (坐标系见上方契约)
        """
        ...

    @abstractmethod
    def key_press(self, key: str) -> None:
        """按下按键"""
        ...

    def key_combo(self, modifiers: list[str], key: str) -> None:
        """Press a modifier+key combo while holding the modifiers.

        Default fallback performs each key as an independent press (old
        behavior) so devices without real combo support keep working.
        WindowsDevice overrides this with true mod-down → key → mod-up.
        """
        for mod in modifiers:
            self.key_press(mod)
        self.key_press(key)

    @abstractmethod
    def text_input(self, text: str) -> None:
        """输入文本"""
        ...

    @abstractmethod
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> None:
        """滑动操作。

        坐标系契约: 同 `click()` — 子类必须显式声明期望坐标系。
        WindowsDevice.swipe 期望 logical, ADBDevice.swipe 期望 physical。

        Args:
            x1: 起始 X 坐标 (坐标系同 click)
            y1: 起始 Y 坐标
            x2: 终止 X 坐标
            y2: 终止 Y 坐标
            duration: 滑动持续时间（毫秒），默认 300ms
        """
        ...

    @abstractmethod
    def get_resolution(self) -> tuple[int, int]:
        """获取设备屏幕分辨率

        Returns:
            (width, height) 元组
        """
        ...

    def get_device_info(self) -> dict[str, Any]:
        """获取设备元信息

        Returns:
            包含设备元信息的字典，子类可覆盖以返回更多信息
        """
        return {
            "device_id": self._device_id,
            "name": self._name,
            "status": self._status.value,
            "type": self.__class__.__name__,
        }

    def exists(self, template: str = "", color: str = "") -> bool:
        """检查模板或颜色是否存在于当前屏幕"""
        return False

    def emit_coord_trace(
        self, *, step: str, raw: Any, converted: Any,
        formula: str, coord_system_in: str = "",
        coord_system_out: str = "", extra: dict[str, Any] | None = None,
    ) -> None:
        """Emit a coordinate transform trace for AI debuggability (N191).

        Default no-op implementation. Devices that support coord tracing
        (e.g. WindowsDevice) override this to forward to the input handler.
        Safe to call unconditionally — no-op when tracing is unsupported.
        """
        return None
