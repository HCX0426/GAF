"""
Windows platform screenshot handler
Ref: ok-script WGC (D3D11+WinRT) ctypes + BitBlt DC cache + sub-window composite
Ref: MaaFramework 6-method race selection + pseudo-minimize
"""
import ctypes
import ctypes.wintypes
import importlib.util
import logging
import time

from device_bridge.platforms.base import PlatformScreenshotHandler, ScreenshotResult

logger = logging.getLogger(__name__)

WINDOWS_METHODS = ['BitBlt', 'PrintWindow', 'DXGI', 'GDI']

# ADB screenshot methods (for emulator devices). These are handled by the
# _adb_screenshot module, not by Windows Win32 capture methods.
ADB_SCREENSHOT_METHODS = {'ld_opengl', 'screencap', 'screencap_png', 'nemuipe', 'bluestacks', 'droidcast'}

# Device models may store lowercase method names (e.g. agent benchmark writes
# 'printwindow'); normalize to the TitleCase names used by this handler.
_METHOD_NAME_MAP = {
    'printwindow': 'PrintWindow',
    'bitblt': 'BitBlt',
    'gdi': 'GDI',
    'dxgi': 'DXGI',
    'wgc': 'WGC',
}

# TD-334: Window class names that indicate a game/engine render window. For
# these, GDI BitBlt cannot capture occluded content (it captures whatever is
# visible on screen, which may be a foreground IDE window). PrintWindow sends
# WM_PRINT directly to the target window, so it can capture occluded game
# content. Kept in sync with agent/src/platforms/windows/screenshot.py.
_GAME_WINDOW_CLASSES = frozenset({
    "UnityWndClass",        # Unity engine (BD2, etc.)
    "UnrealWindow",         # Unreal engine
    "LaunchUnrealUWindowsClient",
    "Godot_Engine_Wnd",     # Godot
    "FFXIVGAME",            # Final Fantasy XIV
    "ArenaNet_Dx_Window_Class",  # Guild Wars 2
    "CrypticWindow",        # Star Trek Online / Neverwinter
})

# Methods that are unreliable for occluded game windows and should be
# redirected to PrintWindow when the target is a game window (TD-334).
_GAME_WINDOW_REDIRECT_METHODS = frozenset({'BitBlt', 'GDI', 'DXGI'})


def _normalize_screenshot_method(method: str) -> str:
    """Return canonical TitleCase method name.

    ADB screenshot methods (ld_opengl, screencap, etc.) are kept as-is
    since they are routed to the ADB screenshot module, not Win32 methods.
    """
    if not method:
        return 'BitBlt'
    if method in ADB_SCREENSHOT_METHODS:
        return method
    return _METHOD_NAME_MAP.get(method.lower(), method)


# DPI awareness: must be set once before any GDI/Win32 calls on HiDPI displays
try:
    _shcore = ctypes.windll.shcore
    _PROCESS_PER_MONITOR_DPI_AWARE = 2
    _shcore.SetProcessDpiAwareness(_PROCESS_PER_MONITOR_DPI_AWARE)
except Exception:
    try:
        _user32_dpi = ctypes.windll.user32
        _user32_dpi.SetProcessDPIAware()
    except Exception as e:
        logger.warning('SetProcessDPIAware fallback failed: %s', e)


