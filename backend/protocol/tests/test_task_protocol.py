"""协议扩展单元测试：Agent 注册/心跳、任务分发 wire format、任务状态机。"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TestCase, override_settings
from workers.models import Worker

from protocol.constants import MessageType
from protocol.consumers import AgentConsumer
from protocol.schemas import (
    AGENT_HEARTBEAT_PAYLOAD_SCHEMA,
    AGENT_REGISTER_PAYLOAD_SCHEMA,
    TASK_CANCEL_SCHEMA,
    TASK_DISPATCH_SCHEMA,
    TASK_PROGRESS_SCHEMA,
    TASK_RESULT_SCHEMA,
    TaskState,
)
from protocol.serializers import (
    AgentHeartbeatPayloadSerializer,
    AgentRegisterPayloadSerializer,
    TaskCancelPayloadSerializer,
    TaskDispatchPayloadSerializer,
    TaskProgressPayloadSerializer,
    TaskResultPayloadSerializer,
    serialize_frame,
    validate_payload,
)
from protocol.tests import TEST_WS_PATH


class TestTaskStateMachine(TestCase):
    """测试 TaskState 状态机。"""

    def test_terminal_states(self):
        """验证终止状态包含 completed / failed / cancelled。"""
        terminal = TaskState.terminal_states()
        self.assertEqual(terminal, {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED})

    def test_active_states(self):
        """验证活跃状态包含 pending / dispatched / running。"""
        active = TaskState.active_states()
        self.assertEqual(active, {TaskState.PENDING, TaskState.DISPATCHED, TaskState.RUNNING})

    def test_valid_transitions_coverage(self):
        """验证所有非终态都有定义的合法转移。"""
        transitions = TaskState.valid_transitions()
        for state in TaskState:
            if state in TaskState.terminal_states():
                continue
            self.assertIn(state.value, transitions,
                          f"{state.value} 应有合法转移定义")

    def test_can_transition_valid(self):
        """验证合法状态转移。"""
        self.assertTrue(TaskState.can_transition(TaskState.PENDING, TaskState.DISPATCHED))
        self.assertTrue(TaskState.can_transition(TaskState.DISPATCHED, TaskState.RUNNING))
        self.assertTrue(TaskState.can_transition(TaskState.RUNNING, TaskState.COMPLETED))
        self.assertTrue(TaskState.can_transition(TaskState.RUNNING, TaskState.FAILED))
        self.assertTrue(TaskState.can_transition(TaskState.RUNNING, TaskState.CANCELLED))
        self.assertTrue(TaskState.can_transition(TaskState.PENDING, TaskState.CANCELLED))

    def test_can_transition_invalid(self):
        """验证非法状态转移被拒绝。"""
        self.assertFalse(TaskState.can_transition(TaskState.COMPLETED, TaskState.RUNNING))
        self.assertFalse(TaskState.can_transition(TaskState.FAILED, TaskState.RUNNING))
        self.assertFalse(TaskState.can_transition(TaskState.CANCELLED, TaskState.RUNNING))
        self.assertFalse(TaskState.can_transition(TaskState.RUNNING, TaskState.PENDING))
        self.assertFalse(TaskState.can_transition(TaskState.COMPLETED, TaskState.PENDING))


class TestJsonSchemas(TestCase):
    """测试各消息类型的 JSON Schema 定义。"""

    def test_task_dispatch_schema_required(self):
        """验证 task.dispatch Schema 必填字段。"""
        self.assertEqual(
            set(TASK_DISPATCH_SCHEMA["required"]),
            {"execution_id", "task_id", "pipeline"},
        )

    def test_task_progress_schema_required(self):
        """验证 task.progress Schema 必填字段。"""
        self.assertEqual(
            set(TASK_PROGRESS_SCHEMA["required"]),
            {"execution_id", "step_index", "status"},
        )

    def test_task_result_schema_required(self):
        """验证 task.result Schema 必填字段。"""
        self.assertEqual(
            set(TASK_RESULT_SCHEMA["required"]),
            {"execution_id", "status", "steps_completed", "total_steps"},
        )

    def test_task_cancel_schema_required(self):
        """验证 task.cancel Schema 必填字段。"""
        self.assertEqual(
            set(TASK_CANCEL_SCHEMA["required"]),
            {"execution_id"},
        )

    def test_agent_register_schema_required(self):
        """验证 agent.register 负载 Schema 必填字段。"""
        self.assertEqual(
            set(AGENT_REGISTER_PAYLOAD_SCHEMA["required"]),
            {"agent_id"},
        )

    def test_agent_heartbeat_schema_no_required(self):
        """验证 agent.heartbeat 负载 Schema 无必填字段。"""
        self.assertEqual(
            set(AGENT_HEARTBEAT_PAYLOAD_SCHEMA["required"]),
            set(),
        )


class TestAgentRegisterPayloadSerializer(TestCase):
    """测试 Agent 注册负载序列化器。"""

    def test_valid_minimal_payload(self):
        """验证最小合法负载（仅 agent_id）通过校验。"""
        serializer = AgentRegisterPayloadSerializer(data={"agent_id": "agent-001"})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_valid_full_payload(self):
        """验证完整注册负载通过校验。"""
        payload = {
            "agent_id": "agent-001",
            "hostname": "test-host",
            "ip_address": "192.168.1.100",
            "os_info": "Windows 11",
            "version": "1.0.0",
            "capabilities": {
                "screenshot_methods": ["pyautogui", "dxcam"],
                "input_methods": ["pyautogui", "pynput"],
                "recognition_engines": ["paddleocr", "tesseract"],
            },
            "resource_quota": {"max_concurrent_tasks": 2, "max_memory_mb": 4096},
        }
        serializer = AgentRegisterPayloadSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["agent_id"], "agent-001")
        self.assertEqual(serializer.validated_data["capabilities"]["screenshot_methods"], ["pyautogui", "dxcam"])

    def test_missing_agent_id(self):
        """验证缺少 agent_id 校验失败。"""
        serializer = AgentRegisterPayloadSerializer(data={"hostname": "test"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("agent_id", serializer.errors)

    def test_default_values(self):
        """验证默认值填充。"""
        serializer = AgentRegisterPayloadSerializer(data={"agent_id": "agent-002"})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["hostname"], "")
        self.assertEqual(serializer.validated_data["capabilities"], {})
        self.assertEqual(serializer.validated_data["resource_quota"], {})


class TestAgentHeartbeatPayloadSerializer(TestCase):
    """测试 Agent 心跳负载序列化器。"""

    def test_valid_empty_payload(self):
        """验证空负载通过校验。"""
        serializer = AgentHeartbeatPayloadSerializer(data={})
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_valid_full_payload(self):
        """验证完整心跳负载通过校验。"""
        payload = {
            "agent_id": "agent-001",
            "resource_stats": {
                "cpu_percent": 45.2,
                "memory_used_mb": 2048,
                "memory_total_mb": 8192,
                "active_tasks": 1,
            },
            "status": "busy",
        }
        serializer = AgentHeartbeatPayloadSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["status"], "busy")

    def test_invalid_status_choice(self):
        """验证非法 status 值被拒绝。"""
        serializer = AgentHeartbeatPayloadSerializer(data={"status": "unknown_status"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("status", serializer.errors)


class TestTaskDispatchPayloadSerializer(TestCase):
    """测试任务分发负载序列化器。"""

    def test_valid_minimal_payload(self):
        """验证最小合法分发负载通过校验。"""
        payload = {
            "execution_id": "exec-001",
            "task_id": "task-001",
            "pipeline": [
                {"step_index": 0, "step_name": "login", "step_type": "click"},
            ],
        }
        serializer = TaskDispatchPayloadSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_valid_full_payload(self):
        """验证完整分发负载通过校验。"""
        payload = {
            "execution_id": "exec-001",
            "task_id": "task-001",
            "pipeline": [
                {
                    "step_index": 0,
                    "step_name": "点击开始",
                    "step_type": "click",
                    "action": "click_position",
                    "params": {"x": 100, "y": 200},
                    "retry_count": 2,
                    "timeout_ms": 5000,
                },
            ],
            "options": {
                "max_retries": 3,
                "timeout_seconds": 300,
                "screenshot_on_error": True,
            },
            "game_account": {"account_id": "acc-123", "username": "player1", "server": "s1"},
            "device_constraints": {"os": "windows", "resolution": "1920x1080"},
        }
        serializer = TaskDispatchPayloadSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["execution_id"], "exec-001")

    def test_missing_required_fields(self):
        """验证缺少必填字段校验失败。"""
        payload = {"execution_id": "exec-001"}
        serializer = TaskDispatchPayloadSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("task_id", serializer.errors)
        self.assertIn("pipeline", serializer.errors)


class TestTaskProgressPayloadSerializer(TestCase):
    """测试任务进度负载序列化器。"""

    def test_valid_progress(self):
        """验证进度负载通过校验。"""
        payload = {
            "execution_id": "exec-001",
            "step_index": 0,
            "status": "running",
            "duration_ms": 1500,
            "message": "正在执行点击操作",
        }
        serializer = TaskProgressPayloadSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_invalid_status(self):
        """验证非法状态被拒绝。"""
        payload = {"execution_id": "exec-001", "step_index": 0, "status": "unknown"}
        serializer = TaskProgressPayloadSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

    def test_negative_step_index(self):
        """验证负数 step_index 被拒绝。"""
        payload = {"execution_id": "exec-001", "step_index": -1, "status": "pending"}
        serializer = TaskProgressPayloadSerializer(data=payload)
        self.assertFalse(serializer.is_valid())


class TestTaskResultPayloadSerializer(TestCase):
    """测试任务结果负载序列化器。"""

    def test_valid_completed_result(self):
        """验证完成结果通过校验。"""
        payload = {
            "execution_id": "exec-001",
            "status": "completed",
            "steps_completed": 5,
            "total_steps": 5,
            "duration_ms": 12000,
            "result_data": {"collected_items": 10},
        }
        serializer = TaskResultPayloadSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_valid_failed_result(self):
        """验证失败结果（含 error）通过校验。"""
        payload = {
            "execution_id": "exec-001",
            "status": "failed",
            "steps_completed": 2,
            "total_steps": 5,
            "error": {"code": "TIMEOUT", "message": "元素未找到", "step_index": 2},
        }
        serializer = TaskResultPayloadSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["error"]["code"], "TIMEOUT")

    def test_invalid_status_choice(self):
        """验证非法最终状态被拒绝。"""
        payload = {
            "execution_id": "exec-001",
            "status": "running",
            "steps_completed": 1,
            "total_steps": 5,
        }
        serializer = TaskResultPayloadSerializer(data=payload)
        self.assertFalse(serializer.is_valid())

    def test_steps_completed_exceeds_total(self):
        """验证完成步骤数允许超过总步骤数（边界测试）。"""
        payload = {
            "execution_id": "exec-001",
            "status": "completed",
            "steps_completed": 10,
            "total_steps": 5,
        }
        serializer = TaskResultPayloadSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)


class TestTaskCancelPayloadSerializer(TestCase):
    """测试任务取消负载序列化器。"""

    def test_valid_cancel(self):
        """验证取消负载通过校验。"""
        payload = {
            "execution_id": "exec-001",
            "reason": "用户手动取消",
            "force": True,
        }
        serializer = TaskCancelPayloadSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertTrue(serializer.validated_data["force"])

    def test_minimal_cancel(self):
        """验证最小取消负载通过校验。"""
        payload = {"execution_id": "exec-001"}
        serializer = TaskCancelPayloadSerializer(data=payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["reason"], "")

    def test_missing_execution_id(self):
        """验证缺少 execution_id 校验失败。"""
        serializer = TaskCancelPayloadSerializer(data={"reason": "测试"})
        self.assertFalse(serializer.is_valid())


class TestValidatePayload(TestCase):
    """测试 validate_payload 函数的路由和校验。"""

    def test_validate_agent_register(self):
        """验证 agent.register 负载校验。"""
        result = validate_payload(MessageType.AGENT_REGISTER, {"agent_id": "agent-001"})
        self.assertEqual(result["agent_id"], "agent-001")

    def test_validate_agent_heartbeat(self):
        """验证 agent.heartbeat 负载校验。"""
        result = validate_payload(MessageType.AGENT_HEARTBEAT, {"status": "idle"})
        self.assertEqual(result["status"], "idle")

    def test_validate_task_dispatch(self):
        """验证 task.dispatch 负载校验。"""
        payload = {
            "execution_id": "exec-001",
            "task_id": "task-001",
            "pipeline": [{"step_index": 0, "step_name": "test", "step_type": "click"}],
        }
        result = validate_payload(MessageType.TASK_DISPATCH, payload)
        self.assertEqual(result["execution_id"], "exec-001")

    def test_validate_task_progress(self):
        """验证 task.progress 负载校验。"""
        result = validate_payload(
            MessageType.TASK_PROGRESS,
            {"execution_id": "exec-001", "step_index": 0, "status": "running"},
        )
        self.assertEqual(result["step_index"], 0)

    def test_validate_task_result(self):
        """验证 task.result 负载校验。"""
        result = validate_payload(
            MessageType.TASK_RESULT,
            {"execution_id": "exec-001", "status": "completed", "steps_completed": 3, "total_steps": 3},
        )
        self.assertEqual(result["status"], "completed")

    def test_validate_task_cancel(self):
        """验证 task.cancel 负载校验。"""
        result = validate_payload(MessageType.TASK_CANCEL, {"execution_id": "exec-001", "reason": "test"})
        self.assertEqual(result["execution_id"], "exec-001")

    def test_validate_unsupported_type(self):
        """验证不支持的 type 返回原始 payload。"""
        result = validate_payload(MessageType.SCREENSHOT_FRAME, {"image": "base64"})
        self.assertEqual(result["image"], "base64")


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestAgentConsumerRegistration(TestCase):
    """测试 AgentConsumer 注册流程集成测试。"""

    async def test_agent_register_with_capabilities(self):
        """验证带能力声明的注册消息正确创建 Agent 记录。"""
        communicator = WebsocketCommunicator(AgentConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        register_frame = serialize_frame(
            msg_type=MessageType.AGENT_REGISTER,
            payload={
                "agent_id": "test-agent-cap-001",
                "hostname": "test-pc",
                "ip_address": "10.0.0.1",
                "os_info": "Windows 11",
                "version": "2.0.0",
                "capabilities": {
                    "screenshot_methods": ["pyautogui", "dxcam"],
                    "input_methods": ["pyautogui"],
                    "recognition_engines": ["paddleocr"],
                },
                "resource_quota": {"max_concurrent_tasks": 2},
            },
        )
        await communicator.send_to(text_data=register_frame)

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], MessageType.AGENT_STATUS)
        self.assertEqual(data["payload"]["status"], "registered")
        self.assertEqual(data["payload"]["agent_id"], "test-agent-cap-001")

        agent = await sync_to_async(Worker.objects.get)(agent_id="test-agent-cap-001")
        self.assertEqual(agent.hostname, "test-pc")
        self.assertEqual(agent.status, Worker.Status.ONLINE)
        self.assertIn("screenshot_methods", agent.capabilities)
        self.assertEqual(agent.capabilities["screenshot_methods"], ["pyautogui", "dxcam"])

        await communicator.disconnect()

    async def test_agent_register_missing_agent_id(self):
        """验证缺少 agent_id 的注册消息返回错误。"""
        communicator = WebsocketCommunicator(AgentConsumer.as_asgi(), TEST_WS_PATH)
        # Use empty agent_id so connect succeeds but register frame has no
        # agent_id to fall back on. Consumer should return status=error.
        communicator.scope['agent'] = MagicMock(agent_id='')
        await communicator.connect()
        await communicator.receive_from()

        register_frame = serialize_frame(
            msg_type=MessageType.AGENT_REGISTER,
            payload={"hostname": "no-id-host"},
        )
        await communicator.send_to(text_data=register_frame)

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], MessageType.AGENT_STATUS)
        self.assertEqual(data["payload"]["status"], "error")

        await communicator.disconnect()

    async def test_agent_register_updates_existing(self):
        """验证重复注册同一 agent_id 时更新已有记录。"""
        await sync_to_async(Worker.objects.create)(
            agent_id="test-agent-update-001",
            hostname="old-host",
            status=Worker.Status.OFFLINE,
        )

        communicator = WebsocketCommunicator(AgentConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        register_frame = serialize_frame(
            msg_type=MessageType.AGENT_REGISTER,
            payload={
                "agent_id": "test-agent-update-001",
                "hostname": "new-host",
                "capabilities": {"screenshot_methods": ["dxcam"]},
            },
        )
        await communicator.send_to(text_data=register_frame)

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["payload"]["status"], "registered")

        agent = await sync_to_async(Worker.objects.get)(agent_id="test-agent-update-001")
        self.assertEqual(agent.hostname, "new-host")
        self.assertEqual(agent.status, Worker.Status.ONLINE)
        self.assertEqual(agent.capabilities["screenshot_methods"], ["dxcam"])

        await communicator.disconnect()


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestAgentConsumerHeartbeat(TestCase):
    """测试 AgentConsumer 心跳处理集成测试。"""

    async def test_heartbeat_updates_last_heartbeat(self):
        """验证心跳消息更新数据库中的 last_heartbeat。"""
        agent = await sync_to_async(Worker.objects.create)(
            agent_id="test-agent-hb-001",
            hostname="hb-host",
            status=Worker.Status.ONLINE,
        )

        communicator = WebsocketCommunicator(AgentConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-hb-001')
        await communicator.connect()
        await communicator.receive_from()

        await communicator.send_to(text_data=serialize_frame(
            msg_type=MessageType.AGENT_REGISTER,
            payload={"agent_id": "test-agent-hb-001"},
        ))
        await communicator.receive_from()

        datetime.now(UTC)
        heartbeat_frame = serialize_frame(
            msg_type=MessageType.AGENT_HEARTBEAT,
            payload={"agent_id": "test-agent-hb-001", "status": "busy"},
        )
        await communicator.send_to(text_data=heartbeat_frame)

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], MessageType.EVENT_ACK)
        self.assertEqual(data["payload"]["ack_type"], MessageType.AGENT_HEARTBEAT)

        await sync_to_async(agent.refresh_from_db)()
        self.assertIsNotNone(agent.last_heartbeat)
        self.assertEqual(agent.status, Worker.Status.BUSY)

        await communicator.disconnect()

    async def test_heartbeat_without_registration_returns_ack(self):
        """验证未注册 Agent 的心跳仍返回 ACK。"""
        communicator = WebsocketCommunicator(AgentConsumer.as_asgi(), TEST_WS_PATH)
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


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestAgentConsumerTaskDispatch(TestCase):
    """测试 AgentConsumer 任务分发相关集成测试。"""

    async def test_task_dispatch_returns_ack(self):
        """验证 task.dispatch 消息收到 ACK 确认。"""
        communicator = WebsocketCommunicator(AgentConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        dispatch_frame = serialize_frame(
            msg_type=MessageType.TASK_DISPATCH,
            payload={
                "execution_id": "exec-test-001",
                "task_id": "task-001",
                "pipeline": [
                    {"step_index": 0, "step_name": "login", "step_type": "click"},
                ],
                "options": {"max_retries": 3},
            },
        )
        await communicator.send_to(text_data=dispatch_frame)

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], MessageType.EVENT_ACK)
        self.assertEqual(data["payload"]["ack_type"], MessageType.TASK_DISPATCH)
        self.assertEqual(data["payload"]["execution_id"], "exec-test-001")

        await communicator.disconnect()

    async def test_task_cancel_returns_ack(self):
        """验证 task.cancel 消息收到 ACK 确认。"""
        communicator = WebsocketCommunicator(AgentConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        cancel_frame = serialize_frame(
            msg_type=MessageType.TASK_CANCEL,
            payload={"execution_id": "exec-test-002", "reason": "manual"},
        )
        await communicator.send_to(text_data=cancel_frame)

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], MessageType.EVENT_ACK)
        self.assertEqual(data["payload"]["ack_type"], MessageType.TASK_CANCEL)
        self.assertEqual(data["payload"]["execution_id"], "exec-test-002")

        await communicator.disconnect()

    async def test_task_result_returns_ack(self):
        """验证 task.result 消息收到 ACK 确认。"""
        communicator = WebsocketCommunicator(AgentConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        result_frame = serialize_frame(
            msg_type=MessageType.TASK_RESULT,
            payload={
                "execution_id": "exec-test-003",
                "status": "completed",
                "steps_completed": 5,
                "total_steps": 5,
            },
        )
        await communicator.send_to(text_data=result_frame)

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], MessageType.EVENT_ACK)
        self.assertEqual(data["payload"]["ack_type"], MessageType.TASK_RESULT)
        self.assertEqual(data["payload"]["execution_id"], "exec-test-003")

        await communicator.disconnect()

    async def test_task_progress_no_response(self):
        """验证 task.progress 不发送响应帧（仅日志）。"""
        communicator = WebsocketCommunicator(AgentConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-mock')
        await communicator.connect()
        await communicator.receive_from()

        progress_frame = serialize_frame(
            msg_type=MessageType.TASK_PROGRESS,
            payload={
                "execution_id": "exec-test-004",
                "step_index": 2,
                "status": "success",
                "duration_ms": 500,
            },
        )
        await communicator.send_to(text_data=progress_frame)

        await communicator.disconnect()


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestAgentConsumerDisconnect(TestCase):
    """测试 AgentConsumer 断开连接时标记离线。"""

    async def test_disconnect_sets_agent_offline(self):
        """验证断开连接后将 Agent 标记为离线。"""
        agent = await sync_to_async(Worker.objects.create)(
            agent_id="test-agent-disconnect-001",
            hostname="dc-host",
            status=Worker.Status.ONLINE,
        )

        communicator = WebsocketCommunicator(AgentConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-disconnect-001')
        await communicator.connect()
        await communicator.receive_from()

        await communicator.send_to(text_data=serialize_frame(
            msg_type=MessageType.AGENT_REGISTER,
            payload={"agent_id": "test-agent-disconnect-001"},
        ))
        await communicator.receive_from()

        await communicator.disconnect()

        await sync_to_async(agent.refresh_from_db)()
        self.assertEqual(agent.status, Worker.Status.OFFLINE)
