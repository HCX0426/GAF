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


class TestParseHwnd:
    """_parse_hwnd handles decimal / hex / int / invalid inputs."""

    def test_decimal_string(self):
        from client.handler import _parse_hwnd

        assert _parse_hwnd("4785844") == 4785844

    def test_hex_string(self):
        from client.handler import _parse_hwnd

        assert _parse_hwnd("0x490b4") == 0x490B4

    def test_int_passthrough(self):
        from client.handler import _parse_hwnd

        assert _parse_hwnd(0x490B4) == 0x490B4

    def test_empty_and_invalid(self):
        from client.handler import _parse_hwnd

        assert _parse_hwnd("") is None
        assert _parse_hwnd(None) is None
        assert _parse_hwnd("abc") is None
        assert _parse_hwnd("0") is None


class TestResolveNewDeviceBindsHwndHint:
    """A freshly created WindowsDevice receives the backend hwnd hint so
    connect() can bind it directly instead of searching a drifted title."""

    @staticmethod
    def _handler_with_empty_mgr():
        handler = MessageHandler(MagicMock())
        handler._orchestrator = MagicMock()
        mgr = MagicMock()
        mgr._devices = {}
        handler._orchestrator._device_manager = mgr
        return handler, mgr

    def test_new_device_receives_parsed_window_handle(self):
        handler, mgr = self._handler_with_empty_mgr()
        device_info = {
            "device_type": "windows",
            "name": "Chrome-Browser",
            "window_title": "about:blank - Google Chrome",
            "window_handle": "4785844",
            "screenshot_method": "auto",
            "input_method": "auto",
            "control_mode": "pseudo_background",
        }
        with patch("client.handler.MessageHandler._ensure_device_connected") as mock_ensure, \
                patch("platforms.windows.device.WindowsDevice") as mock_cls:
            handler._resolve_target_device(device_info)

        kwargs = mock_cls.call_args.kwargs
        assert kwargs["window_handle"] == 4785844
        assert mock_ensure.called

    def test_new_device_hex_handle_normalized(self):
        handler, mgr = self._handler_with_empty_mgr()
        device_info = {
            "device_type": "windows",
            "name": "Chrome-Browser",
            "window_title": "about:blank - Google Chrome",
            "window_handle": "0x490b4",
            "screenshot_method": "auto",
            "input_method": "auto",
            "control_mode": "pseudo_background",
        }
        with patch("client.handler.MessageHandler._ensure_device_connected"), \
                patch("platforms.windows.device.WindowsDevice") as mock_cls:
            handler._resolve_target_device(device_info)

        assert mock_cls.call_args.kwargs["window_handle"] == 0x490B4

    def test_existing_device_matched_by_decimal_hwnd(self):
        """hex-bound device matches a backend decimal hwnd string (format drift)."""
        handler, mgr = self._handler_with_empty_mgr()
        dev = MagicMock()
        dev._window_title = "some other title"  # title mismatch on purpose
        dev.name = "Chrome-Browser"
        dev._window_mgr = MagicMock()
        dev._window_mgr.hwnd = 0x4906B4  # 4785844 in hex (matches the log id)
        mgr._devices = {"windows-hwnd-x": dev}

        device_info = {
            "device_type": "windows",
            "name": "Not-Matching",
            "window_title": "another title",
            "window_handle": "4785844",
            "screenshot_method": "auto",
            "input_method": "auto",
            "control_mode": "pseudo_background",
        }
        with patch("client.handler.MessageHandler._ensure_device_connected") as mock_ensure:
            resolved = handler._resolve_target_device(device_info)

        assert resolved is dev
        mock_ensure.assert_called_once_with(dev)


