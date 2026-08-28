"""压缩相关测试合并 (negotiation + e2e + message_compressor)

合并说明: 原 test_compression_negotiation.py + test_compression_e2e.py + test_message_compressor.py。
三者共享相同的 _make_config / _make_mock_ws / mock_resource_monitor / connection 测试基础设施。
"""

from __future__ import annotations

import asyncio
import json
import zlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from client.connection import AgentConnection
from core.config import AgentConfig
from utils.message_compressor import (
    COMPRESSION_ALGORITHM_MSGPACK_ZLIB,
    DEFAULT_COMPRESS_THRESHOLD,
    HelloFrameError,
    MessageCompressor,
    MessageCompressorError,
    build_hello_ack_frame,
    build_hello_frame,
    parse_hello_ack_capabilities,
    parse_hello_capabilities,
)

pytestmark = pytest.mark.unit

# Wire-format constants
_FORMAT_JSON = 0x01
_FORMAT_MSGPACK = 0x02
_FLAG_RAW = 0x00
_FLAG_ZLIB = 0x01
_HEADER_SIZE = 5


# ===========================================================================
# 共享 Helpers / Fixtures
# ===========================================================================


def _make_config(**overrides) -> AgentConfig:
    """Build an AgentConfig with ws:// (no TLS) and sane test defaults."""
    defaults = {
        "server_url": "ws://127.0.0.1:8000/ws/protocol/agents/",
        "agent_token": "test-token",
        "device_type": "windows",
        "heartbeat_interval": 30,
    }
    defaults.update(overrides)
    return AgentConfig(**defaults)


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
    """An AgentConnection wired with a test config and mock monitor."""
    return AgentConnection(_make_config(), resource_monitor=mock_resource_monitor)


def _decode_sent_frame(send_call):
    """Decode a frame sent via ws.send — handles both text and bytes wire formats."""
    arg = send_call.args[0] if send_call.args else send_call.kwargs.get("message")
    if isinstance(arg, (bytes, bytearray)):
        return MessageCompressor(compress_threshold=1).decompress(arg)
    return json.loads(arg)


def _negotiate(connection, *, threshold: int = DEFAULT_COMPRESS_THRESHOLD):
    """Flip the connection into negotiated state with a fresh compressor."""
    connection._compression_negotiated = True
    connection._compressor = MessageCompressor(compress_threshold=threshold)


# ===========================================================================
# MessageCompressor: round-trip tests (原 test_message_compressor.py)
# ===========================================================================


class TestMessageCompressorRoundTrip:
    """Verify MessageCompressor.compress → decompress returns original payload."""

    def test_small_payload_json_round_trip(self):
        compressor = MessageCompressor(compress_threshold=1024, use_msgpack=False)
        payload = {"type": "agent.heartbeat", "seq": 1}
        wire = compressor.compress(payload)
        assert wire[0] == _FORMAT_JSON
        assert wire[1] == _FLAG_RAW
        assert wire[2:5] == b"\x00\x00\x00"
        result = compressor.decompress(wire)
        assert result == payload

    def test_large_payload_json_zlib_round_trip(self):
        compressor = MessageCompressor(compress_threshold=64, use_msgpack=False)
        payload = {"type": "task.dispatch", "data": "x" * 200}
        wire = compressor.compress(payload)
        assert wire[0] == _FORMAT_JSON
        assert wire[1] == _FLAG_ZLIB
        result = compressor.decompress(wire)
        assert result == payload

    def test_msgpack_round_trip_when_available(self):
        try:
            import msgpack  # noqa: F401
        except ImportError:
            pytest.skip("msgpack not installed — skipping msgpack path test")
        compressor = MessageCompressor(compress_threshold=32, use_msgpack=True)
        payload = {"type": "screenshot.frame", "data": b"\x00" * 200}
        wire = compressor.compress(payload)
        assert wire[0] == _FORMAT_MSGPACK
        assert wire[1] == _FLAG_ZLIB
        result = compressor.decompress(wire)
        assert result == payload

    def test_threshold_boundary_no_compression(self):
        body = json.dumps({"x": "y" * 50}, ensure_ascii=False).encode("utf-8")
        threshold = len(body) + 1
        compressor = MessageCompressor(compress_threshold=threshold, use_msgpack=False)
        wire = compressor.compress({"x": "y" * 50})
        assert wire[1] == _FLAG_RAW

    def test_threshold_boundary_compression_at_equal(self):
        body = json.dumps({"x": "y" * 50}, ensure_ascii=False).encode("utf-8")
        threshold = len(body)
        compressor = MessageCompressor(compress_threshold=threshold, use_msgpack=False)
        wire = compressor.compress({"x": "y" * 50})
        assert wire[1] == _FLAG_ZLIB

    def test_none_payload_treated_as_empty_dict(self):
        compressor = MessageCompressor(use_msgpack=False)
        wire = compressor.compress(None)
        result = compressor.decompress(wire)
        assert result == {}


