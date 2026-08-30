"""P1-7 / P0-5 / P2-5 engine node tests for new input action nodes.

Covers 4 nodes registered in PIPELINE_NODE_REGISTRY:
- LongPressNode (long_press): true mouse-down/sleep/mouse-up + click+sleep fallback.
- DirectHitNode (direct_hit): skip recognition, click coordinates directly.
- MultiSwipeNode (multi_swipe): concurrent multi-touch swipe gestures.
- WheelNode (wheel): mouse wheel scroll at coordinates.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import to register nodes.
import engine.nodes.direct_hit  # noqa: F401
import engine.nodes.long_press  # noqa: F401
import engine.nodes.multi_scroll  # noqa: F401
import engine.nodes.multi_swipe  # noqa: F401
import engine.nodes.multi_touch  # noqa: F401
import engine.nodes.wheel  # noqa: F401
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
    # N191 §10.10 (AI 可调试性, 2026-07-27): 显式设 None 避免 MagicMock
    # 默认属性被 wheel/multi_touch/multi_scroll/click 等节点的
    # `getattr(context, 'coord_transformer', None)` 拿到 MagicMock 实例
    # (truthy), 走 transformer 路径调用 convert_original_to_current_client
    # 返回 MagicMock 导致 unpack 失败。与 test_target_resolution.py 一致。
    ctx.coord_transformer = None
    ctx.coord_system = ""
    ctx.structured_logger = None
    ctx.device_type = ""
    ctx.transformer_id = ""

    def set_var(key, value):
        ctx.variables[key] = value

    def get_var(key, default=None):
        return ctx.variables.get(key, default)

    ctx.set_variable.side_effect = set_var
    ctx.get_variable.side_effect = get_var
    return ctx


def _make_node(node_cls, node_id="test_node", config=None):
    return node_cls(
        id=node_id,
        name=node_id,
        node_type=node_cls.node_type,
        config=config or {},
        next_node_id="next_default",
    )


def _make_device(
    with_long_press=True,
    with_multi_swipe=True,
    with_wheel=True,
    with_multi_touch=True,
    with_multi_scroll=True,
    with_touch_primitives=False,
):
    """Build a mock device with optional input methods.

    Args:
        with_touch_primitives: If True, add touch_down/touch_move/touch_up
            and remove multi_touch (to test the sequential primitive path).
    """
    dev = MagicMock()
    if not with_long_press:
        del dev.long_press
    if not with_multi_swipe:
        del dev.multi_swipe
    if not with_wheel:
        del dev.wheel
    if not with_multi_touch:
        del dev.multi_touch
    if not with_multi_scroll:
        del dev.multi_scroll
    if with_touch_primitives:
        # touch_down/move/up are real methods; remove multi_touch to
        # force the sequential primitive dispatch path.
        dev.touch_down = MagicMock()
        dev.touch_move = MagicMock()
        dev.touch_up = MagicMock()
        if hasattr(dev, "multi_touch"):
            del dev.multi_touch
    else:
        if hasattr(dev, "touch_down"):
            del dev.touch_down
        if hasattr(dev, "touch_move"):
            del dev.touch_move
        if hasattr(dev, "touch_up"):
            del dev.touch_up
    return dev


# ============================================================
# Registration
# ============================================================

class TestNodeRegistration:
    """All 4 new nodes must be registered in PIPELINE_NODE_REGISTRY."""

    def test_long_press_registered(self):
        assert "long_press" in PIPELINE_NODE_REGISTRY

    def test_direct_hit_registered(self):
        assert "direct_hit" in PIPELINE_NODE_REGISTRY

    def test_multi_swipe_registered(self):
        assert "multi_swipe" in PIPELINE_NODE_REGISTRY

    def test_multi_touch_registered(self):
        assert "multi_touch" in PIPELINE_NODE_REGISTRY

    def test_multi_scroll_registered(self):
        assert "multi_scroll" in PIPELINE_NODE_REGISTRY

    def test_wheel_registered(self):
        assert "wheel" in PIPELINE_NODE_REGISTRY


# ============================================================
# LongPressNode
# ============================================================

class TestLongPressNode:
    """LongPressNode: hold mouse button for a duration."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node(PIPELINE_NODE_REGISTRY["long_press"],
                          config={"x": 10, "y": 20, "duration_ms": 100})
        result = node.execute(mock_context)
        assert result.success is False
        assert "None" in result.error_msg or "device" in result.error_msg.lower()

    def test_with_device_long_press_calls_device_long_press(self, mock_context):
        dev = _make_device(with_long_press=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["long_press"],
                          config={"x": 50, "y": 60, "duration_ms": 500, "button": "right"})
        result = node.execute(mock_context)
        assert result.success is True
        dev.long_press.assert_called_once_with(50, 60, duration_ms=500, button="right")
        assert result.data["x"] == 50
        assert result.data["y"] == 60
        assert result.data["button"] == "right"
        assert result.data["duration_ms"] == 500
        assert result.data["emulated"] is False

    def test_without_device_long_press_falls_back_to_click_sleep(self, mock_context):
        dev = _make_device(with_long_press=False)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["long_press"],
                          config={"x": 10, "y": 20, "duration_ms": 50})
        # Patch sleep so the test is fast.
        with patch("engine.nodes.long_press.time.sleep") as mock_sleep:
            result = node.execute(mock_context)
        assert result.success is True
        dev.click.assert_called_once_with(10, 20)
        assert result.data["emulated"] is True
        # Should have slept for the duration (50ms = 0.05s).
        mock_sleep.assert_any_call(0.05)

    def test_resolve_var_reference(self, mock_context):
        dev = _make_device(with_long_press=True)
        mock_context.device = dev
        mock_context.variables["target"] = {"x": 100, "y": 200}
        node = _make_node(PIPELINE_NODE_REGISTRY["long_press"],
                          config={"x": "${target}", "y": "${target}", "duration_ms": 10})
        result = node.execute(mock_context)
        assert result.success is True
        dev.long_press.assert_called_once_with(100, 200, duration_ms=10, button="left")

    def test_missing_var_returns_fail(self, mock_context):
        dev = _make_device(with_long_press=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["long_press"],
                          config={"x": "${missing}", "y": 10, "duration_ms": 10})
        result = node.execute(mock_context)
        assert result.success is False
        assert "resolve" in result.error_msg.lower() or "missing" in result.error_msg.lower()

    def test_default_button_is_left(self, mock_context):
        dev = _make_device(with_long_press=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["long_press"],
                          config={"x": 1, "y": 2, "duration_ms": 10})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["button"] == "left"

    def test_default_duration_is_1000(self, mock_context):
        dev = _make_device(with_long_press=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["long_press"],
                          config={"x": 1, "y": 2})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["duration_ms"] == 1000

    def test_stores_result_in_context(self, mock_context):
        dev = _make_device(with_long_press=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["long_press"], node_id="lp1",
                          config={"x": 1, "y": 2, "duration_ms": 10})
        node.execute(mock_context)
        assert "lp1_long_press_result" in mock_context.variables


