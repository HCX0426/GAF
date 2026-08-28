"""Tests for ADB screenshot method chain and selection."""

from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from device_bridge.platforms.windows import _adb_screenshot

pytestmark = pytest.mark.e2e


class TestGetAvailableMethods(TestCase):
    """Tests for get_available_methods helper."""

    def test_ldplayer_methods(self):
        methods = _adb_screenshot.get_available_methods('ldplayer')
        self.assertIn('ld_opengl', methods)
        self.assertIn('screencap', methods)
        self.assertIn('screencap_png', methods)
        # BlueStacks method belongs to the BlueStacks chain only.
        self.assertNotIn('bluestacks', methods)

    def test_bluestacks_methods(self):
        methods = _adb_screenshot.get_available_methods('bluestacks')
        self.assertIn('bluestacks', methods)
        self.assertIn('screencap', methods)
        self.assertIn('screencap_png', methods)

    def test_mumu_methods(self):
        methods = _adb_screenshot.get_available_methods('mumu')
        self.assertIn('nemuipe', methods)
        self.assertIn('screencap', methods)
        self.assertIn('screencap_png', methods)

    def test_unknown_emulator_falls_back_to_default(self):
        methods = _adb_screenshot.get_available_methods('unknown')
        self.assertIn('droidcast', methods)
        self.assertIn('screencap', methods)
        self.assertIn('screencap_png', methods)

    def test_case_insensitive(self):
        self.assertEqual(
            _adb_screenshot.get_available_methods('LDPlayer'),
            _adb_screenshot.get_available_methods('ldplayer'),
        )


class TestCaptureMethodSelection(TestCase):
    """Tests for capture() with explicit method selection."""

    def setUp(self):
        _adb_screenshot.invalidate_cache('serial-1')

    @patch.dict(
        _adb_screenshot._ALL_METHODS,
        {'fast': lambda s, a: b'fast', 'slow': lambda s, a: b'slow'},
        clear=False,
    )
    @patch.object(_adb_screenshot, '_EMULATOR_CHAINS', {
        'testemu': ['slow', 'fast'],
        '__default__': ['fast', 'slow'],
    })
    def test_capture_uses_chain_when_no_method_given(self):
        img_bytes, method = _adb_screenshot.capture(
            'serial-1', adb_executable='adb',
            emulator_type='testemu', use_cache=False,
        )
        self.assertEqual(method, 'slow')
        self.assertEqual(img_bytes, b'slow')

    @patch.dict(
        _adb_screenshot._ALL_METHODS,
        {'fast': lambda s, a: b'fast', 'slow': lambda s, a: b'slow'},
        clear=False,
    )
    @patch.object(_adb_screenshot, '_EMULATOR_CHAINS', {
        'testemu': ['slow', 'fast'],
        '__default__': ['fast', 'slow'],
    })
    def test_capture_forces_specific_method(self):
        img_bytes, method = _adb_screenshot.capture(
            'serial-1', adb_executable='adb',
            emulator_type='testemu', use_cache=False, method='fast',
        )
        self.assertEqual(method, 'fast')
        self.assertEqual(img_bytes, b'fast')

    @patch.dict(
        _adb_screenshot._ALL_METHODS,
        {'existing': lambda s, a: b'existing'},
        clear=False,
    )
    def test_capture_unknown_method_returns_empty(self):
        img_bytes, method = _adb_screenshot.capture(
            'serial-1', adb_executable='adb',
            emulator_type='ldplayer', use_cache=False, method='missing',
        )
        self.assertIsNone(img_bytes)
        self.assertEqual(method, '')

    @patch.dict(
        _adb_screenshot._ALL_METHODS,
        {'fails': lambda s, a: None},
        clear=False,
    )
    def test_capture_forced_method_failure_returns_empty(self):
        img_bytes, method = _adb_screenshot.capture(
            'serial-1', adb_executable='adb',
            emulator_type='ldplayer', use_cache=False, method='fails',
        )
        self.assertIsNone(img_bytes)
        self.assertEqual(method, '')


class TestBlueStacksCapture(TestCase):
    """Tests for the BlueStacks dedicated screenshot method."""

    def setUp(self):
        self.serial = 'emulator-5554'
        self.adb = 'adb'

    @patch('device_bridge.platforms.windows._adb_screenshot.subprocess.run')
    @patch('device_bridge.platforms.windows._adb_screenshot.urllib.request.urlopen')
    def test_bluestacks_capture_success(self, mock_urlopen, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr=b'')
        mock_response = MagicMock()
        mock_response.read.return_value = b'fake-image-bytes' * 20
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = _adb_screenshot._capture_by_bluestacks(self.serial, self.adb)

        self.assertEqual(result, b'fake-image-bytes' * 20)
        mock_run.assert_called_once_with(
            [self.adb, '-s', self.serial, 'forward', 'tcp:55555', 'tcp:55555'],
            capture_output=True, timeout=5,
        )

    @patch('device_bridge.platforms.windows._adb_screenshot.subprocess.run')
    @patch('device_bridge.platforms.windows._adb_screenshot.urllib.request.urlopen')
    def test_bluestacks_capture_forward_failure(self, mock_urlopen, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr=b'cannot bind')

        result = _adb_screenshot._capture_by_bluestacks(self.serial, self.adb)

        self.assertIsNone(result)
        mock_urlopen.assert_not_called()

    @patch('device_bridge.platforms.windows._adb_screenshot.subprocess.run')
    @patch('device_bridge.platforms.windows._adb_screenshot.urllib.request.urlopen')
    def test_bluestacks_capture_empty_response(self, mock_urlopen, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr=b'')
        mock_response = MagicMock()
        mock_response.read.return_value = b''
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_response)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = _adb_screenshot._capture_by_bluestacks(self.serial, self.adb)

        self.assertIsNone(result)
