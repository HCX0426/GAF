"""P1-5 BackgroundManagedKeyInput guard loop / ensure_key_pressed / generation sync tests.

Covers MaaFramework parity features added in P1-5:
- ensure_key_pressed: 4-step RegisterHotKey + SendInput + WM_HOTKEY + UnregisterHotKey.
- add_managed_key / remove_managed_key: optimistic-locking generation sync.
- wait_until_applied: block until generation processed.
- _guard_loop: 5ms poll, ensures desired keys stay pressed.
- stop_guard: clear all managed keys.
"""

import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import contextlib

import pytest
from platforms.windows.background_key_input import BackgroundManagedKeyInput

pytestmark = pytest.mark.unit

# ============================================================
# Generation counter tests
# ============================================================

class TestGenerationCounter:
    """add/remove_managed_key must return monotonically increasing generations."""

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_add_returns_increasing_generation(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        try:
            gen1 = bmki.add_managed_key("w")
            gen2 = bmki.add_managed_key("a")
            gen3 = bmki.add_managed_key("s")
            assert gen1 < gen2 < gen3
        finally:
            bmki.stop_guard()

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_remove_returns_higher_generation(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        try:
            gen_add = bmki.add_managed_key("w")
            gen_remove = bmki.remove_managed_key("w")
            assert gen_remove > gen_add
        finally:
            bmki.stop_guard()


# ============================================================
# Managed key state
# ============================================================

class TestManagedKeyState:
    """_desired_pressed_keys / _release_keys must reflect add/remove operations."""

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_add_managed_key_adds_to_desired(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        try:
            bmki.add_managed_key("w")
            assert "w" in bmki._desired_pressed_keys
            assert "w" not in bmki._release_keys
        finally:
            bmki.stop_guard()

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_remove_managed_key_moves_to_release(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        try:
            bmki.add_managed_key("w")
            bmki.remove_managed_key("w")
            assert "w" not in bmki._desired_pressed_keys
            assert "w" in bmki._release_keys
        finally:
            bmki.stop_guard()


# ============================================================
# Guard loop lifecycle
# ============================================================

class TestGuardLoopLifecycle:
    """_ensure_guard_running / stop_guard control the guard thread."""

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_add_managed_key_starts_guard_thread(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        try:
            assert bmki._guard_thread is None
            bmki.add_managed_key("w")
            # Thread should be created.
            assert bmki._guard_thread is not None
            assert bmki._guard_thread.is_alive()
        finally:
            bmki.stop_guard()

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_stop_guard_stops_thread(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        bmki.add_managed_key("w")
        thread = bmki._guard_thread
        assert thread is not None
        bmki.stop_guard()
        # Thread should be joined and cleared.
        assert bmki._guard_thread is None
        assert not thread.is_alive()

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_stop_guard_clears_state(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        bmki.add_managed_key("w")
        bmki.add_managed_key("a")
        bmki.remove_managed_key("w")
        bmki.stop_guard()
        assert len(bmki._desired_pressed_keys) == 0
        assert len(bmki._release_keys) == 0

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_double_add_does_not_create_second_thread(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        try:
            bmki.add_managed_key("w")
            thread1 = bmki._guard_thread
            bmki.add_managed_key("a")
            thread2 = bmki._guard_thread
            assert thread1 is thread2
        finally:
            bmki.stop_guard()


# ============================================================
# Generation sync via wait_until_applied
# ============================================================

class TestWaitUntilApplied:
    """wait_until_applied blocks until applied_generation reaches target."""

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_returns_true_if_generation_already_applied(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        try:
            # Set applied_generation high.
            with bmki._applied_lock:
                bmki._applied_generation = 100
            assert bmki.wait_until_applied(50, timeout_sec=0.1) is True
        finally:
            bmki.stop_guard()

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_returns_false_on_timeout(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        try:
            # Set applied_generation low, request unreachable generation.
            with bmki._applied_lock:
                bmki._applied_generation = 0
            start = time.monotonic()
            result = bmki.wait_until_applied(999, timeout_sec=0.1)
            elapsed = time.monotonic() - start
            assert result is False
            assert elapsed >= 0.08  # Allow some slack.
        finally:
            bmki.stop_guard()

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_default_timeout_is_500ms(self, mock_ctypes, mock_user32):
        """P1-5 spec: APPLY_TIMEOUT_SEC = 0.5s (MaaFramework parity)."""
        assert BackgroundManagedKeyInput._APPLY_TIMEOUT_SEC == 0.5


# ============================================================
# Guard interval / hotkey timeout constants
# ============================================================

class TestP15Constants:
    """P1-5 spec: constants must match MaaFramework values."""

    def test_guard_interval_5ms(self):
        """5ms = 0.005s polling interval per MaaFramework."""
        assert BackgroundManagedKeyInput._GUARD_INTERVAL_SEC == 0.005

    def test_hotkey_confirm_timeout_200ms(self):
        """200ms WM_HOTKEY confirmation timeout."""
        assert BackgroundManagedKeyInput._HOTKEY_CONFIRM_TIMEOUT_SEC == 0.2


# ============================================================
# ensure_key_pressed 4-step technique
# ============================================================

class TestEnsureKeyPressed:
    """ensure_key_pressed: 4-step RegisterHotKey + SendInput + WM_HOTKEY + UnregisterHotKey."""

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_register_hotkey_called(self, mock_ctypes, mock_user32):
        # RegisterHotKey returns 1 (success).
        mock_user32.RegisterHotKey.return_value = 1
        mock_user32.UnregisterHotKey.return_value = 1
        mock_user32.PeekMessageW.return_value = 0  # No WM_HOTKEY arrives.
        mock_user32.SendInput.return_value = 1
        # Avoid fallback SendInput returning True by configuring send_key path.
        bmki = BackgroundManagedKeyInput()
        with patch.object(bmki, "send_key", return_value=True):
            bmki.ensure_key_pressed("f5")
        # RegisterHotKey called once.
        mock_user32.RegisterHotKey.assert_called_once()
        # UnregisterHotKey always called in finally.
        mock_user32.UnregisterHotKey.assert_called_once()

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_register_failure_falls_back_to_send_key(self, mock_ctypes, mock_user32):
        # RegisterHotKey returns 0 (failure).
        mock_user32.RegisterHotKey.return_value = 0
        bmki = BackgroundManagedKeyInput()
        with patch.object(bmki, "send_key", return_value=True) as mock_send:
            result = bmki.ensure_key_pressed("f5")
        assert result is True
        mock_send.assert_called_once_with("f5")

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_unparseable_key_returns_false(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        # _parse_combo will fail to find a VK for unknown key.
        result = bmki.ensure_key_pressed("unknown_key_xyz")
        assert result is False

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_sendinput_called_for_down_and_up(self, mock_ctypes, mock_user32):
        mock_user32.RegisterHotKey.return_value = 1
        mock_user32.UnregisterHotKey.return_value = 1
        mock_user32.PeekMessageW.return_value = 0  # No confirmation.
        mock_user32.SendInput.return_value = 1
        bmki = BackgroundManagedKeyInput()
        with patch.object(bmki, "send_key", return_value=True):
            bmki.ensure_key_pressed("f5")
        # SendInput called twice: key down + key up.
        assert mock_user32.SendInput.call_count == 2

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_unregister_always_called_on_exception(self, mock_ctypes, mock_user32):
        """Even if SendInput raises, UnregisterHotKey must run."""
        mock_user32.RegisterHotKey.return_value = 1
        mock_user32.SendInput.side_effect = RuntimeError("boom")
        bmki = BackgroundManagedKeyInput()
        with contextlib.suppress(RuntimeError):
            bmki.ensure_key_pressed("f5")
        # UnregisterHotKey must still be called.
        mock_user32.UnregisterHotKey.assert_called_once()


# ============================================================
# Guard loop processing
# ============================================================

class TestGuardLoopProcessing:
    """The guard loop should call ensure_key_pressed for desired keys."""

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_guard_loop_calls_ensure_key_pressed(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        try:
            with patch.object(bmki, "ensure_key_pressed") as mock_ensure, \
                 patch.object(bmki, "send_key"):
                bmki.add_managed_key("w")
                # Wait for the guard loop to process at least once.
                time.sleep(0.05)
                assert mock_ensure.called
                assert "w" in mock_ensure.call_args[0] or \
                       any(call_args[0] == ("w",) for call_args in mock_ensure.call_args_list)
        finally:
            bmki.stop_guard()

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_guard_loop_updates_applied_generation(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        try:
            with patch.object(bmki, "ensure_key_pressed"), patch.object(bmki, "send_key"):
                gen = bmki.add_managed_key("w")
                # Generation should be applied within timeout.
                assert bmki.wait_until_applied(gen, timeout_sec=1.0) is True
        finally:
            bmki.stop_guard()

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_guard_loop_clears_release_keys_after_processing(self, mock_ctypes, mock_user32):
        bmki = BackgroundManagedKeyInput()
        try:
            with patch.object(bmki, "ensure_key_pressed"), patch.object(bmki, "send_key"):
                gen_add = bmki.add_managed_key("w")
                # Wait for it to be applied.
                bmki.wait_until_applied(gen_add, timeout_sec=1.0)
                gen_remove = bmki.remove_managed_key("w")
                # Wait for remove to be applied.
                bmki.wait_until_applied(gen_remove, timeout_sec=1.0)
                # After processing, release set should be cleared.
                assert "w" not in bmki._release_keys
        finally:
            bmki.stop_guard()

    @patch("platforms.windows.background_key_input.user32")
    @patch("platforms.windows.background_key_input.ctypes")
    def test_guard_loop_swallows_exceptions(self, mock_ctypes, mock_user32):
        """Guard loop should not crash on ensure_key_pressed exceptions."""
        bmki = BackgroundManagedKeyInput()
        try:
            with patch.object(bmki, "ensure_key_pressed", side_effect=RuntimeError("boom")), \
                 patch.object(bmki, "send_key"):
                bmki.add_managed_key("w")
                # Sleep briefly; thread should still be alive (no crash).
                time.sleep(0.05)
                assert bmki._guard_thread is not None
                assert bmki._guard_thread.is_alive()
        finally:
            bmki.stop_guard()
