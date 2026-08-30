"""P1-3 NemuIpc keepalive unit tests.

Tests platforms.windows.nemu_keepalive:
- NemuIpcKeepalive lifecycle: start/stop/is_running/context manager
- Interval clamping (MIN_KEEPALIVE_INTERVAL_SEC)
- Idempotent start/stop
- ping_fn invocation + on_failure callback
- make_ping_fn(): success / connect_id=0 / timeout / exception
"""
import threading
import time
from unittest.mock import MagicMock

import pytest
from platforms.windows.nemu_keepalive import (
    DEFAULT_KEEPALIVE_INTERVAL_SEC,
    MIN_KEEPALIVE_INTERVAL_SEC,
    NemuIpcKeepalive,
    make_ping_fn,
)

pytestmark = pytest.mark.unit


class TestConstants:
    """Module-level constants."""

    def test_default_interval_is_25s(self):
        # MuMu12 idle timeout is ~30s; 25s leaves a 5s safety margin.
        assert DEFAULT_KEEPALIVE_INTERVAL_SEC == 25.0

    def test_min_interval_is_5s(self):
        assert MIN_KEEPALIVE_INTERVAL_SEC == 5.0

    def test_default_greater_than_min(self):
        assert DEFAULT_KEEPALIVE_INTERVAL_SEC > MIN_KEEPALIVE_INTERVAL_SEC


class TestNemuIpcKeepaliveInit:
    """__init__ and property tests."""

    def test_default_init(self):
        keeper = NemuIpcKeepalive(ping_fn=lambda: 0)
        assert keeper.interval == DEFAULT_KEEPALIVE_INTERVAL_SEC
        assert keeper.is_running is False

    def test_custom_interval(self):
        keeper = NemuIpcKeepalive(ping_fn=lambda: 0, interval_sec=10.0)
        assert keeper.interval == 10.0

    def test_interval_clamped_to_min(self):
        # 1s is below MIN_KEEPALIVE_INTERVAL_SEC, should clamp.
        keeper = NemuIpcKeepalive(ping_fn=lambda: 0, interval_sec=1.0)
        assert keeper.interval == MIN_KEEPALIVE_INTERVAL_SEC

    def test_interval_exactly_at_min(self):
        keeper = NemuIpcKeepalive(
            ping_fn=lambda: 0, interval_sec=MIN_KEEPALIVE_INTERVAL_SEC,
        )
        assert keeper.interval == MIN_KEEPALIVE_INTERVAL_SEC

    def test_is_running_false_before_start(self):
        keeper = NemuIpcKeepalive(ping_fn=lambda: 0)
        assert keeper.is_running is False

    def test_on_failure_optional(self):
        # No on_failure supplied — should not crash on construction.
        keeper = NemuIpcKeepalive(ping_fn=lambda: 0)
        assert keeper._on_failure is None


class TestNemuIpcKeepaliveLifecycle:
    """start/stop lifecycle tests."""

    def test_start_sets_running(self):
        keeper = NemuIpcKeepalive(
            ping_fn=lambda: 0, interval_sec=MIN_KEEPALIVE_INTERVAL_SEC,
        )
        try:
            keeper.start()
            assert keeper.is_running is True
        finally:
            keeper.stop()

    def test_stop_clears_running(self):
        keeper = NemuIpcKeepalive(
            ping_fn=lambda: 0, interval_sec=MIN_KEEPALIVE_INTERVAL_SEC,
        )
        keeper.start()
        keeper.stop()
        assert keeper.is_running is False

    def test_start_is_idempotent(self):
        # Calling start() twice should not spawn a second thread.
        keeper = NemuIpcKeepalive(
            ping_fn=lambda: 0, interval_sec=MIN_KEEPALIVE_INTERVAL_SEC,
        )
        try:
            keeper.start()
            first_thread = keeper._thread
            keeper.start()
            assert keeper._thread is first_thread
        finally:
            keeper.stop()

    def test_stop_is_idempotent(self):
        # Calling stop() twice should not raise.
        keeper = NemuIpcKeepalive(ping_fn=lambda: 0)
        keeper.start()
        keeper.stop()
        keeper.stop()  # second stop is a no-op

    def test_stop_without_start_is_noop(self):
        keeper = NemuIpcKeepalive(ping_fn=lambda: 0)
        # Should not raise even though never started.
        keeper.stop()

    def test_thread_is_daemon(self):
        keeper = NemuIpcKeepalive(
            ping_fn=lambda: 0, interval_sec=MIN_KEEPALIVE_INTERVAL_SEC,
        )
        try:
            keeper.start()
            assert keeper._thread is not None
            assert keeper._thread.daemon is True
        finally:
            keeper.stop()


