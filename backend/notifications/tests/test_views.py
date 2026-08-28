"""Tests for notifications.views (API layer).

Covers: Notification CRUD + read actions, WebhookConfig CRUD + test action,
AlertRule CRUD, permission matrix.

URL prefix: /api/v2/notifications/
Global pagination is ON (PageNumberPagination, PAGE_SIZE=20), so list
responses are dicts with 'count', 'next', 'previous', 'results'.
"""

from unittest import mock

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from notifications.models import AlertRule, Notification, WebhookConfig

NOTIF_URL = '/api/v2/notifications/'
WEBHOOK_URL = '/api/v2/notifications/webhooks/'
ALERT_RULE_URL = '/api/v2/notifications/alert-rules/'


def _login(client, username, password):
    """Login and set Bearer token on client."""
    resp = client.post('/api/v2/accounts/auth/login/', {
        'username': username, 'password': password,
    }, format='json')
    assert resp.status_code == 200, f'Login failed: {resp.status_code} {resp.data}'
    assert isinstance(resp.data, dict), f'Login resp not dict: {resp.data}'
    # Task 4.49 (P0-12, 2026-07-28): 修复 token 取值路径 (unified_response 信封)。
    if isinstance(resp.data.get('data'), dict) and 'access' in resp.data['data']:
        token = resp.data['data']['access']
    elif 'access' in resp.data:
        token = resp.data['access']
    else:
        raise AssertionError(f'Login resp missing access token: {resp.data}')
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return resp


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _get_results(resp):
    """Extract results list from a possibly-paginated response."""
    data = _unwrap(resp)
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    return data


