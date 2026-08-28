"""TD-351: TaskExecution 归档策略测试。

测试归档任务 (archive_old_executions) 和 API 默认过滤行为。
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.factories import AdminUserFactory
from tasks.models import TaskExecution
from tasks.tasks import archive_old_executions


def _make_execution(status, completed_at=None, is_archived=False, log="test log"):
    """Helper to create a TaskExecution with minimal required fields."""
    return TaskExecution.objects.create(
        status=status,
        completed_at=completed_at,
        is_archived=is_archived,
        log=log,
    )


class TestArchiveTask(TestCase):
    """归档任务逻辑测试 (archive_old_executions)."""

    def setUp(self):
        self.now = timezone.now()

    def test_archives_old_completed(self):
        """30 天前的 SUCCESS 记录被归档。"""
        _make_execution(
            status=TaskExecution.Status.SUCCESS,
            completed_at=self.now - timedelta(days=31),
        )
        result = archive_old_executions()
        self.assertEqual(result["archived_count"], 1)
        self.assertEqual(result["cleared_log_count"], 1)
        record = TaskExecution.objects.first()
        self.assertTrue(record.is_archived)
        self.assertIsNotNone(record.archived_at)

    def test_archives_old_failed(self):
        """30 天前的 FAILED 记录被归档。"""
        _make_execution(
            status=TaskExecution.Status.FAILED,
            completed_at=self.now - timedelta(days=31),
        )
        result = archive_old_executions()
        self.assertEqual(result["archived_count"], 1)

    def test_skips_recent_completed(self):
        """1 天前的 SUCCESS 记录不被归档。"""
        _make_execution(
            status=TaskExecution.Status.SUCCESS,
            completed_at=self.now - timedelta(days=1),
        )
        result = archive_old_executions()
        self.assertEqual(result["archived_count"], 0)

    def test_skips_pending(self):
        """PENDING 记录不被归档。"""
        _make_execution(
            status=TaskExecution.Status.PENDING,
            completed_at=self.now - timedelta(days=31),
        )
        result = archive_old_executions()
        self.assertEqual(result["archived_count"], 0)

    def test_skips_running(self):
        """RUNNING 记录不被归档。"""
        _make_execution(
            status=TaskExecution.Status.RUNNING,
            completed_at=self.now - timedelta(days=31),
        )
        result = archive_old_executions()
        self.assertEqual(result["archived_count"], 0)

    def test_skips_cancelled_old(self):
        """30 天前的 CANCELLED 记录被归档。"""
        _make_execution(
            status=TaskExecution.Status.CANCELLED,
            completed_at=self.now - timedelta(days=31),
        )
        result = archive_old_executions()
        self.assertEqual(result["archived_count"], 1)

    def test_skips_force_terminated_old(self):
        """30 天前的 FORCE_TERMINATED 记录被归档。"""
        _make_execution(
            status=TaskExecution.Status.FORCE_TERMINATED,
            completed_at=self.now - timedelta(days=31),
        )
        result = archive_old_executions()
        self.assertEqual(result["archived_count"], 1)

    def test_idempotent(self):
        """第二次调用归档数为 0（幂等性）。"""
        _make_execution(
            status=TaskExecution.Status.SUCCESS,
            completed_at=self.now - timedelta(days=31),
        )
        # 第一次归档
        result1 = archive_old_executions()
        self.assertEqual(result1["archived_count"], 1)
        # 第二次归档 — 不应重复归档
        result2 = archive_old_executions()
        self.assertEqual(result2["archived_count"], 0)

    def test_clears_log(self):
        """归档后 log 字段被清空。"""
        _make_execution(
            status=TaskExecution.Status.SUCCESS,
            completed_at=self.now - timedelta(days=31),
            log="some long log text",
        )
        archive_old_executions()
        record = TaskExecution.objects.first()
        self.assertEqual(record.log, "")

    def test_skips_already_archived(self):
        """已归档的记录不被再次归档。"""
        _make_execution(
            status=TaskExecution.Status.SUCCESS,
            completed_at=self.now - timedelta(days=31),
            is_archived=True,
        )
        result = archive_old_executions()
        self.assertEqual(result["archived_count"], 0)

    def test_no_records(self):
        """空表时归档数为 0。"""
        result = archive_old_executions()
        self.assertEqual(result["archived_count"], 0)


class TestArchiveAPI(TestCase):
    """API 默认过滤行为测试。"""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.now = timezone.now()

        # 创建 1 条未归档记录 + 1 条归档记录
        self.active = _make_execution(
            status=TaskExecution.Status.SUCCESS,
            completed_at=self.now - timedelta(days=1),
        )
        self.archived = _make_execution(
            status=TaskExecution.Status.SUCCESS,
            completed_at=self.now - timedelta(days=31),
            is_archived=True,
        )

    def _get_results(self, response):
        """从 unified_response 信封中提取 results 列表。"""
        data = response.data.get("data", {})
        return data.get("results", [])

    def test_excludes_archived_by_default(self):
        """列表 API 默认不返回归档记录。"""
        response = self.client.get("/api/v2/tasks/task-executions/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # 检查返回的记录中不含归档记录
        results = self._get_results(response)
        ids = [r["id"] for r in results]
        self.assertIn(self.active.id, ids)
        self.assertNotIn(self.archived.id, ids)

    def test_include_archived(self):
        """?include_archived=true 返回全部记录。"""
        response = self.client.get(
            "/api/v2/tasks/task-executions/?include_archived=true"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self._get_results(response)
        ids = [r["id"] for r in results]
        self.assertIn(self.active.id, ids)
        self.assertIn(self.archived.id, ids)
