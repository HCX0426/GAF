"""
截图 Handler 模块（向后兼容）
已迁移到 agent.platforms 抽象层，此模块保留以兼容旧代码
"""
import base64
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ScreenshotResult:
    """截图结果（向后兼容旧格式）"""
    screenshot_base64: str = ''
    latency_ms: float = 0.0
    fps: float = 0.0
    resolution: dict = field(default_factory=lambda: {'width': 0, 'height': 0})
    screenshot_method: str = ''
    success: bool = False
    error: str | None = None


class ScreenshotHandler:
    """截图处理器（向后兼容，委托到 platforms 抽象层）"""

    def __init__(self, screenshot_method: str = 'default'):
        self.screenshot_method = screenshot_method
        self._fps_samples: list = []
        self._max_samples = 30

    def capture_base64(self) -> ScreenshotResult:
        """执行截图并测量延迟，返回 base64 编码结果"""
        from device_bridge.platforms import get_screenshot_handler

        handler = get_screenshot_handler(method=self.screenshot_method)
        result = handler.capture(target='', method=self.screenshot_method)

        if result.success and result.image_bytes:
            screenshot_base64 = base64.b64encode(result.image_bytes).decode('utf-8')
            return ScreenshotResult(
                screenshot_base64=screenshot_base64,
                latency_ms=result.latency_ms,
                fps=result.fps,
                resolution=result.resolution,
                screenshot_method=result.method,
                success=True,
            )
        return ScreenshotResult(
            latency_ms=result.latency_ms,
            screenshot_method=result.method,
            success=False,
            error=result.error,
        )

    def _do_capture(self) -> dict:
        return {'success': False, 'error': '已迁移到 platforms 抽象层'}

    def _update_fps(self, t_start: float, t_end: float) -> None:
        elapsed = t_end - t_start
        if elapsed > 0:
            self._fps_samples.append(1.0 / elapsed)
            if len(self._fps_samples) > self._max_samples:
                self._fps_samples.pop(0)

    def _get_avg_fps(self) -> float:
        if not self._fps_samples:
            return 0.0
        return sum(self._fps_samples) / len(self._fps_samples)
