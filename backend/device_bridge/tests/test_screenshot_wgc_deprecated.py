"""Tests for WGC deprecation in backend screenshot handler (TD-125).

Backend never had a real WGC implementation — ``_wgc.py`` was a mock that
returned a fixed 1920x1080 blue image regardless of hwnd. TD-125 removes the
mock and makes ``_capture_wgc`` delegate to PrintWindow (hwnd-isolated, safe).

These tests verify:
  1. ``_capture_wgc`` delegates to ``_capture_printwindow`` (with warning).
  2. ``available_methods()`` does not advertise 'WGC'.
  3. ``_do_capture(target, 'WGC')`` still returns a result (via delegate).
  4. ``MULTI_GAME_SAFE_SCREENSHOT_METHODS`` no longer contains 'wgc'.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from device_bridge.platforms.windows.screenshot import WindowsScreenshotHandler

pytestmark = pytest.mark.e2e


class TestCaptureWgcDelegatesToPrintWindow(TestCase):
    """_capture_wgc delegates to _capture_printwindow (TD-125)."""

    @patch.object(WindowsScreenshotHandler, '_capture_printwindow')
    def test_capture_wgc_delegates_to_printwindow(self, mock_printwindow):
        """_capture_wgc should call _capture_printwindow with the same hwnd."""
        mock_printwindow.return_value = {
            'success': True,
            'image_bytes': b'fake-printwindow-image',
            'resolution': {'width': 800, 'height': 600},
        }

        handler = WindowsScreenshotHandler()
        result = handler._capture_wgc('0x12345')

        mock_printwindow.assert_called_once_with('0x12345')
        self.assertTrue(result['success'])
        self.assertEqual(result['image_bytes'], b'fake-printwindow-image')

    @patch.object(WindowsScreenshotHandler, '_capture_printwindow')
    def test_capture_wgc_logs_deprecation_warning(self, mock_printwindow):
        """_capture_wgc should emit a warning log explaining the delegation."""
        mock_printwindow.return_value = {'success': True, 'image_bytes': b'x'}

        handler = WindowsScreenshotHandler()
        with patch('device_bridge.platforms.windows.screenshot.logger') as mock_logger:
            handler._capture_wgc('0x12345')

        mock_logger.warning.assert_called_once()
        # Warning message should mention TD-125 and the delegation.
        warning_msg = mock_logger.warning.call_args[0][0]
        self.assertIn('TD-125', warning_msg)
        self.assertIn('PrintWindow', warning_msg)


class TestWgcNotAdvertisedInAvailableMethods(TestCase):
    """available_methods() must not advertise 'WGC' (TD-125)."""

    @patch('device_bridge.platforms.windows.screenshot.importlib.util.find_spec')
    def test_wgc_not_in_available_methods(self, mock_find_spec):
        """When all real modules exist, 'WGC' should not be in the list."""
        mock_find_spec.return_value = MagicMock()

        handler = WindowsScreenshotHandler()
        available = handler.available_methods()

        self.assertNotIn('WGC', available)
        # Real methods should still be present.
        for method in ['BitBlt', 'PrintWindow', 'DXGI', 'GDI']:
            self.assertIn(method, available)


class TestDoCaptureWgcRoutesToDelegate(TestCase):
    """_do_capture(target, 'WGC') should still work via _capture_wgc delegate."""

    @patch.object(WindowsScreenshotHandler, '_capture_printwindow')
    def test_do_capture_wgc_returns_result_via_delegate(self, mock_printwindow):
        """Calling _do_capture with 'WGC' should route through _capture_wgc
        (which delegates to PrintWindow) and return a successful result."""
        mock_printwindow.return_value = {
            'success': True,
            'image_bytes': b'fake-image',
            'resolution': {'width': 800, 'height': 600},
        }

        handler = WindowsScreenshotHandler()
        result = handler._do_capture('0x12345', 'WGC')

        mock_printwindow.assert_called_once_with('0x12345')
        self.assertTrue(result['success'])

    @patch.object(WindowsScreenshotHandler, '_capture_printwindow')
    def test_do_capture_wgc_lowercase_routes_to_delegate(self, mock_printwindow):
        """Method names from device configs are lowercased ('wgc'); the
        normalizer maps them to 'WGC' which routes to the delegate.

        Uses ``capture()`` (the public entry point) so the method name flows
        through ``_normalize_screenshot_method`` before reaching ``_do_capture``.
        """
        mock_printwindow.return_value = {
            'success': True,
            'image_bytes': b'fake-image',
            'resolution': {'width': 800, 'height': 600},
        }

        handler = WindowsScreenshotHandler()
        # Pass lowercase 'wgc' — capture() normalizes to 'WGC' before routing.
        result = handler.capture('0x12345', 'wgc')

        mock_printwindow.assert_called_once_with('0x12345')
        self.assertTrue(result.success)


class TestWgcRemovedFromMultiGameSafeList(TestCase):
    """MULTI_GAME_SAFE_SCREENSHOT_METHODS must not contain 'wgc' (TD-125 fix).

    Spec A incorrectly listed 'wgc' as safe because it was a mock (returned
    a fixed image, no real hwnd isolation). With the mock removed (TD-125),
    'wgc' is no longer in the safe list — devices configured with 'wgc'
    must be treated as needing fallback to a real safe method.
    """

    def test_wgc_not_in_safe_screenshot_methods(self):
        """Import via the Django app registry (agents.models, not backend.agents.models)
        so the model class resolves its app_label correctly."""
        from agents.models import MULTI_GAME_SAFE_SCREENSHOT_METHODS

        self.assertNotIn('wgc', MULTI_GAME_SAFE_SCREENSHOT_METHODS)
        # Real safe methods should still be present.
        for method in ['printwindow', 'bitblt', 'gdi']:
            self.assertIn(method, MULTI_GAME_SAFE_SCREENSHOT_METHODS)

    def test_wgc_module_file_deleted(self):
        """The _wgc.py mock file should no longer exist on disk."""
        import os

        wgc_path = os.path.join(
            os.path.dirname(__file__), '..', 'platforms', 'windows', '_wgc.py'
        )
        self.assertFalse(
            os.path.exists(wgc_path),
            f'_wgc.py should be deleted (TD-125), but exists at {wgc_path}',
        )
