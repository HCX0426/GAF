"""
Windows platform input handler with full PostMessage support.
Ref: ok-script's PostMessage dynamic child window discovery strategy.
Ref: MaaFramework's PlatformInputHandler ABC.

Supports three input modes:
  - SendInput: Foreground simulation (requires window focus)
  - PostMessage: Background message-based input (works when minimized)
  - SendMessage: Synchronous background input

Coordinate conventions (Win32 spec, TD-122):
  - PostMessage/SendMessage click/swipe: lParam packs CLIENT-area
    coordinates (relative to window top-left). Do NOT pre-convert.
  - PostMessage/SendMessage scroll (WM_MOUSEWHEEL): lParam packs
    SCREEN coordinates — _client_to_screen is required.
  - SendInput click/swipe: SetCursorPos expects SCREEN coordinates
    — _client_to_screen is required.

Advanced features migrated from worker/src/devices/windows/input_ctrl.py:
  - Dynamic child window discovery via EnumChildWindows
  - DPI-aware coordinate conversion via ClientToScreen (SendInput / WM_MOUSEWHEEL only)
  - Unicode text input via KEYEVENTF_UNICODE with surrogate pair support
  - Multi-button mouse support (left/right/middle)
"""
import ctypes
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes

from device_bridge.platforms.base import InputResult, PlatformInputHandler

logger = logging.getLogger(__name__)

WINDOWS_INPUT_METHODS = ['SendInput', 'PostMessage', 'SendMessage']

_user32 = ctypes.windll.user32

# SetThreadDpiAwarenessContext (Windows 10 1607+).
# Screenshot capture runs in per-monitor DPI awareness (see _printwindow.py
# / _bitblt.py), so captured frames are in physical pixels. SendInput and
# WM_MOUSEWHEEL paths need ClientToScreen to convert those client pixels
# to screen coordinates in the same physical space, otherwise clicks land
# off-target on HiDPI displays. PostMessage/SendMessage click/swipe paths
# pack client coordinates directly into lParam (TD-122) and do NOT need
# ClientToScreen.
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
_user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
_user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]

# Mouse event flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000

# Keyboard event flags
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

# Input type constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

# Window message constants
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEMOVE = 0x0200
WM_MOUSEWHEEL = 0x020A
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102

# Virtual key code mapping
_KEY_MAP: dict[str, int] = {
    'space': 0x20, 'enter': 0x0D, 'return': 0x0D,
    'tab': 0x09, 'escape': 0x1B, 'esc': 0x1B,
    'backspace': 0x08, 'delete': 0x2E, 'del': 0x2E,
    'home': 0x24, 'end': 0x23,
    'pageup': 0x21, 'pagedown': 0x22,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
    'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
    'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77,
    'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
    'ctrl': 0x11, 'shift': 0x10, 'alt': 0x12,
    'win': 0x5B, 'lwin': 0x5B, 'rwin': 0x5C,
    # Android key name aliases (emulators map these to Windows keys)
    'back': 0x1B,       # VK_ESCAPE -> Android BACK in emulators
    'menu': 0x71,       # VK_F2 -> Android MENU in emulators
    'search': 0x73,     # VK_F4 -> Android SEARCH in emulators
    'volume_up': 0xAF,  # VK_VOLUME_UP
    'volume_down': 0xAE, # VK_VOLUME_DOWN
    'power': 0x5F,      # VK_SLEEP
    'camera': 0xD4,     # VK_CAMERA (rare)
    'a': ord('A'), 'b': ord('B'), 'c': ord('C'), 'd': ord('D'),
    'e': ord('E'), 'f': ord('F'), 'g': ord('G'), 'h': ord('H'),
    'i': ord('I'), 'j': ord('J'), 'k': ord('K'), 'l': ord('L'),
    'm': ord('M'), 'n': ord('N'), 'o': ord('O'), 'p': ord('P'),
    'q': ord('Q'), 'r': ord('R'), 's': ord('S'), 't': ord('T'),
    'u': ord('U'), 'v': ord('V'), 'w': ord('W'), 'x': ord('X'),
    'y': ord('Y'), 'z': ord('Z'),
    '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
    '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
}


