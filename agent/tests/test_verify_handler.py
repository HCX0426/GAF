"""VerifyHandler 6 verify types unit tests (N126-F1).

Covers _run_verify dispatch and the 4 newly added verify types:
- exist (template/color element must be present)
- disappear (template/color element must be absent)
- text (OCR must find expected text)
- custom_verify (user-provided callable via module:function)

Also covers backward compatibility for existing template/color verify types.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

# Ensure src on path (conftest already does this, but be explicit for direct runs)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.orchestrator import TaskOrchestrator

pytestmark = pytest.mark.unit

# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_orchestrator():
    """Build orchestrator with mocked device_manager and image_processor."""
    device_manager = MagicMock()
    image_processor = MagicMock()
    config = MagicMock()
    orchestrator = TaskOrchestrator(
        device_manager=device_manager,
        image_processor=image_processor,
        config=config,
    )
    # Default: capture_screen returns a dummy 100x100 BGR image
    device_manager.get_active_device.return_value.capture_screen.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
    return orchestrator, device_manager, image_processor


# ============================================================
# Backward compatibility: template + color verify
# ============================================================

class TestTemplateVerify:
    """Existing template verify type must still work."""

    def test_template_verify_success(self, mock_orchestrator):
        orch, _, img_proc = mock_orchestrator
        img_proc.find_template.return_value = {"x": 10, "y": 20, "confidence": 0.9}
        result = orch._run_verify({"type": "template", "template": "/tmp/t.png"})
        assert result.success is True
        assert result.data == {"x": 10, "y": 20, "confidence": 0.9}

    def test_template_verify_fail(self, mock_orchestrator):
        orch, _, img_proc = mock_orchestrator
        img_proc.find_template.return_value = None
        result = orch._run_verify({"type": "template", "template": "/tmp/t.png"})
        assert result.success is False
        assert "模板未匹配" in result.error_msg


class TestColorVerify:
    """Existing color verify type must still work."""

    def test_color_verify_success(self, mock_orchestrator):
        orch, _, img_proc = mock_orchestrator
        img_proc.find_color.return_value = {"x": 50, "y": 60}
        result = orch._run_verify({"type": "color", "color": "#FF0000"})
        assert result.success is True
        assert result.data == {"x": 50, "y": 60}

    def test_color_verify_fail(self, mock_orchestrator):
        orch, _, img_proc = mock_orchestrator
        img_proc.find_color.return_value = None
        result = orch._run_verify({"type": "color", "color": "#FF0000"})
        assert result.success is False
        assert "颜色未匹配" in result.error_msg


# ============================================================
# New: exist verify (N126-F1)
# ============================================================

class TestExistVerify:
    """exist verify: element must be present on screen."""

    def test_exist_template_present(self, mock_orchestrator):
        orch, _, img_proc = mock_orchestrator
        img_proc.find_template.return_value = {"x": 10, "y": 20, "confidence": 0.9}
        result = orch._run_verify({
            "type": "exist",
            "element": "template",
            "template": "/tmp/t.png",
        })
        assert result.success is True

    def test_exist_template_absent(self, mock_orchestrator):
        orch, _, img_proc = mock_orchestrator
        img_proc.find_template.return_value = None
        result = orch._run_verify({
            "type": "exist",
            "element": "template",
            "template": "/tmp/t.png",
        })
        assert result.success is False
        assert "元素未存在" in result.error_msg

    def test_exist_color_present(self, mock_orchestrator):
        orch, _, img_proc = mock_orchestrator
        img_proc.find_color.return_value = {"x": 50, "y": 60}
        result = orch._run_verify({
            "type": "exist",
            "element": "color",
            "color": "#00FF00",
        })
        assert result.success is True

    def test_exist_color_absent(self, mock_orchestrator):
        orch, _, img_proc = mock_orchestrator
        img_proc.find_color.return_value = None
        result = orch._run_verify({
            "type": "exist",
            "element": "color",
            "color": "#00FF00",
        })
        assert result.success is False
        assert "元素未存在" in result.error_msg

    def test_exist_unknown_element_type(self, mock_orchestrator):
        orch, _, _ = mock_orchestrator
        result = orch._run_verify({
            "type": "exist",
            "element": "unknown_type",
        })
        assert result.success is False
        assert "未知 element 类型" in result.error_msg

    def test_exist_default_element_is_template(self, mock_orchestrator):
        """If 'element' key omitted, default to 'template'."""
        orch, _, img_proc = mock_orchestrator
        img_proc.find_template.return_value = {"x": 1, "y": 2, "confidence": 0.8}
        result = orch._run_verify({"type": "exist", "template": "/tmp/t.png"})
        assert result.success is True


# ============================================================
# New: disappear verify (N126-F1)
# ============================================================

class TestDisappearVerify:
    """disappear verify: element must NOT be present on screen."""

    def test_disappear_template_absent_success(self, mock_orchestrator):
        orch, _, img_proc = mock_orchestrator
        img_proc.find_template.return_value = None
        result = orch._run_verify({
            "type": "disappear",
            "element": "template",
            "template": "/tmp/t.png",
        })
        assert result.success is True

    def test_disappear_template_present_fail(self, mock_orchestrator):
        orch, _, img_proc = mock_orchestrator
        img_proc.find_template.return_value = {"x": 10, "y": 20, "confidence": 0.9}
        result = orch._run_verify({
            "type": "disappear",
            "element": "template",
            "template": "/tmp/t.png",
        })
        assert result.success is False
        assert "元素未消失" in result.error_msg

    def test_disappear_color_absent_success(self, mock_orchestrator):
        orch, _, img_proc = mock_orchestrator
        img_proc.find_color.return_value = None
        result = orch._run_verify({
            "type": "disappear",
            "element": "color",
            "color": "#FF0000",
        })
        assert result.success is True

    def test_disappear_color_present_fail(self, mock_orchestrator):
        orch, _, img_proc = mock_orchestrator
        img_proc.find_color.return_value = {"x": 50, "y": 60}
        result = orch._run_verify({
            "type": "disappear",
            "element": "color",
            "color": "#FF0000",
        })
        assert result.success is False
        assert "元素未消失" in result.error_msg


# ============================================================
# New: text verify (N126-F1) via OCR
# ============================================================

class TestTextVerify:
    """text verify: OCR must find expected text in screenshot/ROI."""

    def test_text_missing_text_param(self, mock_orchestrator):
        orch, _, _ = mock_orchestrator
        result = orch._run_verify({"type": "text"})
        assert result.success is False
        assert "缺少 'text' 参数" in result.error_msg

    def test_text_no_engine_registered(self, mock_orchestrator):
        orch, _, _ = mock_orchestrator
        # Force registry to exist but be empty
        orch._ocr_registry = MagicMock()
        orch._ocr_registry.engine_names = []
        orch._ocr_registry._benchmarked = False
        result = orch._run_verify({"type": "text", "text": "登录"})
        assert result.success is False
        assert "无 OCR 引擎已注册" in result.error_msg

    def test_text_match_success(self, mock_orchestrator):
        orch, _, _ = mock_orchestrator
        # Build mock registry + engine
        mock_result = MagicMock()
        mock_result.text = "欢迎登录游戏"
        mock_result.confidence = 0.95
        mock_result.box = (10, 20, 100, 40)
        mock_engine = MagicMock()
        mock_engine.recognize.return_value = [mock_result]
        orch._ocr_registry = MagicMock()
        orch._ocr_registry.engine_names = ["rapid"]
        orch._ocr_registry._benchmarked = False
        orch._ocr_registry.get_engine.return_value = mock_engine
        result = orch._run_verify({"type": "text", "text": "登录"})
        assert result.success is True
        assert result.data["text"] == "欢迎登录游戏"
        assert result.data["confidence"] == 0.95

    def test_text_no_match(self, mock_orchestrator):
        orch, _, _ = mock_orchestrator
        mock_result = MagicMock()
        mock_result.text = "其他文字"
        mock_result.confidence = 0.9
        mock_result.box = (0, 0, 50, 20)
        mock_engine = MagicMock()
        mock_engine.recognize.return_value = [mock_result]
        orch._ocr_registry = MagicMock()
        orch._ocr_registry.engine_names = ["rapid"]
        orch._ocr_registry._benchmarked = False
        orch._ocr_registry.get_engine.return_value = mock_engine
        result = orch._run_verify({"type": "text", "text": "登录"})
        assert result.success is False
        assert "文本未匹配" in result.error_msg

    def test_text_low_confidence_filtered(self, mock_orchestrator):
        orch, _, _ = mock_orchestrator
        mock_result = MagicMock()
        mock_result.text = "登录"
        mock_result.confidence = 0.3  # Below default threshold 0.5
        mock_result.box = (0, 0, 50, 20)
        mock_engine = MagicMock()
        mock_engine.recognize.return_value = [mock_result]
        orch._ocr_registry = MagicMock()
        orch._ocr_registry.engine_names = ["rapid"]
        orch._ocr_registry._benchmarked = False
        orch._ocr_registry.get_engine.return_value = mock_engine
        result = orch._run_verify({"type": "text", "text": "登录"})
        assert result.success is False
        assert "文本未匹配" in result.error_msg

    def test_text_with_roi_crops_screenshot(self, mock_orchestrator):
        orch, dev_mgr, _ = mock_orchestrator
        mock_engine = MagicMock()
        mock_engine.recognize.return_value = []
        orch._ocr_registry = MagicMock()
        orch._ocr_registry.engine_names = ["rapid"]
        orch._ocr_registry._benchmarked = False
        orch._ocr_registry.get_engine.return_value = mock_engine
        orch._run_verify({
            "type": "text",
            "text": "x",
            "roi": {"x": 10, "y": 20, "w": 30, "h": 40},
        })
        # Verify recognize was called with a cropped array (shape 40x30x3)
        called_arg = mock_engine.recognize.call_args[0][0]
        assert called_arg.shape == (40, 30, 3)


# ============================================================
# New: custom_verify (N126-F1)
# ============================================================

class TestCustomVerify:
    """custom_verify: invoke user-provided callable via module:function."""

    def test_custom_missing_module_param(self, mock_orchestrator):
        orch, _, _ = mock_orchestrator
        result = orch._run_verify({"type": "custom_verify", "function": "foo"})
        assert result.success is False
        assert "缺少 'module' 或 'function' 参数" in result.error_msg

    def test_custom_missing_function_param(self, mock_orchestrator):
        orch, _, _ = mock_orchestrator
        result = orch._run_verify({"type": "custom_verify", "module": "foo"})
        assert result.success is False
        assert "缺少 'module' 或 'function' 参数" in result.error_msg

    def test_custom_module_not_found(self, mock_orchestrator):
        orch, _, _ = mock_orchestrator
        result = orch._run_verify({
            "type": "custom_verify",
            "module": "nonexistent_module_xyz",
            "function": "foo",
        })
        assert result.success is False
        assert "custom_verify 加载失败" in result.error_msg

    def test_custom_function_not_found(self, mock_orchestrator):
        orch, _, _ = mock_orchestrator
        # Use a real module but a nonexistent function
        result = orch._run_verify({
            "type": "custom_verify",
            "module": "core.result",
            "function": "nonexistent_function_xyz",
        })
        assert result.success is False
        assert "custom_verify 加载失败" in result.error_msg

    def test_custom_success(self, mock_orchestrator, tmp_path):
        orch, _, _ = mock_orchestrator
        # Write a temporary module that defines a verify function
        module_dir = tmp_path / "custom_verifiers"
        module_dir.mkdir()
        module_file = module_dir / "my_verifier.py"
        module_file.write_text(
            "from core.result import success_result\n"
            "def check_login(screenshot, verify, **kwargs):\n"
            "    return success_result(data={'verified': True})\n"
        )
        sys.path.insert(0, str(module_dir))
        try:
            result = orch._run_verify({
                "type": "custom_verify",
                "module": "my_verifier",
                "function": "check_login",
            })
            assert result.success is True
            assert result.data == {"verified": True}
        finally:
            sys.path.remove(str(module_dir))

    def test_custom_wrong_return_type(self, mock_orchestrator, tmp_path):
        orch, _, _ = mock_orchestrator
        module_dir = tmp_path / "custom_verifiers_bad"
        module_dir.mkdir()
        module_file = module_dir / "bad_verifier.py"
        module_file.write_text(
            "def bad_check(screenshot, verify, **kwargs):\n"
            "    return 'not an AutoResult'\n"
        )
        sys.path.insert(0, str(module_dir))
        try:
            result = orch._run_verify({
                "type": "custom_verify",
                "module": "bad_verifier",
                "function": "bad_check",
            })
            assert result.success is False
            assert "返回类型错误" in result.error_msg
        finally:
            sys.path.remove(str(module_dir))

    def test_custom_raises_exception(self, mock_orchestrator, tmp_path):
        orch, _, _ = mock_orchestrator
        module_dir = tmp_path / "custom_verifiers_exc"
        module_dir.mkdir()
        module_file = module_dir / "exc_verifier.py"
        module_file.write_text(
            "def exc_check(screenshot, verify, **kwargs):\n"
            "    raise RuntimeError('intentional error')\n"
        )
        sys.path.insert(0, str(module_dir))
        try:
            result = orch._run_verify({
                "type": "custom_verify",
                "module": "exc_verifier",
                "function": "exc_check",
            })
            assert result.success is False
            assert "custom_verify 执行失败" in result.error_msg
            assert "intentional error" in result.error_msg
        finally:
            sys.path.remove(str(module_dir))


# ============================================================
# Unknown verify type
# ============================================================

class TestUnknownVerifyType:
    """Unknown verify type must return fail_result with clear message."""

    def test_unknown_type(self, mock_orchestrator):
        orch, _, _ = mock_orchestrator
        result = orch._run_verify({"type": "unknown_xyz"})
        assert result.success is False
        assert "未知验证类型" in result.error_msg


# ============================================================
# OCR engine registration
# ============================================================

class TestRegisterOCREngine:
    """register_ocr_engine should delegate to OCREngineRegistry."""

    def test_register_with_registry_available(self, mock_orchestrator):
        orch, _, _ = mock_orchestrator
        orch._ocr_registry = MagicMock()
        mock_engine = MagicMock()
        orch.register_ocr_engine(mock_engine, "test_engine")
        orch._ocr_registry.register.assert_called_once_with(mock_engine, "test_engine")

    def test_register_with_registry_none(self, mock_orchestrator):
        orch, _, _ = mock_orchestrator
        orch._ocr_registry = None  # Simulate ImportError
        mock_engine = MagicMock()
        # Should not raise, just log warning
        orch.register_ocr_engine(mock_engine, "test_engine")
        # No assertion needed — just verify no exception raised
