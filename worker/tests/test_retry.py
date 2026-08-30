"""P0-2 retry decorator unit tests.

Tests the Alas-style @retry decorator with exception classification,
exception handler dispatch, interrupt checks, and the timeout utility.
"""

import asyncio
import io
import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from client.connection import WorkerConnection
from core.config import WorkerConfig
from core.retry import (
    retry,
    retry_input,
    retry_network,
    retry_screenshot,
)
from core.timeout import TimeoutError, call_with_timeout, with_timeout
from devices.adb.device import ADBDevice
from PIL import Image
from platforms.windows.screenshot import ScreenshotManager
from websockets.exceptions import ConnectionClosed

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# @retry — basic behaviour
# ---------------------------------------------------------------------------


class TestRetryBasic:
    """Basic retry semantics — success on first try, no retries invoked."""

    def test_success_no_retry(self):
        call_count = 0

        @retry(retries=3, delay=0.01)
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        assert succeed() == "ok"
        assert call_count == 1

    def test_returns_native_value(self):
        @retry(retries=2, delay=0.01)
        def returns_dict():
            return {"x": 1}

        assert returns_dict() == {"x": 1}

    def test_no_retry_on_unmatched_exception(self):
        call_count = 0

        @retry(retries=3, delay=0.01, exception=ValueError)
        def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("not in retry tuple")

        with pytest.raises(TypeError):
            raises_type_error()
        assert call_count == 1


# ---------------------------------------------------------------------------
# @retry — retry-then-succeed
# ---------------------------------------------------------------------------


class TestRetryRecovers:
    """Retries on matching exception and recovers when fn eventually succeeds."""

    def test_retries_then_succeeds(self):
        attempts = []

        @retry(retries=3, delay=0.01, exception=ConnectionError)
        def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("transient")
            return "recovered"

        assert flaky() == "recovered"
        assert len(attempts) == 3

    def test_retries_on_multiple_exception_types(self):
        attempts = []

        @retry(retries=4, delay=0.01, exception=(ConnectionError, TimeoutError))
        def flaky_multi():
            attempts.append(1)
            if len(attempts) == 1:
                raise ConnectionError("conn")
            if len(attempts) == 2:
                raise TimeoutError("timeout")
            return "ok"

        assert flaky_multi() == "ok"
        assert len(attempts) == 3


# ---------------------------------------------------------------------------
# @retry — exhaustion
# ---------------------------------------------------------------------------


class TestRetryExhaustion:
    """Retries exhaust and re-raise the last exception."""

    def test_exhausts_and_reraises(self):
        attempts = []

        @retry(retries=2, delay=0.01, exception=ConnectionError)
        def always_fails():
            attempts.append(1)
            raise ConnectionError("permanent")

        with pytest.raises(ConnectionError, match="permanent"):
            always_fails()
        assert len(attempts) == 3  # 1 initial + 2 retries

    def test_preserves_exception_type_and_message(self):
        @retry(retries=1, delay=0.01, exception=ValueError)
        def raises_value_error():
            raise ValueError("specific message")

        with pytest.raises(ValueError, match="specific message"):
            raises_value_error()


# ---------------------------------------------------------------------------
# @retry — exception handler dispatch
# ---------------------------------------------------------------------------


class TestRetryHandlerDispatch:
    """Exception handlers are invoked before retrying."""

    def test_handler_called_on_matching_exception(self):
        handler_calls = []

        def recovery(*args, **kwargs):
            handler_calls.append(1)

        @retry(
            retries=2,
            delay=0.01,
            exception=ConnectionResetError,
            exception_handlers={ConnectionResetError: recovery},
        )
        def flaky():
            raise ConnectionResetError("reset")

        with pytest.raises(ConnectionResetError):
            flaky()
        # Handler invoked on every failure: 1 initial + 2 retries = 3 calls
        assert len(handler_calls) == 3

    def test_handler_picks_most_specific_type(self):
        """When multiple handler keys match, the most derived class wins."""
        calls = []

        def handle_connection_error(*a, **kw):
            calls.append("base")

        def handle_connection_reset(*a, **kw):
            calls.append("specific")

        @retry(
            retries=1,
            delay=0.01,
            exception=ConnectionError,
            exception_handlers={
                ConnectionError: handle_connection_error,
                ConnectionResetError: handle_connection_reset,
            },
        )
        def raises_reset():
            raise ConnectionResetError("reset")

        with pytest.raises(ConnectionResetError):
            raises_reset()
        # Handler invoked on every failure: 1 initial + 1 retry = 2 calls,
        # all routed to the most-specific handler
        assert calls == ["specific", "specific"]

    def test_handler_raising_aborts_retry(self):
        """If the handler raises, that exception propagates immediately."""

        def abort_handler(*a, **kw):
            raise RuntimeError("unrecoverable")

        @retry(
            retries=3,
            delay=0.01,
            exception=ConnectionError,
            exception_handlers={ConnectionError: abort_handler},
        )
        def flaky():
            raise ConnectionError("transient")

        with pytest.raises(RuntimeError, match="unrecoverable"):
            flaky()


