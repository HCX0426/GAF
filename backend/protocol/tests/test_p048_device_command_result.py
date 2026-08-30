"""P-048 (2026-07-29): device.action_result 恢复动作分支测试.

验证 ``WorkerConsumer._handle_device_action_result`` 在 payload 含 ``command``
字段时正确路由到 ``_handle_device_command_result``:

1. 写入 / 更新 RecoveryLog (N191 schema 归一化: command vs action 字段区分)
2. 广播到 dashboard 供用户调试视角查看 (N192-B6 执行反馈)
3. recovery_level 映射正确 (app vs device)
4. 既有 device_discovered 分支不被破坏 (回归测试)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import TestCase, override_settings

from protocol.constants import MessageType
from protocol.consumers import WorkerConsumer
from protocol.serializers import serialize_frame
from protocol.tests import TEST_WS_PATH


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestDeviceCommandResultHandler(TestCase):
    """WorkerConsumer._handle_device_command_result (P-048 新增分支).

    Uses ``TestCase`` (savepoint isolation). The consumer's
    ``_handle_device_command_result`` uses ``database_sync_to_async`` to
    wrap ORM writes, which execute in their own transaction connection
    and commit immediately (not via ``transaction.on_commit``). Tests
    wait for completion with ``asyncio.sleep``.

    Previously used ``TransactionTestCase`` (truncates tables between
    tests), but that polluted other workers' test data under
    ``pytest -n auto`` parallel runs (N194 fix, 2026-07-29).
    """

    async def _connect(self):
        """Helper: 建立一个 mock agent WS 连接."""
        communicator = WebsocketCommunicator(
            WorkerConsumer.as_asgi(), TEST_WS_PATH,
        )
        communicator.scope['agent'] = MagicMock(agent_id='test-p048-agent')
        await communicator.connect()
        # Consume the initial hello frame
        await communicator.receive_from()
        return communicator

    async def test_command_result_with_recovery_log_id_updates_existing(self):
        """有 recovery_log_id 时, 更新既有 RecoveryLog."""
        from scheduler.models import RecoveryLog

        # 预创建一条 RecoveryLog (模拟 _action_send_device_command 派发时创建)
        log = await sync_to_async(RecoveryLog.objects.create)(
            recovery_level='device',
            trigger_event='device 1 崩溃',
            action_taken='ActionChain: 派发 restart_emulator 到 agent',
            success=False,  # 派发时未确认结果
            details={'target_id': 1, 'command': 'restart_emulator'},
        )

        communicator = await self._connect()
        try:
            result_frame = serialize_frame(
                msg_type=MessageType.DEVICE_ACTION_RESULT,
                payload={
                    "command": "restart_emulator",
                    "target_id": 1,
                    "success": True,
                    "output": {
                        "emulator_type": "ldplayer",
                        "instance_id": 0,
                        "boot_completed": True,
                    },
                    "recovery_log_id": log.id,
                    "execution_id": "exec-1",
                },
            )
            await communicator.send_to(text_data=result_frame)
            await asyncio.sleep(0.2)
        finally:
            await communicator.disconnect()

        await sync_to_async(log.refresh_from_db)()
        self.assertTrue(log.success)
        self.assertIn('restart_emulator', log.action_taken)
        self.assertEqual(log.details['command'], 'restart_emulator')
        self.assertTrue(log.details['output']['boot_completed'])
        self.assertEqual(log.details['execution_id'], 'exec-1')

    async def test_command_result_without_recovery_log_id_creates_new(self):
        """无 recovery_log_id 时 (e.g. warmup 触发), 新建 RecoveryLog."""
        from scheduler.models import RecoveryLog

        before = await sync_to_async(lambda: RecoveryLog.objects.count())()

        communicator = await self._connect()
        try:
            result_frame = serialize_frame(
                msg_type=MessageType.DEVICE_ACTION_RESULT,
                payload={
                    "command": "restart_app",
                    "target_id": 1,
                    "success": True,
                    "output": {"restarted": True, "package_name": "BD2.exe"},
                },
            )
            await communicator.send_to(text_data=result_frame)
            await asyncio.sleep(0.2)
        finally:
            await communicator.disconnect()

        after = await sync_to_async(lambda: RecoveryLog.objects.count())()
        self.assertEqual(after, before + 1)

        new_log = await sync_to_async(
            lambda: RecoveryLog.objects.order_by('-id').first()
        )()
        self.assertEqual(new_log.recovery_level, 'app')  # restart_app → app level
        self.assertTrue(new_log.success)
        self.assertEqual(new_log.details['command'], 'restart_app')

    async def test_command_result_failure_path_writes_error(self):
        """失败结果也落盘 (N192-A2 失败路径落盘)."""
        from scheduler.models import RecoveryLog

        communicator = await self._connect()
        try:
            result_frame = serialize_frame(
                msg_type=MessageType.DEVICE_ACTION_RESULT,
                payload={
                    "command": "relogin",
                    "target_id": 1,
                    "success": False,
                    "output": {
                        "error": "not_implemented",
                        "reason": "relogin requires backend to re-dispatch login pipeline",
                    },
                },
            )
            await communicator.send_to(text_data=result_frame)
            await asyncio.sleep(0.2)
        finally:
            await communicator.disconnect()

        new_log = await sync_to_async(
            lambda: RecoveryLog.objects.order_by('-id').first()
        )()
        self.assertFalse(new_log.success)
        self.assertEqual(new_log.recovery_level, 'app')  # relogin → app level
        self.assertIn('not_implemented', new_log.details['output']['error'])

    async def test_command_result_broadcasts_to_dashboard(self):
        """结果广播到 dashboard 供用户调试视角查看 (N192-B6 执行反馈).

        InMemoryChannelLayer.group_send is async — we just verify it
        doesn't raise and that the RecoveryLog write happens (which
        proves the handler ran to completion including the broadcast).
        """
        from scheduler.models import RecoveryLog

        communicator = await self._connect()
        try:
            result_frame = serialize_frame(
                msg_type=MessageType.DEVICE_ACTION_RESULT,
                payload={
                    "command": "restart_emulator",
                    "target_id": 1,
                    "success": True,
                    "output": {"boot_completed": True},
                },
            )
            await communicator.send_to(text_data=result_frame)
            await asyncio.sleep(0.2)
        finally:
            await communicator.disconnect()

        # RecoveryLog 落盘证明 handler 完整执行 (含 broadcast 调用)
        new_log = await sync_to_async(
            lambda: RecoveryLog.objects.order_by('-id').first()
        )()
        self.assertIsNotNone(new_log)
        self.assertTrue(new_log.success)

    async def test_device_discovered_branch_not_broken(self):
        """回归: 既有 device_discovered 分支仍能正常处理.

        Patch ``_db_register_device`` to return a fixed dict so we don't
        need a real Device setup. Patch at the class level so the bound
        method is replaced.
        """
        communicator = await self._connect()
        try:
            with patch.object(
                WorkerConsumer, '_db_register_device',
                new=AsyncMock(return_value={'created': True, 'id': 99}),
            ):
                result_frame = serialize_frame(
                    msg_type=MessageType.DEVICE_ACTION_RESULT,
                    payload={
                        "action": "device_discovered",
                        "device": {
                            "name": "test-window",
                            "device_type": "windows",
                            "status": "online",
                        },
                    },
                )
                await communicator.send_to(text_data=result_frame)
                await asyncio.sleep(0.2)

        finally:
            await communicator.disconnect()

    def test_recovery_level_mapping(self):
        """_recovery_level_for_command 静态方法映射正确."""
        self.assertEqual(WorkerConsumer._recovery_level_for_command('restart_app'), 'app')
        self.assertEqual(WorkerConsumer._recovery_level_for_command('relogin'), 'app')
        self.assertEqual(WorkerConsumer._recovery_level_for_command('notify_only'), 'app')
        self.assertEqual(WorkerConsumer._recovery_level_for_command('restart_emulator'), 'device')
        self.assertEqual(WorkerConsumer._recovery_level_for_command('reconnect_adb'), 'device')
        self.assertEqual(WorkerConsumer._recovery_level_for_command('switch_backup'), 'device')
        self.assertEqual(WorkerConsumer._recovery_level_for_command('unknown_cmd'), 'device')


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestDeviceCommandForwarding(TestCase):
    """S2 (2026-08-16): consumer.device_command 路由方法.

    scheduler/recovery_engine._action_device_command 通过
    ``channel_layer.group_send('agent_<id>', {'type': 'device.command'})``
    派发恢复命令 — Channels 把该事件路由到本方法, 若缺失则静默丢弃
    (恢复动作报 success 但 agent 永远收不到命令, S2 评估发现的死代码
    路径). 本测试验证 group_send → WS 帧转发链路.
    """

    async def _connect(self):
        communicator = WebsocketCommunicator(
            WorkerConsumer.as_asgi(), TEST_WS_PATH,
        )
        communicator.scope['agent'] = MagicMock(agent_id='test-s2-fwd')
        await communicator.connect()
        await communicator.receive_from()
        return communicator

    async def test_device_command_group_send_forwards_frame(self):
        """group_send device.command → agent 收到对应 WS 帧.

        Note: ``get_channel_layer`` 在模块顶部 import (收集阶段绑定真实
        函数). 若在方法内 import, conftest autouse fixture
        ``_mock_channel_layer`` 已 monkeypatch 该名称, group_send 会打到
        MagicMock 上, 消息永远到不了 consumer.
        """
        import json

        communicator = WebsocketCommunicator(
            WorkerConsumer.as_asgi(), TEST_WS_PATH,
        )
        communicator.scope['agent'] = MagicMock(agent_id='test-s2-fwd')
        await communicator.connect()
        await communicator.receive_from()

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            'agent_test-s2-fwd',
            {
                'type': 'device.command',
                'payload': {
                    'command': 'restart_app',
                    'target_id': 1,
                    'config': {'freeze_timeout_seconds': 120},
                },
            },
        )
        await asyncio.sleep(0.3)
        frame = await communicator.receive_from()
        await communicator.disconnect()

        data = json.loads(frame)
        self.assertEqual(data['type'], MessageType.DEVICE_COMMAND)
        self.assertEqual(data['payload']['command'], 'restart_app')
        self.assertEqual(data['payload']['target_id'], 1)
        self.assertEqual(data['payload']['config']['freeze_timeout_seconds'], 120)

    async def test_device_command_payload_passthrough(self):
        """payload 原样透传 (command / target_id / config 完整)."""
        import json

        communicator = await self._connect()
        try:
            channel_layer = get_channel_layer()
            await channel_layer.group_send(
                'agent_test-s2-fwd',
                {
                    'type': 'device.command',
                    'payload': {
                        'command': 'reconnect_adb',
                        'target_id': 7,
                        'config': {},
                    },
                },
            )
            await asyncio.sleep(0.3)
            frame = await communicator.receive_from()
        finally:
            await communicator.disconnect()

        data = json.loads(frame)
        self.assertEqual(data['type'], MessageType.DEVICE_COMMAND)
        self.assertEqual(data['payload']['command'], 'reconnect_adb')
        self.assertEqual(data['payload']['target_id'], 7)