class TestMessageCompressorErrors:
    """Verify error handling for malformed wire bytes and bad constructor args."""

    def test_decompress_rejects_non_bytes(self):
        compressor = MessageCompressor()
        with pytest.raises(MessageCompressorError) as ctx:
            compressor.decompress("not bytes")
        assert "expected bytes" in str(ctx.value)

    def test_decompress_rejects_short_data(self):
        compressor = MessageCompressor()
        with pytest.raises(MessageCompressorError) as ctx:
            compressor.decompress(b"\x00\x00")
        assert "data too short" in str(ctx.value)

    def test_decompress_rejects_unknown_format_byte(self):
        compressor = MessageCompressor()
        bad = bytes([0xFF, _FLAG_RAW]) + b"\x00\x00\x00" + b"{}"
        with pytest.raises(MessageCompressorError) as ctx:
            compressor.decompress(bad)
        assert "unknown format byte" in str(ctx.value)

    def test_decompress_rejects_unknown_flag_byte(self):
        compressor = MessageCompressor()
        bad = bytes([_FORMAT_JSON, 0xFF]) + b"\x00\x00\x00" + b"{}"
        with pytest.raises(MessageCompressorError) as ctx:
            compressor.decompress(bad)
        assert "unknown flag byte" in str(ctx.value)

    def test_decompress_rejects_corrupted_zlib_body(self):
        compressor = MessageCompressor()
        bad = bytes([_FORMAT_JSON, _FLAG_ZLIB]) + b"\x00\x00\x00" + b"not-zlib"
        with pytest.raises(MessageCompressorError) as ctx:
            compressor.decompress(bad)
        assert "zlib decompress failed" in str(ctx.value)

    def test_decompress_rejects_invalid_json_body(self):
        compressor = MessageCompressor()
        bad = bytes([_FORMAT_JSON, _FLAG_RAW]) + b"\x00\x00\x00" + b"not-json"
        with pytest.raises(MessageCompressorError) as ctx:
            compressor.decompress(bad)
        assert "json decode failed" in str(ctx.value)

    def test_constructor_rejects_negative_threshold(self):
        with pytest.raises(ValueError):
            MessageCompressor(compress_threshold=-1)

    def test_constructor_rejects_invalid_zlib_level(self):
        with pytest.raises(ValueError):
            MessageCompressor(zlib_level=99)

    def test_compress_rejects_non_serializable_payload(self):
        compressor = MessageCompressor(use_msgpack=False)
        with pytest.raises(MessageCompressorError) as ctx:
            compressor.compress({"bad": object()})
        assert "serialization failed" in str(ctx.value)


class TestMessageCompressorProperties:
    """Verify property accessors."""

    def test_threshold_property_returns_constructor_value(self):
        compressor = MessageCompressor(compress_threshold=512)
        assert compressor.compress_threshold == 512

    def test_uses_msgpack_property_reflects_availability(self):
        try:
            import msgpack  # noqa: F401
        except ImportError:
            pytest.skip("msgpack not installed")
        compressor = MessageCompressor(use_msgpack=True)
        assert compressor.uses_msgpack is True
        compressor = MessageCompressor(use_msgpack=False)
        assert compressor.uses_msgpack is False


# ===========================================================================
# Hello frame builders and parsers (原 test_message_compressor.py)
# ===========================================================================