class TestNemuIpcKeepalivePing:
    """Ping invocation tests."""

    def test_ping_called_after_interval(self):
        ping_count = 0
        count_lock = threading.Lock()

        def ping_fn():
            nonlocal ping_count
            with count_lock:
                ping_count += 1
            return 0

        keeper = NemuIpcKeepalive(
            ping_fn=ping_fn, interval_sec=MIN_KEEPALIVE_INTERVAL_SEC,
        )
        try:
            keeper.start()
            # Wait a bit beyond one interval for the first ping to fire.
            time.sleep(MIN_KEEPALIVE_INTERVAL_SEC + 0.5)
            assert ping_count >= 1
        finally:
            keeper.stop()

    def test_ping_continues_after_failure(self):
        # ping_fn returning non-zero should NOT kill the loop.
        ping_count = 0
        count_lock = threading.Lock()

        def ping_fn():
            nonlocal ping_count
            with count_lock:
                ping_count += 1
            return 1783  # recoverable error code

        keeper = NemuIpcKeepalive(
            ping_fn=ping_fn, interval_sec=MIN_KEEPALIVE_INTERVAL_SEC,
        )
        try:
            keeper.start()
            time.sleep(MIN_KEEPALIVE_INTERVAL_SEC + 0.5)
            assert ping_count >= 1
        finally:
            keeper.stop()

    def test_ping_continues_after_exception(self):
        ping_count = 0
        count_lock = threading.Lock()

        def ping_fn():
            nonlocal ping_count
            with count_lock:
                ping_count += 1
            raise RuntimeError("synthetic ping failure")

        keeper = NemuIpcKeepalive(
            ping_fn=ping_fn, interval_sec=MIN_KEEPALIVE_INTERVAL_SEC,
        )
        try:
            keeper.start()
            time.sleep(MIN_KEEPALIVE_INTERVAL_SEC + 0.5)
            assert ping_count >= 1
        finally:
            keeper.stop()

    def test_on_failure_callback_invoked_on_nonzero(self):
        failures = []
        fail_lock = threading.Lock()

        def on_failure(ret_code):
            with fail_lock:
                failures.append(ret_code)

        keeper = NemuIpcKeepalive(
            ping_fn=lambda: 1783,
            interval_sec=MIN_KEEPALIVE_INTERVAL_SEC,
            on_failure=on_failure,
        )
        try:
            keeper.start()
            time.sleep(MIN_KEEPALIVE_INTERVAL_SEC + 0.5)
            assert 1783 in failures
        finally:
            keeper.stop()

    def test_on_failure_callback_not_invoked_on_success(self):
        failures = []
        fail_lock = threading.Lock()

        def on_failure(ret_code):
            with fail_lock:
                failures.append(ret_code)

        keeper = NemuIpcKeepalive(
            ping_fn=lambda: 0,
            interval_sec=MIN_KEEPALIVE_INTERVAL_SEC,
            on_failure=on_failure,
        )
        try:
            keeper.start()
            time.sleep(MIN_KEEPALIVE_INTERVAL_SEC + 0.5)
            assert failures == []
        finally:
            keeper.stop()

    def test_on_failure_exception_does_not_kill_loop(self):
        # If on_failure raises, the loop should keep running.
        ping_count = 0
        count_lock = threading.Lock()

        def ping_fn():
            nonlocal ping_count
            with count_lock:
                ping_count += 1
            return 1783

        def bad_on_failure(ret_code):
            raise ValueError("intentional on_failure error")

        keeper = NemuIpcKeepalive(
            ping_fn=ping_fn,
            interval_sec=MIN_KEEPALIVE_INTERVAL_SEC,
            on_failure=bad_on_failure,
        )
        try:
            keeper.start()
            time.sleep(MIN_KEEPALIVE_INTERVAL_SEC + 0.5)
            assert ping_count >= 1
        finally:
            keeper.stop()


