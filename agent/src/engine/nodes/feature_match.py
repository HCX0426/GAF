"""feature_match 节点：SIFT/ORB/KAZE/AKAZE/BRISK 特征点匹配 + RANSAC"""

from __future__ import annotations

import contextlib
import io
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
from engine.resource_resolver import resolve_resource_path
from engine.target import publish_match_pos
from PIL import Image

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)

# Supported feature detectors
DETECTORS = {
    "sift": cv2.SIFT_create,
    "orb": cv2.ORB_create,
    "kaze": cv2.KAZE_create,
    "akaze": cv2.AKAZE_create,
    "brisk": cv2.BRISK_create,
}

# Detectors that produce float descriptors (use L2 norm), others use Hamming
L2_DETECTORS = {"sift", "kaze", "akaze"}


def _build_fail_diagnostics(
    node: FeatureMatchNode,
    context: PipelineContext,
    num_matches: int | None = None,
) -> dict[str, Any]:
    """N192 A2 P2: 构造 feature_match 失败路径诊断字段, 让 AI 不必读 JSONL
    就能从 result_data 拿到失败上下文.

    统一构造 coord_system / method / min_matches / ratio_threshold 字段,
    避免每个 fail_result 调用点重复构造. 可选 num_matches (仅在到达匹配
    阶段时存在).

    Args:
        node: 当前 FeatureMatchNode 实例 (取 self.config 中的 method /
            min_matches / ratio_threshold).
        context: PipelineContext (取 coord_system 标签).
        num_matches: 失败前已匹配的好点数 (仅匹配点数不足路径有效).

    Returns:
        含诊断字段的 dict, 可直接作为 fail_result(data=...) 入参.
    """
    data: dict[str, Any] = {
        "coord_system": getattr(context, "coord_system", "") or "legacy",
        "method": node.config.get("method", "orb"),
        "min_matches": node.config.get("min_matches", 10),
        "ratio_threshold": node.config.get("ratio_threshold", 0.75),
    }
    if num_matches is not None:
        data["num_matches"] = int(num_matches)
    return data


def _load_image(template_config: Any) -> np.ndarray | None:
    """Load template image from path or base64 data into BGR numpy array.

    Args:
        template_config: File path string or base64-encoded image string

    Returns:
        BGR numpy array, or None if loading fails
    """
    if not template_config:
        logger.error("模板路径或数据为空")
        return None

    try:
        if isinstance(template_config, str):
            has_image_ext = any(
                ext in template_config.lower()
                for ext in ['.png', '.jpg', '.jpeg', '.bmp', '.webp']
            )
            if has_image_ext:
                # File path with image extension — resolve against GAF
                # resources root (handles relative paths). Falls back to
                # raw path for absolute paths.
                resolved = resolve_resource_path(template_config)
                if resolved is not None:
                    pil_img = Image.open(resolved).convert('RGB')
                else:
                    pil_img = Image.open(template_config).convert('RGB')
            else:
                # No image extension — try base64 first (base64 strings
                # may contain '/' which is also a path separator, so we
                # can't rely on path-separator detection). Fall back to
                # file path if base64 decode or image parsing fails.
                try:
                    import base64
                    img_bytes = base64.b64decode(template_config, validate=True)
                    pil_img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
                except Exception:
                    resolved = resolve_resource_path(template_config)
                    if resolved is not None:
                        pil_img = Image.open(resolved).convert('RGB')
                    else:
                        pil_img = Image.open(template_config).convert('RGB')
        elif hasattr(template_config, 'read'):
            pil_img = Image.open(template_config).convert('RGB')
        else:
            logger.error("不支持的模板类型: %s", type(template_config))
            return None
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    except Exception as exc:
        logger.error("模板加载失败: %s", exc)
        return None


