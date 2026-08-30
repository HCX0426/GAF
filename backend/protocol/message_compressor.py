"""WebSocket payload compressor: MessagePack + zlib for >1KB frames.

✅ Status (spec-42, TD-287): helper implemented + Hello/Hello.ack
negotiation protocol added. WorkerConsumer.send() hot path and agent
ws_client are wired via the negotiation flow — see ``build_hello_frame``
/ ``build_hello_ack_frame`` below. Legacy agents/backends that don't
participate in the negotiation fall back to JSON text_data.

Compression strategy
--------------------
1. **Serialize**: try ``msgpack`` (binary, ~30% smaller than JSON for
   nested dicts), fall back to ``json.dumps`` when msgpack is not
   installed.
2. **Compress**: when the serialized bytes exceed ``compress_threshold``
   (default 1024 bytes = 1 KB), apply ``zlib.compress``. Smaller frames
   are sent uncompressed to avoid the per-frame zlib overhead.
3. **Envelope**: wrap the (possibly compressed) bytes in a 5-byte header::

       [0]    format byte: 0x01 = JSON, 0x02 = MessagePack
       [1]    flag byte:  0x00 = raw, 0x01 = zlib-compressed
       [2..4] reserved (0x00, 0x00, 0x00) for future versioning

   This keeps the wire format self-describing so the agent can decode
   without out-of-band config.

API
---
::

    compressor = MessageCompressor(compress_threshold=1024)
    wire_bytes = compressor.compress({"type": "task.dispatch", "payload": {...}})
    payload = compressor.decompress(wire_bytes)  # → original dict

``compress()`` returns ``bytes`` (ready for ``self.send(bytes_data=...)``);
``decompress()`` returns the original ``dict``. Both raise
``MessageCompressorError`` on malformed input.

Compression negotiation (spec-42)
---------------------------------
Right after WS connect, the agent sends a ``hello`` frame advertising
supported algorithms + threshold; the server responds with ``hello.ack``
confirming the chosen algorithm (or ``enabled=False`` to decline).
After successful negotiation both sides switch large frames (>= threshold
bytes) to ``MessageCompressor.compress()`` wire format. Frames smaller
than threshold continue to use JSON text_data (avoiding zlib overhead
for small control messages like ``agent.heartbeat``).
"""

from __future__ import annotations

import json
import logging
import uuid
import zlib
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Try to import msgpack once; cache the result so we don't retry per call.
try:
    import msgpack  # type: ignore[import-not-found]
    _MSGPACK_AVAILABLE = True
except ImportError:
    msgpack = None  # type: ignore[assignment]
    _MSGPACK_AVAILABLE = False
    logger.info(
        "MessageCompressor: msgpack not installed, falling back to JSON "
        "(larger wire size for nested payloads)",
    )


# Wire format bytes — see module docstring.
_FORMAT_JSON = 0x01
_FORMAT_MSGPACK = 0x02
_FLAG_RAW = 0x00
_FLAG_ZLIB = 0x01
_HEADER_SIZE = 5
_RESERVED_BYTES = b"\x00\x00\x00"

# ---- Compression negotiation protocol constants (spec-42, TD-287) ----
# Algorithm identifier exchanged in Hello/Hello.ack frames. Single source
# of truth — both backend and agent must agree on this string. Adding a
# new algorithm (e.g. "zstd") means bumping the protocol version and
# updating both sides in lockstep.
COMPRESSION_ALGORITHM_MSGPACK_ZLIB = "msgpack+zlib"

# Default compression threshold (bytes). Frames with serialized size >=
# this value are compressed; smaller frames skip zlib to avoid per-frame
# overhead. 1024 bytes (1 KB) is the empirical sweet spot — control
# frames (agent.heartbeat, event.ack) stay JSON, large frames
# (screenshot.frame with base64 PNG, task.dispatch with pipeline DAG)
# get compressed.
DEFAULT_COMPRESS_THRESHOLD = 1024


class HelloFrameError(Exception):
    """Raised when Hello/Hello.ack frame construction or parsing fails."""


