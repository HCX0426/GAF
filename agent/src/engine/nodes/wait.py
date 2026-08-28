"""wait 节点：等待（固定时间/画面稳定/模板出现）"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


class WaitMode(Enum):
    """等待模式"""
    FIXED = "fixed"
    STABLE = "stable"
    TEMPLATE = "template"
    OCR = "ocr"  # wait until expected text appears via OCR
    DISAPPEAR = "disappear"  # wait until template is no longer visible


@register_node(
    "wait",
    display_name="等待",
    category="action",
    description="等待（固定时间/画面稳定/模板出现/OCR 文字出现/模板消失）",
    params_schema={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["fixed", "stable", "template", "ocr", "disappear"],
                "default": "fixed",
                "description": "等待模式",
            },
            "seconds": {"type": "number", "minimum": 0, "default": 1.0, "description": "固定等待秒数（fixed 模式）"},
            "timeout": {"type": "number", "minimum": 0, "default": 10.0, "description": "最大等待时间"},
            "max_wait": {"type": "number", "minimum": 0, "default": 10.0, "description": "最大等待时间（legacy 别名）"},
            "check_interval": {"type": "number", "minimum": 0.1, "default": 0.5, "description": "检查间隔（秒）"},
            "template": {"type": "string", "description": "等待出现/消失的模板路径（template/disappear 模式）"},
            "threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.8, "description": "模板匹配阈值"},
            "method": {"type": "string", "default": "TM_CCOEFF_NORMED", "description": "OpenCV 匹配方法"},
            "text": {"type": "string", "description": "等待出现的文字（ocr 模式）"},
            "roi": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4, "description": "等待区域 [x, y, w, h]"},
            "roi_coord_type": {"type": "string", "enum": ["base", "logical", "physical"], "default": "base", "description": "ROI 坐标类型"},
            "lang": {"type": "string", "default": "ch", "description": "OCR 识别语言"},
            "require_seen_first": {"type": "boolean", "default": False, "description": "disappear 模式是否要求模板先出现再消失"},
            "stable_frames": {"type": "integer", "minimum": 1, "default": 3, "description": "stable 模式稳定帧数"},
            "similarity": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.99, "description": "stable 模式帧相似度阈值"},
        },
    },
)
@dataclass
class WaitNode(PipelineNode):
    """等待节点

    支持五种等待模式：
    - fixed: 固定时间等待
    - stable: 等待画面稳定
    - template: 等待指定模板出现
    - ocr: 等待指定文字通过 OCR 识别出现
    - disappear: 等待指定模板消失（不再匹配）

    config 参数：
    - mode: 等待模式 "fixed" / "stable" / "template" / "ocr" / "disappear"，默认 "fixed"
    - seconds: 固定等待秒数（fixed 模式），默认 1.0
    - max_wait: 最大等待时间（stable/template/ocr/disappear 模式），默认 10.0
    - check_interval: 检查间隔（秒），默认 0.5
    - template: 等待出现/消失的模板（template/disappear 模式）
    - threshold: 模板匹配阈值，默认 0.8
    - text: 等待出现的文字（ocr 模式，必填）
    - roi: 等待区域 [x, y, w, h]（ocr 模式，可选）
    - roi_coord_type: 坐标类型 "base"/"logical"/"physical"（ocr 模式，默认 "base"）
    - lang: OCR 识别语言（ocr 模式，默认 "ch"）
    - require_seen_first: disappear 模式专用，是否要求模板先出现再消失（默认 false）
    """

    node_type: str = "wait"

    def _get_timeout(self) -> float:
        """Task 4.66 (P0-15, 2026-07-28): 归一化读取超时字段.

        canonical 字段名 = `timeout` (与 backend validator + 前端 NodePropertyPanel 一致).
        兼容 legacy `max_wait` (agent 历史字段名, 资源文件仍大量使用).

        优先级: timeout > max_wait > 默认 10.0.
        """
        return self.config.get("timeout", self.config.get("max_wait", 10.0))

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — N192 A1+A2: 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "mode": self.config.get("mode", "fixed"),
            "max_wait": self._get_timeout(),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """执行等待

        Args:
            context: Pipeline 执行上下文

        Returns:
            AutoResult，data 包含等待信息和耗时
        """
        start = time.monotonic()
        mode_str = self.config.get("mode", "fixed")

        try:
            mode = WaitMode(mode_str)
        except ValueError:
            return fail_result(
                error_msg=f"未知等待模式: {mode_str}",
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID, mode=mode_str,
                ),
            )

        if mode == WaitMode.FIXED:
            seconds = self.config.get("seconds", 1.0)
            time.sleep(seconds)
            elapsed = time.monotonic() - start
            result_data = {
                "mode": "fixed",
                "seconds": seconds,
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            }
            sp = self._save_debug(context, "fixed", True, {"seconds": seconds})
            if sp:
                result_data["screenshot_path"] = sp
            return success_result(data=result_data, elapsed_time=elapsed)

        elif mode == WaitMode.STABLE:
            result = self._wait_stable(context, start)
            sp = self._save_debug(
                context, "stable", result.success,
                {"max_wait": self._get_timeout()},
            )
            self._inject_screenshot_path(result, sp)
            return result

        elif mode == WaitMode.TEMPLATE:
            result = self._wait_template(context, start)
            sp = self._save_debug(
                context, "template", result.success,
                {"template": self.config.get("template", "")},
            )
            self._inject_screenshot_path(result, sp)
            return result

        elif mode == WaitMode.OCR:
            result = self._wait_ocr(context, start)
            sp = self._save_debug(
                context, "ocr", result.success,
                {"text": self.config.get("text", "")},
            )
            self._inject_screenshot_path(result, sp)
            return result

        elif mode == WaitMode.DISAPPEAR:
            result = self._wait_disappear(context, start)
            sp = self._save_debug(
                context, "disappear", result.success,
                {"template": self.config.get("template", "")},
            )
            self._inject_screenshot_path(result, sp)
            return result

        return fail_result(
            error_msg="未处理的等待模式",
            error_code=NodeErrorCode.UNKNOWN,
            node_id=self.id,
            node_type=self.node_type,
            data=self._build_fail_diagnostics(
                context, NodeErrorCode.UNKNOWN, mode=mode_str,
            ),
        )

    @staticmethod
    def _inject_screenshot_path(
        result: AutoResult,
        paths: dict[str, str | None],
    ) -> None:
        """Inject screenshot_path + raw_screenshot_path into result.data.

        Used by wait branches so structured_logger can correlate the wait
        event with the debug screenshot (spec 阶段 3.2 + 6.5). No-op when
        paths is empty or result.data is not a dict.
        """
        if not paths:
            return
        if not isinstance(result.data, dict):
            result.data = {}
        if paths.get("annotated"):
            result.data["screenshot_path"] = paths["annotated"]
        if paths.get("raw"):
            result.data["raw_screenshot_path"] = paths["raw"]

    def _save_debug(
        self,
        context: PipelineContext,
        mode: str,
        is_success: bool,
        action_info: dict[str, Any],
    ) -> dict[str, str | None]:
        """Save an annotated debug image when context.debug_mode is True.

        Returns dict {annotated, raw} (spec 阶段 6.5), or {None, None} when
        debug_mode is off / save failed / no device available. wait is an
        action node so raw is always None.
        """
        if not getattr(context, "debug_mode", False):
            return {"annotated": None, "raw": None}
        try:
            from utils.debug_image_saver import DebugImageSaver

            # N194 归一化 (2026-07-28): context.debug_dir 已是完整 exec_dir,
            # 不再拼 "action" 子目录. 见 template_match._save_debug 注释.
            debug_dir = getattr(context, "debug_dir", "./debug")
            saver = DebugImageSaver(debug_dir=debug_dir)
            device = getattr(context, "device", None)
            screen = None
            if device is not None and hasattr(device, "capture_screen"):
                try:
                    screen = device.capture_screen()
                except Exception as exc:
                    logger.debug("wait(%s) debug capture error: %s", mode, exc)
            if screen is None or screen.size == 0:
                return {"annotated": None, "raw": None}
            return saver.save_action_debug(
                screen=screen,
                node_id=self.id,
                node_type="wait",
                is_success=is_success,
                action_info={"mode": mode, **action_info},
            )
        except Exception as exc:
            logger.warning("wait debug save failed: %s", exc, exc_info=True)
            return {"annotated": None, "raw": None}

    def _wait_stable(self, context: PipelineContext, start: float) -> AutoResult:
        """Wait until screen content stabilizes by comparing consecutive frames.

        Reuses core.wait_freezes.WaitFreezes (same strategy as WaitFreezesNode).
        """
        max_wait = self._get_timeout()
        check_interval = self.config.get("check_interval", 0.5)
        stable_frames = self.config.get("stable_frames", 3)
        similarity = self.config.get("similarity", 0.99)

        device = getattr(context, "device", None)
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="wait(stable): no device in context",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_DISCONNECTED, mode="stable",
                ),
            )

        try:
            from core.wait_freezes import WaitFreezes
        except ImportError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"wait(stable): WaitFreezes module unavailable: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN, mode="stable",
                    import_error=str(exc),
                ),
            )

        wf = WaitFreezes(
            interval_ms=check_interval * 1000.0,
            stable_frames=stable_frames,
            default_similarity=similarity,
        )

        def _capture():
            try:
                return device.capture_screen()
            except Exception as exc:
                logger.debug("wait(stable) capture error: %s", exc)
                return None

        stable = wf.wait(_capture, timeout=max_wait)
        elapsed = time.monotonic() - start

        if stable:
            logger.info("wait(stable): screen stable after %.2fs", elapsed)
            return success_result(
                data={
                    "mode": "stable",
                    "stable_after": elapsed,
                    "max_wait": max_wait,
                    "check_interval": check_interval,
                    "coord_system": getattr(context, "coord_system", "") or "legacy",
                },
                elapsed_time=elapsed,
            )
        return fail_result(
            error_msg=f"wait(stable): screen did not stabilize within {max_wait}s",
            elapsed_time=elapsed,
            error_code=NodeErrorCode.TIMEOUT,
            node_id=self.id,
            node_type=self.node_type,
            data=self._build_fail_diagnostics(
                context, NodeErrorCode.TIMEOUT, mode="stable",
                stable_frames=stable_frames, similarity=similarity,
            ),
        )

    def _wait_template(self, context: PipelineContext, start: float) -> AutoResult:
        """Wait until a template image appears on screen.

        Reuses engine.nodes.template_match.TemplateMatchNode in a retry loop.
        """
        max_wait = self._get_timeout()
        check_interval = self.config.get("check_interval", 0.5)
        threshold = self.config.get("threshold", 0.8)
        template = self.config.get("template")

        device = getattr(context, "device", None)
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="wait(template): no device in context",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_DISCONNECTED, mode="template",
                ),
            )

        if not template:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="wait(template): 'template' config is required",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID, mode="template",
                ),
            )

        try:
            from engine.nodes.template_match import TemplateMatchNode
        except ImportError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"wait(template): TemplateMatchNode unavailable: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN, mode="template",
                    import_error=str(exc),
                ),
            )

        tm_node = TemplateMatchNode(
            id=f"{self.id}_tm",
            node_type="template_match",
            config={
                "template": template,
                "threshold": threshold,
                "method": self.config.get("method", "TM_CCOEFF_NORMED"),
                "roi": self.config.get("roi"),
                # N191 §10.7 P0-4 (架构层归一化修复, 2026-07-27):
                # 转发 roi_coord_type 让 TemplateMatchNode 走正确的 ROI 缩放
                # 路径 (base/logical/physical)。原代码漏转导致 wait(template)
                # 在 Windows + transformer 下 ROI 坐标系混乱 (BASE 配置被当
                # PHYSICAL 处理)。
                "roi_coord_type": self.config.get("roi_coord_type", "base"),
            },
        )

        deadline = start + max_wait
        last_error = ""
        while time.monotonic() < deadline:
            match_result = tm_node.execute(context)
            if match_result.success and match_result.data:
                elapsed = time.monotonic() - start
                logger.info(
                    "wait(template): matched after %.2fs (confidence=%.4f)",
                    elapsed,
                    match_result.data.get("confidence", 0.0),
                )
                return success_result(
                    data={
                        "mode": "template",
                        "found_after": elapsed,
                        "max_wait": max_wait,
                        "confidence": match_result.data.get("confidence", 0.0),
                        "location": {
                            "x": match_result.data.get("x", 0),
                            "y": match_result.data.get("y", 0),
                        },
                        "coord_system": getattr(context, "coord_system", "") or "legacy",
                    },
                    elapsed_time=elapsed,
                )
            last_error = match_result.error_msg
            time.sleep(check_interval)

        elapsed = time.monotonic() - start
        return fail_result(
            error_msg=f"wait(template): template not found within {max_wait}s (last: {last_error})",
            elapsed_time=elapsed,
            error_code=NodeErrorCode.TARGET_NOT_FOUND,
            node_id=self.id,
            node_type=self.node_type,
            data=self._build_fail_diagnostics(
                context, NodeErrorCode.TARGET_NOT_FOUND, mode="template",
                threshold=threshold, last_error=last_error,
            ),
        )

    def _wait_ocr(self, context: PipelineContext, start: float) -> AutoResult:
        """Wait until expected text appears on screen via OCR.

        Captures a fresh screenshot each ``check_interval``, runs OCR via the
        existing OCRNode, and checks whether ``text`` is found. Reuses OCRNode
        so coordinate transformation, ROI handling, and engine selection stay
        consistent with the standalone OCR node.

        Config used:
        - text: expected text to wait for (required)
        - max_wait: max wait seconds, default 10.0
        - check_interval: check interval seconds, default 0.5
        - roi: optional [x, y, w, h] (base/logical/physical per roi_coord_type)
        - roi_coord_type: "base"/"logical"/"physical", default "base"
        - lang: OCR language, default "ch"
        """
        max_wait = self._get_timeout()
        check_interval = self.config.get("check_interval", 0.5)
        text = self.config.get("text")

        device = getattr(context, "device", None)
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="wait(ocr): no device in context",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_DISCONNECTED, mode="ocr",
                ),
            )

        if not text:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="wait(ocr): 'text' config is required",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID, mode="ocr",
                ),
            )

        try:
            from engine.nodes.ocr import OCRNode
        except ImportError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"wait(ocr): OCRNode unavailable: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN, mode="ocr",
                    import_error=str(exc),
                ),
            )

        # Build OCR config — accept both 'region' (dict) and 'roi' (array)
        # formats so pipelines can use whichever is more convenient.
        ocr_config: dict[str, Any] = {"expected_text": text}
        region = self.config.get("region")
        roi = self.config.get("roi")
        if region:
            ocr_config["region"] = region
        elif roi and isinstance(roi, (list, tuple)) and len(roi) >= 4:
            ocr_config["region"] = {
                "x": int(roi[0]), "y": int(roi[1]),
                "w": int(roi[2]), "h": int(roi[3]),
            }
        if self.config.get("roi_coord_type"):
            ocr_config["roi_coord_type"] = self.config["roi_coord_type"]
        if self.config.get("lang"):
            ocr_config["lang"] = self.config["lang"]

        ocr_node = OCRNode(
            id=f"{self.id}_ocr",
            node_type="ocr",
            config=ocr_config,
        )

        deadline = start + max_wait
        last_error = ""
        while time.monotonic() < deadline:
            # Capture fresh screenshot so OCR sees current screen state.
            try:
                image = device.capture_screen()
            except Exception as exc:
                logger.debug("wait(ocr) capture error: %s", exc)
                last_error = str(exc)
                time.sleep(check_interval)
                continue

            if image is None:
                last_error = "capture returned None"
                time.sleep(check_interval)
                continue

            # OCRNode reads 'image' from context (checked in _get_image).
            context.set_variable("image", image)

            ocr_result = ocr_node.execute(context)
            if ocr_result.success:
                elapsed = time.monotonic() - start
                logger.info(
                    "wait(ocr): text '%s' found after %.2fs",
                    text, elapsed,
                )
                return success_result(
                    data={
                        "mode": "ocr",
                        "text": text,
                        "found_after": elapsed,
                        "max_wait": max_wait,
                        "ocr_result": ocr_result.data,
                        "coord_system": getattr(context, "coord_system", "") or "legacy",
                    },
                    elapsed_time=elapsed,
                )
            last_error = ocr_result.error_msg or ""
            time.sleep(check_interval)

        elapsed = time.monotonic() - start
        return fail_result(
            error_msg=f"wait(ocr): text '{text}' not found within {max_wait}s (last: {last_error})",
            elapsed_time=elapsed,
            error_code=NodeErrorCode.TARGET_NOT_FOUND,
            node_id=self.id,
            node_type=self.node_type,
            data=self._build_fail_diagnostics(
                context, NodeErrorCode.TARGET_NOT_FOUND, mode="ocr",
                text=text, last_error=last_error,
            ),
        )

    def _wait_disappear(self, context: PipelineContext, start: float) -> AutoResult:
        """Wait until a template image is no longer visible on screen.

        Mirrors ``_wait_template`` but inverts the success condition: each
        poll runs TemplateMatchNode; success = template NOT found.

        Two semantics controlled by ``require_seen_first``:
        - require_seen_first=False (default): return success as soon as the
          template is not found. Useful when the caller knows the template
          is currently visible and just wants to wait for it to go away.
        - require_seen_first=True: first wait for the template to appear at
          least once, then wait for it to disappear. Useful for loading
          spinners that may take a moment to render before the wait begins.

        Config used:
        - template: template to watch (required)
        - max_wait: max wait seconds, default 10.0
        - check_interval: check interval seconds, default 0.5
        - threshold: match threshold, default 0.8
        - method: OpenCV match method, default "TM_CCOEFF_NORMED"
        - roi: optional [x, y, w, h]
        - require_seen_first: bool, default False
        """
        max_wait = self._get_timeout()
        check_interval = self.config.get("check_interval", 0.5)
        threshold = self.config.get("threshold", 0.8)
        template = self.config.get("template")
        require_seen_first = self.config.get("require_seen_first", False)

        device = getattr(context, "device", None)
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="wait(disappear): no device in context",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_DISCONNECTED, mode="disappear",
                ),
            )

        if not template:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="wait(disappear): 'template' config is required",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID, mode="disappear",
                ),
            )

        try:
            from engine.nodes.template_match import TemplateMatchNode
        except ImportError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"wait(disappear): TemplateMatchNode unavailable: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN, mode="disappear",
                    import_error=str(exc),
                ),
            )

        tm_node = TemplateMatchNode(
            id=f"{self.id}_tm_disappear",
            node_type="template_match",
            config={
                "template": template,
                "threshold": threshold,
                "method": self.config.get("method", "TM_CCOEFF_NORMED"),
                "roi": self.config.get("roi"),
                # N191 §10.7 P0-4 (架构层归一化修复, 2026-07-27):
                # 转发 roi_coord_type, 同 _wait_template。
                "roi_coord_type": self.config.get("roi_coord_type", "base"),
            },
        )

        deadline = start + max_wait
        seen_at_least_once = False
        last_match_conf = 0.0

        while time.monotonic() < deadline:
            match_result = tm_node.execute(context)
            is_visible = match_result.success and bool(match_result.data)
            if is_visible:
                seen_at_least_once = True
                last_match_conf = match_result.data.get("confidence", 0.0)

            if not is_visible:
                if require_seen_first and not seen_at_least_once:
                    # Template not yet seen; keep waiting for it to appear
                    # before we start waiting for it to disappear.
                    time.sleep(check_interval)
                    continue
                # Template gone (and we either saw it first or don't need to)
                elapsed = time.monotonic() - start
                logger.info(
                    "wait(disappear): template gone after %.2fs "
                    "(seen_first=%s, last_conf=%.4f)",
                    elapsed, seen_at_least_once, last_match_conf,
                )
                return success_result(
                    data={
                        "mode": "disappear",
                        "gone_after": elapsed,
                        "max_wait": max_wait,
                        "seen_first": seen_at_least_once,
                        "last_confidence": last_match_conf,
                        "coord_system": getattr(context, "coord_system", "") or "legacy",
                    },
                    elapsed_time=elapsed,
                )
            time.sleep(check_interval)

        elapsed = time.monotonic() - start
        return fail_result(
            error_msg=(
                f"wait(disappear): template still visible after {max_wait}s "
                f"(seen_first={seen_at_least_once}, last_conf={last_match_conf:.4f})"
            ),
            elapsed_time=elapsed,
            error_code=NodeErrorCode.TIMEOUT,
            node_id=self.id,
            node_type=self.node_type,
            data=self._build_fail_diagnostics(
                context, NodeErrorCode.TIMEOUT, mode="disappear",
                threshold=threshold, seen_first=seen_at_least_once,
                last_confidence=last_match_conf,
            ),
        )
