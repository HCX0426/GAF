"""Pipeline Engine 单元测试 — 覆盖 PipelineNode、Engine、Parser、Validator、Context"""

import base64
import json
import threading
import time
from unittest.mock import MagicMock, patch

import cv2

# 确保所有节点类型被注册到工厂表
import numpy as np
import pytest
from core.result import success_result
from engine.context import (
    PipelineContext,
    PipelineState,
    StepSnapshot,
    StepState,
)
from engine.node import PIPELINE_NODE_REGISTRY, PipelineNode
from engine.parser import PipelineEdge, PipelineGraph, PipelineParser
from engine.pipeline_engine import PipelineEngine, PipelineResult
from engine.validator import PipelineValidator, ValidationError

pytestmark = pytest.mark.integration

# ============================================================
# 辅助函数
# ============================================================

# Deterministic noise pattern used as a template image for template_match
# and feature_match tests. Encoded as base64 PNG so it can be passed via
# the "template" config key (the node treats strings without path
# separators or image extensions as base64 data).
_rng = np.random.RandomState(42)
_TEMPLATE_PATTERN = _rng.randint(0, 256, size=(100, 100, 3), dtype=np.uint8)

def _encode_bgr_to_b64(img_bgr: np.ndarray) -> str:
    """Encode a BGR numpy array as a base64 PNG string for template configs."""
    ok, buf = cv2.imencode('.png', img_bgr)
    if not ok:
        raise RuntimeError("cv2.imencode failed")
    return base64.b64encode(buf.tobytes()).decode('ascii')

_TEMPLATE_B64 = _encode_bgr_to_b64(_TEMPLATE_PATTERN)

def _make_patterned_screen() -> np.ndarray:
    """Build a 200x200 BGR screen for template/feature match tests.

    Red background satisfies color_detect's HSV red bounds; a 100x100 noise
    patch at top-left provides detectable features for template_match
    (cv2.matchTemplate) and feature_match (ORB/SIFT) to find.
    """
    screen = np.zeros((200, 200, 3), dtype=np.uint8)
    screen[:, :, 2] = 255  # BGR red background
    screen[0:100, 0:100] = _TEMPLATE_PATTERN
    return screen


def _make_pipeline_json(nodes=None, edges=None, entry=None):
    """构建标准 Pipeline JSON"""
    data = {"nodes": nodes or [], "edges": edges or []}
    if entry:
        data["entry_node"] = entry
    elif nodes:
        data["entry_node"] = nodes[0]["id"]
    return data


def _make_mock_device():
    """Build a MagicMock device whose click/swipe/key_press/text_input
    methods do not raise, so device-dependent nodes (click/swipe/
    key_press/text_input) succeed in unit tests without real hardware.

    capture_screen returns a solid red BGR image so color_detect (default
    HSV red bounds [0,50,50]-[10,255,255]) finds a matching contour.
    """
    device = MagicMock()
    device.device_id = "mock_device"
    # MagicMock auto-creates click/swipe/key_press/text_input/activate_window
    # returning MagicMock instances (no exception) by default.
    # capture_screen must return a real numpy array for OpenCV-based nodes
    # (color_detect/template_match/feature_match) that access screen.shape.
    red_screen = np.zeros((100, 100, 3), dtype=np.uint8)
    red_screen[:, :, 2] = 255  # BGR red channel
    device.capture_screen.return_value = red_screen
    return device


# ============================================================
# Test: PipelineNode 基础
# ============================================================

class TestPipelineNodeBase:
    """PipelineNode 基类测试"""

    def test_node_to_dict(self):
        """测试节点序列化为字典"""
        node = PipelineNode(id="n1", name="测试节点", node_type="click", config={"x": 10, "y": 20})
        d = node.to_dict()
        assert d["id"] == "n1"
        assert d["name"] == "测试节点"
        assert d["node_type"] == "click"
        assert d["config"] == {"x": 10, "y": 20}

    def test_node_from_dict(self):
        """测试从字典反序列化节点"""
        data = {"id": "n2", "name": "节点2", "node_type": "wait", "config": {"seconds": 3}}
        node = PipelineNode.from_dict(data)
        assert node.id == "n2"
        assert node.name == "节点2"
        assert node.node_type == "wait"
        assert node.config == {"seconds": 3}

    def test_node_to_from_dict_roundtrip(self):
        """测试序列化/反序列化往返一致性"""
        node = PipelineNode(
            id="n3", name="往返", node_type="click",
            config={"x": 50, "y": 60}, next_node_id="n4"
        )
        d = node.to_dict()
        restored = PipelineNode.from_dict(d)
        assert restored.id == node.id
        assert restored.name == node.name
        assert restored.node_type == node.node_type
        assert restored.config == node.config
        assert restored.next_node_id == node.next_node_id

    def test_node_factory_create_click(self):
        """测试工厂方法创建 click 节点"""
        data = {"id": "nc", "node_type": "click", "config": {"x": 100, "y": 200}}
        node = PipelineNode.create(data)
        assert node.node_type == "click"
        assert node.id == "nc"
        assert isinstance(node, PipelineNode)

    def test_node_factory_unknown_type(self):
        """测试工厂方法对未知类型抛出异常"""
        data = {"id": "nx", "node_type": "unknown_node_type"}
        with pytest.raises(ValueError, match="未知的节点类型"):
            PipelineNode.create(data)

    def test_node_factory_all_15_types_registered(self):
        """测试所有 15 种节点类型已注册"""
        expected_types = {
            "template_match", "ocr", "color_detect", "feature_match",
            "click", "swipe", "key_press", "text_input", "wait",
            "branch", "loop", "goto", "device_control", "monitor", "sub_pipeline",
        }
        assert expected_types.issubset(set(PIPELINE_NODE_REGISTRY.keys()))


# ============================================================
# Test: 15 种节点类型 execute
# ============================================================

class TestAllNodeTypes:
    """所有节点类型的 execute 测试"""

    def setup_method(self):
        self.context = PipelineContext()
        self.mock_device = _make_mock_device()

    def _exec(self, node_type, config=None):
        """辅助：创建节点并执行"""
        data = {"id": f"t_{node_type}", "node_type": node_type, "config": config or {}}
        node = PipelineNode.create(data)
        return node.execute(self.context)

    def test_template_match_node(self):
        """模板匹配节点成功执行"""
        self.context.device = self.mock_device
        self.mock_device.capture_screen.return_value = _make_patterned_screen()
        result = self._exec("template_match", {"threshold": 0.8, "template": _TEMPLATE_B64})
        assert result.success
        assert result.data["confidence"] >= 0.8

    def test_template_match_node_below_threshold(self):
        """模板匹配低于阈值失败"""
        self.context.device = self.mock_device
        result = self._exec("template_match", {"threshold": 0.99})
        assert not result.success

    def test_ocr_node(self):
        """OCR 节点执行"""
        # Force _fallback_mock path: empty registry + RapidOCR import fails
        # so the node returns mock_text='识别文本' without a real OCR engine.
        mock_registry = MagicMock()
        mock_registry.engine_names = []
        self.context.set_variable('_ocr_registry', mock_registry)
        with patch('recognition.ocr.rapid_engine.RapidOCREngine', side_effect=ImportError("test")):
            result = self._exec("ocr", {"expected_text": "识别文本"})
        assert result.success
        assert result.data["text"] == "识别文本"

    def test_ocr_node_mismatch(self):
        """OCR 文本不匹配失败"""
        # Same mock setup as test_ocr_node; mock_text='识别文本' won't match
        # expected_text='不匹配的文本'.
        mock_registry = MagicMock()
        mock_registry.engine_names = []
        self.context.set_variable('_ocr_registry', mock_registry)
        with patch('recognition.ocr.rapid_engine.RapidOCREngine', side_effect=ImportError("test")):
            result = self._exec("ocr", {"expected_text": "不匹配的文本"})
        assert not result.success

    def test_color_detect_node(self):
        """颜色检测节点"""
        self.context.device = self.mock_device
        result = self._exec("color_detect", {"min_area": 10})
        assert result.success
        assert result.data["matched"] is True

    def test_feature_match_node(self):
        """特征匹配节点"""
        self.context.device = self.mock_device
        self.mock_device.capture_screen.return_value = _make_patterned_screen()
        result = self._exec("feature_match", {"min_matches": 10, "template": _TEMPLATE_B64})
        assert result.success
        assert result.data["num_matches"] >= 10

    def test_click_node(self):
        """点击节点"""
        self.context.device = self.mock_device
        result = self._exec("click", {"x": 10, "y": 20})
        assert result.success
        assert result.data["x"] == 10
        assert result.data["y"] == 20

    def test_swipe_node(self):
        """滑动节点"""
        self.context.device = self.mock_device
        result = self._exec("swipe", {"x1": 0, "y1": 0, "x2": 100, "y2": 200})
        assert result.success
        assert result.data["from"] == {"x": 0, "y": 0}
        assert result.data["to"] == {"x": 100, "y": 200}

    def test_key_press_node(self):
        """按键节点"""
        self.context.device = self.mock_device
        result = self._exec("key_press", {"key": "enter"})
        assert result.success
        assert result.data["key"] == "enter"

    def test_key_press_empty(self):
        """按键名为空时失败"""
        result = self._exec("key_press", {})
        assert not result.success

    def test_text_input_node(self):
        """文字输入节点"""
        self.context.device = self.mock_device
        result = self._exec("text_input", {"text": "hello"})
        assert result.success
        assert result.data["text"] == "hello"

    def test_wait_node_fixed(self):
        """等待节点 - 固定时间"""
        result = self._exec("wait", {"mode": "fixed", "seconds": 1.0})
        assert result.success
        assert result.data["mode"] == "fixed"

    def test_wait_node_stable(self):
        """等待节点 - 画面稳定（无 device 时应失败，不再返回 mock 数据）"""
        result = self._exec("wait", {"mode": "stable", "max_wait": 5.0})
        # Real implementation requires a device for screen capture;
        # without one it must fail gracefully instead of returning mock data.
        assert not result.success
        assert "no device" in result.error_msg

    def test_wait_node_template(self):
        """等待节点 - 模板出现（无 device 时应失败，不再返回 mock 数据）"""
        result = self._exec("wait", {"mode": "template", "max_wait": 10.0})
        # Real implementation requires a device for screen capture;
        # without one it must fail gracefully instead of returning mock data.
        assert not result.success
        assert "no device" in result.error_msg

    def test_wait_node_disappear_no_device(self):
        """等待节点 - 模板消失（无 device 时应失败）"""
        result = self._exec("wait", {"mode": "disappear", "max_wait": 5.0})
        assert not result.success
        assert "no device" in result.error_msg

    def test_wait_node_disappear_missing_template(self):
        """等待节点 - 模板消失（缺 template 配置应失败）"""
        # Provide a mock device so we pass the device check, then fail on
        # the missing 'template' config.
        class _StubDevice:
            pass
        self.context.device = _StubDevice()
        result = self._exec("wait", {"mode": "disappear", "max_wait": 5.0})
        assert not result.success
        assert "template" in result.error_msg

    def test_wait_node_disappear_unknown_mode(self):
        """等待节点 - 未知模式应失败"""
        result = self._exec("wait", {"mode": "unknown_mode_xyz", "max_wait": 5.0})
        assert not result.success
        assert "未知等待模式" in result.error_msg

    def test_branch_node_true(self):
        """分支节点 - 条件为真"""
        self.context.set_variable("score", 100)
        result = self._exec("branch", {
            "condition_variable": "score",
            "condition_operator": "gt",
            "condition_value": 50,
            "true_node_id": "n_true",
            "false_node_id": "n_false",
        })
        assert result.success
        assert result.data["condition_result"] is True
        assert result.data["branch_taken"] == "n_true"

    def test_branch_node_false(self):
        """分支节点 - 条件为假"""
        self.context.set_variable("score", 30)
        result = self._exec("branch", {
            "condition_variable": "score",
            "condition_operator": "gt",
            "condition_value": 50,
            "true_node_id": "n_true",
            "false_node_id": "n_false",
        })
        assert result.success
        assert result.data["condition_result"] is False
        assert result.data["branch_taken"] == "n_false"

    def test_loop_node_for(self):
        """循环节点 - for 模式"""
        result = self._exec("loop", {"loop_type": "for", "max_iterations": 5, "body_nodes": ["n1", "n2"]})
        assert result.success
        assert result.data["loop_type"] == "for"
        assert result.data["max_iterations"] == 5

    def test_loop_node_while(self):
        """循环节点 - while 模式"""
        result = self._exec("loop", {"loop_type": "while", "condition_variable": "running"})
        assert result.success
        assert result.data["loop_type"] == "while"

    def test_goto_node(self):
        """跳转节点"""
        result = self._exec("goto", {"target_node_id": "n_target"})
        assert result.success
        assert result.data["target_node_id"] == "n_target"

    def test_device_control_node(self):
        """设备控制节点"""
        result = self._exec("device_control", {"action": "switch_window", "window_title": "Test"})
        assert result.success
        assert result.data["action"] == "switch_window"

    def test_device_control_unknown_action(self):
        """设备控制未知操作"""
        result = self._exec("device_control", {"action": "unknown_op"})
        assert not result.success

    def test_monitor_node_no_manager_fails(self):
        """监控节点：context.monitor_manager 缺失时返回 fail_result 暴露配置错误（不静默 Mock 回退）"""
        result = self._exec("monitor", {"action": "popup"})
        assert not result.success
        assert "MonitorManager not available" in result.error_msg

    def test_monitor_node_with_manager(self):
        """监控节点：context.monitor_manager 存在时走真实 PopupHandler 路径"""
        from unittest.mock import MagicMock

        mock_manager = MagicMock()
        mock_manager.popup_handler.check_and_handle.return_value = True
        self.context.monitor_manager = mock_manager

        result = self._exec("monitor", {"action": "popup"})
        assert result.success
        assert result.data["popup_handled"] is True
        assert result.data["source"] == "popup_handler"
        mock_manager.popup_handler.check_and_handle.assert_called_once()

    def test_monitor_node_handler_exception_fails(self):
        """监控节点：popup_handler 抛异常时返回 fail_result 暴露问题"""
        from unittest.mock import MagicMock

        mock_manager = MagicMock()
        mock_manager.popup_handler.check_and_handle.side_effect = RuntimeError("handler boom")
        self.context.monitor_manager = mock_manager

        result = self._exec("monitor", {"action": "popup"})
        assert not result.success
        assert "handler boom" in result.error_msg

    def test_sub_pipeline_node(self):
        """子 Pipeline 节点"""
        sub_json = _make_pipeline_json(
            nodes=[{"id": "sub1", "node_type": "wait", "config": {"mode": "fixed", "seconds": 0.01}}],
        )
        result = self._exec("sub_pipeline", {
            "pipeline_id": "sub_001",
            "pipeline_json": sub_json,
            "parameters": {"k": "v"},
        })
        assert result.success
        assert result.data["pipeline_id"] == "sub_001"
        assert result.data["sub_steps_executed"] == 1


