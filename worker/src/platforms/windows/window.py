"""窗口管理器：窗口查找/激活/状态检测"""

import ctypes
import ctypes.wintypes
import logging
import re
from typing import Any

import psutil

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

EnumWindowsProc = ctypes.WINFUNCTYPE(
    ctypes.wintypes.BOOL,
    ctypes.wintypes.HWND,
    ctypes.wintypes.LPARAM,
)


class WindowManager:
    """窗口管理器：查找、激活、状态检测"""

    def __init__(self):
        self._hwnd: int | None = None
        self._window_title: str = ""
        self._window_class: str = ""

    @property
    def hwnd(self) -> int | None:
        """获取窗口句柄"""
        return self._hwnd

    def find_window(
        self,
        title: str | None = None,
        exact: bool = False,
        regex: bool = False,
        class_name: str | None = None,
        process_name: str | None = None,
    ) -> int | None:
        """多策略查找窗口

        Args:
            title: 窗口标题（支持模糊/精确/正则匹配）
            exact: 是否精确匹配标题
            regex: 是否使用正则匹配标题
            class_name: 窗口类名
            process_name: 进程名

        Returns:
            窗口句柄，未找到返回 None
        """
        found_hwnd = None

        def _enum_callback(hwnd, _lparam):
            nonlocal found_hwnd

            if not user32.IsWindowVisible(hwnd):
                return True

            buf_len = user32.GetWindowTextLengthW(hwnd)
            if buf_len == 0 and title:
                return True

            buf = ctypes.create_unicode_buffer(buf_len + 1)
            user32.GetWindowTextW(hwnd, buf, buf_len + 1)
            win_title = buf.value

            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            win_class = cls_buf.value

            if class_name and win_class != class_name:
                return True

            if title:
                if exact:
                    if win_title != title:
                        return True
                elif regex:
                    if not re.search(title, win_title):
                        return True
                else:
                    if title.lower() not in win_title.lower():
                        return True

            if process_name:
                pid = ctypes.wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                proc_name = self._get_process_name(pid.value)
                if proc_name.lower() != process_name.lower():
                    return True

            found_hwnd = hwnd
            return False

        callback = EnumWindowsProc(_enum_callback)
        user32.EnumWindows(callback, 0)

        if found_hwnd:
            self._hwnd = found_hwnd
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(found_hwnd, buf, 256)
            self._window_title = buf.value
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(found_hwnd, cls_buf, 256)
            self._window_class = cls_buf.value
            logger.info("找到窗口: hwnd=%s, title=%s, class=%s", found_hwnd, self._window_title, self._window_class)

        return found_hwnd

    def set_hwnd(self, hwnd: int) -> None:
        """绑定一个已知有效的窗口句柄并刷新标题/类名。

        Used when the caller already holds a validated hwnd (e.g. from the
        backend's device_info) instead of searching by title. Browser window
        titles drift per page (e.g. ``about:blank`` → ``新标签页 - Google Chrome``),
        so a validated hwnd is more reliable than a title search.
        """
        self._hwnd = hwnd
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        self._window_title = buf.value
        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buf, 256)
        self._window_class = cls_buf.value
        logger.info("绑定窗口句柄: hwnd=%s, title=%s, class=%s", hwnd, self._window_title, self._window_class)

    def activate(self) -> bool:
        """激活窗口到前台"""
        if not self._hwnd:
            logger.warning("未设置窗口句柄，无法激活")
            return False

        if user32.IsIconic(self._hwnd):
            user32.ShowWindow(self._hwnd, 9)  # SW_RESTORE

        user32.SetForegroundWindow(self._hwnd)
        logger.debug("已激活窗口: hwnd=%s", self._hwnd)
        return True

    def get_rect(self) -> tuple[int, int, int, int] | None:
        """获取窗口矩形 (left, top, right, bottom)"""
        if not self._hwnd:
            return None

        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(self._hwnd, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)

    def get_client_rect(self) -> tuple[int, int, int, int] | None:
        """Return client area rect (0, 0, width, height) via GetClientRect.

        The client area excludes the title bar and window borders. This is
        what game UI renders into, and what PostMessage WM_LBUTTON* coords
        are measured against. Used by display_builder to populate
        RuntimeDisplayContext.client_physical_res.

        Returns:
            (0, 0, width, height) on success, or None if no hwnd is bound.
        """
        if not self._hwnd:
            return None

        rect = ctypes.wintypes.RECT()
        # GetClientRect always returns left=0, top=0; right=width, bottom=height
        user32.GetClientRect(self._hwnd, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)

    def client_to_screen(self, x: int = 0, y: int = 0) -> tuple[int, int] | None:
        """Convert client-area coords to screen-physical coords.

        Wrapper around user32.ClientToScreen. With default (0, 0) returns
        the client area's top-left in screen coords — used by
        display_builder to populate RuntimeDisplayContext.client_screen_origin.

        Args:
            x: Client X coordinate (default 0).
            y: Client Y coordinate (default 0).

        Returns:
            (screen_x, screen_y) on success, or None if no hwnd is bound.
        """
        if not self._hwnd:
            return None

        pt = ctypes.wintypes.POINT(x, y)
        if user32.ClientToScreen(self._hwnd, ctypes.byref(pt)):
            return (pt.x, pt.y)
        return None

    def is_foreground(self) -> bool:
        """检查窗口是否在前台"""
        if not self._hwnd:
            return False
        return user32.GetForegroundWindow() == self._hwnd

    def temp_foreground(self) -> Any:
        """临时将窗口置顶，返回上下文管理器"""
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            was_foreground = self.is_foreground()
            old_foreground = user32.GetForegroundWindow()
            if not was_foreground:
                self.activate()
            try:
                yield
            finally:
                if not was_foreground and old_foreground:
                    user32.SetForegroundWindow(old_foreground)

        return _ctx()

    def find_windows_by_process(self, process_name: str) -> list[dict[str, Any]]:
        """通过进程名查找所有可见窗口

        Args:
            process_name: 目标进程名（不区分大小写）

        Returns:
            窗口信息列表 [{"hwnd", "title", "class", "pid"}]
        """
        results: list[dict[str, Any]] = []

        def _enum_callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True

            pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            proc_name = self._get_process_name(pid.value)
            if proc_name.lower() != process_name.lower():
                return True

            buf_len = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(buf_len + 1)
            user32.GetWindowTextW(hwnd, buf, buf_len + 1)

            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)

            results.append({
                "hwnd": hwnd,
                "title": buf.value,
                "class": cls_buf.value,
                "pid": pid.value,
            })
            return True

        callback = EnumWindowsProc(_enum_callback)
        user32.EnumWindows(callback, 0)
        logger.info("通过进程名 %s 找到 %d 个窗口", process_name, len(results))
        return results

    def bring_to_foreground(self) -> bool:
        """可靠地将窗口激活到前台

        使用 Alt 键技巧绕过 SetForegroundWindow 的前台锁定限制，
        适用于跨进程窗口激活场景

        Returns:
            是否成功激活
        """
        if not self._hwnd:
            logger.warning("未设置窗口句柄，无法激活")
            return False

        if user32.IsIconic(self._hwnd):
            user32.ShowWindow(self._hwnd, 9)

        foreground_hwnd = user32.GetForegroundWindow()
        if foreground_hwnd == self._hwnd:
            return True

        foreground_pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(foreground_hwnd, ctypes.byref(foreground_pid))
        target_pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(self._hwnd, ctypes.byref(target_pid))

        if foreground_pid.value != target_pid.value:
            user32.keybd_event(0x12, 0, 0, 0)
            user32.keybd_event(0x12, 0, 2, 0)

        result = user32.SetForegroundWindow(self._hwnd)
        logger.debug("BringToForeground: hwnd=%s, result=%s", self._hwnd, result)
        return bool(result)

    @staticmethod
    def _get_process_name(pid: int) -> str:
        """根据 PID 获取进程名"""
        try:
            return psutil.Process(pid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return ""


# ==================== Module-level stateless wrappers ====================
#
# These thin wrappers expose Win32 user32 functions as plain functions
# so that callers (core/, devices/) do not need to touch ctypes directly.
# They all swallow exceptions and return None/False on failure so callers
# can use them inside try/except blocks without leaking ctypes errors.
#
# Windows-only: importing this module requires `ctypes.windll` (Windows).
# Non-Windows callers must guard the import (try/except ImportError or
# AttributeError) per GAF backend-conventions §11.


def is_window(hwnd: int) -> bool:
    """Check whether a window handle is valid.

    Args:
        hwnd: Window handle.

    Returns:
        True if the handle refers to a valid window, False otherwise
        (including on non-Windows platforms or when user32 is missing).
    """
    try:
        return bool(user32.IsWindow(hwnd))
    except Exception:
        return False


def find_window_by_title(title: str) -> int | None:
    """Find a top-level window by exact title.

    Args:
        title: Window title to match exactly.

    Returns:
        Window handle (HWND) as int, or None if not found.
    """
    try:
        hwnd = user32.FindWindowW(None, title)
        return hwnd if hwnd else None
    except Exception:
        return None


def find_window_by_class(class_name: str) -> int | None:
    """Find a top-level window by exact class name.

    Args:
        class_name: Window class name to match exactly (e.g. "MuMuPlayer").

    Returns:
        Window handle (HWND) as int, or None if not found.
    """
    try:
        hwnd = user32.FindWindowW(class_name, None)
        return hwnd if hwnd else None
    except Exception:
        return None


def post_message_w(hwnd: int, msg: int, wparam: int, lparam: int) -> bool:
    """Post a message to the target window's message queue (non-blocking).

    Wraps user32.PostMessageW. Returns True if the message was posted.

    Args:
        hwnd: Target window handle.
        msg: Message code (e.g. 0x0102 = WM_CHAR).
        wparam: WPARAM value.
        lparam: LPARAM value.

    Returns:
        True on success, False on failure.
    """
    try:
        return bool(user32.PostMessageW(hwnd, msg, wparam, lparam))
    except Exception:
        return False


def get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Get a window's screen rectangle.

    Args:
        hwnd: Window handle.

    Returns:
        (left, top, right, bottom) tuple, or None on failure.
    """
    try:
        rect = ctypes.wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return None


def get_client_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Get a window's client area rectangle via GetClientRect.

    The client area excludes the title bar and window borders. This is what
    game UI renders into. Used by diagnostics to report client dimensions.

    Args:
        hwnd: Window handle.

    Returns:
        (0, 0, width, height) tuple (GetClientRect always returns left=0,
        top=0), or None on failure.
    """
    try:
        rect = ctypes.wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return None


def set_cursor_pos(x: int, y: int) -> bool:
    """Move the mouse cursor to (x, y) in screen coordinates.

    Args:
        x: Screen X coordinate.
        y: Screen Y coordinate.

    Returns:
        True on success, False on failure.
    """
    try:
        return bool(user32.SetCursorPos(x, y))
    except Exception:
        return False


def block_input(block: bool) -> bool:
    """Block or unblock physical keyboard/mouse input.

    Wraps user32.BlockInput. Blocking requires admin rights; unblocking
    always succeeds. The block is automatically released when the calling
    process exits.

    Args:
        block: True to block input, False to unblock.

    Returns:
        True on success, False on failure (e.g. lacking admin rights).
    """
    try:
        return bool(user32.BlockInput(bool(block)))
    except Exception:
        return False
