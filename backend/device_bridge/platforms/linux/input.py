"""
Linux 输入处理器
基于 XTestFakeKeyEvent / XSendEvent (python-xlib) + uinput (kernel-level)
依赖：python-xlib (X11 only), python-uinput (optional, for uinput)
参考：MaaFramework Linux 输入实现

支持三种方式：
1. XTest — X Test extension (推荐，无需 root)
2. XSendEvent — 直接发送 X 事件 (部分窗口管理器会忽略)
3. uinput — 内核级虚拟输入设备 (需 root + uinput 模块)

注意：Linux X11 输入只能针对当前焦点窗口（与 Windows PostMessage 后台输入不同）
"""
import logging
import time

from device_bridge.platforms.base import InputResult, PlatformInputHandler

logger = logging.getLogger(__name__)

LINUX_INPUT_METHODS = ['XTest', 'XSendEvent', 'uinput']

# X11 button constants
_BUTTON1 = 1   # Left
_BUTTON2 = 2   # Middle
_BUTTON3 = 3   # Right
_BUTTON4 = 4   # Scroll up
_BUTTON5 = 5   # Scroll down

# Common keysym mapping (XK_*)
# Reference: X11/keysymdef.h
_KEY_MAP = {
    'enter': 0xff0d,   # XK_Return
    'return': 0xff0d,
    'tab': 0xff09,     # XK_Tab
    'esc': 0xff1b,     # XK_Escape
    'escape': 0xff1b,
    'delete': 0xffff,  # XK_Delete
    'backspace': 0xff08,  # XK_BackSpace
    'forwarddelete': 0xffff,
    'space': 0x0020,   # XK_space
    'up': 0xff52,      # XK_Up
    'down': 0xff54,    # XK_Down
    'left': 0xff51,    # XK_Left
    'right': 0xff53,   # XK_Right
    'home': 0xff50,    # XK_Home
    'end': 0xff57,     # XK_End
    'pageup': 0xff55,  # XK_Page_Up
    'pagedown': 0xff56,  # XK_Page_Down
    'f1': 0xffbe,      # XK_F1
    'f2': 0xffbf,
    'f3': 0xffc0,
    'f4': 0xffc1,
    'f5': 0xffc2,
    'f6': 0xffc3,
    'f7': 0xffc4,
    'f8': 0xffc5,
    'f9': 0xffc6,
    'f10': 0xffc7,
    'f11': 0xffc8,
    'f12': 0xffc9,
    'shift': 0xffe1,   # XK_Shift_L
    'ctrl': 0xffe3,    # XK_Control_L
    'control': 0xffe3,
    'alt': 0xffe9,     # XK_Alt_L
    'option': 0xffe9,
}


def _check_xlib_available() -> bool:
    """Check if python-xlib is importable."""
    try:
        import Xlib  # noqa: F401
        return True
    except ImportError:
        return False


def _check_uinput_available() -> bool:
    """Check if python-uinput is importable."""
    try:
        import uinput  # noqa: F401
        return True
    except ImportError:
        return False


def _char_to_keysym(ch: str) -> int:
    """Convert single character to X11 keysym.

    For ASCII printable chars, keysym == ASCII code.
    For uppercase letters, keysym == uppercase ASCII (0x41-0x5A).
    """
    if len(ch) != 1:
        return 0
    code = ord(ch)
    # ASCII printable range
    if 0x20 <= code <= 0x7e:
        return code
    return 0


