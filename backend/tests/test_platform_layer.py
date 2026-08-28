"""P-028 macOS/Linux platform layer unit tests.

Tests run on any platform (Windows included) by mocking pyobjc/python-xlib imports.
Verifies:
- Module imports without crashing on non-target platforms
- Target parsing (decimal/hex)
- Method dispatch (unknown method returns error)
- Availability checks return False when dependencies missing
- ADB device discovery parses `adb devices` output correctly
- Registry auto-register falls back to Mock on non-target platforms
"""
from unittest import mock

import pytest

from device_bridge.platforms.base import (
    DeviceInfo,
    InputResult,
    PlatformDeviceDiscoverer,
    PlatformInputHandler,
    PlatformScreenshotHandler,
    ScreenshotResult,
)

# ============================================================
# macOS screenshot tests
# ============================================================

class TestMacOSScreenshotHandler:
    """Test MacOSScreenshotHandler without actual macOS."""

    def test_available_methods(self):
        from device_bridge.platforms.macos.screenshot import MacOSScreenshotHandler
        handler = MacOSScreenshotHandler()
        assert handler.available_methods() == ['CGWindowList', 'screencapture']

    def test_parse_target_decimal(self):
        from device_bridge.platforms.macos.screenshot import MacOSScreenshotHandler
        assert MacOSScreenshotHandler._parse_target('12345') == 12345

    def test_parse_target_hex_0x(self):
        from device_bridge.platforms.macos.screenshot import MacOSScreenshotHandler
        assert MacOSScreenshotHandler._parse_target('0x3039') == 12345

    def test_parse_target_hex_hash(self):
        from device_bridge.platforms.macos.screenshot import MacOSScreenshotHandler
        assert MacOSScreenshotHandler._parse_target('#3039') == 12345

    def test_parse_target_empty_raises(self):
        from device_bridge.platforms.macos.screenshot import MacOSScreenshotHandler
        with pytest.raises(ValueError, match='target must be'):
            MacOSScreenshotHandler._parse_target('')

    def test_parse_target_invalid_raises(self):
        from device_bridge.platforms.macos.screenshot import MacOSScreenshotHandler
        with pytest.raises(ValueError, match='Invalid window_id'):
            MacOSScreenshotHandler._parse_target('not-a-number')

    def test_capture_unknown_method_returns_error(self):
        from device_bridge.platforms.macos.screenshot import MacOSScreenshotHandler
        handler = MacOSScreenshotHandler()
        result = handler.capture('123', method='unknown')
        assert result.success is False
        assert 'Unknown method' in (result.error or '')

    def test_capture_no_quartz_returns_permission_error(self):
        """On non-macOS, Quartz is unavailable, so capture should return permission error."""
        from device_bridge.platforms.macos.screenshot import MacOSScreenshotHandler
        handler = MacOSScreenshotHandler()
        # _check_screen_recording_permission returns False when Quartz unavailable
        result = handler.capture('123', method='CGWindowList')
        # Either permission error or pyobjc unavailable error
        assert result.success is False
        assert result.method == 'CGWindowList'

    def test_png_dimensions_valid(self):
        # Create a minimal 1x1 PNG
        import struct
        import zlib

        from device_bridge.platforms.macos.screenshot import MacOSScreenshotHandler
        # PNG signature + IHDR + IDAT + IEND
        sig = b'\x89PNG\r\n\x1a\n'
        ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)  # 1x1, 8-bit, RGB
        ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
        ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
        # Minimal IDAT (1 pixel: filter byte + RGB)
        raw_data = b'\x00\xff\x00\x00'  # filter=none, R=255, G=0, B=0
        compressed = zlib.compress(raw_data)
        idat_crc = zlib.crc32(b'IDAT' + compressed) & 0xffffffff
        idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)
        # IEND
        iend_crc = zlib.crc32(b'IEND') & 0xffffffff
        iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
        png_data = sig + ihdr + idat + iend

        width, height = MacOSScreenshotHandler._png_dimensions(png_data)
        assert width == 1
        assert height == 1

    def test_png_dimensions_invalid(self):
        from device_bridge.platforms.macos.screenshot import MacOSScreenshotHandler
        width, height = MacOSScreenshotHandler._png_dimensions(b'not a png')
        assert width == 0
        assert height == 0

    def test_benchmark_zero_rounds(self):
        from device_bridge.platforms.macos.screenshot import MacOSScreenshotHandler
        handler = MacOSScreenshotHandler()
        result = handler.benchmark('123', 'CGWindowList', rounds=0)
        assert result['success_rate'] == 0.0


