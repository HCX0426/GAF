"""WebSocket client reconnect / heartbeat / send-receive unit tests (Phase 4.8).

Covers ``client.connection.WorkerConnection``:
- Initial connection establishment (connect / register)
- Disconnect behavior
- Exponential backoff reconnection (_try_reconnect)
- Heartbeat thread start / idempotency / send
- Message send frame format and error handling
- Message dispatch routing (_dispatch_to_handler)
- URL / header / SSL context building
- Connection state transitions

The real ``websockets`` library is mocked throughout; no real network
connections are opened.
"""

import asyncio
import json
import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from client.connection import (
    MAX_BACKOFF,
    PING_INTERVAL,
    PING_TIMEOUT,
    WorkerConnection,
    _build_ws_url,
)
from core.config import WorkerConfig

pytestmark = pytest.mark.unit

# ============================================================
# Helpers / Fixtures
# ============================================================

def _make_config(**overrides) -> WorkerConfig:
    """Build an WorkerConfig with ws:// (no TLS) and sane test defaults."""
    defaults = {
        "server_url": "ws://127.0.0.1:8000/ws/protocol/agents/",
        "agent_token": "test-token",
        "device_type": "windows",
        "heartbeat_interval": 30,
    }
    defaults.update(overrides)
    return WorkerConfig(**defaults)


def _make_mock_ws():
    """Create a mock WebSocket object with async send/close methods."""
    ws = MagicMock()
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    ws.state = "OPEN"
    return ws


@pytest.fixture
def mock_resource_monitor():
    """A ResourceMonitor stub whose get_stats returns deterministic values."""
    monitor = MagicMock()
    monitor.get_stats.return_value = {"cpu": 10.0, "memory": 50.0, "fps": 30.0}
    return monitor


@pytest.fixture
def connection(mock_resource_monitor):
    """An WorkerConnection wired with a test config and mock monitor."""
    return WorkerConnection(_make_config(), resource_monitor=mock_resource_monitor)


# ============================================================
# URL building
# ============================================================

class TestBuildWsUrl:
    """``_build_ws_url`` appends token as a query parameter."""

    def test_with_token(self):
        url = _build_ws_url("ws://localhost:8000/ws/agents/", "secret")
        assert "token=secret" in url

    def test_without_token_returns_base(self):
        url = _build_ws_url("ws://localhost:8000/ws/agents/", "")
        assert url == "ws://localhost:8000/ws/agents/"

    def test_preserves_path(self):
        url = _build_ws_url("ws://host:8000/ws/protocol/agents/", "tok")
        assert url.startswith("ws://host:8000/ws/protocol/agents/")
        assert "token=tok" in url


# ============================================================
# Connection establishment
# ============================================================