# ============================================================
# Test: PipelineContext 序列化
# ============================================================

class TestPipelineContext:
    """PipelineContext 测试"""

    def test_context_serialize_restore(self):
        """测试上下文序列化/恢复往返"""
        ctx = PipelineContext(
            current_step_index=3,
            variables={"key1": "val1", "key2": 42},
            pipeline_snapshot={"entry_node": "start"},
        )
        ctx.record_step("n1", "click", StepState.COMPLETED, {"x": 10})
        ctx.record_step("n2", "wait", StepState.COMPLETED, {"s": 1.0})

        data = ctx.serialize()
        restored = PipelineContext.restore(data)

        assert restored.current_step_index == 3
        assert restored.variables == {"key1": "val1", "key2": 42}
        assert restored.pipeline_snapshot == {"entry_node": "start"}
        assert len(restored.step_states) == 2
        assert restored.step_states[0].node_id == "n1"
        assert restored.step_states[1].node_id == "n2"

    def test_context_variable_operations(self):
        """测试上下文变量读写"""
        ctx = PipelineContext()
        ctx.set_variable("name", "test")
        assert ctx.get_variable("name") == "test"
        assert ctx.get_variable("missing", "default") == "default"

    def test_context_get_completed_step_ids(self):
        """测试获取已完成步骤 ID"""
        ctx = PipelineContext()
        ctx.record_step("a", "click", StepState.COMPLETED)
        ctx.record_step("b", "wait", StepState.FAILED)
        ctx.record_step("c", "ocr", StepState.COMPLETED)
        assert ctx.get_completed_step_ids() == ["a", "c"]

    def test_context_reset(self):
        """测试上下文重置"""
        ctx = PipelineContext(current_step_index=5, variables={"k": "v"})
        ctx.record_step("n1", "click", StepState.COMPLETED)
        ctx.reset()
        assert ctx.current_step_index == 0
        assert ctx.variables == {}
        assert ctx.step_states == []

    def test_step_snapshot_serialize_restore(self):
        """测试 StepSnapshot 序列化/恢复"""
        snap = StepSnapshot(
            step_index=0,
            node_id="n1",
            node_type="click",
            state=StepState.COMPLETED,
            result_data={"x": 10},
            error_msg="",
            elapsed_time=0.5,
        )
        d = snap.to_dict()
        restored = StepSnapshot.from_dict(d)
        assert restored.step_index == 0
        assert restored.node_id == "n1"
        assert restored.state == StepState.COMPLETED
        assert restored.result_data == {"x": 10}


# ============================================================
# Test: PipelineParser
# ============================================================

class TestPipelineParser:
    """PipelineParser 测试"""

    def test_parse_standard_json(self):
        """解析标准格式 JSON"""
        json_str = json.dumps({
            "nodes": [
                {"id": "n1", "node_type": "click", "config": {"x": 10, "y": 20}},
                {"id": "n2", "node_type": "wait", "config": {"seconds": 1}},
            ],
            "edges": [
                {"from": "n1", "to": "n2"},
            ],
            "entry_node": "n1",
        })
        graph = PipelineParser.parse(json_str)
        assert graph.entry_node == "n1"
        assert len(graph.nodes) == 2
        assert graph.get_node("n1").node_type == "click"
        assert graph.get_node("n2").node_type == "wait"
        assert graph.get_next_node_id("n1") == "n2"

    def test_parse_simplified_format(self):
        """解析简化格式（type 而非 node_type）"""
        json_str = json.dumps({
            "entry": "start",
            "steps": [
                {"id": "start", "type": "click", "config": {"x": 5, "y": 5}},
                {"id": "end", "type": "wait", "config": {"seconds": 1}},
            ],
            "edges": [{"from": "start", "to": "end"}],
        })
        graph = PipelineParser.parse(json_str)
        assert graph.entry_node == "start"
        assert graph.get_node("start").node_type == "click"

    def test_parse_auto_entry_inference(self):
        """测试自动推断入口节点"""
        json_str = json.dumps({
            "nodes": [
                {"id": "first", "node_type": "click", "config": {}},
                {"id": "second", "node_type": "wait", "config": {}},
            ],
        })
        graph = PipelineParser.parse(json_str)
        assert graph.entry_node == "first"

    def test_parse_unknown_node_type_detected(self):
        """测试未知节点类型触发验证"""
        json_str = json.dumps({
            "nodes": [
                {"id": "n1", "node_type": "click", "config": {}},
            ],
        })
        graph = PipelineParser.parse(json_str)
        # click 已知，应成功
        assert graph.get_node("n1").node_type == "click"

    def test_pipeline_graph_to_dict(self):
        """测试 PipelineGraph 序列化"""
        graph = PipelineParser.parse(json.dumps({
            "nodes": [
                {"id": "a", "node_type": "click", "config": {"x": 1}},
            ],
            "entry_node": "a",
        }))
        d = graph.to_dict()
        assert len(d["nodes"]) == 1
        assert d["entry_node"] == "a"


# ============================================================
# Test: PipelineValidator
# ============================================================

class TestPipelineValidator:
    """PipelineValidator 测试"""

    def test_valid_graph(self):
        """测试有效图通过校验"""
        json_str = json.dumps({
            "nodes": [
                {"id": "n1", "node_type": "click", "config": {"x": 1}},
                {"id": "n2", "node_type": "wait", "config": {"seconds": 1}},
            ],
            "edges": [{"from": "n1", "to": "n2"}],
            "entry_node": "n1",
        })
        graph = PipelineParser.parse(json_str)
        errors = PipelineValidator.validate(graph)
        assert len(errors) == 0

    def test_missing_entry(self):
        """测试缺少入口节点"""
        graph = PipelineGraph(
            nodes={
                "n1": PipelineNode(id="n1", node_type="click"),
            },
            entry_node="",
        )
        errors = PipelineValidator.validate(graph)
        assert any(e.error_type == "missing_entry" for e in errors)

    def test_invalid_entry(self):
        """测试入口节点不存在"""
        graph = PipelineGraph(
            nodes={
                "n1": PipelineNode(id="n1", node_type="click"),
            },
            entry_node="n_nonexistent",
        )
        errors = PipelineValidator.validate(graph)
        assert any(e.error_type == "invalid_entry" for e in errors)

    def test_orphan_node(self):
        """测试孤立节点检测"""
        json_str = json.dumps({
            "nodes": [
                {"id": "n1", "node_type": "click", "config": {}},
                {"id": "n2", "node_type": "wait", "config": {}},
            ],
            "edges": [{"from": "n1", "to": "n2"}],
            "entry_node": "n1",
        })
        # n2 有入边，n1 有出边，所以没有孤立节点
        graph = PipelineParser.parse(json_str)
        errors = PipelineValidator.validate(graph)
        assert not any(e.error_type == "orphan_node" for e in errors)

    def test_circular_ref_detected(self):
        """测试循环引用检测"""
        json_str = json.dumps({
            "nodes": [
                {"id": "n1", "node_type": "click", "config": {}},
                {"id": "n2", "node_type": "wait", "config": {}},
                {"id": "n3", "node_type": "click", "config": {}},
            ],
            "edges": [
                {"from": "n1", "to": "n2"},
                {"from": "n2", "to": "n3"},
                {"from": "n3", "to": "n1"},
            ],
            "entry_node": "n1",
        })
        graph = PipelineParser.parse(json_str)
        errors = PipelineValidator.validate(graph)
        assert any(e.error_type == "circular_ref" for e in errors)

    def test_validator_is_valid(self):
        """测试 is_valid 快捷方法"""
        json_str = json.dumps({
            "nodes": [
                {"id": "n1", "node_type": "click", "config": {}},
            ],
            "entry_node": "n1",
        })
        graph = PipelineParser.parse(json_str)
        assert PipelineValidator.is_valid(graph) is True


# ============================================================
# Test: PipelineEngine
# ============================================================

