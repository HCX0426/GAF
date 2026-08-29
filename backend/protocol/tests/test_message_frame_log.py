"""Tests for message frame logging (spec 2026-08-29-logging-system-consolidation P1-1).

覆盖分层 (规避 channels DatabaseSyncToAsync 在 async TestCase 的建连限制):
1. 接线: AgentConsumer.receive/send 确实调用 _log_frame (mock 断言, WS 集成)
2. 逻辑: _normalize_frame_payload 纯函数 (skip-body / 截断 / 透传)
3. 模型: MessageFrameLog sync 直写可用 (TestTransaction)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TestCase, override_settings

from protocol.consumers import AgentConsumer, _normalize_frame_payload
from protocol.models import MessageFrameLog
from protocol.serializers import serialize_frame
from protocol.tests import TEST_WS_PATH
from tasks.factories import TaskExecutionFactory
from tasks.models import TaskExecution


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestMessageFrameLogWiring(TestCase):
    """WS 接线验证: receive→inbound 记录, send→outbound 记录。"""

    async def _connect_communicator(self):
        communicator = WebsocketCommunicator(
            AgentConsumer.as_asgi(), TEST_WS_PATH
        )
        communicator.scope['agent'] = MagicMock(agent_id='test-frame-log')
        await communicator.connect()
        await communicator.receive_from()  # drain connect ack
        return communicator

    async def test_receive_logs_inbound(self):
        """agent 发送帧 → _log_frame 被以 inbound 调用。"""
        execution = await sync_to_async(TaskExecutionFactory.create)(status=TaskExecution.Status.RUNNING)
        communicator = await self._connect_communicator()
        try:
            with patch.object(AgentConsumer, '_log_frame', new=AsyncMock(return_value=None)) as mock_log:
                frame = serialize_frame(msg_type='task.result', payload={
                    'execution_id': str(execution.id), 'success': True,
                    'elapsed_time': 0.5, 'error_msg': '', 'data': {},
                })
                await communicator.send_to(text_data=frame)
                await communicator.receive_from()  # ack
                await asyncio.sleep(0.05)
                inbound_calls = [c for c in mock_log.await_args_list if c.args[1] == 'inbound']
                self.assertGreaterEqual(len(inbound_calls), 1)
        finally:
            await communicator.disconnect()

    async def test_send_logs_outbound(self):
        """backend 回发 ack → _log_frame 被以 outbound 调用。"""
        execution = await sync_to_async(TaskExecutionFactory.create)(status=TaskExecution.Status.RUNNING)
        communicator = await self._connect_communicator()
        try:
            with patch.object(AgentConsumer, '_log_frame', new=AsyncMock(return_value=None)) as mock_log:
                frame = serialize_frame(msg_type='task.result', payload={
                    'execution_id': str(execution.id), 'success': True,
                    'elapsed_time': 0.5, 'error_msg': '', 'data': {},
                })
                await communicator.send_to(text_data=frame)
                await communicator.receive_from()
                await asyncio.sleep(0.05)
                outbound_calls = [c for c in mock_log.await_args_list if c.args[1] == 'outbound']
                self.assertGreaterEqual(len(outbound_calls), 1)
        finally:
            await communicator.disconnect()

    async def test_disabled_flag_skips(self):
        """PROTOCOL_FRAME_LOG_ENABLED=False 时 receive 不调用 _log_frame。"""
        execution = await sync_to_async(TaskExecutionFactory.create)(status=TaskExecution.Status.RUNNING)
        communicator = await self._connect_communicator()
        try:
            with patch('protocol.consumers.PROTOCOL_FRAME_LOG_ENABLED', False), \
                    patch.object(AgentConsumer, '_log_frame', new=AsyncMock(return_value=None)) as mock_log:
                    frame = serialize_frame(msg_type='task.result', payload={
                        'execution_id': str(execution.id), 'success': True,
                        'elapsed_time': 0.5, 'error_msg': '', 'data': {},
                    })
                    await communicator.send_to(text_data=frame)
                    await communicator.receive_from()
                    await asyncio.sleep(0.05)
                    inbound_calls = [c for c in mock_log.await_args_list if c.args[1] == 'inbound']
                    self.assertEqual(len(inbound_calls), 0)
        finally:
            await communicator.disconnect()


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestMessageFrameLogModel(TestCase):
    """模型 sync 直写可用 + payload 逻辑。"""

    def test_db_insert_and_query(self):
        MessageFrameLog.objects.create(message_type='task.result', direction='inbound', payload={})
        self.assertEqual(MessageFrameLog.objects.filter(message_type='task.result').count(), 1)


class TestNormalizeFramePayload(TestCase):
    """payload 收集/截断纯函数单测。"""

    def test_skipped_body_types(self):
        payload = _normalize_frame_payload('screenshot.frame', {'image_base64': 'A' * 5000})
        self.assertEqual(payload.get('_skipped'), True)
        self.assertNotIn('image_base64', payload)

    def test_large_payload_truncated(self):
        payload = _normalize_frame_payload('task.progress', {'data': {'big': 'X' * 5000}})
        self.assertTrue(payload.get('_truncated'))
        self.assertLessEqual(len(payload.get('preview', '')), 2200)

    def test_small_payload_passthrough(self):
        frame = {'trace_id': 'abc', 'payload': {'done': 1}}
        self.assertEqual(_normalize_frame_payload('task.progress', frame), frame)