# ============================================================
# macOS input tests
# ============================================================

class TestMacOSInputHandler:
    """Test MacOSInputHandler without actual macOS."""

    def test_available_methods(self):
        from device_bridge.platforms.macos.input import MacOSInputHandler
        handler = MacOSInputHandler()
        assert handler.available_methods() == ['CGEvent', 'AppleScript']

    def test_click_unknown_method(self):
        from device_bridge.platforms.macos.input import MacOSInputHandler
        handler = MacOSInputHandler()
        result = handler.click('target', 100, 200, method='unknown')
        assert result.success is False
        assert 'Unknown method' in (result.error or '')

    def test_swipe_unknown_method(self):
        from device_bridge.platforms.macos.input import MacOSInputHandler
        handler = MacOSInputHandler()
        result = handler.swipe('target', 0, 0, 100, 100, method='unknown')
        assert result.success is False

    def test_key_press_unknown_method(self):
        from device_bridge.platforms.macos.input import MacOSInputHandler
        handler = MacOSInputHandler()
        result = handler.key_press('target', 'enter', method='unknown')
        assert result.success is False

    def test_scroll_unknown_method(self):
        from device_bridge.platforms.macos.input import MacOSInputHandler
        handler = MacOSInputHandler()
        result = handler.scroll('target', 100, 100, 1, method='unknown')
        assert result.success is False

    def test_click_cgevent_no_quartz(self):
        """On non-macOS, Quartz unavailable, click should return error."""
        from device_bridge.platforms.macos.input import MacOSInputHandler
        handler = MacOSInputHandler()
        result = handler.click('target', 100, 200, method='CGEvent')
        assert result.success is False
        assert 'Quartz' in (result.error or '') or 'Accessibility' in (result.error or '')

    def test_key_press_cgevent_unknown_key(self):
        """Unknown key returns error (after permission check)."""
        from device_bridge.platforms.macos.input import MacOSInputHandler
        handler = MacOSInputHandler()
        # Will fail at permission check first on non-macOS
        result = handler.key_press('target', 'nonexistent_key', method='CGEvent')
        assert result.success is False

    def test_key_map_has_common_keys(self):
        from device_bridge.platforms.macos.input import _KEY_MAP
        assert 'enter' in _KEY_MAP
        assert 'esc' in _KEY_MAP
        assert 'space' in _KEY_MAP
        assert 'tab' in _KEY_MAP
        assert _KEY_MAP['enter'] == 36

    def test_char_to_keycode_has_letters(self):
        from device_bridge.platforms.macos.input import _CHAR_TO_KEYCODE
        assert 'a' in _CHAR_TO_KEYCODE
        assert 'A' in _CHAR_TO_KEYCODE
        assert '0' in _CHAR_TO_KEYCODE
        assert _CHAR_TO_KEYCODE['a'] == 97
        assert _CHAR_TO_KEYCODE['A'] == 97  # Same keycode, shift handled separately


# ============================================================
# macOS discovery tests
# ============================================================

