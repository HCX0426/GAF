# Merged from test_scheduler.py, test_unattended.py, test_recovery.py - 2026-08-04
"""
调度引擎逻辑测试

覆盖：
- 时间窗口内/外触发
- 4 种账户轮换策略
- 设备×资源包矩阵解析
- 跳过被封禁账户

Phase 8: Unattended control API tests — adapted to P-011 multi-session contract.

恢复策略执行引擎测试

覆盖：
- 步骤级失败重试（含指数退避）
- 任务级连续失败阈值触发
- 应用级卡死检测（未达/达到超时）
- 设备级崩溃恢复
- 系统级 Agent 超时恢复
"""

import datetime
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from gaf_core.error_codes import ErrorCode
from pipeline.models import TaskChain, TaskChainExecution, TaskChainNode
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import GameAccount, User
from agents.models import Agent, Device
from gamestate.models import GameProfile
from scheduler.engine import (
    calculate_account_order,
    check_auto_stop_conditions,
    check_time_window,
    generate_execution_plan,
)
from scheduler.models import (
    AutoStopCondition,
    GameAccountRotation,
    RecoveryLog,
    TimeWindow,
    UnattendedSession,
)
from scheduler.recovery_engine import (
    execute_recovery_action,
    get_strategy_config,
    handle_agent_timeout,
    handle_app_freeze,
    handle_step_failure,
    handle_task_failure,
)
from scheduler.tasks import tick_unattended_session
from tasks.models import ExecutionStep, Task, TaskExecution

pytestmark = pytest.mark.e2e


def _gp(name):
    """测试 helper: window-centric 唯一游戏维度 (find_or_create 全局 profile)."""
    return GameProfile.objects.get_or_create(game_name=name)[0]


def _unwrap(res):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = res.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _get_results(resp):
    """适配信封 + 分页。先解信封, 再取分页 results 字段。"""
    data = _unwrap(resp)
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    return data


