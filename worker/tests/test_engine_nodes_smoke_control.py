"""TD-336 #7: 控制流/生命周期类节点 smoke 测试

覆盖 7 个控制流节点 (含子节点):
- LoopNode (loop): for/while 初始化控制变量
- BranchNode (branch): 条件评估选 true/false 分支
- GotoNode (goto): 无条件跳转
- MaaActions: jump_back / wait_freezes / next / stop / anchor (5 nodes)
- SubPipelineNode (sub_pipeline): 无 pipeline_json/深度上限
- MonitorNode (monitor): skip_story/report_error/screenshot_monitor/popup 无 manager
- DeviceControlNode (device_control): switch_window/start_emulator/screenshot/未知

使用 MagicMock 模拟 PipelineContext 与 device, 不依赖真实 OpenCV.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import to register nodes.
import engine.nodes.branch  # noqa: F401
import engine.nodes.device_control  # noqa: F401
import engine.nodes.goto  # noqa: F401
import engine.nodes.loop  # noqa: F401
import engine.nodes.maa_actions  # noqa: F401
import engine.nodes.monitor  # noqa: F401
import engine.nodes.sub_pipeline  # noqa: F401
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
    ctx.execution_history = []
    ctx.coord_transformer = None

    def set_var(key, value):
        ctx.variables[key] = value

    def get_var(key, default=None):
        return ctx.variables.get(key, default)

    ctx.set_variable.side_effect = set_var
    ctx.get_variable.side_effect = get_var
    return ctx


def _make_node(node_type, node_id="test_node", config=None, next_node_id=None):
    return PIPELINE_NODE_REGISTRY[node_type].from_dict({
        "id": node_id,
        "node_type": node_type,
        "config": config or {},
        "next_node_id": next_node_id,
    })


# ============================================================
# Registration
# ============================================================

class TestRegistration:
    def test_loop_registered(self):
        assert "loop" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["loop"].__name__ == "LoopNode"

    def test_branch_registered(self):
        assert "branch" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["branch"].__name__ == "BranchNode"

    def test_goto_registered(self):
        assert "goto" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["goto"].__name__ == "GotoNode"

    def test_jump_back_registered(self):
        assert "jump_back" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["jump_back"].__name__ == "JumpBackNode"

    def test_wait_freezes_registered(self):
        assert "wait_freezes" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["wait_freezes"].__name__ == "WaitFreezesNode"

    def test_next_registered(self):
        assert "next" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["next"].__name__ == "NextNode"

    def test_stop_registered(self):
        assert "stop" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["stop"].__name__ == "StopNode"

    def test_anchor_registered(self):
        assert "anchor" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["anchor"].__name__ == "AnchorNode"

    def test_sub_pipeline_registered(self):
        assert "sub_pipeline" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["sub_pipeline"].__name__ == "SubPipelineNode"

    def test_monitor_registered(self):
        assert "monitor" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["monitor"].__name__ == "MonitorNode"

    def test_device_control_registered(self):
        assert "device_control" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["device_control"].__name__ == "DeviceControlNode"


# ============================================================
# LoopNode
# ============================================================

class TestLoopNode:
    """LoopNode: for/while 循环控制变量初始化."""

    def test_for_loop_initializes_control_vars(self, mock_context):
        node = _make_node("loop", config={
            "loop_type": "for", "max_iterations": 5, "body_nodes": ["b1", "b2"],
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["loop_type"] == "for"
        assert result.data["max_iterations"] == 5
        assert result.data["body_nodes"] == ["b1", "b2"]
        # Control variables set on context.
        assert mock_context.variables["_loop_active"] is True
        assert mock_context.variables["_loop_type"] == "for"
        assert mock_context.variables["_loop_iteration"] == 0
        assert mock_context.variables["_loop_max"] == 5
        assert mock_context.variables["_loop_body"] == ["b1", "b2"]

    def test_while_loop_initializes_condition_vars(self, mock_context):
        node = _make_node("loop", config={
            "loop_type": "while",
            "condition_variable": "counter",
            "condition_operator": "lt",
            "condition_value": 10,
            "body_nodes": ["b1"],
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["loop_type"] == "while"
        assert result.data["condition_variable"] == "counter"
        # Condition vars set on context.
        assert mock_context.variables["_loop_cond_var"] == "counter"
        assert mock_context.variables["_loop_cond_op"] == "lt"
        assert mock_context.variables["_loop_cond_val"] == 10

    def test_unknown_loop_type_returns_fail(self, mock_context):
        node = _make_node("loop", config={"loop_type": "repeat_until"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "未知循环类型" in result.error_msg
        # Loop slot deactivated.
        assert mock_context.variables["_loop_active"] is False

    def test_default_loop_type_is_for(self, mock_context):
        node = _make_node("loop", config={"max_iterations": 3})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["loop_type"] == "for"

    def test_default_max_iterations_is_10(self, mock_context):
        node = _make_node("loop", config={"loop_type": "for"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["max_iterations"] == 10


# ============================================================
# BranchNode
# ============================================================

class TestBranchNode:
    """BranchNode: 条件分支评估."""

    def test_empty_var_returns_fail(self, mock_context):
        node = _make_node("branch", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "条件变量名称为空" in result.error_msg

    def test_eq_operator_true_returns_true_branch(self, mock_context):
        mock_context.variables["status"] = "ready"
        node = _make_node("branch", config={
            "condition_variable": "status",
            "condition_operator": "eq",
            "condition_value": "ready",
            "true_node_id": "next_a",
            "false_node_id": "next_b",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["condition_result"] is True
        assert result.data["branch_taken"] == "next_a"

    def test_eq_operator_false_returns_false_branch(self, mock_context):
        mock_context.variables["status"] = "loading"
        node = _make_node("branch", config={
            "condition_variable": "status",
            "condition_operator": "eq",
            "condition_value": "ready",
            "true_node_id": "next_a",
            "false_node_id": "next_b",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["condition_result"] is False
        assert result.data["branch_taken"] == "next_b"

    def test_gt_operator_returns_true_for_greater(self, mock_context):
        mock_context.variables["count"] = 15
        node = _make_node("branch", config={
            "condition_variable": "count",
            "condition_operator": "gt",
            "condition_value": 10,
            "true_node_id": "a", "false_node_id": "b",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["condition_result"] is True

    def test_contains_operator_returns_true_for_substring(self, mock_context):
        mock_context.variables["text"] = "hello world"
        node = _make_node("branch", config={
            "condition_variable": "text",
            "condition_operator": "contains",
            "condition_value": "world",
            "true_node_id": "a", "false_node_id": "b",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["condition_result"] is True

    def test_stores_result_in_context(self, mock_context):
        mock_context.variables["x"] = 1
        node = _make_node("branch", node_id="br1", config={
            "condition_variable": "x",
            "condition_operator": "eq",
            "condition_value": 1,
        })
        node.execute(mock_context)
        assert "br1_branch_result" in mock_context.variables


# ============================================================
# GotoNode
# ============================================================

class TestGotoNode:
    """GotoNode: 无条件跳转."""

    def test_no_target_and_no_label_returns_fail(self, mock_context):
        node = _make_node("goto", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "target_node_id" in result.error_msg or "label" in result.error_msg

    def test_target_node_id_succeeds(self, mock_context):
        node = _make_node("goto", config={"target_node_id": "node_x"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target_node_id"] == "node_x"
        # Context stores the target.
        assert mock_context.variables["test_node_goto_target"] == "node_x"

    def test_label_only_succeeds(self, mock_context):
        node = _make_node("goto", config={"label": "start_point"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["label"] == "start_point"
        # Context stores the label as target (label fallback).
        assert mock_context.variables["test_node_goto_target"] == "start_point"

    def test_both_target_and_label_prefers_target(self, mock_context):
        node = _make_node("goto", config={
            "target_node_id": "node_t", "label": "lbl",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert mock_context.variables["test_node_goto_target"] == "node_t"


# ============================================================
# JumpBackNode (Maa)
# ============================================================

class TestJumpBackNode:
    """JumpBackNode: 跳回上一个节点."""

    def test_explicit_target_succeeds(self, mock_context):
        node = _make_node("jump_back", config={"target_node_id": "prev_node"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target_node_id"] == "prev_node"
        assert mock_context.variables["_jump_back_target"] == "prev_node"
        assert mock_context.variables["_jump_back_source"] == "test_node"

    def test_no_target_no_history_returns_fail(self, mock_context):
        mock_context.execution_history = []
        node = _make_node("jump_back", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "no previous node" in result.error_msg.lower()

    def test_target_from_history_succeeds(self, mock_context):
        mock_context.execution_history = [
            {"node_id": "first"},
            {"node_id": "second"},
            {"node_id": "current"},
        ]
        node = _make_node("jump_back", config={"steps_back": 1})
        result = node.execute(mock_context)
        assert result.success is True
        # steps_back=1 means jump to the node before current (index len-1-1=1).
        assert result.data["target_node_id"] == "second"

    def test_default_steps_back_is_1(self, mock_context):
        mock_context.execution_history = [
            {"node_id": "a"}, {"node_id": "b"}, {"node_id": "c"},
        ]
        node = _make_node("jump_back", config={})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target_node_id"] == "b"


# ============================================================
# WaitFreezesNode (Maa)
# ============================================================

class TestWaitFreezesNode:
    """WaitFreezesNode: 等待屏幕稳定 (smoke 走早期失败路径)."""

    def test_no_device_returns_fail(self, mock_context):
        node = _make_node("wait_freezes", config={"timeout": 0.5})
        result = node.execute(mock_context)
        assert result.success is False
        assert "no device" in result.error_msg.lower()

    def test_module_unavailable_returns_fail(self, mock_context):
        # Patch the lazy import to fail.
        mock_context.device = MagicMock()
        node = _make_node("wait_freezes", config={"timeout": 0.5})
        with patch("builtins.__import__", side_effect=ImportError("no module")):
            result = node.execute(mock_context)
        assert result.success is False
        assert "WaitFreezes module unavailable" in result.error_msg or \
            "no device" in result.error_msg.lower()

    def test_stable_screen_returns_success(self, mock_context):
        # Patch WaitFreezes class to short-circuit (avoid real frame comparison).
        from core.exceptions import DeviceError  # noqa: F401
        mock_context.device = MagicMock()
        node = _make_node("wait_freezes", config={"timeout": 0.5})
        with patch("core.wait_freezes.WaitFreezes") as mock_wf:
            instance = mock_wf.return_value
            instance.wait.return_value = True
            result = node.execute(mock_context)
        assert result.success is True
        assert result.data["stable"] is True

    def test_unstable_screen_returns_fail(self, mock_context):
        mock_context.device = MagicMock()
        node = _make_node("wait_freezes", config={"timeout": 0.5})
        with patch("core.wait_freezes.WaitFreezes") as mock_wf:
            instance = mock_wf.return_value
            instance.wait.return_value = False
            result = node.execute(mock_context)
        assert result.success is False
        assert "timeout" in result.error_msg.lower()


# ============================================================
# NextNode (Maa)
# ============================================================

class TestNextNode:
    """NextNode: 跳到下一个节点."""

    def test_explicit_target_succeeds(self, mock_context):
        node = _make_node("next", config={"target_node_id": "next_x"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target_node_id"] == "next_x"
        assert mock_context.variables["_next_override"] == "next_x"

    def test_no_target_no_default_next_returns_fail(self, mock_context):
        node = _make_node("next", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "no target_node_id" in result.error_msg.lower()

    def test_falls_back_to_default_next_node_id(self, mock_context):
        node = _make_node("next", config={}, next_node_id="default_next")
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target_node_id"] == "default_next"


# ============================================================
# StopNode (Maa)
# ============================================================

class TestStopNode:
    """StopNode: 停止 pipeline 执行."""

    def test_basic_stop_succeeds(self, mock_context):
        node = _make_node("stop")
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["action"] == "stop"
        assert mock_context.variables["_stop_requested"] is True

    def test_custom_reason_stored(self, mock_context):
        node = _make_node("stop", config={"reason": "test done"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["reason"] == "test done"
        assert mock_context.variables["_stop_reason"] == "test done"

    def test_save_state_default_true(self, mock_context):
        node = _make_node("stop")
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["save_state"] is True
        assert mock_context.variables["_stop_save_state"] is True

    def test_save_state_false_propagated(self, mock_context):
        node = _make_node("stop", config={"save_state": False})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["save_state"] is False
        assert mock_context.variables["_stop_save_state"] is False


# ============================================================
# AnchorNode (Maa)
# ============================================================

class TestAnchorNode:
    """AnchorNode: 基于参考元素位置 + 偏移计算目标."""

    def test_missing_reference_returns_fail(self, mock_context):
        node = _make_node("anchor", config={
            "reference_variable": "missing_var",
            "offset_x": 10, "offset_y": 20,
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert "reference variable" in result.error_msg.lower()
        assert "not found" in result.error_msg.lower()

    def test_dict_center_reference_with_offset(self, mock_context):
        mock_context.variables["_last_match_pos"] = {"x": 100, "y": 200}
        node = _make_node("anchor", config={
            "offset_x": 50, "offset_y": -30,
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target"]["x"] == 150
        assert result.data["target"]["y"] == 170
        # Default output variable.
        assert "_anchor_pos" in mock_context.variables
        assert mock_context.variables["_anchor_pos"]["x"] == 150
        # Also updates _last_match_pos.
        assert mock_context.variables["_last_match_pos"]["x"] == 150

    def test_absolute_mode_ignores_reference(self, mock_context):
        mock_context.variables["_last_match_pos"] = {"x": 100, "y": 200}
        node = _make_node("anchor", config={
            "offset_x": 500, "offset_y": 600, "absolute": True,
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target"]["x"] == 500
        assert result.data["target"]["y"] == 600

    def test_top_left_reference_computes_center(self, mock_context):
        mock_context.variables["_last_match_pos"] = {
            "x": 100, "y": 100, "w": 40, "h": 60,
        }
        node = _make_node("anchor", config={
            "reference_type": "top_left",
            "offset_x": 0, "offset_y": 0,
        })
        result = node.execute(mock_context)
        assert result.success is True
        # center = top_left + half size = (100+20, 100+30) = (120, 130).
        assert result.data["target"]["x"] == 120
        assert result.data["target"]["y"] == 130

    def test_tuple_reference_supported(self, mock_context):
        mock_context.variables["_last_match_pos"] = (50, 75)
        node = _make_node("anchor", config={"offset_x": 0, "offset_y": 0})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["target"]["x"] == 50
        assert result.data["target"]["y"] == 75

    def test_custom_output_variable(self, mock_context):
        mock_context.variables["_last_match_pos"] = {"x": 0, "y": 0}
        node = _make_node("anchor", config={
            "offset_x": 10, "offset_y": 10,
            "output_variable": "click_target",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert "click_target" in mock_context.variables
        assert mock_context.variables["click_target"]["x"] == 10


# ============================================================
# SubPipelineNode
# ============================================================

class TestSubPipelineNode:
    """SubPipelineNode: 子 pipeline 执行."""

    def test_no_pipeline_json_returns_fail(self, mock_context):
        node = _make_node("sub_pipeline", config={"pipeline_id": "abc"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "pipeline_id" in result.error_msg or "注册表" in result.error_msg

    def test_max_depth_exceeded_returns_fail(self, mock_context):
        mock_context.variables["_sub_pipeline_depth"] = 5
        node = _make_node("sub_pipeline", config={
            "pipeline_json": {"name": "test"},
        })
        result = node.execute(mock_context)
        assert result.success is False
        assert "嵌套深度" in result.error_msg or "上限" in result.error_msg

    def test_basic_sub_pipeline_executes(self, mock_context):
        # Minimal valid pipeline JSON with a single notify node.
        pipeline_json = {
            "name": "test_sub",
            "nodes": [
                {"id": "n1", "node_type": "notify",
                 "config": {"message": "sub pipeline ran"}},
            ],
        }
        node = _make_node("sub_pipeline", config={
            "pipeline_json": pipeline_json,
            "parameters": {"key1": "value1"},
        })
        result = node.execute(mock_context)
        # Sub-pipeline execution may succeed or fail depending on engine init;
        # we just verify the orchestration shape (depth propagated).
        assert result.data is not None
        assert result.data["depth"] == 1
        assert result.data["parameters"] == {"key1": "value1"}


# ============================================================
# MonitorNode
# ============================================================

class TestMonitorNode:
    """MonitorNode: 弹窗/剧情跳过/异常上报."""

    def test_unknown_action_returns_fail(self, mock_context):
        node = _make_node("monitor", config={"action": "invalid_action"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "未知监控操作" in result.error_msg

    def test_skip_story_succeeds(self, mock_context):
        node = _make_node("monitor", config={
            "action": "skip_story", "skip_key": "space",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["action"] == "skip_story"
        assert result.data["skipped"] is True
        assert result.data["skip_key"] == "space"

    def test_report_error_succeeds(self, mock_context):
        node = _make_node("monitor", config={
            "action": "report_error", "report_url": "http://example.com/report",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["action"] == "report_error"
        assert result.data["reported"] is True
        assert result.data["report_url"] == "http://example.com/report"

    def test_screenshot_monitor_succeeds(self, mock_context):
        node = _make_node("monitor", config={"action": "screenshot_monitor"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["action"] == "screenshot_monitor"
        assert result.data["screenshot_taken"] is True

    def test_popup_no_monitor_manager_returns_fail(self, mock_context):
        # context.monitor_manager is None (MagicMock default returns a Mock,
        # so we explicitly set it to None).
        mock_context.monitor_manager = None
        node = _make_node("monitor", config={"action": "popup"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "MonitorManager" in result.error_msg or "monitor_manager" in result.error_msg.lower()

    def test_popup_manager_missing_popup_handler_returns_fail(self, mock_context):
        # monitor_manager present but lacks popup_handler attribute.
        mm = MagicMock()
        # Remove popup_handler to simulate missing attribute.
        del mm.popup_handler
        mock_context.monitor_manager = mm
        node = _make_node("monitor", config={"action": "popup"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "popup_handler" in result.error_msg

    def test_popup_with_real_handler_succeeds(self, mock_context):
        mm = MagicMock()
        mm.popup_handler.check_and_handle.return_value = True
        mock_context.monitor_manager = mm
        node = _make_node("monitor", config={"action": "popup"})
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["popup_handled"] is True
        assert result.data["popup_count"] == 1

    def test_stores_result_in_context(self, mock_context):
        node = _make_node("monitor", node_id="mon1",
                          config={"action": "skip_story"})
        node.execute(mock_context)
        assert "mon1_monitor_result" in mock_context.variables


# ============================================================
# DeviceControlNode
# ============================================================

class TestDeviceControlNode:
    """DeviceControlNode: 设备级操作 (Mock 骨架)."""

    def test_unknown_action_returns_fail(self, mock_context):
        node = _make_node("device_control", config={"action": "invalid"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "未知设备操作" in result.error_msg

    def test_empty_action_returns_fail(self, mock_context):
        node = _make_node("device_control", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "未知设备操作" in result.error_msg

    def test_switch_window_succeeds(self, mock_context):
        node = _make_node("device_control", config={
            "action": "switch_window", "window_title": "Game",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["action"] == "switch_window"
        assert result.data["window_title"] == "Game"
        assert result.data["result"] == "switched"

    def test_start_emulator_succeeds(self, mock_context):
        node = _make_node("device_control", config={
            "action": "start_emulator", "emulator_name": "ldplayer",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["action"] == "start_emulator"
        assert result.data["emulator_name"] == "ldplayer"
        assert result.data["result"] == "started"

    def test_screenshot_succeeds(self, mock_context):
        node = _make_node("device_control", config={
            "action": "screenshot", "save_path": "/tmp/shot.png",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["action"] == "screenshot"
        assert result.data["save_path"] == "/tmp/shot.png"
        assert result.data["result"] == "saved"

    def test_stop_emulator_succeeds(self, mock_context):
        node = _make_node("device_control", config={
            "action": "stop_emulator", "emulator_name": "ldplayer",
        })
        result = node.execute(mock_context)
        assert result.success is True
        assert result.data["action"] == "stop_emulator"
        assert result.data["result"] == "stopped"

    def test_stores_result_in_context(self, mock_context):
        node = _make_node("device_control", node_id="dc1",
                          config={"action": "screenshot"})
        node.execute(mock_context)
        assert "dc1_device_result" in mock_context.variables
