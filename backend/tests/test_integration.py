"""跨模块集成测试：认证、Agent、任务、资源包、LLM分析、监控"""

import json
import os
import tempfile
from unittest import mock

import pytest
from django.test import TestCase
from rest_framework import status
from rest_framework.response import Response as DRFResponse
from rest_framework.test import APIClient
from workers.models import Worker

from accounts.models import User
from debug.models import DebugLogArchive, LLMAnalysisResult
from monitors.models import MonitorEvent, MonitorRule
from resources.models import ResourcePack
from skills.models import SkillDefinition
from tasks.models import Task, TaskExecution

pytestmark = pytest.mark.integration


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _login_token(login_resp):
    """从 login 响应中提取 access token, 兼容 unified_response 信封与裸响应。"""
    return (login_resp.data.get('data', {}) or {}).get('access') or login_resp.data.get('access')


class AuthFlowIntegrationTests(TestCase):
    """完整认证流程集成测试：登录→Token刷新→权限检查→修改密码"""

    def setUp(self):
        """初始化 API 客户端和测试用户"""
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='integration_admin',
            password='AdminPass123!',
            role=User.Role.ADMIN,
        )

    def test_full_auth_flow(self):
        """完整认证流程：默认用户登录→Token刷新→权限检查→修改密码"""
        login_resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'integration_admin',
            'password': 'AdminPass123!',
        })
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)
        login_body = _unwrap(login_resp)
        self.assertIn('access', login_body)
        self.assertIn('refresh', login_body)
        access_token = login_body['access']
        refresh_token = login_body['refresh']

        refresh_resp = self.client.post('/api/v2/accounts/auth/refresh/', {
            'refresh': refresh_token,
        })
        self.assertEqual(refresh_resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', _unwrap(refresh_resp))

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        me_resp = self.client.get('/api/v2/accounts/users/me/')
        self.assertEqual(me_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(me_resp)['username'], 'integration_admin')

        change_pwd_resp = self.client.patch('/api/v2/accounts/auth/change-password/', {
            'old_password': 'AdminPass123!',
            'new_password': 'NewAdminPass456!',
            'confirm_password': 'NewAdminPass456!',
        }, format='json')
        self.assertEqual(change_pwd_resp.status_code, status.HTTP_200_OK)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.check_password('NewAdminPass456!'))

    def test_viewer_permission_denied_for_agents(self):
        """viewer角色无权访问Agent列表"""
        User.objects.create_user(
            username='integration_viewer',
            password='ViewerPass123!',
            role=User.Role.VIEWER,
        )
        login_resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'integration_viewer',
            'password': 'ViewerPass123!',
        })
        _token = _login_token(login_resp)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")
        resp = self.client.get('/api/v2/agents/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_default_user_login(self):
        """默认用户 user/user 可登录并获取Token"""
        resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'user',
            'password': 'user',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', _unwrap(resp))


class AgentLifecycleIntegrationTests(TestCase):
    """Agent 全生命周期集成测试：创建→Token生成→状态变更→能力查询"""

    def setUp(self):
        """初始化操作员用户并认证"""
        self.client = APIClient()
        self.operator = User.objects.create_user(
            username='agent_lifecycle_op',
            password='OpPass123!',
            role=User.Role.OPERATOR,
        )
        login_resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'agent_lifecycle_op',
            'password': 'OpPass123!',
        })
        _token = _login_token(login_resp)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")

    def test_agent_full_lifecycle(self):
        """Agent 全生命周期：创建→Token生成→online→busy→offline"""
        create_resp = self.client.post('/api/v2/agents/', {
            'agent_id': 'agent-lifecycle-001',
            'hostname': 'lifecycle-host',
            'ip_address': '10.0.0.50',
            'os_info': 'Windows Server 2022',
            'status': 'offline',
            'capabilities': {'screen': True, 'input': True, 'clipboard': True},
        }, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        agent_pk = _unwrap(create_resp)['id']
        agent = Worker.objects.get(pk=agent_pk)

        token_resp = self.client.post(f'/api/v2/agents/{agent_pk}/generate-token/')
        self.assertEqual(token_resp.status_code, status.HTTP_200_OK)
        self.assertIn('agent_token', _unwrap(token_resp))
        agent.refresh_from_db()
        # Token is stored as hash (workers.0007_agent_token_hash migration);
        # assert the hash is populated instead of the deprecated plaintext field.
        self.assertIsNotNone(agent.worker_token_hash)

        online_resp = self.client.patch(f'/api/v2/agents/{agent_pk}/', {
            'status': 'online',
        }, format='json')
        self.assertEqual(online_resp.status_code, status.HTTP_200_OK)
        agent.refresh_from_db()
        self.assertEqual(agent.status, Worker.Status.ONLINE)

        busy_resp = self.client.patch(f'/api/v2/agents/{agent_pk}/', {
            'status': 'busy',
        }, format='json')
        self.assertEqual(busy_resp.status_code, status.HTTP_200_OK)
        agent.refresh_from_db()
        self.assertEqual(agent.status, Worker.Status.BUSY)

        offline_resp = self.client.patch(f'/api/v2/agents/{agent_pk}/', {
            'status': 'offline',
        }, format='json')
        self.assertEqual(offline_resp.status_code, status.HTTP_200_OK)
        agent.refresh_from_db()
        self.assertEqual(agent.status, Worker.Status.OFFLINE)

    def test_agent_list_and_filter(self):
        """Agent列表查询和过滤"""
        Worker.objects.create(agent_id='agent-filter-001', hostname='host-a', status=Worker.Status.ONLINE)
        Worker.objects.create(agent_id='agent-filter-002', hostname='host-b', status=Worker.Status.OFFLINE)
        list_resp = self.client.get('/api/v2/agents/')
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(_unwrap(list_resp)), 2)

    def test_agent_token_regeneration(self):
        """Agent Token重新生成——新Token覆盖旧Token"""
        agent = Worker.objects.create(
            agent_id='agent-regen-001',
            hostname='regen-host',
            status=Worker.Status.OFFLINE,
        )
        first_resp = self.client.post(f'/api/v2/agents/{agent.pk}/generate-token/')
        first_token = _unwrap(first_resp)['agent_token']
        second_resp = self.client.post(f'/api/v2/agents/{agent.pk}/generate-token/')
        second_token = _unwrap(second_resp)['agent_token']
        self.assertNotEqual(first_token, second_token)


