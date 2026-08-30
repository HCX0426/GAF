"""Task 1.1 (B7 重试单节点, P0-1): backend retry_from_step action TDD tests.

N192 视角 B 评估发现 B7 复现路径最弱 (4/10): 用户拿到错误后无法自行修复,
必须重新跑整个 pipeline。本测试覆盖新增的 backend retry_from_step action:

- POST /api/v2/tasks/task-executions/{id}/retry-from-step/
  Body: {"step_index": int}
  - 校验 execution 必须为 FAILED 状态 (retryable)
  - 校验 step_index 必须是已存在的失败步骤
  - 从原 execution 的已成功 ExecutionStep 构造 previous_results
  - 创建新 TaskExecution (PENDING)
  - 调用 dispatch_task 透传 start_step_index + previous_results
  - WS payload 包含 retry 字段, agent 跳过前 N 个节点

测试遵循 TDD (RED→GREEN→REFACTOR): 先全部失败 (action 不存在), 再实现.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from workers.models import Worker

from accounts.models import User
from tasks.models import ExecutionStep, Task, TaskExecution


class TestRetryFromStepAction(TestCase):
    """TaskExecutionViewSet.retry_from_step action tests.

    Verifies the full backend flow: validate → build previous_results →
    create new execution → dispatch with retry params.
    """

    def setUp(self):
        """Initialize: admin user, agent, failed task execution with steps."""
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='retry_test_admin',
            password='admin123456',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.admin)

        self.agent = Worker.objects.create(
            agent_id='retry-test-agent',
            hostname='retry-host',
            status=Worker.Status.IDLE,
            is_local=True,
            # Task 1.1: click 节点需要 windows 能力, 否则 dispatch_task
            # 选不到 agent → group_send 永远不会被调用 (test_dispatches_with_retry_params 失败).
            capabilities={"windows": True},
        )

        self.task = Task.objects.create(
            name='retry-test-task',
            description='Task for retry-from-step tests',
            execution_mode='pipeline',
            task_definition={
                'nodes': [
                    {'id': 'step_0', 'node_type': 'click', 'config': {'x': 0, 'y': 0}},
                    {'id': 'step_1', 'node_type': 'click', 'config': {'x': 10, 'y': 10}},
                    {'id': 'step_2', 'node_type': 'click', 'config': {'x': 20, 'y': 20}},
                    {'id': 'step_3', 'node_type': 'click', 'config': {'x': 30, 'y': 30}},
                ],
                'edges': [
                    {'from': 'step_0', 'to': 'step_1'},
                    {'from': 'step_1', 'to': 'step_2'},
                    {'from': 'step_2', 'to': 'step_3'},
                ],
            },
            is_enabled=True,
        )

        # Failed execution: 2 successful steps + 1 failed step (index=2) + 1 pending.
        self.failed_execution = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            triggered_by=self.admin,
            status=TaskExecution.Status.FAILED,
            error_message='节点 step_2 执行失败: 设备点击未响应',
        )
        # step_0 success
        ExecutionStep.objects.create(
            task_result=self.failed_execution,
            step_index=0,
            step_name='step_0',
            step_type='click',
            status=ExecutionStep.Status.SUCCESS,
            recognition_result={'x': 0, 'y': 0, 'success': True},
        )
        # step_1 success
        ExecutionStep.objects.create(
            task_result=self.failed_execution,
            step_index=1,
            step_name='step_1',
            step_type='click',
            status=ExecutionStep.Status.SUCCESS,
            recognition_result={'x': 10, 'y': 10, 'success': True},
        )
        # step_2 failed (this is what user wants to retry from)
        ExecutionStep.objects.create(
            task_result=self.failed_execution,
            step_index=2,
            step_name='step_2',
            step_type='click',
            status=ExecutionStep.Status.FAILED,
            recognition_result={'x': 20, 'y': 20},
            error_message='设备点击未响应',
        )

    @patch('tasks.tasks.get_channel_layer')
    def test_retry_from_step_creates_new_execution(self, mock_channel_layer):
        """POST retry-from-step/ should create a new PENDING TaskExecution.

        The new execution must be a separate row (not update the original)
        so the original failure record is preserved for audit/diagnosis.
        """
        # Mock channel layer so dispatch_task doesn't actually send WS.
        mock_channel = MagicMock()
        mock_channel.group_send = AsyncMock()
        mock_channel_layer.return_value = mock_channel
        # Reset concurrency controller to avoid state from prior tests.
        from tasks.concurrency_controller import get_default_controller
        get_default_controller().reset()

        initial_count = TaskExecution.objects.count()
        response = self.client.post(
            f'/api/v2/tasks/task-executions/{self.failed_execution.id}/retry-from-step/',
            {'step_index': 2},
            format='json',
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            f"Expected 201, got {response.status_code}: {response.data}",
        )
        # New execution row created
        self.assertEqual(TaskExecution.objects.count(), initial_count + 1)
        # N192 B1/B2: unified_response wraps payload as {code, message, data}.
        # new_execution_id lives inside data, not at top level.
        response_data = response.data.get('data') or {}
        new_exec_id = response_data.get('new_execution_id')
        self.assertIsNotNone(new_exec_id, "Response must include new execution id")
        new_exec = TaskExecution.objects.get(id=new_exec_id)
        # dispatch_task runs eagerly under CELERY_TASK_ALWAYS_EAGER, so it
        # may have already transitioned the execution PENDING → RUNNING (when
        # an agent is selected). Either state is acceptable; the key point is
        # that a new execution was created and is in an active (non-terminal) state.
        self.assertIn(
            new_exec.status,
            (TaskExecution.Status.PENDING, TaskExecution.Status.RUNNING),
            f"new execution should be PENDING or RUNNING, got {new_exec.status}",
        )
        # Original execution preserved
        self.failed_execution.refresh_from_db()
        self.assertEqual(self.failed_execution.status, TaskExecution.Status.FAILED)

    @patch('tasks.tasks.get_channel_layer')
    def test_retry_from_step_rejects_non_failed_execution(self, mock_channel_layer):
        """POST retry-from-step/ on a SUCCESS execution should return 400.

        Retry is only meaningful on a failed execution. Success/Pending/Running
        executions should be rejected with a clear user-readable error.
        """
        mock_channel = MagicMock()
        mock_channel.group_send = AsyncMock()
        mock_channel_layer.return_value = mock_channel

        success_exec = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            triggered_by=self.admin,
            status=TaskExecution.Status.SUCCESS,
        )
        response = self.client.post(
            f'/api/v2/tasks/task-executions/{success_exec.id}/retry-from-step/',
            {'step_index': 0},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # N192 B1: unified_response puts the user-readable message under
        # ``message`` (not ``error``). Check it explains the retry restriction.
        msg = response.data.get('message', '')
        self.assertTrue(
            msg and ('重试' in msg or 'retry' in msg.lower()),
            f"error message should explain retry restriction, got: {response.data}",
        )

    def test_retry_from_step_invalid_step_index(self):
        """POST retry-from-step/ with non-existent step_index should 404.

        step_index must correspond to an existing ExecutionStep in the execution.
        """
        response = self.client.post(
            f'/api/v2/tasks/task-executions/{self.failed_execution.id}/retry-from-step/',
            {'step_index': 999},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retry_from_step_missing_step_index(self):
        """POST retry-from-step/ without step_index should 400."""
        response = self.client.post(
            f'/api/v2/tasks/task-executions/{self.failed_execution.id}/retry-from-step/',
            {},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retry_from_step_step_must_be_failed(self):
        """Retry from a SUCCESS step should be rejected.

        User should only retry from a FAILED step — retrying from a
        success step would skip actual work that hasn't run yet.
        """
        response = self.client.post(
            f'/api/v2/tasks/task-executions/{self.failed_execution.id}/retry-from-step/',
            {'step_index': 0},  # step_0 is SUCCESS, not FAILED
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # N192 B1: unified_response puts the user-readable message under ``message``.
        msg = response.data.get('message', '')
        self.assertTrue(
            msg and ('失败' in msg or 'fail' in msg.lower()),
            f"error message should explain only-failed-step restriction, got: {response.data}",
        )

    @patch('tasks.tasks.get_channel_layer')
    def test_retry_from_step_dispatches_with_retry_params(self, mock_channel_layer):
        """dispatch_task must forward start_step_index + previous_results to agent.

        Verifies the WS payload sent to the agent includes:
        - start_step_index = 2 (the failed step's index)
        - previous_results = list of 2 dicts (step_0 + step_1 results)
        """
        mock_channel = MagicMock()
        mock_channel.group_send = AsyncMock()
        mock_channel_layer.return_value = mock_channel
        from tasks.concurrency_controller import get_default_controller
        get_default_controller().reset()

        response = self.client.post(
            f'/api/v2/tasks/task-executions/{self.failed_execution.id}/retry-from-step/',
            {'step_index': 2},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        # Inspect WS payload sent to agent.
        calls = mock_channel.group_send.call_args_list
        self.assertGreater(len(calls), 0, "group_send should be called after dispatch")
        sent_data = calls[0][0][1]
        payload = sent_data.get('payload', sent_data)

        # start_step_index forwarded
        self.assertIn('start_step_index', payload,
                      "WS payload must include start_step_index for agent")
        self.assertEqual(payload['start_step_index'], 2,
                         f"expected start_step_index=2, got {payload.get('start_step_index')}")

        # previous_results forwarded as list of dicts
        self.assertIn('previous_results', payload,
                      "WS payload must include previous_results for agent")
        prev = payload['previous_results']
        self.assertIsInstance(prev, list)
        self.assertEqual(len(prev), 2,
                        f"expected 2 previous_results (step_0 + step_1), got {len(prev)}")
        # Each entry should include node_id from the original ExecutionStep
        node_ids = [p.get('node_id') for p in prev]
        self.assertIn('step_0', node_ids)
        self.assertIn('step_1', node_ids)
        # Each entry should be success=True (only success steps are pre-baked)
        for entry in prev:
            self.assertTrue(entry.get('success'),
                            f"previous_results entries must be success=True, got {entry}")

    @patch('tasks.tasks.get_channel_layer')
    def test_retry_from_step_with_no_successful_predecessors(self, mock_channel_layer):
        """Retry from step_index=0 (no predecessors) should still work.

        previous_results should be an empty list [] when step_index=0
        (no successful predecessors to carry over).
        """
        mock_channel = MagicMock()
        mock_channel.group_send = AsyncMock()
        mock_channel_layer.return_value = mock_channel
        from tasks.concurrency_controller import get_default_controller
        get_default_controller().reset()

        # Make step_0 also failed (so retry from 0 is valid)
        ExecutionStep.objects.filter(
            task_result=self.failed_execution, step_index=0
        ).update(status=ExecutionStep.Status.FAILED)

        response = self.client.post(
            f'/api/v2/tasks/task-executions/{self.failed_execution.id}/retry-from-step/',
            {'step_index': 0},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        calls = mock_channel.group_send.call_args_list
        sent_data = calls[0][0][1]
        payload = sent_data.get('payload', sent_data)
        self.assertEqual(payload['start_step_index'], 0)
        self.assertEqual(payload['previous_results'], [],
                         "previous_results should be empty list when step_index=0")

    def test_retry_from_step_unauthenticated(self):
        """Unauthenticated request should return 401."""
        unauth_client = APIClient()
        response = unauth_client.post(
            f'/api/v2/tasks/task-executions/{self.failed_execution.id}/retry-from-step/',
            {'step_index': 2},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