class TestBuildHelloFrame:
    """Verify build_hello_frame produces correct frame structure."""

    def test_defaults(self):
        frame = build_hello_frame(["msgpack+zlib"])
        assert frame["type"] == "hello"
        assert frame["seq"] == 1
        assert "trace_id" in frame
        assert "timestamp" in frame
        assert frame["payload"]["compression"]["algorithms"] == ["msgpack+zlib"]
        assert frame["payload"]["compression"]["threshold"] == DEFAULT_COMPRESS_THRESHOLD

    def test_custom_threshold_and_seq(self):
        frame = build_hello_frame(["msgpack+zlib"], threshold=2048, seq=42)
        assert frame["seq"] == 42
        assert frame["payload"]["compression"]["threshold"] == 2048

    def test_custom_trace_id(self):
        frame = build_hello_frame(["msgpack+zlib"], trace_id="abc-123")
        assert frame["trace_id"] == "abc-123"

    def test_multiple_algorithms(self):
        frame = build_hello_frame(["msgpack+zlib", "zstd"])
        assert frame["payload"]["compression"]["algorithms"] == ["msgpack+zlib", "zstd"]

    def test_empty_algorithms_raises(self):
        with pytest.raises(HelloFrameError):
            build_hello_frame([])

    def test_negative_threshold_raises(self):
        with pytest.raises(HelloFrameError):
            build_hello_frame(["msgpack+zlib"], threshold=-1)

    def test_non_int_threshold_raises(self):
        with pytest.raises(HelloFrameError):
            build_hello_frame(["msgpack+zlib"], threshold="big")

    def test_algorithms_list_is_copied(self):
        algos = ["msgpack+zlib"]
        frame = build_hello_frame(algos)
        algos.append("zstd")
        assert frame["payload"]["compression"]["algorithms"] == ["msgpack+zlib"]


class TestBuildHelloAckFrame:
    """Verify build_hello_ack_frame produces correct frame structure."""

    def test_defaults(self):
        frame = build_hello_ack_frame("msgpack+zlib")
        assert frame["type"] == "hello.ack"
        assert frame["seq"] == 1
        assert frame["payload"]["compression"]["algorithm"] == "msgpack+zlib"
        assert frame["payload"]["compression"]["threshold"] == DEFAULT_COMPRESS_THRESHOLD
        assert frame["payload"]["compression"]["enabled"] is True

    def test_disabled_flag(self):
        frame = build_hello_ack_frame("msgpack+zlib", enabled=False)
        assert frame["payload"]["compression"]["enabled"] is False

    def test_custom_threshold_and_seq(self):
        frame = build_hello_ack_frame("msgpack+zlib", threshold=512, seq=7)
        assert frame["payload"]["compression"]["threshold"] == 512
        assert frame["seq"] == 7

    def test_empty_algorithm_raises(self):
        with pytest.raises(HelloFrameError):
            build_hello_ack_frame("")

    def test_negative_threshold_raises(self):
        with pytest.raises(HelloFrameError):
            build_hello_ack_frame("msgpack+zlib", threshold=-1)

    def test_non_int_threshold_raises(self):
        with pytest.raises(HelloFrameError):
            build_hello_ack_frame("msgpack+zlib", threshold=1.5)


class TestParseHelloCapabilities:
    """Verify parse_hello_capabilities extracts (algorithms, threshold)."""

    def test_round_trip(self):
        frame = build_hello_frame(["msgpack+zlib"], threshold=2048)
        algos, threshold = parse_hello_capabilities(frame)
        assert algos == ["msgpack+zlib"]
        assert threshold == 2048

    def test_default_threshold_when_missing(self):
        frame = {"type": "hello", "payload": {"compression": {"algorithms": ["msgpack+zlib"]}}}
        algos, threshold = parse_hello_capabilities(frame)
        assert threshold == DEFAULT_COMPRESS_THRESHOLD

    def test_non_dict_frame_raises(self):
        with pytest.raises(HelloFrameError):
            parse_hello_capabilities("not a dict")

    def test_wrong_type_raises(self):
        with pytest.raises(HelloFrameError):
            parse_hello_capabilities({"type": "hello.ack"})

    def test_missing_payload_raises(self):
        with pytest.raises(HelloFrameError):
            parse_hello_capabilities({"type": "hello"})

    def test_missing_compression_raises(self):
        with pytest.raises(HelloFrameError):
            parse_hello_capabilities({"type": "hello", "payload": {}})

    def test_empty_algorithms_raises(self):
        frame = {"type": "hello", "payload": {"compression": {"algorithms": []}}}
        with pytest.raises(HelloFrameError):
            parse_hello_capabilities(frame)

    def test_non_list_algorithms_raises(self):
        frame = {"type": "hello", "payload": {"compression": {"algorithms": "msgpack+zlib"}}}
        with pytest.raises(HelloFrameError):
            parse_hello_capabilities(frame)

    def test_invalid_threshold_raises(self):
        frame = {"type": "hello", "payload": {"compression": {"algorithms": ["msgpack+zlib"], "threshold": -1}}}
        with pytest.raises(HelloFrameError):
            parse_hello_capabilities(frame)

    def test_non_dict_compression_raises(self):
        frame = {"type": "hello", "payload": {"compression": "not a dict"}}
        with pytest.raises(HelloFrameError):
            parse_hello_capabilities(frame)


