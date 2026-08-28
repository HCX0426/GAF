"""color_detect 节点：HSV inRange 颜色检测 + 轮廓查找"""

from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
from core.error_codes import NodeErrorCode
from core.exceptions import DeviceError
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node
from engine.target import publish_match_pos

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


def _to_hsv_bounds(value: Any, default: list[int]) -> np.ndarray:
    """Convert config value to numpy HSV bound array.

    Args:
        value: List of 3 ints [h, s, v] from config, or None
        default: Default bound if value is missing/invalid

    Returns:
        np.ndarray of shape (3,) dtype uint8
    """
    if not value or not isinstance(value, (list, tuple)) or len(value) < 3:
        return np.array(default, dtype=np.uint8)
    return np.array(value[:3], dtype=np.uint8)


def _build_fail_diagnostics(
    node: ColorDetectNode,
    context: PipelineContext,
    mask_nonzero_pixels: int | None = None,
) -> dict[str, Any]:
    """N192 A2 P2: 构造 color_detect 失败路径诊断字段, 让 AI 不必读 JSONL
    就能从 result_data 拿到失败上下文.

    统一构造 coord_system / lower / upper / min_area 字段, 避免每个
    fail_result 调用点重复构造. 可选 mask_nonzero_pixels (仅在到达 HSV
    处理阶段时存在, 用于反推颜色阈值是否过严).

    Args:
        node: 当前 ColorDetectNode 实例 (取 self.config 中的 lower / upper /
            min_area).
        context: PipelineContext (取 coord_system 标签).
        mask_nonzero_pixels: HSV mask 非零像素数 (仅 HSV 处理后路径有效).

    Returns:
        含诊断字段的 dict, 可直接作为 fail_result(data=...) 入参.
    """
    data: dict[str, Any] = {
        "coord_system": getattr(context, "coord_system", "") or "legacy",
        "lower": node.config.get("lower"),
        "upper": node.config.get("upper"),
        "min_area": node.config.get("min_area", 10),
    }
    if mask_nonzero_pixels is not None:
        data["mask_nonzero_pixels"] = int(mask_nonzero_pixels)
    return data


