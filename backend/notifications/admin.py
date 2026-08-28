from django.contrib import admin

from .models import AlertRule, Notification, WebhookConfig


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """通知管理后台配置。"""

    list_display = ('id', 'user', 'title', 'category', 'is_read', 'created_at')
    list_filter = ('category', 'is_read')
    search_fields = ('title', 'body', 'user__username')
    readonly_fields = ('created_at',)


@admin.register(WebhookConfig)
class WebhookConfigAdmin(admin.ModelAdmin):
    """Webhook 配置管理后台配置。"""

    list_display = ('id', 'user', 'channel', 'url', 'is_active', 'created_at')
    list_filter = ('channel', 'is_active')
    search_fields = ('url', 'user__username')
    readonly_fields = ('created_at',)


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    """告警规则管理后台配置（R37-P3 Stage 7: 从 tasks 迁入）。"""

    list_display = ('id', 'user', 'name', 'rule_type', 'threshold', 'enabled', 'created_at')
    list_filter = ('rule_type', 'enabled')
    search_fields = ('name', 'user__username')
    readonly_fields = ('created_at',)
