"""
Verify Handler — 5 verification types (exist/disappear/text/text_disappear/custom_verify).

Based on BD2-AUTO VerifyHandler design, adapted for GAF platform abstraction.
Dependencies (screenshot_fn / template_match_fn / ocr_fn) are injected via constructor,
making this class independent of any specific Auto/Device class and fully testable.

Reference: GAF/docs/architecture/optimal-solution.md §五 (BD2-AUTO VerifyHandler 5种验证)

N128-F1 (2026-06-24): Added 3 sub-features:
- text_disappear verify type (wait for text to disappear via OCR)
- Window validity sensing (window_validity_fn — abort when window handle becomes invalid)
- Failure scene preservation (on_failure_save_fn — save screenshot/log/context on timeout/abort)
"""
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class VerifyType(StrEnum):
    """Verification type enum.

    Mirrors BD2-AUTO VerifyType. N128-F1 implements all 5 types:
    - exist / disappear / text / text_disappear / custom_verify.
    """
    EXIST = "exist"                      # Wait for element to appear (template match)
    DISAPPEAR = "disappear"              # Wait for element to disappear (template match)
    TEXT = "text"                        # Wait for text to appear (OCR)
    TEXT_DISAPPEAR = "text_disappear"    # Wait for text to disappear (OCR) — N128-F1
    CUSTOM_VERIFY = "custom_verify"      # Custom callable verification


@dataclass
class VerifyResult:
    """Verification result.

    Attributes:
        success: Whether verification succeeded.
        elapsed_time: Total elapsed seconds (including waits).
        data: Optional payload — match position (x, y) for exist, True/False for custom, etc.
        error: Error message when success is False.
        is_interrupted: True if verification was interrupted by stop_event.
    """
    success: bool = False
    elapsed_time: float = 0.0
    data: object = None
    error: str | None = None
    is_interrupted: bool = False

    @classmethod
    def ok(cls, data: object = None, elapsed_time: float = 0.0) -> "VerifyResult":
        return cls(success=True, data=data, elapsed_time=elapsed_time)

    @classmethod
    def fail(cls, error: str, elapsed_time: float = 0.0, is_interrupted: bool = False) -> "VerifyResult":
        return cls(success=False, error=error, elapsed_time=elapsed_time, is_interrupted=is_interrupted)


# Type aliases for injected dependencies
TemplateMatchFn = Callable[[bytes, str | list[str], tuple[int, int, int, int] | None], tuple[int, int] | None]
OcrFindFn = Callable[[bytes, str | list[str], tuple[int, int, int, int] | None], bool]
ScreenshotFn = Callable[[], bytes]
CustomVerifyFn = Callable[[], bool]
# N128-F1: Window validity check (returns True if window handle is still valid)
WindowValidityFn = Callable[[], bool]
# N128-F1: Failure scene save callback (desc, result) -> None
FailureSaveFn = Callable[[str, "VerifyResult"], None]


