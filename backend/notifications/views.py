"""通知与 Webhook 配置 REST API。"""

import ipaddress
import socket
from urllib.parse import urlparse

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiTypes, extend_schema
from gaf_core.audit_constants import AuditAction, AuditResourceType
from gaf_core.mixins import AuditMixin, audit_action, build_diff_details
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import RoleBasedPermission
from config.app_info import WEBHOOK_TIMEOUT
from notifications.models import AlertRule, Notification, NotificationPreference, WebhookConfig

# SSRF protection: block private/loopback/internal network targets.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network('127.0.0.0/8'),      # loopback
    ipaddress.ip_network('10.0.0.0/8'),        # Class A private
    ipaddress.ip_network('172.16.0.0/12'),     # Class B private
    ipaddress.ip_network('192.168.0.0/16'),    # Class C private
    ipaddress.ip_network('169.254.0.0/16'),    # link-local
    ipaddress.ip_network('::1/128'),           # IPv6 loopback
    ipaddress.ip_network('fc00::/7'),          # IPv6 ULA
]


def _is_safe_webhook_url(url: str) -> bool:
    """Validate that a webhook URL does not target internal/private networks.

    Prevents SSRF by blocking loopback, private, and link-local addresses.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    # Resolve hostname to IP and check against blocked networks.
    try:
        resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
    except (socket.gaierror, OSError):
        return False
    for _, _, _, _, sockaddr in resolved:
        ip = ipaddress.ip_address(sockaddr[0])
        if any(ip in net for net in _BLOCKED_NETWORKS):
            return False
    return True


class NotificationViewSet(AuditMixin, viewsets.ModelViewSet):
    """通知视图集，仅返回当前用户的通知，支持标记已读、批量已读。"""

    # Restrict pk to digits so the empty-prefix detail route does not
    # shadow sibling routes like /notifications/webhooks/ (TD-021 fix).
    lookup_value_regex = r'\d+'

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['category', 'is_read']
    search_fields = ['title', 'body']
    audit_resource_type = AuditResourceType.NOTIFICATION

    def get_serializer_class(self):
        from notifications.serializers import NotificationSerializer
        return NotificationSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user)

    def get_permissions(self):
        if self.action == 'destroy':
            self.required_permission = 'manage'
        else:
            self.required_permission = 'view'
        return super().get_permissions()

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build before/after diff for audit log.

        ``body`` may contain user-supplied content; we keep it in the
        diff since it is already visible to the user who owns the
        notification. No password/token fields on Notification.
        """
        snapshot_keys = ("title", "category", "is_read")
        if action == AuditAction.CREATE:
            return build_diff_details(
                before=None,
                after={k: getattr(instance, k, None) for k in snapshot_keys},
            )
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k, None) for k in snapshot_keys},
                after={k: getattr(instance, k, None) for k in snapshot_keys},
            )
        if action == AuditAction.DELETE:
            return build_diff_details(
                before={k: getattr(instance, k, None) for k in snapshot_keys},
                after=None,
            )
        return {}

    @action(detail=True, methods=['post'], url_path='read')
    @audit_action(AuditAction.UPDATE, AuditResourceType.NOTIFICATION)
    def mark_read(self, request, pk=None):
        """标记单条通知为已读。"""
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response({'status': 'ok'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='read-all')
    @audit_action(AuditAction.UPDATE, AuditResourceType.NOTIFICATION, resource_id_kw="")
    def mark_all_read(self, request):
        """标记当前用户所有通知为已读。"""
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'status': 'ok', 'updated': updated}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        """获取当前用户未读通知数量。"""
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread_count': count}, status=status.HTTP_200_OK)


