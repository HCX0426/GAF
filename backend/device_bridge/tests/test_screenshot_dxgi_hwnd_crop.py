"""Tests for DXGICapture.capture_window(hwnd) — TD-124 per-window crop.

Verifies that the DXGI Desktop Duplication capture path correctly crops the
full-desktop frame to the target window's rect, enabling per-window capture
in multi-window / multi-game scenarios.

The tests patch ``DXGICapture._get_window_rect`` (extracted helper) instead
of monkey-patching ``ctypes.wintypes.RECT`` so they do not depend on the
internal ``ctypes.byref`` plumbing of the real Win32 call.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from django.test import TestCase

from device_bridge.platforms.windows._dxgi import DXGICapture

pytestmark = pytest.mark.e2e


def _make_rect(left, top, right, bottom):
    """Create a mock RECT-like object with the given coordinates."""
    rect = MagicMock()
    rect.left = left
    rect.top = top
    rect.right = right
    rect.bottom = bottom
    return rect


def _make_output_desc(desktop_left, desktop_top, desktop_right, desktop_bottom):
    """Create a mock DXGI_OUTPUT_DESC with the given DesktopCoordinates."""
    desc = MagicMock()
    desc.DesktopCoordinates = _make_rect(
        desktop_left, desktop_top, desktop_right, desktop_bottom
    )
    return desc


class TestCaptureWindowZeroHwnd(TestCase):
    """capture_window(0) should return None immediately (TD-124)."""

    def test_capture_window_returns_none_for_zero_hwnd(self):
        cap = DXGICapture()
        self.assertIsNone(cap.capture_window(0))

    def test_capture_window_returns_none_for_negative_hwnd(self):
        cap = DXGICapture()
        # Negative hwnd is treated as falsy by `if not hwnd` check.
        self.assertIsNone(cap.capture_window(-1))


class TestCaptureWindowCaptureFailure(TestCase):
    """capture_window returns None when underlying capture() fails."""

    @patch.object(DXGICapture, 'capture')
    @patch.object(DXGICapture, '_get_window_rect')
    def test_capture_window_returns_none_when_capture_returns_none(
        self, mock_get_rect, mock_capture
    ):
        cap = DXGICapture()
        cap._initialized = True
        cap._width = 1920
        cap._height = 1080
        cap._output_desc = _make_output_desc(0, 0, 1920, 1080)

        mock_get_rect.return_value = _make_rect(100, 100, 500, 400)
        mock_capture.return_value = None

        result = cap.capture_window(0x12345)
        self.assertIsNone(result)


class TestCaptureWindowCrop(TestCase):
    """capture_window correctly slices the full-desktop frame to the window rect."""

    @patch.object(DXGICapture, 'capture')
    @patch.object(DXGICapture, '_get_window_rect')
    def test_capture_window_crops_to_window_rect(
        self, mock_get_rect, mock_capture
    ):
        """Window at (100,100)-(500,400) on a 1920x1080 desktop should yield
        a 400x300 image cropped from the full-desktop frame."""
        cap = DXGICapture()
        cap._initialized = True
        cap._width = 1920
        cap._height = 1080
        cap._output_desc = _make_output_desc(0, 0, 1920, 1080)

        # Build a deterministic full-desktop frame: pixel value = row index.
        full_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        for y in range(1080):
            full_frame[y, :, 0] = y % 256
        mock_capture.return_value = full_frame

        mock_get_rect.return_value = _make_rect(100, 100, 500, 400)

        result = cap.capture_window(0x12345)

        self.assertIsNotNone(result)
        # Expected crop: rows 100-400 (300 rows), cols 100-500 (400 cols).
        self.assertEqual(result.shape, (300, 400, 3))
        # Verify the crop actually came from the full frame: row 100 of the
        # result should equal row 100 of the full frame (column-shifted).
        np.testing.assert_array_equal(result[0, :, 0], full_frame[100, 100:500, 0])


class TestCaptureWindowClipToDesktop(TestCase):
    """capture_window clips window rect to desktop bounds."""

    @patch.object(DXGICapture, 'capture')
    @patch.object(DXGICapture, '_get_window_rect')
    def test_capture_window_clips_window_extending_beyond_desktop(
        self, mock_get_rect, mock_capture
    ):
        """Window at (-50,-50)-(2000,2000) on a 1920x1080 desktop should be
        clipped to (0,0)-(1920,1080)."""
        cap = DXGICapture()
        cap._initialized = True
        cap._width = 1920
        cap._height = 1080
        cap._output_desc = _make_output_desc(0, 0, 1920, 1080)

        full_frame = np.ones((1080, 1920, 3), dtype=np.uint8) * 128
        mock_capture.return_value = full_frame

        mock_get_rect.return_value = _make_rect(-50, -50, 2000, 2000)

        result = cap.capture_window(0x12345)

        self.assertIsNotNone(result)
        # Clipped to desktop bounds: 0..1920 (width) and 0..1080 (height).
        self.assertEqual(result.shape, (1080, 1920, 3))


class TestCaptureWindowFullyOutsideDesktop(TestCase):
    """capture_window returns None when window is fully outside the desktop."""

    @patch.object(DXGICapture, 'capture')
    @patch.object(DXGICapture, '_get_window_rect')
    def test_capture_window_returns_none_when_window_fully_outside(
        self, mock_get_rect, mock_capture
    ):
        cap = DXGICapture()
        cap._initialized = True
        cap._width = 1920
        cap._height = 1080
        cap._output_desc = _make_output_desc(0, 0, 1920, 1080)

        # Window fully to the left of the desktop.
        mock_get_rect.return_value = _make_rect(-500, 0, -100, 500)

        result = cap.capture_window(0x12345)

        self.assertIsNone(result)
        # capture() should not be called since the window is fully outside.
        mock_capture.assert_not_called()


class TestCaptureWindowEmptyRect(TestCase):
    """capture_window returns None for empty / invalid window rects."""

    @patch.object(DXGICapture, '_get_window_rect')
    def test_capture_window_returns_none_for_empty_rect(self, mock_get_rect):
        cap = DXGICapture()
        cap._initialized = True
        cap._width = 1920
        cap._height = 1080

        # right <= left and bottom <= top → empty rect.
        mock_get_rect.return_value = _make_rect(100, 100, 100, 100)

        result = cap.capture_window(0x12345)
        self.assertIsNone(result)

    @patch.object(DXGICapture, '_get_window_rect')
    def test_capture_window_returns_none_when_get_window_rect_fails(
        self, mock_get_rect
    ):
        cap = DXGICapture()
        cap._initialized = True
        cap._width = 1920
        cap._height = 1080

        # _get_window_rect returns None when GetWindowRect fails.
        mock_get_rect.return_value = None

        result = cap.capture_window(0x12345)
        self.assertIsNone(result)


class TestCaptureWindowOutputDescOrigin(TestCase):
    """capture_window uses _output_desc.DesktopCoordinates for desktop origin."""

    @patch.object(DXGICapture, 'capture')
    @patch.object(DXGICapture, '_get_window_rect')
    def test_capture_window_uses_non_zero_desktop_origin(
        self, mock_get_rect, mock_capture
    ):
        """When the desktop origin is (1024, 0) (secondary monitor on the
        right), a window at screen (1024+100, 100)-(1024+500, 400) should be
        cropped to frame[100:400, 100:500]."""
        cap = DXGICapture()
        cap._initialized = True
        cap._width = 1920
        cap._height = 1080
        # Secondary monitor: DesktopCoordinates.left = 1024.
        cap._output_desc = _make_output_desc(1024, 0, 2944, 1080)

        full_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        for y in range(1080):
            full_frame[y, :, 1] = (y + 50) % 256
        mock_capture.return_value = full_frame

        # Window on the secondary monitor: screen coords 1124..1524.
        mock_get_rect.return_value = _make_rect(1124, 100, 1524, 400)

        result = cap.capture_window(0x12345)

        self.assertIsNotNone(result)
        # Translated: (1124-1024, 100-0) → (100, 100) → (500, 400).
        self.assertEqual(result.shape, (300, 400, 3))
        np.testing.assert_array_equal(result[0, :, 1], full_frame[100, 100:500, 1])
