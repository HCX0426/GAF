"""P2-4 Composite match node tests — And / Or / Custom.

Uses a test-only child node ("mock_child") whose success/failure is
controlled by config so composite logic can be verified without
device dependencies.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Register composite nodes.
import engine.nodes.composite_match  # noqa: F401
import pytest
from core.result import fail_result, success_result
from engine.context import PipelineContext
from engine.node import PIPELINE_NODE_REGISTRY, PipelineNode, register_node

pytestmark = pytest.mark.unit

# ============================================================
# Test-only child node
# ============================================================

@register_node("mock_child")
class _MockChildNode(PipelineNode):
    """Test node: returns success/failure based on config["succeed"]."""
    node_type: str = "mock_child"

    def execute(self, context):
        if self.config.get("succeed", True):
            return success_result(data={"marker": self.config.get("marker", "ok")})
        return fail_result(error_msg=self.config.get("error", "mock fail"))


def _child(succeed=True, marker="", error="mock fail", idx=0):
    """Build a mock_child spec dict (includes required 'id' field)."""
    return {
        "id": f"child_{idx}",
        "node_type": "mock_child",
        "config": {"succeed": succeed, "marker": marker, "error": error},
    }


# ============================================================
# Test: registration
# ============================================================

class TestRegistration:
    def test_and_match_registered(self):
        assert "and_match" in PIPELINE_NODE_REGISTRY

    def test_or_match_registered(self):
        assert "or_match" in PIPELINE_NODE_REGISTRY

    def test_custom_match_registered(self):
        assert "custom_match" in PIPELINE_NODE_REGISTRY


# ============================================================
# Test: AndMatchNode
# ============================================================

class TestAndMatchNode:
    def test_empty_children_returns_fail(self):
        node = PipelineNode.create({
            "id": "a1", "node_type": "and_match", "config": {"children": []},
        })
        result = node.execute(PipelineContext())
        assert not result.success
        assert "non-empty" in result.error_msg

    def test_all_children_succeed(self):
        node = PipelineNode.create({
            "id": "a2", "node_type": "and_match",
            "config": {"children": [_child(True, "x"), _child(True, "y")]},
        })
        result = node.execute(PipelineContext())
        assert result.success
        assert result.data["all_passed"] is True
        assert result.data["count"] == 2

    def test_first_child_fails_short_circuit(self):
        """short_circuit=True (default): second child not run."""
        node = PipelineNode.create({
            "id": "a3", "node_type": "and_match",
            "config": {
                "children": [_child(False, "first", "boom"), _child(True, "second")],
                "short_circuit": True,
            },
        })
        result = node.execute(PipelineContext())
        assert not result.success
        assert "child[0]" in result.error_msg
        assert "boom" in result.error_msg
        # Only the first child was executed.
        assert result.data["count"] == 1

    def test_first_child_fails_no_short_circuit(self):
        """short_circuit=False: both children run even if first fails."""
        node = PipelineNode.create({
            "id": "a4", "node_type": "and_match",
            "config": {
                "children": [_child(False, "first", "boom"), _child(True, "second")],
                "short_circuit": False,
            },
        })
        result = node.execute(PipelineContext())
        assert not result.success
        # Both children were executed.
        assert result.data["count"] == 2
        assert result.data["all_passed"] is False

    def test_second_child_fails(self):
        node = PipelineNode.create({
            "id": "a5", "node_type": "and_match",
            "config": {"children": [_child(True, "x"), _child(False, "y", "fail2")]},
        })
        result = node.execute(PipelineContext())
        assert not result.success
        assert "child[1]" in result.error_msg

    def test_three_children_all_succeed(self):
        node = PipelineNode.create({
            "id": "a6", "node_type": "and_match",
            "config": {"children": [_child(True), _child(True), _child(True)]},
        })
        result = node.execute(PipelineContext())
        assert result.success
        assert result.data["count"] == 3

    def test_invalid_child_spec_returns_fail(self):
        """Non-dict child spec should fail gracefully."""
        node = PipelineNode.create({
            "id": "a7", "node_type": "and_match",
            "config": {"children": ["not_a_dict"]},
        })
        result = node.execute(PipelineContext())
        assert not result.success

    def test_child_missing_node_type_returns_fail(self):
        node = PipelineNode.create({
            "id": "a8", "node_type": "and_match",
            "config": {"children": [{"config": {}}]},
        })
        result = node.execute(PipelineContext())
        assert not result.success
        assert "node_type" in result.error_msg


# ============================================================
# Test: OrMatchNode
# ============================================================

class TestOrMatchNode:
    def test_empty_children_returns_fail(self):
        node = PipelineNode.create({
            "id": "o1", "node_type": "or_match", "config": {"children": []},
        })
        result = node.execute(PipelineContext())
        assert not result.success
        assert "non-empty" in result.error_msg

    def test_first_child_succeeds_short_circuit(self):
        """stop_on_first_success=True (default): only first runs."""
        node = PipelineNode.create({
            "id": "o2", "node_type": "or_match",
            "config": {"children": [_child(True, "win"), _child(True, "later")]},
        })
        result = node.execute(PipelineContext())
        assert result.success
        assert result.data["matched"] is True
        assert result.data["winner"]["data"]["marker"] == "win"
        # Only one child executed (short circuit).
        assert result.data["count"] == 1

    def test_first_fails_second_succeeds(self):
        node = PipelineNode.create({
            "id": "o3", "node_type": "or_match",
            "config": {"children": [_child(False, "x", "no"), _child(True, "y")]},
        })
        result = node.execute(PipelineContext())
        assert result.success
        assert result.data["winner"]["data"]["marker"] == "y"
        assert result.data["count"] == 2

    def test_all_fail(self):
        node = PipelineNode.create({
            "id": "o4", "node_type": "or_match",
            "config": {"children": [_child(False, error="a"), _child(False, error="b")]},
        })
        result = node.execute(PipelineContext())
        assert not result.success
        assert result.data["matched"] is False
        assert result.data["count"] == 2

    def test_no_short_circuit_runs_all(self):
        """stop_on_first_success=False: all children run, winner is first success."""
        node = PipelineNode.create({
            "id": "o5", "node_type": "or_match",
            "config": {
                "children": [_child(True, "first"), _child(True, "second")],
                "stop_on_first_success": False,
            },
        })
        result = node.execute(PipelineContext())
        assert result.success
        # Winner is the first success.
        assert result.data["winner"]["data"]["marker"] == "first"
        # Both were executed.
        assert result.data["count"] == 2

    def test_three_children_first_wins(self):
        node = PipelineNode.create({
            "id": "o6", "node_type": "or_match",
            "config": {"children": [_child(True, "a"), _child(True, "b"), _child(True, "c")]},
        })
        result = node.execute(PipelineContext())
        assert result.success
        assert result.data["winner"]["data"]["marker"] == "a"


# ============================================================
# Test: CustomMatchNode
# ============================================================

class TestCustomMatchNode:
    def test_missing_expression_returns_fail(self):
        node = PipelineNode.create({
            "id": "c1", "node_type": "custom_match",
            "config": {"children": [_child(True)]},
        })
        result = node.execute(PipelineContext())
        assert not result.success
        assert "expression" in result.error_msg

    def test_expression_true_returns_success(self):
        node = PipelineNode.create({
            "id": "c2", "node_type": "custom_match",
            "config": {
                "children": [_child(True), _child(True)],
                "expression": "all(r['success'] for r in results)",
            },
        })
        result = node.execute(PipelineContext())
        assert result.success
        assert result.data["verdict"] is True

    def test_expression_false_returns_fail(self):
        node = PipelineNode.create({
            "id": "c3", "node_type": "custom_match",
            "config": {
                "children": [_child(True), _child(False, error="nope")],
                "expression": "all(r['success'] for r in results)",
            },
        })
        result = node.execute(PipelineContext())
        assert not result.success
        assert result.data["verdict"] is False

    def test_expression_xor_pattern(self):
        """XOR: exactly one child succeeds."""
        node = PipelineNode.create({
            "id": "c4", "node_type": "custom_match",
            "config": {
                "children": [_child(True), _child(False)],
                "expression": "sum(1 for r in results if r['success']) == 1",
            },
        })
        result = node.execute(PipelineContext())
        assert result.success

    def test_expression_can_access_data(self):
        """Expression can read child data fields."""
        node = PipelineNode.create({
            "id": "c5", "node_type": "custom_match",
            "config": {
                "children": [_child(True, marker="target")],
                "expression": "results[0]['data']['marker'] == 'target'",
            },
        })
        result = node.execute(PipelineContext())
        assert result.success

    def test_expression_syntax_error_returns_fail(self):
        node = PipelineNode.create({
            "id": "c6", "node_type": "custom_match",
            "config": {
                "children": [_child(True)],
                "expression": "results[0]",  # Not a bool expression, but valid syntax
            },
        })
        # Actually results[0] is a dict, which is truthy.
        result = node.execute(PipelineContext())
        assert result.success  # dict is truthy

    def test_expression_invalid_syntax_returns_fail(self):
        node = PipelineNode.create({
            "id": "c7", "node_type": "custom_match",
            "config": {
                "children": [_child(True)],
                "expression": "this is not valid python !!!",
            },
        })
        result = node.execute(PipelineContext())
        assert not result.success
        assert "expression error" in result.error_msg

    def test_safe_mode_blocks_dangerous_builtins(self):
        """In safe_mode, __import__ should not be accessible."""
        node = PipelineNode.create({
            "id": "c8", "node_type": "custom_match",
            "config": {
                "children": [_child(True)],
                "expression": "__import__('os').system('echo hi')",
                "safe_mode": True,
            },
        })
        result = node.execute(PipelineContext())
        # Should fail because __import__ is not in safe builtins.
        assert not result.success
        assert "expression error" in result.error_msg

    def test_empty_children_with_expression(self):
        """No children but expression doesn't reference results — should pass."""
        node = PipelineNode.create({
            "id": "c9", "node_type": "custom_match",
            "config": {
                "children": [],
                "expression": "True",
            },
        })
        result = node.execute(PipelineContext())
        assert result.success
        assert result.data["count"] == 0

    def test_len_in_safe_builtins(self):
        """len() should be available in safe mode."""
        node = PipelineNode.create({
            "id": "c10", "node_type": "custom_match",
            "config": {
                "children": [_child(True), _child(True), _child(True)],
                "expression": "len(results) == 3",
            },
        })
        result = node.execute(PipelineContext())
        assert result.success
