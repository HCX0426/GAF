"""资源监控采集器：采集 CPU、内存、截图帧率等系统资源指标"""

import contextlib
import logging
import time

logger = logging.getLogger(__name__)

try:
    import psutil

    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False
    logger.warning("psutil 未安装，资源监控将返回默认值")


class ResourceMonitor:
    """Agent 资源监控采集器，周期性采集 CPU、内存、截图 FPS 等指标。

    当 psutil 不可用时自动降级，返回安全的默认值（-1.0），
    确保心跳消息仍可正常发送。
    """

    def __init__(self):
        """初始化资源监控器，记录截图时间戳用于 FPS 计算"""
        global _global_monitor
        self._screenshot_timestamps: list = []
        self._fps_window_seconds: float = 5.0
        # Prime the CPU counter so the next reading reflects the elapsed interval.
        # psutil.cpu_percent(interval=None) returns 0.0 on the first call and
        # measures usage since the previous call on subsequent calls.
        if _PSUTIL_AVAILABLE:
            with contextlib.suppress(Exception):
                psutil.cpu_percent(interval=None)
        # Register as the global monitor so screenshot paths can record FPS.
        _global_monitor = self

    def get_cpu_usage(self) -> float:
        """获取整机 CPU 使用率（百分比）。

        Returns:
            float: CPU 使用率百分比，若 psutil 不可用返回 -1.0
        """
        if not _PSUTIL_AVAILABLE:
            return -1.0
        try:
            # Non-blocking: compares elapsed CPU time since last call.
            return psutil.cpu_percent(interval=None)
        except Exception as exc:
            logger.debug("获取 CPU 使用率失败: %s", exc)
            return -1.0

    def get_memory_usage(self) -> float:
        """获取当前系统内存使用率（百分比）。

        Returns:
            float: 内存使用率百分比，若 psutil 不可用返回 -1.0
        """
        if not _PSUTIL_AVAILABLE:
            return -1.0
        try:
            return psutil.virtual_memory().percent
        except Exception as exc:
            logger.debug("获取内存使用率失败: %s", exc)
            return -1.0

    def get_screenshot_fps(self) -> float:
        """从截图时间戳窗口计算截图帧率（FPS）。

        取最近 fps_window_seconds 秒内的截图次数除以时间间隔。
        每次调用 capture_screen 后应调用 record_screenshot() 记录时间戳。

        Returns:
            float: 截图 FPS，若截图不足两次返回 0.0
        """
        now = time.monotonic()
        cutoff = now - self._fps_window_seconds
        self._screenshot_timestamps = [ts for ts in self._screenshot_timestamps if ts > cutoff]
        if len(self._screenshot_timestamps) < 2:
            return 0.0
        elapsed = self._screenshot_timestamps[-1] - self._screenshot_timestamps[0]
        if elapsed <= 0:
            return 0.0
        return (len(self._screenshot_timestamps) - 1) / elapsed

    def record_screenshot(self) -> None:
        """记录一次截图时间戳，用于 FPS 计算。"""
        self._screenshot_timestamps.append(time.monotonic())

    def get_stats(self) -> dict[str, float]:
        """一次性获取所有资源监控指标。

        Returns:
            Dict[str, float]: 包含 cpu、memory、fps 的字典
        """
        return {
            "cpu": self.get_cpu_usage(),
            "memory": self.get_memory_usage(),
            "fps": self.get_screenshot_fps(),
        }


# Global monitor reference used by screenshot paths to report FPS.
_global_monitor: ResourceMonitor | None = None


def record_screenshot() -> None:
    """Record a screenshot timestamp on the global ResourceMonitor.

    Called by device screenshot paths so FPS reflects the actual capture rate.
    """
    monitor = _global_monitor
    if monitor is not None:
        monitor.record_screenshot()
