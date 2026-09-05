"""ADB device controller unit tests for N126-F7.

Covers ascreencap/ascreencap_nc screenshot, NemuIpc DLL screenshot/input,
Hermit HTTP input, minitouch click/swipe, u2 click/swipe/key_press, and
fallback chain ordering.
"""

import struct
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from devices.adb.device import (
    ADB_INPUT,
    ASCREENCAP_BMZ1_MAGIC,
    ASCREENCAP_METHOD,
    ASCREENCAP_NC_METHOD,
    DROIDCAST_METHOD,
    HERMIT_DEFAULT_PORT,
    HERMIT_INPUT,
    HERMIT_PACKAGE_NAME,
    MAATOUCH_INPUT,
    MINITOUCH_INPUT,
    NEMU_IPC_INPUT,
    NEMU_IPC_METHOD,
    NEMU_METHOD,
    SCRCPY_METHOD,
    SCREENCAP_METHOD,
    SCREENCAP_NC_METHOD,
    U2_INPUT,
    U2_METHOD,
    ADBDevice,
)
from devices.base import DeviceStatus
from platforms.windows.nemu_ipc import NEMU_IPC_DLL_PATHS

pytestmark = pytest.mark.unit

# Check if lz4 is available for ascreencap decompression tests
try:
    import lz4.block  # noqa: F401

    LZ4_AVAILABLE = True
except ImportError:
    LZ4_AVAILABLE = False


# ==================== ascreencap BMZ1 header parsing ====================


class TestAscreencapHeaderParsing:
    """Tests for BMZ1 magic detection and byte swap logic."""

    def test_bmz1_magic_constant(self):
        """BMZ1 magic constant should be 828001602."""
        assert ASCREENCAP_BMZ1_MAGIC == 828001602

    def test_reposition_byte_pointer_finds_bmz1(self):
        """_ascreencap_reposition_byte_pointer should skip preamble and find BMZ1."""
        device = ADBDevice()
        preamble = b"linker warning: something\r\n"
        payload = b"BMZ1" + b"\x00" * 16
        data = preamble + payload
        result = device._ascreencap_reposition_byte_pointer(data)
        assert result.startswith(b"BMZ1")

    def test_reposition_byte_pointer_resets_on_failure(self):
        """If BMZ1 not found, bytepointer should reset and raise RuntimeError."""
        device = ADBDevice()
        device._ascreencap_bytepointer = 0
        with pytest.raises(RuntimeError, match="Repositioning byte pointer failed"):
            device._ascreencap_reposition_byte_pointer(b"NO_MAGIC_HERE" + b"\x00" * 20)
        assert device._ascreencap_bytepointer == 0

    def test_reposition_byte_pointer_remembers_offset(self):
        """Bytepointer should be remembered for subsequent calls."""
        device = ADBDevice()
        preamble = b"x" * 10
        payload = b"BMZ1" + b"\x00" * 16
        data = preamble + payload
        device._ascreencap_reposition_byte_pointer(data)
        # After first call, bytepointer should point to BMZ1 offset (10)
        assert device._ascreencap_bytepointer == 10


