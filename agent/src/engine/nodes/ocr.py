"""OCR node: text recognition using OCREngineRegistry + BatchOCRDetector.

Integrates with the production OCR pipeline:
  - OCREngineRegistry for multi-engine management and auto-selection
  - BatchOCRDetector for optimized batch inference with dedup/merge
  - Region-based recognition with configurable area cropping

Replaces the previous Mock implementation (returned hardcoded fake data).
"""

from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node
from engine.target import publish_match_pos
from utils.perf_monitor import Timer

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


def _build_fail_diagnostics(
    node: OCRNode,
    context: PipelineContext,
    engine_name: str | None,
) -> dict[str, Any]:
    """N192 A2 P2: 构造 OCR 失败路径诊断字段, 让 AI 不必读 JSONL 就能从
    result_data 拿到失败上下文.

    统一构造 coord_system / region / expected_text / engine 字段, 避免每个
    fail_result 调用点重复构造. 所有 fail_result 都应通过本 helper 构造 data.

    Args:
        node: 当前 OCRNode 实例 (取 self.config 中的 region / expected_text).
        context: PipelineContext (取 coord_system 标签).
        engine_name: OCR 引擎名 (可能为 None / 'unavailable' / 'rapid' / 'paddle').

    Returns:
        含诊断字段的 dict, 可直接作为 fail_result(data=...) 入参.
    """
    return {
        "coord_system": getattr(context, "coord_system", "") or "legacy",
        "region": node.config.get("region"),
        "expected_text": node.config.get("expected_text"),
        "engine": engine_name,
    }