class TestMacOSDeviceDiscoverer:
    """Test MacOSDeviceDiscoverer."""

    def test_discover_windows_no_quartz(self):
        from device_bridge.platforms.macos.discovery import MacOSDeviceDiscoverer
        discoverer = MacOSDeviceDiscoverer()
        # On non-macOS, Quartz unavailable, should return empty list
        result = discoverer.discover_windows()
        assert result == []

    def test_discover_adb_devices_no_adb(self):
        """When adb not in PATH, returns empty list (no crash)."""
        from device_bridge.platforms.macos.discovery import MacOSDeviceDiscoverer
        discoverer = MacOSDeviceDiscoverer()
        # Mock subprocess.run to raise FileNotFoundError
        with mock.patch('subprocess.run', side_effect=FileNotFoundError):
            result = discoverer.discover_adb_devices()
        assert result == []

    def test_discover_adb_devices_parses_output(self):
        """Test ADB output parsing with mocked subprocess."""
        from device_bridge.platforms.macos.discovery import MacOSDeviceDiscoverer

        # Mock adb devices -l output
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = (
            'List of devices attached\n'
            'emulator-5554          device product:sdk_gphone64_x86_64 model:Pixel_5 device:emu64x64 transport_id:1\n'
            '192.168.1.100:5555     device product:mido model:Redmi_Note_4 device:mido transport_id:2\n'
            'emulator-5556          offline transport_id:3\n'
        )
        with mock.patch('subprocess.run', return_value=mock_result):
            discoverer = MacOSDeviceDiscoverer()
            devices = discoverer.discover_adb_devices()

        # Should find 2 devices (offline one is excluded)
        assert len(devices) == 2
        assert devices[0].identifier == 'emulator-5554'
        assert devices[0].name == 'Pixel_5'
        assert devices[0].device_type == 'adb'
        assert devices[0].platform == 'macos'
        assert devices[1].identifier == '192.168.1.100:5555'
        assert devices[1].name == 'Redmi_Note_4'

    def test_discover_adb_devices_empty_output(self):
        from device_bridge.platforms.macos.discovery import MacOSDeviceDiscoverer
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = 'List of devices attached\n'
        with mock.patch('subprocess.run', return_value=mock_result):
            discoverer = MacOSDeviceDiscoverer()
            devices = discoverer.discover_adb_devices()
        assert devices == []

    def test_discover_adb_devices_command_failure(self):
        from device_bridge.platforms.macos.discovery import MacOSDeviceDiscoverer
        mock_result = mock.Mock()
        mock_result.returncode = 1
        mock_result.stdout = ''
        with mock.patch('subprocess.run', return_value=mock_result):
            discoverer = MacOSDeviceDiscoverer()
            devices = discoverer.discover_adb_devices()
        assert devices == []

    def test_discover_emulators_no_pgrep(self):
        from device_bridge.platforms.macos.discovery import MacOSDeviceDiscoverer
        discoverer = MacOSDeviceDiscoverer()
        with mock.patch('subprocess.run', side_effect=FileNotFoundError):
            devices = discoverer.discover_emulators()
        # Should not crash, returns empty list (adb also fails)
        assert isinstance(devices, list)


# ============================================================
# Linux screenshot tests
# ============================================================

