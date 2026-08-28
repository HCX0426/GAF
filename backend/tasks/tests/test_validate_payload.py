"""Task 1.4 (P1-6): validate-payload 端点测试。

校验 POST /api/v2/tasks/validate-payload/ 端点:
- 不写库 (不创建 Task)
- 复用 PipelineValidator 校验逻辑
- 返回 {valid, detail, errors, warnings} 结构 (errors=fail, warnings=warn)

与 test_tasks.py 中 TestTaskValidationAction 的区别:
- TestTaskValidationAction: 测试 validate action (需要 pk, 校验已存在的 Task)
- TestValidatePayload: 测试 validate_payload action (无需 pk, 校验 inline payload)
"""
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.factories import AdminUserFactory
from tasks.models import Task


class TestValidatePayload(TestCase):
    """validate-payload 端点测试 (Task 1.4 P1-6)。"""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client = APIClient()
        self.url = '/api/v2/tasks/validate-payload/'

    def test_validate_payload_valid_task(self):
        """合法 pipeline task_definition 应返回 200 + valid=true, 不创建 Task。"""
        self.client.force_authenticate(user=self.admin)
        task_count_before = Task.objects.count()
        response = self.client.post(
            self.url,
            {
                'task_definition': {
                    'nodes': [
                        {'id': 'n1', 'type': 'click', 'config': {'x': 100, 'y': 200}},
                    ],
                },
                'execution_mode': 'pipeline',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertTrue(body['valid'])
        # 合法 task 不应有 fail 项
        self.assertEqual(body['errors'], [])
        # warnings 字段必须存在 (可能为空, 也可能有孤立节点 warn)
        self.assertIn('warnings', body)
        # 不创建 Task
        self.assertEqual(Task.objects.count(), task_count_before)

    def test_validate_payload_invalid_task(self):
        """缺必填字段的 task_definition 应返回 400 + valid=false, errors 含 fail 项。"""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            self.url,
            {
                'task_definition': {
                    'nodes': [
                        # template_match 缺 templateId/threshold (必填字段)
                        {'id': 'n1', 'node_type': 'template_match', 'config': {}},
                    ],
                },
                'execution_mode': 'pipeline',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body['valid'])
        # errors 应是 list[dict] 含 fail 项
        self.assertIsInstance(body['errors'], list)
        self.assertGreater(len(body['errors']), 0)
        for item in body['errors']:
            self.assertIsInstance(item, dict)
            self.assertEqual(item['status'], 'fail')
            self.assertIn('check', item)
            self.assertIn('message', item)
            self.assertIn('node_id', item)
            self.assertIn('suggestion', item)
        # warnings 字段必须存在 (即使为空)
        self.assertIn('warnings', body)

    def test_validate_payload_does_not_create_task(self):
        """validate-payload 不应创建 Task 记录, 无论 task_definition 合法与否。"""
        self.client.force_authenticate(user=self.admin)
        task_count_before = Task.objects.count()

        # 发送合法 task_definition
        self.client.post(
            self.url,
            {
                'task_definition': {
                    'nodes': [
                        {'id': 'n1', 'type': 'click', 'config': {'x': 100, 'y': 200}},
                    ],
                },
                'execution_mode': 'pipeline',
            },
            format='json',
        )
        # 发送非法 task_definition (空 nodes)
        self.client.post(
            self.url,
            {
                'task_definition': {'nodes': []},
                'execution_mode': 'pipeline',
            },
            format='json',
        )
        # 发送空 task_definition
        self.client.post(
            self.url,
            {'task_definition': {}, 'execution_mode': 'pipeline'},
            format='json',
        )
        # 三次请求都不应创建 Task
        self.assertEqual(Task.objects.count(), task_count_before)

    def test_validate_payload_empty_task_definition(self):
        """空 task_definition 应返回 400 + CheckItem dict 错误。"""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            self.url,
            {'task_definition': {}, 'execution_mode': 'pipeline'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body['valid'])
        self.assertIsInstance(body['errors'], list)
        self.assertGreater(len(body['errors']), 0)
        # 早期结构错误也应是 CheckItem dict
        first = body['errors'][0]
        self.assertIsInstance(first, dict)
        self.assertIn('message', first)
        self.assertEqual(first['status'], 'fail')
        # warnings 字段必须存在
        self.assertEqual(body['warnings'], [])

    def test_validate_payload_non_dict_task_definition(self):
        """非 dict 的 task_definition (如 list) 应返回 400 + CheckItem dict 错误。"""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            self.url,
            {'task_definition': [], 'execution_mode': 'pipeline'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body['valid'])
        self.assertIsInstance(body['errors'], list)
        self.assertGreater(len(body['errors']), 0)
        first = body['errors'][0]
        self.assertIsInstance(first, dict)
        self.assertIn('message', first)

    def test_validate_payload_state_machine_valid(self):
        """合法 state_machine task_definition 应返回 200 + valid=true。"""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            self.url,
            {
                'task_definition': {
                    'states': [{'name': 'idle', 'transitions': []}],
                },
                'execution_mode': 'state_machine',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertTrue(body['valid'])
        self.assertEqual(body['errors'], [])
        self.assertEqual(body['warnings'], [])

    def test_validate_payload_state_machine_invalid_missing_fields(self):
        """state_machine 缺 name/transitions 应返回 400 + CheckItem dict 错误。"""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            self.url,
            {
                'task_definition': {'states': [{'foo': 'bar'}]},
                'execution_mode': 'state_machine',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body['valid'])
        self.assertGreater(len(body['errors']), 0)
        # 应有缺 name 和缺 transitions 两条错误
        messages = [e['message'] for e in body['errors']]
        self.assertTrue(any('name' in m for m in messages))
        self.assertTrue(any('transitions' in m for m in messages))

    def test_validate_payload_template_id_empty_fails(self):
        """template_match 节点 templateId 留空应返回 fail (Task 3.3 P2-3 升级)。

        Task 3.3 之前: templateId='' 只 warn 不 fail, 导致 backend validate
        通过但 agent 执行失败。现在升级为 fail, 避免 schema 漏洞。
        threshold 已填避免必填字段 fail, 突出 templateId 空字符串 fail 行为。
        """
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            self.url,
            {
                'task_definition': {
                    'nodes': [
                        {'id': 'n1', 'node_type': 'template_match',
                         'config': {'templateId': '', 'threshold': 0.5}},
                    ],
                },
                'execution_mode': 'pipeline',
            },
            format='json',
        )
        # 校验失败 (templateId 空字符串升级为 fail)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body['valid'])
        # errors 应包含 template_refs fail 项
        self.assertIsInstance(body['errors'], list)
        self.assertGreater(len(body['errors']), 0)
        template_ref_fails = [
            e for e in body['errors']
            if e.get('check') == 'template_refs' and e.get('status') == 'fail'
        ]
        self.assertGreater(len(template_ref_fails), 0)
        for item in template_ref_fails:
            self.assertIn('message', item)
            self.assertIn('node_id', item)
            self.assertIn('suggestion', item)
            self.assertEqual(item['node_id'], 'n1')

    def test_validate_payload_returns_check_items_with_node_id(self):
        """fail 项的 CheckItem 应含 node_id, 用于前端定位到具体节点 (N192 B3 P1)。"""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            self.url,
            {
                'task_definition': {
                    'nodes': [
                        {'id': 'n1', 'node_type': 'template_match', 'config': {'templateId': 'tpl_1'}},
                        # 缺 threshold 字段 (fail)
                    ],
                },
                'execution_mode': 'pipeline',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = response.json()
        self.assertFalse(body['valid'])
        # 应有 node_id='n1' 的 fail 项
        fails = [e for e in body['errors'] if e.get('status') == 'fail']
        self.assertGreaterEqual(len(fails), 1)
        n1_fails = [e for e in fails if e.get('node_id') == 'n1']
        self.assertGreaterEqual(len(n1_fails), 1)
        # 应有 suggestion 字段
        self.assertTrue(any(e.get('suggestion') for e in n1_fails))

    def test_validate_payload_no_auth(self):
        """未认证用户应返回 401 (IsAuthenticated 权限)。"""
        response = self.client.post(
            self.url,
            {'task_definition': {'nodes': []}, 'execution_mode': 'pipeline'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_validate_payload_default_execution_mode(self):
        """未传 execution_mode 时默认按 pipeline 模式校验。"""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            self.url,
            {
                'task_definition': {
                    'nodes': [
                        {'id': 'n1', 'type': 'click', 'config': {'x': 100, 'y': 200}},
                    ],
                },
                # 不传 execution_mode
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertTrue(body['valid'])
