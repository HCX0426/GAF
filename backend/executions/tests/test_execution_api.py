"""
执行管理模块 - Phase 9 API 测试套件
覆盖所有4个端点的正常/异常场景
"""
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone
from rest_framework.test import force_authenticate
from scheduler.models import RecoveryLog

from executions.views import (
    daily_report_view,
    execution_intervene_view,
    execution_steps_view,
    unattended_logs_view,
)
from resources.models import ResourcePack
from tasks.models import Task, TaskExecution, ExecutionStep

User = get_user_model()


class BaseExecutionTestCase(TestCase):
    """测试基类 — 提供认证用户、任务、执行记录和步骤数据"""

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            username='test_operator',
            email='operator@test.com',
            password='TestPass123!',
        )
        self.user.role = User.Role.OPERATOR
        self.user.save()

        self.resource_pack = ResourcePack.objects.create(
            name='测试资源包',
            version='1.0.0',
            directory_path='/tmp/test_pack',
        )

        self.task = Task.objects.create(
            name='测试任务',
            execution_mode='pipeline',
        )

        self._create_execution_data()

    def _create_execution_data(self):
        """创建执行记录 #42 及其 8 个步骤"""
        now = timezone.now()
        self.execution_42 = TaskExecution.objects.create(
            id=42,
            task=self.task,
            triggered_by=self.user,
            status='running',
            started_at=now,
        )
        step_names = [
            '初始化浏览器环境', '打开游戏', '等待加载', '点击开始按钮',
            '输入账号', '输入密码', '点击登录', '等待进入游戏',
        ]
        step_statuses = [
            'success', 'success', 'success', 'running',
            'pending', 'pending', 'pending', 'pending',
        ]
        for i, (name, status_val) in enumerate(zip(step_names, step_statuses, strict=False)):
            ExecutionStep.objects.create(
                task_result=self.execution_42,
                step_index=i,
                step_name=name,
                step_type='action',
                status=status_val,
                started_at=now if status_val in ('success', 'running') else None,
                duration=2.0 if status_val == 'success' else 0.0,
            )

        self.execution_1 = TaskExecution.objects.create(
            id=1,
            task=self.task,
            triggered_by=self.user,
            status='success',
            started_at=now,
            completed_at=now,
            duration=timezone.timedelta(minutes=5),
        )
        for i in range(3):
            ExecutionStep.objects.create(
                task_result=self.execution_1,
                step_index=i,
                step_name=f'步骤{i}',
                step_type='action',
                status='success',
            )

        self.failed_execution = TaskExecution.objects.create(
            id=99,
            task=self.task,
            triggered_by=self.user,
            status='failed',
            started_at=now,
            error_message='ADB 设备断开连接',
        )
        ExecutionStep.objects.create(
            task_result=self.failed_execution,
            step_index=0,
            step_name='初始化连接',
            step_type='action',
            status='failed',
            error_message='ADB 设备断开连接',
        )

        for event_type in ['start', 'stop', 'error', 'recover', 'switch', 'complete']:
            RecoveryLog.objects.create(
                recovery_level='step',
                trigger_event=event_type,
                action_taken=f'处理 {event_type} 上传',
                success=event_type != 'error',
                details={'device': '测试设备', 'account': '测试账户'},
            )


