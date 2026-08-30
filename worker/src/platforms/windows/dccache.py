"""DCCache — Per-hwnd DC/Bitmap cache for high-performance BitBlt screenshots

Caches source DC, compatible DC, and bitmap objects per window handle.
Only recreates when window dimensions change. Thread-safe.

Reference: ok-script's DC caching strategy
"""

import ctypes
import ctypes.wintypes
import logging
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class DCCache:
    """Per-hwnd GDI device context and bitmap cache

    Avoids repeated CreateCompatibleDC/CreateCompatibleBitmap calls
    by caching GDI objects per window handle. Automatically detects
    window resize and recreates cache entries.
    """

    def __init__(self):
        self._lock = threading.RLock()
        # Cache entry: (src_dc, mem_dc, bitmap, width, height)
        self._cache: dict[int, tuple[int, int, int, int, int]] = {}
        self._hits = 0
        self._misses = 0

    def capture(self, hwnd: int) -> Optional["np.ndarray"]:
        """Capture screenshot using cached DC/Bitmap

        Args:
            hwnd: Target window handle (0 for desktop)

        Returns:
            BGR numpy array (height, width, 3), or None on failure
        """
        import numpy as np

        with self._lock:
            src_dc, mem_dc, bitmap, width, height = self._get_or_create(hwnd)

            if src_dc is None:
                return None

            try:
                SRCCOPY = 0x00CC0020
                gdi32.BitBlt(mem_dc, 0, 0, width, height, src_dc, 0, 0, SRCCOPY)

                bmi_fields = [
                    ("biSize", ctypes.wintypes.DWORD),
                    ("biWidth", ctypes.wintypes.LONG),
                    ("biHeight", ctypes.wintypes.LONG),
                    ("biPlanes", ctypes.wintypes.WORD),
                    ("biBitCount", ctypes.wintypes.WORD),
                    ("biCompression", ctypes.wintypes.DWORD),
                    ("biSizeImage", ctypes.wintypes.DWORD),
                    ("biXPelsPerMeter", ctypes.wintypes.LONG),
                    ("biYPelsPerMeter", ctypes.wintypes.LONG),
                    ("biClrUsed", ctypes.wintypes.DWORD),
                    ("biClrImportant", ctypes.wintypes.DWORD),
                ]
                BITMAPINFOHEADER = type(
                    "BITMAPINFOHEADER", (ctypes.Structure,), {"_fields_": bmi_fields}
                )
                bi = BITMAPINFOHEADER()
                bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bi.biWidth = width
                bi.biHeight = -height
                bi.biPlanes = 1
                bi.biBitCount = 32
                bi.biCompression = 0

                buf_size = width * height * 4
                buf = ctypes.create_string_buffer(buf_size)

                gdi32.GetDIBits(
                    mem_dc, bitmap, 0, height,
                    buf, ctypes.byref(bi), 0
                )

                img = np.frombuffer(buf, dtype=np.uint8).reshape((height, width, 4))
                return img[:, :, :3].copy()
            except Exception as exc:
                logger.warning("DC cache capture failed for hwnd=%s: %s", hwnd, exc)
                self._invalidate(hwnd)
                return None

    def _get_or_create(self, hwnd: int) -> tuple[int | None, int | None, int | None, int, int]:
        """Get cached DC/Bitmap or create new ones

        Returns:
            (src_dc, mem_dc, bitmap, width, height)
            All None if creation fails
        """
        rect = ctypes.wintypes.RECT()
        target_hwnd = hwnd if hwnd else user32.GetDesktopWindow()
        user32.GetWindowRect(target_hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top

        if width <= 0 or height <= 0:
            return None, None, None, 0, 0

        cached = self._cache.get(hwnd)
        if cached is not None:
            _, _, _, cached_w, cached_h = cached
            if cached_w == width and cached_h == height:
                self._hits += 1
                return cached
            else:
                logger.debug("Window resized %s->%s, invalidating cache", (cached_w, cached_h), (width, height))
                self._invalidate(hwnd)

        self._misses += 1
        return self._create_entry(hwnd, width, height)

    def _create_entry(self, hwnd: int, width: int, height: int) -> tuple[int | None, int | None, int | None, int, int]:
        """Create new DC/Bitmap cache entry for given hwnd and dimensions"""
        try:
            target_hwnd = hwnd if hwnd else user32.GetDesktopWindow()
            src_dc = user32.GetWindowDC(target_hwnd)
            mem_dc = gdi32.CreateCompatibleDC(src_dc)
            bitmap = gdi32.CreateCompatibleBitmap(src_dc, width, height)
            gdi32.SelectObject(mem_dc, bitmap)

            entry = (src_dc, mem_dc, bitmap, width, height)
            self._cache[hwnd] = entry
            logger.debug("DC cache created: hwnd=%s, %sx%s", hwnd, width, height)
            return entry
        except Exception as exc:
            logger.error("Failed to create DC cache for hwnd=%s: %s", hwnd, exc)
            return None, None, None, width, height

    def _invalidate(self, hwnd: int) -> None:
        """Release and remove cache entry for given hwnd"""
        entry = self._cache.pop(hwnd, None)
        if entry is None:
            return

        src_dc, mem_dc, bitmap, _w, _h = entry
        try:
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if mem_dc:
                gdi32.DeleteDC(mem_dc)
            if src_dc:
                target_hwnd = hwnd if hwnd else user32.GetDesktopWindow()
                user32.ReleaseDC(target_hwnd, src_dc)
        except Exception:
            pass
        logger.debug("DC cache invalidated: hwnd=%s", hwnd)

    def release(self, hwnd: int | None = None) -> None:
        """Release cache entries

        Args:
            hwnd: Specific hwnd to release, or None to release all
        """
        with self._lock:
            if hwnd is not None:
                self._invalidate(hwnd)
            else:
                for h in list(self._cache.keys()):
                    self._invalidate(h)

    @property
    def stats(self) -> dict:
        """Cache performance statistics"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            "entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": f"{hit_rate:.1f}%",
        }

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, hwnd: int) -> bool:
        return hwnd in self._cache
