"""VerifyHandler unit tests — 4 verification types (exist/disappear/text/custom_verify).

Tests cover:
- Constructor + default values
- Single-shot checks (timeout=0)
- Wait-with-timeout (success path + timeout path)
- Interrupt via stop_event
- Dependency-not-configured graceful errors
- Exception propagation from injected fns
- VerifyType enum + string coercion
- VerifyResult factory methods (ok/fail)
"""
import threading
import time

from device_bridge.handlers.verify import VerifyHandler, VerifyResult, VerifyType

# ============================================================
# VerifyResult factory tests
# ============================================================

class TestVerifyResult:
    def test_ok_default(self):
        r = VerifyResult.ok()
        assert r.success is True
        assert r.data is None
        assert r.elapsed_time == 0.0
        assert r.error is None
        assert r.is_interrupted is False

    def test_ok_with_data(self):
        r = VerifyResult.ok(data=(100, 200), elapsed_time=1.5)
        assert r.success is True
        assert r.data == (100, 200)
        assert r.elapsed_time == 1.5

    def test_fail_default(self):
        r = VerifyResult.fail("boom")
        assert r.success is False
        assert r.error == "boom"
        assert r.is_interrupted is False

    def test_fail_interrupted(self):
        r = VerifyResult.fail("stopped", is_interrupted=True)
        assert r.success is False
        assert r.is_interrupted is True


# ============================================================
# VerifyType enum tests
# ============================================================

class TestVerifyType:
    def test_enum_values(self):
        assert VerifyType.EXIST.value == "exist"
        assert VerifyType.DISAPPEAR.value == "disappear"
        assert VerifyType.TEXT.value == "text"
        assert VerifyType.CUSTOM_VERIFY.value == "custom_verify"

    def test_string_coercion(self):
        """verify() should accept string form of VerifyType."""
        handler = VerifyHandler(template_match_fn=lambda *_: None)
        # Should not raise on string verify_type
        result = handler.verify("exist", "x.png", timeout=0)
        assert isinstance(result, VerifyResult)

    def test_invalid_string_verify_type(self):
        handler = VerifyHandler()
        result = handler.verify("not_a_type", "x.png", timeout=0)
        assert result.success is False
        assert "Invalid verify_type" in (result.error or "")


# ============================================================
# Constructor / config tests
# ============================================================

class TestVerifyHandlerConstructor:
    def test_defaults(self):
        h = VerifyHandler()
        assert h.screenshot_fn is None
        assert h.template_match_fn is None
        assert h.ocr_fn is None
        assert h.default_timeout == 10.0
        assert h.check_interval == 0.5
        # stop_event is auto-created (not None)
        assert h.stop_event is not None
        assert h.stop_event.is_set() is False

    def test_custom_config(self):
        ev = threading.Event()
        h = VerifyHandler(default_timeout=5.0, check_interval=0.1, stop_event=ev)
        assert h.default_timeout == 5.0
        assert h.check_interval == 0.1
        assert h.stop_event is ev


# ============================================================
# Single-shot (timeout=0) tests
# ============================================================

class TestSingleShotChecks:
    def test_exist_success(self):
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda img, t, roi: (50, 60) if t == "btn.png" else None,
        )
        r = h.check_exist("btn.png")
        assert r.success is True
        assert r.data == (50, 60)

    def test_exist_not_found(self):
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda img, t, roi: None,
        )
        r = h.check_exist("btn.png")
        assert r.success is False
        assert "not found" in (r.error or "")

    def test_disappear_success(self):
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda img, t, roi: None,
        )
        r = h.check_disappear("btn.png")
        assert r.success is True
        assert r.data is True

    def test_disappear_still_present(self):
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda img, t, roi: (10, 20),
        )
        r = h.check_disappear("btn.png")
        assert r.success is False
        assert "still present" in (r.error or "")

    def test_text_success(self):
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            ocr_fn=lambda img, t, roi: t == "Login",
        )
        r = h.check_text("Login")
        assert r.success is True
        assert r.data is True

    def test_text_not_found(self):
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            ocr_fn=lambda img, t, roi: False,
        )
        r = h.check_text("Login")
        assert r.success is False
        assert "text not found" in (r.error or "")

    def test_exist_list_target(self):
        """target can be a list of template names."""
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda img, t, roi: (1, 2) if "a.png" in t else None,
        )
        r = h.check_exist(["a.png", "b.png"])
        assert r.success is True
        assert r.data == (1, 2)

    def test_roi_passed_through(self):
        captured_roi = {}
        def match(img, t, roi):
            captured_roi["roi"] = roi
            return None
        h = VerifyHandler(screenshot_fn=lambda: b"\x89PNG", template_match_fn=match)
        h.check_exist("x.png", roi=(10, 20, 100, 200))
        assert captured_roi["roi"] == (10, 20, 100, 200)


