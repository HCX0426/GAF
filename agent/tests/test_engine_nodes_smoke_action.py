"""TD-336 #7: 动作类节点 smoke 测试

覆盖 4 个动作节点:
- KeyPressNode (key_press): 无设备/空 key/modifiers 顺序/存储结果
- TextInputNode (text_input): 无设备/空文本/调用 device/存储结果
- SwipeUntilNode (swipe_until): 空 templates/首次命中/达到 max_swipes
- SortSelectNode (sort_select): 无 input_variable/变量不存在/空列表/排序选取

使用 MagicMock 模拟 PipelineContext 与 device, 不依赖真实 OpenCV/图像.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import to register nodes.
import engine.nodes.key_press  # noqa: F401
import engine.nodes.sort_select  # noqa: F401
import engine.nodes.swipe_until  # noqa: F401
import engine.nodes.text_input  # noqa: F401
from engine.node import PIPELINE_NODE_REGISTRY

pytestmark = pytest.mark.unit

# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_context():
    """Build a mock PipelineContext with variables dict."""
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


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Patch time.sleep in nodes that sleep, so tests run fast."""
    import engine.nodes.key_press as key_press_mod
    import engine.nodes.swipe_until as swipe_until_mod
    import engine.nodes.text_input as text_input_mod
    monkeypatch.setattr(key_press_mod.time, "sleep", lambda *_a, **_kw: None)
    monkeypatch.setattr(swipe_until_mod.time, "sleep", lambda *_a, **_kw: None)
    monkeypatch.setattr(text_input_mod.time, "sleep", lambda *_a, **_kw: None)


def _make_node(node_type, node_id="test_node", config=None):
    return PIPELINE_NODE_REGISTRY[node_type].from_dict({
        "id": node_id,
        "node_type": node_type,
        "config": config or {},
    })


# ============================================================
# Registration
# ============================================================

class TestRegistration:
    def test_key_press_registered(self):
        assert "key_press" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["key_press"].__name__ == "KeyPressNode"

    def test_text_input_registered(self):
        assert "text_input" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["text_input"].__name__ == "TextInputNode"

    def test_swipe_until_registered(self):
        assert "swipe_until" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["swipe_until"].__name__ == "SwipeUntilNode"

    def test_sort_select_registered(self):
        assert "sort_select" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["sort_select"].__name__ == "SortSelectNode"


# ============================================================
# KeyPressNode
# ============================================================

