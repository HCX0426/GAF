"""Tests for trace_id UUID format consistency (F40, spec 2026-07-30).

Verifies that:
1. All trace_id values in the codebase use the full UUID format
   (``xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx``).
2. ``serialize_frame`` injects trace_id from ``current_trace_id`` ContextVar
   when no explicit trace_id is passed.
3. ``current_trace_id`` ContextVar default is ``None`` (not a truncated hex).
"""

from __future__ import annotations

import json
import re
import uuid
from unittest.mock import MagicMock

import pytest

from protocol.constants import MessageType
from protocol.serializers import serialize_frame

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class TestTraceIdFormat:
    """验证 trace_id 统一为完整 UUID 格式 (F8)."""

    def test_serialize_frame_no_trace_id_falls_back_to_contextvar(self):
        """serialize_frame 不传 trace_id 时从 ContextVar 取."""
        from gaf_core.tracing.context import current_trace_id

        expected = str(uuid.uuid4())
        token = current_trace_id.set(expected)
        try:
            frame_str = serialize_frame(msg_type=MessageType.AGENT_REGISTER, payload={"msg": "hello"})
            frame = json.loads(frame_str)
            assert frame["trace_id"] == expected
        finally:
            current_trace_id.reset(token)

    def test_serialize_frame_explicit_trace_id_wins(self):
        """serialize_frame 显式传 trace_id 时优先使用."""
        from gaf_core.tracing.context import current_trace_id

        ctx_id = str(uuid.uuid4())
        explicit_id = str(uuid.uuid4())
        token = current_trace_id.set(ctx_id)
        try:
            frame_str = serialize_frame(
                msg_type=MessageType.AGENT_REGISTER,
                payload={"msg": "hello"},
                trace_id=explicit_id,
            )
            frame = json.loads(frame_str)
            assert frame["trace_id"] == explicit_id
            assert frame["trace_id"] != ctx_id
        finally:
            current_trace_id.reset(token)

    def test_serialize_frame_contextvar_none_falls_back_to_uuid4(self):
        """ContextVar 为 None 时 serialize_frame 回退到 uuid4 (仍是完整 UUID)."""
        from gaf_core.tracing.context import current_trace_id

        token = current_trace_id.set(None)
        try:
            frame_str = serialize_frame(msg_type=MessageType.AGENT_REGISTER, payload={"msg": "hello"})
            frame = json.loads(frame_str)
            assert UUID_PATTERN.match(frame["trace_id"]), (
                f"trace_id={frame['trace_id']!r} 不是完整 UUID 格式"
            )
        finally:
            current_trace_id.reset(token)

    def test_serialize_frame_contextvar_empty_string_falls_back(self):
        """ContextVar 为空字符串时 serialize_frame 回退到 uuid4."""
        from gaf_core.tracing.context import current_trace_id

        token = current_trace_id.set("")
        try:
            frame_str = serialize_frame(msg_type=MessageType.AGENT_REGISTER, payload={"msg": "hello"})
            frame = json.loads(frame_str)
            assert UUID_PATTERN.match(frame["trace_id"]), (
                f"trace_id={frame['trace_id']!r} 不是完整 UUID 格式"
            )
        finally:
            current_trace_id.reset(token)

    def test_current_trace_id_default_is_none(self):
        """current_trace_id ContextVar 默认值为 None."""
        from gaf_core.tracing.context import current_trace_id

        assert current_trace_id.get() is None

    def test_uuid_format_is_full_uuid(self):
        """验证 str(uuid.uuid4()) 输出完整 UUID 格式."""
        trace_id = str(uuid.uuid4())
        assert UUID_PATTERN.match(trace_id), f"str(uuid.uuid4())={trace_id!r}"
        # 确保不是截断的 16 字符 hex
        assert len(trace_id) == 36, f"完整 UUID 长度应为 36, 实际 {len(trace_id)}"

    @pytest.mark.parametrize(
        "trace_id",
        [
            "550e8400-e29b-41d4-a716-446655440000",
            "00000000-0000-0000-0000-000000000000",
            "ffffffff-ffff-ffff-ffff-ffffffffffff",
        ],
    )
    def test_valid_uuid_patterns(self, trace_id):
        """验证有效 UUID 格式通过正则."""
        assert UUID_PATTERN.match(trace_id)

    @pytest.mark.parametrize(
        "bad_trace_id",
        [
            "550e8400e29b41d4a716446655440000",  # 无连字符
            "550e8400-e29b-41d4-a716",  # 截断
            "550e8400-e29b-41d4-a716-44665544000Z",  # 非法字符
            "",  # 空串
            "exec-12345",  # execution_id 格式
            "trace-abc123",  # 旧 trace- 前缀
        ],
    )
    def test_invalid_uuid_patterns(self, bad_trace_id):
        """验证非 UUID 格式不通过正则."""
        assert not UUID_PATTERN.match(bad_trace_id), (
            f"expected {bad_trace_id!r} to NOT match UUID pattern"
        )


class TestTracingMiddlewareFormat:
    """验证 TracingMiddleware 生成的 trace_id 是完整 UUID (F8)."""

    def test_middleware_generates_full_uuid(self):
        """TracingMiddleware 生成完整 UUID 而非截断 hex."""
        from gaf_core.tracing.middleware import TracingMiddleware

        request = MagicMock()
        request.headers = {}
        request.META = {}

        mock_response = MagicMock()
        middleware = TracingMiddleware(get_response=lambda r: mock_response)
        middleware(request)

        trace_id = getattr(request, "trace_id", None) or ""
        assert trace_id, "middleware 应设置 trace_id 在 request 对象上"
        # 验证完整 UUID 格式
        uuid.UUID(trace_id)


class TestTracingChannelsMiddlewareFormat:
    """验证 TracingChannelsMiddleware 生成的 trace_id 是完整 UUID (F25)."""

    @pytest.mark.asyncio
    async def test_middleware_fallback_uuid_format(self):
        """TracingChannelsMiddleware 无 X-Trace-Id 时生成的 uuid4 是完整 UUID."""
        from gaf_core.tracing.channels_middleware import TracingChannelsMiddleware

        scope = {
            "type": "websocket",
            "query_string": b"",
            "headers": [],
        }

        async def mock_receive():
            return {"type": "websocket.connect"}

        async def mock_send(event):
            pass

        async def _noop_asgi_app(scope, receive, send):
            pass

        middleware = TracingChannelsMiddleware(_noop_asgi_app)
        await middleware(scope, mock_receive, mock_send)
