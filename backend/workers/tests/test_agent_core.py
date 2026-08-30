"""Agent 模型单元测试"""

import pytest
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from workers.models import Worker

pytestmark = pytest.mark.integration


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


class TestCreateAgent(TestCase):
    """Agent 创建测试"""

    def setUp(self):
        """初始化测试数据：操作员用户、API 客户端"""
        self.operator = User.objects.create_user(
            username='agent_operator',
            password='operatorpass123',
            role=User.Role.OPERATOR,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    def test_create_agent(self):
        """创建 Agent"""
        response = self.client.post(
            '/api/v2/agents/',
            {
                'agent_id': 'agent-create-001',
                'hostname': 'test-host',
                'ip_address': '192.168.1.100',
                'os_info': 'Windows 11',
                'status': 'offline',
                'capabilities': {'screen': True, 'input': True},
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(response)['agent_id'], 'agent-create-001')
        self.assertEqual(_unwrap(response)['hostname'], 'test-host')
        agent = Worker.objects.get(agent_id='agent-create-001')
        self.assertEqual(agent.status, Worker.Status.OFFLINE)


class TestAgentStatus(TestCase):
    """Agent 状态切换测试"""

    def setUp(self):
        """初始化测试数据：操作员用户、Agent、API 客户端"""
        self.operator = User.objects.create_user(
            username='status_operator',
            password='operatorpass123',
            role=User.Role.OPERATOR,
        )
        self.agent = Worker.objects.create(
            agent_id='agent-status-001',
            hostname='status-host',
            status=Worker.Status.OFFLINE,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    def test_agent_status(self):
        """Agent 状态切换 — 从 offline 到 online"""
        response = self.client.patch(
            f'/api/v2/agents/{self.agent.pk}/',
            {'status': 'online'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(response)['status'], 'online')
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, Worker.Status.ONLINE)

    def test_agent_status_to_busy(self):
        """Agent 状态切换 — 从 offline 到 busy"""
        response = self.client.patch(
            f'/api/v2/agents/{self.agent.pk}/',
            {'status': 'busy'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.status, Worker.Status.BUSY)


class TestWorkerToken(TestCase):
    """Worker Token 生成测试"""

    def setUp(self):
        """初始化测试数据：操作员用户、Agent、API 客户端"""
        self.operator = User.objects.create_user(
            username='token_operator',
            password='operatorpass123',
            role=User.Role.OPERATOR,
        )
        self.agent = Worker.objects.create(
            agent_id='agent-token-001',
            hostname='token-host',
            status=Worker.Status.OFFLINE,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    def test_worker_token(self):
        """Worker Token 生成"""
        # TD-141 (2026-07-18): agent_token plaintext field removed.
        self.assertIsNone(self.agent.worker_token_hash)
        response = self.client.post(
            f'/api/v2/agents/{self.agent.pk}/generate-token/',
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _unwrap(response)
        self.assertEqual(body['agent_id'], 'agent-token-001')
        self.assertTrue(body['agent_token'])
        self.agent.refresh_from_db()
        # C4 fix: plaintext is not persisted; hash + preview are stored.
        from gaf_core.utils.tokens import hash_token, make_token_preview
        self.assertEqual(self.agent.worker_token_hash, hash_token(body['agent_token']))
        self.assertEqual(self.agent.worker_token_preview, make_token_preview(body['agent_token']))

    def test_worker_token_regenerate(self):
        """Worker Token 重新生成 — 新 Token 覆盖旧 Token"""
        self.client.post(
            f'/api/v2/agents/{self.agent.pk}/generate-token/',
            format='json',
        )
        self.agent.refresh_from_db()
        old_hash = self.agent.worker_token_hash
        old_preview = self.agent.worker_token_preview
        response = self.client.post(
            f'/api/v2/agents/{self.agent.pk}/generate-token/',
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agent.refresh_from_db()
        # C4 fix: hash must change after regeneration.
        self.assertIsNotNone(old_hash)
        self.assertNotEqual(self.agent.worker_token_hash, old_hash)
        self.assertNotEqual(self.agent.worker_token_preview, old_preview)