class TestPipelineEngineBasic:
    """PipelineEngine 基础测试"""

    def setup_method(self):
        self.mock_device = _make_mock_device()

    def test_engine_load_and_execute_simple(self):
        """测试简单两步骤 Pipeline 执行"""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {"id": "step1", "node_type": "click", "config": {"x": 10, "y": 20}},
                {"id": "step2", "node_type": "wait", "config": {"seconds": 0.1}},
            ],
            edges=[{"from": "step1", "to": "step2"}],
        ), device=self.mock_device)
        result = engine.execute()
        assert result.success
        assert result.state == PipelineState.COMPLETED
        assert len(result.step_results) == 2

    def test_engine_screenshot_template_click_e2e(self):
        """E2E 测试：截图→模板匹配→点击（全 Mock）"""
        self.mock_device.capture_screen.return_value = _make_patterned_screen()
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {"id": "screenshot", "node_type": "device_control", "config": {"action": "screenshot"}},
                {"id": "match", "node_type": "template_match", "config": {"threshold": 0.8, "template": _TEMPLATE_B64}},
                {"id": "click_btn", "node_type": "click", "config": {"x": 100, "y": 200}},
            ],
            edges=[
                {"from": "screenshot", "to": "match"},
                {"from": "match", "to": "click_btn"},
            ],
        ), device=self.mock_device)
        result = engine.execute()
        assert result.success
        assert len(result.step_results) == 3
        # 验证中间结果被存储到 context
        ctx = engine.context
        assert ctx.get_variable("match_match_result") is not None

    def test_engine_pause_resume(self):
        """测试 pause/resume 流程"""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {"id": "s1", "node_type": "click", "config": {"x": 1, "y": 1}},
                {"id": "s2", "node_type": "wait", "config": {"mode": "fixed", "seconds": 2.0}},
                {"id": "s3", "node_type": "click", "config": {"x": 2, "y": 2}},
            ],
            edges=[
                {"from": "s1", "to": "s2"},
                {"from": "s2", "to": "s3"},
            ],
        ), device=self.mock_device)

        results = []
        pause_applied = []

        def runner():
            results.append(engine.execute())

        t = threading.Thread(target=runner)
        t.start()

        # 等待第一个步骤完成，然后暂停
        time.sleep(0.2)
        engine.pause()
        pause_applied.append(True)
        assert engine.get_current_state() == PipelineState.PAUSED

        # 恢复执行
        time.sleep(0.2)
        engine.resume()
        t.join(timeout=10)

        assert len(results) == 1
        assert results[0].success

    def test_engine_cancel(self):
        """测试 cancel 流程"""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {"id": "s1", "node_type": "click", "config": {"x": 1, "y": 1}},
                {"id": "s2", "node_type": "wait", "config": {"mode": "fixed", "seconds": 5.0}},
            ],
            edges=[{"from": "s1", "to": "s2"}],
        ), device=self.mock_device)

        results = []

        def runner():
            results.append(engine.execute())

        t = threading.Thread(target=runner)
        t.start()
        time.sleep(0.2)
        engine.cancel()
        t.join(timeout=10)

        assert len(results) == 1
        assert results[0].state == PipelineState.CANCELLED

    def test_engine_skip_step(self):
        """测试 skip_step"""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {"id": "s1", "node_type": "click", "config": {"x": 1, "y": 1}},
                {"id": "s2", "node_type": "wait", "config": {"seconds": 0.1}},
            ],
            edges=[{"from": "s1", "to": "s2"}],
        ), device=self.mock_device)
        # skip_step 在运行时调用才有效，这里先测试接口不报错
        engine.execute()
        engine.skip_step(0)  # 执行完成后跳过已执行的步骤
        assert engine.context.step_states[0].state == StepState.SKIPPED

    def test_engine_get_current_state(self):
        """测试状态获取"""
        engine = PipelineEngine()
        assert engine.get_current_state() == PipelineState.PENDING
        engine.load(_make_pipeline_json(
            nodes=[{"id": "s1", "node_type": "click", "config": {}}],
        ), device=self.mock_device)
        engine.execute()
        assert engine.get_current_state() == PipelineState.COMPLETED

    def test_engine_execute_without_load(self):
        """测试未加载时执行抛出异常"""
        engine = PipelineEngine()
        with pytest.raises(RuntimeError, match="未加载"):
            engine.execute()

    def test_engine_serialize_restore_context(self):
        """测试引擎上下文序列化/恢复"""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {"id": "s1", "node_type": "click", "config": {"x": 1}},
                {"id": "s2", "node_type": "wait", "config": {"seconds": 0.1}},
            ],
            edges=[{"from": "s1", "to": "s2"}],
        ), device=self.mock_device)
        engine.execute()

        ctx_data = engine.get_execution_context()
        assert ctx_data is not None
        assert "current_step_index" in ctx_data
        assert "step_states" in ctx_data

        # 恢复到新引擎
        engine2 = PipelineEngine()
        engine2.load(_make_pipeline_json(
            nodes=[
                {"id": "s1", "node_type": "click", "config": {"x": 1}},
                {"id": "s2", "node_type": "wait", "config": {"seconds": 0.1}},
            ],
            edges=[{"from": "s1", "to": "s2"}],
        ))
        engine2.restore_context(ctx_data)
        assert engine2.context.current_step_index > 0

    def test_engine_branch_flow(self):
        """测试带分支的 Pipeline 执行"""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {"id": "s1", "node_type": "click", "config": {"x": 1, "y": 1}},
                {"id": "branch1", "node_type": "branch", "config": {
                    "condition_variable": "score",
                    "condition_operator": "gt",
                    "condition_value": 50,
                    "true_node_id": "s_true",
                    "false_node_id": "s_false",
                }},
                {"id": "s_true", "node_type": "click", "config": {"x": 10, "y": 10}},
                {"id": "s_false", "node_type": "wait", "config": {"mode": "fixed", "seconds": 0.1}},
            ],
            edges=[
                {"from": "s1", "to": "branch1"},
                {"from": "s_true", "to": ""},
                {"from": "s_false", "to": ""},
            ],
            entry="s1",
        ), device=self.mock_device)
        # 设置 score > 50，应走 true 分支
        engine._context = PipelineContext(device=self.mock_device)
        engine._context.set_variable("score", 100)

        result = engine.execute()
        assert result.success
        # 应该执行了 s1 + branch1 + s_true (共3步)
        assert len(result.step_results) >= 2

    def test_engine_step_failure_stops(self):
        """测试节点失败导致 Pipeline 停止"""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {"id": "s1", "node_type": "key_press", "config": {}},  # 缺少 key 会失败
                {"id": "s2", "node_type": "click", "config": {"x": 1, "y": 1}},
            ],
            edges=[{"from": "s1", "to": "s2"}],
        ), device=self.mock_device)
        result = engine.execute()
        assert not result.success
        assert result.state == PipelineState.FAILED

    def test_max_iterations_reached(self):
        """测试超过最大迭代次数"""
        engine = PipelineEngine()
        engine.set_max_iterations(1)
        engine.load(_make_pipeline_json(
            nodes=[
                {"id": "s1", "node_type": "click", "config": {"x": 1, "y": 1}},
                {"id": "s2", "node_type": "click", "config": {"x": 2, "y": 2}},
            ],
            edges=[{"from": "s1", "to": "s2"}],
        ), device=self.mock_device)
        result = engine.execute()
        assert not result.success
        assert "最大迭代次数" in result.error_msg


# ============================================================
# Test: PipelineResult
# ============================================================

class TestPipelineResult:
    """PipelineResult 测试"""

    def test_result_bool(self):
        """测试布尔转换"""
        r = PipelineResult(success=True, state=PipelineState.COMPLETED)
        assert bool(r) is True
        r2 = PipelineResult(success=False, state=PipelineState.FAILED)
        assert bool(r2) is False

    def test_result_fields(self):
        """测试结果字段"""
        r = PipelineResult(
            success=False,
            state=PipelineState.FAILED,
            error_msg="something wrong",
            elapsed_time=1.5,
            step_results=[success_result()],
        )
        assert r.state == PipelineState.FAILED
        assert r.error_msg == "something wrong"
        assert r.elapsed_time == 1.5
        assert len(r.step_results) == 1


# ============================================================
# Test: PipelineEdge
# ============================================================

class TestPipelineEdge:
    """PipelineEdge 测试"""

    def test_edge_to_from_dict(self):
        """测试边的序列化/反序列化"""
        edge = PipelineEdge(from_node="a", to_node="b", label="true", condition="x > 0")
        d = edge.to_dict()
        assert d["from"] == "a"
        assert d["to"] == "b"
        assert d["label"] == "true"
        assert d["condition"] == "x > 0"

        restored = PipelineEdge.from_dict(d)
        assert restored.from_node == "a"
        assert restored.to_node == "b"
        assert restored.label == "true"

    def test_edge_from_dict_minimal(self):
        """测试最小字段反序列化"""
        edge = PipelineEdge.from_dict({"from": "a", "to": "b"})
        assert edge.from_node == "a"
        assert edge.to_node == "b"
        assert edge.label == ""
        assert edge.condition is None


# ============================================================
# Test: PipelineGraph 边界情况
# ============================================================

class TestPipelineGraphEdgeCases:
    """PipelineGraph 边界情况测试"""

    def test_empty_graph(self):
        """测试空图"""
        graph = PipelineGraph()
        assert graph.get_node("x") is None
        assert graph.get_next_node_id("x") is None
        assert graph.get_all_node_ids() == []

    def test_graph_from_nodes_with_next_node_id(self):
        """测试从节点 next_node_id 推断边"""
        data = {
            "nodes": [
                {"id": "a", "node_type": "click", "config": {}, "next_node_id": "b"},
                {"id": "b", "node_type": "wait", "config": {}},
            ],
            "entry_node": "a",
        }
        graph = PipelineGraph.from_dict(data)
        assert graph.get_next_node_id("a") == "b"

    def test_validation_error_str(self):
        """测试 ValidationError 字符串表示"""
        err = ValidationError(
            error_type="missing_entry",
            message="缺少入口",
            node_id="n1",
        )
        s = str(err)
        assert "missing_entry" in s
        assert "n1" in s
        assert "缺少入口" in s


# ============================================================
# Test: 枚举类型
# ============================================================

class TestEnums:
    """枚举类型测试"""

    def test_pipeline_state_values(self):
        """测试 PipelineState 枚举值"""
        assert PipelineState.PENDING.value == "pending"
        assert PipelineState.RUNNING.value == "running"
        assert PipelineState.PAUSED.value == "paused"
        assert PipelineState.COMPLETED.value == "completed"
        assert PipelineState.FAILED.value == "failed"
        assert PipelineState.CANCELLED.value == "cancelled"

    def test_step_state_values(self):
        """测试 StepState 枚举值"""
        assert StepState.PENDING.value == "pending"
        assert StepState.COMPLETED.value == "completed"
        assert StepState.FAILED.value == "failed"
        assert StepState.SKIPPED.value == "skipped"


