"""
APScheduler-based scheduler for eager mode (replaces Celery Worker + Beat).

In eager mode (GAF_CELERY_MODE=eager):
  - Celery tasks run synchronously (CELERY_TASK_ALWAYS_EAGER=True)
  - APScheduler runs in a background thread inside the daphne process
  - No need for separate Celery Worker + Beat processes (~26s faster startup)

In celery mode (GAF_CELERY_MODE=celery):
  - This module is a no-op when start_scheduler() detects non-eager mode
  - Worker + Beat run as separate processes as before

Design: reads the same beat_schedule from config.celery, so schedule changes
in celery.py automatically apply to the APScheduler — no drift.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _celery_crontab_to_apscheduler(celery_crontab) -> CronTrigger:
    """Convert a celery.schedules.crontab to an APScheduler CronTrigger.

    Celery crontab stores values as sets of ints. This helper extracts
    single values (common case) or joins ranges for APScheduler's
    cron-style string syntax.

    Important: Celery uses 0=Sunday for day_of_week, while APScheduler
    (and standard cron) uses 0=Sunday as well — they are compatible.
    """
    kwargs = {}

    # minute: set of ints, e.g. {0} or {0, 30}
    minute = celery_crontab.minute
    if minute and minute != {'*'}:
        kwargs['minute'] = ','.join(str(v) for v in sorted(minute))
    else:
        kwargs['minute'] = '*'

    # hour: set of ints
    hour = celery_crontab.hour
    if hour and hour != {'*'}:
        kwargs['hour'] = ','.join(str(v) for v in sorted(hour))
    else:
        kwargs['hour'] = '*'

    # day_of_week: 0=Sunday (compatible between Celery and APScheduler/cron)
    dow = celery_crontab.day_of_week
    if dow and dow != {'*'}:
        kwargs['day_of_week'] = ','.join(str(v) for v in sorted(dow))
    else:
        kwargs['day_of_week'] = '*'

    # day_of_month: set of ints
    dom = celery_crontab.day_of_month
    if dom and dom != {'*'}:
        kwargs['day'] = ','.join(str(v) for v in sorted(dom))
    else:
        kwargs['day'] = '*'

    # month_of_year: set of ints
    month = celery_crontab.month_of_year
    if month and month != {'*'}:
        kwargs['month'] = ','.join(str(v) for v in sorted(month))
    else:
        kwargs['month'] = '*'

    return CronTrigger(**kwargs)


def _build_trigger(schedule):
    """Convert a Celery schedule value (int/float/crontab) to APScheduler trigger."""
    from celery.schedules import crontab as _celery_crontab

    if isinstance(schedule, (int, float)):
        return IntervalTrigger(seconds=int(schedule))
    if isinstance(schedule, _celery_crontab):
        return _celery_crontab_to_apscheduler(schedule)
    raise TypeError(f"Unsupported schedule type: {type(schedule)}")


def _import_task(task_path: str):
    """Import a Celery task function by its dotted path.

    Uses Django's import_string which handles both regular functions
    and Celery @shared_task decorated functions. For bind=True tasks,
    wraps the call to pass self=None since we're not going through Celery.
    """
    from django.utils.module_loading import import_string

    func = import_string(task_path)
    # Check if it's a Celery Task (bind=True) — needs self=None
    if hasattr(func, '__wrapped__') or (hasattr(func, 'run') and hasattr(func, 'delay')):
        # It's a Celery task object; use .run() to get the underlying function
        return func.run
    return func


def _job_wrapper(task_path: str):
    """Wrap a Celery task call with error handling (avoid crashing scheduler)."""
    try:
        # Import the task function directly (bypass Celery task name resolution)
        # With CELERY_TASK_ALWAYS_EAGER=True, calling the function directly
        # is equivalent to task.delay() — synchronous execution.
        func = _import_task(task_path)
        # For bind=True tasks, the Celery Task.run() expects self as first arg.
        # We pass None since we're not going through the Celery worker.
        import inspect

        sig = inspect.signature(func)
        if 'self' in sig.parameters:
            func(None)
        else:
            func()
    except Exception:
        logger.exception("APScheduler job failed: %s", task_path)


def _scheduled_task_job(scheduled_task_id):
    """Run a DB ScheduledTask via APScheduler (eager mode replaces Celery Beat)."""
    try:
        from tasks.tasks import execute_scheduled_task

        execute_scheduled_task(scheduled_task_id)
    except Exception:
        logger.exception("APScheduler ScheduledTask job failed: %s", scheduled_task_id)


def _register_db_scheduled_tasks(scheduler: BackgroundScheduler) -> int:
    """Register DB ScheduledTask records as APScheduler jobs.

    In eager mode APScheduler replaces Celery Beat, but only the static
    beat_schedule was wired — DB ScheduledTask (registered via
    django_celery_beat PeriodicTask in celery mode) were never triggered.
    Here we register them directly so cron/one-time schedules fire in eager
    mode too (N###: eager APScheduler missing DB ScheduledTask).
    """
    try:
        from tasks.models import ScheduledTask
    except Exception:
        logger.warning("读取 ScheduledTask 失败，跳过数据库定时任务注册")
        return 0

    registered = 0
    try:
        # 启动时若表未就绪（迁移前）容忍一次
        tasks = list(ScheduledTask.objects.filter(is_enabled=True))
    except Exception as exc:
        logger.warning("查询 ScheduledTask 失败: %s", exc)
        return 0

    for st in tasks:
        job_id = f"scheduled_task_{st.id}"
        try:
            if st.schedule_type == ScheduledTask.ScheduleType.ONE_TIME and st.scheduled_time:
                from apscheduler.triggers.date import DateTrigger

                trigger = DateTrigger(run_date=st.scheduled_time)
            elif st.schedule_type == ScheduledTask.ScheduleType.PERIODIC and st.cron_expression:
                parts = st.cron_expression.strip().split()
                if len(parts) != 5:
                    logger.error("无效 cron 表达式（需要5段）: %s", st.cron_expression)
                    continue
                minute, hour, dom, month, dow = parts
                # APScheduler day_of_week: 0=Monday..6=Sunday; 标准 cron: 0=Sunday.
                # 映射 cron dow -> APScheduler (sun=6, mon=0, ... sat=5).
                dow_map = {"0": "sun", "1": "mon", "2": "tue", "3": "wed", "4": "thu", "5": "fri", "6": "sat"}
                if dow != "*":
                    dow = ",".join(dow_map.get(p.strip(), p.strip()) for p in dow.split(","))
                trigger = CronTrigger(minute=minute, hour=hour, day=dom, month=month, day_of_week=dow)
            else:
                continue
            scheduler.add_job(
                _scheduled_task_job,
                trigger=trigger,
                args=[st.id],
                id=job_id,
                name=job_id,
                replace_existing=True,
                misfire_grace_time=60,
            )
            registered += 1
            logger.info("APScheduler registered DB ScheduledTask: %s (cron=%s)", job_id, st.cron_expression)
        except Exception as exc:
            logger.warning("注册 ScheduledTask %s 失败: %s", st.id, exc)
    return registered


def sync_db_scheduled_tasks() -> None:
    """将 DB ScheduledTask 的启用/禁用/删除同步到 APScheduler (60s beat).

    背景: ``_register_db_scheduled_tasks`` 只在 ``start_scheduler`` 时执行一次。
    前端禁用/删除 ScheduledTask 后, APScheduler 已注册的 job 仍会持续触发
    (实测 2026-09-05: DB 禁用 scheduled_task_1 后, APScheduler 继续每分钟
    触发 task 20 直到服务重启, 产生 exec 460-475 一连串 dev=None 失败)。

    实现 (幂等 reconcile, 注册为 config.celery ``sync-db-scheduled-tasks``):
    - 移除 APScheduler 中 DB 已禁用/删除的 ``scheduled_task_*`` job
    - 重新注册 DB enabled 任务 (``replace_existing`` 幂等, 顺带覆盖 cron 变更)
    """
    global _scheduler
    if _scheduler is None:
        return
    from tasks.models import ScheduledTask

    try:
        enabled_job_ids = {
            f"scheduled_task_{st.id}"
            for st in ScheduledTask.objects.filter(is_enabled=True)
        }
    except Exception as exc:
        logger.warning("sync_db_scheduled_tasks: 查询 ScheduledTask 失败: %s", exc)
        return

    try:
        existing = {job.id for job in _scheduler.get_jobs()}
    except Exception as exc:
        logger.warning("sync_db_scheduled_tasks: get_jobs 失败: %s", exc)
        return

    removed = 0
    for jid in existing:
        if not jid.startswith("scheduled_task_"):
            continue
        if jid in enabled_job_ids:
            continue
        try:
            _scheduler.remove_job(jid)
            removed += 1
        except Exception as exc:
            logger.warning("sync_db_scheduled_tasks: 移除 %s 失败: %s", jid, exc)

    added = _register_db_scheduled_tasks(_scheduler)
    if added or removed:
        logger.info(
            "sync_db_scheduled_tasks: enabled=%d, added=%d, removed=%d",
            len(enabled_job_ids), added, removed,
        )


def start_scheduler() -> BackgroundScheduler | None:
    """Start the APScheduler background scheduler.

    Reads the same beat_schedule from config.celery and registers
    each entry as an APScheduler job. Skips silently if not in eager mode.

    Returns the scheduler instance, or None if:
      - Not in eager mode (CELERY_TASK_ALWAYS_EAGER is False)
      - Scheduler is already running
      - No beat_schedule configured
    """
    from django.conf import settings

    # Only run in eager mode
    if not settings.CELERY_TASK_ALWAYS_EAGER:
        logger.info("APScheduler skipped (CELERY_TASK_ALWAYS_EAGER=False, celery mode)")
        return None

    global _scheduler

    if _scheduler is not None:
        return _scheduler

    # Import Celery app to read beat_schedule — this is just config reading,
    # not starting any Celery worker/beat processes.
    from config.celery import app as celery_app

    beat_schedule = getattr(celery_app.conf, 'beat_schedule', {})
    if not beat_schedule:
        logger.warning("APScheduler: no beat_schedule found, nothing to schedule")
        return None

    _scheduler = BackgroundScheduler()
    _scheduler._logger = logging.getLogger('apscheduler')

    for name, entry in beat_schedule.items():
        task_path = entry['task']
        schedule = entry['schedule']
        trigger = _build_trigger(schedule)
        _scheduler.add_job(
            _job_wrapper,
            trigger=trigger,
            args=[task_path],
            id=name,
            name=name,
            replace_existing=True,
        )
        logger.info("APScheduler registered: %s (%s, every %s)", name, task_path, schedule)

    # Register DB ScheduledTask records too (eager APScheduler previously
    # ignored them — only the static beat_schedule was wired).
    db_count = _register_db_scheduled_tasks(_scheduler)

    _scheduler.start()
    logger.info("APScheduler started (%d static + %d DB jobs)", len(beat_schedule), db_count)
    return _scheduler


def stop_scheduler() -> None:
    """Shut down the APScheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("APScheduler stopped")
