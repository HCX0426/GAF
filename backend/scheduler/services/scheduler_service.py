"""
SchedulerService — business logic for scheduler operations.

Phase 1 (2026-08-08): Extracted from ``scheduler/views.py`` to decouple
HTTP concerns (request/response serialization) from business rules.

Service methods raise standard Python exceptions on validation failures;
callers (views, Celery tasks, management commands) are responsible for
translating them into the appropriate HTTP or task response.
"""
import logging

from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError

from scheduler.engine import generate_execution_plan
from scheduler.models import TimeWindow

logger = logging.getLogger(__name__)


class SchedulerService:
    """Scheduler business logic — execution plan, today schedule, etc."""

    @staticmethod
    def get_execution_plan(days: int = 7) -> dict:
        """Generate execution plan for the next N days.

        Delegates to ``scheduler.engine.generate_execution_plan`` for the
        core algorithm, then enriches the result with counts.

        Args:
            days: Number of future days to plan (must be > 0).

        Returns:
            dict with ``days``, ``total_events``, ``device_count``,
            ``account_count``, and ``events`` keys.

        Raises:
            ValueError: If ``days`` is not a positive integer.
        """
        days = int(days)
        if days <= 0:
            raise ValueError("days must be a positive integer")

        plans = generate_execution_plan(days)

        device_ids = {p["device_id"] for p in plans if p.get("device_id")}
        account_ids = {p["account_id"] for p in plans if p.get("account_id")}

        return {
            "days": days,
            "total_events": len(plans),
            "device_count": len(device_ids),
            "account_count": len(account_ids),
            "events": plans,
        }

    @staticmethod
    def get_today_schedule() -> dict:
        """Derive today's unattended schedule from the execution plan engine.

        Notes (N219, 2026-08-29):
        - 今日日程 = **计划排期** (引擎按 Device+default_routine 推导
          "今天该跑哪些链"), 非实际执行记录. 计划项状态用 ``planned``
          (计划中) 而非 ``pending``, 避免与"已派发待执行"混淆 — 用户
          未启动无人值守时, 计划只是"排了期", 不是"在排队".

        Returns:
            dict with ``date``, ``total``, ``completed``, ``failed``,
            and ``items`` keys.
        """
        today = timezone.now().date()
        plans = generate_execution_plan(days=1)

        today_items = []
        for plan in plans:
            item = {
                "id": hash((plan.get("device_id"), plan.get("task_chain_id"))) % 1000000,
                "device_id": plan.get("device_id"),
                "device_name": plan.get("device_name", "未知设备"),
                "account_id": plan.get("account_id"),
                "account_name": plan.get("account_name") or "",
                "task_chain_id": plan.get("task_chain_id"),
                "task_chain_name": plan.get("task_chain_name", "未知任务链"),
                "scheduled_time": None,
                "actual_start_time": None,
                "actual_end_time": None,
                "status": "planned",
                "progress": 0,
                "error_message": None,
            }
            today_items.append(item)

        return {
            "date": today.isoformat(),
            "total": len(today_items),
            "completed": 0,
            "failed": 0,
            "items": today_items,
        }

    @staticmethod
    def list_executions(page: int = 1, page_size: int = 20) -> dict:
        """List scheduled task execution history (paginated).

        Maps ``TaskExecution`` rows to the ``ScheduledExecutionRecord``
        shape expected by the frontend, joining ``ScheduledTask`` via
        ``task.schedules`` to populate ``scheduled_task_id``.

        Args:
            page: 1-indexed page number.
            page_size: Items per page (max 100).

        Returns:
            dict with ``count``, ``page``, ``page_size``, and ``results`` keys.
        """
        from tasks.models import TaskExecution

        # Status mapping: TaskExecution.Status -> frontend ScheduledExecutionRecord.status
        status_map = {
            TaskExecution.Status.SUCCESS: "success",
            TaskExecution.Status.FAILED: "failed",
            TaskExecution.Status.RUNNING: "running",
            TaskExecution.Status.PENDING: "running",
            TaskExecution.Status.CANCELLED: "failed",
            TaskExecution.Status.FORCE_TERMINATED: "failed",
            TaskExecution.Status.PAUSED: "running",
        }

        page = max(int(page), 1)
        page_size = max(min(int(page_size), 100), 1)

        qs = (
            TaskExecution.objects
            .select_related("task")
            .prefetch_related("task__schedules")
            .order_by("-created_at")
        )
        total = qs.count()
        offset = (page - 1) * page_size
        items = qs[offset:offset + page_size]

        results = []
        for ex in items:
            scheduled_task_id = ""
            if ex.task_id:
                sched = ex.task.schedules.first() if hasattr(ex.task, "schedules") else None
                if sched is not None:
                    scheduled_task_id = str(sched.id)
            duration_seconds = None
            if ex.started_at and ex.completed_at:
                duration_seconds = (ex.completed_at - ex.started_at).total_seconds()
            results.append({
                "id": str(ex.id),
                "task_name": ex.task.name if ex.task else "",
                "scheduled_task_id": scheduled_task_id,
                "status": status_map.get(ex.status, "failed"),
                "started_at": ex.started_at.isoformat() if ex.started_at else ex.created_at.isoformat(),
                "finished_at": ex.completed_at.isoformat() if ex.completed_at else None,
                "duration_seconds": duration_seconds,
                "error_message": ex.error_message or None,
            })

        return {
            "count": total,
            "page": page,
            "page_size": page_size,
            "results": results,
        }

    @staticmethod
    def validate_time_window(data: dict, exclude_id: int = None) -> None:
        """Validate that a time window does not overlap with existing ones.

        Args:
            data: dict with ``start_time``, ``end_time``, and ``days_of_week``.
            exclude_id: When updating, exclude this window's ID from overlap checks.

        Raises:
            DRFValidationError: If the window overlaps with an existing window
                or if ``start_time >= end_time``.
        """
        new_start = data["start_time"]
        new_end = data["end_time"]
        new_days = data.get("days_of_week", [])

        if new_start >= new_end:
            raise DRFValidationError({"error": "结束时间必须晚于开始时间"})

        existing_windows = TimeWindow.objects.filter(is_enabled=True)
        if exclude_id:
            existing_windows = existing_windows.exclude(id=exclude_id)

        for window in existing_windows:
            existing_days = window.days_of_week if window.days_of_week else list(range(7))
            check_days = new_days if new_days else list(range(7))

            has_common_day = bool(set(existing_days) & set(check_days))
            if not has_common_day:
                continue

            if new_start < window.end_time and new_end > window.start_time:
                raise DRFValidationError({"error": "时间窗口与已有窗口重叠"})
