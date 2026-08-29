import logging
import secrets
from collections.abc import Sequence
from typing import Any, cast

from django.db.models import Prefetch
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from gaf_core.audit_constants import (
    AuditAction,
    AuditResourceType,
)
from gaf_core.mixins import AuditMixin, audit_action, build_diff_details
from gaf_core.utils.tokens import hash_token, make_token_preview
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import BaseFilterBackend, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from accounts.permissions import RoleBasedPermission
from agents.models import Agent, Device, DeviceGroup
from agents.serializers import (
    AgentSerializer,
    AgentTokenSerializer,
    DeviceGroupSerializer,
    DeviceSerializer,
)
from agents.services import DeviceService

logger = logging.getLogger(__name__)





class AgentViewSet(AuditMixin, viewsets.ModelViewSet):
    """Agent 管理视图集，operator 及以上权限可操作。"""

    queryset = Agent.objects.all()
    serializer_class = AgentSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"
    filterset_fields = ["status", "is_local", "hostname"]
    search_fields = ["agent_id", "hostname", "ip_address"]
    audit_resource_type = AuditResourceType.AGENT

    # Defensive redaction set: agent_token_hash is already a SHA-256 digest
    # (TD-141 removed the plaintext field), but we still redact to keep the
    # audit payload free of any token-derived material. agent_token_preview
    # is a 4+4 char preview used in list UIs; redacted as well so the audit
    # log never carries partial token data.
    _AUDIT_SENSITIVE_EXTRA = {"agent_token_hash", "agent_token_preview", "agent_token"}

    def _build_audit_details(self, action, instance, *, old_instance=None) -> dict:
        """Build audit details for Agent writes; token fields always redacted."""
        snapshot_keys = (
            "agent_id", "hostname", "ip_address", "os_info", "status",
            "is_local", "agent_token_hash", "agent_token_preview",
        )
        if action == AuditAction.CREATE:
            return build_diff_details(
                before=None,
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=self._AUDIT_SENSITIVE_EXTRA,
            )
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k, None) for k in snapshot_keys},
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=self._AUDIT_SENSITIVE_EXTRA,
            )
        if action == AuditAction.DELETE:
            return build_diff_details(
                before={k: getattr(instance, k, None) for k in snapshot_keys},
                after=None,
                sensitive_extra=self._AUDIT_SENSITIVE_EXTRA,
            )
        return {}

    @action(detail=True, methods=["post"], url_path="generate-token")
    @audit_action(
        action=AuditAction.UPDATE,
        resource_type=AuditResourceType.AGENT,
        resource_id_kw="pk",
    )
    def generate_token(self, request: Request, pk: int | None = None) -> Response:
        """为指定 Agent 生成新的鉴权令牌。"""
        agent = self.get_object()
        token = secrets.token_urlsafe(32)
        # C4 fix: store SHA-256 hash + preview, never persist plaintext.
        # TD-141 (2026-07-18): agent_token plaintext field removed entirely.
        agent.agent_token_hash = hash_token(token)
        agent.agent_token_preview = make_token_preview(token)
        agent.save(update_fields=["agent_token_hash", "agent_token_preview", "updated_at"])
        serializer = AgentTokenSerializer({"agent_id": agent.agent_id, "agent_token": token})
        return Response(serializer.data, status=status.HTTP_200_OK)


