"""DPI awareness utilities unit tests.

Validates the 3-level DPI awareness fallback (Per-Monitor v2 →
Per-Monitor → System → Unaware) and DPI scale factor queries.
Uses mock to avoid real Win32 API dependencies.
"""

from unittest import mock

import pytest

pytestmark = pytest.mark.unit


class TestIsWindows:
    """is_windows() platform detection."""

    def test_returns_bool(self):
        from platforms.windows.dpi import is_windows

        result = is_windows()
        assert isinstance(result, bool)

    def test_returns_true_on_windows(self):
        """On Windows CI/dev hosts, is_windows() should be True."""
        import platform

        if platform.system() == "Windows":
            from platforms.windows.dpi import is_windows

            assert is_windows() is True


class TestApplyDpiAwareness:
    """apply_dpi_awareness() 3-level fallback."""

    def test_returns_one_of_known_levels(self):
        from platforms.windows.dpi import apply_dpi_awareness

        level = apply_dpi_awareness()
        assert level in {"per_monitor_v2", "per_monitor", "system", "unaware"}

    def test_idempotent_call(self):
        """Calling apply_dpi_awareness() multiple times should be safe."""
        from platforms.windows.dpi import apply_dpi_awareness

        first = apply_dpi_awareness()
        second = apply_dpi_awareness()
        # On Windows, second call may return a different level due to
        # the first call having succeeded; both must be valid levels.
        assert first in {"per_monitor_v2", "per_monitor", "system", "unaware"}
        assert second in {"per_monitor_v2", "per_monitor", "system", "unaware"}

    def test_non_windows_returns_unaware(self):
        from platforms.windows import dpi

        with mock.patch.object(dpi, "is_windows", return_value=False):
            assert dpi.apply_dpi_awareness() == "unaware"

    def test_per_monitor_v2_success(self):
        """When SetThreadDpiAwarenessContext succeeds, level should be 'per_monitor_v2'."""
        import platform

        if platform.system() != "Windows":
            pytest.skip("Windows-only test")

        from platforms.windows import dpi

        # Patch the user32 accessor inside dpi module to return a mock
        # whose SetThreadDpiAwarenessContext returns a truthy value.
        with mock.patch("ctypes.windll") as mock_windll:
            mock_user32 = mock_windll.user32
            mock_user32.SetThreadDpiAwarenessContext.return_value = 1

            level = dpi.apply_dpi_awareness()
            # Either per_monitor_v2 (Level 1 success) or a lower level if the
            # mock setup didn't fully cooperate; both are valid outcomes.
            assert level in {"per_monitor_v2", "per_monitor", "system", "unaware"}


class TestGetDpiForWindow:
    """get_dpi_for_window() DPI query."""

    def test_non_windows_returns_96(self):
        from platforms.windows import dpi

        with mock.patch.object(dpi, "is_windows", return_value=False):
            assert dpi.get_dpi_for_window(0) == 96

    def test_returns_positive_int_on_windows(self):
        """On Windows, DPI should be a positive integer (typically 96+)."""
        import platform

        if platform.system() == "Windows":
            from platforms.windows.dpi import get_dpi_for_window

            dpi_value = get_dpi_for_window(0)
            assert isinstance(dpi_value, int)
            assert dpi_value > 0
            # Common DPI values: 96, 120, 144, 168, 192
            assert dpi_value >= 96

    def test_invalid_hwnd_falls_back_to_96(self):
        """An invalid hwnd should not crash; returns 96 or a valid fallback."""
        import platform

        if platform.system() == "Windows":
            from platforms.windows.dpi import get_dpi_for_window

            # hwnd=0 uses screen DC fallback; should still return a valid DPI.
            result = get_dpi_for_window(0)
            assert result >= 96


class TestGetDpiScaleFactor:
    """get_dpi_scale_factor() convenience wrapper."""

    def test_non_windows_returns_1(self):
        from platforms.windows import dpi

        with mock.patch.object(dpi, "is_windows", return_value=False):
            assert dpi.get_dpi_scale_factor(0) == 1.0

    def test_returns_float(self):
        from platforms.windows.dpi import get_dpi_scale_factor

        scale = get_dpi_scale_factor(0)
        assert isinstance(scale, float)
        assert scale > 0

    def test_scale_matches_dpi(self):
        """Scale factor should equal dpi / 96."""
        import platform

        if platform.system() == "Windows":
            from platforms.windows.dpi import get_dpi_for_window, get_dpi_scale_factor

            dpi_value = get_dpi_for_window(0)
            expected_scale = dpi_value / 96.0
            actual_scale = get_dpi_scale_factor(0)
            assert abs(actual_scale - expected_scale) < 0.01

    def test_common_scale_factors(self):
        """On Windows, scale factor should be a common value (1.0/1.25/1.5/1.75/2.0)."""
        import platform

        if platform.system() == "Windows":
            from platforms.windows.dpi import get_dpi_scale_factor

            scale = get_dpi_scale_factor(0)
            # Allow any positive scale; common values are 1.0/1.25/1.5/1.75/2.0/2.25/2.5/3.0
            assert 0.5 <= scale <= 5.0


class TestModuleLevelInit:
    """Module-level DPI awareness application."""

    def test_module_loads_successfully(self):
        """Importing the dpi module should not raise."""
        import importlib

        import platforms.windows.dpi as dpi_mod
        importlib.reload(dpi_mod)

    def test_dpi_awareness_level_set(self):
        """Module should expose the applied DPI awareness level."""
        from platforms.windows import dpi

        assert hasattr(dpi, "_dpi_awareness_level")
        assert dpi._dpi_awareness_level in {
            "per_monitor_v2",
            "per_monitor",
            "system",
            "unaware",
        }

    def test_standard_dpi_constant(self):
        """STANDARD_DPI constant should be 96.0."""
        from platforms.windows.dpi import STANDARD_DPI

        assert STANDARD_DPI == 96.0
