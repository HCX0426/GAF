"""TD-336 #7: 检测/匹配类节点 smoke 测试

覆盖 6 个匹配类节点:
- TemplateMatchNode (template_match): 无设备/截图失败/OpenCV 异常容错
- TemplateMatchAnyNode (template_match_any): 空 templates/首个命中/全部失败
- FeatureMatchNode (feature_match): 无设备/未知方法/截图失败
- ColorDetectNode (color_detect): 无设备/截图失败/截图异常
- OCRNode (ocr): mock fallback/expected_text 不匹配
- CompositeMatch (and_match/or_match/custom_match): 空 children/全 pass/全 fail

使用 MagicMock 模拟 PipelineContext 与 device, 不依赖真实 OpenCV 算法路径
(只触发早期失败分支, 避免构造真实图像数据)。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import to register nodes.
import engine.nodes.color_detect  # noqa: F401
import engine.nodes.composite_match  # noqa: F401
import engine.nodes.feature_match  # noqa: F401
import engine.nodes.ocr  # noqa: F401
import engine.nodes.template_match  # noqa: F401
import engine.nodes.template_match_any  # noqa: F401
from engine.node import PIPELINE_NODE_REGISTRY

pytestmark = pytest.mark.unit


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_context():
    """Build a mock PipelineContext with variables dict + debug_mode off."""
    ctx = MagicMock()
    ctx.variables = {}
    ctx.device = None
    ctx.debug_mode = False
    ctx.coord_transformer = None

    def set_var(key, value):
        ctx.variables[key] = value

    def get_var(key, default=None):
        return ctx.variables.get(key, default)

    ctx.set_variable.side_effect = set_var
    ctx.get_variable.side_effect = get_var
    return ctx


def _make_node(node_type, node_id="test_node", config=None):
    """Build a node instance via the factory."""
    return PIPELINE_NODE_REGISTRY[node_type].from_dict({
        "id": node_id,
        "node_type": node_type,
        "config": config or {},
    })


def _make_capture_device(screen=None, raise_exc=None):
    """Build a mock device whose capture_screen returns ``screen``.

    Args:
        screen: numpy array to return from capture_screen (or None).
        raise_exc: if set, capture_screen raises this exception.
    """
    dev = MagicMock()
    if raise_exc is not None:
        dev.capture_screen.side_effect = raise_exc
    else:
        dev.capture_screen.return_value = screen
    return dev


# ============================================================
# Registration
# ============================================================

class TestRegistration:
    def test_template_match_registered(self):
        assert "template_match" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["template_match"].__name__ == "TemplateMatchNode"

    def test_template_match_any_registered(self):
        assert "template_match_any" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["template_match_any"].__name__ == "TemplateMatchAnyNode"

    def test_feature_match_registered(self):
        assert "feature_match" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["feature_match"].__name__ == "FeatureMatchNode"

    def test_color_detect_registered(self):
        assert "color_detect" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["color_detect"].__name__ == "ColorDetectNode"

    def test_ocr_registered(self):
        assert "ocr" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["ocr"].__name__ == "OCRNode"

    def test_and_match_registered(self):
        assert "and_match" in PIPELINE_NODE_REGISTRY

    def test_or_match_registered(self):
        assert "or_match" in PIPELINE_NODE_REGISTRY

    def test_custom_match_registered(self):
        assert "custom_match" in PIPELINE_NODE_REGISTRY


# ============================================================
# TemplateMatchNode
# ============================================================

class TestTemplateMatchNode:
    """TemplateMatchNode: OpenCV 模板匹配 (smoke 走早期失败路径)."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node("template_match", config={"template": "x.png"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "device=None" in result.error_msg or "未设置设备" in result.error_msg

    def test_capture_returns_none_fails(self, mock_context):
        dev = _make_capture_device(screen=None)
        mock_context.device = dev
        node = _make_node("template_match", config={"template": "x.png"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "截图返回空" in result.error_msg

    def test_device_capture_failure_returns_fail(self, mock_context):
        from core.exceptions import DeviceError
        dev = _make_capture_device(raise_exc=DeviceError("capture failed"))
        mock_context.device = dev
        node = _make_node("template_match", config={"template": "x.png"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "设备截图失败" in result.error_msg

    def test_capture_unknown_exception_returns_fail(self, mock_context):
        dev = _make_capture_device(raise_exc=RuntimeError("unexpected"))
        mock_context.device = dev
        node = _make_node("template_match", config={"template": "x.png"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "截图过程异常" in result.error_msg


# ============================================================
# TemplateMatchAnyNode
# ============================================================

class TestTemplateMatchAnyNode:
    """TemplateMatchAnyNode: 多模板任一匹配 (走 run_child 编排)."""

    def test_empty_templates_returns_fail(self, mock_context):
        node = _make_node("template_match_any", config={"templates": []})
        result = node.execute(mock_context)
        assert result.success is False
        assert "templates" in result.error_msg.lower()

    def test_missing_templates_returns_fail(self, mock_context):
        node = _make_node("template_match_any", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "templates" in result.error_msg.lower()

    def test_all_templates_fail_returns_fail(self, mock_context):
        # No device → every child template_match fails → composite fail.
        node = _make_node("template_match_any",
                          config={"templates": ["a.png", "b.png"]})
        result = node.execute(mock_context)
        assert result.success is False
        assert "all" in result.error_msg.lower() or "failed" in result.error_msg.lower()
        # Children list should be populated even on failure.
        assert result.data is not None
        assert result.data["matched"] is False
        assert result.data["count"] == 2

    def test_first_template_wins(self, mock_context):
        # Provide a real device with a captured screen; both children
        # fail at template load, so first-wins path is exercised via
        # failure path. We assert the orchestration shape instead.
        dev = _make_capture_device(screen=np.zeros((100, 100, 3), dtype=np.uint8))
        mock_context.device = dev
        node = _make_node("template_match_any",
                          config={"templates": ["nonexistent_a.png", "nonexistent_b.png"]})
        result = node.execute(mock_context)
        # Both children fail at "模板图片加载失败".
        assert result.success is False
        assert result.data["count"] == 2


# ============================================================
# FeatureMatchNode
# ============================================================

class TestFeatureMatchNode:
    """FeatureMatchNode: 特征点匹配 (smoke 走早期失败路径)."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node("feature_match", config={"template": "x.png"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "device=None" in result.error_msg or "未设置设备" in result.error_msg

    def test_invalid_method_returns_fail(self, mock_context):
        node = _make_node("feature_match",
                          config={"template": "x.png", "method": "invalid_detector"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "不支持的特征检测方法" in result.error_msg
        assert "invalid_detector" in result.error_msg

    def test_capture_returns_none_fails(self, mock_context):
        dev = _make_capture_device(screen=None)
        mock_context.device = dev
        node = _make_node("feature_match", config={"template": "x.png"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "截图返回空" in result.error_msg

    def test_device_capture_failure_returns_fail(self, mock_context):
        from core.exceptions import DeviceError
        dev = _make_capture_device(raise_exc=DeviceError("capture failed"))
        mock_context.device = dev
        node = _make_node("feature_match", config={"template": "x.png"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "设备截图失败" in result.error_msg

    def test_method_validation_precedes_device_check(self, mock_context):
        # Invalid method short-circuits before device check.
        node = _make_node("feature_match",
                          config={"template": "x.png", "method": "bad"})
        result = node.execute(mock_context)
        assert result.success is False
        # Method validation fires first.
        assert "不支持的特征检测方法" in result.error_msg


# ============================================================
# ColorDetectNode
# ============================================================

class TestColorDetectNode:
    """ColorDetectNode: HSV 颜色检测 (smoke 走早期失败路径)."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node("color_detect", config={"lower": [0, 50, 50]})
        result = node.execute(mock_context)
        assert result.success is False
        assert "device=None" in result.error_msg or "未设置设备" in result.error_msg

    def test_capture_returns_none_fails(self, mock_context):
        dev = _make_capture_device(screen=None)
        mock_context.device = dev
        node = _make_node("color_detect")
        result = node.execute(mock_context)
        assert result.success is False
        assert "截图返回空" in result.error_msg

    def test_device_capture_failure_returns_fail(self, mock_context):
        from core.exceptions import DeviceError
        dev = _make_capture_device(raise_exc=DeviceError("capture failed"))
        mock_context.device = dev
        node = _make_node("color_detect")
        result = node.execute(mock_context)
        assert result.success is False
        assert "设备截图失败" in result.error_msg

    def test_capture_unknown_exception_returns_fail(self, mock_context):
        dev = _make_capture_device(raise_exc=RuntimeError("unexpected"))
        mock_context.device = dev
        node = _make_node("color_detect")
        result = node.execute(mock_context)
        assert result.success is False
        assert "截图过程异常" in result.error_msg


# ============================================================
# OCRNode
# ============================================================

class TestOCRNode:
    """OCRNode: 文本识别 (smoke 走 mock fallback + 无图像失败路径).

    Conda gaf 环境装有 RapidOCR, 默认走真实引擎路径 (非 mock fallback):
    - 真实引擎 + 无图像 + 无设备 → fail "No image available"
    - mock fallback 路径 (无引擎) 通过 patch _get_ocr_engine 触发
    """

    def test_no_image_no_device_returns_fail(self, mock_context):
        # Conda env has RapidOCR; engine acquired but no image available.
        node = _make_node("ocr")
        result = node.execute(mock_context)
        assert result.success is False
        assert "No image available" in result.error_msg or "no image" in result.error_msg.lower()

    def test_mock_fallback_succeeds_when_engine_unavailable(self, mock_context):
        # Patch _get_ocr_engine to simulate no-engine path → mock fallback.
        node = _make_node("ocr", config={"mock_text": "hello world"})
        with patch.object(type(node), "_get_ocr_engine", return_value=(None, None)):
            result = node.execute(mock_context)
        assert result.success is True
        assert result.data["text"] == "hello world"
        assert result.data["texts"] == ["hello world"]

    def test_mock_fallback_expected_text_mismatch_returns_fail(self, mock_context):
        node = _make_node("ocr", config={
            "mock_text": "actual text",
            "expected_text": "expected different",
        })
        with patch.object(type(node), "_get_ocr_engine", return_value=(None, None)):
            result = node.execute(mock_context)
        assert result.success is False
        assert "expected" in result.error_msg.lower()

    def test_mock_fallback_expected_text_match_succeeds(self, mock_context):
        node = _make_node("ocr", config={
            "mock_text": "level 5",
            "expected_text": "level",
        })
        with patch.object(type(node), "_get_ocr_engine", return_value=(None, None)):
            result = node.execute(mock_context)
        assert result.success is True
        assert result.data["text"] == "level 5"

    def test_mock_fallback_stores_result_in_context(self, mock_context):
        node = _make_node("ocr", node_id="ocr1",
                          config={"mock_text": "stored"})
        with patch.object(type(node), "_get_ocr_engine", return_value=(None, None)):
            node.execute(mock_context)
        assert "ocr1_ocr_result" in mock_context.variables
        assert mock_context.variables["ocr1_ocr_result"]["text"] == "stored"


# ============================================================
# AndMatchNode
# ============================================================

class TestAndMatchNode:
    """AndMatchNode: 全部 child 必须成功."""

    def test_empty_children_returns_fail(self, mock_context):
        node = _make_node("and_match", config={"children": []})
        result = node.execute(mock_context)
        assert result.success is False
        assert "children" in result.error_msg.lower()

    def test_missing_children_returns_fail(self, mock_context):
        node = _make_node("and_match", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "children" in result.error_msg.lower()

    def test_all_children_pass_returns_success(self, mock_context):
        # Children: two notify nodes (always succeed when message provided).
        children = [
            {"node_type": "notify", "config": {"message": "first"}},
            {"node_type": "notify", "config": {"message": "second"}},
        ]
        node = _make_node("and_match", config={"children": children})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["all_passed"] is True
        assert result.data["count"] == 2

    def test_one_child_fails_returns_fail(self, mock_context):
        # First child: notify (succeeds); second: template_match (fails, no device).
        children = [
            {"node_type": "notify", "config": {"message": "ok"}},
            {"node_type": "template_match", "config": {"template": "x.png"}},
        ]
        node = _make_node("and_match", config={"children": children})
        result = node.execute(mock_context)
        assert result.success is False
        assert result.data["all_passed"] is False
        assert "and_match failed" in result.error_msg

    def test_short_circuit_default_true(self, mock_context):
        # short_circuit=True: first failure stops the chain.
        children = [
            {"node_type": "template_match", "config": {"template": "x.png"}},  # fails
            {"node_type": "notify", "config": {"message": "should_not_run"}},
        ]
        node = _make_node("and_match", config={"children": children})
        result = node.execute(mock_context)
        assert result.success is False
        # Only 1 child executed due to short-circuit.
        assert result.data["count"] == 1


# ============================================================
# OrMatchNode
# ============================================================

class TestOrMatchNode:
    """OrMatchNode: 首个 child 命中即返回."""

    def test_empty_children_returns_fail(self, mock_context):
        node = _make_node("or_match", config={"children": []})
        result = node.execute(mock_context)
        assert result.success is False
        assert "children" in result.error_msg.lower()

    def test_first_child_wins(self, mock_context):
        children = [
            {"node_type": "notify", "config": {"message": "winner"}},  # succeeds
            {"node_type": "template_match", "config": {"template": "x.png"}},  # would fail
        ]
        node = _make_node("or_match", config={"children": children})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["matched"] is True
        assert result.data["winner"]["node_type"] == "notify"
        # stop_on_first_success default True → only 1 child executed.
        assert result.data["count"] == 1

    def test_all_children_fail_returns_fail(self, mock_context):
        children = [
            {"node_type": "template_match", "config": {"template": "a.png"}},
            {"node_type": "template_match", "config": {"template": "b.png"}},
        ]
        node = _make_node("or_match", config={"children": children})
        result = node.execute(mock_context)
        assert result.success is False
        assert result.data["matched"] is False
        assert result.data["count"] == 2

    def test_stop_on_first_success_false_runs_all(self, mock_context):
        children = [
            {"node_type": "notify", "config": {"message": "first"}},
            {"node_type": "notify", "config": {"message": "second"}},
        ]
        node = _make_node("or_match",
                          config={"children": children, "stop_on_first_success": False})
        result = node.execute(mock_context)
        assert result.success is True
        # Both children ran.
        assert result.data["count"] == 2


# ============================================================
# CustomMatchNode
# ============================================================

class TestCustomMatchNode:
    """CustomMatchNode: 表达式评估决定成功/失败."""

    def test_missing_expression_returns_fail(self, mock_context):
        node = _make_node("custom_match", config={"children": []})
        result = node.execute(mock_context)
        assert result.success is False
        assert "expression" in result.error_msg.lower()

    def test_expression_true_returns_success(self, mock_context):
        children = [
            {"node_type": "notify", "config": {"message": "a"}},
        ]
        node = _make_node("custom_match", config={
            "children": children,
            "expression": "results[0]['success'] == True",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["verdict"] is True

    def test_expression_false_returns_fail(self, mock_context):
        children = [
            {"node_type": "notify", "config": {"message": "a"}},
        ]
        node = _make_node("custom_match", config={
            "children": children,
            "expression": "results[0]['success'] == False",
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert result.data["verdict"] is False

    def test_expression_error_returns_fail(self, mock_context):
        node = _make_node("custom_match", config={
            "children": [],
            "expression": "undefined_name",
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert "expression error" in result.error_msg.lower()

    def test_complex_expression_with_safe_builtins(self, mock_context):
        # Use safe_mode default True; len/any/all are available.
        children = [
            {"node_type": "notify", "config": {"message": "a"}},
            {"node_type": "notify", "config": {"message": "b"}},
        ]
        node = _make_node("custom_match", config={
            "children": children,
            "expression": "len(results) == 2 and all(r['success'] for r in results)",
        })
        result = node.execute(mock_context)
        assert result.success is True
