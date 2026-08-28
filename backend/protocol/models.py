import uuid

from django.db import models


class AgentSession(models.Model):
    """Agent 会话模型，记录 Agent 的连接会话和运行状态。"""

    class Status(models.TextChoices):
        ONLINE = 'online', 'Online'
        OFFLINE = 'offline', 'Offline'

    agent_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name='Agent 唯一标识',
    )
    name = models.CharField(
        max_length=255,
        verbose_name='名称',
    )
    hostname = models.CharField(
        max_length=255,
        verbose_name='主机名',
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP 地址',
    )
    capabilities = models.JSONField(
        default=dict,
        verbose_name='能力标签',
    )
    resource_quota = models.JSONField(
        default=dict,
        verbose_name='资源配额',
    )
    token_hash = models.CharField(
        max_length=64,
        db_index=True,
        null=True,
        blank=True,
        verbose_name='连接 Token 哈希 (SHA-256)',
        help_text='C5: SHA-256(token) 十六进制摘要，取代 capabilities.agent_token 明文存储。',
    )
    token_preview = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='Token 预览',
        help_text='C5: 前后各 4 位字符预览，用于列表展示，不暴露完整 Token。',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ONLINE,
        verbose_name='状态',
    )
    last_heartbeat = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='最后心跳时间',
    )
    cpu_usage = models.FloatField(
        null=True,
        blank=True,
        verbose_name='CPU 使用率',
    )
    memory_usage = models.FloatField(
        null=True,
        blank=True,
        verbose_name='内存使用率',
    )
    screenshot_fps = models.FloatField(
        null=True,
        blank=True,
        verbose_name='截图 FPS',
    )
    connected_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='连接时间',
    )
    disconnected_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='断开时间',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间',
    )

    class Meta:
        db_table = 'protocol_agentsession'
        ordering = ['-id']
        verbose_name = 'Agent 会话'
        verbose_name_plural = 'Agent 会话'

    def __str__(self):
        return f'{self.name} ({self.get_status_display()})'


class MessageFrameLog(models.Model):
    """消息帧日志模型，记录 Agent 通信的每一帧消息。"""

    class Direction(models.TextChoices):
        INBOUND = 'inbound', 'Inbound'
        OUTBOUND = 'outbound', 'Outbound'

    trace_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        db_index=True,
        verbose_name='追踪 ID',
    )
    message_type = models.CharField(
        max_length=50,
        db_index=True,
        verbose_name='消息类型',
    )
    direction = models.CharField(
        max_length=10,
        choices=Direction.choices,
        verbose_name='消息方向',
    )
    payload = models.JSONField(
        default=dict,
        verbose_name='消息体',
    )
    agent_session = models.ForeignKey(
        AgentSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Agent 会话',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
    )

    class Meta:
        db_table = 'protocol_messageframelog'
        ordering = ['-id']
        verbose_name = '消息帧日志'
        verbose_name_plural = '消息帧日志'

    def __str__(self):
        return f'{self.trace_id} ({self.get_direction_display()})'
