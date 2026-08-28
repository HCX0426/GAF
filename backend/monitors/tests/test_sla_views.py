"""Tests for SLA metric views (migrated from metrics app — 2026-08-04).

Covers: SLAMetric read-only list/retrieve, summary/by-name/report actions,
permission matrix.

URL prefix: /api/v2/monitors/sla/
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from agents.models import Agent
from monitors.models import SLAMetric

SLA_URL = '/api/v2/monitors/sla/'


def _login(client, username, password):
    """Login and set Bearer token on client."""
    resp = client.post('/api/v2/accounts/auth/login/', {
        'username': username, 'password': password,
    }, format='json')
    assert resp.status_code == 200, f'Login failed: {resp.status_code} {resp.data}'
    assert isinstance(resp.data, dict), f'Login resp not dict: {resp.data}'
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


class SLAMetricViewSetTests(TestCase):
    """SLAMetric ViewSet: read-only list/retrieve + summary/by-name/report."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='sla_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        _login(self.client, 'sla_admin', 'AdminPass123!')

    def test_list_empty(self):
        resp = self.client.get(SLA_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_get_results(resp)), 0)

    def test_list_metrics(self):
        SLAMetric.objects.create(metric_name='cpu', value=80)
        SLAMetric.objects.create(metric_name='mem', value=60)
        resp = self.client.get(SLA_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_get_results(resp)), 2)

    def test_retrieve_metric(self):
        metric = SLAMetric.objects.create(metric_name='cpu', value=42)
        resp = self.client.get(f'{SLA_URL}{metric.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(resp)['metric_name'], 'cpu')
        self.assertEqual(_unwrap(resp)['value'], 42)

    def test_retrieve_metric_includes_agent_name(self):
        agent = Agent.objects.create(agent_id='s-agent-001', hostname='s-host')
        metric = SLAMetric.objects.create(
            metric_name='latency', value=10, agent=agent,
        )
        resp = self.client.get(f'{SLA_URL}{metric.id}/')
        self.assertEqual(_unwrap(resp)['agent_name'], 's-host')

    def test_retrieve_metric_agent_name_null(self):
        metric = SLAMetric.objects.create(metric_name='uptime', value=99)
        resp = self.client.get(f'{SLA_URL}{metric.id}/')
        self.assertIsNone(_unwrap(resp)['agent_name'])

    def test_filter_by_metric_name(self):
        SLAMetric.objects.create(metric_name='cpu', value=1)
        SLAMetric.objects.create(metric_name='mem', value=2)
        resp = self.client.get(f'{SLA_URL}?metric_name=cpu')
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['metric_name'], 'cpu')


class SLAMetricSummaryTests(TestCase):
    """SLAMetric summary action: aggregate stats."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='sum_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        _login(self.client, 'sum_admin', 'AdminPass123!')

    def test_summary_all_metrics(self):
        SLAMetric.objects.create(metric_name='cpu', value=10)
        SLAMetric.objects.create(metric_name='cpu', value=20)
        SLAMetric.objects.create(metric_name='cpu', value=30)
        resp = self.client.get(f'{SLA_URL}summary/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = _unwrap(resp)
        self.assertEqual(body['count'], 3)
        self.assertEqual(body['average'], 20.0)
        self.assertEqual(body['max'], 30)
        self.assertEqual(body['min'], 10)

    def test_summary_filtered_by_name(self):
        SLAMetric.objects.create(metric_name='cpu', value=10)
        SLAMetric.objects.create(metric_name='mem', value=100)
        resp = self.client.get(f'{SLA_URL}summary/?metric_name=cpu')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = _unwrap(resp)
        self.assertEqual(body['metric_name'], 'cpu')
        self.assertEqual(body['count'], 1)

    def test_summary_empty(self):
        resp = self.client.get(f'{SLA_URL}summary/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = _unwrap(resp)
        self.assertEqual(body['count'], 0)
        self.assertEqual(body['average'], 0)


class SLAMetricReportTests(TestCase):
    """SLAMetric report action: POST to create metric."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='rep_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        _login(self.client, 'rep_admin', 'AdminPass123!')

    def test_report_creates_metric(self):
        resp = self.client.post(f'{SLA_URL}report/', {
            'metric_name': 'disk_usage',
            'value': 88.5,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(resp)['metric_name'], 'disk_usage')
        self.assertEqual(_unwrap(resp)['value'], 88.5)
        self.assertTrue(SLAMetric.objects.filter(metric_name='disk_usage').exists())

    def test_report_with_labels(self):
        resp = self.client.post(f'{SLA_URL}report/', {
            'metric_name': 'req_latency',
            'value': 150,
            'labels': {'endpoint': '/api/v2/tasks/'},
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        metric = SLAMetric.objects.get(metric_name='req_latency')
        self.assertEqual(metric.labels, {'endpoint': '/api/v2/tasks/'})

    def test_report_invalid_missing_value(self):
        resp = self.client.post(f'{SLA_URL}report/', {
            'metric_name': 'bad_metric',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class SLAMetricByNameTests(TestCase):
    """SLAMetric by-name action: latest value per metric_name."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='bn_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        _login(self.client, 'bn_admin', 'AdminPass123!')

    def test_by_name_returns_latest_per_metric(self):
        import time
        SLAMetric.objects.create(metric_name='cpu', value=10)
        time.sleep(0.01)
        SLAMetric.objects.create(metric_name='cpu', value=20)
        SLAMetric.objects.create(metric_name='mem', value=50)
        resp = self.client.get(f'{SLA_URL}by-name/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        items = _unwrap(resp)['items']
        self.assertEqual(len(items), 2)
        cpu_item = next(i for i in items if i['metric_name'] == 'cpu')
        self.assertEqual(cpu_item['value'], 20)

    def test_by_name_empty(self):
        resp = self.client.get(f'{SLA_URL}by-name/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_unwrap(resp)['items']), 0)


class SLAMetricPermissionTests(TestCase):
    """Permission matrix: viewer can read, unauthenticated denied."""

    def setUp(self):
        self.client = APIClient()
        self.viewer = User.objects.create_user(
            username='m_viewer', password='ViewerPass123!', role=User.Role.VIEWER,
        )
        self.operator = User.objects.create_user(
            username='m_operator', password='OpPass123!', role=User.Role.OPERATOR,
        )

    def test_unauthenticated_denied(self):
        resp = self.client.get(SLA_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_viewer_can_list(self):
        _login(self.client, 'm_viewer', 'ViewerPass123!')
        resp = self.client.get(SLA_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_viewer_can_access_summary(self):
        _login(self.client, 'm_viewer', 'ViewerPass123!')
        resp = self.client.get(f'{SLA_URL}summary/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_operator_can_report(self):
        _login(self.client, 'm_operator', 'OpPass123!')
        resp = self.client.post(f'{SLA_URL}report/', {
            'metric_name': 'op_metric', 'value': 1,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
