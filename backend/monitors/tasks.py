"""P-024 告警升级 Celery 任务。

提供 escalate_unhandled_alerts 任务, 扫描 P1 告警在指定阈值时间内未确认
则自动升级为 P0, 同时为所有管理员创建 Notification 通知。
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from monitors.models import MonitorEvent

logger = logging.getLogger(__name__)
User = get_user_model()

# 升级阈值 (P1 未确认多少分钟后升级到 P0)
DEFAULT_ESCALATION_THRESHOLD_MINUTES = 30


@shared_task(name='monitors.tasks.escalate_unhandled_alerts', bind=True, max_retries=3, acks_late=True)
def escalate_unhandled_alerts(self, threshold_minutes: int = DEFAULT_ESCALATION_THRESHOLD_MINUTES):
    """扫描 P1 未确认告警, 超过阈值时间则升级为 P0 并通知管理员。

    Args:
        threshold_minutes: 升级阈值 (分钟), 默认 30 分钟。

    Returns:
        dict: {'escalated_count': N, 'notification_count': M, 'threshold_minutes': T}
    """
    threshold_time = timezone.now() - timedelta(minutes=threshold_minutes)
    candidates = MonitorEvent.objects.filter(
        severity=MonitorEvent.Severity.P1_HIGH,
        acknowledged_at__isnull=True,
        escalated_at__isnull=True,
        created_at__lte=threshold_time,
    )

    candidate_ids = list(candidates.values_list('id', flat=True))
    if not candidate_ids:
        logger.info('P-024 escalate_unhandled_alerts: 无候选告警 (阈值=%dmin)', threshold_minutes)
        return {'escalated_count': 0, 'notification_count': 0, 'threshold_minutes': threshold_minutes}

    escalated_count = 0
    notification_count = 0
    now = timezone.now()

    # 收集管理员用户 (role=admin 或 is_superuser=True)
    admin_users = User.objects.filter(is_superuser=True) | User.objects.filter(role='admin')
    admin_users = admin_users.distinct()

    with transaction.atomic():
        # 批量升级 P1 → P0
        escalated = MonitorEvent.objects.filter(id__in=candidate_ids).update(
            severity=MonitorEvent.Severity.P0_CRITICAL,
            escalated_at=now,
        )
        escalated_count = escalated

        # 给每个管理员创建 Notification
        events = MonitorEvent.objects.filter(id__in=candidate_ids)
        for admin in admin_users:
            for event in events:
                title = f'P0 紧急告警: {event.event_type}'
                body = (
                    f'告警 #{event.id} ({event.event_type}) 已被自动升级为 P0, '
                    f'因 {threshold_minutes} 分钟内未确认。\n'
                    f'创建时间: {event.created_at.isoformat()}\n'
                    f'关联资源: {event.resource_pack_id or "无"}'
                )
                # 使用 get_or_create 防止重复通知 (同一 event 对同一 admin 限 1 次)
                from notifications.models import Notification
                _, created = Notification.objects.get_or_create(
                    user=admin,
                    category='alert_escalation',
                    link=f'/monitors/events/{event.id}',
                    defaults={
                        'title': title,
                        'body': body,
                    },
                )
                if created:
                    notification_count += 1

    logger.info(
        'P-024 escalate_unhandled_alerts: 升级 %d 条, 通知 %d 条 (阈值=%dmin)',
        escalated_count, notification_count, threshold_minutes,
    )
    return {
        'escalated_count': escalated_count,
        'notification_count': notification_count,
        'threshold_minutes': threshold_minutes,
    }
