from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenBlacklistView

from accounts.oauth_views import (
    GitHubOAuthCallbackView,
    GitHubOAuthView,
    GoogleOAuthCallbackView,
    GoogleOAuthView,
)
from accounts.views import (
    AgentTokenViewSet,
    APIKeyViewSet,
    AuditLogViewSet,
    ChangePasswordView,
    CheckAdminView,
    CreateAdminView,
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    DeviceScanView,
    EnvCheckView,
    ExamplePacksView,
    GameAccountGroupViewSet,
    GameAccountRotationViewSet,
    GameAccountViewSet,
    ImportExamplePacksView,
    InitStatusView,
    Login2FAView,
    LoginHistoryViewSet,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
    SetupView,
    SystemHealthView,
    TOTPDisableView,
    TOTPSetupView,
    TOTPVerifySetupView,
    UserSessionViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'game-accounts', GameAccountViewSet, basename='game-account')
router.register(r'groups', GameAccountGroupViewSet, basename='account-group')
router.register(r'rotation-rules', GameAccountRotationViewSet, basename='rotation-rule')
router.register(r'api-keys', APIKeyViewSet, basename='api-key')
router.register(r'audit-logs', AuditLogViewSet, basename='audit-log')

urlpatterns = [
    # Auth: login/refresh/logout unified under /api/v2/accounts/auth/
    path('auth/login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('auth/logout/', TokenBlacklistView.as_view(), name='token_blacklist'),
    path('users/me/', MeView.as_view(), name='user-me'),
    path('', include(router.urls)),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/agent-tokens/', AgentTokenViewSet.as_view({
        'get': 'list',
        'post': 'create',
    }), name='agent-token-list'),
    path('auth/agent-tokens/<int:pk>/', AgentTokenViewSet.as_view({
        'delete': 'destroy',
    }), name='agent-token-detail'),
    path('auth/2fa/setup/', TOTPSetupView.as_view(), name='2fa-setup'),
    path('auth/2fa/verify-setup/', TOTPVerifySetupView.as_view(), name='2fa-verify-setup'),
    path('auth/2fa/disable/', TOTPDisableView.as_view(), name='2fa-disable'),
    path('auth/login-2fa/', Login2FAView.as_view(), name='login-2fa'),
    path('auth/sessions/', UserSessionViewSet.as_view({'get': 'list'}), name='session-list'),
    path('auth/sessions/<int:pk>/', UserSessionViewSet.as_view({'delete': 'destroy'}), name='session-detail'),
    path('auth/sessions/logout-all-others/', UserSessionViewSet.as_view({'post': 'logout_all_others'}), name='session-logout-all-others'),
    # M4 Login History — read-only audit trail
    path('login-history/', LoginHistoryViewSet.as_view({'get': 'list'}), name='login-history-list'),
    path('login-history/<int:pk>/', LoginHistoryViewSet.as_view({'get': 'retrieve'}), name='login-history-detail'),
    path('login-history/all/', LoginHistoryViewSet.as_view({'get': 'all_history'}), name='login-history-all'),
    path('auth/password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('auth/oauth/github/', GitHubOAuthView.as_view(), name='oauth-github'),
    path('auth/oauth/github/callback/', GitHubOAuthCallbackView.as_view(), name='oauth-github-callback'),
    path('auth/oauth/google/', GoogleOAuthView.as_view(), name='oauth-google'),
    path('auth/oauth/google/callback/', GoogleOAuthCallbackView.as_view(), name='oauth-google-callback'),
    path('init/status/', InitStatusView.as_view(), name='init-status'),
    path('init/setup/', SetupView.as_view(), name='init-setup'),
    path('init/check-admin/', CheckAdminView.as_view(), name='init-check-admin'),
    path('init/create-admin/', CreateAdminView.as_view(), name='init-create-admin'),
    path('init/health/', SystemHealthView.as_view(), name='init-health'),
    path('init/devices/scan/', DeviceScanView.as_view(), name='init-devices-scan'),
    path('init/example-packs/', ExamplePacksView.as_view(), name='init-example-packs'),
    path('init/import/', ImportExamplePacksView.as_view(), name='init-import'),
    path('init/env-check/', EnvCheckView.as_view(), name='init-env-check'),
]
