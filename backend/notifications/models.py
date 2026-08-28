from django.conf import settings
from django.db import models


class Notification(models.Model):
    """通知模型，记录系统向用户推送的通知消息。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name='用户',
    )
    title = models.CharField(
        max_length=255,
        verbose_name='标题',
    )
    body = models.TextField(
        verbose_name='内容',
    )
    category = models.CharField(
        max_length=50,
        verbose_name='分类',
    )
    is_read = models.BooleanField(
        default=False,
        verbose_name='是否已读',
    )
    link = models.CharField(
        max_length=512,
        blank=True,
        verbose_name='跳转链接',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
    )

    class Meta:
        db_table = 'notifications_notification'
        ordering = ['-created_at']
        verbose_name = '通知'
        verbose_name_plural = '通知'

    def __str__(self):
        return f'{self.title} -> {self.user}'


class WebhookConfig(models.Model):
    """Webhook 配置模型，存储用户配置的第三方 Webhook 通知渠道。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='webhook_configs',
        verbose_name='用户',
    )
    channel = models.CharField(
        max_length=50,
        verbose_name='渠道',
    )
    url = models.CharField(
        max_length=512,
        verbose_name='Webhook URL',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='是否启用',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
    )

    class Meta:
        db_table = 'notifications_webhookconfig'
        ordering = ['-id']
        verbose_name = 'Webhook 配置'
        verbose_name_plural = 'Webhook 配置'

    def __str__(self):
        return f'{self.channel} ({self.user})'


class AlertRule(models.Model):
    """告警规则模型，定义触发告警的条件与通知方式。

    Migrated from tasks app (R37-P3 Stage 7 Task 20a) — AlertRule is a
    notifications-domain concept (it declares *how* to notify the user when
    a threshold is crossed), so it belongs in the notifications app rather
    than tasks. db_table kept as 'alert_rule' to avoid a data migration;
    the move is state-only (SeparateDatabaseAndState).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='alert_rules',
        verbose_name='用户',
        help_text='规则所属的用户',
    )
    name = models.CharField(
        max_length=100,
        verbose_name='规则名称',
        help_text='告警规则的名称',
    )
    rule_type = models.CharField(
        max_length=50,
        verbose_name='规则类型',
        help_text='告警规则的类型标识',
    )
    threshold = models.IntegerField(
        default=3,
        verbose_name='阈值',
        help_text='触发告警的阈值',
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name='已启用',
        help_text='标记规则是否启用',
    )
    quiet_start = models.TimeField(
        null=True,
        blank=True,
        verbose_name='静默开始',
        help_text='静默时段的开始时间',
    )
    quiet_end = models.TimeField(
        null=True,
        blank=True,
        verbose_name='静默结束',
        help_text='静默时段的结束时间',
    )
    notify_methods = models.JSONField(
        default=list,
        verbose_name='通知方式',
        help_text='告警触发的通知方式列表',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
        help_text='记录创建的时间戳',
    )

    class Meta:
        db_table = 'alert_rule'
        verbose_name = '告警规则'
        verbose_name_plural = '告警规则'

    def __str__(self):
        return f'{self.name} ({self.user})'


class NotificationPreference(models.Model):
    """User-specific notification preferences (singleton per user).

    Tracks desktop/sound/system in-app channels, category-level toggles,
    quiet hours, and retention policy. Upserted via
    POST /api/v2/notifications/preferences/.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preference',
        verbose_name='用户',
    )
    desktop_notification = models.BooleanField(default=True, verbose_name='桌面通知')
    sound_alert = models.BooleanField(default=True, verbose_name='声音提醒')
    system_notification = models.BooleanField(default=True, verbose_name='系统通知')
    alert_notification = models.BooleanField(default=True, verbose_name='告警通知')
    community_notification = models.BooleanField(default=False, verbose_name='社区通知')
    quiet_hours_start = models.TimeField(
        null=True, blank=True, verbose_name='静默开始时间',
    )
    quiet_hours_end = models.TimeField(
        null=True, blank=True, verbose_name='静默结束时间',
    )
    retention_days = models.IntegerField(
        default=30, verbose_name='通知保留天数',
        help_text='超过 N 天的通知自动清理',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'notifications_notification_preference'
        verbose_name = '通知偏好'
        verbose_name_plural = '通知偏好'

    def __str__(self):
        return f'NotificationPreference ({self.user})'
