"""
A5 登录设备管理测试

覆盖：
- UserSession 模型字段与索引
- 登录流程创建 UserSession 记录
- access token 包含 session_jti claim
- GET /api/v2/accounts/auth/sessions/ 列出活跃会话
- DELETE /api/v2/accounts/auth/sessions/<id>/ 踢下线指定会话
- POST /api/v2/accounts/auth/sessions/logout-all-others/ 批量踢下线
- 当前会话标记 is_current=True
- 不能踢下线当前会话
- User-Agent 解析 (browser + OS + device_type)
- 2FA 登录流程也创建 UserSession
"""
from datetime import timedelta

import pytest
from django.test import TestCase
from django.utils.timezone import now
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from accounts.models import User, UserSession
from accounts.serializers import CustomTokenObtainPairSerializer

pytestmark = pytest.mark.integration


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


class TestUserSessionModel(TestCase):
    """UserSession 模型基础测试"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='model_user',
            password='testpass123',
            role=User.Role.OPERATOR,
        )

    def test_create_session(self):
        """用例1: 创建 UserSession 记录"""
        session = UserSession.objects.create(
            user=self.user,
            refresh_token_jti='test-jti-001',
            device_name='Chrome on Windows 10',
            device_type=UserSession.DeviceType.WEB,
            ip_address='192.168.1.1',
            user_agent='Mozilla/5.0 Chrome/120',
            expires_at=now() + timedelta(days=7),
        )
        self.assertEqual(session.refresh_token_jti, 'test-jti-001')
        self.assertTrue(session.is_active)
        self.assertEqual(session.device_type, UserSession.DeviceType.WEB)
        self.assertIsNotNone(session.created_at)
        self.assertIsNotNone(session.last_activity)

    def test_jti_unique(self):
        """用例2: refresh_token_jti 必须唯一"""
        UserSession.objects.create(
            user=self.user,
            refresh_token_jti='unique-jti',
            expires_at=now() + timedelta(days=7),
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            UserSession.objects.create(
                user=self.user,
                refresh_token_jti='unique-jti',
                expires_at=now() + timedelta(days=7),
            )

    def test_str_representation(self):
        """用例3: __str__ 返回用户名 + 设备名"""
        session = UserSession.objects.create(
            user=self.user,
            refresh_token_jti='str-jti',
            device_name='Firefox on macOS',
            ip_address='10.0.0.1',
            expires_at=now() + timedelta(days=7),
        )
        self.assertIn('model_user', str(session))
        self.assertIn('Firefox on macOS', str(session))

    def test_user_related_name_sessions(self):
        """用例4: User.sessions related_name 反向查询"""
        UserSession.objects.create(
            user=self.user,
            refresh_token_jti='related-jti-1',
            expires_at=now() + timedelta(days=7),
        )
        UserSession.objects.create(
            user=self.user,
            refresh_token_jti='related-jti-2',
            expires_at=now() + timedelta(days=7),
        )
        self.assertEqual(self.user.sessions.count(), 2)


class TestLoginCreatesSession(TestCase):
    """登录流程创建 UserSession 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='login_user',
            password='testpass123',
            role=User.Role.OPERATOR,
        )

    def test_login_creates_session(self):
        """用例5: 登录成功后创建 UserSession 记录"""
        response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {
                'username': 'login_user',
                'password': 'testpass123',
                'remember_me': False,
            },
            format='json',
            HTTP_USER_AGENT='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0',
            REMOTE_ADDR='192.168.1.100',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.sessions.count(), 1)

        session = self.user.sessions.first()
        self.assertTrue(session.is_active)
        self.assertIn('Chrome', session.device_name)
        self.assertIn('Windows', session.device_name)
        self.assertEqual(session.device_type, UserSession.DeviceType.WEB)
        self.assertEqual(session.ip_address, '192.168.1.100')

    def test_access_token_contains_session_jti(self):
        """用例6: access token 包含 session_jti claim"""
        response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {
                'username': 'login_user',
                'password': 'testpass123',
            },
            format='json',
            HTTP_USER_AGENT='Mozilla/5.0 Chrome/120',
        )
        # Task 4.49 (P0-12, 2026-07-28): 修复 token 取值路径 (unified_response 信封)。
        access_str = response.data.get('data', {}).get('access') or response.data.get('access')
        access = AccessToken(access_str)
        session_jti = access.payload.get('session_jti')
        self.assertIsNotNone(session_jti)

        session = self.user.sessions.first()
        self.assertEqual(session_jti, session.refresh_token_jti)

    def test_remember_me_extends_expiry(self):
        """用例7: remember_me=True 时 UserSession.expires_at 延长到 30 天"""
        from django.conf import settings
        self.client.post(
            '/api/v2/accounts/auth/login/',
            {
                'username': 'login_user',
                'password': 'testpass123',
                'remember_me': True,
            },
            format='json',
            HTTP_USER_AGENT='Mozilla/5.0',
        )
        session = self.user.sessions.first()
        remember_days = getattr(settings, 'GAF_REMEMBER_ME_DAYS', 30)
        # Should be roughly remember_days in the future (within 1 minute tolerance)
        expected_min = now() + timedelta(days=remember_days, minutes=-1)
        expected_max = now() + timedelta(days=remember_days, minutes=1)
        self.assertGreater(session.expires_at, expected_min)
        self.assertLess(session.expires_at, expected_max)


