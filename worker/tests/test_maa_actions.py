"""Maa protocol action nodes unit tests (N126-F2 + N128-F2).

Covers 5 nodes:
- JumpBackNode: jump back to previous node
- WaitFreezesNode: wait until screen stabilizes
- NextNode: skip to next node
- StopNode: stop pipeline execution
- AnchorNode (N128-F2): compute target position based on reference element offset
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import to register nodes
import engine.nodes.maa_actions  # noqa: F401
from engine.node import PIPELINE_NODE_REGISTRY

pytestmark = pytest.mark.unit

# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_context():
    """Build a mock PipelineContext with variables dict and execution_history."""
    ctx = MagicMock()
    ctx.variables = {}
    ctx.execution_history = []
    ctx.device = None

    def set_var(key, value):
        ctx.variables[key] = value

    def get_var(key, default=None):
        return ctx.variables.get(key, default)

    ctx.set_variable.side_effect = set_var
    ctx.get_variable.side_effect = get_var
    return ctx


def _make_node(node_cls, node_id="test_node", config=None):
    """Helper to instantiate a node with common defaults."""
    return node_cls(
        id=node_id,
        name=node_id,
        node_type=node_cls.node_type,
        config=config or {},
        next_node_id="next_default",
    )


# ============================================================
# JumpBackNode tests
# ============================================================

class TestJumpBackNode:
    """JumpBack: jump back to previous node for re-execution."""

    def test_registered(self):
        assert "jump_back" in PIPELINE_NODE_REGISTRY

    def test_jump_back_with_explicit_target(self, mock_context):
        node = _make_node(
            PIPELINE_NODE_REGISTRY["jump_back"],
            config={"target_node_id": "prev_node"},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target_node_id"] == "prev_node"
        assert mock_context.variables["_jump_back_target"] == "prev_node"
        assert mock_context.variables["_jump_back_source"] == "test_node"

    def test_jump_back_default_steps_back_1(self, mock_context):
        """Without target_node_id, use history to find previous node."""
        mock_context.execution_history = [
            {"node_id": "node_a"},
            {"node_id": "node_b"},
            {"node_id": "test_node"},  # current
        ]
        node = _make_node(PIPELINE_NODE_REGISTRY["jump_back"])
        result = node.execute(mock_context)
        assert result.success is True
        # Should jump back 1 step (to node_b)
        assert result.data["target_node_id"] == "node_b"

    def test_jump_back_steps_back_2(self, mock_context):
        mock_context.execution_history = [
            {"node_id": "node_a"},
            {"node_id": "node_b"},
            {"node_id": "node_c"},
            {"node_id": "test_node"},
        ]
        node = _make_node(
            PIPELINE_NODE_REGISTRY["jump_back"],
            config={"steps_back": 2},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target_node_id"] == "node_b"

    def test_jump_back_empty_history_fails(self, mock_context):
        node = _make_node(PIPELINE_NODE_REGISTRY["jump_back"])
        result = node.execute(mock_context)
        assert result.success is False
        assert "no previous node" in result.error_msg

    def test_jump_back_short_history_fails(self, mock_context):
        mock_context.execution_history = []
        node = _make_node(
            PIPELINE_NODE_REGISTRY["jump_back"],
            config={"steps_back": 5},
        )
        result = node.execute(mock_context)
        assert result.success is False


# ============================================================
# WaitFreezesNode tests
# ============================================================

class TestWaitFreezesNode:
    """WaitFreezes: wait until screen stabilizes."""

    def test_registered(self):
        assert "wait_freezes" in PIPELINE_NODE_REGISTRY

    def test_no_device_fails(self, mock_context):
        mock_context.device = None
        node = _make_node(PIPELINE_NODE_REGISTRY["wait_freezes"])
        result = node.execute(mock_context)
        assert result.success is False
        assert "no device" in result.error_msg

    def test_stable_screen_success(self, mock_context):
        """When capture returns identical frames, should succeed quickly."""
        mock_context.device = MagicMock()
        # Return same frame every time → instantly stable
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_context.device.capture_screen.return_value = frame

        node = _make_node(
            PIPELINE_NODE_REGISTRY["wait_freezes"],
            config={"timeout": 2.0, "interval_ms": 10, "stable_frames": 3},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["stable"] is True

    def test_changing_screen_timeout(self, mock_context):
        """When capture returns very different frames each time, should timeout."""
        mock_context.device = MagicMock()
        call_count = [0]

        def changing_capture():
            call_count[0] += 1
            # Alternate between black and white frames (max difference)
            val = 0 if call_count[0] % 2 == 0 else 255
            return np.full((100, 100, 3), val, dtype=np.uint8)

        mock_context.device.capture_screen.side_effect = changing_capture

        node = _make_node(
            PIPELINE_NODE_REGISTRY["wait_freezes"],
            config={"timeout": 0.3, "interval_ms": 10, "stable_frames": 3, "similarity": 0.99},
        )
        result = node.execute(mock_context)
        assert result.success is False
        assert "timeout" in result.error_msg.lower()

    def test_with_roi(self, mock_context):
        """ROI config should be passed to WaitFreezes as diff_region."""
        mock_context.device = MagicMock()
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        mock_context.device.capture_screen.return_value = frame

        node = _make_node(
            PIPELINE_NODE_REGISTRY["wait_freezes"],
            config={
                "timeout": 1.0,
                "interval_ms": 10,
                "stable_frames": 2,
                "roi": {"x": 10, "y": 20, "w": 50, "h": 60},
            },
        )
        result = node.execute(mock_context)
        assert result.success is True

    def test_capture_returns_none_handled(self, mock_context):
        """If capture returns None, should not crash, eventually timeout."""
        mock_context.device = MagicMock()
        mock_context.device.capture_screen.return_value = None

        node = _make_node(
            PIPELINE_NODE_REGISTRY["wait_freezes"],
            config={"timeout": 0.3, "interval_ms": 10, "stable_frames": 3},
        )
        result = node.execute(mock_context)
        assert result.success is False


# ============================================================
# NextNode tests
# ============================================================

class TestNextNode:
    """Next: skip to next node."""

    def test_registered(self):
        assert "next" in PIPELINE_NODE_REGISTRY

    def test_next_with_explicit_target(self, mock_context):
        node = _make_node(
            PIPELINE_NODE_REGISTRY["next"],
            config={"target_node_id": "explicit_next"},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target_node_id"] == "explicit_next"
        assert mock_context.variables["_next_override"] == "explicit_next"
        assert mock_context.variables["_next_source"] == "test_node"

    def test_next_uses_default_next_node_id(self, mock_context):
        """Without target_node_id, use node's next_node_id attribute."""
        node = _make_node(PIPELINE_NODE_REGISTRY["next"])
        # _make_node sets next_node_id="next_default"
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target_node_id"] == "next_default"

    def test_next_no_target_fails(self, mock_context):
        """Without target_node_id or next_node_id, should fail."""
        node_cls = PIPELINE_NODE_REGISTRY["next"]
        node = node_cls(
            id="test_node",
            name="test_node",
            node_type="next",
            config={},
            next_node_id=None,  # Explicitly None
        )
        result = node.execute(mock_context)
        assert result.success is False
        assert "no target_node_id" in result.error_msg