# ============================================================
# Dependency-not-configured tests
# ============================================================

class TestMissingDependencies:
    def test_exist_without_screenshot_fn(self):
        h = VerifyHandler(template_match_fn=lambda *_: None)
        r = h.check_exist("x.png")
        assert r.success is False
        assert "screenshot_fn not configured" in (r.error or "")

    def test_exist_without_template_match_fn(self):
        h = VerifyHandler(screenshot_fn=lambda: b"\x89PNG")
        r = h.check_exist("x.png")
        assert r.success is False
        assert "template_match_fn not configured" in (r.error or "")

    def test_text_without_ocr_fn(self):
        h = VerifyHandler(screenshot_fn=lambda: b"\x89PNG")
        r = h.check_text("hello")
        assert r.success is False
        assert "ocr_fn not configured" in (r.error or "")

    def test_custom_verify_works_without_screenshot_fn(self):
        """custom_verify does not need screenshot_fn — it calls the callable directly."""
        h = VerifyHandler()  # no fns configured
        r = h.verify(VerifyType.CUSTOM_VERIFY, lambda: True, timeout=0)
        assert r.success is True

    def test_custom_verify_non_callable_target(self):
        h = VerifyHandler()
        r = h.verify(VerifyType.CUSTOM_VERIFY, "not_callable", timeout=0)
        assert r.success is False
        assert "must be callable" in (r.error or "")


# ============================================================
# Exception propagation tests
# ============================================================

class TestExceptionHandling:
    def test_screenshot_fn_raises(self):
        def boom():
            raise RuntimeError("camera disconnected")
        h = VerifyHandler(screenshot_fn=boom, template_match_fn=lambda *_: None)
        r = h.check_exist("x.png")
        assert r.success is False
        assert "screenshot failed" in (r.error or "")
        assert "camera disconnected" in (r.error or "")

    def test_template_match_fn_raises(self):
        def boom(*_):
            raise ValueError("bad template")
        h = VerifyHandler(screenshot_fn=lambda: b"\x89PNG", template_match_fn=boom)
        r = h.check_exist("x.png")
        assert r.success is False
        assert "template_match failed" in (r.error or "")

    def test_ocr_fn_raises(self):
        def boom(*_):
            raise OSError("onnxruntime missing")
        h = VerifyHandler(screenshot_fn=lambda: b"\x89PNG", ocr_fn=boom)
        r = h.check_text("hello")
        assert r.success is False
        assert "ocr failed" in (r.error or "")

    def test_custom_verify_raises(self):
        def boom():
            raise RuntimeError("custom logic crashed")
        h = VerifyHandler()
        r = h.verify(VerifyType.CUSTOM_VERIFY, boom, timeout=0)
        assert r.success is False
        assert "custom_verify raised" in (r.error or "")


# ============================================================
# Wait-with-timeout tests
# ============================================================

