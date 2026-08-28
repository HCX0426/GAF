"""Agent Token API 单元测试：创建、列表、吊销 Token。"""

import pytest
from django.test import TestCase
from gaf_core.utils.tokens import hash_token, make_token_preview
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from agents.models import Agent

pytestmark = pytest.mark.integration


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
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


class TestAgentTokenAPI(TestCase):
    """Agent Token API 接口测试"""

    def setUp(self):
        """初始化测试数据：管理员用户、API 客户端。"""
        self.admin = User.objects.create_user(
            username='token_admin',
            password='adminpass123',
            role=User.Role.ADMIN,
        )
        self.operator = User.objects.create_user(
            username='token_operator',
            password='operatorpass123',
            role=User.Role.OPERATOR,
        )
        self.client = APIClient()

    def _auth_admin(self):
        """以管理员身份认证。"""
        self.client.force_authenticate(user=self.admin)

    def _auth_operator(self):
        """以操作员身份认证。"""
        self.client.force_authenticate(user=self.operator)

    def test_create_agent_token(self):
        """创建 Agent Token 成功，返回完整 Token 信息。"""
        self._auth_admin()
        response = self.client.post(
            '/api/v2/accounts/auth/agent-tokens/',
            {
                'name': 'my-test-agent',
                'permissions': ['task.execute', 'device.control'],
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = _unwrap(response)
        self.assertIn('token', body)
        self.assertIn('agent_id', body)
        self.assertEqual(body['name'], 'my-test-agent')
        self.assertTrue(len(body['token']) > 20)

        agent = Agent.objects.get(agent_id=body['agent_id'])
        self.assertEqual(agent.hostname, 'my-test-agent')
        self.assertEqual(
            agent.capabilities.get('permissions'),
            ['task.execute', 'device.control'],
        )

    def test_create_agent_token_no_permissions(self):
        """创建 Agent Token 不传权限参数时默认空列表。"""
        self._auth_admin()
        response = self.client.post(
            '/api/v2/accounts/auth/agent-tokens/',
            {'name': 'basic-agent'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        agent = Agent.objects.get(agent_id=_unwrap(response)['agent_id'])
        self.assertEqual(agent.capabilities.get('permissions'), [])

    def test_create_agent_token_missing_name(self):
        """创建 Agent Token 缺少名称时返回 400。"""
        self._auth_admin()
        response = self.client.post(
            '/api/v2/accounts/auth/agent-tokens/',
            {'permissions': ['task.execute']},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # unified_response 信封下, 400 错误的 data 可能为 None, 兼容多种形态
        body = _unwrap(response)
        if isinstance(body, dict):
            self.assertIn('name', body)
        else:
            self.assertIsNotNone(response.data)

    def test_create_agent_token_unauthorized(self):
        """未认证用户创建 Token 返回 401。"""
        response = self.client.post(
            '/api/v2/accounts/auth/agent-tokens/',
            {'name': 'unauthorized-agent'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_agent_token_operator_forbidden(self):
        """操作员角色创建 Token 返回 403（需要 manage 权限）。"""
        self._auth_operator()
        response = self.client.post(
            '/api/v2/accounts/auth/agent-tokens/',
            {'name': 'operator-agent'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_agent_tokens(self):
        """列出 Agent Token 时隐藏完整 Token 值。"""
        self._auth_admin()
        # C4 fix: agents are now created with hash + preview, no plaintext.
        long_token = 'abc12345-very-long-token-xyz98765'
        short_token = 'short'
        Agent.objects.create(
            agent_id='list-agent-001',
            hostname='list-agent-1',
            agent_token_hash=hash_token(long_token),
            agent_token_preview=make_token_preview(long_token),
            status=Agent.Status.OFFLINE,
            capabilities={'permissions': ['task.execute']},
        )
        Agent.objects.create(
            agent_id='list-agent-002',
            hostname='list-agent-2',
            agent_token_hash=hash_token(short_token),
            agent_token_preview=make_token_preview(short_token),
            status=Agent.Status.ONLINE,
        )

        response = self.client.get('/api/v2/accounts/auth/agent-tokens/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        tokens = _get_results(response)
        self.assertGreaterEqual(len(tokens), 2)

        found_long = [t for t in tokens if t['name'] == 'list-agent-1']
        self.assertEqual(len(found_long), 1)
        self.assertIn('...', found_long[0]['token_preview'])
        # Plaintext token must never appear in the list response.
        self.assertNotIn('abc12345-very-long-token-xyz98765', str(found_long[0]))

        found_short = [t for t in tokens if t['name'] == 'list-agent-2']
        self.assertEqual(len(found_short), 1)

    def test_list_agent_tokens_unauthorized(self):
        """未认证用户列出 Token 返回 401。"""
        response = self.client.get('/api/v2/accounts/auth/agent-tokens/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_revoke_agent_token(self):
        """吊销 Agent Token 成功，Agent 记录被删除。"""
        self._auth_admin()
        agent = Agent.objects.create(
            agent_id='revoke-agent-001',
            hostname='revoke-agent',
            agent_token_hash=hash_token('token-to-revoke-12345678'),
            agent_token_preview=make_token_preview('token-to-revoke-12345678'),
            status=Agent.Status.OFFLINE,
        )

        response = self.client.delete(f'/api/v2/accounts/auth/agent-tokens/{agent.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('已吊销', _unwrap(response)['detail'])

        with self.assertRaises(Agent.DoesNotExist):
            Agent.objects.get(pk=agent.id)

    def test_revoke_nonexistent_token(self):
        """吊销不存在的 Token 返回 404。"""
        self._auth_admin()
        response = self.client.delete('/api/v2/accounts/auth/agent-tokens/99999/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_revoke_agent_token_unauthorized(self):
        """未认证用户吊销 Token 返回 401。"""
        agent = Agent.objects.create(
            agent_id='unauth-revoke',
            hostname='unauth-revoke',
            agent_token_hash=hash_token('unauth-token'),
            agent_token_preview=make_token_preview('unauth-token'),
            status=Agent.Status.OFFLINE,
        )
        response = self.client.delete(f'/api/v2/accounts/auth/agent-tokens/{agent.id}/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