class TestUserAgentParsing(TestCase):
    """User-Agent 解析测试"""

    def test_parse_chrome_windows(self):
        """用例8: Chrome on Windows 10 解析"""
        ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0'
        name, dtype = CustomTokenObtainPairSerializer._parse_user_agent(ua)
        self.assertIn('Chrome', name)
        self.assertIn('Windows', name)
        self.assertEqual(dtype, UserSession.DeviceType.WEB)

    def test_parse_firefox_macos(self):
        """用例9: Firefox on macOS 解析"""
        ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Gecko/20100101 Firefox/121.0'
        name, dtype = CustomTokenObtainPairSerializer._parse_user_agent(ua)
        self.assertIn('Firefox', name)
        self.assertIn('macOS', name)
        self.assertEqual(dtype, UserSession.DeviceType.WEB)

    def test_parse_mobile_android(self):
        """用例10: Android 移动端解析为 MOBILE"""
        ua = 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 Chrome/120.0'
        name, dtype = CustomTokenObtainPairSerializer._parse_user_agent(ua)
        self.assertEqual(dtype, UserSession.DeviceType.MOBILE)

    def test_parse_api_client(self):
        """用例11: python-requests 解析为 API"""
        ua = 'python-requests/2.31.0'
        name, dtype = CustomTokenObtainPairSerializer._parse_user_agent(ua)
        self.assertEqual(dtype, UserSession.DeviceType.API)

    def test_parse_empty_ua(self):
        """用例12: 空 UA 返回 Unknown"""
        name, dtype = CustomTokenObtainPairSerializer._parse_user_agent('')
        self.assertEqual(name, 'Unknown')
        self.assertEqual(dtype, UserSession.DeviceType.UNKNOWN)

    def test_parse_edge_browser(self):
        """用例13: Edge 浏览器解析"""
        ua = 'Mozilla/5.0 (Windows NT 10.0) Edg/120.0.0.0'
        name, dtype = CustomTokenObtainPairSerializer._parse_user_agent(ua)
        self.assertIn('Edge', name)


