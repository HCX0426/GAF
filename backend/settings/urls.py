"""
系统设置路由配置
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from settings.views import (
    AppSettingsViewSet,
    FeatureFlagViewSet,
    LLMConfigViewSet,
    agent_debug_view,
    cleanup_view,
    config_generator_view,
    config_migration_view,
    generate_diagnostic,
    unattended_strategy_view,
    wait_when_background_view,
)

router = DefaultRouter()
# Register LLMConfig as a ViewSet. router.register generates:
#   llm-config/        -> list (GET), create (POST)
#   llm-config/<pk>/   -> retrieve (GET), update (PUT/PATCH), destroy (DELETE)
# These match the former llm_config_view URL paths exactly (no frontend breakage).
router.register(r'llm-config', LLMConfigViewSet, basename='llm-config')
# R37-P3 Stage 7 Task 20a: migrated from tasks/feature-flags (TD-039).
router.register(r'feature-flags', FeatureFlagViewSet, basename='feature-flag')
# R37-P3 Stage 7 Task 20b: migrated from tasks/app-settings (TD-039).
router.register(r'app-settings', AppSettingsViewSet, basename='app-settings')

urlpatterns = [
    path('', include(router.urls)),
    path('unattended-strategy/', unattended_strategy_view, name='unattended-strategy'),
    path('agent-debug/', agent_debug_view, name='agent-debug'),
    path('wait-when-background/', wait_when_background_view, name='wait-when-background'),
    path('diagnostic/', generate_diagnostic, name='diagnostic'),
    path('cleanup/', cleanup_view, name='cleanup'),
    path('config-generator/', config_generator_view, name='config-generator'),
    path('config-migration/', config_migration_view, name='config-migration'),
]
