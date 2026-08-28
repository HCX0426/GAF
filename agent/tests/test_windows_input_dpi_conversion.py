"""Tests for DPI coordinate conversion in SendInput/PseudoBackground modes.

Verifies that _click_sendinput converts LOGICAL client coords to PHYSICAL
client coords before calling ClientToScreen, using the _dpi_ratio set via
set_dpi_ratio().

Background: template_match produces LOGICAL coords (via coord_transformer),
but ClientToScreen (called from _click_sendinput) expects PHYSICAL coords
when the agent process is DPI-aware. Without conversion, clicks on HiDPI
displays (e.g. 150% scaling) land at the wrong screen position.
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


class TestDpiRatioSetter:
    """set_dpi_ratio stores and validates the ratio."""

    def test_default_ratio_is_1(self):
        handler = WindowsInputHandler("SendInput")
        assert handler._dpi_ratio == 1.0

    def test_set_valid_ratio(self):
        handler = WindowsInputHandler("SendInput")
        handler.set_dpi_ratio(1.5)
        assert handler._dpi_ratio == 1.5

    def test_set_ratio_1_is_noop(self):
        handler = WindowsInputHandler("SendInput")
        handler.set_dpi_ratio(1.0)
        assert handler._dpi_ratio == 1.0

    def test_set_invalid_ratio_ignored(self):
        handler = WindowsInputHandler("SendInput")
        handler.set_dpi_ratio(1.5)
        handler.set_dpi_ratio(0)  # invalid
        assert handler._dpi_ratio == 1.5  # unchanged

    def test_set_negative_ratio_ignored(self):
        handler = WindowsInputHandler("SendInput")
        handler.set_dpi_ratio(1.5)
        handler.set_dpi_ratio(-1.0)  # invalid
        assert handler._dpi_ratio == 1.5  # unchanged


class TestLogicalToPhysical:
    """_logical_to_physical converts coords using _dpi_ratio."""

    def test_noop_when_ratio_1(self):
        handler = WindowsInputHandler("SendInput")
        assert handler._logical_to_physical(857, 30) == (857, 30)

    def test_converts_with_ratio_1_5(self):
        handler = WindowsInputHandler("SendInput")
        handler.set_dpi_ratio(1.5)
        # 857 * 1.5 = 1285.5 → round to 1286
        # 30 * 1.5 = 45.0 → 45
        assert handler._logical_to_physical(857, 30) == (1286, 45)

    def test_converts_with_ratio_2(self):
        handler = WindowsInputHandler("SendInput")
        handler.set_dpi_ratio(2.0)
        assert handler._logical_to_physical(100, 50) == (200, 100)

    def test_zero_coords(self):
        handler = WindowsInputHandler("SendInput")
        handler.set_dpi_ratio(1.5)
        assert handler._logical_to_physical(0, 0) == (0, 0)


class TestClickSendInputDpiConversion:
    """_click_sendinput must convert logical→physical before ClientToScreen."""

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_click_converts_logical_to_physical_dpi_1_5(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        """With DPI=1.5, logical (857,30) → physical (1286,45) before ClientToScreen."""
        handler = WindowsInputHandler("SendInput")
        handler.set_dpi_ratio(1.5)

        # Mock ClientToScreen: capture the point it receives
        MagicMock()

        def client_to_screen_side_effect(hwnd, point_ref):
            # Read the point values that were passed in
            # point_ref is ctypes.byref(point) — mock returns MagicMock
            # We need to check what _client_to_screen was called with
            return 1

        mock_user32.ClientToScreen.return_value = 1
        mock_user32.GetSystemMetrics.side_effect = [2560, 1600]
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()

        # Patch _client_to_screen to capture the coords
        with patch("platforms.windows.input._client_to_screen") as mock_c2s:
            mock_c2s.return_value = (2211, 510)  # expected screen coords

            handler.click("0x90084", 857, 30, button="left")

            # Verify _client_to_screen was called with PHYSICAL coords
            mock_c2s.assert_called_once()
            call_args = mock_c2s.call_args
            # call_args[0] = positional args: (hwnd, x, y)
            call_args[0][0]
            passed_x = call_args[0][1]
            passed_y = call_args[0][2]
            assert passed_x == 1286, f"Expected physical x=1286, got {passed_x}"
            assert passed_y == 45, f"Expected physical y=45, got {passed_y}"

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_click_no_conversion_when_dpi_1(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        """With DPI=1.0, coords pass through unchanged."""
        handler = WindowsInputHandler("SendInput")
        # Default ratio is 1.0 — no set_dpi_ratio call

        mock_user32.ClientToScreen.return_value = 1
        mock_user32.GetSystemMetrics.side_effect = [1920, 1080]
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()

        with patch("platforms.windows.input._client_to_screen") as mock_c2s:
            mock_c2s.return_value = (100, 200)

            handler.click("0x12345", 857, 30)

            mock_c2s.assert_called_once()
            call_args = mock_c2s.call_args
            passed_x = call_args[0][1]
            passed_y = call_args[0][2]
            assert passed_x == 857, f"Expected x=857 (no conversion), got {passed_x}"
            assert passed_y == 30, f"Expected y=30 (no conversion), got {passed_y}"


class TestPseudoBackgroundDpiConversion:
    """PseudoBackground calls _click_sendinput internally, so DPI conversion
    must also apply in pseudo-background mode."""

    @patch("platforms.windows.input_variants.bring_to_foreground")
    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_pseudo_background_converts_logical_to_physical(
        self, mock_sleep, mock_ctypes, mock_user32, mock_bring_to_fg
    ):
        mock_bring_to_fg.return_value = True
        mock_user32.GetForegroundWindow.side_effect = [0x10001, 0x12345]
        mock_user32.SetForegroundWindow.return_value = 1
        mock_user32.SetCursorPos.return_value = 1
        mock_user32.ClientToScreen.return_value = 1
        mock_user32.GetSystemMetrics.side_effect = [2560, 1600]
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()

        handler = WindowsInputHandler("PseudoBackground")
        handler.set_dpi_ratio(1.5)

        with patch("platforms.windows.input._client_to_screen") as mock_c2s:
            mock_c2s.return_value = (2211, 510)

            handler.click("0x12345", 857, 30)

            mock_c2s.assert_called_once()
            call_args = mock_c2s.call_args
            passed_x = call_args[0][1]
            passed_y = call_args[0][2]
            assert passed_x == 1286, f"Expected physical x=1286, got {passed_x}"
            assert passed_y == 45, f"Expected physical y=45, got {passed_y}"


class TestSwipeSendInputDpiConversion:
    """_swipe_sendinput must also convert logical→physical."""

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_swipe_converts_both_endpoints(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        handler = WindowsInputHandler("SendInput")
        handler.set_dpi_ratio(2.0)

        mock_user32.GetSystemMetrics.side_effect = [2560, 1600]
        mock_user32.SendInput.return_value = 1
        mock_user32.ClientToScreen.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()

        with patch("platforms.windows.input._client_to_screen") as mock_c2s:
            mock_c2s.side_effect = [(200, 100), (400, 200)]

            handler.swipe("0x12345", 100, 50, 200, 100, duration_ms=100)

            # Should be called twice with physical coords
            assert mock_c2s.call_count == 2
            first_call = mock_c2s.call_args_list[0]
            second_call = mock_c2s.call_args_list[1]
            # 100*2=200, 50*2=100
            assert first_call[0][1] == 200
            assert first_call[0][2] == 100
            # 200*2=400, 100*2=200
            assert second_call[0][1] == 400
            assert second_call[0][2] == 200