class ExecutionStepsViewTests(BaseExecutionTestCase):
    """execution_steps_view 端点测试"""

    def test_get_all_steps_returns_full_list(self):
        """获取全部步骤应返回8条记录及统计摘要"""
        request = self.factory.get('/api/executions/42/steps/')
        force_authenticate(request, user=self.user)
        response = execution_steps_view(request, pk=42)

        self.assertEqual(response.status_code, 200)
        data = response.data
        assert isinstance(data, dict) and data.keys() >= {
            'execution_id', 'total_steps', 'steps',
            'completed_steps', 'running_steps', 'pending_steps',
        }
        self.assertEqual(data['execution_id'], 42)
        self.assertEqual(data['total_steps'], 8)
        self.assertEqual(len(data['steps']), 8)
        self.assertIn('completed_steps', data)
        self.assertIn('running_steps', data)
        self.assertIn('pending_steps', data)

    def test_get_single_step_by_index(self):
        """通过 step_index 查询单个步骤应返回该步骤详情"""
        request = self.factory.get('/api/executions/42/steps/?step_index=0')
        force_authenticate(request, user=self.user)
        response = execution_steps_view(request, pk=42)

        self.assertEqual(response.status_code, 200)
        assert isinstance(response.data, dict) and 'step' in response.data
        step = response.data['step']
        self.assertEqual(step['index'], 0)
        self.assertEqual(step['name'], '初始化浏览器环境')
        self.assertEqual(step['status'], 'success')

    def test_get_nonexistent_step_returns_404(self):
        """查询不存在的步骤索引应返回404"""
        request = self.factory.get('/api/executions/42/steps/?step_index=99')
        force_authenticate(request, user=self.user)
        response = execution_steps_view(request, pk=42)

        self.assertEqual(response.status_code, 404)

    def test_invalid_step_index_returns_400(self):
        """非法的 step_index 参数应返回400"""
        request = self.factory.get('/api/executions/42/steps/?step_index=abc')
        force_authenticate(request, user=self.user)
        response = execution_steps_view(request, pk=42)

        self.assertEqual(response.status_code, 400)

    def test_step_data_contains_required_fields(self):
        """每条步骤数据必须包含所有必要字段"""
        required_fields = {
            'id', 'execution_id', 'index', 'name', 'status',
            'started_at', 'duration', 'retries', 'error_message', 'screenshot_url',
        }
        request = self.factory.get('/api/executions/1/steps/')
        force_authenticate(request, user=self.user)
        response = execution_steps_view(request, pk=1)

        for step in response.data['steps']:
            self.assertTrue(required_fields.issubset(step.keys()))


class ExecutionInterveneViewTests(BaseExecutionTestCase):
    """execution_intervene_view 端点测试"""

    def test_valid_pause_action(self):
        """有效的 pause 操作应返回成功响应"""
        request = self.factory.post(
            '/api/executions/42/intervene/',
            {'action': 'pause', 'reason': '临时维护'},
            content_type='application/json',
        )
        force_authenticate(request, user=self.user)
        response = execution_intervene_view(request, pk=42)

        self.assertEqual(response.status_code, 200)
        assert isinstance(response.data, dict) and response.data.keys() >= {'success', 'intervention'}
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['intervention']['action'], 'pause')

    def test_valid_cancel_action(self):
        """有效的 cancel 操作应返回成功响应"""
        request = self.factory.post(
            '/api/executions/42/intervene/',
            {'action': 'cancel'},
            content_type='application/json',
        )
        force_authenticate(request, user=self.user)
        response = execution_intervene_view(request, pk=42)

        self.assertEqual(response.status_code, 200)
        assert isinstance(response.data, dict) and 'intervention' in response.data
        self.assertEqual(response.data['intervention']['action_label'], '取消执行')

    def test_missing_action_returns_400(self):
        """缺少 action 参数应返回400"""
        request = self.factory.post(
            '/api/executions/42/intervene/',
            {},
            content_type='application/json',
        )
        force_authenticate(request, user=self.user)
        response = execution_intervene_view(request, pk=42)

        self.assertEqual(response.status_code, 400)
        # N192 B1: unified_response envelope is {code, message, data}.
        # Old 'error' key is now 'message'.
        self.assertIn('message', response.data)

    def test_invalid_action_returns_400_with_list(self):
        """无效的 action 应返回400并列出合法选项"""
        request = self.factory.post(
            '/api/executions/42/intervene/',
            {'action': 'delete'},
            content_type='application/json',
        )
        force_authenticate(request, user=self.user)
        response = execution_intervene_view(request, pk=42)

        self.assertEqual(response.status_code, 400)
        # N192 B1: unified_response envelope is {code, message, data};
        # valid_actions now lives under data.valid_actions.
        self.assertIn('data', response.data)
        self.assertIn('valid_actions', response.data['data'])
        self.assertIn('cancel', response.data['data']['valid_actions'])

    def test_all_valid_actions_accepted(self):
        """所有5种合法 action 均应被接受"""
        valid_actions = ['pause', 'resume', 'skip_step', 'fail_step', 'cancel']
        for action in valid_actions:
            with self.subTest(action=action):
                request = self.factory.post(
                    '/api/executions/42/intervene/',
                    {'action': action},
                    content_type='application/json',
                )
                force_authenticate(request, user=self.user)
                response = execution_intervene_view(request, pk=42)
                self.assertEqual(response.status_code, 200)
                assert isinstance(response.data, dict) and 'success' in response.data

    def test_intervention_log_contains_operator_info(self):
        """干预日志应包含操作人信息"""
        request = self.factory.post(
            '/api/executions/42/intervene/',
            {'action': 'skip_step', 'reason': '此步可跳过'},
            content_type='application/json',
        )
        force_authenticate(request, user=self.user)
        response = execution_intervene_view(request, pk=42)

        log = response.data['intervention']
        self.assertEqual(log['operator'], 'test_operator')
        self.assertEqual(log['reason'], '此步可跳过')
        self.assertEqual(log['status'], 'success')


