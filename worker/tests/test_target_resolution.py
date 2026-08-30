"""P0-6 target / target_offset resolution tests.

Covers:
- engine.target.publish_match_pos / resolve_target / _extract_xy / _resolve_offset
- ClickNode integration: target overrides x/y, target_offset applied
- SwipeNode integration: target/end_target for start/end points
- Recognition nodes publish _last_match_pos (template_match/feature_match/ocr/color_detect)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Register nodes.
import engine.nodes.click  # noqa: F401
import engine.nodes.color_detect  # noqa: F401
import engine.nodes.direct_hit  # noqa: F401
import engine.nodes.feature_match  # noqa: F401
import engine.nodes.long_press  # noqa: F401
import engine.nodes.maa_actions  # noqa: F401
import engine.nodes.ocr  # noqa: F401
import engine.nodes.swipe  # noqa: F401
import engine.nodes.template_match  # noqa: F401
import engine.nodes.wheel  # noqa: F401
from engine.node import PIPELINE_NODE_REGISTRY
from engine.target import (
    ANCHOR_POS_VAR,
    LAST_MATCH_POS_VAR,
    publish_match_pos,
    resolve_target,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.variables = {}
    ctx.device = None
    # N191 §10.10 (AI 可调试性, 2026-07-27): 显式设 None 避免 MagicMock
    # 默认属性被 click.py 的 `getattr(context, 'coord_transformer', None)`
    # 拿到 MagicMock 实例 (truthy) 触发 convert_original_to_current_client
    # 返回 MagicMock 导致 unpack 失败。
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


# ============================================================
# publish_match_pos
# ============================================================

class TestPublishMatchPos:
    def test_publish_writes_last_match_pos(self, mock_context):
        publish_match_pos(mock_context, 100, 200, source="test")
        pos = mock_context.variables[LAST_MATCH_POS_VAR]
        assert pos["x"] == 100
        assert pos["y"] == 200
        assert pos["source"] == "test"

    def test_publish_extra_fields_merged(self, mock_context):
        publish_match_pos(mock_context, 10, 20, source="t", extra={"confidence": 0.95})
        pos = mock_context.variables[LAST_MATCH_POS_VAR]
        assert pos["confidence"] == 0.95

    def test_publish_without_source(self, mock_context):
        publish_match_pos(mock_context, 5, 6)
        pos = mock_context.variables[LAST_MATCH_POS_VAR]
        assert "source" not in pos
        assert pos["x"] == 5
        assert pos["y"] == 6

    def test_publish_overwrites_previous(self, mock_context):
        publish_match_pos(mock_context, 1, 2)
        publish_match_pos(mock_context, 99, 88)
        pos = mock_context.variables[LAST_MATCH_POS_VAR]
        assert pos["x"] == 99
        assert pos["y"] == 88


# ============================================================
# resolve_target — dict spec
# ============================================================

class TestResolveTargetDict:
    def test_dict_with_xy(self, mock_context):
        x, y = resolve_target(mock_context, {"x": 50, "y": 75})
        assert (x, y) == (50, 75)

    def test_dict_missing_x_raises(self, mock_context):
        with pytest.raises(ValueError, match="missing"):
            resolve_target(mock_context, {"y": 75})

    def test_dict_with_offset(self, mock_context):
        x, y = resolve_target(mock_context, {"x": 50, "y": 75}, offset={"x": 10, "y": -5})
        assert (x, y) == (60, 70)

    def test_dict_with_list_offset(self, mock_context):
        x, y = resolve_target(mock_context, {"x": 50, "y": 75}, offset=[10, 20])
        assert (x, y) == (60, 95)


# ============================================================
# resolve_target — string spec (variable reference)
# ============================================================

class TestResolveTargetString:
    def test_string_resolves_variable(self, mock_context):
        mock_context.variables["my_pos"] = {"x": 100, "y": 200}
        x, y = resolve_target(mock_context, "my_pos")
        assert (x, y) == (100, 200)

    def test_dollar_brace_syntax(self, mock_context):
        mock_context.variables["anchor"] = {"x": 33, "y": 44}
        x, y = resolve_target(mock_context, "${anchor}")
        assert (x, y) == (33, 44)

    def test_default_last_match_pos(self, mock_context):
        # "_last_match_pos" is the conventional default.
        mock_context.variables[LAST_MATCH_POS_VAR] = {"x": 7, "y": 8}
        x, y = resolve_target(mock_context, LAST_MATCH_POS_VAR)
        assert (x, y) == (7, 8)

    def test_anchor_pos_var(self, mock_context):
        mock_context.variables[ANCHOR_POS_VAR] = {"x": 11, "y": 22}
        x, y = resolve_target(mock_context, ANCHOR_POS_VAR)
        assert (x, y) == (11, 22)

    def test_missing_variable_raises(self, mock_context):
        with pytest.raises(ValueError, match="not found"):
            resolve_target(mock_context, "nonexistent_var")

    def test_dict_with_center_field(self, mock_context):
        # feature_match result shape: {"center": {"x": .., "y": ..}}
        mock_context.variables["feat"] = {"center": {"x": 50, "y": 60}}
        x, y = resolve_target(mock_context, "feat")
        assert (x, y) == (50, 60)

    def test_list_variable(self, mock_context):
        mock_context.variables["coord"] = [123, 456]
        x, y = resolve_target(mock_context, "coord")
        assert (x, y) == (123, 456)

    def test_scalar_variable_raises(self, mock_context):
        mock_context.variables["num"] = 42
        with pytest.raises(ValueError, match="scalar"):
            resolve_target(mock_context, "num")

    def test_string_with_offset(self, mock_context):
        mock_context.variables["pos"] = {"x": 100, "y": 200}
        x, y = resolve_target(mock_context, "pos", offset={"x": -10, "y": 5})
        assert (x, y) == (90, 205)


# ============================================================
# resolve_target — fallback (None)
# ============================================================

class TestResolveTargetFallback:
    def test_none_with_fallback(self, mock_context):
        x, y = resolve_target(mock_context, None, fallback_x=10, fallback_y=20)
        assert (x, y) == (10, 20)

    def test_none_without_fallback_raises(self, mock_context):
        with pytest.raises(ValueError, match="no fallback"):
            resolve_target(mock_context, None)

    def test_empty_string_uses_fallback(self, mock_context):
        x, y = resolve_target(mock_context, "", fallback_x=99, fallback_y=88)
        assert (x, y) == (99, 88)

    def test_none_with_offset(self, mock_context):
        x, y = resolve_target(mock_context, None, offset={"x": 5, "y": 5},
                              fallback_x=10, fallback_y=20)
        assert (x, y) == (15, 25)


# ============================================================
# resolve_target — invalid types
# ============================================================

class TestResolveTargetInvalid:
    def test_int_target_raises(self, mock_context):
        with pytest.raises(ValueError, match="unsupported target type"):
            resolve_target(mock_context, 123)  # type: ignore[arg-type]

    def test_list_offset_too_short(self, mock_context):
        with pytest.raises(ValueError, match="too short"):
            resolve_target(mock_context, {"x": 1, "y": 2}, offset=[5])  # type: ignore

    def test_dict_offset_missing_y(self, mock_context):
        with pytest.raises(ValueError, match="missing"):
            resolve_target(mock_context, {"x": 1, "y": 2}, offset={"x": 5})


# ============================================================
# ClickNode integration with target / target_offset
# ============================================================

class TestClickNodeTarget:
    def test_target_overrides_xy(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        mock_context.variables[LAST_MATCH_POS_VAR] = {"x": 100, "y": 200}
        node = _make_node(PIPELINE_NODE_REGISTRY["click"],
                          config={"target": "_last_match_pos"})
        result = node.execute(mock_context)
        assert result.success is True
        dev.click.assert_called_once_with(100, 200)

    def test_target_with_offset(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        mock_context.variables[LAST_MATCH_POS_VAR] = {"x": 100, "y": 200}
        node = _make_node(PIPELINE_NODE_REGISTRY["click"],
                          config={"target": "_last_match_pos",
                                  "target_offset": {"x": -20, "y": 30}})
        result = node.execute(mock_context)
        assert result.success is True
        dev.click.assert_called_once_with(80, 230)

    def test_target_dict_literal(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["click"],
                          config={"target": {"x": 50, "y": 60}})
        result = node.execute(mock_context)
        assert result.success is True
        dev.click.assert_called_once_with(50, 60)

    def test_xy_fallback_when_no_target(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["click"],
                          config={"x": 10, "y": 20})
        result = node.execute(mock_context)
        assert result.success is True
        dev.click.assert_called_once_with(10, 20)

    def test_target_anchor_pos(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        mock_context.variables[ANCHOR_POS_VAR] = {"x": 333, "y": 444}
        node = _make_node(PIPELINE_NODE_REGISTRY["click"],
                          config={"target": "_anchor_pos"})
        result = node.execute(mock_context)
        assert result.success is True
        dev.click.assert_called_once_with(333, 444)

    def test_target_missing_var_returns_fail(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["click"],
                          config={"target": "nonexistent"})
        result = node.execute(mock_context)
        assert result.success is False


# ============================================================
# SwipeNode integration with target / end_target
# ============================================================

class TestSwipeNodeTarget:
    def test_target_and_end_target(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        mock_context.variables["start"] = {"x": 10, "y": 20}
        mock_context.variables["end"] = {"x": 100, "y": 200}
        node = _make_node(PIPELINE_NODE_REGISTRY["swipe"],
                          config={"target": "start", "end_target": "end"})
        result = node.execute(mock_context)
        assert result.success is True
        dev.swipe.assert_called_once_with(10, 20, 100, 200, duration=300)

    def test_target_with_offset_only_start(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        mock_context.variables["start"] = {"x": 10, "y": 20}
        node = _make_node(PIPELINE_NODE_REGISTRY["swipe"],
                          config={"target": "start", "target_offset": {"x": 5, "y": 5},
                                  "x2": 100, "y2": 100})
        result = node.execute(mock_context)
        assert result.success is True
        dev.swipe.assert_called_once_with(15, 25, 100, 100, duration=300)

    def test_xy_fallback_when_no_target(self, mock_context):
        dev = MagicMock()
        mock_context.device = dev
        node = _make_node(PIPELINE_NODE_REGISTRY["swipe"],
                          config={"x1": 1, "y1": 2, "x2": 3, "y2": 4})
        result = node.execute(mock_context)
        assert result.success is True
        dev.swipe.assert_called_once_with(1, 2, 3, 4, duration=300)


# ============================================================
# Constants
# ============================================================

class TestTargetConstants:
    def test_last_match_pos_var_name(self):
        assert LAST_MATCH_POS_VAR == "_last_match_pos"

    def test_anchor_pos_var_name(self):
        assert ANCHOR_POS_VAR == "_anchor_pos"
