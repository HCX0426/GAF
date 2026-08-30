"""P2-2 4-point cubic Bezier curve tests for humanize.swipe().

Covers:
- _cubic_bezier_4p(): endpoint correctness, sample count, monotonic param,
  midpoint symmetry, collinear control points (linear case).
- HumanizedInput.swipe(cubic=True) dispatches to _cubic_bezier_4p.
- HumanizedInput.swipe(cubic=False) falls back to legacy _bezier_curve.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from devices.humanize import HumanizedInput, _bezier_curve, _cubic_bezier_4p

pytestmark = pytest.mark.unit

# ============================================================
# _cubic_bezier_4p pure-function tests
# ============================================================

class TestCubicBezier4pEndpoints:
    """B(0) must equal P0, B(1) must equal P3."""

    def test_start_equals_p0(self):
        pts = _cubic_bezier_4p((0.0, 0.0), (10.0, 20.0), (30.0, 40.0), (50.0, 50.0), num_samples=10)
        assert pts[0] == pytest.approx((0.0, 0.0), abs=1e-9)

    def test_end_equals_p3(self):
        pts = _cubic_bezier_4p((0.0, 0.0), (10.0, 20.0), (30.0, 40.0), (50.0, 50.0), num_samples=10)
        assert pts[-1] == pytest.approx((50.0, 50.0), abs=1e-9)


class TestCubicBezier4pSampleCount:
    """Output length must be num_samples + 1."""

    def test_sample_count_20(self):
        pts = _cubic_bezier_4p((0, 0), (1, 1), (2, 2), (3, 3), num_samples=20)
        assert len(pts) == 21

    def test_sample_count_0_returns_endpoints(self):
        pts = _cubic_bezier_4p((0, 0), (1, 1), (2, 2), (3, 3), num_samples=0)
        assert len(pts) == 1  # t=0 only
        assert pts[0] == pytest.approx((0.0, 0.0), abs=1e-9)

    def test_sample_count_5(self):
        pts = _cubic_bezier_4p((0, 0), (1, 1), (2, 2), (3, 3), num_samples=5)
        assert len(pts) == 6


class TestCubicBezier4pLinear:
    """When all 4 control points are collinear, the curve is a straight line."""

    def test_collinear_points_produce_linear_interpolation(self):
        # All points on y=x line: should interpolate linearly.
        pts = _cubic_bezier_4p((0.0, 0.0), (1.0, 1.0), (2.0, 2.0), (3.0, 3.0), num_samples=10)
        for x, y in pts:
            assert x == pytest.approx(y, abs=1e-9)

    def test_linear_curve_midpoint_is_halfway(self):
        pts = _cubic_bezier_4p((0.0, 0.0), (1.0, 1.0), (2.0, 2.0), (3.0, 3.0), num_samples=10)
        # t=0.5 -> midpoint of P0-P3 line: (1.5, 1.5)
        mid = pts[len(pts) // 2]
        assert mid == pytest.approx((1.5, 1.5), abs=1e-9)


class TestCubicBezier4pControlPoints:
    """Control points P1/P2 influence the curve shape."""

    def test_control_point_pulls_curve_toward_itself(self):
        # P1 high above the line should pull the midpoint above the line.
        pts_high = _cubic_bezier_4p((0.0, 0.0), (0.0, 100.0), (50.0, 0.0), (100.0, 0.0), num_samples=20)
        # P1 below the line should pull the midpoint below.
        pts_low = _cubic_bezier_4p((0.0, 0.0), (0.0, -100.0), (50.0, 0.0), (100.0, 0.0), num_samples=20)
        mid_high = pts_high[len(pts_high) // 2][1]
        mid_low = pts_low[len(pts_low) // 2][1]
        assert mid_high > 0, "P1 above line should pull midpoint up"
        assert mid_low < 0, "P1 below line should pull midpoint down"

    def test_symmetric_control_points_symmetric_curve(self):
        # For symmetry around the midpoint (50, 0), P1 and P2 must be mirror
        # images: P1=(50-dx, dy), P2=(50+dx, -dy).
        pts = _cubic_bezier_4p((0.0, 0.0), (33.0, 30.0), (67.0, -30.0), (100.0, 0.0), num_samples=10)
        # Mirror around midpoint: pts[i] + pts[N-i] should equal (100, 0).
        n = len(pts) - 1
        for i in range(n // 2 + 1):
            x_sum = pts[i][0] + pts[n - i][0]
            y_sum = pts[i][1] + pts[n - i][1]
            assert x_sum == pytest.approx(100.0, abs=1e-6)
            assert y_sum == pytest.approx(0.0, abs=1e-6)


class TestCubicBezier4pMatchesGeneralBezier:
    """_cubic_bezier_4p must produce the same result as _bezier_curve with 4 points."""

    def test_matches_general_4_point_bezier(self):
        p0, p1, p2, p3 = (0.0, 0.0), (10.0, 30.0), (40.0, 50.0), (100.0, 100.0)
        direct = _cubic_bezier_4p(p0, p1, p2, p3, num_samples=30)
        general = _bezier_curve([p0, p1, p2, p3], num_samples=30)
        assert len(direct) == len(general)
        for (dx, dy), (gx, gy) in zip(direct, general, strict=False):
            assert dx == pytest.approx(gx, abs=1e-9)
            assert dy == pytest.approx(gy, abs=1e-9)


# ============================================================
# HumanizedInput.swipe cubic=True/False dispatch
# ============================================================

class TestHumanizedInputSwipeCubic:
    """HumanizedInput.swipe(cubic=True) should use 4-point cubic curve."""

    def test_cubic_true_uses_4_point_curve(self):
        controller = MagicMock()
        hi = HumanizedInput(controller)
        with patch("devices.humanize._cubic_bezier_4p") as mock_cubic, \
             patch("devices.humanize._bezier_curve") as mock_general:
            mock_cubic.return_value = [(0, 0), (50, 50), (100, 100)]
            hi.swipe(0, 0, 100, 100, duration=0.3, cubic=True)
            mock_cubic.assert_called_once()
            mock_general.assert_not_called()

    def test_cubic_false_uses_general_bezier(self):
        controller = MagicMock()
        hi = HumanizedInput(controller)
        with patch("devices.humanize._cubic_bezier_4p") as mock_cubic, \
             patch("devices.humanize._bezier_curve") as mock_general:
            mock_general.return_value = [(0, 0), (50, 50), (100, 100)]
            hi.swipe(0, 0, 100, 100, duration=0.3, cubic=False)
            mock_general.assert_called_once()
            mock_cubic.assert_not_called()

    def test_default_cubic_is_true(self):
        """swipe() should default to cubic=True per P2-2."""
        controller = MagicMock()
        hi = HumanizedInput(controller)
        # Inspect signature default.
        import inspect
        sig = inspect.signature(hi.swipe)
        assert sig.parameters["cubic"].default is True

    def test_cubic_swipe_calls_controller_swipe(self):
        """swipe(cubic=True) must still dispatch to controller.swipe()."""
        controller = MagicMock()
        hi = HumanizedInput(controller)
        hi.swipe(0, 0, 100, 100, duration=0.1, steps=2)
        assert controller.swipe.call_count >= 1
