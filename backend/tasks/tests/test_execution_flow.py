"""任务执行流程集成测试：创建→执行→监控→取消"""

from unittest.mock import AsyncMock, MagicMock, patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from agents.models import Agent
from gamestate.models import GameProfile
from tasks.models import Task, TaskExecution
from tasks.tasks import dispatch_task


class TestTaskExecutionFlow(TestCase):
    """任务执行完整流程测试"""

    def setUp(self):
        """初始化测试环境：用户、Agent、资源包、任务"""
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='exec_test_admin',
            password='admin123456',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.admin)

        self.agent = Agent.objects.create(
            agent_id='test-agent-001',
            # TD-141 (2026-07-18): agent_token plaintext field removed.
            hostname='test-host',
            status=Agent.Status.IDLE,
            is_local=True,
        )

        self.task = Task.objects.create(
            name='测试任务-签到',
            description='自动化签到流程',
            execution_mode='pipeline',
            task_definition={'nodes': [{'id': 'n1', 'type': 'click', 'config': {'x': 100, 'y': 200}}]},
            is_enabled=True,
        )

    def test_list_tasks(self):
        """获取任务列表"""
        response = self.client.get('/api/v2/tasks/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # UnifiedResponse middleware 把原 response.data 包到 {code, message, data} 信封里
        self.assertIn('results', response.data['data'])
        self.assertGreaterEqual(response.data['data']['count'], 1)

    def test_get_task_detail(self):
        """获取任务详情"""
        response = self.client.get(f'/api/v2/tasks/{self.task.id}/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['name'], '测试任务-签到')
        self.assertEqual(response.data['data']['execution_mode'], 'pipeline')
        self.assertTrue(response.data['data']['is_enabled'])

    def test_create_task(self):
        """创建新任务"""
        response = self.client.post('/api/v2/tasks/', {
            'name': '新任务-采集',
            'description': '资源采集任务',
            'execution_mode': 'state_machine',
            'task_definition': {'states': [{'name': 'start'}]},
            'is_enabled': True,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['name'], '新任务-采集')
        self.assertEqual(response.data['data']['execution_mode'], 'state_machine')

    def test_update_task(self):
        """更新任务"""
        response = self.client.patch(
            f'/api/v2/tasks/{self.task.id}/',
            {'name': '测试任务-签到-已更新', 'is_enabled': False},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['name'], '测试任务-签到-已更新')
        self.assertFalse(response.data['data']['is_enabled'])

    def test_execute_task(self):
        """执行任务（dev 环境 Celery Eager 模式同步执行）"""
        response = self.client.post(
            f'/api/v2/tasks/{self.task.id}/execute/',
            {'agent_id': self.agent.agent_id},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['task'], self.task.id)
        self.assertIn(response.data['data']['status'], ['pending', 'running'])

    def test_execute_task_without_agent(self):
        """执行任务不指定 Agent 时应自动选择"""
        response = self.client.post(
            f'/api/v2/tasks/{self.task.id}/execute/',
            {},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn(response.data['data']['status'], ['pending', 'running'])

    def test_list_executions(self):
        """获取执行记录列表"""
        TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            status=TaskExecution.Status.SUCCESS,
            triggered_by=self.admin,
        )
        response = self.client.get('/api/v2/tasks/task-executions/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # UnifiedResponse middleware 把原 response.data 包到 {code, message, data} 信封里
        self.assertIn('results', response.data['data'])
        self.assertGreaterEqual(response.data['data']['count'], 1)

    def test_get_execution_detail(self):
        """获取执行详情含步骤"""
        execution = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            status=TaskExecution.Status.RUNNING,
            triggered_by=self.admin,
        )
        response = self.client.get(
            f'/api/v2/tasks/task-executions/{execution.id}/',
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['status'], 'running')
        self.assertIn('steps', response.data['data'])

    def test_get_execution_steps(self):
        """获取执行步骤列表"""
        execution = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            status=TaskExecution.Status.SUCCESS,
            triggered_by=self.admin,
            log='step1 completed',
        )
        from tasks.models import TaskStep
        TaskStep.objects.create(
            execution=execution,
            step_index=0,
            step_name='点击签到按钮',
            step_type='click',
            status=TaskStep.Status.SUCCESS,
        )
        TaskStep.objects.create(
            execution=execution,
            step_index=1,
            step_name='等待结果',
            step_type='wait',
            status=TaskStep.Status.SUCCESS,
        )
        response = self.client.get(
            f'/api/v2/tasks/task-executions/{execution.id}/steps/',
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # UnifiedResponse middleware 包到 data 字段, steps 在 data.steps 中
        self.assertEqual(len(response.data['data']['steps']), 2)
        self.assertEqual(response.data['data']['steps'][0]['name'], '点击签到按钮')

    def test_cancel_execution(self):
        """取消执行"""
        execution = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            status=TaskExecution.Status.RUNNING,
            triggered_by=self.admin,
        )
        response = self.client.post(
            f'/api/v2/tasks/task-executions/{execution.id}/cancel/',
            {'reason': '手动取消'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.CANCELLED)

    def test_pause_execution(self):
        """暂停执行"""
        execution = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            status=TaskExecution.Status.RUNNING,
            triggered_by=self.admin,
        )
        response = self.client.post(
            f'/api/v2/tasks/task-executions/{execution.id}/pause/',
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.PAUSED)

    def test_resume_execution(self):
        """恢复暂停的执行"""
        execution = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            status=TaskExecution.Status.PAUSED,
            triggered_by=self.admin,
        )
        response = self.client.post(
            f'/api/v2/tasks/task-executions/{execution.id}/resume/',
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.RUNNING)

    def test_skip_step(self):
        """跳过执行步骤"""
        from tasks.models import TaskStep
        execution = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            status=TaskExecution.Status.RUNNING,
            triggered_by=self.admin,
        )
        TaskStep.objects.create(
            execution=execution,
            step_index=0,
            step_name='点击签到按钮',
            step_type='click',
            status=TaskStep.Status.PENDING,
        )
        response = self.client.post(
            f'/api/v2/tasks/task-executions/{execution.id}/skip/',
            {'step_index': 0},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_execution_unauthorized(self):
        """未认证用户无法获取执行记录"""
        client = APIClient()
        response = client.get('/api/v2/tasks/task-executions/', format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cancel_completed_fails(self):
        """已完成的任务不可取消"""
        execution = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            status=TaskExecution.Status.SUCCESS,
            triggered_by=self.admin,
        )
        response = self.client.post(
            f'/api/v2/tasks/task-executions/{execution.id}/cancel/',
            {'reason': '尝试取消'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DispatchTaskResourcePackTest(TestCase):
    """Verify dispatch_task passes resource_pack + game_account to agent.

    N197-8: Resource pack resolution priority:
    1. Task.resource_pack (primary — task directly associates with a resource pack)
    2. GameAccount.resource_pack (fallback — legacy dead-field landing)

    Also verifies server_region is forwarded for server-specific template loading.
    """

    @patch('tasks.tasks.get_channel_layer')
    def test_dispatch_task_includes_resource_pack(self, mock_channel_layer):
        """dispatch_task should read GameAccount.resource_pack and pass to agent."""
        from accounts.models import GameAccount
        from agents.models import Device
        from resources.models import ResourcePack
        from tasks.concurrency_controller import get_default_controller

        # Reset concurrency controller so in-flight state from other tests
        # doesn't block the dispatch.
        controller = get_default_controller()
        controller.reset()

        # Setup — ResourcePack with version + directory_path (required fields).
        pack = ResourcePack.objects.create(
            name='BD2-v1', version='1.0',
            directory_path='resources/BrownDust-II/v1',
        )
        # GameAccount requires owner, game_name, username, encrypted_password.
        owner = User.objects.create_user(
            username='rp-test-owner', password='test123456',
        )
        account = GameAccount.objects.create(
            owner=owner,
            game_profile=GameProfile.objects.get_or_create(game_name='BD2')[0],
            username='test-acct',
            game_name='BD2',
            encrypted_password='encrypted-blob',
            resource_pack=pack,
        )
        # Agent must be IDLE and have capability matching task_definition.
        # task_definition has 'click' action → required capability 'windows'.
        agent = Agent.objects.create(
            agent_id='rp-test-agent', hostname='rp-host',
            status=Agent.Status.IDLE,
            capabilities={'windows': True, 'adb': True},
            is_local=True,
        )
        # Device bound to agent + game_account (window-centric).
        device = Device.objects.create(
            name='rp-test-device', device_type='windows',
            agent=agent, game_account=account,
        )
        task = Task.objects.create(
            name='rp-test-task',
            task_definition={'nodes': [{'id': 'n1', 'type': 'click', 'config': {'x': 1, 'y': 2}}]},
        )
        execution = TaskExecution.objects.create(
            task=task, device=device, game_account=account,
            status=TaskExecution.Status.PENDING,
        )

        # Mock channel layer — group_send is async, so use AsyncMock.
        mock_channel = MagicMock()
        mock_channel.group_send = AsyncMock()
        mock_channel_layer.return_value = mock_channel

        # Act: dispatch synchronously (CELERY_TASK_ALWAYS_EAGER in dev).
        dispatch_task(execution.id)

        # Assert: group_send called with resource_pack in payload.
        calls = mock_channel.group_send.call_args_list
        assert len(calls) > 0, "group_send should be called after successful dispatch"
        sent_data = calls[0][0][1]  # second positional arg to group_send
        # spec-29b: canonical "payload" key (was "data" before spec-29a #31).
        # Fall back to sent_data itself for non-task.assign message shapes.
        payload = sent_data.get('payload', sent_data)

        assert 'resource_pack' in payload, (
            "dispatch_task payload must include resource_pack — "
            "landing the dead GameAccount.resource_pack FK"
        )
        assert payload['resource_pack'] is not None, (
            "resource_pack should be a dict when game_account.resource_pack is set"
        )
        assert payload['resource_pack']['name'] == 'BD2-v1'
        assert payload['resource_pack']['directory_path'] == 'resources/BrownDust-II/v1'
        assert payload['game_account_id'] == account.id
        assert payload['game_account_name'] == 'test-acct'

    @patch('tasks.tasks.get_channel_layer')
    def test_dispatch_task_prefers_task_resource_pack(self, mock_channel_layer):
        """N197-8: dispatch_task should prefer Task.resource_pack over GameAccount.resource_pack."""
        from accounts.models import GameAccount
        from agents.models import Device
        from resources.models import ResourcePack
        from tasks.concurrency_controller import get_default_controller

        # Reset concurrency controller.
        controller = get_default_controller()
        controller.reset()

        # Setup — two resource packs: one on Task, one on GameAccount.
        task_pack = ResourcePack.objects.create(
            name='Task-Pack', version='1.0',
            directory_path='resources/TaskPack/v1',
        )
        account_pack = ResourcePack.objects.create(
            name='Account-Pack', version='1.0',
            directory_path='resources/AccountPack/v1',
        )
        owner = User.objects.create_user(
            username='priority-test-owner', password='test123456',
        )
        account = GameAccount.objects.create(
            owner=owner,
            game_profile=GameProfile.objects.get_or_create(game_name='BD2')[0],
            username='priority-test-acct',
            game_name='BD2', encrypted_password='encrypted-blob',
            resource_pack=account_pack,  # should NOT be used
        )
        agent = Agent.objects.create(
            agent_id='priority-test-agent', hostname='priority-host',
            status=Agent.Status.IDLE,
            capabilities={'windows': True, 'adb': True},
            is_local=True,
        )
        device = Device.objects.create(
            name='priority-test-device', device_type='windows',
            agent=agent, game_account=account,
        )
        task = Task.objects.create(
            name='priority-test-task',
            resource_pack=task_pack,  # N197-8: should take priority
            task_definition={'nodes': [{'id': 'n1', 'type': 'click', 'config': {'x': 1, 'y': 2}}]},
        )
        execution = TaskExecution.objects.create(
            task=task, device=device, game_account=account,
            status=TaskExecution.Status.PENDING,
        )

        # Mock channel layer.
        mock_channel = MagicMock()
        mock_channel.group_send = AsyncMock()
        mock_channel_layer.return_value = mock_channel

        # Act.
        dispatch_task(execution.id)

        # Assert: Task.resource_pack is used, not GameAccount.resource_pack.
        calls = mock_channel.group_send.call_args_list
        assert len(calls) > 0, "group_send should be called after successful dispatch"
        sent_data = calls[0][0][1]
        payload = sent_data.get('payload', sent_data)

        assert payload['resource_pack'] is not None
        assert payload['resource_pack']['name'] == 'Task-Pack', (
            "N197-8: should use Task.resource_pack ('Task-Pack'), not "
            f"GameAccount.resource_pack ({payload['resource_pack']['name']})"
        )
        assert payload['resource_pack']['directory_path'] == 'resources/TaskPack/v1'
        # server_region comes from the game account (empty string if not set)
        assert payload['resource_pack'].get('server_region') == '', (
            "N197-8: server_region should be empty when game_account has no server set"
        )


class DispatchTaskTraceIdTest(TestCase):
    """B3-4 (spec 2026-07-30-debug-directory-restructure): dispatch_task 注入 trace_id.

    dispatch_task 应从 ``current_trace_id`` ContextVar 取 HTTP 请求级 trace_id,
    持久化到 ``TaskExecution.trace_id`` 字段, 并传入 ``write_meta_json`` 让
    meta.json 含 trace_id, 实现 HTTP → DB → meta.json → agent 全链路贯穿.
    """

    @patch('tasks.tasks.get_channel_layer')
    @patch('django.conf.settings.DEBUG_DIR', '/tmp/gaf_b3_4_test_debug')
    def test_dispatch_task_persists_trace_id_to_execution(self, mock_channel_layer):
        """dispatch_task should persist ContextVar trace_id to TaskExecution.trace_id."""
        import tempfile

        from gaf_core.tracing.context import current_trace_id

        tmpdir = tempfile.mkdtemp(prefix="gaf_b3_4_")
        try:
            with patch('django.conf.settings.DEBUG_DIR', tmpdir):
                # Reset concurrency controller
                from tasks.concurrency_controller import get_default_controller
                controller = get_default_controller()
                controller.reset()

                # Setup minimal Agent + Task + TaskExecution
                Agent.objects.create(
                    agent_id='b3-4-trace-agent', hostname='b3-4-host',
                    status=Agent.Status.IDLE,
                    capabilities={'windows': True},
                    is_local=True,
                )
                task = Task.objects.create(
                    name='b3-4-trace-task',
                    task_definition={'nodes': [{'id': 'n1', 'type': 'click', 'config': {'x': 1, 'y': 2}}]},
                )
                execution = TaskExecution.objects.create(
                    task=task,
                    status=TaskExecution.Status.PENDING,
                )

                mock_channel = MagicMock()
                mock_channel.group_send = AsyncMock()
                mock_channel_layer.return_value = mock_channel

                ctx_trace_id = "550e8400-e29b-41d4-a716-446655440000"
                token = current_trace_id.set(ctx_trace_id)
                try:
                    dispatch_task(execution.id)
                finally:
                    current_trace_id.reset(token)

                execution.refresh_from_db()
                self.assertEqual(
                    execution.trace_id, ctx_trace_id,
                    "TaskExecution.trace_id should be persisted from ContextVar",
                )
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    @patch('tasks.tasks.get_channel_layer')
    def test_dispatch_task_writes_trace_id_to_meta_json(self, mock_channel_layer):
        """dispatch_task should write trace_id field to meta.json."""
        import json
        import os
        import tempfile

        from gaf_core.tracing.context import current_trace_id

        tmpdir = tempfile.mkdtemp(prefix="gaf_b3_4_meta_")
        try:
            with patch('django.conf.settings.DEBUG_DIR', tmpdir):
                from tasks.concurrency_controller import get_default_controller
                controller = get_default_controller()
                controller.reset()

                Agent.objects.create(
                    agent_id='b3-4-meta-agent', hostname='b3-4-meta-host',
                    status=Agent.Status.IDLE,
                    capabilities={'windows': True},
                    is_local=True,
                )
                task = Task.objects.create(
                    name='b3-4-meta-task',
                    task_definition={'nodes': [{'id': 'n1', 'type': 'click', 'config': {'x': 1, 'y': 2}}]},
                )
                execution = TaskExecution.objects.create(
                    task=task,
                    status=TaskExecution.Status.PENDING,
                )

                mock_channel = MagicMock()
                mock_channel.group_send = AsyncMock()
                mock_channel_layer.return_value = mock_channel

                ctx_trace_id = "abcdef12-3456-7890-abcd-ef1234567890"
                token = current_trace_id.set(ctx_trace_id)
                try:
                    dispatch_task(execution.id)
                finally:
                    current_trace_id.reset(token)

                # Find meta.json under tmpdir (nested structure: YYYYMMDD/<safe_name>/HHMMSS_<suffix>/meta.json)
                meta_paths = []
                for root, _dirs, files in os.walk(tmpdir):
                    if 'meta.json' in files:
                        meta_paths.append(os.path.join(root, 'meta.json'))

                self.assertGreaterEqual(
                    len(meta_paths), 1,
                    f"meta.json should be written; tmpdir contents: {os.listdir(tmpdir)}",
                )
                # Read the first meta.json (归一化目录, not 镜像)
                meta_path = meta_paths[0]
                with open(meta_path, encoding='utf-8') as f:
                    meta = json.load(f)
                self.assertEqual(
                    meta.get('trace_id'), ctx_trace_id,
                    f"meta.json should contain trace_id; actual meta: {meta}",
                )
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    @patch('tasks.tasks.get_channel_layer')
    def test_dispatch_task_writes_execution_jsonl_with_trace_id(self, mock_channel_layer):
        """dispatch_task should write execution.jsonl with trace_id via BackendTaskLogger."""
        import json
        import os
        import tempfile

        from gaf_core.tracing.context import current_trace_id

        tmpdir = tempfile.mkdtemp(prefix="gaf_b3_4_jsonl_")
        try:
            with patch('django.conf.settings.DEBUG_DIR', tmpdir):
                from tasks.concurrency_controller import get_default_controller
                controller = get_default_controller()
                controller.reset()

                Agent.objects.create(
                    agent_id='b3-4-jsonl-agent', hostname='b3-4-jsonl-host',
                    status=Agent.Status.IDLE,
                    capabilities={'windows': True},
                    is_local=True,
                )
                task = Task.objects.create(
                    name='b3-4-jsonl-task',
                    task_definition={'nodes': [{'id': 'n1', 'type': 'click', 'config': {'x': 1, 'y': 2}}]},
                )
                execution = TaskExecution.objects.create(
                    task=task,
                    status=TaskExecution.Status.PENDING,
                )

                mock_channel = MagicMock()
                mock_channel.group_send = AsyncMock()
                mock_channel_layer.return_value = mock_channel

                ctx_trace_id = "11111111-2222-3333-4444-555555555555"
                token = current_trace_id.set(ctx_trace_id)
                try:
                    dispatch_task(execution.id)
                finally:
                    current_trace_id.reset(token)

                # Find execution.jsonl under tmpdir (path: YYYYMMDD/backend/tasks/<pipeline>/HH/execution.jsonl)
                jsonl_paths = []
                for root, _dirs, files in os.walk(tmpdir):
                    if 'execution.jsonl' in files:
                        jsonl_paths.append(os.path.join(root, 'execution.jsonl'))

                self.assertGreaterEqual(
                    len(jsonl_paths), 1,
                    f"execution.jsonl should be written; tmpdir contents: {os.listdir(tmpdir)}",
                )
                # Read lines and verify each has trace_id
                with open(jsonl_paths[0], encoding='utf-8') as f:
                    lines = [json.loads(line) for line in f if line.strip()]
                self.assertGreaterEqual(len(lines), 1)
                for rec in lines:
                    self.assertEqual(
                        rec.get('trace_id'), ctx_trace_id,
                        f"execution.jsonl line should contain trace_id; actual: {rec}",
                    )
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