class TestWaitWithTimeout:
    def test_wait_succeeds_before_timeout(self):
        """Condition becomes true after 2 checks."""
        call_count = {"n": 0}

        def match(img, t, roi):
            call_count["n"] += 1
            return (1, 2) if call_count["n"] >= 2 else None

        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=match,
            default_timeout=5.0,
            check_interval=0.05,
        )
        r = h.verify(VerifyType.EXIST, "x.png")  # uses default_timeout
        assert r.success is True
        assert r.data == (1, 2)
        assert call_count["n"] == 2
        assert r.elapsed_time < 5.0

    def test_wait_times_out(self):
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: None,
            check_interval=0.05,
        )
        r = h.verify(VerifyType.EXIST, "x.png", timeout=0.2)
        assert r.success is False
        assert "timeout" in (r.error or "")
        assert r.elapsed_time >= 0.2
        assert r.is_interrupted is False

    def test_timeout_none_uses_default(self):
        """timeout=None falls back to default_timeout."""
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: None,
            default_timeout=0.15,
            check_interval=0.05,
        )
        r = h.verify(VerifyType.EXIST, "x.png")  # timeout=None
        assert r.success is False
        assert "timeout" in (r.error or "")

    def test_wait_disappear_succeeds_when_gone(self):
        """DISAPPEAR succeeds when template_match returns None."""
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: None,
            check_interval=0.05,
        )
        r = h.verify(VerifyType.DISAPPEAR, "x.png", timeout=0.5)
        assert r.success is True
        # Should succeed quickly (first check)
        assert r.elapsed_time < 0.5

    def test_wait_disappear_times_out_when_still_present(self):
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: (10, 20),  # always present
            check_interval=0.05,
        )
        r = h.verify(VerifyType.DISAPPEAR, "x.png", timeout=0.2)
        assert r.success is False
        assert "timeout" in (r.error or "")


# ============================================================
# Interrupt tests
# ============================================================

class TestInterrupt:
    def test_interrupt_before_check(self):
        """stop_event set before verify() returns interrupted immediately."""
        ev = threading.Event()
        ev.set()
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: None,
            stop_event=ev,
        )
        r = h.verify(VerifyType.EXIST, "x.png", timeout=0)
        assert r.success is False
        assert r.is_interrupted is True
        assert "interrupted" in (r.error or "")

    def test_interrupt_during_wait(self):
        """stop_event set during wait cancels the verify."""
        ev = threading.Event()
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: None,  # never matches
            check_interval=0.05,
            stop_event=ev,
        )

        # Set stop_event after 100ms
        def setter():
            time.sleep(0.1)
            ev.set()

        threading.Thread(target=setter, daemon=True).start()

        r = h.verify(VerifyType.EXIST, "x.png", timeout=5.0)
        assert r.success is False
        assert r.is_interrupted is True
        # Should return quickly after interrupt, not wait full 5s
        assert r.elapsed_time < 1.0

    def test_sleep_wakes_on_stop_event(self):
        """_sleep returns immediately when stop_event is set during sleep."""
        ev = threading.Event()
        h = VerifyHandler(stop_event=ev)

        def setter():
            time.sleep(0.05)
            ev.set()

        threading.Thread(target=setter, daemon=True).start()

        start = time.time()
        h._sleep(5.0)  # would block 5s without interrupt
        elapsed = time.time() - start
        assert elapsed < 0.5  # woke up quickly


# ============================================================
# Custom verify tests
# ============================================================

class TestCustomVerify:
    def test_custom_returns_true(self):
        h = VerifyHandler()
        r = h.verify(VerifyType.CUSTOM_VERIFY, lambda: True, timeout=0)
        assert r.success is True
        assert r.data is True

    def test_custom_returns_false(self):
        h = VerifyHandler()
        r = h.verify(VerifyType.CUSTOM_VERIFY, lambda: False, timeout=0)
        assert r.success is False
        assert "returned False" in (r.error or "")

    def test_custom_returns_truthy_non_bool(self):
        """Non-bool truthy values are coerced to True."""
        h = VerifyHandler()
        r = h.verify(VerifyType.CUSTOM_VERIFY, lambda: "ok", timeout=0)
        assert r.success is True

    def test_custom_returns_falsy_non_bool(self):
        h = VerifyHandler()
        r = h.verify(VerifyType.CUSTOM_VERIFY, lambda: 0, timeout=0)
        assert r.success is False

    def test_custom_wait_succeeds_eventually(self):
        """custom_verify with wait — condition becomes true after N calls."""
        counter = {"n": 0}

        def cond():
            counter["n"] += 1
            return counter["n"] >= 3

        h = VerifyHandler(check_interval=0.05)
        r = h.verify(VerifyType.CUSTOM_VERIFY, cond, timeout=2.0)
        assert r.success is True
        assert counter["n"] == 3