class TaskExecutionFlowIntegrationTests(TestCase):
    """任务执行全链路集成测试：创建Task→执行→状态流转→取消"""

    def setUp(self):
        """初始化操作员、资源包、Agent并认证"""
        self.client = APIClient()
        self.operator = User.objects.create_user(
            username='task_flow_op',
            password='OpPass123!',
            role=User.Role.OPERATOR,
        )
        self.resource_pack = ResourcePack.objects.create(
            name='任务流测试资源包',
            version='1.0.0',
            directory_path='/tmp/task_flow_resources',
        )
        self.agent = Worker.objects.create(
            agent_id='task-flow-agent',
            hostname='task-flow-host',
            status=Worker.Status.IDLE,
        )
        login_resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'task_flow_op',
            'password': 'OpPass123!',
        })
        _token = _login_token(login_resp)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")

    @mock.patch('tasks.tasks.dispatch_task.delay')
    def test_task_execution_full_flow(self, mock_dispatch):
        """任务执行全链路：创建Task→创建TaskExecution→pending→running→success→取消"""
        create_resp = self.client.post('/api/v2/tasks/', {
            'name': '全链路测试任务',
            'description': '集成测试任务',
            'execution_mode': 'pipeline',
            'task_definition': {'nodes': [{'id': 'n1', 'type': 'click', 'config': {'x': 100, 'y': 200}}]},
        }, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        task_pk = _unwrap(create_resp)['id']
        task = Task.objects.get(pk=task_pk)
        self.assertEqual(task.name, '全链路测试任务')

        # TD-260: tasks/views.py schedules dispatch_task.delay through
        # transaction.on_commit. Django TestCase wraps each test in an outer
        # transaction that is rolled back, so on_commit callbacks never fire
        # and the dispatch mock is never invoked. captureOnCommitCallbacks
        # (execute=True) captures and runs those callbacks immediately so the
        # mock is called within the test window.
        with self.captureOnCommitCallbacks(execute=True):
            execute_resp = self.client.post(f'/api/v2/tasks/{task_pk}/execute/', {
                'agent_id': 'task-flow-agent',
            }, format='json')
        self.assertEqual(execute_resp.status_code, status.HTTP_201_CREATED)
        execute_body = _unwrap(execute_resp)
        self.assertEqual(execute_body['status'], 'pending')
        execution_pk = execute_body['id']
        mock_dispatch.assert_called_once()
        args, kwargs = mock_dispatch.call_args
        self.assertEqual(args[0], execution_pk)
        self.assertIn('trace_id', kwargs)
        self.assertIsInstance(kwargs['trace_id'], str)

        execution = TaskExecution.objects.get(pk=execution_pk)
        execution.status = TaskExecution.Status.RUNNING
        execution.save()
        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.RUNNING)

        execution.status = TaskExecution.Status.SUCCESS
        execution.result_data = {'output': '任务执行成功'}
        execution.save()
        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.SUCCESS)
        self.assertEqual(execution.result_data, {'output': '任务执行成功'})

        another_execution = TaskExecution.objects.create(
            task=task,
            agent=self.agent,
            triggered_by=self.operator,
            status=TaskExecution.Status.RUNNING,
        )
        cancel_resp = self.client.post(f'/api/v2/tasks/{task_pk}/cancel/', {
            'reason': '集成测试取消',
        }, format='json')
        self.assertEqual(cancel_resp.status_code, status.HTTP_200_OK)
        another_execution.refresh_from_db()
        self.assertEqual(another_execution.status, TaskExecution.Status.CANCELLED)

    @mock.patch('tasks.tasks.dispatch_task.delay')
    def test_task_execution_without_agent(self, mock_dispatch):
        """不指定Agent也能创建任务执行记录"""
        task = Task.objects.create(
            name='无Agent任务',
            execution_mode='pipeline',
            task_definition={'nodes': []},
        )
        # TD-260: trigger on_commit callbacks immediately so the dispatch
        # mock is actually invoked (otherwise TestCase rollback discards the
        # deferred callback and the mock silently records zero calls).
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(f'/api/v2/tasks/{task.pk}/execute/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(resp)['status'], 'pending')

    def test_task_execution_readonly_list(self):
        """任务执行记录只读列表查询"""
        task = Task.objects.create(
            name='列表查询任务',
            execution_mode='pipeline',
            task_definition={'nodes': []},
        )
        TaskExecution.objects.create(
            task=task, agent=self.agent, triggered_by=self.operator,
            status=TaskExecution.Status.PENDING,
        )
        TaskExecution.objects.create(
            task=task, agent=self.agent, triggered_by=self.operator,
            status=TaskExecution.Status.SUCCESS,
        )
        resp = self.client.get('/api/v2/tasks/task-executions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class ResourcePackFlowIntegrationTests(TestCase):
    """资源包管理流程集成测试：创建→激活→校验→查询模板"""

    def setUp(self):
        """初始化管理员用户并认证"""
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='rp_flow_admin',
            password='AdminPass123!',
            role=User.Role.ADMIN,
        )
        login_resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'rp_flow_admin',
            'password': 'AdminPass123!',
        })
        _token = _login_token(login_resp)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")

    def _create_temp_pack_dir(self, name='test-pack', version='1.0.0'):
        """创建一个最小合法的资源包临时目录"""
        tmpdir = tempfile.mkdtemp(prefix='gaf_test_pack_')
        manifest = {
            'name': name,
            'version': version,
            'target_app': 'test_app',
            'author': 'test',
            'gaf_version': '1.0',
            'description': 'test pack',
        }
        with open(os.path.join(tmpdir, 'manifest.json'), 'w', encoding='utf-8') as f:
            json.dump(manifest, f)
        os.makedirs(os.path.join(tmpdir, 'templates'), exist_ok=True)
        return tmpdir

    def test_resource_pack_create_and_activate(self):
        """创建ResourcePack并激活"""
        pack_dir = self._create_temp_pack_dir('集成测试资源包', '2.0.0')
        create_resp = self.client.post('/api/v2/resources/resource-packs/', {
            'name': '集成测试资源包',
            'version': '2.0.0',
            'directory_path': pack_dir,
            'description': '集成测试用资源包',
        }, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        pack_pk = _unwrap(create_resp)['id']
        pack = ResourcePack.objects.get(pk=pack_pk)
        self.assertFalse(pack.is_active)

        activate_resp = self.client.post(f'/api/v2/resources/resource-packs/{pack_pk}/activate/')
        self.assertEqual(activate_resp.status_code, status.HTTP_200_OK)
        pack.refresh_from_db()
        self.assertTrue(pack.is_active)

    def test_resource_pack_activate_exclusive(self):
        """激活新资源包时其他资源包自动取消激活"""
        pack_a = ResourcePack.objects.create(
            name='资源包A', version='1.0', directory_path='/tmp/pack_a', is_active=True,
        )
        pack_b = ResourcePack.objects.create(
            name='资源包B', version='1.0', directory_path='/tmp/pack_b', is_active=False,
        )
        self.client.post(f'/api/v2/resources/resource-packs/{pack_b.pk}/activate/')
        pack_a.refresh_from_db()
        pack_b.refresh_from_db()
        self.assertFalse(pack_a.is_active)
        self.assertTrue(pack_b.is_active)

    def test_resource_pack_validate(self):
        """校验资源包结构——目录不存在时校验失败"""
        pack = ResourcePack.objects.create(
            name='校验测试包', version='1.0', directory_path='/nonexistent/pack',
        )
        resp = self.client.post(f'/api/v2/resources/resource-packs/{pack.pk}/validate/')
        self.assertIn(resp.status_code, [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST])

    def test_resource_pack_templates(self):
        """查询资源包模板列表——使用mock模拟目录"""
        pack = ResourcePack.objects.create(
            name='模板测试包', version='1.0', directory_path='/tmp/template_test_pack',
        )
        with mock.patch('os.path.isdir', return_value=True), mock.patch('os.walk') as mock_walk:
            mock_walk.return_value = [
                ('/tmp/template_test_pack/templates', [], ['screen1.png', 'screen2.jpg']),
            ]
            resp = self.client.get(f'/api/v2/resources/resource-packs/{pack.pk}/templates/')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertIn('templates', _unwrap(resp))

    def test_resource_pack_list(self):
        """资源包列表查询"""
        ResourcePack.objects.create(name='列表包1', version='1.0', directory_path='/tmp/list1')
        ResourcePack.objects.create(name='列表包2', version='1.0', directory_path='/tmp/list2')
        resp = self.client.get('/api/v2/resources/resource-packs/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(_unwrap(resp)), 2)


class LLMAnalysisFlowIntegrationTests(TestCase):
    """LLM分析流程集成测试：创建日志归档→关联Skill→分析→审核"""

    def setUp(self):
        """初始化操作员、Skill并认证"""
        self.client = APIClient()
        self.operator = User.objects.create_user(
            username='llm_flow_op',
            password='OpPass123!',
            role=User.Role.OPERATOR,
        )
        self.skill = SkillDefinition.objects.create(
            name='日志分析Skill',
            description='分析调试日志中的错误',
            yaml_content='name: log_analyzer\ntype: llm',
            version='1.0',
            is_builtin=True,
            is_enabled=True,
        )
        login_resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'llm_flow_op',
            'password': 'OpPass123!',
        })
        _token = _login_token(login_resp)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")

    def _create_log_archive(self):
        """辅助方法：创建一个 DebugLogArchive 记录"""
        log_archive = DebugLogArchive.objects.create(
            zip_file_path='/tmp/test_debug_logs.zip',
            analysis_status=DebugLogArchive.AnalysisStatus.PENDING,
            uploaded_by=self.operator,
        )
        return log_archive

    @mock.patch('debug.tasks.analyze_log_archive.delay')
    def test_llm_analysis_full_flow(self, mock_analyze_task):
        """LLM分析完整流程：创建日志归档→关联Skill分析→创建分析结果→审核"""
        log_archive = self._create_log_archive()

        analyze_resp = self.client.post(
            f'/api/v2/debug/debug-logs/{log_archive.pk}/analyze/',
            {'skill_id': self.skill.pk},
            format='json',
        )
        self.assertEqual(analyze_resp.status_code, status.HTTP_201_CREATED)
        self.assertIn('review_status', _unwrap(analyze_resp))
        mock_analyze_task.assert_called_once()

        log_archive.refresh_from_db()
        self.assertEqual(log_archive.analysis_status, DebugLogArchive.AnalysisStatus.ANALYZING)
        self.assertEqual(log_archive.skill, self.skill)

        analysis_result = LLMAnalysisResult.objects.create(
            log_archive=log_archive,
            skill=self.skill,
            result_data={'findings': ['异常日志模式', '内存泄漏迹象']},
            suggestions=['建议重启服务', '检查内存配置'],
            review_status=LLMAnalysisResult.ReviewStatus.PENDING,
            confidence=0.85,
            model_name='gpt-4',
        )

        review_resp = self.client.put(
            f'/api/v2/debug/analysis-results/{analysis_result.pk}/review/',
            {'review_status': 'adopted'},
            format='json',
        )
        self.assertEqual(review_resp.status_code, status.HTTP_200_OK)
        analysis_result.refresh_from_db()
        self.assertEqual(analysis_result.review_status, LLMAnalysisResult.ReviewStatus.ADOPTED)

    @mock.patch('debug.tasks.analyze_log_archive.delay')
    def test_llm_analysis_review_ignored(self, mock_analyze_task):
        """审核分析结果——标记为忽略"""
        log_archive = self._create_log_archive()
        self.client.post(
            f'/api/v2/debug/debug-logs/{log_archive.pk}/analyze/',
            {'skill_id': self.skill.pk},
            format='json',
        )
        result = LLMAnalysisResult.objects.first()
        review_resp = self.client.put(
            f'/api/v2/debug/analysis-results/{result.pk}/review/',
            {'review_status': 'ignored'},
            format='json',
        )
        self.assertEqual(review_resp.status_code, status.HTTP_200_OK)
        result.refresh_from_db()
        self.assertEqual(result.review_status, LLMAnalysisResult.ReviewStatus.IGNORED)

    @mock.patch('debug.tasks.analyze_log_archive.delay')
    def test_llm_analysis_duplicate_prevents(self, mock_analyze_task):
        """重复提交分析——正在分析中的日志不允许重复分析"""
        log_archive = self._create_log_archive()
        self.client.post(
            f'/api/v2/debug/debug-logs/{log_archive.pk}/analyze/',
            {'skill_id': self.skill.pk},
            format='json',
        )
        duplicate_resp = self.client.post(
            f'/api/v2/debug/debug-logs/{log_archive.pk}/analyze/',
            {'skill_id': self.skill.pk},
            format='json',
        )
        self.assertEqual(duplicate_resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_analysis_result_list(self):
        """分析结果列表查询"""
        log_archive = self._create_log_archive()
        LLMAnalysisResult.objects.create(
            log_archive=log_archive,
            skill=self.skill,
            result_data={},
            suggestions=[],
            review_status=LLMAnalysisResult.ReviewStatus.PENDING,
        )
        resp = self.client.get('/api/v2/debug/analysis-results/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class MonitorRuleFlowIntegrationTests(TestCase):
    """监控规则流程集成测试：创建规则→启用/禁用→创建事件→确认告警"""

    def setUp(self):
        """初始化操作员、资源包、Agent并认证"""
        self.client = APIClient()
        self.operator = User.objects.create_user(
            username='monitor_flow_op',
            password='OpPass123!',
            role=User.Role.OPERATOR,
        )
        self.resource_pack = ResourcePack.objects.create(
            name='监控测试资源包',
            version='1.0.0',
            directory_path='/tmp/monitor_resources',
        )
        self.agent = Worker.objects.create(
            agent_id='monitor-agent',
            hostname='monitor-host',
            status=Worker.Status.ONLINE,
        )
        login_resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'monitor_flow_op',
            'password': 'OpPass123!',
        })
        _token = _login_token(login_resp)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")

    def test_monitor_rule_crud_and_toggle(self):
        """监控规则完整流程：创建→查询→启用/禁用→删除"""
        create_resp = self.client.post('/api/v2/monitors/monitor-rules/', {
            'name': 'CPU告警规则',
            'rule_definition': {
                'metric': 'cpu_usage',
                'threshold': 90,
                'operator': 'gt',
                'duration': '5m',
            },
            'resource_pack': self.resource_pack.pk,
            'is_enabled': True,
        }, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        rule_pk = _unwrap(create_resp)['id']
        rule = MonitorRule.objects.get(pk=rule_pk)
        self.assertEqual(rule.name, 'CPU告警规则')
        self.assertTrue(rule.is_enabled)

        get_resp = self.client.get(f'/api/v2/monitors/monitor-rules/{rule_pk}/')
        self.assertEqual(get_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(get_resp)['name'], 'CPU告警规则')

        patch_resp = self.client.patch(f'/api/v2/monitors/monitor-rules/{rule_pk}/', {
            'is_enabled': False,
        }, format='json')
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        rule.refresh_from_db()
        self.assertFalse(rule.is_enabled)

        enable_resp = self.client.patch(f'/api/v2/monitors/monitor-rules/{rule_pk}/', {
            'is_enabled': True,
        }, format='json')
        self.assertEqual(enable_resp.status_code, status.HTTP_200_OK)
        rule.refresh_from_db()
        self.assertTrue(rule.is_enabled)

        delete_resp = self.client.delete(f'/api/v2/monitors/monitor-rules/{rule_pk}/')
        self.assertEqual(delete_resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(MonitorRule.objects.filter(pk=rule_pk).exists())

    def test_monitor_event_create_and_acknowledge(self):
        """创建MonitorEvent并确认告警"""
        MonitorRule.objects.create(
            name='内存告警规则',
            rule_definition={'metric': 'memory_usage', 'threshold': 85},
            resource_pack=self.resource_pack,
            is_enabled=True,
        )
        event = MonitorEvent.objects.create(
            event_type='threshold_breach',
            handling_result='',
            event_data={'metric': 'memory_usage', 'value': 92, 'threshold': 85},
            agent=self.agent,
            resource_pack=self.resource_pack,
        )

        list_resp = self.client.get('/api/v2/monitors/monitor-events/')
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)

        def _mock_acknowledge(self, request, pk=None):
            event_obj = self.get_object()
            event_obj.handling_result = 'acknowledged'
            event_obj.save(update_fields=['handling_result'])
            return DRFResponse({'id': event_obj.pk, 'handling_result': 'acknowledged'})

        with mock.patch('monitors.views.MonitorEventViewSet.acknowledge', _mock_acknowledge):
            ack_resp = self.client.post(f'/api/v2/monitors/monitor-events/{event.pk}/acknowledge/')
            self.assertEqual(ack_resp.status_code, status.HTTP_200_OK)

    def test_monitor_event_filter_by_agent(self):
        """按Agent过滤监控事件"""
        agent_b = Worker.objects.create(
            agent_id='monitor-agent-b',
            hostname='monitor-host-b',
            status=Worker.Status.ONLINE,
        )
        MonitorEvent.objects.create(
            event_type='error', agent=self.agent, resource_pack=self.resource_pack,
        )
        MonitorEvent.objects.create(
            event_type='warning', agent=agent_b, resource_pack=self.resource_pack,
        )
        resp = self.client.get('/api/v2/monitors/monitor-events/', {'agent': agent_b.pk})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_monitor_rule_list(self):
        """监控规则列表查询"""
        MonitorRule.objects.create(
            name='规则1', rule_definition={}, resource_pack=self.resource_pack, is_enabled=True,
        )
        MonitorRule.objects.create(
            name='规则2', rule_definition={}, resource_pack=self.resource_pack, is_enabled=False,
        )
        resp = self.client.get('/api/v2/monitors/monitor-rules/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(_unwrap(resp)), 2)