class NotificationViewSetTests(TestCase):
    """Notification ViewSet: list (user-scoped), mark_read, mark_all_read, unread_count."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='notif_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        self.operator = User.objects.create_user(
            username='notif_op', password='OpPass123!', role=User.Role.OPERATOR,
        )
        _login(self.client, 'notif_admin', 'AdminPass123!')

    def test_list_empty(self):
        resp = self.client.get(NOTIF_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_get_results(resp)), 0)

    def test_list_returns_only_own_notifications(self):
        """Queryset filters by request.user, so admin only sees admin's notifications."""
        Notification.objects.create(
            user=self.admin, title='Admin Notif', body='b', category='system',
        )
        Notification.objects.create(
            user=self.operator, title='Op Notif', body='b', category='system',
        )
        resp = self.client.get(NOTIF_URL)
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Admin Notif')

    def test_retrieve_own_notification(self):
        notif = Notification.objects.create(
            user=self.admin, title='Retrieve Me', body='b', category='info',
        )
        resp = self.client.get(f'{NOTIF_URL}{notif.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(resp)['title'], 'Retrieve Me')

    def test_retrieve_other_user_notification_404(self):
        """User cannot retrieve another user's notification (queryset-scoped)."""
        notif = Notification.objects.create(
            user=self.operator, title='Op Only', body='b', category='info',
        )
        resp = self.client.get(f'{NOTIF_URL}{notif.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_mark_read_action(self):
        notif = Notification.objects.create(
            user=self.admin, title='Read Me', body='b', category='info', is_read=False,
        )
        resp = self.client.post(f'{NOTIF_URL}{notif.id}/read/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_mark_all_read_action(self):
        Notification.objects.create(
            user=self.admin, title='A', body='b', category='c', is_read=False,
        )
        Notification.objects.create(
            user=self.admin, title='B', body='b', category='c', is_read=False,
        )
        Notification.objects.create(
            user=self.admin, title='C', body='b', category='c', is_read=True,
        )
        resp = self.client.post(f'{NOTIF_URL}read-all/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(resp)['updated'], 2)
        self.assertEqual(
            Notification.objects.filter(user=self.admin, is_read=False).count(), 0,
        )

    def test_unread_count_action(self):
        Notification.objects.create(
            user=self.admin, title='U1', body='b', category='c', is_read=False,
        )
        Notification.objects.create(
            user=self.admin, title='U2', body='b', category='c', is_read=False,
        )
        Notification.objects.create(
            user=self.admin, title='R1', body='b', category='c', is_read=True,
        )
        resp = self.client.get(f'{NOTIF_URL}unread-count/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(resp)['unread_count'], 2)

    def test_filter_by_category(self):
        Notification.objects.create(
            user=self.admin, title='Sys', body='b', category='system',
        )
        Notification.objects.create(
            user=self.admin, title='Alert', body='b', category='alert',
        )
        resp = self.client.get(f'{NOTIF_URL}?category=system')
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['category'], 'system')

    def test_filter_by_is_read(self):
        Notification.objects.create(
            user=self.admin, title='Read', body='b', category='c', is_read=True,
        )
        Notification.objects.create(
            user=self.admin, title='Unread', body='b', category='c', is_read=False,
        )
        resp = self.client.get(f'{NOTIF_URL}?is_read=true')
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Read')

    def test_search_by_title(self):
        Notification.objects.create(
            user=self.admin, title='Alpha Bug', body='b', category='c',
        )
        Notification.objects.create(
            user=self.admin, title='Beta Feature', body='b', category='c',
        )
        resp = self.client.get(f'{NOTIF_URL}?search=Alpha')
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Alpha Bug')


class WebhookConfigViewSetTests(TestCase):
    """WebhookConfig ViewSet: CRUD (manage perm), test_webhook action."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='wh_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        _login(self.client, 'wh_admin', 'AdminPass123!')

    def test_create_webhook(self):
        resp = self.client.post(WEBHOOK_URL, {
            'channel': 'dingtalk',
            'url': 'https://oapi.dingtalk.com/robot/send',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(resp)['channel'], 'dingtalk')
        self.assertTrue(_unwrap(resp)['is_active'])

    def test_create_sets_user_automatically(self):
        resp = self.client.post(WEBHOOK_URL, {
            'channel': 'feishu', 'url': 'https://open.feishu.cn/hook/x',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        wh = WebhookConfig.objects.get(pk=_unwrap(resp)['id'])
        self.assertEqual(wh.user, self.admin)

    def test_list_returns_only_own_webhooks(self):
        other = User.objects.create_user(
            username='wh_other', password='Pass123!', role=User.Role.ADMIN,
        )
        WebhookConfig.objects.create(user=self.admin, channel='c1', url='https://a.com')
        WebhookConfig.objects.create(user=other, channel='c2', url='https://b.com')
        resp = self.client.get(WEBHOOK_URL)
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['channel'], 'c1')

    def test_update_webhook(self):
        wh = WebhookConfig.objects.create(
            user=self.admin, channel='slack', url='https://hooks.slack.com/x',
        )
        resp = self.client.patch(f'{WEBHOOK_URL}{wh.id}/', {
            'is_active': False,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        wh.refresh_from_db()
        self.assertFalse(wh.is_active)

    def test_destroy_webhook(self):
        wh = WebhookConfig.objects.create(
            user=self.admin, channel='slack', url='https://hooks.slack.com/x',
        )
        resp = self.client.delete(f'{WEBHOOK_URL}{wh.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(WebhookConfig.objects.filter(id=wh.id).exists())

    @mock.patch('requests.post')
    def test_test_webhook_success(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = 'ok'
        wh = WebhookConfig.objects.create(
            user=self.admin, channel='dingtalk', url='https://oapi.dingtalk.com/x',
        )
        resp = self.client.post(f'{WEBHOOK_URL}{wh.id}/test/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(resp)['status'], 'ok')
        mock_post.assert_called_once()


class AlertRuleViewSetTests(TestCase):
    """AlertRule ViewSet: CRUD (view read, execute write)."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='ar_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        self.operator = User.objects.create_user(
            username='ar_op', password='OpPass123!', role=User.Role.OPERATOR,
        )
        _login(self.client, 'ar_admin', 'AdminPass123!')

    def test_create_alert_rule(self):
        resp = self.client.post(ALERT_RULE_URL, {
            'name': 'CPU High',
            'rule_type': 'threshold',
            'threshold': 80,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(resp)['name'], 'CPU High')
        self.assertEqual(_unwrap(resp)['threshold'], 80)

    def test_create_sets_user_automatically(self):
        resp = self.client.post(ALERT_RULE_URL, {
            'name': 'Disk Full', 'rule_type': 'threshold',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        rule = AlertRule.objects.get(pk=_unwrap(resp)['id'])
        self.assertEqual(rule.user, self.admin)

    def test_list_returns_only_own_rules(self):
        AlertRule.objects.create(user=self.admin, name='Admin Rule', rule_type='t')
        AlertRule.objects.create(user=self.operator, name='Op Rule', rule_type='t')
        resp = self.client.get(ALERT_RULE_URL)
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'Admin Rule')

    def test_update_alert_rule(self):
        rule = AlertRule.objects.create(
            user=self.admin, name='Update Me', rule_type='t',
        )
        resp = self.client.patch(f'{ALERT_RULE_URL}{rule.id}/', {
            'threshold': 95,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        rule.refresh_from_db()
        self.assertEqual(rule.threshold, 95)

    def test_destroy_alert_rule(self):
        rule = AlertRule.objects.create(
            user=self.admin, name='Delete Me', rule_type='t',
        )
        resp = self.client.delete(f'{ALERT_RULE_URL}{rule.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AlertRule.objects.filter(id=rule.id).exists())


class NotificationPermissionTests(TestCase):
    """Permission matrix: viewer read-only, operator read+execute, admin full."""

    def setUp(self):
        self.client = APIClient()
        self.viewer = User.objects.create_user(
            username='n_viewer', password='ViewerPass123!', role=User.Role.VIEWER,
        )
        self.operator = User.objects.create_user(
            username='n_operator', password='OpPass123!', role=User.Role.OPERATOR,
        )
        self.admin = User.objects.create_user(
            username='n_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )

    def test_unauthenticated_denied(self):
        resp = self.client.get(NOTIF_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_viewer_can_list_notifications(self):
        _login(self.client, 'n_viewer', 'ViewerPass123!')
        resp = self.client.get(NOTIF_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_destroy_notification(self):
        notif = Notification.objects.create(
            user=self.viewer, title='V', body='b', category='c',
        )
        _login(self.client, 'n_viewer', 'ViewerPass123!')
        resp = self.client.delete(f'{NOTIF_URL}{notif.id}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_operator_cannot_destroy_notification(self):
        notif = Notification.objects.create(
            user=self.operator, title='O', body='b', category='c',
        )
        _login(self.client, 'n_operator', 'OpPass123!')
        resp = self.client.delete(f'{NOTIF_URL}{notif.id}/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_destroy_notification(self):
        notif = Notification.objects.create(
            user=self.admin, title='A', body='b', category='c',
        )
        _login(self.client, 'n_admin', 'AdminPass123!')
        resp = self.client.delete(f'{NOTIF_URL}{notif.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_viewer_cannot_access_webhooks(self):
        _login(self.client, 'n_viewer', 'ViewerPass123!')
        resp = self.client.get(WEBHOOK_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_operator_cannot_access_webhooks(self):
        _login(self.client, 'n_operator', 'OpPass123!')
        resp = self.client.get(WEBHOOK_URL)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_access_webhooks(self):
        _login(self.client, 'n_admin', 'AdminPass123!')
        resp = self.client.get(WEBHOOK_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_viewer_can_list_alert_rules(self):
        _login(self.client, 'n_viewer', 'ViewerPass123!')
        resp = self.client.get(ALERT_RULE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_create_alert_rule(self):
        _login(self.client, 'n_viewer', 'ViewerPass123!')
        resp = self.client.post(ALERT_RULE_URL, {
            'name': 'Denied', 'rule_type': 't',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_operator_can_create_alert_rule(self):
        _login(self.client, 'n_operator', 'OpPass123!')
        resp = self.client.post(ALERT_RULE_URL, {
            'name': 'Op Rule', 'rule_type': 't',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