# ============================================================
# N128-F1: text_disappear verify type tests
# ============================================================

class TestTextDisappear:
    """N128-F1: text_disappear verify type — wait for text to disappear via OCR."""

    def test_enum_has_text_disappear(self):
        assert VerifyType.TEXT_DISAPPEAR.value == "text_disappear"

    def test_string_coercion_text_disappear(self):
        h = VerifyHandler(screenshot_fn=lambda: b"\x89PNG", ocr_fn=lambda *_: False)
        r = h.verify("text_disappear", "Loading...", timeout=0)
        assert r.success is True

    def test_single_shot_text_gone(self):
        """Text is absent → success."""
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            ocr_fn=lambda img, t, roi: False,  # text not found
        )
        r = h.check_text_disappear("Loading...")
        assert r.success is True
        assert r.data is True

    def test_single_shot_text_still_present(self):
        """Text is still present → failure."""
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            ocr_fn=lambda img, t, roi: True,  # text found
        )
        r = h.check_text_disappear("Loading...")
        assert r.success is False
        assert "still present" in (r.error or "")

    def test_text_disappear_without_ocr_fn(self):
        """Graceful error when ocr_fn is not configured."""
        h = VerifyHandler(screenshot_fn=lambda: b"\x89PNG")
        r = h.check_text_disappear("Loading...")
        assert r.success is False
        assert "ocr_fn not configured" in (r.error or "")

    def test_text_disappear_ocr_raises(self):
        def boom(*_):
            raise OSError("onnxruntime missing")
        h = VerifyHandler(screenshot_fn=lambda: b"\x89PNG", ocr_fn=boom)
        r = h.check_text_disappear("Loading...")
        assert r.success is False
        assert "ocr failed" in (r.error or "")

    def test_wait_text_disappear_succeeds_when_text_gone(self):
        """Wait succeeds when OCR reports text absent on first check."""
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            ocr_fn=lambda *_: False,
            check_interval=0.05,
        )
        r = h.verify(VerifyType.TEXT_DISAPPEAR, "Loading...", timeout=0.5)
        assert r.success is True
        assert r.elapsed_time < 0.5

    def test_wait_text_disappear_times_out_when_still_present(self):
        """Wait times out when text never disappears."""
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            ocr_fn=lambda *_: True,  # text always present
            check_interval=0.05,
        )
        r = h.verify(VerifyType.TEXT_DISAPPEAR, "Loading...", timeout=0.2)
        assert r.success is False
        assert "timeout" in (r.error or "")

    def test_wait_text_disappear_succeeds_after_n_checks(self):
        """Text disappears after N checks — wait should succeed."""
        call_count = {"n": 0}

        def ocr(img, t, roi):
            call_count["n"] += 1
            return call_count["n"] < 3  # present for first 2 checks, gone on 3rd

        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            ocr_fn=ocr,
            check_interval=0.05,
        )
        r = h.verify(VerifyType.TEXT_DISAPPEAR, "Loading...", timeout=2.0)
        assert r.success is True
        assert call_count["n"] == 3

    def test_roi_passed_to_ocr_for_text_disappear(self):
        captured = {}

        def ocr(img, t, roi):
            captured["roi"] = roi
            return False

        h = VerifyHandler(screenshot_fn=lambda: b"\x89PNG", ocr_fn=ocr)
        h.check_text_disappear("Loading...", roi=(10, 20, 100, 200))
        assert captured["roi"] == (10, 20, 100, 200)

    def test_list_target_text_disappear(self):
        """target can be a list of text strings."""
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            ocr_fn=lambda img, t, roi: False,
        )
        r = h.check_text_disappear(["Loading...", "Please wait"])
        assert r.success is True


