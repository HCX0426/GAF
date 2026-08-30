"""Verifier module — 6 verify types extracted from TaskOrchestrator (spec §3.1).

This module is a pure refactor: it moves the verify dispatch logic out of
`core/orchestrator.py::_run_verify` into a standalone, dependency-injected
class so that PipelineEngine can reuse the same 6 verify types for
`post_verify` (spec 阶段 3 — 任务 3.2) without depending on the full
TaskOrchestrator (which carries device_manager / monitor_manager /
delay_manager baggage).

Supported verify types (unchanged from N126-F1):
- template: template image must be present on screen
- color: color must be present in ROI
- exist: template OR color must be present (alias with explicit element type)
- disappear: template OR color must NOT be present (inverse of exist)
- text: OCR must find expected text in ROI
- custom_verify: invoke user-provided callable path (module:function)

Backward compatibility:
- TaskOrchestrator._run_verify delegates to Verifier.verify() (single-line
  change in orchestrator.py), so all existing test_orchestrator.py +
  test_verify_handler.py tests continue to pass without modification.

Design notes:
- Verifier does NOT own screenshot/template/color state — it receives
  callable hooks at construction. This makes it trivially testable with
  plain MagicMock functions.
- OCR registry is lazily resolved via `ocr_registry_fn` so importing
  `core.verify` never triggers heavy OCR imports.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from collections.abc import Callable
from typing import Any

from core.result import AutoResult, fail_result, success_result

logger = logging.getLogger(__name__)


# Type aliases for clarity (not enforced — duck typing)
ScreenshotFn = Callable[[], Any]
TemplateMatchFn = Callable[..., Any | None]
ColorPickFn = Callable[..., Any | None]
OcrRegistryFn = Callable[[], Any | None]


class Verifier:
    """Standalone verifier supporting 6 verify types (spec §3.1).

    Each verify type maps to a private method. The public `verify()` is
    a thin dispatcher that selects the method by `verify_dict["type"]`.

    Supported types (N126-F1):
        - "template"      → _verify_template
        - "color"         → _verify_color
        - "exist"         → _verify_exist (expect_present=True)
        - "disappear"     → _verify_exist (expect_present=False)
        - "text"          → _verify_text
        - "custom_verify" → _verify_custom

    Args (dependency injection — all callables, no concrete deps):
        screenshot_fn: () -> screenshot (numpy ndarray / PIL Image / bytes)
        template_match_fn: (screenshot, template, roi: dict|None, threshold)
                           -> dict|None
        color_pick_fn: (screenshot, color, roi: dict|None) -> dict|None
        ocr_registry_fn: () -> OCREngineRegistry | None  (lazy)
    """

    SUPPORTED_TYPES: frozenset[str] = frozenset({
        "template", "color", "exist", "disappear", "text", "custom_verify",
    })

    def __init__(
        self,
        screenshot_fn: ScreenshotFn,
        template_match_fn: TemplateMatchFn,
        color_pick_fn: ColorPickFn,
        ocr_registry_fn: OcrRegistryFn,
    ) -> None:
        self._screenshot_fn = screenshot_fn
        self._template_match_fn = template_match_fn
        self._color_pick_fn = color_pick_fn
        self._ocr_registry_fn = ocr_registry_fn

    # ------------------------------------------------------------------
    # Public dispatch
    # ------------------------------------------------------------------

    def verify(self, verify: dict[str, Any]) -> AutoResult:
        """Dispatch verification based on ``verify["type"]``.

        Args:
            verify: verify dict with "type" and type-specific params.

        Returns:
            AutoResult with success/fail and matched data. Never raises —
            any exception in a verify path is caught and converted to
            fail_result so the caller (engine / orchestrator) keeps running.
        """
        verify_type = verify.get("type", "")
        try:
            if verify_type == "template":
                return self._verify_template(verify)
            elif verify_type == "color":
                return self._verify_color(verify)
            elif verify_type == "exist":
                return self._verify_exist(verify, expect_present=True)
            elif verify_type == "disappear":
                return self._verify_exist(verify, expect_present=False)
            elif verify_type == "text":
                return self._verify_text(verify)
            elif verify_type == "custom_verify":
                return self._verify_custom(verify)
            else:
                return fail_result(error_msg=f"未知验证类型: {verify_type}")
        except Exception as exc:
            return fail_result(error_msg=str(exc))

    # ------------------------------------------------------------------
    # Type-specific verifiers
    # ------------------------------------------------------------------

    def _verify_template(self, verify: dict[str, Any]) -> AutoResult:
        """Template image must be present on screen."""
        screenshot = self._screenshot_fn()
        match = self._template_match_fn(
            screenshot,
            verify.get("template"),
            roi=verify.get("roi"),
            threshold=verify.get("threshold", 0.8),
        )
        return success_result(data=match) if match else fail_result(error_msg="模板未匹配")

    def _verify_color(self, verify: dict[str, Any]) -> AutoResult:
        """Color must be present in ROI."""
        screenshot = self._screenshot_fn()
        match = self._color_pick_fn(
            screenshot,
            verify.get("color"),
            roi=verify.get("roi"),
        )
        return success_result(data=match) if match else fail_result(error_msg="颜色未匹配")

    def _verify_exist(
        self, verify: dict[str, Any], expect_present: bool,
    ) -> AutoResult:
        """Verify element existence (template or color) in ROI.

        Args:
            verify: must contain "element" key with value "template"
                or "color", plus element-specific params.
            expect_present: True for 'exist', False for 'disappear'.
        """
        element_type = verify.get("element", "template")
        screenshot = self._screenshot_fn()
        match = None

        if element_type == "template":
            match = self._template_match_fn(
                screenshot,
                verify.get("template"),
                roi=verify.get("roi"),
                threshold=verify.get("threshold", 0.8),
            )
        elif element_type == "color":
            match = self._color_pick_fn(
                screenshot,
                verify.get("color"),
                roi=verify.get("roi"),
            )
        else:
            return fail_result(error_msg=f"未知 element 类型: {element_type}")

        present = match is not None
        if present == expect_present:
            return success_result(data=match)
        # Mismatch: build descriptive error message
        action = "存在" if expect_present else "消失"
        return fail_result(error_msg=f"元素未{action}: element={element_type}")

    def _verify_text(self, verify: dict[str, Any]) -> AutoResult:
        """Verify text presence via OCR.

        Uses the OCR registry returned by ``ocr_registry_fn``. If the
        registry is unavailable or no engine is registered, returns a
        fail_result with a clear message (no exception).

        Args:
            verify: dict with keys:
                - text: expected text (substring match)
                - roi: optional ROI dict {x, y, w, h}
                - lang: optional OCR language code (default 'ch')
                - threshold: optional confidence threshold (default 0.5)
        """
        expected_text = verify.get("text", "")
        if not expected_text:
            return fail_result(error_msg="text 验证缺少 'text' 参数")

        screenshot = self._screenshot_fn()
        roi = verify.get("roi")
        if roi:
            x, y = roi.get("x", 0), roi.get("y", 0)
            w, h = roi.get("w", 0), roi.get("h", 0)
            if w > 0 and h > 0:
                screenshot = screenshot[y:y + h, x:x + w]

        # Lazy probe via importlib.util.find_spec to avoid hard dependency
        # on OCR engines (ruff F401: the imported name was never used —
        # this is a pure availability check, not a real import).
        if importlib.util.find_spec("recognition.ocr.registry") is None:
            return fail_result(
                error_msg="OCR 模块不可用: recognition.ocr.registry not installed"
            )

        registry = self._ocr_registry_fn()
        if registry is None or not registry.engine_names:
            return fail_result(
                error_msg="无 OCR 引擎已注册, 请先注册 RapidOCREngine 或 PaddleOCREngine"
            )

        lang = verify.get("lang", "ch")
        threshold = verify.get("threshold", 0.5)
        try:
            engine = (
                registry.get_best() if registry._benchmarked
                else registry.get_engine(registry.engine_names[0])
            )
            results = engine.recognize(screenshot, lang=lang)
        except Exception as exc:
            return fail_result(error_msg=f"OCR 识别失败: {exc}")

        for result in results:
            if result.confidence < threshold:
                continue
            if expected_text in result.text:
                return success_result(data={
                    "text": result.text,
                    "confidence": result.confidence,
                    "box": result.box,
                })

        return fail_result(
            error_msg=(
                f"文本未匹配: expected='{expected_text}', "
                f"got={[r.text for r in results]}"
            )
        )

    def _verify_custom(self, verify: dict[str, Any]) -> AutoResult:
        """Invoke user-provided custom verify callable.

        The callable is specified via "module" and "function" keys in the
        verify dict. The callable receives (screenshot, verify_dict) and
        must return an AutoResult.

        Args:
            verify: dict with keys:
                - module: dotted module path (e.g. "myapp.verifiers")
                - function: function name in module (e.g. "check_login")
                - args: optional dict of extra kwargs passed to function
        """
        module_path = verify.get("module", "")
        function_name = verify.get("function", "")
        if not module_path or not function_name:
            return fail_result(
                error_msg="custom_verify 缺少 'module' 或 'function' 参数"
            )

        try:
            module = importlib.import_module(module_path)
            func = getattr(module, function_name)
        except (ImportError, AttributeError) as exc:
            return fail_result(error_msg=f"custom_verify 加载失败: {exc}")

        screenshot = self._screenshot_fn()
        extra_args = verify.get("args", {})

        try:
            result = func(screenshot, verify, **extra_args)
        except Exception as exc:
            return fail_result(error_msg=f"custom_verify 执行失败: {exc}")

        if not isinstance(result, AutoResult):
            return fail_result(
                error_msg=(
                    f"custom_verify 返回类型错误: 期望 AutoResult, "
                    f"实际 {type(result).__name__}"
                )
            )
        return result