class TestStepTimeout:
    """Step-level timeout tests (spec 阶段 2.2)."""

    def setup_method(self):
        self.mock_device = _make_mock_device()

    def test_step_timeout_not_triggered_when_fast(self):
        """A fast node with a generous timeout should complete normally."""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {
                    "id": "fast",
                    "node_type": "wait",
                    "config": {"mode": "fixed", "seconds": 0.05, "timeout": 5.0},
                },
            ],
        ), device=self.mock_device)
        result = engine.execute()
        assert result.success
        assert result.state == PipelineState.COMPLETED
        assert len(result.step_results) == 1
        assert result.step_results[0].success

    def test_step_timeout_fires_when_node_hangs(self):
        """A node that sleeps longer than `timeout` should be timed out."""
        engine = PipelineEngine()
        # wait(fixed, seconds=10) would block for 10s; step timeout=0.5s
        # should fire and produce a failure result.
        engine.load(_make_pipeline_json(
            nodes=[
                {
                    "id": "slow",
                    "node_type": "wait",
                    "config": {"mode": "fixed", "seconds": 10.0, "timeout": 0.5},
                },
            ],
        ), device=self.mock_device)
        start = time.monotonic()
        result = engine.execute()
        elapsed = time.monotonic() - start

        # Should fail due to timeout, not succeed after 10s
        assert not result.success
        assert result.state == PipelineState.FAILED
        assert "超时" in result.error_msg or "timeout" in result.error_msg.lower()
        # Should return quickly (well under the 10s the node wanted to sleep)
        assert elapsed < 5.0, f"engine.execute took {elapsed:.1f}s, expected < 5s"

    def test_step_timeout_default_when_not_configured(self):
        """Nodes without `timeout` config use MAX_STEP_TIMEOUT (300s)."""
        from engine.pipeline_engine import MAX_STEP_TIMEOUT
        assert MAX_STEP_TIMEOUT == 300.0

    def test_step_timeout_negative_falls_back_to_max(self):
        """A negative timeout should be rejected by schema validation (minimum: 0)."""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {
                    "id": "fast",
                    "node_type": "wait",
                    "config": {"mode": "fixed", "seconds": 0.05, "timeout": -1},
                },
            ],
        ), device=self.mock_device)
        result = engine.execute()
        # Schema validation catches negative timeout before execution
        assert not result.success
        assert "param_invalid" in result.error_msg

    def test_step_timeout_continue_on_error(self):
        """A timed-out node with continue_on_error should not stop the pipeline."""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {
                    "id": "slow",
                    "node_type": "wait",
                    "config": {
                        "mode": "fixed", "seconds": 10.0,
                        "timeout": 0.3, "continue_on_error": True,
                    },
                },
                {
                    "id": "next",
                    "node_type": "wait",
                    "config": {"mode": "fixed", "seconds": 0.05},
                },
            ],
            edges=[{"from": "slow", "to": "next"}],
        ), device=self.mock_device)
        result = engine.execute()
        # Pipeline continues past the timed-out node
        assert result.success
        assert len(result.step_results) == 2
        assert not result.step_results[0].success  # slow node timed out
        assert result.step_results[1].success  # next node ran fine


# ============================================================
# Test: AutoResult 节点元数据自动填充 (spec 阶段 3.4.2 — 任务 1.2)
# ============================================================

class TestAutoResultNodeMetadataFilling:
    """engine 应在 _execute_node_step 返回前自动填充 node_id/node_type。

    场景：节点自己返回的 AutoResult 不带 node_id/node_type（向后兼容旧节点），
    engine 拿到 result 后应补全这两个字段，便于后续 JSONL 诊断与失败定位。
    """

    def setup_method(self):
        self.mock_device = _make_mock_device()

    def test_engine_fills_node_id_and_node_type_on_success(self):
        """成功节点的 result 应被 engine 自动填充 node_id/node_type。"""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {
                    "id": "step_1",
                    "node_type": "wait",
                    "config": {"mode": "fixed", "seconds": 0.01},
                },
            ],
        ), device=self.mock_device)
        result = engine.execute()
        assert result.success
        assert len(result.step_results) == 1
        step_result = result.step_results[0]
        assert step_result.node_id == "step_1"
        assert step_result.node_type == "wait"

    def test_engine_fills_node_id_and_node_type_on_failure(self):
        """失败节点的 result 也应被填充 node_id/node_type 用于诊断。"""
        engine = PipelineEngine()
        # wait(mode=template, template="") 通过 schema 校验，但执行时立即 fail
        engine.load(_make_pipeline_json(
            nodes=[
                {
                    "id": "bad_step",
                    "node_type": "wait",
                    "config": {"mode": "template", "template": "", "timeout": 0.1},
                },
            ],
        ), device=self.mock_device)
        result = engine.execute()
        # 失败的 pipeline 整体 success=False
        assert not result.success
        assert len(result.step_results) == 1
        step_result = result.step_results[0]
        assert step_result.node_id == "bad_step"
        assert step_result.node_type == "wait"

    def test_engine_does_not_overwrite_node_set_node_id(self):
        """如果节点本身已填充 node_id（如内部子步骤），engine 不应覆盖。"""

        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {
                    "id": "outer_step",
                    "node_type": "wait",
                    "config": {"mode": "fixed", "seconds": 0.01},
                },
            ],
        ), device=self.mock_device)

        # 用 monkey patch 覆盖 wait 节点的 execute，让它返回带 node_id 的 result
        from engine.nodes.wait import WaitNode

        original_execute = WaitNode.execute

        def patched_execute(self, context):
            result = original_execute(self, context)
            # 模拟节点主动设置了 node_id（如子步骤标识）
            result.node_id = "inner_sub_step"
            return result

        WaitNode.execute = patched_execute
        try:
            result = engine.execute()
        finally:
            WaitNode.execute = original_execute

        assert result.success
        # engine 不应覆盖节点主动设置的 node_id
        assert result.step_results[0].node_id == "inner_sub_step"
        # node_type 仍由 engine 填充（节点未主动设置）
        assert result.step_results[0].node_type == "wait"


# ============================================================
# Test: JSONL 跨步骤关联字段 + variables_snapshot (任务 1.4)
# ============================================================

class _FakeStructuredLogger:
    """记录所有 log_node_event 调用，便于断言 engine 传入了哪些字段。"""

    def __init__(self):
        self.events: list[dict] = []
        self.file_path = "/fake/structured.jsonl"
        self.execution_id = "exec-fake"

    def log_node_event(self, **kwargs):
        self.events.append(dict(kwargs))

    def close(self):
        pass


class TestStructuredLogCrossStepFields:
    """engine 应在 log_node_event 中传入 variables_snapshot 与跨步骤关联字段。

    覆盖 spec 阶段 3.2 (previous_node_id/previous_node_type/inter_node_gap_ms)
    和 3.3 (variables_snapshot 实际传值)。
    """

    def setup_method(self):
        self.mock_device = _make_mock_device()

    def _make_engine_with_fake_logger(self, nodes, edges=None):
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(nodes=nodes, edges=edges or []),
                    device=self.mock_device)
        fake = _FakeStructuredLogger()
        # execute() 会用 get_structured_logger 重新覆盖 _structured_logger，
        # 所以必须 patch 模块级函数才能让 fake 生效。
        import engine.pipeline_engine as engine_mod
        original_get_logger = engine_mod.get_structured_logger
        engine_mod.get_structured_logger = lambda *args, **kwargs: fake
        self._original_get_logger = original_get_logger
        self._engine_mod = engine_mod
        return engine, fake

    def teardown_method(self):
        # 恢复被 patch 的函数
        if hasattr(self, "_original_get_logger"):
            self._engine_mod.get_structured_logger = self._original_get_logger

    def test_log_node_event_receives_variables_snapshot(self):
        """成功节点的 JSONL 事件应包含 variables_snapshot（白名单过滤后）。"""
        engine, fake = self._make_engine_with_fake_logger([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {"mode": "fixed", "seconds": 0.01},
            },
        ])
        # 用 monkey patch 让 wait 节点在 execute 时设置变量
        # （engine.execute() 会 context.reset() 清空预设变量，所以必须
        # 在节点内部设置才能进入 snapshot）
        from engine.nodes.wait import WaitNode

        original_execute = WaitNode.execute

        def patched_execute(self, context):
            context.set_variable("task_name", "daily_login")
            context.set_variable("retry_count", 3)
            return original_execute(self, context)

        WaitNode.execute = patched_execute
        try:
            engine.execute()
        finally:
            WaitNode.execute = original_execute

        # Task 3.3 引入 node.execute.start 事件, 每个节点产生 start+complete
        # 两个事件. 这里只关心 complete 事件 (含 variables_snapshot).
        complete_events = [e for e in fake.events if e.get("event") == "node.execute.complete"]
        assert len(complete_events) == 1
        snapshot = complete_events[0].get("variables_snapshot")
        assert snapshot is not None
        assert snapshot["task_name"] == "daily_login"
        assert snapshot["retry_count"] == 3

    def test_variables_snapshot_skips_underscore_prefix_keys(self):
        """下划线前缀的内部协议变量不应进入 snapshot。"""
        engine, fake = self._make_engine_with_fake_logger([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {"mode": "fixed", "seconds": 0.01},
            },
        ])
        from engine.nodes.wait import WaitNode

        original_execute = WaitNode.execute

        def patched_execute(self, context):
            context.set_variable("_internal_protocol", "secret")
            context.set_variable("public_var", "ok")
            return original_execute(self, context)

        WaitNode.execute = patched_execute
        try:
            engine.execute()
        finally:
            WaitNode.execute = original_execute

        # Task 3.3: 过滤 complete 事件 (start 事件不含 variables_snapshot)
        complete_events = [e for e in fake.events if e.get("event") == "node.execute.complete"]
        assert len(complete_events) == 1
        snapshot = complete_events[0]["variables_snapshot"]
        assert "public_var" in snapshot
        assert "_internal_protocol" not in snapshot

    def test_variables_snapshot_omitted_when_empty(self):
        """没有变量时 variables_snapshot 应为 None（不写入 JSONL）。"""
        engine, fake = self._make_engine_with_fake_logger([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {"mode": "fixed", "seconds": 0.01},
            },
        ])
        engine.execute()
        # variables_snapshot=None 时 log_node_event 不会写入该字段
        # Task 3.3: 过滤 complete 事件 (start 事件不含 variables_snapshot)
        complete_events = [e for e in fake.events if e.get("event") == "node.execute.complete"]
        assert len(complete_events) == 1
        assert complete_events[0].get("variables_snapshot") is None

    def test_variables_snapshot_skips_ndarray(self):
        """spec §3.3: np.ndarray 大对象不应进入 snapshot (偏差 2 修复验证).

        spec 要求 ``isinstance(value, (bytes, np.ndarray))`` 跳过, 之前实
        现误写为 ``(bytes, bytearray)`` 漏掉了 np.ndarray. ndarray 会被
        ``json.dumps(default=str)`` 转成巨大字符串污染 snapshot.
        """
        import numpy as np

        engine, fake = self._make_engine_with_fake_logger([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {"mode": "fixed", "seconds": 0.01},
            },
        ])
        from engine.nodes.wait import WaitNode

        original_execute = WaitNode.execute

        def patched_execute(self, context):
            # 模拟节点把截图 ndarray 塞进 variables (常见场景: prev_match_screenshot)
            context.set_variable("public_str", "ok")
            context.set_variable("frame_buffer", np.zeros((100, 100, 3), dtype=np.uint8))
            return original_execute(self, context)

        WaitNode.execute = patched_execute
        try:
            engine.execute()
        finally:
            WaitNode.execute = original_execute

        # Task 3.3: 过滤 complete 事件 (start 事件不含 variables_snapshot)
        complete_events = [e for e in fake.events if e.get("event") == "node.execute.complete"]
        assert len(complete_events) == 1
        snapshot = complete_events[0]["variables_snapshot"]
        assert snapshot is not None
        # 公共字符串变量应保留
        assert snapshot["public_str"] == "ok"
        # np.ndarray 应被跳过, 不进 snapshot
        assert "frame_buffer" not in snapshot, (
            f"np.ndarray 应被跳过, 但出现在 snapshot 中: {snapshot.keys()}"
        )

    def test_log_node_event_receives_previous_node_fields_for_second_step(self):
        """第二步开始的 JSONL 事件应包含 previous_node_id/previous_node_type/inter_node_gap_ms。"""
        engine, fake = self._make_engine_with_fake_logger([
            {
                "id": "step_a",
                "node_type": "wait",
                "config": {"mode": "fixed", "seconds": 0.01},
            },
            {
                "id": "step_b",
                "node_type": "wait",
                "config": {"mode": "fixed", "seconds": 0.01},
            },
        ], edges=[{"from": "step_a", "to": "step_b"}])

        engine.execute()

        # Task 3.3: 每个节点产生 start+complete 两个事件, 共 4 个.
        # 这里只校验 complete 事件 (含 previous_node_* 字段).
        complete_events = [e for e in fake.events if e.get("event") == "node.execute.complete"]
        assert len(complete_events) == 2
        # 第一个 complete 事件无前置节点（extra=None 或空 dict）
        first_extra = complete_events[0].get("extra") or {}
        assert not first_extra.get("previous_node_id")
        # 第二个 complete 事件应有前置节点信息
        second = complete_events[1]
        extra = second.get("extra") or {}
        assert extra.get("previous_node_id") == "step_a"
        assert extra.get("previous_node_type") == "wait"
        assert isinstance(extra.get("inter_node_gap_ms"), (int, float))
        assert extra["inter_node_gap_ms"] >= 0

    def test_log_node_event_first_step_has_no_previous(self):
        """首节点的 JSONL 事件 extra 中不应有 previous_node_id 字段。"""
        engine, fake = self._make_engine_with_fake_logger([
            {
                "id": "first",
                "node_type": "wait",
                "config": {"mode": "fixed", "seconds": 0.01},
            },
        ])
        engine.execute()
        extra = fake.events[0].get("extra") or {}
        # 首节点无前置，previous_node_id 不应出现或为空
        assert not extra.get("previous_node_id")


