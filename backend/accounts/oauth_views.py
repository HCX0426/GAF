import logging
import secrets

import requests
from django.conf import settings
from django.shortcuts import redirect
from django.utils.timezone import now
from drf_spectacular.utils import OpenApiResponse, OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import LoginHistory, User, UserSession
from accounts.serializers import CustomTokenObtainPairSerializer, UserSerializer
from config.app_info import OAUTH_REQUEST_TIMEOUT

logger = logging.getLogger(__name__)


def _generate_username(provider: str, oauth_uid: str, profile_name: str) -> str:
    """为 OAuth 用户生成唯一用户名。"""
    base = f"{provider}_{profile_name}"
    username = base[:145]
    if not User.objects.filter(username=username).exists():
        return username
    uid_suffix = oauth_uid[-6:]
    username = f"{base[:143]}_{uid_suffix}"
    if not User.objects.filter(username=username).exists():
        return username
    username = f"{base[:140]}_{secrets.token_hex(4)}"
    return username


def _get_or_create_oauth_user(
    provider: str,
    oauth_uid: str,
    profile_name: str,
    email: str = '',
    email_verified: bool = False,
) -> User:
    """通过 OAuth 信息获取或创建用户，返回 User 实例。

    C3 fix: 仅当 ``email_verified=True`` 时才允许通过邮箱匹配现有本地账号。
    GitHub 默认不验证邮箱，若不限制 ``email_verified``，攻击者可用受害者邮箱
    注册 GitHub 即可接管 GAF 账号。
    """
    user = User.objects.filter(oauth_provider=provider, oauth_uid=oauth_uid).first()
    if user:
        return user
    if email and email_verified:
        existing = User.objects.filter(email=email).first()
        if existing and not existing.oauth_provider:
            existing.oauth_provider = provider
            existing.oauth_uid = oauth_uid
            existing.save(update_fields=['oauth_provider', 'oauth_uid'])
            return existing
    username = _generate_username(provider, oauth_uid, profile_name)
    user = User.objects.create_user(
        username=username,
        email=email or '',
        oauth_provider=provider,
        oauth_uid=oauth_uid,
        role=User.Role.VIEWER,
        must_change_password=False,
    )
    return user


def _make_oauth_state(request, provider: str) -> str:
    """C7 fix: generate and store an OAuth ``state`` nonce in the session.

    Mitigates login CSRF — the callback verifies the nonce matches before
    accepting the authorization code.
    """
    state = secrets.token_urlsafe(32)
    request.session[f'oauth_state_{provider}'] = state
    return state


def _verify_oauth_state(request, provider: str) -> bool:
    """C7 fix: verify OAuth ``state`` from query string matches the session value.

    Returns True if state matches (and consumes the stored nonce so it can't be
    replayed); False otherwise.
    """
    stored = request.session.pop(f'oauth_state_{provider}', None)
    received = request.GET.get('state')
    if not stored or not received:
        return False
    # Use secrets.compare_digest to avoid timing attacks.
    return secrets.compare_digest(stored, received)


def _post_login_setup(user: User, request) -> RefreshToken:
    """H4 fix: shared post-login setup for OAuth flows.

    Mirrors CustomTokenObtainPairSerializer._create_user_session:
    1. Issues a RefreshToken
    2. Injects session_jti claim into the access token
    3. Creates a UserSession record (enables logout / force-offline)
    4. Creates a LoginHistory record (audit trail)

    Without this, OAuth logins bypass session management — logout
    can't revoke the session and audit logs are missing.
    """
    refresh = RefreshToken.for_user(user)

    # Inject session_jti claim into access token so UserSessionViewSet
    # can identify the current session (A5).
    refresh_jti = str(refresh.payload.get('jti', ''))
    access_token = refresh.access_token
    if refresh_jti:
        access_token['session_jti'] = refresh_jti

    if not refresh_jti or request is None:
        return refresh

    # Extract IP + User-Agent
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(',')[0].strip()
    else:
        ip_address = request.META.get('REMOTE_ADDR') or '0.0.0.0'

    user_agent = request.META.get('HTTP_USER_AGENT', '')
    device_name, device_type = CustomTokenObtainPairSerializer._parse_user_agent(user_agent)

    # Compute expiry (mirror the non-remember-me branch — OAuth tokens
    # don't carry a "remember me" flag, so default to refresh token lifetime).
    from datetime import timedelta
    expires_at = now() + timedelta(seconds=jwt_settings.REFRESH_TOKEN_LIFETIME.total_seconds())

    try:
        UserSession.objects.create(
            user=user,
            refresh_token_jti=refresh_jti,
            device_name=device_name,
            device_type=device_type,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )
    except Exception:
        logger.warning('OAuth UserSession create failed for user=%s', user.pk, exc_info=True)

    try:
        LoginHistory.objects.create(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            location='',  # GeoIP lookup not implemented
        )
    except Exception:
        logger.warning('OAuth LoginHistory create failed for user=%s', user.pk, exc_info=True)

    return refresh


