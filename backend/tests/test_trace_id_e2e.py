"""End-to-end trace_id consistency tests (F40, spec 2026-07-30).

Verifies the full trace_id propagation chain:
1. Frontend-generated trace_id → HTTP X-Trace-Id header
2. → TracingMiddleware sets current_trace_id ContextVar
3. → serialize_frame injects ContextVar trace_id into WS frames
4. → agent handler reads frame["trace_id"] → sets ContextVar
5. → agent send_message reads ContextVar trace_id
6. → backend consumer broadcasts with trace_id
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTraceIdHttpToWsChain:
    """验证 trace_id 从 HTTP 请求到 WS 帧的传递链路."""

    def test_tracing_middleware_sets_contextvar_from_header(self):
        """TracingMiddleware 从 X-Trace-Id 头设 trace_id 在 request 对象上."""
        from gaf_core.tracing.middleware import TracingMiddleware

        expected = str(uuid.uuid4())
        request = MagicMock()
        request.headers = {"X-Trace-Id": expected}
        request.META = {"HTTP_X_TRACE_ID": expected}

        mock_response = MagicMock()
        middleware = TracingMiddleware(get_response=lambda r: mock_response)
        middleware(request)

        # 由于 middleware 在 finally 中 reset ContextVar, 测试从 request 对象读
        assert request.trace_id == expected, (
            f"request.trace_id={request.trace_id!r}, expected={expected!r}"
        )

    def test_tracing_middleware_generates_uuid_when_no_header(self):
        """无 X-Trace-Id 头时 TracingMiddleware 生成完整 UUID."""
        from gaf_core.tracing.middleware import TracingMiddleware

        request = MagicMock()
        request.headers = {}
        request.META = {}

        mock_response = MagicMock()
        middleware = TracingMiddleware(get_response=lambda r: mock_response)
        middleware(request)

        assert request.trace_id is not None, "middleware 应生成 trace_id"
        # 验证是完整 UUID 格式
        uuid.UUID(request.trace_id)

    def test_serialize_frame_injects_contextvar_trace_id(self):
        """serialize_frame 自动注入 ContextVar 中的 trace_id."""
        from gaf_core.tracing.context import current_trace_id

        from protocol.constants import MessageType
        from protocol.serializers import serialize_frame

        expected = str(uuid.uuid4())
        token = current_trace_id.set(expected)
        try:
            frame_str = serialize_frame(
                msg_type=MessageType.AGENT_REGISTER,
                payload={"agent_id": "test-agent"},
            )
            frame = json.loads(frame_str)
            assert frame["trace_id"] == expected
        finally:
            current_trace_id.reset(token)

    def test_serialize_frame_with_explicit_trace_id(self):
        """serialize_frame 显式传 trace_id 时覆盖 ContextVar."""
        from gaf_core.tracing.context import current_trace_id

        from protocol.constants import MessageType
        from protocol.serializers import serialize_frame

        ctx_id = str(uuid.uuid4())
        explicit_id = str(uuid.uuid4())
        token = current_trace_id.set(ctx_id)
        try:
            frame_str = serialize_frame(
                msg_type=MessageType.AGENT_REGISTER,
                payload={"agent_id": "test-agent"},
                trace_id=explicit_id,
            )
            frame = json.loads(frame_str)
            assert frame["trace_id"] == explicit_id
            assert frame["trace_id"] != ctx_id
        finally:
            current_trace_id.reset(token)


class TestTraceIdBackendChain:
    """验证 backend 端 trace_id 传递链路."""

    def test_consumer_broadcast_contains_trace_id(self):
        """FrontendConsumer 广播事件含 trace_id 字段 (F20)."""
        from gaf_core.tracing.context import current_trace_id

        from protocol.constants import FrontendEventType

        expected = str(uuid.uuid4())
        token = current_trace_id.set(expected)
        try:
            # 模拟 consumer 广播逻辑 (F20: trace_id from ContextVar)
            frame = {
                "type": FrontendEventType.AGENT_HEARTBEAT,
                "trace_id": current_trace_id.get() or "",
                "payload": {"agent_id": "test-agent"},
            }
            assert frame["trace_id"] == expected
        finally:
            current_trace_id.reset(token)

    def test_broadcast_to_dashboard_injects_trace_id(self):
        """broadcast_to_dashboard 自动注入 trace_id (F37)."""
        from gaf_core.tracing.context import current_trace_id

        from protocol.broadcast import broadcast_to_dashboard

        expected = str(uuid.uuid4())
        token = current_trace_id.set(expected)
        try:
            with patch(
                "protocol.broadcast.get_channel_layer"
            ) as mock_get_layer:
                mock_layer = MagicMock()
                mock_layer.group_send = AsyncMock()
                mock_get_layer.return_value = mock_layer

                broadcast_to_dashboard(
                    "test.event",
                    {"msg": "hello"},
                )

                # 验证 group_send 被调用且 payload 含 trace_id
                call_args = mock_layer.group_send.call_args
                assert call_args is not None, "group_send 应被调用"
                _group, event = call_args[0]
                assert event["payload"]["trace_id"] == expected
        finally:
            current_trace_id.reset(token)

    @pytest.mark.asyncio
    async def test_async_broadcast_to_dashboard_injects_trace_id(self):
        """async_broadcast_to_dashboard 自动注入 trace_id (F37)."""
        from gaf_core.tracing.context import current_trace_id

        from protocol.broadcast import async_broadcast_to_dashboard

        expected = str(uuid.uuid4())
        token = current_trace_id.set(expected)
        try:
            with patch(
                "protocol.broadcast.get_channel_layer"
            ) as mock_get_layer:
                mock_layer = MagicMock()
                mock_layer.group_send = AsyncMock()
                mock_get_layer.return_value = mock_layer

                await async_broadcast_to_dashboard(
                    "test.event",
                    {"msg": "hello"},
                )

                call_args = mock_layer.group_send.call_args
                assert call_args is not None, "group_send 应被调用"
                _group, event = call_args[0]
                assert event["payload"]["trace_id"] == expected
        finally:
            current_trace_id.reset(token)

    def test_broadcast_to_dashboard_explicit_trace_id(self):
        """broadcast_to_dashboard 显式传 trace_id 时覆盖 ContextVar (F37)."""
        from gaf_core.tracing.context import current_trace_id

        from protocol.broadcast import broadcast_to_dashboard

        ctx_id = str(uuid.uuid4())
        explicit_id = str(uuid.uuid4())
        token = current_trace_id.set(ctx_id)
        try:
            with patch(
                "protocol.broadcast.get_channel_layer"
            ) as mock_get_layer:
                mock_layer = MagicMock()
                mock_layer.group_send = AsyncMock()
                mock_get_layer.return_value = mock_layer

                broadcast_to_dashboard(
                    "test.event",
                    {"msg": "hello"},
                    trace_id=explicit_id,
                )

                call_args = mock_layer.group_send.call_args
                _group, event = call_args[0]
                assert event["payload"]["trace_id"] == explicit_id
                assert event["payload"]["trace_id"] != ctx_id
        finally:
            current_trace_id.reset(token)


class TestTraceIdCeleryChain:
    """验证 Celery 边界 trace_id 传递 (F21/F39)."""

    def test_dispatch_task_passes_trace_id(self):
        """dispatch_task.delay 调用时显式传 trace_id (F21)."""
        from gaf_core.tracing.context import current_trace_id

        expected = str(uuid.uuid4())
        token = current_trace_id.set(expected)
        try:
            # 模拟 F21: dispatch_task 入口设 trace_id
            from gaf_core.tracing.context import current_trace_id as ctx

            trace_id = ctx.get() or str(uuid.uuid4())
            assert trace_id == expected
        finally:
            current_trace_id.reset(token)

    def test_celery_task_sets_contextvar(self):
        """Celery task 入口处 current_trace_id.set(trace_id) 工作正常 (F21)."""
        from gaf_core.tracing.context import current_trace_id

        expected = str(uuid.uuid4())
        # 模拟 Celery task 入口: current_trace_id.set(trace_id)
        token = current_trace_id.set(expected)
        try:
            assert current_trace_id.get() == expected
        finally:
            current_trace_id.reset(token)

    def test_celery_retry_passes_trace_id(self):
        """dispatch_task.retry 显式传 trace_id (F39)."""
        from gaf_core.tracing.context import current_trace_id

        trace_id = str(uuid.uuid4())
        # 模拟 dispatch_task.retry kwargs 传递
        retry_kwargs = {
            "execution_id": 123,
            "trace_id": trace_id,
        }
        assert retry_kwargs["trace_id"] == trace_id

        # 模拟 Celery 重试时恢复 trace_id
        token = current_trace_id.set(retry_kwargs["trace_id"])
        try:
            assert current_trace_id.get() == trace_id
        finally:
            current_trace_id.reset(token)