# ============================================================
# N128-F1: Window validity sensing tests
# ============================================================

class TestWindowValidity:
    """N128-F1: window_validity_fn — abort verify when window handle becomes invalid."""

    def test_window_valid_no_abort(self):
        """When window_validity_fn returns True, verify proceeds normally."""
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: (5, 6),
            window_validity_fn=lambda: True,
        )
        r = h.check_exist("x.png")
        assert r.success is True
        assert r.data == (5, 6)

    def test_window_invalid_aborts_single_shot(self):
        """When window_validity_fn returns False, single-shot verify aborts."""
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: (5, 6),
            window_validity_fn=lambda: False,
        )
        r = h.check_exist("x.png")
        assert r.success is False
        assert r.is_interrupted is True
        assert "window no longer valid" in (r.error or "")

    def test_window_invalid_aborts_wait(self):
        """During wait, if window becomes invalid, verify aborts immediately."""
        call_count = {"n": 0}

        def validity():
            call_count["n"] += 1
            return call_count["n"] < 3  # valid for first 2 checks, invalid on 3rd

        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: None,  # never matches
            window_validity_fn=validity,
            check_interval=0.05,
        )
        r = h.verify(VerifyType.EXIST, "x.png", timeout=5.0)
        assert r.success is False
        assert r.is_interrupted is True
        assert "window no longer valid" in (r.error or "")
        # Should abort quickly, not wait full 5s
        assert r.elapsed_time < 1.0

    def test_window_validity_fn_not_called_when_none(self):
        """When window_validity_fn is None, no validity check is performed."""
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: (1, 2),
        )
        r = h.check_exist("x.png")
        assert r.success is True

    def test_window_validity_fn_raises(self):
        """If window_validity_fn raises, verify aborts with interrupted status."""
        def boom():
            raise RuntimeError("IsWindow check failed")

        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: (1, 2),
            window_validity_fn=boom,
        )
        r = h.check_exist("x.png")
        assert r.success is False
        assert r.is_interrupted is True
        assert "window_validity_fn raised" in (r.error or "")
        assert "IsWindow check failed" in (r.error or "")

    def test_window_validity_checked_before_screenshot(self):
        """screenshot_fn should NOT be called when window is invalid."""
        screenshot_called = {"n": 0}

        def screenshot():
            screenshot_called["n"] += 1
            return b"\x89PNG"

        h = VerifyHandler(
            screenshot_fn=screenshot,
            template_match_fn=lambda *_: (1, 2),
            window_validity_fn=lambda: False,
        )
        r = h.check_exist("x.png")
        assert r.success is False
        assert screenshot_called["n"] == 0  # screenshot never called

    def test_window_validity_with_custom_verify(self):
        """custom_verify also respects window_validity_fn."""
        h = VerifyHandler(
            window_validity_fn=lambda: False,
        )
        r = h.verify(VerifyType.CUSTOM_VERIFY, lambda: True, timeout=0)
        assert r.success is False
        assert r.is_interrupted is True
        assert "window no longer valid" in (r.error or "")


# ============================================================
# N128-F1: Failure scene preservation tests
# ============================================================

