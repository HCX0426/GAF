"""数据库归档服务 — 定期清理和归档历史数据。

Task 3.2 (2026-08-08): 提供 ``ArchiveService``，对 ``TaskExecution``、
``MonitorEvent`` 等大表进行定期归档，避免数据膨胀导致性能下降。

归档策略：
- 超过 30 天的已完成/已取消执行记录 → 归档到 ``archived_task_executions`` 表。
- 超过 90 天的监控事件 → 删除 (日志级别事件无需长期保留)。
- 保留最近 7 天的 P0/P1 监控事件作为告警追溯。

Usage::

    from monitors.archival import ArchiveService

    # 手动运行归档
    stats = ArchiveService.run_archive()
    print(f"Archived {stats['task_executions_archived']} executions")

    # 注册为 Celery Beat 定时任务
    # celery_app.conf.beat_schedule = {
    #     "archive-old-data": {
    #         "task": "monitors.tasks.run_archive",
    #         "schedule": crontab(hour=3, minute=0),  # 每天凌晨 3 点
    #     },
    # }
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Default retention periods (days) ───────────────────────────────────

# Completed/cancelled TaskExecution records older than this are archived.
EXECUTION_RETENTION_DAYS = 30

# MonitorEvent records older than this are eligible for deletion.
MONITOR_EVENT_RETENTION_DAYS = 90

# Keep P0/P1 critical monitor events for at least this many days.
CRITICAL_EVENT_RETENTION_DAYS = 7


class ArchiveService:
    """数据库归档服务 — 清理历史 TaskExecution 和 MonitorEvent 数据。

    所有方法均为静态方法，可在 Celery 任务中直接调用。
    """

    @staticmethod
    def run_archive(
        execution_days: int = EXECUTION_RETENTION_DAYS,
        monitor_days: int = MONITOR_EVENT_RETENTION_DAYS,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """执行完整归档流程。

        Args:
            execution_days: TaskExecution 保留天数。
            monitor_days: MonitorEvent 保留天数。
            dry_run: 如果为 True，只统计不实际删除。

        Returns:
            包含各步骤统计信息的字典。
        """
        stats: dict[str, Any] = {
            "task_executions_archived": 0,
            "monitor_events_deleted": 0,
            "errors": [],
        }

        # 1. 归档旧 TaskExecution
        try:
            archived = ArchiveService.archive_task_executions(
                days=execution_days, dry_run=dry_run,
            )
            stats["task_executions_archived"] = archived
        except Exception as exc:
            logger.exception("Failed to archive TaskExecution records")
            stats["errors"].append(f"task_execution: {exc}")

        # 2. 清理旧 MonitorEvent
        try:
            deleted = ArchiveService.cleanup_monitor_events(
                days=monitor_days, dry_run=dry_run,
            )
            stats["monitor_events_deleted"] = deleted
        except Exception as exc:
            logger.exception("Failed to cleanup MonitorEvent records")
            stats["errors"].append(f"monitor_event: {exc}")

        if dry_run:
            logger.info(
                "[DRY RUN] Would archive %d execution(s) and delete %d event(s)",
                stats["task_executions_archived"],
                stats["monitor_events_deleted"],
            )
        else:
            logger.info(
                "Archive completed: %d execution(s) archived, %d event(s) deleted",
                stats["task_executions_archived"],
                stats["monitor_events_deleted"],
            )

        return stats

    @staticmethod
    def archive_task_executions(
        days: int = EXECUTION_RETENTION_DAYS,
        dry_run: bool = False,
    ) -> int:
        """归档超过指定天数的已完成/已取消 TaskExecution 记录。

        将记录序列化为 JSON 并写入 ``archived_task_executions`` 表，
        然后从原表删除。

        Args:
            days: 保留天数。超过此天数的已完成/已取消记录将被归档。
            dry_run: 如果为 True，只统计不实际删除。

        Returns:
            归档的记录数。
        """
        from tasks.models import TaskExecution

        cutoff = timezone.now() - timedelta(days=days)

        # 只归档终态记录 (completed / cancelled / failed)
        terminal_statuses = [
            TaskExecution.Status.COMPLETED,
            TaskExecution.Status.CANCELLED,
            TaskExecution.Status.FAILED,
        ]

        old_executions = TaskExecution.objects.filter(
            status__in=terminal_statuses,
            updated_at__lt=cutoff,
        )

        count = old_executions.count()
        if count == 0:
            logger.info("No TaskExecution records to archive (cutoff=%s)", cutoff.date())
            return 0

        if dry_run:
            logger.info(
                "[DRY RUN] Would archive %d TaskExecution records (cutoff=%s)",
                count, cutoff.date(),
            )
            return count

        # Archive to JSON file for now (simple approach).
        # In production, this could write to a separate archive DB or S3.
        _write_archive_file("task_executions", old_executions, cutoff)

        # Delete from primary table
        with transaction.atomic():
            deleted_count, _ = old_executions.delete()

        logger.info("Archived %d TaskExecution records (cutoff=%s)", deleted_count, cutoff.date())
        return deleted_count

    @staticmethod
    def cleanup_monitor_events(
        days: int = MONITOR_EVENT_RETENTION_DAYS,
        dry_run: bool = False,
    ) -> int:
        """清理超过指定天数的 MonitorEvent 记录。

        保留最近 ``CRITICAL_EVENT_RETENTION_DAYS`` 天的 P0/P1 事件。

        Args:
            days: 保留天数。
            dry_run: 如果为 True，只统计不实际删除。

        Returns:
            删除的记录数。
        """
        from monitors.models import MonitorEvent

        cutoff = timezone.now() - timedelta(days=days)
        critical_cutoff = timezone.now() - timedelta(days=CRITICAL_EVENT_RETENTION_DAYS)

        # 删除条件：超过 days 天，且不是 P0/P1 级别的关键事件
        old_events = MonitorEvent.objects.filter(
            created_at__lt=cutoff,
        ).exclude(
            severity__in=["P0", "P1"],
            created_at__gte=critical_cutoff,
        )

        count = old_events.count()
        if count == 0:
            logger.info("No MonitorEvent records to clean up (cutoff=%s)", cutoff.date())
            return 0

        if dry_run:
            logger.info(
                "[DRY RUN] Would delete %d MonitorEvent records (cutoff=%s)",
                count, cutoff.date(),
            )
            return count

        with transaction.atomic():
            deleted_count, _ = old_events.delete()

        logger.info("Cleaned up %d MonitorEvent records (cutoff=%s)", deleted_count, cutoff.date())
        return deleted_count


# ── Archive file helpers ───────────────────────────────────────────────

def _write_archive_file(
    name: str,
    queryset: Any,
    cutoff: Any,
) -> None:
    """将 queryset 序列化为 JSON 归档文件。

    Args:
        name: 归档名称 (用于文件名)。
        queryset: Django QuerySet 实例。
        cutoff: 截止日期 (用于文件名)。
    """
    import os

    from django.conf import settings

    archive_dir = getattr(settings, "ARCHIVE_DIR", None)
    if not archive_dir:
        archive_dir = os.path.join(settings.BASE_DIR, "..", "data", "archives")

    os.makedirs(archive_dir, exist_ok=True)

    filename = f"{name}_{cutoff.strftime('%Y%m%d')}.json"
    filepath = os.path.join(archive_dir, filename)

    records = list(queryset.values())
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2, default=str)

    logger.info("Wrote archive file: %s (%d records)", filepath, len(records))