# ============================================================
# Test: error_code 透传到 JSONL (spec 阶段 5 — 任务 1.8)
# ============================================================

class TestStructuredLogErrorCodePropagation:
    """engine 应把 AutoResult.error_code 传给 log_node_event 的 error_code 参数。

    覆盖 spec 阶段 5.3：让 AI 诊断时能按 NodeErrorCode 分类失败原因，
    而非解析 error_msg 字符串。
    """

    def setup_method(self):
        self.mock_device = _make_mock_device()

    def _make_engine_with_fake_logger(self, nodes, edges=None):
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(nodes=nodes, edges=edges or []),
                    device=self.mock_device)
        fake = _FakeStructuredLogger()
        import engine.pipeline_engine as engine_mod
        original_get_logger = engine_mod.get_structured_logger
        engine_mod.get_structured_logger = lambda *args, **kwargs: fake
        self._original_get_logger = original_get_logger
        self._engine_mod = engine_mod
        return engine, fake

    def teardown_method(self):
        if hasattr(self, "_original_get_logger"):
            self._engine_mod.get_structured_logger = self._original_get_logger

    def test_error_code_propagates_to_log_node_event(self):
        """节点 result.error_code 应原样传给 log_node_event.error_code。"""
        from gaf_core.error_codes import NodeErrorCode

        engine, fake = self._make_engine_with_fake_logger([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {"mode": "fixed", "seconds": 0.01},
            },
        ])
        from engine.nodes.wait import WaitNode

        original_execute = WaitNode.execute

        def patched_execute(self, context):
            # 模拟节点主动设置了 error_code（如识别失败节点）
            result = original_execute(self, context)
            result.error_code = NodeErrorCode.NO_MATCH
            return result

        WaitNode.execute = patched_execute
        try:
            engine.execute()
        finally:
            WaitNode.execute = original_execute

        # Task 3.3: 过滤 complete 事件 (start 事件不含 error_code)
        complete_events = [e for e in fake.events if e.get("event") == "node.execute.complete"]
        assert len(complete_events) == 1
        # error_code 应为字符串值（StrEnum 自动转 str）
        assert complete_events[0]["error_code"] == "NO_MATCH"

    def test_error_code_defaults_to_empty_for_successful_node(self):
        """成功节点的 error_code 默认为空字符串。"""
        engine, fake = self._make_engine_with_fake_logger([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {"mode": "fixed", "seconds": 0.01},
            },
        ])
        engine.execute()
        # engine 传 "" 给 log_node_event（log_node_event 内部会省略）
        # Task 3.3: 过滤 complete 事件 (start 事件不含 error_code)
        complete_events = [e for e in fake.events if e.get("event") == "node.execute.complete"]
        assert len(complete_events) == 1
        assert complete_events[0]["error_code"] == ""


# ============================================================
# Test: node.execute.start 事件 + previous_node_result_data (N192 A3/A4 P2)
# ============================================================

class TestStructuredLogNodeExecuteStart:
    """engine 应在节点开始执行前写 node.execute.start 事件, 并在后继节点的
    complete 事件中带 previous_node_result_data 字段.

    覆盖 N192 A3 P2 (日志分段: 让 AI 从 JSONL 反推"卡在第几个节点") 和
    N192 A4 P2 (节点链路可追溯: 前驱 result_data → 当前节点输入数据流).
    """

    def setup_method(self):
        self.mock_device = _make_mock_device()

    def _make_engine_with_fake_logger(self, nodes, edges=None):
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(nodes=nodes, edges=edges or []),
                    device=self.mock_device)
        fake = _FakeStructuredLogger()
        import engine.pipeline_engine as engine_mod
        original_get_logger = engine_mod.get_structured_logger
        engine_mod.get_structured_logger = lambda *args, **kwargs: fake
        self._original_get_logger = original_get_logger
        self._engine_mod = engine_mod
        return engine, fake

    def teardown_method(self):
        if hasattr(self, "_original_get_logger"):
            self._engine_mod.get_structured_logger = self._original_get_logger

    def test_node_execute_start_event_emitted_with_input_config(self):
        """节点开始执行前应该写 node.execute.start 事件, 含 input_config."""
        engine, fake = self._make_engine_with_fake_logger([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {"mode": "fixed", "seconds": 0.01},
            },
        ])
        engine.execute()

        start_events = [e for e in fake.events if e.get("event") == "node.execute.start"]
        assert len(start_events) == 1, (
            f"Expected 1 start event, got {len(start_events)}; "
            f"all events: {[e.get('event') for e in fake.events]}"
        )
        evt = start_events[0]
        assert evt["node_id"] == "step_1"
        assert evt["node_type"] == "wait"
        # 注意: _FakeStructuredLogger 不合并 extra (与真实 log_node_event 的
        # payload.update(extra) 行为不同), extra 作为独立 dict 保留. 真实
        # JSONL 文件中 input_config 会被合并到顶层 (见 TestRetryFallbackJsonlEvents
        # 用 Path 读真实文件验证).
        assert "extra" in evt, f"missing extra in start event: {evt}"
        extra = evt["extra"] or {}
        assert "input_config" in extra, f"missing input_config in extra: {extra}"
        assert extra["input_config"].get("mode") == "fixed"
        assert extra["input_config"].get("seconds") == 0.01

    def test_node_execute_start_emitted_before_complete(self):
        """start 事件应该在 complete 事件之前."""
        engine, fake = self._make_engine_with_fake_logger([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {"mode": "fixed", "seconds": 0.01},
            },
        ])
        engine.execute()

        event_types = [e.get("event") for e in fake.events]
        # 应同时有 start 和 complete
        assert "node.execute.start" in event_types
        assert "node.execute.complete" in event_types
        # start 应该在 complete 之前
        start_idx = event_types.index("node.execute.start")
        complete_idx = event_types.index("node.execute.complete")
        assert start_idx < complete_idx, (
            f"start event should come before complete; "
            f"order: {event_types}"
        )

    def test_complete_event_includes_previous_node_result_data(self):
        """第二个节点的 complete 事件应含 previous_node_result_data."""
        from engine.nodes.wait import WaitNode

        original_execute = WaitNode.execute

        def patched_execute(self, context):
            # 让第一个节点产出 result.data 以便后继节点能看到
            result = original_execute(self, context)
            if self.id == "step_1":
                result.data = {"step1_marker": "hello", "value": 42}
            return result

        WaitNode.execute = patched_execute
        try:
            engine, fake = self._make_engine_with_fake_logger([
                {
                    "id": "step_1",
                    "node_type": "wait",
                    "config": {"mode": "fixed", "seconds": 0.01},
                },
                {
                    "id": "step_2",
                    "node_type": "wait",
                    "config": {"mode": "fixed", "seconds": 0.01},
                },
            ])
            engine.execute()
        finally:
            WaitNode.execute = original_execute

        complete_events = [
            e for e in fake.events
            if e.get("event") == "node.execute.complete"
        ]
        assert len(complete_events) == 2
        # 第二个节点的 complete 事件应含 previous_node_result_data
        # 注意: _FakeStructuredLogger 不合并 extra, previous_node_result_data
        # 在 evt["extra"] 里 (真实 JSONL 会合并到顶层).
        n2_complete = [e for e in complete_events if e.get("node_id") == "step_2"]
        assert len(n2_complete) == 1
        evt = n2_complete[0]
        assert "extra" in evt
        extra = evt["extra"] or {}
        assert "previous_node_result_data" in extra, (
            f"missing previous_node_result_data in extra: {extra}"
        )
        prev_data = extra["previous_node_result_data"]
        assert prev_data is not None
        assert prev_data.get("step1_marker") == "hello"
        assert prev_data.get("value") == 42

    def test_complete_event_no_previous_node_result_data_for_first_node(self):
        """第一个节点 (无前驱) 的 complete 事件不应有 previous_node_result_data."""
        engine, fake = self._make_engine_with_fake_logger([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {"mode": "fixed", "seconds": 0.01},
            },
        ])
        engine.execute()

        complete_events = [
            e for e in fake.events
            if e.get("event") == "node.execute.complete"
        ]
        assert len(complete_events) == 1
        # 第一个节点 _step_results 此时为空 (还没追加), extra 不含 previous_node_result_data
        # (因为 self._previous_node_id 也是空, extra 本身就是 None)
        evt = complete_events[0]
        extra = evt.get("extra") or {}
        assert "previous_node_result_data" not in extra


# ============================================================
# Test: previous_node_result_data 按字段重要性分级截断 (N193 Task 5.2)
# ============================================================

