import logging
from typing import cast

from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from gaf_core.audit_constants import (
    AuditAction,
    AuditResourceType,
    filter_sensitive_fields,
    get_client_ip,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import RoleBasedPermission
from protocol.broadcast import broadcast_to_dashboard
from protocol.constants import FrontendEventType
from workers.models import Device

logger = logging.getLogger(__name__)


# Import service-layer helpers (moved to agents/services/device_service.py in Phase 1).


class DeviceLockView(APIView):
    """设备锁定视图 (BE-3.04)
    POST /api/devices/{id}/lock/
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
        description="Lock a device for exclusive use by the current user.",
    )
    def post(self, request: Request, id: int):
        """锁定设备"""
        from django.db import transaction
        from django.utils.timezone import now

        from accounts.models import User

        try:
            with transaction.atomic():
                device = Device.objects.select_for_update().select_related("locked_by").get(pk=id)

                force = request.query_params.get("force") == "true"
                current_user = cast(User, request.user)
                is_admin = current_user.role == User.Role.ADMIN

                if device.locked_by and device.locked_by != request.user:
                    if is_admin and force:
                        pass
                    else:
                        return Response(
                            {
                                "error": f"设备已被 {device.locked_by.username} 锁定",
                                "locked_by": device.locked_by.username,
                            },
                            status=status.HTTP_403_FORBIDDEN,
                        )

                device.locked_by = current_user  # type: ignore[assignment]
                device.locked_at = now()
                device.save(update_fields=["locked_by", "locked_at", "updated_at"])
        except Device.DoesNotExist:
            return Response({"error": "设备不存在"}, status=status.HTTP_404_NOT_FOUND)

        self._broadcast_lock_change(device, "locked")

        # Audit log: device lock is a sensitive state change (exclusive
        # access granted to a user). Include who locked and previous
        # holder (if force-taken) for forensic traceability.
        try:
            from accounts.audit import log_audit

            log_audit(
                user=getattr(request, "user", None),
                action=AuditAction.UPDATE,
                resource_type=AuditResourceType.DEVICE,
                resource_id=str(device.pk),
                details=filter_sensitive_fields({
                    "lock_action": "locked",
                    "locked_by": getattr(request.user, "username", ""),
                    "force": request.query_params.get("force") == "true",
                    "device_name": device.name,
                }),
                ip_address=get_client_ip(request),
            )
        except Exception as audit_exc:
            logger.warning("Audit log failed for device lock: %s", audit_exc)

        return Response(
            {
                "status": "locked",
                "locked_by": getattr(request.user, "username", ""),
                "locked_at": device.locked_at.isoformat(),
            }
        )

    def _broadcast_lock_change(self, device, status):
        """通过 Channels 广播锁状态变化"""
        try:
            broadcast_to_dashboard(
                FrontendEventType.DEVICE_UPDATED,
                {
                    "device_id": device.id,
                    "changed_fields": ["locked_by", "status"],
                    "lock_status": status,
                    "locked_by": device.locked_by.username if device.locked_by else None,
                    "timestamp": timezone.now().isoformat(),
                },
            )
        except Exception as e:
            logger.warning("Failed to broadcast lock change for device %d: %s", device.id, e)


class DeviceUnlockView(APIView):
    """设备解锁视图 (BE-3.04)
    POST /api/devices/{id}/unlock/
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
        description="Release the lock on a device (only the lock owner may unlock).",
    )
    def post(self, request: Request, id: int):
        """解锁设备"""
        from django.db import transaction

        from accounts.models import User

        try:
            with transaction.atomic():
                device = Device.objects.select_for_update().select_related("locked_by").get(pk=id)

                is_admin = request.user.role == User.Role.ADMIN  # type: ignore[union-attr]

                if not device.locked_by:
                    return Response({"status": "unlocked", "message": "设备未被锁定"})

                if device.locked_by != request.user and not is_admin:
                    return Response(
                        {
                            "error": "无权解锁此设备",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                device.locked_by = None
                device.locked_at = None
                device.save(update_fields=["locked_by", "locked_at", "updated_at"])
        except Device.DoesNotExist:
            return Response({"error": "设备不存在"}, status=status.HTTP_404_NOT_FOUND)

        try:
            broadcast_to_dashboard(
                FrontendEventType.DEVICE_UPDATED,
                {
                    "device_id": device.id,
                    "changed_fields": ["locked_by", "status"],
                    "lock_status": "unlocked",
                    "locked_by": None,
                    "timestamp": timezone.now().isoformat(),
                },
            )
        except Exception as e:
            logger.warning("Failed to broadcast unlock for device %d: %s", id, e)

        # Audit log: device unlock releases exclusive access. Include who
        # initiated the unlock so auditors can correlate lock/unlock pairs.
        try:
            from accounts.audit import log_audit

            log_audit(
                user=getattr(request, "user", None),
                action=AuditAction.UPDATE,
                resource_type=AuditResourceType.DEVICE,
                resource_id=str(device.pk),
                details=filter_sensitive_fields({
                    "lock_action": "unlocked",
                    "unlocked_by": getattr(request.user, "username", ""),
                    "device_name": device.name,
                }),
                ip_address=get_client_ip(request),
            )
        except Exception as audit_exc:
            logger.warning("Audit log failed for device unlock: %s", audit_exc)

        return Response({"status": "unlocked"})


class DeviceStatsView(APIView):
    """设备性能统计视图 (BE-3.06)
    GET /api/devices/{id}/stats/
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Return performance stats (FPS / latency / memory) for a device.",
    )
    def get(self, request: Request, id: int):
        """获取设备性能统计"""
        try:
            device = Device.objects.get(pk=id)
        except Device.DoesNotExist:
            return Response({"error": "设备不存在"}, status=status.HTTP_404_NOT_FOUND)

        stats = device.device_stats or {}
        return Response(
            {
                "fps_avg": stats.get("fps_avg", None),
                "fps_min": stats.get("fps_min", None),
                "fps_max": stats.get("fps_max", None),
                "screenshot_latency_avg_ms": stats.get("screenshot_latency_avg_ms", None),
                "input_latency_avg_ms": stats.get("input_latency_avg_ms", None),
                "uptime_seconds": stats.get("uptime_seconds", None),
                "total_screenshots": stats.get("total_screenshots", 0),
                "screenshot_method": device.screenshot_method or "",
                "input_method": device.input_method or "",
                "resolution": {
                    "width": device.resolution_width,
                    "height": device.resolution_height,
                },
                "dpi": stats.get("dpi", None),
            }
        )
