"""
macOS 输入处理器
基于 CGEventPost + CGEventCreateMouseEvent (pyobjc-framework-Quartz)
依赖：pyobjc-framework-Quartz (macOS only)
参考：MaaFramework macOS 输入实现

注意：macOS 输入需要 Accessibility 权限
  System Preferences > Security & Privacy > Privacy > Accessibility
"""
import logging
import time

from device_bridge.platforms.base import InputResult, PlatformInputHandler

logger = logging.getLogger(__name__)

MACOS_INPUT_METHODS = ['CGEvent', 'AppleScript']

# macOS CGEvent mouse button constants
_LEFT_BUTTON = 0
_RIGHT_BUTTON = 1
_CENTER_BUTTON = 2

# CGEvent types
_LEFT_MOUSE_DOWN = 1
_LEFT_MOUSE_UP = 2
_RIGHT_MOUSE_DOWN = 3
_RIGHT_MOUSE_UP = 4
_MOUSE_MOVED = 5
_LEFT_MOUSE_DRAGGED = 6
_SCROLL_WHEEL = 22

# CGEvent key codes (common keys, full list in Carbon.HIToolbox.Events)
_KEY_MAP = {
    'enter': 36,
    'return': 36,
    'tab': 48,
    'esc': 53,
    'escape': 53,
    'delete': 51,
    'backspace': 51,
    'forwarddelete': 117,
    'space': 49,
    'up': 126,
    'down': 125,
    'left': 123,
    'right': 124,
    'home': 115,
    'end': 119,
    'pageup': 116,
    'pagedown': 121,
    'f1': 122,
    'f2': 120,
    'f3': 99,
    'f4': 118,
    'f5': 96,
    'f6': 97,
    'f7': 98,
    'f8': 100,
    'f9': 101,
    'f10': 109,
    'f11': 103,
    'f12': 111,
    'shift': 56,
    'ctrl': 59,
    'control': 59,
    'cmd': 55,
    'command': 55,
    'alt': 58,
    'option': 58,
}

# CGEvent flags (reserved for future modifier key combinations)
# _FLAG_SHIFT = 1 << 17
# _FLAG_CTRL = 1 << 18
# _FLAG_CMD = 1 << 20
# _FLAG_ALT = 1 << 19

# Letter key code -> required flag (uppercase letters need shift)
_CHAR_TO_KEYCODE = {}
for _c in range(ord('a'), ord('z') + 1):
    _CHAR_TO_KEYCODE[chr(_c)] = _c - ord('a') + 97  # a=97, b=98, ...
for _c in range(ord('A'), ord('Z') + 1):
    _CHAR_TO_KEYCODE[chr(_c)] = _c - ord('A') + 97
for _c in range(ord('0'), ord('9') + 1):
    _CHAR_TO_KEYCODE[chr(_c)] = _c - ord('0') + 29  # 0=29, 1=30, ...


def _check_accessibility_permission() -> bool:
    """Check Accessibility permission (required for CGEvent posting)."""
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        from Foundation import NSDictionary
        # Prompt for permission if not granted
        options = NSDictionary.dictionaryWithObject_forKey_(True, 'AXTrustedCheckOptionPrompt')
        return bool(AXIsProcessTrustedWithOptions(options))
    except ImportError:
        # pyobjc-framework-ApplicationServices not installed
        return False
    except Exception:
        logger.warning("macOS input: AXIsProcessTrusted check failed", exc_info=True)
        return False


def _check_quartz_available() -> bool:
    """Check if Quartz framework is importable."""
    try:
        from Quartz import CGEventPost  # noqa: F401
        return True
    except ImportError:
        return False


