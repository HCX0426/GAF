"""template_match 节点：OpenCV 模板匹配，返回置信度+坐标"""

from __future__ import annotations

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
from utils.perf_monitor import Timer

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)

# Supported OpenCV template matching methods
MATCH_METHODS = {
    "TM_SQDIFF": cv2.TM_SQDIFF,
    "TM_SQDIFF_NORMED": cv2.TM_SQDIFF_NORMED,
    "TM_CCORR": cv2.TM_CCORR,
    "TM_CCORR_NORMED": cv2.TM_CCORR_NORMED,
    "TM_CCOEFF": cv2.TM_CCOEFF,
    "TM_CCOEFF_NORMED": cv2.TM_CCOEFF_NORMED,
}

# Methods where lower value = better match (need to invert confidence)
SQDIFF_METHODS = {cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED}


def _get_template_config_value(config: dict) -> Any:
    """Task 4.2 (P0-3, 2026-07-28): 归一化读取 template 配置字段.

    canonical 字段名 = `template_id` (snake_case, 与 Editor.tsx 保存字段一致).
    兼容历史字段:
    - `template` (agent nested schema legacy, 无 Id 后缀)
    - `templateId` (canvas schema, camelCase)

    优先级: template_id > template > templateId. 三者都为空返回 None.

    Args:
        config: 节点 config dict.

    Returns:
        模板配置值 (str 路径 / str base64 / None).
    """
    return config.get("template_id") or config.get("template") or config.get("templateId")


def _build_fail_diagnostics(
    node: TemplateMatchNode,
    threshold: float,
    confidence: float = 0.0,
    match_loc: tuple | None = None,
    coord_system: str = "physical",
) -> dict[str, Any]:
    """N192 A2 P2: 构造失败路径诊断字段, 让 AI 不必读 JSONL 就能从 result_data 拿到失败上下文.

    统一构造 threshold / confidence / coord_system / template / roi 字段,
    避免每个 fail_result 调用点重复构造. 可选 match_loc (仅在到达匹配阶段时).

    Args:
        node: 当前 TemplateMatchNode 实例 (取 self.config 中的 template / roi).
        threshold: 本次匹配阈值.
        confidence: 本次匹配置信度, 失败前未到匹配阶段则 0.0.
        match_loc: 匹配坐标 (x, y, w, h) 或 None.
        coord_system: 坐标系标注 ("physical" / "logical").

    Returns:
        含诊断字段的 dict, 可直接作为 fail_result(data=...) 入参.
    """
    data: dict[str, Any] = {
        "threshold": float(threshold),
        "confidence": round(float(confidence), 4),
        "coord_system": coord_system,
        "template": _get_template_config_value(node.config),
        "roi": node.config.get("roi"),
    }
    if match_loc is not None:
        data["match_loc"] = list(match_loc) if isinstance(match_loc, tuple) else match_loc
    return data