# ============================================================
# DirectHitNode
# ============================================================

class TestDirectHitNode:
    """DirectHitNode: skip recognition, click coordinates directly."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node(PIPELINE_NODE_REGISTRY["direct_hit"],
                          config={"x": 10, "y": 20})
        result = node.execute(mock_context)
        assert result.success is False
        assert "None" in result.error_msg or "device" in result.error_msg.lower()

    def test_single_click(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["direct_hit"],
                          config={"x": 100, "y": 200})
        result = node.execute(mock_context)
        assert result.success is True
        dev.click.assert_called_once_with(100, 200)
        assert result.data["clicks"] == 1
        assert result.data["recognition"] == "direct_hit"

    def test_multiple_clicks(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["direct_hit"],
                          config={"x": 100, "y": 200, "clicks": 3, "interval": 0.01})
        with patch("engine.nodes.direct_hit.time.sleep"):
            result = node.execute(mock_context)
        assert result.success is True
        assert dev.click.call_count == 3
        assert result.data["clicks"] == 3

    def test_zero_clicks_returns_fail(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["direct_hit"],
                          config={"x": 1, "y": 2, "clicks": 0})
        result = node.execute(mock_context)
        assert result.success is False
        assert "clicks" in result.error_msg.lower()

    def test_var_reference(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        mock_context.variables["pos"] = {"x": 50, "y": 75}
        node = _make_node(PIPELINE_NODE_REGISTRY["direct_hit"],
                          config={"x": "${pos}", "y": "${pos}"})
        result = node.execute(mock_context)
        assert result.success is True
        dev.click.assert_called_once_with(50, 75)

    def test_default_clicks_is_1(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["direct_hit"],
                          config={"x": 1, "y": 2})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["clicks"] == 1

    def test_default_interval_is_0_1(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["direct_hit"],
                          config={"x": 1, "y": 2, "clicks": 2})
        with patch("engine.nodes.direct_hit.time.sleep"):
            result = node.execute(mock_context)
        assert result.success is True
        assert result.data["interval"] == 0.1

    def test_stores_result_in_context(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["direct_hit"], node_id="dh1",
                          config={"x": 1, "y": 2})
        node.execute(mock_context)
        assert "dh1_direct_hit_result" in mock_context.variables


# ============================================================
# MultiSwipeNode
# ============================================================

class TestMultiSwipeNode:
    """MultiSwipeNode: concurrent multi-touch swipe gestures."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_swipe"],
                          config={"swipes": [{"x1": 0, "y1": 0, "x2": 100, "y2": 100}]})
        result = node.execute(mock_context)
        assert result.success is False

    def test_empty_swipes_returns_fail(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_swipe"],
                          config={"swipes": []})
        result = node.execute(mock_context)
        assert result.success is False
        assert "empty" in result.error_msg.lower()

    def test_missing_swipes_returns_fail(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_swipe"],
                          config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "empty" in result.error_msg.lower()

    def test_with_device_multi_swipe_calls_device_multi_swipe(self, mock_context):
        dev = _make_device(with_multi_swipe=True)
        mock_context.device = dev
        swipes = [
            {"x1": 0, "y1": 0, "x2": 100, "y2": 100, "duration_ms": 200},
            {"x1": 50, "y1": 50, "x2": 150, "y2": 150},
        ]
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_swipe"],
                          config={"swipes": swipes, "parallel": True})
        result = node.execute(mock_context)
        assert result.success is True
        dev.multi_swipe.assert_called_once()
        args, kwargs = dev.multi_swipe.call_args
        # First positional arg is the swipes list.
        normalized = args[0] if args else kwargs.get("swipes")
        assert len(normalized) == 2
        assert normalized[0]["x1"] == 0
        assert normalized[0]["duration_ms"] == 200
        # Default duration_ms for missing key.
        assert normalized[1]["duration_ms"] == 300
        assert result.data["count"] == 2
        assert result.data["parallel"] is True
        assert result.data["emulated"] is False

    def test_without_device_multi_swipe_falls_back_sequential(self, mock_context):
        dev = _make_device(with_multi_swipe=False)
        mock_context.device = dev
        swipes = [
            {"x1": 0, "y1": 0, "x2": 100, "y2": 100, "duration_ms": 100},
            {"x1": 50, "y1": 50, "x2": 150, "y2": 150, "duration_ms": 100},
        ]
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_swipe"],
                          config={"swipes": swipes})
        result = node.execute(mock_context)
        assert result.success is True
        assert dev.swipe.call_count == 2
        assert result.data["emulated"] is True
        assert result.data["parallel"] is False

    def test_invalid_swipe_entry_returns_fail(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        swipes = [
            {"x1": 0, "y1": 0, "x2": 100, "y2": 100},
            "not-a-dict",
        ]
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_swipe"],
                          config={"swipes": swipes})
        result = node.execute(mock_context)
        assert result.success is False
        assert "swipe[1]" in result.error_msg

    def test_default_parallel_is_true(self, mock_context):
        dev = _make_device(with_multi_swipe=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_swipe"],
                          config={"swipes": [{"x1": 0, "y1": 0, "x2": 10, "y2": 10}]})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["parallel"] is True

    def test_stores_result_in_context(self, mock_context):
        dev = _make_device(with_multi_swipe=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_swipe"], node_id="ms1",
                          config={"swipes": [{"x1": 0, "y1": 0, "x2": 10, "y2": 10}]})
        node.execute(mock_context)
        assert "ms1_multi_swipe_result" in mock_context.variables