class DeviceViewSet(AuditMixin, viewsets.ModelViewSet):
    """Device 管理视图集，支持设备 CRUD 与发现。"""

    queryset = Device.objects.select_related("agent", "locked_by", "game_profile").all()
    serializer_class = DeviceSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"
    filter_backends: Sequence[type[BaseFilterBackend]] = [
        cast(type[BaseFilterBackend], DjangoFilterBackend),
        SearchFilter,
    ]
    filterset_fields = ["device_type", "status", "agent"]
    search_fields = ["name"]
    _cached_adb_path: str | None = None
    audit_resource_type = AuditResourceType.DEVICE

    # Defensive redaction set for Device: extra_info may carry window_title
    # or other operator-supplied strings; fcm_token/agent_token/secret are
    # listed defensively (no current Device field uses these names, but
    # future-proofs against schema drift).
    _AUDIT_SENSITIVE_EXTRA = {"agent_token", "secret", "fcm_token", "api_key", "token"}

    def _build_audit_details(self, action, instance, *, old_instance=None) -> dict:
        """Build audit details for Device writes; sensitive fields redacted."""
        snapshot_keys = (
            "name", "device_type", "status", "agent_id", "adb_serial",
            "window_handle", "emulator_brand", "control_mode",
            "screenshot_method", "input_method",
            "game_profile_id", "game_account_id",
            "resolution_width", "resolution_height",
        )
        if action == AuditAction.CREATE:
            return build_diff_details(
                before=None,
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=self._AUDIT_SENSITIVE_EXTRA,
            )
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k, None) for k in snapshot_keys},
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=self._AUDIT_SENSITIVE_EXTRA,
            )
        if action == AuditAction.DELETE:
            return build_diff_details(
                before={k: getattr(instance, k, None) for k in snapshot_keys},
                after=None,
                sensitive_extra=self._AUDIT_SENSITIVE_EXTRA,
            )
        return {}

    @action(detail=False, methods=["post"], url_path="health-check")
    def health_check(self, request: Request) -> Response:
        """Health check all devices: probe real online/offline status.

        POST /api/devices/health-check/
        Delegates to ``DeviceService.check_all_devices_health`` (Phase 1).
        """
        service = DeviceService()
        results = service.check_all_devices_health()
        hb_info: dict[str, Any]
        try:
            from agents.agent_runtime import is_heartbeat_alive, is_heartbeat_started

            hb_info = {
                "thread_alive": is_heartbeat_alive(),
                "thread_exists": is_heartbeat_started(),
            }
        except Exception:
            logger.warning("heartbeat_info: agent_runtime import failed", exc_info=True)
            hb_info = {"thread_alive": False, "thread_exists": False, "error": "import failed"}
        return Response(
            {
                "checked_at": timezone.now().isoformat(),
                "total": len(results),
                "online": sum(1 for r in results if r["new_status"] == Device.Status.ONLINE),
                "offline": sum(1 for r in results if r["new_status"] == Device.Status.OFFLINE),
                "heartbeat_thread": hb_info,
                "results": results,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="refresh-status")
    def refresh_status(self, request: Request, pk: int | None = None) -> Response:
        """Refresh single device status by running health check.

        POST /api/devices/{id}/refresh-status/
        Delegates to ``DeviceService.check_single_device_health`` (Phase 1).
        Returns updated device data with real-time status.
        """
        try:
            device = Device.objects.select_related("agent").get(pk=pk)  # type: ignore[misc]
        except Device.DoesNotExist:
            return Response(
                {"success": False, "error": "设备不存在"},
                status=status.HTTP_404_NOT_FOUND,
            )
        service = DeviceService()
        result = service.check_single_device_health(device)
        return Response(result, status=status.HTTP_200_OK)

    # ---- v3 §2.7.2 window-centric binding APIs ------------------------

    @action(detail=True, methods=['patch'], url_path='bind-game-account')
    @audit_action(
        action=AuditAction.UPDATE,
        resource_type=AuditResourceType.DEVICE,
        resource_id_kw='pk',
    )
    def bind_game_account(self, request: Request, pk: int | None = None) -> Response:
        """Bind a Device to a GameAccount (spec v3 §2.7.2).

        Sets ``Device.game_account`` so dispatch flows can read
        ``device.game_account.resource_pack`` and
        ``device.game_account.username`` without an extra lookup.

        Body: ``{"game_account_id": 123}``

        Passing ``game_account_id: null`` clears the binding.
        """
        from accounts.models import GameAccount

        device = self.get_object()
        account_id = request.data.get('game_account_id')

        if account_id is None:
            device.game_account = None
            device.save(update_fields=['game_account'])
            return Response({
                'status': 'ok',
                'device_id': device.pk,
                'game_account_id': None,
                'message': f'Device [{device.name}] cleared game_account binding',
            })

        try:
            account = GameAccount.objects.get(pk=account_id)
        except GameAccount.DoesNotExist:
            return Response(
                {'error': f'GameAccount {account_id} not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        device.game_account = account
        device.save(update_fields=['game_account'])

        return Response({
            'status': 'ok',
            'device_id': device.pk,
            'device_name': device.name,
            'game_account_id': account.pk,
            'game_account_username': account.username,
            'message': f'Device [{device.name}] bound to GameAccount [{account.username}]',
        })

    @action(detail=True, methods=['patch'], url_path='bind-game-profile')
    @audit_action(
        action=AuditAction.UPDATE,
        resource_type=AuditResourceType.DEVICE,
        resource_id_kw='pk',
    )
    def bind_game_profile(self, request: Request, pk: int | None = None) -> Response:
        """Bind a Device to a GameProfile (spec v3 §2.7.2 + §2.8).

        Sets ``Device.game_profile`` so the device inherits the profile's
        default_routine / default_screenshot_method / default_input_method /
        default_control_mode (the 'auto' resolution is implemented in
        stage 5 ``resolve_device_methods``; this endpoint only persists
        the FK).

        Body: ``{"game_profile_id": 123}``

        Passing ``game_profile_id: null`` clears the binding.
        """
        from gamestate.models import GameProfile

        device = self.get_object()
        profile_id = request.data.get('game_profile_id')

        if profile_id is None:
            device.game_profile = None
            device.save(update_fields=['game_profile'])
            return Response({
                'status': 'ok',
                'device_id': device.pk,
                'game_profile_id': None,
                'message': f'Device [{device.name}] cleared game_profile binding',
            })

        try:
            profile = GameProfile.objects.get(pk=profile_id)
        except GameProfile.DoesNotExist:
            return Response(
                {'error': f'GameProfile {profile_id} not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # N197: allowed_device_types 校验 — 设备类型必须在游戏档案允许的列表内
        if profile.allowed_device_types and device.device_type not in profile.allowed_device_types:
            return Response(
                {
                    'error': (
                        f'设备类型 "{device.device_type}" 不被游戏档案 '
                        f'"{profile.game_name}" 允许。'
                        f'允许的类型: {profile.allowed_device_types}'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        device.game_profile = profile
        device.save(update_fields=['game_profile'])

        return Response({
            'status': 'ok',
            'device_id': device.pk,
            'device_name': device.name,
            'game_profile_id': profile.pk,
            'game_name': profile.game_name,
            'default_routine_id': profile.default_routine_id,
            'message': f'Device [{device.name}] bound to GameProfile [{profile.game_name}]',
        })

    @classmethod
    def _get_adb_path(cls) -> str:
        """Backward-compatible delegate — ADB path discovery moved to
        ``DeviceService.get_adb_path`` (Phase 1)."""
        return DeviceService().get_adb_path()


class DeviceGroupViewSet(AuditMixin, viewsets.ModelViewSet):
    """DeviceGroup 管理视图集，支持分组的 CRUD（树形结构）。"""

    serializer_class = DeviceGroupSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"
    filter_backends: Sequence[type[BaseFilterBackend]] = [
        cast(type[BaseFilterBackend], DjangoFilterBackend),
        SearchFilter,
    ]
    search_fields = ["name"]
    audit_resource_type = AuditResourceType.DEVICE_GROUP

    def get_queryset(self):
        """仅返回当前用户的顶级分组（parent 为空）。"""
        if getattr(self, 'swagger_fake_view', False):
            return DeviceGroup.objects.none()
        return DeviceGroup.objects.filter(
            user=self.request.user,
            parent__isnull=True,
        ).prefetch_related(Prefetch("devices", queryset=Device.objects.select_related("agent", "locked_by", "game_profile")), "children")

    def perform_create(self, serializer):
        """创建分组时自动关联当前用户，并触发 AuditMixin 审计日志。"""
        # AuditMixin.perform_create calls super().perform_create which invokes
        # serializer.save() with no args; we need to inject the user here.
        # Mirrors the GameAccountGroupViewSet pattern (accounts/views.py).
        instance = serializer.save(user=self.request.user)
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, instance)

    def _build_audit_details(self, action, instance, *, old_instance=None) -> dict:
        """Build audit details for DeviceGroup writes."""
        snapshot_keys = ("name", "user_id", "parent_id")
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