def _unwrap_original(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _get_results_original(resp):
    """适配信封 + 分页。先解信封, 再取分页 results 字段。"""
    data = _unwrap_original(resp)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    return data


class TestTimeWindowCheck(TestCase):
    """时间窗口检查测试"""

    def test_inside_time_window(self):
        """TC-6.3.2-1：时间窗口内正常触发"""
        TimeWindow.objects.create(
            start_time=datetime.time(6, 0),
            end_time=datetime.time(12, 0),
            days_of_week=[1, 2, 3, 4, 5],
            is_enabled=True,
        )

        test_time = timezone.make_aware(
            datetime.datetime(2026, 5, 21, 8, 0, 0)  # 周四
        )
        self.assertTrue(check_time_window(test_time))

    def test_outside_time_window(self):
        """TC-6.3.2-2：时间窗口外跳过"""
        TimeWindow.objects.create(
            start_time=datetime.time(6, 0),
            end_time=datetime.time(12, 0),
            days_of_week=[1, 2, 3, 4, 5],
            is_enabled=True,
        )

        test_time = timezone.make_aware(
            datetime.datetime(2026, 5, 21, 14, 0, 0)
        )
        self.assertFalse(check_time_window(test_time))


class TestAccountRotation(TestCase):
    """账户轮换策略测试"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='rotation_test',
            password='testpass123',
        )
        self.account1 = GameAccount.objects.create(
            owner=self.user,
            game_profile=_gp('TestGame'),
            username='account_a',
            server_region='官服',
            login_method='password',
            status='ok',
        )
        self.account2 = GameAccount.objects.create(
            owner=self.user,
            game_profile=_gp('TestGame'),
            username='account_b',
            server_region='官服',
            login_method='password',
            status='ok',
        )
        self.account3 = GameAccount.objects.create(
            owner=self.user,
            game_profile=_gp('TestGame'),
            username='account_banned',
            server_region='官服',
            login_method='password',
            status='error',
        )

    def test_sequential_rotation(self):
        """TC-6.3.2-3：顺序轮换策略正确计算账户顺序"""
        rule = GameAccountRotation.objects.create(
            name='测试顺序',
            rotation_strategy='sequential',
            auto_skip_blocked=True,
        )
        rule.accounts.add(self.account1, self.account2)

        accounts = rule.accounts.all()
        ordered = calculate_account_order(rule, accounts)
        self.assertEqual(len(ordered), 2)

    def test_random_rotation(self):
        """TC-6.3.2-4：随机轮换策略返回账户列表"""
        rule = GameAccountRotation.objects.create(
            name='测试随机',
            rotation_strategy='random',
            auto_skip_blocked=False,
        )
        rule.accounts.add(self.account1, self.account2)

        accounts = rule.accounts.all()
        ordered = calculate_account_order(rule, accounts)
        self.assertEqual(len(ordered), 2)

    def test_skip_blocked_account(self):
        """TC-6.3.2-6：跳过被封禁账户"""
        rule = GameAccountRotation.objects.create(
            name='测试跳过封禁',
            rotation_strategy='sequential',
            auto_skip_blocked=True,
        )
        rule.accounts.add(self.account1, self.account2, self.account3)

        accounts = rule.accounts.all()
        ordered = calculate_account_order(rule, accounts)
        self.assertEqual(len(ordered), 2)
        account_ids = [a.id for a in ordered]
        self.assertNotIn(self.account3.id, account_ids)


class TestAutoStopConditions(TestCase):
    """自动停止条件测试"""

    def test_trigger_consecutive_failures(self):
        """连续失败触发停止条件"""
        AutoStopCondition.objects.create(
            condition_type='consecutive_failures',
            is_enabled=True,
            threshold=5,
            action='stop_all',
        )

        triggered = check_auto_stop_conditions(consecutive_failures=5)
        self.assertEqual(len(triggered), 1)

    def test_no_trigger_below_threshold(self):
        """未达阈值不触发"""
        AutoStopCondition.objects.create(
            condition_type='consecutive_failures',
            is_enabled=True,
            threshold=5,
            action='stop_all',
        )

        triggered = check_auto_stop_conditions(consecutive_failures=3)
        self.assertEqual(len(triggered), 0)

    def test_trigger_device_offline(self):
        """设备离线触发停止条件"""
        AutoStopCondition.objects.create(
            condition_type='device_offline',
            is_enabled=True,
            threshold=10,
            action='stop_device',
        )

        triggered = check_auto_stop_conditions(device_offline_minutes=15)
        self.assertEqual(len(triggered), 1)

    def test_trigger_window_end(self):
        """时间窗口结束触发"""
        AutoStopCondition.objects.create(
            condition_type='window_end',
            is_enabled=True,
            action='stop_all',
        )

        triggered = check_auto_stop_conditions(in_time_window=False)
        self.assertEqual(len(triggered), 1)

    def test_condition_disabled_not_trigger(self):
        """已禁用条件不触发"""
        AutoStopCondition.objects.create(
            condition_type='all_completed',
            is_enabled=False,
            action='stop_all',
        )

        triggered = check_auto_stop_conditions(all_accounts_completed=True)
        self.assertEqual(len(triggered), 0)


class TestExecutionPlan(TestCase):
    """generate_execution_plan tests (spec §2.4.2 — window-centric, no fallback)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='plan_test',
            password='testpass123',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_generate_7_day_plan(self):
        """days=7 generates a plan without crashing."""
        plans = generate_execution_plan(days=7)
        self.assertIsInstance(plans, list)

    def test_plan_returns_empty_when_no_default_task_chain(self):
        """TD-097: empty_fallback path removed — plan is empty when no device
        has a default_task_chain configured (no placeholder item)."""
        plans = generate_execution_plan(days=7)
        self.assertEqual(plans, [])

    def test_plan_structure_matches_spec(self):
        """Plan items have the spec §2.4.2 structure."""
        profile = GameProfile.objects.create(game_name='BD2')
        chain = TaskChain.objects.create(
            name='BD2-daily',
            game_profile=profile,
            is_enabled=True,
            is_default=True,
            created_by=self.user,
        )
        profile.default_task_chain = chain
        profile.save(update_fields=['default_task_chain'])
        Device.objects.create(
            name='Win-PC-1',
            device_type='windows',
            game_profile=profile,
        )

        plans = generate_execution_plan(days=1)
        self.assertEqual(len(plans), 1)
        plan = plans[0]
        required_keys = {
            'device_id', 'device_name', 'account_id', 'account_name',
            'task_chain_id', 'task_chain_name', 'day_offset',
        }
        self.assertTrue(required_keys.issubset(plan.keys()))
        self.assertEqual(plan['task_chain_name'], 'BD2-daily')
        self.assertEqual(plan['device_name'], 'Win-PC-1')
        self.assertEqual(plan['day_offset'], 0)
        self.assertIsNone(plan['account_id'])
        self.assertIsNone(plan['account_name'])

    def test_plan_one_item_per_device_per_day(self):
        """Each device with a default_task_chain produces exactly one item per day."""
        profile = GameProfile.objects.create(game_name='BD2')
        chain = TaskChain.objects.create(
            name='BD2-daily',
            game_profile=profile,
            is_enabled=True,
            is_default=True,
            created_by=self.user,
        )
        profile.default_task_chain = chain
        profile.save(update_fields=['default_task_chain'])
        Device.objects.create(name='Dev-A', device_type='windows', game_profile=profile)
        Device.objects.create(name='Dev-B', device_type='windows', game_profile=profile)

        plans = generate_execution_plan(days=3)
        # 2 devices × 3 days = 6 items
        self.assertEqual(len(plans), 6)
        # Each day_offset should have exactly 2 items (one per device)
        for day_offset in range(3):
            day_items = [p for p in plans if p['day_offset'] == day_offset]
            self.assertEqual(len(day_items), 2)

    def test_today_schedule_api(self):
        """Today schedule API returns correct shape."""
        res = self.client.get('/api/v2/scheduler/today/')
        self.assertIn(res.status_code, [status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED])

        if res.status_code == status.HTTP_200_OK:
            body = _unwrap_original(res)
            self.assertIn('date', body)
            self.assertIn('items', body)
            self.assertIn('total', body)
            self.assertIn('completed', body)
            self.assertIn('failed', body)

    def test_today_schedule_planned_status_and_empty_account(self):
        """N219: 计划项状态为 planned(计划中) + 无绑定账户时 account_name 为空串.

        今日日程 = 计划排期 (引擎按 Device+default_task_chain 推导), 非实际执行:
        ① 状态用 planned 而非 pending, 避免"待执行"误导 ② 未绑账户时
        account_name 为 "" (前端不渲染空段箭头), 而非 "未知账户".
        """
        profile = GameProfile.objects.create(game_name='BD2-plan')
        chain = TaskChain.objects.create(
            name='BD2-daily-plan',
            game_profile=profile,
            is_enabled=True,
            is_default=True,
            created_by=self.user,
        )
        profile.default_task_chain = chain
        profile.save(update_fields=['default_task_chain'])
        Device.objects.create(name='Win-PC-1', device_type='windows', game_profile=profile)

        res = self.client.get('/api/v2/scheduler/today/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap_original(res)
        self.assertEqual(body['total'], 1)
        item = body['items'][0]
        self.assertEqual(item['status'], 'planned')
        self.assertEqual(item['account_name'], '')
        self.assertEqual(item['device_name'], 'Win-PC-1')
        self.assertEqual(item['task_chain_name'], 'BD2-daily-plan')


class TestPlanAPIIntegration(TestCase):
    """Execution plan API integration tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='plan_api_test',
            password='testpass123',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_execution_plan_api_returns_200(self):
        """Execution plan API returns 200."""
        res = self.client.get('/api/v2/scheduler/execution-plan/?days=7')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap_original(res)
        self.assertIn('days', body)
        self.assertIn('events', body)

    def test_execution_plan_api_defaults_to_7_days(self):
        """Execution plan API defaults to 7 days."""
        res = self.client.get('/api/v2/scheduler/execution-plan/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap_original(res)['days'], 7)

    def test_execution_plan_api_invalid_days_returns_400(self):
        """spec-55 TD-293: invalid days param (non-int) returns 400, not 500."""
        res = self.client.get('/api/v2/scheduler/execution-plan/?days=abc')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        # unified_response 信封: 错误响应字段是 message (非 error), data 为 None
        self.assertEqual(res.data['code'], ErrorCode.INVALID_PARAMS)
        self.assertIn('message', res.data)


class TestUnattendedStartRealDispatch(TestCase):
    """unattended_start_view real TaskChain dispatch (spec §2.4.1).

    Success path mocks dispatch_chain_node.delay so no Celery task runs.
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_superuser('admin', 'admin@test.com', 'admin123')
        self.user.role = 'admin'
        self.user.save(update_fields=['role'])
        self.client.force_authenticate(user=self.user)
        # P-009 Phase 1: no module-level dict to reset — Django TestCase
        # rolls back DB transaction between tests, so each test starts
        # with no UnattendedSession records.
        # P-011: start requires game_profile_id — shared profile for tests
        # that don't construct their own profile/chain/device setup.
        self.game_profile = GameProfile.objects.create(
            game_name='Game-Scheduler-Plan-Test',
        )

    def test_already_running_returns_409(self):
        """If unattended mode is already running, POST start returns 409.

        P-009 Phase 1: replaced direct dict manipulation with a real
        POST start to create an active session, then a second POST start.
        P-011: 409 is scoped per game_profile_id — second start with the
        same game_profile_id hits the singleton guard.
        """
        url = '/api/v2/scheduler/unattended/start/'
        payload = {'game_profile_id': self.game_profile.id}
        # First start creates an active RUNNING session
        self.client.post(url, payload, format='json')
        # Second start with the same game_profile_id hits the 409 guard
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data['code'], ErrorCode.INVALID_PARAMS)

    def test_no_devices_with_default_task_chain_returns_zero_dispatch(self):
        """No devices with default_task_chain → dispatched_count=0, status=running."""
        res = self.client.post(
            '/api/v2/scheduler/unattended/start/',
            {'game_profile_id': self.game_profile.id},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap_original(res)
        self.assertEqual(body['status'], 'running')
        self.assertEqual(body['dispatched_count'], 0)
        self.assertEqual(body['skipped_count'], 0)
        self.assertEqual(body['failed_count'], 0)

    def test_device_with_disabled_chain_is_skipped(self):
        """Device bound to a disabled default_task_chain chain is skipped."""
        profile = GameProfile.objects.create(game_name='BD2')
        chain = TaskChain.objects.create(
            name='disabled-chain',
            game_profile=profile,
            is_enabled=False,
            is_default=True,
            created_by=self.user,
        )
        profile.default_task_chain = chain
        profile.save(update_fields=['default_task_chain'])
        agent = Agent.objects.create(
            agent_id='online-agent-1',
            hostname='host-1',
            status=Agent.Status.ONLINE,
        )
        Device.objects.create(
            name='Win-PC-1',
            device_type='windows',
            game_profile=profile,
            agent=agent,
        )

        res = self.client.post(
            '/api/v2/scheduler/unattended/start/',
            {'game_profile_id': profile.id},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap_original(res)
        self.assertEqual(body['dispatched_count'], 0)
        self.assertEqual(body['skipped_count'], 1)
        self.assertEqual(body['skipped'][0]['reason'], 'chain_disabled')

    def test_device_without_online_agent_not_in_dispatch_list(self):
        """Device with offline/no agent is filtered out by the query."""
        profile = GameProfile.objects.create(game_name='BD2')
        chain = TaskChain.objects.create(
            name='active-chain',
            game_profile=profile,
            is_enabled=True,
            is_default=True,
            created_by=self.user,
        )
        profile.default_task_chain = chain
        profile.save(update_fields=['default_task_chain'])
        # Device with offline agent
        offline_agent = Agent.objects.create(
            agent_id='offline-agent-1',
            hostname='host-offline',
            status=Agent.Status.OFFLINE,
        )
        Device.objects.create(
            name='Win-Offline',
            device_type='windows',
            game_profile=profile,
            agent=offline_agent,
        )

        res = self.client.post(
            '/api/v2/scheduler/unattended/start/',
            {'game_profile_id': profile.id},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap_original(res)
        # Device filtered out by agent__status__in=[online, idle] query
        self.assertEqual(body['dispatched_count'], 0)
        self.assertEqual(body['skipped_count'], 0)
        self.assertEqual(body['failed_count'], 0)

    @patch('pipeline.tasks.dispatch_chain_node.delay')
    def test_device_with_online_agent_and_enabled_chain_dispatches(self, mock_delay):
        """Device with online agent + enabled default_task_chain chain dispatches."""
        profile = GameProfile.objects.create(game_name='BD2')
        chain = TaskChain.objects.create(
            name='active-chain',
            game_profile=profile,
            is_enabled=True,
            is_default=True,
            created_by=self.user,
        )
        profile.default_task_chain = chain
        profile.save(update_fields=['default_task_chain'])
        # Chain must have at least one node
        task = Task.objects.create(name='Task A')
        TaskChainNode.objects.create(chain=chain, task=task, order=1)

        agent = Agent.objects.create(
            agent_id='online-agent-2',
            hostname='host-2',
            status=Agent.Status.ONLINE,
        )
        Device.objects.create(
            name='Win-Online',
            device_type='windows',
            game_profile=profile,
            agent=agent,
        )

        res = self.client.post(
            '/api/v2/scheduler/unattended/start/',
            {'game_profile_id': profile.id},
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap_original(res)
        self.assertEqual(body['dispatched_count'], 1)
        self.assertEqual(body['skipped_count'], 0)
        self.assertEqual(body['failed_count'], 0)
        # Verify TaskChainExecution was created
        self.assertEqual(TaskChainExecution.objects.count(), 1)
        chain_exec = TaskChainExecution.objects.first()
        self.assertIn(chain_exec.id, body['dispatched_chain_execution_ids'])
        # Verify dispatch_chain_node.delay was called
        mock_delay.assert_called_once()


class TestTimeWindowCRUD(TestCase):
    """时间窗口 CRUD 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='scheduler_test',
            password='testpass123',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.user)
        self.base_url = '/api/v2/scheduler/time-windows/'

    def test_create_time_window(self):
        """TC-6.3.1-1：创建单个时间窗口 -> 201 + 数据正确"""
        data = {
            'start_time': '06:00:00',
            'end_time': '12:00:00',
            'days_of_week': [1, 2, 3, 4, 5],
            'is_enabled': True,
        }
        res = self.client.post(self.base_url, data, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        body = _unwrap_original(res)
        self.assertEqual(body['start_time'], '06:00:00')
        self.assertEqual(body['end_time'], '12:00:00')
        self.assertEqual(body['days_of_week'], [1, 2, 3, 4, 5])
        self.assertTrue(body['is_enabled'])

    def test_list_time_windows(self):
        """TC-6.3.1-2：获取时间窗口列表 -> 200 + 返回包含创建的窗口"""
        tw1 = TimeWindow.objects.create(
            start_time=datetime.time(6, 0),
            end_time=datetime.time(12, 0),
            days_of_week=[1, 2, 3],
            is_enabled=True,
        )
        tw2 = TimeWindow.objects.create(
            start_time=datetime.time(14, 0),
            end_time=datetime.time(18, 0),
            days_of_week=[1, 2, 3],
            is_enabled=False,
        )

        res = self.client.get(self.base_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = _get_results_original(res)
        ids = [item['id'] for item in items]
        self.assertIn(tw1.id, ids)
        self.assertIn(tw2.id, ids)

    def test_update_time_window(self):
        """TC-6.3.1-3：更新时间窗口 -> 200 + 数据已更新"""
        tw = TimeWindow.objects.create(
            start_time=datetime.time(6, 0),
            end_time=datetime.time(12, 0),
            days_of_week=[1, 2, 3],
            is_enabled=True,
        )

        data = {
            'start_time': '08:00:00',
            'end_time': '14:00:00',
            'days_of_week': [1, 2, 3, 4],
            'is_enabled': True,
        }
        res = self.client.put(f'{self.base_url}{tw.id}/', data, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap_original(res)
        self.assertEqual(body['start_time'], '08:00:00')
        self.assertEqual(body['end_time'], '14:00:00')

    def test_delete_time_window(self):
        """TC-6.3.1-4：删除时间窗口 -> 204"""
        tw = TimeWindow.objects.create(
            start_time=datetime.time(6, 0),
            end_time=datetime.time(12, 0),
            days_of_week=[1, 2, 3],
            is_enabled=True,
        )

        res = self.client.delete(f'{self.base_url}{tw.id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(TimeWindow.objects.filter(id=tw.id).count(), 0)

    def test_overlap_validation(self):
        """TC-6.3.1-5：时间窗口重叠校验 -> 400 + 错误信息"""
        TimeWindow.objects.create(
            start_time=datetime.time(6, 0),
            end_time=datetime.time(12, 0),
            days_of_week=[1, 2, 3, 4, 5],
            is_enabled=True,
        )

        data = {
            'start_time': '08:00:00',
            'end_time': '14:00:00',
            'days_of_week': [1, 2, 3, 4, 5],
            'is_enabled': True,
        }
        res = self.client.post(self.base_url, data, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_enabled(self):
        """TC-6.3.1-6：过滤已启用窗口 -> ?enabled=true 正确过滤"""
        tw_enabled = TimeWindow.objects.create(
            start_time=datetime.time(6, 0),
            end_time=datetime.time(12, 0),
            days_of_week=[1, 2, 3],
            is_enabled=True,
        )
        tw_disabled = TimeWindow.objects.create(
            start_time=datetime.time(14, 0),
            end_time=datetime.time(18, 0),
            days_of_week=[1, 2, 3],
            is_enabled=False,
        )

        res = self.client.get(f'{self.base_url}?enabled=true')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = _get_results_original(res)
        ids = [item['id'] for item in items]
        self.assertIn(tw_enabled.id, ids)
        self.assertNotIn(tw_disabled.id, ids)


# =========================================================================
# Unattended Control API Tests (from test_unattended.py)
# =========================================================================

UserModel = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    """Create authenticated API client for unattended endpoints."""
    client = APIClient()
    user, _ = UserModel.objects.get_or_create(
        username='test_unattended',
        defaults={'email': 'test@gaf.local', 'is_active': True},
    )
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def game_profile(db):
    """GameProfile for unattended control tests (P-011 required param)."""
    return GameProfile.objects.create(game_name='Game-Unattended-Test')


# ---------------------------------------------------------------------------
# Helpers — every call site passes the P-011 required parameter
# ---------------------------------------------------------------------------

def _start(client, game_profile_id, **extra):
    """POST unattended-start with game_profile_id (P-011 required)."""
    payload = {'game_profile_id': game_profile_id, **extra}
    return client.post(reverse('unattended-start'), data=payload, format='json')


def _stop(client, session_id, reason='manual'):
    """POST unattended-stop with session_id (P-011 required)."""
    return client.post(
        reverse('unattended-stop'),
        data={'session_id': session_id, 'reason': reason},
        format='json',
    )


def _pause(client, session_id):
    """POST unattended-pause with session_id (P-011 required)."""
    return client.post(
        reverse('unattended-pause'),
        data={'session_id': session_id},
        format='json',
    )


def _resume(client, session_id):
    """POST unattended-resume with session_id (P-011 required)."""
    return client.post(
        reverse('unattended-resume'),
        data={'session_id': session_id},
        format='json',
    )


@pytest.mark.django_db
class TestUnattendedStart:
    """Tests for unattended start API (P-011: scoped by game_profile_id)."""

    def test_start_success(self, api_client, game_profile):
        """POST start with game_profile_id returns 200 and running status."""
        res = _start(api_client, game_profile.id, reason='test')
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['status'] == 'running'
        assert body['session_id'] is not None
        assert body['game_profile_id'] == game_profile.id
        assert body['game_profile_name'] == game_profile.game_name
        assert body['started_at'] is not None
        # No devices configured in test -> dispatched_count == 0
        assert body['dispatched_count'] == 0

    def test_start_missing_game_profile_id_returns_400(self, api_client):
        """POST start without game_profile_id returns 400 missing_game_profile_id."""
        res = api_client.post(reverse('unattended-start'), format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert res.data['code'] == ErrorCode.INVALID_PARAMS

    def test_start_already_running_returns_409(self, api_client, game_profile):
        """Repeated start with the same game_profile returns 409 already_running."""
        _start(api_client, game_profile.id)
        res = _start(api_client, game_profile.id)
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.data['code'] == ErrorCode.INVALID_PARAMS


@pytest.mark.django_db
class TestUnattendedStop:
    """Tests for unattended stop API (P-011: operates by session_id)."""

    def test_stop_success(self, api_client, game_profile):
        """POST stop with session_id returns stopped status."""
        start_res = _start(api_client, game_profile.id)
        session_id = _unwrap(start_res)['session_id']

        res = _stop(api_client, session_id, reason='manual')
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['status'] == 'stopped'
        assert body['stop_reason'] == 'manual'
        assert body['session_id'] == session_id
        assert body['stopped_at'] is not None

    def test_stop_session_not_found_returns_404(self, api_client):
        """POST stop with unknown session_id returns 404 session_not_found."""
        res = _stop(api_client, session_id=999999)
        assert res.status_code == status.HTTP_404_NOT_FOUND
        assert res.data['code'] == ErrorCode.NOT_FOUND

    def test_stop_already_stopped_returns_409(self, api_client, game_profile):
        """POST stop on a STOPPED session returns 409 already_stopped."""
        start_res = _start(api_client, game_profile.id)
        session_id = _unwrap(start_res)['session_id']
        _stop(api_client, session_id)
        res = _stop(api_client, session_id)
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.data['code'] == ErrorCode.INVALID_PARAMS


@pytest.mark.django_db
class TestUnattendedPauseResume:
    """Tests for pause/resume API (P-011: operates by session_id)."""

    def test_pause_success(self, api_client, game_profile):
        """POST pause on a RUNNING session returns paused."""
        start_res = _start(api_client, game_profile.id)
        session_id = _unwrap(start_res)['session_id']

        res = _pause(api_client, session_id)
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['status'] == 'paused'
        assert body['session_id'] == session_id

    def test_pause_session_not_found_returns_404(self, api_client):
        """POST pause with unknown session_id returns 404 session_not_found."""
        res = _pause(api_client, session_id=999999)
        assert res.status_code == status.HTTP_404_NOT_FOUND
        assert res.data['code'] == ErrorCode.NOT_FOUND

    def test_pause_not_running_returns_409(self, api_client, game_profile):
        """POST pause on a PAUSED session returns 409 not_running."""
        start_res = _start(api_client, game_profile.id)
        session_id = _unwrap(start_res)['session_id']
        _pause(api_client, session_id)
        res = _pause(api_client, session_id)
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.data['code'] == ErrorCode.INVALID_PARAMS

    def test_resume_success(self, api_client, game_profile):
        """POST resume on a PAUSED session returns running."""
        start_res = _start(api_client, game_profile.id)
        session_id = _unwrap(start_res)['session_id']
        _pause(api_client, session_id)

        res = _resume(api_client, session_id)
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['status'] == 'running'
        assert body['session_id'] == session_id

    def test_resume_session_not_found_returns_404(self, api_client):
        """POST resume with unknown session_id returns 404 session_not_found."""
        res = _resume(api_client, session_id=999999)
        assert res.status_code == status.HTTP_404_NOT_FOUND
        assert res.data['code'] == ErrorCode.NOT_FOUND

    def test_resume_not_paused_returns_409(self, api_client, game_profile):
        """POST resume on a RUNNING session returns 409 not_paused."""
        start_res = _start(api_client, game_profile.id)
        session_id = _unwrap(start_res)['session_id']
        res = _resume(api_client, session_id)
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.data['code'] == ErrorCode.INVALID_PARAMS


@pytest.mark.django_db
class TestUnattendedPreflight:
    """Tests for preflight checklist API (unchanged by P-011)."""

    def test_preflight_returns_checks(self, api_client):
        """Preflight API returns 5 check items."""
        url = reverse('unattended-preflight')
        res = api_client.get(url)
        assert res.status_code == status.HTTP_200_OK
        checks = _unwrap(res).get('checks', [])
        assert len(checks) == 5
        check_types = {c['check_type'] for c in checks}
        expected_types = {
            'device_online', 'account_valid', 'resource_ready',
            'agent_connection', 'scheduler_rules',
        }
        assert check_types == expected_types

    def test_preflight_has_overall_status(self, api_client):
        """Preflight result includes an overall field."""
        url = reverse('unattended-preflight')
        res = api_client.get(url)
        assert res.status_code == status.HTTP_200_OK
        overall = _unwrap(res).get('overall')
        assert overall in ('pass', 'fail', 'warning')

    def test_preflight_can_start_field(self, api_client):
        """can_start field is a boolean."""
        url = reverse('unattended-preflight')
        res = api_client.get(url)
        assert isinstance(_unwrap(res).get('can_start'), bool)


@pytest.mark.django_db
class TestUnattendedStatus:
    """Tests for status matrix API (P-011: active_sessions + mode_status)."""

    def test_status_returns_matrix(self, api_client):
        """Status API returns a matrix list."""
        url = reverse('unattended-status')
        res = api_client.get(url)
        assert res.status_code == status.HTTP_200_OK
        matrix = _unwrap(res).get('matrix', [])
        assert isinstance(matrix, list)

    def test_status_mode_field(self, api_client):
        """mode_status is one of the valid values."""
        url = reverse('unattended-status')
        res = api_client.get(url)
        mode = _unwrap(res).get('mode_status')
        assert mode in ('running', 'paused', 'stopped')

    def test_status_no_session_returns_stopped(self, api_client):
        """Status with no active session returns mode_status=stopped + empty list."""
        res = api_client.get(reverse('unattended-status'))
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['mode_status'] == 'stopped'
        assert body['active_sessions'] == []

    def test_status_running_session_returns_running(self, api_client, game_profile):
        """Status with a RUNNING session returns mode_status=running + 1 entry."""
        _start(api_client, game_profile.id)
        res = api_client.get(reverse('unattended-status'))
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['mode_status'] == 'running'
        active = body['active_sessions']
        assert len(active) == 1
        assert active[0]['game_profile_id'] == game_profile.id
        assert active[0]['game_profile_name'] == game_profile.game_name


@pytest.mark.django_db
class TestUnattendedQueue:
    """Tests for execution queue API (unchanged by P-011)."""

    def test_queue_returns_list(self, api_client):
        """Queue API returns a task list."""
        url = reverse('unattended-queue')
        res = api_client.get(url)
        assert res.status_code == status.HTTP_200_OK
        queue = _unwrap(res).get('queue', [])
        assert isinstance(queue, list)

    def test_queue_limit_param(self, api_client):
        """limit param caps the returned count."""
        url = reverse('unattended-queue') + '?limit=3'
        res = api_client.get(url)
        queue = _unwrap(res).get('queue', [])
        assert len(queue) <= 3


@pytest.mark.django_db
class TestUnattendedProgress:
    """Tests for today progress API (unchanged by P-011)."""

    def test_progress_returns_stats(self, api_client):
        """Progress API returns statistics fields."""
        url = reverse('unattended-progress')
        res = api_client.get(url)
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        required_fields = [
            'date', 'total_accounts', 'completed',
            'success', 'failed', 'skipped', 'success_rate',
        ]
        for field in required_fields:
            assert field in body, f"missing field: {field}"

    def test_progress_rate_range(self, api_client):
        """success_rate is within 0-100."""
        url = reverse('unattended-progress')
        res = api_client.get(url)
        rate = _unwrap(res).get('success_rate', 0)
        assert 0 <= rate <= 100


# =========================================================================
# P-011: UnattendedSession multi-session parallel API tests
# =========================================================================

@pytest.fixture
def api_client_p011():
    """Create authenticated API client for P-011 session tests."""
    client = APIClient()
    user, _ = UserModel.objects.get_or_create(
        username='test_p011_session',
        defaults={'email': 'p011@gaf.local', 'is_active': True},
    )
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def game_profile_a(db):
    """GameProfile A for multi-session tests."""
    return GameProfile.objects.create(game_name='GameA-P011')


@pytest.fixture
def game_profile_b(db):
    """GameProfile B for multi-session tests."""
    return GameProfile.objects.create(game_name='GameB-P011')


@pytest.mark.django_db
class TestUnattendedSessionStart:
    """P-011: start creates a DB session record scoped to game_profile."""

    def test_start_creates_session_record(self, api_client_p011, game_profile_a):
        """POST start with game_profile_id creates UnattendedSession(RUNNING)."""
        res = _start(api_client_p011, game_profile_a.id, reason='p011-test')
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['status'] == 'running'
        assert 'session_id' in body
        assert body['game_profile_id'] == game_profile_a.id
        assert body['game_profile_name'] == game_profile_a.game_name
        assert body['started_at'] is not None
        # No devices configured in test → dispatched_count == 0
        assert body['dispatched_count'] == 0

        session = UnattendedSession.objects.get(id=body['session_id'])
        assert session.status == UnattendedSession.Status.RUNNING
        assert session.game_profile_id == game_profile_a.id
        assert session.started_at is not None
        assert session.stopped_at is None
        assert session.stop_reason == ''

    def test_start_missing_game_profile_id_returns_400(self, api_client_p011):
        """POST start without game_profile_id returns 400 missing_game_profile_id."""
        res = api_client_p011.post(reverse('unattended-start'), format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert res.data['code'] == ErrorCode.INVALID_PARAMS

    def test_start_already_running_returns_409(self, api_client_p011, game_profile_a):
        """Repeated start with the same game_profile returns 409 already_running."""
        _start(api_client_p011, game_profile_a.id)
        res = _start(api_client_p011, game_profile_a.id)
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.data['code'] == ErrorCode.INVALID_PARAMS
        # No duplicate session for this game_profile
        assert UnattendedSession.objects.filter(
            game_profile_id=game_profile_a.id,
        ).count() == 1

    def test_start_blocked_when_paused(self, api_client_p011, game_profile_a):
        """Start while the same game_profile has a PAUSED session returns 409."""
        start_res = _start(api_client_p011, game_profile_a.id)
        _pause(api_client_p011, _unwrap(start_res)['session_id'])
        res = _start(api_client_p011, game_profile_a.id)
        assert res.status_code == status.HTTP_409_CONFLICT
        assert UnattendedSession.objects.filter(
            game_profile_id=game_profile_a.id,
        ).count() == 1


@pytest.mark.django_db
class TestUnattendedSessionStop:
    """P-011: stop transitions a session to STOPPED by session_id."""

    def test_stop_transitions_session(self, api_client_p011, game_profile_a):
        """POST stop with session_id sets status=STOPPED + stopped_at + stop_reason."""
        start_res = _start(api_client_p011, game_profile_a.id)
        session_id = _unwrap(start_res)['session_id']

        res = _stop(api_client_p011, session_id, reason='manual')
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['status'] == 'stopped'
        assert body['stop_reason'] == 'manual'
        assert body['session_id'] == session_id
        assert body['stopped_at'] is not None

        session = UnattendedSession.objects.get(id=session_id)
        assert session.status == UnattendedSession.Status.STOPPED
        assert session.stopped_at is not None
        assert session.stop_reason == 'manual'
        assert session.paused_at is None  # cleared on stop

    def test_stop_session_not_found_returns_404(self, api_client_p011):
        """POST stop with unknown session_id returns 404 session_not_found."""
        res = _stop(api_client_p011, session_id=999999)
        assert res.status_code == status.HTTP_404_NOT_FOUND
        assert res.data['code'] == ErrorCode.NOT_FOUND

    def test_stop_already_stopped_returns_409(self, api_client_p011, game_profile_a):
        """POST stop on a STOPPED session returns 409 already_stopped."""
        start_res = _start(api_client_p011, game_profile_a.id)
        session_id = _unwrap(start_res)['session_id']
        _stop(api_client_p011, session_id)
        res = _stop(api_client_p011, session_id)
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.data['code'] == ErrorCode.INVALID_PARAMS


@pytest.mark.django_db
class TestUnattendedSessionPauseResume:
    """P-011: pause/resume transition DB status by session_id."""

    def test_pause_transitions_session(self, api_client_p011, game_profile_a):
        """POST pause with session_id sets status=PAUSED + paused_at."""
        start_res = _start(api_client_p011, game_profile_a.id)
        session_id = _unwrap(start_res)['session_id']

        res = _pause(api_client_p011, session_id)
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['status'] == 'paused'
        assert body['session_id'] == session_id

        session = UnattendedSession.objects.get(id=session_id)
        assert session.status == UnattendedSession.Status.PAUSED
        assert session.paused_at is not None

    def test_resume_transitions_session(self, api_client_p011, game_profile_a):
        """POST resume with session_id sets status=RUNNING + clears paused_at."""
        start_res = _start(api_client_p011, game_profile_a.id)
        session_id = _unwrap(start_res)['session_id']
        _pause(api_client_p011, session_id)

        res = _resume(api_client_p011, session_id)
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['status'] == 'running'
        assert body['session_id'] == session_id

        session = UnattendedSession.objects.get(id=session_id)
        assert session.status == UnattendedSession.Status.RUNNING
        assert session.paused_at is None

    def test_pause_session_not_found_returns_404(self, api_client_p011):
        """POST pause with unknown session_id returns 404 session_not_found."""
        res = _pause(api_client_p011, session_id=999999)
        assert res.status_code == status.HTTP_404_NOT_FOUND
        assert res.data['code'] == ErrorCode.NOT_FOUND

    def test_pause_not_running_returns_409(self, api_client_p011, game_profile_a):
        """POST pause on a PAUSED session returns 409 not_running."""
        start_res = _start(api_client_p011, game_profile_a.id)
        session_id = _unwrap(start_res)['session_id']
        _pause(api_client_p011, session_id)
        res = _pause(api_client_p011, session_id)
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.data['code'] == ErrorCode.INVALID_PARAMS

    def test_resume_session_not_found_returns_404(self, api_client_p011):
        """POST resume with unknown session_id returns 404 session_not_found."""
        res = _resume(api_client_p011, session_id=999999)
        assert res.status_code == status.HTTP_404_NOT_FOUND
        assert res.data['code'] == ErrorCode.NOT_FOUND

    def test_resume_not_paused_returns_409(self, api_client_p011, game_profile_a):
        """POST resume on a RUNNING session returns 409 not_paused."""
        start_res = _start(api_client_p011, game_profile_a.id)
        session_id = _unwrap(start_res)['session_id']
        res = _resume(api_client_p011, session_id)
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.data['code'] == ErrorCode.INVALID_PARAMS


@pytest.mark.django_db
class TestUnattendedStatusMapping:
    """P-011: status endpoint returns active_sessions list + aggregated mode_status.

    N112 contract: frontend ``useUnattendedStore.session`` expects
    mode_status in {"running", "paused", "stopped"} — preserved as the
    aggregated status across all active sessions.
    """

    def test_status_no_session_returns_stopped(self, api_client_p011):
        """status endpoint with no active session returns mode_status=stopped + empty list."""
        res = api_client_p011.get(reverse('unattended-status'))
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['mode_status'] == 'stopped'
        assert body['active_sessions'] == []

    def test_status_running_session_returns_running(self, api_client_p011, game_profile_a):
        """status endpoint with a RUNNING session returns mode_status=running + 1 entry."""
        _start(api_client_p011, game_profile_a.id)
        res = api_client_p011.get(reverse('unattended-status'))
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['mode_status'] == 'running'
        active = body['active_sessions']
        assert len(active) == 1
        assert active[0]['game_profile_id'] == game_profile_a.id
        assert active[0]['game_profile_name'] == game_profile_a.game_name
        assert active[0]['status'] == UnattendedSession.Status.RUNNING
        assert active[0]['mode_status'] == 'running'

    def test_status_paused_session_returns_paused(self, api_client_p011, game_profile_a):
        """status endpoint with a PAUSED session returns mode_status=paused."""
        start_res = _start(api_client_p011, game_profile_a.id)
        _pause(api_client_p011, _unwrap(start_res)['session_id'])
        res = api_client_p011.get(reverse('unattended-status'))
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['mode_status'] == 'paused'
        active = body['active_sessions']
        assert len(active) == 1
        assert active[0]['mode_status'] == 'paused'

    def test_status_stopped_session_returns_stopped(self, api_client_p011, game_profile_a):
        """status endpoint after stop returns mode_status=stopped + empty list."""
        start_res = _start(api_client_p011, game_profile_a.id)
        _stop(api_client_p011, _unwrap(start_res)['session_id'])
        res = api_client_p011.get(reverse('unattended-status'))
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['mode_status'] == 'stopped'
        assert body['active_sessions'] == []


@pytest.mark.django_db
class TestUnattendedSessionsList:
    """P-011: sessions list endpoint returns history (unchanged contract)."""

    def test_sessions_list_empty(self, api_client_p011):
        """GET sessions returns empty list when no sessions exist."""
        res = api_client_p011.get(reverse('unattended-sessions'))
        assert res.status_code == status.HTTP_200_OK
        assert _unwrap(res)['sessions'] == []

    def test_sessions_list_after_start(self, api_client_p011, game_profile_a):
        """GET sessions returns 1 entry after start."""
        _start(api_client_p011, game_profile_a.id)
        res = api_client_p011.get(reverse('unattended-sessions'))
        assert res.status_code == status.HTTP_200_OK
        sessions = _unwrap(res)['sessions']
        assert len(sessions) == 1
        session = sessions[0]
        assert session['status'] == UnattendedSession.Status.RUNNING
        assert session['started_at'] is not None

    def test_sessions_list_most_recent_first(self, api_client_p011, game_profile_a):
        """GET sessions returns most recent first (ordering = ['-created_at'])."""
        # First session (start + stop) — same game_profile is OK after stop
        start_res_1 = _start(api_client_p011, game_profile_a.id)
        _stop(api_client_p011, _unwrap(start_res_1)['session_id'])
        # Second session (running)
        _start(api_client_p011, game_profile_a.id)

        res = api_client_p011.get(reverse('unattended-sessions'))
        assert res.status_code == status.HTTP_200_OK
        sessions = _unwrap(res)['sessions']
        assert len(sessions) == 2
        # Most recent first
        assert sessions[0]['status'] == UnattendedSession.Status.RUNNING
        assert sessions[1]['status'] == UnattendedSession.Status.STOPPED


@pytest.mark.django_db
class TestUnattendedMultiSessionParallel:
    """P-011: multiple game_profiles can run unattended sessions in parallel."""

    def test_different_game_profiles_can_start_parallel(
        self, api_client_p011, game_profile_a, game_profile_b,
    ):
        """Start on two different game_profiles succeeds without 409."""
        res_a = _start(api_client_p011, game_profile_a.id)
        res_b = _start(api_client_p011, game_profile_b.id)
        assert res_a.status_code == status.HTTP_200_OK
        assert res_b.status_code == status.HTTP_200_OK
        assert _unwrap(res_a)['session_id'] != _unwrap(res_b)['session_id']
        # Two active sessions coexist
        assert UnattendedSession.objects.filter(
            status__in=[
                UnattendedSession.Status.RUNNING,
                UnattendedSession.Status.PAUSED,
            ],
        ).count() == 2

    def test_same_game_profile_second_start_returns_409(
        self, api_client_p011, game_profile_a, game_profile_b,
    ):
        """Second start on the same game_profile returns 409; different one succeeds."""
        res_a = _start(api_client_p011, game_profile_a.id)
        assert res_a.status_code == status.HTTP_200_OK

        # Same game_profile -> 409 already_running
        res_a2 = _start(api_client_p011, game_profile_a.id)
        assert res_a2.status_code == status.HTTP_409_CONFLICT
        assert res_a2.data['code'] == ErrorCode.INVALID_PARAMS

        # Different game_profile -> 200 (parallel allowed)
        res_b = _start(api_client_p011, game_profile_b.id)
        assert res_b.status_code == status.HTTP_200_OK

    def test_multi_session_independent_stop(
        self, api_client_p011, game_profile_a, game_profile_b,
    ):
        """Stopping one session does not affect the other."""
        res_a = _start(api_client_p011, game_profile_a.id)
        res_b = _start(api_client_p011, game_profile_b.id)
        sid_a = _unwrap(res_a)['session_id']
        sid_b = _unwrap(res_b)['session_id']

        # Stop only session A
        stop_res = _stop(api_client_p011, sid_a)
        assert stop_res.status_code == status.HTTP_200_OK

        # Session A is STOPPED, session B is still RUNNING
        sa = UnattendedSession.objects.get(id=sid_a)
        sb = UnattendedSession.objects.get(id=sid_b)
        assert sa.status == UnattendedSession.Status.STOPPED
        assert sb.status == UnattendedSession.Status.RUNNING

    def test_multi_session_independent_pause_resume(
        self, api_client_p011, game_profile_a, game_profile_b,
    ):
        """Pausing one session does not affect the other; both resume independently."""
        res_a = _start(api_client_p011, game_profile_a.id)
        res_b = _start(api_client_p011, game_profile_b.id)
        sid_a = _unwrap(res_a)['session_id']
        sid_b = _unwrap(res_b)['session_id']

        # Pause only session A
        pause_res = _pause(api_client_p011, sid_a)
        assert pause_res.status_code == status.HTTP_200_OK

        # Session A is PAUSED, session B is still RUNNING
        sa = UnattendedSession.objects.get(id=sid_a)
        sb = UnattendedSession.objects.get(id=sid_b)
        assert sa.status == UnattendedSession.Status.PAUSED
        assert sb.status == UnattendedSession.Status.RUNNING

        # Resume session A; pause session B (independent transitions)
        resume_res = _resume(api_client_p011, sid_a)
        assert resume_res.status_code == status.HTTP_200_OK
        pause_res_b = _pause(api_client_p011, sid_b)
        assert pause_res_b.status_code == status.HTTP_200_OK

        sa.refresh_from_db()
        sb.refresh_from_db()
        assert sa.status == UnattendedSession.Status.RUNNING
        assert sb.status == UnattendedSession.Status.PAUSED

    def test_multi_session_status_returns_list(
        self, api_client_p011, game_profile_a, game_profile_b,
    ):
        """status endpoint returns all active sessions in active_sessions list."""
        _start(api_client_p011, game_profile_a.id)
        _start(api_client_p011, game_profile_b.id)

        res = api_client_p011.get(reverse('unattended-status'))
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        # Aggregated mode_status is running (at least one RUNNING)
        assert body['mode_status'] == 'running'
        active = body['active_sessions']
        assert len(active) == 2
        # Both game_profiles represented
        gp_ids = {s['game_profile_id'] for s in active}
        assert gp_ids == {game_profile_a.id, game_profile_b.id}

    def test_multi_session_mixed_statuses_aggregated_running(
        self, api_client_p011, game_profile_a, game_profile_b,
    ):
        """Aggregated mode_status is 'running' when any session is RUNNING."""
        res_a = _start(api_client_p011, game_profile_a.id)
        _start(api_client_p011, game_profile_b.id)
        # Pause session A -> A=PAUSED, B=RUNNING -> aggregated = running
        _pause(api_client_p011, _unwrap(res_a)['session_id'])

        res = api_client_p011.get(reverse('unattended-status'))
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['mode_status'] == 'running'  # B is still RUNNING
        assert len(body['active_sessions']) == 2

    def test_multi_session_all_paused_aggregated_paused(
        self, api_client_p011, game_profile_a, game_profile_b,
    ):
        """Aggregated mode_status is 'paused' when all active sessions are PAUSED."""
        res_a = _start(api_client_p011, game_profile_a.id)
        res_b = _start(api_client_p011, game_profile_b.id)
        _pause(api_client_p011, _unwrap(res_a)['session_id'])
        _pause(api_client_p011, _unwrap(res_b)['session_id'])

        res = api_client_p011.get(reverse('unattended-status'))
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body['mode_status'] == 'paused'
        assert len(body['active_sessions']) == 2


# =========================================================================
# P-009 Phase 2: tick_unattended_session Celery task tests
# =========================================================================

# ---------------------------------------------------------------------------
# Fixtures for tick tests
# ---------------------------------------------------------------------------

@pytest.fixture
def tick_user(db):
    """User that triggers the unattended session."""
    return User.objects.create_user(
        username='tick_user', password='Pass123!',
    )


@pytest.fixture
def tick_game_profile(db):
    """GameProfile with an enabled default_task_chain TaskChain."""
    chain = TaskChain.objects.create(
        name='Tick Test Chain',
        is_enabled=True,
    )
    return GameProfile.objects.create(
        game_name='TickGame',
        default_task_chain=chain,
    )


@pytest.fixture
def online_agent(db):
    """Agent with status=ONLINE."""
    return Agent.objects.create(
        agent_id='tick-agent-001',
        hostname='tick-host',
        status=Agent.Status.ONLINE,
    )


@pytest.fixture
def idle_device(tick_game_profile, online_agent):
    """Device bound to game_profile + online agent."""
    return Device.objects.create(
        name='tick-device',
        device_type=Device.DeviceType.WINDOWS,
        status=Device.Status.ONLINE,
        agent=online_agent,
        game_profile=tick_game_profile,
    )


@pytest.fixture
def running_session(tick_user, tick_game_profile):
    """RUNNING UnattendedSession bound to game_profile (P-011 multi-session).

    P-011: every session is scoped to a GameProfile — `_tick_session` filters
    devices by `session.game_profile_id`. The fixture binds the session to
    the same `game_profile` fixture that `idle_device` uses so they match.
    """
    return UnattendedSession.objects.create(
        status=UnattendedSession.Status.RUNNING,
        started_at=timezone.now(),
        triggered_by=tick_user,
        game_profile=tick_game_profile,
    )


def _make_chain_execution(chain, user, device=None, account=None):
    """Helper: create a real TaskChainExecution row.

    Uses status=SUCCESS so the row does NOT trigger the tick's
    ``has_active`` guard (which checks for PENDING/RUNNING). This
    lets us pre-create the mock return value without blocking the
    device we want to test.
    """
    return TaskChainExecution.objects.create(
        chain=chain,
        triggered_by=user,
        device=device,
        game_account=account,
        status=TaskChainExecution.Status.SUCCESS,
    )


def _patch_dispatch_success(chain_exec):
    """Patch create_chain_execution_and_dispatch to return chain_exec."""
    return patch(
        'pipeline.services.create_chain_execution_and_dispatch',
        return_value=chain_exec,
    )


# ---------------------------------------------------------------------------
# Tick gate tests (no-session / paused / time-window)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_tick_no_session_does_nothing():
    """tick with no active session is a no-op (no exception)."""
    with patch('scheduler.engine.check_time_window', return_value=True):
        # Should not raise even with zero sessions
        tick_unattended_session()
    assert UnattendedSession.objects.count() == 0


@pytest.mark.django_db
def test_tick_paused_session_not_processed(running_session, idle_device, tick_user):
    """PAUSED session is not processed by the tick (only RUNNING)."""
    running_session.status = UnattendedSession.Status.PAUSED
    running_session.save(update_fields=['status'])

    chain_exec = _make_chain_execution(
        idle_device.game_profile.default_task_chain,
        tick_user,
    )

    with patch('scheduler.engine.check_time_window', return_value=True), \
         _patch_dispatch_success(chain_exec) as mock_dispatch:
        tick_unattended_session()
        mock_dispatch.assert_not_called()


@pytest.mark.django_db
def test_tick_outside_time_window_skipped(running_session, idle_device, tick_user):
    """tick returns early when check_time_window returns False."""
    chain_exec = _make_chain_execution(
        idle_device.game_profile.default_task_chain,
        tick_user,
    )

    with patch('scheduler.engine.check_time_window', return_value=False), \
         _patch_dispatch_success(chain_exec) as mock_dispatch:
        tick_unattended_session()
        mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# Dispatch success path tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_tick_dispatches_for_idle_device_no_rotation(
    running_session, idle_device, tick_user,
):
    """tick dispatches chain for idle device (legacy one-shot mode)."""
    # Bind a game_account to the device (legacy mode uses device.game_account)
    account = GameAccount.objects.create(
        owner=tick_user,
        game_profile=_gp('TickGame'),
        username='tick-acct-1',
        login_method='password',
    )
    idle_device.game_account = account
    idle_device.save(update_fields=['game_account'])

    chain_exec = _make_chain_execution(
        idle_device.game_profile.default_task_chain,
        tick_user,
        device=idle_device,
        account=account,
    )

    with patch('scheduler.engine.check_time_window', return_value=True), \
         _patch_dispatch_success(chain_exec) as mock_dispatch:
        tick_unattended_session()

    mock_dispatch.assert_called_once()
    # Account ID should be tracked on session
    running_session.refresh_from_db()
    assert account.id in (running_session.dispatched_account_ids or [])
    # Chain execution linked to session
    assert chain_exec in running_session.active_chain_executions.all()


@pytest.mark.django_db
def test_tick_skips_already_dispatched_account_no_rotation(
    running_session, idle_device, tick_user,
):
    """Legacy mode: already-dispatched account is not dispatched again."""
    account = GameAccount.objects.create(
        owner=tick_user,
        game_profile=_gp('TickGame'),
        username='tick-acct-2',
        login_method='password',
    )
    idle_device.game_account = account
    idle_device.save(update_fields=['game_account'])

    # Pre-mark account as dispatched on session
    running_session.dispatched_account_ids = [account.id]
    running_session.save(update_fields=['dispatched_account_ids'])

    chain_exec = _make_chain_execution(
        idle_device.game_profile.default_task_chain,
        tick_user,
    )

    with patch('scheduler.engine.check_time_window', return_value=True), \
         _patch_dispatch_success(chain_exec) as mock_dispatch:
        tick_unattended_session()

    mock_dispatch.assert_not_called()


@pytest.mark.django_db
def test_tick_skips_device_with_active_chain_execution(
    running_session, idle_device, tick_user,
):
    """Device that already has a PENDING/RUNNING chain_execution is skipped."""
    account = GameAccount.objects.create(
        owner=tick_user,
        game_profile=_gp('TickGame'),
        username='tick-acct-3',
        login_method='password',
    )
    idle_device.game_account = account
    idle_device.save(update_fields=['game_account'])

    # Create an existing RUNNING chain_execution for this device
    TaskChainExecution.objects.create(
        chain=idle_device.game_profile.default_task_chain,
        triggered_by=tick_user,
        device=idle_device,
        status=TaskChainExecution.Status.RUNNING,
    )

    chain_exec = _make_chain_execution(
        idle_device.game_profile.default_task_chain,
        tick_user,
    )

    with patch('scheduler.engine.check_time_window', return_value=True), \
         _patch_dispatch_success(chain_exec) as mock_dispatch:
        tick_unattended_session()

    mock_dispatch.assert_not_called()


@pytest.mark.django_db
def test_tick_skips_disabled_chain(
    running_session, idle_device, tick_user,
):
    """Disabled chain (is_enabled=False) is skipped."""
    chain = idle_device.game_profile.default_task_chain
    chain.is_enabled = False
    chain.save(update_fields=['is_enabled'])

    account = GameAccount.objects.create(
        owner=tick_user,
        game_profile=_gp('TickGame'),
        username='tick-acct-4',
        login_method='password',
    )
    idle_device.game_account = account
    idle_device.save(update_fields=['game_account'])

    chain_exec = _make_chain_execution(chain, tick_user)

    with patch('scheduler.engine.check_time_window', return_value=True), \
         _patch_dispatch_success(chain_exec) as mock_dispatch:
        tick_unattended_session()

    mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# Rotation rule tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_tick_dispatches_with_rotation_rule(
    running_session, idle_device, tick_user,
):
    """tick with rotation_rule picks next undispatched account.

    The exact account picked depends on ``calculate_account_order`` which,
    for 'sequential' strategy without an ``account_order`` field, returns
    the queryset as-is (GameAccount.Meta.ordering = ['-created_at']).
    Rather than asserting on a specific account, we compute the expected
    first pick and assert against it.
    """
    from scheduler.engine import calculate_account_order

    acct1 = GameAccount.objects.create(
        owner=tick_user, game_profile=_gp('TickGame'),
        username='rot-acct-1', login_method='password',
    )
    acct2 = GameAccount.objects.create(
        owner=tick_user, game_profile=_gp('TickGame'),
        username='rot-acct-2', login_method='password',
    )

    rotation = GameAccountRotation.objects.create(
        name='tick-rotation',
        rotation_strategy='sequential',
    )
    rotation.accounts.add(acct1, acct2)

    running_session.rotation_rule = rotation
    running_session.save(update_fields=['rotation_rule'])

    # Compute the expected first pick (deterministic given the rotation rule)
    ordered = calculate_account_order(rotation, list(rotation.accounts.all()))
    expected_account = ordered[0]

    chain_exec = _make_chain_execution(
        idle_device.game_profile.default_task_chain,
        tick_user,
        device=idle_device,
        account=expected_account,
    )

    with patch('scheduler.engine.check_time_window', return_value=True), \
         _patch_dispatch_success(chain_exec) as mock_dispatch:
        tick_unattended_session()

    mock_dispatch.assert_called_once()
    kwargs = mock_dispatch.call_args.kwargs
    assert kwargs['game_account_id'] == expected_account.id
    running_session.refresh_from_db()
    assert expected_account.id in (running_session.dispatched_account_ids or [])


@pytest.mark.django_db
def test_tick_rotation_skips_already_dispatched(
    running_session, idle_device, tick_user,
):
    """Rotation: already-dispatched account is skipped, next one is used."""
    acct1 = GameAccount.objects.create(
        owner=tick_user, game_profile=_gp('TickGame'),
        username='rot-acct-3', login_method='password',
    )
    acct2 = GameAccount.objects.create(
        owner=tick_user, game_profile=_gp('TickGame'),
        username='rot-acct-4', login_method='password',
    )

    rotation = GameAccountRotation.objects.create(
        name='tick-rotation-2',
        rotation_strategy='sequential',
    )
    rotation.accounts.add(acct1, acct2)

    running_session.rotation_rule = rotation
    # Pre-mark acct1 as dispatched
    running_session.dispatched_account_ids = [acct1.id]
    running_session.save(update_fields=['rotation_rule', 'dispatched_account_ids'])

    chain_exec = _make_chain_execution(
        idle_device.game_profile.default_task_chain,
        tick_user,
        device=idle_device,
        account=acct2,
    )

    with patch('scheduler.engine.check_time_window', return_value=True), \
         _patch_dispatch_success(chain_exec) as mock_dispatch:
        tick_unattended_session()

    mock_dispatch.assert_called_once()
    kwargs = mock_dispatch.call_args.kwargs
    # Should dispatch acct2 (acct1 already dispatched)
    assert kwargs['game_account_id'] == acct2.id


@pytest.mark.django_db
def test_tick_rotation_all_dispatched_skips(
    running_session, idle_device, tick_user,
):
    """Rotation: when all accounts already dispatched, no dispatch happens."""
    acct1 = GameAccount.objects.create(
        owner=tick_user, game_profile=_gp('TickGame'),
        username='rot-acct-5', login_method='password',
    )

    rotation = GameAccountRotation.objects.create(
        name='tick-rotation-3',
        rotation_strategy='sequential',
    )
    rotation.accounts.add(acct1)

    running_session.rotation_rule = rotation
    running_session.dispatched_account_ids = [acct1.id]
    running_session.save(update_fields=['rotation_rule', 'dispatched_account_ids'])

    chain_exec = _make_chain_execution(
        idle_device.game_profile.default_task_chain,
        tick_user,
    )

    with patch('scheduler.engine.check_time_window', return_value=True), \
         _patch_dispatch_success(chain_exec) as mock_dispatch:
        tick_unattended_session()

    mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_tick_handles_dispatch_error(
    running_session, idle_device, tick_user,
):
    """ChainDispatchError is caught; tick continues without crashing."""
    from pipeline.services import ChainDispatchError

    account = GameAccount.objects.create(
        owner=tick_user, game_profile=_gp('TickGame'),
        username='tick-acct-err', login_method='password',
    )
    idle_device.game_account = account
    idle_device.save(update_fields=['game_account'])

    with patch('scheduler.engine.check_time_window', return_value=True), \
         patch(
             'pipeline.services.create_chain_execution_and_dispatch',
             side_effect=ChainDispatchError('simulated failure'),
         ):
        # Should not raise
        tick_unattended_session()

    # Account ID should NOT be tracked (dispatch failed)
    running_session.refresh_from_db()
    assert account.id not in (running_session.dispatched_account_ids or [])
    # No chain execution linked
    assert running_session.active_chain_executions.count() == 0


@pytest.mark.django_db
def test_tick_continues_after_device_exception(running_session, tick_user):
    """tick continues to next device after one device raises."""
    # Set up 2 devices sharing the same GameProfile/chain as running_session
    # (P-011: _tick_session filters devices by session.game_profile_id, so
    # the devices must be bound to the session's game_profile to be seen).
    # The dispatch mock fails for the first call and succeeds for the
    # second; both devices must be attempted, and the successful one's
    # account must be tracked.
    profile = running_session.game_profile
    agent = Agent.objects.create(
        agent_id='tick-agent-002',
        hostname='tick-host-2',
        status=Agent.Status.ONLINE,
    )

    dev1 = Device.objects.create(
        name='dev-fail', device_type=Device.DeviceType.WINDOWS,
        status=Device.Status.ONLINE,
        agent=agent, game_profile=profile,
    )
    dev2 = Device.objects.create(
        name='dev-ok', device_type=Device.DeviceType.WINDOWS,
        status=Device.Status.ONLINE,
        agent=agent, game_profile=profile,
    )

    acct1 = GameAccount.objects.create(
        owner=tick_user, game_profile=profile,
        username='dev1-acct', login_method='password',
    )
    acct2 = GameAccount.objects.create(
        owner=tick_user, game_profile=profile,
        username='dev2-acct', login_method='password',
    )
    dev1.game_account = acct1
    dev1.save(update_fields=['game_account'])
    dev2.game_account = acct2
    dev2.save(update_fields=['game_account'])

    chain_exec_ok = _make_chain_execution(
        profile.default_task_chain, tick_user, device=dev2, account=acct2,
    )

    from pipeline.services import ChainDispatchError

    dispatch_calls = [0]

    def side_effect(*args, **kwargs):
        # Order-independent: fail when called with acct1, succeed with acct2.
        # Device.Meta ordering = ['-id'] so iteration order is not creation
        # order; this side_effect is robust to either order.
        dispatch_calls[0] += 1
        if kwargs.get('game_account_id') == acct1.id:
            raise ChainDispatchError('dev1 fails')
        return chain_exec_ok

    with patch('scheduler.engine.check_time_window', return_value=True), \
         patch(
             'pipeline.services.create_chain_execution_and_dispatch',
             side_effect=side_effect,
         ):
        tick_unattended_session()

    # Both devices were attempted
    assert dispatch_calls[0] == 2
    # acct2 (the successful one) is tracked; acct1 is not (dispatch failed)
    running_session.refresh_from_db()
    assert acct2.id in (running_session.dispatched_account_ids or [])
    assert acct1.id not in (running_session.dispatched_account_ids or [])


@pytest.mark.django_db
def test_tick_scopes_devices_by_session_game_profile(
    running_session, idle_device, tick_user,
):
    """P-011: tick only dispatches devices bound to session.game_profile.

    Regression guard for the `_tick_session` bug where the device query
    lacked `game_profile_id=session.game_profile_id` filtering — without
    it, a session for game_profile A would also dispatch devices bound to
    game_profile B (cross-session candidate contamination).
    """
    # Create a second GameProfile + device that should NOT be touched by
    # running_session's tick (running_session is bound to the `game_profile`
    # fixture via the running_session fixture).
    other_profile = GameProfile.objects.create(
        game_name='OtherGame',
        default_task_chain=TaskChain.objects.create(
            name='Other Chain', is_enabled=True,
        ),
    )
    other_agent = Agent.objects.create(
        agent_id='other-agent',
        hostname='other-host',
        status=Agent.Status.ONLINE,
    )
    other_device = Device.objects.create(
        name='other-device',
        device_type=Device.DeviceType.WINDOWS,
        status=Device.Status.ONLINE,
        agent=other_agent,
        game_profile=other_profile,
    )
    other_account = GameAccount.objects.create(
        owner=tick_user,
        game_profile=other_profile,
        username='other-acct',
        login_method='password',
    )
    other_device.game_account = other_account
    other_device.save(update_fields=['game_account'])

    # running_session's own device (idle_device) gets a real account too
    own_account = GameAccount.objects.create(
        owner=tick_user,
        game_profile=running_session.game_profile,
        username='own-acct',
        login_method='password',
    )
    idle_device.game_account = own_account
    idle_device.save(update_fields=['game_account'])

    own_chain_exec = _make_chain_execution(
        running_session.game_profile.default_task_chain,
        tick_user,
        device=idle_device,
        account=own_account,
    )

    dispatched_device_ids: list[int] = []

    def side_effect(*args, **kwargs):
        chain_exec = own_chain_exec
        # Persist the dispatched device so we can assert which device was used
        if kwargs.get('device_id') is not None:
            dispatched_device_ids.append(kwargs['device_id'])
        return chain_exec

    with patch('scheduler.engine.check_time_window', return_value=True), \
         patch(
             'pipeline.services.create_chain_execution_and_dispatch',
             side_effect=side_effect,
         ):
        tick_unattended_session()

    # Only idle_device (bound to running_session.game_profile) was dispatched
    assert dispatched_device_ids == [idle_device.id]
    # other_device was NOT touched
    assert other_device.id not in dispatched_device_ids
    # other_account is not tracked on running_session
    running_session.refresh_from_db()
    tracked = running_session.dispatched_account_ids or []
    assert own_account.id in tracked
    assert other_account.id not in tracked


# =========================================================================
# Recovery Engine Tests (from test_recovery.py)
# =========================================================================

class TestRecoveryEngine(TestCase):
    """恢复策略执行引擎测试"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='recovery_test',
            password='testpass123',
        )

    def test_step_failure_retry_with_backoff(self):
        """TC-7.4-1: handle_step_failure 返回重试信息"""
        result = handle_step_failure(1, '点击超时')
        self.assertIn('success', result)
        self.assertEqual(result['action'], 'retry')

    def test_task_failure_below_threshold_continues(self):
        """TC-7.4-2: 任务连续失败未达阈值继续执行"""
        result = handle_task_failure(1, consecutive_failures=2)
        self.assertEqual(result['action'], 'continue')

    def test_task_failure_above_threshold_triggers_skip(self):
        """TC-7.4-3: 任务连续失败达阈值触发跳过"""
        result = handle_task_failure(1, consecutive_failures=5)
        self.assertEqual(result['action'], 'skip')

    def test_app_freeze_detection_triggers(self):
        """TC-7.4-4: 应用卡死超时触发恢复"""
        result = handle_app_freeze(1, freeze_duration_seconds=200)
        self.assertIn(result['action'], ['restart_app', 'relogin', 'notify_only'])

    def test_agent_timeout_triggers_system_recovery(self):
        """TC-7.4-5: Agent 超时触发系统级恢复"""
        result = handle_agent_timeout('test-agent', timeout_duration_seconds=600)
        self.assertEqual(result['action'], 'system_recovery')

    def test_get_strategy_config_returns_defaults(self):
        """get_strategy_config 返回默认值"""
        config = get_strategy_config()
        self.assertIn('stepLevel', config)
        self.assertIn('taskLevel', config)
        self.assertIn('appLevel', config)
        self.assertIn('deviceLevel', config)
        self.assertIn('systemLevel', config)


# =========================================================================
# P-020-A: RecoveryLog ViewSet API 测试
# =========================================================================

UserModel = get_user_model()


@pytest.fixture
def auth_client(db):
    """创建已认证的 API 客户端"""
    client = APIClient()
    user, _ = UserModel.objects.get_or_create(
        username="test_recovery_log",
        defaults={"email": "test_recovery@gaf.local", "is_active": True},
    )
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def sample_logs(db):
    """创建测试用的 RecoveryLog 样本数据 (5 条, 跨多 level/多 success)

    显式设置 created_at 让排序测试稳定 (避免 auto_now_add 同 microsecond)
    """
    base_time = timezone.now() - timedelta(minutes=10)
    logs = []
    fixtures = [
        ("step", "点击失败", "重试 3/3 次", True, {"execution_step_id": 1}),
        ("task", "任务失败 5 次", "跳过当前任务", True, {"task_execution_id": 1}),
        ("app", "设备 1 卡死 200s", "重启游戏应用", True, {"device_id": 1}),
        ("device", "设备 2 崩溃", "重启模拟器", False, {"device_id": 2}),
        ("system", "Agent timeout", "通知+离线+重分配", True, {"agent_id": "a1"}),
    ]
    for idx, (level, event, action, success, details) in enumerate(fixtures):
        log = RecoveryLog.objects.create(
            recovery_level=level,
            trigger_event=event,
            action_taken=action,
            success=success,
            details=details,
        )
        # 强制 created_at 错开 (idx 0 最旧, idx 4 最新)
        RecoveryLog.objects.filter(pk=log.pk).update(created_at=base_time + timedelta(seconds=idx))
        log.refresh_from_db()
        logs.append(log)
    return logs


@pytest.mark.django_db
class TestRecoveryLogList:
    """测试 RecoveryLog 列表 API"""

    def test_list_returns_all_logs(self, auth_client, sample_logs):
        """GET /api/scheduler/recovery-logs/ 应返回全部 5 条记录"""
        url = reverse("recovery-log-list")
        res = auth_client.get(url)
        assert res.status_code == status.HTTP_200_OK
        # DRF 默认分页, 但我们的 ViewSet 未配 pagination_class, 应直接返回 list
        # 兼容: 既支持 list 也支持 paginated dict
        results = _get_results(res)
        assert len(results) == 5

    def test_list_ordering_desc_by_created_at(self, auth_client, sample_logs):
        """默认应按 -created_at 排序 (最新在前)"""
        url = reverse("recovery-log-list")
        res = auth_client.get(url)
        results = _get_results(res)
        # 第一条应 id 最大的 (最后创建的)
        ids = [r["id"] for r in results]
        assert ids == sorted(ids, reverse=True)

    def test_filter_by_recovery_level(self, auth_client, sample_logs):
        """?recovery_level=step 应只返回 step 级别"""
        url = reverse("recovery-log-list") + "?recovery_level=step"
        res = auth_client.get(url)
        results = _get_results(res)
        assert len(results) == 1
        assert results[0]["recovery_level"] == "step"
        assert results[0]["recovery_level_display"] == "步骤级"

    def test_filter_by_success_true(self, auth_client, sample_logs):
        """?success=true 应只返回成功的 (5 条样本中 4 条 success=True)"""
        url = reverse("recovery-log-list") + "?success=true"
        res = auth_client.get(url)
        results = _get_results(res)
        assert len(results) == 4
        for r in results:
            assert r["success"] is True

    def test_filter_by_success_false(self, auth_client, sample_logs):
        """?success=false 应只返回失败的 (5 条样本中 1 条 success=False)"""
        url = reverse("recovery-log-list") + "?success=false"
        res = auth_client.get(url)
        results = _get_results(res)
        assert len(results) == 1
        assert results[0]["success"] is False
        assert results[0]["recovery_level"] == "device"


@pytest.mark.django_db
class TestRecoveryLogDetail:
    """测试 RecoveryLog 详情 API"""

    def test_retrieve_single_log(self, auth_client, sample_logs):
        """GET /api/scheduler/recovery-logs/{id}/ 应返回单条记录"""
        log = sample_logs[0]
        url = reverse("recovery-log-detail", kwargs={"pk": log.pk})
        res = auth_client.get(url)
        assert res.status_code == status.HTTP_200_OK
        body = _unwrap(res)
        assert body["id"] == log.id
        assert body["trigger_event"] == "点击失败"
        assert body["action_taken"] == "重试 3/3 次"
        assert body["details"] == {"execution_step_id": 1}

    def test_retrieve_404_not_found(self, auth_client, sample_logs):
        """访问不存在的 ID 应返回 404"""
        url = reverse("recovery-log-detail", kwargs={"pk": 99999})
        res = auth_client.get(url)
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_serialized_fields_complete(self, auth_client, sample_logs):
        """序列化应包含全部 8 个字段"""
        log = sample_logs[2]  # app level
        url = reverse("recovery-log-detail", kwargs={"pk": log.pk})
        res = auth_client.get(url)
        body = _unwrap(res)
        expected_fields = {
            "id",
            "recovery_level",
            "recovery_level_display",
            "trigger_event",
            "action_taken",
            "success",
            "details",
            "created_at",
        }
        assert set(body.keys()) == expected_fields
        assert body["recovery_level_display"] == "应用级"


@pytest.mark.django_db
class TestRecoveryLogAuth:
    """测试 RecoveryLog API 认证"""

    def test_unauthenticated_returns_401(self, sample_logs):
        """未认证请求应返回 401"""
        client = APIClient()  # 未 force_authenticate
        url = reverse("recovery-log-list")
        res = client.get(url)
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_readonly_no_post(self, auth_client, sample_logs):
        """只读 ViewSet 不应接受 POST"""
        url = reverse("recovery-log-list")
        res = auth_client.post(url, data={}, format='json')
        # ReadOnlyModelViewSet 不允许 POST, 应返回 405
        assert res.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# =========================================================================
# P-048: 5 层恢复引擎接线测试
# =========================================================================

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _make_agent(*, status=Agent.Status.ONLINE, last_heartbeat=None, agent_id='agent-1'):
    """Create a minimal Agent for testing."""
    return Agent.objects.create(
        agent_id=agent_id,
        hostname=f'host-{agent_id}',
        status=status,
        last_heartbeat=last_heartbeat or timezone.now(),
    )


def _make_device(agent, *, status=Device.Status.ONLINE, name='test-device'):
    """Create a minimal Device bound to an agent."""
    return Device.objects.create(
        agent=agent,
        name=name,
        device_type=Device.DeviceType.WINDOWS,
        status=status,
    )


# ─────────────────────────────────────────────
# 1. Device crash recovery signal
# ─────────────────────────────────────────────


class TestDeviceCrashRecoverySignal(TestCase):
    """agents/signals.py: trigger_device_crash_recovery"""

    def setUp(self):
        self.agent = _make_agent()
        self.device = _make_device(self.agent, status=Device.Status.ONLINE)

    def test_online_to_error_triggers_handle_device_crash(self):
        """Device.status ONLINE → ERROR: handle_device_crash 应被调用 1 次."""
        with (
            patch('scheduler.recovery_engine.handle_device_crash') as mock_handler,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.device.status = Device.Status.ERROR
            self.device.save(update_fields=['status'])

        mock_handler.assert_called_once_with(device_id=self.device.id)

    def test_error_to_error_does_not_trigger(self):
        """ERROR → ERROR: 不应重复触发 (避免 recovery storm)."""
        # 先把 device 置为 ERROR
        with (
            patch('scheduler.recovery_engine.handle_device_crash') as mock_first,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.device.status = Device.Status.ERROR
            self.device.save(update_fields=['status'])
        self.assertEqual(mock_first.call_count, 1)

        # 再次保存, 仍是 ERROR (改 extra_info 触发 full save)
        with (
            patch('scheduler.recovery_engine.handle_device_crash') as mock_second,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.device.extra_info = {'note': 'still broken'}
            self.device.save()

        mock_second.assert_not_called()

    def test_error_to_online_does_not_trigger(self):
        """ERROR → ONLINE: 恢复成功路径, 不应触发 crash recovery."""
        # 先置为 ERROR
        with self.captureOnCommitCallbacks(execute=True):
            self.device.status = Device.Status.ERROR
            self.device.save(update_fields=['status'])

        # 再恢复为 ONLINE
        with (
            patch('scheduler.recovery_engine.handle_device_crash') as mock_handler,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.device.status = Device.Status.ONLINE
            self.device.save(update_fields=['status'])

        mock_handler.assert_not_called()

    def test_update_fields_excluding_status_skips_trigger(self):
        """update_fields 不含 status 时跳过 crash recovery."""
        with (
            patch('scheduler.recovery_engine.handle_device_crash') as mock_handler,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.device.name = 'renamed-device'
            self.device.save(update_fields=['name'])

        mock_handler.assert_not_called()

    def test_created_device_skips_trigger(self):
        """新建设备 (created=True) 不触发 crash recovery (由 register 流程处理)."""
        with (
            patch('scheduler.recovery_engine.handle_device_crash') as mock_handler,
            self.captureOnCommitCallbacks(execute=True),
        ):
            _make_device(self.agent, name='brand-new', status=Device.Status.ERROR)

        mock_handler.assert_not_called()


# ─────────────────────────────────────────────
# 2. App freeze detection Celery task
# ─────────────────────────────────────────────


class TestDetectAppFreezeTask(TestCase):
    """scheduler/tasks.py: detect_app_freeze"""

    def setUp(self):
        self.user = User.objects.create_user(username='p048_user', password='test123')
        self.agent = _make_agent(agent_id='freeze-agent')
        self.device = _make_device(self.agent, name='freeze-device')
        self.task = Task.objects.create(name='p048-freeze-task')
        self.execution = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            device=self.device,
            triggered_by=self.user,
            status=TaskExecution.Status.RUNNING,
        )

    def _make_frozen_step(self, freeze_seconds=200):
        """Create a RUNNING ExecutionStep started ``freeze_seconds`` ago."""
        step = ExecutionStep.objects.create(
            task_result=self.execution,
            step_index=0,
            node_id='frozen-node',
            step_type='pipeline_node',
            step_name='frozen-node',
            status=ExecutionStep.Status.RUNNING,
        )
        # Backdate started_at so the step looks frozen
        step.started_at = timezone.now() - timedelta(seconds=freeze_seconds)
        step.save(update_fields=['started_at'])
        return step

    def test_frozen_step_triggers_handle_app_freeze(self):
        """RUNNING step 超 freezeTimeoutSeconds 应触发 handle_app_freeze."""
        self._make_frozen_step(freeze_seconds=200)  # > default 120s

        with patch('scheduler.recovery_engine.handle_app_freeze') as mock_handler:
            from scheduler.tasks import detect_app_freeze
            detect_app_freeze()

        mock_handler.assert_called_once()
        call_kwargs = mock_handler.call_args.kwargs
        self.assertEqual(call_kwargs['device_id'], self.device.id)
        self.assertGreaterEqual(call_kwargs['freeze_duration_seconds'], 120)

    def test_short_running_step_does_not_trigger(self):
        """RUNNING step 未达 freezeTimeoutSeconds 不应触发."""
        self._make_frozen_step(freeze_seconds=30)  # < default 120s

        with patch('scheduler.recovery_engine.handle_app_freeze') as mock_handler:
            from scheduler.tasks import detect_app_freeze
            detect_app_freeze()

        mock_handler.assert_not_called()

    def test_freeze_detection_disabled_skips_scan(self):
        """freezeDetection=False 时跳过整个扫描."""
        self._make_frozen_step(freeze_seconds=300)

        with (
            patch(
                'scheduler.recovery_engine.get_strategy_config',
                return_value={'appLevel': {'freezeDetection': False}},
            ),
            patch('scheduler.recovery_engine.handle_app_freeze') as mock_handler,
        ):
            from scheduler.tasks import detect_app_freeze
            detect_app_freeze()

        mock_handler.assert_not_called()

    def test_dedup_skips_recent_recovery_log(self):
        """同设备在 dedup 窗口内已有 app-level RecoveryLog 时跳过."""
        self._make_frozen_step(freeze_seconds=200)

        # 预先写一条 app-level RecoveryLog, target_id = device.id
        RecoveryLog.objects.create(
            recovery_level='app',
            trigger_event='device 1 游戏卡死 200 秒',
            action_taken='ActionChain: 2/2 步完成',
            success=True,
            details={'target_id': self.device.id},
        )

        with patch('scheduler.recovery_engine.handle_app_freeze') as mock_handler:
            from scheduler.tasks import detect_app_freeze
            detect_app_freeze()

        mock_handler.assert_not_called()

    def test_terminal_task_execution_not_scanned(self):
        """TaskExecution 已 FAILED 时, 其 RUNNING step 不会被扫描."""
        self._make_frozen_step(freeze_seconds=200)
        self.execution.status = TaskExecution.Status.FAILED
        self.execution.save(update_fields=['status'])

        with patch('scheduler.recovery_engine.handle_app_freeze') as mock_handler:
            from scheduler.tasks import detect_app_freeze
            detect_app_freeze()

        mock_handler.assert_not_called()

    def test_device_without_device_id_skipped(self):
        """TaskExecution.device_id 为 null 时跳过 (无法 map 到 device-level chain)."""
        self.execution.device = None
        self.execution.save(update_fields=['device'])
        self._make_frozen_step(freeze_seconds=200)

        with patch('scheduler.recovery_engine.handle_app_freeze') as mock_handler:
            from scheduler.tasks import detect_app_freeze
            detect_app_freeze()

        mock_handler.assert_not_called()


# ─────────────────────────────────────────────
# 3. Heartbeat → handle_agent_timeout wiring
# ─────────────────────────────────────────────


class TestHeartbeatAgentTimeoutWiring(TestCase):
    """tasks/heartbeat.py: check_agent_heartbeats → handle_agent_timeout"""

    def setUp(self):
        # ONLINE agent with stale heartbeat (>30s threshold)
        self.stale_heartbeat = timezone.now() - timedelta(seconds=60)
        self.agent = _make_agent(
            agent_id='stale-agent',
            status=Agent.Status.ONLINE,
            last_heartbeat=self.stale_heartbeat,
        )

    def test_stale_agent_triggers_handle_agent_timeout(self):
        """ONLINE agent 心跳超时 → 调用 handle_agent_timeout."""
        with patch('scheduler.recovery_engine.handle_agent_timeout') as mock_handler:
            mock_handler.return_value = {
                'success': True,
                'action': 'system_recovery',
                'details': {},
            }
            from tasks.heartbeat import check_agent_heartbeats
            check_agent_heartbeats()

        mock_handler.assert_called_once()
        call_kwargs = mock_handler.call_args.kwargs
        self.assertEqual(call_kwargs['agent_id'], self.agent.agent_id)
        # timeout_duration_seconds 应是 now - last_heartbeat 的秒数
        self.assertGreaterEqual(call_kwargs['timeout_duration_seconds'], 30)

    def test_agent_marked_offline_after_timeout(self):
        """超时 agent 应被标记为 OFFLINE (detection 层职责)."""
        with patch('scheduler.recovery_engine.handle_agent_timeout') as mock_handler:
            mock_handler.return_value = {
                'success': True,
                'action': 'system_recovery',
            }
            from tasks.heartbeat import check_agent_heartbeats
            check_agent_heartbeats()

        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, Agent.Status.OFFLINE)

    def test_never_heartbeated_agent_marked_offline(self):
        """ONLINE agent 从未心跳 (last_heartbeat=None) 也应被标记 OFFLINE.

        Regression (2026-08-27): 原实现 ``last_heartbeat__lt=threshold`` 在 SQL 中
        不匹配 NULL (NULL < timestamp 结果为 NULL, Django filter 不会选中),
        导致扫描时未心跳过的 legacy Agent 记录永远保持 ONLINE, 工作台显示
        幻影 agent。修复后 IS NULL 与超时联合判定。
        """
        # NOTE: 不能走 _make_agent — 它会把 last_heartbeat=None 兜底成当前时间。
        # 这里直接建一条真的"从未心跳"记录 (last_heartbeat IS NULL)。
        phantom_agent = Agent.objects.create(
            agent_id='phantom-agent',
            hostname='host-phantom-agent',
            status=Agent.Status.ONLINE,
            last_heartbeat=None,
        )
        # Agent 离线后其管理的窗口必须联动离线 (一致性, mark_agent_devices_offline)
        phantom_device = _make_device(phantom_agent, name='phantom-window')
        with patch('scheduler.recovery_engine.handle_agent_timeout') as mock_handler:
            mock_handler.return_value = {
                'success': True,
                'action': 'system_recovery',
            }
            from tasks.heartbeat import check_agent_heartbeats
            check_agent_heartbeats()

        # setUp 的 stale-agent 也会同时被检测, 这里只断言 phantom-agent 被处理到
        phantom_calls = [
            c.kwargs for c in mock_handler.call_args_list
            if c.kwargs.get('agent_id') == 'phantom-agent'
        ]
        self.assertEqual(len(phantom_calls), 1)
        phantom_kwargs = phantom_calls[0]
        # never-heartbeated → 按最大超时处理, 不应为负或极小
        self.assertGreaterEqual(phantom_kwargs['timeout_duration_seconds'], 30)
        phantom_agent.refresh_from_db()
        self.assertEqual(phantom_agent.status, Agent.Status.OFFLINE)
        # 窗口联动离线
        phantom_device.refresh_from_db()
        self.assertEqual(phantom_device.status, Device.Status.OFFLINE)

    def test_waiting_action_fails_running_executions(self):
        """handle_agent_timeout 返回 'waiting' (grace period 未到) → 标记 task FAILED."""
        user = User.objects.create_user(username='hb_user', password='test123')
        task = Task.objects.create(name='hb-task')
        execution = TaskExecution.objects.create(
            task=task,
            agent=self.agent,
            triggered_by=user,
            status=TaskExecution.Status.RUNNING,
        )

        with patch('scheduler.recovery_engine.handle_agent_timeout') as mock_handler:
            mock_handler.return_value = {
                'success': True,
                'action': 'waiting',
            }
            from tasks.heartbeat import check_agent_heartbeats
            check_agent_heartbeats()

        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.FAILED)

    def test_handle_agent_timeout_exception_falls_back_to_fail_executions(self):
        """handle_agent_timeout 抛异常 → fallback 直接 fail task execution."""
        user = User.objects.create_user(username='hb_user2', password='test123')
        task = Task.objects.create(name='hb-task-2')
        execution = TaskExecution.objects.create(
            task=task,
            agent=self.agent,
            triggered_by=user,
            status=TaskExecution.Status.RUNNING,
        )

        with patch('scheduler.recovery_engine.handle_agent_timeout') as mock_handler:
            mock_handler.side_effect = RuntimeError('recovery engine down')
            from tasks.heartbeat import check_agent_heartbeats
            check_agent_heartbeats()

        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.FAILED)

    def test_healthy_agent_not_affected(self):
        """ONLINE agent 心跳未超时 → 不应被处理."""
        fresh_agent = _make_agent(
            agent_id='fresh-agent',
            status=Agent.Status.ONLINE,
            last_heartbeat=timezone.now(),
        )

        with patch('scheduler.recovery_engine.handle_agent_timeout') as mock_handler:
            from tasks.heartbeat import check_agent_heartbeats
            check_agent_heartbeats()

        # stale_agent 应被处理 (setUp 创建的)
        # fresh_agent 不应被处理
        mock_handler.assert_called_once_with(
            agent_id=self.agent.agent_id,
            timeout_duration_seconds=mock_handler.call_args.kwargs['timeout_duration_seconds'],
        )
        fresh_agent.refresh_from_db()
        self.assertEqual(fresh_agent.status, Agent.Status.ONLINE)


# ─────────────────────────────────────────────
# 4. execute_recovery_action 真实动作
# ─────────────────────────────────────────────


class TestExecuteRecoveryActionRealActions(TestCase):
    """scheduler/recovery_engine.py: _action_notify / _action_mark_offline / _action_reassign"""

    def setUp(self):
        self.user = User.objects.create_user(username='action_user', password='test123')
        self.agent = _make_agent(agent_id='action-agent', status=Agent.Status.ONLINE)
        # 第二个 agent 作为 reassign 备用
        self.backup_agent = _make_agent(agent_id='backup-agent', status=Agent.Status.ONLINE)
        self.task = Task.objects.create(name='action-task')
        self.execution = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            triggered_by=self.user,
            status=TaskExecution.Status.RUNNING,
        )

    def test_action_notify_broadcasts_via_channel_layer(self):
        """_action_notify 应通过 channel_layer.group_send 广播 dashboard 通知.

        Note: ``async_to_sync`` is also called by the GAF log broadcast
        system (sends to 'logs' group with 'log.entry' type) on every
        logger.info call inside ``_action_notify``. We therefore cannot
        assert ``assert_called_once`` — instead we look for any call
        whose 2nd arg has type='notification' and group='dashboard'.
        """

        with (
            patch('channels.layers.get_channel_layer') as mock_get_layer,
            patch('asgiref.sync.async_to_sync') as mock_async,
        ):
            mock_layer = MagicMock()
            mock_get_layer.return_value = mock_layer
            # async_to_sync(coro_func) → callable mock; calling it sends the message.
            mock_send = MagicMock(return_value=None)
            mock_async.return_value = mock_send

            result = execute_recovery_action(
                action_type='notify',
                target_id='admin',
                config={'message': 'test alert', 'level': 'warning'},
            )

        self.assertTrue(result['success'])
        self.assertEqual(result['action'], 'notify')

        # Find the notification call (group='dashboard', type='notification')
        # among all group_send calls (log broadcasts use 'logs' + 'log.entry').
        notify_calls = [
            c for c in mock_send.call_args_list
            if len(c.args) == 2
            and c.args[0] == 'dashboard'
            and c.args[1].get('type') == 'notification'
        ]
        self.assertEqual(
            len(notify_calls), 1,
            f'expected exactly 1 dashboard notification call, got {len(notify_calls)}',
        )
        payload = notify_calls[0].args[1]['payload']
        self.assertEqual(payload['message'], 'test alert')
        self.assertEqual(payload['level'], 'warning')
        self.assertEqual(payload['target_id'], 'admin')

    def test_action_notify_channel_layer_none_returns_error(self):
        """channel_layer 为 None 时返回 success=False."""

        with patch('channels.layers.get_channel_layer', return_value=None):
            result = execute_recovery_action(
                action_type='notify',
                target_id='admin',
                config={'message': 'test alert'},
            )

        self.assertFalse(result['success'])
        self.assertIn('error', result)

    def test_action_mark_offline_sets_agent_offline(self):
        """_action_mark_offline 应将 Agent 状态置为 OFFLINE."""

        result = execute_recovery_action(
            action_type='mark_offline',
            target_id=self.agent.agent_id,
            config={},
        )

        self.assertTrue(result['success'])
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, Agent.Status.OFFLINE)

    def test_action_mark_offline_agent_not_found(self):
        """target_id 不存在时返回 success=False."""

        result = execute_recovery_action(
            action_type='mark_offline',
            target_id='non-existent-agent',
            config={},
        )

        self.assertFalse(result['success'])
        self.assertIn('agent not found', result.get('error', ''))

    def test_action_reassign_moves_task_to_backup_agent(self):
        """_action_reassign 应将 TaskExecution.agent 切换到备用 agent."""

        # 创建 RUNNING step, reassign 后应被重置为 PENDING
        step = ExecutionStep.objects.create(
            task_result=self.execution,
            step_index=0,
            node_id='running-node',
            step_type='pipeline_node',
            step_name='running-node',
            status=ExecutionStep.Status.RUNNING,
        )

        result = execute_recovery_action(
            action_type='reassign',
            target_id=self.execution.id,
            config={},
        )

        self.assertTrue(result['success'])
        self.execution.refresh_from_db()
        self.assertEqual(self.execution.agent_id, self.backup_agent.id)
        self.assertEqual(self.execution.recovery_layer, 5)  # system level

        step.refresh_from_db()
        self.assertEqual(step.status, ExecutionStep.Status.PENDING)

    def test_action_reassign_no_available_agent(self):
        """无可用 agent 时返回 success=False."""

        # backup_agent 设为 BUSY, 不可用
        self.backup_agent.status = Agent.Status.BUSY
        self.backup_agent.save(update_fields=['status'])
        self.agent.status = Agent.Status.OFFLINE
        self.agent.save(update_fields=['status'])

        result = execute_recovery_action(
            action_type='reassign',
            target_id=self.execution.id,
            config={},
        )

        self.assertFalse(result['success'])
        self.assertIn('no available agent', result.get('error', ''))

    def test_action_reassign_target_not_task_execution_id(self):
        """target_id 不是 int 时返回 success=False."""

        result = execute_recovery_action(
            action_type='reassign',
            target_id='not-a-task-id',
            config={},
        )

        self.assertFalse(result['success'])

    def test_device_command_action_dispatches_ws_frame(self):
        """P-048 升级: device-command action 通过 WS device.command 帧派发到 agent.

        替换原 placeholder 测试 (2026-07-29): restart_app / restart_emulator 等
        不再返回 'placeholder' note, 而是通过 channel_layer.group_send 发送
        device.command 帧到 agent 拥有的设备.

        Note: ``async_to_sync`` is also called by the GAF log broadcast
        system (sends to 'logs' group with 'log.entry' type) on every
        logger.info call. We therefore cannot assert ``call_count == 1``
        — instead we filter calls by group name = ``agent_{agent_id}`` and
        type = ``device.command``.
        """

        device = _make_device(self.agent, name='device-command-target')

        for action_type in ('restart_app', 'relogin', 'notify_only',
                            'restart_emulator', 'reconnect_adb', 'switch_backup'):
            with (
                patch('channels.layers.get_channel_layer') as mock_get_layer,
                patch('asgiref.sync.async_to_sync') as mock_async,
            ):
                mock_layer = MagicMock()
                mock_get_layer.return_value = mock_layer
                mock_send = MagicMock(return_value=None)
                mock_async.return_value = mock_send

                result = execute_recovery_action(
                    action_type=action_type,
                    target_id=device.id,  # Device.id → _resolve_agent_or_device_owner
                    config={'emulator_type': 'ldplayer', 'instance_id': 0},
                )

                self.assertTrue(
                    result['success'],
                    f'{action_type} should dispatch successfully, '
                    f'got: {result}',
                )
                self.assertEqual(result['action'], action_type)
                self.assertEqual(result['target_id'], device.id)
                self.assertIn('agent_id', result['details'])
                self.assertEqual(result['details']['agent_id'], self.agent.agent_id)
                # 过滤出 device.command 派发调用 (排除 log broadcast 的 log.entry 调用)
                expected_group = f'agent_{self.agent.agent_id}'
                device_command_calls = [
                    c for c in mock_send.call_args_list
                    if len(c.args) == 2
                    and c.args[0] == expected_group
                    and c.args[1].get('type') == 'device.command'
                ]
                self.assertEqual(
                    len(device_command_calls), 1,
                    f'{action_type}: expected 1 device.command group_send call, '
                    f'got {len(device_command_calls)} (total calls: '
                    f'{mock_send.call_count})',
                )
                send_args = device_command_calls[0].args
                self.assertEqual(send_args[1]['payload']['command'], action_type)
                self.assertEqual(send_args[1]['payload']['target_id'], device.id)

    def test_device_command_action_unresolvable_target_returns_error(self):
        """target_id 无法解析到 agent 时返回 success=False."""

        # 999999 是一个不存在的 Device.id
        result = execute_recovery_action(
            action_type='restart_app',
            target_id=999999,
            config={},
        )

        self.assertFalse(result['success'])
        self.assertIn('cannot resolve agent', result['error'])

    def test_device_command_action_channel_layer_none_returns_error(self):
        """channel_layer 为 None 时返回 success=False."""

        device = _make_device(self.agent, name='no-channel-layer-target')
        with patch('channels.layers.get_channel_layer', return_value=None):
            result = execute_recovery_action(
                action_type='restart_emulator',
                target_id=device.id,
                config={'emulator_type': 'ldplayer', 'instance_id': 0},
            )

        self.assertFalse(result['success'])
        self.assertIn('channel layer', result['error'])

    def test_semantic_action_returns_success(self):
        """语义性 action (retry/skip) 返回 success=True.

        S2-2.7 (2026-08-17): restart / switch_account 不再无条件下成功 —
        需解析到执行 agent 的 ONLINE 设备才派发 device.command; 无执行
        上下文时返回显式 error (不再返回假 success). retry/skip 保持
        原地语义.
        """

        # 不存在的 target → retry/skip 宽容处理, restart/switch_account 显式 error
        for action_type in ('retry', 'skip'):
            result = execute_recovery_action(
                action_type=action_type,
                target_id=999999,
                config={},
            )
            self.assertIn('success', result)

        for action_type in ('restart', 'switch_account'):
            result = execute_recovery_action(
                action_type=action_type,
                target_id=999999,
                config={},
            )
            self.assertFalse(result['success'])
            self.assertIn('cannot resolve target', result['error'])

        # 已有 execution (RUNNING + agent) 但无 ONLINE 设备 → 设备缺失 error
        result = execute_recovery_action(
            action_type='restart',
            target_id=self.execution.id,
            config={},
        )
        self.assertFalse(result['success'])
        self.assertIn('ONLINE device', result['error'])

    def test_unknown_action_returns_error(self):
        """未知 action_type 应返回 success=False + error."""

        result = execute_recovery_action(
            action_type='unknown_action',
            target_id=1,
            config={},
        )

        self.assertFalse(result['success'])
        self.assertIn('unknown action_type', result.get('error', ''))


# ─────────────────────────────────────────────
# 5. End-to-end: handle_device_crash via signal → ActionChain → RecoveryLog
# ─────────────────────────────────────────────


class TestDeviceCrashRecoveryEndToEnd(TestCase):
    """端到端: Device ERROR → signal → handle_device_crash → RecoveryLog 写入."""

    def setUp(self):
        self.agent = _make_agent(agent_id='e2e-agent')
        self.device = _make_device(self.agent, status=Device.Status.ONLINE)

    def test_device_error_writes_recovery_log(self):
        """Device ONLINE → ERROR 应产生 app/device level RecoveryLog 记录."""
        before = RecoveryLog.objects.filter(recovery_level='device').count()

        with self.captureOnCommitCallbacks(execute=True):
            self.device.status = Device.Status.ERROR
            self.device.save(update_fields=['status'])

        after = RecoveryLog.objects.filter(recovery_level='device').count()
        self.assertEqual(after, before + 1)

        log = RecoveryLog.objects.filter(
            recovery_level='device',
        ).order_by('-created_at').first()
        self.assertIsNotNone(log)
        self.assertIn(str(self.device.id), log.trigger_event)
        self.assertIn('崩溃', log.trigger_event)
