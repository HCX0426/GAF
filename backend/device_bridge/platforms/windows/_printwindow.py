import ctypes
from ctypes import wintypes

import numpy as np

_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32

SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
PW_RENDERFULLCONTENT = 0x00000002

# SetThreadDpiAwarenessContext (Windows 10 1607+).
# Makes the calling thread per-monitor DPI-aware so that GetWindowRect,
# GetClientRect and PrintWindow all report/render physical pixels and stay
# consistent with each other. This is essential when the host process (e.g.
# Django) is NOT DPI-aware: without it, GetWindowRect returns logical coords
# while PrintWindow renders at a different size, producing off-by-DPI bitmaps.
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


def capture_by_printwindow(hwnd: int) -> np.ndarray:
    w_hwnd = wintypes.HWND(hwnd)

    # Switch the calling thread to per-monitor DPI awareness so every Win32
    # call below (GetWindowRect / GetClientRect / ClientToScreen / PrintWindow)
    # operates in physical pixels. The previous context is restored on exit so
    # the rest of the process is unaffected.
    old_ctx = _user32.SetThreadDpiAwarenessContext(
        DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
    )

    try:
        # Full window rect (physical pixels). PrintWindow will render at this
        # size, so the bitmap must match exactly — no DPI scaling needed.
        win_rect = wintypes.RECT()
        _user32.GetWindowRect(w_hwnd, ctypes.byref(win_rect))
        full_width = win_rect.right - win_rect.left
        full_height = win_rect.bottom - win_rect.top
        if full_width <= 0 or full_height <= 0:
            raise RuntimeError(f'invalid window size: {full_width}x{full_height}')

        # Client rect in screen coordinates to compute the crop offset.
        client_rect = wintypes.RECT()
        _user32.GetClientRect(w_hwnd, ctypes.byref(client_rect))
        client_point = wintypes.POINT(client_rect.left, client_rect.top)
        _user32.ClientToScreen(w_hwnd, ctypes.byref(client_point))
        crop_x = client_point.x - win_rect.left
        crop_y = client_point.y - win_rect.top
        client_width = client_rect.right - client_rect.left
        client_height = client_rect.bottom - client_rect.top
        if client_width <= 0 or client_height <= 0:
            raise RuntimeError(
                f'invalid client area size: {client_width}x{client_height}'
            )

        window_dc = _user32.GetDC(w_hwnd)
        if not window_dc:
            raise RuntimeError('GetDC failed')

        try:
            compatible_dc = _gdi32.CreateCompatibleDC(window_dc)
            if not compatible_dc:
                raise RuntimeError('CreateCompatibleDC failed')

            bitmap = _gdi32.CreateCompatibleBitmap(window_dc, full_width, full_height)
            if not bitmap:
                _gdi32.DeleteDC(compatible_dc)
                raise RuntimeError('CreateCompatibleBitmap failed')

            old_obj = _gdi32.SelectObject(compatible_dc, bitmap)

            success = _user32.PrintWindow(w_hwnd, compatible_dc, PW_RENDERFULLCONTENT)
            if not success:
                _gdi32.SelectObject(compatible_dc, old_obj)
                _gdi32.DeleteObject(bitmap)
                _gdi32.DeleteDC(compatible_dc)
                raise RuntimeError('PrintWindow failed')

            bmi_header = _BITMAPINFOHEADER()
            bmi_header.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            bmi_header.biWidth = full_width
            bmi_header.biHeight = -full_height
            bmi_header.biPlanes = 1
            bmi_header.biBitCount = 32
            bmi_header.biCompression = 0
            bmi_header.biSizeImage = full_width * full_height * 4

            buf = ctypes.create_string_buffer(full_width * full_height * 4)
            _gdi32.GetDIBits(
                compatible_dc, bitmap,
                0, full_height, buf,
                ctypes.byref(_BITMAPINFO(bmiHeader=bmi_header)),
                DIB_RGB_COLORS,
            )

            _gdi32.SelectObject(compatible_dc, old_obj)
            _gdi32.DeleteObject(bitmap)
            _gdi32.DeleteDC(compatible_dc)

            img = np.frombuffer(buf, dtype=np.dtype(np.uint8)).reshape(full_height, full_width, 4)
            # Crop to the client area so the title bar and borders are excluded.
            img = img[crop_y : crop_y + client_height, crop_x : crop_x + client_width]
            return img[:, :, [2, 1, 0]]
        finally:
            _user32.ReleaseDC(w_hwnd, window_dc)
    finally:
        if old_ctx:
            _user32.SetThreadDpiAwarenessContext(old_ctx)
