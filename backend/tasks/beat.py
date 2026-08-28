import logging

from django_celery_beat.models import ClockedSchedule, CrontabSchedule, PeriodicTask

from tasks.models import ScheduledTask

logger = logging.getLogger(__name__)


class BeatSchedulerService:
    """Celery Beat 调度服务，将 ScheduledTask 模型动态注册到 Celery Beat。"""

    @staticmethod
    def sync_scheduled_tasks():
        """从数据库读取所有启用的 ScheduledTask，注册到 Celery Beat。

        遍历所有 is_enabled=True 的 ScheduledTask 记录，逐一调用
        register_periodic_task 进行注册。同时清理数据库中已禁用但
        Celery Beat 中仍存在的 PeriodicTask。
        """
        enabled_tasks = ScheduledTask.objects.filter(is_enabled=True)
        registered_names = set()

        for scheduled_task in enabled_tasks:
            BeatSchedulerService.register_periodic_task(scheduled_task)
            registered_names.add(f"scheduled_task_{scheduled_task.id}")

        stale_tasks = PeriodicTask.objects.filter(
            name__startswith="scheduled_task_",
        ).exclude(name__in=registered_names)
        stale_count = stale_tasks.count()
        if stale_count:
            stale_tasks.delete()
            logger.info("已清理 %d 条过期的 PeriodicTask", stale_count)

        logger.info("同步完成，共注册 %d 条定时任务", len(registered_names))

    @staticmethod
    def register_periodic_task(scheduled_task):
        """注册单个定时任务到 Celery Beat。

        根据 scheduled_task 的 schedule_type 创建对应的调度策略：
        - one_time: 使用 ClockedSchedule 在指定时间执行一次
        - periodic: 使用 CrontabSchedule 按 cron 表达式周期执行

        Args:
            scheduled_task: ScheduledTask 模型实例
        """
        task_name = f"scheduled_task_{scheduled_task.id}"

        if scheduled_task.schedule_type == ScheduledTask.ScheduleType.ONE_TIME:
            if not scheduled_task.scheduled_time:
                logger.warning(
                    "定时任务 %s 为一次性任务但未设置执行时间，跳过注册",
                    scheduled_task.id,
                )
                return

            clocked, _ = ClockedSchedule.objects.get_or_create(
                clocked_time=scheduled_task.scheduled_time,
            )

            PeriodicTask.objects.update_or_create(
                name=task_name,
                defaults={
                    "task": "tasks.tasks.execute_scheduled_task",
                    "clocked": clocked,
                    "crontab": None,
                    "args": f'[{scheduled_task.id}]',
                    "enabled": scheduled_task.is_enabled,
                    "one_off": True,
                },
            )

        elif scheduled_task.schedule_type == ScheduledTask.ScheduleType.PERIODIC:
            if not scheduled_task.cron_expression:
                logger.warning(
                    "定时任务 %s 为周期任务但未设置 cron 表达式，跳过注册",
                    scheduled_task.id,
                )
                return

            crontab = BeatSchedulerService._parse_cron_expression(
                scheduled_task.cron_expression,
            )
            if crontab is None:
                return

            PeriodicTask.objects.update_or_create(
                name=task_name,
                defaults={
                    "task": "tasks.tasks.execute_scheduled_task",
                    "crontab": crontab,
                    "clocked": None,
                    "args": f'[{scheduled_task.id}]',
                    "enabled": scheduled_task.is_enabled,
                    "one_off": False,
                },
            )

        logger.info(
            "已注册定时任务: %s (类型=%s)",
            task_name, scheduled_task.schedule_type,
        )

    @staticmethod
    def unregister_periodic_task(scheduled_task):
        """从 Celery Beat 移除定时任务。

        删除与 scheduled_task 关联的 PeriodicTask 及其调度对象。

        Args:
            scheduled_task: ScheduledTask 模型实例
        """
        task_name = f"scheduled_task_{scheduled_task.id}"

        try:
            periodic_task = PeriodicTask.objects.get(name=task_name)
            clocked = periodic_task.clocked
            crontab = periodic_task.crontab
            periodic_task.delete()

            if clocked:
                clocked.delete()
            if crontab:
                crontab.delete()

            logger.info("已移除定时任务: %s", task_name)
        except PeriodicTask.DoesNotExist:
            logger.debug("定时任务 %s 不存在于 Celery Beat 中，无需移除", task_name)

    @staticmethod
    def _parse_cron_expression(cron_expression):
        """解析 cron 表达式，创建 CrontabSchedule 对象。

        支持标准 5 段 cron 格式: 分 时 日 月 周

        Args:
            cron_expression: cron 表达式字符串，如 "*/5 * * * *"

        Returns:
            CrontabSchedule 实例或 None（解析失败时）
        """
        parts = cron_expression.strip().split()
        if len(parts) != 5:
            logger.error("无效的 cron 表达式（需要5段）: %s", cron_expression)
            return None

        minute, hour, day_of_month, month_of_year, day_of_week = parts

        try:
            crontab, _ = CrontabSchedule.objects.get_or_create(
                minute=minute,
                hour=hour,
                day_of_month=day_of_month,
                month_of_year=month_of_year,
                day_of_week=day_of_week,
            )
            return crontab
        except Exception:
            logger.exception("创建 CrontabSchedule 失败: %s", cron_expression)
            return None
