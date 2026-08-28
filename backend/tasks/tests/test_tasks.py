"""Task model and API unit tests — CRUD, filtering, permissions, validation."""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.factories import AdminUserFactory, OperatorUserFactory
from accounts.models import User
from tasks.models import Task


class TestCreateTask(TestCase):
    """Task creation tests."""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.operator = OperatorUserFactory()
        self.client = APIClient()

    def test_create_task(self):
        """Create a task."""
        self.client.force_authenticate(user=self.operator)
        response = self.client.post(
            '/api/v2/tasks/',
            {
                'name': '测试任务',
                'description': '这是一个测试任务',
                'execution_mode': 'pipeline',
                'task_definition': {'nodes': []},
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # UnifiedResponse middleware 把原 response.data 包到 {code, message, data} 信封里
        self.assertEqual(response.data['data']['name'], '测试任务')
        self.assertEqual(response.data['data']['execution_mode'], 'pipeline')
        task = Task.objects.get(name='测试任务')
        self.assertEqual(task.execution_mode, 'pipeline')

    def test_create_task_with_state_machine_mode(self):
        """Create a task with state_machine execution mode."""
        self.client.force_authenticate(user=self.operator)
        response = self.client.post(
            '/api/v2/tasks/',
            {
                'name': '状态机任务',
                'execution_mode': 'state_machine',
                'task_definition': {'states': []},
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['data']['execution_mode'], 'state_machine')

    def test_create_task_missing_name(self):
        """Create task without name should fail."""
        self.client.force_authenticate(user=self.operator)
        response = self.client.post(
            '/api/v2/tasks/',
            {'execution_mode': 'pipeline', 'task_definition': {'nodes': []}},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_task_invalid_execution_mode(self):
        """Create task with invalid execution_mode should fail."""
        self.client.force_authenticate(user=self.operator)
        response = self.client.post(
            '/api/v2/tasks/',
            {
                'name': '无效模式任务',
                'execution_mode': 'invalid_mode',
                'task_definition': {'nodes': []},
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestTaskListRetrieve(TestCase):
    """Task list and retrieve tests."""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.operator = OperatorUserFactory()
        self.client = APIClient()
        self.task1 = Task.objects.create(
            name='任务A',
            execution_mode='pipeline',
            task_definition={'nodes': []},
            is_enabled=True,
        )
        self.task2 = Task.objects.create(
            name='任务B',
            execution_mode='state_machine',
            task_definition={'states': []},
            is_enabled=False,
        )

    def test_list_tasks(self):
        """List all tasks (paginated response)."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/v2/tasks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['count'], 2)
        self.assertEqual(len(response.data['data']['results']), 2)

    def test_list_tasks_as_viewer(self):
        """Viewer can list tasks (read-only)."""
        viewer = User.objects.create_user(
            username='task_viewer',
            password='ViewerPass123!',
            role=User.Role.VIEWER,
        )
        self.client.force_authenticate(user=viewer)
        response = self.client.get('/api/v2/tasks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_tasks_unauthenticated(self):
        """Unauthenticated user cannot list tasks."""
        response = self.client.get('/api/v2/tasks/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_task(self):
        """Retrieve a single task by ID."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/v2/tasks/{self.task1.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['name'], '任务A')

    def test_retrieve_nonexistent_task(self):
        """Retrieve non-existent task returns 404."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/v2/tasks/99999/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_filter_by_execution_mode(self):
        """Filter tasks by execution_mode."""
        self.client.force_authenticate(user=self.admin)
        # spec-2026-07-27-execution-path-unification: chain 已废弃，过滤用 pipeline
        response = self.client.get('/api/v2/tasks/?execution_mode=pipeline')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['count'], 1)
        self.assertEqual(response.data['data']['results'][0]['name'], '任务A')

    def test_filter_by_is_enabled(self):
        """Filter tasks by is_enabled."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/v2/tasks/?is_enabled=false')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['count'], 1)
        self.assertEqual(response.data['data']['results'][0]['name'], '任务B')


class TestTaskUpdateDelete(TestCase):
    """Task update and delete tests."""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.operator = OperatorUserFactory()
        self.viewer = User.objects.create_user(
            username='task_upd_viewer',
            password='ViewerPass123!',
            role=User.Role.VIEWER,
        )
        self.client = APIClient()
        self.task = Task.objects.create(
            name='待更新任务',
            execution_mode='pipeline',
            task_definition={'nodes': []},
        )

    def test_update_task_put(self):
        """Full update via PUT."""
        self.client.force_authenticate(user=self.operator)
        response = self.client.put(
            f'/api/v2/tasks/{self.task.pk}/',
            {
                'name': '更新后任务',
                'execution_mode': 'state_machine',
                'task_definition': {'states': []},
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['name'], '更新后任务')
        self.task.refresh_from_db()
        self.assertEqual(self.task.execution_mode, 'state_machine')

    def test_update_task_patch(self):
        """Partial update via PATCH."""
        self.client.force_authenticate(user=self.operator)
        response = self.client.patch(
            f'/api/v2/tasks/{self.task.pk}/',
            {'is_enabled': False},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.task.refresh_from_db()
        self.assertFalse(self.task.is_enabled)

    def test_delete_task(self):
        """Delete a task."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/v2/tasks/{self.task.pk}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())

    def test_viewer_cannot_create(self):
        """Viewer cannot create tasks."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.post(
            '/api/v2/tasks/',
            {'name': 'viewer任务', 'execution_mode': 'pipeline', 'task_definition': {'nodes': []}},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_cannot_update(self):
        """Viewer cannot update tasks."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.patch(
            f'/api/v2/tasks/{self.task.pk}/',
            {'is_enabled': False},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_cannot_delete(self):
        """Viewer cannot delete tasks."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.delete(f'/api/v2/tasks/{self.task.pk}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TestTaskValidationAction(TestCase):
    """Task validate action tests."""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client = APIClient()

    def test_validate_pipeline_task_valid(self):
        """Validate a well-formed pipeline task."""
        task = Task.objects.create(
            name='流水线任务',
            execution_mode='pipeline',
            task_definition={'nodes': [{'id': 'n1', 'type': 'click', 'config': {'x': 100, 'y': 200}}]},
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/v2/tasks/{task.pk}/validate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()['valid'])

    def test_validate_pipeline_task_missing_required_field(self):
        """Validate pipeline task with node missing required field (templateId).

        N192 B3 P1: 缺 type/node_type 不再早期 fail (交给 PipelineValidator,
        node_required.get(None)=[]), 改为测试缺必填字段 (template_match 缺
        templateId/threshold) 触发 fail.
        """
        task = Task.objects.create(
            name='缺字段任务',
            execution_mode='pipeline',
            task_definition={
                'nodes': [
                    {'id': 'n1', 'node_type': 'template_match', 'config': {}},
                ],
            },
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/v2/tasks/{task.pk}/validate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.json()['valid'])
        # 应返回 CheckItem dict 列表
        errors = response.json()['errors']
        self.assertIsInstance(errors, list)
        if errors:
            self.assertIsInstance(errors[0], dict)

    def test_validate_state_machine_task_valid(self):
        """Validate a well-formed state_machine task."""
        task = Task.objects.create(
            name='状态机任务',
            execution_mode='state_machine',
            task_definition={
                'states': [{'name': 'idle', 'transitions': []}]
            },
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/v2/tasks/{task.pk}/validate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()['valid'])

    def test_validate_empty_task_definition(self):
        """Validate task with empty task_definition."""
        task = Task.objects.create(
            name='空定义任务',
            execution_mode='pipeline',
            task_definition={},
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/v2/tasks/{task.pk}/validate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_validate_returns_check_items_with_node_id(self):
        """validate action 应返回 list[dict] 含 node_id/suggestion, 而非 list[str].

        N192 B3 P1: 用 templateId='' + threshold=0.5 触发校验, 验证返回的
        CheckItem 是 dict 含 check/status/message/node_id/suggestion 字段.
        Spec Task 1.5 设计变更: templateId='' 现在触发 fail (400), 不再是 warn.
        """
        task = Task.objects.create(
            name='warn任务',
            execution_mode='pipeline',
            task_definition={
                'nodes': [
                    {'id': 'n1', 'node_type': 'template_match',
                     'config': {'templateId': '', 'threshold': 0.5}},
                ],
            },
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/v2/tasks/{task.pk}/validate/', {}, format='json')
        # Spec Task 1.5 设计变更: templateId='' 触发 fail, 返回 400
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertIn('errors', body)
        # errors 应该是 list[dict] 含 check/status/message/node_id/suggestion 字段
        self.assertIsInstance(body['errors'], list)
        # 应至少有 1 项 fail (templateId 为空), 否则无法验证 dict 结构
        self.assertGreater(len(body['errors']), 0)
        for item in body['errors']:
            self.assertIsInstance(item, dict)
            self.assertIn('check', item)
            self.assertIn('status', item)
            self.assertIn('message', item)
            self.assertIn('node_id', item)
            self.assertIn('suggestion', item)

    def test_validate_returns_check_items_for_failing_node(self):
        """缺必填字段的节点应返回 fail 状态的 CheckItem, 含 node_id."""
        task = Task.objects.create(
            name='缺threshold任务',
            execution_mode='pipeline',
            task_definition={
                'nodes': [
                    {'id': 'n1', 'node_type': 'template_match', 'config': {'templateId': 'tpl_1'}},
                    # 缺 threshold 字段
                ],
            },
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/v2/tasks/{task.pk}/validate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body['valid'])
        # errors 应包含 node_id='n1' 的 fail 项
        fails = [e for e in body['errors'] if e.get('status') == 'fail']
        self.assertGreaterEqual(len(fails), 1)
        n1_fails = [e for e in fails if e.get('node_id') == 'n1']
        self.assertGreaterEqual(len(n1_fails), 1)
        # 应该有 suggestion 字段
        self.assertTrue(any(e.get('suggestion') for e in n1_fails))

    def test_validate_empty_task_definition_returns_check_item_dict(self):
        """空 task_definition 的早期错误也应返回 dict 列表 (不是 list[str])."""
        task = Task.objects.create(
            name='空定义任务',
            execution_mode='pipeline',
            task_definition={},
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/v2/tasks/{task.pk}/validate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body['valid'])
        # errors 应是 list[dict], 即使是早期结构错误
        self.assertIsInstance(body['errors'], list)
        if len(body['errors']) > 0:
            first = body['errors'][0]
            self.assertIsInstance(first, dict)
            self.assertIn('message', first)

    def test_validate_state_machine_task_invalid_empty_states(self):
        """state_machine 模式 states=[] 应返回 400 + CheckItem dict 列表."""
        task = Task.objects.create(
            name='空states任务',
            execution_mode='state_machine',
            task_definition={'states': []},
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/v2/tasks/{task.pk}/validate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body['valid'])
        # errors 应是 list[dict] 含 check/status/message 字段
        self.assertIsInstance(body['errors'], list)
        self.assertGreater(len(body['errors']), 0)
        first = body['errors'][0]
        self.assertIsInstance(first, dict)
        self.assertIn('check', first)
        self.assertIn('status', first)
        self.assertIn('message', first)

    def test_validate_state_machine_task_invalid_missing_fields(self):
        """state_machine 模式 state 缺 name/transitions 应返回 400 + CheckItem dict."""
        task = Task.objects.create(
            name='缺字段states任务',
            execution_mode='state_machine',
            task_definition={'states': [{'foo': 'bar'}]},  # 缺 name 和 transitions
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/v2/tasks/{task.pk}/validate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body['valid'])
        self.assertGreater(len(body['errors']), 0)
        # 应该有两条错误: 缺 name + 缺 transitions
        messages = [e['message'] for e in body['errors']]
        self.assertTrue(any('name' in m for m in messages))
        self.assertTrue(any('transitions' in m for m in messages))

    def test_validate_non_dict_task_definition(self):
        """task_definition 是 list/string 时应返回 400 + CheckItem dict."""
        task = Task.objects.create(
            name='非dict任务',
            execution_mode='pipeline',
            task_definition=[],  # list 而非 dict
        )
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/v2/tasks/{task.pk}/validate/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body['valid'])
        self.assertIsInstance(body['errors'], list)
        self.assertGreater(len(body['errors']), 0)
        first = body['errors'][0]
        self.assertIsInstance(first, dict)
        self.assertIn('message', first)