class TestParseHelloAckCapabilities:
    """Verify parse_hello_ack_capabilities extracts (algorithm, threshold, enabled)."""

    def test_round_trip(self):
        frame = build_hello_ack_frame("msgpack+zlib", threshold=512, enabled=True)
        algo, threshold, enabled = parse_hello_ack_capabilities(frame)
        assert algo == "msgpack+zlib"
        assert threshold == 512
        assert enabled is True

    def test_disabled_flag(self):
        frame = build_hello_ack_frame("msgpack+zlib", enabled=False)
        _, _, enabled = parse_hello_ack_capabilities(frame)
        assert enabled is False

    def test_non_dict_frame_raises(self):
        with pytest.raises(HelloFrameError):
            parse_hello_ack_capabilities(None)

    def test_wrong_type_raises(self):
        with pytest.raises(HelloFrameError):
            parse_hello_ack_capabilities({"type": "hello"})

    def test_missing_payload_raises(self):
        with pytest.raises(HelloFrameError):
            parse_hello_ack_capabilities({"type": "hello.ack"})

    def test_missing_compression_raises(self):
        with pytest.raises(HelloFrameError):
            parse_hello_ack_capabilities({"type": "hello.ack", "payload": {}})

    def test_missing_algorithm_raises(self):
        frame = {"type": "hello.ack", "payload": {"compression": {"threshold": 1024, "enabled": True}}}
        with pytest.raises(HelloFrameError):
            parse_hello_ack_capabilities(frame)

    def test_empty_algorithm_raises(self):
        frame = {"type": "hello.ack", "payload": {"compression": {"algorithm": ""}}}
        with pytest.raises(HelloFrameError):
            parse_hello_ack_capabilities(frame)

    def test_non_str_algorithm_raises(self):
        frame = {"type": "hello.ack", "payload": {"compression": {"algorithm": 123}}}
        with pytest.raises(HelloFrameError):
            parse_hello_ack_capabilities(frame)

    def test_invalid_threshold_raises(self):
        frame = {"type": "hello.ack", "payload": {"compression": {"algorithm": "msgpack+zlib", "threshold": -1}}}
        with pytest.raises(HelloFrameError):
            parse_hello_ack_capabilities(frame)

    def test_default_threshold_when_missing(self):
        frame = {"type": "hello.ack", "payload": {"compression": {"algorithm": "msgpack+zlib"}}}
        _, threshold, _ = parse_hello_ack_capabilities(frame)
        assert threshold == DEFAULT_COMPRESS_THRESHOLD

    def test_default_enabled_when_missing(self):
        frame = {"type": "hello.ack", "payload": {"compression": {"algorithm": "msgpack+zlib", "threshold": 1024}}}
        _, _, enabled = parse_hello_ack_capabilities(frame)
        assert enabled is True


class TestWireFormatEnvelope:
    """Verify the 5-byte header layout is stable across compress paths."""

    def test_header_size_is_5_bytes(self):
        compressor = MessageCompressor(use_msgpack=False)
        wire = compressor.compress({"x": 1})
        assert len(wire) >= _HEADER_SIZE
        assert wire[2:5] == b"\x00\x00\x00"

    def test_reserved_bytes_always_zero(self):
        compressor = MessageCompressor(compress_threshold=1, use_msgpack=False)
        wire_zlib = compressor.compress({"x": "y" * 100})
        assert wire_zlib[2:5] == b"\x00\x00\x00"
        compressor_raw = MessageCompressor(compress_threshold=10_000, use_msgpack=False)
        wire_raw = compressor_raw.compress({"x": "y" * 100})
        assert wire_raw[2:5] == b"\x00\x00\x00"

    def test_format_byte_distinct_for_json_vs_msgpack(self):
        c_json = MessageCompressor(use_msgpack=False)
        wire_json = c_json.compress({"x": 1})
        assert wire_json[0] == _FORMAT_JSON
        try:
            import msgpack  # noqa: F401
        except ImportError:
            pytest.skip("msgpack not installed")
        c_msgpack = MessageCompressor(use_msgpack=True)
        wire_msgpack = c_msgpack.compress({"x": 1})
        assert wire_msgpack[0] == _FORMAT_MSGPACK
        assert wire_json[0] != wire_msgpack[0]

    def test_compressed_body_is_valid_zlib_stream(self):
        compressor = MessageCompressor(compress_threshold=1, use_msgpack=False)
        wire = compressor.compress({"x": "y" * 100})
        assert wire[1] == _FLAG_ZLIB
        body = wire[_HEADER_SIZE:]
        decompressed = zlib.decompress(body)
        assert json.loads(decompressed.decode("utf-8")) == {"x": "y" * 100}


