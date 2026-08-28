"""Windows input handler: dual-mode (SendInput foreground / PostMessage background).

Provides WindowsInputHandler class that unifies:
- SendInput: foreground input (works with fullscreen apps, games)
- PostMessage: background input (works when window is not in foreground)

Also exports low-level helpers (_resolve_vk, _make_key_input, INPUT) used by
BackgroundManagedKeyInput in background_key_input.py.
"""

from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes
import logging
import threading
import time
from typing import Any

from core.result import AutoResult, fail_result, success_result

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32


def _set_dpi_aware() -> None:
    """Set process DPI awareness to avoid coordinate scaling on HiDPI displays.

    Without this, GetSystemMetrics returns logical pixels (not physical) and
    SendInput absolute coordinates are off on HiDPI screens (e.g. 150% scaling).
    Safe to call multiple times; no-op if already set or running on non-Windows.
    """
    with contextlib.suppress(AttributeError, OSError):
        # Windows 10 1703+: per-monitor v2 DPI aware (preferred).
        ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
        return
    with contextlib.suppress(AttributeError, OSError):
        # Windows 8.1+: per-monitor DPI aware.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    with contextlib.suppress(AttributeError, OSError):
        # Windows Vista+: system DPI aware.
        ctypes.windll.user32.SetProcessDPIAware()


_set_dpi_aware()


def _client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
    """Convert window-relative (x, y) to screen-absolute coordinates.

    If hwnd is 0 or invalid, returns (x, y) unchanged (treats as screen coords).
    """
    if not hwnd:
        return x, y
    point = ctypes.wintypes.POINT(x, y)
    if user32.ClientToScreen(hwnd, ctypes.byref(point)):
        return point.x, point.y
    return x, y


# ── Win32 focus / cursor helpers for pseudo-background mode ────────────

# Prototype SetCursorPos so we can restore cursor position after a click.
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = ctypes.wintypes.BOOL


def _get_foreground_window() -> int:
    """Return the current foreground window handle."""
    return user32.GetForegroundWindow()


def _set_foreground_window(hwnd: int) -> bool:
    """Bring a window to the foreground.

    Returns True on success. This may fail for windows owned by other
    processes unless the calling thread already has foreground rights,
    but attaching to the foreground thread is not attempted here to keep
    the helper self-contained.
    """
    if not hwnd:
        return False
    return bool(user32.SetForegroundWindow(hwnd))


def _get_cursor_pos() -> tuple[int, int]:
    """Return current cursor position in screen coordinates."""
    point = ctypes.wintypes.POINT(0, 0)
    if user32.GetCursorPos(ctypes.byref(point)):
        return point.x, point.y
    return 0, 0


def _set_cursor_pos(x: int, y: int) -> bool:
    """Move the cursor to screen coordinates (x, y)."""
    return bool(user32.SetCursorPos(x, y))


# ── Windows constants ──────────────────────────────────────────────────

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEMOVE = 0x0200

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

# ── ctypes structures ──────────────────────────────────────────────────


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.wintypes.ULONG)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.wintypes.ULONG)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.wintypes.DWORD),
        ("wParamL", ctypes.wintypes.WORD),
        ("wParamH", ctypes.wintypes.WORD),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("union", _InputUnion),
    ]


# ── Virtual key map (extended) ─────────────────────────────────────────

VK_MAP: dict[str, int] = {
    "backspace": 0x08, "tab": 0x09, "clear": 0x0C,
    "enter": 0x0D, "return": 0x0D,
    "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
    "pause": 0x13, "capslock": 0x14,
    "escape": 0x1B, "esc": 0x1B,
    "space": 0x20, "pageup": 0x21, "pagedown": 0x22,
    "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "select": 0x29, "print": 0x2A, "snapshot": 0x2C,
    "insert": 0x2D, "delete": 0x2E, "del": 0x2E,
    "lwin": 0x5B, "rwin": 0x5C,
    "win": 0x5B,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44,
    "e": 0x45, "f": 0x46, "g": 0x47, "h": 0x48,
    "i": 0x49, "j": 0x4A, "k": 0x4B, "l": 0x4C,
    "m": 0x4D, "n": 0x4E, "o": 0x4F, "p": 0x50,
    "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
    "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58,
    "y": 0x59, "z": 0x5A,
    "numpad0": 0x60, "numpad1": 0x61, "numpad2": 0x62,
    "numpad3": 0x63, "numpad4": 0x64, "numpad5": 0x65,
    "numpad6": 0x66, "numpad7": 0x67, "numpad8": 0x68,
    "numpad9": 0x69,
    "multiply": 0x6A, "add": 0x6B, "subtract": 0x6D,
    "decimal": 0x6E, "divide": 0x6F,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "numlock": 0x90, "scrolllock": 0x91,
    "lshift": 0xA0, "rshift": 0xA1,
    "lctrl": 0xA2, "rctrl": 0xA3,
    "lalt": 0xA4, "ralt": 0xA5,
    "semicolon": 0xBA,
    "plus": 0xBB, "equals": 0xBB,
    "comma": 0xBC,
    "minus": 0xBD,
    "period": 0xBE, "dot": 0xBE,
    "slash": 0xBF,
    "tilde": 0xC0, "backtick": 0xC0,
    "lbracket": 0xDB, "rbracket": 0xDD,
    "backslash": 0xDC,
    "quote": 0xDE,
}