# ============================================================
# WheelNode
# ============================================================

class TestWheelNode:
    """WheelNode: mouse wheel scroll at coordinates."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node(PIPELINE_NODE_REGISTRY["wheel"],
                          config={"x": 10, "y": 20})
        result = node.execute(mock_context)
        assert result.success is False

    def test_default_delta_is_120(self, mock_context):
        dev = _make_device(with_wheel=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["wheel"],
                          config={"x": 10, "y": 20})
        result = node.execute(mock_context)
        assert result.success is True
        dev.wheel.assert_called_once_with(10, 20, delta=120)
        assert result.data["delta"] == 120

    def test_explicit_delta(self, mock_context):
        dev = _make_device(with_wheel=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["wheel"],
                          config={"x": 10, "y": 20, "delta": -240})
        result = node.execute(mock_context)
        assert result.success is True
        dev.wheel.assert_called_once_with(10, 20, delta=-240)
        assert result.data["delta"] == -240

    def test_notches_multiplied_by_wheel_delta(self, mock_context):
        dev = _make_device(with_wheel=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["wheel"],
                          config={"x": 10, "y": 20, "notches": 3})
        result = node.execute(mock_context)
        assert result.success is True
        # 3 notches * 120 = 360
        dev.wheel.assert_called_once_with(10, 20, delta=360)
        assert result.data["delta"] == 360

    def test_delta_wins_over_notches(self, mock_context):
        dev = _make_device(with_wheel=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["wheel"],
                          config={"x": 10, "y": 20, "delta": 240, "notches": 5})
        result = node.execute(mock_context)
        assert result.success is True
        # Explicit delta wins.
        dev.wheel.assert_called_once_with(10, 20, delta=240)
        assert result.data["delta"] == 240

    def test_no_wheel_returns_fail(self, mock_context):
        dev = _make_device(with_wheel=False)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["wheel"],
                          config={"x": 10, "y": 20})
        result = node.execute(mock_context)
        assert result.success is False
        assert "wheel" in result.error_msg.lower()

    def test_var_reference(self, mock_context):
        dev = _make_device(with_wheel=True)
        mock_context.device = dev
        mock_context.variables["pos"] = {"x": 50, "y": 75}
        node = _make_node(PIPELINE_NODE_REGISTRY["wheel"],
                          config={"x": "${pos}", "y": "${pos}", "delta": 240})
        result = node.execute(mock_context)
        assert result.success is True
        dev.wheel.assert_called_once_with(50, 75, delta=240)

    def test_stores_result_in_context(self, mock_context):
        dev = _make_device(with_wheel=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["wheel"], node_id="wh1",
                          config={"x": 1, "y": 2})
        node.execute(mock_context)
        assert "wh1_wheel_result" in mock_context.variables


# ============================================================
# MultiTouchNode
# ============================================================

class TestMultiTouchNode:
    """MultiTouchNode: primitive multi-touch gesture composition."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_touch"],
                          config={"touches": [{"action": "down", "x": 10, "y": 20}]})
        result = node.execute(mock_context)
        assert result.success is False

    def test_empty_touches_returns_fail(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_touch"],
                          config={"touches": []})
        result = node.execute(mock_context)
        assert result.success is False
        assert "empty" in result.error_msg.lower()

    def test_missing_touches_returns_fail(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_touch"],
                          config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "empty" in result.error_msg.lower()

    def test_invalid_action_returns_fail(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_touch"],
                          config={"touches": [{"action": "tap", "x": 0, "y": 0}]})
        result = node.execute(mock_context)
        assert result.success is False
        assert "invalid action" in result.error_msg.lower()

    def test_with_device_multi_touch_calls_native(self, mock_context):
        dev = _make_device(with_multi_touch=True)
        mock_context.device = dev
        touches = [
            {"action": "down", "contact": 0, "x": 100, "y": 200, "pressure": 50},
            {"action": "down", "contact": 1, "x": 300, "y": 400},
            {"action": "up", "contact": 0},
            {"action": "up", "contact": 1},
        ]
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_touch"],
                          config={"touches": touches, "parallel": True})
        result = node.execute(mock_context)
        assert result.success is True
        dev.multi_touch.assert_called_once()
        args, kwargs = dev.multi_touch.call_args
        normalized = args[0] if args else kwargs.get("touches")
        assert len(normalized) == 4
        assert normalized[0]["action"] == "down"
        assert normalized[0]["contact"] == 0
        assert normalized[0]["pressure"] == 50
        # Default contact and pressure.
        assert normalized[1]["contact"] == 1
        assert normalized[1]["pressure"] == 0
        assert result.data["count"] == 4
        assert result.data["parallel"] is True
        assert result.data["emulated"] is False

    def test_with_touch_primitives_sequential_path(self, mock_context):
        dev = _make_device(with_touch_primitives=True)
        mock_context.device = dev
        touches = [
            {"action": "down", "contact": 0, "x": 10, "y": 20},
            {"action": "move", "contact": 0, "x": 30, "y": 40},
            {"action": "up", "contact": 0},
        ]
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_touch"],
                          config={"touches": touches})
        result = node.execute(mock_context)
        assert result.success is True
        dev.touch_down.assert_called_once_with(0, 10, 20, 0)
        dev.touch_move.assert_called_once_with(0, 30, 40, 0)
        dev.touch_up.assert_called_once_with(0)
        assert result.data["parallel"] is False
        assert result.data["emulated"] is False

    def test_degraded_fallback_to_click_swipe(self, mock_context):
        # Device with no multi_touch and no touch primitives.
        dev = _make_device(with_multi_touch=False, with_touch_primitives=False)
        mock_context.device = dev
        touches = [
            {"action": "down", "x": 50, "y": 60},
            {"action": "move", "x": 70, "y": 80},
            {"action": "up", "x": 70, "y": 80},
        ]
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_touch"],
                          config={"touches": touches})
        result = node.execute(mock_context)
        assert result.success is True
        dev.click.assert_called_once_with(50, 60)
        dev.swipe.assert_called_once_with(70, 80, 70, 80, duration=0)
        assert result.data["emulated"] is True

    def test_invalid_touch_entry_returns_fail(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        touches = [
            {"action": "down", "x": 0, "y": 0},
            "not-a-dict",
        ]
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_touch"],
                          config={"touches": touches})
        result = node.execute(mock_context)
        assert result.success is False
        assert "touch[1]" in result.error_msg

    def test_stores_result_in_context(self, mock_context):
        dev = _make_device(with_multi_touch=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_touch"], node_id="mt1",
                          config={"touches": [{"action": "down", "x": 1, "y": 2}]})
        node.execute(mock_context)
        assert "mt1_multi_touch_result" in mock_context.variables


