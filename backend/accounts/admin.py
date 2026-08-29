from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import APIKey, AuditLog, GameAccount, LoginHistory, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """用户管理后台配置。"""

    list_display = ('id', 'username', 'role', 'is_active', 'must_change_password', 'last_login', 'created_at')
    list_filter = ('role', 'is_active', 'must_change_password')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    readonly_fields = ('created_at', 'updated_at', 'last_login', 'date_joined')

    fieldsets = BaseUserAdmin.fieldsets + (
        ('扩展信息', {
            'fields': ('role', 'must_change_password', 'created_at', 'updated_at'),
        }),
    )


@admin.register(GameAccount)
class GameAccountAdmin(admin.ModelAdmin):
    """游戏账号管理后台配置。"""

    list_display = ('id', 'owner', 'game_profile', 'username', 'server_region', 'login_method', 'status', 'is_active', 'created_at')
    list_filter = ('is_active', 'game_profile', 'login_method')
    search_fields = ('game_profile__game_name', 'username', 'server_region')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    """API 密钥管理后台配置。"""

    list_display = ('id', 'name', 'user', 'call_count', 'expires_at', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'user__username')
    readonly_fields = ('created_at', 'call_count', 'key_hash')


@admin.register(LoginHistory)
class LoginHistoryAdmin(admin.ModelAdmin):
    """登录历史管理后台配置。"""

    list_display = ('id', 'user', 'ip_address', 'location', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'ip_address', 'location')
    readonly_fields = ('created_at',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """审计日志管理后台配置。"""

    list_display = ('id', 'user', 'action', 'resource_type', 'resource_id', 'ip_address', 'created_at')
    list_filter = ('action', 'resource_type', 'created_at')
    search_fields = ('user__username', 'action', 'resource_type', 'resource_id')
    readonly_fields = ('created_at',)
