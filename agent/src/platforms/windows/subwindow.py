"""SubWindowCompositor — Multi-child-window screenshot compositing

Captures multiple child windows of a parent hwnd and composites them
into a single image using cached DC/Bitmap for performance.

Also provides resolve_child_at_client_point() for P1-6 child-window
coordinate resolution used by WithWindowPos input variants.

Reference: ok-script's composite_hwnds strategy
"""

import ctypes
import ctypes.wintypes
import logging
from typing import Any

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32

# ChildWindowFromPointEx flags (uFlags).
CWP_SKIPINVISIBLE = 0x0001
CWP_SKIPDISABLED = 0x0002
CWP_SKIPTRANSPARENT = 0x0004

# Max recursion depth for child window resolution (prevents infinite loops
# on pathological window hierarchies).
_MAX_CHILD_DEPTH = 32


def resolve_child_at_client_point(
    top_hwnd: int,
    x: int,
    y: int,
    skip_invisible: bool = True,
    skip_disabled: bool = True,
    skip_transparent: bool = True,
) -> tuple[int, int, int]:
    """Resolve (top_hwnd, x, y) to (deepest_child_hwnd, child_x, child_y).

    Walks ChildWindowFromPointEx recursively to find the deepest visible,
    enabled, non-transparent child window at the given client coordinate.
    At each level, translates the point from the parent's client space
    into the resolved child's client space via ClientToScreen/ScreenToClient.

    P1-6: Used by WithWindowPos input variants to dispatch mouse messages
    to the correct child window (e.g. Unity render panel inside a launcher
    shell) instead of silently dropping them on the top-level window.

    Args:
        top_hwnd: Top-level window handle.
        x, y: Client coordinates relative to top_hwnd.
        skip_invisible: Skip invisible child windows (default True).
        skip_disabled: Skip disabled child windows (default True).
        skip_transparent: Skip transparent child windows (default True).

    Returns:
        Tuple of (child_hwnd, child_x, child_y). If the top-level window
        has no child at that point, returns (top_hwnd, x, y) unchanged.
    """
    flags = 0
    if skip_invisible:
        flags |= CWP_SKIPINVISIBLE
    if skip_disabled:
        flags |= CWP_SKIPDISABLED
    if skip_transparent:
        flags |= CWP_SKIPTRANSPARENT

    parent = top_hwnd
    pt = ctypes.wintypes.POINT(x, y)

    for _ in range(_MAX_CHILD_DEPTH):
        child = user32.ChildWindowFromPointEx(parent, pt, flags)
        # ChildWindowFromPointEx returns:
        #   - parent itself if the point is in parent but not in any child
        #   - NULL (0) if the point is outside parent's client area
        #   - a child hwnd if a child contains the point
        if child == 0 or child == parent:
            break
        # Translate pt from parent's client space to child's client space
        # via screen coordinates.
        user32.ClientToScreen(parent, ctypes.byref(pt))
        user32.ScreenToClient(child, ctypes.byref(pt))
        parent = child

    return parent, pt.x, pt.y