class WebhookConfigViewSet(AuditMixin, viewsets.ModelViewSet):
    """Webhook 配置视图集，支持用户管理自己的 Webhook 渠道。"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'manage'
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['channel', 'is_active']
    audit_resource_type = AuditResourceType.WEBHOOK_CONFIG
    # Webhook URL may carry secret tokens in query string or path;
    # redact the entire url + any explicit secret/token field.
    _AUDIT_SENSITIVE_EXTRA = {"url", "secret", "token", "headers"}

    def get_serializer_class(self):
        from notifications.serializers import WebhookConfigSerializer
        return WebhookConfigSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return WebhookConfig.objects.none()
        return WebhookConfig.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, serializer.instance)

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build before/after diff for audit log.

        ``url`` may contain secret tokens (e.g. Slack/DingTalk webhook
        URLs with auth tokens in the path); treat it as sensitive and
        rely on ``filter_sensitive_fields`` to redact via the
        ``_AUDIT_SENSITIVE_EXTRA`` deny-list.
        """
        snapshot_keys = ("channel", "is_active", "url")
        sensitive = self._AUDIT_SENSITIVE_EXTRA
        if action == AuditAction.CREATE:
            return build_diff_details(
                before=None,
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=sensitive,
            )
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k, None) for k in snapshot_keys},
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=sensitive,
            )
        if action == AuditAction.DELETE:
            return build_diff_details(
                before={k: getattr(instance, k, None) for k in snapshot_keys},
                after=None,
                sensitive_extra=sensitive,
            )
        return {}

    @action(detail=True, methods=['post'], url_path='test')
    @audit_action(AuditAction.EXECUTE, AuditResourceType.WEBHOOK_CONFIG)
    def test_webhook(self, request, pk=None):
        """发送测试消息到指定 Webhook。"""
        from django.utils import timezone

        webhook = self.get_object()
        import requests as req

        # SSRF protection: reject URLs targeting internal networks.
        if not _is_safe_webhook_url(webhook.url):
            return Response(
                {'status': 'error', 'message': 'Webhook URL targets a private/internal network (SSRF blocked)'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            test_payload = {
                'title': 'GAF Webhook 测试',
                'body': '如果您收到此消息，说明 Webhook 配置正确。',
                'timestamp': str(timezone.now()),
            }
            resp = req.post(webhook.url, json=test_payload, timeout=WEBHOOK_TIMEOUT)
            if resp.status_code < 400:
                return Response({'status': 'ok', 'http_status': resp.status_code}, status=status.HTTP_200_OK)
            return Response(
                {'status': 'failed', 'http_status': resp.status_code, 'body': resp.text[:500]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except req.RequestException as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AlertRuleViewSet(AuditMixin, viewsets.ModelViewSet):
    """告警规则视图集（R37-P3 Stage 7: 从 tasks 迁入）。

    用户只能管理自己的告警规则；读操作允许 viewer，写操作需 operator+。
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    audit_resource_type = AuditResourceType.ALERT_RULE

    def get_serializer_class(self):
        from notifications.serializers import AlertRuleSerializer
        return AlertRuleSerializer

    def get_permissions(self):
        """H5 fix preserved from tasks app: viewer can read; writes need execute."""
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            self.required_permission = 'execute'
        else:
            self.required_permission = 'view'
        return super().get_permissions()

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return AlertRule.objects.none()
        return AlertRule.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, serializer.instance)

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build before/after diff for audit log.

        AlertRule ``config`` JSON may embed endpoint URLs / tokens for
        downstream channels; treat it as sensitive via the default
        deny-list plus ``config`` extra.
        """
        snapshot_keys = ("name", "rule_type", "enabled", "threshold")
        sensitive = {"config", "endpoint", "secret", "token"}
        if action == AuditAction.CREATE:
            return build_diff_details(
                before=None,
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=sensitive,
            )
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k, None) for k in snapshot_keys},
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=sensitive,
            )
        if action == AuditAction.DELETE:
            return build_diff_details(
                before={k: getattr(instance, k, None) for k in snapshot_keys},
                after=None,
                sensitive_extra=sensitive,
            )
        return {}


@extend_schema(
    tags=['notifications'],
    summary='Notification preferences singleton upsert (per user)',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def preferences_view(request):
    """Get or upsert the current user's notification preferences.

    GET /api/v2/notifications/preferences/
        Returns current preferences (or defaults if not yet set).

    POST /api/v2/notifications/preferences/
        Body: NotificationPreference fields (desktop_notification, sound_alert,
              system_notification, alert_notification, community_notification,
              quiet_hours_start, quiet_hours_end, retention_days)
        Upserts the preferences for the current user (OneToOne per user).
    """
    # @api_view allowed: singleton upsert per user (OneToOne), not collection CRUD
    from notifications.serializers import NotificationPreferenceSerializer

    defaults = {
        'desktop_notification': True,
        'sound_alert': True,
        'system_notification': True,
        'alert_notification': True,
        'community_notification': False,
        'quiet_hours_start': None,
        'quiet_hours_end': None,
        'retention_days': 30,
    }

    if request.method == 'GET':
        pref = NotificationPreference.objects.filter(user=request.user).first()
        if pref:
            return Response(NotificationPreferenceSerializer(pref).data)
        return Response(defaults)

    # POST: upsert
    serializer = NotificationPreferenceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    obj, _created = NotificationPreference.objects.update_or_create(
        user=request.user,
        defaults=serializer.validated_data,
    )
    return Response(
        NotificationPreferenceSerializer(obj).data,
        status=status.HTTP_201_CREATED if _created else status.HTTP_200_OK,
    )