class VerifyHandler:
    """Verification handler with 5 verification types.

    Design:
    - Dependencies are injected (screenshot_fn / template_match_fn / ocr_fn),
      so this class has no hard dependency on any specific platform/OCR/template engine.
    - When a dependency is None, the corresponding verify type returns a clear error
      rather than crashing — enables graceful degradation when OCR/template engine
      is not installed.
    - stop_event (threading.Event) allows cooperative cancellation from the caller.
    - All public methods return VerifyResult for uniform error handling.
    - N128-F1: window_validity_fn — when set, _check_once verifies the window handle
      is still valid (IsWindow) before each screenshot; aborts early if invalid.
    - N128-F1: on_failure_save_fn — when set, invoked on timeout or window-invalid
      abort to preserve failure scene (screenshot/log/context) for post-mortem.

    Usage:
        handler = VerifyHandler(
            screenshot_fn=device.capture_bytes,
            template_match_fn=image_processor.match_template,
            ocr_fn=ocr_processor.find_text,
            window_validity_fn=lambda: device.is_window_valid(),  # N128-F1
            on_failure_save_fn=save_failure_scene,                # N128-F1
        )
        result = handler.verify(VerifyType.EXIST, "button.png", timeout=10.0)
        if result.success:
            print("Found at", result.data)
    """

    def __init__(
        self,
        screenshot_fn: ScreenshotFn | None = None,
        template_match_fn: TemplateMatchFn | None = None,
        ocr_fn: OcrFindFn | None = None,
        default_timeout: float = 10.0,
        check_interval: float = 0.5,
        stop_event: threading.Event | None = None,
        window_validity_fn: WindowValidityFn | None = None,
        on_failure_save_fn: FailureSaveFn | None = None,
    ):
        """
        Args:
            screenshot_fn: Returns image bytes for current screen. Required for exist/disappear/text/text_disappear.
            template_match_fn: (image_bytes, template_name_or_list, roi) -> (x, y) or None.
            ocr_fn: (image_bytes, text_or_list, roi) -> bool (whether text found).
            default_timeout: Default timeout in seconds when timeout=None.
            check_interval: Polling interval in seconds.
            stop_event: External threading.Event for cooperative cancellation.
            window_validity_fn: N128-F1 — returns True if target window is still valid.
                When set, _check_once aborts with is_interrupted=True if window becomes invalid.
            on_failure_save_fn: N128-F1 — callback(desc, result) invoked on timeout or
                window-invalid abort to preserve failure scene.
        """
        self.screenshot_fn = screenshot_fn
        self.template_match_fn = template_match_fn
        self.ocr_fn = ocr_fn
        self.default_timeout = default_timeout
        self.check_interval = check_interval
        self.stop_event = stop_event or threading.Event()
        self.window_validity_fn = window_validity_fn
        self.on_failure_save_fn = on_failure_save_fn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(
        self,
        verify_type: VerifyType | str,
        target: str | list[str] | CustomVerifyFn,
        timeout: float | None = None,
        roi: tuple[int, int, int, int] | None = None,
    ) -> VerifyResult:
        """Unified verify entry — wait for condition with timeout.

        Args:
            verify_type: One of VerifyType values (or its string form).
            target: Template name / text / list of names / callable for custom_verify.
            timeout: Max wait seconds. None = default_timeout. 0 = single check (no wait).
            roi: Optional region of interest (x, y, w, h) to restrict matching.
        """
        try:
            vt = VerifyType(verify_type) if isinstance(verify_type, str) else verify_type
        except ValueError:
            return VerifyResult.fail(f"Invalid verify_type: {verify_type}")

        actual_timeout = self.default_timeout if timeout is None else timeout
        start_time = time.time()

        if actual_timeout == 0:
            return self._check_once(vt, target, roi, start_time)

        return self._wait_with_condition(vt, target, roi, actual_timeout, start_time)

    def check_exist(self, target: str | list[str], roi: tuple[int, int, int, int] | None = None) -> VerifyResult:
        """Single-shot check: element exists?"""
        return self.verify(VerifyType.EXIST, target, timeout=0, roi=roi)

    def check_disappear(self, target: str | list[str], roi: tuple[int, int, int, int] | None = None) -> VerifyResult:
        """Single-shot check: element disappeared?"""
        return self.verify(VerifyType.DISAPPEAR, target, timeout=0, roi=roi)

    def check_text(self, target: str | list[str], roi: tuple[int, int, int, int] | None = None) -> VerifyResult:
        """Single-shot check: text present?"""
        return self.verify(VerifyType.TEXT, target, timeout=0, roi=roi)

    def check_text_disappear(self, target: str | list[str], roi: tuple[int, int, int, int] | None = None) -> VerifyResult:
        """Single-shot check: text disappeared? (N128-F1)"""
        return self.verify(VerifyType.TEXT_DISAPPEAR, target, timeout=0, roi=roi)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_once(
        self,
        vt: VerifyType,
        target: str | list[str] | CustomVerifyFn,
        roi: tuple[int, int, int, int] | None,
        start_time: float,
    ) -> VerifyResult:
        """Single check without waiting."""
        if self.stop_event.is_set():
            return VerifyResult.fail("verify interrupted", elapsed_time=time.time() - start_time, is_interrupted=True)

        # N128-F1: Window validity sensing — abort early if window handle is no longer valid.
        # This avoids wasting screenshot/OCR cycles on a dead window (e.g. game crashed/closed).
        if self.window_validity_fn is not None:
            try:
                still_valid = self.window_validity_fn()
            except Exception as e:
                logger.error("window_validity_fn raised: %s", e, exc_info=True)
                return VerifyResult.fail(
                    f"window_validity_fn raised: {e}",
                    elapsed_time=time.time() - start_time,
                    is_interrupted=True,
                )
            if not still_valid:
                logger.warning("[verify] window no longer valid, aborting: %s - %s", vt.value, target)
                return VerifyResult.fail(
                    "window no longer valid",
                    elapsed_time=time.time() - start_time,
                    is_interrupted=True,
                )

        if vt == VerifyType.CUSTOM_VERIFY:
            return self._run_custom_verify(target, start_time)

        # Type narrowing: past the CUSTOM_VERIFY branch above, target must be
        # str | list[str] (the only other allowed type per verify()'s signature).
        # This assert helps mypy understand the narrowing without adding runtime
        # overhead in production (asserts are stripped under -O).
        assert isinstance(target, (str, list))

        # exist / disappear / text / text_disappear all need a screenshot
        if self.screenshot_fn is None:
            return VerifyResult.fail("screenshot_fn not configured", elapsed_time=time.time() - start_time)

        try:
            image_bytes = self.screenshot_fn()
        except Exception as e:
            logger.error("screenshot failed: %s", e, exc_info=True)
            return VerifyResult.fail(f"screenshot failed: {e}", elapsed_time=time.time() - start_time)

        if vt == VerifyType.EXIST:
            return self._run_exist(image_bytes, target, roi, start_time)
        if vt == VerifyType.DISAPPEAR:
            return self._run_disappear(image_bytes, target, roi, start_time)
        if vt == VerifyType.TEXT:
            return self._run_text(image_bytes, target, roi, start_time)
        if vt == VerifyType.TEXT_DISAPPEAR:
            return self._run_text_disappear(image_bytes, target, roi, start_time)

        return VerifyResult.fail(f"Unsupported verify_type: {vt}", elapsed_time=time.time() - start_time)

    def _run_exist(
        self,
        image_bytes: bytes,
        target: str | list[str],
        roi: tuple[int, int, int, int] | None,
        start_time: float,
    ) -> VerifyResult:
        if self.template_match_fn is None:
            return VerifyResult.fail("template_match_fn not configured", elapsed_time=time.time() - start_time)
        try:
            pos = self.template_match_fn(image_bytes, target, roi)
        except Exception as e:
            logger.error("template_match failed: %s", e, exc_info=True)
            return VerifyResult.fail(f"template_match failed: {e}", elapsed_time=time.time() - start_time)
        if pos is not None:
            return VerifyResult.ok(data=pos, elapsed_time=time.time() - start_time)
        return VerifyResult.fail(f"element not found: {target}", elapsed_time=time.time() - start_time)

    def _run_disappear(
        self,
        image_bytes: bytes,
        target: str | list[str],
        roi: tuple[int, int, int, int] | None,
        start_time: float,
    ) -> VerifyResult:
        if self.template_match_fn is None:
            return VerifyResult.fail("template_match_fn not configured", elapsed_time=time.time() - start_time)
        try:
            pos = self.template_match_fn(image_bytes, target, roi)
        except Exception as e:
            logger.error("template_match failed: %s", e, exc_info=True)
            return VerifyResult.fail(f"template_match failed: {e}", elapsed_time=time.time() - start_time)
        if pos is None:
            return VerifyResult.ok(data=True, elapsed_time=time.time() - start_time)
        return VerifyResult.fail(f"element still present: {target}", elapsed_time=time.time() - start_time)

    def _run_text(
        self,
        image_bytes: bytes,
        target: str | list[str],
        roi: tuple[int, int, int, int] | None,
        start_time: float,
    ) -> VerifyResult:
        if self.ocr_fn is None:
            return VerifyResult.fail("ocr_fn not configured", elapsed_time=time.time() - start_time)
        try:
            found = self.ocr_fn(image_bytes, target, roi)
        except Exception as e:
            logger.error("ocr failed: %s", e, exc_info=True)
            return VerifyResult.fail(f"ocr failed: {e}", elapsed_time=time.time() - start_time)
        if found:
            return VerifyResult.ok(data=True, elapsed_time=time.time() - start_time)
        return VerifyResult.fail(f"text not found: {target}", elapsed_time=time.time() - start_time)

    def _run_text_disappear(
        self,
        image_bytes: bytes,
        target: str | list[str],
        roi: tuple[int, int, int, int] | None,
        start_time: float,
    ) -> VerifyResult:
        """N128-F1: Check that text is NOT present (inverse of _run_text).

        Used to wait for loading screens / toast notifications / modal text to disappear.
        """
        if self.ocr_fn is None:
            return VerifyResult.fail("ocr_fn not configured", elapsed_time=time.time() - start_time)
        try:
            found = self.ocr_fn(image_bytes, target, roi)
        except Exception as e:
            logger.error("ocr failed: %s", e, exc_info=True)
            return VerifyResult.fail(f"ocr failed: {e}", elapsed_time=time.time() - start_time)
        if not found:
            return VerifyResult.ok(data=True, elapsed_time=time.time() - start_time)
        return VerifyResult.fail(f"text still present: {target}", elapsed_time=time.time() - start_time)

    def _run_custom_verify(
        self,
        target: str | list[str] | CustomVerifyFn,
        start_time: float,
    ) -> VerifyResult:
        if not callable(target):
            return VerifyResult.fail("custom_verify target must be callable", elapsed_time=time.time() - start_time)
        try:
            ok = bool(target())
        except Exception as e:
            logger.error("custom_verify raised: %s", e, exc_info=True)
            return VerifyResult.fail(f"custom_verify raised: {e}", elapsed_time=time.time() - start_time)
        if ok:
            return VerifyResult.ok(data=True, elapsed_time=time.time() - start_time)
        return VerifyResult.fail("custom_verify returned False", elapsed_time=time.time() - start_time)

    def _wait_with_condition(
        self,
        vt: VerifyType,
        target: str | list[str] | CustomVerifyFn,
        roi: tuple[int, int, int, int] | None,
        timeout: float,
        start_time: float,
    ) -> VerifyResult:
        """Poll _check_once until success / timeout / interrupt.

        For DISAPPEAR / TEXT_DISAPPEAR, success = _check_once.success (which means element/text is gone).
        For others, success = _check_once.success directly.

        N128-F1: On timeout or window-invalid abort, invoke on_failure_save_fn to
        preserve failure scene (screenshot/log/context) for post-mortem analysis.
        """
        desc = f"{vt.value} - {target}"
        logger.info("[verify] waiting: %s, timeout=%.1fs", desc, timeout)

        while True:
            if self.stop_event.is_set():
                elapsed = time.time() - start_time
                logger.info("[verify] interrupted: %s", desc)
                result = VerifyResult.fail(f"{desc} interrupted", elapsed_time=elapsed, is_interrupted=True)
                self._save_failure_context(desc, result)
                return result

            result = self._check_once(vt, target, roi, start_time)
            if result.success:
                logger.info("[verify] success: %s, elapsed=%.2fs", desc, result.elapsed_time)
                return result

            # N128-F1: Window-invalid abort — save failure scene and return immediately
            # (no point retrying when the target window is gone).
            if result.is_interrupted and "window no longer valid" in (result.error or ""):
                logger.warning("[verify] window invalid, saving failure scene: %s", desc)
                self._save_failure_context(desc, result)
                return result

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning("[verify] timeout: %s (%.1fs)", desc, timeout)
                final_result = VerifyResult.fail(
                    error=f"verify timeout: {desc} ({timeout:.1f}s)",
                    elapsed_time=elapsed,
                )
                # N128-F1: Save failure scene on timeout for post-mortem analysis.
                self._save_failure_context(desc, final_result)
                return final_result

            # Sleep with cooperative cancellation
            self._sleep(self.check_interval)

    def _save_failure_context(self, desc: str, result: VerifyResult) -> None:
        """N128-F1: Invoke on_failure_save_fn to preserve failure scene.

        Best-effort: errors in the save callback are logged but never propagated,
        so a failing save cannot mask the original verify failure.
        """
        if self.on_failure_save_fn is None:
            return
        try:
            self.on_failure_save_fn(desc, result)
        except Exception as e:
            logger.error("on_failure_save_fn raised: %s", e, exc_info=True)

    def _sleep(self, seconds: float) -> None:
        """Sleep that wakes up immediately when stop_event is set."""
        if self.stop_event.wait(timeout=seconds):
            return  # stop_event was set during sleep