# ---------------------------------------------------------------------------
# @retry — on_retry callback
# ---------------------------------------------------------------------------


class TestRetryOnRetryCallback:
    """on_retry callback is invoked with attempt number and exception."""

    def test_on_retry_invoked(self):
        events = []

        def on_retry(attempt, exc):
            events.append((attempt, str(exc)))

        @retry(
            retries=2,
            delay=0.01,
            exception=ValueError,
            on_retry=on_retry,
        )
        def fails_twice():
            attempts = getattr(fails_twice, "_attempts", 0)
            fails_twice._attempts = attempts + 1
            if fails_twice._attempts < 3:
                raise ValueError(f"fail-{attempts + 1}")
            return "ok"

        assert fails_twice() == "ok"
        assert len(events) == 2
        assert events[0][0] == 1
        assert events[1][0] == 2

    def test_on_retry_failure_does_not_abort(self):
        """A failing on_retry callback logs but does not abort retries."""

        def bad_on_retry(attempt, exc):
            raise RuntimeError("on_retry broken")

        @retry(retries=2, delay=0.01, exception=ValueError, on_retry=bad_on_retry)
        def flaky():
            attempts = getattr(flaky, "_n", 0)
            flaky._n = attempts + 1
            if flaky._n < 3:
                raise ValueError("transient")
            return "ok"

        # Should still succeed — bad on_retry is logged, not propagated
        assert flaky() == "ok"


# ---------------------------------------------------------------------------
# @retry — interrupt handling
# ---------------------------------------------------------------------------


class TestRetryInterrupt:
    """stop_event / check_interrupt aborts retries."""

    def test_check_interrupt_aborts(self):
        call_count = 0

        def always_interrupt():
            return True

        @retry(
            retries=5,
            delay=0.01,
            exception=ValueError,
            check_interrupt=always_interrupt,
        )
        def never_runs():
            nonlocal call_count
            call_count += 1
            raise ValueError("should not get here")

        with pytest.raises(RuntimeError, match="interrupted"):
            never_runs()
        assert call_count == 0

    def test_stop_event_aborts_between_attempts(self):
        stop_event = threading.Event()
        attempts = []

        class Owner:
            def __init__(self):
                self._stop_event = stop_event

            @retry(retries=5, delay=0.01, exception=ValueError)
            def flaky_method(self):
                attempts.append(1)
                if len(attempts) == 2:
                    stop_event.set()
                raise ValueError("transient")

        owner = Owner()
        with pytest.raises(ValueError, match="transient"):
            owner.flaky_method()
        # First attempt fails, second attempt fails + sets event,
        # third iteration sees interrupt and re-raises last_exc.
        assert len(attempts) == 2


# ---------------------------------------------------------------------------
# call_with_timeout
# ---------------------------------------------------------------------------


class TestCallWithTimeout:
    """call_with_timeout utility behaviour."""

    def test_returns_value_when_fast(self):
        def add(a, b):
            return a + b

        assert call_with_timeout(add, 1.0, 2, 3) == 5

    def test_zero_timeout_calls_directly(self):
        def echo(x):
            return x

        assert call_with_timeout(echo, 0, "hi") == "hi"

    def test_negative_timeout_calls_directly(self):
        def echo(x):
            return x

        assert call_with_timeout(echo, -1, "hi") == "hi"

    def test_raises_timeout_when_slow(self):
        def slow():
            time.sleep(2.0)
            return "done"

        with pytest.raises(TimeoutError):
            call_with_timeout(slow, 0.1)

    def test_propagates_exception_from_func(self):
        def raises():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            call_with_timeout(raises, 1.0)

    def test_with_kwargs(self):
        def greet(name, greeting="hello"):
            return f"{greeting}, {name}"

        assert call_with_timeout(greet, 1.0, "world", greeting="hi") == "hi, world"


