"""Coordinate transformer: base↔logical↔physical↔screen conversion.

This is the GAF port of BD2-AUTO's `CoordinateTransformer`. It depends
on `RuntimeDisplayContext` for live window/DPI/screen parameters and
implements the full coordinate chain used by ROI processing and template
scaling:

    BASE (reference, e.g. 1920x1080)
      │  scale_x = client_logical_w / orig_w
      ▼
    LOGICAL (client-area, DPI-independent)
      │  × dpi_scale
      ▼
    PHYSICAL (client-area pixels = screenshot pixels for borderless windows)
      │  + client_screen_origin (via ClientToScreen)
      ▼
    SCREEN (absolute screen coords, for SendInput)

Key methods:
- `process_roi(roi, boundary_w, boundary_h, roi_coord_type)` — full ROI
  pipeline: format check → mode adapt → boundary limit → optional expand.
  Returns (physical_roi, offset). Used by template_match / feature_match
  / color_detect before cv2.matchTemplate.
- `calculate_template_scale_ratio(target_phys_size)` — `min(target_w/orig_w,
  target_h/orig_h)`, used to cv2.resize templates before matching.
- `apply_roi_offset_to_subcoord(sub_coord, roi_offset)` — adds ROI offset
  back to sub-image match coordinates to recover full-image coordinates.

Differences from BD2-AUTO:
- Fullscreen detection via MonitorFromWindow + GetMonitorInfoW (TD-361)
  is implemented in real-time with FULLSCREEN_CACHE_DURATION caching.
- The numpy/list/tuple ROI normalization is preserved verbatim.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import cast

import numpy as np
from utils.display_context import RuntimeDisplayContext
from utils.perf_monitor import Timer

logger = logging.getLogger(__name__)

# Type aliases
Point = tuple[int, int]
ROI = tuple[int, int, int, int]  # (x, y, w, h)
LoggerLike = logging.Logger

# ── Windows API imports (TD-361: real-time fullscreen detection) ──
try:
    import ctypes
    import ctypes.wintypes
    _user32 = ctypes.windll.user32
    _MONITOR_DEFAULTTONEAREST = 0x00000002

    class _MONITORINFO(ctypes.Structure):
        """MONITORINFO struct for GetMonitorInfoW."""
        _fields_ = [
            ("cbSize", ctypes.wintypes.DWORD),
            ("rcMonitor", ctypes.wintypes.RECT),
            ("rcWork", ctypes.wintypes.RECT),
            ("dwFlags", ctypes.wintypes.DWORD),
        ]

    _HAS_WIN32 = True
except Exception:
    _HAS_WIN32 = False


class CoordType(Enum):
    """Coordinate system tag for ROI inputs and recognition results.

    N191 §10.10 决策点 3 (AI 可调试性, 2026-07-27): 新增 SUB_IMAGE
    显式标注子图坐标系, 堵住 "节点 crop 子图后忘了加 ROI 偏移就 publish"
    类 bug 的调试盲点 (OCR §10.2 已发生过)。
    """

    BASE = "base"          # Reference resolution (e.g. 1920x1080)
    LOGICAL = "logical"    # Client-area logical (DPI-independent)
    PHYSICAL = "physical"  # Client-area physical (actual pixels)
    SUB_IMAGE = "sub_image"  # Cropped sub-image local coords (origin = ROI top-left)


class CoordinateTransformer:
    """Coordinate and ROI processor built on `RuntimeDisplayContext`.

    Provides the full base↔logical↔physical↔screen conversion chain plus
    ROI-specific helpers (format validation, boundary clamping, safe
    expansion, sub-coordinate offset). The transformer reads live values
    from the context, so callers should mutate the context (via
    `update_from_window`) before each pipeline execution.
    """

    # N191 §10.7 P0-1 (架构层归一化, 2026-07-27): 当前 transformer 下
    # convert_original_to_current_client 返回的坐标系标签。Windows 路径
    # 返回 logical (client), ADB 路径 (ADBCoordinateTransformer) 返回 physical。
    # orchestrator 读取此属性注入 PipelineContext.coord_system, 让
    # publish_match_pos / structured_logger / resolve_target 知道坐标系。
    coord_system: str = "logical"

    # ── Constants ─────────────────────────────────────────────────
    FULLSCREEN_ERROR_TOLERANCE: int = 5
    """Fullscreen detection tolerance (px): match if window and screen
    dimensions differ by less than this on each axis."""

    DEFAULT_ROI_EXPAND_PIXEL: int = 10
    """Default ROI safe-expand pixel count (OCR use case: prevents target
    edges from being clipped)."""

    FULLSCREEN_CACHE_DURATION: float = 0.5
    """Fullscreen state cache TTL (seconds): reduces system API calls."""

    def __init__(self, display_context: RuntimeDisplayContext, logger: LoggerLike | None = None):
        """Initialize the transformer.

        Args:
            display_context: Live display context (mutated externally).
            logger: Optional logger; falls back to module logger.
        """
        self._display_context = display_context
        self.logger = logger or globals()["logger"]
        # Fullscreen cache (unused for now — is_fullscreen comes from context)
        self._fullscreen_cache: bool | None = None
        self._fullscreen_cache_time: float = 0.0

        self.logger.info(
            "CoordinateTransformer initialized | base=%s | fullscreen_cache=%.0fms",
            display_context.original_base_res,
            self.FULLSCREEN_CACHE_DURATION * 1000,
        )

    # ── Public properties ─────────────────────────────────────────
    @property
    def display_context(self) -> RuntimeDisplayContext:
        """Live display context."""
        return self._display_context

    @property
    def is_fullscreen(self) -> bool:
        """Real-time fullscreen detection via MonitorFromWindow + GetMonitorInfo.

        TD-361: Replaces the previous approach of reading from the
        display_context flag (set once at build time). Now calls
        MonitorFromWindow + GetMonitorInfoW to get the current monitor's
        resolution, then compares the window's client rect against it
        within FULLSCREEN_ERROR_TOLERANCE.

        The result is cached for FULLSCREEN_CACHE_DURATION seconds to
        reduce system API calls. Falls back to display_context flag on
        non-Windows or when the window handle is unavailable.
        """
        now = time.time()
        if self._fullscreen_cache is not None and (now - self._fullscreen_cache_time) < self.FULLSCREEN_CACHE_DURATION:
            return self._fullscreen_cache

        hwnd = self._display_context.hwnd
        if not hwnd or not _HAS_WIN32:
            # Fallback: use the display_context flag (set at build time).
            result = bool(self._display_context.is_fullscreen)
            self._fullscreen_cache = result
            self._fullscreen_cache_time = now
            return result

        try:
            # Get the monitor that contains this window.
            hmonitor = _user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
            if not hmonitor:
                raise OSError("MonitorFromWindow returned NULL")

            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(mi)
            if not _user32.GetMonitorInfoW(hmonitor, ctypes.byref(mi)):
                raise OSError("GetMonitorInfoW failed")

            monitor_w = mi.rcMonitor.right - mi.rcMonitor.left
            monitor_h = mi.rcMonitor.bottom - mi.rcMonitor.top

            # Get the window's client rect.
            client_rect = ctypes.wintypes.RECT()
            if not _user32.GetClientRect(hwnd, ctypes.byref(client_rect)):
                raise OSError("GetClientRect failed")

            client_w = client_rect.right - client_rect.left
            client_h = client_rect.bottom - client_rect.top

            # Fullscreen: client rect covers the monitor within tolerance.
            result = (
                abs(client_w - monitor_w) < self.FULLSCREEN_ERROR_TOLERANCE
                and abs(client_h - monitor_h) < self.FULLSCREEN_ERROR_TOLERANCE
            )
        except Exception:
            self.logger.debug("is_fullscreen: MonitorFromWindow failed, falling back to context flag", exc_info=True)
            result = bool(self._display_context.is_fullscreen)

        self._fullscreen_cache = result
        self._fullscreen_cache_time = now
        return result

    # ── Internal helpers ──────────────────────────────────────────
    @staticmethod
    def _ensure_positive_size(w: int, h: int) -> Point:
        """Clamp size to ≥1 on each axis."""
        return (max(1, w), max(1, h))

    @staticmethod
    def _ensure_coords_in_boundary(x: int, y: int, bw: int, bh: int) -> Point:
        """Clamp coords to [0, boundary-1]."""
        return (max(0, min(x, bw - 1)), max(0, min(y, bh - 1)))

    def _ensure_rect_in_boundary(self, rect: ROI, bw: int, bh: int) -> ROI:
        """Clamp rect to fit inside [0,bw]×[0,bh], preserving size ≥1."""
        x, y, w, h = rect
        x, y = self._ensure_coords_in_boundary(x, y, bw, bh)
        w = max(1, min(w, bw - x))
        h = max(1, min(h, bh - y))
        return (x, y, w, h)

    @staticmethod
    def _convert_numpy_to_tuple(item: tuple | list | np.ndarray) -> tuple:
        """Normalize numpy arrays / lists to tuple."""
        if isinstance(item, np.ndarray):
            return tuple(item.tolist())
        if isinstance(item, list):
            return tuple(item)
        return item

    # ── Point conversions (base chain) ────────────────────────────
    def convert_original_to_current_client(self, x: int, y: int) -> Point:
        """Base → client logical (axis-aligned scale).

        Fullscreen mode: base coords used directly (only boundary clamped).
        Window mode: scaled by (client_logical_w / orig_w, client_logical_h / orig_h).
        """
        ctx = self._display_context
        orig_w, orig_h = ctx.original_base_res

        if self.is_fullscreen:
            screen_w, screen_h = ctx.screen_physical_res
            return self._ensure_coords_in_boundary(x, y, screen_w, screen_h)

        curr_w, curr_h = ctx.client_logical_res
        if orig_w <= 0 or orig_h <= 0 or curr_w <= 0 or curr_h <= 0:
            self.logger.error(
                "convert_original_to_current_client: invalid resolution | base=%sx%s | logical=%sx%s",
                orig_w, orig_h, curr_w, curr_h,
            )
            return (x, y)

        scale_x = curr_w / orig_w
        scale_y = curr_h / orig_h
        fx, fy = int(round(x * scale_x)), int(round(y * scale_y))
        return self._ensure_coords_in_boundary(fx, fy, curr_w, curr_h)

    def convert_client_logical_to_physical(self, x: int, y: int) -> Point:
        """Client logical → client physical (apply DPI scale).

        Fullscreen mode: returns input unchanged (logical == physical).
        """
        if self.is_fullscreen:
            ctx = self._display_context
            phys_w, phys_h = ctx.screen_physical_res
            return self._ensure_coords_in_boundary(x, y, phys_w, phys_h)

        ctx = self._display_context
        ratio = ctx.logical_to_physical_ratio
        phys_w, phys_h = ctx.client_physical_res
        px, py = int(round(x * ratio)), int(round(y * ratio))
        return self._ensure_coords_in_boundary(px, py, phys_w, phys_h)

    def convert_client_physical_to_logical(self, x: int, y: int) -> Point:
        """Client physical → client logical (inverse DPI scale)."""
        ctx = self._display_context
        ratio = ctx.logical_to_physical_ratio
        if ratio <= 0:
            self.logger.error("convert_client_physical_to_logical: invalid ratio %s", ratio)
            return (x, y)

        lx, ly = int(round(x / ratio)), int(round(y / ratio))
        logical_w, logical_h = ctx.client_logical_res
        return self._ensure_coords_in_boundary(lx, ly, logical_w, logical_h)

    # ── Rectangle conversions ─────────────────────────────────────
    def convert_original_rect_to_current_client(self, rect: ROI) -> ROI:
        """Base rect → client logical rect (axis-aligned scale)."""
        x, y, w, h = rect
        if w <= 0 or h <= 0:
            self.logger.error("convert_original_rect_to_current_client: invalid size %s", rect)
            return rect

        ctx = self._display_context
        orig_w, orig_h = ctx.original_base_res
        curr_w, curr_h = ctx.client_logical_res
        if orig_w <= 0 or orig_h <= 0 or curr_w <= 0 or curr_h <= 0:
            self.logger.error(
                "convert_original_rect_to_current_client: invalid resolution | base=%sx%s | logical=%sx%s",
                orig_w, orig_h, curr_w, curr_h,
            )
            return rect

        scale_x = curr_w / orig_w
        scale_y = curr_h / orig_h
        nx, ny = int(round(x * scale_x)), int(round(y * scale_y))
        nw, nh = int(round(w * scale_x)), int(round(h * scale_y))

        nx = max(0, nx)
        ny = max(0, ny)
        nw, nh = self._ensure_positive_size(nw, nh)
        nw = min(nw, curr_w - nx)
        nh = min(nh, curr_h - ny)
        return (nx, ny, nw, nh)

    def convert_client_physical_rect_to_logical(self, rect: ROI) -> ROI:
        """Client physical rect → client logical rect (inverse DPI)."""
        x, y, w, h = rect
        if w <= 0 or h <= 0:
            self.logger.error("convert_client_physical_rect_to_logical: invalid size %s", rect)
            return rect

        nx, ny = self.convert_client_physical_to_logical(x, y)
        ctx = self._display_context
        ratio = ctx.logical_to_physical_ratio
        nw = int(round(w / ratio)) if ratio > 0 else w
        nh = int(round(h / ratio)) if ratio > 0 else h
        nw, nh = self._ensure_positive_size(nw, nh)
        return (nx, ny, nw, nh)

    # ── ROI format validation ─────────────────────────────────────
    def validate_roi_format(self, roi: ROI | list[int] | np.ndarray) -> tuple[bool, str | None]:
        """Validate ROI is a 4-tuple with x,y ≥ 0 and w,h > 0."""
        roi = self._convert_numpy_to_tuple(roi)
        if not isinstance(roi, (tuple, list)) or len(roi) != 4:
            return False, f"format error (need 4-tuple/list): type={type(roi)}, value={roi}"
        x, y, w, h = roi
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            return False, f"param error (x,y≥0, w,h>0): {roi}"
        return True, None

    # ── ROI full pipeline ─────────────────────────────────────────
    def process_roi(
        self,
        roi: ROI | list[int] | np.ndarray | None,
        boundary_width: int,
        boundary_height: int,
        enable_expand: bool = False,
        expand_pixel: int | None = None,
        roi_coord_type: CoordType = CoordType.BASE,
    ) -> tuple[ROI | None, Point]:
        """Full ROI pipeline: validate → mode-adapt → clamp → optional expand.

        Args:
            roi: Input ROI (x, y, w, h). None means "full image".
            boundary_width: Physical boundary width (typically screenshot width).
            boundary_height: Physical boundary height (typically screenshot height).
            enable_expand: Whether to apply safe-expand (OCR use case).
            expand_pixel: Override expand pixel count (default DEFAULT_ROI_EXPAND_PIXEL).
            roi_coord_type: Coordinate system of `roi` (BASE/LOGICAL/PHYSICAL).

        Returns:
            (physical_roi, roi_offset_phys):
              - physical_roi: (x, y, w, h) in physical pixels within boundary,
                or None if input was None or invalid.
              - roi_offset_phys: (offset_x, offset_y) of the ROI's top-left in
                the full image. Equal to physical_roi[:2] when expand is off.
        """
        if roi is None:
            return None, (0, 0)

        roi = cast(ROI, self._convert_numpy_to_tuple(roi))
        is_valid, err_msg = self.validate_roi_format(roi)
        if not is_valid:
            self.logger.warning("process_roi: %s", err_msg)
            return None, (0, 0)

        x, y, w, h = roi
        is_fullscreen = self.is_fullscreen
        ctx = self._display_context
        roi_offset_phys: Point = (0, 0)

        try:
            _timer_coord = Timer("pipeline.node.coord_transform", tags={"method": "process_roi"})
            _timer_coord.__enter__()
            if roi_coord_type == CoordType.PHYSICAL or is_fullscreen:
                rx_phys, ry_phys, rw_phys, rh_phys = x, y, w, h
            else:
                ratio = ctx.logical_to_physical_ratio
                if roi_coord_type == CoordType.LOGICAL:
                    rx_log, ry_log, rw_log, rh_log = x, y, w, h
                elif roi_coord_type == CoordType.BASE:
                    rx_log, ry_log, rw_log, rh_log = self.convert_original_rect_to_current_client(roi)
                else:
                    raise ValueError(f"unsupported roi_coord_type: {roi_coord_type}")

                client_w_log, client_h_log = ctx.client_logical_res
                rx_log = max(0, rx_log)
                ry_log = max(0, ry_log)
                rw_log = min(rw_log, client_w_log - rx_log)
                rh_log = min(rh_log, client_h_log - ry_log)

                rx_phys, ry_phys = self.convert_client_logical_to_physical(rx_log, ry_log)
                rw_phys = int(round(rw_log * ratio))
                rh_phys = int(round(rh_log * ratio))

            # Boundary clamp
            rx_phys = max(0, rx_phys)
            ry_phys = max(0, ry_phys)
            rw_phys = min(rw_phys, boundary_width - rx_phys)
            rh_phys = min(rh_phys, boundary_height - ry_phys)
            if rw_phys <= 0 or rh_phys <= 0:
                raise ValueError(f"physical ROI invalid after clamp: ({rx_phys},{ry_phys},{rw_phys},{rh_phys})")

            if enable_expand:
                ep = expand_pixel or self.DEFAULT_ROI_EXPAND_PIXEL
                new_rx = max(0, rx_phys - ep)
                new_ry = max(0, ry_phys - ep)
                new_rw = min(boundary_width - new_rx, rw_phys + 2 * ep)
                new_rh = min(boundary_height - new_ry, rh_phys + 2 * ep)
                if new_rw <= 0 or new_rh <= 0:
                    new_rx, new_ry, new_rw, new_rh = rx_phys, ry_phys, rw_phys, rh_phys
                processed = (new_rx, new_ry, new_rw, new_rh)
                roi_offset_phys = (new_rx, new_ry)
            else:
                processed = (rx_phys, ry_phys, rw_phys, rh_phys)
                roi_offset_phys = (rx_phys, ry_phys)

            _timer_coord.__exit__(None, None, None)
            return processed, roi_offset_phys

        except Exception as exc:
            _timer_coord.__exit__(None, None, None)
            self.logger.error("process_roi exception: %s (falling back to full image)", exc, exc_info=True)
            return None, (0, 0)

    # ── Generic rect utilities ────────────────────────────────────
    def get_rect_center(self, rect: ROI | list[int] | np.ndarray) -> Point:
        """Compute rect center (x+w//2, y+h//2). Returns (0,0) on invalid input."""
        rect = self._convert_numpy_to_tuple(rect)
        is_valid, _ = self.validate_roi_format(rect)
        if not is_valid:
            return (0, 0)
        try:
            x, y, w, h = map(int, rect)
            return (x + w // 2, y + h // 2)
        except (ValueError, TypeError):
            return (0, 0)

    def limit_rect_to_boundary(self, rect: ROI, bw: int, bh: int) -> ROI:
        """Clamp rect to boundary."""
        return self._ensure_rect_in_boundary(rect, bw, bh)

    def get_unified_logical_rect(self, phys_rect: ROI | list[int]) -> ROI | tuple[()]:
        """Convert physical rect → unified logical rect (mode-aware).

        Window mode: physical → logical (inverse DPI).
        Fullscreen mode: physical == logical, just clamp to screen.
        Returns () on invalid input.
        """
        phys_rect = cast(ROI, self._convert_numpy_to_tuple(phys_rect))
        is_valid, err_msg = self.validate_roi_format(phys_rect)
        if not is_valid:
            self.logger.error("get_unified_logical_rect: %s", err_msg)
            return ()

        if not self.is_fullscreen:
            return self.convert_client_physical_rect_to_logical(phys_rect)

        screen_w, screen_h = self._display_context.screen_physical_res
        return self._ensure_rect_in_boundary(phys_rect, screen_w, screen_h)

    # ── Sub-coordinate offset (for cv2.matchTemplate results) ─────
    def apply_roi_offset_to_subcoord(
        self,
        sub_coord: Point | ROI | list[int] | np.ndarray,
        roi_offset_phys: Point,
    ) -> Point | ROI:
        """Add ROI offset back to sub-image coords (recovers full-image coords).

        Args:
            sub_coord: Coords within the cropped sub-image. Either (x, y) or
                (x, y, w, h). PaddleOCR-style 4-point lists are also accepted.
            roi_offset_phys: (offset_x, offset_y) of the ROI's top-left in
                the full image (from process_roi's second return value).

        Returns:
            Coords in the full image (same shape as input).
        """
        # PaddleOCR 4-point format: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        if isinstance(sub_coord, list) and len(sub_coord) == 4 and isinstance(sub_coord[0], list):
            ox, oy = roi_offset_phys
            new_pts: list[list[int]] = []
            for pt in sub_coord:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    new_pts.append([pt[0] + ox, pt[1] + oy])
            if not new_pts:
                return (0, 0, 0, 0)
            xs = [p[0] for p in new_pts]
            ys = [p[1] for p in new_pts]
            x, y = min(xs), min(ys)
            return (x, y, max(xs) - x, max(ys) - y)

        sub_coord = cast(Point | ROI, self._convert_numpy_to_tuple(sub_coord))
        if not sub_coord or len(sub_coord) not in (2, 4):
            self.logger.error("apply_roi_offset_to_subcoord: invalid input %s", sub_coord)
            return sub_coord

        ox, oy = roi_offset_phys
        if len(sub_coord) == 2:
            return (sub_coord[0] + ox, sub_coord[1] + oy)
        return (sub_coord[0] + ox, sub_coord[1] + oy, sub_coord[2], sub_coord[3])

    # ── Sub-image → full-image (semantic alias, N191 §10.10 决策点 3) ─
    def sub_image_to_full(
        self,
        sub_coord: Point | ROI | list[int] | np.ndarray,
        roi_offset_phys: Point,
    ) -> Point | ROI:
        """Convert sub-image local coords → full-image physical coords.

        N191 §10.10 决策点 3 (AI 可调试性, 2026-07-27):
            语义化别名, 行为等同 ``apply_roi_offset_to_subcoord``。强制
            节点用 ``sub_image_to_full`` 名字调用, 让代码意图清晰: 输入
            是 SUB_IMAGE 坐标系, 输出是 PHYSICAL 坐标系。AI 读日志/
            代码时无需靠 roi_offset 隐式回加推断, 直接看到 SUB_IMAGE →
            PHYSICAL 的转换链路。

            节点调用本方法后, 应通过 ``context.emit_coord_trace`` 记录
            trace, step="sub_image_to_full", raw=sub_coord, converted=结果,
            让 AI 调试时能从 JSONL 日志反推偏移是否加对。

        Args:
            sub_coord: Coords within the cropped sub-image (SUB_IMAGE
                coordinate system). Either (x, y) or (x, y, w, h).
            roi_offset_phys: (offset_x, offset_y) of the ROI's top-left in
                the full image (from process_roi's second return value).

        Returns:
            Coords in the full image (PHYSICAL coordinate system).
        """
        return self.apply_roi_offset_to_subcoord(sub_coord, roi_offset_phys)

    # ── Template scaling ──────────────────────────────────────────
    def calculate_template_scale_ratio(
        self,
        target_phys_size: Point,
        has_roi: bool = False,
        roi_logical_size: Point | None = None,
    ) -> float:
        """Compute template image scale ratio (preserves aspect, no stretching).

        Ratio = min(target_w / orig_w, target_h / orig_h). Clamped to ≥0.001.
        Returns 1.0 on invalid input (skips scaling).

        Args:
            target_phys_size: Target physical size (w, h) — typically the
                screenshot dimensions (fullscreen) or client physical size.
            has_roi: If True, use roi_logical_size for ratio computation.
            roi_logical_size: ROI logical size (w, h), required when has_roi=True.

        Returns:
            Scale ratio in [0.001, ∞). 1.0 means no scaling needed.
        """
        target_w, target_h = target_phys_size
        if target_w <= 0 or target_h <= 0:
            self.logger.error("calculate_template_scale_ratio: invalid target %s", target_phys_size)
            return 1.0

        ctx = self._display_context
        orig_w, orig_h = ctx.original_base_res
        if orig_w <= 0 or orig_h <= 0:
            self.logger.error("calculate_template_scale_ratio: invalid base %s", ctx.original_base_res)
            return 1.0

        if has_roi and roi_logical_size is not None:
            rw, rh = roi_logical_size
            if rw <= 0 or rh <= 0:
                return 1.0
            # Match within ROI: scale by ROI's logical-to-base ratio
            ratio = min(rw / orig_w, rh / orig_h)
        else:
            ratio = min(target_w / orig_w, target_h / orig_h)

        return max(0.001, ratio)