class TestProtocolConstants:
    """Verify protocol constants used in negotiation frames."""

    def test_algorithm_identifier_value(self):
        assert COMPRESSION_ALGORITHM_MSGPACK_ZLIB == "msgpack+zlib"

    def test_default_threshold_value(self):
        assert DEFAULT_COMPRESS_THRESHOLD == 1024

    def test_hello_frame_type_is_lowercase(self):
        frame = build_hello_frame(["msgpack+zlib"])
        assert frame["type"] == "hello"

    def test_hello_ack_frame_type_is_lowercase(self):
        frame = build_hello_ack_frame("msgpack+zlib")
        assert frame["type"] == "hello.ack"


class TestNegotiationRoundTrip:
    """End-to-end negotiation frame exchange."""

    def test_full_negotiation_flow(self):
        agent_hello = build_hello_frame(
            algorithms=[COMPRESSION_ALGORITHM_MSGPACK_ZLIB],
            threshold=1024,
        )
        algos, threshold = parse_hello_capabilities(agent_hello)
        assert COMPRESSION_ALGORITHM_MSGPACK_ZLIB in algos
        server_ack = build_hello_ack_frame(
            algorithm=COMPRESSION_ALGORITHM_MSGPACK_ZLIB,
            threshold=threshold,
            enabled=True,
        )
        algo, thr, enabled = parse_hello_ack_capabilities(server_ack)
        assert algo == COMPRESSION_ALGORITHM_MSGPACK_ZLIB
        assert thr == 1024
        assert enabled is True

    def test_server_declines_compression(self):
        agent_hello = build_hello_frame(
            algorithms=[COMPRESSION_ALGORITHM_MSGPACK_ZLIB],
            threshold=1024,
        )
        _, _ = parse_hello_capabilities(agent_hello)
        server_ack = build_hello_ack_frame(
            algorithm=COMPRESSION_ALGORITHM_MSGPACK_ZLIB,
            threshold=1024,
            enabled=False,
        )
        _, _, enabled = parse_hello_ack_capabilities(server_ack)
        assert enabled is False


# ===========================================================================
# AgentConnection compression negotiation tests (原 test_compression_negotiation.py)
# ===========================================================================


class TestConnectSendsHello:
    """``connect()`` and ``_try_reconnect()`` must send a Hello frame after register."""

    def test_connect_sends_hello_after_register(self, connection):
        mock_ws = _make_mock_ws()

        async def fake_connect(*args, **kwargs):
            return mock_ws

        with patch("client.connection.ws_connect", side_effect=fake_connect):
            asyncio.run(connection.connect())

        sent_types = [json.loads(call.args[0])["type"] for call in mock_ws.send.await_args_list]
        assert "agent.register" in sent_types
        assert "hello" in sent_types
        assert sent_types.index("hello") > sent_types.index("agent.register")

    def test_connect_hello_frame_advertises_supported_algorithm(self, connection):
        mock_ws = _make_mock_ws()

        async def fake_connect(*args, **kwargs):
            return mock_ws

        with patch("client.connection.ws_connect", side_effect=fake_connect):
            asyncio.run(connection.connect())

        hello_call = next(
            call for call in mock_ws.send.await_args_list
            if json.loads(call.args[0])["type"] == "hello"
        )
        hello_frame = json.loads(hello_call.args[0])
        assert hello_frame["payload"]["compression"]["algorithms"] == [COMPRESSION_ALGORITHM_MSGPACK_ZLIB]
        assert hello_frame["payload"]["compression"]["threshold"] == DEFAULT_COMPRESS_THRESHOLD

    def test_reconnect_resets_state_and_resends_hello(self, connection):
        connection._compression_negotiated = True
        connection._compressor = MessageCompressor()
        connection._connected = False

        mock_ws = _make_mock_ws()

        async def fake_connect(*args, **kwargs):
            return mock_ws

        async def fake_sleep(delay):
            pass

        with patch("client.connection.ws_connect", side_effect=fake_connect), \
             patch("client.connection.asyncio.sleep", side_effect=fake_sleep):
            asyncio.run(connection._try_reconnect())

        assert connection._compression_negotiated is False
        assert connection._compressor is None
        sent_types = [json.loads(call.args[0])["type"] for call in mock_ws.send.await_args_list]
        assert "agent.register" in sent_types
        assert "hello" in sent_types