@register_node("feature_match")
@dataclass
class FeatureMatchNode(PipelineNode):
    """Feature point matching node using SIFT/ORB/KAZE/AKAZE/BRISK.

    Captures screen from device, loads template image, extracts features
    from both, matches with BFMatcher + Lowe's ratio test, and estimates
    homography with RANSAC to locate the template in the screen.

    Config parameters:
    - template: Template image path (str) or base64-encoded image data (str)
    - method: Feature detector "sift"/"orb"/"kaze"/"akaze"/"brisk", default "orb"
    - min_matches: Minimum good match count, default 10
    - ratio_threshold: Lowe's ratio test threshold, default 0.75
    - roi: Search region {"x": int, "y": int, "w": int, "h": int}, optional
    - ransac_threshold: RANSAC reprojection threshold, default 5.0
    - click_on_match: bool, default false. If true, click the matched center
      after a successful match (BD2 chain.click_feature shortcut).
    - roi_coord_type: str, default "base". Coordinate system of `roi` when
      context.coord_transformer is set. "base" = reference resolution
      (e.g. 1920x1080), auto-scaled to current client physical pixels;
      "logical"/"physical" = used as-is. When a transformer is present the
      template is also resized by calculate_template_scale_ratio before
      feature extraction (so base-resolution templates match at any DPI).
      Ignored when no transformer.
    """

    node_type: str = "feature_match"

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
        Feature matching uses ``enable_expand=False`` (same as template_match).

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

    def _scale_template_for_transformer(
        self, template: np.ndarray, screen: np.ndarray, transformer: Any,
    ) -> np.ndarray:
        """Resize template by calculate_template_scale_ratio before matching.

        Port of template_match._match_with_scaling step 3: the template is
        authored at base resolution and must be scaled to the current client
        physical resolution so feature descriptors are comparable.

        Args:
            template: Original BGR template (H, W, C).
            screen: Cropped physical screenshot (used for target size).
            transformer: CoordinateTransformer from PipelineContext.

        Returns:
            Scaled BGR template. On any failure, returns the original
            template unchanged (feature matching will still run, just with
            reduced accuracy at non-base DPIs).
        """
        target_phys_size = (screen.shape[1], screen.shape[0])
        try:
            scale_ratio = transformer.calculate_template_scale_ratio(
                target_phys_size=target_phys_size, has_roi=False,
            )
        except Exception as exc:
            logger.error("calculate_template_scale_ratio failed: %s (using raw template)", exc)
            return template

        h_t, w_t = template.shape[:2]
        scaled_w = max(1, int(round(w_t * scale_ratio)))
        scaled_h = max(1, int(round(h_t * scale_ratio)))
        # Clamp to screen size (detectAndCompute still works but corners must
        # stay within the search region for perspectiveTransform to be useful)
        scaled_w = min(scaled_w, screen.shape[1])
        scaled_h = min(scaled_h, screen.shape[0])
        if scaled_w <= 0 or scaled_h <= 0:
            return template

        if scaled_w == w_t and scaled_h == h_t:
            return template  # no scaling needed

        interpolation = cv2.INTER_LANCZOS4 if scale_ratio < 1.0 else cv2.INTER_CUBIC
        try:
            scaled = cv2.resize(template, (scaled_w, scaled_h), interpolation=interpolation)
            logger.info(
                "模板缩放: %dx%d → %dx%d (ratio=%.4f)",
                w_t, h_t, scaled_w, scaled_h, scale_ratio,
            )
            return scaled
        except cv2.error as exc:
            logger.error("模板缩放异常: %s (using raw template)", exc)
            return template

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute feature point matching with real OpenCV + device screenshot.

        Args:
            context: Pipeline execution context (must have device set)

        Returns:
            AutoResult with data containing {num_matches, method, center, homography}
        """
        start = time.monotonic()
        method = self.config.get("method", "orb")
        min_matches = self.config.get("min_matches", 10)
        ratio_threshold = self.config.get("ratio_threshold", 0.75)
        ransac_threshold = self.config.get("ransac_threshold", 5.0)

        # Validate detector
        detector_factory = DETECTORS.get(method)
        if detector_factory is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"不支持的特征检测方法: {method}，可选: {list(DETECTORS.keys())}",
                data=_build_fail_diagnostics(self, context),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
            )

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
        # 不一致, base→phys 缩放比例会错, feature_match center/box 会偏移。
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
                    "feature_match validate_capture_resolution raised (non-fatal): %s",
                    validate_exc,
                )

        # Step 2: Apply ROI if specified
        # When context.coord_transformer is present, the roi is interpreted
        # per roi_coord_type (base/logical/physical) and scaled to current
        # client physical pixels before cropping; the matched center is later
        # converted back to logical coords for click_on_match /
        # publish_match_pos. The template is also resized by the same scale
        # ratio so base-resolution templates match at any DPI.
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
            logger.info("应用 ROI 搜索区域: offset=(%d, %d)", roi_offset_x, roi_offset_y)

        # Step 3: Load template image (and scale it when a transformer is
        # active so feature descriptors match the current physical resolution)
        template = _load_image(self.config.get("template"))
        if template is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"模板图片加载失败: {self.config.get('template')}",
                data=_build_fail_diagnostics(self, context),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
            )
        if transformer is not None:
            template = self._scale_template_for_transformer(template, screen, transformer)

        # Step 4: Detect features and compute descriptors
        try:
            detector = detector_factory()
            kp_template, desc_template = detector.detectAndCompute(template, None)
            kp_screen, desc_screen = detector.detectAndCompute(screen, None)

            if desc_template is None or desc_screen is None:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg="特征点提取失败：模板或截图无描述子（可能是纯色图像）",
                    data=_build_fail_diagnostics(self, context),
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.NO_MATCH,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            logger.info(
                "特征点提取: template=%d, screen=%d, method=%s",
                len(kp_template), len(kp_screen), method,
            )

            # Step 5: Match descriptors with BFMatcher + Lowe's ratio test
            norm_type = cv2.NORM_L2 if method in L2_DETECTORS else cv2.NORM_HAMMING
            bf = cv2.BFMatcher(norm_type)

            # knnMatch needs at least 2 descriptors in each set
            if len(desc_template) < 2 or len(desc_screen) < 2:
                elapsed = time.monotonic() - start
                fail_data = _build_fail_diagnostics(self, context)
                fail_data["num_matches"] = 0
                fail_data["template_keypoints"] = int(len(desc_template) if desc_template is not None else 0)
                fail_data["screen_keypoints"] = int(len(desc_screen) if desc_screen is not None else 0)
                return fail_result(
                    error_msg=f"特征点数不足（template={len(desc_template)}, screen={len(desc_screen)}），至少需要 2 个",
                    data=fail_data,
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.NO_MATCH,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            matches = bf.knnMatch(desc_template, desc_screen, k=2)

            good_matches = []
            for match_pair in matches:
                if len(match_pair) < 2:
                    continue
                m, n = match_pair[0], match_pair[1]
                if m.distance < ratio_threshold * n.distance:
                    good_matches.append(m)

            logger.info(
                "特征匹配: total=%d, good=%d, ratio=%.2f",
                len(matches), len(good_matches), ratio_threshold,
            )

            if len(good_matches) < min_matches:
                result_data = {
                    "num_matches": len(good_matches),
                    "method": method,
                    "center": {"x": 0, "y": 0},
                    "homography": None,
                    "matched": False,
                }
                context.set_variable(f"{self.id}_feature_result", result_data)
                elapsed = time.monotonic() - start
                # N192 A2 P2: 合并 result_data (含 num_matches) 与诊断字段.
                fail_data = _build_fail_diagnostics(
                    self, context, num_matches=len(good_matches),
                )
                fail_data.update(result_data)
                return fail_result(
                    error_msg=f"匹配点数 {len(good_matches)} 少于最小要求 {min_matches}",
                    data=fail_data,
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.LOW_CONFIDENCE,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            # Step 6: Estimate homography with RANSAC
            src_pts = np.float32(
                [kp_template[m.queryIdx].pt for m in good_matches]
            ).reshape(-1, 1, 2)
            dst_pts = np.float32(
                [kp_screen[m.trainIdx].pt for m in good_matches]
            ).reshape(-1, 1, 2)

            homography, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, ransac_threshold)
            inlier_count = int(mask.sum()) if mask is not None else 0

            logger.info(
                "RANSAC 完成: inliers=%d/%d, threshold=%.1f",
                inlier_count, len(good_matches), ransac_threshold,
            )

            # Step 7: Compute template center in screen coordinates via perspectiveTransform
            # The center is in the cropped sub-image coord system. When a
            # coord_transformer is active, convert sub-image center → physical
            # full-image (apply_roi_offset_to_subcoord) → logical
            # (convert_client_physical_to_logical) for click coords.
            h_t, w_t = template.shape[:2]
            template_corners = np.float32(
                [[0, 0], [w_t, 0], [w_t, h_t], [0, h_t]]
            ).reshape(-1, 1, 2)

            if homography is not None:
                screen_corners = cv2.perspectiveTransform(template_corners, homography)
                center_x_sub = int(screen_corners[:, 0, 0].mean())
                center_y_sub = int(screen_corners[:, 0, 1].mean())
                homography_list = homography.tolist()
            else:
                # Fallback: use average of good match points
                center_x_sub = int(dst_pts[:, 0, 0].mean())
                center_y_sub = int(dst_pts[:, 0, 1].mean())
                homography_list = None

            if transformer is not None:
                # N191 §10.10 决策点 3 (AI 可调试性, 2026-07-27):
                # 用 sub_image_to_full (语义化别名) 替代 apply_roi_offset_to_subcoord,
                # 强制 SUB_IMAGE → PHYSICAL 转换显式化。center + bbox 两次转换
                # 都记 trace, 让 AI 反推 ROI 偏移是否加对 (D4 bug 现场重建)。
                center_sub_in = (center_x_sub, center_y_sub)
                phys_pt = transformer.sub_image_to_full(
                    center_sub_in, roi_offset_phys,
                )
                with contextlib.suppress(Exception):
                    context.emit_coord_trace(
                        node_id=self.id,
                        step="sub_image_to_full",
                        raw=center_sub_in,
                        converted=phys_pt,
                        formula=f"sub_image_to_full(sub={center_sub_in}, roi_offset_phys={roi_offset_phys}) -> phys={phys_pt} (center)",
                        coord_system_in="sub_image",
                        coord_system_out="physical",
                        extra={"roi_offset_phys": list(roi_offset_phys), "target": "center"},
                    )
                logical_pt = transformer.convert_client_physical_to_logical(
                    phys_pt[0], phys_pt[1],
                )
                center_x = int(logical_pt[0])
                center_y = int(logical_pt[1])
                # N191 §10.7 P1-2: 模板 bbox 用 perspectiveTransform 的 4 角点
                # 算 min/max 得到 axis-aligned bbox, 加 ROI offset 转全图坐标。
                if homography is not None:
                    sub_corners = screen_corners[:, 0, :]
                    sub_bbox = (
                        int(sub_corners[:, 0].min()),
                        int(sub_corners[:, 1].min()),
                        int(sub_corners[:, 0].max() - sub_corners[:, 0].min()),
                        int(sub_corners[:, 1].max() - sub_corners[:, 1].min()),
                    )
                    feature_box = list(
                        transformer.sub_image_to_full(
                            sub_bbox, roi_offset_phys,
                        ),
                    )
                    with contextlib.suppress(Exception):
                        context.emit_coord_trace(
                            node_id=self.id,
                            step="sub_image_to_full",
                            raw=sub_bbox,
                            converted=tuple(feature_box),
                            formula=f"sub_image_to_full(sub={sub_bbox}, roi_offset_phys={roi_offset_phys}) -> phys={tuple(feature_box)} (bbox)",
                            coord_system_in="sub_image",
                            coord_system_out="physical",
                            extra={"roi_offset_phys": list(roi_offset_phys), "target": "bbox"},
                        )
                else:
                    feature_box = None
            else:
                center_x = center_x_sub + roi_offset_x
                center_y = center_y_sub + roi_offset_y
                if homography is not None:
                    sub_corners = screen_corners[:, 0, :]
                    feature_box = [
                        int(sub_corners[:, 0].min()) + roi_offset_x,
                        int(sub_corners[:, 1].min()) + roi_offset_y,
                        int(sub_corners[:, 0].max() - sub_corners[:, 0].min()),
                        int(sub_corners[:, 1].max() - sub_corners[:, 1].min()),
                    ]
                else:
                    feature_box = None

            result_data = {
                "num_matches": len(good_matches),
                "inlier_matches": inlier_count,
                "method": method,
                "center": {"x": center_x, "y": center_y},
                "box": feature_box,
                "homography": homography_list,
                "matched": True,
                "template_size": {"w": w_t, "h": h_t},
                "screen_size": {"w": screen.shape[1], "h": screen.shape[0]},
                # N191 §10.5 节点间数据流 (2026-07-27): result_data 标 coord_system。
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            }

            context.set_variable(f"{self.id}_feature_result", result_data)
            # P0-6: publish _last_match_pos for downstream target resolution.
            publish_match_pos(
                context, center_x, center_y,
                source=f"{self.id}:feature_match",
                extra={
                    "num_matches": len(good_matches),
                    "inliers": inlier_count,
                    # N191 §10.7 P1-2: 带 box 字段, 让前端绘制识别框。
                    "box": feature_box,
                },
            )

            # click_on_match: BD2 chain.click_feature(tpl) shortcut.
            # If true, click the matched center on the device.
            click_on_match = self.config.get("click_on_match", False)
            if click_on_match:
                try:
                    device.click(center_x, center_y)
                    result_data["clicked"] = True
                    logger.info(
                        "click_on_match 已点击: (%d, %d)", center_x, center_y,
                    )
                except Exception as click_exc:
                    logger.error("click_on_match 点击失败: %s", click_exc)
                    # Click failure is non-fatal: match itself succeeded.
                    result_data["clicked"] = False
                    result_data["click_error"] = str(click_exc)

            elapsed = time.monotonic() - start
            logger.info(
                "特征匹配成功: good=%d, inliers=%d, center=(%d, %d), 耗时=%.3fs",
                len(good_matches), inlier_count, center_x, center_y, elapsed,
            )
            return success_result(data=result_data, elapsed_time=elapsed)

        except cv2.error as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"OpenCV 特征匹配异常: {exc}",
                data=_build_fail_diagnostics(self, context),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"特征匹配过程异常: {exc}",
                data=_build_fail_diagnostics(self, context),
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
            )
