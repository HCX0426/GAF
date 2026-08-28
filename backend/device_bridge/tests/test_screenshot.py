"""Tests for the Windows platform screenshot handler."""

from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from device_bridge.platforms.windows.screenshot import WindowsScreenshotHandler

pytestmark = pytest.mark.e2e


class TestAvailableMethods(TestCase):
    """Tests for method availability discovery."""

    @patch('device_bridge.platforms.windows.screenshot.importlib.util.find_spec')
    def test_all_methods_reported_available_when_modules_exist(self, mock_find_spec):
        mock_find_spec.return_value = MagicMock()
        handler = WindowsScreenshotHandler()
        available = handler.available_methods()

        # WGC was removed in TD-125 (backend had no real WGC impl, only a mock).
        for method in ['BitBlt', 'PrintWindow', 'DXGI', 'GDI']:
            self.assertIn(method, available)
        self.assertNotIn('WGC', available)

    @patch('device_bridge.platforms.windows.screenshot.importlib.util.find_spec')
    def test_methods_filtered_when_modules_missing(self, mock_find_spec):
        mock_find_spec.return_value = None
        handler = WindowsScreenshotHandler()
        available = handler.available_methods()

        self.assertEqual(available, ['mock'])


class TestMethodAvailability(TestCase):
    """Tests for _check_method_available helper."""

    def test_unknown_method_returns_false(self):
        handler = WindowsScreenshotHandler()
        self.assertFalse(handler._check_method_available('UnknownMethod'))


class TestCaptureDxgi(TestCase):
    """Tests for the DXGI screenshot path."""

    def setUp(self):
        self.handler = WindowsScreenshotHandler()

    @patch('cv2.imencode')
    @patch('cv2.cvtColor')
    @patch('device_bridge.platforms.windows._dxgi.DXGICapture')
    def test_dxgi_capture_success(self, mock_capture_class, mock_cvt_color, mock_imencode):
        mock_instance = MagicMock()
        mock_instance.initialize.return_value = True
        # _capture_dxgi now uses capture_window(hwnd) instead of capture() (TD-124).
        mock_instance.capture_window.return_value = MagicMock(shape=(1080, 1920, 3))
        mock_capture_class.return_value = mock_instance

        mock_buf = MagicMock()
        mock_buf.tobytes.return_value = b'fake-dxgi-image'
        mock_cvt_color.return_value = MagicMock()
        mock_imencode.return_value = (True, mock_buf)

        # Use a non-zero hwnd: capture_window(0) returns None (early exit).
        result = self.handler._capture_dxgi('0x12345')

        self.assertTrue(result['success'])
        self.assertEqual(result['image_bytes'], b'fake-dxgi-image')
        self.assertEqual(result['resolution'], {'width': 1920, 'height': 1080})
        mock_instance.release.assert_called_once()

    @patch('device_bridge.platforms.windows._dxgi.DXGICapture')
    def test_dxgi_capture_initialization_failure(self, mock_capture_class):
        mock_instance = MagicMock()
        mock_instance.initialize.return_value = False
        mock_capture_class.return_value = mock_instance

        result = self.handler._capture_dxgi('0x12345')

        self.assertFalse(result['success'])
        self.assertIn('DXGI initialization failed', result['error'])
        mock_instance.release.assert_called_once()

    @patch('device_bridge.platforms.windows._dxgi.DXGICapture')
    def test_dxgi_capture_frame_none(self, mock_capture_class):
        mock_instance = MagicMock()
        mock_instance.initialize.return_value = True
        # capture_window returns None when full-desktop capture() returns None
        # or hwnd is invalid (TD-124).
        mock_instance.capture_window.return_value = None
        mock_capture_class.return_value = mock_instance

        result = self.handler._capture_dxgi('0x12345')

        self.assertFalse(result['success'])
        self.assertIn('frame acquisition returned None', result['error'])
        mock_instance.release.assert_called_once()


class TestCaptureGdi(TestCase):
    """Tests for the GDI screenshot path."""

    @patch.object(WindowsScreenshotHandler, '_capture_bitblt')
    def test_gdi_delegates_to_bitblt(self, mock_bitblt):
        mock_bitblt.return_value = {'success': True, 'method': 'BitBlt'}
        handler = WindowsScreenshotHandler()

        result = handler._capture_gdi('12345')

        self.assertEqual(result, {'success': True, 'method': 'BitBlt'})
        mock_bitblt.assert_called_once_with('12345')


