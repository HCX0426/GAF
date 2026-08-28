"""认证流程集成测试：登录→Token刷新→权限检查→注销"""
import pytest
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User

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


class AuthFlowTest(TestCase):
    """认证流程集成测试"""

    def setUp(self):
        """初始化 API 客户端"""
        self.client = APIClient()

    def test_login_with_default_user(self):
        """测试默认用户登录"""
        response = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'user',
            'password': 'user',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _unwrap(response)
        self.assertIn('access', body)
        self.assertIn('refresh', body)

    def test_token_refresh(self):
        """测试Token刷新"""
        login_resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'user',
            'password': 'user',
        })
        refresh_token = _unwrap(login_resp)['refresh']
        response = self.client.post('/api/v2/accounts/auth/refresh/', {
            'refresh': refresh_token,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', _unwrap(response))

    def test_viewer_permissions(self):
        """测试viewer角色权限 — viewer仅可查看，不可执行Agent操作"""
        login_resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'user',
            'password': 'user',
        })
        _token = _login_token(login_resp)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")
        response = self.client.get('/api/v2/agents/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_init_status(self):
        """测试初始化状态检查"""
        response = self.client.get('/api/v2/accounts/init/status/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('initialized', _unwrap(response))

    def test_setup_flow(self):
        """测试首次启动设置流程"""
        response = self.client.post('/api/v2/accounts/init/setup/', {
            'admin_username': 'admin',
            'admin_password': 'admin123',
            'device_type': 'windows',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        admin = User.objects.get(username='admin')
        self.assertEqual(admin.role, 'admin')


class AgentAPITest(TestCase):
    """Agent API 集成测试"""

    def setUp(self):
        """初始化 API 客户端并使用 operator 角色登录"""
        self.client = APIClient()
        self.operator = User.objects.create_user(
            username='operator_test',
            password='testpass123',
            role=User.Role.OPERATOR,
        )
        login_resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'operator_test',
            'password': 'testpass123',
        })
        _token = _login_token(login_resp)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")

    def test_agent_register_and_list(self):
        """测试Agent注册和列表查询"""
        response = self.client.post('/api/v2/agents/', {
            'agent_id': 'test-agent-001',
            'hostname': 'test-host',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get('/api/v2/agents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_agent_generate_token(self):
        """测试Agent Token生成"""
        create_resp = self.client.post('/api/v2/agents/', {
            'agent_id': 'test-agent-002',
            'hostname': 'test-host-2',
        })
        agent_id = _unwrap(create_resp)['id']
        response = self.client.post(f'/api/v2/agents/{agent_id}/generate-token/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('agent_token', _unwrap(response))


class TaskAPITest(TestCase):
    """Task API 集成测试"""

    def setUp(self):
        """初始化 API 客户端、operator 用户和资源包"""
        self.client = APIClient()
        self.operator = User.objects.create_user(
            username='operator_task',
            password='testpass123',
            role=User.Role.OPERATOR,
        )
        login_resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'operator_task',
            'password': 'testpass123',
        })
        _token = _login_token(login_resp)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")
        from resources.models import ResourcePack
        self.resource_pack = ResourcePack.objects.create(
            name='Test Pack',
            version='1.0.0',
            directory_path='/tmp/test_pack',
        )

    def test_task_crud(self):
        """测试任务CRUD"""
        response = self.client.post('/api/v2/tasks/', {
            'name': 'Test Task',
            'execution_mode': 'pipeline',
            'task_definition': {'nodes': []},
            'resource_pack': self.resource_pack.id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        task_id = _unwrap(response)['id']

        response = self.client.get(f'/api/v2/tasks/{task_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(response)['name'], 'Test Task')

        response = self.client.patch(f'/api/v2/tasks/{task_id}/', {
            'name': 'Updated Task',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.delete(f'/api/v2/tasks/{task_id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class SkillAPITest(TestCase):
    """Skill API 集成测试"""

    def setUp(self):
        """初始化 API 客户端并登录"""
        self.client = APIClient()
        self.operator = User.objects.create_user(
            username='operator_skill',
            password='testpass123',
            role=User.Role.OPERATOR,
        )
        login_resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'operator_skill',
            'password': 'testpass123',
        })
        _token = _login_token(login_resp)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")

    def test_skill_list(self):
        """测试Skill列表"""
        response = self.client.get('/api/v2/skills/skills/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_skill_auto_match(self):
        """测试Skill自动匹配"""
        response = self.client.post('/api/v2/skills/skills/auto-match/', {
            'keywords': '日志 错误 分析',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_skill_toggle(self):
        """测试Skill启用/禁用切换"""
        from skills.models import SkillDefinition
        skill = SkillDefinition.objects.create(
            name='test_skill',
            description='测试Skill',
            version='1.0',
            yaml_content='name: test_skill',
            is_builtin=True,
            is_enabled=True,
        )
        response = self.client.post(f'/api/v2/skills/skills/{skill.id}/toggle/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        skill.refresh_from_db()
        self.assertFalse(skill.is_enabled)