def _issue_jwt_response(user: User, request) -> Response:
    """为给定用户生成 JWT Token 并返回标准响应。"""
    refresh = _post_login_setup(user, request)
    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': UserSerializer(user).data,
    }, status=status.HTTP_200_OK)


def _issue_jwt_redirect(user: User, request) -> Response:
    """为给定用户生成 JWT Token 并重定向到前端（Token 通过 fragment 传递）。"""
    refresh = _post_login_setup(user, request)
    frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    fragment = (
        f'access={str(refresh.access_token)}'
        f'&refresh={str(refresh)}'
        f'&username={user.username}'
        f'&role={user.role}'
    )
    return redirect(f'{frontend_url}/auth/callback#{fragment}')


class GitHubOAuthView(APIView):
    """GitHub OAuth 登录入口视图。"""

    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={302: OpenApiResponse(description="Redirect to GitHub OAuth authorization URL.")},
        description="Redirect to GitHub OAuth authorization URL.",
    )
    def get(self, request):
        """构建 GitHub OAuth 授权 URL 并重定向。"""
        client_id = getattr(settings, 'GITHUB_CLIENT_ID', '')
        redirect_uri = getattr(settings, 'GITHUB_REDIRECT_URI', '')
        scope = 'read:user user:email'
        # C7 fix: generate and store state nonce to prevent login CSRF.
        state = _make_oauth_state(request, 'github')
        auth_url = (
            f'https://github.com/login/oauth/authorize'
            f'?client_id={client_id}'
            f'&redirect_uri={redirect_uri}'
            f'&scope={scope}'
            f'&state={state}'
        )
        return redirect(auth_url)


class GitHubOAuthCallbackView(APIView):
    """GitHub OAuth 回调处理视图。"""

    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={
            200: OpenApiTypes.OBJECT,
            302: OpenApiResponse(description="Redirect to frontend with JWT token."),
            400: OpenApiTypes.OBJECT,
        },
        description="GitHub OAuth callback — exchanges code for JWT and redirects to frontend.",
    )
    def get(self, request):
        """处理 GitHub OAuth 回调，返回 JWT Token。"""
        # C7 fix: verify state matches the nonce stored at redirect time.
        if not _verify_oauth_state(request, 'github'):
            return Response({'detail': 'OAuth state 校验失败'}, status=status.HTTP_400_BAD_REQUEST)

        code = request.GET.get('code')
        if not code:
            return Response({'detail': '缺少授权码'}, status=status.HTTP_400_BAD_REQUEST)

        client_id = getattr(settings, 'GITHUB_CLIENT_ID', '')
        client_secret = getattr(settings, 'GITHUB_CLIENT_SECRET', '')

        token_resp = requests.post(
            'https://github.com/login/oauth/access_token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code,
            },
            headers={'Accept': 'application/json'},
            timeout=OAUTH_REQUEST_TIMEOUT,
        )
        token_data = token_resp.json()
        access_token = token_data.get('access_token')
        if not access_token:
            return Response({'detail': '获取 GitHub Token 失败'}, status=status.HTTP_400_BAD_REQUEST)

        user_resp = requests.get(
            'https://api.github.com/user',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json',
            },
            timeout=OAUTH_REQUEST_TIMEOUT,
        )
        user_data = user_resp.json()
        github_id = str(user_data.get('id', ''))
        username = user_data.get('login', 'github_user')

        email = ''
        email_verified = False
        email_resp = requests.get(
            'https://api.github.com/user/emails',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json',
            },
            timeout=OAUTH_REQUEST_TIMEOUT,
        )
        if email_resp.status_code == 200:
            emails = email_resp.json()
            for e in emails:
                if e.get('primary') and e.get('verified'):
                    email = e.get('email', '')
                    email_verified = True
                    break
            # C3 fix: do NOT fall back to unverified emails — keep email_verified=False
            # so _get_or_create_oauth_user won't silently link to an existing local account.
            if not email and emails:
                email = emails[0].get('email', '')
                # email_verified stays False

        user = _get_or_create_oauth_user(
            'github', github_id, username, email, email_verified=email_verified,
        )
        return _issue_jwt_redirect(user, request)