# ---------------------------------------------------------------------------
# with_timeout decorator
# ---------------------------------------------------------------------------


class TestWithTimeoutDecorator:
    """with_timeout decorator form."""

    def test_decorated_function_returns_value(self):
        @with_timeout(timeout_sec=1.0)
        def add(a, b):
            return a + b

        assert add(1, 2) == 3

    def test_decorated_function_times_out(self):
        @with_timeout(timeout_sec=0.1)
        def slow():
            time.sleep(2.0)

        with pytest.raises(TimeoutError):
            slow()

    def test_decorated_method(self):
        class Owner:
            @with_timeout(timeout_sec=1.0)
            def compute(self, x):
                return x * 2

        assert Owner().compute(21) == 42


# ---------------------------------------------------------------------------
# @retry — async support
# ---------------------------------------------------------------------------


class TestRetryAsync:
    """Async functions are retried with asyncio.sleep between attempts."""

    def test_async_retries_then_succeeds(self):
        attempts = []

        @retry(retries=2, delay=0.01, exception=ConnectionError)
        async def flaky_async():
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("transient")
            return "recovered"

        result = asyncio.run(flaky_async())
        assert result == "recovered"
        assert len(attempts) == 3

    def test_async_exhausts_and_reraises(self):
        attempts = []

        @retry(retries=1, delay=0.01, exception=ConnectionError)
        async def always_fails_async():
            attempts.append(1)
            raise ConnectionError("permanent")

        with pytest.raises(ConnectionError, match="permanent"):
            asyncio.run(always_fails_async())
        assert len(attempts) == 2

    def test_async_no_retry_on_unmatched_exception(self):
        attempts = []

        @retry(retries=2, delay=0.01, exception=ValueError)
        async def raises_type_error_async():
            attempts.append(1)
            raise TypeError("not matched")

        with pytest.raises(TypeError, match="not matched"):
            asyncio.run(raises_type_error_async())
        assert len(attempts) == 1


# ---------------------------------------------------------------------------
# Preset retry decorators
# ---------------------------------------------------------------------------


class TestRetryPresets:
    """Preset decorators retry on their configured exception taxonomies."""

    def test_retry_screenshot_retries_runtime_error(self):
        attempts = []

        @retry_screenshot(retries=1, delay=0.01)
        def flaky_screenshot():
            attempts.append(1)
            if len(attempts) < 2:
                raise RuntimeError("dll transient")
            return "frame"

        assert flaky_screenshot() == "frame"
        assert len(attempts) == 2

    def test_retry_input_retries_runtime_error(self):
        attempts = []

        @retry_input(retries=1, delay=0.01)
        def flaky_input():
            attempts.append(1)
            if len(attempts) < 2:
                raise RuntimeError("injection transient")
            return "ok"

        assert flaky_input() == "ok"
        assert len(attempts) == 2

    def test_retry_network_retries_connection_closed(self):
        attempts = []

        @retry_network(retries=1, delay=0.01)
        def flaky_network():
            attempts.append(1)
            if len(attempts) < 2:
                raise ConnectionClosed(None, None)  # type: ignore[arg-type]
            return "sent"

        assert flaky_network() == "sent"
        assert len(attempts) == 2


# ---------------------------------------------------------------------------
# Integration — ADB device retry-decorated paths
# ---------------------------------------------------------------------------


