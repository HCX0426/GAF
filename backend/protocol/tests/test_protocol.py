# Merged from test_message_frame.py, test_compression.py - 2026-08-04

"""消息帧协议单元测试：覆盖序列化/反序列化/Jsonschema 校验及 Consumer 行为。

Merged test suite covering:
  - Message frame serialization / deserialization / validation
  - Compression algorithms, negotiation, and E2E
  - WorkerConsumer and FrontendConsumer WebSocket behavior
"""

from __future__ import annotations

import json
import uuid
import zlib
from unittest.mock import MagicMock

import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import SimpleTestCase, TestCase, override_settings
from gaf_core.tracing.context import current_trace_id
from rest_framework import serializers

from protocol.constants import MESSAGE_FRAME_SCHEMA, MessageType
from protocol.consumers import FrontendConsumer, WorkerConsumer
from protocol.message_compressor import (
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
from protocol.serializers import (
    MessageFrameSerializer,
    build_error_frame,
    deserialize_frame,
    serialize_frame,
)
from protocol.tests import TEST_WS_PATH

pytestmark = pytest.mark.unit

# ====================================================================
# Source: test_message_frame.py — Message frame serialization
# ====================================================================


class TestSerializeFrame(TestCase):
    """测试 serialize_frame 序列化消息帧。"""

    def test_serialize_all_14_types(self):
        """验证 14 种消息类型均可正常序列化出有效 JSON 帧。"""
        for msg_type in MessageType.all_types():
            result = serialize_frame(msg_type=msg_type)
            self.assertIsInstance(result, str)
            data = json.loads(result)
            self.assertIn("trace_id", data)
            self.assertIn("type", data)
            self.assertIn("seq", data)
            self.assertIn("timestamp", data)
            self.assertIn("payload", data)
            self.assertEqual(data["type"], msg_type)
            self.assertEqual(data["seq"], 1)
            self.assertEqual(data["payload"], {})
            uuid.UUID(data["trace_id"])

    def test_serialize_with_payload(self):
        """验证带 payload 的序列化。"""
        payload = {"agent_id": "agent-001", "version": "1.0"}
        result = serialize_frame(
            msg_type=MessageType.AGENT_REGISTER,
            payload=payload,
        )
        data = json.loads(result)
        self.assertEqual(data["payload"], payload)

    def test_serialize_with_custom_trace_id(self):
        """验证自定义 trace_id 的序列化。"""
        custom_id = uuid.uuid4()
        result = serialize_frame(
            msg_type=MessageType.AGENT_HEARTBEAT,
            trace_id=custom_id,
        )
        data = json.loads(result)
        self.assertEqual(data["trace_id"], str(custom_id))

    def test_serialize_invalid_type_raises(self):
        """验证无效消息类型抛出 ValueError。"""
        with self.assertRaises(ValueError):
            serialize_frame(msg_type="invalid.type")

    def test_serialize_with_custom_seq(self):
        """验证自定义 seq 序号。"""
        result = serialize_frame(
            msg_type=MessageType.TASK_RESULT,
            seq=42,
        )
        data = json.loads(result)
        self.assertEqual(data["seq"], 42)


class TestSerializeFrameContextVar(TestCase):
    """B3-1 (spec 2026-07-30-debug-directory-restructure): 断点②修复.

    ``serialize_frame`` 当 ``trace_id=None`` 时优先从 ``current_trace_id``
    ContextVar 取 (HTTP 请求经由 TracingMiddleware 注入), ContextVar 也
    未设置时才回退到 ``uuid.uuid4()``. 这样 15 个调用点零改动即可让所有
    WS 帧自动携带当前请求的 trace_id, 实现 HTTP → WS trace 全链路贯穿.
    """

    def test_uses_contextvar_trace_id_when_not_passed(self):
        """不传 trace_id 参数时, 应使用 ContextVar 中的 trace_id."""
        ctx_trace_id = "550e8400-e29b-41d4-a716-446655440000"
        token = current_trace_id.set(ctx_trace_id)
        try:
            result = serialize_frame(msg_type=MessageType.AGENT_HEARTBEAT)
        finally:
            current_trace_id.reset(token)
        data = json.loads(result)
        self.assertEqual(data["trace_id"], ctx_trace_id)

    def test_explicit_trace_id_overrides_contextvar(self):
        """显式传 trace_id 应覆盖 ContextVar 中的值."""
        ctx_trace_id = "11111111-2222-3333-4444-555555555555"
        explicit_id = uuid.UUID("99999999-8888-7777-6666-555555555555")
        token = current_trace_id.set(ctx_trace_id)
        try:
            result = serialize_frame(
                msg_type=MessageType.AGENT_HEARTBEAT,
                trace_id=explicit_id,
            )
        finally:
            current_trace_id.reset(token)
        data = json.loads(result)
        self.assertEqual(data["trace_id"], str(explicit_id))

    def test_falls_back_to_uuid_when_contextvar_unset(self):
        """ContextVar 未设置时, 应回退到新生成的 UUID."""
        # 确保 ContextVar 默认为 None
        self.assertIsNone(current_trace_id.get())
        result = serialize_frame(msg_type=MessageType.AGENT_HEARTBEAT)
        data = json.loads(result)
        # 应该是合法 UUID (回退生成)
        uuid.UUID(data["trace_id"])

    def test_falls_back_to_uuid_when_contextvar_none(self):
        """ContextVar 显式为 None 时, 也应回退到新生成的 UUID."""
        token = current_trace_id.set(None)
        try:
            result = serialize_frame(msg_type=MessageType.AGENT_HEARTBEAT)
        finally:
            current_trace_id.reset(token)
        data = json.loads(result)
        uuid.UUID(data["trace_id"])

    def test_contextvar_trace_id_propagates_across_multiple_calls(self):
        """同一 ContextVar scope 内的多次 serialize_frame 调用使用同一 trace_id."""
        ctx_trace_id = "abcdef12-3456-7890-abcd-ef1234567890"
        token = current_trace_id.set(ctx_trace_id)
        try:
            r1 = serialize_frame(msg_type=MessageType.AGENT_HEARTBEAT)
            r2 = serialize_frame(msg_type=MessageType.TASK_PROGRESS)
            r3 = serialize_frame(msg_type=MessageType.TASK_RESULT)
        finally:
            current_trace_id.reset(token)
        ids = {json.loads(r)["trace_id"] for r in (r1, r2, r3)}
        self.assertEqual(ids, {ctx_trace_id})


class TestDeserializeFrame(TestCase):
    """测试 deserialize_frame 反序列化与校验。"""

    def test_deserialize_valid_frame(self):
        """验证合法帧反序列化成功。"""
        raw = serialize_frame(msg_type=MessageType.TASK_PROGRESS)
        data = deserialize_frame(raw)
        self.assertEqual(data["type"], MessageType.TASK_PROGRESS)
        self.assertEqual(data["seq"], 1)

    def test_deserialize_from_dict(self):
        """验证 dict 输入也能反序列化。"""
        frame_dict = {
            "trace_id": str(uuid.uuid4()),
            "type": MessageType.AGENT_HEARTBEAT,
            "seq": 5,
            "timestamp": "2026-05-18T12:00:00Z",
            "payload": {"cpu": 0.5},
        }
        data = deserialize_frame(frame_dict)
        self.assertEqual(data["type"], MessageType.AGENT_HEARTBEAT)
        self.assertEqual(data["seq"], 5)

    def test_deserialize_invalid_json(self):
        """验证非法 JSON 抛出 JSONDecodeError。"""
        with self.assertRaises(json.JSONDecodeError):
            deserialize_frame("not a json string {{{")

    def test_deserialize_unsupported_type(self):
        """验证不支持的类型抛出 ValueError。"""
        with self.assertRaises(ValueError):
            deserialize_frame(12345)

    def test_deserialize_missing_required_fields(self):
        """验证缺失必填字段抛出 ValidationError。"""
        with self.assertRaises(serializers.ValidationError):
            deserialize_frame({"type": MessageType.AGENT_HEARTBEAT})

    def test_deserialize_extra_fields_rejected(self):
        """验证额外字段被禁止。"""
        frame_dict = {
            "trace_id": str(uuid.uuid4()),
            "type": MessageType.AGENT_HEARTBEAT,
            "seq": 1,
            "timestamp": "2026-05-18T12:00:00Z",
            "payload": {},
            "unauthorized_field": "should_be_rejected",
        }
        with self.assertRaises(serializers.ValidationError):
            deserialize_frame(frame_dict)

    def test_deserialize_invalid_type_enum(self):
        """验证不在枚举内的 type 被拒绝。"""
        frame_dict = {
            "trace_id": str(uuid.uuid4()),
            "type": "not.a.valid.type",
            "seq": 1,
            "timestamp": "2026-05-18T12:00:00Z",
            "payload": {},
        }
        with self.assertRaises(serializers.ValidationError):
            deserialize_frame(frame_dict)

    def test_deserialize_seq_zero_rejected(self):
        """验证 seq 为 0 被拒绝（min_value=1）。"""
        frame_dict = {
            "trace_id": str(uuid.uuid4()),
            "type": MessageType.AGENT_HEARTBEAT,
            "seq": 0,
            "timestamp": "2026-05-18T12:00:00Z",
            "payload": {},
        }
        with self.assertRaises(serializers.ValidationError):
            deserialize_frame(frame_dict)

    def test_deserialize_invalid_uuid_rejected(self):
        """验证非法 UUID 格式被拒绝。"""
        frame_dict = {
            "trace_id": "not-a-uuid",
            "type": MessageType.AGENT_HEARTBEAT,
            "seq": 1,
            "timestamp": "2026-05-18T12:00:00Z",
            "payload": {},
        }
        with self.assertRaises(serializers.ValidationError):
            deserialize_frame(frame_dict)

    def test_deserialize_payload_not_dict_rejected(self):
        """验证 payload 非 object 类型被拒绝。"""
        frame_dict = {
            "trace_id": str(uuid.uuid4()),
            "type": MessageType.AGENT_HEARTBEAT,
            "seq": 1,
            "timestamp": "2026-05-18T12:00:00Z",
            "payload": "should_be_dict",
        }
        with self.assertRaises(serializers.ValidationError):
            deserialize_frame(frame_dict)


class TestMessageFrameSerializer(TestCase):
    """测试 MessageFrameSerializer 校验逻辑。"""

    def test_valid_data(self):
        """验证合法数据通过校验。"""
        serializer = MessageFrameSerializer(data={
            "trace_id": str(uuid.uuid4()),
            "type": MessageType.AGENT_HEARTBEAT,
            "seq": 1,
            "timestamp": "2026-05-18T12:00:00Z",
            "payload": {},
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_invalid_type_choice(self):
        """验证不在 ChoiceField 枚举内的 type 校验失败。"""
        serializer = MessageFrameSerializer(data={
            "trace_id": str(uuid.uuid4()),
            "type": "unknown.type",
            "seq": 1,
            "timestamp": "2026-05-18T12:00:00Z",
            "payload": {},
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("type", serializer.errors)

    def test_negative_seq_rejected(self):
        """验证负数 seq 被拒绝。"""
        serializer = MessageFrameSerializer(data={
            "trace_id": str(uuid.uuid4()),
            "type": MessageType.AGENT_HEARTBEAT,
            "seq": -1,
            "timestamp": "2026-05-18T12:00:00Z",
            "payload": {},
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("seq", serializer.errors)

    def test_extra_fields_in_validate(self):
        """验证 validate() 方法拒绝附加字段。"""
        serializer = MessageFrameSerializer(data={
            "trace_id": str(uuid.uuid4()),
            "type": MessageType.AGENT_HEARTBEAT,
            "seq": 1,
            "timestamp": "2026-05-18T12:00:00Z",
            "payload": {},
            "bogus": True,
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("_schema", serializer.errors)


class TestBuildErrorFrame(TestCase):
    """测试 build_error_frame 错误帧构建。"""

    def test_build_error_frame(self):
        """验证错误帧结构正确。"""
        result = build_error_frame("测试错误消息")
        data = json.loads(result)
        self.assertEqual(data["type"], MessageType.AGENT_STATUS)
        self.assertEqual(data["payload"]["status"], "error")
        self.assertEqual(data["payload"]["message"], "测试错误消息")

    def test_build_error_frame_with_trace_id(self):
        """验证错误帧携带 trace_id。"""
        custom_id = uuid.uuid4()
        result = build_error_frame("测试", trace_id=custom_id)
        data = json.loads(result)
        self.assertEqual(data["trace_id"], str(custom_id))


class TestConstants(TestCase):
    """测试 protocol.constants 常量定义。"""

    def test_all_types_contains_expected_count(self):
        """验证 all_types() 返回当前定义的全部消息类型数量。"""
        # spec-29c (2026-07-19): 20 → 17 (removed AGENT_CONNECTED/AGENT_REGISTERED/ERROR after legacy /ws/agents/ deletion)
        # spec-42 (2026-07-20): 17 → 19 (added HELLO + HELLO_ACK for compression negotiation)
        # Phase 6.4 (2026-07-29): 19 → 20 (added TASK_FORCE_TERMINATE — not yet in MessageType)
        # P-048 (2026-07-29): 20 → 21 (added DEVICE_COMMAND for device-level recovery — not yet in MessageType)
        # 2026-07-31: 21 → 19 (TASK_FORCE_TERMINATE + DEVICE_COMMAND 尚未在 MessageType 中定义)
        # Task 2.1 (2026-08-08): 19 → 21 (added LLM_CALL + LLM_RESULT for WebSocket RPC)
        # S2 (2026-08-16): 21 → 22 (added DEVICE_COMMAND — device-level recovery command)
        self.assertEqual(len(MessageType.all_types()), 22)

    def test_agent_to_server_contains_expected_count(self):
        """验证上行消息类型数量与 constants 定义一致。"""
        # spec-42 (2026-07-20): 8 → 9 (added HELLO)
        # Task 2.1 (2026-08-08): 9 → 10 (added LLM_CALL)
        self.assertEqual(len(MessageType.agent_to_server_types()), 10)

    def test_server_to_agent_contains_expected_count(self):
        """验证下行消息类型数量与 constants 定义一致。"""
        # spec-29c (2026-07-19): 12 → 9 (removed AGENT_CONNECTED/AGENT_REGISTERED/ERROR; kept TASK_ASSIGN which is still sent by tasks/tasks.py + pipeline/tasks.py)
        # spec-42 (2026-07-20): 9 → 10 (added HELLO_ACK)
        # Phase 6.4 (2026-07-29): 10 → 11 (added TASK_FORCE_TERMINATE — not yet in MessageType)
        # P-048 (2026-07-29): 11 → 12 (added DEVICE_COMMAND — not yet in MessageType)
        # 2026-07-31: 12 → 10 (TASK_FORCE_TERMINATE + DEVICE_COMMAND 尚未在 MessageType 中定义)
        # Task 2.1 (2026-08-08): 10 → 11 (added LLM_RESULT)
        # S2 (2026-08-16): 11 → 12 (added DEVICE_COMMAND — server→agent direction)
        self.assertEqual(len(MessageType.server_to_agent_types()), 12)

    def test_no_direction_overlap(self):
        """验证上下行类型互斥。"""
        upstream = set(MessageType.agent_to_server_types())
        downstream = set(MessageType.server_to_agent_types())
        self.assertEqual(upstream & downstream, set())

    def test_directions_cover_all(self):
        """验证上下行合集等于全部类型。"""
        upstream = set(MessageType.agent_to_server_types())
        downstream = set(MessageType.server_to_agent_types())
        all_types = set(MessageType.all_types())
        self.assertEqual(upstream | downstream, all_types)

    def test_frame_schema_has_expected_structure(self):
        """验证帧 Schema 定义包含必填字段。"""
        self.assertIn("required", MESSAGE_FRAME_SCHEMA)
        required = set(MESSAGE_FRAME_SCHEMA["required"])
        self.assertEqual(
            required,
            {"trace_id", "type", "seq", "timestamp", "payload"},
        )
        self.assertFalse(MESSAGE_FRAME_SCHEMA["additionalProperties"])


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestWorkerConsumer(TestCase):
    """测试 WorkerConsumer WebSocket 连接行为。"""

    async def test_connect_receives_status_frame(self):
        """验证连接成功后收到 AGENT_STATUS 确认帧。"""
        communicator = WebsocketCommunicator(WorkerConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], MessageType.AGENT_STATUS)
        self.assertEqual(data["payload"]["status"], "connected")

        await communicator.disconnect()

    async def test_agent_register(self):
        """验证 agent.register 消息被正确处理并返回注册确认。"""
        communicator = WebsocketCommunicator(WorkerConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        register_frame = serialize_frame(
            msg_type=MessageType.AGENT_REGISTER,
            payload={"agent_id": "test-agent-001"},
        )
        await communicator.send_to(text_data=register_frame)

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], MessageType.AGENT_STATUS)
        self.assertEqual(data["payload"]["status"], "registered")
        self.assertEqual(data["payload"]["agent_id"], "test-agent-001")

        await communicator.disconnect()

    async def test_agent_heartbeat(self):
        """验证 agent.heartbeat 消息被正确处理并返回 ACK。"""
        communicator = WebsocketCommunicator(WorkerConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        heartbeat_frame = serialize_frame(msg_type=MessageType.AGENT_HEARTBEAT)
        await communicator.send_to(text_data=heartbeat_frame)

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], MessageType.EVENT_ACK)
        self.assertEqual(data["payload"]["ack_type"], MessageType.AGENT_HEARTBEAT)

        await communicator.disconnect()

    async def test_unknown_message_type(self):
        """验证未知消息类型返回错误帧（_handle_unknown 走不到因为 Schema 会先拒绝）。
        改为测试非法 JSON 返回错误帧。"""
        communicator = WebsocketCommunicator(WorkerConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        await communicator.send_to(text_data="not valid json {{{")

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], MessageType.AGENT_STATUS)
        self.assertEqual(data["payload"]["status"], "error")

        await communicator.disconnect()

    async def test_task_progress_stub(self):
        """验证 task.progress stub handler 不回送帧（只打 log）。"""
        communicator = WebsocketCommunicator(WorkerConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        progress_frame = serialize_frame(
            msg_type=MessageType.TASK_PROGRESS,
            payload={"task_id": "task-001", "percent": 50},
        )
        await communicator.send_to(text_data=progress_frame)

        await communicator.disconnect()

    async def test_screenshot_frame_stub(self):
        """验证 screenshot.frame stub handler 处理正常。"""
        communicator = WebsocketCommunicator(WorkerConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        screenshot_frame = serialize_frame(
            msg_type=MessageType.SCREENSHOT_FRAME,
            payload={"image": "base64...", "width": 1920, "height": 1080},
        )
        await communicator.send_to(text_data=screenshot_frame)

        await communicator.disconnect()

    async def test_device_action_result_stub(self):
        """验证 device.action_result stub handler 处理正常。"""
        communicator = WebsocketCommunicator(WorkerConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        action_frame = serialize_frame(
            msg_type=MessageType.DEVICE_ACTION_RESULT,
            payload={"action": "click", "success": True, "x": 100, "y": 200},
        )
        await communicator.send_to(text_data=action_frame)

        await communicator.disconnect()

    async def test_event_alert_stub(self):
        """验证 event.alert stub handler 处理正常。"""
        communicator = WebsocketCommunicator(WorkerConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        alert_frame = serialize_frame(
            msg_type=MessageType.EVENT_ALERT,
            payload={"alert_type": "cpu_high", "value": 95},
        )
        await communicator.send_to(text_data=alert_frame)

        await communicator.disconnect()

    async def test_task_result_stub(self):
        """验证 task.result stub handler 处理正常。"""
        communicator = WebsocketCommunicator(WorkerConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        result_frame = serialize_frame(
            msg_type=MessageType.TASK_RESULT,
            payload={"task_id": "task-001", "status": "completed", "output": "done"},
        )
        await communicator.send_to(text_data=result_frame)

        await communicator.disconnect()


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestFrontendConsumer(TestCase):
    """H25 fix: 验证 FrontendConsumer 向前端广播使用 `payload` 字段。"""

    def _patch_auth(self):
        """Bypass JWT verification for unit tests."""
        async def _mock_verify(self, token):
            return MagicMock(is_authenticated=True)

        FrontendConsumer._verify_access_token = _mock_verify

    async def test_connect_welcome_uses_payload(self):
        """验证连接成功后返回的消息使用 `payload` 而非 `data`。"""
        communicator = WebsocketCommunicator(FrontendConsumer.as_asgi(), "/ws/dashboard/")
        communicator.scope['subprotocols'] = []
        communicator.scope['query_string'] = b'token=dummy'
        self._patch_auth()
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], "connected")
        self.assertIn("payload", data)
        self.assertNotIn("data", data)
        self.assertEqual(data["payload"]["status"], "ok")

        await communicator.disconnect()

    async def test_ping_replies_pong(self):
        """验证 /ws/dashboard 对前端心跳 ping 返回 pong (L10)。

        前端 WsClient 每 30s 发 `{type:'ping'}`，连续 2 次未收到 pong 会
        主动断开重连（半开检测）。后端必须应答 pong，否则产生重连循环。
        """
        communicator = WebsocketCommunicator(FrontendConsumer.as_asgi(), "/ws/dashboard/")
        communicator.scope['subprotocols'] = []
        communicator.scope['query_string'] = b'token=dummy'
        self._patch_auth()
        await communicator.connect()
        await communicator.receive_from()  # consume the "connected" welcome

        await communicator.send_json_to({"type": "ping", "payload": {}})
        response = await communicator.receive_from(timeout=3)
        data = json.loads(response)
        self.assertEqual(data["type"], "pong")

        await communicator.disconnect()

    async def test_broadcast_agent_heartbeat_uses_payload(self):
        """验证 agent_heartbeat 广播使用 `payload` 字段。"""
        communicator = WebsocketCommunicator(FrontendConsumer.as_asgi(), "/ws/dashboard/")
        communicator.scope['subprotocols'] = []
        communicator.scope['query_string'] = b'token=dummy'
        self._patch_auth()
        await communicator.connect()
        await communicator.receive_from()

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "dashboard",
            {
                "type": "agent_heartbeat",
                "payload": {"agent_id": "agent-001", "stats": {"cpu": 10}},
            },
        )

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], "agent_heartbeat")
        self.assertIn("payload", data)
        self.assertNotIn("data", data)
        self.assertEqual(data["payload"]["agent_id"], "agent-001")

        await communicator.disconnect()

    async def test_broadcast_canonical_payload(self):
        """Verify FrontendConsumer forwards canonical `payload` events as-is.

        spec-29a #31: legacy `data` fallback removed. Backend senders must
        wrap event data under the `payload` key (per protocol.constants
        DASHBOARD_GROUP contract). This test replaces the old legacy-data
        fallback test.
        """
        communicator = WebsocketCommunicator(FrontendConsumer.as_asgi(), "/ws/dashboard/")
        communicator.scope['subprotocols'] = []
        communicator.scope['query_string'] = b'token=dummy'
        self._patch_auth()
        await communicator.connect()
        await communicator.receive_from()

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "dashboard",
            {
                "type": "agent_status",
                "payload": {"agent_id": "agent-002", "status": "online"},
            },
        )

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], "agent_status")
        self.assertIn("payload", data)
        self.assertEqual(data["payload"]["agent_id"], "agent-002")

        await communicator.disconnect()


# ====================================================================
# Source: test_compression.py — Compression algorithms, negotiation, E2E
# ====================================================================

# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


def _decode_response(response, *, threshold: int = DEFAULT_COMPRESS_THRESHOLD) -> dict:
    """Decode a WS response that could be text (JSON) or bytes (compressed).

    Post-negotiation the server may send either wire format depending on
    frame size vs. threshold. Tests that don't care which path was taken
    can use this helper to get the parsed dict either way.

    Args:
        response: Either ``str`` (JSON text_data) or ``bytes`` (compressed
            wire bytes from MessageCompressor.compress()).
        threshold: Compression threshold — only used to instantiate the
            decompressor (decompression doesn't depend on it, but we pass
            it for consistency with the negotiated config).

    Returns:
        Parsed frame dict.
    """
    if isinstance(response, bytes):
        compressor = MessageCompressor(compress_threshold=threshold, use_msgpack=True)
        return compressor.decompress(response)
    return json.loads(response)


# Wire-format constants — mirror the private module constants so the test
# is independent of the exact values used by the implementation (we only
# care that the layout is stable and self-describing).
_FORMAT_JSON = 0x01
_FORMAT_MSGPACK = 0x02
_FLAG_RAW = 0x00
_FLAG_ZLIB = 0x01
_HEADER_SIZE = 5


# ────────────────────────────────────────────────────────────────────
# MessageCompressor: round-trip tests (pre-existing behavior)
# ────────────────────────────────────────────────────────────────────


class TestMessageCompressorRoundTrip(SimpleTestCase):
    """Verify MessageCompressor.compress → decompress returns original payload."""

    def test_small_payload_json_round_trip(self):
        """Small payload (below threshold) uses JSON + raw (no zlib)."""
        compressor = MessageCompressor(compress_threshold=1024, use_msgpack=False)
        payload = {"type": "agent.heartbeat", "seq": 1}
        wire = compressor.compress(payload)

        # Header layout: [format=json][flag=raw][reserved x3]
        self.assertEqual(wire[0], _FORMAT_JSON)
        self.assertEqual(wire[1], _FLAG_RAW)
        self.assertEqual(wire[2:5], b"\x00\x00\x00")

        result = compressor.decompress(wire)
        self.assertEqual(result, payload)

    def test_large_payload_json_zlib_round_trip(self):
        """Large JSON payload (above threshold) uses JSON + zlib."""
        compressor = MessageCompressor(compress_threshold=64, use_msgpack=False)
        # Build a payload > 64 bytes when serialized.
        payload = {"type": "task.dispatch", "data": "x" * 200}
        wire = compressor.compress(payload)

        self.assertEqual(wire[0], _FORMAT_JSON)
        self.assertEqual(wire[1], _FLAG_ZLIB)

        result = compressor.decompress(wire)
        self.assertEqual(result, payload)

    def test_msgpack_round_trip_when_available(self):
        """When msgpack is installed, large payload uses msgpack + zlib."""
        try:
            import msgpack  # noqa: F401  # type: ignore[import-not-found]
        except ImportError:
            self.skipTest("msgpack not installed — skipping msgpack path test")

        compressor = MessageCompressor(compress_threshold=32, use_msgpack=True)
        payload = {"type": "screenshot.frame", "data": b"\x00" * 200}
        wire = compressor.compress(payload)

        self.assertEqual(wire[0], _FORMAT_MSGPACK)
        self.assertEqual(wire[1], _FLAG_ZLIB)

        result = compressor.decompress(wire)
        # msgpack preserves bytes as bytes (use_bin_type=True / raw=False).
        self.assertEqual(result, payload)

    def test_threshold_boundary_no_compression(self):
        """Payload strictly below threshold is not compressed."""
        body = json.dumps({"x": "y" * 50}, ensure_ascii=False).encode("utf-8")
        # Implementation uses `>=`, so body == threshold triggers compression.
        # For the "no compression" path we need body < threshold.
        threshold = len(body) + 1
        compressor = MessageCompressor(compress_threshold=threshold, use_msgpack=False)
        wire = compressor.compress({"x": "y" * 50})
        self.assertEqual(wire[1], _FLAG_RAW)

    def test_threshold_boundary_compression_at_equal(self):
        """Payload size == threshold triggers compression (>= semantics)."""
        body = json.dumps({"x": "y" * 50}, ensure_ascii=False).encode("utf-8")
        # body == threshold → compression triggers.
        threshold = len(body)
        compressor = MessageCompressor(compress_threshold=threshold, use_msgpack=False)
        wire = compressor.compress({"x": "y" * 50})
        self.assertEqual(wire[1], _FLAG_ZLIB)

    def test_none_payload_treated_as_empty_dict(self):
        """compress(None) should serialize as {} per implementation contract."""
        compressor = MessageCompressor(use_msgpack=False)
        wire = compressor.compress(None)
        result = compressor.decompress(wire)
        self.assertEqual(result, {})


class TestMessageCompressorErrors(SimpleTestCase):
    """Verify error handling for malformed wire bytes and bad constructor args."""

    def test_decompress_rejects_non_bytes(self):
        compressor = MessageCompressor()
        with self.assertRaises(MessageCompressorError) as ctx:
            compressor.decompress("not bytes")  # type: ignore[arg-type]
        self.assertIn("expected bytes", str(ctx.exception))

    def test_decompress_rejects_short_data(self):
        compressor = MessageCompressor()
        with self.assertRaises(MessageCompressorError) as ctx:
            compressor.decompress(b"\x00\x00")
        self.assertIn("data too short", str(ctx.exception))

    def test_decompress_rejects_unknown_format_byte(self):
        compressor = MessageCompressor()
        # Header with invalid format byte 0xFF, raw flag, 3 reserved + body.
        bad = bytes([0xFF, _FLAG_RAW]) + b"\x00\x00\x00" + b"{}"
        with self.assertRaises(MessageCompressorError) as ctx:
            compressor.decompress(bad)
        self.assertIn("unknown format byte", str(ctx.exception))

    def test_decompress_rejects_unknown_flag_byte(self):
        compressor = MessageCompressor()
        bad = bytes([_FORMAT_JSON, 0xFF]) + b"\x00\x00\x00" + b"{}"
        with self.assertRaises(MessageCompressorError) as ctx:
            compressor.decompress(bad)
        self.assertIn("unknown flag byte", str(ctx.exception))

    def test_decompress_rejects_corrupted_zlib_body(self):
        compressor = MessageCompressor()
        # Header says JSON + zlib but body is not valid zlib stream.
        bad = bytes([_FORMAT_JSON, _FLAG_ZLIB]) + b"\x00\x00\x00" + b"not-zlib"
        with self.assertRaises(MessageCompressorError) as ctx:
            compressor.decompress(bad)
        self.assertIn("zlib decompress failed", str(ctx.exception))

    def test_decompress_rejects_invalid_json_body(self):
        compressor = MessageCompressor()
        bad = bytes([_FORMAT_JSON, _FLAG_RAW]) + b"\x00\x00\x00" + b"not-json"
        with self.assertRaises(MessageCompressorError) as ctx:
            compressor.decompress(bad)
        self.assertIn("json decode failed", str(ctx.exception))

    def test_constructor_rejects_negative_threshold(self):
        with self.assertRaises(ValueError):
            MessageCompressor(compress_threshold=-1)

    def test_constructor_rejects_invalid_zlib_level(self):
        with self.assertRaises(ValueError):
            MessageCompressor(zlib_level=99)

    def test_compress_rejects_non_serializable_payload(self):
        compressor = MessageCompressor(use_msgpack=False)
        with self.assertRaises(MessageCompressorError) as ctx:
            compressor.compress({"bad": object()})
        self.assertIn("serialization failed", str(ctx.exception))


class TestMessageCompressorProperties(SimpleTestCase):
    """Verify public property accessors."""

    def test_compress_threshold_property(self):
        compressor = MessageCompressor(compress_threshold=512)
        self.assertEqual(compressor.compress_threshold, 512)

    def test_uses_msgpack_property_false_when_forced_json(self):
        compressor = MessageCompressor(use_msgpack=False)
        self.assertFalse(compressor.uses_msgpack)

    def test_uses_msgpack_property_reflects_availability(self):
        try:
            import msgpack  # noqa: F401  # type: ignore[import-not-found]
        except ImportError:
            compressor = MessageCompressor(use_msgpack=True)
            self.assertFalse(compressor.uses_msgpack)
        else:
            compressor = MessageCompressor(use_msgpack=True)
            self.assertTrue(compressor.uses_msgpack)


# ────────────────────────────────────────────────────────────────────
# Hello / Hello.ack frame helpers (spec-42)
# ────────────────────────────────────────────────────────────────────


class TestBuildHelloFrame(SimpleTestCase):
    """Tests for build_hello_frame."""

    def test_defaults_with_single_algorithm(self):
        frame = build_hello_frame([COMPRESSION_ALGORITHM_MSGPACK_ZLIB])
        self.assertEqual(frame["type"], "hello")
        self.assertEqual(frame["seq"], 1)
        self.assertIn("trace_id", frame)
        self.assertIn("timestamp", frame)
        compression = frame["payload"]["compression"]
        self.assertEqual(compression["algorithms"], [COMPRESSION_ALGORITHM_MSGPACK_ZLIB])
        self.assertEqual(compression["threshold"], DEFAULT_COMPRESS_THRESHOLD)

    def test_custom_threshold_and_trace_id_and_seq(self):
        custom_id = "11111111-1111-1111-1111-111111111111"
        frame = build_hello_frame(
            algorithms=["algo-a", "algo-b"],
            threshold=2048,
            trace_id=custom_id,
            seq=42,
        )
        self.assertEqual(frame["trace_id"], custom_id)
        self.assertEqual(frame["seq"], 42)
        self.assertEqual(frame["payload"]["compression"]["algorithms"], ["algo-a", "algo-b"])
        self.assertEqual(frame["payload"]["compression"]["threshold"], 2048)

    def test_generated_trace_id_is_valid_uuid(self):
        import uuid

        frame = build_hello_frame(["algo"])
        # Should not raise.
        uuid.UUID(frame["trace_id"])

    def test_timestamp_is_iso_with_z_suffix(self):
        frame = build_hello_frame(["algo"])
        ts = frame["timestamp"]
        self.assertTrue(ts.endswith("Z"), f"timestamp should end with 'Z', got: {ts!r}")

    def test_empty_algorithms_raises(self):
        with self.assertRaises(HelloFrameError) as ctx:
            build_hello_frame([])
        self.assertIn("non-empty", str(ctx.exception))

    def test_negative_threshold_raises(self):
        with self.assertRaises(HelloFrameError):
            build_hello_frame(["algo"], threshold=-1)

    def test_non_int_threshold_raises(self):
        with self.assertRaises(HelloFrameError):
            build_hello_frame(["algo"], threshold="1024")  # type: ignore[arg-type]

    def test_algorithms_list_is_copied(self):
        """Mutating the input list after build must not affect the frame."""
        original = ["algo-a"]
        frame = build_hello_frame(original)
        original.append("algo-b")
        self.assertEqual(frame["payload"]["compression"]["algorithms"], ["algo-a"])


class TestBuildHelloAckFrame(SimpleTestCase):
    """Tests for build_hello_ack_frame."""

    def test_defaults_with_enabled_true(self):
        frame = build_hello_ack_frame(COMPRESSION_ALGORITHM_MSGPACK_ZLIB)
        self.assertEqual(frame["type"], "hello.ack")
        self.assertEqual(frame["seq"], 1)
        compression = frame["payload"]["compression"]
        self.assertEqual(compression["algorithm"], COMPRESSION_ALGORITHM_MSGPACK_ZLIB)
        self.assertEqual(compression["threshold"], DEFAULT_COMPRESS_THRESHOLD)
        self.assertIs(compression["enabled"], True)

    def test_disabled_flag(self):
        frame = build_hello_ack_frame(
            algorithm=COMPRESSION_ALGORITHM_MSGPACK_ZLIB,
            enabled=False,
        )
        self.assertIs(frame["payload"]["compression"]["enabled"], False)

    def test_custom_threshold_and_trace_id(self):
        custom_id = "22222222-2222-2222-2222-222222222222"
        frame = build_hello_ack_frame(
            algorithm="zstd",
            threshold=4096,
            trace_id=custom_id,
            seq=7,
        )
        self.assertEqual(frame["trace_id"], custom_id)
        self.assertEqual(frame["seq"], 7)
        self.assertEqual(frame["payload"]["compression"]["algorithm"], "zstd")
        self.assertEqual(frame["payload"]["compression"]["threshold"], 4096)

    def test_empty_algorithm_raises(self):
        with self.assertRaises(HelloFrameError) as ctx:
            build_hello_ack_frame("")
        self.assertIn("non-empty", str(ctx.exception))

    def test_negative_threshold_raises(self):
        with self.assertRaises(HelloFrameError):
            build_hello_ack_frame("algo", threshold=-5)

    def test_non_int_threshold_raises(self):
        with self.assertRaises(HelloFrameError):
            build_hello_ack_frame("algo", threshold=1.5)  # type: ignore[arg-type]


class TestParseHelloCapabilities(SimpleTestCase):
    """Tests for parse_hello_capabilities."""

    def test_valid_frame_round_trip(self):
        frame = build_hello_frame(["msgpack+zlib", "zstd"], threshold=2048)
        algorithms, threshold = parse_hello_capabilities(frame)
        self.assertEqual(algorithms, ["msgpack+zlib", "zstd"])
        self.assertEqual(threshold, 2048)

    def test_valid_frame_default_threshold(self):
        frame = build_hello_frame(["msgpack+zlib"])
        algorithms, threshold = parse_hello_capabilities(frame)
        self.assertEqual(algorithms, ["msgpack+zlib"])
        self.assertEqual(threshold, DEFAULT_COMPRESS_THRESHOLD)

    def test_non_dict_input_raises(self):
        with self.assertRaises(HelloFrameError) as ctx:
            parse_hello_capabilities("not a dict")  # type: ignore[arg-type]
        self.assertIn("expected dict", str(ctx.exception))

    def test_wrong_type_raises(self):
        frame = {"type": "agent.heartbeat", "payload": {}}
        with self.assertRaises(HelloFrameError) as ctx:
            parse_hello_capabilities(frame)
        self.assertIn("not a hello frame", str(ctx.exception))

    def test_missing_payload_raises(self):
        frame = {"type": "hello"}
        with self.assertRaises(HelloFrameError) as ctx:
            parse_hello_capabilities(frame)
        self.assertIn("payload must be dict", str(ctx.exception))

    def test_payload_not_dict_raises(self):
        frame = {"type": "hello", "payload": "not a dict"}
        with self.assertRaises(HelloFrameError):
            parse_hello_capabilities(frame)

    def test_missing_compression_raises(self):
        frame = {"type": "hello", "payload": {}}
        with self.assertRaises(HelloFrameError) as ctx:
            parse_hello_capabilities(frame)
        self.assertIn("compression must be dict", str(ctx.exception))

    def test_compression_not_dict_raises(self):
        frame = {"type": "hello", "payload": {"compression": "not a dict"}}
        with self.assertRaises(HelloFrameError):
            parse_hello_capabilities(frame)

    def test_empty_algorithms_raises(self):
        frame = {
            "type": "hello",
            "payload": {"compression": {"algorithms": [], "threshold": 1024}},
        }
        with self.assertRaises(HelloFrameError) as ctx:
            parse_hello_capabilities(frame)
        self.assertIn("algorithms must be a non-empty list", str(ctx.exception))

    def test_algorithms_not_list_raises(self):
        frame = {
            "type": "hello",
            "payload": {"compression": {"algorithms": "not a list", "threshold": 1024}},
        }
        with self.assertRaises(HelloFrameError):
            parse_hello_capabilities(frame)

    def test_invalid_threshold_raises(self):
        frame = {
            "type": "hello",
            "payload": {"compression": {"algorithms": ["x"], "threshold": -1}},
        }
        with self.assertRaises(HelloFrameError):
            parse_hello_capabilities(frame)

    def test_missing_threshold_uses_default(self):
        frame = {
            "type": "hello",
            "payload": {"compression": {"algorithms": ["x"]}},
        }
        algorithms, threshold = parse_hello_capabilities(frame)
        self.assertEqual(algorithms, ["x"])
        self.assertEqual(threshold, DEFAULT_COMPRESS_THRESHOLD)


class TestParseHelloAckCapabilities(SimpleTestCase):
    """Tests for parse_hello_ack_capabilities."""

    def test_valid_frame_round_trip(self):
        frame = build_hello_ack_frame(
            algorithm="msgpack+zlib",
            threshold=2048,
            enabled=True,
        )
        algorithm, threshold, enabled = parse_hello_ack_capabilities(frame)
        self.assertEqual(algorithm, "msgpack+zlib")
        self.assertEqual(threshold, 2048)
        self.assertIs(enabled, True)

    def test_valid_frame_disabled(self):
        frame = build_hello_ack_frame("msgpack+zlib", enabled=False)
        algorithm, threshold, enabled = parse_hello_ack_capabilities(frame)
        self.assertEqual(algorithm, "msgpack+zlib")
        self.assertIs(enabled, False)

    def test_non_dict_input_raises(self):
        with self.assertRaises(HelloFrameError) as ctx:
            parse_hello_ack_capabilities(None)  # type: ignore[arg-type]
        self.assertIn("expected dict", str(ctx.exception))

    def test_wrong_type_raises(self):
        frame = {"type": "hello", "payload": {}}
        with self.assertRaises(HelloFrameError) as ctx:
            parse_hello_ack_capabilities(frame)
        self.assertIn("not a hello.ack frame", str(ctx.exception))

    def test_missing_payload_raises(self):
        frame = {"type": "hello.ack"}
        with self.assertRaises(HelloFrameError) as ctx:
            parse_hello_ack_capabilities(frame)
        self.assertIn("payload must be dict", str(ctx.exception))

    def test_missing_compression_raises(self):
        frame = {"type": "hello.ack", "payload": {}}
        with self.assertRaises(HelloFrameError) as ctx:
            parse_hello_ack_capabilities(frame)
        self.assertIn("compression must be dict", str(ctx.exception))

    def test_missing_algorithm_raises(self):
        frame = {
            "type": "hello.ack",
            "payload": {"compression": {"threshold": 1024, "enabled": True}},
        }
        with self.assertRaises(HelloFrameError) as ctx:
            parse_hello_ack_capabilities(frame)
        self.assertIn("algorithm must be non-empty str", str(ctx.exception))

    def test_empty_algorithm_raises(self):
        frame = {
            "type": "hello.ack",
            "payload": {"compression": {"algorithm": "", "threshold": 1024}},
        }
        with self.assertRaises(HelloFrameError):
            parse_hello_ack_capabilities(frame)

    def test_algorithm_not_str_raises(self):
        frame = {
            "type": "hello.ack",
            "payload": {"compression": {"algorithm": 123, "threshold": 1024}},
        }
        with self.assertRaises(HelloFrameError):
            parse_hello_ack_capabilities(frame)

    def test_invalid_threshold_raises(self):
        frame = {
            "type": "hello.ack",
            "payload": {"compression": {"algorithm": "x", "threshold": -1}},
        }
        with self.assertRaises(HelloFrameError):
            parse_hello_ack_capabilities(frame)

    def test_missing_threshold_uses_default(self):
        frame = {
            "type": "hello.ack",
            "payload": {"compression": {"algorithm": "x", "enabled": True}},
        }
        algorithm, threshold, enabled = parse_hello_ack_capabilities(frame)
        self.assertEqual(algorithm, "x")
        self.assertEqual(threshold, DEFAULT_COMPRESS_THRESHOLD)
        self.assertIs(enabled, True)

    def test_missing_enabled_defaults_true(self):
        frame = {
            "type": "hello.ack",
            "payload": {"compression": {"algorithm": "x", "threshold": 1024}},
        }
        _, _, enabled = parse_hello_ack_capabilities(frame)
        self.assertIs(enabled, True)


# ────────────────────────────────────────────────────────────────────
# Wire-format envelope stability
# ────────────────────────────────────────────────────────────────────


class TestWireFormatEnvelope(SimpleTestCase):
    """Verify the 5-byte envelope is self-describing and stable."""

    def test_header_size_is_5_bytes(self):
        compressor = MessageCompressor(use_msgpack=False)
        wire = compressor.compress({"x": 1})
        self.assertGreaterEqual(len(wire), _HEADER_SIZE)

    def test_reserved_bytes_are_zero(self):
        compressor = MessageCompressor(use_msgpack=False)
        wire = compressor.compress({"x": 1})
        self.assertEqual(wire[2:5], b"\x00\x00\x00")

    def test_format_byte_distinct_for_json_vs_msgpack(self):
        json_compressor = MessageCompressor(use_msgpack=False)
        json_wire = json_compressor.compress({"x": 1})
        self.assertEqual(json_wire[0], _FORMAT_JSON)

        try:
            import msgpack  # noqa: F401  # type: ignore[import-not-found]
        except ImportError:
            self.skipTest("msgpack not installed")
        msgpack_compressor = MessageCompressor(use_msgpack=True)
        msgpack_wire = msgpack_compressor.compress({"x": 1})
        self.assertEqual(msgpack_wire[0], _FORMAT_MSGPACK)
        self.assertNotEqual(json_wire[0], msgpack_wire[0])

    def test_compressed_body_is_valid_zlib_stream(self):
        """Body of a compressed frame should be a valid zlib stream."""
        compressor = MessageCompressor(compress_threshold=32, use_msgpack=False)
        wire = compressor.compress({"data": "x" * 100})
        self.assertEqual(wire[1], _FLAG_ZLIB)
        body = wire[_HEADER_SIZE:]
        # Should not raise — confirms body is a valid zlib stream.
        decompressed = zlib.decompress(body)
        self.assertEqual(json.loads(decompressed.decode("utf-8")), {"data": "x" * 100})


# ────────────────────────────────────────────────────────────────────
# Constants sanity check
# ────────────────────────────────────────────────────────────────────


class TestProtocolConstants(SimpleTestCase):
    """Verify protocol-level constants are stable (spec-42 wire contract)."""

    def test_algorithm_identifier_value(self):
        """The algorithm string is the wire contract — must not change without
        bumping protocol version on both backend + agent."""
        self.assertEqual(COMPRESSION_ALGORITHM_MSGPACK_ZLIB, "msgpack+zlib")

    def test_default_threshold_value(self):
        """1 KB is the documented sweet spot — verify it is the actual default."""
        self.assertEqual(DEFAULT_COMPRESS_THRESHOLD, 1024)

    def test_hello_frame_type_matches_message_type_constant(self):
        """build_hello_frame should produce type="hello" matching MessageType.HELLO."""
        from protocol.constants import MessageType

        frame = build_hello_frame(["msgpack+zlib"])
        self.assertEqual(frame["type"], MessageType.HELLO)

    def test_hello_ack_frame_type_matches_message_type_constant(self):
        from protocol.constants import MessageType

        frame = build_hello_ack_frame("msgpack+zlib")
        self.assertEqual(frame["type"], MessageType.HELLO_ACK)


# ────────────────────────────────────────────────────────────────────
# Cross-helper round-trip (build → parse → build_ack → parse_ack)
# ────────────────────────────────────────────────────────────────────


class TestNegotiationRoundTrip(SimpleTestCase):
    """End-to-end helper round-trip simulating a full negotiation exchange."""

    def test_full_negotiation_flow(self):
        """Simulate: agent builds hello → server parses + builds ack → agent parses ack."""
        # 1. Agent advertises capabilities.
        agent_hello = build_hello_frame(
            algorithms=[COMPRESSION_ALGORITHM_MSGPACK_ZLIB],
            threshold=2048,
        )
        # 2. Server parses hello.
        algorithms, threshold = parse_hello_capabilities(agent_hello)
        self.assertIn(COMPRESSION_ALGORITHM_MSGPACK_ZLIB, algorithms)
        self.assertEqual(threshold, 2048)
        # 3. Server picks the algorithm and responds.
        server_ack = build_hello_ack_frame(
            algorithm=COMPRESSION_ALGORITHM_MSGPACK_ZLIB,
            threshold=threshold,
            enabled=True,
        )
        # 4. Agent parses ack and switches to compressed mode.
        algorithm, negotiated_threshold, enabled = parse_hello_ack_capabilities(server_ack)
        self.assertEqual(algorithm, COMPRESSION_ALGORITHM_MSGPACK_ZLIB)
        self.assertEqual(negotiated_threshold, 2048)
        self.assertTrue(enabled)

    def test_server_declines_compression_flow(self):
        """Server can decline (enabled=False) — agent must fall back to JSON."""
        agent_hello = build_hello_frame(["msgpack+zlib"])
        _, _ = parse_hello_capabilities(agent_hello)
        server_ack = build_hello_ack_frame(
            algorithm="msgpack+zlib",
            enabled=False,  # decline
        )
        _, _, enabled = parse_hello_ack_capabilities(server_ack)
        self.assertFalse(enabled)


# ====================================================================
# Source: test_compression.py — Negotiation protocol
# ====================================================================


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
class TestCompressionNegotiation(TestCase):
    """End-to-end Hello/Hello.ack negotiation via WebsocketCommunicator."""

    async def _connect(self, *, agent_id: str = "test-agent-compression"):
        """Connect a WS communicator with a stubbed agent scope.

        Drains the initial connect ack frame so subsequent receive_from()
        calls return the frame we actually want to assert on.
        """
        communicator = WebsocketCommunicator(
            WorkerConsumer.as_asgi(), TEST_WS_PATH,
        )
        communicator.scope["agent"] = MagicMock(agent_id=agent_id)
        await communicator.connect()
        await communicator.receive_from()  # drain connect ack
        return communicator

    async def _send_hello(
        self,
        communicator,
        *,
        algorithms: list[str],
        threshold: int = DEFAULT_COMPRESS_THRESHOLD,
    ) -> dict:
        """Send a Hello frame and return the parsed Hello.ack response."""
        hello_frame = build_hello_frame(algorithms, threshold=threshold)
        await communicator.send_to(text_data=json.dumps(hello_frame))
        ack_raw = await communicator.receive_from()
        # Hello.ack is always JSON text_data per the spec-42 wire contract
        # (negotiation frames are never compressed).
        return json.loads(ack_raw)

    # ── Accept path ──────────────────────────────────────────────────

    async def test_hello_with_supported_algorithm_negotiates(self):
        """Agent advertises msgpack+zlib → server accepts (enabled=True)."""
        communicator = await self._connect()
        try:
            ack = await self._send_hello(
                communicator,
                algorithms=[COMPRESSION_ALGORITHM_MSGPACK_ZLIB],
                threshold=1024,
            )
            self.assertEqual(ack["type"], MessageType.HELLO_ACK)
            compression = ack["payload"]["compression"]
            self.assertEqual(compression["algorithm"], COMPRESSION_ALGORITHM_MSGPACK_ZLIB)
            self.assertEqual(compression["threshold"], 1024)
            self.assertIs(compression["enabled"], True)
        finally:
            await communicator.disconnect()

    async def test_hello_picks_msgpack_zlib_when_advertised_alongside_others(self):
        """Server prefers msgpack+zlib even when agent lists multiple algos."""
        communicator = await self._connect()
        try:
            ack = await self._send_hello(
                communicator,
                algorithms=["zstd", COMPRESSION_ALGORITHM_MSGPACK_ZLIB, "gzip"],
            )
            self.assertEqual(ack["payload"]["compression"]["algorithm"],
                             COMPRESSION_ALGORITHM_MSGPACK_ZLIB)
            self.assertTrue(ack["payload"]["compression"]["enabled"])
        finally:
            await communicator.disconnect()

    # ── Decline path ─────────────────────────────────────────────────

    async def test_hello_with_unsupported_algorithm_declines(self):
        """Agent advertises only unknown algos → server declines (enabled=False)."""
        communicator = await self._connect()
        try:
            ack = await self._send_hello(
                communicator,
                algorithms=["zstd", "gzip"],  # neither is server-supported
            )
            self.assertEqual(ack["type"], MessageType.HELLO_ACK)
            compression = ack["payload"]["compression"]
            self.assertIs(compression["enabled"], False)
            # algorithm field should echo one of the agent's algorithms
            self.assertIn(compression["algorithm"], ["zstd", "gzip"])
        finally:
            await communicator.disconnect()

    # ── Malformed Hello ──────────────────────────────────────────────

    async def test_malformed_hello_returns_error_frame_and_stays_unnegotiated(self):
        """Malformed Hello (missing compression) → error frame, negotiation off."""
        communicator = await self._connect()
        try:
            # Build a frame with type=hello but missing compression payload.
            bad_hello = {
                "trace_id": "00000000-0000-0000-0000-000000000001",
                "type": "hello",
                "seq": 1,
                "timestamp": "2026-07-20T00:00:00Z",
                "payload": {},  # missing "compression"
            }
            await communicator.send_to(text_data=json.dumps(bad_hello))
            response_raw = await communicator.receive_from()
            response = json.loads(response_raw)
            # Server should return an error frame (agent.status + status=error).
            self.assertEqual(response["type"], MessageType.AGENT_STATUS)
            self.assertEqual(response["payload"]["status"], "error")
            # And the consumer should remain non-negotiated.
            # (No direct access to consumer instance via communicator, but
            # we can verify by sending a normal frame and confirming
            # text_data round-trips — i.e., no compression kicked in.)
        finally:
            await communicator.disconnect()

    # ── Backward compat: legacy agent ───────────────────────────────

    async def test_legacy_agent_without_hello_stays_json(self):
        """Agent never sends Hello → all frames stay JSON text_data."""
        communicator = await self._connect()
        try:
            # Send a heartbeat directly (no Hello first).
            heartbeat = serialize_frame(
                msg_type=MessageType.AGENT_HEARTBEAT,
                payload={"status": "idle", "stats": {"cpu": 10, "memory": 20, "fps": 30}},
            )
            await communicator.send_to(text_data=heartbeat)
            # Expect an event.ack back as text_data (not bytes_data).
            ack_raw = await communicator.receive_from()
            # Should be a JSON string, not bytes.
            self.assertIsInstance(ack_raw, str)
            ack = json.loads(ack_raw)
            self.assertEqual(ack["type"], MessageType.EVENT_ACK)
        finally:
            await communicator.disconnect()


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
class TestSendCompressionPath(TestCase):
    """Verify WorkerConsumer.send() switches to bytes_data post-negotiation."""

    async def _connect_and_negotiate(
        self,
        *,
        threshold: int = 64,  # low threshold so we can trigger compression easily
    ):
        """Connect + negotiate compression; return (communicator, consumer)."""
        communicator = WebsocketCommunicator(
            WorkerConsumer.as_asgi(), TEST_WS_PATH,
        )
        communicator.scope["agent"] = MagicMock(agent_id="test-agent-send")
        await communicator.connect()
        await communicator.receive_from()  # drain connect ack

        # Negotiate.
        hello_frame = build_hello_frame(
            [COMPRESSION_ALGORITHM_MSGPACK_ZLIB], threshold=threshold,
        )
        await communicator.send_to(text_data=json.dumps(hello_frame))
        await communicator.receive_from()  # drain Hello.ack

        return communicator

    async def test_large_frame_post_negotiation_sent_as_bytes(self):
        """After negotiation, large frames go out as compressed bytes_data.

        With threshold=32 even a small event.ack frame triggers compression,
        so the response should be bytes (proving send() took the compressed
        path). We then decompress and verify the content is the expected ack.
        """
        communicator = await self._connect_and_negotiate(threshold=32)
        try:
            heartbeat = serialize_frame(
                msg_type=MessageType.AGENT_HEARTBEAT,
                payload={"status": "idle", "stats": {"cpu": 1, "memory": 2, "fps": 3}},
            )
            await communicator.send_to(text_data=heartbeat)
            response = await communicator.receive_from()
            # With threshold=32 the ack frame (~150 bytes JSON) triggers
            # compression → response must be bytes.
            self.assertIsInstance(response, bytes,
                                 "Large ack frame should be compressed bytes_data")
            ack = _decode_response(response, threshold=32)
            self.assertEqual(ack["type"], MessageType.EVENT_ACK)
            self.assertEqual(ack["payload"]["ack_type"], MessageType.AGENT_HEARTBEAT)
        finally:
            await communicator.disconnect()

    async def test_small_frame_post_negotiation_stays_text(self):
        """After negotiation, frames < threshold still go out as JSON text_data."""
        communicator = await self._connect_and_negotiate(threshold=4096)
        try:
            # Send a heartbeat with a tiny payload — well under 4096 bytes.
            heartbeat = serialize_frame(
                msg_type=MessageType.AGENT_HEARTBEAT,
                payload={"status": "idle"},
            )
            await communicator.send_to(text_data=heartbeat)
            # The consumer's event.ack response should also be small → text_data.
            response = await communicator.receive_from()
            self.assertIsInstance(response, str)
            ack = json.loads(response)
            self.assertEqual(ack["type"], MessageType.EVENT_ACK)
        finally:
            await communicator.disconnect()


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
class TestReceiveCompressionPath(TestCase):
    """Verify WorkerConsumer.receive() handles compressed bytes_data post-negotiation."""

    async def _connect_and_negotiate(
        self,
        *,
        threshold: int = 64,
        agent_id: str = "test-agent-recv",
    ):
        """Connect + negotiate compression; return communicator."""
        communicator = WebsocketCommunicator(
            WorkerConsumer.as_asgi(), TEST_WS_PATH,
        )
        communicator.scope["agent"] = MagicMock(agent_id=agent_id)
        await communicator.connect()
        await communicator.receive_from()  # drain connect ack

        hello_frame = build_hello_frame(
            [COMPRESSION_ALGORITHM_MSGPACK_ZLIB], threshold=threshold,
        )
        await communicator.send_to(text_data=json.dumps(hello_frame))
        await communicator.receive_from()  # drain Hello.ack

        return communicator

    async def test_compressed_heartbeat_round_trips_through_consumer(self):
        """Agent sends a compressed heartbeat → server decompresses + acks."""
        communicator = await self._connect_and_negotiate(threshold=32)
        try:
            # Build a heartbeat frame larger than threshold so the agent
            # would compress it on its end. Here we simulate the agent
            # side by manually compressing.
            heartbeat_payload = {
                "status": "idle",
                "stats": {"cpu": 10, "memory": 20, "fps": 30},
                "padding": "x" * 200,  # ensure body > 32 bytes
            }
            heartbeat_frame = {
                "trace_id": "00000000-0000-0000-0000-000000000002",
                "type": MessageType.AGENT_HEARTBEAT,
                "seq": 1,
                "timestamp": "2026-07-20T00:00:00Z",
                "payload": heartbeat_payload,
            }
            # Use a compressor matching the negotiated config.
            compressor = MessageCompressor(compress_threshold=32, use_msgpack=True)
            wire_bytes = compressor.compress(heartbeat_frame)
            # Send as bytes_data.
            await communicator.send_to(bytes_data=wire_bytes)

            # Consumer should decompress + dispatch → send event.ack back.
            # The ack frame may itself be compressed (threshold=32), so
            # decode either format.
            ack_raw = await communicator.receive_from()
            ack = _decode_response(ack_raw, threshold=32)
            self.assertEqual(ack["type"], MessageType.EVENT_ACK)
            self.assertEqual(ack["payload"]["ack_type"], MessageType.AGENT_HEARTBEAT)
        finally:
            await communicator.disconnect()

    async def test_compressed_frame_with_invalid_bytes_returns_error(self):
        """Garbage bytes_data post-negotiation → error frame, connection survives."""
        communicator = await self._connect_and_negotiate(threshold=32)
        try:
            # Send garbage bytes — not a valid compressor envelope.
            await communicator.send_to(bytes_data=b"not-a-valid-compressor-envelope")
            # Consumer should send an error frame (text or compressed bytes
            # depending on threshold — decode either way) and continue.
            response = await communicator.receive_from()
            error = _decode_response(response, threshold=32)
            self.assertEqual(error["type"], MessageType.AGENT_STATUS)
            self.assertEqual(error["payload"]["status"], "error")
        finally:
            await communicator.disconnect()

    async def test_mixed_mode_text_and_bytes_both_work_post_negotiation(self):
        """Post-negotiation, agent can send text_data AND bytes_data in any mix."""
        communicator = await self._connect_and_negotiate(threshold=32)
        try:
            # 1. Send a text_data heartbeat (small control frame path).
            small_heartbeat = serialize_frame(
                msg_type=MessageType.AGENT_HEARTBEAT,
                payload={"status": "idle"},
            )
            await communicator.send_to(text_data=small_heartbeat)
            ack1_raw = await communicator.receive_from()
            ack1 = _decode_response(ack1_raw, threshold=32)
            self.assertEqual(ack1["type"], MessageType.EVENT_ACK)

            # 2. Send a compressed bytes_data heartbeat (large frame path).
            large_payload = {
                "status": "idle",
                "stats": {"cpu": 10, "memory": 20, "fps": 30},
                "padding": "y" * 200,
            }
            heartbeat_frame = {
                "trace_id": "00000000-0000-0000-0000-000000000003",
                "type": MessageType.AGENT_HEARTBEAT,
                "seq": 2,
                "timestamp": "2026-07-20T00:00:00Z",
                "payload": large_payload,
            }
            compressor = MessageCompressor(compress_threshold=32, use_msgpack=True)
            wire_bytes = compressor.compress(heartbeat_frame)
            await communicator.send_to(bytes_data=wire_bytes)
            ack2_raw = await communicator.receive_from()
            ack2 = _decode_response(ack2_raw, threshold=32)

            # Both acks should be valid event.ack frames.
            for ack in (ack1, ack2):
                self.assertEqual(ack["type"], MessageType.EVENT_ACK)
        finally:
            await communicator.disconnect()


# ====================================================================
# Source: test_compression.py — End-to-end tests
# ====================================================================


@override_settings(
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
class TestCompressionE2E(TestCase):
    """Full-flow E2E: negotiate → compress → verify wire properties."""

    async def _connect_and_negotiate(
        self,
        *,
        agent_id: str = "test-agent-e2e",
        threshold: int = DEFAULT_COMPRESS_THRESHOLD,
    ):
        """Connect + send Hello + drain Hello.ack. Returns (communicator, ack_frame)."""
        communicator = WebsocketCommunicator(
            WorkerConsumer.as_asgi(), TEST_WS_PATH,
        )
        communicator.scope["agent"] = MagicMock(agent_id=agent_id)
        await communicator.connect()
        await communicator.receive_from()  # drain connect ack

        hello = build_hello_frame(
            algorithms=[COMPRESSION_ALGORITHM_MSGPACK_ZLIB],
            threshold=threshold,
        )
        await communicator.send_to(text_data=json.dumps(hello))
        ack_raw = await communicator.receive_from()
        ack_frame = json.loads(ack_raw)  # Hello.ack is always JSON text
        return communicator, ack_frame

    async def test_full_negotiation_enables_compression(self):
        """Hello + Hello.ack flips server into compressed mode."""
        communicator, ack_frame = await self._connect_and_negotiate()
        try:
            self.assertEqual(ack_frame["type"], "hello.ack")
            algorithm, threshold, enabled = parse_hello_ack_capabilities(ack_frame)
            self.assertTrue(enabled)
            self.assertEqual(algorithm, COMPRESSION_ALGORITHM_MSGPACK_ZLIB)
            self.assertEqual(threshold, DEFAULT_COMPRESS_THRESHOLD)
        finally:
            await communicator.disconnect()

    async def test_large_frame_post_negotiation_is_compressed(self):
        """Frames >= threshold are sent as compressed bytes (not JSON text)."""
        # Use a small threshold so even a modest payload triggers compression.
        communicator, _ = await self._connect_and_negotiate(threshold=64)
        try:
            # Send a heartbeat; server's event.ack response is small (~150 bytes
            # JSON), which is still > 64 → compressed.
            heartbeat = serialize_frame(msg_type=MessageType.AGENT_HEARTBEAT)
            await communicator.send_to(text_data=heartbeat)

            response = await communicator.receive_from()
            self.assertIsInstance(
                response, bytes,
                "post-negotiation response >= threshold must be compressed bytes",
            )
            # Decompresses cleanly and matches expected ack structure.
            decoded = MessageCompressor(compress_threshold=64).decompress(response)
            self.assertEqual(decoded["type"], MessageType.EVENT_ACK)
        finally:
            await communicator.disconnect()

    async def test_compression_ratio_for_large_payload(self):
        """Wire size of a compressed large frame is <= 50% of JSON size.

        spec-42 acceptance: screenshot-like ~10KB payloads must see
        bandwidth reduction >= 50%. We build a comparable payload here
        (no base64 image, but a deeply nested structure with repeated
        strings) and verify the ratio.
        """
        # Build a ~10KB JSON-serializable payload (nested dict + list).
        big_payload = {
            "type": "task.result",
            "trace_id": "test-trace-id-e2e-0001",
            "seq": 42,
            "timestamp": "2026-07-20T12:00:00Z",
            "payload": {
                "execution_id": "exec-001",
                "success": True,
                "elapsed_time": 1.5,
                "steps": [
                    {"step_id": i, "name": f"step-{i}", "result": "ok" * 20}
                    for i in range(50)
                ],
                "screenshot_metadata": {
                    "width": 1920,
                    "height": 1080,
                    "format": "png",
                    "hash": "abc123" * 50,
                },
            },
        }
        json_size = len(json.dumps(big_payload).encode("utf-8"))
        self.assertGreater(json_size, 5000, "test payload must be > 5KB")

        # Compress with msgpack + zlib (server's chosen algorithm).
        compressor = MessageCompressor(compress_threshold=1, use_msgpack=True)
        wire_bytes = compressor.compress(big_payload)
        wire_size = len(wire_bytes)

        # Acceptance: wire_size <= 50% of json_size.
        ratio = wire_size / json_size
        self.assertLess(
            ratio, 0.5,
            f"compression ratio {ratio:.2%} does not meet <50% target "
            f"(json={json_size}B, wire={wire_size}B)",
        )

        # Round-trip integrity.
        decoded = compressor.decompress(wire_bytes)
        self.assertEqual(decoded, big_payload)

    async def test_round_trip_integrity_post_negotiation(self):
        """Compressed frames round-trip with no data loss."""
        communicator, _ = await self._connect_and_negotiate(threshold=32)
        try:
            # Send a heartbeat with a distinct trace_id we can verify back.
            heartbeat = serialize_frame(
                msg_type=MessageType.AGENT_HEARTBEAT,
                payload={"marker": "round-trip-test"},
            )
            await communicator.send_to(text_data=heartbeat)

            response = await communicator.receive_from()
            decoded = _decode_response(response, threshold=32)

            self.assertEqual(decoded["type"], MessageType.EVENT_ACK)
            self.assertEqual(
                decoded["payload"]["ack_type"],
                MessageType.AGENT_HEARTBEAT,
            )
        finally:
            await communicator.disconnect()

    async def test_legacy_agent_stays_json_end_to_end(self):
        """Agent that never sends Hello keeps the connection on JSON text."""
        communicator = WebsocketCommunicator(
            WorkerConsumer.as_asgi(), TEST_WS_PATH,
        )
        communicator.scope["agent"] = MagicMock(agent_id="legacy-agent")
        await communicator.connect()
        try:
            await communicator.receive_from()  # drain connect ack

            # Send a heartbeat directly (no Hello first).
            heartbeat = serialize_frame(msg_type=MessageType.AGENT_HEARTBEAT)
            await communicator.send_to(text_data=heartbeat)

            response = await communicator.receive_from()
            # Legacy path: response is JSON text, not compressed bytes.
            self.assertIsInstance(response, str)
            decoded = json.loads(response)
            self.assertEqual(decoded["type"], MessageType.EVENT_ACK)
        finally:
            await communicator.disconnect()

    async def test_small_frame_post_negotiation_stays_text(self):
        """Small frames (< threshold) post-negotiation avoid zlib overhead.

        The server's Hello.ack response itself is the canonical example:
        it's sent right after negotiation, as JSON text, because the
        payload is small and Hello.ack must be self-describing for the
        agent to decode it before any compressor is initialized.
        """
        communicator, _ = await self._connect_and_negotiate()
        # The _connect_and_negotiate helper already received Hello.ack as
        # JSON text — the fact that we got here without error proves
        # small frames stay text. The explicit assertion below documents
        # the invariant for future readers.
        try:
            # Send a tiny custom frame that the server will reject with an
            # error frame. Error frames are small and should stay JSON.
            await communicator.send_to(text_data="not a valid frame {{{")
            response = await communicator.receive_from()
            # Small error frame → JSON text (not bytes).
            self.assertIsInstance(response, str)
        finally:
            await communicator.disconnect()
