"""Regression test for TD-009 screenshot stream dedup + consecutive_errors.

Ensures that when all devices return identical frames (static screen), the
screenshot stream loop:
  1. Sends the first frame normally.
  2. Skips sending subsequent identical frames (dedup via compute_frame_hash).
  3. Does NOT trip the consecutive_errors guard and kill the thread.

Bug origin: the dedup ``continue`` skipped ``sent_any_frame = True``, so
dedup rounds were miscounted as "no frame sent" errors. After 10 rounds
on a static screen the loop logged "停止线程" and broke out — killing the
screenshot feed even though every capture was healthy.

Fix: track ``processed_any_device`` (set True after a successful capture)
and key the consecutive_errors guard on that, not on whether a frame was
actually sent.
"""

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

# Ensure src on path (conftest already does this, but be explicit for direct runs)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from client.handler import MessageHandler  # noqa: E402
from devices.base import DeviceStatus  # noqa: E402


class _CountingEvent(threading.Event):
    """Event whose wait() returns False N times then True (stop signal).

    Lets the screenshot loop run a fixed number of rounds without blocking
    on the 1.0s frame_interval, so the test finishes in milliseconds.
    """

    def __init__(self, rounds: int = 12):
        super().__init__()
        self._rounds = rounds
        self._count = 0

    def wait(self, timeout=None):
        self._count += 1
        return self._count > self._rounds  # signal stop → loop exits


def _make_static_device(device_id: str = "test-device") -> MagicMock:
    """Build a mock device that always returns the same static frame."""
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    device = MagicMock()
    device.device_id = device_id
    device.status = DeviceStatus.CONNECTED
    device.capture_screen.return_value = frame
    device.name = "Test Device"
    device.device_type = "windows"
    return device


@pytest.fixture
def handler_with_static_device() -> tuple[MessageHandler, MagicMock]:
    """MessageHandler wired to a single device returning a static frame."""
    device = _make_static_device()
    device_manager = MagicMock()
    device_manager._devices = {device.device_id: device}

    orchestrator = MagicMock()
    orchestrator._device_manager = device_manager

    handler = MessageHandler(orchestrator)
    # Mock _send_to_server to avoid asyncio / WebSocket coupling; we only
    # care about call count and the consecutive_errors control flow.
    handler._send_to_server = MagicMock()
    return handler, device


class TestScreenshotStreamDedup:
    """TD-009: dedup must not trip the consecutive_errors guard."""

    def test_static_screen_keeps_thread_alive_and_dedups(
        self, handler_with_static_device
    ):
        """Static frame for 12 rounds: send once, dedup 11, thread survives.

        Pre-fix (bug present):
          - round 1: send frame, sent_any_frame=True, errors=0
          - rounds 2..10: dedup skip, sent_any_frame=False, errors++ → 9
          - round 11: dedup skip, errors=10 >= max(10) → break
          - capture_screen.call_count == 11 (loop broke early)

        Post-fix (this test asserts):
          - round 1: send frame, processed_any_device=True, errors=0
          - rounds 2..12: dedup skip but processed_any_device=True, errors=0
          - loop exits cleanly via stop_event after 12 rounds
          - capture_screen.call_count == 12 (no early break)
          - _send_to_server.call_count == 1 (dedup working)
        """
        handler, device = handler_with_static_device
        handler._screenshot_stream_stop_event = _CountingEvent(rounds=12)

        # Run the loop inline (it exits when CountingEvent signals stop).
        handler._screenshot_stream_loop()

        # Dedup: only the first frame is sent, the other 11 are skipped.
        assert handler._send_to_server.call_count == 1, (
            "dedup should send exactly one frame for a static screen, "
            f"got {handler._send_to_server.call_count}"
        )
        # Loop stayed alive all 12 rounds — no early break from the bug.
        assert device.capture_screen.call_count == 12, (
            "loop should run 12 rounds on a static screen without tripping "
            "the consecutive_errors guard; capture was called "
            f"{device.capture_screen.call_count} times (bug would break at 11)"
        )
        # Per-device hash cache populated.
        assert "test-device" in handler._last_frame_hashes
        assert handler._last_frame_hashes["test-device"] != ""

    def test_first_frame_after_clear_is_sent(self, handler_with_static_device):
        """After _stop clears the hash cache, the next loop sends a fresh frame."""
        handler, device = handler_with_static_device

        # First run: sends 1 frame, dedups the rest.
        handler._screenshot_stream_stop_event = _CountingEvent(rounds=3)
        handler._screenshot_stream_loop()
        assert handler._send_to_server.call_count == 1
        assert "test-device" in handler._last_frame_hashes

        # Simulate stop: clears the cache (see _stop_screenshot_stream).
        handler._last_frame_hashes.clear()

        # Second run: cache is empty, so the first frame is sent again.
        handler._screenshot_stream_stop_event = _CountingEvent(rounds=3)
        handler._screenshot_stream_loop()
        assert handler._send_to_server.call_count == 2, (
            "after clearing the dedup cache, the first frame of the new "
            "stream must be sent; got call_count="
            f"{handler._send_to_server.call_count}"
        )

    def test_different_frames_are_all_sent(self, handler_with_static_device):
        """When frames differ each round, dedup never skips and all are sent."""
        handler, device = handler_with_static_device

        # Make capture_screen return a different frame each call so the
        # hash changes every round → dedup never hits.
        frame_seq = iter(
            np.full((100, 100, 3), fill_value=i, dtype=np.uint8)
            for i in range(12)
        )
        device.capture_screen.side_effect = lambda: next(frame_seq)

        handler._screenshot_stream_stop_event = _CountingEvent(rounds=12)
        handler._screenshot_stream_loop()

        # Every frame is different → every frame is sent.
        assert handler._send_to_server.call_count == 12, (
            "with all-different frames, dedup should never skip; "
            f"got {handler._send_to_server.call_count} sends"
        )