class WindowsScreenshotHandler(PlatformScreenshotHandler):
    """Windows 截图处理器，支持 WGC / BitBlt / PrintWindow / DXGI / GDI 五种方式"""

    def __init__(self, method: str = ''):
        self.method = _normalize_screenshot_method(method)
        self._fps_samples: list[float] = []
        self._max_samples = 30

    def available_methods(self) -> list[str]:
        available = []
        for m in WINDOWS_METHODS:
            if self._check_method_available(m):
                available.append(m)
        if not available:
            available = ['mock']
        return available

    def capture(self, target: str, method: str = '') -> ScreenshotResult:
        method = _normalize_screenshot_method(method or self.method)
        t1 = time.perf_counter()

        try:
            result = self._do_capture(target, method)
        except Exception as e:
            return ScreenshotResult(
                method=method,
                success=False,
                error=f'{method} 截图异常: {e}',
            )

        t2 = time.perf_counter()
        latency_ms = round((t2 - t1) * 1000, 2)
        self._update_fps(t1, t2)

        if result.get('success') and result.get('image_bytes'):
            return ScreenshotResult(
                image_bytes=result['image_bytes'],
                latency_ms=latency_ms,
                fps=round(self._get_avg_fps(), 1),
                resolution=result.get('resolution', {'width': 0, 'height': 0}),
                method=method,
                success=True,
            )
        return ScreenshotResult(
            latency_ms=latency_ms,
            method=method,
            success=False,
            error=result.get('error', '截图失败'),
        )

    def benchmark(self, target: str, method: str, rounds: int = 10) -> dict:
        latencies = []
        success_count = 0
        for _ in range(rounds):
            result = self.capture(target, method)
            if result.success:
                latencies.append(result.latency_ms)
                success_count += 1
        if not latencies:
            return {'method': method, 'avg_ms': 0, 'min_ms': 0, 'max_ms': 0, 'fps': 0, 'success_rate': 0.0}
        avg_ms = sum(latencies) / len(latencies)
        return {
            'method': method,
            'avg_ms': round(avg_ms, 2),
            'min_ms': round(min(latencies), 2),
            'max_ms': round(max(latencies), 2),
            'fps': round(1000.0 / avg_ms, 1) if avg_ms > 0 else 0,
            'success_rate': round(success_count / rounds, 2),
        }

    def _do_capture(self, target: str, method: str) -> dict:
        # Route ADB screenshot methods to the ADB screenshot module (for emulators)
        if method in ADB_SCREENSHOT_METHODS:
            return self._capture_adb(target, method)

        # TD-334: 游戏窗口守卫 — BitBlt/GDI/DXGI 对遮挡游戏窗口不可靠,
        # 主动 redirect 到 PrintWindow (不等黑图 fallback, 节省一次失败截图).
        # WGC 已 delegate 到 PrintWindow (TD-125), 不需要 redirect.
        if method in _GAME_WINDOW_REDIRECT_METHODS and self._is_game_window(target):
            logger.info(
                "TD-334: target hwnd=%s 是游戏引擎窗口, %s 不可靠, "
                "redirect 到 PrintWindow",
                target, method,
            )
            return self._capture_printwindow(target)

        if method == 'WGC':
            return self._capture_wgc(target)
        elif method == 'BitBlt':
            return self._capture_bitblt(target)
        elif method == 'PrintWindow':
            return self._capture_printwindow(target)
        elif method == 'DXGI':
            return self._capture_dxgi(target)
        elif method == 'GDI':
            return self._capture_gdi(target)
        return {'success': False, 'error': f'不支持的截图方式: {method}'}

    @staticmethod
    def _get_window_class_name(hwnd_str: str) -> str:
        """Return the Win32 class name of the window identified by hwnd_str.

        Args:
            hwnd_str: Window handle as hex string ('0x12345') or decimal.

        Returns:
            Class name string, or empty string if hwnd is invalid / not on
            Windows / GetClassNameW fails. Mirrors agent-side
            ScreenshotManager._get_window_class_name.
        """
        if not hwnd_str:
            return ''
        try:
            hwnd_int = int(hwnd_str, 16) if isinstance(hwnd_str, str) and hwnd_str.startswith('0x') else int(hwnd_str)
        except (ValueError, TypeError):
            return ''
        if hwnd_int <= 0:
            return ''
        try:
            user32 = ctypes.windll.user32
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW.argtypes = [
                ctypes.wintypes.HWND, ctypes.wintypes.LPWSTR, ctypes.c_int,
            ]
            user32.GetClassNameW.restype = ctypes.c_int
            if user32.GetClassNameW(hwnd_int, class_name, 256) > 0:
                return class_name.value
        except (AttributeError, OSError):
            # Non-Windows test env (no ctypes.windll) or invalid hwnd
            pass
        return ''

    @staticmethod
    def _is_game_window(hwnd_str: str) -> bool:
        """Check if the target hwnd belongs to a known game engine window class.

        Mirrors agent-side ScreenshotManager._is_game_window (TD-334).
        Returns False if hwnd is invalid or class retrieval fails.
        """
        return WindowsScreenshotHandler._get_window_class_name(hwnd_str) in _GAME_WINDOW_CLASSES

    def _capture_adb(self, adb_serial: str, method: str) -> dict:
        """Capture screenshot via ADB for emulator devices.

        Routes to the _adb_screenshot module which supports ld_opengl,
        screencap, screencap_png, and other ADB-based methods.
        """
        try:
            from device_bridge.platforms.windows._adb_screenshot import capture as adb_capture

            image_bytes, used_method = adb_capture(adb_serial, method=method)
            if image_bytes:
                return {
                    'success': True,
                    'image_bytes': image_bytes,
                    'method': used_method or method,
                    'resolution': {'width': 0, 'height': 0},
                }
            return {'success': False, 'error': f'ADB 截图失败: {method} 未返回数据'}
        except Exception as e:
            return {'success': False, 'error': f'ADB 截图失败: {e}'}

    def _capture_wgc(self, hwnd: str) -> dict:
        """WGC 截图 — backend 无真实 WGC 实现 (TD-125)，delegate 到 PrintWindow.

        Backend 端从未实现真实 WGC（之前的 ``_wgc.py`` 是返回固定蓝色
        图片的 mock）。Agent 有自己的 ``Win32WGC`` 实现用于实际任务执行，
        backend API 不再提供 WGC。已存配置 ``screenshot_method='wgc'`` 的
        设备会通过此处降级到 PrintWindow（hwnd-isolated, 安全）。
        """
        logger.warning(
            "Backend WGC is deprecated (was a mock, TD-125); "
            "delegating to PrintWindow for hwnd=%s",
            hwnd,
        )
        return self._capture_printwindow(hwnd)

    def _capture_bitblt(self, hwnd: str) -> dict:
        try:
            from device_bridge.platforms.windows._bitblt import BitBltCapture
            hwnd_int = int(hwnd, 16) if isinstance(hwnd, str) and hwnd.startswith('0x') else int(hwnd)
            capturer = BitBltCapture()
            img = capturer.capture(hwnd_int)
            if self._is_image_black(img):
                logger.debug('BitBlt returned all-black image for hwnd=%s, falling back to PrintWindow', hwnd)
                fallback = self._capture_printwindow(hwnd)
                if fallback.get('success'):
                    return fallback
                import cv2
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                _, buf = cv2.imencode('.jpg', img_rgb, [cv2.IMWRITE_JPEG_QUALITY, 85])
                return {'success': True, 'image_bytes': buf.tobytes(), 'resolution': {'width': img.shape[1], 'height': img.shape[0]}}
            import cv2
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            _, buf = cv2.imencode('.jpg', img_rgb, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_bytes = buf.tobytes()
            height, width = img.shape[:2]
            return {'success': True, 'image_bytes': image_bytes, 'resolution': {'width': width, 'height': height}}
        except ImportError:
            return {'success': False, 'error': 'BitBlt failed: missing numpy or opencv-python'}
        except Exception as e:
            return {'success': False, 'error': f'BitBlt capture failed: {e}'}

    def _capture_printwindow(self, hwnd: str) -> dict:
        try:
            from device_bridge.platforms.windows._printwindow import capture_by_printwindow
            hwnd_int = int(hwnd, 16) if isinstance(hwnd, str) and hwnd.startswith('0x') else int(hwnd)
            img = capture_by_printwindow(hwnd_int)
            import cv2
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            _, buf = cv2.imencode('.jpg', img_rgb, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_bytes = buf.tobytes()
            height, width = img.shape[:2]
            return {'success': True, 'image_bytes': image_bytes, 'resolution': {'width': width, 'height': height}}
        except ImportError:
            return {'success': False, 'error': 'PrintWindow 失败: 缺少 numpy 或 opencv-python'}
        except Exception as e:
            return {'success': False, 'error': f'PrintWindow 截图失败: {e}'}

    def _capture_dxgi(self, hwnd: str) -> dict:
        """DXGI Desktop Duplication screenshot cropped to target window (TD-124).

        Uses ``DXGICapture.capture_window(hwnd)`` to crop the full-desktop frame
        to the target window's rect. The hwnd is parsed from hex/decimal string
        form (frontend convention) and passed to the capturer.
        """
        try:
            from device_bridge.platforms.windows._dxgi import DXGICapture

            hwnd_int = int(hwnd, 16) if isinstance(hwnd, str) and hwnd.startswith('0x') else int(hwnd)
            capturer = DXGICapture()
            try:
                # initialize() still accepts hwnd for API compat but ignores it
                # (DXGI captures the full monitor output). The hwnd is used by
                # capture_window() below to crop the frame to the window rect.
                if not capturer.initialize(0):
                    return {'success': False, 'error': 'DXGI initialization failed'}
                img = capturer.capture_window(hwnd_int)
                if img is None:
                    return {'success': False, 'error': 'DXGI frame acquisition returned None'}
                import cv2
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                _, buf = cv2.imencode('.jpg', img_rgb, [cv2.IMWRITE_JPEG_QUALITY, 85])
                image_bytes = buf.tobytes()
                height, width = img.shape[:2]
                return {
                    'success': True,
                    'image_bytes': image_bytes,
                    'resolution': {'width': width, 'height': height},
                }
            finally:
                capturer.release()
        except ImportError:
            return {'success': False, 'error': 'DXGI failed: missing numpy or opencv-python'}
        except Exception as e:
            return {'success': False, 'error': f'DXGI capture failed: {e}'}

    def _capture_gdi(self, hwnd: str) -> dict:
        """GDI screenshot fallback using the same BitBlt implementation.

        GDI and BitBlt share the same underlying GDI32 API. This method exists
        to provide the 'GDI' method name expected by benchmarking/discovery code.
        """
        return self._capture_bitblt(hwnd)

    def _check_method_available(self, method: str) -> bool:
        module_map = {
            'BitBlt': 'device_bridge.platforms.windows._bitblt',
            'PrintWindow': 'device_bridge.platforms.windows._printwindow',
            'DXGI': 'device_bridge.platforms.windows._dxgi',
            'GDI': 'device_bridge.platforms.windows._bitblt',
        }
        module_name = module_map.get(method)
        if not module_name:
            # 'WGC' is no longer available in backend (TD-125); return False so
            # available_methods() does not advertise it. _capture_wgc still
            # exists as a PrintWindow delegate for legacy device configs.
            return False
        return importlib.util.find_spec(module_name) is not None

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

    @staticmethod
    def _is_image_black(img, threshold: float = 10.0) -> bool:
        """Check if image is effectively all-black (GPU-rendered windows return black via BitBlt).
        Samples center pixels and checks mean brightness against threshold."""
        import numpy as np
        if img is None or img.size == 0:
            return True
        h, w = img.shape[:2]
        if h < 4 or w < 4:
            return False
        sample = img[h // 2 - 2:h // 2 + 2, w // 2 - 2:w // 2 + 2]
        return float(np.mean(sample)) < threshold