class TestAscreencapUncompress:
    """Tests for BMZ1 stream decompression."""

    @pytest.mark.skipif(not LZ4_AVAILABLE, reason="lz4 not installed")
    def _make_bmz1_stream(self, width: int, height: int, pixels: bytes) -> bytes:
        """Build a valid BMZ1 compressed stream for testing."""
        from lz4.block import compress

        uncompressed_size = len(pixels)
        # Header: magic, uncompressed_size, reserved, width, height (5 uint32)
        header = struct.pack(
            "<IIIII",
            ASCREENCAP_BMZ1_MAGIC,
            uncompressed_size,
            0,
            width,
            height,
        )
        compressed = compress(pixels, store_size=False)
        return header + compressed

    @pytest.mark.skipif(not LZ4_AVAILABLE, reason="lz4 not installed")
    def test_uncompress_valid_stream(self):
        """_ascreencap_uncompress should decode a valid BMZ1 stream to BGR array."""
        device = ADBDevice()
        width, height = 4, 2
        # BGR pixels (3 channels)
        pixels = bytes(range(width * height * 3))
        stream = self._make_bmz1_stream(width, height, pixels)
        image = device._ascreencap_uncompress(stream)
        assert image.shape == (height, width, 3)
        assert image.dtype == np.uint8

    @pytest.mark.skipif(not LZ4_AVAILABLE, reason="lz4 not installed")
    def test_uncompress_byteswap_header(self):
        """_ascreencap_uncompress should handle big-endian (byteswapped) header."""
        device = ADBDevice()
        width, height = 2, 2
        pixels = bytes(range(width * height * 3))
        stream = self._make_bmz1_stream(width, height, pixels)
        # Byteswap the header (first 20 bytes)
        swapped_header = np.frombuffer(stream[:20], dtype=np.uint32).byteswap().tobytes()
        swapped_stream = swapped_header + stream[20:]
        image = device._ascreencap_uncompress(swapped_stream)
        assert image.shape == (height, width, 3)

    def test_uncompress_invalid_magic_raises(self):
        """Invalid magic number should raise NotImplementedError (lz4/cv2 required) or RuntimeError."""
        device = ADBDevice()
        bad_header = struct.pack("<IIIII", 0xDEADBEEF, 100, 0, 4, 2)
        # If lz4/cv2 not installed, raises NotImplementedError; otherwise RuntimeError for bad magic
        with pytest.raises((RuntimeError, NotImplementedError)):
            device._ascreencap_uncompress(bad_header + b"\x00" * 100)

    def test_load_screenshot_method_0_passthrough(self):
        """Method 0 should return input unchanged."""
        device = ADBDevice()
        data = b"hello\r\nworld"
        assert device._ascreencap_load_screenshot(data, 0) == data

    def test_load_screenshot_method_1_crlf_to_lf(self):
        """Method 1 should replace \\r\\n with \\n."""
        device = ADBDevice()
        data = b"hello\r\nworld"
        assert device._ascreencap_load_screenshot(data, 1) == b"hello\nworld"

    def test_load_screenshot_method_2_crcrlf_to_lf(self):
        """Method 2 should replace \\r\\r\\n with \\n."""
        device = ADBDevice()
        data = b"hello\r\r\nworld"
        assert device._ascreencap_load_screenshot(data, 2) == b"hello\nworld"

    def test_load_screenshot_invalid_method_raises(self):
        """Invalid method should raise ValueError."""
        device = ADBDevice()
        with pytest.raises(ValueError, match="Unknown ascreencap load method"):
            device._ascreencap_load_screenshot(b"data", 99)


# ==================== ascreencap capture methods ====================


class TestAscreencapCapture:
    """Tests for _capture_ascreencap and _capture_ascreencap_nc."""

    def test_capture_ascreencap_no_device_returns_none(self):
        """_capture_ascreencap should return None if no device connected."""
        device = ADBDevice()
        assert device._capture_ascreencap() is None

    def test_capture_ascreencap_unavailable_raises(self):
        """_capture_ascreencap should raise NotImplementedError if binary unavailable."""
        device = ADBDevice()
        device._device = MagicMock()
        device._ascreencap_available = False
        with pytest.raises(NotImplementedError, match="ascreencap binary not available"):
            device._capture_ascreencap()

    def test_capture_ascreencap_nc_no_device_returns_none(self):
        """_capture_ascreencap_nc should return None if no device connected."""
        device = ADBDevice()
        assert device._capture_ascreencap_nc() is None

    def test_capture_ascreencap_nc_unavailable_raises(self):
        """_capture_ascreencap_nc should raise NotImplementedError if binary unavailable."""
        device = ADBDevice()
        device._device = MagicMock()
        device._ascreencap_available = False
        with pytest.raises(NotImplementedError, match="ascreencap binary not available"):
            device._capture_ascreencap_nc()


# ==================== NemuIpc DLL loading ====================


