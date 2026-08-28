"""TD-336 #5: 基础动作节点 (click/wait/swipe) smoke 测试

覆盖 3 个动作节点的核心分支:
- ClickNode: 无设备失败 / 直接坐标点击 / 变量解析 / 多次点击 / click 失败容错
- WaitNode: fixed 模式 / 未知模式 / stable 模式无设备
- SwipeNode: 无设备失败 / 直接坐标滑动 / DeviceError 容错

使用 MagicMock 模拟 PipelineContext 与 device, 不依赖真实 OpenCV/设备.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import to register nodes.
import engine.nodes.click  # noqa: F401
import engine.nodes.swipe  # noqa: F401
import engine.nodes.wait  # noqa: F401
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
    # N191 §10.10 (AI 可调试性, 2026-07-27): 显式设 None 避免 MagicMock
    # 默认属性被 click/swipe 等节点的 `getattr(context, 'coord_transformer', None)`
    # 拿到 MagicMock 实例 (truthy), 走 transformer 路径调用
    # convert_original_to_current_client 返回 MagicMock 导致 unpack 失败。
    # 与 test_target_resolution.py / test_engine_nodes_input.py 一致。
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


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Replace time.sleep with a no-op so tests run fast (wait/click)."""
    import engine.nodes.click as click_mod
    import engine.nodes.wait as wait_mod
    monkeypatch.setattr(click_mod.time, "sleep", lambda *_a, **_kw: None)
    monkeypatch.setattr(wait_mod.time, "sleep", lambda *_a, **_kw: None)


def _make_node(node_type, node_id="test_node", config=None):
    """Build a node instance via the factory."""
    return PIPELINE_NODE_REGISTRY[node_type].from_dict({
        "id": node_id,
        "node_type": node_type,
        "config": config or {},
    })


# ============================================================
# Registration
# ============================================================

class TestRegistration:
    def test_click_registered(self):
        assert "click" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["click"].__name__ == "ClickNode"

    def test_wait_registered(self):
        assert "wait" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["wait"].__name__ == "WaitNode"

    def test_swipe_registered(self):
        assert "swipe" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["swipe"].__name__ == "SwipeNode"


# ============================================================
# ClickNode
# ============================================================

class TestClickNode:
    def test_no_device_returns_fail(self, mock_context):
        node = _make_node("click", config={"x": 100, "y": 200})
        result = node.execute(mock_context)
        assert not result.success
        assert "device=None" in result.error_msg or "未设置设备" in result.error_msg

    def test_basic_click_succeeds(self, mock_context):
        device = MagicMock()
        mock_context.device = device
        node = _make_node("click", config={"x": 100, "y": 200})
        result = node.execute(mock_context)
        assert result.success
        assert result.data["x"] == 100
        assert result.data["y"] == 200
        assert result.data["clicks"] == 1
        device.click.assert_called_once_with(100, 200)

    def test_multiple_clicks(self, mock_context):
        device = MagicMock()
        mock_context.device = device
        node = _make_node("click", config={"x": 10, "y": 20, "clicks": 3, "interval": 0})
        result = node.execute(mock_context)
        assert result.success
        assert result.data["clicks"] == 3
        assert device.click.call_count == 3

    def test_invalid_clicks_returns_fail(self, mock_context):
        device = MagicMock()
        mock_context.device = device
        node = _make_node("click", config={"x": 10, "y": 20, "clicks": 0})
        result = node.execute(mock_context)
        assert not result.success
        assert "点击次数" in result.error_msg

    def test_device_click_failure_returns_fail(self, mock_context):
        from core.exceptions import DeviceError
        device = MagicMock()
        device.click.side_effect = DeviceError("connection lost")
        mock_context.device = device
        node = _make_node("click", config={"x": 10, "y": 20})
        result = node.execute(mock_context)
        assert not result.success
        assert "设备点击失败" in result.error_msg

    def test_variable_resolution_for_coordinates(self, mock_context):
        device = MagicMock()
        mock_context.device = device
        # 变量解析: ${var_name} 整体作为 key 查找, 查到的 dict 按 axis 取值
        mock_context.variables["prev_pos"] = {"x": 55, "y": 66}
        node = _make_node("click", config={"x": "${prev_pos}", "y": "${prev_pos}"})
        result = node.execute(mock_context)
        assert result.success
        assert result.data["x"] == 55
        assert result.data["y"] == 66
        device.click.assert_called_once_with(55, 66)

    def test_missing_variable_returns_fail(self, mock_context):
        device = MagicMock()
        mock_context.device = device
        node = _make_node("click", config={"x": "${missing_var}", "y": 100})
        result = node.execute(mock_context)
        assert not result.success
        assert "坐标解析失败" in result.error_msg

    def test_context_variable_set_on_success(self, mock_context):
        device = MagicMock()
        mock_context.device = device
        node = _make_node("click", node_id="c1", config={"x": 100, "y": 200})
        node.execute(mock_context)
        assert "c1_click_result" in mock_context.variables
        assert mock_context.variables["c1_click_result"]["x"] == 100


