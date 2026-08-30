"""Window state monitoring — foreground detection and background-wait support.

This module provides two monitors:

1. ``WindowMonitor`` — General-purpose foreground change detector.
   Polls GetForegroundWindow() and fires registered callbacks when the
   foreground window changes. Used by the monitoring subsystem for
   detecting window switches during task execution.

2. ``WindowBackgroundMonitor`` — Pipeline pause/resume controller.
   When ``wait_when_background`` is enabled, the orchestrator starts
   this monitor during pipeline execution. It polls
   ``device.is_foreground()`` and:
   - Window loses foreground → engine.pause() + on_pause callback
   - Window regains foreground → engine.resume() + on_resume callback
   - Timeout exceeded → engine.cancel() + on_timeout callback
"""
import ctypes
import ctypes.wintypes
import logging
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32


class WindowMonitor:
    """窗口状态监控器，检测窗口状态变化"""

    def __init__(self, window_manager):
        """初始化窗口监控器

        Args:
            window_manager: WindowManager 实例
        """
        self._window_manager = window_manager
        self._callbacks: list[Callable] = []
        self._last_foreground_hwnd: int | None = None
        self._monitor_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._check_interval: float = 0.5

    def check_foreground(self, expected_title: str) -> bool:
        """检查目标窗口是否在前台

        Args:
            expected_title: 期望的窗口标题（模糊匹配）

        Returns:
            目标窗口在前台返回 True
        """
        foreground_hwnd = user32.GetForegroundWindow()
        if foreground_hwnd == 0:
            return False

        buf_len = user32.GetWindowTextLengthW(foreground_hwnd)
        if buf_len == 0:
            return False

        buf = ctypes.create_unicode_buffer(buf_len + 1)
        user32.GetWindowTextW(foreground_hwnd, buf, buf_len + 1)
        current_title = buf.value

        is_match = expected_title.lower() in current_title.lower()
        if not is_match:
            logger.debug(
                "窗口不在前台: expected=%s, current=%s",
                expected_title, current_title,
            )
        return is_match

    def wait_foreground(self, expected_title: str, timeout: float = 10.0) -> bool:
        """等待窗口到前台

        Args:
            expected_title: 期望的窗口标题
            timeout: 超时时间（秒）

        Returns:
            在超时前窗口到达前台返回 True
        """
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout:
            if self.check_foreground(expected_title):
                logger.info("窗口已到前台: %s", expected_title)
                return True
            time.sleep(0.2)

        logger.warning("等待窗口前台超时: %s (%.1fs)", expected_title, timeout)
        return False

    def on_window_change(self, callback: Callable[[int, int], None]) -> None:
        """注册窗口变化回调

        当前台窗口发生变化时，回调函数将被调用，参数为 (旧句柄, 新句柄)

        Args:
            callback: 回调函数，签名为 callback(old_hwnd, new_hwnd)
        """
        self._callbacks.append(callback)
        logger.debug("已注册窗口变化回调，当前共 %d 个", len(self._callbacks))

    def start_monitoring(self, interval: float = 0.5) -> None:
        """启动窗口状态监控线程

        Args:
            interval: 检查间隔（秒）

        TD-358: 先停止旧线程再启动，防止线程泄漏。
        """
        if self._monitor_thread and self._monitor_thread.is_alive():
            logger.warning("窗口监控: 旧线程仍在运行，先停止再重启")
            self.stop_monitoring()

        self._check_interval = interval
        self._stop_event.clear()
        self._last_foreground_hwnd = user32.GetForegroundWindow()

        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
        )
        self._monitor_thread.start()
        logger.info("窗口状态监控已启动，间隔 %.1fs", interval)

    def stop_monitoring(self) -> None:
        """停止窗口状态监控线程"""
        self._stop_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=3.0)
        self._monitor_thread = None
        logger.info("窗口状态监控已停止")

    def _monitor_loop(self) -> None:
        """监控循环：检测前台窗口变化并触发回调"""
        while not self._stop_event.is_set():
            try:
                current_hwnd = user32.GetForegroundWindow()

                if current_hwnd != self._last_foreground_hwnd:
                    old_hwnd = self._last_foreground_hwnd
                    self._last_foreground_hwnd = current_hwnd

                    for callback in self._callbacks:
                        try:
                            callback(old_hwnd or 0, current_hwnd)
                        except Exception as exc:
                            logger.error("窗口变化回调异常: %s", exc)

            except Exception as exc:
                logger.error("窗口监控循环异常: %s", exc)

            self._stop_event.wait(timeout=self._check_interval)


