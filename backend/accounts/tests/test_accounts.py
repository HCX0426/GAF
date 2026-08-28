"""用户认证模块单元测试"""

import pyotp
import pytest
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.factories import AdminUserFactory, UserFactory
from accounts.models import User
from accounts.permissions import RoleBasedPermission

pytestmark = pytest.mark.integration


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


class TestCreateDefaultUser(TestCase):
    """默认用户创建测试"""

    def test_create_default_user(self):
        """验证默认用户 user/user 存在且角色为 viewer"""
        user = User.objects.get(username='user')
        self.assertTrue(user.check_password('user'))
        self.assertEqual(user.role, User.Role.VIEWER)
        self.assertTrue(user.must_change_password)


class TestLogin(TestCase):
    """登录相关测试"""

    def setUp(self):
        """初始化 API 客户端和测试用户"""
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin_login',
            password='admin123456',
            role=User.Role.ADMIN,
        )

    def test_login(self):
        """登录获取 JWT Token"""
        response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {'username': 'admin_login', 'password': 'admin123456'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _unwrap(response)
        self.assertIn('access', body)
        self.assertIn('refresh', body)

    def test_login_wrong_password(self):
        """错误密码登录失败"""
        response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {'username': 'admin_login', 'password': 'wrong_password'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TestChangePassword(TestCase):
    """修改密码测试"""

    def setUp(self):
        """初始化 API 客户端和测试用户"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='change_pwd_user',
            password='oldpassword123',
            role=User.Role.OPERATOR,
        )
        self.client.force_authenticate(user=self.user)

    def test_change_password(self):
        """修改密码成功"""
        response = self.client.patch(
            '/api/v2/accounts/auth/change-password/',
            {
                'old_password': 'oldpassword123',
                'new_password': 'newpassword123',
                'confirm_password': 'newpassword123',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpassword123'))
        self.assertFalse(self.user.must_change_password)


class TestRolePermissions(TestCase):
    """角色权限验证测试"""

    def test_role_permissions(self):
        """不同角色权限验证"""
        role_perms = RoleBasedPermission.ROLE_PERMISSIONS
        self.assertIn('view', role_perms['viewer'])
        self.assertNotIn('execute', role_perms['viewer'])
        self.assertIn('execute', role_perms['operator'])
        self.assertIn('manage', role_perms['admin'])
        self.assertNotIn('manage', role_perms['operator'])

    def test_viewer_cannot_create_user(self):
        """viewer 角色无法创建用户"""
        viewer = UserFactory(role=User.Role.VIEWER)
        client = APIClient()
        client.force_authenticate(user=viewer)
        response = client.post(
            '/api/v2/accounts/users/',
            {'username': 'new_user', 'password': 'testpass123', 'role': 'viewer'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_user(self):
        """admin 角色可以创建用户"""
        admin = AdminUserFactory()
        client = APIClient()
        client.force_authenticate(user=admin)
        response = client.post(
            '/api/v2/accounts/users/',
            {'username': 'new_user_by_admin', 'password': 'testpass123', 'role': 'viewer'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class TestInitStatus(TestCase):
    """初始化状态检查测试"""

    def test_init_status(self):
        """初始化状态检查 — 无 admin 时返回未初始化"""
        client = APIClient()
        response = client.get('/api/v2/accounts/init/status/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _unwrap(response)
        self.assertFalse(body['initialized'])
        self.assertFalse(body['has_admin'])

    def test_init_status_after_setup(self):
        """创建 admin 后初始化状态为已初始化"""
        AdminUserFactory()
        client = APIClient()
        response = client.get('/api/v2/accounts/init/status/', format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _unwrap(response)
        self.assertTrue(body['initialized'])
        self.assertTrue(body['has_admin'])


class Test2FA(TestCase):
    """TOTP 二次验证测试"""

    def setUp(self):
        """初始化 API 客户端和测试用户"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='2fa_user',
            password='password123',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.user)

    def test_totp_setup(self):
        """未启用 2FA 的用户可以获取 TOTP 设置信息"""
        response = self.client.post('/api/v2/accounts/auth/2fa/setup/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _unwrap(response)
        self.assertIn('secret', body)
        self.assertIn('otp_uri', body)
        self.assertTrue(body['otp_uri'].startswith('otpauth://totp/'))

    def test_totp_setup_already_enabled(self):
        """已启用 2FA 的用户不能重新初始化设置"""
        self.user.totp_enabled = True
        self.user.save(update_fields=['totp_enabled'])
        response = self.client.post('/api/v2/accounts/auth/2fa/setup/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('message', response.data)

    def test_totp_verify_setup(self):
        """使用正确的 TOTP 码启用 2FA"""
        setup_response = self.client.post('/api/v2/accounts/auth/2fa/setup/')
        secret = _unwrap(setup_response)['secret']
        totp = pyotp.TOTP(secret)

        response = self.client.post(
            '/api/v2/accounts/auth/2fa/verify-setup/',
            {'totp_code': totp.now()},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.totp_enabled)

    def test_totp_verify_setup_invalid_code(self):
        """使用错误的 TOTP 码无法启用 2FA"""
        self.client.post('/api/v2/accounts/auth/2fa/setup/')
        response = self.client.post(
            '/api/v2/accounts/auth/2fa/verify-setup/',
            {'totp_code': '000000'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)

    def test_login_requires_2fa(self):
        """启用 2FA 的用户登录后返回临时 Token"""
        setup_response = self.client.post('/api/v2/accounts/auth/2fa/setup/')
        secret = _unwrap(setup_response)['secret']
        self.client.post(
            '/api/v2/accounts/auth/2fa/verify-setup/',
            {'totp_code': pyotp.TOTP(secret).now()},
            format='json',
        )

        client = APIClient()
        response = client.post(
            '/api/v2/accounts/auth/login/',
            {'username': '2fa_user', 'password': 'password123'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _unwrap(response)
        self.assertTrue(body['requires_2fa'])
        self.assertIn('temp_token', body)
        self.assertNotIn('access', body)

    def test_login_2fa_with_temp_token(self):
        """使用临时 Token 和正确 TOTP 码换取完整 JWT"""
        setup_response = self.client.post('/api/v2/accounts/auth/2fa/setup/')
        secret = _unwrap(setup_response)['secret']
        self.client.post(
            '/api/v2/accounts/auth/2fa/verify-setup/',
            {'totp_code': pyotp.TOTP(secret).now()},
            format='json',
        )

        client = APIClient()
        login_response = client.post(
            '/api/v2/accounts/auth/login/',
            {'username': '2fa_user', 'password': 'password123'},
            format='json',
        )
        temp_token = _unwrap(login_response)['temp_token']

        response = client.post(
            '/api/v2/accounts/auth/login-2fa/',
            {
                'temp_token': temp_token,
                'totp_code': pyotp.TOTP(secret).now(),
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _unwrap(response)
        self.assertIn('access', body)
        self.assertIn('refresh', body)
        self.assertEqual(body['user']['username'], '2fa_user')

    def test_disable_2fa(self):
        """使用正确密码禁用 2FA"""
        setup_response = self.client.post('/api/v2/accounts/auth/2fa/setup/')
        secret = _unwrap(setup_response)['secret']
        self.client.post(
            '/api/v2/accounts/auth/2fa/verify-setup/',
            {'totp_code': pyotp.TOTP(secret).now()},
            format='json',
        )

        response = self.client.post(
            '/api/v2/accounts/auth/2fa/disable/',
            {'password': 'password123'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.totp_enabled)
        self.assertIsNone(self.user.totp_secret)