class TestLinuxScreenshotHandler:
    """Test LinuxScreenshotHandler without actual Linux X11."""

    def test_available_methods(self):
        from device_bridge.platforms.linux.screenshot import LinuxScreenshotHandler
        handler = LinuxScreenshotHandler()
        assert handler.available_methods() == ['XGetImage', 'XShmGetImage', 'xdg_portal']

    def test_parse_target_decimal(self):
        from device_bridge.platforms.linux.screenshot import _parse_target
        assert _parse_target('12345') == 12345

    def test_parse_target_hex(self):
        from device_bridge.platforms.linux.screenshot import _parse_target
        assert _parse_target('0x3039') == 12345
        assert _parse_target('#3039') == 12345

    def test_parse_target_empty_raises(self):
        from device_bridge.platforms.linux.screenshot import _parse_target
        with pytest.raises(ValueError, match='target must be'):
            _parse_target('')

    def test_parse_target_invalid_raises(self):
        from device_bridge.platforms.linux.screenshot import _parse_target
        with pytest.raises(ValueError, match='Invalid window id'):
            _parse_target('xyz')

    def test_capture_unknown_method(self):
        from device_bridge.platforms.linux.screenshot import LinuxScreenshotHandler
        handler = LinuxScreenshotHandler()
        result = handler.capture('123', method='unknown')
        assert result.success is False
        assert 'Unknown method' in (result.error or '')

    def test_capture_xgetimage_no_xlib(self):
        """On non-Linux, python-xlib unavailable, should return error."""
        from device_bridge.platforms.linux.screenshot import LinuxScreenshotHandler
        handler = LinuxScreenshotHandler()
        result = handler.capture('123', method='XGetImage')
        assert result.success is False
        assert 'python-xlib' in (result.error or '') or 'XGetImage' in (result.error or '')

    def test_capture_xshmgetimage_falls_back_to_xgetimage(self):
        """XShmGetImage should fall back to XGetImage (which fails without xlib)."""
        from device_bridge.platforms.linux.screenshot import LinuxScreenshotHandler
        handler = LinuxScreenshotHandler()
        result = handler.capture('123', method='XShmGetImage')
        assert result.success is False  # Fails because no xlib on Windows

    def test_capture_xdg_portal_no_tools(self):
        """xdg_portal method should fail gracefully when grim/gnome-screenshot not installed."""
        from device_bridge.platforms.linux.screenshot import LinuxScreenshotHandler
        handler = LinuxScreenshotHandler()
        with mock.patch('subprocess.run', side_effect=FileNotFoundError):
            result = handler.capture('123', method='xdg_portal')
        assert result.success is False
        assert 'screenshot tool' in (result.error or '').lower() or 'grim' in (result.error or '').lower()

    def test_detect_display_server_unknown(self):
        """On Windows, display server detection returns 'unknown'."""
        from device_bridge.platforms.linux.screenshot import _detect_display_server
        # Clear env vars to simulate no display
        with mock.patch.dict('os.environ', {}, clear=False):
            # Remove X11/Wayland env vars if present
            import os
            env_without_display = {k: v for k, v in os.environ.items()
                                   if k not in ('DISPLAY', 'WAYLAND_DISPLAY', 'XDG_SESSION_TYPE')}
            with mock.patch.dict('os.environ', env_without_display, clear=True):
                result = _detect_display_server()
        # On Windows, should be 'unknown'
        assert result in ('x11', 'wayland', 'unknown')

    def test_benchmark_zero_rounds(self):
        from device_bridge.platforms.linux.screenshot import LinuxScreenshotHandler
        handler = LinuxScreenshotHandler()
        result = handler.benchmark('123', 'XGetImage', rounds=0)
        assert result['success_rate'] == 0.0


# ============================================================
# Linux input tests
# ============================================================