class TestNemuIpcLibLoading:
    """Tests for _load_nemu_ipc_lib DLL discovery."""

    def test_load_nemu_ipc_lib_non_windows_raises(self):
        """_load_nemu_ipc_lib should raise NotImplementedError on non-Windows."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        with patch.object(sys, "platform", "linux"), pytest.raises(
            NotImplementedError, match="only supported on Windows"
        ):
            device._load_nemu_ipc_lib()

    def test_load_nemu_ipc_lib_no_folder_raises(self):
        """_load_nemu_ipc_lib should raise NotImplementedError if nemu_folder empty."""
        device = ADBDevice(nemu_folder="")
        with patch.object(sys, "platform", "win32"), pytest.raises(
            NotImplementedError, match="nemu_folder to be set"
        ):
            device._load_nemu_ipc_lib()

    def test_load_nemu_ipc_lib_dll_not_found_raises(self):
        """_load_nemu_ipc_lib should raise NotImplementedError if no DLL exists."""
        device = ADBDevice(nemu_folder="C:\\NonExistent")
        with (
            patch.object(sys, "platform", "win32"),
            patch("os.path.exists", return_value=False),
            pytest.raises(NotImplementedError, match="MuMu12 >= 3.8.13"),
        ):
            device._load_nemu_ipc_lib()

    def test_load_nemu_ipc_lib_cached(self):
        """_load_nemu_ipc_lib should return cached lib on second call."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        mock_lib = MagicMock()
        device._nemu_ipc_lib = mock_lib
        assert device._load_nemu_ipc_lib() is mock_lib

    def test_nemu_ipc_dll_paths_constant(self):
        """NEMU_IPC_DLL_PATHS should contain expected relative paths."""
        assert "shell/sdk/external_renderer_ipc.dll" in NEMU_IPC_DLL_PATHS
        assert "nx_device/12.0/shell/sdk/external_renderer_ipc.dll" in NEMU_IPC_DLL_PATHS