class DailyReportViewTests(BaseExecutionTestCase):
    """daily_report_view 端点测试"""

    def test_report_returns_markdown_and_structured_data(self):
        """报告应同时包含 markdown 文本和结构化 JSON 数据"""
        request = self.factory.get('/api/executions/daily-report/')
        force_authenticate(request, user=self.user)
        response = daily_report_view(request)

        self.assertEqual(response.status_code, 200)
        assert isinstance(response.data, dict) and response.data.keys() >= {'report_markdown', 'data'}
        self.assertIn('report_markdown', response.data)
        self.assertIn('data', response.data)
        self.assertIsInstance(response.data['report_markdown'], str)

    def test_report_markdown_contains_tables(self):
        """Markdown 报告应包含表格格式内容"""
        request = self.factory.get('/api/executions/daily-report/')
        force_authenticate(request, user=self.user)
        response = daily_report_view(request)

        md = response.data['report_markdown']
        self.assertIn('|', md)
        self.assertIn('执行概览', md)
        self.assertIn('设备统计', md)
        self.assertIn('失败记录', md)

    def test_report_overview_stats_present(self):
        """报告概览应包含完整的统计数据"""
        request = self.factory.get('/api/executions/daily-report/')
        force_authenticate(request, user=self.user)
        response = daily_report_view(request)

        overview = response.data['data']['overview']
        self.assertIn('total_executions', overview)
        self.assertIn('success_rate', overview)
        self.assertIn('avg_duration_minutes', overview)
        self.assertGreater(overview['total_executions'], 0)

    def test_custom_date_parameter(self):
        """自定义日期参数应正确传递到响应中"""
        request = self.factory.get('/api/executions/daily-report/?date=2026-05-20')
        force_authenticate(request, user=self.user)
        response = daily_report_view(request)

        self.assertEqual(response.data['date'], '2026-05-20')

    def test_failures_list_not_empty(self):
        """失败记录列表不应为空"""
        request = self.factory.get('/api/executions/daily-report/')
        force_authenticate(request, user=self.user)
        response = daily_report_view(request)

        failures = response.data['data']['failures']
        self.assertGreater(len(failures), 0)
        for f in failures:
            self.assertIn('execution_id', f)
            self.assertIn('error', f)
            self.assertIn('root_cause', f)

    def test_anomalies_have_severity(self):
        """异常检测记录应包含严重级别"""
        request = self.factory.get('/api/executions/daily-report/')
        force_authenticate(request, user=self.user)
        response = daily_report_view(request)

        anomalies = response.data['data']['anomalies']
        for a in anomalies:
            self.assertIn(a['severity'], ('critical', 'warning', 'info'))