class SubWindowCompositor:
    """Multi-sub-window screenshot compositor

    For games that render content across multiple child windows
    (e.g., main game area + chat panel + inventory bar),
    captures each sub-window independently and composites into one image.
    """

    def __init__(self):
        self._dccache = None

    def _get_dccache(self):
        """Lazy import DC cache"""
        if self._dccache is None:
            from platforms.windows.dccache import DCCache
            self._dccache = DCCache()
        return self._dccache

    def find_child_windows(
        self,
        parent_hwnd: int,
        class_filter: str | None = None,
        title_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Find all visible child windows of a parent window

        Args:
            parent_hwnd: Parent window handle
            class_filter: Optional class name filter (substring match)
            title_filter: Optional title filter (substring match)

        Returns:
            List of child window info dicts
        """
        results: list[dict[str, Any]] = []

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.wintypes.BOOL,
            ctypes.wintypes.HWND,
            ctypes.wintypes.LPARAM,
        )

        def _enum_callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True

            buf_len = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(buf_len + 1)
            user32.GetWindowTextW(hwnd, buf, buf_len + 1)
            win_title = buf.value

            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            win_class = cls_buf.value

            if class_filter and class_filter.lower() not in win_class.lower():
                return True
            if title_filter and title_filter.lower() not in win_title.lower():
                return True

            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))

            results.append({
                "hwnd": hwnd,
                "title": win_title,
                "class": win_class,
                "rect": (rect.left, rect.top, rect.right, rect.bottom),
                "width": rect.right - rect.left,
                "height": rect.bottom - rect.top,
            })
            return True

        callback = EnumWindowsProc(_enum_callback)
        user32.EnumChildWindows(parent_hwnd, callback, 0)
        logger.info("Found %d child windows for parent=%s", len(results), parent_hwnd)
        return results

    def composite(
        self,
        hwnds: list[int],
        layout: str | None = "grid",
        padding: int = 0,
        background: tuple[int, int, int] | None = None,
    ) -> Any | None:
        """Composite screenshots of multiple windows into one image

        Args:
            hwnds: List of window handles to capture
            layout: Layout mode - "grid" (row), "vertical" (col), or "overlay"
            padding: Pixel gap between captured regions
            background: RGB tuple for background color (default black)

        Returns:
            Composite numpy array (BGR), or None on failure
        """

        if not hwnds:
            logger.warning("No windows to composite")
            return None

        dccache = self._get_dccache()

        frames = []
        rects = []

        for hwnd in hwnds:
            frame = dccache.capture(hwnd)
            if frame is not None:
                frames.append(frame)

                rect = ctypes.wintypes.RECT()
                target = hwnd if hwnd else user32.GetDesktopWindow()
                user32.GetWindowRect(target, ctypes.byref(rect))
                rects.append((rect.left, rect.top, rect.right, rect.bottom))
            else:
                logger.warning("Failed to capture hwnd=%s", hwnd)

        if not frames:
            logger.error("All window captures failed")
            return None

        bg = background if background else (0, 0, 0)
        return self._layout_composite(frames, rects, layout, padding, bg)

    def _layout_composite(
        self,
        frames: list,
        rects: list,
        layout: str,
        padding: int,
        bg: tuple[int, int, int],
    ) -> Any:
        """Layout multiple frames according to specified mode"""

        n = len(frames)
        if n == 1:
            return frames[0]

        if layout == "grid":
            return self._layout_grid(frames, padding, bg)
        elif layout == "vertical":
            return self._layout_vertical(frames, padding, bg)
        elif layout == "horizontal":
            return self._layout_horizontal(frames, padding, bg)
        elif layout == "overlay":
            return self._layout_overlay(frames, rects, bg)
        else:
            return self._layout_grid(frames, padding, bg)

    def _layout_grid(
        self, frames: list, padding: int, bg: tuple[int, int, int]
    ) -> Any:
        """Grid layout: arrange in roughly square grid"""
        import math

        import numpy as np

        n = len(frames)
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)

        max_h = max(f.shape[0] for f in frames)
        max_w = max(f.shape[1] for f in frames)

        out_h = rows * max_h + (rows - 1) * padding
        out_w = cols * max_w + (cols - 1) * padding
        canvas = np.full((out_h, out_w, 3), bg, dtype=np.uint8)

        for i, frame in enumerate(frames):
            row = i // cols
            col = i % cols
            y_off = row * (max_h + padding)
            x_off = col * (max_w + padding)
            h, w = frame.shape[:2]
            canvas[y_off:y_off + h, x_off:x_off + w] = frame

        return canvas

    def _layout_vertical(
        self, frames: list, padding: int, bg: tuple[int, int, int]
    ) -> Any:
        """Vertical stack layout"""
        import numpy as np

        total_h = sum(f.shape[0] for f in frames) + (len(frames) - 1) * padding
        max_w = max(f.shape[1] for f in frames)
        canvas = np.full((total_h, max_w, 3), bg, dtype=np.uint8)

        y_off = 0
        for frame in frames:
            h, w = frame.shape[:2]
            canvas[y_off:y_off + h, :w] = frame
            y_off += h + padding

        return canvas

    def _layout_horizontal(
        self, frames: list, padding: int, bg: tuple[int, int, int]
    ) -> Any:
        """Horizontal side-by-side layout"""
        import numpy as np

        total_w = sum(f.shape[1] for f in frames) + (len(frames) - 1) * padding
        max_h = max(f.shape[0] for f in frames)
        canvas = np.full((max_h, total_w, 3), bg, dtype=np.uint8)

        x_off = 0
        for frame in frames:
            h, w = frame.shape[:2]
            canvas[:h, x_off:x_off + w] = frame
            x_off += w + padding

        return canvas

    def _layout_overlay(
        self, frames: list, rects: list, bg: tuple[int, int, int]
    ) -> Any:
        """Overlay layout: composite at original screen positions using DPI scaling"""
        import numpy as np

        if not rects:
            return self._layout_grid(frames, 0, bg)

        min_left = min(r[0] for r in rects)
        min_top = min(r[1] for r in rects)
        max_right = max(r[2] for r in rects)
        max_bottom = max(r[3] for r in rects)

        canvas_w = max_right - min_left
        canvas_h = max_bottom - min_top
        canvas = np.full((canvas_h, canvas_w, 3), bg, dtype=np.uint8)

        dpi_scale = self._get_dpi_scale_factor()

        for frame, rect in zip(frames, rects, strict=False):
            h, w = frame.shape[:2]
            x = int((rect[0] - min_left) * dpi_scale)
            y = int((rect[1] - min_top) * dpi_scale)
            scaled_w = int(w * dpi_scale)
            scaled_h = int(h * dpi_scale)

            if scaled_w > 0 and scaled_h > 0:
                resized = frame
                if abs(dpi_scale - 1.0) > 0.01:
                    resized = self._resize_frame(frame, scaled_w, scaled_h)

                y_end = min(y + scaled_h, canvas_h)
                x_end = min(x + scaled_w, canvas_w)
                canvas[y:y_end, x:x_end] = resized[:y_end - y, :x_end - x]

        return canvas

    @staticmethod
    def _get_dpi_scale_factor() -> float:
        """Get DPI scaling factor for high-DPI displays.

        Delegates to platforms.windows.dpi which implements the 3-level
        DPI awareness fallback (Per-Monitor v2 -> Per-Monitor -> System)
        per the MaaFramework pattern (P1-4).
        """
        try:
            from platforms.windows.dpi import get_dpi_scale_factor
            return get_dpi_scale_factor(0)
        except Exception:
            return 1.0

    @staticmethod
    def _resize_frame(frame: Any, new_w: int, new_h: int) -> Any:
        """Resize numpy frame to new dimensions using cv2 or numpy"""
        try:
            import cv2
            return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        except ImportError:
            import numpy as np
            return np.asarray(frame).astype(np.float32).reshape(frame.shape)

    def release(self) -> None:
        """Release cached resources"""
        if self._dccache:
            self._dccache.release()
            self._dccache = None
