"""TD-019: ScreenshotCache wiring into the screenshot capture path.

Regression tests for the integration between ``client.handler._capture_one_device``
and ``devices.screenshot_cache.get_default_cache``. Verifies that:

1. On cache hit, ``cv2.imencode`` is NOT called (cached bytes reused).
2. On cache miss, ``cv2.imencode`` runs and the result is stored via
   ``ScreenshotCache.set`` for future reuse.
3. Cache write failures are non-fatal — the screenshot stream still
   returns True (capture succeeded).
4. A static screen captured 10 times triggers at most 2 JPEG encodes
   (first miss + first set; subsequent hits skip encode).
5. When the frame changes between captures, no cache hit occurs and
   ``cv2.imencode`` runs every time.
"""

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

pytestmark = pytest.mark.e2e

# Ensure src on path (conftest already does this, but be explicit for direct runs)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import client.handler  # noqa: E402
from devices.base import DeviceStatus  # noqa: E402
from devices.screenshot_cache import ScreenshotCache  # noqa: E402


def _make_static_device(
    device_id: str = "test-device",
    frame: np.ndarray | None = None,
) -> MagicMock:
    """Build a mock device that returns ``frame`` from capture_screen()."""
    if frame is None:
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
    device = MagicMock()
    device.device_id = device_id
    device.status = DeviceStatus.CONNECTED
    device.capture_screen.return_value = frame
    device.name = "Test Device"
    device.device_type = "windows"
    device.hwnd = None
    return device


def _make_handler(device: MagicMock) -> "client.handler.MessageHandler":
    """MessageHandler wired to a single mock device."""
    device_manager = MagicMock()
    device_manager._devices = {device.device_id: device}

    orchestrator = MagicMock()
    orchestrator._device_manager = device_manager

    handler = client.handler.MessageHandler(orchestrator)
    # Avoid asyncio / WebSocket coupling; we only care about the encode
    # path. _send_to_server is mocked so no frame actually leaves.
    handler._send_to_server = MagicMock()
    return handler


@pytest.fixture(autouse=True)
def _reset_default_cache_singleton():
    """Reset the module-level ScreenshotCache singleton between tests.

    Each test patches ``get_default_cache`` with its own cache instance,
    but resetting the singleton avoids cross-test contamination if any
    test forgets to patch.
    """
    from devices import screenshot_cache as sc_module

    sc_module._default_cache = None
    yield
    sc_module._default_cache = None


class _CountingEvent(threading.Event):
    """Event whose wait() returns False N times then True (stop signal)."""

    def __init__(self, rounds: int = 12):
        super().__init__()
        self._rounds = rounds
        self._count = 0

    def wait(self, timeout=None):
        self._count += 1
        return self._count > self._rounds  # signal stop → loop exits


