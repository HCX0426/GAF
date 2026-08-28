"""
JWT Token 刷新 & 记住我 功能测试

覆盖：
- Token 刷新 API 正常流程
- 刷新失败（无效/已黑名单 Token）
- 记住我 vs 普通 Token 有效期差异
- 记住我 Token 刷新后保留延长有效期
- Token 黑名单（刷新旋转后旧 Token 不可用）
- 登出后 Token 不可刷新
"""
import time

import pytest
from django.conf import settings
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User

pytestmark = pytest.mark.integration


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


class TestTokenRefresh(TestCase):
    """Token 刷新 API 基础测试"""

    def setUp(self):
        """初始化 API 客户端和测试用户"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            role=User.Role.OPERATOR,
        )

    def test_token_refresh_success(self):
        """用例1: 有效 Refresh Token 可成功刷新获取新 Access Token"""
        refresh = RefreshToken.for_user(self.user)
        response = self.client.post(
            '/api/v2/accounts/auth/refresh/',
            {'refresh': str(refresh)},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', _unwrap(response))

    def test_token_refresh_invalid_token(self):
        """用例2: 无效 Refresh Token 刷新失败返回 401"""
        response = self.client.post(
            '/api/v2/accounts/auth/refresh/',
            {'refresh': 'invalid-refresh-token-string'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TestRememberMeToken(TestCase):
    """记住我 Token 有效期测试"""

    def setUp(self):
        """初始化 API 客户端和测试用户"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='rememberme_user',
            password='testpass123',
            role=User.Role.OPERATOR,
        )

    def test_login_without_remember_me(self):
        """用例3: 不开启记住我时，Refresh Token 使用默认短期有效期"""
        response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {
                'username': 'rememberme_user',
                'password': 'testpass123',
                'remember_me': False,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refresh_str = _unwrap(response)['refresh']
        refresh = RefreshToken(refresh_str)
        payload = refresh.payload
        exp_timestamp = payload['exp']
        now_timestamp = int(time.time())
        days_diff = (exp_timestamp - now_timestamp) / 86400.0
        self.assertLess(days_diff, 31)

        self.assertNotIn('remember_me', payload)

    def test_login_with_remember_me(self):
        """用例4: 开启记住我时，Refresh Token 使用 GAF_REMEMBER_ME_DAYS 有效期"""
        response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {
                'username': 'rememberme_user',
                'password': 'testpass123',
                'remember_me': True,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refresh_str = _unwrap(response)['refresh']
        refresh = RefreshToken(refresh_str)
        payload = refresh.payload

        self.assertTrue(payload.get('remember_me', False))

        exp_timestamp = payload['exp']
        now_timestamp = int(time.time())
        days_diff = (exp_timestamp - now_timestamp) / 86400.0
        expected_days = getattr(settings, 'GAF_REMEMBER_ME_DAYS', 30)
        self.assertAlmostEqual(days_diff, expected_days, delta=1)

    def test_remember_me_token_refresh_preserves_lifetime(self):
        """用例5: 记住我 Token 刷新后，新 Refresh Token 仍保留延长有效期"""
        login_response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {
                'username': 'rememberme_user',
                'password': 'testpass123',
                'remember_me': True,
            },
            format='json',
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        original_refresh = _unwrap(login_response)['refresh']

        refresh_response = self.client.post(
            '/api/v2/accounts/auth/refresh/',
            {'refresh': original_refresh},
            format='json',
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)

        refresh_body = _unwrap(refresh_response)
        if 'refresh' in refresh_body:
            new_refresh = RefreshToken(refresh_body['refresh'])
            new_payload = new_refresh.payload
            self.assertTrue(new_payload.get('remember_me', False))
            exp_timestamp = new_payload['exp']
            now_timestamp = int(time.time())
            days_diff = (exp_timestamp - now_timestamp) / 86400.0
            expected_days = getattr(settings, 'GAF_REMEMBER_ME_DAYS', 30)
            self.assertAlmostEqual(days_diff, expected_days, delta=1)

    def test_remember_me_vs_normal_token_exp_diff(self):
        """用例6: 记住我 Token 有效期显著长于普通 Token"""
        normal_response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {
                'username': 'rememberme_user',
                'password': 'testpass123',
                'remember_me': False,
            },
            format='json',
        )
        normal_refresh = RefreshToken(_unwrap(normal_response)['refresh'])
        normal_exp = normal_refresh.payload['exp']

        remember_response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {
                'username': 'rememberme_user',
                'password': 'testpass123',
                'remember_me': True,
            },
            format='json',
        )
        remember_refresh = RefreshToken(_unwrap(remember_response)['refresh'])
        remember_exp = remember_refresh.payload['exp']

        self.assertGreater(remember_exp - normal_exp, 7 * 86400)


class TestTokenBlacklist(TestCase):
    """Token 黑名单测试"""

    def setUp(self):
        """初始化 API 客户端和测试用户"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='blacklist_user',
            password='testpass123',
            role=User.Role.OPERATOR,
        )

    def test_rotated_token_cannot_be_reused(self):
        """用例7: Token 刷新旋转后，旧 Refresh Token 不可再次使用（已加入黑名单）"""
        login_response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {
                'username': 'blacklist_user',
                'password': 'testpass123',
            },
            format='json',
        )
        original_refresh = _unwrap(login_response)['refresh']

        first_refresh_response = self.client.post(
            '/api/v2/accounts/auth/refresh/',
            {'refresh': original_refresh},
            format='json',
        )
        self.assertEqual(first_refresh_response.status_code, status.HTTP_200_OK)

        second_refresh_response = self.client.post(
            '/api/v2/accounts/auth/refresh/',
            {'refresh': original_refresh},
            format='json',
        )
        self.assertEqual(second_refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_token(self):
        """用例8: 登出后 Refresh Token 加入黑名单，不可再刷新"""
        login_response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {
                'username': 'blacklist_user',
                'password': 'testpass123',
            },
            format='json',
        )
        refresh_token = _unwrap(login_response)['refresh']

        logout_response = self.client.post(
            '/api/v2/accounts/auth/logout/',
            {'refresh': refresh_token},
            format='json',
        )
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)

        refresh_response = self.client.post(
            '/api/v2/accounts/auth/refresh/',
            {'refresh': refresh_token},
            format='json',
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)
