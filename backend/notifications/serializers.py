"""通知与 Webhook 配置序列化器。"""

from rest_framework import serializers

from notifications.models import AlertRule, Notification, NotificationPreference, WebhookConfig


class NotificationSerializer(serializers.ModelSerializer):
    """通知序列化器。"""

    # M7 fix (2026-08-28): 前端渲染 item.content，但模型字段是 body —
    # 缺此 alias 导致前端通知正文恒为空。保留 body 兼容旧客户端。
    content = serializers.CharField(source='body', read_only=True, required=False)

    class Meta:
        model = Notification
        fields = ['id', 'user', 'title', 'body', 'content', 'category', 'is_read', 'link', 'created_at']
        read_only_fields = ['user']


class WebhookConfigSerializer(serializers.ModelSerializer):
    """Webhook 配置序列化器。"""

    class Meta:
        model = WebhookConfig
        fields = ['id', 'user', 'channel', 'url', 'is_active', 'created_at']
        read_only_fields = ['user']


class AlertRuleSerializer(serializers.ModelSerializer):
    """告警规则序列化器（R37-P3 Stage 7: 从 tasks 迁入）。"""

    class Meta:
        model = AlertRule
        fields = [
            'id', 'name', 'rule_type', 'threshold', 'enabled',
            'quiet_start', 'quiet_end', 'notify_methods', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """通知偏好序列化器 (per-user singleton upsert)."""

    class Meta:
        model = NotificationPreference
        fields = [
            'desktop_notification', 'sound_alert', 'system_notification',
            'alert_notification', 'community_notification',
            'quiet_hours_start', 'quiet_hours_end', 'retention_days',
        ]
