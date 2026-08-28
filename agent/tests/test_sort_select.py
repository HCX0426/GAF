"""P2-6 SortSelect node tests — order_by / index selection.

Verifies sorting (asc/desc), index selection (incl. negative), nested
path keys (center.x), dict-with-list-field inputs, publish_match_pos
side effect, and error paths.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Register nodes.
import engine.nodes.sort_select  # noqa: F401
import pytest
from engine.context import PipelineContext
from engine.node import PIPELINE_NODE_REGISTRY, PipelineNode
from engine.nodes.sort_select import _get_nested
from engine.target import LAST_MATCH_POS_VAR

pytestmark = pytest.mark.unit

# ============================================================
# Test: registration
# ============================================================

class TestRegistration:
    def test_sort_select_registered(self):
        assert "sort_select" in PIPELINE_NODE_REGISTRY


# ============================================================
# Test: _get_nested helper
# ============================================================

class TestGetNested:
    def test_top_level_key(self):
        obj = {"x": 10, "y": 20}
        assert _get_nested(obj, "x") == 10

    def test_dotted_path(self):
        obj = {"center": {"x": 5, "y": 15}}
        assert _get_nested(obj, "center.x") == 5
        assert _get_nested(obj, "center.y") == 15

    def test_missing_key_returns_none(self):
        obj = {"x": 1}
        assert _get_nested(obj, "z") is None

    def test_missing_nested_key_returns_none(self):
        obj = {"center": {"x": 1}}
        assert _get_nested(obj, "center.z") is None

    def test_empty_path_returns_none(self):
        obj = {"x": 1}
        assert _get_nested(obj, "") is None

    def test_attribute_fallback(self):
        class _Obj:
            def __init__(self):
                self.foo = "bar"
        assert _get_nested(_Obj(), "foo") == "bar"


# ============================================================
# Test: SortSelectNode basic
# ============================================================

class TestSortSelectBasic:
    def test_missing_input_variable_returns_fail(self):
        node = PipelineNode.create({
            "id": "s1", "node_type": "sort_select", "config": {},
        })
        result = node.execute(PipelineContext())
        assert not result.success
        assert "input_variable" in result.error_msg

    def test_variable_not_found_returns_fail(self):
        node = PipelineNode.create({
            "id": "s2", "node_type": "sort_select",
            "config": {"input_variable": "missing_var"},
        })
        result = node.execute(PipelineContext())
        assert not result.success
        assert "not found" in result.error_msg

    def test_empty_list_returns_fail(self):
        ctx = PipelineContext()
        ctx.set_variable("items", [])
        node = PipelineNode.create({
            "id": "s3", "node_type": "sort_select",
            "config": {"input_variable": "items"},
        })
        result = node.execute(ctx)
        assert not result.success
        assert "empty" in result.error_msg

    def test_non_list_variable_returns_fail(self):
        ctx = PipelineContext()
        ctx.set_variable("items", "not_a_list")
        node = PipelineNode.create({
            "id": "s4", "node_type": "sort_select",
            "config": {"input_variable": "items"},
        })
        result = node.execute(ctx)
        assert not result.success
        assert "not a list" in result.error_msg


# ============================================================
# Test: SortSelectNode sorting
# ============================================================

class TestSortSelectSorting:
    def test_no_order_by_preserves_order(self):
        ctx = PipelineContext()
        ctx.set_variable("items", [{"v": 3}, {"v": 1}, {"v": 2}])
        node = PipelineNode.create({
            "id": "s5", "node_type": "sort_select",
            "config": {"input_variable": "items", "index": 0},
        })
        result = node.execute(ctx)
        assert result.success
        assert result.data["selected"]["v"] == 3  # No sort, first element.

    def test_order_by_desc(self):
        ctx = PipelineContext()
        ctx.set_variable("items", [{"v": 3}, {"v": 1}, {"v": 2}])
        node = PipelineNode.create({
            "id": "s6", "node_type": "sort_select",
            "config": {
                "input_variable": "items",
                "order_by": "v",
                "order": "desc",
                "index": 0,
            },
        })
        result = node.execute(ctx)
        assert result.success
        assert result.data["selected"]["v"] == 3  # Highest first.

    def test_order_by_asc(self):
        ctx = PipelineContext()
        ctx.set_variable("items", [{"v": 3}, {"v": 1}, {"v": 2}])
        node = PipelineNode.create({
            "id": "s7", "node_type": "sort_select",
            "config": {
                "input_variable": "items",
                "order_by": "v",
                "order": "asc",
                "index": 0,
            },
        })
        result = node.execute(ctx)
        assert result.success
        assert result.data["selected"]["v"] == 1  # Lowest first.

    def test_order_by_default_is_desc(self):
        ctx = PipelineContext()
        ctx.set_variable("items", [{"v": 1}, {"v": 9}, {"v": 5}])
        node = PipelineNode.create({
            "id": "s8", "node_type": "sort_select",
            "config": {
                "input_variable": "items",
                "order_by": "v",  # No order field → default desc.
                "index": 0,
            },
        })
        result = node.execute(ctx)
        assert result.success
        assert result.data["selected"]["v"] == 9

    def test_order_by_dotted_path(self):
        ctx = PipelineContext()
        ctx.set_variable("items", [
            {"center": {"x": 100}},
            {"center": {"x": 50}},
            {"center": {"x": 200}},
        ])
        node = PipelineNode.create({
            "id": "s9", "node_type": "sort_select",
            "config": {
                "input_variable": "items",
                "order_by": "center.x",
                "order": "asc",
                "index": 0,
            },
        })
        result = node.execute(ctx)
        assert result.success
        assert result.data["selected"]["center"]["x"] == 50

    def test_index_selects_after_sort(self):
        """Pick the 2nd-highest by sorting desc and using index=1."""
        ctx = PipelineContext()
        ctx.set_variable("items", [{"v": 1}, {"v": 9}, {"v": 5}])
        node = PipelineNode.create({
            "id": "s10", "node_type": "sort_select",
            "config": {
                "input_variable": "items",
                "order_by": "v",
                "order": "desc",
                "index": 1,
            },
        })
        result = node.execute(ctx)
        assert result.success
        assert result.data["selected"]["v"] == 5  # 2nd highest.

    def test_negative_index_selects_last(self):
        ctx = PipelineContext()
        ctx.set_variable("items", [{"v": 1}, {"v": 9}, {"v": 5}])
        node = PipelineNode.create({
            "id": "s11", "node_type": "sort_select",
            "config": {
                "input_variable": "items",
                "order_by": "v",
                "order": "desc",
                "index": -1,
            },
        })
        result = node.execute(ctx)
        assert result.success
        assert result.data["selected"]["v"] == 1  # Last after desc sort.

    def test_index_out_of_range_returns_fail(self):
        ctx = PipelineContext()
        ctx.set_variable("items", [{"v": 1}])
        node = PipelineNode.create({
            "id": "s12", "node_type": "sort_select",
            "config": {
                "input_variable": "items",
                "order_by": "v",
                "index": 5,
            },
        })
        result = node.execute(ctx)
        assert not result.success
        assert "out of range" in result.error_msg

    def test_missing_sort_key_treated_as_inf_for_asc(self):
        """Items missing the sort key are placed at the end for asc."""
        ctx = PipelineContext()
        ctx.set_variable("items", [{"v": 5}, {"no_v": True}, {"v": 1}])
        node = PipelineNode.create({
            "id": "s13", "node_type": "sort_select",
            "config": {
                "input_variable": "items",
                "order_by": "v",
                "order": "asc",
                "index": 2,  # The missing-key item should be at index 2.
            },
        })
        result = node.execute(ctx)
        assert result.success
        assert "no_v" in result.data["selected"]


# ============================================================
# Test: output_variable + publish_match_pos
# ============================================================

class TestOutputAndPublish:
    def test_default_output_variable_name(self):
        ctx = PipelineContext()
        ctx.set_variable("items", [{"v": 1}])
        node = PipelineNode.create({
            "id": "s14", "node_type": "sort_select",
            "config": {"input_variable": "items"},
        })
        result = node.execute(ctx)
        assert result.success
        # Default output variable: f"{node_id}_selected"
        assert ctx.get_variable("s14_selected") == {"v": 1}

    def test_custom_output_variable_name(self):
        ctx = PipelineContext()
        ctx.set_variable("items", [{"v": 1}])
        node = PipelineNode.create({
            "id": "s15", "node_type": "sort_select",
            "config": {
                "input_variable": "items",
                "output_variable": "chosen_one",
            },
        })
        result = node.execute(ctx)
        assert result.success
        assert ctx.get_variable("chosen_one") == {"v": 1}

    def test_publish_match_pos_top_level_xy(self):
        """Selected item with top-level x/y publishes _last_match_pos."""
        ctx = PipelineContext()
        ctx.set_variable("items", [{"x": 42, "y": 99, "v": 1}])
        node = PipelineNode.create({
            "id": "s16", "node_type": "sort_select",
            "config": {"input_variable": "items"},
        })
        result = node.execute(ctx)
        assert result.success
        pos = ctx.get_variable(LAST_MATCH_POS_VAR)
        assert pos is not None
        assert pos["x"] == 42
        assert pos["y"] == 99

    def test_publish_match_pos_center_xy(self):
        """Selected item with center.x/y publishes _last_match_pos."""
        ctx = PipelineContext()
        ctx.set_variable("items", [{"center": {"x": 7, "y": 8}, "v": 1}])
        node = PipelineNode.create({
            "id": "s17", "node_type": "sort_select",
            "config": {"input_variable": "items"},
        })
        result = node.execute(ctx)
        assert result.success
        pos = ctx.get_variable(LAST_MATCH_POS_VAR)
        assert pos["x"] == 7
        assert pos["y"] == 8

    def test_publish_match_pos_disabled(self):
        """publish_match_pos=False skips publishing."""
        ctx = PipelineContext()
        ctx.set_variable("items", [{"x": 42, "y": 99, "v": 1}])
        node = PipelineNode.create({
            "id": "s18", "node_type": "sort_select",
            "config": {
                "input_variable": "items",
                "publish_match_pos": False,
            },
        })
        result = node.execute(ctx)
        assert result.success
        assert ctx.get_variable(LAST_MATCH_POS_VAR) is None

    def test_publish_match_pos_skipped_without_xy(self):
        """Selected item without x/y or center.x/y → no publish, no crash."""
        ctx = PipelineContext()
        ctx.set_variable("items", [{"v": 1}])  # No x/y.
        node = PipelineNode.create({
            "id": "s19", "node_type": "sort_select",
            "config": {"input_variable": "items"},
        })
        result = node.execute(ctx)
        assert result.success
        assert ctx.get_variable(LAST_MATCH_POS_VAR) is None


# ============================================================
# Test: variable reference syntax
# ============================================================

class TestVariableReference:
    def test_dollar_brace_syntax(self):
        """${var} syntax should resolve to var name."""
        ctx = PipelineContext()
        ctx.set_variable("my_list", [{"v": 1}])
        node = PipelineNode.create({
            "id": "s20", "node_type": "sort_select",
            "config": {"input_variable": "${my_list}"},
        })
        result = node.execute(ctx)
        assert result.success
        assert result.data["selected"]["v"] == 1

    def test_dict_with_list_field_contours(self):
        """Dict input with 'contours' field should auto-detect list."""
        ctx = PipelineContext()
        ctx.set_variable("result", {"contours": [{"v": 1}, {"v": 2}]})
        node = PipelineNode.create({
            "id": "s21", "node_type": "sort_select",
            "config": {
                "input_variable": "result",
                "order_by": "v",
                "order": "desc",
            },
        })
        result = node.execute(ctx)
        assert result.success
        assert result.data["selected"]["v"] == 2

    def test_dict_with_list_field_boxes(self):
        """Dict input with 'boxes' field should auto-detect list."""
        ctx = PipelineContext()
        ctx.set_variable("result", {"boxes": [{"v": 5}, {"v": 9}]})
        node = PipelineNode.create({
            "id": "s22", "node_type": "sort_select",
            "config": {
                "input_variable": "result",
                "order_by": "v",
                "order": "desc",
            },
        })
        result = node.execute(ctx)
        assert result.success
        assert result.data["selected"]["v"] == 9

    def test_dict_with_list_field_matches(self):
        """Dict input with 'matches' field should auto-detect list."""
        ctx = PipelineContext()
        ctx.set_variable("result", {"matches": [{"v": 1}]})
        node = PipelineNode.create({
            "id": "s23", "node_type": "sort_select",
            "config": {"input_variable": "result"},
        })
        result = node.execute(ctx)
        assert result.success

    def test_dict_without_list_field_returns_fail(self):
        ctx = PipelineContext()
        ctx.set_variable("result", {"foo": "bar"})
        node = PipelineNode.create({
            "id": "s24", "node_type": "sort_select",
            "config": {"input_variable": "result"},
        })
        result = node.execute(ctx)
        assert not result.success
        assert "without list field" in result.error_msg


# ============================================================
# Test: result_data contents
# ============================================================

class TestResultData:
    def test_result_data_includes_metadata(self):
        ctx = PipelineContext()
        ctx.set_variable("items", [{"v": 1}, {"v": 2}])
        node = PipelineNode.create({
            "id": "s25", "node_type": "sort_select",
            "config": {
                "input_variable": "items",
                "order_by": "v",
                "order": "desc",
                "index": 0,
            },
        })
        result = node.execute(ctx)
        assert result.success
        data = result.data
        assert data["input_variable"] == "items"
        assert data["order_by"] == "v"
        assert data["order"] == "desc"
        assert data["index"] == 0
        assert data["list_length"] == 2
        assert data["selected"]["v"] == 2
        assert data["output_variable"] == "s25_selected"