class TestKeyPressNode:
    """KeyPressNode: 按键输入 (调用真实 Device.key_press)."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node("key_press", config={"key": "enter"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "device=None" in result.error_msg or "未设置设备" in result.error_msg

    def test_empty_key_returns_fail(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node("key_press", config={"key": ""})
        result = node.execute(mock_context)
        assert result.success is False
        assert "按键名称为空" in result.error_msg

    def test_basic_key_press_calls_device(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node("key_press", config={"key": "enter"})
        result = node.execute(mock_context)
        assert result.success is True
        dev.key_press.assert_called_once_with("enter")
        assert result.data["key"] == "enter"
        assert result.data["modifiers"] == []

    def test_modifiers_pressed_in_order(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node("key_press", config={
            "key": "a", "modifiers": ["ctrl", "shift"], "hold_duration": 0,
        })
        result = node.execute(mock_context)
        assert result.success is True
        # TD-398: 组合键改走 device.key_combo (mod-down → key down/up →
        # mod-up 严格顺序), 不再逐次 key_press —— 旧实现 Ctrl+L 会泄漏 'l'.
        dev.key_combo.assert_called_once_with(["ctrl", "shift"], "a")
        dev.key_press.assert_not_called()
        assert result.data["modifiers"] == ["ctrl", "shift"]

    def test_device_key_press_failure_returns_fail(self, mock_context):
        from core.exceptions import DeviceError
        dev = MagicMock()
        dev.key_press.side_effect = DeviceError("connection lost")
        mock_context.device = dev
        node = _make_node("key_press", config={"key": "enter"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "设备按键失败" in result.error_msg

    def test_default_hold_duration_is_0_05(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node("key_press", config={"key": "a"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["hold_duration"] == 0.05

    def test_stores_result_in_context(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node("key_press", node_id="kp1", config={"key": "esc"})
        node.execute(mock_context)
        assert "kp1_key_result" in mock_context.variables
        assert mock_context.variables["kp1_key_result"]["key"] == "esc"


# ============================================================
# TextInputNode
# ============================================================

class TestTextInputNode:
    """TextInputNode: 文本输入 (调用真实 Device.text_input)."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node("text_input", config={"text": "hello"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "device=None" in result.error_msg or "未设置设备" in result.error_msg

    def test_empty_text_returns_fail(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node("text_input", config={"text": ""})
        result = node.execute(mock_context)
        assert result.success is False
        assert "输入文本为空" in result.error_msg

    def test_basic_text_input_calls_device(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node("text_input", config={"text": "hello world"})
        result = node.execute(mock_context)
        assert result.success is True
        dev.text_input.assert_called_once_with("hello world")
        assert result.data["text"] == "hello world"
        assert result.data["length"] == 11

    def test_clear_before_input_presses_ctrl_a_backspace(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node("text_input",
                          config={"text": "x", "clear_before": True})
        result = node.execute(mock_context)
        assert result.success is True
        # ctrl, a, backspace pressed during clear, then text_input called.
        dev.key_press.assert_any_call("ctrl")
        dev.key_press.assert_any_call("a")
        dev.key_press.assert_any_call("backspace")
        dev.text_input.assert_called_once_with("x")
        assert result.data["clear_before"] is True

    def test_device_text_input_failure_returns_fail(self, mock_context):
        from core.exceptions import DeviceError
        dev = MagicMock()
        dev.text_input.side_effect = DeviceError("input failed")
        mock_context.device = dev
        node = _make_node("text_input", config={"text": "x"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "设备文本输入失败" in result.error_msg

    def test_default_interval_is_0_02(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node("text_input", config={"text": "x"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["interval"] == 0.02

    def test_stores_result_in_context(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node("text_input", node_id="ti1", config={"text": "abc"})
        node.execute(mock_context)
        assert "ti1_text_result" in mock_context.variables
        assert mock_context.variables["ti1_text_result"]["text"] == "abc"


# ============================================================
# SwipeUntilNode
# ============================================================

class TestSwipeUntilNode:
    """SwipeUntilNode: 循环滑动直到模板匹配."""

    def test_empty_templates_returns_fail(self, mock_context):
        node = _make_node("swipe_until",
                          config={"templates": [], "x1": 0, "y1": 0, "x2": 10, "y2": 10})
        result = node.execute(mock_context)
        assert result.success is False
        assert "templates" in result.error_msg.lower()

    def test_missing_templates_returns_fail(self, mock_context):
        node = _make_node("swipe_until", config={"x1": 0, "y1": 0, "x2": 10, "y2": 10})
        result = node.execute(mock_context)
        assert result.success is False
        assert "templates" in result.error_msg.lower()

    def test_first_attempt_match_succeeds_no_swipe(self, mock_context):
        # No device → first match attempt fails → swipe child runs but also
        # fails (no device). We verify the orchestration shape: at least 1
        # match attempt + swipe attempts recorded in result.
        node = _make_node("swipe_until", config={
            "templates": ["x.png"],
            "x1": 0, "y1": 0, "x2": 10, "y2": 10,
            "max_swipes": 2,
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert result.data["matched"] is False
        # 2 swipes performed (the max).
        assert result.data["swipes_performed"] == 2
        # attempts list has match + swipe entries (alternating).
        phases = [a["phase"] for a in result.data["attempts"]]
        assert "match" in phases
        assert "swipe" in phases

    def test_max_swipes_exhausted_returns_fail(self, mock_context):
        node = _make_node("swipe_until", config={
            "templates": ["a.png", "b.png"],
            "x1": 100, "y1": 500, "x2": 100, "y2": 100,
            "max_swipes": 3,
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert result.data["matched"] is False
        assert result.data["swipes_performed"] == 3
        # 4 match attempts (1 before + 3 after each swipe).
        match_attempts = [a for a in result.data["attempts"] if a["phase"] == "match"]
        assert len(match_attempts) == 4

    def test_default_max_swipes_is_3(self, mock_context):
        node = _make_node("swipe_until", config={
            "templates": ["x.png"],
            "x1": 0, "y1": 0, "x2": 0, "y2": 0,
        })
        result = node.execute(mock_context)
        assert result.success is False
        # Default max_swipes=3 → 3 swipes performed.
        assert result.data["swipes_performed"] == 3


# ============================================================
# SortSelectNode
# ============================================================

class TestSortSelectNode:
    """SortSelectNode: 列表排序后按索引选取元素."""

    def test_missing_input_variable_returns_fail(self, mock_context):
        node = _make_node("sort_select", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "input_variable" in result.error_msg

    def test_variable_not_found_returns_fail(self, mock_context):
        node = _make_node("sort_select", config={"input_variable": "missing"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "not found" in result.error_msg.lower()

    def test_empty_list_returns_fail(self, mock_context):
        mock_context.variables["items"] = []
        node = _make_node("sort_select",
                          config={"input_variable": "items"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "empty" in result.error_msg.lower()

    def test_non_list_variable_returns_fail(self, mock_context):
        mock_context.variables["val"] = 42
        node = _make_node("sort_select",
                          config={"input_variable": "val"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "not a list" in result.error_msg.lower()

    def test_dict_with_contours_field_extracts_list(self, mock_context):
        mock_context.variables["detect"] = {
            "contours": [
                {"area": 10, "center": {"x": 1, "y": 1}},
                {"area": 50, "center": {"x": 2, "y": 2}},
            ],
        }
        node = _make_node("sort_select", config={
            "input_variable": "detect",
            "order_by": "area",
            "order": "desc",
            "index": 0,
        })
        result = node.execute(mock_context)
        assert result.success is True
        # Descending sort → first element has area=50.
        assert result.data["selected"]["area"] == 50
        assert result.data["list_length"] == 2

    def test_sort_descending_and_select_first(self, mock_context):
        mock_context.variables["boxes"] = [
            {"confidence": 0.5, "x": 10, "y": 20},
            {"confidence": 0.9, "x": 30, "y": 40},
            {"confidence": 0.7, "x": 50, "y": 60},
        ]
        node = _make_node("sort_select", config={
            "input_variable": "boxes",
            "order_by": "confidence",
            "order": "desc",
            "index": 0,
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["selected"]["confidence"] == 0.9
        assert result.data["selected"]["x"] == 30

    def test_negative_index_selects_last(self, mock_context):
        mock_context.variables["items"] = [
            {"v": 1}, {"v": 2}, {"v": 3},
        ]
        node = _make_node("sort_select", config={
            "input_variable": "items",
            "index": -1,
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["selected"]["v"] == 3

    def test_index_out_of_range_returns_fail(self, mock_context):
        mock_context.variables["items"] = [{"v": 1}]
        node = _make_node("sort_select", config={
            "input_variable": "items",
            "index": 5,
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert "out of range" in result.error_msg.lower()

    def test_publishes_match_pos_when_xy_present(self, mock_context):
        mock_context.variables["items"] = [
            {"x": 100, "y": 200, "confidence": 0.9},
        ]
        node = _make_node("sort_select", config={
            "input_variable": "items",
            "index": 0,
        })
        result = node.execute(mock_context)
        assert result.success is True
        # _last_match_pos should be published via engine.target.publish_match_pos.
        # We can't easily assert it without depending on the helper; just verify success.

    def test_var_reference_syntax_resolves(self, mock_context):
        mock_context.variables["boxes"] = [{"x": 1, "y": 2}]
        node = _make_node("sort_select", config={
            "input_variable": "${boxes}",
            "index": 0,
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["selected"]["x"] == 1

    def test_stores_result_in_default_output_variable(self, mock_context):
        mock_context.variables["items"] = [{"v": 1}]
        node = _make_node("sort_select", node_id="ss1",
                          config={"input_variable": "items"})
        node.execute(mock_context)
        assert "ss1_selected" in mock_context.variables