def _resolve_vk(key_name: str) -> int:
    """Resolve a key name to its Windows virtual key code.

    Args:
        key_name: Key name (e.g., "enter", "a", "f1", "space")

    Returns:
        Virtual key code, or 0 if unknown
    """
    key_lower = key_name.lower().strip()
    if key_lower in VK_MAP:
        return VK_MAP[key_lower]
    if len(key_lower) == 1 and key_lower.isalpha():
        return ord(key_lower.upper())
    if len(key_lower) == 1 and key_lower.isdigit():
        return ord(key_lower)
    return 0


def _make_key_input(vk: int, flags: int) -> INPUT:
    """Create a keyboard INPUT structure for SendInput.

    Args:
        vk: Virtual key code
        flags: Key event flags (0 = key down, KEYEVENTF_KEYUP = key up)

    Returns:
        INPUT structure with keyboard data
    """
    ki = KEYBDINPUT(
        wVk=vk,
        wScan=0,
        dwFlags=flags,
        time=0,
        dwExtraInfo=None,
    )
    return INPUT(type=INPUT_KEYBOARD, union=_InputUnion(ki=ki))


def _make_key_unicode(char_code: int, flags: int) -> INPUT:
    """Create a Unicode keyboard INPUT structure for SendInput.

    Args:
        char_code: Unicode character code
        flags: Key event flags (KEYEVENTF_UNICODE for char input)

    Returns:
        INPUT structure with keyboard data
    """
    ki = KEYBDINPUT(
        wVk=0,
        wScan=char_code,
        dwFlags=flags | KEYEVENTF_UNICODE,
        time=0,
        dwExtraInfo=None,
    )
    return INPUT(type=INPUT_KEYBOARD, union=_InputUnion(ki=ki))


def _parse_hwnd(target: str) -> int:
    """Parse target string to window handle integer.

    Args:
        target: Hex string of hwnd (e.g. "0x1a2b3c") or "0" for desktop

    Returns:
        Integer hwnd
    """
    if isinstance(target, int):
        return target
    try:
        return int(target, 16) if target.startswith("0x") else int(target)
    except (ValueError, TypeError):
        return 0