class TestSessionListAPI(TestCase):
    """GET /api/v2/accounts/auth/sessions/ 列表 API 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='list_user',
            password='testpass123',
            role=User.Role.OPERATOR,
        )
        # Login to get access token
        response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {'username': 'list_user', 'password': 'testpass123'},
            format='json',
            HTTP_USER_AGENT='Mozilla/5.0 Chrome/120',
        )
        # Task 4.49 (P0-12, 2026-07-28): 修复 token 取值路径 (unified_response 信封)。
        self.access_token = response.data.get('data', {}).get('access') or response.data.get('access')

    def test_list_sessions_unauthenticated(self):
        """用例14: 未认证请求返回 401"""
        response = self.client.get('/api/v2/accounts/auth/sessions/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_sessions_authenticated(self):
        """用例15: 认证用户可列出自己的活跃会话"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        response = self.client.get('/api/v2/accounts/auth/sessions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sessions = _unwrap(response)
        self.assertEqual(len(sessions), 1)
        self.assertIn('device_name', sessions[0])
        self.assertIn('is_current', sessions[0])
        self.assertIn('is_active', sessions[0])

    def test_list_sessions_marks_current(self):
        """用例16: 当前会话标记 is_current=True"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        response = self.client.get('/api/v2/accounts/auth/sessions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        current_sessions = [s for s in _unwrap(response) if s['is_current']]
        self.assertEqual(len(current_sessions), 1)

    def test_list_sessions_excludes_inactive(self):
        """用例17: 已下线会话不在列表中"""
        # Create an inactive session
        UserSession.objects.create(
            user=self.user,
            refresh_token_jti='inactive-jti',
            device_name='Old Device',
            is_active=False,
            expires_at=now() + timedelta(days=7),
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        response = self.client.get('/api/v2/accounts/auth/sessions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        sessions = _unwrap(response)
        # Only the active login session should be in the list
        self.assertEqual(len(sessions), 1)
        self.assertNotIn('Old Device', [s['device_name'] for s in sessions])

    def test_list_sessions_excludes_other_users(self):
        """用例18: 用户只能看到自己的会话"""
        other_user = User.objects.create_user(
            username='other_user',
            password='testpass123',
            role=User.Role.OPERATOR,
        )
        UserSession.objects.create(
            user=other_user,
            refresh_token_jti='other-user-jti',
            device_name='Other User Device',
            expires_at=now() + timedelta(days=7),
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        response = self.client.get('/api/v2/accounts/auth/sessions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('Other User Device', [s['device_name'] for s in _unwrap(response)])


class TestSessionKickAPI(TestCase):
    """DELETE /api/v2/accounts/auth/sessions/<id>/ 踢下线 API 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='kick_user',
            password='testpass123',
            role=User.Role.OPERATOR,
        )
        # Login as current session
        response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {'username': 'kick_user', 'password': 'testpass123'},
            format='json',
            HTTP_USER_AGENT='Mozilla/5.0 Chrome/120',
        )
        # Task 4.49 (P0-12, 2026-07-28): 修复 token 取值路径 (unified_response 信封)。
        self.access_token = response.data.get('data', {}).get('access') or response.data.get('access')
        self.current_session = self.user.sessions.first()

        # Create another session to be kicked
        self.other_session = UserSession.objects.create(
            user=self.user,
            refresh_token_jti='other-session-jti',
            device_name='Other Browser',
            device_type=UserSession.DeviceType.WEB,
            expires_at=now() + timedelta(days=7),
        )

    def test_kick_session_success(self):
        """用例19: 踢下线其他会话成功"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        response = self.client.delete(f'/api/v2/accounts/auth/sessions/{self.other_session.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.other_session.refresh_from_db()
        self.assertFalse(self.other_session.is_active)

    def test_kick_session_not_found(self):
        """用例20: 不存在的会话 ID 返回 404"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        response = self.client.delete('/api/v2/accounts/auth/sessions/99999/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_kick_current_session_forbidden(self):
        """用例21: 不能踢下线当前会话"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        response = self.client.delete(f'/api/v2/accounts/auth/sessions/{self.current_session.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_kick_session_blacklists_token(self):
        """用例22: 踢下线时拉黑对应的 refresh token"""
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )
        # Generate a real refresh token to get an OutstandingToken record
        refresh = RefreshToken.for_user(self.user)
        refresh_jti = str(refresh.payload['jti'])
        # Update the other_session's jti to match
        self.other_session.refresh_token_jti = refresh_jti
        self.other_session.save()
        # OutstandingToken is created automatically when RefreshToken is generated
        outstanding = OutstandingToken.objects.filter(
            user=self.user, jti=refresh_jti
        ).first()
        self.assertIsNotNone(outstanding)

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        response = self.client.delete(f'/api/v2/accounts/auth/sessions/{self.other_session.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertTrue(BlacklistedToken.objects.filter(token=outstanding).exists())


class TestLogoutAllOthersAPI(TestCase):
    """POST /api/v2/accounts/auth/sessions/logout-all-others/ 批量踢下线测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='bulk_user',
            password='testpass123',
            role=User.Role.OPERATOR,
        )
        response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {'username': 'bulk_user', 'password': 'testpass123'},
            format='json',
            HTTP_USER_AGENT='Mozilla/5.0 Chrome/120',
        )
        # Task 4.49 (P0-12, 2026-07-28): 修复 token 取值路径 (unified_response 信封)。
        self.access_token = response.data.get('data', {}).get('access') or response.data.get('access')
        self.current_session = self.user.sessions.first()

        # Create 3 other sessions
        self.other_sessions = []
        for i in range(3):
            s = UserSession.objects.create(
                user=self.user,
                refresh_token_jti=f'bulk-other-jti-{i}',
                device_name=f'Device {i}',
                expires_at=now() + timedelta(days=7),
            )
            self.other_sessions.append(s)

    def test_logout_all_others_success(self):
        """用例23: 批量踢下线其他会话成功，当前会话保留"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        response = self.client.post('/api/v2/accounts/auth/sessions/logout-all-others/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('3', _unwrap(response)['detail'])

        # Current session still active
        self.current_session.refresh_from_db()
        self.assertTrue(self.current_session.is_active)

        # Other sessions all inactive
        for s in self.other_sessions:
            s.refresh_from_db()
            self.assertFalse(s.is_active)

    def test_logout_all_others_no_others(self):
        """用例24: 没有其他会话时返回 0"""
        # Kick all other sessions first
        for s in self.other_sessions:
            s.is_active = False
            s.save()

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        response = self.client.post('/api/v2/accounts/auth/sessions/logout-all-others/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('0', _unwrap(response)['detail'])


class Test2FALoginCreatesSession(TestCase):
    """2FA 登录流程创建 UserSession 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='twofa_user',
            password='testpass123',
            role=User.Role.OPERATOR,
        )
        # Enable 2FA
        import pyotp
        self.user.totp_secret = pyotp.random_base32()
        self.user.totp_enabled = True
        self.user.save()

    def test_2fa_login_creates_session(self):
        """用例25: 2FA 登录第二步成功后创建 UserSession"""
        import pyotp
        # Step 1: login to get temp_token
        response = self.client.post(
            '/api/v2/accounts/auth/login/',
            {'username': 'twofa_user', 'password': 'testpass123'},
            format='json',
            HTTP_USER_AGENT='Mozilla/5.0 Chrome/120',
        )
        self.assertTrue(_unwrap(response).get('requires_2fa'))
        temp_token = _unwrap(response)['temp_token']

        # No session should be created yet (only temp token issued)
        self.assertEqual(self.user.sessions.count(), 0)

        # Step 2: 2FA verify
        totp = pyotp.TOTP(self.user.totp_secret)
        code = totp.now()
        response = self.client.post(
            '/api/v2/accounts/auth/login-2fa/',
            {'temp_token': temp_token, 'totp_code': code},
            format='json',
            HTTP_USER_AGENT='Mozilla/5.0 Chrome/120',
            REMOTE_ADDR='10.0.0.1',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _unwrap(response)
        self.assertIn('access', body)

        # Session should now be created
        self.assertEqual(self.user.sessions.count(), 1)
        session = self.user.sessions.first()
        self.assertIn('Chrome', session.device_name)
        self.assertEqual(session.ip_address, '10.0.0.1')

        # Access token should contain session_jti
        access = AccessToken(body['access'])
        self.assertEqual(access.payload.get('session_jti'), session.refresh_token_jti)
