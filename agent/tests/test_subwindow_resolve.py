"""P1-6 unit tests for resolve_child_at_client_point() in platforms.windows.subwindow.

Verifies the ChildWindowFromPointEx recursive resolver:
- No child at point -> returns top_hwnd unchanged
- Single-level child resolution with coordinate translation
- Nested multi-level child chain
- Skip-flag combinations (invisible / disabled / transparent)
- Max recursion depth cap
- Point outside parent client area
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from platforms.windows import subwindow
from platforms.windows.subwindow import (
    CWP_SKIPDISABLED,
    CWP_SKIPINVISIBLE,
    CWP_SKIPTRANSPARENT,
    resolve_child_at_client_point,
)

pytestmark = pytest.mark.e2e

# ============================================================
# Constants
# ============================================================

class TestCWPSkipConstants:
    """CWP_SKIP* flag values must match the Win32 spec."""

    def test_cwp_skipinvisible_value(self):
        assert CWP_SKIPINVISIBLE == 0x0001

    def test_cwp_skipdisabled_value(self):
        assert CWP_SKIPDISABLED == 0x0002

    def test_cwp_skiptransparent_value(self):
        assert CWP_SKIPTRANSPARENT == 0x0004


# ============================================================
# No child at point -> passthrough
# ============================================================

class TestNoChildPassthrough:
    """When ChildWindowFromPointEx returns 0 or parent itself, the resolver
    must return (top_hwnd, x, y) unchanged (no coordinate translation)."""

    @patch("platforms.windows.subwindow.user32")
    @patch("platforms.windows.subwindow.ctypes")
    def test_point_outside_parent_returns_top_hwnd(self, mock_ctypes, mock_user32):
        """ChildWindowFromPointEx returning 0 (point outside) -> top_hwnd unchanged."""
        mock_user32.ChildWindowFromPointEx.return_value = 0
        point_mock = MagicMock()
        point_mock.x = 50
        point_mock.y = 60
        mock_ctypes.wintypes.POINT.return_value = point_mock

        hwnd, cx, cy = resolve_child_at_client_point(0x100, 50, 60)

        assert hwnd == 0x100
        assert cx == 50
        assert cy == 60
        # No coordinate translation should occur.
        mock_user32.ClientToScreen.assert_not_called()
        mock_user32.ScreenToClient.assert_not_called()

    @patch("platforms.windows.subwindow.user32")
    @patch("platforms.windows.subwindow.ctypes")
    def test_point_in_parent_but_no_child_returns_top_hwnd(self, mock_ctypes, mock_user32):
        """ChildWindowFromPointEx returning parent itself -> top_hwnd unchanged."""
        mock_user32.ChildWindowFromPointEx.return_value = 0x100  # == parent
        point_mock = MagicMock()
        point_mock.x = 50
        point_mock.y = 60
        mock_ctypes.wintypes.POINT.return_value = point_mock

        hwnd, cx, cy = resolve_child_at_client_point(0x100, 50, 60)

        assert (hwnd, cx, cy) == (0x100, 50, 60)
        mock_user32.ClientToScreen.assert_not_called()
        mock_user32.ScreenToClient.assert_not_called()


# ============================================================
# Single-level child resolution
# ============================================================

class TestSingleLevelChild:
    """A single child window at the point must be returned with translated coords."""

    @patch("platforms.windows.subwindow.user32")
    @patch("platforms.windows.subwindow.ctypes")
    def test_returns_child_hwnd_with_translated_coords(self, mock_ctypes, mock_user32):
        """First call returns a child; second call (on child) returns the child
        itself -> loop breaks. Coordinates are translated via screen space."""
        # First call on parent -> returns child 0x200.
        # Second call on child 0x200 -> returns 0x200 itself -> loop breaks.
        mock_user32.ChildWindowFromPointEx.side_effect = [0x200, 0x200]

        # The POINT mock: starts at (50, 60), and after ClientToScreen +
        # ScreenToClient the mock's x/y are mutated to the translated values.
        # We simulate translation by setting up a POINT whose x/y change
        # when ClientToScreen/ScreenToClient are called.
        point_mock = MagicMock()
        point_mock.x = 50
        point_mock.y = 60

        # After translation, the child-relative coords become (10, 20).
        def _translate_side_effect(hwnd, pt_ref):
            pt_ref._obj.contents.x = 10
            pt_ref._obj.contents.y = 20
            return 1

        # Simpler: just have ClientToScreen + ScreenToClient mutate point_mock.
        # Since ctypes.byref(pt) is passed, we mutate via the mock's attributes.
        def _client_to_screen(hwnd, pt_ref):
            point_mock.x = 100  # screen x
            point_mock.y = 110  # screen y
            return 1

        def _screen_to_client(hwnd, pt_ref):
            point_mock.x = 10  # child-relative x
            point_mock.y = 20  # child-relative y
            return 1

        mock_user32.ClientToScreen.side_effect = _client_to_screen
        mock_user32.ScreenToClient.side_effect = _screen_to_client
        mock_ctypes.wintypes.POINT.return_value = point_mock

        hwnd, cx, cy = resolve_child_at_client_point(0x100, 50, 60)

        assert hwnd == 0x200
        assert cx == 10
        assert cy == 20
        # ClientToScreen + ScreenToClient called once for the single child level.
        assert mock_user32.ClientToScreen.call_count == 1
        assert mock_user32.ScreenToClient.call_count == 1

    @patch("platforms.windows.subwindow.user32")
    @patch("platforms.windows.subwindow.ctypes")
    def test_child_hwnd_zero_breaks_loop(self, mock_ctypes, mock_user32):
        """If first child resolution returns 0, loop breaks immediately."""
        mock_user32.ChildWindowFromPointEx.return_value = 0
        point_mock = MagicMock()
        point_mock.x = 5
        point_mock.y = 7
        mock_ctypes.wintypes.POINT.return_value = point_mock

        hwnd, cx, cy = resolve_child_at_client_point(0x100, 5, 7)

        assert (hwnd, cx, cy) == (0x100, 5, 7)


# ============================================================
# Nested child chain
# ============================================================

class TestNestedChildChain:
    """A multi-level child hierarchy (top -> child -> grandchild) must resolve
    to the deepest child, with coordinates translated at each level."""

    @patch("platforms.windows.subwindow.user32")
    @patch("platforms.windows.subwindow.ctypes")
    def test_two_level_chain_resolves_to_grandchild(self, mock_ctypes, mock_user32):
        """top(0x100) -> child(0x200) -> grandchild(0x300) -> self(0x300)."""
        # Call 1 on 0x100 returns 0x200 (child).
        # Call 2 on 0x200 returns 0x300 (grandchild).
        # Call 3 on 0x300 returns 0x300 (self) -> loop breaks.
        mock_user32.ChildWindowFromPointEx.side_effect = [0x200, 0x300, 0x300]

        point_mock = MagicMock()
        point_mock.x = 50
        point_mock.y = 60
        mock_ctypes.wintypes.POINT.return_value = point_mock

        # Coordinate translation: each level shifts coords. We don't care
        # about exact values, just that translation was called twice.
        mock_user32.ClientToScreen.return_value = 1
        mock_user32.ScreenToClient.return_value = 1

        hwnd, cx, cy = resolve_child_at_client_point(0x100, 50, 60)

        assert hwnd == 0x300
        # ChildWindowFromPointEx called 3 times (parent, child, grandchild-self).
        assert mock_user32.ChildWindowFromPointEx.call_count == 3
        # Translation called twice (parent->child, child->grandchild).
        assert mock_user32.ClientToScreen.call_count == 2
        assert mock_user32.ScreenToClient.call_count == 2

    @patch("platforms.windows.subwindow.user32")
    @patch("platforms.windows.subwindow.ctypes")
    def test_max_depth_cap_prevents_infinite_loop(self, mock_ctypes, mock_user32):
        """If ChildWindowFromPointEx keeps returning new children, the loop
        must cap at _MAX_CHILD_DEPTH iterations."""
        # Always return a brand-new hwnd (never 0, never == parent) to force
        # the loop to run until the depth cap.
        call_count = [0]

        def _always_new_child(parent, pt, flags):
            call_count[0] += 1
            return 0x1000 + call_count[0]  # always unique, never 0, never == parent

        mock_user32.ChildWindowFromPointEx.side_effect = _always_new_child
        point_mock = MagicMock()
        point_mock.x = 1
        point_mock.y = 2
        mock_ctypes.wintypes.POINT.return_value = point_mock
        mock_user32.ClientToScreen.return_value = 1
        mock_user32.ScreenToClient.return_value = 1

        hwnd, cx, cy = resolve_child_at_client_point(0x100, 1, 2)

        # Loop ran exactly _MAX_CHILD_DEPTH times.
        assert call_count[0] == subwindow._MAX_CHILD_DEPTH
        # Returned hwnd is the last resolved child.
        assert hwnd == 0x1000 + subwindow._MAX_CHILD_DEPTH


# ============================================================
# Skip flags
# ============================================================

class TestSkipFlags:
    """The CWP_SKIP* flags must be combined correctly based on kwargs."""

    @patch("platforms.windows.subwindow.user32")
    @patch("platforms.windows.subwindow.ctypes")
    def test_default_flags_skip_all(self, mock_ctypes, mock_user32):
        """Default (all True) -> flags = CWP_SKIPINVISIBLE | DISABLED | TRANSPARENT."""
        mock_user32.ChildWindowFromPointEx.return_value = 0
        point_mock = MagicMock()
        point_mock.x = 1
        point_mock.y = 2
        mock_ctypes.wintypes.POINT.return_value = point_mock

        resolve_child_at_client_point(0x100, 1, 2)

        flags_arg = mock_user32.ChildWindowFromPointEx.call_args[0][2]
        expected = CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT
        assert flags_arg == expected

    @patch("platforms.windows.subwindow.user32")
    @patch("platforms.windows.subwindow.ctypes")
    def test_disable_skip_invisible(self, mock_ctypes, mock_user32):
        """skip_invisible=False removes CWP_SKIPINVISIBLE from flags."""
        mock_user32.ChildWindowFromPointEx.return_value = 0
        point_mock = MagicMock()
        point_mock.x = 1
        point_mock.y = 2
        mock_ctypes.wintypes.POINT.return_value = point_mock

        resolve_child_at_client_point(0x100, 1, 2, skip_invisible=False)

        flags_arg = mock_user32.ChildWindowFromPointEx.call_args[0][2]
        expected = CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT
        assert flags_arg == expected

    @patch("platforms.windows.subwindow.user32")
    @patch("platforms.windows.subwindow.ctypes")
    def test_disable_skip_disabled(self, mock_ctypes, mock_user32):
        """skip_disabled=False removes CWP_SKIPDISABLED from flags."""
        mock_user32.ChildWindowFromPointEx.return_value = 0
        point_mock = MagicMock()
        point_mock.x = 1
        point_mock.y = 2
        mock_ctypes.wintypes.POINT.return_value = point_mock

        resolve_child_at_client_point(0x100, 1, 2, skip_disabled=False)

        flags_arg = mock_user32.ChildWindowFromPointEx.call_args[0][2]
        expected = CWP_SKIPINVISIBLE | CWP_SKIPTRANSPARENT
        assert flags_arg == expected

    @patch("platforms.windows.subwindow.user32")
    @patch("platforms.windows.subwindow.ctypes")
    def test_disable_skip_transparent(self, mock_ctypes, mock_user32):
        """skip_transparent=False removes CWP_SKIPTRANSPARENT from flags."""
        mock_user32.ChildWindowFromPointEx.return_value = 0
        point_mock = MagicMock()
        point_mock.x = 1
        point_mock.y = 2
        mock_ctypes.wintypes.POINT.return_value = point_mock

        resolve_child_at_client_point(0x100, 1, 2, skip_transparent=False)

        flags_arg = mock_user32.ChildWindowFromPointEx.call_args[0][2]
        expected = CWP_SKIPINVISIBLE | CWP_SKIPDISABLED
        assert flags_arg == expected

    @patch("platforms.windows.subwindow.user32")
    @patch("platforms.windows.subwindow.ctypes")
    def test_no_skip_flags_all_false(self, mock_ctypes, mock_user32):
        """All skip flags False -> flags = 0 (return any child, even invisible)."""
        mock_user32.ChildWindowFromPointEx.return_value = 0
        point_mock = MagicMock()
        point_mock.x = 1
        point_mock.y = 2
        mock_ctypes.wintypes.POINT.return_value = point_mock

        resolve_child_at_client_point(
            0x100, 1, 2,
            skip_invisible=False, skip_disabled=False, skip_transparent=False,
        )

        flags_arg = mock_user32.ChildWindowFromPointEx.call_args[0][2]
        assert flags_arg == 0


# ============================================================
# POINT argument wiring
# ============================================================

class TestPointArgumentWiring:
    """The POINT struct passed to ChildWindowFromPointEx must carry (x, y)."""

    @patch("platforms.windows.subwindow.user32")
    @patch("platforms.windows.subwindow.ctypes")
    def test_point_constructed_with_xy(self, mock_ctypes, mock_user32):
        """ctypes.wintypes.POINT must be constructed with the input (x, y)."""
        mock_user32.ChildWindowFromPointEx.return_value = 0
        point_mock = MagicMock()
        point_mock.x = 42
        point_mock.y = 99
        mock_ctypes.wintypes.POINT.return_value = point_mock

        resolve_child_at_client_point(0x100, 42, 99)

        # POINT(x, y) constructor call.
        mock_ctypes.wintypes.POINT.assert_called_with(42, 99)