class TestScreenshotCacheWiring:
    """Tests for the ScreenshotCache wire-in at handler.py L889-918."""

    def test_cache_hit_skips_imencode(self):
        """On cache hit, cv2.imencode is NOT called and cached bytes reused."""
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        device = _make_static_device(frame=frame)
        handler = _make_handler(device)

        # Pre-populate the cache with a known JPEG byte string so the
        # first capture hits the cache. Use a real ScreenshotCache
        # instance so compute_frame_hash + set/get roundtrip correctly.
        real_cache = ScreenshotCache(default_ttl=300, max_memory_entries=10)
        # Compute the frame hash the same way the handler does, then
        # pre-seed the cache.
        from devices.screenshot_cache import compute_frame_hash

        fh = compute_frame_hash(frame)
        real_cache.set(device.device_id, fh, b"CACHED-JPEG-BYTES")

        with (
            patch("client.handler.get_default_cache", return_value=real_cache),
            patch("client.handler.cv2.imencode") as mock_encode,
        ):
            # If the cache check is bypassed, this would be called.
            # We assert it's NOT called when the cache hits.
            result = handler._capture_one_device(
                device, stop_event=threading.Event()
            )

        assert result is True, "cache hit should still return True (capture succeeded)"
        mock_encode.assert_not_called()
        # The frame was sent with the cached bytes base64-encoded.
        assert handler._send_to_server.call_count == 1
        sent_payload = handler._send_to_server.call_args[0][1]
        # b64encode(b"CACHED-JPEG-BYTES") == "Q0FDSEVELUpQRUctQllURVM="
        import base64

        assert sent_payload["image_base64"] == base64.b64encode(
            b"CACHED-JPEG-BYTES"
        ).decode("utf-8")
        real_cache.clear()

    def test_cache_miss_encodes_and_stores(self):
        """On cache miss, cv2.imencode runs and result is stored in cache."""
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        device = _make_static_device(frame=frame)
        handler = _make_handler(device)

        real_cache = ScreenshotCache(default_ttl=300, max_memory_entries=10)
        fake_buf = np.frombuffer(b"ENCODED-JPEG", dtype=np.uint8)

        with (
            patch("client.handler.get_default_cache", return_value=real_cache),
            patch("client.handler.cv2.imencode", return_value=(True, fake_buf)) as mock_encode,
        ):
            result = handler._capture_one_device(
                device, stop_event=threading.Event()
            )

        assert result is True
        mock_encode.assert_called_once()
        # Verify the encoded bytes were stored in the cache.
        from devices.screenshot_cache import compute_frame_hash

        fh = compute_frame_hash(frame)
        cached = real_cache.get(device.device_id, fh)
        assert cached == b"ENCODED-JPEG", (
            "cache miss should call ScreenshotCache.set with the encoded bytes"
        )
        real_cache.clear()

    def test_cache_set_failure_non_fatal(self):
        """If ScreenshotCache.set raises, capture still returns True."""
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        device = _make_static_device(frame=frame)
        handler = _make_handler(device)

        # Cache returns None (miss) but set raises — handler must not crash.
        flaky_cache = MagicMock(spec=ScreenshotCache)
        flaky_cache.get.return_value = None
        flaky_cache.set.side_effect = RuntimeError("Redis connection lost")

        fake_buf = np.frombuffer(b"ENCODED-JPEG", dtype=np.uint8)

        with (
            patch("client.handler.get_default_cache", return_value=flaky_cache),
            patch("client.handler.cv2.imencode", return_value=(True, fake_buf)),
        ):
            result = handler._capture_one_device(
                device, stop_event=threading.Event()
            )

        assert result is True, (
            "cache write failure must be non-fatal — capture still succeeds"
        )
        flaky_cache.get.assert_called_once()
        flaky_cache.set.assert_called_once()
        # Frame was still sent (encode path completed).
        assert handler._send_to_server.call_count == 1

    def test_static_screen_10_captures_le_2_encodes(self):
        """10 captures of the same static frame → ≤ 2 cv2.imencode calls.

        Expected sequence:
          - capture 1: cache miss → encode (1) + set
          - captures 2..10: cache hit → skip encode

        The dedup layer (``self._last_frame_hashes``) short-circuits
        BEFORE the cache lookup, so for captures 2..10 the cache is
        never even queried. To exercise the cache path for ALL 10
        captures, we clear the dedup hash between calls. This simulates
        a stream where the same frame is requested again after a
        reconnection or a per-device hash reset, while the cache
        remains warm.

        Assert: cv2.imencode call count == 1 (first miss). The TD-019
        register entry allows ≤ 2 (covers a TTL expiry mid-run); we
        tighten to == 1 here for a non-expiring cache.
        """
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        device = _make_static_device(frame=frame)
        handler = _make_handler(device)

        real_cache = ScreenshotCache(default_ttl=300, max_memory_entries=10)
        encode_count = 0
        real_buf = np.frombuffer(b"JPEG-BYTES", dtype=np.uint8)

        def fake_imencode(*args, **kwargs):
            nonlocal encode_count
            encode_count += 1
            return (True, real_buf)

        with (
            patch("client.handler.get_default_cache", return_value=real_cache),
            patch("client.handler.cv2.imencode", side_effect=fake_imencode),
        ):
            for _ in range(10):
                    # Clear the dedup hash so each capture reaches the
                    # cache lookup. Without this the dedup short-circuits
                    # captures 2..10 before they reach the cache.
                    handler._last_frame_hashes.pop(device.device_id, None)
                    result = handler._capture_one_device(
                        device, stop_event=threading.Event()
                    )
                    assert result is True

        assert encode_count <= 2, (
            "static screen captured 10× with a warm cache must trigger at "
            f"most 2 encodes (1 first miss + at most 1 TTL expiry); got "
            f"{encode_count}"
        )
        # Tighter assertion: with a 300s TTL no entry expires mid-test,
        # so exactly 1 encode should occur.
        assert encode_count == 1, (
            f"expected exactly 1 encode on a 10× static capture with non-"
            f"expiring cache; got {encode_count}"
        )
        # All 10 captures sent a frame (cache hits still send).
        assert handler._send_to_server.call_count == 10
        real_cache.clear()

    def test_frame_hash_changes_reencodes(self):
        """When frame changes between captures, cv2.imencode runs each time."""
        handler_device = _make_static_device(frame=np.zeros((100, 100, 3), dtype=np.uint8))
        device = handler_device
        handler = _make_handler(device)

        real_cache = ScreenshotCache(default_ttl=300, max_memory_entries=10)

        frame_a = np.zeros((100, 100, 3), dtype=np.uint8)
        frame_b = np.full((100, 100, 3), fill_value=42, dtype=np.uint8)

        encode_count = 0
        real_buf = np.frombuffer(b"JPEG-BYTES", dtype=np.uint8)

        def fake_imencode(*args, **kwargs):
            nonlocal encode_count
            encode_count += 1
            return (True, real_buf)

        with (
            patch("client.handler.get_default_cache", return_value=real_cache),
            patch("client.handler.cv2.imencode", side_effect=fake_imencode),
        ):
            # Capture frame A — miss + encode + set.
            device.capture_screen.return_value = frame_a
            handler._last_frame_hashes.pop(device.device_id, None)
            assert handler._capture_one_device(
                device, stop_event=threading.Event()
            ) is True

            # Capture frame B — different hash, miss + encode + set.
            device.capture_screen.return_value = frame_b
            handler._last_frame_hashes.pop(device.device_id, None)
            assert handler._capture_one_device(
                device, stop_event=threading.Event()
            ) is True

        assert encode_count == 2, (
            "two different frames must trigger 2 encodes (no cache hit on "
            f"the second); got {encode_count}"
        )
        # Both frames were sent.
        assert handler._send_to_server.call_count == 2
        real_cache.clear()