@register_node("template_match")
@dataclass
class TemplateMatchNode(PipelineNode):
    """Template matching node using OpenCV

    Captures screen from device, loads template image, runs cv2.matchTemplate,
    and returns confidence + matched coordinates.

    Config parameters:
    - template: Template image path (str) or base64-encoded image data (str).
                Relative paths are resolved against GAF resources root
                (e.g. "BrownDust-II/templates/guild_btn.png"). Extension is
                optional; .png/.jpg/.jpeg/.bmp/.webp are auto-tried.
    - threshold: Matching confidence threshold (0.0~1.0), default 0.8
    - roi: Search region. Accepts dict {"x","y","w","h"} or list [x,y,w,h].
           Optional.
    - method: Matching method, default "TM_CCOEFF_NORMED"
    - scale: Multi-scale matching scales (list of float), optional
    - click_on_match: bool, default false. If true, click the matched center
                      after a successful match (BD2 chain.click_template shortcut).
    """

    node_type: str = "template_match"

    # ── Debug helpers ──────────────────────────────────────────────────

    @staticmethod
    def _get_template_name(template_config: Any) -> str:
        """Get a human-readable name for the template, used in debug output.

        Returns the file path for path-based templates, "base64_data" for
        base64-encoded data, or the type name otherwise.
        """
        if not template_config:
            return ""
        if isinstance(template_config, str):
            # Heuristic: same as _load_template — looks like a path if it has
            # an image extension or a path separator.
            if any(ext in template_config.lower() for ext in ['.png', '.jpg', '.jpeg', '.bmp', '.webp']) \
               or '/' in template_config or '\\' in template_config:
                return template_config
            return "base64_data"
        return type(template_config).__name__

    def _save_debug(
        self,
        context: PipelineContext,
        screen: np.ndarray,
        payload: dict[str, Any],
        threshold: float,
    ) -> dict[str, str | None]:
        """Save an annotated debug image when context.debug_mode is True.

        Returns dict {annotated, raw} (spec 阶段 6.5 — for structured_logger
        screenshot_path + raw_screenshot_path fields), or {None, None} when
        debug_mode is off / save failed. Failures are non-fatal — only a
        warning is logged so the main pipeline flow is never blocked.
        """
        if not getattr(context, "debug_mode", False):
            return {"annotated": None, "raw": None}
        try:
            from utils.debug_image_saver import DebugImageSaver

            # N194 归一化 (2026-07-28): context.debug_dir 已是完整 exec_dir
            # (<root>/<YYYYMMDD_HHMMSS>_<task>_<suffix>/), 不再拼 node_type
            # 子目录. 所有节点的截图统一写 screenshots/{annotated,raw}/,
            # 文件名含节点类型 (match_*/ocr_*/click_*) 即可区分.
            debug_dir = getattr(context, "debug_dir", "./debug")
            saver = DebugImageSaver(debug_dir=debug_dir)
            return saver.save_template_debug(
                screen=screen,
                template_orig=payload.get("template_orig"),
                template_scaled=payload.get("template_scaled"),
                template_name=payload.get("template_name", ""),
                is_success=payload.get("is_success", False),
                confidence=float(payload.get("confidence", 0.0)),
                threshold=threshold,
                scale_ratio=float(payload.get("scale_ratio", 0.0)),
                roi_phys=payload.get("roi_phys"),
                match_bbox_phys=payload.get("match_bbox_phys"),
                screen_size=(screen.shape[1], screen.shape[0]),
                node_id=self.id,
            )
        except Exception as exc:
            logger.warning("template_match debug save failed: %s", exc, exc_info=True)
            return {"annotated": None, "raw": None}

    def _auto_heal_and_retry(
        self,
        context: PipelineContext,
        threshold: float,
        cv_method: int,
        method_name: str,
        original_error: str,
        start: float,
    ) -> AutoResult | None:
        """Debug-mode auto-heal: try all screenshot methods and retry match.

        Per project_rules.md §4.8.2: when debug_mode=True and template_match
        fails due to low confidence, AI must automatically try alternative
        screenshot methods (PrintWindow/GDI/DXGI/WGC) before notifying the
        user. Only if ALL methods fail should the user be notified.

        This method:
        1. Runs utils.screenshot_diagnostic.run_diagnostic() to test each
           capture method against the current template + ROI.
        2. If the best method's confidence ≥ threshold, switches the device's
           screenshot method and re-runs the match.
        3. If all methods fail, returns a fail_result with the full
           diagnostic report attached, so the orchestrator can surface it
           to the user.

        Args:
            context: Pipeline context (must have debug_mode=True).
            threshold: Match confidence threshold.
            cv_method: OpenCV match method constant.
            method_name: OpenCV match method name string.
            original_error: Error message from the original failed match.
            start: Start time (monotonic) for elapsed_time calculation.

        Returns:
            AutoResult if auto-heal succeeded or failed definitively (with
            diagnostic report), or None if auto-heal was not applicable
            (non-debug mode, non-Windows device, missing config) and the
            caller should return its original fail_result.
        """
        # Only attempt auto-heal in debug mode.
        if not getattr(context, "debug_mode", False):
            return None

        device = context.device
        if device is None:
            return None

        # Auto-heal currently only supports WindowsDevice (screenshot_diagnostic
        # iterates WGC/DXGI/GDI/PrintWindow — all Windows-specific).
        device_type_name = type(device).__name__
        if "Windows" not in device_type_name:
            return None

        # Need template path and ROI to run the diagnostic.
        template_config = _get_template_config_value(self.config)
        roi_config = self.config.get("roi")
        if not template_config or not roi_config:
            return None

        # Resolve template path to a string the diagnostic can load.
        template_path_str: str
        if isinstance(template_config, str):
            try:
                resolved = resolve_resource_path(template_config)
                template_path_str = str(resolved) if resolved else template_config
            except Exception:
                template_path_str = template_config
        else:
            # base64-data templates can't be re-loaded by path — skip heal.
            return None

        # Normalize ROI to (x, y, w, h) tuple for the diagnostic.
        roi_dict = self._normalize_roi(roi_config)
        if roi_dict is None or roi_dict.get("w", 0) <= 0 or roi_dict.get("h", 0) <= 0:
            return None
        roi_base = (
            roi_dict["x"], roi_dict["y"],
            roi_dict["w"], roi_dict["h"],
        )

        # Determine base_res from context's display_context.
        base_res = (1920, 1080)
        rdc = getattr(context, "display_context", None)
        if rdc is not None and hasattr(rdc, "original_base_res"):
            base_res = tuple(rdc.original_base_res)

        # Run the diagnostic.
        try:
            from utils.screenshot_diagnostic import run_diagnostic
        except ImportError as exc:
            logger.warning("Auto-heal: screenshot_diagnostic unavailable: %s", exc)
            return None

        try:
            report = run_diagnostic(
                device=device,
                template_path=template_path_str,
                roi_base=roi_base,
                base_res=base_res,
                debug_dir=getattr(context, "debug_dir", None),
            )
        except Exception as exc:
            logger.warning("Auto-heal: diagnostic raised: %s", exc, exc_info=True)
            return None

        best = report.best_method()
        best_conf = best.template_match_confidence if best else 0.0
        best_method_name = best.method if best else "NONE"

        # Case 1: All methods failed or below threshold — surface to user.
        if best is None or not best.template_match_success or best_conf < threshold:
            logger.warning(
                "Auto-heal: all %d methods below threshold %.2f. Best: %s (conf=%.4f)",
                len(report.results), threshold, best_method_name, best_conf,
            )
            # LLM auto-heal (§4.8.2): when all local screenshot methods
            # fail, ask the LLM to diagnose the root cause before
            # surfacing to the user. Non-blocking — LLM failure leaves
            # the original error unchanged.
            llm_diagnosis = self._llm_diagnose_match_failure(
                context=context,
                original_error=original_error,
                diagnostic_report=report.summary_table(),
                template_name=self._get_template_name(template_config),
                confidence=best_conf,
                threshold=threshold,
                roi=roi_config,
            )
            base_error = (
                f"{original_error} | Auto-heal exhausted: tried "
                f"{len(report.results)} methods, best={best_method_name} "
                f"(conf={best_conf:.4f}). User intervention required. "
                f"Diagnostic report:\n{report.summary_table()}"
            )
            if llm_diagnosis is not None:
                # Append LLM diagnosis to error message and attach to
                # result.data so the frontend can display it separately.
                diagnosis_text = llm_diagnosis.get("diagnosis", "")
                fix_text = llm_diagnosis.get("suggested_fix", "")
                if diagnosis_text or fix_text:
                    base_error += (
                        f"\n\nLLM Diagnosis: {diagnosis_text}\n"
                        f"Suggested Fix: {fix_text}"
                    )
                heal_fail_data = _build_fail_diagnostics(
                    self, threshold,
                    confidence=best_conf,
                    coord_system="logical" if getattr(context, "coord_transformer", None) else "physical",
                )
                if llm_diagnosis:
                    heal_fail_data["llm_diagnosis"] = llm_diagnosis
                return fail_result(
                    error_msg=base_error,
                    elapsed_time=time.monotonic() - start,
                    error_code=NodeErrorCode.UNKNOWN,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=heal_fail_data,
                )
            return fail_result(
                error_msg=base_error,
                elapsed_time=time.monotonic() - start,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=_build_fail_diagnostics(
                    self, threshold,
                    confidence=best_conf,
                    coord_system="logical" if getattr(context, "coord_transformer", None) else "physical",
                ),
            )

        # Case 2: Found a working method — switch device and retry.
        logger.info(
            "Auto-heal: switching device to %s (conf=%.4f), retrying match",
            best_method_name, best_conf,
        )
        screenshot_mgr = getattr(device, "_screenshot_mgr", None)
        if screenshot_mgr is not None and hasattr(screenshot_mgr, "set_method"):
            screenshot_mgr.set_method(best_method_name)
        else:
            logger.warning(
                "Auto-heal: device has no set_method-capable screenshot_mgr, "
                "cannot persist method switch",
            )
            return None

        # Re-capture with the new method.
        try:
            new_screen = device.capture_screen()
            if new_screen is None:
                return fail_result(
                    error_msg=(
                        f"{original_error} | Auto-heal: re-capture with "
                        f"{best_method_name} returned None"
                    ),
                    elapsed_time=time.monotonic() - start,
                    error_code=NodeErrorCode.DEVICE_ERROR,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=_build_fail_diagnostics(
                        self, threshold,
                        confidence=best_conf,
                        coord_system="logical" if getattr(context, "coord_transformer", None) else "physical",
                    ),
                )
        except Exception as exc:
            return fail_result(
                error_msg=(
                    f"{original_error} | Auto-heal: re-capture with "
                    f"{best_method_name} failed: {exc}"
                ),
                elapsed_time=time.monotonic() - start,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=_build_fail_diagnostics(
                    self, threshold,
                    confidence=best_conf,
                    coord_system="logical" if getattr(context, "coord_transformer", None) else "physical",
                ),
            )

        # Re-run the match with the new screen. Only the transformer path is
        # supported (legacy raw-pixel path is not worth auto-healing — it's
        # used by old pipelines without DPI awareness).
        transformer = context.coord_transformer
        if transformer is None:
            return None

        roi_coord_type_str = str(self.config.get("roi_coord_type", "base")).lower()
        result_data, center_x, center_y, confidence, debug_payload = self._match_with_scaling(
            new_screen, roi_config, roi_coord_type_str,
            transformer, threshold, cv_method, method_name,
            context=context,
        )
        if result_data is None:
            # Retry still failed — return fail with diagnostic context.
            fail_screenshot = self._save_debug(context, new_screen, debug_payload, threshold)
            heal_data: dict[str, Any] = _build_fail_diagnostics(
                self, threshold,
                confidence=debug_payload.get("confidence", float(confidence)),
                match_loc=debug_payload.get("match_bbox_phys"),
                coord_system="logical",
            )
            heal_data["auto_heal_method"] = best_method_name
            if fail_screenshot.get("annotated"):
                heal_data["screenshot_path"] = fail_screenshot["annotated"]
            if fail_screenshot.get("raw"):
                heal_data["raw_screenshot_path"] = fail_screenshot["raw"]
            return fail_result(
                error_msg=(
                    f"{original_error} | Auto-heal: retry with {best_method_name} "
                    f"still failed: {center_x}"
                ),
                elapsed_time=time.monotonic() - start,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=heal_data,
            )

        # Success — publish result and return.
        debug_payload["auto_heal_method"] = best_method_name
        healed_screenshot = self._save_debug(context, new_screen, debug_payload, threshold)
        if healed_screenshot.get("annotated"):
            result_data["screenshot_path"] = healed_screenshot["annotated"]
        if healed_screenshot.get("raw"):
            result_data["raw_screenshot_path"] = healed_screenshot["raw"]
        context.set_variable(f"{self.id}_match_result", result_data)
        publish_match_pos(
            context, center_x, center_y,
            source=f"{self.id}:template_match(auto-healed:{best_method_name})",
            extra={
                "confidence": result_data["confidence"],
                "auto_heal_method": best_method_name,
            },
        )

        # click_on_match: must mirror the normal-path tail so auto-healed
        # matches also click the target. Without this, auto-heal succeeds
        # but the click is skipped, causing downstream wait nodes to fail.
        click_on_match = self.config.get("click_on_match", False)
        if click_on_match:
            try:
                device.click(center_x, center_y)
                result_data["clicked"] = True
                logger.info(
                    "click_on_match 已点击(auto-heal): (%d, %d)", center_x, center_y,
                )
            except Exception as click_exc:
                logger.error("click_on_match 点击失败(auto-heal): %s", click_exc)
                result_data["clicked"] = False
                result_data["click_error"] = str(click_exc)

        elapsed = time.monotonic() - start
        logger.info(
            "Auto-heal 成功: method=%s, confidence=%.4f, center=(%d, %d), 耗时=%.3fs",
            best_method_name, confidence, center_x, center_y, elapsed,
        )
        return success_result(data=result_data, elapsed_time=elapsed)

    def _llm_diagnose_match_failure(
        self,
        context: PipelineContext,
        original_error: str,
        diagnostic_report: str,
        template_name: str,
        confidence: float,
        threshold: float,
        roi: Any,
    ) -> dict[str, Any] | None:
        """Ask the LLM to diagnose a template_match failure.

        Called after screenshot-method auto-heal exhausts all options
        (§4.8.2). Delegates to ``context.llm_client.diagnose_failure()``
        with a structured error context including the diagnostic report,
        template name, confidence, and threshold.

        Non-blocking: returns ``None`` when:
        - ``context.llm_client`` is not set (no server connection)
        - LLM call fails (network / config missing / empty reply)
        - diagnose_failure returns an error dict

        Args:
            context: Pipeline context (must have debug_mode=True).
            original_error: Error from the original failed match.
            diagnostic_report: Full text diagnostic report from
                screenshot_diagnostic.DiagnosticReport.summary_table().
            template_name: Template path or "base64_data".
            confidence: Best confidence reached across all methods.
            threshold: Required confidence threshold.
            roi: ROI config (dict or list).

        Returns:
            Diagnosis dict on success, ``None`` on any failure.
        """
        llm_client = getattr(context, "llm_client", None)
        if llm_client is None:
            return None

        error_context = {
            "node_type": "template_match",
            "error_msg": original_error,
            "diagnostic_report": diagnostic_report,
            "template_name": template_name,
            "confidence": confidence,
            "threshold": threshold,
            "roi": roi,
        }

        try:
            diagnosis = llm_client.diagnose_failure(error_context)
        except Exception as exc:
            logger.warning(
                "LLM diagnose_failure raised unexpectedly: %s", exc,
            )
            return None

        # diagnose_failure() never raises but may return an error dict
        # when the LLM is unavailable / misconfigured. Skip in that case.
        if diagnosis.get("error") and not diagnosis.get("diagnosis"):
            logger.info(
                "LLM diagnosis skipped (reason=%s)", diagnosis.get("error"),
            )
            return None

        return diagnosis

    # ── Template / ROI helpers ─────────────────────────────────────────

    def _load_template(self, template_config: Any) -> np.ndarray | None:
        """Load template image from path or base64 data into BGR numpy array

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
                # File-like object
                pil_img = Image.open(template_config).convert('RGB')
            else:
                logger.error("不支持的模板类型: %s", type(template_config))
                return None

            # Convert PIL RGB -> OpenCV BGR
            template = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            logger.info("模板加载成功，尺寸: %s", template.shape[:2])
            return template
        except ImportError:
            logger.error("缺少 base64 模块")
            return None
        except Exception as exc:
            logger.error("模板加载失败: %s", exc)
            return None

    def _normalize_roi(self, roi: Any) -> dict[str, int] | None:
        """Normalize ROI from dict or list form to dict {x, y, w, h}.

        Args:
            roi: Either {"x": int, "y": int, "w": int, "h": int} or
                 [x, y, w, h] list/tuple.

        Returns:
            Normalized dict, or None if input is invalid.
        """
        if roi is None:
            return None
        if isinstance(roi, dict):
            return {
                "x": int(roi.get("x", 0)),
                "y": int(roi.get("y", 0)),
                "w": int(roi.get("w", 0)),
                "h": int(roi.get("h", 0)),
            }
        if isinstance(roi, (list, tuple)) and len(roi) >= 4:
            return {
                "x": int(roi[0]),
                "y": int(roi[1]),
                "w": int(roi[2]),
                "h": int(roi[3]),
            }
        logger.error("ROI 格式无效，应为 dict {x,y,w,h} 或 list [x,y,w,h]: %r", roi)
        return None

    def _apply_roi(self, screen: np.ndarray, roi: dict[str, int]) -> np.ndarray:
        """Crop screen to region of interest

        Args:
            screen: Full-screen BGR numpy array
            roi: Region dict with x, y, w, h keys

        Returns:
            Cropped BGR numpy array
        """
        x, y, w, h = roi.get("x", 0), roi.get("y", 0), roi.get("w", 0), roi.get("h", 0)
        h_screen, w_screen = screen.shape[:2]
        # Clamp ROI to screen bounds
        x2 = min(x + w, w_screen)
        y2 = min(y + h, h_screen)
        x = max(0, x)
        y = max(0, y)
        return screen[y:y2, x:x2]

    def _match_with_scaling(
        self,
        screen: np.ndarray,
        roi_config: Any,
        roi_coord_type_str: str,
        transformer,
        threshold: float,
        cv_method: int,
        method_name: str,
        context: PipelineContext | None = None,
    ) -> tuple[dict[str, Any] | None, Any, int, float, dict[str, Any]]:
        """BD2 DPI-aware scaling path — ports BD2-AUTO's find_template flow.

        1. process_roi(roi, boundary, roi_coord_type=BASE) → crop screenshot
        2. calculate_template_scale_ratio(target_phys_size) → scale_ratio
        3. cv2.resize(template, orig_size * scale_ratio)
        4. cv2.matchTemplate(cropped, scaled_template)
        5. apply_roi_offset_to_subcoord(match_bbox_sub, roi_offset_phys) → physical
        6. get_unified_logical_rect(physical) → logical (for click coords)

        Returns:
            (result_data, center_x, center_y, confidence, debug_payload) on
            success. (None, error_msg, 0, confidence, debug_payload) on failure
            — error_msg in the center_x slot so the caller can build
            fail_result(error_msg=str(center_x)). debug_payload is always
            populated for debug visualization (None fields where data was not
            reached).
        """
        from utils.coord_transformer import CoordType

        # Initialize debug payload — populated progressively as we go so any
        # early-return path still has data for the debug visualization.
        template_config = _get_template_config_value(self.config)
        debug_payload: dict[str, Any] = {
            "template_name": self._get_template_name(template_config),
            "template_orig": None,
            "template_scaled": None,
            "scale_ratio": 0.0,
            "roi_phys": None,
            "match_bbox_phys": None,
            "confidence": 0.0,
            "is_success": False,
        }

        # Map string → CoordType enum
        roi_coord_type = {
            "base": CoordType.BASE,
            "logical": CoordType.LOGICAL,
            "physical": CoordType.PHYSICAL,
        }.get(roi_coord_type_str, CoordType.BASE)

        # 1. Process ROI (base→physical) and crop screenshot
        roi_offset_phys = (0, 0)
        search_region = screen
        if roi_config:
            roi_normalized = self._normalize_roi(roi_config)
            if roi_normalized:
                roi_tuple = (
                    roi_normalized["x"], roi_normalized["y"],
                    roi_normalized["w"], roi_normalized["h"],
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
                    logger.error("process_roi failed: %s", exc)
                    return None, f"process_roi 失败: {exc}", 0, 0.0, debug_payload

                if processed_roi_phys:
                    debug_payload["roi_phys"] = tuple(processed_roi_phys)
                    rx, ry, rw, rh = processed_roi_phys
                    search_region = screen[ry:ry + rh, rx:rx + rw]
                    if search_region.size == 0:
                        logger.warning("ROI 裁剪后子图为空，使用原图匹配")
                        search_region = screen
                        roi_offset_phys = (0, 0)
                        debug_payload["roi_phys"] = None

        # 2. Load template
        template = self._load_template(template_config)
        if template is None:
            return None, f"模板图片加载失败: {template_config}", 0, 0.0, debug_payload
        debug_payload["template_orig"] = template

        # 3. Calculate scale ratio and resize template
        # Screenshot is in client-physical pixels, so it IS the target physical
        # size for the scale-ratio calculation (matches BD2-AUTO's
        # display_context.client_physical_res usage).
        target_phys_size = (screen.shape[1], screen.shape[0])
        try:
            scale_ratio = transformer.calculate_template_scale_ratio(
                target_phys_size=target_phys_size, has_roi=False,
            )
        except Exception as exc:
            logger.error("calculate_template_scale_ratio failed: %s", exc)
            return None, f"模板缩放比例计算失败: {exc}", 0, 0.0, debug_payload
        debug_payload["scale_ratio"] = float(scale_ratio)

        h_t, w_t = template.shape[:2]
        scaled_w = max(1, int(round(w_t * scale_ratio)))
        scaled_h = max(1, int(round(h_t * scale_ratio)))
        # Clamp to search region (matchTemplate requires template ≤ search image)
        scaled_w = min(scaled_w, search_region.shape[1] - 2)
        scaled_h = min(scaled_h, search_region.shape[0] - 2)
        if scaled_w <= 0 or scaled_h <= 0:
            return None, f"模板缩放后尺寸无效: ({scaled_w},{scaled_h})", 0, 0.0, debug_payload

        interpolation = cv2.INTER_LANCZOS4 if scale_ratio < 1.0 else cv2.INTER_CUBIC
        try:
            scaled_template = cv2.resize(
                template, (scaled_w, scaled_h), interpolation=interpolation,
            )
        except cv2.error as exc:
            return None, f"模板缩放异常: {exc}", 0, 0.0, debug_payload
        debug_payload["template_scaled"] = scaled_template

        # 4. Match
        if scaled_template.shape[0] > search_region.shape[0] or \
           scaled_template.shape[1] > search_region.shape[1]:
            return None, (
                f"缩放后模板尺寸({scaled_w}x{scaled_h})大于搜索区域"
                f"({search_region.shape[1]}x{search_region.shape[0]})"
            ), 0, 0.0, debug_payload

        try:
            result_map = cv2.matchTemplate(search_region, scaled_template, cv_method)
            _, max_val, _, max_loc = cv2.minMaxLoc(result_map)

            if cv_method in SQDIFF_METHODS:
                _, min_val, _, min_loc = cv2.minMaxLoc(result_map)
                confidence = 1.0 - min_val
                match_loc = min_loc
            else:
                confidence = max_val
                match_loc = max_loc
        except cv2.error as exc:
            return None, f"OpenCV 匹配异常: {exc}", 0, 0.0, debug_payload
        except Exception as exc:
            return None, f"匹配计算异常: {exc}", 0, 0.0, debug_payload

        debug_payload["confidence"] = float(confidence)

        logger.info(
            "匹配完成(scaled): method=%s, confidence=%.4f, threshold=%.2f, "
            "loc=%s, scale_ratio=%.4f, template=%dx%d→%dx%d",
            method_name, confidence, threshold, match_loc,
            scale_ratio, w_t, h_t, scaled_w, scaled_h,
        )

        # 5. Threshold check
        if confidence < threshold:
            return None, (
                f"模板匹配置信度 {confidence:.4f} 低于阈值 {threshold}"
            ), 0, confidence, debug_payload

        # 6. Apply ROI offset → physical coords → logical coords
        # N191 §10.10 决策点 3 (AI 可调试性, 2026-07-27):
        # 用 sub_image_to_full (语义化别名) 替代 apply_roi_offset_to_subcoord,
        # 强制 SUB_IMAGE → PHYSICAL 的转换显式化。转换后必记 trace, 让 AI
        # 反推 ROI 偏移是否加对 (D4 bug 现场重建)。
        match_bbox_sub = (match_loc[0], match_loc[1], scaled_w, scaled_h)
        try:
            match_bbox_phys = transformer.sub_image_to_full(
                sub_coord=match_bbox_sub, roi_offset_phys=roi_offset_phys,
            )
        except Exception as exc:
            logger.error("sub_image_to_full failed: %s", exc)
            return None, f"ROI 偏移应用失败: {exc}", 0, confidence, debug_payload
        # context 可能为 None (内部 _match_with_scaling 方法签名上 context 是可选的);
        # 仅在 context 可用时记 trace, 否则跳过 — 行为与之前一致, 仅增强可观测性。
        try:
            if context is not None and hasattr(context, "emit_coord_trace"):
                context.emit_coord_trace(
                    node_id=self.id,
                    step="sub_image_to_full",
                    raw=match_bbox_sub,
                    converted=match_bbox_phys,
                    formula=f"sub_image_to_full(sub={match_bbox_sub}, roi_offset_phys={roi_offset_phys}) -> phys={match_bbox_phys}",
                    coord_system_in="sub_image",
                    coord_system_out="physical",
                    extra={"roi_offset_phys": list(roi_offset_phys)},
                )
        except Exception:
            pass
        debug_payload["match_bbox_phys"] = tuple(match_bbox_phys)

        # Convert physical → logical for click coords (WindowsDevice.click uses
        # PostMessage WM_LBUTTON* which expects client-logical coords).
        try:
            logical_rect = transformer.get_unified_logical_rect(match_bbox_phys)
        except Exception as exc:
            logger.error("get_unified_logical_rect failed: %s", exc)
            logical_rect = None

        if logical_rect:
            center_x = int(logical_rect[0] + logical_rect[2] / 2)
            center_y = int(logical_rect[1] + logical_rect[3] / 2)
        else:
            # Fallback: use physical center (may be off if DPI ≠ 1.0)
            center_x = int(match_bbox_phys[0] + match_bbox_phys[2] / 2)
            center_y = int(match_bbox_phys[1] + match_bbox_phys[3] / 2)

        result_data = {
            "confidence": round(float(confidence), 4),
            "x": center_x,
            "y": center_y,
            "method": method_name,
            "match_loc": {"x": match_bbox_phys[0], "y": match_bbox_phys[1]},
            "template_size": {
                "w": scaled_w, "h": scaled_h,
                "orig_w": w_t, "orig_h": h_t,
                "scale_ratio": round(scale_ratio, 4),
            },
            "screen_size": {"w": screen.shape[1], "h": screen.shape[0]},
            "coord_system": "logical",
        }
        debug_payload["is_success"] = True
        return result_data, center_x, center_y, confidence, debug_payload

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute template matching with real OpenCV + device screenshot

        Args:
            context: Pipeline execution context (must have device set)

        Returns:
            AutoResult with data containing {confidence, x, y} or error
        """
        start = time.monotonic()
        threshold = self.config.get("threshold", 0.8)
        method_name = self.config.get("method", "TM_CCOEFF_NORMED")

        # Validate device is available
        device = context.device
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="PipelineContext 中未设置设备实例(device=None)，无法执行截图",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=_build_fail_diagnostics(self, threshold, confidence=0.0, coord_system="physical"),
            )

        # Step 1: Capture screen from device
        try:
            with Timer("pipeline.node.screenshot", tags={"node_id": self.id, "node_type": "template_match"}):
                screen = device.capture_screen()
            if screen is None:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg="设备截图返回空结果",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.DEVICE_ERROR,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=_build_fail_diagnostics(self, threshold, confidence=0.0, coord_system="physical"),
                )
        except DeviceError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"设备截图失败: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=_build_fail_diagnostics(self, threshold, confidence=0.0, coord_system="physical"),
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"截图过程异常: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=_build_fail_diagnostics(self, threshold, confidence=0.0, coord_system="physical"),
            )

        logger.info("截图成功，屏幕尺寸: %s", screen.shape[:2])

        # ── Branch on DPI-aware scaling vs legacy raw-pixel path ──
        # When context.coord_transformer is set (orchestrator built it from
        # pipeline_json.metadata.original_base_res), ROIs are interpreted as
        # base-resolution coords (e.g. 1920x1080) and auto-scaled to the
        # current client area; templates are resized by the same ratio before
        # matchTemplate. When None, legacy pipelines get raw-pixel behavior.
        transformer = context.coord_transformer

        # N191 §10.7 P0-2 架构层归一化 (2026-07-27): ADB 路径截图分辨率校验。
        # ADB 截图降级链不同方法 (nemu/scrcpy/droidcast/screencap) 可能返回
        # 不同分辨率的截图, 若与 transformer 构造时的 device.get_resolution()
        # 不一致, base→phys 缩放比例会错。校验失败仅记 warning, 不阻断流程
        # (caller 可继续用 legacy raw-pixel 路径, 或 orchestrator 下次重建)。
        if transformer is not None and hasattr(transformer, "validate_capture_resolution"):
            try:
                transformer.validate_capture_resolution(
                    (screen.shape[1], screen.shape[0]),
                )
            except Exception as validate_exc:
                logger.debug(
                    "validate_capture_resolution raised (non-fatal): %s",
                    validate_exc,
                )
        roi_config = self.config.get("roi")
        # roi_coord_type tags the coordinate system of the ROI value.
        # "base" = reference resolution (e.g. 1920x1080), scaled at runtime.
        # "logical" / "physical" = client-area coords, used as-is for the
        # respective layer. Default "base" — only takes effect when a
        # transformer is present.
        roi_coord_type_str = str(self.config.get("roi_coord_type", "base")).lower()

        cv_method = MATCH_METHODS.get(method_name, cv2.TM_CCOEFF_NORMED)

        if transformer is not None:
            with Timer("pipeline.node.template_match", tags={"node_id": self.id, "node_type": "template_match"}):
                result_data, center_x, center_y, confidence, debug_payload = self._match_with_scaling(
                    screen, roi_config, roi_coord_type_str,
                    transformer, threshold, cv_method, method_name,
                    context=context,
                )
            if result_data is None:
                # Match failed — center_x carries the error message string.
                # Capture screenshot_path so structured_logger can correlate
                # the failure with the debug image (spec 阶段 3.2 + 6.5).
                fail_screenshot = self._save_debug(context, screen, debug_payload, threshold)
                # Auto-heal: in debug mode, try alternative screenshot methods
                # before giving up (project_rules.md §4.8.2). Returns None if
                # auto-heal is not applicable (non-debug / non-Windows).
                healed = self._auto_heal_and_retry(
                    context, threshold, cv_method, method_name,
                    original_error=str(center_x), start=start,
                )
                if healed is not None:
                    return healed
                # N192 A2 P2: 构造诊断字段, 合并 debug_payload 中已经渐进填充的
                # confidence / match_bbox_phys / scale_ratio / roi_phys, 让 AI
                # 不必读 JSONL 就能从 result_data 拿到失败上下文.
                fail_data: dict[str, Any] = _build_fail_diagnostics(
                    self, threshold,
                    confidence=debug_payload.get("confidence", 0.0),
                    match_loc=debug_payload.get("match_bbox_phys"),
                    coord_system="logical",
                )
                if fail_screenshot.get("annotated"):
                    fail_data["screenshot_path"] = fail_screenshot["annotated"]
                if fail_screenshot.get("raw"):
                    fail_data["raw_screenshot_path"] = fail_screenshot["raw"]
                # 附加 debug_payload 中 transformer 路径独有的诊断字段
                fail_data["scale_ratio"] = debug_payload.get("scale_ratio", 0.0)
                fail_data["roi_phys"] = debug_payload.get("roi_phys")
                # 按错误信息归类: 置信度低 → LOW_CONFIDENCE; 模板/ROI 失败 →
                # PARAM_INVALID; 其他 → UNKNOWN
                err_str = str(center_x)
                if "低于阈值" in err_str:
                    err_code = NodeErrorCode.LOW_CONFIDENCE
                elif "加载失败" in err_str or "尺寸" in err_str or "无效" in err_str:
                    err_code = NodeErrorCode.PARAM_INVALID
                elif "process_roi" in err_str or "sub_image_to_full" in err_str or "缩放" in err_str:
                    err_code = NodeErrorCode.UNKNOWN
                else:
                    err_code = NodeErrorCode.NO_MATCH
                return fail_result(
                    error_msg=err_str,
                    elapsed_time=time.monotonic() - start,
                    error_code=err_code,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=fail_data,
                )
        else:
            # ── Legacy raw-pixel path (no transformer) ──
            template_config = _get_template_config_value(self.config)
            debug_payload: dict[str, Any] = {
                "template_name": self._get_template_name(template_config),
                "template_orig": None,
                "template_scaled": None,
                # Legacy path doesn't DPI-scale, so ratio is effectively 1.0
                "scale_ratio": 1.0,
                "roi_phys": None,
                "match_bbox_phys": None,
                "confidence": 0.0,
                "is_success": False,
            }

            roi = self._normalize_roi(roi_config)
            roi_offset_x = 0
            roi_offset_y = 0
            if roi:
                search_region = self._apply_roi(screen, roi)
                roi_offset_x = roi.get("x", 0)
                roi_offset_y = roi.get("y", 0)
                debug_payload["roi_phys"] = (
                    roi.get("x", 0), roi.get("y", 0),
                    roi.get("w", 0), roi.get("h", 0),
                )
                logger.info("应用 ROI 搜索区域: %s", roi)
            else:
                search_region = screen

            template = self._load_template(template_config)
            if template is None:
                self._save_debug(context, screen, debug_payload, threshold)
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"模板图片加载失败: {template_config}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=_build_fail_diagnostics(self, threshold, confidence=0.0, coord_system="physical"),
                )
            debug_payload["template_orig"] = template
            # Legacy path doesn't scale — show the same template as "scaled"
            # so the debug thumbnail is still populated.
            debug_payload["template_scaled"] = template

            try:
                h_t, w_t = template.shape[:2]
                h_s, w_s = search_region.shape[:2]
                if h_t > h_s or w_t > w_s:
                    self._save_debug(context, screen, debug_payload, threshold)
                    elapsed = time.monotonic() - start
                    return fail_result(
                        error_msg=f"模板尺寸({w_t}x{h_t})大于搜索区域({w_s}x{h_s})",
                        elapsed_time=elapsed,
                        error_code=NodeErrorCode.PARAM_INVALID,
                        node_id=self.id,
                        node_type=self.node_type,
                        data=_build_fail_diagnostics(self, threshold, confidence=0.0, coord_system="physical"),
                    )

                result_map = cv2.matchTemplate(search_region, template, cv_method)
                _, max_val, _, max_loc = cv2.minMaxLoc(result_map)

                if cv_method in SQDIFF_METHODS:
                    _, min_val, _, min_loc = cv2.minMaxLoc(result_map)
                    confidence = 1.0 - min_val
                    match_loc = min_loc
                else:
                    confidence = max_val
                    match_loc = max_loc

                logger.info(
                    "匹配完成: method=%s, confidence=%.4f, threshold=%.2f, loc=%s",
                    method_name, confidence, threshold, match_loc,
                )
            except cv2.error as exc:
                self._save_debug(context, screen, debug_payload, threshold)
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"OpenCV 匹配异常: {exc}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.UNKNOWN,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=_build_fail_diagnostics(self, threshold, confidence=debug_payload.get("confidence", 0.0), coord_system="physical"),
                )
            except Exception as exc:
                self._save_debug(context, screen, debug_payload, threshold)
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"匹配计算异常: {exc}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.UNKNOWN,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=_build_fail_diagnostics(self, threshold, confidence=debug_payload.get("confidence", 0.0), coord_system="physical"),
                )

            debug_payload["confidence"] = float(confidence)

            if confidence < threshold:
                self._save_debug(context, screen, debug_payload, threshold)
                # Auto-heal: in debug mode, try alternative screenshot methods
                # before giving up (project_rules.md §4.8.2). Returns None if
                # auto-heal is not applicable (non-debug / non-Windows / no
                # transformer — legacy path doesn't support re-match after
                # method switch because there's no coord_transformer).
                healed = self._auto_heal_and_retry(
                    context, threshold, cv_method, method_name,
                    original_error=f"模板匹配置信度 {confidence:.4f} 低于阈值 {threshold}",
                    start=start,
                )
                if healed is not None:
                    return healed
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"模板匹配置信度 {confidence:.4f} 低于阈值 {threshold}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.LOW_CONFIDENCE,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=_build_fail_diagnostics(
                        self, threshold,
                        confidence=float(confidence),
                        match_loc=(match_loc[0] + roi_offset_x, match_loc[1] + roi_offset_y, w_t, h_t),
                        coord_system="physical",
                    ),
                )

            center_x = int(match_loc[0] + w_t / 2) + roi_offset_x
            center_y = int(match_loc[1] + h_t / 2) + roi_offset_y
            match_bbox_phys = (
                match_loc[0] + roi_offset_x,
                match_loc[1] + roi_offset_y,
                w_t, h_t,
            )
            debug_payload["match_bbox_phys"] = match_bbox_phys
            debug_payload["is_success"] = True

            result_data = {
                "confidence": round(float(confidence), 4),
                "x": center_x,
                "y": center_y,
                "method": method_name,
                "match_loc": {"x": match_loc[0] + roi_offset_x, "y": match_loc[1] + roi_offset_y},
                "template_size": {"w": w_t, "h": h_t},
                "screen_size": {"w": screen.shape[1], "h": screen.shape[0]},
                "coord_system": "physical",
            }

        # Save debug image on success too (visualize the match bbox).
        # Capture the returned paths so structured_logger can correlate the
        # success event with annotated + raw screenshots (spec 阶段 6.5).
        success_screenshot = self._save_debug(context, screen, debug_payload, threshold)
        if success_screenshot.get("annotated"):
            result_data["screenshot_path"] = success_screenshot["annotated"]
        if success_screenshot.get("raw"):
            result_data["raw_screenshot_path"] = success_screenshot["raw"]

        # ── Common tail: publish result, click_on_match, return ──
        context.set_variable(f"{self.id}_match_result", result_data)
        # P0-6: publish _last_match_pos so downstream action nodes can resolve
        # `target` without explicit variable wiring.
        publish_match_pos(
            context, center_x, center_y,
            source=f"{self.id}:template_match",
            extra={"confidence": result_data["confidence"]},
        )

        # click_on_match: BD2 chain.click_template(tpl) shortcut.
        # If true, click the matched center on the device before returning.
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
            "模板匹配成功: confidence=%.4f, center=(%d, %d), 耗时=%.3fs",
            confidence, center_x, center_y, elapsed,
        )
        return success_result(data=result_data, elapsed_time=elapsed)