class TestGameWindowDetection(TestCase):
    """TD-334: backend 截图 handler 应识别游戏窗口类并主动降级到 PrintWindow."""

    def test_is_game_window_unity(self):
        """UnityWndClass 应识别为游戏窗口."""
        handler = WindowsScreenshotHandler()
        with patch.object(WindowsScreenshotHandler, '_get_window_class_name', return_value='UnityWndClass'):
            self.assertTrue(handler._is_game_window('0x12345'))

    def test_is_game_window_unreal(self):
        """UnrealWindow 应识别为游戏窗口."""
        handler = WindowsScreenshotHandler()
        with patch.object(WindowsScreenshotHandler, '_get_window_class_name', return_value='UnrealWindow'):
            self.assertTrue(handler._is_game_window('0x12345'))

    def test_is_game_window_standard_window(self):
        """标准窗口类 (Notepad 等) 不应识别为游戏窗口."""
        handler = WindowsScreenshotHandler()
        with patch.object(WindowsScreenshotHandler, '_get_window_class_name', return_value='Notepad'):
            self.assertFalse(handler._is_game_window('0x12345'))

    def test_is_game_window_empty_class(self):
        """空类名 (hwnd 无效) 不应识别为游戏窗口."""
        handler = WindowsScreenshotHandler()
        with patch.object(WindowsScreenshotHandler, '_get_window_class_name', return_value=''):
            self.assertFalse(handler._is_game_window('0x12345'))


class TestGameWindowRedirect(TestCase):
    """TD-334: 游戏窗口上 BitBlt/GDI/DXGI 主动 redirect 到 PrintWindow."""

    def setUp(self):
        self.handler = WindowsScreenshotHandler()

    @patch.object(WindowsScreenshotHandler, '_capture_printwindow')
    @patch.object(WindowsScreenshotHandler, '_is_game_window', return_value=True)
    def test_bitblt_redirects_to_printwindow_on_game_window(self, mock_is_game, mock_printwindow):
        """BitBlt 在游戏窗口上应直接走 PrintWindow, 不调用 _capture_bitblt."""
        mock_printwindow.return_value = {'success': True, 'image_bytes': b'fake'}
        result = self.handler._do_capture('0x12345', 'BitBlt')
        self.assertTrue(result['success'])
        mock_printwindow.assert_called_once_with('0x12345')

    @patch.object(WindowsScreenshotHandler, '_capture_printwindow')
    @patch.object(WindowsScreenshotHandler, '_is_game_window', return_value=True)
    def test_gdi_redirects_to_printwindow_on_game_window(self, mock_is_game, mock_printwindow):
        """GDI 在游戏窗口上应直接走 PrintWindow."""
        mock_printwindow.return_value = {'success': True, 'image_bytes': b'fake'}
        result = self.handler._do_capture('0x12345', 'GDI')
        self.assertTrue(result['success'])
        mock_printwindow.assert_called_once_with('0x12345')

    @patch.object(WindowsScreenshotHandler, '_capture_printwindow')
    @patch.object(WindowsScreenshotHandler, '_is_game_window', return_value=True)
    def test_dxgi_redirects_to_printwindow_on_game_window(self, mock_is_game, mock_printwindow):
        """DXGI 在游戏窗口上应直接走 PrintWindow."""
        mock_printwindow.return_value = {'success': True, 'image_bytes': b'fake'}
        result = self.handler._do_capture('0x12345', 'DXGI')
        self.assertTrue(result['success'])
        mock_printwindow.assert_called_once_with('0x12345')

    @patch.object(WindowsScreenshotHandler, '_capture_bitblt')
    @patch.object(WindowsScreenshotHandler, '_is_game_window', return_value=False)
    def test_bitblt_not_redirected_on_standard_window(self, mock_is_game, mock_bitblt):
        """标准窗口上 BitBlt 不应 redirect, 走原路径."""
        mock_bitblt.return_value = {'success': True, 'image_bytes': b'fake'}
        result = self.handler._do_capture('0x12345', 'BitBlt')
        self.assertTrue(result['success'])
        mock_bitblt.assert_called_once_with('0x12345')

    @patch.object(WindowsScreenshotHandler, '_capture_printwindow')
    @patch.object(WindowsScreenshotHandler, '_is_game_window', return_value=True)
    def test_printwindow_not_redirected_on_game_window(self, mock_is_game, mock_printwindow):
        """PrintWindow 在游戏窗口上应直接走原路径 (不需要 redirect)."""
        mock_printwindow.return_value = {'success': True, 'image_bytes': b'fake'}
        result = self.handler._do_capture('0x12345', 'PrintWindow')
        self.assertTrue(result['success'])
        mock_printwindow.assert_called_once_with('0x12345')

    @patch.object(WindowsScreenshotHandler, '_capture_printwindow')
    @patch.object(WindowsScreenshotHandler, '_is_game_window', return_value=False)
    def test_adb_methods_not_redirected(self, mock_is_game, mock_printwindow):
        """ADB 截图方法 (emulator) 不应被 game-window redirect 影响."""
        # ADB methods route to _capture_adb before any game-window check
        from device_bridge.platforms.windows.screenshot import ADB_SCREENSHOT_METHODS
        for adb_method in ADB_SCREENSHOT_METHODS:
            mock_printwindow.reset_mock()
            # _capture_adb 内部会 import _adb_screenshot, 在非 Windows 测试环境
            # 会 ImportError, 我们直接 mock _capture_adb 避免依赖
            with patch.object(self.handler, '_capture_adb', return_value={'success': True}) as mock_adb:
                result = self.handler._do_capture('emulator-5554', adb_method)
                self.assertTrue(result['success'])
                mock_adb.assert_called_once()
                mock_printwindow.assert_not_called()