class TestPreviousNodeResultDataPriorityTruncation:
    """N193 Task 5.2: previous_node_result_data 应按字段重要性分级截断.

    P0 诊断关键字段 (confidence / match_loc / coord_system) 必须保留,
    P2 大对象 (detections / boxes) 替换为摘要, 让 AI 从 JSONL 就能定位
    失败上下文.
    """

    def test_preserves_p0_priority_fields_in_large_result(self):
        """大 result 中 P0 字段 (confidence/match_loc/coord_system) 应保留."""
        from engine.pipeline_engine import _truncate_result_data_priority

        # 模拟一个 template_match 节点的大 result_data:
        # 含 P0 字段 + P2 大对象 + P3 其他字段
        large_data = {
            # P0 必保字段
            "confidence": 0.85,
            "threshold": 0.8,
            "match_loc": {"x": 960, "y": 540},
            "coord_system": "logical",
            "source": "template_match_node",
            "success": True,
            "node_id": "step_1",
            "error_code": "",
            # P2 大对象 (应被替换为摘要)
            "detections": [{"box": [i, i, i+10, i+10]} for i in range(100)],
            "boxes": [[i, i, i+10, i+10] for i in range(100)],
            "screenshot_path": "/very/long/path/" + "x" * 200,
            # P3 其他字段
            "extra_info": "y" * 800,
        }

        result = _truncate_result_data_priority(large_data, max_chars=1000)

        # P0 字段应完整保留
        assert result["confidence"] == 0.85
        assert result["threshold"] == 0.8
        assert result["match_loc"] == {"x": 960, "y": 540}
        assert result["coord_system"] == "logical"
        assert result["source"] == "template_match_node"
        assert result["success"] is True
        assert result["node_id"] == "step_1"

    def test_truncates_p2_large_lists_to_summary(self):
        """P2 大对象 (detections/boxes) 应替换为 {_truncated, _count} 摘要."""
        from engine.pipeline_engine import _truncate_result_data_priority

        large_data = {
            "confidence": 0.9,
            "coord_system": "logical",
            "detections": [{"box": [i, i, i+10, i+10]} for i in range(50)],
            "boxes": [[i, i, i+10, i+10] for i in range(50)],
        }

        result = _truncate_result_data_priority(large_data, max_chars=1000)

        # P2 字段应被替换为摘要
        assert isinstance(result["detections"], dict)
        assert result["detections"].get("_truncated") is True
        assert result["detections"].get("_count") == 50
        assert isinstance(result["boxes"], dict)
        assert result["boxes"].get("_truncated") is True
        assert result["boxes"].get("_count") == 50

    def test_small_result_preserved_as_is(self):
        """小 result_data 应原样保留 (不截断)."""
        from engine.pipeline_engine import _truncate_result_data_priority

        small_data = {
            "confidence": 0.95,
            "match_loc": {"x": 100, "y": 200},
            "coord_system": "logical",
        }

        result = _truncate_result_data_priority(small_data, max_chars=1000)
        assert result == small_data

    def test_non_dict_returns_truncated_value(self):
        """非 dict 输入应回退到 _truncate_dict."""
        from engine.pipeline_engine import _truncate_result_data_priority

        # 字符串输入
        s = "x" * 2000
        result = _truncate_result_data_priority(s, max_chars=1000)
        assert isinstance(result, dict)
        assert result.get("_truncated") is True

    def test_none_returns_none(self):
        """None 输入应返回 None."""
        from engine.pipeline_engine import _truncate_result_data_priority

        assert _truncate_result_data_priority(None) is None

    def test_p0_always_preserved_even_when_total_exceeds_limit(self):
        """总长度超限时, P0 字段始终保留, P3/P2/P1 依次降级."""
        from engine.pipeline_engine import _truncate_result_data_priority

        # 构造超大 result: P0 字段 + 大量 P3 字段
        huge_data = {
            # P0
            "confidence": 0.88,
            "match_loc": {"x": 500, "y": 300},
            "coord_system": "physical",
            # 大量 P3 字段 (强制总长度超限)
            **{f"field_{i}": "z" * 200 for i in range(20)},
            # P2 大对象
            "detections": [{"box": [i, i, i+10, i+10]} for i in range(30)],
        }

        result = _truncate_result_data_priority(huge_data, max_chars=1000)

        # P0 必须保留
        assert result["confidence"] == 0.88
        assert result["match_loc"] == {"x": 500, "y": 300}
        assert result["coord_system"] == "physical"


# ============================================================
# Test: post_verify 强验证集成 (spec 阶段 3 — 任务 3.2)
# ============================================================

class TestPostVerifyIntegration:
    """engine 应在节点成功后执行 post_verify 配置的验证。

    场景：节点自身 execute 成功，但需要进一步验证屏幕状态符合预期
    （如点击后确认弹窗已关闭、OCR 后确认目标文字出现）。
    post_verify 失败时把节点标记为失败，error_code=POST_VERIFY_FAILED。
    """

    def setup_method(self):
        self.mock_device = _make_mock_device()

    def _make_engine_with_verifier(self, nodes, mock_verifier):
        """构造 engine 并注入 mock_verifier。"""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(nodes=nodes),
                    device=self.mock_device)
        engine.set_verifier(mock_verifier)
        return engine

    def test_post_verify_runs_when_node_succeeds(self):
        """节点成功后应调用 verifier.verify(post_verify 配置)。"""
        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = success_result(data={"matched": True})

        engine = self._make_engine_with_verifier([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {
                    "mode": "fixed", "seconds": 0.01,
                    "post_verify": {"type": "exist", "template": "ok.png"},
                },
            },
        ], mock_verifier)

        result = engine.execute()
        assert result.success
        mock_verifier.verify.assert_called_once()
        # 传入 verify 的应是 post_verify 配置 dict
        call_arg = mock_verifier.verify.call_args[0][0]
        assert call_arg["type"] == "exist"
        assert call_arg["template"] == "ok.png"

    def test_post_verify_skipped_when_not_configured(self):
        """没有 post_verify 配置时不应调用 verifier。"""
        mock_verifier = MagicMock()
        engine = self._make_engine_with_verifier([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {"mode": "fixed", "seconds": 0.01},
            },
        ], mock_verifier)

        result = engine.execute()
        assert result.success
        mock_verifier.verify.assert_not_called()

    def test_post_verify_skipped_when_node_fails(self):
        """节点自身失败时不应再调用 post_verify。"""
        mock_verifier = MagicMock()
        engine = self._make_engine_with_verifier([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {
                    "mode": "invalid_mode",
                    "post_verify": {"type": "exist", "template": "ok.png"},
                },
            },
        ], mock_verifier)

        result = engine.execute()
        assert not result.success
        mock_verifier.verify.assert_not_called()

    def test_post_verify_failed_marks_node_failed(self):
        """post_verify 失败应把节点标记为失败 + error_code=POST_VERIFY_FAILED。"""
        from core.result import fail_result

        mock_verifier = MagicMock()
        mock_verifier.verify.return_value = fail_result(error_msg="模板未找到")

        engine = self._make_engine_with_verifier([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {
                    "mode": "fixed", "seconds": 0.01,
                    "post_verify": {"type": "exist", "template": "ok.png"},
                },
            },
        ], mock_verifier)

        result = engine.execute()
        # pipeline 整体失败
        assert not result.success
        assert len(result.step_results) == 1
        step = result.step_results[0]
        # 节点被标记失败
        assert not step.success
        assert step.error_code == "POST_VERIFY_FAILED"
        # 错误消息包含 post_verify 失败原因
        assert "模板未找到" in step.error_msg

    def test_post_verify_no_verifier_injected_skips_silently(self):
        """未注入 verifier 时 post_verify 配置应被静默跳过（向后兼容）。"""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {
                    "mode": "fixed", "seconds": 0.01,
                    "post_verify": {"type": "exist", "template": "ok.png"},
                },
            },
        ]), device=self.mock_device)
        # 不调用 set_verifier

        result = engine.execute()
        # 不应抛异常，节点成功
        assert result.success

    def test_post_verify_exception_caught_and_marks_failed(self):
        """verifier.verify 抛异常时节点应被标记失败，不应传播异常。"""
        mock_verifier = MagicMock()
        mock_verifier.verify.side_effect = RuntimeError("verifier crashed")

        engine = self._make_engine_with_verifier([
            {
                "id": "step_1",
                "node_type": "wait",
                "config": {
                    "mode": "fixed", "seconds": 0.01,
                    "post_verify": {"type": "exist", "template": "ok.png"},
                },
            },
        ], mock_verifier)

        result = engine.execute()
        assert not result.success
        step = result.step_results[0]
        assert step.error_code == "POST_VERIFY_FAILED"
        assert "verifier crashed" in step.error_msg


# ============================================================
# Test: retry/fallback JSONL trace (N192 A5 P1 — 任务 2.2)
# ============================================================

class TestRetryFallbackJsonlEvents:
    """retry/fallback 应写 node.execute.retry / node.execute.fallback JSONL 事件.

    覆盖 N192 A5 P1 (AI 调试视角 — retry/fallback trace):
    AI 跑 pipeline 时若节点反复重试或降级到 fallback, 没有结构化 trace 就只能
    看文本日志猜. 补 JSONL 事件后, AI 用 jq 'select(.event=="node.execute.retry")'
    即可过滤, 含 attempt / max_retries / delay_ms / last_error_code 字段.
    """

    def test_retry_emits_jsonl_event(self, tmp_path):
        """retry 应该写 node.execute.retry JSONL 事件 (含 attempt/max_retries/delay_ms).

        场景: template_match 无模板 + 高阈值 → 失败; retry.max_retries=2
        期望: JSONL 恰好 2 个 node.execute.retry 事件, 每个含 attempt/max_retries/delay_ms.
        """
        from pathlib import Path

        mock_device = _make_mock_device()
        pipeline_dict = _make_pipeline_json(nodes=[
            {
                "id": "n1",
                "node_type": "template_match",
                "config": {"threshold": 0.99},  # no template -> fails
                "retry": {
                    "max_retries": 2,
                    "base_delay": 0.01,
                    "backoff_factor": 1.0,
                },
            },
        ])
        engine = PipelineEngine()
        engine.load(pipeline_dict, device=mock_device, debug_dir=str(tmp_path))
        result = engine.execute()
        # 节点应失败 (template_match 无模板, 重试 2 次仍失败)
        assert not result.success

        # 读 JSONL 文件
        log_path = engine.structured_log_path
        assert log_path, "structured_log_path should be non-empty"
        lines = Path(log_path).read_text(encoding="utf-8").strip().split("\n")
        events = [json.loads(line) for line in lines]

        # 验证有 node.execute.retry 事件 (应恰好 2 个, 对应 max_retries=2)
        retry_events = [e for e in events if e.get("event") == "node.execute.retry"]
        assert len(retry_events) == 2, (
            f"Expected 2 retry events, got {len(retry_events)}; "
            f"all events: {[e.get('event') for e in events]}"
        )
        # 每个 retry 事件应含 attempt / max_retries / delay_ms (extra 字段
        # 被 log_node_event 合并到 payload 顶层, 故直接 assert 顶层)
        for evt in retry_events:
            assert "attempt" in evt, f"missing 'attempt' in retry event: {evt}"
            assert "max_retries" in evt, f"missing 'max_retries' in retry event: {evt}"
            assert "delay_ms" in evt, f"missing 'delay_ms' in retry event: {evt}"
            assert evt["max_retries"] == 2
            assert evt["attempt"] in (1, 2)
            assert isinstance(evt["delay_ms"], int)
            assert evt["delay_ms"] >= 0

    def test_fallback_emits_jsonl_event(self, tmp_path):
        """fallback 触发应该写 node.execute.fallback JSONL 事件 (含 fallback_action/trigger_phase).

        场景: template_match 无模板 → 失败; fallback.action=wait 0.01s
        期望: JSONL 至少 1 个 node.execute.fallback 事件, 含 fallback_action/trigger_phase.
        """
        from pathlib import Path

        mock_device = _make_mock_device()
        pipeline_dict = _make_pipeline_json(nodes=[
            {
                "id": "n1",
                "node_type": "template_match",
                "config": {"threshold": 0.99},  # no template -> fails
                "fallback": {"action": "wait", "params": {"seconds": 0.01}},
            },
        ])
        engine = PipelineEngine()
        engine.load(pipeline_dict, device=mock_device, debug_dir=str(tmp_path))
        engine.execute()
        # fallback wait 应成功 (执行了 device wait 0.01s), 但不强制断言
        # result.success — 我们只关心 fallback 事件是否写入 JSONL.

        log_path = engine.structured_log_path
        assert log_path, "structured_log_path should be non-empty"
        lines = Path(log_path).read_text(encoding="utf-8").strip().split("\n")
        events = [json.loads(line) for line in lines]

        # 验证有 node.execute.fallback 事件
        fallback_events = [e for e in events if e.get("event") == "node.execute.fallback"]
        assert len(fallback_events) >= 1, (
            f"Expected >= 1 fallback event, got {len(fallback_events)}; "
            f"all events: {[e.get('event') for e in events]}"
        )
        # 每个 fallback 事件应含 fallback_action / trigger_phase
        for evt in fallback_events:
            assert "fallback_action" in evt, (
                f"missing 'fallback_action' in fallback event: {evt}"
            )
            assert "trigger_phase" in evt, (
                f"missing 'trigger_phase' in fallback event: {evt}"
            )
            assert evt["fallback_action"] == "wait"
            assert evt["trigger_phase"] in (
                "fallback_triggered", "fallback_completed",
            )
        # 应恰好 1 个 trigger_phase=fallback_triggered (方法入口处发射)
        triggered = [
            e for e in fallback_events
            if e.get("trigger_phase") == "fallback_triggered"
        ]
        assert len(triggered) == 1, (
            f"Expected 1 fallback_triggered event, got {len(triggered)}"
        )


