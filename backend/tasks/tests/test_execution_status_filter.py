"""N218: TaskExecutionViewSet status 过滤回归测试.

背景: TaskExecutionViewSet 缺 filter_backends → ``?status=running`` 被静默忽略,
工作台"运行任务"恒显示全表 count (91), 即使没有任务在跑. 本测试固化修复.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from tasks.models import TaskExecution


class TestExecutionStatusFilter(TestCase):
    """list 接口 status 过滤生效."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="exec_filter_admin",
            password="admin123456",
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.admin)
        TaskExecution.objects.create(
            task=None, status=TaskExecution.Status.RUNNING,
        )
        TaskExecution.objects.create(
            task=None, status=TaskExecution.Status.FAILED,
        )
        TaskExecution.objects.create(
            task=None, status=TaskExecution.Status.SUCCESS,
        )

    def test_status_filter_returns_subset(self):
        """status=running 只返回 running, 不返回全表."""
        res = self.client.get("/api/v2/tasks/task-executions/", {"status": "running", "page_size": 100})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        payload = res.data.get("data", res.data) if isinstance(res.data, dict) else res.data
        count = payload.get("count", 0)
        self.assertEqual(count, 1)

    def test_failed_filter_count(self):
        """status=failed 返回失败数."""
        res = self.client.get("/api/v2/tasks/task-executions/", {"status": "failed", "page_size": 100})
        payload = res.data.get("data", res.data) if isinstance(res.data, dict) else res.data
        self.assertEqual(payload.get("count", 0), 1)

    def test_no_filter_returns_all(self):
        """无 status 参数返回全部记录."""
        res = self.client.get("/api/v2/tasks/task-executions/", {"page_size": 100})
        payload = res.data.get("data", res.data) if isinstance(res.data, dict) else res.data
        self.assertEqual(payload.get("count", 0), 3)