class TestHandleHelloAck:
    """``_handle_hello_ack`` flips negotiation state based on server response."""

    def test_valid_ack_enables_compression(self, connection):
        ack = build_hello_ack_frame(algorithm=COMPRESSION_ALGORITHM_MSGPACK_ZLIB, threshold=1024, enabled=True)
        assert connection._compression_negotiated is False
        assert connection._compressor is None
        connection._handle_hello_ack(ack)
        assert connection._compression_negotiated is True
        assert connection._compressor is not None
        assert connection._compressor.compress_threshold == 1024

    def test_disabled_ack_keeps_compression_off(self, connection):
        ack = build_hello_ack_frame(algorithm=COMPRESSION_ALGORITHM_MSGPACK_ZLIB, threshold=1024, enabled=False)
        connection._handle_hello_ack(ack)
        assert connection._compression_negotiated is False
        assert connection._compressor is None

    def test_unsupported_algorithm_keeps_compression_off(self, connection):
        ack = build_hello_ack_frame(algorithm="zstd+v1", threshold=1024, enabled=True)
        connection._handle_hello_ack(ack)
        assert connection._compression_negotiated is False
        assert connection._compressor is None

    def test_malformed_ack_keeps_compression_off(self, connection):
        bad_ack = {"type": "hello.ack"}
        connection._handle_hello_ack(bad_ack)
        assert connection._compression_negotiated is False
        assert connection._compressor is None

    def test_wrong_type_ack_keeps_compression_off(self, connection):
        not_an_ack = build_hello_frame(["msgpack+zlib"])
        connection._handle_hello_ack(not_an_ack)
        assert connection._compression_negotiated is False
        assert connection._compressor is None

    def test_custom_threshold_propagates_to_compressor(self, connection):
        ack = build_hello_ack_frame(algorithm=COMPRESSION_ALGORITHM_MSGPACK_ZLIB, threshold=512, enabled=True)
        connection._handle_hello_ack(ack)
        assert connection._compressor.compress_threshold == 512


