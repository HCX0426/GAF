import ctypes
from ctypes import wintypes

import numpy as np

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_kernel32 = ctypes.windll.kernel32

SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0

# SetThreadDpiAwarenessContext (Windows 10 1607+).
# Ensures GetClientRect / BitBlt operate in physical pixels so the captured
# bitmap matches the window's real rendering size. Without this, a DPI-unaware
# host process reports logical coords while the window renders at physical
# size, producing misaligned or clipped screenshots.
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
_user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
_user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]

class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD),
        ('biWidth', wintypes.LONG),
        ('biHeight', wintypes.LONG),
        ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD),
        ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD),
        ('biXPelsPerMeter', wintypes.LONG),
        ('biYPelsPerMeter', wintypes.LONG),
        ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD),
    ]

class _BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ('bmiHeader', _BITMAPINFOHEADER),
        ('bmiColors', wintypes.DWORD * 0),
    ]

class BitBltCapture:
    def __init__(self):
        self._window_dc = None
        self._compatible_dc = None
        self._bitmap = None
        self._old_obj = None
        self._cached_hwnd = None
        self._cached_width = 0
        self._cached_height = 0

    def _cleanup(self):
        if self._old_obj and self._compatible_dc:
            _gdi32.SelectObject(self._compatible_dc, self._old_obj)
            self._old_obj = None
        if self._bitmap:
            _gdi32.DeleteObject(self._bitmap)
            self._bitmap = None
        if self._compatible_dc:
            _gdi32.DeleteDC(self._compatible_dc)
            self._compatible_dc = None
        if self._window_dc:
            _user32.ReleaseDC(self._cached_hwnd, self._window_dc)
            self._window_dc = None
        self._cached_hwnd = None
        self._cached_width = 0
        self._cached_height = 0

    def capture(self, hwnd: int) -> np.ndarray:
        w_hwnd = wintypes.HWND(hwnd)

        # Switch the calling thread to per-monitor DPI awareness so GetClientRect
        # and BitBlt operate in physical pixels, matching the window's real
        # rendering size. Restored on exit so the rest of the process is unaffected.
        old_ctx = _user32.SetThreadDpiAwarenessContext(
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
        try:
            rect = wintypes.RECT()
            _user32.GetClientRect(w_hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width <= 0 or height <= 0:
                raise RuntimeError(f'invalid window size: {width}x{height}')

            if (self._cached_hwnd != hwnd or
                    self._cached_width != width or
                    self._cached_height != height):
                self._cleanup()

            if self._window_dc is None:
                self._window_dc = _user32.GetDC(w_hwnd)
                if not self._window_dc:
                    raise RuntimeError('GetDC failed')
                self._compatible_dc = _gdi32.CreateCompatibleDC(self._window_dc)
                if not self._compatible_dc:
                    self._cleanup()
                    raise RuntimeError('CreateCompatibleDC failed')
                self._bitmap = _gdi32.CreateCompatibleBitmap(self._window_dc, width, height)
                if not self._bitmap:
                    self._cleanup()
                    raise RuntimeError('CreateCompatibleBitmap failed')
                self._old_obj = _gdi32.SelectObject(self._compatible_dc, self._bitmap)
                self._cached_hwnd = hwnd
                self._cached_width = width
                self._cached_height = height

            success = _gdi32.BitBlt(
                self._compatible_dc, 0, 0, width, height,
                self._window_dc, 0, 0, SRCCOPY,
            )
            if not success:
                raise RuntimeError('BitBlt failed')

            bmi_header = _BITMAPINFOHEADER()
            bmi_header.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            bmi_header.biWidth = width
            bmi_header.biHeight = -height
            bmi_header.biPlanes = 1
            bmi_header.biBitCount = 32
            bmi_header.biCompression = 0
            bmi_header.biSizeImage = width * height * 4

            buf = ctypes.create_string_buffer(width * height * 4)
            _gdi32.GetDIBits(
                self._compatible_dc, self._bitmap,
                0, height, buf,
                ctypes.byref(_BITMAPINFO(bmiHeader=bmi_header)),
                DIB_RGB_COLORS,
            )

            img = np.frombuffer(buf, dtype=np.uint8).reshape(height, width, 4)
            return img[:, :, [2, 1, 0]]
        finally:
            if old_ctx:
                _user32.SetThreadDpiAwarenessContext(old_ctx)

    def __del__(self):
        self._cleanup()


def capture_by_bitblt(hwnd: int) -> np.ndarray:
    capturer = BitBltCapture()
    return capturer.capture(hwnd)