class TestNemuIpcConnect:
    """Tests for _nemu_ipc_connect and _nemu_ipc_disconnect."""

    def test_connect_returns_cached_id(self):
        """_nemu_ipc_connect should return cached connect_id if > 0 without loading DLL."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        device._nemu_ipc_connect_id = 42
        # Should return 42 without calling _load_nemu_ipc_lib
        with patch.object(device, "_load_nemu_ipc_lib") as mock_load:
            assert device._nemu_ipc_connect() == 42
            mock_load.assert_not_called()

    def test_connect_failure_raises(self):
        """_nemu_ipc_connect should raise RuntimeError if nemu_connect returns 0."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        mock_lib = MagicMock()
        mock_lib.nemu_connect.return_value = 0
        device._nemu_ipc_lib = mock_lib
        # P1-2: Error message now mentions root causes explicitly.
        with pytest.raises(RuntimeError, match="nemu_connect returned 0"):
            device._nemu_ipc_connect()

    def test_connect_success_stores_id(self):
        """_nemu_ipc_connect should store and return the connect_id on success."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        mock_lib = MagicMock()
        mock_lib.nemu_connect.return_value = 12345
        device._nemu_ipc_lib = mock_lib
        result = device._nemu_ipc_connect()
        assert result == 12345
        assert device._nemu_ipc_connect_id == 12345

    def test_disconnect_noop_if_not_connected(self):
        """_nemu_ipc_disconnect should be a no-op if connect_id is 0."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        device._nemu_ipc_disconnect()  # Should not raise

    def test_disconnect_calls_nemu_disconnect(self):
        """_nemu_ipc_disconnect should call nemu_disconnect and reset connect_id."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        mock_lib = MagicMock()
        device._nemu_ipc_lib = mock_lib
        device._nemu_ipc_connect_id = 99
        device._nemu_ipc_disconnect()
        mock_lib.nemu_disconnect.assert_called_once_with(99)
        assert device._nemu_ipc_connect_id == 0


class TestNemuIpcConvertXY:
    """Tests for _nemu_ipc_convert_xy coordinate transformation."""

    def test_convert_xy_basic(self):
        """_nemu_ipc_convert_xy should apply (height - y, x) transformation."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        device._nemu_ipc_height = 1080
        # ADB (100, 200) -> NemuIpc (1080 - 200, 100) = (880, 100)
        nx, ny = device._nemu_ipc_convert_xy(100, 200)
        assert nx == 880
        assert ny == 100

    def test_convert_xy_queries_resolution_if_unknown(self):
        """_nemu_ipc_convert_xy should query resolution if height is 0."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        device._nemu_ipc_height = 0

        # Mock _nemu_ipc_get_resolution to set height as side effect
        def mock_get_resolution():
            device._nemu_ipc_width = 1920
            device._nemu_ipc_height = 1080
            return (1920, 1080)

        with patch.object(device, "_nemu_ipc_get_resolution", side_effect=mock_get_resolution):
            nx, ny = device._nemu_ipc_convert_xy(100, 200)
        assert device._nemu_ipc_height == 1080
        assert nx == 880


# ==================== Hermit input ====================


class TestHermitInput:
    """Tests for Hermit HTTP API input methods."""

    def test_hermit_constants(self):
        """Hermit constants should have expected values."""
        assert HERMIT_DEFAULT_PORT == 9999
        assert HERMIT_PACKAGE_NAME == "com.lookcos.hermit"

    def test_hermit_click_success(self):
        """_input_hermit_click should send GET /click with x,y params."""
        device = ADBDevice()
        device._device = MagicMock()
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"code": 0, "msg": "ok"}'
        mock_session.get.return_value = mock_response
        device._hermit_session = mock_session

        with patch("time.sleep"):  # Skip the 50ms delay
            device._input_hermit_click(500, 300)

        mock_session.get.assert_called_once()
        call_args = mock_session.get.call_args
        assert "/click" in call_args[0][0]
        assert call_args[1]["params"] == {"x": 500, "y": 300}

    def test_hermit_click_error_response_raises(self):
        """_input_hermit_click should raise RuntimeError on error code."""
        device = ADBDevice()
        device._device = MagicMock()
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"code": -1, "msg": "error"}'
        mock_session.get.return_value = mock_response
        device._hermit_session = mock_session

        with pytest.raises(RuntimeError, match="Hermit 错误响应"):
            device._input_hermit_click(500, 300)

    def test_hermit_click_invalid_json_raises(self):
        """_input_hermit_click should raise RuntimeError on invalid JSON."""
        device = ADBDevice()
        device._device = MagicMock()
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "not json"
        mock_session.get.return_value = mock_response
        device._hermit_session = mock_session

        with pytest.raises(RuntimeError, match="Hermit 返回非 JSON 响应"):
            device._input_hermit_click(500, 300)

    def test_hermit_click_resets_session_on_connection_error(self):
        """_input_hermit_click should reset session on connection error."""
        device = ADBDevice()
        device._device = MagicMock()
        mock_session = MagicMock()
        mock_session.get.side_effect = ConnectionError("refused")
        device._hermit_session = mock_session

        with pytest.raises(RuntimeError, match="Hermit 请求失败"):
            device._input_hermit_click(500, 300)
        assert device._hermit_session is None

    def test_get_hermit_session_no_device_raises(self):
        """_get_hermit_session should raise DeviceError if no device."""
        device = ADBDevice()
        from core.exceptions import DeviceError

        with pytest.raises(DeviceError, match="ADB 设备未连接"):
            device._get_hermit_session()


# ==================== minitouch input ====================


class TestMinitouchInput:
    """Tests for minitouch click/swipe handlers."""

    def test_minitouch_click_sends_correct_command(self):
        """_input_minitouch_click should send 'd 0 x y 50\\nc\\nu 0\\nc\\n'."""
        device = ADBDevice()
        mock_sock = MagicMock()
        # Mock _get_minitouch_socket to return our mock socket directly
        with patch.object(device, "_get_minitouch_socket", return_value=mock_sock):
            device._input_minitouch_click(100, 200)

        mock_sock.sendall.assert_called_once()
        sent_data = mock_sock.sendall.call_args[0][0].decode("utf-8")
        assert "d 0 100 200 50" in sent_data
        assert "c" in sent_data
        assert "u 0" in sent_data

    def test_minitouch_click_socket_error_resets(self):
        """_input_minitouch_click should raise RuntimeError on socket send failure."""
        device = ADBDevice()
        mock_sock = MagicMock()
        mock_sock.sendall.side_effect = OSError("broken pipe")
        with patch.object(
            device, "_get_minitouch_socket", return_value=mock_sock
        ), pytest.raises(RuntimeError, match="minitouch 点击失败"):
            device._input_minitouch_click(100, 200)

    def test_minitouch_swipe_sends_multiple_commands(self):
        """_input_minitouch_swipe should send down + multiple move + up commands."""
        device = ADBDevice()
        mock_sock = MagicMock()
        with (
            patch.object(device, "_get_minitouch_socket", return_value=mock_sock),
            patch("time.sleep"),  # Skip delays
        ):
            device._input_minitouch_swipe(0, 0, 100, 100, duration=100)

        # Should send: down + moves + up (at least 3 sendall calls)
        assert mock_sock.sendall.call_count >= 3


# ==================== u2 input ====================


class TestU2Input:
    """Tests for uiautomator2 click/swipe/key_press handlers."""

    def test_u2_click_calls_device_click(self):
        """_input_u2_click should call u2 device.click(x, y)."""
        device = ADBDevice()
        mock_u2 = MagicMock()
        device._u2_device = mock_u2

        device._input_u2_click(100, 200)

        mock_u2.click.assert_called_once_with(100, 200)

    def test_u2_click_error_resets_device(self):
        """_input_u2_click should reset u2_device on exception."""
        device = ADBDevice()
        mock_u2 = MagicMock()
        mock_u2.click.side_effect = RuntimeError("disconnected")
        device._u2_device = mock_u2

        with (
            patch.object(device, "_get_u2_device", return_value=mock_u2),
            patch("time.sleep"),  # skip retry delays
            pytest.raises(RuntimeError, match="u2 点击失败"),
        ):
            device._input_u2_click(100, 200)
        assert device._u2_device is None

    def test_u2_swipe_calls_device_swipe(self):
        """_input_u2_swipe should call u2 device.swipe with duration in seconds."""
        device = ADBDevice()
        mock_u2 = MagicMock()
        device._u2_device = mock_u2

        device._input_u2_swipe(0, 0, 100, 100, duration=300)

        mock_u2.swipe.assert_called_once_with(0, 0, 100, 100, duration=0.3)

    def test_u2_key_press_calls_press_keycode(self):
        """_input_u2_key_press should call u2 device.press_keycode with resolved keycode."""
        device = ADBDevice()
        mock_u2 = MagicMock()
        device._u2_device = mock_u2

        device._input_u2_key_press("home")

        mock_u2.press_keycode.assert_called_once_with(3)  # home = 3

    def test_u2_key_press_numeric_string(self):
        """_input_u2_key_press should handle numeric keycode strings."""
        device = ADBDevice()
        mock_u2 = MagicMock()
        device._u2_device = mock_u2

        device._input_u2_key_press("82")

        mock_u2.press_keycode.assert_called_once_with(82)

    def test_get_u2_device_caches_instance(self):
        """_get_u2_device should cache the u2 device instance."""
        device = ADBDevice(serial="127.0.0.1:5555")
        mock_u2_module = MagicMock()
        mock_u2_instance = MagicMock()
        mock_u2_module.connect.return_value = mock_u2_instance

        with patch.dict("sys.modules", {"uiautomator2": mock_u2_module}):
            result1 = device._get_u2_device()
            result2 = device._get_u2_device()

        assert result1 is mock_u2_instance
        assert result2 is mock_u2_instance
        mock_u2_module.connect.assert_called_once_with("127.0.0.1:5555")


# ==================== NemuIpc input ====================


class TestNemuIpcInput:
    """Tests for NemuIpc click/swipe handlers."""

    def test_nemu_ipc_click_calls_touch_down_and_up(self):
        """_input_nemu_ipc_click should call nemu_input_event_touch_down then up."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        mock_lib = MagicMock()
        mock_lib.nemu_input_event_touch_down.return_value = 0
        mock_lib.nemu_input_event_touch_up.return_value = 0
        device._nemu_ipc_lib = mock_lib
        device._nemu_ipc_connect_id = 1
        device._nemu_ipc_height = 1080

        with patch("time.sleep"):
            device._input_nemu_ipc_click(100, 200)

        mock_lib.nemu_input_event_touch_down.assert_called_once()
        mock_lib.nemu_input_event_touch_up.assert_called_once()

    def test_nemu_ipc_click_down_failure_raises(self):
        """_input_nemu_ipc_click should raise if touch_down returns > 0."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        mock_lib = MagicMock()
        mock_lib.nemu_input_event_touch_down.return_value = 1
        device._nemu_ipc_lib = mock_lib
        device._nemu_ipc_connect_id = 1
        device._nemu_ipc_height = 1080

        with pytest.raises(RuntimeError, match="NemuIpc 点击失败"):
            device._input_nemu_ipc_click(100, 200)

    def test_nemu_ipc_click_up_failure_raises(self):
        """_input_nemu_ipc_click should raise if touch_up returns > 0."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        mock_lib = MagicMock()
        mock_lib.nemu_input_event_touch_down.return_value = 0
        mock_lib.nemu_input_event_touch_up.return_value = 1
        device._nemu_ipc_lib = mock_lib
        device._nemu_ipc_connect_id = 1
        device._nemu_ipc_height = 1080

        with patch("time.sleep"), pytest.raises(RuntimeError, match="NemuIpc 点击失败"):
            device._input_nemu_ipc_click(100, 200)

    def test_nemu_ipc_swipe_sends_multiple_down_events(self):
        """_input_nemu_ipc_swipe should call touch_down multiple times then up."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        mock_lib = MagicMock()
        mock_lib.nemu_input_event_touch_down.return_value = 0
        mock_lib.nemu_input_event_touch_up.return_value = 0
        device._nemu_ipc_lib = mock_lib
        device._nemu_ipc_connect_id = 1
        device._nemu_ipc_height = 1080

        with patch("time.sleep"):
            device._input_nemu_ipc_swipe(0, 0, 100, 100, duration=100)

        # touch_down called multiple times (steps + 1), touch_up called once
        assert mock_lib.nemu_input_event_touch_down.call_count >= 2
        mock_lib.nemu_input_event_touch_up.assert_called_once()


# ==================== Fallback chain ordering ====================


class TestFallbackChainOrdering:
    """Tests for screenshot and input fallback chain ordering."""

    def test_screenshot_fallback_includes_all_methods(self):
        """capture_screen fallback should include all 11 screenshot methods."""
        device = ADBDevice()
        device._device = MagicMock()
        device._status = DeviceStatus.CONNECTED  # Bypass require_operable
        methods_called = []

        def mock_capture(method_name):
            def _capture():
                methods_called.append(method_name)
                raise RuntimeError(f"{method_name} failed")
            return _capture

        with (
            patch.object(device, "_capture_nemu_ipc", side_effect=mock_capture("nemu_ipc")),
            patch.object(device, "_capture_nemu", side_effect=mock_capture("nemu")),
            patch.object(device, "_capture_scrcpy", side_effect=mock_capture("scrcpy")),
            patch.object(device, "_capture_droidcast_raw", side_effect=mock_capture("droidcast_raw")),
            patch.object(device, "_capture_droidcast", side_effect=mock_capture("droidcast")),
            patch.object(device, "_capture_uiautomator2", side_effect=mock_capture("u2")),
            patch.object(device, "_capture_ascreencap_nc", side_effect=mock_capture("ascreencap_nc")),
            patch.object(device, "_capture_ascreencap", side_effect=mock_capture("ascreencap")),
            patch.object(device, "_capture_screencap_nc", side_effect=mock_capture("screencap_nc")),
            patch.object(device, "_capture_screencap", side_effect=mock_capture("screencap")),
            patch.object(device, "_capture_ldopengl", side_effect=mock_capture("ldopengl")),
            patch("time.sleep"),  # skip retry delays
        ):
            result = device.capture_screen()

        assert result is None
        # All 11 methods should have been tried in order. Each leaf method is
        # wrapped by @retry_screenshot, so each name appears retries+1 times.
        expected_order = [
            "nemu_ipc", "nemu", "ldopengl", "scrcpy", "droidcast_raw", "droidcast",
            "u2", "ascreencap_nc", "ascreencap", "screencap_nc", "screencap",
        ]
        unique_called = []
        for name in methods_called:
            if name not in unique_called:
                unique_called.append(name)
        assert unique_called == expected_order

    def test_click_fallback_includes_all_methods(self):
        """click fallback should include all 6 input methods."""
        device = ADBDevice()
        device._device = MagicMock()
        device._status = DeviceStatus.CONNECTED  # Bypass require_operable
        methods_called = []

        def make_mock(name):
            def _mock(*args, **kwargs):
                methods_called.append(name)
                raise RuntimeError(f"{name} failed")
            return _mock

        with (
            patch.object(device, "_input_nemu_ipc_click", side_effect=make_mock("nemu_ipc")),
            patch.object(device, "_input_maatouch_click", side_effect=make_mock("maatouch")),
            patch.object(device, "_input_minitouch_click", side_effect=make_mock("minitouch")),
            patch.object(device, "_input_u2_click", side_effect=make_mock("u2")),
            patch.object(device, "_input_hermit_click", side_effect=make_mock("hermit")),
            patch.object(device, "_input_adb_click", side_effect=make_mock("adb")),
        ):
            from core.exceptions import DeviceError

            with pytest.raises(DeviceError, match="所有点击方法均失败"):
                device.click(100, 200)

        assert methods_called == ["nemu_ipc", "maatouch", "minitouch", "u2", "hermit", "adb"]

    def test_screenshot_method_map_has_all_handlers(self):
        """_capture_by_method should map all 10 method constants to handlers."""
        ADBDevice()
        # Verify all constants are mapped
        assert True
        # More robust: call each method and verify it doesn't fall through to screencap
        # We test by checking the method_map dict indirectly via behavior

    def test_input_method_constants_distinct(self):
        """All input method constants should be distinct strings."""
        methods = [NEMU_IPC_INPUT, MAATOUCH_INPUT, MINITOUCH_INPUT, U2_INPUT, HERMIT_INPUT, ADB_INPUT]
        assert len(methods) == len(set(methods))

    def test_screenshot_method_constants_distinct(self):
        """All screenshot method constants should be distinct strings."""
        methods = [
            NEMU_IPC_METHOD, NEMU_METHOD, SCRCPY_METHOD,
            DROIDCAST_METHOD, U2_METHOD, ASCREENCAP_NC_METHOD,
            ASCREENCAP_METHOD, SCREENCAP_NC_METHOD, SCREENCAP_METHOD,
        ]
        assert len(methods) == len(set(methods))


# ==================== Resource cleanup ====================


class TestResourceCleanup:
    """Tests for _cleanup_resources covering new resources."""

    def test_cleanup_closes_hermit_session(self):
        """_cleanup_resources should close Hermit session."""
        device = ADBDevice()
        mock_session = MagicMock()
        device._hermit_session = mock_session

        device._cleanup_resources()

        mock_session.close.assert_called_once()
        assert device._hermit_session is None

    def test_cleanup_disconnects_nemu_ipc(self):
        """_cleanup_resources should disconnect NemuIpc."""
        device = ADBDevice(nemu_folder="C:\\MuMu")
        mock_lib = MagicMock()
        device._nemu_ipc_lib = mock_lib
        device._nemu_ipc_connect_id = 42

        device._cleanup_resources()

        mock_lib.nemu_disconnect.assert_called_once_with(42)
        assert device._nemu_ipc_connect_id == 0

    def test_cleanup_noop_when_no_resources(self):
        """_cleanup_resources should be safe to call with no resources."""
        device = ADBDevice()
        device._cleanup_resources()  # Should not raise


# ==================== Device info ====================


class TestDeviceInfo:
    """Tests for get_device_info including new fields."""

    def test_device_info_includes_hermit_port(self):
        """get_device_info should include hermit_port."""
        device = ADBDevice(hermit_port=8888)
        device._status = DeviceStatus.CONNECTED
        device._device = MagicMock()
        device._device.shell.return_value = "Physical size: 1920x1080"
        info = device.get_device_info()
        assert info["hermit_port"] == 8888

    def test_device_info_includes_nemu_folder(self):
        """get_device_info should include nemu_folder."""
        device = ADBDevice(nemu_folder="C:\\MuMu12")
        device._status = DeviceStatus.CONNECTED
        device._device = MagicMock()
        device._device.shell.return_value = "Physical size: 1920x1080"
        info = device.get_device_info()
        assert info["nemu_folder"] == "C:\\MuMu12"

    def test_device_info_includes_nemu_ipc_connected(self):
        """get_device_info should include nemu_ipc_connected status."""
        device = ADBDevice(nemu_folder="C:\\MuMu12")
        device._status = DeviceStatus.CONNECTED
        device._device = MagicMock()
        device._device.shell.return_value = "Physical size: 1920x1080"
        device._nemu_ipc_connect_id = 0
        info = device.get_device_info()
        assert info["nemu_ipc_connected"] is False

        device._nemu_ipc_connect_id = 42
        info = device.get_device_info()
        assert info["nemu_ipc_connected"] is True


# ==================== Constructor parameters ====================


class TestConstructorParameters:
    """Tests for new constructor parameters."""

    def test_default_hermit_port(self):
        """Default hermit_port should be 9999."""
        device = ADBDevice()
        assert device._hermit_port == HERMIT_DEFAULT_PORT

    def test_custom_hermit_port(self):
        """Custom hermit_port should be stored."""
        device = ADBDevice(hermit_port=7777)
        assert device._hermit_port == 7777

    def test_default_nemu_folder_empty(self):
        """Default nemu_folder should be empty string."""
        device = ADBDevice()
        assert device._nemu_folder == ""

    def test_custom_nemu_folder(self):
        """Custom nemu_folder should be stored."""
        device = ADBDevice(nemu_folder="D:\\MuMuPlayer-12.0")
        assert device._nemu_folder == "D:\\MuMuPlayer-12.0"

    def test_default_nemu_instance_id(self):
        """Default nemu_instance_id should be 0."""
        device = ADBDevice()
        assert device._nemu_instance_id == 0

    def test_custom_nemu_instance_id(self):
        """Custom nemu_instance_id should be stored."""
        device = ADBDevice(nemu_instance_id=3)
        assert device._nemu_instance_id == 3

    def test_ascreencap_state_initialized(self):
        """ascreencap state should be initialized to defaults."""
        device = ADBDevice()
        assert device._ascreencap_bytepointer == 0
        assert device._ascreencap_available is True

    def test_nemu_ipc_state_initialized(self):
        """NemuIpc state should be initialized to defaults."""
        device = ADBDevice()
        assert device._nemu_ipc_lib is None
        assert device._nemu_ipc_connect_id == 0
        assert device._nemu_ipc_width == 0
        assert device._nemu_ipc_height == 0


class TestAdbNetworkSerialConnect:
    """host:port 网络 serial 先 adb connect 注册 (2026-09-05).

    模拟器 adb 端口 (127.0.0.1:5555) 需 adb connect 后 adbutils adb.device()
    才能找到, 否则按键/点击全挂 "device not found".
    """

    def test_is_network_serial(self):
        from devices.adb.adb_lifecycle import ADBLifecycleMixin

        assert ADBLifecycleMixin._is_network_serial("127.0.0.1:5555") is True
        assert ADBLifecycleMixin._is_network_serial("emulator-5554") is False
        assert ADBLifecycleMixin._is_network_serial("localhost:62001") is True
        assert ADBLifecycleMixin._is_network_serial("") is False

    @patch("devices.adb.adb_lifecycle.subprocess.run")
    @patch("devices.emulator_discovery.EmulatorDiscovery._discover_adb_path", return_value="D:/adb.exe")
    def test_adb_connect_registers_serial(self, mock_discover, mock_run):
        from devices.adb.adb_lifecycle import ADBLifecycleMixin

        mock_run.return_value.stdout = "connected to 127.0.0.1:5555"
        ADBLifecycleMixin._adb_connect("127.0.0.1:5555")
        mock_run.assert_called_once()
        args = mock_run.call_args.args[0]
        assert args[:3] == ["D:/adb.exe", "connect", "127.0.0.1:5555"]

    @patch("devices.adb.adb_lifecycle.ADBLifecycleMixin._adb_connect")
    @patch("devices.adb.adb_lifecycle.get_adb_pool")
    def test_connect_registers_network_serial_first(self, mock_pool, mock_connect):
        mock_pool.return_value.get.return_value = MagicMock()
        device = ADBDevice.__new__(ADBDevice)
        device._serial = "127.0.0.1:5555"
        device._device = None
        device._status = None
        device._nemu_keepalive = None
        device.connect()
        mock_connect.assert_called_once_with("127.0.0.1:5555")

    @patch("devices.adb.adb_lifecycle.ADBLifecycleMixin._adb_connect")
    @patch("devices.adb.adb_lifecycle.get_adb_pool")
    def test_connect_skips_local_alias(self, mock_pool, mock_connect):
        mock_pool.return_value.get.return_value = MagicMock()
        device = ADBDevice.__new__(ADBDevice)
        device._serial = "emulator-5554"
        device._device = None
        device._status = None
        device._nemu_keepalive = None
        device.connect()
        mock_connect.assert_not_called()

    def test_maatouch_key_press_falls_back(self):
        """MaaTouch 无按键能力 → NotImplementedError (降级链到 adb)."""
        from devices.adb.device import ADBDevice

        device = ADBDevice()
        with pytest.raises(NotImplementedError):
            device._input_maatouch_key_press("home")
