"""Monitors app tests (system status + alert escalation)

合并说明: 原 test_system_status.py + test_alert_escalation.py
两者同属 monitors app，共享 fixture 模式，合并后减少文件碎片。
"""

# ===========================================================================
# 系统状态 API (原 test_system_status.py)
# ===========================================================================

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from monitors.models import MonitorEvent
from monitors.tasks import escalate_unhandled_alerts
from notifications.models import Notification
from resources.models import ResourcePack


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


class TestSystemStatusAPI(TestCase):
    """系统状态 API 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='status_test',
            password='testpass123',
        )
        self.client.force_authenticate(user=self.user)
        self.url = '/api/v2/monitors/status/'

    def test_status_returns_200_with_fields(self):
        """TC-7.3-1: 系统状态返回 200 及核心字段"""
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap(res)
        self.assertIn('overall', body)
        self.assertIn('devicesOnline', body)
        self.assertIn('devicesTotal', body)
        self.assertIn('activeExecutions', body)

    def test_status_overall_is_valid(self):
        """TC-7.3-2: overall 字段为合法值"""
        res = self.client.get(self.url)
        overall = _unwrap(res)['overall']
        self.assertIn(
            overall,
            ['running', 'warning', 'error', 'idle'],
            f'invalid overall value: {overall}',
        )

    def test_status_idle_when_no_data(self):
        """TC-7.3-3: 无设备时 overall 为 idle"""
        res = self.client.get(self.url)
        self.assertEqual(_unwrap(res)['overall'], 'idle')

    def test_status_contains_warnings_and_errors_arrays(self):
        """TC-7.3-4: 最近警告和错误数组存在"""
        res = self.client.get(self.url)
        body = _unwrap(res)
        self.assertIn('recentWarnings', body)
        self.assertIn('recentErrors', body)
        self.assertIsInstance(body['recentWarnings'], list)
        self.assertIsInstance(body['recentErrors'], list)


# ===========================================================================
# 告警升级策略 (原 test_alert_escalation.py)
# ===========================================================================


class TestAlertEscalationTask(TestCase):
    """P-024 escalate_unhandled_alerts Celery 任务测试"""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin_test',
            password='testpass123',
            is_superuser=True,
        )
        self.pack = ResourcePack.objects.create(
            name='测试资源包',
            version='1.0',
            directory_path='/tmp/test_pack_p024',
        )

    def _create_p1_event(self, age_minutes: int, **kwargs):
        """创建 P1 告警事件, age_minutes 是创建时间距现在的分钟数。"""
        # auto_now_add=True 会覆盖 create() 时传入的 created_at, 需 create 后再 update 一次
        explicit_created_at = kwargs.pop('created_at', None)
        event = MonitorEvent.objects.create(
            event_type='test_alert',
            severity=MonitorEvent.Severity.P1_HIGH,
            resource_pack=self.pack,
            event_data={'age_minutes': age_minutes},
            **kwargs,
        )
        target_created = explicit_created_at or (timezone.now() - timedelta(minutes=age_minutes))
        MonitorEvent.objects.filter(pk=event.pk).update(created_at=target_created)
        event.refresh_from_db()
        return event

    def test_escalate_p1_unhandled_to_p0(self):
        """TC-P024-1: P1 告警 31 分钟未确认 → 升级为 P0 + 通知"""
        event = self._create_p1_event(age_minutes=31)
        result = escalate_unhandled_alerts(threshold_minutes=30)
        event.refresh_from_db()
        self.assertEqual(result['escalated_count'], 1)
        self.assertEqual(result['notification_count'], 1)
        self.assertEqual(event.severity, MonitorEvent.Severity.P0_CRITICAL)
        self.assertIsNotNone(event.escalated_at)
        # 管理员应收到 Notification
        notif = Notification.objects.filter(user=self.admin, category='alert_escalation').first()
        self.assertIsNotNone(notif)
        self.assertIn('P0 紧急告警', notif.title)

    def test_skip_p1_within_threshold(self):
        """TC-P024-2: P1 告警 10 分钟未确认 (< 30min 阈值) → 不升级"""
        event = self._create_p1_event(age_minutes=10)
        result = escalate_unhandled_alerts(threshold_minutes=30)
        event.refresh_from_db()
        self.assertEqual(result['escalated_count'], 0)
        self.assertEqual(event.severity, MonitorEvent.Severity.P1_HIGH)
        self.assertIsNone(event.escalated_at)

    def test_skip_already_acknowledged(self):
        """TC-P024-3: P1 告警已确认 → 不升级"""
        event = self._create_p1_event(
            age_minutes=60,
            acknowledged_at=timezone.now() - timedelta(minutes=10),
            acknowledged_by=self.admin,
        )
        result = escalate_unhandled_alerts(threshold_minutes=30)
        event.refresh_from_db()
        self.assertEqual(result['escalated_count'], 0)
        self.assertEqual(event.severity, MonitorEvent.Severity.P1_HIGH)
        self.assertIsNone(event.escalated_at)

    def test_skip_already_escalated(self):
        """TC-P024-4: P1 告警已升级 → 跳过 (二次扫描不重复)"""
        event = self._create_p1_event(
            age_minutes=60,
            escalated_at=timezone.now() - timedelta(minutes=5),
        )
        result = escalate_unhandled_alerts(threshold_minutes=30)
        event.refresh_from_db()
        self.assertEqual(result['escalated_count'], 0)

    def test_p0_severity_not_re_escalated(self):
        """TC-P024-5: 已经是 P0 的告警不参与升级扫描 (P0 没得升)"""
        event = MonitorEvent.objects.create(
            event_type='critical_alert',
            severity=MonitorEvent.Severity.P0_CRITICAL,
            resource_pack=self.pack,
            created_at=timezone.now() - timedelta(minutes=60),
        )
        result = escalate_unhandled_alerts(threshold_minutes=30)
        self.assertEqual(result['escalated_count'], 0)
        event.refresh_from_db()
        self.assertIsNone(event.escalated_at)  # 没动


# ===========================================================================
# 确认告警 API (原 test_alert_escalation.py)
# ===========================================================================

class TestAcknowledgeAPI(TestCase):
    """P-024 acknowledge API 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='ack_user',
            password='testpass123',
        )
        self.client.force_authenticate(user=self.user)
        self.pack = ResourcePack.objects.create(
            name='ack_test_pack',
            version='1.0',
            directory_path='/tmp/ack_test_pack',
        )
        self.event = MonitorEvent.objects.create(
            event_type='test_to_ack',
            severity=MonitorEvent.Severity.P1_HIGH,
            resource_pack=self.pack,
        )

    def test_acknowledge_success(self):
        """TC-P024-6: 确认告警 API 成功, acknowledged_at + acknowledged_by 正确"""
        res = self.client.post(
            f'/api/v2/monitors/monitor-events/{self.event.id}/acknowledge/',
            {'note': '已派人处理'},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.event.refresh_from_db()
        self.assertIsNotNone(self.event.acknowledged_at)
        self.assertEqual(self.event.acknowledged_by, self.user)
        self.assertIn('已派人处理', self.event.handling_result)

    def test_acknowledge_already_acked_returns_409(self):
        """TC-P024-7: 重复确认返回 409 Conflict"""
        self.event.acknowledged_at = timezone.now()
        self.event.acknowledged_by = self.user
        self.event.save()
        res = self.client.post(f'/api/v2/monitors/monitor-events/{self.event.id}/acknowledge/')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)

    def test_is_unacknowledged_property(self):
        """TC-P024-8: is_unacknowledged 属性反映状态"""
        self.assertTrue(self.event.is_unacknowledged)
        self.event.acknowledged_at = timezone.now()
        self.event.save()
        self.event.refresh_from_db()
        self.assertFalse(self.event.is_unacknowledged)
        # escalated 也算非未确认
        new_event = MonitorEvent.objects.create(
            event_type='escalated',
            severity=MonitorEvent.Severity.P0_CRITICAL,
            resource_pack=self.pack,
            escalated_at=timezone.now(),
        )
        self.assertFalse(new_event.is_unacknowledged)
