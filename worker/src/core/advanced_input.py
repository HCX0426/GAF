"""高级输入模式：消息输入FPS锁帧、鼠标锁定跟随、物理输入阻止"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# Win32 wrappers live in platforms/windows/window.py (a Windows-only module
# that requires ctypes.windll). On non-Windows platforms the import fails
# and _WIN32_AVAILABLE stays False, causing all Win32-dependent features
# to degrade to no-ops. Per GAF backend-conventions §11, business code
# must not call ctypes.windll directly — it goes through these wrappers.
_WIN32_AVAILABLE = False
try:
    from platforms.windows.window import (
        block_input as _block_input,
    )
    from platforms.windows.window import (
        find_window_by_title as _find_window_by_title,
    )
    from platforms.windows.window import (
        get_window_rect as _get_window_rect,
    )
    from platforms.windows.window import (
        post_message_w as _post_message_w,
    )
    from platforms.windows.window import (
        set_cursor_pos as _set_cursor_pos,
    )
    _WIN32_AVAILABLE = True
except (ImportError, AttributeError):
    logger.info("Win32 API 不可用，部分 Windows API 功能将降级")


class MessageInputFPS:
    """消息输入 FPS 追踪类

    使用 WithWindowPos + 60fps 追踪窗口位置，持续向目标窗口发送消息。
    适用于需要高频输入文字或指令的游戏场景。

    Attributes:
        window_title: 目标窗口标题
        message: 要发送的消息内容
        _running: 运行状态标志
        _thread: 后台发送线程
        _fps: 发送帧率
    """

    def __init__(self, window_title: str = "", message: str = "", fps: int = 60):
        """初始化消息输入

        Args:
            window_title: 目标窗口标题
            message: 要发送的消息内容
            fps: 发送帧率，默认 60
        """
        self.window_title = window_title
        self.message = message
        self._fps = fps
        self._running = False
        self._thread: threading.Thread | None = None
        self._hwnd = None

    def _find_window(self) -> Any | None:
        """查找目标窗口句柄

        Returns:
            窗口句柄，未找到返回 None
        """
        if not _WIN32_AVAILABLE:
            return None

        try:
            return _find_window_by_title(self.window_title)
        except Exception as exc:
            logger.warning("查找窗口失败: %s", exc)
            return None

    def _send_loop(self) -> None:
        """后台发送循环，以指定帧率向窗口发送消息"""
        interval = 1.0 / max(self._fps, 1)

        while self._running:
            try:
                if self._hwnd is None:
                    self._hwnd = self._find_window()

                if self._hwnd and _WIN32_AVAILABLE:
                    for char in self.message:
                        _post_message_w(self._hwnd, 0x0102, ord(char), 0)

                time.sleep(interval)
            except Exception as exc:
                logger.warning("消息发送循环异常: %s", exc)
                time.sleep(interval)

    def start(self) -> None:
        """启动消息发送"""
        if self._running:
            return

        self._running = True
        self._hwnd = self._find_window()

        if self._hwnd is None:
            logger.warning("MessageInputFPS: 未找到目标窗口 '%s'", self.window_title)

        self._thread = threading.Thread(target=self._send_loop, daemon=True)
        self._thread.start()
        logger.info(
            "MessageInputFPS 已启动: window=%s, fps=%d",
            self.window_title,
            self._fps,
        )

    def stop(self) -> None:
        """停止消息发送"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("MessageInputFPS 已停止")

    @property
    def is_active(self) -> bool:
        """检查是否正在运行"""
        return self._running

    @property
    def is_available(self) -> bool:
        """检查模块是否可用"""
        return _WIN32_AVAILABLE