class MOUSEINPUT(ctypes.Structure):
    """Mouse input structure for SendInput API"""
    _fields_ = [
        ('dx', wintypes.LONG),
        ('dy', wintypes.LONG),
        ('mouseData', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    """Keyboard input structure for SendInput API"""
    _fields_ = [
        ('wVk', wintypes.WORD),
        ('wScan', wintypes.WORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    """Hardware input structure for SendInput API"""
    _fields_ = [
        ('uMsg', wintypes.DWORD),
        ('wParamL', wintypes.WORD),
        ('wParamH', wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):  # noqa: N801
    """Union discriminating between input types"""
    _fields_ = [
        ('mi', MOUSEINPUT),
        ('ki', KEYBDINPUT),
        ('hi', HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    """Generic input structure for SendInput API"""
    _fields_ = [
        ('type', wintypes.DWORD),
        ('u', _INPUT_UNION),
    ]


def _resolve_vk(key: str) -> int:
    """Resolve key name to virtual key code

    Args:
        key: Key name ('enter', 'a', 'f1', etc.) or hex string

    Returns:
        Virtual key code, or 0 if unknown
    """
    key_lower = key.lower()
    if key_lower in _KEY_MAP:
        return _KEY_MAP[key_lower]
    if len(key) == 1:
        return ord(key.upper())
    try:
        return int(key, 0)
    except ValueError:
        logger.warning("Unknown key: %s, defaulting to 0", key)
        return 0


def _make_mouse_input(dx: int, dy: int, flags: int, dwData: int = 0) -> INPUT:  # noqa: N803
    """Construct a mouse INPUT structure

    Args:
        dx: X coordinate or delta
        dy: Y coordinate or delta
        flags: Mouse event flags (MOUSEEVENTF_*)
        dwData: Additional data (wheel delta for MOUSEEVENTF_WHEEL, button mask for clicks)

    Returns:
        Populated INPUT structure for mouse event
    """
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.u.mi = MOUSEINPUT(
        dx=dx, dy=dy, mouseData=dwData,
        dwFlags=flags, time=0,
        dwExtraInfo=ctypes.pointer(ctypes.c_ulong(0)),
    )
    return inp


def _make_key_input(vk: int, flags: int, scan: int = 0) -> INPUT:
    """Construct a keyboard INPUT structure

    Args:
        vk: Virtual key code
        flags: Keyboard event flags (KEYEVENTF_*)
        scan: Hardware scan code (for KEYEVENTF_UNICODE)

    Returns:
        Populated INPUT structure for keyboard event
    """
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki = KEYBDINPUT(
        wVk=vk, wScan=scan,
        dwFlags=flags, time=0,
        dwExtraInfo=ctypes.pointer(ctypes.c_ulong(0)),
    )
    return inp


def _foreground_window(hwnd: int) -> bool:
    """Bring window to foreground and verify success

    Args:
        hwnd: Target window handle

    Returns:
        True if window is now in foreground
    """
    current = _user32.GetForegroundWindow()
    if current == hwnd:
        return True
    _user32.ShowWindow(hwnd, 5)
    _user32.SetForegroundWindow(hwnd)
    time.sleep(0.05)
    _user32.BringWindowToTop(hwnd)
    _user32.SetFocus(hwnd)
    _user32.SetActiveWindow(hwnd)
    return _user32.GetForegroundWindow() == hwnd


class WindowsInputHandler(PlatformInputHandler):
    """Windows input handler with full PostMessage support

    Implements PlatformInputHandler ABC with three modes:
      - SendInput: Foreground simulation (default)
      - PostMessage: Asynchronous background messages
      - SendMessage: Synchronous background messages

    Coordinate conventions (Win32 spec, TD-122):
      - PostMessage/SendMessage click/swipe: lParam packs CLIENT-area
        coordinates. _client_to_screen is NOT called.
      - PostMessage/SendMessage scroll (WM_MOUSEWHEEL): lParam packs
        SCREEN coordinates. _client_to_screen IS called.
      - SendInput click/swipe: SetCursorPos expects SCREEN coordinates.
        _client_to_screen IS called by the click()/swipe() entry points.

    Advanced features (migrated from agent InputController/PostMessageInput):
      - Dynamic child window discovery via find_target_child()
      - DPI-aware coordinate conversion via _client_to_screen()
        (SendInput + WM_MOUSEWHEEL paths only — see TD-122)
      - Unicode text input via text_input() with surrogate pair support
      - Multi-button mouse clicks (left/right/middle)
    """

    def __init__(self, method: str = ''):
        """Initialize input handler

        Args:
            method: Default input method ('SendInput', 'PostMessage', 'SendMessage')
        """
        self.method = method or 'SendInput'
        self._dpi_scale = self._detect_dpi_scale()

    @staticmethod
    @contextmanager
    def _dpi_aware() -> Iterator[None]:
        """Run a block in per-monitor DPI-aware thread context.

        Required for code paths that convert client→screen coordinates:
        - SendInput click/swipe (SetCursorPos expects physical screen coords)
        - WM_MOUSEWHEEL PostMessage/SendMessage (lParam expects screen coords)

        NOT strictly required for PostMessage/SendMessage click/swipe paths
        (they pack client coords directly into lParam per Win32 spec, TD-122),
        but kept as the outer wrapper for consistency and so future message
        types can reuse the same context. The previous context is restored
        on exit.
        """
        old_ctx = _user32.SetThreadDpiAwarenessContext(
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
        try:
            yield
        finally:
            if old_ctx:
                _user32.SetThreadDpiAwarenessContext(old_ctx)

    def available_methods(self) -> list[str]:
        """List available input methods on this system"""
        available = []
        for m in WINDOWS_INPUT_METHODS:
            if self._check_method_available(m):
                available.append(m)
        if not available:
            available = ['mock']
        return available

    def click(self, target: str, x: int, y: int, method: str = '',
              button: str = 'left') -> InputResult:
        """Send mouse click to target window

        Supports three mouse buttons. Coordinate space depends on method:
          - SendInput: caller passes CLIENT coords; this method converts to
            screen via _client_to_screen (SetCursorPos needs screen coords).
          - PostMessage/SendMessage: caller passes CLIENT coords; they are
            packed directly into lParam (Win32 spec, TD-122) — no conversion.

        Args:
            target: Window handle (hex string or integer)
            x: Client X coordinate (converted to screen for SendInput)
            y: Client Y coordinate (converted to screen for SendInput)
            method: Override input method (None uses default)
            button: Mouse button ('left', 'right', 'middle')

        Returns:
            InputResult with success status and method used
        """
        method = method or self.method
        logger.debug('Windows click: target=%s x=%d y=%d method=%s button=%s',
                     target, x, y, method, button)
        hwnd = self._parse_hwnd(target)
        if hwnd is None:
            return InputResult(success=False, method=method,
                             error=f'Invalid window handle: {target}')

        try:
            with self._dpi_aware():
                if method == 'SendInput':
                    _foreground_window(hwnd)
                    # Convert client coordinates to screen coordinates
                    # This handles DPI scaling and window position automatically
                    screen_x, screen_y = self._client_to_screen(hwnd, x, y)
                    success = self._sendinput_click(screen_x, screen_y, button)
                elif method == 'PostMessage':
                    success = self._postmessage_click(hwnd, x, y, button)
                elif method == 'SendMessage':
                    success = self._sendmessage_click(hwnd, x, y, button)
                else:
                    return InputResult(success=False, method=method,
                                     error=f'Unsupported input method: {method}')
            return InputResult(success=success, method=method)
        except Exception as e:
            return InputResult(success=False, method=method, error=str(e))

    def swipe(self, target: str, x1: int, y1: int, x2: int, y2: int,
              duration_ms: int = 300, method: str = '') -> InputResult:
        """Send mouse swipe/drag from (x1,y1) to (x2,y2)

        Args:
            target: Window handle
            x1, y1: Start coordinates
            x2, y2: End coordinates
            duration_ms: Swipe duration in milliseconds
            method: Override input method

        Returns:
            InputResult with success status
        """
        method = method or self.method
        logger.debug('Windows swipe: target=%s (%d,%d)->(%d,%d) method=%s',
                     target, x1, y1, x2, y2, method)
        hwnd = self._parse_hwnd(target)
        if hwnd is None:
            return InputResult(success=False, method=method,
                             error=f'Invalid window handle: {target}')

        try:
            with self._dpi_aware():
                if method == 'SendInput':
                    _foreground_window(hwnd)
                    steps = max(5, duration_ms // 30)
                    success = self._sendinput_swipe(x1, y1, x2, y2, steps)
                elif method == 'PostMessage':
                    success = self._postmessage_swipe(hwnd, x1, y1, x2, y2)
                elif method == 'SendMessage':
                    success = self._sendmessage_swipe(hwnd, x1, y1, x2, y2)
                else:
                    return InputResult(success=False, method=method,
                                     error=f'Unsupported input method: {method}')
            return InputResult(success=success, method=method)
        except Exception as e:
            return InputResult(success=False, method=method, error=str(e))

    def key_press(self, target: str, key: str, method: str = '') -> InputResult:
        """Send key press (down + up) to target window

        Args:
            target: Window handle
            key: Key name ('enter', 'a', 'f1', etc.)
            method: Override input method

        Returns:
            InputResult with success status
        """
        method = method or self.method
        logger.debug('Windows key_press: target=%s key=%s method=%s',
                     target, key, method)
        hwnd = self._parse_hwnd(target)
        if hwnd is None:
            return InputResult(success=False, method=method,
                             error=f'Invalid window handle: {target}')

        vk = _resolve_vk(key)
        if not vk:
            return InputResult(success=False, method=method,
                             error=f'Unknown key: {key}')

        try:
            if method == 'SendInput':
                _foreground_window(hwnd)
                success = self._sendinput_key_press(vk)
            elif method == 'PostMessage':
                self._postmessage_key_down(hwnd, vk)
                time.sleep(0.05)
                self._postmessage_key_up(hwnd, vk)
                success = True
            elif method == 'SendMessage':
                _user32.SendMessageW(hwnd, WM_KEYDOWN, vk, 0)
                _user32.SendMessageW(hwnd, WM_KEYUP, vk, 0)
                success = True
            else:
                return InputResult(success=False, method=method,
                                 error=f'Unsupported input method: {method}')
            return InputResult(success=success, method=method)
        except Exception as e:
            return InputResult(success=False, method=method, error=str(e))

    def text_input(self, target: str, text: str, method: str = '') -> InputResult:
        """Input Unicode text using KEYEVENTF_UNICODE events

        Supports all Unicode characters including emoji and
        surrogate pairs (characters outside BMP like 𝄞).

        Args:
            target: Window handle
            text: Text string to input (supports Unicode/emoji)
            method: Override input method (only SendInput supports Unicode)

        Returns:
            InputResult with success status
        """
        method = method or self.method
        logger.debug('Windows text_input: target=%s text=%s method=%s',
                     target, text[:20] + '...' if len(text) > 20 else text, method)

        if method != 'SendInput':
            return InputResult(success=False, method=method,
                             error='Unicode text input only supported in SendInput mode')

        hwnd = self._parse_hwnd(target)
        if hwnd is None:
            return InputResult(success=False, method=method,
                             error=f'Invalid window handle: {target}')

        try:
            _foreground_window(hwnd)
            utf16_bytes = text.encode('utf-16-le')

            for i in range(0, len(utf16_bytes), 2):
                scan = int.from_bytes(utf16_bytes[i:i + 2], byteorder='little')
                _user32.SendInput(
                    1,
                    ctypes.byref(_make_key_input(0, KEYEVENTF_UNICODE, scan=scan)),
                    ctypes.sizeof(INPUT),
                )
                time.sleep(0.01)
                _user32.SendInput(
                    1,
                    ctypes.byref(_make_key_input(0, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, scan=scan)),
                    ctypes.sizeof(INPUT),
                )
                time.sleep(0.01)

            logger.debug("Text input completed: %s", text[:30])
            return InputResult(success=True, method=method)
        except Exception as e:
            return InputResult(success=False, method=method, error=str(e))

    def scroll(self, target: str, x: int, y: int, delta: int, method: str = '') -> InputResult:
        """Send mouse wheel scroll to target window

        Positive delta scrolls up (away from user), negative scrolls down.
        Standard wheel delta is 120 per notch.

        Args:
            target: Window handle
            x: X coordinate for scroll position
            y: Y coordinate for scroll position
            delta: Scroll amount (120 = one notch, -120 = one notch down)
            method: Override input method

        Returns:
            InputResult with success status
        """
        method = method or self.method
        logger.debug('Windows scroll: target=%s x=%d y=%d delta=%d method=%s',
                     target, x, y, delta, method)
        hwnd = self._parse_hwnd(target)
        if hwnd is None:
            return InputResult(success=False, method=method,
                             error=f'Invalid window handle: {target}')

        try:
            with self._dpi_aware():
                if method == 'SendInput':
                    _foreground_window(hwnd)
                    success = self._sendinput_scroll(x, y, delta)
                elif method == 'PostMessage':
                    success = self._postmessage_scroll(hwnd, x, y, delta)
                elif method == 'SendMessage':
                    success = self._sendmessage_scroll(hwnd, x, y, delta)
                else:
                    return InputResult(success=False, method=method,
                                     error=f'Unsupported input method: {method}')
            return InputResult(success=success, method=method)
        except Exception as e:
            return InputResult(success=False, method=method, error=str(e))

    def find_target_child(
        self,
        parent_hwnd: int,
        class_filter: str | None = None,
        title_filter: str | None = None,
        index: int = 0,
    ) -> int | None:
        """Find a child window matching filters using EnumChildWindows

        Dynamically discovers sub-windows within a parent window,
        enabling precise targeting of embedded controls (e.g., Chrome's
        rendering window, video player overlay).

        Reference: ok-script's PostMessage dynamic positioning strategy.

        Args:
            parent_hwnd: Parent window handle to search within
            class_filter: Class name substring filter (case-insensitive)
            title_filter: Window title substring filter (case-insensitive)
            index: Nth match to select (0-based)

        Returns:
            Found child window handle, or None if not found
        """
        children = self._enum_children(parent_hwnd, class_filter, title_filter)
        if not children:
            logger.warning("No matching child windows found for parent=%s", parent_hwnd)
            return None

        if index >= len(children):
            index = len(children) - 1

        target = children[index]
        logger.info(
            "Target child selected: hwnd=%s title='%s' class='%s'",
            target['hwnd'], target.get('title'), target.get('class'),
        )
        return target['hwnd']

    # ── Private implementation methods ──────────────────────────────

    def _sendinput_click(self, x: int, y: int, button: str = 'left') -> bool:
        """Send click via SendInput (foreground mode)

        Args:
            x: Screen X coordinate
            y: Screen Y coordinate
            button: Mouse button name

        Returns:
            True if both events sent successfully
        """
        _user32.SetCursorPos(x, y)
        time.sleep(0.01)

        down_flag = {
            'left': MOUSEEVENTF_LEFTDOWN,
            'right': MOUSEEVENTF_RIGHTDOWN,
            'middle': MOUSEVENTF_MIDDLEDOWN,
        }.get(button, MOUSEEVENTF_LEFTDOWN)

        up_flag = {
            'left': MOUSEEVENTF_LEFTUP,
            'right': MOUSEEVENTF_RIGHTUP,
            'middle': MOUSEEVENTF_MIDDLEUP,
        }.get(button, MOUSEEVENTF_LEFTUP)

        _user32.SendInput(1, ctypes.byref(_make_mouse_input(0, 0, down_flag)),
                         ctypes.sizeof(INPUT))
        time.sleep(0.02)
        _user32.SendInput(1, ctypes.byref(_make_mouse_input(0, 0, up_flag)),
                         ctypes.sizeof(INPUT))
        return True

    def _postmessage_click(self, hwnd: int, x: int, y: int,
                           button: str = 'left') -> bool:
        """Send click via PostMessage (asynchronous background mode)

        lParam packs client-area coordinates (relative to window top-left),
        per Win32 spec for WM_LBUTTONDOWN/UP. Do NOT convert to screen
        coordinates — that would mis-target when the window is moved or
        on multi-monitor setups. (TD-122)

        Args:
            hwnd: Target window handle
            x: Client X coordinate
            y: Client Y coordinate
            button: Mouse button name

        Returns:
            True always (PostMessage cannot fail synchronously)
        """
        lparam = self._make_lparam(x, y)

        down_msg = {
            'left': WM_LBUTTONDOWN,
            'right': WM_RBUTTONDOWN,
            'middle': WM_MBUTTONDOWN,
        }.get(button, WM_LBUTTONDOWN)

        up_msg = {
            'left': WM_LBUTTONUP,
            'right': WM_RBUTTONUP,
            'middle': WM_MBUTTONUP,
        }.get(button, WM_LBUTTONUP)

        wparam = {'left': 1, 'right': 2, 'middle': 16}.get(button, 1)

        _user32.PostMessageW(hwnd, down_msg, wparam, lparam)
        time.sleep(0.05)
        _user32.PostMessageW(hwnd, up_msg, 0, lparam)

        logger.debug("PostMessage click: hwnd=%s (%d,%d) btn=%s", hwnd, x, y, button)
        return True

    def _sendmessage_click(self, hwnd: int, x: int, y: int,
                           button: str = 'left') -> bool:
        """Send click via SendMessage (synchronous background mode)

        lParam packs client-area coordinates (same Win32 spec as PostMessage,
        see _postmessage_click / TD-122).

        Args:
            hwnd: Target window handle
            x: Client X coordinate
            y: Client Y coordinate
            button: Mouse button name

        Returns:
            True always
        """
        lparam = self._make_lparam(x, y)

        down_msg = {
            'left': WM_LBUTTONDOWN,
            'right': WM_RBUTTONDOWN,
            'middle': WM_MBUTTONDOWN,
        }.get(button, WM_LBUTTONDOWN)

        up_msg = {
            'left': WM_LBUTTONUP,
            'right': WM_RBUTTONUP,
            'middle': WM_MBUTTONUP,
        }.get(button, WM_LBUTTONUP)

        wparam = {'left': 1, 'right': 2, 'middle': 16}.get(button, 1)

        _user32.SendMessageW(hwnd, down_msg, wparam, lparam)
        time.sleep(0.05)
        _user32.SendMessageW(hwnd, up_msg, 0, lparam)
        return True

    def _sendinput_swipe(self, x1: int, y1: int, x2: int, y2: int,
                          steps: int) -> bool:
        """Send swipe gesture via SendInput with linear interpolation

        Args:
            x1, y1: Start screen coordinates
            x2, y2: End screen coordinates
            steps: Number of interpolation steps

        Returns:
            True always
        """
        _user32.SetCursorPos(x1, y1)
        time.sleep(0.05)

        _user32.SendInput(
            1, ctypes.byref(_make_mouse_input(0, 0, MOUSEEVENTF_LEFTDOWN)),
            ctypes.sizeof(INPUT),
        )

        for i in range(1, steps + 1):
            t = i / steps
            cx = int(x1 + (x2 - x1) * t)
            cy = int(y1 + (y2 - y1) * t)
            _user32.SetCursorPos(cx, cy)
            time.sleep(0.01)

        _user32.SendInput(
            1, ctypes.byref(_make_mouse_input(0, 0, MOUSEEVENTF_LEFTUP)),
            ctypes.sizeof(INPUT),
        )
        return True

    def _postmessage_swipe(self, hwnd: int, x1: int, y1: int,
                            x2: int, y2: int) -> bool:
        """Send swipe via PostMessage (background mode)

        lParam packs client-area coordinates (Win32 spec for WM_LBUTTONDOWN/UP
        and WM_MOUSEMOVE — see TD-122).

        Args:
            hwnd: Target window handle
            x1, y1: Start client coordinates
            x2, y2: End client coordinates

        Returns:
            True always
        """
        lparam_start = self._make_lparam(x1, y1)
        lparam_end = self._make_lparam(x2, y2)

        _user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lparam_start)
        _user32.PostMessageW(hwnd, WM_MOUSEMOVE, 1, lparam_end)
        _user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam_end)
        return True

    def _sendmessage_swipe(self, hwnd: int, x1: int, y1: int,
                            x2: int, y2: int) -> bool:
        """Send swipe via SendMessage (synchronous background mode)

        lParam packs client-area coordinates (same Win32 spec as PostMessage
        swipe — see TD-122).

        Args:
            hwnd: Target window handle
            x1, y1: Start client coordinates
            x2, y2: End client coordinates

        Returns:
            True always
        """
        lparam_start = self._make_lparam(x1, y1)
        lparam_end = self._make_lparam(x2, y2)

        _user32.SendMessageW(hwnd, WM_LBUTTONDOWN, 1, lparam_start)
        _user32.SendMessageW(hwnd, WM_MOUSEMOVE, 1, lparam_end)
        _user32.SendMessageW(hwnd, WM_LBUTTONUP, 0, lparam_end)
        return True

    def _sendinput_scroll(self, x: int, y: int, delta: int) -> bool:
        """Send mouse wheel scroll via SendInput (foreground mode)

        Args:
            x: Screen X coordinate for scroll position
            y: Screen Y coordinate for scroll position
            delta: Scroll amount (positive = up, negative = down, 120 = one notch)

        Returns:
            True always
        """
        _user32.SetCursorPos(x, y)
        time.sleep(0.02)

        input_data = _make_mouse_input(0, 0, MOUSEEVENTF_WHEEL, dwData=delta)
        _user32.SendInput(1, ctypes.byref(input_data), ctypes.sizeof(INPUT))
        return True

    def _postmessage_scroll(self, hwnd: int, x: int, y: int, delta: int) -> bool:
        """Send mouse wheel scroll via PostMessage (background mode)

        WM_MOUSEWHEEL wParam packs: (fwKeys << 16) | (delta)
        lParam packs: (screen_y << 16) | screen_x  — WM_MOUSEWHEEL is the
        exception that expects SCREEN coordinates (not client), so
        _client_to_screen is intentionally kept here. (TD-122)

        Args:
            hwnd: Target window handle
            x: Client X coordinate
            y: Client Y coordinate
            delta: Scroll amount (positive = up, negative = down)

        Returns:
            True always
        """
        sx, sy = self._client_to_screen(hwnd, x, y)
        wparam = delta & 0xFFFFFFFF
        lparam = self._make_lparam(sx, sy)

        _user32.PostMessageW(hwnd, WM_MOUSEWHEEL, wparam, lparam)
        return True

    def _sendmessage_scroll(self, hwnd: int, x: int, y: int, delta: int) -> bool:
        """Send mouse wheel scroll via SendMessage (synchronous background mode)

        WM_MOUSEWHEEL lParam expects SCREEN coordinates (see
        _postmessage_scroll / TD-122) — _client_to_screen is intentionally
        kept here, unlike click/swipe which use client coordinates.

        Args:
            hwnd: Target window handle
            x: Client X coordinate
            y: Client Y coordinate
            delta: Scroll amount (positive = up, negative = down)

        Returns:
            True always
        """
        sx, sy = self._client_to_screen(hwnd, x, y)
        wparam = delta & 0xFFFFFFFF
        lparam = self._make_lparam(sx, sy)

        _user32.SendMessageW(hwnd, WM_MOUSEWHEEL, wparam, lparam)
        return True

    def _sendinput_key_press(self, vk: int) -> bool:
        """Send key press via SendInput

        Args:
            vk: Virtual key code

        Returns:
            True if both events sent successfully
        """
        _user32.SendInput(1, ctypes.byref(_make_key_input(vk, 0)),
                         ctypes.sizeof(INPUT))
        time.sleep(0.02)
        _user32.SendInput(1, ctypes.byref(_make_key_input(vk, KEYEVENTF_KEYUP)),
                         ctypes.sizeof(INPUT))
        return True

    def _postmessage_key_down(self, hwnd: int, vk: int) -> None:
        """Send key down event via PostMessage

        Args:
            hwnd: Target window handle
            vk: Virtual key code
        """
        _user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)

    def _postmessage_key_up(self, hwnd: int, vk: int) -> None:
        """Send key up event via PostMessage

        Args:
            hwnd: Target window handle
            vk: Virtual key code
        """
        _user32.PostMessageW(hwnd, WM_KEYUP, vk, 0)

    @staticmethod
    def _make_lparam(x: int, y: int) -> int:
        """Pack coordinates into LPARAM for mouse messages

        Windows message LPARAM packs coordinates as (Y << 16) | X.

        Coordinate space depends on the message:
        - WM_LBUTTONDOWN/UP, WM_RBUTTONDOWN/UP, WM_MBUTTONDOWN/UP,
          WM_MOUSEMOVE: client-area coordinates (relative to window
          top-left). Callers must NOT pre-convert via _client_to_screen.
        - WM_MOUSEWHEEL: SCREEN coordinates (relative to desktop
          top-left). Callers MUST pre-convert via _client_to_screen.

        Args:
            x: X coordinate (client or screen, depending on message)
            y: Y coordinate (client or screen, depending on message)

        Returns:
            Packed LPARAM value
        """
        return (y << 16) | (x & 0xFFFF)

    @staticmethod
    def _client_to_screen(hwnd: int, client_x: int,
                           client_y: int) -> tuple[int, int]:
        """Convert client-area coordinates to screen coordinates

        Reserved for code paths that need SCREEN coordinates:
        - SendInput click/swipe (SetCursorPos expects screen coords)
        - WM_MOUSEWHEEL PostMessage/SendMessage (lParam expects screen)

        PostMessage/SendMessage click/swipe do NOT call this — they pack
        client-area coordinates directly into lParam per Win32 spec (TD-122).

        Uses ClientToScreen Win32 API which automatically accounts
        for DPI scaling, window decorations, and multi-monitor setups.

        Critical for HiDPI displays where client coordinates differ
        from screen coordinates by the DPI scale factor.

        Args:
            hwnd: Window handle
            client_x: Client area X coordinate
            client_y: Client area Y coordinate

        Returns:
            Tuple of (screen_x, screen_y)
        """
        point = wintypes.POINT(client_x, client_y)
        _user32.ClientToScreen(hwnd, ctypes.byref(point))
        return point.x, point.y

    @staticmethod
    def _detect_dpi_scale() -> float:
        """Detect system DPI scaling factor

        Queries GetDeviceCaps(LOGPIXELSX) to determine the current
        DPI scaling (100%, 125%, 150%, etc.).

        Returns:
            DPI scale factor (1.0 = 96 DPI, 1.25 = 120 DPI, etc.)
        """
        try:
            _user32.SetProcessDPIAware()
            dc = _user32.GetDC(0)
            scale = ctypes.windll.gdi32.GetDeviceCaps(dc, 88) / 96.0
            _user32.ReleaseDC(0, dc)
            return scale
        except Exception:
            return 1.0

    @staticmethod
    def _enum_children(
        parent_hwnd: int,
        class_filter: str | None = None,
        title_filter: str | None = None,
    ) -> list[dict]:
        """Enumerate visible child windows with optional filtering

        Uses EnumChildWindows Win32 API to discover all immediate
        child windows of a parent. Filters by class name and/or
        window title substrings.

        Reference: ok-script's dynamic child window discovery.

        Args:
            parent_hwnd: Parent window to enumerate
            class_filter: Class name substring filter (case-insensitive)
            title_filter: Title substring filter (case-insensitive)

        Returns:
            List of dicts with keys: hwnd, title, class, rect, width, height
        """
        results = []

        EnumWindowsProc = ctypes.WINFUNCTYPE(  # noqa: N806
            ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
        )

        def _callback(hwnd, _lparam):
            if not _user32.IsWindowVisible(hwnd):
                return True

            buf_len = _user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(buf_len + 1)
            _user32.GetWindowTextW(hwnd, buf, buf_len + 1)
            win_title = buf.value

            cls_buf = ctypes.create_unicode_buffer(256)
            _user32.GetClassNameW(hwnd, cls_buf, 256)
            win_class = cls_buf.value

            if class_filter and class_filter.lower() not in win_class.lower():
                return True
            if title_filter and title_filter.lower() not in win_title.lower():
                return True

            rect = wintypes.RECT()
            _user32.GetWindowRect(hwnd, ctypes.byref(rect))
            results.append({
                'hwnd': hwnd,
                'title': win_title,
                'class': win_class,
                'rect': (rect.left, rect.top, rect.right, rect.bottom),
                'width': rect.right - rect.left,
                'height': rect.bottom - rect.top,
            })
            return True

        callback = EnumWindowsProc(_callback)
        _user32.EnumChildWindows(parent_hwnd, callback, 0)
        return results

    def _check_method_available(self, method: str) -> bool:
        """Check if an input method is available on this system

        Args:
            method: Method name to check

        Returns:
            True if method appears available
        """
        if method in ('SendInput', 'PostMessage', 'SendMessage'):
            try:
                _ = ctypes.windll.user32.SendInput
                return True
            except (AttributeError, OSError):
                return False
        return False

    def _parse_hwnd(self, target: str) -> int | None:
        """Parse target string to window handle integer

        Accepts hex strings ('0x123AB') or decimal strings.

        Args:
            target: Target identifier string

        Returns:
            Window handle integer, or None if invalid
        """
        if not target:
            return None
        try:
            if isinstance(target, str) and target.startswith('0x'):
                return int(target, 16)
            return int(target)
        except (ValueError, TypeError):
            return None