class TestNemuIpcKeepaliveContextManager:
    """Context manager __enter__ / __exit__."""

    def test_context_manager_starts_and_stops(self):
        keeper = NemuIpcKeepalive(
            ping_fn=lambda: 0, interval_sec=MIN_KEEPALIVE_INTERVAL_SEC,
        )
        with keeper:
            assert keeper.is_running is True
        assert keeper.is_running is False

    def test_context_manager_stop_on_exception(self):
        keeper = NemuIpcKeepalive(
            ping_fn=lambda: 0, interval_sec=MIN_KEEPALIVE_INTERVAL_SEC,
        )
        with pytest.raises(RuntimeError, match="intentional"), keeper:
            assert keeper.is_running is True
            raise RuntimeError("intentional")
        assert keeper.is_running is False


class TestNemuIpcKeepaliveStopTimeout:
    """stop() timeout behavior."""

    def test_stop_returns_within_reasonable_time(self):
        # Even with a long interval, stop() should return quickly because
        # the loop uses interruptible wait on stop_event.
        keeper = NemuIpcKeepalive(
            ping_fn=lambda: 0, interval_sec=60.0,  # long interval
        )
        keeper.start()
        start = time.monotonic()
        keeper.stop(timeout=2.0)
        elapsed = time.monotonic() - start
        # Should return well under 1s, but allow generous margin for CI.
        assert elapsed < 1.0


class TestMakePingFn:
    """make_ping_fn() factory tests."""

    def test_returns_zero_when_connect_id_is_zero(self):
        lib = MagicMock()
        ping = make_ping_fn(lib, connect_id_getter=lambda: 0)
        # Should short-circuit without touching lib.
        assert ping() == 0
        lib.nemu_capture_display.assert_not_called()

    def test_returns_zero_on_successful_ping(self):
        lib = MagicMock()
        lib.nemu_capture_display.return_value = 0
        ping = make_ping_fn(lib, connect_id_getter=lambda: 42)
        assert ping() == 0

    def test_returns_error_code_on_failure(self):
        lib = MagicMock()
        lib.nemu_capture_display.return_value = 1783
        ping = make_ping_fn(lib, connect_id_getter=lambda: 42)
        assert ping() == 1783

    def test_returns_negative_on_timeout(self):
        from core.timeout import TimeoutError

        lib = MagicMock()
        lib.nemu_capture_display.side_effect = TimeoutError("synthetic")
        ping = make_ping_fn(lib, connect_id_getter=lambda: 42)
        assert ping() == -1

    def test_returns_negative_on_exception(self):
        lib = MagicMock()
        lib.nemu_capture_display.side_effect = OSError("synthetic")
        ping = make_ping_fn(lib, connect_id_getter=lambda: 42)
        assert ping() == -2

    def test_passes_connect_id_to_lib(self):
        lib = MagicMock()
        lib.nemu_capture_display.return_value = 0
        ping = make_ping_fn(lib, connect_id_getter=lambda: 99)
        ping()
        # First positional arg is the function, then connect_id.
        # call_with_timeout invokes fn(*args) — check the call args.
        args = lib.nemu_capture_display.call_args.args
        assert args[0] == 99  # connect_id

    def test_uses_length_zero_for_noop_query(self):
        lib = MagicMock()
        lib.nemu_capture_display.return_value = 0
        ping = make_ping_fn(lib, connect_id_getter=lambda: 1)
        ping()
        args = lib.nemu_capture_display.call_args.args
        # Arg layout: (connect_id, display_id, length, width_ptr, height_ptr, nullptr)
        assert args[1] == 0  # display_id
        assert args[2] == 0  # length=0 → no-op query
