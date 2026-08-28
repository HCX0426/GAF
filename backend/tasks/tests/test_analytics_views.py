"""TD-389: 恢复(recovery)指标聚合后端测试�?
验证真实前端消费�?analytics 端点(executions/views.py)已返回恢复指标：
- /api/v2/analytics/weekly-report/  (weekly_report_view)
- /api/v2/analytics/task-stats/     (task_stats_view)
"""

import pytest
from rest_framework.test import APIClient

from tasks.models import Task, TaskExecution

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    from accounts.models import User
    return User.objects.create_user(
        username='td389user', password='td389pass', role='admin'
    )


@pytest.fixture
def task(user):
    return Task.objects.create(name='TD389 任务', execution_mode='pipeline', is_enabled=True)


def _make_execution(task, user, recovery_attempts, status):
    return TaskExecution.objects.create(
        task=task,
        triggered_by=user,
        status=status,
        recovery_attempts=recovery_attempts,
    )


def _auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_weekly_report_includes_recovery_metrics(user, task):
    # 本周�? 2 次触发恢�?均成�?, 1 次未触发恢复(成功)
    _make_execution(task, user, 2, 'success')
    _make_execution(task, user, 1, 'success')
    _make_execution(task, user, 0, 'success')

    client = _auth_client(user)
    resp = client.get('/api/v2/analytics/weekly-report/')
    assert resp.status_code == 200, resp.data

    data = resp.data['data']
    assert data['recovery_triggered_count'] == 2
    assert data['avg_recovery_attempts'] == pytest.approx(1.0, abs=0.01)
    assert data['recovery_success_rate'] == 100.0
    # 扁平字段契约(修复此前 undefined)
    assert data['total_executions'] == 3


def test_weekly_report_recovery_success_rate_none_when_no_recovery(user, task):
    _make_execution(task, user, 0, 'success')

    client = _auth_client(user)
    resp = client.get('/api/v2/analytics/weekly-report/')
    assert resp.status_code == 200, resp.data

    data = resp.data['data']
    assert data['recovery_triggered_count'] == 0
    assert data['recovery_success_rate'] is None


def test_task_stats_includes_recovery_metrics(user, task):
    _make_execution(task, user, 3, 'success')
    _make_execution(task, user, 1, 'failed')

    client = _auth_client(user)
    resp = client.get('/api/v2/analytics/task-stats/')
    assert resp.status_code == 200, resp.data

    item = next(r for r in resp.data['data']['results'] if r['task_id'] == task.id)
    assert item['recovery_triggered_count'] == 2
    assert item['avg_recovery_attempts'] == pytest.approx(2.0, abs=0.01)
    assert item['recovery_success_rate'] == 50.0
