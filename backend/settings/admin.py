"""
系统设置管理后台配置
"""

from django.contrib import admin

from settings.models import AppSettings, FeatureFlag, UnattendedStrategy


@admin.register(UnattendedStrategy)
class UnattendedStrategyAdmin(admin.ModelAdmin):
    """无人值守策略配置管理后台。"""

    list_display = ('id', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    """功能开关管理后台配置（R37-P3 Stage 7: 从 tasks 迁入，原 tasks 未注册）。"""

    list_display = ('id', 'name', 'enabled', 'rollout_percentage', 'created_at', 'updated_at')
    list_filter = ('enabled',)
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    """应用设置管理后台配置（R37-P3 Stage 7: 从 tasks 迁入）。"""

    list_display = ('id', 'setting_key', 'category', 'description', 'updated_by', 'updated_at')
    list_filter = ('category',)
    search_fields = ('setting_key', 'description')
    readonly_fields = ('created_at', 'updated_at')
