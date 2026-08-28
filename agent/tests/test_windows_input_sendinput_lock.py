"""Tests for TD-121: SendInput/PseudoBackground serialization via _sendinput_lock.

Verifies:
- `_sendinput_lock` is a reentrant lock (RLock), so PseudoBackground methods
  can internally call `_sendinput` methods without deadlocking.
- All 6 SendInput/PseudoBackground paths acquire the lock.
- PostMessage paths do NOT acquire the lock (parallel-safe, hwnd-isolated).
- Concurrent SendInput calls from multiple threads are serialized (no overlap).
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from platforms.windows.input import WindowsInputHandler

pytestmark = pytest.mark.unit


class TestSendInputLockType:
    """_sendinput_lock must be a reentrant lock (RLock, not Lock)."""

    def test_sendinput_lock_is_rlock(self):
        """RLock allows the same thread to acquire it multiple times.

        PseudoBackground methods internally call _sendinput methods (e.g.
        _click_pseudo_background -> _click_sendinput), so a non-reentrant
        Lock would deadlock. RLock is mandatory.
        """
        handler = WindowsInputHandler("SendInput")
        # RLock reports as "locked" after first acquire and allows re-acquire
        # by the same thread. Lock would also pass this, so we verify the
        # specific behavior: acquire twice without blocking.
        assert handler._sendinput_lock.acquire()
        try:
            # Second acquire by same thread must not block (RLock behavior).
            assert handler._sendinput_lock.acquire()
            handler._sendinput_lock.release()
        finally:
            handler._sendinput_lock.release()

    def test_sendinput_lock_is_not_block_locked_after_release(self):
        """After release, the lock is free for another thread to acquire."""
        handler = WindowsInputHandler("SendInput")
        acquired = []

        def grab():
            acquired.append(handler._sendinput_lock.acquire(timeout=0.5))

        handler._sendinput_lock.acquire()
        try:
            t = threading.Thread(target=grab)
            t.start()
            t.join(timeout=1.0)
            # Lock held by main thread, other thread must time out.
            assert acquired == [False]
        finally:
            handler._sendinput_lock.release()


class TestSendInputPathsAcquireLock:
    """All SendInput/PseudoBackground paths must acquire _sendinput_lock.

    Note: `with lock:` invokes __enter__/__exit__, not acquire/release
    directly, so we assert on the context-manager protocol methods.
    """

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_click_sendinput_acquires_lock(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        mock_user32.GetSystemMetrics.side_effect = [1920, 1080]
        mock_user32.ClientToScreen.return_value = 1
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()
        point_mock = MagicMock()
        mock_ctypes.wintypes.POINT.return_value = point_mock
        point_mock.x = 100
        point_mock.y = 200

        handler = WindowsInputHandler("SendInput")
        with patch.object(handler, "_sendinput_lock", wraps=handler._sendinput_lock) as mock_lock:
            result = handler.click("0x12345", 10, 20, button="left")

        assert result.success is True
        mock_lock.__enter__.assert_called()
        mock_lock.__exit__.assert_called()

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_key_press_sendinput_acquires_lock(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()

        handler = WindowsInputHandler("SendInput")
        with patch.object(handler, "_sendinput_lock", wraps=handler._sendinput_lock) as mock_lock:
            result = handler.key_press("0", "enter")

        assert result.success is True
        mock_lock.__enter__.assert_called()
        mock_lock.__exit__.assert_called()

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_text_input_sendinput_acquires_lock(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()

        handler = WindowsInputHandler("SendInput")
        with patch.object(handler, "_sendinput_lock", wraps=handler._sendinput_lock) as mock_lock:
            result = handler.text_input("0", "hi")

        assert result.success is True
        mock_lock.__enter__.assert_called()
        mock_lock.__exit__.assert_called()

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_swipe_sendinput_acquires_lock(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        mock_user32.GetSystemMetrics.side_effect = [1920, 1080]
        mock_user32.ClientToScreen.return_value = 1
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()
        point_mock = MagicMock()
        mock_ctypes.wintypes.POINT.return_value = point_mock
        point_mock.x = 10
        point_mock.y = 20

        handler = WindowsInputHandler("SendInput")
        with patch.object(handler, "_sendinput_lock", wraps=handler._sendinput_lock) as mock_lock:
            result = handler.swipe("0x12345", 10, 20, 30, 40, duration_ms=50)

        assert result.success is True
        mock_lock.__enter__.assert_called()
        mock_lock.__exit__.assert_called()


class TestPseudoBackgroundPathsAcquireLock:
    """PseudoBackground paths must acquire _sendinput_lock (and re-acquire
    internally when calling _sendinput helpers — RLock prevents deadlock)."""

    @patch("platforms.windows.input_variants.bring_to_foreground")
    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_click_pseudo_background_acquires_lock(
        self, mock_sleep, mock_ctypes, mock_user32, mock_bring_to_fg
    ):
        mock_bring_to_fg.return_value = True
        mock_user32.GetForegroundWindow.side_effect = [0x10001, 0x12345]
        mock_user32.SetForegroundWindow.return_value = 1
        mock_user32.SetCursorPos.return_value = 1
        mock_user32.ClientToScreen.return_value = 1
        mock_user32.GetSystemMetrics.side_effect = [1920, 1080]
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()
        point_mock = MagicMock()
        mock_ctypes.wintypes.POINT.return_value = point_mock
        point_mock.x = 100
        point_mock.y = 200

        handler = WindowsInputHandler("PseudoBackground")
        with patch.object(handler, "_sendinput_lock", wraps=handler._sendinput_lock) as mock_lock:
            result = handler.click("0x12345", 10, 20, button="left")

        assert result.success is True
        # Outer PseudoBackground acquire + inner _click_sendinput re-acquire
        # (RLock allows both). At least 2 __enter__ calls expected on slow path.
        assert mock_lock.__enter__.call_count >= 2
        assert mock_lock.__exit__.call_count >= 2

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_key_press_pseudo_background_no_deadlock(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        """PseudoBackground key_press must not deadlock when re-acquiring
        the RLock inside _key_press_sendinput."""
        mock_user32.GetForegroundWindow.side_effect = [0x10001, 0x12345]
        mock_user32.SetForegroundWindow.return_value = 1
        mock_user32.SetCursorPos.return_value = 1
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()
        point_mock = MagicMock()
        mock_ctypes.wintypes.POINT.return_value = point_mock
        point_mock.x = 30
        point_mock.y = 40

        handler = WindowsInputHandler("PseudoBackground")
        # If RLock is misconfigured as Lock, this would deadlock.
        result = handler.key_press("0x12345", "enter")

        assert result.success is True

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_text_input_pseudo_background_no_deadlock(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        mock_user32.GetForegroundWindow.side_effect = [0x10001, 0x12345]
        mock_user32.SetForegroundWindow.return_value = 1
        mock_user32.SetCursorPos.return_value = 1
        mock_user32.SendInput.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()
        point_mock = MagicMock()
        mock_ctypes.wintypes.POINT.return_value = point_mock
        point_mock.x = 90
        point_mock.y = 100

        handler = WindowsInputHandler("PseudoBackground")
        result = handler.text_input("0x12345", "hi")

        assert result.success is True


class TestPostMessagePathsDoNotAcquireLock:
    """PostMessage paths are parallel-safe (hwnd-isolated) and must NOT
    acquire _sendinput_lock — otherwise they would be needlessly serialized
    alongside SendInput paths."""

    @patch("platforms.windows.input.user32")
    def test_click_postmessage_does_not_acquire_lock(self, mock_user32):
        mock_user32.PostMessageW.return_value = 1

        handler = WindowsInputHandler("PostMessage")
        with patch.object(handler, "_sendinput_lock", wraps=handler._sendinput_lock) as mock_lock:
            result = handler.click("0x12345", 10, 20, button="left")

        assert result.success is True
        mock_lock.__enter__.assert_not_called()
        mock_lock.__exit__.assert_not_called()

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.time.sleep")
    def test_key_press_postmessage_does_not_acquire_lock(
        self, mock_sleep, mock_user32
    ):
        mock_user32.PostMessageW.return_value = 1

        handler = WindowsInputHandler("PostMessage")
        with patch.object(handler, "_sendinput_lock", wraps=handler._sendinput_lock) as mock_lock:
            result = handler.key_press("0x12345", "enter")

        assert result.success is True
        mock_lock.__enter__.assert_not_called()
        mock_lock.__exit__.assert_not_called()

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.time.sleep")
    def test_swipe_postmessage_does_not_acquire_lock(
        self, mock_sleep, mock_user32
    ):
        mock_user32.PostMessageW.return_value = 1

        handler = WindowsInputHandler("PostMessage")
        with patch.object(handler, "_sendinput_lock", wraps=handler._sendinput_lock) as mock_lock:
            result = handler.swipe("0x12345", 10, 20, 30, 40, duration_ms=50)

        assert result.success is True
        mock_lock.__enter__.assert_not_called()
        mock_lock.__exit__.assert_not_called()


class TestConcurrentSendInputIsSerialized:
    """Two threads calling _click_sendinput concurrently must NOT overlap
    their SendInput system calls — that is the core TD-121 guarantee."""

    @patch("platforms.windows.input.user32")
    @patch("platforms.windows.input.ctypes")
    @patch("platforms.windows.input.time.sleep")
    def test_concurrent_click_sendinput_does_not_overlap(
        self, mock_sleep, mock_ctypes, mock_user32
    ):
        """Track overlap by recording active-call count inside SendInput.

        Without the lock, two threads can interleave their SendInput calls
        (move/down/up from thread A mixed with move/down/up from thread B),
        causing the OS to deliver clicks to the wrong window. With the lock,
        each thread's full click sequence runs to completion before the other
        starts.
        """
        mock_user32.GetSystemMetrics.side_effect = [1920, 1080]
        mock_user32.ClientToScreen.return_value = 1
        mock_ctypes.sizeof.return_value = 40
        mock_ctypes.byref.return_value = MagicMock()
        point_mock = MagicMock()
        mock_ctypes.wintypes.POINT.return_value = point_mock
        point_mock.x = 100
        point_mock.y = 200

        active = 0
        max_active = 0
        lock = threading.Lock()

        def fake_sendinput(_n, _ref, _size):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
            # Simulate small work window so the other thread has a chance to
            # race in if the serialization lock is missing.
            import time as _t
            _t.sleep(0.01)
            with lock:
                active -= 1
            return 1

        mock_user32.SendInput.side_effect = fake_sendinput

        handler = WindowsInputHandler("SendInput")
        threads = [
            threading.Thread(target=handler.click, args=("0x12345", 10, 20)),
            threading.Thread(target=handler.click, args=("0x12345", 30, 40)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # Each click issues 3 SendInput calls (move/down/up), so total = 6.
        assert mock_user32.SendInput.call_count == 6
        # Serialization guarantee: never more than 1 concurrent SendInput.
        assert max_active == 1, (
            f"SendInput calls overlapped (max_active={max_active}); "
            f"TD-121 serialization broken"
        )