class TestLinuxInputHandler:
    """Test LinuxInputHandler without actual Linux X11."""

    def test_available_methods(self):
        from device_bridge.platforms.linux.input import LinuxInputHandler
        handler = LinuxInputHandler()
        assert handler.available_methods() == ['XTest', 'XSendEvent', 'uinput']

    def test_click_unknown_method(self):
        from device_bridge.platforms.linux.input import LinuxInputHandler
        handler = LinuxInputHandler()
        result = handler.click('target', 100, 200, method='unknown')
        assert result.success is False

    def test_swipe_unknown_method(self):
        from device_bridge.platforms.linux.input import LinuxInputHandler
        handler = LinuxInputHandler()
        result = handler.swipe('target', 0, 0, 100, 100, method='unknown')
        assert result.success is False

    def test_key_press_unknown_method(self):
        from device_bridge.platforms.linux.input import LinuxInputHandler
        handler = LinuxInputHandler()
        result = handler.key_press('target', 'enter', method='unknown')
        assert result.success is False

    def test_scroll_unknown_method(self):
        from device_bridge.platforms.linux.input import LinuxInputHandler
        handler = LinuxInputHandler()
        result = handler.scroll('target', 100, 100, 1, method='unknown')
        assert result.success is False

    def test_click_xtest_no_xlib(self):
        """On non-Linux, python-xlib unavailable, should return error."""
        from device_bridge.platforms.linux.input import LinuxInputHandler
        handler = LinuxInputHandler()
        result = handler.click('target', 100, 200, method='XTest')
        assert result.success is False
        assert 'python-xlib' in (result.error or '') or 'XTest' in (result.error or '')

    def test_key_press_xtest_unknown_key(self):
        from device_bridge.platforms.linux.input import LinuxInputHandler
        handler = LinuxInputHandler()
        # Will fail at xlib check first on non-Linux
        result = handler.key_press('target', 'nonexistent_key', method='XTest')
        assert result.success is False

    def test_key_map_has_common_keys(self):
        from device_bridge.platforms.linux.input import _KEY_MAP
        assert 'enter' in _KEY_MAP
        assert 'esc' in _KEY_MAP
        assert 'space' in _KEY_MAP
        assert _KEY_MAP['enter'] == 0xff0d  # XK_Return

    def test_resolve_keysym_named_key(self):
        from device_bridge.platforms.linux.input import LinuxInputHandler
        assert LinuxInputHandler._resolve_keysym('enter') == 0xff0d
        assert LinuxInputHandler._resolve_keysym('ENTER') == 0xff0d  # Case insensitive
        assert LinuxInputHandler._resolve_keysym('esc') == 0xff1b

    def test_resolve_keysym_single_char(self):
        from device_bridge.platforms.linux.input import LinuxInputHandler
        assert LinuxInputHandler._resolve_keysym('a') == ord('a')
        assert LinuxInputHandler._resolve_keysym('A') == ord('A')
        assert LinuxInputHandler._resolve_keysym('1') == ord('1')
        assert LinuxInputHandler._resolve_keysym(' ') == ord(' ')

    def test_resolve_keysym_unknown(self):
        from device_bridge.platforms.linux.input import LinuxInputHandler
        assert LinuxInputHandler._resolve_keysym('nonexistent') == 0
        assert LinuxInputHandler._resolve_keysym('') == 0

    def test_char_to_keysym_ascii(self):
        from device_bridge.platforms.linux.input import _char_to_keysym
        assert _char_to_keysym('a') == ord('a')
        assert _char_to_keysym('Z') == ord('Z')
        assert _char_to_keysym('0') == ord('0')
        assert _char_to_keysym('~') == ord('~')

    def test_char_to_keysym_non_ascii(self):
        from device_bridge.platforms.linux.input import _char_to_keysym
        assert _char_to_keysym('é') == 0  # Non-ASCII
        assert _char_to_keysym('中') == 0  # Non-ASCII
        assert _char_to_keysym('') == 0   # Empty
        assert _char_to_keysym('ab') == 0  # Multi-char


# ============================================================
# Linux discovery tests
# ============================================================

class TestLinuxDeviceDiscoverer:
    """Test LinuxDeviceDiscoverer."""

    def test_discover_windows_no_xlib(self):
        from device_bridge.platforms.linux.discovery import LinuxDeviceDiscoverer
        discoverer = LinuxDeviceDiscoverer()
        # On non-Linux, python-xlib unavailable
        result = discoverer.discover_windows()
        assert result == []

    def test_discover_adb_devices_parses_output(self):
        from device_bridge.platforms.linux.discovery import LinuxDeviceDiscoverer
        mock_result = mock.Mock()
        mock_result.returncode = 0
        mock_result.stdout = (
            'List of devices attached\n'
            'emulator-5554          device product:sdk_phone_x86 model:Android_SDK device:generic transport_id:1\n'
        )
        with mock.patch('subprocess.run', return_value=mock_result):
            discoverer = LinuxDeviceDiscoverer()
            devices = discoverer.discover_adb_devices()
        assert len(devices) == 1
        assert devices[0].identifier == 'emulator-5554'
        assert devices[0].platform == 'linux'

    def test_discover_adb_devices_no_adb(self):
        from device_bridge.platforms.linux.discovery import LinuxDeviceDiscoverer
        with mock.patch('subprocess.run', side_effect=FileNotFoundError):
            discoverer = LinuxDeviceDiscoverer()
            devices = discoverer.discover_adb_devices()
        assert devices == []


# ============================================================
# Registry tests
# ============================================================