class UnattendedLogsViewTests(BaseExecutionTestCase):
    """unattended_logs_view 端点测试"""

    def setUp(self):
        """Override to use admin role — unattended_logs_view filters by
        details__account=username for non-admin users, but the base
        RecoveryLog fixtures use a generic '测试账户' string."""
        super().setUp()
        self.user.role = User.Role.ADMIN
        self.user.save()

    def test_logs_return_grouped_by_device_account(self):
        """日志应按设备/账户分组返回"""
        request = self.factory.get('/api/executions/unattended-logs/')
        force_authenticate(request, user=self.user)
        response = unattended_logs_view(request)

        self.assertEqual(response.status_code, 200)
        assert isinstance(response.data, dict) and 'grouped_by_device_account' in response.data
        grouped = response.data['grouped_by_device_account']
        self.assertGreater(len(grouped), 0)
        for group in grouped:
            self.assertIn('device_name', group)
            self.assertIn('account_alias', group)
            self.assertIn('logs', group)

    def test_event_types_covered(self):
        """日志应包含所有定义的事件类型"""
        expected_types = {'start', 'stop', 'error', 'recover', 'switch', 'complete'}
        request = self.factory.get('/api/executions/unattended-logs/')
        force_authenticate(request, user=self.user)
        response = unattended_logs_view(request)

        actual_types = set(response.data['event_type_summary'].keys())
        self.assertTrue(expected_types.issubset(actual_types))

    def test_level_filter_error_only(self):
        """按 ERROR 级别过滤应只返回错误日志"""
        request = self.factory.get('/api/executions/unattended-logs/?level=ERROR')
        force_authenticate(request, user=self.user)
        response = unattended_logs_view(request)

        for group in response.data['grouped_by_device_account']:
            for log in group['logs']:
                self.assertEqual(log['level'], 'ERROR')

    def test_search_keyword_filter(self):
        """关键词搜索应过滤匹配 message 字段的日志"""
        request = self.factory.get(
            '/api/executions/unattended-logs/?search=上传'
        )
        force_authenticate(request, user=self.user)
        response = unattended_logs_view(request)

        for group in response.data['grouped_by_device_account']:
            for log in group['logs']:
                self.assertIn('上传', log['message'])

    def test_level_summary_present(self):
        """响应应包含各级别的汇总计数"""
        request = self.factory.get('/api/executions/unattended-logs/')
        force_authenticate(request, user=self.user)
        response = unattended_logs_view(request)

        summary = response.data['level_summary']
        self.assertIn('INFO', summary)
        self.assertIn('WARNING', summary)
        self.assertIn('ERROR', summary)

    def test_filters_applied_reflected(self):
        """应用的过滤条件应在响应中体现"""
        request = self.factory.get(
            '/api/executions/unattended-logs/?date=2026-05-21&level=ERROR&search=超时'
        )
        force_authenticate(request, user=self.user)
        response = unattended_logs_view(request)

        filters = response.data['filters_applied']
        self.assertEqual(filters['date'], '2026-05-21')
        self.assertEqual(filters['level'], 'ERROR')
        self.assertEqual(filters['search'], '超时')

    def test_log_entry_has_required_fields(self):
        """每条日志应包含完整的事件字段"""
        required_fields = {
            'id', 'timestamp', 'device_name', 'account_alias',
            'event_type', 'level', 'message', 'details',
        }
        request = self.factory.get('/api/executions/unattended-logs/')
        force_authenticate(request, user=self.user)
        response = unattended_logs_view(request)

        for group in response.data['grouped_by_device_account']:
            for log in group['logs']:
                self.assertTrue(required_fields.issubset(log.keys()))
