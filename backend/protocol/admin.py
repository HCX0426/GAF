from django.contrib import admin

from .models import MessageFrameLog, WorkerSession


@admin.register(WorkerSession)
class WorkerSessionAdmin(admin.ModelAdmin):
    """Agent 会话管理后台配置。"""

    list_display = ('id', 'agent_id', 'name', 'hostname', 'ip_address', 'status', 'last_heartbeat', 'connected_at')
    list_filter = ('status',)
    search_fields = ('agent_id', 'name', 'hostname', 'ip_address')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MessageFrameLog)
class MessageFrameLogAdmin(admin.ModelAdmin):
    """消息帧日志管理后台配置。"""

    list_display = ('id', 'trace_id', 'message_type', 'direction', 'agent_session', 'created_at')
    list_filter = ('direction', 'message_type')
    search_fields = ('trace_id', 'message_type')
    readonly_fields = ('created_at',)