class MacOSInputHandler(PlatformInputHandler):
    """macOS 输入处理器，支持 CGEvent / AppleScript 两种方式"""

    def __init__(self, method: str = ''):
        self.method = method or 'CGEvent'

    def available_methods(self) -> list[str]:
        return MACOS_INPUT_METHODS

    def click(self, target: str, x: int, y: int, method: str = '') -> InputResult:
        method = method or self.method
        start = time.monotonic()

        if method == 'CGEvent':
            return self._click_cgevent(target, x, y, 'left', start)
        elif method == 'AppleScript':
            return self._click_applescript(target, x, y, start)
        return InputResult(success=False, method=method, error=f'Unknown method: {method}')

    def swipe(self, target: str, x1: int, y1: int, x2: int, y2: int,
              duration_ms: int = 300, method: str = '') -> InputResult:
        method = method or self.method
        start = time.monotonic()

        if not _check_quartz_available():
            return InputResult(success=False, method=method,
                               error='Quartz framework not available. Install: pip install pyobjc-framework-Quartz')
        if not _check_accessibility_permission():
            return InputResult(success=False, method=method,
                               error='Accessibility permission not granted. System Preferences > Security & Privacy > Privacy > Accessibility')

        try:
            from CoreGraphics import CGPoint
            from Quartz import (
                CGEventCreateMouseEvent,
                CGEventPost,
                kCGHIDEventTap,
            )

            # Move to start
            move_event = CGEventCreateMouseEvent(None, _MOUSE_MOVED, CGPoint(x1, y1), _LEFT_BUTTON)
            CGEventPost(kCGHIDEventTap, move_event)

            # Mouse down at start
            down_event = CGEventCreateMouseEvent(None, _LEFT_MOUSE_DOWN, CGPoint(x1, y1), _LEFT_BUTTON)
            CGEventPost(kCGHIDEventTap, down_event)

            # Interpolate drag over duration_ms in ~16ms steps (60fps)
            steps = max(1, duration_ms // 16)
            for i in range(1, steps + 1):
                t = i / steps
                cx = int(x1 + (x2 - x1) * t)
                cy = int(y1 + (y2 - y1) * t)
                drag_event = CGEventCreateMouseEvent(None, _LEFT_MOUSE_DRAGGED, CGPoint(cx, cy), _LEFT_BUTTON)
                CGEventPost(kCGHIDEventTap, drag_event)
                time.sleep(duration_ms / 1000.0 / steps)

            # Mouse up at end
            up_event = CGEventCreateMouseEvent(None, _LEFT_MOUSE_UP, CGPoint(x2, y2), _LEFT_BUTTON)
            CGEventPost(kCGHIDEventTap, up_event)

            latency_ms = (time.monotonic() - start) * 1000
            return InputResult(success=True, method=method, latency_ms=latency_ms)
        except Exception as e:
            return InputResult(success=False, method=method, error=f'CGEvent swipe failed: {e}')

    def key_press(self, target: str, key: str, method: str = '') -> InputResult:
        method = method or self.method
        start = time.monotonic()

        if method == 'CGEvent':
            return self._key_press_cgevent(key, start, method)
        elif method == 'AppleScript':
            return self._key_press_applescript(key, start, method)
        return InputResult(success=False, method=method, error=f'Unknown method: {method}')

    def scroll(self, target: str, x: int, y: int, delta: int, method: str = '') -> InputResult:
        method = method or self.method
        start = time.monotonic()

        if not _check_quartz_available():
            return InputResult(success=False, method=method,
                               error='Quartz framework not available. Install: pip install pyobjc-framework-Quartz')
        if not _check_accessibility_permission():
            return InputResult(success=False, method=method,
                               error='Accessibility permission not granted')

        try:
            from CoreGraphics import CGPoint
            from Quartz import CGEventCreateMouseEvent, CGEventPost, kCGHIDEventTap

            # Move to scroll position first
            move_event = CGEventCreateMouseEvent(None, _MOUSE_MOVED, CGPoint(x, y), _LEFT_BUTTON)
            CGEventPost(kCGHIDEventTap, move_event)

            # Create scroll event
            # delta: positive = up, negative = down (matches Windows convention)
            scroll_event = CGEventCreateMouseEvent(None, _SCROLL_WHEEL, CGPoint(x, y), _LEFT_BUTTON)
            # Set scroll delta (field 1 = vertical scroll)
            scroll_event.setIntegerValueField_forField_(1, delta)
            CGEventPost(kCGHIDEventTap, scroll_event)

            latency_ms = (time.monotonic() - start) * 1000
            return InputResult(success=True, method=method, latency_ms=latency_ms)
        except Exception as e:
            return InputResult(success=False, method=method, error=f'CGEvent scroll failed: {e}')

    def _click_cgevent(self, target: str, x: int, y: int, button: str, start: float) -> InputResult:
        """Click via CGEvent (foreground only — macOS does not support background input)."""
        if not _check_quartz_available():
            return InputResult(success=False, method='CGEvent',
                               error='Quartz framework not available. Install: pip install pyobjc-framework-Quartz')
        if not _check_accessibility_permission():
            return InputResult(success=False, method='CGEvent',
                               error='Accessibility permission not granted. System Preferences > Security & Privacy > Privacy > Accessibility')

        try:
            from CoreGraphics import CGPoint
            from Quartz import CGEventCreateMouseEvent, CGEventPost, kCGHIDEventTap

            btn_const = _LEFT_BUTTON if button == 'left' else _RIGHT_BUTTON if button == 'right' else _CENTER_BUTTON
            down_type = _LEFT_MOUSE_DOWN if button == 'left' else _RIGHT_MOUSE_DOWN
            up_type = _LEFT_MOUSE_UP if button == 'left' else _RIGHT_MOUSE_UP

            # Move to position first
            move_event = CGEventCreateMouseEvent(None, _MOUSE_MOVED, CGPoint(x, y), btn_const)
            CGEventPost(kCGHIDEventTap, move_event)

            # Mouse down
            down_event = CGEventCreateMouseEvent(None, down_type, CGPoint(x, y), btn_const)
            CGEventPost(kCGHIDEventTap, down_event)

            # Mouse up
            up_event = CGEventCreateMouseEvent(None, up_type, CGPoint(x, y), btn_const)
            CGEventPost(kCGHIDEventTap, up_event)

            latency_ms = (time.monotonic() - start) * 1000
            return InputResult(success=True, method='CGEvent', latency_ms=latency_ms)
        except Exception as e:
            return InputResult(success=False, method='CGEvent', error=f'CGEvent click failed: {e}')

    def _click_applescript(self, target: str, x: int, y: int, start: float) -> InputResult:
        """Click via AppleScript (cliclick wrapper, requires `cliclick` brew install)."""
        import subprocess
        try:
            result = subprocess.run(
                ['cliclick', f'c:{x},{y}'],
                capture_output=True,
                timeout=5,
                check=False,
            )
            latency_ms = (time.monotonic() - start) * 1000
            if result.returncode == 0:
                return InputResult(success=True, method='AppleScript', latency_ms=latency_ms)
            return InputResult(success=False, method='AppleScript',
                               error=f'cliclick failed: {result.stderr.decode(errors="replace")}')
        except FileNotFoundError:
            return InputResult(success=False, method='AppleScript',
                               error='cliclick not installed. Install: brew install cliclick')
        except subprocess.TimeoutExpired:
            return InputResult(success=False, method='AppleScript', error='cliclick timed out')
        except Exception as e:
            return InputResult(success=False, method='AppleScript', error=f'AppleScript click failed: {e}')

    def _key_press_cgevent(self, key: str, start: float, method: str) -> InputResult:
        """Key press via CGEvent."""
        if not _check_quartz_available():
            return InputResult(success=False, method=method,
                               error='Quartz framework not available')
        if not _check_accessibility_permission():
            return InputResult(success=False, method=method,
                               error='Accessibility permission not granted')

        key_lower = key.lower()
        key_code = _KEY_MAP.get(key_lower)
        if key_code is None and len(key) == 1:
            key_code = _CHAR_TO_KEYCODE.get(key)
        if key_code is None:
            return InputResult(success=False, method=method,
                               error=f'Unknown key: {key!r}. Supported: {list(_KEY_MAP.keys())} or single char')

        try:
            from Quartz import (
                CGEventCreateKeyboardEvent,
                CGEventPost,
                kCGHIDEventTap,
            )

            # Key down
            down_event = CGEventCreateKeyboardEvent(None, key_code, True)
            CGEventPost(kCGHIDEventTap, down_event)
            # Key up
            up_event = CGEventCreateKeyboardEvent(None, key_code, False)
            CGEventPost(kCGHIDEventTap, up_event)

            latency_ms = (time.monotonic() - start) * 1000
            return InputResult(success=True, method=method, latency_ms=latency_ms)
        except Exception as e:
            return InputResult(success=False, method=method, error=f'CGEvent key_press failed: {e}')

    def _key_press_applescript(self, key: str, start: float, method: str) -> InputResult:
        """Key press via AppleScript (uses osascript)."""
        import subprocess
        # Map common keys to AppleScript key names
        applescript_key = key.upper() if len(key) == 1 else key
        script = f'''
        tell application "System Events"
            keystroke "{applescript_key}"
        end tell
        '''
        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                timeout=5,
                check=False,
            )
            latency_ms = (time.monotonic() - start) * 1000
            if result.returncode == 0:
                return InputResult(success=True, method=method, latency_ms=latency_ms)
            return InputResult(success=False, method=method,
                               error=f'osascript failed: {result.stderr.decode(errors="replace")}')
        except FileNotFoundError:
            return InputResult(success=False, method=method,
                               error='osascript not found (not running on macOS?)')
        except subprocess.TimeoutExpired:
            return InputResult(success=False, method=method, error='osascript timed out')
        except Exception as e:
            return InputResult(success=False, method=method, error=f'AppleScript key_press failed: {e}')
