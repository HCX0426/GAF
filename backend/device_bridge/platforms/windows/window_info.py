"""Win32 window information helpers (HWND enumeration, DPI, screen resolution).

B001 fix: business views in agents/views.py previously called user32/
kernel32 directly via `import ctypes`, which:
1. Crashed on Linux/macOS at import time
2. Violated the platform abstraction rule (§11)

This module concentrates all Win32 window-info calls behind a
platform-safe Python API. On non-Windows platforms every function
returns a sensible empty/False value without raising.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == 'nt'


def _get_user32():
    """Return (user32, wintypes, ctypes) on Windows or (None, None, None) otherwise.

    Centralizes the ctypes import so callers don't need to repeat the
    platform check / import guard pattern.
    """
    if not _IS_WINDOWS:
        return None, None, None
    try:
        import ctypes
        from ctypes import wintypes
        return ctypes.windll.user32, wintypes, ctypes
    except (ImportError, AttributeError) as exc:
        logger.warning('Win32 user32 unavailable: %s', exc)
        return None, None, None


def is_window_handle_valid(hwnd: int) -> bool:
    """Return True if hwnd refers to a live window. Non-Windows: False."""
    user32, _, _ = _get_user32()
    if user32 is None:
        return False
    try:
        return bool(user32.IsWindow(hwnd))
    except Exception as exc:
        logger.warning('IsWindow failed for hwnd=%s: %s', hwnd, exc)
        return False


def get_client_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Return (left, top, right, bottom) of hwnd's client rect or None.

    Non-Windows or invalid hwnd: None.
    """
    user32, wintypes, ctypes = _get_user32()
    if user32 is None:
        return None
    try:
        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception as exc:
        logger.warning('GetClientRect failed for hwnd=%s: %s', hwnd, exc)
        return None


def get_client_size(hwnd: int) -> tuple[int, int] | None:
    """Return (width, height) of hwnd's client area or None.

    Returns None for zero-size client areas (e.g. minimized windows).
    """
    rect = get_client_rect(hwnd)
    if rect is None:
        return None
    left, top, right, bottom = rect
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        return None
    return (w, h)


def get_client_scale(hwnd: int, screenshot_width: int) -> float:
    """Return scale factor between screenshot pixels and client logical pixels.

    Used to convert template-match coordinates (screenshot pixels) to
    click coordinates (client logical pixels), accounting for DPI scaling.

    Returns 1.0 if any step fails (non-Windows, invalid hwnd, zero size),
    so callers can multiply unconditionally without branching.
    """
    if not hwnd or screenshot_width <= 0:
        return 1.0
    size = get_client_size(hwnd)
    if size is None:
        return 1.0
    client_w, _ = size
    if client_w <= 0:
        return 1.0
    return client_w / screenshot_width


def get_screen_resolution() -> tuple[int, int] | None:
    """Return primary screen (width, height) or None on non-Windows/failure.

    Wraps GetSystemMetrics(SM_CXSCREEN=0, SM_CYSCREEN=1).
    """
    user32, _, _ = _get_user32()
    if user32 is None:
        return None
    try:
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        if w <= 0 or h <= 0:
            return None
        return (w, h)
    except Exception as exc:
        logger.warning('GetSystemMetrics failed: %s', exc)
        return None


def find_best_window_match(
    title_keyword: str,
    target_class: str = '',
    target_process: str = '',
) -> int | None:
    """Enumerate top-level windows and return the hwnd that best matches.

    Scoring:
    +100 if window class name equals target_class
    +50  if window class name contains target_class
    +30  if window title equals title_keyword
    +10  if window title starts with title_keyword

    Requires title_keyword to be a substring of the window title at minimum.
    Stops enumeration early when a strong (>=100) match is found.

    Returns None on non-Windows or no match.
    """
    user32, wintypes, ctypes = _get_user32()
    if user32 is None:
        return None
    if not title_keyword:
        return None

    best_match = [None, 0]  # [hwnd, score]
    found_strong = [None]   # hwnd if score >= 100

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_callback(hwnd, lp):
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        win_title = buf.value
        if title_keyword not in win_title:
            return True

        # Skip windows with zero-size client rects (hidden/closed).
        cr = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(cr)):
            return True
        if cr.right - cr.left <= 0 or cr.bottom - cr.top <= 0:
            return True

        score = 0
        if target_class:
            try:
                class_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_buf, 256)
                win_class = class_buf.value
                if win_class == target_class:
                    score += 100
                elif target_class in win_class:
                    score += 50
            except Exception as exc:
                logger.warning('GetClassNameW failed: %s', exc)

        if win_title == title_keyword:
            score += 30
        elif win_title.startswith(title_keyword):
            score += 10

        if score > best_match[1]:
            best_match[0] = hwnd
            best_match[1] = score
            if score >= 100:
                found_strong[0] = hwnd
                return False  # Stop enumeration on strong match
        return True

    try:
        user32.EnumWindows(enum_callback, 0)
    except Exception as exc:
        logger.warning('EnumWindows failed: %s', exc)
        return None

    return found_strong[0] or best_match[0]


def enumerate_visible_windows(
    system_process_blacklist: frozenset | None = None,
    min_size: int = 200,
) -> list:
    """Enumerate top-level visible windows suitable for device discovery.

    Replaces the ctypes window-enum logic previously inlined in
    agent_client._discover_windows_devices (TD-085 / L1 fix: Win32 API
    must live under platforms/windows/, not in business logic).

    Each entry: {hwnd, title, process_name, width, height}.

    Args:
        system_process_blacklist: lower-case process names to skip.
        min_size: skip windows smaller than this (width or height).

    Returns:
        List of window dicts. Empty on non-Windows or failure.
    """
    user32, wintypes, ctypes = _get_user32()
    if user32 is None:
        return []
    try:
        kernel32 = ctypes.windll.kernel32
    except (ImportError, AttributeError) as exc:
        logger.warning('Win32 kernel32 unavailable: %s', exc)
        return []

    windows: list = []

    def _get_process_name(hwnd):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_handle = kernel32.OpenProcess(0x0400 | 0x0010, False, pid.value)
        if not process_handle:
            return ''
        exe_name = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        kernel32.QueryFullProcessImageNameW(process_handle, 0, exe_name, ctypes.byref(size))
        kernel32.CloseHandle(process_handle)
        name = exe_name.value.lower()
        if '\\' in name:
            name = name.rsplit('\\', 1)[-1]
        return name

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if not user32.IsWindowEnabled(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if not title:
            return True

        process_name = _get_process_name(hwnd)
        if system_process_blacklist and process_name.lower() in system_process_blacklist:
            return True

        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w < min_size or h < min_size:
            return True

        windows.append({
            'hwnd': hwnd,
            'title': title,
            'process_name': process_name,
            'width': w,
            'height': h,
        })
        return True

    try:
        user32.EnumWindows(enum_callback, 0)
    except Exception as exc:
        logger.warning('EnumWindows failed: %s', exc)
    return windows