class WindowBackgroundMonitor:
    """Monitor target window foreground state during task execution.

    When the window loses foreground, the pipeline engine is paused and
    the on_pause callback is invoked (typically sends a WS task.progress
    frame to the frontend). When the window regains foreground, the
    engine is resumed and on_resume is invoked. If the window stays in
    the background longer than timeout_seconds, the engine is cancelled
    and on_timeout is invoked.

    Attributes:
        device: WindowsDevice with is_foreground() method.
        engine: PipelineEngine with pause()/resume()/cancel() methods.
        timeout: Max seconds to wait in background (0 = infinite).
        interval: Polling interval in seconds.
        on_pause: Callback invoked when window loses foreground.
        on_resume: Callback invoked when window regains foreground.
        on_timeout: Callback invoked when wait timeout is exceeded.
    """

    def __init__(
        self,
        device,
        engine,
        timeout: float,
        interval: float,
        on_pause: Callable[[], None] | None = None,
        on_resume: Callable[[], None] | None = None,
        on_timeout: Callable[[], None] | None = None,
    ) -> None:
        self._device = device
        self._engine = engine
        self._timeout = timeout  # seconds, 0 = infinite wait
        self._interval = interval
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_timeout = on_timeout
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._paused = False
        self._pause_start_time = 0.0

    def start(self) -> None:
        """Start the monitor thread (daemon)."""
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="WindowBackgroundMonitor"
        )
        self._thread.start()
        logger.info(
            "WindowBackgroundMonitor started: timeout=%ss, interval=%.3fs",
            self._timeout, self._interval,
        )

    def stop(self) -> None:
        """Signal the monitor thread to stop and wait for it to exit."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("WindowBackgroundMonitor stopped (paused=%s)", self._paused)

    def _monitor_loop(self) -> None:
        """Main polling loop — runs until stop() is called or timeout fires."""
        while not self._stop_event.is_set():
            try:
                is_fg = self._device.is_foreground()
            except Exception as exc:
                logger.warning("is_foreground() failed: %s — treating as foreground", exc)
                is_fg = True

            if not is_fg and not self._paused:
                # Window just lost foreground — pause engine
                logger.info("Window lost foreground, pausing pipeline")
                try:
                    self._engine.pause()
                except Exception as exc:
                    logger.error("engine.pause() failed: %s", exc)
                self._paused = True
                self._pause_start_time = time.monotonic()
                if self._on_pause:
                    try:
                        self._on_pause()
                    except Exception as exc:
                        logger.warning("on_pause callback failed: %s", exc)

            elif is_fg and self._paused:
                # Window regained foreground — resume engine
                logger.info("Window regained foreground, resuming pipeline")
                try:
                    self._engine.resume()
                except Exception as exc:
                    logger.error("engine.resume() failed: %s", exc)
                self._paused = False
                if self._on_resume:
                    try:
                        self._on_resume()
                    except Exception as exc:
                        logger.warning("on_resume callback failed: %s", exc)

            elif self._paused:
                # Still in background — check timeout
                if self._timeout > 0:
                    elapsed = time.monotonic() - self._pause_start_time
                    if elapsed > self._timeout:
                        logger.warning(
                            "Window background wait timeout (%.1fs > %ss)",
                            elapsed, self._timeout,
                        )
                        try:
                            self._engine.cancel()
                        except Exception as exc:
                            logger.error("engine.cancel() failed: %s", exc)
                        if self._on_timeout:
                            try:
                                self._on_timeout()
                            except Exception as exc:
                                logger.warning("on_timeout callback failed: %s", exc)
                        self._stop_event.set()
                        break

            # Wait for next interval or stop signal
            self._stop_event.wait(self._interval)