class WindowsInputHandler:
    """Unified Windows input handler with dual-mode (SendInput/PostMessage).

    SendInput mode:
        Injects input events at the system level. Works with fullscreen
        applications and games. Target window must be in foreground.

    PostMessage mode:
        Sends window messages directly to the target window handle.
        Works when the window is in background (not focused), but may
        be blocked by anti-cheat software.

    Concurrency safety (TD-121):
        SendInput/PseudoBackground modes rely on global system state
        (foreground window + cursor position) and MUST be serialized
        across threads. A reentrant lock (`_sendinput_lock`) guards all
        SendInput/PseudoBackground paths so concurrent calls are
        serialized at the handler level. PostMessage/SendMessage paths
        are NOT locked (hwnd-isolated, parallel-safe).
    """

    def __init__(self, method: str = "SendInput"):
        """Initialize input handler.

        Args:
            method: Input method - "SendInput" (foreground) or "PostMessage" (background)
        """
        self._method = method
        # DPI scale factor (logical→physical) for coordinate conversion.
        # Set by the orchestrator after building RuntimeDisplayContext.
        # SendInput/PseudoBackground need PHYSICAL coords for ClientToScreen,
        # but template_match produces LOGICAL coords. This ratio bridges the gap.
        # Default 1.0 = no conversion (legacy/raw-pixel pipelines).
        self._dpi_ratio: float = 1.0
        # N191 §10.10 决策点 2 A+ (AI 可调试性, 2026-07-27):
        # coord_trace_callback — 由 PipelineEngine.load 注入 (转发到
        # context.emit_coord_trace)。device 内部 logical→physical 转换
        # 时调本 callback 记 trace, 堵住「ADBDevice.click / WindowsDevice.click
        # 内部转换黑盒」的调试盲点 (D5 转换黑盒检查)。
        # None in tests / standalone CLI — 不阻塞 device 主流程。
        self._coord_trace_callback: Any = None
        # RLock serializes SendInput/PseudoBackground paths across threads.
        # RLock (not Lock) because PseudoBackground methods internally call
        # _sendinput methods (e.g. _click_pseudo_background → _click_sendinput),
        # which would deadlock with a non-reentrant Lock. PostMessage paths
        # do not acquire this lock — they remain parallel-safe (hwnd-isolated).
        self._sendinput_lock = threading.RLock()

    @property
    def method(self) -> str:
        """Get current input method."""
        return self._method

    @method.setter
    def method(self, value: str) -> None:
        """Set input method.

        Supported methods:
        - "SendInput"        : foreground system-level input
        - "PostMessage"      : background window-message input
        - "PseudoBackground" : temporarily foreground the target window,
                               inject SendInput, then restore focus/cursor
        """
        if value not in ("SendInput", "PostMessage", "PseudoBackground"):
            logger.warning("Unknown input method: %s, keeping current: %s", value, self._method)
            return
        self._method = value
        logger.debug("Input method switched to: %s", value)

    def set_dpi_ratio(self, ratio: float) -> None:
        """Set the logical-to-physical DPI scale ratio.

        SendInput uses ClientToScreen which expects PHYSICAL client
        coordinates, but pipeline nodes produce LOGICAL coordinates
        (via coord_transformer). This ratio converts logical→physical
        inside _click_sendinput / _swipe_sendinput.

        Args:
            ratio: logical_to_physical_ratio (1.0 = 100%, 1.5 = 150%).
                   Set 1.0 to disable conversion (legacy/raw-pixel mode).
        """
        if ratio <= 0:
            logger.warning("set_dpi_ratio: invalid ratio %s, ignoring", ratio)
            return
        self._dpi_ratio = ratio
        logger.debug("DPI ratio set to: %.4f", ratio)

    def _logical_to_physical(self, x: int, y: int) -> tuple[int, int]:
        """Convert logical client coords to physical client coords.

        No-op when _dpi_ratio is 1.0 (fullscreen, 100% scaling, or legacy
        raw-pixel pipelines without coord_transformer).

        N191 §10.10 决策点 2 A+ (AI 可调试性, 2026-07-27):
            转换时调 _coord_trace_callback 记 trace, AI 能看到
            ``input_logical → converted_physical → formula`` 链路。
            堵住「device 内部转换黑盒」的调试盲点 (D5)。
        """
        if self._dpi_ratio == 1.0:
            # No conversion, but still emit trace for observability (AI
            # can confirm "no conversion happened" from log).
            self._emit_coord_trace_safe(
                step="logical_to_physical",
                raw=(x, y),
                converted=(x, y),
                formula="logical_to_physical: no-op (dpi_ratio=1.0)",
                coord_system_in="logical",
                coord_system_out="physical",
            )
            return x, y
        phys_x = int(round(x * self._dpi_ratio))
        phys_y = int(round(y * self._dpi_ratio))
        self._emit_coord_trace_safe(
            step="logical_to_physical",
            raw=(x, y),
            converted=(phys_x, phys_y),
            formula=f"physical = logical * dpi_scale({self._dpi_ratio:.4f})",
            coord_system_in="logical",
            coord_system_out="physical",
        )
        return phys_x, phys_y

    def set_coord_trace_callback(self, callback: Any) -> None:
        """Inject a coord_trace callback for AI debuggability (N191 §10.10).

        Args:
            callback: A callable matching ``callback(*, node_id, step, raw,
                converted, formula, coord_system_in, coord_system_out, extra=None)``
                or None to clear. Typically ``context.emit_coord_trace``.
        """
        self._coord_trace_callback = callback

    def _emit_coord_trace_safe(
        self, *, step: str, raw: Any, converted: Any,
        formula: str, coord_system_in: str = "",
        coord_system_out: str = "", extra: dict[str, Any] | None = None,
    ) -> None:
        """Call _coord_trace_callback if set; swallow all errors (best-effort)."""
        cb = self._coord_trace_callback
        if cb is None:
            return
        with contextlib.suppress(Exception):
            # best-effort: trace 失败不能阻塞 device.click。
            cb(
                node_id="windows_device",
                step=step,
                raw=raw,
                converted=converted,
                formula=formula,
                coord_system_in=coord_system_in,
                coord_system_out=coord_system_out,
                extra=extra,
            )

    def click(
        self,
        target: str,
        x: int,
        y: int,
        method: str | None = None,
        button: str = "left",
    ) -> AutoResult:
        """Perform a mouse click at the specified coordinates.

        Args:
            target: Target window handle (hex string) or "0" for desktop
            x: X coordinate relative to target window
            y: Y coordinate relative to target window
            method: Override input method (None = use current)
            button: Mouse button - "left", "right", or "middle"

        Returns:
            AutoResult indicating success/failure
        """
        actual_method = method or self._method

        try:
            if actual_method == "PostMessage":
                return self._click_postmessage(target, x, y, button)
            if actual_method == "PseudoBackground":
                return self._click_pseudo_background(target, x, y, button)
            return self._click_sendinput(target, x, y, button)
        except Exception as exc:
            return fail_result(error_msg=f"Click failed: {exc}")

    def _click_sendinput(self, target: str, x: int, y: int, button: str = "left") -> AutoResult:
        """Click via SendInput (requires window in foreground).

        Converts window-relative (x, y) to screen-absolute coordinates via
        ClientToScreen when target hwnd is provided. Falls back to treating
        (x, y) as screen-absolute when target is "0" or invalid.

        Coordinate contract: (x, y) are LOGICAL client coords (produced by
        template_match via coord_transformer). ClientToScreen expects
        PHYSICAL client coords, so we convert using _dpi_ratio first.

        Thread-safety: serialized via `_sendinput_lock` (TD-121).
        """
        with self._sendinput_lock:
            button_down = {
                "left": MOUSEEVENTF_LEFTDOWN,
                "right": MOUSEEVENTF_RIGHTDOWN,
                "middle": MOUSEEVENTF_MIDDLEDOWN,
            }.get(button, MOUSEEVENTF_LEFTDOWN)

            button_up = {
                "left": MOUSEEVENTF_LEFTUP,
                "right": MOUSEEVENTF_RIGHTUP,
                "middle": MOUSEEVENTF_MIDDLEUP,
            }.get(button, MOUSEEVENTF_LEFTUP)

            # Convert logical→physical, then window-relative to screen-absolute.
            hwnd = _parse_hwnd(target)
            phys_x, phys_y = self._logical_to_physical(x, y)
            screen_x, screen_y = _client_to_screen(hwnd, phys_x, phys_y)
            self._emit_coord_trace_safe(
                step="client_to_screen",
                raw=(phys_x, phys_y),
                converted=(screen_x, screen_y),
                formula=f"ClientToScreen(hwnd={hwnd}, physical=({phys_x},{phys_y})) -> screen=({screen_x},{screen_y})",
                coord_system_in="physical",
                coord_system_out="screen",
                extra={"hwnd": hwnd, "window_offset": (screen_x - phys_x, screen_y - phys_y)},
            )
            abs_x = int(screen_x * 65535 / ctypes.windll.user32.GetSystemMetrics(0))
            abs_y = int(screen_y * 65535 / ctypes.windll.user32.GetSystemMetrics(1))

            move = INPUT(
                type=INPUT_MOUSE,
                union=_InputUnion(mi=MOUSEINPUT(
                    dx=abs_x, dy=abs_y,
                    mouseData=0,
                    dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
                    time=0, dwExtraInfo=None,
                )),
            )
            down = INPUT(
                type=INPUT_MOUSE,
                union=_InputUnion(mi=MOUSEINPUT(
                    dx=0, dy=0,
                    mouseData=0,
                    dwFlags=button_down,
                    time=0, dwExtraInfo=None,
                )),
            )
            up = INPUT(
                type=INPUT_MOUSE,
                union=_InputUnion(mi=MOUSEINPUT(
                    dx=0, dy=0,
                    mouseData=0,
                    dwFlags=button_up,
                    time=0, dwExtraInfo=None,
                )),
            )

            size = ctypes.sizeof(INPUT)
            for inp in (move, down, up):
                user32.SendInput(1, ctypes.byref(inp), size)
                time.sleep(0.01)

            return success_result(data={"x": x, "y": y, "button": button})

    def _click_postmessage(self, target: str, x: int, y: int, button: str = "left") -> AutoResult:
        """Click via PostMessage (works in background).

        Sends mouse messages directly to the target window.
        """
        hwnd = _parse_hwnd(target)
        if not hwnd:
            return fail_result(error_msg="Invalid target hwnd for PostMessage click")

        lparam = (y << 16) | (x & 0xFFFF)
        wparam_down = {
            "left": 0x0001,
            "right": 0x0002,
            "middle": 0x0010,
        }.get(button, 0x0001)
        wparam_up = 0

        button_down_msg = {
            "left": WM_LBUTTONDOWN,
            "right": WM_RBUTTONDOWN,
            "middle": WM_MBUTTONDOWN,
        }.get(button, WM_LBUTTONDOWN)

        button_up_msg = {
            "left": WM_LBUTTONUP,
            "right": WM_RBUTTONUP,
            "middle": WM_MBUTTONUP,
        }.get(button, WM_LBUTTONUP)

        user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
        user32.PostMessageW(hwnd, button_down_msg, wparam_down, lparam)
        user32.PostMessageW(hwnd, button_up_msg, wparam_up, lparam)

        return success_result(data={"x": x, "y": y, "button": button, "hwnd": hex(hwnd)})

    def _click_pseudo_background(
        self,
        target: str,
        x: int,
        y: int,
        button: str = "left",
    ) -> AutoResult:
        """Click via temporary foreground + SendInput.

        Saves the current foreground window and cursor position, brings the
        target window to the foreground (using AttachThreadInput trick for
        cross-process foreground lock bypass), injects a SendInput click at
        the window-relative coordinates, then restores the previous foreground
        window and cursor position.

        This gives reliable game-compatible input (SendInput) without keeping
        the target window permanently in the foreground.

        Thread-safety: serialized via `_sendinput_lock` (TD-121). Internal
        call to `_click_sendinput` re-acquires the RLock (reentrant, no
        deadlock).
        """
        # Import inside function to avoid circular import
        # (input_variants.py imports from input.py at module level).
        from platforms.windows.input_variants import bring_to_foreground

        hwnd = _parse_hwnd(target)
        if not hwnd:
            return fail_result(error_msg="Invalid target hwnd for pseudo-background click")

        with self._sendinput_lock:
            prev_hwnd = _get_foreground_window()

            # Fast path: if the target window is already in the foreground,
            # behave identically to plain SendInput. The cursor save/restore
            # and foreground switch would be no-ops anyway, but skipping them
            # entirely avoids side effects (some games cancel a click if the
            # cursor is moved via SetCursorPos immediately after SendInput).
            if prev_hwnd == hwnd:
                logger.info(
                    "PseudoBackground fast-path: target %s already foreground, plain SendInput",
                    hex(hwnd),
                )
                return self._click_sendinput(target, x, y, button)

            logger.info(
                "PseudoBackground slow-path: target %s, prev_fg=%s, need foreground switch",
                hex(hwnd), hex(prev_hwnd) if prev_hwnd else "0",
            )

            prev_cursor = _get_cursor_pos()

            try:
                # Use AttachThreadInput trick to bypass cross-process foreground lock.
                # Plain SetForegroundWindow is rejected by OS when target window
                # belongs to another process, causing silent click failures.
                fg_success = bring_to_foreground(hwnd, log=True)
                if not fg_success:
                    logger.warning(
                        "PseudoBackground: bring_to_foreground failed (hwnd=%s), "
                        "SendInput click may go to wrong window",
                        hex(hwnd),
                    )

                result = self._click_sendinput(target, x, y, button)

                # Wait for the OS to finish processing the SendInput events
                # before restoring focus. Without this delay, the foreground
                # switch away from the target window races with the click event
                # delivery, causing the click to be dropped or sent to the
                # wrong window. 50ms is enough for move+down+up (3 events with
                # 10ms spacing = 30ms) plus OS scheduling latency.
                time.sleep(0.05)

                # Only restore if we successfully foregrounded the target and no
                # other window stole focus in the meantime.
                current_hwnd = _get_foreground_window()
                if current_hwnd == hwnd:
                    _set_foreground_window(prev_hwnd)
                _set_cursor_pos(prev_cursor[0], prev_cursor[1])

                return result
            except Exception as exc:
                # Best-effort restore on failure.
                try:
                    _set_foreground_window(prev_hwnd)
                    _set_cursor_pos(prev_cursor[0], prev_cursor[1])
                except Exception:
                    pass
                return fail_result(error_msg=f"Pseudo-background click failed: {exc}")

    def key_press(
        self,
        target: str,
        key: str,
        method: str | None = None,
    ) -> AutoResult:
        """Press and release a key.

        Args:
            target: Target window handle (hex string) or "0" for desktop
            key: Key name (e.g., "enter", "a", "f1", "space")
            method: Override input method (None = use current)

        Returns:
            AutoResult indicating success/failure
        """
        actual_method = method or self._method

        try:
            if actual_method == "PostMessage":
                return self._key_press_postmessage(target, key)
            if actual_method == "PseudoBackground":
                return self._key_press_pseudo_background(target, key)
            return self._key_press_sendinput(key)
        except Exception as exc:
            return fail_result(error_msg=f"Key press failed: {exc}")

    def _key_press_sendinput(self, key: str) -> AutoResult:
        """Press and release a key via SendInput.

        Thread-safety: serialized via `_sendinput_lock` (TD-121).
        """
        with self._sendinput_lock:
            vk = _resolve_vk(key)
            if vk == 0:
                return fail_result(error_msg=f"Cannot resolve key: {key}")

            size = ctypes.sizeof(INPUT)
            down = _make_key_input(vk, 0)
            up = _make_key_input(vk, KEYEVENTF_KEYUP)

            result1 = user32.SendInput(1, ctypes.byref(down), size)
            time.sleep(0.03)
            result2 = user32.SendInput(1, ctypes.byref(up), size)

            if result1 == 0 or result2 == 0:
                return fail_result(error_msg=f"SendInput failed for key: {key}")

            return success_result(data={"key": key, "vk": vk})

    def _key_down(self, key: str) -> bool:
        """SendInput key-down only for a resolved key name."""
        vk = _resolve_vk(key)
        if vk == 0:
            return False
        size = ctypes.sizeof(INPUT)
        return user32.SendInput(1, ctypes.byref(_make_key_input(vk, 0)), size) == 1

    def _key_up(self, key: str) -> bool:
        """SendInput key-up only for a resolved key name."""
        vk = _resolve_vk(key)
        if vk == 0:
            return False
        size = ctypes.sizeof(INPUT)
        return user32.SendInput(1, ctypes.byref(_make_key_input(vk, KEYEVENTF_KEYUP)), size) == 1

    def key_combo(self, target: str, modifiers: list[str], key: str) -> AutoResult:
        """Press a real modifier+key combo (mod down → key → key up → mod up).

        TD-398: the old pipeline held each modifier as an independent
        tap-then-release, so Ctrl+L degenerated into 'L' typed into the
        focused field (leaked 'l' into Chrome's omnibox). This paths the
        combo through SendInput with strict ordering while temporarily
        foregrounding the target window (PseudoBackground style).
        """
        hwnd = _parse_hwnd(target) if _parse_hwnd(target) else None

        with self._sendinput_lock:
            prev_hwnd = _get_foreground_window()
            need_switch = hwnd is not None and prev_hwnd != hwnd
            prev_cursor = _get_cursor_pos()

            try:
                if need_switch:
                    from platforms.windows.input_variants import bring_to_foreground

                    fg_success = bring_to_foreground(hwnd, log=True)
                    if not fg_success:
                        logger.warning(
                            "key_combo: bring_to_foreground failed (hwnd=%s), "
                            "SendInput may go to wrong window",
                            hex(hwnd),
                        )
                    time.sleep(0.05)

                for mod in modifiers:
                    if not self._key_down(mod):
                        raise ValueError(f"cannot resolve modifier: {mod}")
                    time.sleep(0.03)
                time.sleep(0.02)

                if not self._key_down(key):
                    raise ValueError(f"cannot resolve key: {key}")
                time.sleep(0.03)
                if not self._key_up(key):
                    raise ValueError(f"key-up failed: {key}")
                time.sleep(0.02)

                for mod in reversed(modifiers):
                    self._key_up(mod)
                    time.sleep(0.02)

                time.sleep(0.05)
                if need_switch:
                    cur_hwnd = _get_foreground_window()
                    if cur_hwnd == hwnd:
                        _set_foreground_window(prev_hwnd)
                    _set_cursor_pos(prev_cursor[0], prev_cursor[1])

                return success_result(data={"modifiers": modifiers, "key": key})
            except Exception as exc:
                try:
                    for mod in reversed(modifiers):
                        self._key_up(mod)
                    _set_cursor_pos(prev_cursor[0], prev_cursor[1])
                except Exception as restore_err:  # noqa: BLE001 — best-effort restore
                    logger.warning("key_combo restore failed: %s", restore_err)
                return fail_result(error_msg=f"key_combo failed: {exc}")

    def _key_press_postmessage(self, target: str, key: str) -> AutoResult:
        """Press and release a key via PostMessage."""
        hwnd = _parse_hwnd(target)
        if not hwnd:
            return fail_result(error_msg="Invalid target hwnd for PostMessage key press")

        vk = _resolve_vk(key)
        if vk == 0:
            return fail_result(error_msg=f"Cannot resolve key: {key}")

        lparam_down = 0x00000001
        lparam_up = 0xC0000001

        user32.PostMessageW(hwnd, WM_KEYDOWN, vk, lparam_down)
        time.sleep(0.03)
        user32.PostMessageW(hwnd, WM_KEYUP, vk, lparam_up)

        return success_result(data={"key": key, "vk": vk, "hwnd": hex(hwnd)})

    def _key_press_pseudo_background(self, target: str, key: str) -> AutoResult:
        """Key press via temporary foreground + SendInput.

        Mirrors _click_pseudo_background: saves/restores foreground window and
        cursor position, foregrounds the target window, then sends the key via
        SendInput. Cursor position is restored because some games move the
        cursor on focus changes.

        Thread-safety: serialized via `_sendinput_lock` (TD-121). Internal
        call to `_key_press_sendinput` re-acquires the RLock (reentrant, no
        deadlock).
        """
        hwnd = _parse_hwnd(target)
        if not hwnd:
            return fail_result(error_msg="Invalid target hwnd for pseudo-background key press")

        with self._sendinput_lock:
            prev_hwnd = _get_foreground_window()

            # Fast path: target already foreground → plain SendInput (same as
            # _click_pseudo_background). Avoids cursor restore side effects.
            if prev_hwnd == hwnd:
                return self._key_press_sendinput(key)

            prev_cursor = _get_cursor_pos()

            try:
                # Use the AttachThreadInput trick (same as clicks) — plain
                # SetForegroundWindow is rejected by the OS for windows owned
                # by other processes, so SendInput keys (e.g. Enter) would go
                # to whatever window was foreground, silently dropping them.
                from platforms.windows.input_variants import bring_to_foreground

                fg_success = bring_to_foreground(hwnd, log=True)
                if not fg_success:
                    logger.warning(
                        "PseudoBackground key: bring_to_foreground failed (hwnd=%s), "
                        "SendInput may go to wrong window",
                        hex(hwnd),
                    )
                time.sleep(0.05)

                result = self._key_press_sendinput(key)

                # Wait for OS to process SendInput key events before restoring
                # focus (same rationale as _click_pseudo_background).
                time.sleep(0.05)

                current_hwnd = _get_foreground_window()
                if current_hwnd == hwnd:
                    _set_foreground_window(prev_hwnd)
                _set_cursor_pos(prev_cursor[0], prev_cursor[1])

                return result
            except Exception as exc:
                try:
                    _set_foreground_window(prev_hwnd)
                    _set_cursor_pos(prev_cursor[0], prev_cursor[1])
                except Exception:
                    pass
                return fail_result(error_msg=f"Pseudo-background key press failed: {exc}")

    def text_input(
        self,
        target: str,
        text: str,
        method: str | None = None,
    ) -> AutoResult:
        """Input text string.

        Args:
            target: Target window handle (hex string) or "0" for desktop
            text: Text to input
            method: Override input method (None = use current)

        Returns:
            AutoResult indicating success/failure
        """
        actual_method = method or self._method

        try:
            if actual_method == "PostMessage":
                return self._text_input_postmessage(target, text)
            if actual_method == "PseudoBackground":
                return self._text_input_pseudo_background(target, text)
            return self._text_input_sendinput(text)
        except Exception as exc:
            return fail_result(error_msg=f"Text input failed: {exc}")

    def _text_input_sendinput(self, text: str) -> AutoResult:
        """Input text via SendInput (Unicode supported).

        Thread-safety: serialized via `_sendinput_lock` (TD-121).
        """
        with self._sendinput_lock:
            size = ctypes.sizeof(INPUT)
            char_count = 0

            for char in text:
                char_code = ord(char)
                down = _make_key_unicode(char_code, 0)
                up = _make_key_unicode(char_code, KEYEVENTF_KEYUP)

                result1 = user32.SendInput(1, ctypes.byref(down), size)
                result2 = user32.SendInput(1, ctypes.byref(up), size)

                if result1 > 0 and result2 > 0:
                    char_count += 1
                time.sleep(0.01)

            logger.debug("Text input via SendInput: %d/%d chars sent", char_count, len(text))
            return success_result(data={"chars_sent": char_count, "total": len(text)})

    def _text_input_postmessage(self, target: str, text: str) -> AutoResult:
        """Input text via PostMessage (BMP characters only)."""
        hwnd = _parse_hwnd(target)
        if not hwnd:
            return fail_result(error_msg="Invalid target hwnd for PostMessage text input")

        char_count = 0
        for char in text:
            result = user32.PostMessageW(hwnd, WM_CHAR, ord(char), 0)
            if result:
                char_count += 1
            time.sleep(0.01)

        return success_result(data={"chars_sent": char_count, "total": len(text), "hwnd": hex(hwnd)})

    def _text_input_pseudo_background(self, target: str, text: str) -> AutoResult:
        """Text input via temporary foreground + SendInput.

        Mirrors the other pseudo-background helpers: temporarily foreground
        the target window so SendInput reaches it, then restore focus/cursor.

        Thread-safety: serialized via `_sendinput_lock` (TD-121). Internal
        call to `_text_input_sendinput` re-acquires the RLock (reentrant, no
        deadlock).
        """
        hwnd = _parse_hwnd(target)
        if not hwnd:
            return fail_result(error_msg="Invalid target hwnd for pseudo-background text input")

        with self._sendinput_lock:
            prev_hwnd = _get_foreground_window()

            # Fast path: target already foreground → plain SendInput (same as
            # _click_pseudo_background). Avoids cursor restore side effects.
            if prev_hwnd == hwnd:
                return self._text_input_sendinput(text)

            prev_cursor = _get_cursor_pos()

            try:
                # Same AttachThreadInput trick as clicks/keys: plain
                # SetForegroundWindow is rejected for cross-process windows,
                # which makes SendInput text go to the wrong foreground window.
                from platforms.windows.input_variants import bring_to_foreground

                fg_success = bring_to_foreground(hwnd, log=True)
                if not fg_success:
                    logger.warning(
                        "PseudoBackground text: bring_to_foreground failed (hwnd=%s), "
                        "SendInput may go to wrong window",
                        hex(hwnd),
                    )
                time.sleep(0.05)

                result = self._text_input_sendinput(text)

                # Wait for OS to process SendInput key events before restoring
                # focus (same rationale as _click_pseudo_background).
                time.sleep(0.05)

                current_hwnd = _get_foreground_window()
                if current_hwnd == hwnd:
                    _set_foreground_window(prev_hwnd)
                _set_cursor_pos(prev_cursor[0], prev_cursor[1])

                return result
            except Exception as exc:
                try:
                    _set_foreground_window(prev_hwnd)
                    _set_cursor_pos(prev_cursor[0], prev_cursor[1])
                except Exception:
                    pass
                return fail_result(error_msg=f"Pseudo-background text input failed: {exc}")

    def swipe(
        self,
        target: str,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
        method: str | None = None,
    ) -> AutoResult:
        """Perform a swipe/drag gesture.

        Args:
            target: Target window handle (hex string) or "0" for desktop
            x1, y1: Start coordinates
            x2, y2: End coordinates
            duration_ms: Swipe duration in milliseconds
            method: Override input method (None = use current)

        Returns:
            AutoResult indicating success/failure
        """
        actual_method = method or self._method

        try:
            if actual_method == "PostMessage":
                return self._swipe_postmessage(target, x1, y1, x2, y2, duration_ms)
            return self._swipe_sendinput(target, x1, y1, x2, y2, duration_ms)
        except Exception as exc:
            return fail_result(error_msg=f"Swipe failed: {exc}")

    def _swipe_sendinput(self, target: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> AutoResult:
        """Swipe via SendInput. Sends mousedown → moves → mouseup for a true drag gesture.

        Converts window-relative coordinates to screen-absolute via ClientToScreen
        when target hwnd is provided.

        Coordinate contract: (x1,y1)/(x2,y2) are LOGICAL client coords.
        ClientToScreen expects PHYSICAL, so we convert using _dpi_ratio first.

        Thread-safety: serialized via `_sendinput_lock` (TD-121).
        """
        with self._sendinput_lock:
            size = ctypes.sizeof(INPUT)
            screen_w = ctypes.windll.user32.GetSystemMetrics(0)
            screen_h = ctypes.windll.user32.GetSystemMetrics(1)

            # Convert logical→physical, then window-relative to screen-absolute.
            hwnd = _parse_hwnd(target)
            px1, py1 = self._logical_to_physical(x1, y1)
            px2, py2 = self._logical_to_physical(x2, y2)
            sx1, sy1 = _client_to_screen(hwnd, px1, py1)
            self._emit_coord_trace_safe(
                step="client_to_screen",
                raw=(px1, py1),
                converted=(sx1, sy1),
                formula=f"ClientToScreen(hwnd={hwnd}, physical=({px1},{py1})) -> screen=({sx1},{sy1})",
                coord_system_in="physical",
                coord_system_out="screen",
                extra={"hwnd": hwnd, "window_offset": (sx1 - px1, sy1 - py1)},
            )
            sx2, sy2 = _client_to_screen(hwnd, px2, py2)
            self._emit_coord_trace_safe(
                step="client_to_screen",
                raw=(px2, py2),
                converted=(sx2, sy2),
                formula=f"ClientToScreen(hwnd={hwnd}, physical=({px2},{py2})) -> screen=({sx2},{sy2})",
                coord_system_in="physical",
                coord_system_out="screen",
                extra={"hwnd": hwnd, "window_offset": (sx2 - px2, sy2 - py2)},
            )

            steps = max(int(duration_ms / 16), 1)
            step_delay = duration_ms / (steps * 1000.0) if steps > 0 else 0.01

            # Mouse down at start position
            abs_x = int(sx1 * 65535 / screen_w)
            abs_y = int(sy1 * 65535 / screen_h)
            down = INPUT(
                type=INPUT_MOUSE,
                union=_InputUnion(mi=MOUSEINPUT(
                    dx=abs_x, dy=abs_y,
                    mouseData=0,
                    dwFlags=MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE,
                    time=0, dwExtraInfo=None,
                )),
            )
            user32.SendInput(1, ctypes.byref(down), size)

            for i in range(steps + 1):
                t = i / steps if steps > 0 else 1
                x = int(sx1 + (sx2 - sx1) * t)
                y = int(sy1 + (sy2 - sy1) * t)
                abs_x = int(x * 65535 / screen_w)
                abs_y = int(y * 65535 / screen_h)

                move = INPUT(
                    type=INPUT_MOUSE,
                    union=_InputUnion(mi=MOUSEINPUT(
                        dx=abs_x, dy=abs_y,
                        mouseData=0,
                        dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
                        time=0, dwExtraInfo=None,
                    )),
                )
                user32.SendInput(1, ctypes.byref(move), size)
                time.sleep(step_delay)

            # Mouse up at end position
            abs_x = int(sx2 * 65535 / screen_w)
            abs_y = int(sy2 * 65535 / screen_h)
            up = INPUT(
                type=INPUT_MOUSE,
                union=_InputUnion(mi=MOUSEINPUT(
                    dx=abs_x, dy=abs_y,
                    mouseData=0,
                    dwFlags=MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE,
                    time=0, dwExtraInfo=None,
                )),
            )
            user32.SendInput(1, ctypes.byref(up), size)

            return success_result(data={
                "from": {"x": x1, "y": y1},
                "to": {"x": x2, "y": y2},
                "steps": steps,
            })

    def _swipe_postmessage(self, target: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int) -> AutoResult:
        """Swipe via PostMessage. Sends WM_LBUTTONDOWN → WM_MOUSEMOVE → WM_LBUTTONUP for a true drag."""
        hwnd = _parse_hwnd(target)
        if not hwnd:
            return fail_result(error_msg="Invalid target hwnd for PostMessage swipe")

        steps = max(int(duration_ms / 16), 1)
        step_delay = duration_ms / (steps * 1000.0) if steps > 0 else 0.01

        # Mouse down at start position (wparam = MK_LBUTTON = 0x0001)
        lparam_down = (y1 << 16) | (x1 & 0xFFFF)
        user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 0x0001, lparam_down)

        for i in range(steps + 1):
            t = i / steps if steps > 0 else 1
            x = int(x1 + (x2 - x1) * t)
            y = int(y1 + (y2 - y1) * t)
            lparam = (y << 16) | (x & 0xFFFF)
            user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0x0001, lparam)
            time.sleep(step_delay)

        # Mouse up at end position
        lparam_up = (y2 << 16) | (x2 & 0xFFFF)
        user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam_up)

        return success_result(data={
            "from": {"x": x1, "y": y1},
            "to": {"x": x2, "y": y2},
            "hwnd": hex(hwnd),
        })

    def find_target_child(
        self,
        parent_hwnd: int,
        class_name: str | None = None,
        title: str | None = None,
    ) -> int | None:
        """Find a child window of the target for precise input targeting.

        Args:
            parent_hwnd: Parent window handle
            class_name: Child window class name filter
            title: Child window title filter

        Returns:
            Child hwnd or None if not found
        """
        def enum_callback(hwnd: int, _lparam) -> int:
            buffer = ctypes.create_unicode_buffer(256)
            if class_name:
                user32.GetClassNameW(hwnd, buffer, 256)
                if class_name.lower() not in buffer.value.lower():
                    return 1
            if title:
                user32.GetWindowTextW(hwnd, buffer, 256)
                if title.lower() not in buffer.value.lower():
                    return 1
            found_hwnds.append(hwnd)
            return 0

        found_hwnds: list[int] = []
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_int)
        callback = callback_type(enum_callback)
        user32.EnumChildWindows(parent_hwnd, callback, 0)

        return found_hwnds[0] if found_hwnds else None
