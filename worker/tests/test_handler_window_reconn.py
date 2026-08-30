"""Regression tests for browser window re-binding (user 2026-08-27).

Browsers change title per page and get a NEW hwnd on every restart; a cached
WindowsDevice handle can outlive its window. Cover:

1. ``_ensure_device_connected`` forces a reconnect when the cached hwnd is
   stale (is_window == False), even if the device claims CONNECTED.
2. A fresh hwnd on a CONNECTED device is left untouched (no reconnect).
3. Non-window devices (emulators, no window_mgr) skip the hwnd check.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # noqa: E402

import pytest  # noqa: E402
from client.handler import MessageHandler  # noqa: E402

pytestmark = pytest.mark.unit


class TestEnsureDeviceConnectedReconnect:
    """_ensure_device_connected stale-hwnd re-connect behaviour."""

    @staticmethod
    def _window_device(status, hwnd):
        dev = MagicMock()
        dev._window_mgr = MagicMock()
        dev._window_mgr.hwnd = hwnd
        dev.status = status
        dev.device_id = "windows-hwnd-test"
        return dev

    def test_stale_hwnd_forces_reconnect(self):
        """is_window(stale) == False → disconnect + reconnect even if CONNECTED."""
        from devices.base import DeviceStatus

        dev = self._window_device(DeviceStatus.CONNECTED, 0x123)
        dev.disconnect.side_effect = lambda: setattr(dev, "status", DeviceStatus.DISCONNECTED)
        with patch("platforms.windows.window.is_window", return_value=False):
            MessageHandler._ensure_device_connected(dev)
        dev.disconnect.assert_called_once()
        dev.connect.assert_called_once()

    def test_fresh_hwnd_connected_no_reconnect(self):
        """is_window(valid) == True + CONNECTED → no disconnect, no reconnect."""
        from devices.base import DeviceStatus

        dev = self._window_device(DeviceStatus.CONNECTED, 0x456)
        with patch("platforms.windows.window.is_window", return_value=True):
            MessageHandler._ensure_device_connected(dev)
        dev.disconnect.assert_not_called()
        dev.connect.assert_not_called()

    def test_disconnected_with_valid_hwnd_connects(self):
        """VALID hwnd but DISCONNECTED → connect once, no disconnect."""
        from devices.base import DeviceStatus

        dev = self._window_device(DeviceStatus.DISCONNECTED, 0x789)
        with patch("platforms.windows.window.is_window", return_value=True):
            MessageHandler._ensure_device_connected(dev)
        dev.disconnect.assert_not_called()
        dev.connect.assert_called_once()

    def test_emulator_device_skips_hwnd_check(self):
        """Device without _window_mgr (emulator) never touches is_window."""
        from devices.base import DeviceStatus

        dev = MagicMock()
        dev._window_mgr = None  # no window manager — emulator/proxy device
        dev.status = DeviceStatus.IDLE
        dev.device_id = "emulator-test"
        MessageHandler._ensure_device_connected(dev)
        dev.disconnect.assert_not_called()
        dev.connect.assert_not_called()


class TestResolveTargetDeviceTitleRefresh:
    """Matched existing device picks up the freshest window_title."""

    def test_refreshes_cached_title_from_device_info(self):
        handler = MessageHandler(MagicMock())
        handler._orchestrator = MagicMock()
        mgr = MagicMock()
        handler._orchestrator._device_manager = mgr
        dev = MagicMock()
        dev._window_title = "旧页面 - Google Chrome"
        dev.name = "Chrome-Browser"
        mgr._devices = {"windows-title-x": dev}

        device_info = {
            "id": 2,
            "name": "Chrome-Browser",
            "device_type": "windows",
            "window_title": "搜索 - Microsoft 必应 - Google Chrome",
            "window_handle": "",
            "screenshot_method": "auto",
            "input_method": "auto",
            "control_mode": "pseudo_background",
        }
        with patch("client.handler.MessageHandler._ensure_device_connected") as mock_ensure:
            resolved = handler._resolve_target_device(device_info)

        assert resolved is not None
        assert dev._window_title == "搜索 - Microsoft 必应 - Google Chrome"
        mock_ensure.assert_called_once_with(dev)
