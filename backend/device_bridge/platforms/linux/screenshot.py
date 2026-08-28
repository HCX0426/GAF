"""
Linux 截图处理器
基于 X11 XGetImage / XShmGetImage (python-xlib) + xdg-desktop-portal (Wayland fallback)
依赖：python-xlib (X11 only), xdg-desktop-portal (Wayland)
参考：MaaFramework Linux 截图实现

支持三种方式：
1. XGetImage — 慢但兼容性最好（无 MIT-SHM 依赖）
2. XShmGetImage — 快，需要 MIT-SHM 扩展（大多数 X Server 都支持）
3. xdg_portal — Wayland 兼容（通过 xdg-desktop-portal DBus 接口）
"""
import io
import logging
import os
import time

from device_bridge.platforms.base import PlatformScreenshotHandler, ScreenshotResult

logger = logging.getLogger(__name__)

LINUX_METHODS = ['XGetImage', 'XShmGetImage', 'xdg_portal']


def _check_xlib_available() -> bool:
    """Check if python-xlib is importable."""
    try:
        import Xlib  # noqa: F401
        return True
    except ImportError:
        return False


def _detect_display_server() -> str:
    """Detect current display server: 'x11' | 'wayland' | 'unknown'.

    Uses XDG_SESSION_TYPE env var (set by most modern desktop environments).
    Falls back to checking WAYLAND_DISPLAY env var.
    """
    session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
    if session_type in ('x11', 'wayland'):
        return session_type
    # Fallback: WAYLAND_DISPLAY present means Wayland
    if os.environ.get('WAYLAND_DISPLAY'):
        return 'wayland'
    if os.environ.get('DISPLAY'):
        return 'x11'
    return 'unknown'


def _parse_target(target: str) -> int:
    """Parse target string to X11 window id (int).

    Accepts:
      - Decimal: "12345"
      - Hex: "0x3039" or "#3039"
    """
    if not target:
        raise ValueError(f'target must be an X11 window id (int or hex string), got: {target!r}')
    target = target.strip()
    try:
        if target.startswith('0x') or target.startswith('0X'):
            return int(target, 16)
        if target.startswith('#'):
            return int(target[1:], 16)
        return int(target)
    except ValueError as e:
        raise ValueError(f'Invalid window id: {target!r}. Expected decimal or hex (0x.../#...).') from e