@register_node("color_detect")
@dataclass
class ColorDetectNode(PipelineNode):
    """Color detection node using HSV inRange + contour finding.

    Captures screen from device, converts BGR to HSV, applies cv2.inRange
    with configured lower/upper bounds, finds contours, and returns the
    largest contour area + center that exceeds min_area threshold.

    Config parameters:
    - lower: HSV lower bound [h, s, v], default [0, 50, 50]
    - upper: HSV upper bound [h, s, v], default [10, 255, 255]
    - roi: Detection region {"x": int, "y": int, "w": int, "h": int}, optional
    - min_area: Minimum contour area threshold, default 10
    - max_results: Maximum number of contours to return, default 1 (largest)
    - click_on_match: bool, default false. If true, click the largest contour
      center after a successful detection (BD2 chain.click_color shortcut).
    - roi_coord_type: str, default "base". Coordinate system of `roi` when
      context.coord_transformer is set. "base" = reference resolution
      (e.g. 1920x1080), auto-scaled to current client physical pixels;
      "logical"/"physical" = used as-is. Ignored when no transformer.
    """

    node_type: str = "color_detect"

    def _apply_roi(
        self, screen: np.ndarray, roi: dict[str, int]
    ) -> tuple[np.ndarray, int, int]:
        """Crop screen to region of interest.

        Args:
            screen: Full-screen BGR numpy array
            roi: Region dict with x, y, w, h keys

        Returns:
            Tuple of (cropped BGR array, offset_x, offset_y)
        """
        x = max(0, roi.get("x", 0))
        y = max(0, roi.get("y", 0))
        h_screen, w_screen = screen.shape[:2]
        x2 = min(x + roi.get("w", 0), w_screen)
        y2 = min(y + roi.get("h", 0), h_screen)
        return screen[y:y2, x:x2], x, y

    def _apply_roi_scaled(
        self, screen: np.ndarray, roi: dict[str, int], transformer: Any,
    ) -> tuple[np.ndarray, tuple[int, int]]:
        """Crop screen using coord_transformer to scale roi to physical pixels.

        Mirrors template_match._match_with_scaling ROI handling: the roi
        (interpreted per ``roi_coord_type`` config) is converted to physical
        pixels via ``transformer.process_roi``, then the screen is cropped.
        Color detection uses ``enable_expand=False`` (the target is a color
        region, not text that could be clipped at edges).

        Args:
            screen: Full physical screenshot (H, W, C).
            roi: Dict with x, y, w, h keys (base/logical/physical coords).
            transformer: CoordinateTransformer from PipelineContext.

        Returns:
            (cropped_screen, roi_offset_phys) tuple. On failure, falls back
            to the legacy ``_apply_roi`` path with offset (0, 0).
        """
        from utils.coord_transformer import CoordType

        roi_coord_type_str = str(self.config.get('roi_coord_type', 'base')).lower()
        roi_coord_type = {
            'base': CoordType.BASE,
            'logical': CoordType.LOGICAL,
            'physical': CoordType.PHYSICAL,
        }.get(roi_coord_type_str, CoordType.BASE)

        roi_tuple = (
            int(roi.get('x', 0)), int(roi.get('y', 0)),
            int(roi.get('w', 0)), int(roi.get('h', 0)),
        )
        try:
            processed_roi_phys, roi_offset_phys = transformer.process_roi(
                roi=roi_tuple,
                boundary_width=screen.shape[1],
                boundary_height=screen.shape[0],
                enable_expand=False,
                roi_coord_type=roi_coord_type,
            )
        except Exception as exc:
            logger.error("process_roi failed: %s, falling back to _apply_roi", exc)
            cropped, _, _ = self._apply_roi(screen, roi)
            return cropped, (0, 0)

        if not processed_roi_phys:
            return screen, (0, 0)

        rx, ry, rw, rh = processed_roi_phys
        cropped = screen[ry:ry + rh, rx:rx + rw]
        if cropped.size == 0:
            logger.warning("ROI 裁剪后子图为空，使用原图")
            return screen, (0, 0)
        logger.info(
            "应用 scaled ROI: phys=(%d,%d,%d,%d), offset=%s",
            rx, ry, rw, rh, roi_offset_phys,
        )
        return cropped, roi_offset_phys

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute HSV color detection with real OpenCV + device screenshot.

        Args:
            context: Pipeline execution context (must have device set)

        Returns:
            AutoResult with data containing {matched, area, center, count, contours}
        """
        start = time.monotonic()
        min_area = self.config.get("min_area", 10)
        max_results = self.config.get("max_results", 1)

        # Validate device is available
        device = context.device
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="PipelineContext 中未设置设备实例(device=None)，无法执行截图",
                data=_build_fail_diagnostics(self, context),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
            )

        # Step 1: Capture screen from device
        try:
            screen = device.capture_screen()
            if screen is None:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg="设备截图返回空结果",
                    data=_build_fail_diagnostics(self, context),
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.DEVICE_ERROR,
                    node_id=self.id,
                    node_type=self.node_type,
                )
        except DeviceError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"设备截图失败: {exc}",
                data=_build_fail_diagnostics(self, context),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"截图过程异常: {exc}",
                data=_build_fail_diagnostics(self, context),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
            )

        # N191 §10.13 继续检查 (2026-07-27): ADB 截图分辨率校验 (与
        # template_match.py 一致)。ADB 截图降级链不同方法可能返回不同
        # 分辨率的截图, 若与 transformer 构造时的 device.get_resolution()
        # 不一致, base→phys 缩放比例会错, color_detect center/box 会偏移。
        _transformer_for_validate = getattr(context, 'coord_transformer', None)
        if _transformer_for_validate is not None \
                and hasattr(_transformer_for_validate, "validate_capture_resolution") \
                and screen is not None and hasattr(screen, "shape"):
            try:
                _transformer_for_validate.validate_capture_resolution(
                    (screen.shape[1], screen.shape[0]),
                )
            except Exception as validate_exc:
                logger.debug(
                    "color_detect validate_capture_resolution raised (non-fatal): %s",
                    validate_exc,
                )

        # Step 2: Apply ROI if specified
        # When context.coord_transformer is present, the roi is interpreted
        # per roi_coord_type (base/logical/physical) and scaled to current
        # client physical pixels before cropping; contour centers are later
        # converted back to logical coords for click_on_match /
        # publish_match_pos.
        roi = self.config.get("roi")
        transformer = getattr(context, 'coord_transformer', None)
        roi_offset_phys: tuple[int, int] = (0, 0)
        # roi_offset_x/y kept for the legacy (no-transformer) path only.
        roi_offset_x = 0
        roi_offset_y = 0
        if roi and isinstance(roi, dict) and transformer is not None:
            screen, roi_offset_phys = self._apply_roi_scaled(screen, roi, transformer)
        elif roi and isinstance(roi, dict):
            screen, roi_offset_x, roi_offset_y = self._apply_roi(screen, roi)
            logger.info("应用 ROI 检测区域: offset=(%d, %d)", roi_offset_x, roi_offset_y)

        # Step 3: Convert BGR to HSV and apply inRange
        try:
            lower = _to_hsv_bounds(self.config.get("lower"), [0, 50, 50])
            upper = _to_hsv_bounds(self.config.get("upper"), [10, 255, 255])

            hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, lower, upper)

            # Morphological operations to reduce noise
            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            mask_nonzero_pixels = int(cv2.countNonZero(mask))
            logger.info(
                "HSV inRange 完成: lower=%s, upper=%s, mask 非零像素=%d",
                lower.tolist(), upper.tolist(), mask_nonzero_pixels,
            )
        except cv2.error as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"OpenCV HSV 转换异常: {exc}",
                data=_build_fail_diagnostics(self, context),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"HSV 处理异常: {exc}",
                data=_build_fail_diagnostics(self, context),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
            )

        # Step 4: Find contours and filter by area
        try:
            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )

            # Filter by min_area and sort by area descending
            valid_contours = [
                c for c in contours if cv2.contourArea(c) >= min_area
            ]
            valid_contours.sort(key=cv2.contourArea, reverse=True)
            valid_contours = valid_contours[:max_results]

            if not valid_contours:
                result_data = {
                    "matched": False,
                    "area": 0,
                    "count": 0,
                    "center": {"x": 0, "y": 0},
                    "lower": lower.tolist(),
                    "upper": upper.tolist(),
                    "contours": [],
                }
                context.set_variable(f"{self.id}_color_result", result_data)
                elapsed = time.monotonic() - start
                logger.info("颜色检测未匹配到符合条件的轮廓")
                # N192 A2 P2: 合并 result_data 与诊断字段 (含 mask_nonzero_pixels).
                fail_data = _build_fail_diagnostics(
                    self, context, mask_nonzero_pixels=mask_nonzero_pixels,
                )
                fail_data.update(result_data)
                return fail_result(
                    error_msg="颜色检测未匹配到面积 >= min_area 的轮廓",
                    data=fail_data,
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.COLOR_NOT_FOUND,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            # Build result with contour info
            # Contour centers are computed in the cropped sub-image coord
            # system. When a coord_transformer is active, convert sub-image
            # center → physical full-image (apply_roi_offset_to_subcoord) →
            # logical (convert_client_physical_to_logical) for click coords.
            contour_list = []
            largest_area = 0
            largest_center = {"x": 0, "y": 0}
            largest_box: list[int] | None = None
            for contour in valid_contours:
                area = float(cv2.contourArea(contour))
                m = cv2.moments(contour)
                if m["m00"] > 0:
                    cx_sub = int(m["m10"] / m["m00"])
                    cy_sub = int(m["m01"] / m["m00"])
                else:
                    cx_sub, cy_sub = 0, 0
                # N191 §10.7 P1-2: 计算 contour 的 axis-aligned bbox
                # (cv2.boundingRect 返回子图内坐标), 用于 publish 的 box 字段。
                bx_sub, by_sub, bw_sub, bh_sub = cv2.boundingRect(contour)
                if transformer is not None:
                    # N191 §10.10 决策点 3 (AI 可调试性, 2026-07-27):
                    # 用 sub_image_to_full (语义化别名) 替代 apply_roi_offset_to_subcoord,
                    # 强制 SUB_IMAGE → PHYSICAL 转换显式化。每个 contour 的 center
                    # + bbox 两次转换都记 trace, 让 AI 反推 ROI 偏移是否加对。
                    center_sub_in = (cx_sub, cy_sub)
                    phys_pt = transformer.sub_image_to_full(
                        center_sub_in, roi_offset_phys,
                    )
                    with contextlib.suppress(Exception):
                        context.emit_coord_trace(
                            node_id=self.id,
                            step="sub_image_to_full",
                            raw=center_sub_in,
                            converted=phys_pt,
                            formula=f"sub_image_to_full(sub={center_sub_in}, roi_offset_phys={roi_offset_phys}) -> phys={phys_pt} (center, area={area:.1f})",
                            coord_system_in="sub_image",
                            coord_system_out="physical",
                            extra={"roi_offset_phys": list(roi_offset_phys), "target": "center", "area": area},
                        )
                    logical_pt = transformer.convert_client_physical_to_logical(
                        phys_pt[0], phys_pt[1],
                    )
                    cx, cy = int(logical_pt[0]), int(logical_pt[1])
                    box_sub_in = (bx_sub, by_sub, bw_sub, bh_sub)
                    phys_box = transformer.sub_image_to_full(
                        box_sub_in, roi_offset_phys,
                    )
                    with contextlib.suppress(Exception):
                        context.emit_coord_trace(
                            node_id=self.id,
                            step="sub_image_to_full",
                            raw=box_sub_in,
                            converted=phys_box,
                            formula=f"sub_image_to_full(sub={box_sub_in}, roi_offset_phys={roi_offset_phys}) -> phys={phys_box} (bbox)",
                            coord_system_in="sub_image",
                            coord_system_out="physical",
                            extra={"roi_offset_phys": list(roi_offset_phys), "target": "bbox"},
                        )
                    contour_box = list(phys_box)
                else:
                    cx = cx_sub + roi_offset_x
                    cy = cy_sub + roi_offset_y
                    contour_box = [
                        bx_sub + roi_offset_x,
                        by_sub + roi_offset_y,
                        bw_sub, bh_sub,
                    ]
                contour_list.append({
                    "area": round(area, 2),
                    "center": {"x": cx, "y": cy},
                    "box": contour_box,
                })
                if area > largest_area:
                    largest_area = area
                    largest_center = {"x": cx, "y": cy}
                    largest_box = contour_box

            result_data = {
                "matched": True,
                "area": round(largest_area, 2),
                "count": len(valid_contours),
                "center": largest_center,
                "box": largest_box,
                "lower": lower.tolist(),
                "upper": upper.tolist(),
                "contours": contour_list,
                # N191 §10.5 节点间数据流 (2026-07-27): result_data 标 coord_system。
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            }

            context.set_variable(f"{self.id}_color_result", result_data)
            # P0-6: publish _last_match_pos for downstream target resolution.
            if largest_center is not None:
                publish_match_pos(
                    context, largest_center["x"], largest_center["y"],
                    source=f"{self.id}:color_detect",
                    extra={
                        "area": result_data["area"],
                        "count": result_data["count"],
                        # N191 §10.7 P1-2: 带 box 字段, 让前端绘制识别框。
                        "box": largest_box,
                    },
                )

            # click_on_match: BD2 chain.click_color(color, roi) shortcut.
            # If true, click the largest contour center on the device.
            click_on_match = self.config.get("click_on_match", False)
            if click_on_match and largest_center is not None:
                try:
                    device.click(largest_center["x"], largest_center["y"])
                    result_data["clicked"] = True
                    logger.info(
                        "click_on_match 已点击: (%d, %d)",
                        largest_center["x"], largest_center["y"],
                    )
                except Exception as click_exc:
                    logger.error("click_on_match 点击失败: %s", click_exc)
                    # Click failure is non-fatal: detection itself succeeded.
                    result_data["clicked"] = False
                    result_data["click_error"] = str(click_exc)

            elapsed = time.monotonic() - start
            logger.info(
                "颜色检测成功: count=%d, largest_area=%.2f, center=%s, 耗时=%.3fs",
                len(valid_contours), largest_area, largest_center, elapsed,
            )
            return success_result(data=result_data, elapsed_time=elapsed)

        except cv2.error as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"OpenCV 轮廓查找异常: {exc}",
                data=_build_fail_diagnostics(
                    self, context, mask_nonzero_pixels=mask_nonzero_pixels,
                ),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"轮廓处理异常: {exc}",
                data=_build_fail_diagnostics(
                    self, context, mask_nonzero_pixels=mask_nonzero_pixels,
                ),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
            )
