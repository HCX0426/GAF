"""
macOS 截图处理器
基于 CoreGraphics CGWindowListCreateImage (pyobjc-framework-Quartz)
依赖：pyobjc-framework-Quartz (macOS only)
参考：MaaFramework macOS 截图实现
"""
import logging
import time

from device_bridge.platforms.base import PlatformScreenshotHandler, ScreenshotResult

logger = logging.getLogger(__name__)

MACOS_METHODS = ['CGWindowList', 'screencapture']

# Cache availability check result
_availability_cache: dict[str, bool] = {}


def _check_quartz_available() -> bool:
    """Check if pyobjc Quartz framework is importable (macOS only)."""
    if 'quartz' in _availability_cache:
        return _availability_cache['quartz']
    try:
        import Quartz  # noqa: F401
        from Quartz import CGWindowListCreateImage  # noqa: F401
        _availability_cache['quartz'] = True
        return True
    except ImportError:
        _availability_cache['quartz'] = False
        return False


def _check_screen_recording_permission() -> bool:
    """
    Check Screen Recording permission (macOS 10.15+).
    Uses CGPreflightScreenCaptureAccess / CGRequestScreenCaptureAccess when available.
    """
    if not _check_quartz_available():
        return False
    try:
        from Quartz import (
            CGPreflightScreenCaptureAccess,
            CGRequestScreenCaptureAccess,
        )
        # Preflight (does not prompt)
        if CGPreflightScreenCaptureAccess():
            return True
        # Request (prompts once, returns current state)
        return bool(CGRequestScreenCaptureAccess())
    except (ImportError, AttributeError):
        # Older macOS without preflight API — assume granted
        return True


class MacOSScreenshotHandler(PlatformScreenshotHandler):
    """macOS 截图处理器，支持 CGWindowListCreateImage / screencapture 两种方式"""

    def __init__(self, method: str = ''):
        self.method = method or 'CGWindowList'

    def available_methods(self) -> list[str]:
        return MACOS_METHODS

    def capture(self, target: str, method: str = '') -> ScreenshotResult:
        method = method or self.method
        start = time.monotonic()

        # Validate method first (no permission needed for parameter check)
        if method not in MACOS_METHODS:
            return ScreenshotResult(
                method=method,
                success=False,
                error=f'Unknown method: {method}. Supported: {MACOS_METHODS}',
            )

        # Permission preflight
        if not _check_screen_recording_permission():
            return ScreenshotResult(
                method=method,
                success=False,
                error='Screen Recording permission not granted. '
                      'System Preferences > Security & Privacy > Privacy > Screen Recording',
            )

        try:
            window_id = self._parse_target(target)
        except ValueError as e:
            return ScreenshotResult(method=method, success=False, error=str(e))

        if method == 'CGWindowList':
            return self._capture_cgwindowlist(window_id, start)
        elif method == 'screencapture':
            return self._capture_screencapture(window_id, start)
        # Unreachable due to method check above, but keep for safety
        return ScreenshotResult(
            method=method,
            success=False,
            error=f'Unknown method: {method}. Supported: {MACOS_METHODS}',
        )

    def _capture_cgwindowlist(self, window_id: int, start: float) -> ScreenshotResult:
        """Capture via CGWindowListCreateImage (no shell subprocess, fastest)."""
        try:
            # Use BitmapRep to convert CGImage to PNG bytes
            from AppKit import NSBitmapImageRep, NSPNGFileType
            from CoreGraphics import CGImageGetHeight, CGImageGetWidth
            from Quartz import (
                CGRectNull,
                CGWindowListCreateImage,
                kCGWindowListOptionIncludingWindow,
            )
        except ImportError as e:
            return ScreenshotResult(
                method='CGWindowList',
                success=False,
                error=f'pyobjc framework not available: {e}. Install: pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa',
            )

        try:
            # CGRectNull means "capture full window bounds"
            cg_image = CGWindowListCreateImage(
                CGRectNull,
                kCGWindowListOptionIncludingWindow,
                window_id,
                0,  # imageOption (default)
            )
            if cg_image is None:
                return ScreenshotResult(
                    method='CGWindowList',
                    success=False,
                    error=f'CGWindowListCreateImage returned None for window_id={window_id}. Window may not exist.',
                )

            width = CGImageGetWidth(cg_image)
            height = CGImageGetHeight(cg_image)

            # Convert CGImage -> NSBitmapImageRep -> PNG bytes
            rep = NSBitmapImageRep.alloc().initWithCGImage_(cg_image)
            png_data = rep.representationUsingType_properties_(NSPNGFileType, {})
            latency_ms = (time.monotonic() - start) * 1000

            return ScreenshotResult(
                image_bytes=bytes(png_data),
                latency_ms=latency_ms,
                resolution={'width': width, 'height': height},
                method='CGWindowList',
                success=True,
            )
        except Exception as e:
            return ScreenshotResult(
                method='CGWindowList',
                success=False,
                error=f'CGWindowList capture failed: {e}',
            )

    def _capture_screencapture(self, window_id: int, start: float) -> ScreenshotResult:
        """Capture via `screencapture` CLI utility (fallback, slower)."""
        import os
        import subprocess
        import tempfile

        # screencapture does not support window_id directly; capture full screen
        # then crop is non-trivial. For now, capture full screen as fallback.
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp_path = tmp.name
            # -x: no sound, -C: cursor not included
            result = subprocess.run(
                ['screencapture', '-x', tmp_path],
                capture_output=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                return ScreenshotResult(
                    method='screencapture',
                    success=False,
                    error=f'screencapture failed: {result.stderr.decode(errors="replace")}',
                )
            with open(tmp_path, 'rb') as f:
                image_bytes = f.read()
            os.unlink(tmp_path)

            # Get resolution from PNG
            width, height = self._png_dimensions(image_bytes)
            latency_ms = (time.monotonic() - start) * 1000
            return ScreenshotResult(
                image_bytes=image_bytes,
                latency_ms=latency_ms,
                resolution={'width': width, 'height': height},
                method='screencapture',
                success=True,
            )
        except FileNotFoundError:
            return ScreenshotResult(
                method='screencapture',
                success=False,
                error='screencapture command not found (not running on macOS?)',
            )
        except subprocess.TimeoutExpired:
            return ScreenshotResult(
                method='screencapture',
                success=False,
                error='screencapture timed out after 10s',
            )
        except Exception as e:
            return ScreenshotResult(
                method='screencapture',
                success=False,
                error=f'screencapture failed: {e}',
            )

    @staticmethod
    def _parse_target(target: str) -> int:
        """Parse target string to window_id (int).

        Accepts:
          - Decimal: "12345"
          - Hex: "0x3039" or "#3039"
        """
        if not target:
            raise ValueError(f'target must be a window_id (int or hex string), got: {target!r}')
        target = target.strip()
        try:
            if target.startswith('0x') or target.startswith('0X'):
                return int(target, 16)
            if target.startswith('#'):
                return int(target[1:], 16)
            return int(target)
        except ValueError as e:
            raise ValueError(f'Invalid window_id: {target!r}. Expected decimal or hex (0x.../#...).') from e

    @staticmethod
    def _png_dimensions(data: bytes) -> tuple[int, int]:
        """Extract width/height from PNG IHDR chunk (no PIL dependency)."""
        if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
            return (0, 0)
        import struct
        # IHDR is at offset 8, width at offset 16, height at offset 20 (big-endian uint32)
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
