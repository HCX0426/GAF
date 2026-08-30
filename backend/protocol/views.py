"""Agent 会话管理、消息帧日志查询 REST API。"""

import secrets

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from gaf_core.audit_constants import AuditAction, AuditResourceType
from gaf_core.mixins import AuditMixin, audit_action, build_diff_details
from gaf_core.utils.tokens import hash_token, make_token_preview
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import RoleBasedPermission
from protocol.models import MessageFrameLog, WorkerSession
from protocol.serializers import (
    WorkerRegisterPayloadSerializer,
)


class WorkerSessionViewSet(AuditMixin, viewsets.ModelViewSet):
    """Agent 会话管理视图集，支持列表查询、详情查看和心跳更新。"""

    queryset = WorkerSession.objects.all()
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'hostname']
    search_fields = ['name', 'hostname', 'ip_address']
    audit_resource_type = AuditResourceType.AGENT_SESSION
    # Use agent_id (UUID) as resource_id so audit logs can be cross-
    # referenced with WebSocket layer / agent-side logs that all use
    # the UUID (not the database pk).
    audit_resource_id_attr = 'agent_id'

    def get_serializer_class(self):
        """根据操作返回对应序列化器（动态导入避免循环引用）。"""
        from protocol.serializers import WorkerSessionListSerializer, WorkerSessionSerializer
        if self.action == 'list':
            return WorkerSessionListSerializer
        return WorkerSessionSerializer

    def get_permissions(self):
        """生成 Token 需要 manage 权限。"""
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'generate_token'):
            self.required_permission = 'manage'
        else:
            self.required_permission = 'view'
        return super().get_permissions()

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build before/after diff for audit log.

        ``token_hash`` / ``token_preview`` are derived from the secret
        connection token; never include raw values, but recording the
        hash + preview is safe (they are already non-reversible).
        ``capabilities`` may carry operator-supplied config; treat as
        sensitive to avoid leaking operational config.
        """
        snapshot_keys = ("name", "hostname", "status", "token_preview")
        sensitive = {"capabilities", "token_hash", "resource_quota", "secret", "token"}
        if action == AuditAction.CREATE:
            return build_diff_details(
                before=None,
                after={k: str(getattr(instance, k, None) or "") for k in snapshot_keys},
                sensitive_extra=sensitive,
            )
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: str(getattr(old_instance, k, None) or "") for k in snapshot_keys},
                after={k: str(getattr(instance, k, None) or "") for k in snapshot_keys},
                sensitive_extra=sensitive,
            )
        if action == AuditAction.DELETE:
            return build_diff_details(
                before={k: str(getattr(instance, k, None) or "") for k in snapshot_keys},
                after=None,
                sensitive_extra=sensitive,
            )
        return {}

    @action(detail=True, methods=['post'], url_path='generate-token')
    @audit_action(AuditAction.EXECUTE, AuditResourceType.AGENT_SESSION)
    def generate_token(self, request, pk=None):
        """为 WorkerSession 生成新的连接 Token。

        Note: the actual token value is returned in the response but
        deliberately not written to ``AuditLog.details`` — only the
        ``token_preview`` (first/last 4 chars) is recorded via the
        ViewSet's ``_build_audit_details`` hook.
        """
        session = self.get_object()
        token = secrets.token_urlsafe(32)
        # C5 fix: store hash + preview in dedicated fields; remove plaintext
        # from capabilities JSON.
        session.token_hash = hash_token(token)
        session.token_preview = make_token_preview(token)
        caps = dict(session.capabilities or {})
        caps.pop('agent_token', None)
        session.capabilities = caps
        session.save(update_fields=['capabilities', 'token_hash', 'token_preview', 'updated_at'])
        return Response({'agent_id': str(session.agent_id), 'token': token}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='heartbeat')
    @audit_action(AuditAction.UPDATE, AuditResourceType.AGENT_SESSION)
    def heartbeat(self, request, pk=None):
        """Agent 心跳上报 REST 接口（备选，主通道为 WebSocket）。"""
        session = self.get_object()
        serializer = WorkerRegisterPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session.last_heartbeat = timezone.now()
        resource_stats = serializer.validated_data.get('resource_quota', {})
        session.cpu_usage = resource_stats.get('cpu_percent')
        session.memory_usage = resource_stats.get('memory_percent')
        # M1: use enum constant instead of hardcoded string.
        session.status = WorkerSession.Status.ONLINE
        session.save()
        return Response({'status': 'ok'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='online')
    def online(self, request):
        """获取所有在线 WorkerSession 列表。"""
        # M1: use enum constant instead of hardcoded string.
        online_sessions = self.get_queryset().filter(status=WorkerSession.Status.ONLINE)
        from protocol.serializers import WorkerSessionListSerializer
        serializer = WorkerSessionListSerializer(online_sessions, many=True)
        return Response({'items': serializer.data}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """获取 Agent 汇总统计信息。"""
        total = WorkerSession.objects.count()
        # M1: use enum constant instead of hardcoded string.
        online_count = WorkerSession.objects.filter(status=WorkerSession.Status.ONLINE).count()
        offline_count = total - online_count
        return Response({
            'total': total,
            'online': online_count,
            'offline': offline_count,
        }, status=status.HTTP_200_OK)


class MessageFrameLogViewSet(viewsets.ReadOnlyModelViewSet):
    """消息帧日志视图集，只读查询用于调试和追踪。"""

    queryset = MessageFrameLog.objects.select_related('agent_session').all()
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['message_type', 'direction', 'agent_session']
    search_fields = ['trace_id']

    def get_serializer_class(self):
        from protocol.serializers import MessageFrameLogSerializer
        return MessageFrameLogSerializer
