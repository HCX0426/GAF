"""TD-425 邻域: DB ScheduledTask 与 APScheduler 同步 (2026-09-05).

根因: ``_register_db_scheduled_tasks`` 只在启动时执行一次; 前端禁用/删除
ScheduledTask 后 APScheduler 已注册 job 仍触发 (实测 exec 460-475 一连串
dev=None 失败). ``sync_db_scheduled_tasks`` beat 幂等 reconcile:
- DB 禁用 → 移除对应 APScheduler job
- DB 启用 → 注册 job
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from tasks.factories import TaskFactory
from tasks.models import ScheduledTask


def _make_scheduled_task(enabled=True):
    task = TaskFactory.create()
    return ScheduledTask.objects.create(
        task=task,
        is_enabled=enabled,
        schedule_type=ScheduledTask.ScheduleType.PERIODIC,
        cron_expression="0 * * * *",
    )


class TestSyncDbScheduledTasks(TestCase):
    """sync_db_scheduled_tasks: DB 状态 → APScheduler job 集合对齐."""

    def _run_sync(self, existing_job_ids, scheduler=None):
        from config.scheduler import sync_db_scheduled_tasks

        mock_scheduler = scheduler or MagicMock()
        mock_scheduler.get_jobs.return_value = [
            MagicMock(id=jid) for jid in existing_job_ids
        ]
        with patch("config.scheduler._scheduler", mock_scheduler):
            sync_db_scheduled_tasks()
        return mock_scheduler

    def test_disabled_task_job_removed(self):
        st = _make_scheduled_task(enabled=False)  # DB 禁用
        job_id = f"scheduled_task_{st.id}"
        scheduler = self._run_sync([job_id])
        scheduler.remove_job.assert_called_once_with(job_id)

    def test_enabled_task_job_registered(self):
        _make_scheduled_task(enabled=True)  # DB 启用
        scheduler = self._run_sync([])  # APScheduler 无此 job
        scheduler.add_job.assert_called()

    def test_unrelated_jobs_untouched(self):
        scheduler = self._run_sync(["check-stuck-chains", "sync-db-scheduled-tasks"])
        scheduler.remove_job.assert_not_called()

    def test_scheduler_none_noop(self):
        _make_scheduled_task(enabled=False)
        with patch("config.scheduler._scheduler", None):
            from config.scheduler import sync_db_scheduled_tasks

            sync_db_scheduled_tasks()  # 不应抛异常 (非 eager 模式无 scheduler)
