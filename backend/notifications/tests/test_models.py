"""Tests for notifications.models (model layer, DB-backed).

Models under test: Notification, WebhookConfig, AlertRule.
"""

from django.test import TestCase

from accounts.models import User
from notifications.models import AlertRule, Notification, WebhookConfig


class NotificationModelTests(TestCase):
    """Notification model: creation, defaults, __str__, ordering, FK."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='notif_user', password='Pass123!',
        )

    def test_create_with_defaults(self):
        notif = Notification.objects.create(
            user=self.user, title='Hello', body='World', category='system',
        )
        self.assertFalse(notif.is_read)
        self.assertEqual(notif.link, '')
        self.assertIsNotNone(notif.created_at)

    def test_str_representation(self):
        notif = Notification.objects.create(
            user=self.user, title='My Title', body='body', category='info',
        )
        self.assertEqual(str(notif), f'My Title -> {self.user}')

    def test_user_related_name(self):
        notif = Notification.objects.create(
            user=self.user, title='Rel', body='b', category='c',
        )
        self.assertIn(notif, self.user.notifications.all())

    def test_cascade_delete_user(self):
        notif = Notification.objects.create(
            user=self.user, title='Cascade', body='b', category='c',
        )
        notif_id = notif.id
        self.user.delete()
        self.assertFalse(Notification.objects.filter(id=notif_id).exists())

    def test_ordering_by_created_at_desc(self):
        import time
        Notification.objects.create(
            user=self.user, title='N1', body='b', category='c',
        )
        time.sleep(0.01)
        Notification.objects.create(
            user=self.user, title='N2', body='b', category='c',
        )
        titles = list(Notification.objects.values_list('title', flat=True))
        self.assertEqual(titles[0], 'N2')


class WebhookConfigModelTests(TestCase):
    """WebhookConfig model: creation, defaults, __str__, FK."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='webhook_user', password='Pass123!',
        )

    def test_create_with_defaults(self):
        wh = WebhookConfig.objects.create(
            user=self.user, channel='dingtalk', url='https://oapi.dingtalk.com/robot/send',
        )
        self.assertTrue(wh.is_active)
        self.assertIsNotNone(wh.created_at)

    def test_str_representation(self):
        wh = WebhookConfig.objects.create(
            user=self.user, channel='feishu', url='https://open.feishu.cn/open-apis/bot/v2/hook/x',
        )
        self.assertEqual(str(wh), f'feishu ({self.user})')

    def test_cascade_delete_user(self):
        wh = WebhookConfig.objects.create(
            user=self.user, channel='slack', url='https://hooks.slack.com/services/x',
        )
        wh_id = wh.id
        self.user.delete()
        self.assertFalse(WebhookConfig.objects.filter(id=wh_id).exists())


class AlertRuleModelTests(TestCase):
    """AlertRule model: creation, defaults, __str__, FK."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='alert_user', password='Pass123!',
        )

    def test_create_with_defaults(self):
        rule = AlertRule.objects.create(
            user=self.user, name='High CPU', rule_type='threshold',
        )
        self.assertEqual(rule.threshold, 3)
        self.assertTrue(rule.enabled)
        self.assertIsNone(rule.quiet_start)
        self.assertIsNone(rule.quiet_end)
        self.assertEqual(rule.notify_methods, [])
        self.assertIsNotNone(rule.created_at)

    def test_str_representation(self):
        rule = AlertRule.objects.create(
            user=self.user, name='Disk Full', rule_type='threshold',
        )
        self.assertEqual(str(rule), f'Disk Full ({self.user})')

    def test_user_related_name(self):
        rule = AlertRule.objects.create(
            user=self.user, name='Rel Rule', rule_type='metric',
        )
        self.assertIn(rule, self.user.alert_rules.all())

    def test_cascade_delete_user(self):
        rule = AlertRule.objects.create(
            user=self.user, name='Cascade Rule', rule_type='metric',
        )
        rule_id = rule.id
        self.user.delete()
        self.assertFalse(AlertRule.objects.filter(id=rule_id).exists())