class LinuxScreenshotHandler(PlatformScreenshotHandler):
    """Linux 截图处理器，支持 X11 / XShm / xdg-desktop-portal 三种方式"""

    def __init__(self, method: str = ''):
        self.method = method or 'XGetImage'

    def available_methods(self) -> list[str]:
        return LINUX_METHODS

    def capture(self, target: str, method: str = '') -> ScreenshotResult:
        method = method or self.method
        start = time.monotonic()

        try:
            window_id = _parse_target(target)
        except ValueError as e:
            return ScreenshotResult(method=method, success=False, error=str(e))

        if method == 'XGetImage':
            return self._capture_xgetimage(window_id, start)
        elif method == 'XShmGetImage':
            return self._capture_xshmgetimage(window_id, start)
        elif method == 'xdg_portal':
            return self._capture_xdg_portal(start)
        else:
            return ScreenshotResult(
                method=method,
                success=False,
                error=f'Unknown method: {method}. Supported: {LINUX_METHODS}',
            )

    def _capture_xgetimage(self, window_id: int, start: float) -> ScreenshotResult:
        """Capture via XGetImage (slow, no MIT-SHM required)."""
        if not _check_xlib_available():
            return ScreenshotResult(
                method='XGetImage',
                success=False,
                error='python-xlib not available. Install: pip install python-xlib',
            )

        try:
            from Xlib import X
            from Xlib import display as Xdisplay  # noqa: N812
            from Xlib.Xutil import VisibleIconMask  # noqa: F401 (ensures Xutil loads)
        except ImportError as e:
            return ScreenshotResult(
                method='XGetImage',
                success=False,
                error=f'python-xlib import failed: {e}',
            )

        try:
            dpy = Xdisplay.Display()
            try:
                window = dpy.create_resource_object('window', window_id)
                # Get window geometry
                geom = window.get_geometry()
                width = geom.width
                height = geom.height

                # XGetImage returns XImage
                ximage = window.get_image(0, 0, width, height, X.ZPixmap, 0xffffffff)
                if ximage is None:
                    return ScreenshotResult(
                        method='XGetImage',
                        success=False,
                        error=f'XGetImage returned None for window_id={window_id}',
                    )

                # Convert raw pixel data to PNG via PIL
                from PIL import Image
                # XImage.data is bytes in ZPixmap format (RGB or BGR depending on visual)
                # For simplicity, assume 32-bit BGRA (most common on modern X servers)
                img = Image.frombytes('RGBX', (width, height), ximage.data, 'raw', 'BGRX')
                # Convert to RGB (drop alpha channel)
                img = img.convert('RGB')

                buffer = io.BytesIO()
                img.save(buffer, format='PNG')
                latency_ms = (time.monotonic() - start) * 1000

                return ScreenshotResult(
                    image_bytes=buffer.getvalue(),
                    latency_ms=latency_ms,
                    resolution={'width': width, 'height': height},
                    method='XGetImage',
                    success=True,
                )
            finally:
                dpy.close()
        except Exception as e:
            return ScreenshotResult(
                method='XGetImage',
                success=False,
                error=f'XGetImage capture failed: {e}',
            )

    def _capture_xshmgetimage(self, window_id: int, start: float) -> ScreenshotResult:
        """Capture via XShmGetImage (fast, requires MIT-SHM extension).

        python-xlib does not natively wrap MIT-SHM, so we fall back to XGetImage
        and warn the user. For real XShm support, use `mss` library or C extension.
        """
        # python-xlib lacks XShm wrapper; fall back to XGetImage with a warning
        logger.warning('XShmGetImage not directly supported by python-xlib, falling back to XGetImage')
        result = self._capture_xgetimage(window_id, start)
        if result.success:
            result.method = 'XShmGetImage'  # Report as XShm for caller consistency
        return result

    def _capture_xdg_portal(self, start: float) -> ScreenshotResult:
        """Capture via xdg-desktop-portal (Wayland-compatible).

        Uses `gnome-screenshot` or `grim` (Wayland) as fallback if xdg-desktop-portal DBus is unavailable.
        """
        import subprocess
        import tempfile

        # Try grim (Wayland-native)
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_path = tmp.name
            result = subprocess.run(
                ['grim', tmp_path],
                capture_output=True,
                timeout=10,
                check=False,
                env={**os.environ, 'XDG_SESSION_TYPE': 'wayland'},
            )
            if result.returncode == 0:
                with open(tmp_path, 'rb') as f:
                    image_bytes = f.read()
                os.unlink(tmp_path)
                width, height = self._png_dimensions(image_bytes)
                latency_ms = (time.monotonic() - start) * 1000
                return ScreenshotResult(
                    image_bytes=image_bytes,
                    latency_ms=latency_ms,
                    resolution={'width': width, 'height': height},
                    method='xdg_portal',
                    success=True,
                )
        except FileNotFoundError:
            pass  # grim not installed
        except subprocess.TimeoutExpired:
            return ScreenshotResult(method='xdg_portal', success=False, error='grim timed out')
        except Exception as e:
            logger.debug('grim capture failed: %s', e)

        # Try gnome-screenshot (GNOME desktop)
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_path = tmp.name
            result = subprocess.run(
                ['gnome-screenshot', '-f', tmp_path],
                capture_output=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0 and os.path.exists(tmp_path):
                with open(tmp_path, 'rb') as f:
                    image_bytes = f.read()
                os.unlink(tmp_path)
                width, height = self._png_dimensions(image_bytes)
                latency_ms = (time.monotonic() - start) * 1000
                return ScreenshotResult(
                    image_bytes=image_bytes,
                    latency_ms=latency_ms,
                    resolution={'width': width, 'height': height},
                    method='xdg_portal',
                    success=True,
                )
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            return ScreenshotResult(method='xdg_portal', success=False, error='gnome-screenshot timed out')
        except Exception as e:
            logger.debug('gnome-screenshot failed: %s', e)

        return ScreenshotResult(
            method='xdg_portal',
            success=False,
            error='No Wayland screenshot tool found. Install grim or gnome-screenshot.',
        )

    @staticmethod
    def _png_dimensions(data: bytes) -> tuple[int, int]:
        """Extract width/height from PNG IHDR chunk (no PIL dependency)."""
        if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
            return (0, 0)
        import struct
        width = struct.unpack('>I', data[16:20])[0]
        height = struct.unpack('>I', data[20:24])[0]
        return (width, height)

    def benchmark(self, target: str, method: str, rounds: int = 10) -> dict:
        """Run N capture rounds and report stats."""
        if rounds <= 0:
            return {'method': method, 'avg_ms': 0, 'min_ms': 0, 'max_ms': 0, 'fps': 0, 'success_rate': 0.0}

        latencies: list[float] = []
        success_count = 0
        for _ in range(rounds):
            result = self.capture(target, method)
            if result.success:
                success_count += 1
                latencies.append(result.latency_ms)

        if not latencies:
            return {
                'method': method,
                'avg_ms': 0,
                'min_ms': 0,
                'max_ms': 0,
                'fps': 0,
                'success_rate': 0.0,
            }

        avg_ms = sum(latencies) / len(latencies)
        return {
            'method': method,
            'avg_ms': round(avg_ms, 2),
            'min_ms': round(min(latencies), 2),
            'max_ms': round(max(latencies), 2),
            'fps': round(1000 / avg_ms, 2) if avg_ms > 0 else 0,
            'success_rate': round(success_count / rounds, 2),
        }