# ============================================================
# WaitNode
# ============================================================

class TestWaitNode:
    def test_fixed_mode_succeeds(self, mock_context):
        node = _make_node("wait", config={"mode": "fixed", "seconds": 0.5})
        result = node.execute(mock_context)
        assert result.success
        assert result.data["mode"] == "fixed"
        assert result.data["seconds"] == 0.5

    def test_unknown_mode_returns_fail(self, mock_context):
        node = _make_node("wait", config={"mode": "unknown_mode"})
        result = node.execute(mock_context)
        assert not result.success
        assert "未知等待模式" in result.error_msg

    def test_default_mode_is_fixed(self, mock_context):
        # 不提供 mode 时应默认走 fixed 分支
        node = _make_node("wait", config={"seconds": 0.1})
        result = node.execute(mock_context)
        assert result.success
        assert result.data["mode"] == "fixed"

    def test_stable_mode_no_device_returns_fail(self, mock_context):
        node = _make_node("wait", config={"mode": "stable", "max_wait": 1.0})
        result = node.execute(mock_context)
        assert not result.success
        assert "no device" in result.error_msg or "device" in result.error_msg

    def test_template_mode_no_device_returns_fail(self, mock_context):
        node = _make_node("wait", config={"mode": "template", "template": "x.png"})
        result = node.execute(mock_context)
        assert not result.success
        assert "no device" in result.error_msg or "device" in result.error_msg

    def test_template_mode_missing_template_returns_fail(self, mock_context):
        device = MagicMock()
        mock_context.device = device
        node = _make_node("wait", config={"mode": "template"})
        result = node.execute(mock_context)
        assert not result.success
        assert "template" in result.error_msg.lower()


# ============================================================
# SwipeNode
# ============================================================

class TestSwipeNode:
    def test_no_device_returns_fail(self, mock_context):
        node = _make_node("swipe", config={"x1": 100, "y1": 200, "x2": 100, "y2": 500})
        result = node.execute(mock_context)
        assert not result.success
        assert "device=None" in result.error_msg or "未设置设备" in result.error_msg

    def test_basic_swipe_succeeds(self, mock_context):
        device = MagicMock()
        mock_context.device = device
        node = _make_node("swipe", config={
            "x1": 100, "y1": 500, "x2": 100, "y2": 200, "duration": 300,
        })
        result = node.execute(mock_context)
        assert result.success
        assert result.data["from"] == {"x": 100, "y": 500}
        assert result.data["to"] == {"x": 100, "y": 200}
        assert result.data["duration"] == 300
        device.swipe.assert_called_once_with(100, 500, 100, 200, duration=300)

    def test_default_duration_is_300(self, mock_context):
        device = MagicMock()
        mock_context.device = device
        node = _make_node("swipe", config={
            "x1": 0, "y1": 0, "x2": 100, "y2": 100,
        })
        result = node.execute(mock_context)
        assert result.success
        assert result.data["duration"] == 300

    def test_device_swipe_failure_returns_fail(self, mock_context):
        from core.exceptions import DeviceError
        device = MagicMock()
        device.swipe.side_effect = DeviceError("swipe failed")
        mock_context.device = device
        node = _make_node("swipe", config={"x1": 0, "y1": 0, "x2": 10, "y2": 10})
        result = node.execute(mock_context)
        assert not result.success
        assert "设备滑动失败" in result.error_msg

    def test_context_variable_set_on_success(self, mock_context):
        device = MagicMock()
        mock_context.device = device
        node = _make_node("swipe", node_id="s1", config={
            "x1": 0, "y1": 0, "x2": 10, "y2": 10,
        })
        node.execute(mock_context)
        assert "s1_swipe_result" in mock_context.variables
        assert mock_context.variables["s1_swipe_result"]["from"]["x"] == 0