class GoogleOAuthView(APIView):
    """Google OAuth 登录入口视图。"""

    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={302: OpenApiResponse(description="Redirect to Google OAuth authorization URL.")},
        description="Redirect to Google OAuth authorization URL.",
    )
    def get(self, request):
        """构建 Google OAuth 授权 URL 并重定向。"""
        client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
        redirect_uri = getattr(settings, 'GOOGLE_REDIRECT_URI', '')
        scope = 'openid email profile'
        # C7 fix: generate and store state nonce to prevent login CSRF.
        state = _make_oauth_state(request, 'google')
        auth_url = (
            'https://accounts.google.com/o/oauth2/v2/auth'
            f'?client_id={client_id}'
            f'&redirect_uri={redirect_uri}'
            f'&response_type=code'
            f'&scope={scope}'
            f'&state={state}'
        )
        return redirect(auth_url)


class GoogleOAuthCallbackView(APIView):
    """Google OAuth 回调处理视图。"""

    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={
            200: OpenApiTypes.OBJECT,
            302: OpenApiResponse(description="Redirect to frontend with JWT token."),
            400: OpenApiTypes.OBJECT,
        },
        description="Google OAuth callback — exchanges code for JWT and redirects to frontend.",
    )
    def get(self, request):
        """处理 Google OAuth 回调，返回 JWT Token。"""
        # C7 fix: verify state matches the nonce stored at redirect time.
        if not _verify_oauth_state(request, 'google'):
            return Response({'detail': 'OAuth state 校验失败'}, status=status.HTTP_400_BAD_REQUEST)

        code = request.GET.get('code')
        if not code:
            return Response({'detail': '缺少授权码'}, status=status.HTTP_400_BAD_REQUEST)

        client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
        client_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', '')
        redirect_uri = getattr(settings, 'GOOGLE_REDIRECT_URI', '')

        token_resp = requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code',
            },
            headers={'Accept': 'application/json'},
            timeout=OAUTH_REQUEST_TIMEOUT,
        )
        token_data = token_resp.json()
        # H6 fix: Google's userinfo endpoint requires access_token, not id_token.
        # The previous implementation sent id_token as Bearer, which Google
        # rejects with 401 — making the entire Google login flow unusable.
        access_token = token_data.get('access_token')
        if not access_token:
            return Response({'detail': '获取 Google Token 失败'}, status=status.HTTP_400_BAD_REQUEST)

        user_info_resp = requests.get(
            'https://openidconnect.googleapis.com/v1/userinfo',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=OAUTH_REQUEST_TIMEOUT,
        )
        user_data = user_info_resp.json()
        google_id = str(user_data.get('sub', ''))
        name = user_data.get('name', 'google_user')
        email = user_data.get('email', '')
        # C3 fix: Google's userinfo endpoint returns email_verified as a string 'true'/'false'.
        email_verified = str(user_data.get('email_verified', 'false')).lower() == 'true'

        user = _get_or_create_oauth_user(
            'google', google_id, name, email, email_verified=email_verified,
        )
        return _issue_jwt_redirect(user, request)