@register_node("ocr")
@dataclass
class OCRNode(PipelineNode):
    """OCR text recognition node with real engine integration.

    Performs text recognition on screen regions using the optimal OCR engine
    selected by OCREngineRegistry. Supports single-image and batch mode via
    BatchOCRDetector for improved performance.

    Config parameters:
      - region: Recognition area {"x": int, "y": int, "w": int, "h": int}
        If omitted, recognizes the full image.
      - expected_text: Expected text to match (optional, for verification)
      - lang: Recognition language, default "ch"
      - engine: OCR engine preference ("rapid"/"paddle"), default "rapid"
      - confidence_min: Minimum confidence threshold, default 0.5
      - mock_text: Fallback text when no engine available (backward compat)
      - click_on_match: bool, default false. If true, click the center of the
        highest-confidence text box after a successful recognition
        (BD2 chain.click_text shortcut).
      - roi_coord_type: str, default "base". Coordinate system of `region`
        when context.coord_transformer is set. "base" = reference resolution
        (e.g. 1920x1080), auto-scaled to current client physical pixels;
        "logical"/"physical" = used as-is. Ignored when no transformer.
    """

    node_type: str = "ocr"

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute OCR recognition using registered engine.

        Pipeline:
          1. Get or create OCREngineRegistry singleton
          2. Acquire screenshot image from context
          3. Crop to region if specified
          4. Run BatchOCRDetector.detect() with best engine
          5. Return results or expected_text match result

        Args:
            context: Pipeline execution context

        Returns:
            AutoResult with data containing:
            - texts: List[str] — recognized text lines
            - confidences: List[float] — per-line confidence scores
            - boxes: List[List[int]] — bounding boxes [x,y,w,h]
            - engine: str — engine name used
            - region: dict — region config used
        """
        start = time.monotonic()

        try:
            # Step 1: Get OCR engine from registry
            engine_name, ocr_func = self._get_ocr_engine(context)
            if ocr_func is None:
                return self._fallback_mock(context, start, engine_name)

            # Step 2: Acquire image (context override → device fallback)
            image = self._get_image(context)
            if image is None:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg='No image available (context empty + device capture failed/unavailable)',
                    data=_build_fail_diagnostics(self, context, engine_name),
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.DEVICE_ERROR,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            # N191 §10.13 继续检查 (2026-07-27): ADB 截图分辨率校验 (与
            # template_match.py 一致)。ADB 截图降级链不同方法可能返回不同
            # 分辨率的截图, 若与 transformer 构造时的 device.get_resolution()
            # 不一致, base→phys 缩放比例会错, OCR boxes 全图坐标会偏移。
            _transformer_for_validate = getattr(context, 'coord_transformer', None)
            if _transformer_for_validate is not None \
                    and hasattr(_transformer_for_validate, "validate_capture_resolution") \
                    and image is not None and hasattr(image, "shape"):
                try:
                    _transformer_for_validate.validate_capture_resolution(
                        (image.shape[1], image.shape[0]),
                    )
                except Exception as validate_exc:
                    logger.debug(
                        "ocr validate_capture_resolution raised (non-fatal): %s",
                        validate_exc,
                    )

            # Step 3: Crop to region if specified
            # When context.coord_transformer is present, the region is
            # interpreted per roi_coord_type (base/logical/physical) and
            # scaled to current client physical pixels before cropping;
            # detected text boxes are later converted back to logical coords
            # for click_on_match / publish_match_pos. Requires the context
            # image to be the full physical screenshot (normal case when a
            # ScreenshotNode precedes this OCR node).
            #
            # N191 schema-unification fix (2026-07-28, BD2 get_email 测试发现):
            # BD2 pipeline 文件统一使用 `roi` 数组 [x,y,w,h] (与 template_match
            # 节点一致), 但 OCR 节点原只读 `region` dict, 导致 ROI 被忽略,
            # OCR 在全图识别 → click_on_match 点击错误位置 (71,20 而非 ROI 中心).
            # 修复: 优先读 `roi` (BD2 canonical), 兼容 `region` (legacy dict).
            region = self.config.get('roi') or self.config.get('region')
            if isinstance(region, (list, tuple)):
                # Normalize [x,y,w,h] list to dict for downstream code
                # (与 template_match._normalize_roi 保持一致).
                if len(region) >= 4:
                    region = {
                        "x": int(region[0]),
                        "y": int(region[1]),
                        "w": int(region[2]),
                        "h": int(region[3]),
                    }
                else:
                    region = None
            transformer = getattr(context, 'coord_transformer', None)
            roi_offset_phys = (0, 0)
            if region and transformer is not None:
                image, roi_offset_phys = self._crop_region_scaled(
                    image, region, transformer,
                )
            elif region:
                image = self._crop_region(image, region)
                # N191 (spec-2026-07-27-execution-path-unification 数据流检查):
                # legacy 路径(无 transformer)也要记录 ROI 原点偏移,否则
                # 下游 publish_match_pos 发布的 box 中心是子图内坐标,
                # click 节点拿这个坐标点击会偏移到错误位置。
                roi_offset_phys = (region.get('x', 0), region.get('y', 0))

            # Step 4: Run detection
            from core.batch_ocr import BatchOCRDetector

            detector = BatchOCRDetector(
                ocr_engine=ocr_func,
                confidence_threshold=self.config.get('confidence_min', 0.5),
            )

            prepared = detector.prepare_batch([image])
            with Timer("pipeline.node.ocr", tags={"node_id": self.id, "node_type": "ocr"}):
                results = detector.detect(prepared, ocr_engine=ocr_func)

            if not results or not results[0]:
                elapsed = time.monotonic() - start
                fail_data = _build_fail_diagnostics(self, context, engine_name)
                fail_data['texts'] = []
                fail_data['confidences'] = []
                fail_data['boxes'] = []
                return fail_result(
                    error_msg='OCR returned no results',
                    data=fail_data,
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.OCR_EMPTY,
                    node_id=self.id,
                    node_type=self.node_type,
                )

            # Step 5: Format output
            ocr_results = results[0]
            texts = [r['text'] for r in ocr_results]
            confidences = [r.get('confidence', 0.0) for r in ocr_results]
            boxes = [r.get('bbox', [0, 0, 0, 0]) for r in ocr_results]

            # N191 §10.13 继续检查 (2026-07-27): boxes 是 OCR 引擎返回的
            # 子图内坐标 (SUB_IMAGE), 与 publish_match_pos 发布的 best_box
            # (全图 PHYSICAL 坐标) 混在同一 result_data 里会让 AI 调试混淆。
            # 统一转成全图坐标: 加 roi_offset_phys (legacy 路径) 或走
            # sub_image_to_full (transformer 路径)。box_coord_system 字段
            # 标注 boxes 现在的坐标系, 与 coord_system (中心点坐标系) 区分。
            boxes_full_image: list[list[int]] = []
            for bx, by, bw, bh in boxes:
                if transformer is not None:
                    full_box = transformer.sub_image_to_full(
                        (bx, by, bw, bh), roi_offset_phys,
                    )
                    boxes_full_image.append(list(full_box))
                else:
                    # legacy: 直接加 roi_offset_phys
                    boxes_full_image.append([
                        bx + roi_offset_phys[0],
                        by + roi_offset_phys[1],
                        bw, bh,
                    ])

            result_data = {
                'text': '\n'.join(texts),
                'texts': texts,
                'confidence': max(confidences) if confidences else 0.0,
                'confidences': confidences,
                'boxes': boxes_full_image,  # 全图坐标 (PHYSICAL on ADB / LOGICAL on Windows+transformer / raw on legacy)
                'boxes_sub_image': boxes,  # 保留原始子图坐标供调试
                'engine': engine_name,
                'region': region,
                # N191 §10.5 节点间数据流 (2026-07-27): result_data 标 coord_system
                # 让 AI 调试时知道 boxes/region 是哪个坐标系 (与 template_match 一致)。
                # Windows + transformer 路径 = logical; ADB / legacy = physical。
                'coord_system': getattr(context, 'coord_system', '') or 'legacy',
                # N191 §10.13: boxes 已转全图坐标, 坐标系同 coord_system。
                # boxes_sub_image 仍是 SUB_IMAGE, 调试用。
                'box_coord_system': getattr(context, 'coord_system', '') or 'legacy',
            }

            context.set_variable(f"{self.id}_ocr_result", result_data)

            # Save debug image when debug_mode is enabled; capture paths for
            # structured_logger correlation (spec 阶段 6.5).
            ocr_screenshot = self._save_debug(
                context, image, texts, confidences, boxes,
                region, engine_name, roi_offset_phys,
            )
            if ocr_screenshot.get("annotated"):
                result_data["screenshot_path"] = ocr_screenshot["annotated"]
            if ocr_screenshot.get("raw"):
                result_data["raw_screenshot_path"] = ocr_screenshot["raw"]

            # P0-6: publish _last_match_pos for downstream target resolution.
            # Use the highest-confidence text box center as the match position.
            # When a coord_transformer is active, the box coords (relative to
            # the cropped sub-image) are converted to physical full-image coords
            # via sub_image_to_full, then to logical coords (for
            # WindowsDevice.click which expects client-logical coords).
            best_center_x: int | None = None
            best_center_y: int | None = None
            best_box: list[int] | None = None
            if boxes and confidences:
                best_idx = max(range(len(confidences)), key=lambda i: confidences[i])
                bx, by, bw, bh = boxes[best_idx]
                if bw > 0 and bh > 0:
                    if transformer is not None:
                        # N191 §10.10 决策点 3 (AI 可调试性, 2026-07-27):
                        # 用 sub_image_to_full (语义化别名) 替代 apply_roi_offset_to_subcoord,
                        # 强制 SUB_IMAGE → PHYSICAL 的转换显式化。AI 调试时 grep
                        # "sub_image_to_full" 即可看到所有子图坐标转全图坐标的位置。
                        # 转换后必记 trace, 让 AI 反推 ROI 偏移是否加对 (D4 bug 现场重建)。
                        sub_coord_in = (bx, by, bw, bh)
                        phys_box = transformer.sub_image_to_full(
                            sub_coord_in, roi_offset_phys,
                        )
                        with contextlib.suppress(Exception):
                            context.emit_coord_trace(
                                node_id=self.id,
                                step="sub_image_to_full",
                                raw=sub_coord_in,
                                converted=phys_box,
                                formula=f"sub_image_to_full(sub={sub_coord_in}, roi_offset_phys={roi_offset_phys}) -> phys={phys_box}",
                                coord_system_in="sub_image",
                                coord_system_out="physical",
                                extra={"box_idx": best_idx, "roi_offset_phys": list(roi_offset_phys)},
                            )
                        # N191 §10.7 P1-2 + P0-6 fix (AI 可调试性, 2026-07-27):
                        # best_box 必须与 publish_match_pos 的坐标系对齐
                        # (Windows + transformer 路径 = LOGICAL)。之前 best_box
                        # 写 phys_box (PHYSICAL), 而 best_center_x/y 写 LOGICAL,
                        # 导致 result_data 里 box 与 publish 的 coord_system="logical"
                        # 标签不一致 — AI 调试时按 coord_system="logical" 解析 box
                        # 会绘制错误位置。现在 best_box 也走 get_unified_logical_rect
                        # 转 LOGICAL, 保证 box/center/coord_system 三者一致。
                        logical_rect = transformer.get_unified_logical_rect(phys_box)
                        if logical_rect:
                            best_box = list(logical_rect)
                            best_center_x = int(logical_rect[0] + logical_rect[2] / 2)
                            best_center_y = int(logical_rect[1] + logical_rect[3] / 2)
                        else:
                            # Fallback: keep physical box + physical center
                            # (may be off if DPI ≠ 1.0). 标记 box_coord_system
                            # 为 physical 让 AI 知道此处未对齐。
                            best_box = list(phys_box)
                            best_center_x = int(phys_box[0] + phys_box[2] / 2)
                            best_center_y = int(phys_box[1] + phys_box[3] / 2)
                    else:
                        # N191: legacy 路径(无 transformer) — box 是子图内坐标,
                        # 加上 roi_offset_phys 转回全图坐标,与 click 节点期望一致。
                        best_center_x = int(bx + bw / 2) + roi_offset_phys[0]
                        best_center_y = int(by + bh / 2) + roi_offset_phys[1]
                        best_box = [
                            bx + roi_offset_phys[0],
                            by + roi_offset_phys[1],
                            bw, bh,
                        ]
                    # N191 §10.7 P1-2 (架构层归一化, 2026-07-27): publish 带
                    # box 字段, 让前端调试可视化 / AI 诊断能绘制识别框, 不仅
                    # 是中心点。box 是 [x, y, w, h] 在当前坐标系下的全图坐标。
                    publish_match_pos(
                        context, best_center_x, best_center_y,
                        source=f"{self.id}:ocr",
                        extra={
                            "text": texts[best_idx] if best_idx < len(texts) else "",
                            "box": best_box,
                        },
                    )

            # click_on_match: BD2 chain.click_text(text) shortcut.
            # If true, click the center of the best text box on the device.
            click_on_match = self.config.get("click_on_match", False)
            if click_on_match and best_center_x is not None and best_center_y is not None:
                device = getattr(context, "device", None)
                if device is not None:
                    try:
                        device.click(best_center_x, best_center_y)
                        result_data["clicked"] = True
                        logger.info(
                            "click_on_match 已点击: (%d, %d)", best_center_x, best_center_y,
                        )
                    except Exception as click_exc:
                        logger.error("click_on_match 点击失败: %s", click_exc)
                        # Click failure is non-fatal: OCR itself succeeded.
                        result_data["clicked"] = False
                        result_data["click_error"] = str(click_exc)
                else:
                    logger.warning("click_on_match=True but context.device is None; skip click")

            # Verify expected_text if provided
            expected = self.config.get('expected_text')
            if expected:
                full_text = result_data['text']
                if expected not in full_text:
                    elapsed = time.monotonic() - start
                    # N192 A2 P2: 合并 result_data (含 texts/boxes/confidences
                    # 等识别产物) 与诊断字段, 让 AI 看到完整失败上下文.
                    fail_data = _build_fail_diagnostics(self, context, engine_name)
                    fail_data.update(result_data)
                    return fail_result(
                        error_msg=f"OCR text '{full_text}' does not contain expected '{expected}'",
                        data=fail_data,
                        elapsed_time=elapsed,
                        error_code=NodeErrorCode.OCR_EMPTY,
                        node_id=self.id,
                        node_type=self.node_type,
                    )

            elapsed = time.monotonic() - start
            logger.info(
                "OCR completed: engine=%s texts=%d confidence=%.2f time=%.3fs",
                engine_name, len(texts), result_data['confidence'], elapsed,
            )
            return success_result(data=result_data, elapsed_time=elapsed)

        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error("OCR execution failed: %s", exc, exc_info=True)
            fail_data = _build_fail_diagnostics(self, context, None)
            fail_data['error'] = str(exc)
            return fail_result(
                error_msg=f'OCR execution error: {exc}',
                data=fail_data,
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
            )

    # ── Debug helpers ──────────────────────────────────────────────────

    def _save_debug(
        self,
        context: PipelineContext,
        image: np.ndarray,
        texts: list[str],
        confidences: list[float],
        boxes: list[list[int]],
        region: dict[str, int] | None,
        engine_name: str,
        roi_offset_phys: tuple[int, int] = (0, 0),
    ) -> dict[str, str | None]:
        """Save an annotated debug image when context.debug_mode is True.

        Returns dict {annotated, raw} (spec 阶段 6.5 — for structured_logger
        screenshot_path + raw_screenshot_path fields), or {None, None} when
        debug_mode is off / save
        failed. Failures are non-fatal.

        Strategy: pull the full physical screenshot from context (not the
        cropped sub-image) so the debug image shows where the ROI was on
        the screen. Text boxes (relative to the cropped sub-image) are
        converted back to full-image physical coords by adding
        ``roi_offset_phys``. When the full screenshot is unavailable,
        falls back to the cropped ``image`` with boxes drawn as-is.

        ``is_success`` is computed from ``expected_text``: if provided,
        success = expected_text found in recognized text; otherwise
        success = at least one text line detected.
        """
        if not getattr(context, "debug_mode", False):
            return {"annotated": None, "raw": None}
        try:
            from utils.debug_image_saver import DebugImageSaver

            # N194 归一化 (2026-07-28): context.debug_dir 已是完整 exec_dir,
            # 不再拼 node_type 子目录. 见 template_match._save_debug 注释.
            debug_dir = getattr(context, "debug_dir", "./debug")
            saver = DebugImageSaver(debug_dir=debug_dir)

            # Try to use the full physical screenshot for context. The
            # local `image` was cropped above, so re-fetch from context.
            full_screen = self._get_image(context)
            if full_screen is not None and full_screen.size > 0:
                screen = full_screen
                # Shift boxes from sub-image coords to full-image coords
                offset_x, offset_y = roi_offset_phys
                adjusted_boxes = [
                    [b[0] + offset_x, b[1] + offset_y, b[2], b[3]]
                    if b and len(b) >= 4 else b
                    for b in boxes
                ]
                # Compute roi_phys for drawing the ROI rect on the full
                # screenshot. When no region was used, leave roi_phys=None.
                roi_phys = None
                if region:
                    rx = int(region.get('x', 0)) + offset_x
                    ry = int(region.get('y', 0)) + offset_y
                    rw = int(region.get('w', 0))
                    rh = int(region.get('h', 0))
                    if rw > 0 and rh > 0:
                        roi_phys = (rx, ry, rw, rh)
            else:
                # Fallback: use the cropped image as-is
                screen = image
                adjusted_boxes = boxes
                roi_phys = None

            # Compute is_success based on expected_text (if configured)
            expected = self.config.get('expected_text')
            if expected:
                full_text = '\n'.join(texts)
                is_success = expected in full_text
            else:
                is_success = len(texts) > 0

            return saver.save_ocr_debug(
                screen=screen,
                node_id=self.id,
                is_success=is_success,
                texts=texts,
                confidences=confidences,
                boxes=adjusted_boxes,
                roi_phys=roi_phys,
                expected_text=expected or "",
                engine_name=engine_name,
            )
        except Exception as exc:
            logger.warning("OCR debug save failed: %s", exc, exc_info=True)
            return {"annotated": None, "raw": None}

    def _get_ocr_engine(self, context):
        """Acquire OCR engine from registry or create fallback.

        Args:
            context: Pipeline context (for caching registry instance)

        Returns:
            Tuple of (engine_name: str, ocr_callable: Callable or None)
        """
        try:
            from recognition.ocr.registry import OCREngineRegistry

            registry_key = '_ocr_registry'
            registry = context.get_variable(registry_key)
            if registry is None:
                registry = OCREngineRegistry()
                context.set_variable(registry_key, registry)

            if not registry.engine_names:
                # Auto-register RapidOCR on first use. The orchestrator's
                # register_ocr_engine() call wires RapidOCR into the
                # orchestrator-scoped registry, but pipeline nodes use a
                # separate context-scoped registry that is not pre-populated.
                # Fall back here so OCR nodes work without explicit context
                # injection (TD-075: orchestrator↔context registry gap).
                try:
                    from recognition.ocr.rapid_engine import RapidOCREngine
                    registry.register(RapidOCREngine(), "rapid")
                    logger.info("OCR node 自动注册 RapidOCR 引擎到 context registry")
                except ImportError:
                    logger.warning("No OCR engines registered and RapidOCR import failed")
                    return None, None
                except Exception as exc:
                    logger.warning("No OCR engines registered; auto-register RapidOCR failed: %s", exc)
                    return None, None

            image = self._get_image(context)
            if image is not None:
                try:
                    best_name = registry.benchmark(image)
                    engine = registry.get_best()
                    return best_name, self._adapt_ocr_engine(engine.recognize)
                except Exception as bench_exc:
                    logger.warning("Benchmark failed, using first engine: %s", bench_exc)
                    first_name = registry.engine_names[0]
                    return first_name, self._adapt_ocr_engine(
                        registry.get_engine(first_name).recognize,
                    )

            first_name = registry.engine_names[0]
            return first_name, self._adapt_ocr_engine(
                registry.get_engine(first_name).recognize,
            )

        except ImportError as imp_err:
            logger.warning("OCREngineRegistry not available: %s", imp_err)
            return 'unavailable', None
        except Exception as exc:
            logger.error("Failed to get OCR engine: %s", exc)
            return None, None

    @staticmethod
    def _adapt_ocr_engine(recognize_fn):
        """Adapt an OCR engine's recognize() to the dict-list contract.

        BaseOCREngine.recognize() returns List[OCRResult] where
        OCRResult.box is (x1, y1, x2, y2). BatchOCRDetector and this node
        expect dicts with "text"/"confidence"/"bbox" keys, where "bbox" is
        [x, y, w, h]. This adapter bridges the gap so:

          - the engine contract stays clean (returns typed OCRResult),
          - the batch/node layer keeps its dict-based contract,
          - coordinate format is converted (x1y1x2y2 -> xywh).

        Introduced for TD-076: RapidOCREngine returned OCRResult objects
        but batch_ocr.py called d.get("confidence"), causing
        AttributeError at runtime.
        """
        def adapted(image: np.ndarray):
            results = recognize_fn(image)
            adapted_list = []
            for r in results:
                # OCRResult.box is (x1, y1, x2, y2); convert to [x, y, w, h].
                x1, y1, x2, y2 = r.box
                adapted_list.append({
                    "text": r.text,
                    "confidence": float(r.confidence),
                    "bbox": [int(x1), int(y1), int(x2 - x1), int(y2 - y1)],
                })
            return adapted_list
        return adapted

    def _get_image(self, context: PipelineContext) -> np.ndarray | None:
        """Extract image array from pipeline context.

        Looks for image in order:
          1. Direct 'image' variable
          2. 'screenshot' variable (from ScreenshotNode)
          3. 'last_frame' variable (from device stream)
          4. Fallback: device.capture_screen() — aligns with template_match /
             feature_match / color_detect nodes which capture on demand.

        The device fallback (step 4) ensures OCR nodes can be the first node
        in a pipeline (no preceding ScreenshotNode/wait). Context variables
        (steps 1-3) act as explicit override (e.g., wait node writes 'image'
        to let downstream OCR reuse the same frame without re-capturing).

        Args:
            context: Pipeline context

        Returns:
            numpy array (H, W, C), or None if not found and device capture
            unavailable / failed.
        """
        for var_name in ('image', 'screenshot', 'last_frame'):
            img = context.get_variable(var_name)
            if img is not None and isinstance(img, np.ndarray):
                return img
        # Fallback: capture from device. Mirrors template_match L782 /
        # feature_match L287 / color_detect L166 strategy. Failures are
        # non-fatal — return None so execute() surfaces a clear error.
        device = getattr(context, 'device', None)
        if device is None:
            return None
        try:
            with Timer("pipeline.node.screenshot", tags={"node_id": self.id, "node_type": "ocr"}):
                screen = device.capture_screen()
        except Exception as exc:
            logger.warning("OCR _get_image device.capture_screen() failed: %s", exc)
            return None
        if screen is not None and isinstance(screen, np.ndarray):
            return screen
        return None

    def _crop_region(self, image: np.ndarray, region: dict[str, int]) -> np.ndarray:
        """Crop image to specified region.

        Args:
            image: Full image array (H, W, C)
            region: Dict with keys x, y, w, h

        Returns:
            Cropped image array
        """
        try:
            x = region.get('x', 0)
            y = region.get('y', 0)
            w = region.get('w', image.shape[1])
            h = region.get('h', image.shape[0])

            x = max(0, min(x, image.shape[1] - 1))
            y = max(0, min(y, image.shape[0] - 1))
            x2 = min(x + w, image.shape[1])
            y2 = min(y + h, image.shape[0])

            return image[y:y2, x:x2]
        except Exception as crop_exc:
            logger.warning("Region crop failed, using full image: %s", crop_exc)
            return image

    def _crop_region_scaled(
        self, image: np.ndarray, region: dict[str, int], transformer: Any,
    ) -> tuple[np.ndarray, tuple[int, int]]:
        """Crop image using coord_transformer to scale region to physical pixels.

        Mirrors template_match._match_with_scaling ROI handling: the region
        (interpreted per ``roi_coord_type`` config) is converted to physical
        pixels via ``transformer.process_roi``, then the image is cropped.
        OCR uses ``enable_expand=True`` (DEFAULT_ROI_EXPAND_PIXEL) to avoid
        clipping text edges at ROI boundaries — the returned ``roi_offset_phys``
        already reflects the expanded origin, so downstream coordinate
        conversion via ``apply_roi_offset_to_subcoord`` stays correct.

        Args:
            image: Full physical screenshot (H, W, C).
            region: Dict with x, y, w, h keys (base/logical/physical coords).
            transformer: CoordinateTransformer from PipelineContext.

        Returns:
            (cropped_image, roi_offset_phys) tuple. On failure, falls back to
            the legacy ``_crop_region`` path with offset (0, 0).
        """
        from utils.coord_transformer import CoordType

        roi_coord_type_str = str(self.config.get('roi_coord_type', 'base')).lower()
        roi_coord_type = {
            'base': CoordType.BASE,
            'logical': CoordType.LOGICAL,
            'physical': CoordType.PHYSICAL,
        }.get(roi_coord_type_str, CoordType.BASE)

        roi_tuple = (
            int(region.get('x', 0)), int(region.get('y', 0)),
            int(region.get('w', 0)), int(region.get('h', 0)),
        )
        try:
            processed_roi_phys, roi_offset_phys = transformer.process_roi(
                roi=roi_tuple,
                boundary_width=image.shape[1],
                boundary_height=image.shape[0],
                enable_expand=True,
                roi_coord_type=roi_coord_type,
            )
        except Exception as exc:
            logger.error("process_roi failed: %s, falling back to _crop_region", exc)
            return self._crop_region(image, region), (0, 0)

        if not processed_roi_phys:
            return image, (0, 0)

        rx, ry, rw, rh = processed_roi_phys
        cropped = image[ry:ry + rh, rx:rx + rw]
        if cropped.size == 0:
            logger.warning("ROI 裁剪后子图为空，使用原图")
            return image, (0, 0)
        logger.info(
            "应用 scaled ROI: phys=(%d,%d,%d,%d), offset=%s",
            rx, ry, rw, rh, roi_offset_phys,
        )
        return cropped, roi_offset_phys

    def _fallback_mock(self, context, start_time, engine_name):
        """Fallback to mock data when no real engine available.

        Maintains backward compatibility with existing pipelines that may
        expect the old mock behavior during development/testing.

        Args:
            context: Pipeline context
            start_time: Monotonic timestamp from execute() start
            engine_name: Engine name (or reason for unavailability)

        Returns:
            AutoResult with mock data
        """
        mock_text = self.config.get('mock_text', '识别文本')
        mock_confidence = 0.92

        result_data = {
            'text': mock_text,
            'texts': [mock_text],
            'confidence': mock_confidence,
            'confidences': [mock_confidence],
            'boxes': [[0, 0, 100, 30]],
            'engine': engine_name or 'mock',
            'region': self.config.get('region'),
        }

        context.set_variable(f"{self.id}_ocr_result", result_data)

        expected = self.config.get('expected_text')
        if expected and expected not in mock_text:
            elapsed = time.monotonic() - start_time
            # N192 A2 P2: mock 路径与真实 OCR 路径错误码一致 (OCR_EMPTY).
            fail_data = _build_fail_diagnostics(self, context, engine_name)
            fail_data.update(result_data)
            return fail_result(
                error_msg=f"Mock OCR text '{mock_text}' does not match expected '{expected}'",
                data=fail_data,
                elapsed_time=elapsed,
                error_code=NodeErrorCode.OCR_EMPTY,
                node_id=self.id,
                node_type=self.node_type,
            )

        elapsed = time.monotonic() - start_time
        logger.warning("Using mock OCR fallback (no engine available)")
        return success_result(data=result_data, elapsed_time=elapsed)