class TestSendMessageCompressionPath:
    """``send_message`` picks wire format based on negotiation + size."""

    def test_pre_negotiation_sends_json_text(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        assert connection._compression_negotiated is False
        asyncio.run(connection.send_message("task.result", {"task_id": 1}))
        assert mock_ws.send.await_count == 1
        sent = mock_ws.send.call_args.args[0]
        assert isinstance(sent, str)
        frame = json.loads(sent)
        assert frame["type"] == "task.result"

    def test_post_negotiation_small_payload_sends_json_text(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        connection._compression_negotiated = True
        connection._compressor = MessageCompressor(compress_threshold=10_000)
        asyncio.run(connection.send_message("task.result", {"task_id": 1}))
        assert mock_ws.send.await_count == 1
        sent = mock_ws.send.call_args.args[0]
        assert isinstance(sent, str)

    def test_post_negotiation_large_payload_sends_compressed_bytes(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        connection._compression_negotiated = True
        connection._compressor = MessageCompressor(compress_threshold=32)
        large_payload = {"task_id": 1, "data": "x" * 500}
        asyncio.run(connection.send_message("task.result", large_payload))
        assert mock_ws.send.await_count == 1
        sent = mock_ws.send.call_args.args[0]
        assert isinstance(sent, (bytes, bytearray))
        decoded = connection._compressor.decompress(sent)
        assert decoded["type"] == "task.result"
        assert decoded["payload"]["data"] == "x" * 500

    def test_compress_failure_falls_back_to_json_text(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        connection._compression_negotiated = True
        bad_compressor = MagicMock()
        bad_compressor.compress.side_effect = MessageCompressorError("boom")
        bad_compressor.compress_threshold = 1
        connection._compressor = bad_compressor
        asyncio.run(connection.send_message("task.result", {"task_id": 1}))
        assert mock_ws.send.await_count == 1
        sent = mock_ws.send.call_args.args[0]
        assert isinstance(sent, str)
        frame = json.loads(sent)
        assert frame["type"] == "task.result"


class TestDisconnectResetsState:
    """``disconnect()`` resets compression state so re-connect re-negotiates."""

    def test_disconnect_clears_negotiation_state(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        connection._compression_negotiated = True
        connection._compressor = MessageCompressor()
        asyncio.run(connection.disconnect())
        assert connection._compression_negotiated is False
        assert connection._compressor is None


class TestListenInterceptsHelloAck:
    """``listen()`` intercepts Hello.ack before any handler runs."""

    def test_listen_processes_hello_ack(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        ack_frame = build_hello_ack_frame(algorithm=COMPRESSION_ALGORITHM_MSGPACK_ZLIB, threshold=1024, enabled=True)
        messages = [json.dumps(ack_frame)]

        async def async_iter():
            for m in messages:
                yield m

        mock_ws.__aiter__ = MagicMock(return_value=async_iter())
        handler = MagicMock()

        async def run_listen():
            with patch.object(connection, "start_heartbeat"):
                original_handle = connection._handle_hello_ack

                def handle_and_stop(frame):
                    original_handle(frame)
                    connection._connected = False

                with patch.object(connection, "_handle_hello_ack", side_effect=handle_and_stop):
                    await connection.listen(handler)

        asyncio.run(run_listen())
        assert connection._compression_negotiated is True
        handler.handle_task_assign.assert_not_called()


class TestListenHandlesCompressedBytes:
    """``listen()`` decompresses bytes frames post-negotiation."""

    def test_listen_decompresses_bytes_frame(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        connection._compression_negotiated = True
        connection._compressor = MessageCompressor(compress_threshold=32)
        task_frame = {
            "type": "task.assign",
            "trace_id": "test-trace",
            "seq": 1,
            "timestamp": "2026-07-20T12:00:00Z",
            "payload": {"task_id": 42},
        }
        compressed = connection._compressor.compress(task_frame)

        async def async_iter():
            yield compressed

        mock_ws.__aiter__ = MagicMock(return_value=async_iter())
        handler = MagicMock()

        async def run_listen():
            with patch.object(connection, "start_heartbeat"):
                original_dispatch = connection._dispatch_to_handler

                def dispatch_and_stop(msg, h):
                    original_dispatch(msg, h)
                    connection._connected = False

                with patch.object(connection, "_dispatch_to_handler", side_effect=dispatch_and_stop):
                    await connection.listen(handler)

        asyncio.run(run_listen())
        handler.handle_task_assign.assert_called_once_with({"task_id": 42}, trace_id="test-trace")

    def test_listen_drops_bytes_frame_pre_negotiation(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        assert connection._compressor is None

        async def async_iter():
            try:
                yield b"\x01\x01\x00\x00\x00not-valid-zlib"
            finally:
                connection._connected = False

        mock_ws.__aiter__ = MagicMock(return_value=async_iter())
        handler = MagicMock()

        async def run_listen():
            with patch.object(connection, "start_heartbeat"):
                await connection.listen(handler)

        asyncio.run(run_listen())
        handler.handle_task_assign.assert_not_called()

    def test_listen_handles_mixed_text_and_bytes(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        connection._compression_negotiated = True
        connection._compressor = MessageCompressor(compress_threshold=32)
        text_frame = {"type": "agent.status", "trace_id": "t1", "seq": 1, "timestamp": "2026-07-20T12:00:00Z", "payload": {"status": "ok"}}
        big_frame = {"type": "task.assign", "trace_id": "t2", "seq": 2, "timestamp": "2026-07-20T12:00:01Z", "payload": {"task_id": 99, "data": "x" * 200}}
        compressed_big = connection._compressor.compress(big_frame)
        messages = [json.dumps(text_frame), compressed_big]

        async def async_iter():
            for m in messages:
                yield m

        mock_ws.__aiter__ = MagicMock(return_value=async_iter())
        handler = MagicMock()
        received_payloads = []

        async def run_listen():
            with patch.object(connection, "start_heartbeat"):
                original_dispatch = connection._dispatch_to_handler

                def dispatch_and_collect(msg, h):
                    received_payloads.append(msg.get("payload", {}))
                    original_dispatch(msg, h)
                    if len(received_payloads) >= 2:
                        connection._connected = False

                with patch.object(connection, "_dispatch_to_handler", side_effect=dispatch_and_collect):
                    await connection.listen(handler)

        asyncio.run(run_listen())
        assert {"status": "ok"} in received_payloads
        assert {"task_id": 99, "data": "x" * 200} in received_payloads


# ===========================================================================
# Agent-side E2E compression tests (原 test_compression_e2e.py)
# ===========================================================================


class TestAgentCompressionE2E:
    """Full-flow E2E from the agent's perspective."""

    def test_full_negotiate_then_send_large_frame(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        ack = build_hello_ack_frame(algorithm=COMPRESSION_ALGORITHM_MSGPACK_ZLIB, threshold=32, enabled=True)
        connection._handle_hello_ack(ack)
        assert connection._compression_negotiated is True
        large_payload = {"execution_id": "exec-001", "success": True, "data": "x" * 500}
        asyncio.run(connection.send_message("task.result", large_payload))
        assert mock_ws.send.await_count == 1
        sent = mock_ws.send.call_args.args[0]
        assert isinstance(sent, (bytes, bytearray))
        decoded = connection._compressor.decompress(sent)
        assert decoded["type"] == "task.result"
        assert decoded["payload"]["data"] == "x" * 500
        assert decoded["payload"]["execution_id"] == "exec-001"

    def test_compression_ratio_for_large_payload(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        _negotiate(connection, threshold=1)
        big_data = {
            "execution_id": "exec-e2e-001",
            "success": True,
            "elapsed_time": 1.5,
            "steps": [{"step_id": i, "name": f"step-{i}", "result": "ok" * 20} for i in range(50)],
            "screenshot_metadata": {"width": 1920, "height": 1080, "format": "png", "hash": "abc123" * 50},
        }
        json_frame = {"trace_id": "ratio-test", "type": "task.result", "seq": 1, "timestamp": "2026-07-20T12:00:00Z", "payload": big_data}
        json_size = len(json.dumps(json_frame).encode("utf-8"))
        assert json_size > 5000, "test payload must be > 5KB"
        asyncio.run(connection.send_message("task.result", big_data))
        sent = mock_ws.send.call_args.args[0]
        assert isinstance(sent, (bytes, bytearray))
        wire_size = len(sent)
        ratio = wire_size / json_size
        assert ratio < 0.5, f"compression ratio {ratio:.2%} does not meet <50% target (json={json_size}B, wire={wire_size}B)"

    def test_legacy_server_keeps_json_text(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        assert connection._compression_negotiated is False
        assert connection._compressor is None
        asyncio.run(connection.send_message("task.result", {"task_id": 1, "data": "x" * 500}))
        sent = mock_ws.send.call_args.args[0]
        assert isinstance(sent, str)
        frame = json.loads(sent)
        assert frame["type"] == "task.result"

    def test_round_trip_integrity(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        _negotiate(connection, threshold=1)
        nested_payload = {"execution_id": "exec-rt-001", "success": True, "nested": {"level1": {"level2": [1, 2, 3, {"deep": "value"}], "flag": True}}, "items": [{"id": i, "name": f"item-{i}"} for i in range(20)]}
        asyncio.run(connection.send_message("task.result", nested_payload))
        sent = mock_ws.send.call_args.args[0]
        decoded = connection._compressor.decompress(sent)
        assert decoded["payload"] == nested_payload
        assert decoded["type"] == "task.result"

    def test_mixed_size_frames_post_negotiation(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        _negotiate(connection, threshold=256)
        asyncio.run(connection.send_message("agent.heartbeat", {"stats": {"cpu": 10.0}}))
        small_sent = mock_ws.send.call_args.args[0]
        assert isinstance(small_sent, str), "small frame should stay JSON text"
        asyncio.run(connection.send_message("task.result", {"execution_id": "x", "data": "y" * 500}))
        large_sent = mock_ws.send.call_args.args[0]
        assert isinstance(large_sent, (bytes, bytearray)), "large frame should be compressed bytes"

    def test_compression_failure_falls_back_gracefully(self, connection):
        mock_ws = _make_mock_ws()
        connection._ws = mock_ws
        connection._connected = True
        _negotiate(connection, threshold=1)
        bad_compressor = MagicMock()
        bad_compressor.compress.side_effect = MessageCompressorError("injected failure")
        bad_compressor.compress_threshold = 1
        connection._compressor = bad_compressor
        asyncio.run(connection.send_message("task.result", {"task_id": 1}))
        sent = mock_ws.send.call_args.args[0]
        assert isinstance(sent, str)
        frame = json.loads(sent)
        assert frame["type"] == "task.result"
