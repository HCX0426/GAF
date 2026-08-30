"""P0-1 DXGI integration tests for ScreenshotManager.

Validates the lazy-init + reuse + release lifecycle of the DXGICapture
instance wired into ScreenshotManager.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

pytestmark = pytest.mark.unit


class TestScreenshotManagerDxgiWiring:
    """P0-1 DXGI integration into ScreenshotManager."""

    def test_dxgi_instance_starts_none(self):
        from platforms.windows.screenshot import ScreenshotManager

        mgr = ScreenshotManager()
        assert mgr._dxgi_instance is None

    def test_set_hwnd_releases_dxgi(self):
        """set_hwnd should release any cached DXGI instance."""
        from platforms.windows.screenshot import ScreenshotManager

        mgr = ScreenshotManager()
        # Inject a fake instance to verify release is called.
        fake_dxgi = MagicMock()
        mgr._dxgi_instance = fake_dxgi

        mgr.set_hwnd(12345)

        fake_dxgi.release.assert_called_once()
        assert mgr._dxgi_instance is None

    def test_release_releases_dxgi(self):
        """release() should release the DXGI instance."""
        from platforms.windows.screenshot import ScreenshotManager

        mgr = ScreenshotManager()
        fake_dxgi = MagicMock()
        mgr._dxgi_instance = fake_dxgi

        mgr.release()

        fake_dxgi.release.assert_called_once()
        assert mgr._dxgi_instance is None

    def test_capture_dxgi_initializes_and_captures(self):
        """_capture_dxgi should lazily initialize DXGICapture and call capture()."""
        from platforms.windows.screenshot import ScreenshotManager

        mgr = ScreenshotManager(hwnd=0)
        fake_dxgi = MagicMock()
        fake_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        fake_dxgi.capture.return_value = fake_frame

        with patch("platforms.windows.dxgi_capture.DXGICapture") as mock_dxgi:
            mock_dxgi.return_value = fake_dxgi
            result = mgr._capture_dxgi()

        assert result is fake_frame
        fake_dxgi.initialize.assert_called_once_with(0)
        fake_dxgi.capture.assert_called_once()
        assert mgr._dxgi_instance is fake_dxgi

    def test_capture_dxgi_raises_on_init_failure(self):
        """DXGI init failure should raise RuntimeError so the degradation chain can skip it."""
        from platforms.windows.screenshot import ScreenshotManager

        mgr = ScreenshotManager(hwnd=0)
        fake_dxgi = MagicMock()
        fake_dxgi.initialize.return_value = False

        with patch("platforms.windows.dxgi_capture.DXGICapture") as mock_dxgi:
            mock_dxgi.return_value = fake_dxgi
            with pytest.raises(RuntimeError, match="DXGI 初始化失败"):
                mgr._capture_dxgi()

    def test_capture_dxgi_reuses_instance(self):
        """Subsequent _capture_dxgi calls should reuse the existing DXGICapture instance."""
        from platforms.windows.screenshot import ScreenshotManager

        mgr = ScreenshotManager(hwnd=0)
        fake_dxgi = MagicMock()
        fake_dxgi.capture.return_value = np.zeros((5, 5, 3), dtype=np.uint8)
        mgr._dxgi_instance = fake_dxgi

        with patch("platforms.windows.dxgi_capture.DXGICapture") as mock_dxgi:
            mgr._capture_dxgi()
            mgr._capture_dxgi()

        mock_dxgi.assert_not_called()  # No new instance created
        assert fake_dxgi.capture.call_count == 2

    def test_capture_dxgi_with_none_hwnd_uses_zero(self):
        """When hwnd is None, _capture_dxgi should pass 0 to DXGICapture.initialize."""
        from platforms.windows.screenshot import ScreenshotManager

        mgr = ScreenshotManager(hwnd=None)
        fake_dxgi = MagicMock()
        fake_dxgi.capture.return_value = np.zeros((5, 5, 3), dtype=np.uint8)

        with patch("platforms.windows.dxgi_capture.DXGICapture") as mock_dxgi:
            mock_dxgi.return_value = fake_dxgi
            mgr._capture_dxgi()

        fake_dxgi.initialize.assert_called_once_with(0)

    def test_capture_dxgi_import_error_raises_runtime_error(self):
        """ImportError from dxgi_capture should be re-raised as RuntimeError."""
        from platforms.windows.screenshot import ScreenshotManager

        mgr = ScreenshotManager(hwnd=0)

        # Force the import inside _capture_dxgi to fail.
        with (
            patch.dict("sys.modules", {"platforms.windows.dxgi_capture": None}),
            pytest.raises(RuntimeError, match="DXGI 模块不可用"),
        ):
            mgr._capture_dxgi()