# ============================================================
# StopNode tests
# ============================================================

class TestStopNode:
    """Stop: stop pipeline execution."""

    def test_registered(self):
        assert "stop" in PIPELINE_NODE_REGISTRY

    def test_stop_default_reason(self, mock_context):
        node = _make_node(PIPELINE_NODE_REGISTRY["stop"])
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["reason"] == "user requested"
        assert result.data["save_state"] is True
        assert mock_context.variables["_stop_requested"] is True
        assert mock_context.variables["_stop_reason"] == "user requested"
        assert mock_context.variables["_stop_source"] == "test_node"
        assert mock_context.variables["_stop_save_state"] is True

    def test_stop_custom_reason(self, mock_context):
        node = _make_node(
            PIPELINE_NODE_REGISTRY["stop"],
            config={"reason": "task completed", "save_state": False},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["reason"] == "task completed"
        assert result.data["save_state"] is False
        assert mock_context.variables["_stop_reason"] == "task completed"
        assert mock_context.variables["_stop_save_state"] is False

    def test_stop_sets_all_context_vars(self, mock_context):
        node = _make_node(PIPELINE_NODE_REGISTRY["stop"])
        node.execute(mock_context)
        # Verify all 5 stop-related variables are set
        expected_vars = [
            "_stop_requested",
            "_stop_reason",
            "_stop_source",
            "_stop_save_state",
        ]
        for var in expected_vars:
            assert var in mock_context.variables, f"Missing var: {var}"


# ============================================================
# Integration: all 5 nodes registered
# ============================================================

class TestAllNodesRegistered:
    """Verify all 5 Maa action nodes are registered."""

    def test_all_5_nodes_registered(self):
        expected = {"jump_back", "wait_freezes", "next", "stop", "anchor"}
        registered = set(PIPELINE_NODE_REGISTRY.keys())
        missing = expected - registered
        assert not missing, f"Missing nodes: {missing}"


# ============================================================
# AnchorNode tests (N128-F2)
# ============================================================

class TestAnchorNode:
    """Anchor: compute target position based on reference element offset."""

    def test_registered(self):
        assert "anchor" in PIPELINE_NODE_REGISTRY

    def test_anchor_center_reference_with_offset(self, mock_context):
        """Center reference + positive offset → target = ref + offset."""
        mock_context.set_variable("_last_match_pos", {"x": 100, "y": 200})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": 50, "offset_y": -30},
        )
        result = node.execute(mock_context)
        assert result.success is True
        target = result.data["target"]
        assert target["x"] == 150
        assert target["y"] == 170
        assert target["source"] == "anchor"

    def test_anchor_default_reference_variable(self, mock_context):
        """Default reference_variable is _last_match_pos."""
        mock_context.set_variable("_last_match_pos", {"x": 50, "y": 60})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": 10, "offset_y": 10},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target"]["x"] == 60
        assert result.data["target"]["y"] == 70

    def test_anchor_custom_reference_variable(self, mock_context):
        """Custom reference_variable reads from a different context var."""
        mock_context.set_variable("my_ref", {"x": 200, "y": 300})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"reference_variable": "my_ref", "offset_x": 0, "offset_y": 0},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target"]["x"] == 200
        assert result.data["target"]["y"] == 300

    def test_anchor_missing_reference_variable(self, mock_context):
        """Missing reference variable → failure with descriptive error."""
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"reference_variable": "nonexistent", "offset_x": 0, "offset_y": 0},
        )
        result = node.execute(mock_context)
        assert result.success is False
        assert "not found" in result.error_msg
        assert "nonexistent" in result.error_msg

    def test_anchor_top_left_reference_with_size(self, mock_context):
        """top_left reference + w/h → center computed from top-left + half size."""
        mock_context.set_variable("_last_match_pos", {"x": 100, "y": 100, "w": 40, "h": 60})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"reference_type": "top_left", "offset_x": 0, "offset_y": 0},
        )
        result = node.execute(mock_context)
        assert result.success is True
        # center = (100 + 40//2, 100 + 60//2) = (120, 130)
        assert result.data["target"]["x"] == 120
        assert result.data["target"]["y"] == 130

    def test_anchor_top_left_without_size_falls_back_to_center(self, mock_context):
        """top_left reference without w/h → treated as center (with warning)."""
        mock_context.set_variable("_last_match_pos", {"x": 100, "y": 100})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"reference_type": "top_left", "offset_x": 0, "offset_y": 0},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target"]["x"] == 100
        assert result.data["target"]["y"] == 100

    def test_anchor_custom_reference_type(self, mock_context):
        """custom reference_type uses (x, y) as-is."""
        mock_context.set_variable("_last_match_pos", {"x": 250, "y": 350})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"reference_type": "custom", "offset_x": 10, "offset_y": 10},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target"]["x"] == 260
        assert result.data["target"]["y"] == 360

    def test_anchor_tuple_reference(self, mock_context):
        """Reference can be a (x, y) tuple."""
        mock_context.set_variable("_last_match_pos", (150, 250))
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": 10, "offset_y": 10},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target"]["x"] == 160
        assert result.data["target"]["y"] == 260

    def test_anchor_tuple_reference_with_size(self, mock_context):
        """Reference can be a (x, y, w, h) tuple for top_left reference_type."""
        mock_context.set_variable("_last_match_pos", (100, 100, 40, 60))
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"reference_type": "top_left", "offset_x": 0, "offset_y": 0},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target"]["x"] == 120
        assert result.data["target"]["y"] == 130

    def test_anchor_negative_offset(self, mock_context):
        """Negative offsets are supported."""
        mock_context.set_variable("_last_match_pos", {"x": 500, "y": 500})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": -100, "offset_y": -200},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target"]["x"] == 400
        assert result.data["target"]["y"] == 300

    def test_anchor_absolute_mode(self, mock_context):
        """absolute=True → target = (offset_x, offset_y), ignoring reference."""
        mock_context.set_variable("_last_match_pos", {"x": 999, "y": 999})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": 100, "offset_y": 200, "absolute": True},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target"]["x"] == 100
        assert result.data["target"]["y"] == 200
        assert result.data["target"]["offset"]["absolute"] is True

    def test_anchor_output_variable(self, mock_context):
        """Computed target is stored in output_variable (default _anchor_pos)."""
        mock_context.set_variable("_last_match_pos", {"x": 100, "y": 100})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": 50, "offset_y": 50},
        )
        result = node.execute(mock_context)
        assert result.success is True
        # Default output_variable
        assert "_anchor_pos" in mock_context.variables
        assert mock_context.variables["_anchor_pos"]["x"] == 150
        assert mock_context.variables["_anchor_pos"]["y"] == 150

    def test_anchor_custom_output_variable(self, mock_context):
        """Custom output_variable stores target in a different context var."""
        mock_context.set_variable("_last_match_pos", {"x": 100, "y": 100})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": 50, "offset_y": 50, "output_variable": "my_target"},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert "my_target" in mock_context.variables
        assert mock_context.variables["my_target"]["x"] == 150

    def test_anchor_updates_last_match_pos(self, mock_context):
        """Anchor also updates _last_match_pos so click/swipe nodes pick it up."""
        mock_context.set_variable("_last_match_pos", {"x": 100, "y": 100})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": 50, "offset_y": 50},
        )
        result = node.execute(mock_context)
        assert result.success is True
        # _last_match_pos should be updated to the computed target
        assert mock_context.variables["_last_match_pos"]["x"] == 150
        assert mock_context.variables["_last_match_pos"]["y"] == 150

    def test_anchor_invalid_reference_type(self, mock_context):
        """Invalid reference_type → failure."""
        mock_context.set_variable("_last_match_pos", {"x": 100, "y": 100})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"reference_type": "invalid_type", "offset_x": 0, "offset_y": 0},
        )
        result = node.execute(mock_context)
        assert result.success is False
        assert "cannot extract center" in result.error_msg

    def test_anchor_invalid_reference_format(self, mock_context):
        """Reference of wrong type (string) → failure."""
        mock_context.set_variable("_last_match_pos", "not_a_position")
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": 0, "offset_y": 0},
        )
        result = node.execute(mock_context)
        assert result.success is False
        assert "cannot extract center" in result.error_msg

    def test_anchor_dict_missing_x(self, mock_context):
        """Reference dict missing 'x' key → failure."""
        mock_context.set_variable("_last_match_pos", {"y": 100})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": 0, "offset_y": 0},
        )
        result = node.execute(mock_context)
        assert result.success is False
        assert "cannot extract center" in result.error_msg

    def test_anchor_tuple_too_short(self, mock_context):
        """Reference tuple with < 2 elements → failure."""
        mock_context.set_variable("_last_match_pos", (100,))
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": 0, "offset_y": 0},
        )
        result = node.execute(mock_context)
        assert result.success is False
        assert "cannot extract center" in result.error_msg

    def test_anchor_result_data_structure(self, mock_context):
        """Result data contains action/target/output_variable/source_node_id."""
        mock_context.set_variable("_last_match_pos", {"x": 100, "y": 100})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": 50, "offset_y": 50, "output_variable": "out_var"},
        )
        result = node.execute(mock_context)
        assert result.success is True
        data = result.data
        assert data["action"] == "anchor"
        assert "target" in data
        assert data["output_variable"] == "out_var"
        assert data["source_node_id"] == "test_node"
        # target structure
        target = data["target"]
        assert target["x"] == 150
        assert target["y"] == 150
        assert target["source"] == "anchor"
        assert "reference" in target
        assert "offset" in target
        assert target["reference"]["x"] == 100
        assert target["reference"]["y"] == 100
        assert target["offset"]["x"] == 50
        assert target["offset"]["y"] == 50

    def test_anchor_zero_offset(self, mock_context):
        """Zero offset → target = reference."""
        mock_context.set_variable("_last_match_pos", {"x": 100, "y": 100})
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": 0, "offset_y": 0},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target"]["x"] == 100
        assert result.data["target"]["y"] == 100

    def test_anchor_list_reference(self, mock_context):
        """Reference can be a list [x, y]."""
        mock_context.set_variable("_last_match_pos", [100, 200])
        node = _make_node(
            PIPELINE_NODE_REGISTRY["anchor"],
            config={"offset_x": 10, "offset_y": 10},
        )
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target"]["x"] == 110
        assert result.data["target"]["y"] == 210
