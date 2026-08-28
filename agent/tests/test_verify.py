"""Verifier 模块单元测试 (spec 阶段 3 — 任务 3.1).

Verifies the 6 verify types extracted from TaskOrchestrator._run_verify:
  - template / color / exist / disappear / text / custom_verify

The Verifier is constructed with 4 callable hooks (screenshot_fn /
template_match_fn / color_pick_fn / ocr_registry_fn), so tests use plain
MagicMock functions — no Django / device / OCR engine setup needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure src on path (conftest already does this, but be explicit for direct runs)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.result import AutoResult
from core.verify import Verifier

pytestmark = pytest.mark.unit


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_deps():
    """Build 4 MagicMock callables for Verifier construction."""
    screenshot_fn = MagicMock(return_value=None)
    template_match_fn = MagicMock(return_value=None)
    color_pick_fn = MagicMock(return_value=None)
    ocr_registry_fn = MagicMock(return_value=None)
    return screenshot_fn, template_match_fn, color_pick_fn, ocr_registry_fn


@pytest.fixture
def verifier(mock_deps):
    """Build a Verifier with mocked deps."""
    return Verifier(*mock_deps)


# ============================================================
# SUPPORTED_TYPES + dispatch
# ============================================================

class TestSupportedTypes:
    """Verifier.SUPPORTED_TYPES enumerates the 6 verify types."""

    def test_supported_types_contains_all_6(self):
        assert frozenset({
            "template", "color", "exist", "disappear", "text", "custom_verify",
        }) == Verifier.SUPPORTED_TYPES

    def test_unknown_type_returns_fail(self, verifier):
        result = verifier.verify({"type": "magic"})
        assert result.success is False
        assert "未知验证类型" in result.error_msg


# ============================================================
# template verify
# ============================================================

class TestTemplateVerify:
    def test_template_match_success(self, verifier, mock_deps):
        screenshot_fn, template_match_fn, _, _ = mock_deps
        template_match_fn.return_value = {"x": 10, "y": 20, "confidence": 0.95}

        result = verifier.verify({"type": "template", "template": "t.png"})

        assert result.success is True
        assert result.data == {"x": 10, "y": 20, "confidence": 0.95}
        screenshot_fn.assert_called_once()
        template_match_fn.assert_called_once()
        # Verify threshold default + roi pass-through
        _, kwargs = template_match_fn.call_args
        assert kwargs["threshold"] == 0.8
        assert kwargs["roi"] is None

    def test_template_match_failure(self, verifier, mock_deps):
        _, template_match_fn, _, _ = mock_deps
        template_match_fn.return_value = None

        result = verifier.verify({"type": "template", "template": "t.png"})

        assert result.success is False
        assert "模板未匹配" in result.error_msg

    def test_template_passes_threshold_and_roi(self, verifier, mock_deps):
        _, template_match_fn, _, _ = mock_deps
        template_match_fn.return_value = {"x": 1, "y": 1}

        verifier.verify({
            "type": "template", "template": "t.png",
            "threshold": 0.95, "roi": {"x": 0, "y": 0, "w": 100, "h": 100},
        })

        _, kwargs = template_match_fn.call_args
        assert kwargs["threshold"] == 0.95
        assert kwargs["roi"] == {"x": 0, "y": 0, "w": 100, "h": 100}


# ============================================================
# color verify
# ============================================================

class TestColorVerify:
    def test_color_match_success(self, verifier, mock_deps):
        _, _, color_pick_fn, _ = mock_deps
        color_pick_fn.return_value = {"x": 5, "y": 5}

        result = verifier.verify({"type": "color", "color": [255, 0, 0]})

        assert result.success is True
        assert result.data == {"x": 5, "y": 5}

    def test_color_match_failure(self, verifier, mock_deps):
        _, _, color_pick_fn, _ = mock_deps
        color_pick_fn.return_value = None

        result = verifier.verify({"type": "color", "color": [255, 0, 0]})

        assert result.success is False
        assert "颜色未匹配" in result.error_msg


# ============================================================
# exist / disappear verify
# ============================================================

class TestExistDisappearVerify:
    def test_exist_template_present(self, verifier, mock_deps):
        _, template_match_fn, _, _ = mock_deps
        template_match_fn.return_value = {"x": 1, "y": 1}

        result = verifier.verify({
            "type": "exist", "element": "template", "template": "t.png",
        })

        assert result.success is True

    def test_exist_template_absent(self, verifier, mock_deps):
        _, template_match_fn, _, _ = mock_deps
        template_match_fn.return_value = None

        result = verifier.verify({
            "type": "exist", "element": "template", "template": "t.png",
        })

        assert result.success is False
        assert "未存在" in result.error_msg

    def test_disappear_template_absent(self, verifier, mock_deps):
        """'disappear' with element not found → success."""
        _, template_match_fn, _, _ = mock_deps
        template_match_fn.return_value = None

        result = verifier.verify({
            "type": "disappear", "element": "template", "template": "t.png",
        })

        assert result.success is True

    def test_disappear_template_still_present(self, verifier, mock_deps):
        """'disappear' but element still present → fail."""
        _, template_match_fn, _, _ = mock_deps
        template_match_fn.return_value = {"x": 1, "y": 1}

        result = verifier.verify({
            "type": "disappear", "element": "template", "template": "t.png",
        })

        assert result.success is False
        assert "未消失" in result.error_msg

    def test_exist_color_element(self, verifier, mock_deps):
        """'exist' with element=color should route to color_pick_fn."""
        _, _, color_pick_fn, _ = mock_deps
        color_pick_fn.return_value = {"x": 10, "y": 10}

        result = verifier.verify({
            "type": "exist", "element": "color", "color": [0, 255, 0],
        })

        assert result.success is True
        color_pick_fn.assert_called_once()

    def test_exist_unknown_element(self, verifier):
        result = verifier.verify({
            "type": "exist", "element": "audio", "template": "t.png",
        })
        assert result.success is False
        assert "未知 element 类型" in result.error_msg

    def test_exist_defaults_to_template_element(self, verifier, mock_deps):
        """'exist' without 'element' key defaults to 'template'."""
        _, template_match_fn, _, _ = mock_deps
        template_match_fn.return_value = {"x": 1, "y": 1}

        result = verifier.verify({"type": "exist", "template": "t.png"})

        assert result.success is True
        template_match_fn.assert_called_once()


# ============================================================
# text verify (OCR)
# ============================================================

class TestTextVerify:
    def test_text_missing_text_param(self, verifier):
        """'text' verify without 'text' key → fail early (no OCR call)."""
        result = verifier.verify({"type": "text"})
        assert result.success is False
        assert "'text' 参数" in result.error_msg

    def test_text_no_ocr_module_installed(self, verifier, monkeypatch):
        """When recognition.ocr.registry is not installed → fail with clear message."""
        # Simulate the importlib.util.find_spec returning None
        import importlib.util
        monkeypatch.setattr(
            importlib.util, "find_spec",
            lambda name: None if name == "recognition.ocr.registry" else MagicMock(),
        )

        result = verifier.verify({"type": "text", "text": "登录"})

        assert result.success is False
        assert "OCR 模块不可用" in result.error_msg

    def test_text_no_engine_registered(self, verifier, monkeypatch, mock_deps):
        """OCR module present but registry returns None → fail."""
        _, _, _, ocr_registry_fn = mock_deps
        ocr_registry_fn.return_value = None
        # Make find_spec succeed so we reach the registry check
        import importlib.util
        monkeypatch.setattr(
            importlib.util, "find_spec",
            lambda name: MagicMock(),  # truthy
        )

        result = verifier.verify({"type": "text", "text": "登录"})

        assert result.success is False
        assert "无 OCR 引擎已注册" in result.error_msg

    def test_text_match_success(self, verifier, monkeypatch, mock_deps):
        """OCR returns a result containing expected text → success."""
        _, _, _, ocr_registry_fn = mock_deps
        # Build mock OCR result
        ocr_result = MagicMock()
        ocr_result.text = "欢迎登录游戏"
        ocr_result.confidence = 0.95
        ocr_result.box = [10, 20, 100, 40]
        # Build mock engine + registry
        engine = MagicMock()
        engine.recognize.return_value = [ocr_result]
        registry = MagicMock()
        registry.engine_names = ["rapid"]
        registry._benchmarked = False
        registry.get_engine.return_value = engine
        ocr_registry_fn.return_value = registry
        # find_spec succeeds
        import importlib.util
        monkeypatch.setattr(
            importlib.util, "find_spec", lambda name: MagicMock(),
        )

        result = verifier.verify({"type": "text", "text": "登录"})

        assert result.success is True
        assert result.data["text"] == "欢迎登录游戏"
        assert result.data["confidence"] == 0.95
        assert result.data["box"] == [10, 20, 100, 40]

    def test_text_low_confidence_filtered(self, verifier, monkeypatch, mock_deps):
        """OCR result below threshold is skipped."""
        _, _, _, ocr_registry_fn = mock_deps
        ocr_result = MagicMock()
        ocr_result.text = "登录"
        ocr_result.confidence = 0.3  # below default 0.5
        ocr_result.box = [10, 20, 100, 40]
        engine = MagicMock()
        engine.recognize.return_value = [ocr_result]
        registry = MagicMock()
        registry.engine_names = ["rapid"]
        registry._benchmarked = False
        registry.get_engine.return_value = engine
        ocr_registry_fn.return_value = registry
        import importlib.util
        monkeypatch.setattr(
            importlib.util, "find_spec", lambda name: MagicMock(),
        )

        result = verifier.verify({"type": "text", "text": "登录"})

        assert result.success is False
        assert "文本未匹配" in result.error_msg

    def test_text_uses_roi_when_provided(self, verifier, monkeypatch, mock_deps):
        """ROI crop is applied to screenshot before OCR."""
        screenshot_fn, _, _, ocr_registry_fn = mock_deps
        import numpy as np
        full_screen = np.zeros((200, 200, 3), dtype=np.uint8)
        screenshot_fn.return_value = full_screen

        ocr_result = MagicMock()
        ocr_result.text = "登录"
        ocr_result.confidence = 0.9
        ocr_result.box = [0, 0, 50, 20]
        engine = MagicMock()
        engine.recognize.return_value = [ocr_result]
        registry = MagicMock()
        registry.engine_names = ["rapid"]
        registry._benchmarked = False
        registry.get_engine.return_value = engine
        ocr_registry_fn.return_value = registry
        import importlib.util
        monkeypatch.setattr(
            importlib.util, "find_spec", lambda name: MagicMock(),
        )

        verifier.verify({
            "type": "text", "text": "登录",
            "roi": {"x": 10, "y": 20, "w": 100, "h": 50},
        })

        # engine.recognize should receive the cropped screenshot (shape 50x100)
        args, _ = engine.recognize.call_args
        cropped = args[0]
        assert cropped.shape == (50, 100, 3)


# ============================================================
# custom_verify
# ============================================================

class TestCustomVerify:
    def test_custom_missing_module(self, verifier):
        result = verifier.verify({"type": "custom_verify", "function": "f"})
        assert result.success is False
        assert "module" in result.error_msg

    def test_custom_missing_function(self, verifier):
        result = verifier.verify({"type": "custom_verify", "module": "m"})
        assert result.success is False
        assert "module" in result.error_msg  # error mentions both

    def test_custom_load_failure(self, verifier, monkeypatch):
        """import_module raises ImportError → fail_result."""
        import importlib
        monkeypatch.setattr(
            importlib, "import_module",
            lambda name: (_ for _ in ()).throw(ImportError("nope")),
        )

        result = verifier.verify({
            "type": "custom_verify", "module": "x", "function": "y",
        })

        assert result.success is False
        assert "custom_verify 加载失败" in result.error_msg

    def test_custom_callable_raises(self, verifier, monkeypatch, mock_deps):
        """Custom callable raises → fail_result."""
        screenshot_fn, _, _, _ = mock_deps
        screenshot_fn.return_value = b"fake-screenshot"

        # Create a fake module with a function that raises
        import sys
        fake_module = MagicMock()
        fake_module.my_verify = MagicMock(side_effect=RuntimeError("boom"))
        monkeypatch.setitem(sys.modules, "fake_verifiers", fake_module)

        result = verifier.verify({
            "type": "custom_verify",
            "module": "fake_verifiers", "function": "my_verify",
        })

        assert result.success is False
        assert "custom_verify 执行失败" in result.error_msg
        assert "boom" in result.error_msg

    def test_custom_returns_non_autoresult(self, verifier, monkeypatch, mock_deps):
        """Custom callable returns non-AutoResult → fail_result."""
        screenshot_fn, _, _, _ = mock_deps
        screenshot_fn.return_value = b"fake-screenshot"

        import sys
        fake_module = MagicMock()
        fake_module.my_verify = MagicMock(return_value={"oops": "dict"})
        monkeypatch.setitem(sys.modules, "fake_verifiers", fake_module)

        result = verifier.verify({
            "type": "custom_verify",
            "module": "fake_verifiers", "function": "my_verify",
        })

        assert result.success is False
        assert "返回类型错误" in result.error_msg
        assert "AutoResult" in result.error_msg

    def test_custom_returns_autoresult(self, verifier, monkeypatch, mock_deps):
        """Custom callable returns AutoResult → forwarded as-is."""
        screenshot_fn, _, _, _ = mock_deps
        screenshot_fn.return_value = b"fake-screenshot"

        import sys
        expected = AutoResult(success=True, data={"checked": True})
        fake_module = MagicMock()
        fake_module.my_verify = MagicMock(return_value=expected)
        monkeypatch.setitem(sys.modules, "fake_verifiers", fake_module)

        result = verifier.verify({
            "type": "custom_verify",
            "module": "fake_verifiers", "function": "my_verify",
            "args": {"extra": "kwarg"},
        })

        assert result.success is True
        assert result.data == {"checked": True}
        # Verify extra args forwarded
        _, kwargs = fake_module.my_verify.call_args
        assert kwargs == {"extra": "kwarg"}


# ============================================================
# Exception isolation
# ============================================================

class TestExceptionIsolation:
    """verify() must catch exceptions and convert to fail_result."""

    def test_screenshot_fn_exception_returns_fail(self, mock_deps):
        screenshot_fn, _, _, _ = mock_deps
        screenshot_fn.side_effect = RuntimeError("device disconnected")
        verifier = Verifier(*mock_deps)

        result = verifier.verify({"type": "template", "template": "t.png"})

        assert result.success is False
        assert "device disconnected" in result.error_msg

    def test_template_match_fn_exception_returns_fail(self, mock_deps):
        _, template_match_fn, _, _ = mock_deps
        template_match_fn.side_effect = ValueError("bad template")
        verifier = Verifier(*mock_deps)

        result = verifier.verify({"type": "template", "template": "t.png"})

        assert result.success is False
        assert "bad template" in result.error_msg