# ============================================================
# Test: fallback/timeout fail_result 三要素 (N192 A7 P3)
# ============================================================

class TestFallbackTimeoutFailResultThreeFields:
    """fallback / timeout / 异常路径的 fail_result 应带 node_id / node_type / error_code.

    覆盖 N192 A7 P3: 报错边界 — 节点内部异常应被捕获并包装成「节点级失败」
    而非让整个 pipeline 崩, 且 fail_result 必须带三要素让 AI 可定位.
    """

    def setup_method(self):
        self.mock_device = _make_mock_device()

    def test_fallback_invalid_config_includes_three_fields(self, tmp_path):
        """fallback 配置无效 (缺 action/type) 时 fail_result 应带三要素."""
        pipeline_dict = _make_pipeline_json(nodes=[
            {
                "id": "n1",
                "node_type": "template_match",
                "config": {"threshold": 0.99},  # no template -> fails
                "fallback": {"params": {"x": 1}},  # 缺 action/type
            },
        ])
        engine = PipelineEngine()
        engine.load(pipeline_dict, device=self.mock_device, debug_dir=str(tmp_path))
        result = engine.execute()
        assert not result.success

        # 找到 fallback 路径产生的失败 step
        failed_steps = [s for s in engine._step_results if not s.success]
        assert len(failed_steps) >= 1
        # 最后一个失败 step 应是 fallback 的 fail_result
        last_fail = failed_steps[-1]
        assert last_fail.node_id == "n1"
        assert last_fail.node_type == "template_match"
        assert last_fail.error_code != ""
        assert last_fail.error_code != "UNKNOWN" or "fallback" in last_fail.error_msg.lower()
        # 应该是 PARAM_INVALID (配置无效)
        from core.error_codes import NodeErrorCode
        assert last_fail.error_code == NodeErrorCode.PARAM_INVALID.value

    def test_fallback_unknown_action_includes_three_fields(self, tmp_path):
        """fallback 未知动作时 fail_result 应带三要素 + PARAM_INVALID."""
        pipeline_dict = _make_pipeline_json(nodes=[
            {
                "id": "n1",
                "node_type": "template_match",
                "config": {"threshold": 0.99},
                "fallback": {"action": "invalid_action_xyz", "params": {}},
            },
        ])
        engine = PipelineEngine()
        engine.load(pipeline_dict, device=self.mock_device, debug_dir=str(tmp_path))
        result = engine.execute()
        assert not result.success

        failed_steps = [s for s in engine._step_results if not s.success]
        assert len(failed_steps) >= 1
        last_fail = failed_steps[-1]
        assert last_fail.node_id == "n1"
        assert last_fail.node_type == "template_match"
        from core.error_codes import NodeErrorCode
        assert last_fail.error_code == NodeErrorCode.PARAM_INVALID.value

    def test_fallback_no_device_includes_three_fields(self, tmp_path):
        """fallback 无可用设备时 fail_result 应带三要素 + DEVICE_DISCONNECTED."""
        # 构造一个会触发 fallback 且 fallback 时 device 为 None 的场景
        # 需要 mock context.device = None
        pipeline_dict = _make_pipeline_json(nodes=[
            {
                "id": "n1",
                "node_type": "template_match",
                "config": {"threshold": 0.99},
                "fallback": {"action": "click", "params": {"x": 1, "y": 1}},
            },
        ])
        engine = PipelineEngine()
        # 不传 device, context.device = None
        engine.load(pipeline_dict, device=None, debug_dir=str(tmp_path))
        result = engine.execute()
        assert not result.success

        failed_steps = [s for s in engine._step_results if not s.success]
        # 至少有一个失败 step 带 node_id
        assert len(failed_steps) >= 1
        # 找到 fallback 失败的 step (error_msg 含 "fallback")
        fallback_fails = [
            s for s in failed_steps
            if s.error_msg and "fallback" in s.error_msg.lower()
        ]
        if fallback_fails:
            last_fail = fallback_fails[-1]
            assert last_fail.node_id == "n1"
            assert last_fail.node_type == "template_match"
            from core.error_codes import NodeErrorCode
            assert last_fail.error_code == NodeErrorCode.DEVICE_DISCONNECTED.value

    def test_timeout_fail_result_includes_three_fields(self, tmp_path):
        """节点执行超时时 fail_result 应带三要素 + TIMEOUT."""
        from core.error_codes import NodeErrorCode

        # 构造一个会超时的 pipeline: wait 节点 + 极短 timeout
        pipeline_dict = _make_pipeline_json(nodes=[
            {
                "id": "n1",
                "node_type": "wait",
                "config": {
                    "mode": "fixed",
                    "seconds": 5,  # 等 5 秒
                    "timeout": 0.05,  # 但 50ms 就超时
                },
            },
        ])
        engine = PipelineEngine()
        engine.load(pipeline_dict, device=self.mock_device, debug_dir=str(tmp_path))
        result = engine.execute()
        assert not result.success

        failed_steps = [s for s in engine._step_results if not s.success]
        assert len(failed_steps) >= 1
        last_fail = failed_steps[-1]
        # 超时 fail_result 应带三要素
        assert last_fail.node_id == "n1"
        assert last_fail.node_type == "wait"
        assert last_fail.error_code == NodeErrorCode.TIMEOUT.value

    def test_node_execute_exception_includes_three_fields(self, tmp_path):
        """节点 execute 抛异常时 fail_result 应带三要素 + UNKNOWN."""
        from core.error_codes import NodeErrorCode
        from engine.nodes.wait import WaitNode

        original_execute = WaitNode.execute

        def crashing_execute(self, context):
            raise RuntimeError("故意崩溃测试 N192 A7")

        WaitNode.execute = crashing_execute
        try:
            pipeline_dict = _make_pipeline_json(nodes=[
                {
                    "id": "n1",
                    "node_type": "wait",
                    "config": {"mode": "fixed", "seconds": 0.01},
                },
            ])
            engine = PipelineEngine()
            engine.load(pipeline_dict, device=self.mock_device, debug_dir=str(tmp_path))
            result = engine.execute()
        finally:
            WaitNode.execute = original_execute

        assert not result.success
        failed_steps = [s for s in engine._step_results if not s.success]
        assert len(failed_steps) >= 1
        last_fail = failed_steps[-1]
        # 异常 fail_result 应带三要素
        assert last_fail.node_id == "n1"
        assert last_fail.node_type == "wait"
        assert last_fail.error_code == NodeErrorCode.UNKNOWN.value
        assert "故意崩溃" in last_fail.error_msg


# ============================================================
# Test: HumanTakeoverError 携带 node_id (N193 Task 5.3)
# ============================================================

class TestHumanTakeoverErrorNodeId:
    """N193 Task 5.3: HumanTakeoverError 应携带 node_id, orchestrator 捕获时
    应把 node_id 写入 fail_result, 让 AI 诊断时能定位是哪个节点触发了
    人工接管.
    """

    def test_human_takeover_error_carries_node_id(self):
        """HumanTakeoverError 构造时传入 node_id 应被保留."""
        from core.recovery import HumanTakeoverError

        exc = HumanTakeoverError("测试人工接管", node_id="step_3")
        assert exc.node_id == "step_3"
        assert "测试人工接管" in str(exc)

    def test_human_takeover_error_default_node_id_empty(self):
        """HumanTakeoverError 不传 node_id 时默认为空字符串."""
        from core.recovery import HumanTakeoverError

        exc = HumanTakeoverError("测试人工接管")
        assert exc.node_id == ""

    def test_request_human_takeover_passes_node_id_to_exception(self):
        """RecoveryStrategy.request_human_takeover 传 node_id 时,
        抛出的 HumanTakeoverError 应携带该 node_id.
        """
        from core.recovery import HumanTakeoverError, RecoveryStrategy

        strategy = RecoveryStrategy()
        with pytest.raises(HumanTakeoverError) as exc_info:
            strategy.request_human_takeover(
                reason="连续失败超阈值",
                task_id="task_001",
                device_id="device_001",
                node_id="step_5",
            )
        assert exc_info.value.node_id == "step_5"

    def test_orchestrator_human_takeover_fail_result_has_node_id(self, tmp_path):
        """orchestrator 捕获 HumanTakeoverError 时, fail_result 应含 node_id."""
        from unittest.mock import patch

        from core.orchestrator import TaskOrchestrator
        from core.recovery import HumanTakeoverError
        from devices.manager import DeviceManager
        from image.processor import ImageProcessor

        # 构造一个会抛 HumanTakeoverError 的 mock engine.
        # 继承 MagicMock 并 spec=None, 这样 orchestrator 调用任意方法
        # (set_callbacks / set_monitor_manager / set_recovery_manager ...)
        # 都自动返回 MagicMock 而非抛 AttributeError.
        class _FakeEngine(MagicMock):
            def __init__(self, *args, **kwargs):
                super().__init__(spec=None)
                self._structured_logger = None
                self._execution_id = ""

            def load(self, *args, **kwargs):
                pass

            # Task 1.1: orchestrator.execute_pipeline 现在把 start_step_index
            # + previous_results 透传给 engine.execute(). 这个 _FakeEngine 只
            # 验证 HumanTakeoverError 路径, 不关心重试参数, 用 **kwargs 吞掉.
            def execute(self, **kwargs):
                raise HumanTakeoverError(
                    "节点 step_2 恢复耗尽, 需人工接管",
                    node_id="step_2",
                )

            @property
            def structured_log_path(self):
                return ""

        device_manager = MagicMock(spec=DeviceManager)
        image_processor = MagicMock(spec=ImageProcessor)
        orchestrator = TaskOrchestrator(device_manager, image_processor)

        # patch engine 构造函数返回 _FakeEngine
        # PipelineEngine 在 execute_pipeline 内部局部导入 (from engine.pipeline_engine import),
        # 所以 patch 路径是 engine.pipeline_engine.PipelineEngine, 不是 core.orchestrator.PipelineEngine.
        with patch("engine.pipeline_engine.PipelineEngine", return_value=_FakeEngine()):
            pipeline_dict = {
                "nodes": [{"id": "step_2", "node_type": "wait", "config": {"seconds": 0.01}}],
                "edges": [],
                "entry_node": "step_2",
            }
            result = orchestrator.execute_pipeline(pipeline_dict)

        assert not result.success
        # N193 Task 5.3: fail_result 应含 node_id (从 HumanTakeoverError 取)
        assert result.node_id == "step_2"
        assert "人工接管" in result.error_msg


