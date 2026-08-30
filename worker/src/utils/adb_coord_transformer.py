"""ADB coordinate transformer: base → physical scaling for ADB devices.

N191 §10.7 P0-2 (架构层归一化, 2026-07-27) 新增。

背景:
    Windows 路径用 ``CoordinateTransformer`` 做 base→logical→physical→screen
    四级转换 (依赖 hwnd / DPI / 客户区分辨率)。ADB 设备没有 hwnd 也没有
    DPI-aware 概念, 整个屏幕就是物理屏幕, 但仍需 base→physical 缩放支持
    跨分辨率任务复用 (如 base=1920x1080 任务跑在 1080x1920 ADB)。

设计:
    实现 ``convert_original_to_current_client`` / ``process_roi`` /
    ``apply_roi_offset_to_subcoord`` / ``get_unified_logical_rect`` /
    ``calculate_template_scale_ratio`` / ``convert_client_physical_to_logical``
    等接口 (方法名继承自 Windows CoordinateTransformer 以统一节点代码路径),
    让动作节点 (click/swipe/wheel/multi_*) 和识别节点 (template_match/ocr/
    feature_match/color_detect/roi_resolver) 都能透明调用, 不需 hasattr 分支。

    ADB 语义下:
    - logical ↔ physical 恒等变换 (无 DPI 概念, 截图就是物理像素)
    - base → physical 按 device_phys / base 比例缩放
    - ROI 处理: roi_coord_type=BASE 时按 base 比例缩放, LOGICAL/PHYSICAL 原样

    ``coord_system = "physical"`` 类属性标识当前坐标系, orchestrator 读取
    此值注入 ``PipelineContext.coord_system``, 让 publish_match_pos /
    structured_logger 知道当前流转的是 physical 坐标。

    ``display_context`` 属性返回 self, 暴露 ``client_physical_res`` /
    ``original_base_res`` 等字段供 roi_resolver 等节点读取。

限制 (TD-360 已修复):
    - 旋转: base 与 device 方向不一致时自动 90° 旋转坐标 (横屏↔竖屏)。
      方向检测: width > height = 横屏, height > width = 竖屏, 相等 = 正方形。
    - DPI: ADB 设备无 Windows DPI 概念, 截图就是物理像素, 无需 DPI 转换。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

Point = tuple[int, int]
ROI = tuple[int, int, int, int]  # (x, y, w, h)


class _CoordTypeStub:
    """Stub for CoordType enum values (BASE/LOGICAL/PHYSICAL/SUB_IMAGE).

    ADBCoordinateTransformer doesn't depend on the real CoordType enum
    (which lives in utils.coord_transformer and imports numpy etc.). We
    accept either the real enum or string aliases ("base"/"logical"/"physical"/
    "sub_image") so callers can pass either form.

    N191 §10.10 决策点 3 (2026-07-27): 加 SUB_IMAGE 与 Windows CoordType 对齐。
    """

    BASE = "base"
    LOGICAL = "logical"
    PHYSICAL = "physical"
    SUB_IMAGE = "sub_image"


class ADBCoordinateTransformer:
    """ADB device coordinate transformer: base → physical scaling.

    Provides the same interface as Windows ``CoordinateTransformer`` so
    action nodes (click/swipe/wheel/multi_scroll/etc.) and recognition
    nodes (template_match/ocr/feature_match/color_detect/roi_resolver)
    can call transformer methods uniformly without branching on device
    type or hasattr checks.

    All returned coordinates are in **device physical pixel** space —
    ADB has no DPI concept, so logical ↔ physical are identity transforms,
    and base → physical is a simple axis-aligned scale.

    Attributes:
        coord_system: Always ``"physical"`` — identifies the coordinate
            system of values returned by ``convert_original_to_current_client``.
            Read by orchestrator to populate ``PipelineContext.coord_system``.
        base_res: Reference resolution (e.g. (1920, 1080)) — the resolution
            at which task config x/y coordinates were authored.
        device_physical_res: ADB device physical screen resolution (e.g.
            (1080, 1920)) — the actual screen pixel dimensions.
    """

    coord_system: str = "physical"

    # ROI safe-expand default (mirrors Windows DEFAULT_ROI_EXPAND_PIXEL).
    DEFAULT_ROI_EXPAND_PIXEL: int = 10

    def __init__(
        self,
        base_res: Point,
        device_physical_res: Point,
        logger_obj: logging.Logger | None = None,
    ) -> None:
        """Initialize the ADB transformer.

        Args:
            base_res: Base reference resolution (w, h) — typically from
                ``pipeline_json.metadata.original_base_res``.
            device_physical_res: ADB device physical screen resolution
                (w, h) — typically from ``ADBDevice.get_resolution()``.
            logger_obj: Optional logger; falls back to module logger.
        """
        self._base_res = base_res
        self._device_physical_res = device_physical_res
        self._needs_rotation = self._check_orientation_mismatch()
        self.logger = logger_obj or logger
        self.logger.info(
            "ADBCoordinateTransformer initialized | base=%s | device_physical=%s | needs_rotation=%s",
            base_res, device_physical_res, self._needs_rotation,
        )

    # ── Orientation detection (TD-360) ─────────────────────────────
    @staticmethod
    def _is_landscape(res: Point) -> bool:
        """True if resolution is landscape (width > height)."""
        return res[0] > res[1]

    @staticmethod
    def _is_portrait(res: Point) -> bool:
        """True if resolution is portrait (height > width)."""
        return res[1] > res[0]

    def _check_orientation_mismatch(self) -> bool:
        """Check if base and device orientations differ (need rotation).

        Returns True if one is landscape and the other is portrait
        (orientation mismatch). Square resolutions (w == h) never
        trigger rotation.
        """
        base_landscape = self._is_landscape(self._base_res)
        base_portrait = self._is_portrait(self._base_res)
        dev_landscape = self._is_landscape(self._device_physical_res)
        dev_portrait = self._is_portrait(self._device_physical_res)

        # If either is square, no rotation needed.
        if not base_landscape and not base_portrait:
            return False
        if not dev_landscape and not dev_portrait:
            return False

        # Mismatch: base is landscape and device is portrait, or vice versa.
        return base_landscape != dev_landscape

    def _rotate_point(self, x: int, y: int) -> Point:
        """Rotate a point 90° when base and device orientations differ.

        The rotation direction depends on the orientation change:
        - Base landscape → device portrait: 90° counter-clockwise
        - Base portrait → device landscape: 90° clockwise

        After rotation, coordinates are scaled to device resolution.

        Returns:
            (x, y) rotated and scaled to device physical resolution.
        """
        base_w, base_h = self._base_res
        dev_w, dev_h = self._device_physical_res

        if self._is_landscape(self._base_res) and self._is_portrait(self._device_physical_res):
            # Base landscape → device portrait: 90° counter-clockwise.
            # x_device = y_base * (dev_w / base_h)
            # y_device = (base_w - x_base) * (dev_h / base_w)
            rx = int(round(y * (dev_w / base_h)))
            ry = int(round((base_w - x) * (dev_h / base_w)))
        else:
            # Base portrait → device landscape: 90° clockwise.
            # x_device = (base_h - y_base) * (dev_w / base_h)
            # y_device = x_base * (dev_h / base_w)
            rx = int(round((base_h - y) * (dev_w / base_h)))
            ry = int(round(x * (dev_h / base_w)))

        # Clamp to device boundaries.
        rx = max(0, min(rx, dev_w - 1))
        ry = max(0, min(ry, dev_h - 1))
        return (rx, ry)

    # ── Properties (mimic Windows CoordinateTransformer interface) ──
    @property
    def base_res(self) -> Point:
        return self._base_res

    @property
    def device_physical_res(self) -> Point:
        return self._device_physical_res

    # N191 §10.7 P0-2 架构层归一化 (2026-07-27): 截图分辨率校验接口。
    # ADB 截图降级链 (nemu→scrcpy→droidcast→screencap) 不同方法可能返回
    # 不同分辨率的截图 (nemu 模拟器原生 / scrcpy 设备物理 / screencap
    # 可能被 ROM 缩放)。orchestrator 用 device.get_resolution() 构造
    # transformer, 但若实际截图分辨率与此不符, base→phys 缩放比例会错。
    # 节点截图后调用本方法校验, 不一致时记 warning + 触发 transformer 重建。
    def validate_capture_resolution(self, capture_shape: tuple[int, int]) -> bool:
        """Validate that a captured screenshot matches the transformer's baseline.

        Args:
            capture_shape: (width, height) of the captured screenshot —
                typically ``screen.shape[1], screen.shape[0]``.

        Returns:
            True if the capture matches the transformer's
            ``device_physical_res``. False otherwise (caller should log a
            warning and consider rebuilding the transformer).
        """
        if len(capture_shape) != 2:
            self.logger.error(
                "validate_capture_resolution: invalid shape %s", capture_shape,
            )
            return False
        cap_w, cap_h = capture_shape
        base_w, base_h = self._device_physical_res
        if cap_w == base_w and cap_h == base_h:
            return True
        self.logger.warning(
            "ADB capture resolution mismatch | capture=%dx%d | "
            "transformer_baseline=%dx%d — base→phys scale may be wrong. "
            "Likely cause: screenshot method switched in fallback chain "
            "(nemu→scrcpy→droidcast) and the new method returns a "
            "different resolution. Consider rebuilding transformer.",
            cap_w, cap_h, base_w, base_h,
        )
        return False

    @property
    def original_base_res(self) -> Point:
        """Alias for base_res — matches RuntimeDisplayContext attribute name."""
        return self._base_res

    @property
    def client_physical_res(self) -> Point:
        """ADB device physical resolution (no DPI distinction)."""
        return self._device_physical_res

    @property
    def client_logical_res(self) -> Point:
        """ADB logical == physical (no DPI)."""
        return self._device_physical_res

    @property
    def screen_physical_res(self) -> Point:
        """ADB screen == device physical (no window vs screen distinction)."""
        return self._device_physical_res

    @property
    def logical_to_physical_ratio(self) -> float:
        """ADB logical ↔ physical is identity, ratio = 1.0."""
        return 1.0

    @property
    def is_fullscreen(self) -> bool:
        """ADB always fullscreen (whole device screen)."""
        return True

    @property
    def display_context(self) -> ADBCoordinateTransformer:
        """Return self — ADB transformer doubles as display context.

        Recognition nodes (roi_resolver) read ``transformer.display_context``
        to get ``client_physical_res`` for ROI boundary clamping. Since ADB
        has no separate RuntimeDisplayContext, this transformer exposes the
        needed attributes directly.
        """
        return self

    # ── Point conversions ─────────────────────────────────────────
    def convert_original_to_current_client(self, x: int, y: int) -> Point:
        """Base → device physical (axis-aligned scale or rotated).

        TD-360: When base and device orientations differ, coordinates are
        automatically rotated 90° before scaling. The rotation preserves
        spatial layout across landscape↔portrait transitions.

        Args:
            x, y: BASE coordinate values.

        Returns:
            (x, y) scaled to device physical resolution. Returns input
            unchanged if either resolution is invalid (e.g. (0, 0) from
            a disconnected device).
        """
        orig_w, orig_h = self._base_res
        curr_w, curr_h = self._device_physical_res
        if orig_w <= 0 or orig_h <= 0 or curr_w <= 0 or curr_h <= 0:
            self.logger.error(
                "ADBCoordinateTransformer.convert_original_to_current_client: "
                "invalid resolution | base=%s | device=%s",
                self._base_res, self._device_physical_res,
            )
            return (x, y)

        if self._needs_rotation:
            return self._rotate_point(x, y)

        scale_x = curr_w / orig_w
        scale_y = curr_h / orig_h
        fx = max(0, min(int(round(x * scale_x)), curr_w - 1))
        fy = max(0, min(int(round(y * scale_y)), curr_h - 1))
        return (fx, fy)

    def convert_client_logical_to_physical(self, x: int, y: int) -> Point:
        """Client logical → client physical (ADB: identity, no DPI)."""
        curr_w, curr_h = self._device_physical_res
        return (max(0, min(int(x), curr_w - 1)), max(0, min(int(y), curr_h - 1)))

    def convert_client_physical_to_logical(self, x: int, y: int) -> Point:
        """Client physical → client logical (ADB: identity, no DPI)."""
        curr_w, curr_h = self._device_physical_res
        return (max(0, min(int(x), curr_w - 1)), max(0, min(int(y), curr_h - 1)))

    # ── Rectangle conversions ─────────────────────────────────────
    def convert_original_rect_to_current_client(self, rect: ROI) -> ROI:
        """Base rect → device physical rect (axis-aligned scale or rotated).

        TD-360: When base and device orientations differ, the rect is
        rotated 90° and its width/height are swapped to maintain the
        correct aspect ratio.
        """
        x, y, w, h = rect
        if w <= 0 or h <= 0:
            return rect
        orig_w, orig_h = self._base_res
        curr_w, curr_h = self._device_physical_res
        if orig_w <= 0 or orig_h <= 0 or curr_w <= 0 or curr_h <= 0:
            return rect

        if self._needs_rotation:
            # Rotate the rect's top-left corner and swap w/h.
            nx, ny = self._rotate_point(x, y)
            # w and h are swapped after rotation: base width → device height.
            nw = int(round(h * (curr_w / orig_h)))
            nh = int(round(w * (curr_h / orig_w)))
            nw = max(1, min(nw, curr_w - nx))
            nh = max(1, min(nh, curr_h - ny))
            return (nx, ny, nw, nh)

        scale_x = curr_w / orig_w
        scale_y = curr_h / orig_h
        nx = max(0, int(round(x * scale_x)))
        ny = max(0, int(round(y * scale_y)))
        nw = max(1, int(round(w * scale_x)))
        nh = max(1, int(round(h * scale_y)))
        nw = min(nw, curr_w - nx)
        nh = min(nh, curr_h - ny)
        return (nx, ny, nw, nh)

    def convert_client_physical_rect_to_logical(self, rect: ROI) -> ROI:
        """Client physical rect → logical rect (ADB: identity)."""
        return rect

    # ── ROI format validation ─────────────────────────────────────
    @staticmethod
    def _validate_roi(roi) -> tuple[bool, str | None]:
        """Validate ROI is a 4-tuple/list with x,y ≥ 0 and w,h > 0."""
        if not isinstance(roi, (tuple, list)) or len(roi) != 4:
            return False, f"format error (need 4-tuple/list): type={type(roi)}, value={roi}"
        x, y, w, h = roi
        if x < 0 or y < 0 or w <= 0 or h <= 0:
            return False, f"param error (x,y≥0, w,h>0): {roi}"
        return True, None

    # ── ROI full pipeline ─────────────────────────────────────────
    def process_roi(
        self,
        roi,
        boundary_width: int,
        boundary_height: int,
        enable_expand: bool = False,
        expand_pixel: int | None = None,
        roi_coord_type=_CoordTypeStub.BASE,
    ) -> tuple[ROI | None, Point]:
        """Full ROI pipeline: validate → mode-adapt → clamp → optional expand.

        Mirrors Windows ``CoordinateTransformer.process_roi`` interface but
        ADB has no DPI, so logical ↔ physical are identity. Only BASE mode
        triggers base→device_phys scaling.

        Args:
            roi: Input ROI (x, y, w, h). None means "full image".
            boundary_width: Physical boundary width (typically screenshot width).
            boundary_height: Physical boundary height (typically screenshot height).
            enable_expand: Whether to apply safe-expand (OCR use case).
            expand_pixel: Override expand pixel count (default DEFAULT_ROI_EXPAND_PIXEL).
            roi_coord_type: Coordinate system of `roi` (BASE/LOGICAL/PHYSICAL).
                Accepts CoordType enum or string "base"/"logical"/"physical".

        Returns:
            (physical_roi, roi_offset_phys):
              - physical_roi: (x, y, w, h) in physical pixels within boundary,
                or None if input was None or invalid.
              - roi_offset_phys: (offset_x, offset_y) of the ROI's top-left in
                the full image. Equal to physical_roi[:2] when expand is off.
        """
        if roi is None:
            return None, (0, 0)

        if not isinstance(roi, (tuple, list)):
            self.logger.warning("process_roi: non-tuple/list roi: %s", type(roi))
            return None, (0, 0)

        roi = tuple(roi)
        is_valid, err_msg = self._validate_roi(roi)
        if not is_valid:
            self.logger.warning("process_roi: %s", err_msg)
            return None, (0, 0)

        x, y, w, h = roi
        # Normalize roi_coord_type to string for easy comparison.
        rct = str(getattr(roi_coord_type, "value", roi_coord_type)).lower()

        try:
            if rct == "base":
                # Base → device physical scale.
                rx_phys, ry_phys, rw_phys, rh_phys = (
                    self.convert_original_rect_to_current_client(roi)
                )
            else:
                # LOGICAL / PHYSICAL: ADB identity (no DPI).
                rx_phys, ry_phys, rw_phys, rh_phys = x, y, w, h

            # Boundary clamp.
            rx_phys = max(0, rx_phys)
            ry_phys = max(0, ry_phys)
            rw_phys = min(rw_phys, boundary_width - rx_phys)
            rh_phys = min(rh_phys, boundary_height - ry_phys)
            if rw_phys <= 0 or rh_phys <= 0:
                raise ValueError(
                    f"physical ROI invalid after clamp: "
                    f"({rx_phys},{ry_phys},{rw_phys},{rh_phys})"
                )

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

            return processed, roi_offset_phys

        except Exception as exc:
            self.logger.error(
                "process_roi exception: %s (falling back to full image)",
                exc, exc_info=True,
            )
            return None, (0, 0)

    # ── Generic rect utilities ────────────────────────────────────
    def get_unified_logical_rect(self, phys_rect) -> ROI | tuple[()]:
        """ADB: physical == logical, just validate and clamp to screen."""
        if not isinstance(phys_rect, (tuple, list)) or len(phys_rect) != 4:
            self.logger.error("get_unified_logical_rect: invalid input %s", phys_rect)
            return ()
        x, y, w, h = phys_rect
        if w <= 0 or h <= 0:
            return ()
        screen_w, screen_h = self._device_physical_res
        x = max(0, min(int(x), screen_w - 1))
        y = max(0, min(int(y), screen_h - 1))
        w = max(1, min(int(w), screen_w - x))
        h = max(1, min(int(h), screen_h - y))
        return (x, y, w, h)

    # ── Sub-coordinate offset (for cv2.matchTemplate results) ─────
    def apply_roi_offset_to_subcoord(
        self,
        sub_coord,
        roi_offset_phys: Point,
    ):
        """Add ROI offset back to sub-image coords (recovers full-image coords).

        Mirrors Windows ``CoordinateTransformer.apply_roi_offset_to_subcoord``.
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

        if not isinstance(sub_coord, (tuple, list)):
            return sub_coord
        sub_coord = tuple(sub_coord)
        if len(sub_coord) not in (2, 4):
            self.logger.error(
                "apply_roi_offset_to_subcoord: invalid input %s", sub_coord,
            )
            return sub_coord

        ox, oy = roi_offset_phys
        if len(sub_coord) == 2:
            return (sub_coord[0] + ox, sub_coord[1] + oy)
        return (
            sub_coord[0] + ox, sub_coord[1] + oy,
            sub_coord[2], sub_coord[3],
        )

    # ── Sub-image → full-image (semantic alias, N191 §10.10 决策点 3) ─
    def sub_image_to_full(
        self,
        sub_coord,
        roi_offset_phys: Point,
    ):
        """Convert sub-image local coords → full-image physical coords.

        N191 §10.10 决策点 3 (AI 可调试性, 2026-07-27):
            语义化别名, 行为等同 ``apply_roi_offset_to_subcoord``。强制
            节点用 ``sub_image_to_full`` 名字调用, 让代码意图清晰: 输入
            是 SUB_IMAGE 坐标系, 输出是 PHYSICAL 坐标系。ADB 路径与
            Windows 路径接口对齐, 节点代码无需 hasattr 分支。

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
        """Compute template image scale ratio.

        Ratio = min(device_phys_w / base_w, device_phys_h / base_h).
        ADB has no DPI, so target_phys_size is typically the device
        physical resolution. When has_roi=True, scale by ROI's logical
        size / base (mirrors Windows behavior).

        Args:
            target_phys_size: Target physical size (w, h) — typically the
                screenshot dimensions.
            has_roi: If True, use roi_logical_size for ratio computation.
            roi_logical_size: ROI logical size (w, h), required when has_roi=True.

        Returns:
            Scale ratio in [0.001, ∞). 1.0 means no scaling needed.
        """
        target_w, target_h = target_phys_size
        if target_w <= 0 or target_h <= 0:
            self.logger.error(
                "calculate_template_scale_ratio: invalid target %s", target_phys_size,
            )
            return 1.0

        orig_w, orig_h = self._base_res
        if orig_w <= 0 or orig_h <= 0:
            self.logger.error(
                "calculate_template_scale_ratio: invalid base %s", self._base_res,
            )
            return 1.0

        if has_roi and roi_logical_size is not None:
            rw, rh = roi_logical_size
            if rw <= 0 or rh <= 0:
                return 1.0
            ratio = min(rw / orig_w, rh / orig_h)
        else:
            ratio = min(target_w / orig_w, target_h / orig_h)

        return max(0.001, ratio)