class TestFailureScenePreservation:
    """N128-F1: on_failure_save_fn — preserve failure scene on timeout/abort."""

    def test_save_called_on_timeout(self):
        """on_failure_save_fn is invoked when verify times out."""
        saved = []

        def save(desc, result):
            saved.append((desc, result))

        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: None,  # never matches
            check_interval=0.05,
            on_failure_save_fn=save,
        )
        r = h.verify(VerifyType.EXIST, "x.png", timeout=0.2)
        assert r.success is False
        assert "timeout" in (r.error or "")
        assert len(saved) == 1
        desc, saved_result = saved[0]
        assert "exist" in desc
        assert "x.png" in desc
        assert saved_result.success is False
        assert "timeout" in (saved_result.error or "")

    def test_save_called_on_window_invalid_abort(self):
        """on_failure_save_fn is invoked when verify aborts due to invalid window."""
        saved = []

        def save(desc, result):
            saved.append((desc, result))

        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: None,
            window_validity_fn=lambda: False,
            check_interval=0.05,
            on_failure_save_fn=save,
        )
        r = h.verify(VerifyType.EXIST, "x.png", timeout=5.0)
        assert r.success is False
        assert r.is_interrupted is True
        assert len(saved) == 1
        desc, saved_result = saved[0]
        assert "exist" in desc
        assert saved_result.is_interrupted is True
        assert "window no longer valid" in (saved_result.error or "")

    def test_save_called_on_stop_event_interrupt(self):
        """on_failure_save_fn is invoked when verify is interrupted by stop_event."""
        saved = []
        ev = threading.Event()

        def save(desc, result):
            saved.append((desc, result))

        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: None,
            check_interval=0.05,
            stop_event=ev,
            on_failure_save_fn=save,
        )

        def setter():
            time.sleep(0.1)
            ev.set()

        threading.Thread(target=setter, daemon=True).start()

        r = h.verify(VerifyType.EXIST, "x.png", timeout=5.0)
        assert r.success is False
        assert r.is_interrupted is True
        assert len(saved) == 1

    def test_save_not_called_on_success(self):
        """on_failure_save_fn is NOT invoked when verify succeeds."""
        saved = []

        def save(desc, result):
            saved.append((desc, result))

        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: (1, 2),  # always matches
            check_interval=0.05,
            on_failure_save_fn=save,
        )
        r = h.verify(VerifyType.EXIST, "x.png", timeout=1.0)
        assert r.success is True
        assert len(saved) == 0

    def test_save_not_called_when_none(self):
        """When on_failure_save_fn is None, timeout does not raise."""
        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: None,
            check_interval=0.05,
        )
        r = h.verify(VerifyType.EXIST, "x.png", timeout=0.2)
        assert r.success is False
        # No exception, no crash

    def test_save_fn_raises_is_swallowed(self):
        """If on_failure_save_fn raises, the error is logged but does not propagate."""
        def boom(desc, result):
            raise RuntimeError("disk full")

        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: None,
            check_interval=0.05,
            on_failure_save_fn=boom,
        )
        # Should not raise
        r = h.verify(VerifyType.EXIST, "x.png", timeout=0.2)
        assert r.success is False
        assert "timeout" in (r.error or "")

    def test_save_called_on_single_shot_window_invalid(self):
        """Single-shot (timeout=0) with window invalid also triggers save via _wait_with_condition.

        Note: single-shot path goes through _check_once directly, not _wait_with_condition,
        so save is NOT called for single-shot. This test documents that behavior.
        """
        saved = []

        def save(desc, result):
            saved.append((desc, result))

        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: (1, 2),
            window_validity_fn=lambda: False,
            on_failure_save_fn=save,
        )
        r = h.check_exist("x.png")  # single-shot
        assert r.success is False
        assert r.is_interrupted is True
        # Single-shot does NOT invoke save (only _wait_with_condition does)
        assert len(saved) == 0

    def test_save_desc_format(self):
        """save callback receives desc in format '{vt.value} - {target}'."""
        saved_desc = {"value": None}

        def save(desc, result):
            saved_desc["value"] = desc

        h = VerifyHandler(
            screenshot_fn=lambda: b"\x89PNG",
            template_match_fn=lambda *_: None,
            check_interval=0.05,
            on_failure_save_fn=save,
        )
        h.verify(VerifyType.EXIST, "my_template.png", timeout=0.2)
        assert saved_desc["value"] == "exist - my_template.png"
