"""Tests for Windows input handler PostMessage/SendMessage coordinate handling.

Verifies TD-122 fix: PostMessage/SendMessage click/swipe pack CLIENT-area
coordinates into lParam (per Win32 spec), while scroll (WM_MOUSEWHEEL)
still uses SCREEN coordinates.

Ref: TD-122 (PostMessage/SendMessage coordinate fix)
"""

from unittest.mock import patch

import pytest
from django.test import SimpleTestCase

from device_bridge.platforms.windows.input import (
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MOUSEMOVE,
    WM_MOUSEWHEEL,
    WindowsInputHandler,
)

pytestmark = pytest.mark.unit


class TestPostMessageClickUsesClientCoords(SimpleTestCase):
    """TD-122: _postmessage_click must pack CLIENT coordinates into lParam."""

    def setUp(self):
        self.handler = WindowsInputHandler(method='PostMessage')

    @patch('device_bridge.platforms.windows.input._user32')
    def test_postmessage_click_uses_client_coords(self, mock_user32):
        """lParam must equal (y << 16) | x with NO ClientToScreen call."""
        hwnd = 0x1234
        x, y = 100, 200

        self.handler._postmessage_click(hwnd, x, y, button='left')

        # ClientToScreen must NOT be called by _postmessage_click
        mock_user32.ClientToScreen.assert_not_called()

        # Verify lParam = (200 << 16) | 100 = 0x00C80064
        expected_lparam = (y << 16) | (x & 0xFFFF)
        calls = mock_user32.PostMessageW.call_args_list
        self.assertEqual(len(calls), 2)  # DOWN + UP
        # PostMessageW(hwnd, msg, wparam, lparam) — 4 positional args
        # First call: WM_LBUTTONDOWN, wparam=1, lparam=expected
        hwnd0, down_msg, down_wparam, down_lparam = calls[0].args
        self.assertEqual(hwnd0, hwnd)
        self.assertEqual(down_msg, WM_LBUTTONDOWN)
        self.assertEqual(down_wparam, 1)
        self.assertEqual(down_lparam, expected_lparam)
        # Second call: WM_LBUTTONUP, wparam=0, lparam=expected
        hwnd1, up_msg, up_wparam, up_lparam = calls[1].args
        self.assertEqual(hwnd1, hwnd)
        self.assertEqual(up_msg, WM_LBUTTONUP)
        self.assertEqual(up_wparam, 0)
        self.assertEqual(up_lparam, expected_lparam)


class TestSendMessageClickUsesClientCoords(SimpleTestCase):
    """TD-122: _sendmessage_click must pack CLIENT coordinates into lParam."""

    def setUp(self):
        self.handler = WindowsInputHandler(method='SendMessage')

    @patch('device_bridge.platforms.windows.input._user32')
    def test_sendmessage_click_uses_client_coords(self, mock_user32):
        """lParam must equal (y << 16) | x with NO ClientToScreen call."""
        hwnd = 0x5678
        x, y = 50, 75

        self.handler._sendmessage_click(hwnd, x, y, button='left')

        # ClientToScreen must NOT be called by _sendmessage_click
        mock_user32.ClientToScreen.assert_not_called()

        expected_lparam = (y << 16) | (x & 0xFFFF)
        calls = mock_user32.SendMessageW.call_args_list
        self.assertEqual(len(calls), 2)  # DOWN + UP
        hwnd0, down_msg, down_wparam, down_lparam = calls[0].args
        self.assertEqual(hwnd0, hwnd)
        self.assertEqual(down_msg, WM_LBUTTONDOWN)
        self.assertEqual(down_wparam, 1)
        self.assertEqual(down_lparam, expected_lparam)
        hwnd1, up_msg, up_wparam, up_lparam = calls[1].args
        self.assertEqual(hwnd1, hwnd)
        self.assertEqual(up_msg, WM_LBUTTONUP)
        self.assertEqual(up_wparam, 0)
        self.assertEqual(up_lparam, expected_lparam)


class TestPostMessageSwipeUsesClientCoords(SimpleTestCase):
    """TD-122: _postmessage_swipe must pack CLIENT coordinates into lParam."""

    def setUp(self):
        self.handler = WindowsInputHandler(method='PostMessage')

    @patch('device_bridge.platforms.windows.input._user32')
    def test_postmessage_swipe_uses_client_coords(self, mock_user32):
        """Both start and end lParam must use CLIENT coordinates."""
        hwnd = 0xABCD
        x1, y1 = 10, 20
        x2, y2 = 300, 400

        self.handler._postmessage_swipe(hwnd, x1, y1, x2, y2)

        # ClientToScreen must NOT be called
        mock_user32.ClientToScreen.assert_not_called()

        expected_start = (y1 << 16) | (x1 & 0xFFFF)
        expected_end = (y2 << 16) | (x2 & 0xFFFF)

        calls = mock_user32.PostMessageW.call_args_list
        self.assertEqual(len(calls), 3)  # DOWN + MOVE + UP
        # WM_LBUTTONDOWN with start coords
        hwnd0, msg_down, wparam_down, lparam_down = calls[0].args
        self.assertEqual(hwnd0, hwnd)
        self.assertEqual(msg_down, WM_LBUTTONDOWN)
        self.assertEqual(lparam_down, expected_start)
        # WM_MOUSEMOVE with end coords
        hwnd1, msg_move, wparam_move, lparam_move = calls[1].args
        self.assertEqual(hwnd1, hwnd)
        self.assertEqual(msg_move, WM_MOUSEMOVE)
        self.assertEqual(lparam_move, expected_end)
        # WM_LBUTTONUP with end coords
        hwnd2, msg_up, wparam_up, lparam_up = calls[2].args
        self.assertEqual(hwnd2, hwnd)
        self.assertEqual(msg_up, WM_LBUTTONUP)
        self.assertEqual(lparam_up, expected_end)


