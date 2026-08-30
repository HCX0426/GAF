"""Tests for WindowsInputHandler pseudo-background mode.

Covers:
- Method setter accepts "PseudoBackground".
- click() / key_press() dispatch to pseudo-background helpers.
- _click_pseudo_background saves/restores foreground window and cursor position.
- _key_press_pseudo_background saves/restores foreground window and cursor position.
- Restore happens even when the inner SendInput operation raises.
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


class TestPseudoBackgroundMethodSetter:
    """WindowsInputHandler.method must accept PseudoBackground."""

    def test_method_setter_accepts_pseudo_background(self):
        handler = WindowsInputHandler("SendInput")
        handler.method = "PseudoBackground"
        assert handler.method == "PseudoBackground"

    def test_method_setter_rejects_unknown_value(self):
        handler = WindowsInputHandler("SendInput")
        handler.method = "UnknownMethod"
        assert handler.method == "SendInput"


class TestClickPseudoBackground:
    """_click_pseudo_background save/restore behavior."""

    @patch("platforms.windows.input_variants.bring_to_foreground")
    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_click_saves_and_restores_foreground_and_cursor(
        self, mock_sleep, mock_ctypes, mock_user32, mock_bring_to_fg
    ):
        # bring_to_foreground succeeds (uses AttachThreadInput internally)
        mock_bring_to_fg.return_value = True
        # Simulate current foreground is some other window, target becomes foreground.
        mock_user32.GetForegroundWindow.side_effect = [0x10001, 0x12345]
        mock_user32.SetForegroundWindow.return_value = 1
        mock_user32.SetCursorPos.return_value = 1
        mock_user32.ClientToScreen.return_value = 1
        mock_user32.GetSystemMetrics.side_effect = [1920, 1080]
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()
        point_mock = MagicMock()
        mock_ctypes.wintypes.POINT.return_value = point_mock
        point_mock.x = 100
        point_mock.y = 200

        handler = WindowsInputHandler("PseudoBackground")
        result = handler.click("0x12345", 10, 20, button="left")

        assert result.success is True
        # bring_to_foreground called with target hwnd (replaces direct SetForegroundWindow)
        mock_bring_to_fg.assert_called_once_with(0x12345, log=True)
        # Foreground saved once (prev_hwnd) and checked once (current_hwnd before restore).
        assert mock_user32.GetForegroundWindow.call_count == 2
        # Restore: SetForegroundWindow called with prev_hwnd (0x10001).
        mock_user32.SetForegroundWindow.assert_any_call(0x10001)
        # Cursor saved once and restored.
        mock_user32.GetCursorPos.assert_called_once()
        mock_user32.SetCursorPos.assert_any_call(100, 200)

    @patch("platforms.windows.input_variants.bring_to_foreground")
    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_click_restores_on_exception(
        self, mock_sleep, mock_ctypes, mock_user32, mock_bring_to_fg
    ):
        # Inner SendInput raises; restore must still happen.
        mock_bring_to_fg.return_value = True
        mock_user32.GetForegroundWindow.side_effect = [0x10001, 0x12345]
        mock_user32.SetForegroundWindow.return_value = 1
        mock_user32.SetCursorPos.return_value = 1
        mock_user32.SendInput.side_effect = RuntimeError("SendInput failed")
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()
        point_mock = MagicMock()
        mock_ctypes.wintypes.POINT.return_value = point_mock
        point_mock.x = 50
        point_mock.y = 60

        handler = WindowsInputHandler("PseudoBackground")
        result = handler.click("0x12345", 10, 20)

        assert result.success is False
        assert "SendInput failed" in result.error_msg
        # Restore attempted.
        mock_user32.SetForegroundWindow.assert_any_call(0x10001)
        mock_user32.SetCursorPos.assert_any_call(50, 60)

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_click_invalid_target_returns_fail(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        handler = WindowsInputHandler("PseudoBackground")
        result = handler.click("0", 10, 20)

        assert result.success is False
        assert "Invalid target hwnd" in result.error_msg


class TestKeyPressPseudoBackground:
    """_key_press_pseudo_background save/restore behavior."""

    @patch("platforms.windows.input_variants.bring_to_foreground")
    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_key_press_saves_and_restores_foreground_and_cursor(
        self, mock_sleep, mock_ctypes, mock_user32, mock_bring_to_fg
    ):
        # bring_to_foreground succeeds (uses AttachThreadInput internally)
        mock_bring_to_fg.return_value = True
        mock_user32.GetForegroundWindow.side_effect = [0x10001, 0x12345]
        mock_user32.SetForegroundWindow.return_value = 1
        mock_user32.SetCursorPos.return_value = 1
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()
        point_mock = MagicMock()
        mock_ctypes.wintypes.POINT.return_value = point_mock
        point_mock.x = 30
        point_mock.y = 40

        handler = WindowsInputHandler("PseudoBackground")
        result = handler.key_press("0x12345", "enter")

        assert result.success is True
        assert result.data["key"] == "enter"
        assert result.data["vk"] == 0x0D
        # TD-396/589ca82c: 前台切换改走 bring_to_foreground (AttachThreadInput 技巧)
        mock_bring_to_fg.assert_called_once_with(0x12345, log=True)
        mock_user32.SetForegroundWindow.assert_any_call(0x10001)
        mock_user32.SetCursorPos.assert_any_call(30, 40)

    @patch("platforms.windows.input_variants.bring_to_foreground")
    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_key_press_restores_on_exception(
        self, mock_sleep, mock_ctypes, mock_user32, mock_bring_to_fg
    ):
        mock_bring_to_fg.return_value = True
        mock_user32.GetForegroundWindow.side_effect = [0x10001, 0x12345]
        mock_user32.SetForegroundWindow.return_value = 1
        mock_user32.SetCursorPos.return_value = 1
        mock_user32.SendInput.side_effect = RuntimeError("SendInput failed")
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()
        point_mock = MagicMock()
        mock_ctypes.wintypes.POINT.return_value = point_mock
        point_mock.x = 70
        point_mock.y = 80

        handler = WindowsInputHandler("PseudoBackground")
        result = handler.key_press("0x12345", "a")

        assert result.success is False
        mock_user32.SetForegroundWindow.assert_any_call(0x10001)
        mock_user32.SetCursorPos.assert_any_call(70, 80)

    @patch("platforms.windows.input.user32")
    def test_key_press_invalid_target_returns_fail(self, mock_user32):
        handler = WindowsInputHandler("PseudoBackground")
        result = handler.key_press("0", "enter")

        assert result.success is False
        assert "Invalid target hwnd" in result.error_msg


class TestTextInputPseudoBackground:
    """_text_input_pseudo_background save/restore behavior."""

    @patch("platforms.windows.input_variants.bring_to_foreground")
    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_text_input_saves_and_restores_foreground_and_cursor(
        self, mock_sleep, mock_ctypes, mock_user32, mock_bring_to_fg
    ):
        # bring_to_foreground succeeds (uses AttachThreadInput internally)
        mock_bring_to_fg.return_value = True
        mock_user32.GetForegroundWindow.side_effect = [0x10001, 0x12345]
        mock_user32.SetForegroundWindow.return_value = 1
        mock_user32.SetCursorPos.return_value = 1
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()
        point_mock = MagicMock()
        mock_ctypes.wintypes.POINT.return_value = point_mock
        point_mock.x = 90
        point_mock.y = 100

        handler = WindowsInputHandler("PseudoBackground")
        result = handler.text_input("0x12345", "hi")

        assert result.success is True
        assert result.data["chars_sent"] == 2
        # TD-396/589ca82c: 前台切换改走 bring_to_foreground (AttachThreadInput 技巧)
        mock_bring_to_fg.assert_called_once_with(0x12345, log=True)
        mock_user32.SetForegroundWindow.assert_any_call(0x10001)
        mock_user32.SetCursorPos.assert_any_call(90, 100)


class TestClickDispatch:
    """click() must dispatch based on method property and override."""

    @patch("platforms.windows.input_variants.bring_to_foreground")
    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_click_dispatch_pseudo_background_by_method(
        self, mock_sleep, mock_ctypes, mock_user32, mock_bring_to_fg
    ):
        # bring_to_foreground succeeds (uses AttachThreadInput internally)
        mock_bring_to_fg.return_value = True
        mock_user32.GetForegroundWindow.side_effect = [0x10001, 0x12345]
        mock_user32.SetForegroundWindow.return_value = 1
        mock_user32.SetCursorPos.return_value = 1
        mock_user32.ClientToScreen.return_value = 1
        mock_user32.GetSystemMetrics.side_effect = [1920, 1080]
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()
        point_mock = MagicMock()
        mock_ctypes.wintypes.POINT.return_value = point_mock
        point_mock.x = 0
        point_mock.y = 0

        handler = WindowsInputHandler("SendInput")
        result = handler.click("0x12345", 5, 5, method="PseudoBackground")

        assert result.success is True
        # bring_to_foreground called with target hwnd (replaces direct SetForegroundWindow)
        mock_bring_to_fg.assert_called_once_with(0x12345, log=True)


class TestKeyPressDispatch:
    """key_press() must dispatch based on method property and override."""

    @patch("platforms.windows.input_variants.bring_to_foreground")
    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_key_press_dispatch_pseudo_background_by_method(
        self, mock_sleep, mock_ctypes, mock_user32, mock_bring_to_fg
    ):
        mock_bring_to_fg.return_value = True
        mock_user32.GetForegroundWindow.side_effect = [0x10001, 0x12345]
        mock_user32.SetForegroundWindow.return_value = 1
        mock_user32.SetCursorPos.return_value = 1
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()
        point_mock = MagicMock()
        mock_ctypes.wintypes.POINT.return_value = point_mock
        point_mock.x = 0
        point_mock.y = 0

        handler = WindowsInputHandler("SendInput")
        result = handler.key_press("0x12345", "space", method="PseudoBackground")

        assert result.success is True
        mock_bring_to_fg.assert_called_once_with(0x12345, log=True)