class LinuxInputHandler(PlatformInputHandler):
    """Linux 输入处理器，支持 XTest / XSendEvent / uinput 三种方式"""

    def __init__(self, method: str = ''):
        self.method = method or 'XTest'

    def available_methods(self) -> list[str]:
        return LINUX_INPUT_METHODS

    def click(self, target: str, x: int, y: int, method: str = '') -> InputResult:
        method = method or self.method
        start = time.monotonic()

        if method == 'XTest':
            return self._click_xtest(x, y, 'left', start)
        elif method == 'XSendEvent':
            return self._click_xsendevent(target, x, y, 'left', start)
        elif method == 'uinput':
            return self._click_uinput(x, y, 'left', start)
        return InputResult(success=False, method=method, error=f'Unknown method: {method}')

    def swipe(self, target: str, x1: int, y1: int, x2: int, y2: int,
              duration_ms: int = 300, method: str = '') -> InputResult:
        method = method or self.method
        start = time.monotonic()

        if method == 'XTest':
            return self._swipe_xtest(x1, y1, x2, y2, duration_ms, start)
        elif method == 'XSendEvent':
            return self._swipe_xsendevent(target, x1, y1, x2, y2, duration_ms, start)
        elif method == 'uinput':
            return self._swipe_uinput(x1, y1, x2, y2, duration_ms, start)
        return InputResult(success=False, method=method, error=f'Unknown method: {method}')

    def key_press(self, target: str, key: str, method: str = '') -> InputResult:
        method = method or self.method
        start = time.monotonic()

        if method == 'XTest':
            return self._key_press_xtest(key, start)
        elif method == 'XSendEvent':
            return self._key_press_xsendevent(target, key, start)
        elif method == 'uinput':
            return self._key_press_uinput(key, start)
        return InputResult(success=False, method=method, error=f'Unknown method: {method}')

    def scroll(self, target: str, x: int, y: int, delta: int, method: str = '') -> InputResult:
        method = method or self.method
        start = time.monotonic()

        if method == 'XTest':
            return self._scroll_xtest(x, y, delta, start)
        elif method == 'XSendEvent':
            return self._scroll_xsendevent(target, x, y, delta, start)
        elif method == 'uinput':
            return self._scroll_uinput(x, y, delta, start)
        return InputResult(success=False, method=method, error=f'Unknown method: {method}')

    def _click_xtest(self, x: int, y: int, button: str, start: float) -> InputResult:
        """Click via XTest extension (no focus requirement, but foreground only)."""
        if not _check_xlib_available():
            return InputResult(success=False, method='XTest',
                               error='python-xlib not available. Install: pip install python-xlib')

        try:
            from Xlib import X
            from Xlib import display as Xdisplay  # noqa: N812
            from Xlib.ext import xtest
        except ImportError as e:
            return InputResult(success=False, method='XTest',
                               error=f'python-xlib import failed: {e}')

        try:
            dpy = Xdisplay.Display()
            try:
                btn = _BUTTON1 if button == 'left' else _BUTTON3 if button == 'right' else _BUTTON2

                # Move pointer to (x, y) using XTest fake motion event
                # Args: display, screen, x, y
                xtest.fake_input(dpy, X.MotionNotify, x=x, y=y)
                dpy.sync()

                # Button press
                xtest.fake_input(dpy, X.ButtonPress, btn)
                dpy.sync()
                # Button release
                xtest.fake_input(dpy, X.ButtonRelease, btn)
                dpy.sync()

                latency_ms = (time.monotonic() - start) * 1000
                return InputResult(success=True, method='XTest', latency_ms=latency_ms)
            finally:
                dpy.close()
        except Exception as e:
            return InputResult(success=False, method='XTest', error=f'XTest click failed: {e}')

    def _click_xsendevent(self, target: str, x: int, y: int, button: str, start: float) -> InputResult:
        """Click via XSendEvent (target window must be specified)."""
        if not _check_xlib_available():
            return InputResult(success=False, method='XSendEvent',
                               error='python-xlib not available')

        try:
            from Xlib import X
            from Xlib import display as Xdisplay  # noqa: N812
            from Xlib.protocol.event import ButtonPress, ButtonRelease
        except ImportError as e:
            return InputResult(success=False, method='XSendEvent',
                               error=f'python-xlib import failed: {e}')

        try:
            dpy = Xdisplay.Display()
            try:
                # Parse target window id
                try:
                    win_id = int(target, 0) if target else 0
                except ValueError:
                    return InputResult(success=False, method='XSendEvent',
                                       error=f'Invalid target window id: {target!r}')

                if win_id == 0:
                    return InputResult(success=False, method='XSendEvent',
                                       error='XSendEvent requires target window id')

                window = dpy.create_resource_object('window', win_id)
                btn = _BUTTON1 if button == 'left' else _BUTTON3 if button == 'right' else _BUTTON2

                # Send ButtonPress
                event = ButtonPress(detail=btn, time=X.CurrentTime, root=dpy.screen().root,
                                    window=window, same_screen=1, child=X.NONE,
                                    root_x=x, root_y=y, event_x=x, event_y=y,
                                    state=0, same_screen_flag=1)
                window.send_event(event)
                dpy.sync()

                # Send ButtonRelease
                event = ButtonRelease(detail=btn, time=X.CurrentTime, root=dpy.screen().root,
                                      window=window, same_screen=1, child=X.NONE,
                                      root_x=x, root_y=y, event_x=x, event_y=y,
                                      state=0x100, same_screen_flag=1)
                window.send_event(event)
                dpy.sync()

                latency_ms = (time.monotonic() - start) * 1000
                return InputResult(success=True, method='XSendEvent', latency_ms=latency_ms)
            finally:
                dpy.close()
        except Exception as e:
            return InputResult(success=False, method='XSendEvent', error=f'XSendEvent click failed: {e}')

    def _click_uinput(self, x: int, y: int, button: str, start: float) -> InputResult:
        """Click via uinput (kernel-level, requires root)."""
        # uinput requires root and is complex (need to manage virtual device lifecycle)
        # Defer to subprocess calling `xdotool` as a more practical fallback
        import subprocess
        try:
            result = subprocess.run(
                ['xdotool', 'mousemove', str(x), str(y), 'click', '1' if button == 'left' else '3'],
                capture_output=True,
                timeout=5,
                check=False,
            )
            latency_ms = (time.monotonic() - start) * 1000
            if result.returncode == 0:
                return InputResult(success=True, method='uinput', latency_ms=latency_ms)
            return InputResult(success=False, method='uinput',
                               error=f'xdotool failed: {result.stderr.decode(errors="replace")}')
        except FileNotFoundError:
            return InputResult(success=False, method='uinput',
                               error='xdotool not installed. Install: apt install xdotool')
        except subprocess.TimeoutExpired:
            return InputResult(success=False, method='uinput', error='xdotool timed out')
        except Exception as e:
            return InputResult(success=False, method='uinput', error=f'uinput click failed: {e}')

    def _swipe_xtest(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int, start: float) -> InputResult:
        """Swipe via XTest (interpolated motion + button press/release)."""
        if not _check_xlib_available():
            return InputResult(success=False, method='XTest',
                               error='python-xlib not available')

        try:
            from Xlib import X
            from Xlib import display as Xdisplay  # noqa: N812
            from Xlib.ext import xtest
        except ImportError as e:
            return InputResult(success=False, method='XTest',
                               error=f'python-xlib import failed: {e}')

        try:
            dpy = Xdisplay.Display()
            try:
                # Move to start
                xtest.fake_input(dpy, X.MotionNotify, x=x1, y=y1)
                dpy.sync()
                # Press left button
                xtest.fake_input(dpy, X.ButtonPress, _BUTTON1)
                dpy.sync()

                # Interpolate drag
                steps = max(1, duration_ms // 16)
                for i in range(1, steps + 1):
                    t = i / steps
                    cx = int(x1 + (x2 - x1) * t)
                    cy = int(y1 + (y2 - y1) * t)
                    xtest.fake_input(dpy, X.MotionNotify, x=cx, y=cy)
                    dpy.sync()
                    time.sleep(duration_ms / 1000.0 / steps)

                # Release at end
                xtest.fake_input(dpy, X.ButtonRelease, _BUTTON1)
                dpy.sync()

                latency_ms = (time.monotonic() - start) * 1000
                return InputResult(success=True, method='XTest', latency_ms=latency_ms)
            finally:
                dpy.close()
        except Exception as e:
            return InputResult(success=False, method='XTest', error=f'XTest swipe failed: {e}')

    def _swipe_xsendevent(self, target: str, x1: int, y1: int, x2: int, y2: int,
                          duration_ms: int, start: float) -> InputResult:
        """Swipe via XSendEvent (less reliable than XTest)."""
        # For simplicity, delegate to XTest (XSendEvent swipe is complex and rarely works)
        return self._swipe_xtest(x1, y1, x2, y2, duration_ms, start)

    def _swipe_uinput(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int, start: float) -> InputResult:
        """Swipe via uinput (xdotool fallback)."""
        import subprocess
        try:
            # xdotool mousedown 1, mousemove, mouseup
            cmds = [
                ['xdotool', 'mousemove', str(x1), str(y1), 'mousedown', '1'],
            ]
            steps = max(1, duration_ms // 50)
            for i in range(1, steps + 1):
                t = i / steps
                cx = int(x1 + (x2 - x1) * t)
                cy = int(y1 + (y2 - y1) * t)
                cmds.append(['xdotool', 'mousemove', str(cx), str(cy)])
            cmds.append(['xdotool', 'mouseup', '1'])

            for cmd in cmds:
                result = subprocess.run(cmd, capture_output=True, timeout=2, check=False)
                if result.returncode != 0:
                    return InputResult(success=False, method='uinput',
                                       error=f'xdotool failed: {result.stderr.decode(errors="replace")}')
                time.sleep(duration_ms / 1000.0 / (steps + 2))

            latency_ms = (time.monotonic() - start) * 1000
            return InputResult(success=True, method='uinput', latency_ms=latency_ms)
        except FileNotFoundError:
            return InputResult(success=False, method='uinput',
                               error='xdotool not installed')
        except Exception as e:
            return InputResult(success=False, method='uinput', error=f'uinput swipe failed: {e}')

    def _key_press_xtest(self, key: str, start: float) -> InputResult:
        """Key press via XTest."""
        if not _check_xlib_available():
            return InputResult(success=False, method='XTest',
                               error='python-xlib not available')

        try:
            from Xlib import X
            from Xlib import display as Xdisplay  # noqa: N812
            from Xlib.ext import xtest
        except ImportError as e:
            return InputResult(success=False, method='XTest',
                               error=f'python-xlib import failed: {e}')

        keysym = self._resolve_keysym(key)
        if keysym == 0:
            return InputResult(success=False, method='XTest',
                               error=f'Unknown key: {key!r}')

        try:
            dpy = Xdisplay.Display()
            try:
                # Convert keysym to keycode
                keycode = dpy.keysym_to_keycode(keysym)
                if keycode == 0:
                    return InputResult(success=False, method='XTest',
                                       error=f'No keycode for keysym 0x{keysym:x}')

                xtest.fake_input(dpy, X.KeyPress, keycode)
                dpy.sync()
                xtest.fake_input(dpy, X.KeyRelease, keycode)
                dpy.sync()

                latency_ms = (time.monotonic() - start) * 1000
                return InputResult(success=True, method='XTest', latency_ms=latency_ms)
            finally:
                dpy.close()
        except Exception as e:
            return InputResult(success=False, method='XTest', error=f'XTest key_press failed: {e}')

    def _key_press_xsendevent(self, target: str, key: str, start: float) -> InputResult:
        """Key press via XSendEvent (delegate to XTest for reliability)."""
        return self._key_press_xtest(key, start)

    def _key_press_uinput(self, key: str, start: float) -> InputResult:
        """Key press via uinput (xdotool fallback)."""
        import subprocess
        try:
            result = subprocess.run(
                ['xdotool', 'key', key],
                capture_output=True,
                timeout=5,
                check=False,
            )
            latency_ms = (time.monotonic() - start) * 1000
            if result.returncode == 0:
                return InputResult(success=True, method='uinput', latency_ms=latency_ms)
            return InputResult(success=False, method='uinput',
                               error=f'xdotool key failed: {result.stderr.decode(errors="replace")}')
        except FileNotFoundError:
            return InputResult(success=False, method='uinput',
                               error='xdotool not installed')
        except Exception as e:
            return InputResult(success=False, method='uinput', error=f'uinput key_press failed: {e}')

    def _scroll_xtest(self, x: int, y: int, delta: int, start: float) -> InputResult:
        """Scroll via XTest (button 4 = up, button 5 = down)."""
        if not _check_xlib_available():
            return InputResult(success=False, method='XTest',
                               error='python-xlib not available')

        try:
            from Xlib import X
            from Xlib import display as Xdisplay  # noqa: N812
            from Xlib.ext import xtest
        except ImportError as e:
            return InputResult(success=False, method='XTest',
                               error=f'python-xlib import failed: {e}')

        try:
            dpy = Xdisplay.Display()
            try:
                # Move to position
                xtest.fake_input(dpy, X.MotionNotify, x=x, y=y)
                dpy.sync()

                # Each scroll "click" is one button press/release
                # delta > 0: scroll up (button 4)
                # delta < 0: scroll down (button 5)
                btn = _BUTTON4 if delta > 0 else _BUTTON5
                clicks = min(abs(delta), 20)  # Cap at 20 clicks to avoid runaway

                for _ in range(clicks):
                    xtest.fake_input(dpy, X.ButtonPress, btn)
                    dpy.sync()
                    xtest.fake_input(dpy, X.ButtonRelease, btn)
                    dpy.sync()

                latency_ms = (time.monotonic() - start) * 1000
                return InputResult(success=True, method='XTest', latency_ms=latency_ms)
            finally:
                dpy.close()
        except Exception as e:
            return InputResult(success=False, method='XTest', error=f'XTest scroll failed: {e}')

    def _scroll_xsendevent(self, target: str, x: int, y: int, delta: int, start: float) -> InputResult:
        """Scroll via XSendEvent (delegate to XTest)."""
        return self._scroll_xtest(x, y, delta, start)

    def _scroll_uinput(self, x: int, y: int, delta: int, start: float) -> InputResult:
        """Scroll via uinput (xdotool fallback)."""
        import subprocess
        try:
            # Move to position
            subprocess.run(['xdotool', 'mousemove', str(x), str(y)],
                           capture_output=True, timeout=2, check=False)
            # Scroll: button 4 = up, button 5 = down
            btn = '4' if delta > 0 else '5'
            clicks = min(abs(delta), 20)
            for _ in range(clicks):
                result = subprocess.run(['xdotool', 'click', btn],
                                        capture_output=True, timeout=2, check=False)
                if result.returncode != 0:
                    return InputResult(success=False, method='uinput',
                                       error=f'xdotool click failed: {result.stderr.decode(errors="replace")}')

            latency_ms = (time.monotonic() - start) * 1000
            return InputResult(success=True, method='uinput', latency_ms=latency_ms)
        except FileNotFoundError:
            return InputResult(success=False, method='uinput',
                               error='xdotool not installed')
        except Exception as e:
            return InputResult(success=False, method='uinput', error=f'uinput scroll failed: {e}')

    @staticmethod
    def _resolve_keysym(key: str) -> int:
        """Resolve key name/char to X11 keysym."""
        key_lower = key.lower()
        if key_lower in _KEY_MAP:
            return _KEY_MAP[key_lower]
        if len(key) == 1:
            return _char_to_keysym(key)
        return 0