class MessageCompressorError(Exception):
    """Raised when compression or decompression fails."""


class MessageCompressor:
    """Compress WS payloads with MessagePack + zlib, JSON fallback.

    Args:
        compress_threshold: Minimum payload size (bytes, after serialization)
            above which zlib compression is applied. Default 1024 (1 KB).
            Set to a very large value (e.g. ``float('inf')``) to disable
            compression entirely.
        zlib_level: zlib compression level [0, 9]. Default 6 (zlib default).
            0 = no compression, 9 = best compression (slowest).
        use_msgpack: Whether to use msgpack when available. Default True.
            Set to False to force JSON serialization (e.g. for debugging).
    """

    def __init__(
        self,
        compress_threshold: int = 1024,
        zlib_level: int = 6,
        use_msgpack: bool = True,
    ):
        if compress_threshold < 0:
            raise ValueError(
                f"compress_threshold must be >= 0, got {compress_threshold}",
            )
        if not 0 <= zlib_level <= 9:
            raise ValueError(f"zlib_level must be in [0, 9], got {zlib_level}")
        self._compress_threshold = int(compress_threshold)
        self._zlib_level = int(zlib_level)
        self._use_msgpack = bool(use_msgpack) and _MSGPACK_AVAILABLE

    # ── Public properties ──────────────────────────────────────
    @property
    def compress_threshold(self) -> int:
        """Configured compression threshold (bytes)."""
        return self._compress_threshold

    @property
    def uses_msgpack(self) -> bool:
        """True if msgpack is active (False = JSON fallback)."""
        return self._use_msgpack

    # ── Public API ──────────────────────────────────────────────
    def compress(self, payload: Any) -> bytes:
        """Serialize + conditionally compress a payload to wire bytes.

        Args:
            payload: Any JSON-serializable / msgpack-serializable object
                (typically a dict).

        Returns:
            Wire-format bytes (5-byte header + body). Ready for
            ``self.send(bytes_data=...)``.

        Raises:
            MessageCompressorError: on serialization failure.
        """
        if payload is None:
            payload = {}

        # Step 1: serialize to bytes.
        try:
            if self._use_msgpack:
                body = msgpack.packb(payload, use_bin_type=True)
                format_byte = _FORMAT_MSGPACK
            else:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                format_byte = _FORMAT_JSON
        except (TypeError, ValueError) as exc:
            raise MessageCompressorError(f"serialization failed: {exc}") from exc

        # Step 2: conditionally compress.
        if len(body) >= self._compress_threshold:
            try:
                body = zlib.compress(body, self._zlib_level)
                flag_byte = _FLAG_ZLIB
            except zlib.error as exc:
                raise MessageCompressorError(f"zlib compress failed: {exc}") from exc
        else:
            flag_byte = _FLAG_RAW

        # Step 3: envelope (5-byte header + body).
        return bytes([format_byte, flag_byte]) + _RESERVED_BYTES + body

    def decompress(self, data: bytes) -> Any:
        """Reverse of ``compress()``: return the original payload.

        Args:
            data: Wire-format bytes from ``compress()``.

        Returns:
            Original payload (dict / list / scalar).

        Raises:
            MessageCompressorError: on malformed header or decompression
                failure.
        """
        if not isinstance(data, (bytes, bytearray)):
            raise MessageCompressorError(
                f"expected bytes, got {type(data).__name__}",
            )
        if len(data) < _HEADER_SIZE:
            raise MessageCompressorError(
                f"data too short: need >= {_HEADER_SIZE} bytes, got {len(data)}",
            )

        format_byte = data[0]
        flag_byte = data[1]
        body = bytes(data[_HEADER_SIZE:])

        # Step 1: decompress if needed.
        if flag_byte == _FLAG_ZLIB:
            try:
                body = zlib.decompress(body)
            except zlib.error as exc:
                raise MessageCompressorError(f"zlib decompress failed: {exc}") from exc
        elif flag_byte != _FLAG_RAW:
            raise MessageCompressorError(
                f"unknown flag byte: 0x{flag_byte:02x}",
            )

        # Step 2: deserialize.
        if format_byte == _FORMAT_MSGPACK:
            if not _MSGPACK_AVAILABLE:
                raise MessageCompressorError(
                    "payload is msgpack-encoded but msgpack is not installed",
                )
            try:
                return msgpack.unpackb(body, raw=False)
            except (msgpack.exceptions.UnpackException, ValueError) as exc:  # type: ignore[union-attr]
                raise MessageCompressorError(f"msgpack unpack failed: {exc}") from exc
        elif format_byte == _FORMAT_JSON:
            try:
                return json.loads(body.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise MessageCompressorError(f"json decode failed: {exc}") from exc
        else:
            raise MessageCompressorError(
                f"unknown format byte: 0x{format_byte:02x}",
            )


# ────────────────────────────────────────────────────────────────────
# Hello / Hello.ack negotiation frame helpers (spec-42, TD-287)
# ────────────────────────────────────────────────────────────────────
# These helpers build/parse the negotiation frames exchanged right after
# WS connect. The frames themselves are plain JSON text_data (NOT yet
# compressed — compression kicks in only after both sides agree). Each
# helper returns/accepts the standard frame dict
# (trace_id/type/seq/timestamp/payload) so callers can pass it directly
# to ``serialize_frame()`` / ``json.dumps()``.
#
# Frame payload schema:
#   Hello (agent → server):
#       {"compression": {"algorithms": ["msgpack+zlib"], "threshold": 1024}}
#   Hello.ack (server → agent):
#       {"compression": {"algorithm": "msgpack+zlib", "threshold": 1024, "enabled": true}}


def _now_iso() -> str:
    """Current UTC timestamp in ISO 8601 with 'Z' suffix (matches serialize_frame)."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def build_hello_frame(
    algorithms: list[str],
    threshold: int = DEFAULT_COMPRESS_THRESHOLD,
    trace_id: str | None = None,
    seq: int = 1,
) -> dict[str, Any]:
    """Build a ``hello`` frame dict advertising agent compression capabilities.

    Args:
        algorithms: List of algorithm identifiers the agent supports
            (e.g. ``["msgpack+zlib"]``). Must be non-empty.
        threshold: Compression threshold in bytes. Frames with serialized
            size >= threshold will be compressed after negotiation.
        trace_id: Optional trace UUID. Generated if omitted.
        seq: Frame sequence number (default 1 for the first frame after connect).

    Returns:
        Frame dict with ``type="hello"``. Caller is responsible for
        serializing it (typically via ``serialize_frame`` or ``json.dumps``)
        and sending as ``text_data`` on the WebSocket.

    Raises:
        HelloFrameError: If ``algorithms`` is empty or threshold is invalid.
    """
    if not algorithms:
        raise HelloFrameError("algorithms must be a non-empty list")
    if not isinstance(threshold, int) or threshold < 0:
        raise HelloFrameError(f"threshold must be a non-negative int, got {threshold!r}")
    return {
        "trace_id": str(trace_id or uuid.uuid4()),
        "type": "hello",
        "seq": seq,
        "timestamp": _now_iso(),
        "payload": {
            "compression": {
                "algorithms": list(algorithms),
                "threshold": int(threshold),
            },
        },
    }


def build_hello_ack_frame(
    algorithm: str,
    threshold: int = DEFAULT_COMPRESS_THRESHOLD,
    enabled: bool = True,
    trace_id: str | None = None,
    seq: int = 1,
) -> dict[str, Any]:
    """Build a ``hello.ack`` frame dict confirming server-side compression config.

    Args:
        algorithm: Algorithm identifier the server selected (must match one
            of the algorithms advertised in the agent's Hello frame).
        threshold: Negotiated compression threshold (bytes). Typically the
            server echoes the agent's threshold or applies a server-side cap.
        enabled: Whether compression is actually enabled. ``False`` means
            the server understood the Hello but declined (e.g. msgpack not
            installed on server side); agent must fall back to JSON text_data.
        trace_id: Optional trace UUID. Should match the Hello frame's
            trace_id when responding. Generated if omitted.
        seq: Frame sequence number.

    Returns:
        Frame dict with ``type="hello.ack"``.

    Raises:
        HelloFrameError: If ``algorithm`` is empty or threshold is invalid.
    """
    if not algorithm:
        raise HelloFrameError("algorithm must be a non-empty string")
    if not isinstance(threshold, int) or threshold < 0:
        raise HelloFrameError(f"threshold must be a non-negative int, got {threshold!r}")
    return {
        "trace_id": str(trace_id or uuid.uuid4()),
        "type": "hello.ack",
        "seq": seq,
        "timestamp": _now_iso(),
        "payload": {
            "compression": {
                "algorithm": algorithm,
                "threshold": int(threshold),
                "enabled": bool(enabled),
            },
        },
    }


def parse_hello_capabilities(frame: dict[str, Any]) -> tuple[list[str], int]:
    """Extract advertised capabilities from a parsed ``hello`` frame.

    Args:
        frame: Parsed frame dict (e.g. from ``deserialize_frame`` or
            ``json.loads``). Must have ``type == "hello"``.

    Returns:
        Tuple ``(algorithms, threshold)``:
            - algorithms: List of algorithm identifiers the agent supports.
            - threshold: Compression threshold in bytes.

    Raises:
        HelloFrameError: If frame is malformed or not a hello frame.
    """
    if not isinstance(frame, dict):
        raise HelloFrameError(f"expected dict, got {type(frame).__name__}")
    if frame.get("type") != "hello":
        raise HelloFrameError(f"not a hello frame: type={frame.get('type')!r}")
    payload = frame.get("payload")
    if not isinstance(payload, dict):
        raise HelloFrameError(f"payload must be dict, got {type(payload).__name__}")
    compression = payload.get("compression")
    if not isinstance(compression, dict):
        raise HelloFrameError(
            f"compression must be dict, got {type(compression).__name__}",
        )
    algorithms = compression.get("algorithms")
    if not isinstance(algorithms, list) or not algorithms:
        raise HelloFrameError(
            f"algorithms must be a non-empty list, got {algorithms!r}",
        )
    threshold = compression.get("threshold", DEFAULT_COMPRESS_THRESHOLD)
    if not isinstance(threshold, int) or threshold < 0:
        raise HelloFrameError(f"threshold must be non-negative int, got {threshold!r}")
    return [str(a) for a in algorithms], int(threshold)


def parse_hello_ack_capabilities(
    frame: dict[str, Any],
) -> tuple[str, int, bool]:
    """Extract negotiated config from a parsed ``hello.ack`` frame.

    Args:
        frame: Parsed frame dict. Must have ``type == "hello.ack"``.

    Returns:
        Tuple ``(algorithm, threshold, enabled)``:
            - algorithm: Algorithm identifier the server selected.
            - threshold: Negotiated compression threshold (bytes).
            - enabled: Whether compression is active. When False, the
              agent must continue using JSON text_data.

    Raises:
        HelloFrameError: If frame is malformed or not a hello.ack frame.
    """
    if not isinstance(frame, dict):
        raise HelloFrameError(f"expected dict, got {type(frame).__name__}")
    if frame.get("type") != "hello.ack":
        raise HelloFrameError(f"not a hello.ack frame: type={frame.get('type')!r}")
    payload = frame.get("payload")
    if not isinstance(payload, dict):
        raise HelloFrameError(f"payload must be dict, got {type(payload).__name__}")
    compression = payload.get("compression")
    if not isinstance(compression, dict):
        raise HelloFrameError(
            f"compression must be dict, got {type(compression).__name__}",
        )
    algorithm = compression.get("algorithm")
    if not isinstance(algorithm, str) or not algorithm:
        raise HelloFrameError(f"algorithm must be non-empty str, got {algorithm!r}")
    threshold = compression.get("threshold", DEFAULT_COMPRESS_THRESHOLD)
    if not isinstance(threshold, int) or threshold < 0:
        raise HelloFrameError(f"threshold must be non-negative int, got {threshold!r}")
    enabled = bool(compression.get("enabled", True))
    return str(algorithm), int(threshold), enabled