class TestRetryDeviceIntegration:
    """Retry-decorated ADB device methods retry on transient failures."""

    @staticmethod
    def _make_png_bytes(width: int = 10, height: int = 10) -> bytes:
        """Return a minimal valid PNG byte stream."""
        img = Image.new("RGB", (width, height), color=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_adb_screenshot_retries_then_succeeds(self):
        """_capture_screencap retries when the underlying adb call fails transiently."""
        device = ADBDevice()
        device._device = MagicMock()
        attempts = []

        def fail_twice():
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("capture transient")
            return self._make_png_bytes()

        device._device.screencap = fail_twice
        with patch("time.sleep"):  # skip retry delays
            result = device._capture_screencap()

        assert result is not None
        assert result.shape == (10, 10, 3)
        assert len(attempts) == 3  # 1 initial + 2 retries

    def test_adb_screenshot_retries_then_exhausts(self):
        """_capture_screencap re-raises the last exception after retries are exhausted."""
        device = ADBDevice()
        device._device = MagicMock()
        device._device.screencap.side_effect = RuntimeError("permanent")

        with patch("time.sleep"), pytest.raises(RuntimeError, match="permanent"):
            device._capture_screencap()

    def test_adb_input_click_retries_then_succeeds(self):
        """_input_adb_click retries when the underlying adb call fails transiently."""
        device = ADBDevice()
        device._device = MagicMock()
        attempts = []

        def fail_twice(x: int, y: int):
            attempts.append((x, y))
            if len(attempts) < 3:
                raise RuntimeError("click transient")

        device._device.click = fail_twice
        with patch("time.sleep"):  # skip retry delays
            device._input_adb_click(100, 200)

        assert len(attempts) == 3
        assert attempts[-1] == (100, 200)

    def test_adb_input_click_retries_then_exhausts(self):
        """_input_adb_click re-raises the last exception after retries are exhausted."""
        device = ADBDevice()
        device._device = MagicMock()
        device._device.click.side_effect = RuntimeError("permanent")

        with patch("time.sleep"), pytest.raises(RuntimeError, match="permanent"):
            device._input_adb_click(100, 200)


# ---------------------------------------------------------------------------
# Integration — Windows screenshot manager retry-decorated paths
# ---------------------------------------------------------------------------


class TestRetryWindowsScreenshotIntegration:
    """Retry-decorated Windows ScreenshotManager methods retry on transient failures."""

    def test_wgc_retries_then_succeeds(self):
        """_capture_wgc retries when the WGC capture surface fails transiently."""
        manager = ScreenshotManager(hwnd=12345, method="wgc")
        mock_wgc = MagicMock()
        attempts = []

        def fail_twice():
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("WGC transient")
            return np.zeros((100, 100, 3), dtype=np.uint8)

        mock_wgc.initialize.return_value = True
        mock_wgc.capture = fail_twice

        with (
            patch("platforms.windows.wgc.Win32WGC", return_value=mock_wgc),
            patch("time.sleep"),  # skip retry delays
        ):
            result = manager._capture_wgc()

        assert result is not None
        assert result.shape == (100, 100, 3)
        assert len(attempts) == 3

    def test_wgc_retries_then_exhausts(self):
        """_capture_wgc re-raises the last exception after retries are exhausted."""
        manager = ScreenshotManager(hwnd=12345, method="wgc")
        mock_wgc = MagicMock()
        mock_wgc.initialize.return_value = True
        mock_wgc.capture.side_effect = RuntimeError("WGC permanent")

        with (
            patch("platforms.windows.wgc.Win32WGC", return_value=mock_wgc),
            patch("time.sleep"),
            pytest.raises(RuntimeError, match="WGC permanent"),
        ):
            manager._capture_wgc()


# ---------------------------------------------------------------------------
# Integration — WebSocket client retry-decorated paths
# ---------------------------------------------------------------------------


class TestRetryWebSocketIntegration:
    """Retry-decorated WebSocket send_message retries on transient failures."""

    def test_send_message_retries_connection_closed(self):
        """send_message retries when the WebSocket raises ConnectionClosed."""
        config = WorkerConfig(server_url="ws://localhost:8000/ws")
        conn = WorkerConnection(config, resource_monitor=MagicMock())
        mock_ws = MagicMock()
        conn._ws = mock_ws
        conn._connected = True
        attempts = []

        async def fail_twice(message):
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionClosed(None, None)  # type: ignore[arg-type]

        mock_ws.send = fail_twice

        async def run():
            await conn.send_message("test", {"data": 1})

        with patch("asyncio.sleep"):  # skip retry delays
            asyncio.run(run())

        assert len(attempts) == 3

    def test_send_message_retries_then_exhausts(self):
        """send_message re-raises the last exception after retries are exhausted."""
        config = WorkerConfig(server_url="ws://localhost:8000/ws")
        conn = WorkerConnection(config, resource_monitor=MagicMock())
        mock_ws = MagicMock()
        conn._ws = mock_ws
        conn._connected = True

        async def always_fail(message):
            raise ConnectionClosed(None, None)  # type: ignore[arg-type]

        mock_ws.send = always_fail

        async def run():
            await conn.send_message("test", {"data": 1})

        with patch("asyncio.sleep"), pytest.raises(ConnectionClosed):
            asyncio.run(run())
