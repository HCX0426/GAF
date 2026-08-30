"""E1 (spec 2026-07-30-debug-directory-restructure) — 转换⑤ ClientToScreen trace.

验证 ``_click_sendinput`` 和 ``_swipe_sendinput`` 在调用 ``_client_to_screen``
后, 通过 ``_emit_coord_trace_safe(step="client_to_screen", ...)`` 记 trace,
让 AI 调试时能看到 physical → screen 的窗口原点偏移转换链路.

Background: 转换④ ``_logical_to_physical`` 已在 N191 修复时补 trace, 但
转换⑤ ``ClientToScreen`` (physical → screen) 仍是黑盒. 当窗口不在屏幕左上角
时, screen 坐标 = physical + 窗口原点偏移, 此偏移量无 trace → AI 调试时
无法从日志反推实际传给 SendInput 的屏幕绝对坐标.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from platforms.windows.input import WindowsInputHandler

pytestmark = pytest.mark.unit


class TestClickSendInputClientToScreenTrace:
    """_click_sendinput 调用 _client_to_screen 后必须记 trace."""

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_click_emits_client_to_screen_trace(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        """click 调用后, coord_trace_callback 应被以 step=client_to_screen 调用."""
        handler = WindowsInputHandler("SendInput")
        handler.set_dpi_ratio(1.5)

        # 设置 trace callback 捕获调用
        trace_calls: list[dict] = []
        handler.set_coord_trace_callback(
            lambda **kwargs: trace_calls.append(kwargs)
        )

        mock_user32.GetSystemMetrics.side_effect = [2560, 1600]
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()

        # Mock _client_to_screen: physical (1286, 45) → screen (2211, 510)
        with patch("platforms.windows.input._client_to_screen") as mock_c2s:
            mock_c2s.return_value = (2211, 510)

            handler.click("0x90084", 857, 30, button="left")

            # 验证 _client_to_screen 被调用
            mock_c2s.assert_called_once()

        # 验证至少有 logical_to_physical 和 client_to_screen 两种 trace
        step_values = [c["step"] for c in trace_calls]
        assert "logical_to_physical" in step_values, (
            f"Expected logical_to_physical trace, got steps: {step_values}"
        )
        assert "client_to_screen" in step_values, (
            f"Expected client_to_screen trace, got steps: {step_values}"
        )

        # 验证 client_to_screen trace 的字段
        c2s_call = next(c for c in trace_calls if c["step"] == "client_to_screen")
        # raw = physical coords (input to ClientToScreen)
        assert c2s_call["raw"] == (1286, 45), (
            f"Expected raw=(1286, 45) physical, got {c2s_call['raw']}"
        )
        # converted = screen coords (output of ClientToScreen)
        assert c2s_call["converted"] == (2211, 510), (
            f"Expected converted=(2211, 510) screen, got {c2s_call['converted']}"
        )
        # coord_system_in/out
        assert c2s_call["coord_system_in"] == "physical"
        assert c2s_call["coord_system_out"] == "screen"
        # formula 包含 ClientToScreen 关键字
        assert "ClientToScreen" in c2s_call["formula"], (
            f"Expected formula to mention ClientToScreen, got: {c2s_call['formula']}"
        )
        # extra 包含 hwnd
        assert "hwnd" in c2s_call.get("extra", {}), (
            f"Expected extra.hwnd, got extra: {c2s_call.get('extra')}"
        )

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_click_no_trace_when_callback_not_set(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        """无 callback 时 click 不应报错 (best-effort)."""
        handler = WindowsInputHandler("SendInput")
        # 不调 set_coord_trace_callback — _coord_trace_callback 为 None

        mock_user32.GetSystemMetrics.side_effect = [1920, 1080]
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()

        with patch("platforms.windows.input._client_to_screen") as mock_c2s:
            mock_c2s.return_value = (100, 200)

            # 不应抛异常
            result = handler.click("0x12345", 100, 50)
            assert result.success


class TestSwipeSendInputClientToScreenTrace:
    """_swipe_sendinput 调用 _client_to_screen (两次: start+end) 后必须记 trace."""

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_swipe_emits_two_client_to_screen_traces(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        """swipe 有 start + end 两个端点, 应记两次 client_to_screen trace."""
        handler = WindowsInputHandler("SendInput")
        handler.set_dpi_ratio(2.0)

        trace_calls: list[dict] = []
        handler.set_coord_trace_callback(
            lambda **kwargs: trace_calls.append(kwargs)
        )

        mock_user32.GetSystemMetrics.side_effect = [2560, 1600]
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()

        # Mock _client_to_screen: 两次调用返回不同 screen 坐标
        # physical start (200, 100) → screen (300, 150)
        # physical end (400, 200) → screen (500, 250)
        with patch("platforms.windows.input._client_to_screen") as mock_c2s:
            mock_c2s.side_effect = [(300, 150), (500, 250)]

            handler.swipe("0x12345", 100, 50, 200, 100, duration_ms=100)

            assert mock_c2s.call_count == 2

        # 验证有两次 client_to_screen trace
        c2s_calls = [c for c in trace_calls if c["step"] == "client_to_screen"]
        assert len(c2s_calls) == 2, (
            f"Expected 2 client_to_screen traces (start+end), got {len(c2s_calls)}: "
            f"{[c['step'] for c in trace_calls]}"
        )

        # 第一次: start point
        assert c2s_calls[0]["raw"] == (200, 100), (
            f"Expected start raw=(200, 100), got {c2s_calls[0]['raw']}"
        )
        assert c2s_calls[0]["converted"] == (300, 150), (
            f"Expected start converted=(300, 150), got {c2s_calls[0]['converted']}"
        )

        # 第二次: end point
        assert c2s_calls[1]["raw"] == (400, 200), (
            f"Expected end raw=(400, 200), got {c2s_calls[1]['raw']}"
        )
        assert c2s_calls[1]["converted"] == (500, 250), (
            f"Expected end converted=(500, 250), got {c2s_calls[1]['converted']}"
        )

        # 两次都应是 physical → screen
        for call in c2s_calls:
            assert call["coord_system_in"] == "physical"
            assert call["coord_system_out"] == "screen"


class TestClientToScreenTraceFields:
    """client_to_screen trace 的字段完整性检查."""

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_trace_includes_window_offset_in_extra(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        """extra 字段应包含 window_offset (screen - physical 差值)."""
        handler = WindowsInputHandler("SendInput")
        handler.set_dpi_ratio(1.0)  # no conversion, raw == physical

        trace_calls: list[dict] = []
        handler.set_coord_trace_callback(
            lambda **kwargs: trace_calls.append(kwargs)
        )

        mock_user32.GetSystemMetrics.side_effect = [1920, 1080]
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()

        # physical (100, 50) → screen (340, 150) → window_offset = (240, 100)
        with patch("platforms.windows.input._client_to_screen") as mock_c2s:
            mock_c2s.return_value = (340, 150)

            handler.click("0x12345", 100, 50)

        c2s_calls = [c for c in trace_calls if c["step"] == "client_to_screen"]
        assert len(c2s_calls) == 1
        call = c2s_calls[0]

        extra = call.get("extra", {})
        assert "window_offset" in extra, (
            f"Expected extra.window_offset, got extra: {extra}"
        )
        # window_offset = screen - physical = (340-100, 150-50) = (240, 100)
        assert extra["window_offset"] == (240, 100), (
            f"Expected window_offset=(240, 100), got {extra['window_offset']}"
        )
