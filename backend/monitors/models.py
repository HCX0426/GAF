from django.conf import settings
from django.db import models


class SLAMetric(models.Model):
    """SLA 指标模型，记录系统服务等级协议相关的度量数据。

    (Migrated from metrics app — 2026-08-04)
    Field naming follows Prometheus/OpenMetrics conventions (value / labels /
    timestamp). The optional `agent` FK preserves attribution for metrics
    reported by a specific agent; system-level metrics leave it null.
    """

    agent = models.ForeignKey(
        'workers.Worker',
        on_delete=models.CASCADE,
        related_name='sla_metrics',
        null=True,
        blank=True,
        verbose_name='Agent',
        help_text='Agent that reported this metric (null for system-level metrics).',
    )
    metric_name = models.CharField(
        max_length=100,
        verbose_name='指标名称',
    )
    value = models.FloatField(
        verbose_name='指标值',
    )
    labels = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='标签',
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name='时间戳',
    )

    class Meta:
        db_table = 'monitors_slametric'
        ordering = ['-timestamp']
        verbose_name = 'SLA 指标'
        verbose_name_plural = 'SLA 指标'
        indexes = [
            models.Index(fields=['metric_name', 'timestamp'], name='idx_monitors_slametric_name_ts'),
        ]

    def __str__(self):
        return f'{self.metric_name} = {self.value}'


class MonitorRule(models.Model):
    """监控规则模型，定义自动化监控的触发条件和处理策略。

    TD-420 (2026-08-29): 增加 ``rule_kind`` 字段，区分两类规则语义——
    - ``monitor``: 真正的监控/告警规则（心跳超时、步骤执行超时等）
    - ``game_ui``: 资源包导入的游戏 UI 处理规则（弹窗点击/剧情跳过），
      原历史设计误占用本表，现通过 kind 显式分类，避免"监控规则"
      名不副实。

    Agent 端 (MonitorManager) 消费 game_ui 规则做弹窗/剧情自动处理；
    backend 端 escalate 链路消费 monitor 规则 / MonitorEvent 做告警升级。
    """

    class RuleKind(models.TextChoices):
        MONITOR = 'monitor', '监控告警规则'
        GAME_UI = 'game_ui', '游戏 UI 处理规则'

    name = models.CharField(
        max_length=255,
        verbose_name='规则名称',
        help_text='监控规则的显示名称',
    )
    rule_kind = models.CharField(
        max_length=16,
        choices=RuleKind.choices,
        default=RuleKind.MONITOR,
        db_index=True,
        verbose_name='规则类型',
        help_text='monitor=监控告警规则; game_ui=游戏 UI 处理规则(弹窗/剧情)',
    )
    rule_definition = models.JSONField(
        default=dict,
        verbose_name='规则定义',
        help_text='监控规则的完整定义 JSON',
    )
    resource_pack = models.ForeignKey(
        'resources.ResourcePack',
        on_delete=models.CASCADE,
        related_name='monitor_rules',
        verbose_name='资源包',
        help_text='关联的资源包记录',
    )
    is_enabled = models.BooleanField(
        default=True,
        verbose_name='是否启用',
        help_text='标记规则是否处于启用状态',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
        help_text='记录创建的时间戳',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间',
        help_text='记录最近一次更新的时间戳',
    )

    class Meta:
        ordering = ['-id']
        verbose_name = '监控规则'
        verbose_name_plural = '监控规则'

    def __str__(self):
        return self.name


class MonitorEvent(models.Model):
    """监控事件模型，记录监控规则触发后产生的事件及处理结果。"""

    class Severity(models.TextChoices):
        """告警严重级别。P0=紧急需立即处理, P1=高需 30 分钟内处理, P2=中需 1 天内处理, P3=低仅记录。"""
        P0_CRITICAL = 'P0', 'P0 紧急'
        P1_HIGH = 'P1', 'P1 高'
        P2_MEDIUM = 'P2', 'P2 中'
        P3_LOW = 'P3', 'P3 低'

    event_type = models.CharField(
        max_length=100,
        verbose_name='事件类型',
        help_text='监控事件的类型标识',
    )
    severity = models.CharField(
        max_length=2,
        choices=Severity.choices,
        default=Severity.P2_MEDIUM,
        verbose_name='严重级别',
        help_text='P0=紧急/P1=高/P2=中/P3=低, 用于 P-024 告警升级策略',
    )
    handling_result = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='处理结果',
        help_text='事件处理结果的描述',
    )
    screenshot_path = models.CharField(
        max_length=512,
        blank=True,
        verbose_name='截图路径',
        help_text='事件触发时的截图文件路径',
    )
    event_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='事件数据',
        help_text='事件的详细数据',
    )
    agent = models.ForeignKey(
        'workers.Worker',
        on_delete=models.SET_NULL,
        null=True,
        related_name='monitor_events',
        verbose_name='关联 Agent',
        help_text='事件来源的 Agent 记录',
    )
    resource_pack = models.ForeignKey(
        'resources.ResourcePack',
        on_delete=models.SET_NULL,
        null=True,
        related_name='monitor_events',
        verbose_name='资源包',
        help_text='关联的资源包记录',
    )
    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='确认时间',
        help_text='人工确认处理的时间, null=未确认',
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_alerts',
        verbose_name='确认人',
        help_text='确认处理该事件的用户',
    )
    escalated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='升级时间',
        help_text='Celery 任务自动升级的时间, null=未升级',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
        help_text='记录创建的时间戳',
    )

    class Meta:
        db_table = 'monitors_monitorevent'
        ordering = ['-created_at']
        verbose_name = '监控事件'
        verbose_name_plural = '监控事件'
        indexes = [
            models.Index(fields=['agent', 'created_at'], name='idx_monitorevent_agent_created'),
            models.Index(fields=['severity', 'acknowledged_at'], name='idx_monitorevent_sev_ack'),
        ]

    def __str__(self):
        return f'[{self.severity}] {self.event_type} - {self.created_at}'

    @property
    def is_unacknowledged(self):
        """未确认状态: 未确认 AND 未升级。"""
        return self.acknowledged_at is None and self.escalated_at is None