class TestSendMessageSwipeUsesClientCoords(SimpleTestCase):
    """TD-122: _sendmessage_swipe must pack CLIENT coordinates into lParam."""

    def setUp(self):
        self.handler = WindowsInputHandler(method='SendMessage')

    @patch('device_bridge.platforms.windows.input._user32')
    def test_sendmessage_swipe_uses_client_coords(self, mock_user32):
        """Both start and end lParam must use CLIENT coordinates."""
        hwnd = 0xBEEF
        x1, y1 = 5, 15
        x2, y2 = 250, 350

        self.handler._sendmessage_swipe(hwnd, x1, y1, x2, y2)

        # ClientToScreen must NOT be called
        mock_user32.ClientToScreen.assert_not_called()

        expected_start = (y1 << 16) | (x1 & 0xFFFF)
        expected_end = (y2 << 16) | (x2 & 0xFFFF)

        calls = mock_user32.SendMessageW.call_args_list
        self.assertEqual(len(calls), 3)  # DOWN + MOVE + UP
        hwnd0, msg_down, _, lparam_down = calls[0].args
        self.assertEqual(hwnd0, hwnd)
        self.assertEqual(msg_down, WM_LBUTTONDOWN)
        self.assertEqual(lparam_down, expected_start)
        hwnd1, msg_move, _, lparam_move = calls[1].args
        self.assertEqual(hwnd1, hwnd)
        self.assertEqual(msg_move, WM_MOUSEMOVE)
        self.assertEqual(lparam_move, expected_end)
        hwnd2, msg_up, _, lparam_up = calls[2].args
        self.assertEqual(hwnd2, hwnd)
        self.assertEqual(msg_up, WM_LBUTTONUP)
        self.assertEqual(lparam_up, expected_end)


class TestPostMessageScrollUsesScreenCoords(SimpleTestCase):
    """TD-122: _postmessage_scroll must STILL convert to screen coords.

    WM_MOUSEWHEEL is the Win32 exception — its lParam expects SCREEN
    coordinates, not client. So _client_to_screen must remain.
    """

    def setUp(self):
        self.handler = WindowsInputHandler(method='PostMessage')

    @patch('device_bridge.platforms.windows.input._user32')
    @patch.object(WindowsInputHandler, '_client_to_screen')
    def test_postmessage_scroll_calls_client_to_screen(
        self, mock_client_to_screen, mock_user32,
    ):
        """_postmessage_scroll must call _client_to_screen (WM_MOUSEWHEEL spec)."""
        hwnd = 0xDEAD
        x, y = 80, 120
        delta = 120

        # Stub _client_to_screen to return fixed screen coords (offset by 1000, 2000)
        screen_x = 1000 + x
        screen_y = 2000 + y
        mock_client_to_screen.return_value = (screen_x, screen_y)

        self.handler._postmessage_scroll(hwnd, x, y, delta)

        # _client_to_screen MUST be called
        mock_client_to_screen.assert_called_once_with(hwnd, x, y)

        # lParam should pack SCREEN coords
        expected_lparam = (screen_y << 16) | (screen_x & 0xFFFF)

        calls = mock_user32.PostMessageW.call_args_list
        self.assertEqual(len(calls), 1)
        hwnd_arg, msg, wparam, lparam = calls[0].args
        self.assertEqual(hwnd_arg, hwnd)
        self.assertEqual(msg, WM_MOUSEWHEEL)
        self.assertEqual(lparam, expected_lparam)



class TestMakeLparamPacking(SimpleTestCase):
    """Verify _make_lparam packs as (y << 16) | (x & 0xFFFF)."""

    def test_make_lparam_packs_y_high_x_low(self):
        self.assertEqual(WindowsInputHandler._make_lparam(0, 0), 0)
        self.assertEqual(WindowsInputHandler._make_lparam(1, 0), 1)
        self.assertEqual(WindowsInputHandler._make_lparam(0, 1), 1 << 16)
        self.assertEqual(WindowsInputHandler._make_lparam(100, 200), (200 << 16) | 100)
        self.assertEqual(
            WindowsInputHandler._make_lparam(0xFFFF, 0xFFFF),
            (0xFFFF << 16) | 0xFFFF,
        )

    def test_make_lparam_x_masked_to_16_bits(self):
        """High bits of X must be masked off (Win32 lParam packs low 16 bits)."""
        # x = 0x10000 (bit 17 set) should be masked to 0
        self.assertEqual(WindowsInputHandler._make_lparam(0x10000, 0), 0)
        # x = 0x12345 should keep only low 16 bits = 0x2345
        self.assertEqual(WindowsInputHandler._make_lparam(0x12345, 0), 0x2345)