class TestWindowsDeviceConnectBindsHwndHint:
    """WindowsDevice.connect() binds a valid backend hwnd hint directly,
    surviving window title drift (browser page navigation) that breaks title
    search and leaves the device unbound (uia: no window handle)."""

    @staticmethod
    def _make_device(window_handle=None, window_title="about:blank - Google Chrome"):
        from platforms.windows.device import WindowsDevice

        return WindowsDevice(
            device_id="windows-hwnd-test",
            name="Chrome-Browser",
            window_title=window_title,
            window_handle=window_handle,
        )

    def test_valid_hwnd_binds_directly_no_title_search(self):
        from devices.base import DeviceStatus

        dev = self._make_device(window_handle=0x490B4)
        with patch("platforms.windows.window.is_window", return_value=True) as mock_valid, \
                patch.object(dev, "_bind_hwnd") as mock_bind:
            dev.connect()

        mock_valid.assert_called_once_with(0x490B4)
        mock_bind.assert_called_once_with(0x490B4)
        # Real set_hwnd ran: the WindowManager is bound to the hint.
        assert dev._window_mgr.hwnd == 0x490B4
        assert dev.status == DeviceStatus.CONNECTED

    def test_invalid_hwnd_falls_back_to_title_search(self):
        from devices.base import DeviceStatus

        dev = self._make_device(window_handle=0x490B4)
        with patch("platforms.windows.window.is_window", return_value=False) as mock_valid, \
                patch.object(dev._window_mgr, "find_window", return_value=0x123) as mock_find:
            dev.connect()

        mock_valid.assert_called_once_with(0x490B4)
        mock_find.assert_called_once_with(title="about:blank - Google Chrome")
        assert dev.status == DeviceStatus.CONNECTED

    def test_no_hint_uses_title_search(self):
        from devices.base import DeviceStatus

        dev = self._make_device(window_handle=None)
        with patch.object(dev._window_mgr, "find_window", return_value=0x123) as mock_find, \
                patch.object(dev, "_bind_hwnd") as mock_bind:
            dev.connect()

        mock_find.assert_called_once_with(title="about:blank - Google Chrome")
        mock_bind.assert_called_once_with(0x123)
        assert dev.status == DeviceStatus.CONNECTED


class TestResolveEmulatorSerialAlias:
    """模拟器 adb_serial 别名匹配 (2026-09-05).

    backend DB 存 ldconsole 视角 (emulator-5554), agent ADBDevice 用 adb 视角
    (127.0.0.1:5555) 且属性是 _serial (旧代码查 _adb_serial 永不命中) —
    修复后按 adb 视角归一化匹配, 不再 fallback 到未连接的活跃设备.
    """

    def test_normalize_emulator_view_to_adb_view(self):
        from client.handler import MessageHandler

        assert MessageHandler._normalize_serial("emulator-5554") == "127.0.0.1:5555"
        assert MessageHandler._normalize_serial("127.0.0.1:5555") == "127.0.0.1:5555"
        assert MessageHandler._normalize_serial("emulator-5554-extra") == "emulator-5554-extra"
        assert MessageHandler._normalize_serial("") == ""

    def test_device_serial_reads_serial_or_adb_serial(self):
        from client.handler import MessageHandler

        d1 = MagicMock()
        d1._serial = "127.0.0.1:5555"
        assert MessageHandler._device_serial(d1) == "127.0.0.1:5555"

        d2 = MagicMock()
        d2._serial = None
        d2._adb_serial = "legacy-serial"
        assert MessageHandler._device_serial(d2) == "legacy-serial"

        d3 = MagicMock()
        d3._serial = None
        d3._adb_serial = None
        assert MessageHandler._device_serial(d3) == ""

    def test_resolve_emulator_device_matches_alias(self):
        from client.handler import MessageHandler

        handler = MessageHandler(MagicMock())
        handler._orchestrator = MagicMock()
        mgr = MagicMock()
        handler._orchestrator._device_manager = mgr
        dev = MagicMock()
        dev._serial = "127.0.0.1:5555"
        dev.device_id = "adb-ldplayer-1"
        mgr._devices = {"adb-ldplayer-1": dev}

        device_info = {"device_type": "emulator", "adb_serial": "emulator-5554"}
        with patch("client.handler.MessageHandler._ensure_device_connected") as mock_ensure:
            resolved = handler._resolve_target_device(device_info)

        assert resolved is dev
        mock_ensure.assert_called_once_with(dev)

    def test_resolve_emulator_device_no_match_falls_back(self):
        from client.handler import MessageHandler

        handler = MessageHandler(MagicMock())
        handler._orchestrator = MagicMock()
        mgr = MagicMock()
        handler._orchestrator._device_manager = mgr
        active = MagicMock()
        mgr.get_active_device.return_value = active
        mgr._devices = {}  # no emulator devices

        device_info = {"device_type": "emulator", "adb_serial": "emulator-5554"}
        with patch("client.handler.MessageHandler._ensure_device_connected") as mock_ensure:
            resolved = handler._resolve_target_device(device_info)

        assert resolved is active
        mock_ensure.assert_not_called()