class TestScreenshotStreamLoopIntegration:
    """Integration test exercising the full _screenshot_stream_loop with cache."""

    def test_static_screen_loop_runs_12_rounds_with_warm_cache(self):
        """Loop with a static frame: 12 rounds, 1 encode (first miss), 11 hits.

        Uses the real ScreenshotCache so the wiring is exercised
        end-to-end. The dedup layer skips sends on rounds 2..12, but
        this test asserts that IF dedup were cleared (e.g. by a brief
        disconnect), the cache would prevent re-encoding.
        """
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        device = _make_static_device(frame=frame)
        handler = _make_handler(device)

        real_cache = ScreenshotCache(default_ttl=300, max_memory_entries=10)
        encode_count = 0
        real_buf = np.frombuffer(b"JPEG-BYTES", dtype=np.uint8)

        def fake_imencode(*args, **kwargs):
            nonlocal encode_count
            encode_count += 1
            return (True, real_buf)

        # Force the dedup hash to be empty so every round reaches the
        # cache lookup. This simulates a stream where the per-device
        # hash is reset on every capture (e.g. a misbehaving caller),
        # isolating the cache behavior from the dedup behavior.
        original_capture = handler._capture_one_device

        def capture_no_dedup(device, stop_event):
            handler._last_frame_hashes.pop(device.device_id, None)
            return original_capture(device, stop_event)

        handler._screenshot_stream_stop_event = _CountingEvent(rounds=12)

        with (
            patch("client.handler.get_default_cache", return_value=real_cache),
            patch("client.handler.cv2.imencode", side_effect=fake_imencode),
            patch.object(
                handler, "_capture_one_device", side_effect=capture_no_dedup
            ),
        ):
            handler._screenshot_stream_loop()

        # 12 rounds, only the first should encode (cache hits for the rest).
        assert encode_count <= 2, (
            f"expected ≤ 2 encodes for 12× static capture (warm cache); "
            f"got {encode_count}"
        )
        # Without dedup, every round still sends (cache hits send too).
        assert handler._send_to_server.call_count == 12, (
            "all 12 captures should send a frame (cache hit still sends); "
            f"got {handler._send_to_server.call_count}"
        )
        real_cache.clear()
