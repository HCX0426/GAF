"""TaskExecutionViewSet.node_trace action tests.

Tests the current node_trace implementation which reads from the ExecutionStep
table (not JSONL files):

- GET /api/v2/tasks/task-executions/{pk}/node-trace/?step_index=N
- 从 ExecutionStep 表读取数据
- 返回字段: execution_id, step_index, step_name, status, result_data,
  screenshot_path, error_message, started_at, duration_ms, retry_count

测试用例:
    1. test_node_trace_returns_step_data — 创建 TaskExecution + ExecutionStep,
       请求 step_index=0，验证 200 和返回字段
    2. test_node_trace_invalid_step_index — 请求不存在的 step_index,
       验证 404
    3. test_node_trace_bad_step_index — 请求非数字 step_index, 验证 400
    4. test_node_trace_unauthorized — 未认证用户, 验证 401
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from workers.models import Worker

from accounts.models import User
from tasks.models import ExecutionStep, Task, TaskExecution


class TestNodeTraceAction(TestCase):
    """TaskExecutionViewSet.node_trace action tests.

    Verifies reading ExecutionStep by step_index and returning structured
    payload for the frontend NodeDetailDrawer.
    """

    def setUp(self):
        """Initialize: admin user, agent, task, execution, and ExecutionStep."""
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='node_trace_admin',
            password='admin123456',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.admin)

        self.agent = Worker.objects.create(
            agent_id='node-trace-test-agent',
            hostname='trace-host',
            status=Worker.Status.IDLE,
            is_local=True,
            capabilities={"windows": True},
        )

        self.task = Task.objects.create(
            name='node-trace-test-task',
            description='Task for node-trace tests',
            execution_mode='pipeline',
            task_definition={
                'nodes': [
                    {'id': 'match_1', 'node_type': 'template_match',
                     'config': {'template': 'tpl_1.png', 'threshold': 0.8,
                                'roi': [0, 0, 100, 100]}},
                    {'id': 'click_1', 'node_type': 'click',
                     'config': {'x': 100, 'y': 200}},
                ],
                'edges': [{'from': 'match_1', 'to': 'click_1'}],
            },
            is_enabled=True,
        )

        self.task_result = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            triggered_by=self.admin,
            status=TaskExecution.Status.FAILED,
            error_message='节点 click_1 执行失败: 设备点击未响应',
        )

        self.step_0 = ExecutionStep.objects.create(
            task_result=self.task_result,
            step_index=0,
            step_name='匹配登录按钮',
            step_type='template_match',
            status=ExecutionStep.Status.SUCCESS,
            recognition_result={
                'confidence': 0.92,
                'match_location': {'x': 50, 'y': 60},
                'coord_system': 'logical',
            },
            screenshot_path='debug/match_1.png',
            retry_count=0,
            duration=0.12,
            started_at=timezone.now() - timedelta(minutes=5),
        )

        self.step_1 = ExecutionStep.objects.create(
            task_result=self.task_result,
            step_index=1,
            step_name='点击登录按钮',
            step_type='click',
            status=ExecutionStep.Status.FAILED,
            recognition_result={'attempted': True},
            error_message='设备点击未响应 (timeout=5s)',
            screenshot_path='debug/click_1_failed.png',
            retry_count=2,
            duration=5.0,
            started_at=timezone.now() - timedelta(minutes=4),
        )

    def _get_url(self, execution_id: int, step_index) -> str:
        """Build the node-trace URL with step_index query parameter."""
        return (
            f'/api/v2/tasks/task-executions/{execution_id}/node-trace/'
            f'?step_index={step_index}'
        )

    def test_node_trace_returns_step_data(self):
        """GET node-trace/?step_index=0 应返回 ExecutionStep 数据.

        UnifiedResponseMiddleware 把成功响应包装为
        {code: 0, message: "ok", data: payload}, 实际字段在 data 子字段里.
        """
        response = self.client.get(self._get_url(self.task_result.id, 0))
        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            f"Expected 200, got {response.status_code}: {response.data}",
        )

        # UnifiedResponseMiddleware 包装: 实际 payload 在 data 中
        data = response.data.get("data") or {}

        # 基本信息
        self.assertEqual(data["execution_id"], str(self.task_result.id))
        self.assertEqual(data["step_index"], 0)
        self.assertEqual(data["step_name"], "匹配登录按钮")
        self.assertEqual(data["status"], ExecutionStep.Status.SUCCESS)

        # result_data
        self.assertEqual(data["result_data"]["confidence"], 0.92)
        self.assertEqual(
            data["result_data"]["match_location"], {"x": 50, "y": 60},
        )

        # screenshot_path
        self.assertEqual(data["screenshot_path"], "debug/match_1.png")

        # error_message (成功节点无错误信息)
        self.assertIsNone(data["error_message"])

        # started_at
        self.assertIsNotNone(data["started_at"])

        # duration_ms
        self.assertEqual(data["duration_ms"], 120)

        # retry_count
        self.assertEqual(data["retry_count"], 0)

    def test_node_trace_returns_failed_step_data(self):
        """GET node-trace/?step_index=1 应返回失败节点的错误信息.

        验证失败节点的 error_message / duration_ms / retry_count 正确.
        """
        response = self.client.get(self._get_url(self.task_result.id, 1))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get("data") or {}

        self.assertEqual(data["step_index"], 1)
        self.assertEqual(data["step_name"], "点击登录按钮")
        self.assertEqual(data["status"], ExecutionStep.Status.FAILED)

        # 失败节点特有字段
        self.assertEqual(
            data["error_message"], "设备点击未响应 (timeout=5s)",
        )
        self.assertEqual(data["retry_count"], 2)
        self.assertEqual(data["duration_ms"], 5000)

        # result_data 透传
        self.assertEqual(data["result_data"]["attempted"], True)

        # screenshot_path
        self.assertEqual(
            data["screenshot_path"], "debug/click_1_failed.png",
        )

    def test_node_trace_invalid_step_index(self):
        """请求不存在的 step_index → 404 + friendly message."""
        response = self.client.get(self._get_url(self.task_result.id, 99))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # UnifiedResponseMiddleware 把 4xx 包装为 {code, message, data: None}
        message = response.data.get("message", "")
        self.assertIn("未找到索引为 99 的步骤", message)

    def test_node_trace_bad_step_index(self):
        """请求非数字 step_index → 400 + friendly message."""
        response = self.client.get(
            self._get_url(self.task_result.id, "abc"),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        message = response.data.get("message", "")
        self.assertIn("step_index 必须为整数", message)

    def test_node_trace_unauthorized(self):
        """未认证用户 → 401."""
        self.client.logout()
        response = self.client.get(self._get_url(self.task_result.id, 0))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