# ============================================================
# Task 1.1: B7 重试单节点功能 (P0-1) — start_step_index
#
# N192 视角 B 评估发现 B7 复现路径最弱 (4/10): 用户拿到错误后无法
# 自行修复, 必须重新跑整个 pipeline. PipelineEngine.execute() 新增
# start_step_index 参数, 跳过前 N 个节点从第 N+1 个开始执行, 之前
# 成功步骤的 result 通过 previous_results 参数恢复, 让用户能"重试
# 此步"而不必重跑全流程.
# ============================================================


class TestRetryFromStep:
    """Task 1.1: PipelineEngine.execute(start_step_index=N) 跳过前 N 个节点.

    覆盖两个场景:
    - test_execute_with_start_step_index_skips_earlier_nodes:
      start_step_index > 0 时前 N 个节点不应被执行 (mock_device.click
      调用次数为 0), 仅第 N+1 个节点被执行.
    - test_execute_with_start_step_index_preserves_previous_results:
      previous_results 列表传入时, 跳过节点的 result 应被合并到
      最终 PipelineResult.step_results 中, 让用户能看到完整链路.
    """

    def setup_method(self):
        self.mock_device = _make_mock_device()

    def test_execute_with_start_step_index_skips_earlier_nodes(self):
        """start_step_index=2 时, step_1/step_2 不应执行, 仅 step_3 执行.

        验证:
        - step_1/step_2 的 mock_device.click 未被调用 (前置节点跳过)
        - step_3 的 mock_device.click 被调用 1 次 (实际执行)
        - result.step_results 中 step_1/step_2 来自 previous_results (非执行)
        - result.step_results 中 step_3 是真实执行结果
        - result.success == True
        """
        from core.result import AutoResult

        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {"id": "step_1", "node_type": "click", "config": {"x": 10, "y": 20}},
                {"id": "step_2", "node_type": "click", "config": {"x": 30, "y": 40}},
                {"id": "step_3", "node_type": "click", "config": {"x": 50, "y": 60}},
            ],
            edges=[
                {"from": "step_1", "to": "step_2"},
                {"from": "step_2", "to": "step_3"},
            ],
        ), device=self.mock_device)

        # 前两个节点的"之前成功" result, 模拟重试场景下保留的状态
        previous_results = [
            AutoResult(
                success=True,
                data={"x": 10, "y": 20},
                node_id="step_1",
                node_type="click",
            ),
            AutoResult(
                success=True,
                data={"x": 30, "y": 40},
                node_id="step_2",
                node_type="click",
            ),
        ]

        # 重置 mock 以便断言
        self.mock_device.click.reset_mock()

        result = engine.execute(start_step_index=2, previous_results=previous_results)

        # 1. 整体成功
        assert result.success, f"expected success, got error: {result.error_msg}"
        assert result.state == PipelineState.COMPLETED

        # 2. step_results 长度 = 3 (2 个 previous + 1 个实际执行)
        assert len(result.step_results) == 3, (
            f"expected 3 step_results (2 previous + 1 executed), "
            f"got {len(result.step_results)}"
        )

        # 3. 前两个 step_results 来自 previous_results (节点 id 匹配)
        assert result.step_results[0].node_id == "step_1"
        assert result.step_results[1].node_id == "step_2"

        # 4. 第三个是 step_3 真实执行结果
        assert result.step_results[2].node_id == "step_3"
        assert result.step_results[2].success

        # 5. 关键断言: device.click 只被调用 1 次 (仅 step_3 真实执行)
        # 前两个节点跳过执行, 不应触达 device
        assert self.mock_device.click.call_count == 1, (
            f"expected device.click called 1 time (only step_3), "
            f"got {self.mock_device.click.call_count}"
        )

    def test_execute_with_start_step_index_preserves_previous_results(self):
        """previous_results 传入时, 跳过节点的 result 必须出现在最终 step_results 中.

        验证:
        - previous_results 中的 result 被原样保留到最终 step_results
        - 跳过节点的 data 字段不丢失 (用户能看到前驱节点输出)
        - previous_node_id 链路状态正确传递: step_3 的 JSONL 事件
          应能拿到 step_2 作为 previous_node_id
        """
        from core.result import AutoResult

        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {"id": "step_1", "node_type": "click", "config": {"x": 1, "y": 2}},
                {"id": "step_2", "node_type": "click", "config": {"x": 3, "y": 4}},
                {"id": "step_3", "node_type": "click", "config": {"x": 5, "y": 6}},
            ],
            edges=[
                {"from": "step_1", "to": "step_2"},
                {"from": "step_2", "to": "step_3"},
            ],
        ), device=self.mock_device)

        previous_results = [
            AutoResult(
                success=True,
                data={"x": 1, "y": 2, "marker": "step_1_data"},
                node_id="step_1",
                node_type="click",
            ),
            AutoResult(
                success=True,
                data={"x": 3, "y": 4, "marker": "step_2_data"},
                node_id="step_2",
                node_type="click",
            ),
        ]

        self.mock_device.click.reset_mock()
        result = engine.execute(start_step_index=2, previous_results=previous_results)

        assert result.success, f"expected success, got: {result.error_msg}"
        assert len(result.step_results) == 3

        # previous_results 的 data 必须原样保留 (用户调试时需要看前驱节点输出)
        assert result.step_results[0].data.get("marker") == "step_1_data"
        assert result.step_results[1].data.get("marker") == "step_2_data"

        # step_3 是实际执行的, data 来自真实节点 (click 节点 data 默认 {})
        assert result.step_results[2].node_id == "step_3"

    def test_execute_with_start_step_index_zero_behaves_like_normal(self):
        """start_step_index=0 (默认) 时行为与原 execute() 一致 (无跳过, 无 previous_results)."""
        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {"id": "step_1", "node_type": "click", "config": {"x": 1, "y": 2}},
                {"id": "step_2", "node_type": "wait", "config": {"seconds": 0.01}},
            ],
            edges=[{"from": "step_1", "to": "step_2"}],
        ), device=self.mock_device)

        self.mock_device.click.reset_mock()
        result = engine.execute()

        assert result.success
        assert len(result.step_results) == 2
        # device.click 应被调用 1 次 (step_1)
        assert self.mock_device.click.call_count == 1

    def test_execute_with_start_step_index_out_of_range_returns_completed(self):
        """start_step_index >= 节点数时, 所有节点都跳过, 返回 COMPLETED (空执行).

        场景: 用户重试"最后一步之后" (边缘情况), 应该是合法的 no-op 而非报错.
        """
        from core.result import AutoResult

        engine = PipelineEngine()
        engine.load(_make_pipeline_json(
            nodes=[
                {"id": "step_1", "node_type": "click", "config": {"x": 1, "y": 2}},
            ],
        ), device=self.mock_device)

        previous_results = [
            AutoResult(success=True, data={}, node_id="step_1", node_type="click"),
        ]

        self.mock_device.click.reset_mock()
        # start_step_index=1 = 跳过第 1 个节点 (从第 2 个开始, 但没有第 2 个)
        result = engine.execute(start_step_index=1, previous_results=previous_results)

        # 应该 COMPLETED, device.click 未被调用
        assert result.success
        assert result.state == PipelineState.COMPLETED
        assert self.mock_device.click.call_count == 0
        # previous_results 仍应保留
        assert len(result.step_results) == 1


class TestOrchestratorRetryFromStep:
    """Task 1.1: orchestrator.execute_pipeline 应透传 start_step_index 给 engine.

    覆盖:
    - test_orchestrator_passes_start_step_index_to_engine: 验证参数透传
    - test_orchestrator_start_step_index_default_zero: 默认值不影响现有行为
    """

    def test_orchestrator_passes_start_step_index_to_engine(self, tmp_path):
        """orchestrator.execute_pipeline(start_step_index=N) 应把 N 透传给 engine.execute()."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator import TaskOrchestrator
        from devices.manager import DeviceManager
        from image.processor import ImageProcessor

        # 用 MagicMock spec=None 让任意方法调用都不抛 AttributeError
        class _FakeEngine(MagicMock):
            def __init__(self, *args, **kwargs):
                super().__init__(spec=None)
                self._structured_logger = None
                self._execution_id = ""
                # 记录 execute() 被调用时收到的 kwargs
                self.execute_kwargs = {}

            def load(self, *args, **kwargs):
                pass

            def execute(self, **kwargs):
                self.execute_kwargs = kwargs
                from core.result import success_result
                return success_result(data={})

            @property
            def structured_log_path(self):
                return ""

        device_manager = MagicMock(spec=DeviceManager)
        image_processor = MagicMock(spec=ImageProcessor)
        orchestrator = TaskOrchestrator(device_manager, image_processor)

        # device_manager.get_active_device 返回一个 mock device
        mock_device = MagicMock()
        mock_device.device_id = "mock_device"
        device_manager.get_active_device.return_value = mock_device

        fake_engine = _FakeEngine()
        with patch("engine.pipeline_engine.PipelineEngine", return_value=fake_engine):
            pipeline_dict = {
                "nodes": [{"id": "step_1", "node_type": "click", "config": {"x": 1, "y": 2}}],
                "edges": [],
                "entry_node": "step_1",
            }
            orchestrator.execute_pipeline(pipeline_dict, start_step_index=2)

        # engine.execute 应该收到 start_step_index=2
        assert fake_engine.execute_kwargs.get("start_step_index") == 2, (
            f"orchestrator 应透传 start_step_index=2 给 engine.execute(), "
            f"got kwargs: {fake_engine.execute_kwargs}"
        )

    def test_orchestrator_start_step_index_default_zero(self, tmp_path):
        """orchestrator.execute_pipeline 不传 start_step_index 时默认为 0 (无重试)."""
        from unittest.mock import MagicMock, patch

        from core.orchestrator import TaskOrchestrator
        from devices.manager import DeviceManager
        from image.processor import ImageProcessor

        class _FakeEngine(MagicMock):
            def __init__(self, *args, **kwargs):
                super().__init__(spec=None)
                self._structured_logger = None
                self._execution_id = ""
                self.execute_kwargs = {}

            def load(self, *args, **kwargs):
                pass

            def execute(self, **kwargs):
                self.execute_kwargs = kwargs
                from core.result import success_result
                return success_result(data={})

            @property
            def structured_log_path(self):
                return ""

        device_manager = MagicMock(spec=DeviceManager)
        image_processor = MagicMock(spec=ImageProcessor)
        orchestrator = TaskOrchestrator(device_manager, image_processor)

        mock_device = MagicMock()
        mock_device.device_id = "mock_device"
        device_manager.get_active_device.return_value = mock_device

        fake_engine = _FakeEngine()
        with patch("engine.pipeline_engine.PipelineEngine", return_value=fake_engine):
            pipeline_dict = {
                "nodes": [{"id": "step_1", "node_type": "click", "config": {"x": 1, "y": 2}}],
                "edges": [],
                "entry_node": "step_1",
            }
            orchestrator.execute_pipeline(pipeline_dict)

        # 默认 start_step_index 应为 0 (与现有行为兼容)
        assert fake_engine.execute_kwargs.get("start_step_index") == 0