class MouseLockFollow:
    """FPS 游戏鼠标锁定跟随类

    适用于需要鼠标视角锁定跟随的游戏场景。
    启动后持续追踪窗口中心位置，实时跟随鼠标移动。

    Attributes:
        window_title: 目标窗口标题
        _running: 运行状态标志
        _thread: 后台追踪线程
        _center_x: 窗口中心 X
        _center_y: 窗口中心 Y
    """

    def __init__(self, window_title: str = "", sample_rate: int = 120):
        """初始化鼠标锁定跟随

        Args:
            window_title: 目标窗口标题
            sample_rate: 鼠标采样率，默认 120
        """
        self.window_title = window_title
        self._sample_rate = sample_rate
        self._running = False
        self._thread: threading.Thread | None = None
        self._center_x = 0
        self._center_y = 0

    def _get_window_center(self) -> tuple:
        """获取目标窗口的中心坐标

        Returns:
            (center_x, center_y) 元组
        """
        if not _WIN32_AVAILABLE:
            return (0, 0)

        try:
            hwnd = _find_window_by_title(self.window_title)
            if not hwnd:
                return (0, 0)

            rect = _get_window_rect(hwnd)
            if rect is None:
                return (0, 0)
            left, top, right, bottom = rect
            cx = (left + right) // 2
            cy = (top + bottom) // 2
            return (cx, cy)
        except Exception as exc:
            logger.warning("获取窗口中心失败: %s", exc)
            return (0, 0)

    def _lock_loop(self) -> None:
        """后台鼠标锁定循环"""
        interval = 1.0 / max(self._sample_rate, 1)

        while self._running:
            try:
                cx, cy = self._get_window_center()
                if cx > 0 and cy > 0 and _WIN32_AVAILABLE:
                    _set_cursor_pos(cx, cy)
                    self._center_x = cx
                    self._center_y = cy

                time.sleep(interval)
            except Exception as exc:
                logger.warning("鼠标锁定循环异常: %s", exc)
                time.sleep(interval)

    def start(self) -> None:
        """启动鼠标锁定跟随"""
        if self._running:
            return

        self._running = True
        cx, cy = self._get_window_center()
        self._center_x = cx
        self._center_y = cy
        self._thread = threading.Thread(target=self._lock_loop, daemon=True)
        self._thread.start()
        logger.info("MouseLockFollow 已启动: window=%s", self.window_title)

    def stop(self) -> None:
        """停止鼠标锁定跟随"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("MouseLockFollow 已停止")

    @property
    def is_active(self) -> bool:
        """检查是否正在运行"""
        return self._running

    @property
    def is_available(self) -> bool:
        """检查模块是否可用"""
        return _WIN32_AVAILABLE


class BlockInput:
    """物理输入阻止类

    任务运行时阻止物理键鼠输入，防止用户误触干扰自动化任务。
    调用 Windows API BlockInput 函数。

    Attributes:
        _blocked: 当前阻止状态
    """

    def __init__(self):
        """初始化物理输入阻止"""
        self._blocked = False

    def start(self) -> bool:
        """启用物理输入阻止

        Returns:
            True 表示成功启用
        """
        if not _WIN32_AVAILABLE:
            logger.warning("BlockInput: Windows API 不可用，无法阻止物理输入")
            return False

        try:
            result = _block_input(True)
            self._blocked = result
            if self._blocked:
                logger.info("BlockInput: 物理输入已阻止")
            else:
                logger.warning("BlockInput: 阻止物理输入失败（可能需要管理员权限）")
            return self._blocked
        except Exception as exc:
            logger.warning("BlockInput 调用失败: %s", exc)
            return False

    def stop(self) -> bool:
        """解除物理输入阻止

        Returns:
            True 表示成功解除
        """
        if not self._blocked:
            return True

        if not _WIN32_AVAILABLE:
            self._blocked = False
            return True

        try:
            result = _block_input(False)
            self._blocked = not result
            logger.info("BlockInput: 物理输入已解除")
            return not self._blocked
        except Exception as exc:
            logger.warning("BlockInput 解除失败: %s", exc)
            self._blocked = False
            return True

    @property
    def is_active(self) -> bool:
        """检查是否正在阻止物理输入"""
        return self._blocked

    @property
    def is_available(self) -> bool:
        """检查模块是否可用"""
        return _WIN32_AVAILABLE

    def __del__(self):
        """析构时自动解除阻止"""
        if self._blocked:
            self.stop()