class TestConnectEstablishment:
    """``connect()`` establishes the WebSocket and sends register."""

    def test_connect_success_sets_connected(self, connection):
        mock_ws = _make_mock_ws()

        async def fake_connect(*args, **kwargs):
            return mock_ws

        with patch("client.connection.ws_connect", side_effect=fake_connect):
            asyncio.run(connection.connect())

        assert connection.connected is True
        assert connection._ws is mock_ws

    def test_connect_success_resets_reconnect_delay(self, connection):
        connection._reconnect_delay = 16.0
        mock_ws = _make_mock_ws()

        async def fake_connect(*args, **kwargs):
            return mock_ws

        with patch("client.connection.ws_connect", side_effect=fake_connect):
            asyncio.run(connection.connect())

        assert connection._reconnect_delay == 1.0

    def test_connect_passes_ping_params(self, connection):
        mock_ws = _make_mock_ws()
        captured_kwargs = {}

        async def fake_connect(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_ws

        with patch("client.connection.ws_connect", side_effect=fake_connect):
            asyncio.run(connection.connect())

        assert captured_kwargs["ping_interval"] == PING_INTERVAL
        assert captured_kwargs["ping_timeout"] == PING_TIMEOUT

    def test_connect_sends_register(self, connection):
        mock_ws = _make_mock_ws()

        async def fake_connect(*args, **kwargs):
            return mock_ws

        with patch("client.connection.ws_connect", side_effect=fake_connect):
            asyncio.run(connection.connect())

        # _send_register calls send_message which calls ws.send.
        # spec-42: connect() also sends a Hello frame after register, so
        # we scan all sent frames rather than asserting on the last one.
        assert mock_ws.send.await_count >= 1
        sent_types = [
            json.loads(call.args[0])["type"]
            for call in mock_ws.send.await_args_list
        ]
        assert "agent.register" in sent_types
        # Find the register frame and validate its payload.
        register_frame = next(
            json.loads(call.args[0])
            for call in mock_ws.send.await_args_list
            if json.loads(call.args[0])["type"] == "agent.register"
        )
        assert "capabilities" in register_frame["payload"]

    def test_connect_failure_triggers_reconnect(self, connection):
        """When ws_connect raises, connect() delegates to _try_reconnect."""
        reconnect_called = []

        async def fake_reconnect():
            reconnect_called.append(True)
            # Simulate immediate success to avoid infinite loop
            connection._connected = True

        with patch("client.connection.ws_connect", side_effect=ConnectionError("refused")), \
             patch.object(connection, "_try_reconnect", side_effect=fake_reconnect):
            asyncio.run(connection.connect())

        assert reconnect_called == [True]

    def test_connect_passes_headers_with_token(self, connection):
        mock_ws = _make_mock_ws()
        captured_kwargs = {}

        async def fake_connect(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return mock_ws

        with patch("client.connection.ws_connect", side_effect=fake_connect):
            asyncio.run(connection.connect())

        headers = captured_kwargs.get("additional_headers", {})
        assert headers.get("X-Agent-Token") == "test-token"


# ============================================================
# Disconnect
# ============================================================

class TestDisconnect:
    """``disconnect()`` tears down the WebSocket cleanly."""

    def test_disconnect_sets_connected_false(self, connection):
        connection._ws = _make_mock_ws()
        connection._connected = True

        asyncio.run(connection.disconnect())

        assert connection.connected is False

    def test_disconnect_closes_ws(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True

        asyncio.run(connection.disconnect())

        mock_ws.close.assert_awaited_once()

    def test_disconnect_sets_ws_to_none(self, connection):
        connection._ws = _make_mock_ws()
        connection._connected = True

        asyncio.run(connection.disconnect())

        assert connection._ws is None

    def test_disconnect_with_no_ws_does_not_raise(self, connection):
        connection._ws = None
        connection._connected = False

        # Should not raise
        asyncio.run(connection.disconnect())


# ============================================================
# Reconnection with exponential backoff
# ============================================================

class TestReconnectBackoff:
    """``_try_reconnect`` uses exponential backoff capped at MAX_BACKOFF."""

    def test_reconnect_success_resets_delay(self, connection):
        mock_ws = _make_mock_ws()
        attempt = [0]

        async def fake_connect(*args, **kwargs):
            attempt[0] += 1
            if attempt[0] == 1:
                raise ConnectionError("down")
            return mock_ws

        async def fake_sleep(delay):
            pass

        with patch("client.connection.ws_connect", side_effect=fake_connect), \
             patch("client.connection.asyncio.sleep", side_effect=fake_sleep):
            asyncio.run(connection._try_reconnect())

        assert connection.connected is True
        assert connection._reconnect_delay == 1.0

    def test_reconnect_failure_doubles_delay(self, connection):
        """Each failed attempt doubles the delay up to MAX_BACKOFF."""
        delays = []
        attempt = [0]

        async def fake_connect(*args, **kwargs):
            attempt[0] += 1
            if attempt[0] <= 3:
                raise ConnectionError("still down")
            return _make_mock_ws()

        async def fake_sleep(delay):
            delays.append(delay)

        with patch("client.connection.ws_connect", side_effect=fake_connect), \
             patch("client.connection.asyncio.sleep", side_effect=fake_sleep):
            asyncio.run(connection._try_reconnect())

        # _try_reconnect sleeps BEFORE each attempt. 3 failures + 1 success = 4 sleeps.
        # Delays: 1.0 (before attempt 1), 2.0 (before attempt 2), 4.0 (before
        # attempt 3), 8.0 (before attempt 4 which succeeds and resets to 1.0).
        assert delays == [1.0, 2.0, 4.0, 8.0]

    def test_reconnect_delay_capped_at_max_backoff(self, connection):
        """Backoff never exceeds MAX_BACKOFF."""
        delays = []
        attempt = [0]

        async def fake_connect(*args, **kwargs):
            attempt[0] += 1
            if attempt[0] <= 7:
                raise ConnectionError("down")
            return _make_mock_ws()

        async def fake_sleep(delay):
            delays.append(delay)

        with patch("client.connection.ws_connect", side_effect=fake_connect), \
             patch("client.connection.asyncio.sleep", side_effect=fake_sleep):
            asyncio.run(connection._try_reconnect())

        # _try_reconnect sleeps BEFORE each attempt. 7 failures + 1 success = 8 sleeps.
        # Delays: 1, 2, 4, 8, 16, 30 (capped), 30, 30. After 16.0*2=32 is capped
        # to MAX_BACKOFF(30), subsequent delays stay at 30 until success.
        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 30, 30, 30]
        assert max(delays) <= MAX_BACKOFF

    def test_reconnect_success_sends_register(self, connection):
        mock_ws = _make_mock_ws()

        async def fake_connect(*args, **kwargs):
            return mock_ws

        async def fake_sleep(delay):
            pass

        with patch("client.connection.ws_connect", side_effect=fake_connect), \
             patch("client.connection.asyncio.sleep", side_effect=fake_sleep):
            asyncio.run(connection._try_reconnect())

        # _send_register was called. spec-42: _try_reconnect also sends a
        # Hello frame after register, so we scan all sent frames rather
        # than asserting on the last one.
        assert mock_ws.send.await_count >= 1
        sent_types = [
            json.loads(call.args[0])["type"]
            for call in mock_ws.send.await_args_list
        ]
        assert "agent.register" in sent_types

    def test_reconnect_uses_ws_url_with_token(self, connection):
        """Reconnect calls ws_connect with the pre-built URL containing token."""
        mock_ws = _make_mock_ws()
        captured_args = []

        async def fake_connect(*args, **kwargs):
            captured_args.append(args)
            return mock_ws

        async def fake_sleep(delay):
            pass

        with patch("client.connection.ws_connect", side_effect=fake_connect), \
             patch("client.connection.asyncio.sleep", side_effect=fake_sleep):
            asyncio.run(connection._try_reconnect())

        # First positional arg is the URL
        url = captured_args[0][0]
        assert "token=test-token" in url


# ============================================================
# Heartbeat
# ============================================================

class TestHeartbeat:
    """Heartbeat thread lifecycle and message sending."""

    def test_start_heartbeat_starts_thread(self, connection):
        connection._connected = True
        connection._loop = asyncio.new_event_loop()

        connection.start_heartbeat(interval=1)

        assert connection._heartbeat_thread is not None
        assert connection._heartbeat_thread.is_alive()

        # Cleanup: stop the thread
        connection._connected = False
        connection._heartbeat_thread.join(timeout=2)

    def test_start_heartbeat_idempotent(self, connection):
        """Calling start_heartbeat twice does not spawn a second thread."""
        connection._connected = True
        connection._loop = asyncio.new_event_loop()

        connection.start_heartbeat(interval=60)
        first_thread = connection._heartbeat_thread

        connection.start_heartbeat(interval=60)

        assert connection._heartbeat_thread is first_thread

        # Cleanup
        connection._connected = False
        first_thread.join(timeout=2)

    def test_start_heartbeat_restarts_after_exit(self, connection):
        """If the heartbeat thread has exited, start_heartbeat restarts it."""
        connection._connected = True
        connection._loop = asyncio.new_event_loop()

        # Use a short interval so the thread checks _connected quickly.
        connection.start_heartbeat(interval=0.05)
        first_thread = connection._heartbeat_thread

        # Simulate thread exit: set _connected=False so the loop exits on
        # the next iteration (within interval seconds).
        connection._connected = False
        first_thread.join(timeout=2)
        assert not first_thread.is_alive()

        # Restart
        connection._connected = True
        connection.start_heartbeat(interval=0.05)
        second_thread = connection._heartbeat_thread

        assert second_thread is not first_thread
        assert second_thread.is_alive()

        # Cleanup
        connection._connected = False
        second_thread.join(timeout=2)

    def test_send_heartbeat_noop_when_not_connected(self, connection):
        """_send_heartbeat does nothing when disconnected."""
        connection._ws = None
        connection._connected = False

        # Should not raise
        asyncio.run(connection._send_heartbeat({"cpu": 10.0}))

    def test_send_heartbeat_sends_heartbeat_frame(self, connection):
        """_send_heartbeat sends an agent.heartbeat frame with stats."""
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True

        stats = {"cpu": 42.0, "memory": 60.0, "fps": 25.0}
        asyncio.run(connection._send_heartbeat(stats))

        assert mock_ws.send.await_count == 1
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["type"] == "agent.heartbeat"
        assert sent["payload"]["stats"] == stats


# ============================================================
# Message send
# ============================================================

class TestSendMessage:
    """``send_message`` builds the standard frame and handles errors."""

    def test_send_increments_seq(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True

        asyncio.run(connection.send_message("task.result", {"task_id": 1}))
        seq_after_first = connection._seq

        asyncio.run(connection.send_message("task.progress", {"task_id": 1}))
        seq_after_second = connection._seq

        assert seq_after_second == seq_after_first + 1

    def test_send_returns_when_ws_is_none(self, connection):
        connection._ws = None
        connection._connected = True

        # Should not raise and should not send anything
        asyncio.run(connection.send_message("task.result", {"task_id": 1}))

    def test_send_returns_when_not_connected(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = False

        asyncio.run(connection.send_message("task.result", {"task_id": 1}))

        mock_ws.send.assert_not_awaited()

    def test_send_builds_correct_frame(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True

        asyncio.run(connection.send_message("task.result", {"task_id": 42, "success": True}))

        assert mock_ws.send.await_count == 1
        raw = mock_ws.send.call_args[0][0]
        frame = json.loads(raw)

        assert frame["type"] == "task.result"
        assert frame["trace_id"]  # non-empty UUID
        assert "seq" in frame
        assert "timestamp" in frame
        assert frame["payload"]["task_id"] == 42
        assert frame["payload"]["success"] is True

    def test_send_sets_connected_false_on_error(self, connection):
        """When ws.send raises a non-retryable error, _connected goes False."""
        mock_ws = _make_mock_ws()
        mock_ws.send = AsyncMock(side_effect=RuntimeError("broken pipe"))
        connection._ws = mock_ws
        connection._connected = True

        # RuntimeError is not in NETWORK_RETRY_EXCEPTIONS, so the retry
        # decorator does not retry and the exception propagates.
        with pytest.raises(RuntimeError, match="broken pipe"):
            asyncio.run(connection.send_message("task.result", {"task_id": 1}))

        assert connection.connected is False

    def test_send_serializes_dataclass_payload(self, connection):
        """send_message handles dataclass values in payload via _serialize_for_json."""
        import dataclasses

        @dataclasses.dataclass
        class MatchResult:
            score: float
            bbox: list

        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True

        payload = {"result": MatchResult(score=0.9, bbox=[1, 2, 3, 4])}
        asyncio.run(connection.send_message("task.result", payload))

        raw = mock_ws.send.call_args[0][0]
        frame = json.loads(raw)
        assert frame["payload"]["result"] == {"score": 0.9, "bbox": [1, 2, 3, 4]}


# ============================================================
# Message receive / dispatch
# ============================================================

class TestMessageDispatch:
    """``_dispatch_to_handler`` routes frames to the correct handler method."""

    def _make_handler(self):
        handler = MagicMock()
        return handler

    def test_dispatch_task_assign(self, connection):
        handler = self._make_handler()
        msg = {"type": "task.assign", "payload": {"task_id": 1, "task_name": "test"}}

        connection._dispatch_to_handler(msg, handler)

        handler.handle_task_assign.assert_called_once_with(
            {"task_id": 1, "task_name": "test"}, trace_id="",
        )

    def test_dispatch_task_dispatch_alias(self, connection):
        """task.dispatch is an alias for task.assign."""
        handler = self._make_handler()
        msg = {"type": "task.dispatch", "payload": {"task_id": 2}}

        connection._dispatch_to_handler(msg, handler)

        handler.handle_task_assign.assert_called_once_with({"task_id": 2}, trace_id="")

    def test_dispatch_event_ack_is_noop(self, connection):
        """event.ack does not trigger any handler method or warning."""
        handler = self._make_handler()
        msg = {"type": "event.ack", "payload": {"ack_type": "heartbeat"}}

        # Should not raise and should not call any handler method
        connection._dispatch_to_handler(msg, handler)

        handler.handle_task_assign.assert_not_called()

    def test_dispatch_task_cancel(self, connection):
        handler = self._make_handler()
        msg = {"type": "task.cancel", "payload": {"task_id": 5}}

        connection._dispatch_to_handler(msg, handler)

        handler.handle_task_cancel.assert_called_once_with({"task_id": 5}, trace_id="")

    def test_dispatch_pipeline_execute_not_handled(self, connection):
        """pipeline.execute 已从 handler_map 移除，不再分发到任何 handler。"""
        handler = self._make_handler()
        msg = {"type": "pipeline.execute", "payload": {"task_id": 9, "graph_data": {}}}

        connection._dispatch_to_handler(msg, handler)

        handler.handle_task_assign.assert_not_called()

    def test_dispatch_falls_back_to_data_key(self, connection):
        """Legacy frames using 'data' instead of 'payload' are still dispatched."""
        handler = self._make_handler()
        msg = {"type": "task.assign", "data": {"task_id": 7}}

        connection._dispatch_to_handler(msg, handler)

        handler.handle_task_assign.assert_called_once_with({"task_id": 7}, trace_id="")

    def test_dispatch_unknown_type_logs_warning(self, connection, caplog):
        """Unknown message types log a warning (not error)."""
        import logging

        handler = self._make_handler()
        msg = {"type": "unknown.type", "payload": {}}

        with caplog.at_level(logging.WARNING):
            connection._dispatch_to_handler(msg, handler)

        assert any("unknown.type" in record.message for record in caplog.records)


class TestListenLoop:
    """``listen()`` receives messages and dispatches them."""

    def test_listen_dispatches_received_messages(self, connection):
        """The listen loop parses incoming JSON and dispatches to handler."""
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True

        # Build an async iterable that yields one message then stops
        messages = [
            json.dumps({"type": "task.assign", "payload": {"task_id": 11}}),
        ]

        async def async_iter():
            for m in messages:
                yield m

        mock_ws.__aiter__ = MagicMock(return_value=async_iter())

        handler = MagicMock()

        async def run_listen():
            # The loop exits when the async iterator is exhausted AND
            # _connected is still True — we force-exit by setting
            # _connected = False after the first message.

            original_dispatch = connection._dispatch_to_handler

            def dispatch_and_stop(msg, h):
                original_dispatch(msg, h)
                connection._connected = False

            with (
                patch.object(connection, "_dispatch_to_handler", side_effect=dispatch_and_stop),
                # Patch start_heartbeat to avoid spawning a real thread
                patch.object(connection, "start_heartbeat"),
            ):
                await connection.listen(handler)

        asyncio.run(run_listen())

        handler.handle_task_assign.assert_called_once_with({"task_id": 11}, trace_id="")

    def test_listen_sets_send_callback(self, connection):
        """listen() wires handler.send_callback to send_message."""
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True


        async def async_iter():
            return
            yield  # make it an async generator

        mock_ws.__aiter__ = MagicMock(return_value=async_iter())

        handler = MagicMock()

        async def run_listen():
            # Exit immediately after wiring by setting _connected=False
            connection._connected = False
            with patch.object(connection, "start_heartbeat"):
                await connection.listen(handler)

        asyncio.run(run_listen())

        assert handler.send_callback == connection.send_message


# ============================================================
# Headers and SSL context
# ============================================================

class TestHeadersAndSsl:
    """``_build_headers`` and ``_build_ssl_context`` behavior."""

    def test_build_headers_with_token(self, connection):
        headers = connection._build_headers()
        assert headers["X-Agent-Token"] == "test-token"

    def test_build_headers_without_token(self, mock_resource_monitor):
        config = _make_config(agent_token="")
        conn = WorkerConnection(config, resource_monitor=mock_resource_monitor)
        assert conn._build_headers() == {}

    def test_build_ssl_context_no_tls(self, connection):
        """ws:// URL does not enable TLS; ssl context is None."""
        assert connection._build_ssl_context() is None

    def test_build_ssl_context_wss_enables_tls(self, mock_resource_monitor):
        config = _make_config(server_url="wss://127.0.0.1:8000/ws/protocol/agents/")
        conn = WorkerConnection(config, resource_monitor=mock_resource_monitor)
        ctx = conn._build_ssl_context()
        assert ctx is not None
        assert isinstance(ctx, ssl.SSLContext)

    def test_build_ssl_context_wss_no_verify(self, mock_resource_monitor):
        config = _make_config(
            server_url="wss://127.0.0.1:8000/ws/protocol/agents/",
            ssl_verify=False,
        )
        conn = WorkerConnection(config, resource_monitor=mock_resource_monitor)
        ctx = conn._build_ssl_context()
        assert ctx.check_hostname is False
        assert ctx.verify_mode == ssl.CERT_NONE


# ============================================================
# Connection state transitions
# ============================================================

class TestStateTransitions:
    """Connection state moves through connecting -> connected -> disconnected."""

    def test_initial_state_disconnected(self, connection):
        assert connection.connected is False
        assert connection._ws is None
        assert connection._reconnect_delay == 1.0

    def test_connect_then_disconnect(self, connection):
        mock_ws = _make_mock_ws()

        async def fake_connect(*args, **kwargs):
            return mock_ws

        with patch("client.connection.ws_connect", side_effect=fake_connect):
            asyncio.run(connection.connect())

        assert connection.connected is True

        asyncio.run(connection.disconnect())

        assert connection.connected is False
        assert connection._ws is None

    def test_send_error_transitions_to_disconnected(self, connection):
        """A send failure transitions state from connected to disconnected."""
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        assert connection.connected is True

        mock_ws.send = AsyncMock(side_effect=RuntimeError("socket closed"))

        with pytest.raises(RuntimeError):
            asyncio.run(connection.send_message("task.result", {"task_id": 1}))

        assert connection.connected is False

    def test_reconnect_transitions_to_reconnecting_then_connected(self, connection):
        """After disconnection, _try_reconnect transitions back to connected."""
        mock_ws = _make_mock_ws()
        attempt = [0]

        async def fake_connect(*args, **kwargs):
            attempt[0] += 1
            if attempt[0] == 1:
                raise ConnectionError("server restarting")
            return mock_ws

        async def fake_sleep(delay):
            pass

        connection._connected = False

        with patch("client.connection.ws_connect", side_effect=fake_connect), \
             patch("client.connection.asyncio.sleep", side_effect=fake_sleep):
            asyncio.run(connection._try_reconnect())

        assert connection.connected is True
        assert connection._reconnect_delay == 1.0


class TestRegisterCapabilities:
    """_send_register capabilities 声明 (2026-09-05).

    Windows agent 机器上检测到 ADB (模拟器) 也必须声明 adb 能力, 否则需要
    adb 的任务永远匹配不到本 agent (实测 task 22 报"无具备所需能力 (adb)").
    """

    @staticmethod
    def _make_conn(device_type):
        conn = WorkerConnection.__new__(WorkerConnection)
        conn._config = MagicMock()
        conn._config.device_type = device_type
        conn.send_message = AsyncMock()
        return conn

    def test_windows_agent_with_adb_declares_adb(self):
        conn = self._make_conn("windows")
        with patch.object(WorkerConnection, "_adb_available", return_value=True):
            asyncio.run(conn._send_register())
        payload = conn.send_message.await_args.args[1]
        assert payload["capabilities"]["adb"] is True
        assert payload["capabilities"]["windows"] is True

    def test_windows_agent_without_adb_no_adb_cap(self):
        conn = self._make_conn("windows")
        with patch.object(WorkerConnection, "_adb_available", return_value=False):
            asyncio.run(conn._send_register())
        payload = conn.send_message.await_args.args[1]
        assert "adb" not in payload["capabilities"]
        assert payload["capabilities"]["windows"] is True

    def test_emulator_agent_declares_adb(self):
        conn = self._make_conn("emulator")
        asyncio.run(conn._send_register())
        payload = conn.send_message.await_args.args[1]
        assert payload["capabilities"]["adb"] is True

    def test_adb_available_true_when_path_found(self):
        with patch("devices.emulator_discovery.EmulatorDiscovery._discover_adb_path", return_value="D:/adb.exe"):
            assert WorkerConnection._adb_available() is True

    def test_adb_available_false_when_not_found(self):
        with patch("devices.emulator_discovery.EmulatorDiscovery._discover_adb_path", return_value=None):
            assert WorkerConnection._adb_available() is False