# ============================================================
# MultiScrollNode
# ============================================================

class TestMultiScrollNode:
    """MultiScrollNode: concurrent mouse wheel scroll at multiple coordinates."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_scroll"],
                          config={"scrolls": [{"x": 10, "y": 20}]})
        result = node.execute(mock_context)
        assert result.success is False

    def test_empty_scrolls_returns_fail(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_scroll"],
                          config={"scrolls": []})
        result = node.execute(mock_context)
        assert result.success is False
        assert "empty" in result.error_msg.lower()

    def test_with_device_multi_scroll_calls_native(self, mock_context):
        dev = _make_device(with_multi_scroll=True)
        mock_context.device = dev
        scrolls = [
            {"x": 100, "y": 200, "delta": 240},
            {"x": 300, "y": 400, "notches": -2},
        ]
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_scroll"],
                          config={"scrolls": scrolls, "parallel": True})
        result = node.execute(mock_context)
        assert result.success is True
        dev.multi_scroll.assert_called_once()
        args, kwargs = dev.multi_scroll.call_args
        normalized = args[0] if args else kwargs.get("scrolls")
        assert len(normalized) == 2
        assert normalized[0]["delta"] == 240
        # notches=-2 → delta=-240.
        assert normalized[1]["delta"] == -240
        assert result.data["count"] == 2
        assert result.data["parallel"] is True
        assert result.data["emulated"] is False

    def test_without_multi_scroll_falls_back_to_wheel(self, mock_context):
        dev = _make_device(with_multi_scroll=False, with_wheel=True)
        mock_context.device = dev
        scrolls = [
            {"x": 10, "y": 20, "delta": 120},
            {"x": 30, "y": 40, "delta": -120},
        ]
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_scroll"],
                          config={"scrolls": scrolls})
        result = node.execute(mock_context)
        assert result.success is True
        assert dev.wheel.call_count == 2
        dev.wheel.assert_any_call(10, 20, delta=120)
        dev.wheel.assert_any_call(30, 40, delta=-120)
        assert result.data["emulated"] is True
        assert result.data["parallel"] is False

    def test_default_delta_is_wheel_delta(self, mock_context):
        dev = _make_device(with_multi_scroll=True)
        mock_context.device = dev
        scrolls = [{"x": 0, "y": 0}]
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_scroll"],
                          config={"scrolls": scrolls})
        result = node.execute(mock_context)
        assert result.success is True
        args, _ = dev.multi_scroll.call_args
        assert args[0][0]["delta"] == 120

    def test_no_wheel_no_multi_scroll_returns_fail(self, mock_context):
        dev = _make_device(with_multi_scroll=False, with_wheel=False)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_scroll"],
                          config={"scrolls": [{"x": 0, "y": 0}]})
        result = node.execute(mock_context)
        assert result.success is False
        assert "wheel" in result.error_msg.lower()

    def test_invalid_scroll_entry_returns_fail(self, mock_context):
        dev = _make_device()
        mock_context.device = dev
        scrolls = [
            {"x": 0, "y": 0},
            "not-a-dict",
        ]
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_scroll"],
                          config={"scrolls": scrolls})
        result = node.execute(mock_context)
        assert result.success is False
        assert "scroll[1]" in result.error_msg

    def test_stores_result_in_context(self, mock_context):
        dev = _make_device(with_multi_scroll=True)
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["multi_scroll"], node_id="msc1",
                          config={"scrolls": [{"x": 1, "y": 2}]})
        node.execute(mock_context)
        assert "msc1_multi_scroll_result" in mock_context.variables