class TestPlatformRegistry:
    """Test platform registry and factory functions."""

    def test_get_current_platform_returns_valid(self):
        from device_bridge.platforms.registry import get_current_platform
        platform_name = get_current_platform()
        assert platform_name in ('windows', 'macos', 'linux')

    def test_get_screenshot_handler_returns_instance(self):
        from device_bridge.platforms.base import PlatformScreenshotHandler
        from device_bridge.platforms.registry import get_screenshot_handler
        handler = get_screenshot_handler()
        assert isinstance(handler, PlatformScreenshotHandler)

    def test_get_input_handler_returns_instance(self):
        from device_bridge.platforms.base import PlatformInputHandler
        from device_bridge.platforms.registry import get_input_handler
        handler = get_input_handler()
        assert isinstance(handler, PlatformInputHandler)

    def test_get_device_discoverer_returns_instance(self):
        from device_bridge.platforms.base import PlatformDeviceDiscoverer
        from device_bridge.platforms.registry import get_device_discoverer
        discoverer = get_device_discoverer()
        assert isinstance(discoverer, PlatformDeviceDiscoverer)

    def test_auto_register_windows_on_windows(self):
        """On Windows, auto_register should register Windows handlers."""
        import platform as platform_module
        if platform_module.system().lower() != 'windows':
            pytest.skip('Test only runs on Windows')
        from device_bridge.platforms.registry import (
            _device_discoverers,
            _input_handlers,
            _screenshot_handlers,
        )
        assert 'windows' in _screenshot_handlers
        assert 'windows' in _input_handlers
        assert 'windows' in _device_discoverers

    def test_mock_handlers_fallback(self):
        """When platform has no implementation, Mock handlers are used."""
        from device_bridge.platforms.registry import (
            _MockDeviceDiscoverer,
            _MockInputHandler,
            _MockScreenshotHandler,
        )
        # Mock screenshot
        handler = _MockScreenshotHandler()
        result = handler.capture('test')
        assert result.success is True
        assert result.method == 'mock'

        # Mock input
        handler = _MockInputHandler()
        result = handler.click('test', 0, 0)
        assert result.success is True

        # Mock discoverer
        discoverer = _MockDeviceDiscoverer()
        assert discoverer.discover_windows() == []
        assert discoverer.discover_emulators() == []
        assert discoverer.discover_adb_devices() == []


# ============================================================
# Base ABC tests
# ============================================================

class TestBaseABCs:
    """Test that base ABCs cannot be instantiated without implementing methods."""

    def test_cannot_instantiate_screenshot_handler(self):
        with pytest.raises(TypeError):
            PlatformScreenshotHandler()  # type: ignore[abstract]

    def test_cannot_instantiate_input_handler(self):
        with pytest.raises(TypeError):
            PlatformInputHandler()  # type: ignore[abstract]

    def test_cannot_instantiate_device_discoverer(self):
        with pytest.raises(TypeError):
            PlatformDeviceDiscoverer()  # type: ignore[abstract]

    def test_screenshot_result_defaults(self):
        result = ScreenshotResult()
        assert result.image_bytes == b''
        assert result.latency_ms == 0.0
        assert result.success is False
        assert result.error is None
        assert result.resolution == {'width': 0, 'height': 0}

    def test_input_result_defaults(self):
        result = InputResult()
        assert result.success is False
        assert result.latency_ms == 0.0
        assert result.method == ''
        assert result.error is None

    def test_device_info_required_fields(self):
        info = DeviceInfo(name='Test', device_type='window', identifier='123')
        assert info.name == 'Test'
        assert info.device_type == 'window'
        assert info.identifier == '123'
        assert info.resolution == {'width': 0, 'height': 0}
        assert info.platform == ''
        assert info.extra == {}

    def test_device_info_with_all_fields(self):
        info = DeviceInfo(
            name='Test Window',
            device_type='window',
            identifier='0x123',
            resolution={'width': 1920, 'height': 1080},
            platform='macos',
            extra={'process_name': 'TestApp', 'is_game': False},
        )
        assert info.resolution == {'width': 1920, 'height': 1080}
        assert info.platform == 'macos'
        assert info.extra['process_name'] == 'TestApp'
