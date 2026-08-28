"""UIAutomation semantic node tests (spec-2026-08-26 P2).

Coverage:
- 6 uia node types registered under expected names
- param validation (missing value/option, invalid direction)
- device/window-requirement failures (no device / no hwnd)
- success + failure paths for uia_session-backed execution
- context variable write-back on success

Uses MagicMock for PipelineContext/device and patches
platforms.windows.uia.uia_session — no real UIA/Windows interaction.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Import to register nodes.
import engine.nodes.uia_control  # noqa: F401
from engine.node import PIPELINE_NODE_REGISTRY

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_context():
    """Build a mock PipelineContext with variables dict."""
    ctx = MagicMock()
    ctx.variables = {}
    ctx.device = None
    ctx.debug_mode = False
    ctx.coord_system = "legacy"

    def set_var(key, value):
        ctx.variables[key] = value

    ctx.set_variable.side_effect = set_var
    return ctx


def _make_node(node_type, node_id="uia_node", config=None):
    return PIPELINE_NODE_REGISTRY[node_type].from_dict({
        "id": node_id,
        "node_type": node_type,
        "config": config or {},
    })


def _windows_device(hwnd=0x12345):
    dev = MagicMock()
    dev._window_mgr = None
    dev._hwnd = hwnd
    return dev


# ============================================================
# Registration
# ============================================================

class TestUiaRegistration:
    def test_all_six_uia_nodes_registered(self):
        for node_type in (
            "uia_set_value", "uia_invoke", "uia_get_state",
            "uia_get_window_title", "uia_select", "uia_scroll",
        ):
            assert node_type in PIPELINE_NODE_REGISTRY, f"{node_type} missing"


# ============================================================
# uia_set_value
# ============================================================

class TestUiaSetValueNode:
    def test_missing_value_returns_fail(self, mock_context):
        node = _make_node("uia_set_value", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "'value' config required" in result.error_msg

    def test_no_device_returns_fail(self, mock_context):
        mock_context.device = None
        node = _make_node("uia_set_value", config={"value": "hello"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "no device" in result.error_msg

    @patch("platforms.windows.uia.uia_session.set_value", return_value=True)
    def test_success_calls_session_and_writes_var(self, mock_set_value, mock_context):
        mock_context.device = _windows_device()
        node = _make_node("uia_set_value", config={
            "value": "www.baidu.com", "control_name": "地址栏",
        })
        result = node.execute(mock_context)
        assert result.success is True
        mock_set_value.assert_called_once_with(
            0x12345, "www.baidu.com",
            name="地址栏", automation_id=None, timeout=3.0,
        )
        assert mock_context.variables["uia_node_uia_value"] == {
            "value": "www.baidu.com", "ok": True,
        }

    @patch("platforms.windows.uia.uia_session.set_value", return_value=False)
    def test_session_false_returns_fail(self, mock_set_value, mock_context):
        mock_context.device = _windows_device()
        node = _make_node("uia_set_value", config={"value": "v"})
        result = node.execute(mock_context)
        assert result.success is False


# ============================================================
# uia_invoke
# ============================================================

class TestUiaInvokeNode:
    def test_no_device_returns_fail(self, mock_context):
        node = _make_node("uia_invoke", config={})
        result = node.execute(mock_context)
        assert result.success is False

    @patch("platforms.windows.uia.uia_session.invoke", return_value=True)
    def test_success_calls_session(self, mock_invoke, mock_context):
        mock_context.device = _windows_device()
        node = _make_node("uia_invoke", config={"control_automation_id": "btn"})
        result = node.execute(mock_context)
        assert result.success is True
        mock_invoke.assert_called_once_with(
            0x12345, name=None, automation_id="btn", timeout=3.0,
        )

    @patch("platforms.windows.uia.uia_session.invoke", return_value=False)
    def test_session_false_returns_fail(self, mock_invoke, mock_context):
        mock_context.device = _windows_device()
        node = _make_node("uia_invoke", config={})
        result = node.execute(mock_context)
        assert result.success is False


# ============================================================
# uia_select
# ============================================================

class TestUiaSelectNode:
    def test_missing_option_returns_fail(self, mock_context):
        node = _make_node("uia_select", config={})
        result = node.execute(mock_context)
        assert result.success is False
        assert "'option' config required" in result.error_msg

    @patch("platforms.windows.uia.uia_session.select_option", return_value=True)
    def test_success_calls_session_and_writes_var(self, mock_select, mock_context):
        mock_context.device = _windows_device()
        node = _make_node("uia_select", config={"option": "百度"})
        result = node.execute(mock_context)
        assert result.success is True
        mock_select.assert_called_once_with(
            0x12345, "百度",
            name=None, automation_id=None, timeout=3.0, exact=True,
        )
        assert mock_context.variables["uia_node_uia_select"] == {
            "option": "百度", "ok": True,
        }

    @patch("platforms.windows.uia.uia_session.select_option", return_value=False)
    def test_option_not_found_returns_fail(self, mock_select, mock_context):
        mock_context.device = _windows_device()
        node = _make_node("uia_select", config={"option": "不存在的选项"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "not selectable" in result.error_msg


# ============================================================
# uia_scroll
# ============================================================

class TestUiaScrollNode:
    def test_invalid_direction_returns_fail(self, mock_context):
        node = _make_node("uia_scroll", config={"direction": "diagonal"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "direction" in result.error_msg

    @patch("platforms.windows.uia.uia_session.scroll", return_value=True)
    def test_success_calls_session(self, mock_scroll, mock_context):
        mock_context.device = _windows_device()
        node = _make_node("uia_scroll", config={"direction": "down", "amount": "large"})
        result = node.execute(mock_context)
        assert result.success is True
        mock_scroll.assert_called_once_with(
            0x12345, "down",
            amount="large", name=None, automation_id=None,
            control_type="document", timeout=3.0,
        )

    @patch("platforms.windows.uia.uia_session.scroll", return_value=False)
    def test_session_false_returns_fail(self, mock_scroll, mock_context):
        mock_context.device = _windows_device()
        node = _make_node("uia_scroll", config={"direction": "up"})
        result = node.execute(mock_context)
        assert result.success is False
        assert "not scrollable" in result.error_msg


# ============================================================
# uia_get_state
# ============================================================

class TestUiaGetStateNode:
    @patch("platforms.windows.uia.uia_session.get_state",
           return_value={"found": True, "value": "baidu.com"})
    def test_success_writes_verification_var(self, mock_get_state, mock_context):
        mock_context.device = _windows_device()
        node = _make_node("uia_get_state", config={"var": "addr_state"})
        result = node.execute(mock_context)
        assert result.success is True
        assert mock_context.variables["addr_state"] == {
            "found": True, "value": "baidu.com",
        }
        assert result.data["var"] == "addr_state"


# ============================================================
# uia_get_window_title
# ============================================================

class TestUiaGetWindowTitleNode:
    @patch("platforms.windows.uia.uia_session.get_active_window_title",
           return_value="百度一下，你就知道 - Google Chrome")
    def test_success_writes_title_var(self, mock_title, mock_context):
        node = _make_node("uia_get_window_title", config={})
        result = node.execute(mock_context)
        assert result.success is True
        assert mock_context.variables["uia_node_window_title"]["title"] == (
            "百度一下，你就知道 - Google Chrome"
        )
