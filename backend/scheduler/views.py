"""
调度模块视图 — split in spec-29d (2026-07-19).

Phase 1 (2026-08-08): Business logic extracted to ``SchedulerService``
(``scheduler/services/scheduler_service.py``). Views are thin delegates
that handle HTTP concerns (request/response) only.

Original 1200-line file split into:
- views.py (this file): RecoveryLog/TimeWindow ViewSets + 调度配置 FBVs
  (warmup / auto-stop / execution-plan / today / executions)
- unattended_views.py: 无人值守总控 API (Phase 8) — helpers + 8 FBVs
"""
import logging

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from gaf_core.audit_constants import AuditAction, AuditResourceType
from gaf_core.mixins import AuditMixin, build_diff_details
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import RoleBasedPermission
from scheduler.models import (
    AutoStopCondition,
    RecoveryLog,
    TimeWindow,
    WarmupConfig,
)
from scheduler.serializers import (
    AutoStopConditionBulkSerializer,
    AutoStopConditionSerializer,
    RecoveryLogSerializer,
    TimeWindowSerializer,
    WarmupConfigSerializer,
)
from scheduler.services import SchedulerService

logger = logging.getLogger(__name__)


class RecoveryLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    恢复操作日志 ViewSet (P-020-A)

    只读: GET /api/scheduler/recovery-logs/ + /{id}/
    过滤: ?recovery_level=step&success=true
    排序: 默认 -created_at (最新在前)

    Note: pagination is disabled so the list endpoint returns a plain array.
    The two frontend callers (LogCenter specialty tab and Monitors page) expect
    RecoveryLogEntry[] and do not implement pagination controls.
    """

    serializer_class = RecoveryLogSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    pagination_class = None

    def get_queryset(self):
        qs = RecoveryLog.objects.all().order_by("-created_at")
        level = self.request.query_params.get("recovery_level")
        if level:
            qs = qs.filter(recovery_level=level)
        success = self.request.query_params.get("success")
        if success is not None:
            qs = qs.filter(success=success.lower() == "true")
        return qs


class TimeWindowViewSet(AuditMixin, viewsets.ModelViewSet):
    """
    时间窗口 ViewSet

    提供时间窗口的 CRUD 操作，支持 ?enabled=true 过滤。
    创建时校验时间窗口不重叠。
    """

    serializer_class = TimeWindowSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'manage'
    audit_resource_type = AuditResourceType.TIME_WINDOW

    def get_queryset(self):
        queryset = TimeWindow.objects.all()
        enabled_param = self.request.query_params.get("enabled")
        if enabled_param is not None:
            queryset = queryset.filter(is_enabled=enabled_param.lower() == "true")
        return queryset

    def perform_create(self, serializer):
        self._validate_no_overlap(serializer.validated_data)
        serializer.save()
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, serializer.instance)

    def perform_update(self, serializer):
        validated = serializer.validated_data
        if "start_time" in validated or "end_time" in validated or "days_of_week" in validated:
            existing = serializer.instance
            start = validated.get("start_time", existing.start_time)
            end = validated.get("end_time", existing.end_time)
            days = validated.get("days_of_week", existing.days_of_week)
            self._validate_no_overlap(
                {"start_time": start, "end_time": end, "days_of_week": days},
                exclude_id=existing.id,
            )
        # Snapshot before-state for audit diff (must run before serializer.save()).
        old_instance = None
        if self.audit_log_update:
            try:
                old_instance = self.get_object()
            except Exception:
                logger.warning("audit_log_update: get_object() failed", exc_info=True)
                old_instance = None
        serializer.save()
        if self.audit_log_update:
            self._log_audit(
                AuditAction.UPDATE,
                serializer.instance,
                old_instance=old_instance,
            )

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build before/after diff for audit log.

        ``start_time``/``end_time`` are ``datetime.time`` objects which are
        NOT JSON-serializable by the default stdlib ``json`` encoder used
        by ``AuditLog.details`` (JSONField uses DjangoJSONEncoder at the
        DB layer, but ``log_audit``'s try/except short-circuits before
        that). Convert to ISO-format strings so the details dict is
        always stdlib-json-serializable. No known sensitive fields on
        TimeWindow.
        """
        snapshot_keys = ("start_time", "end_time", "is_enabled")

        def _snapshot(obj):
            data = {}
            for k in snapshot_keys:
                val = getattr(obj, k, None)
                # datetime.time objects need explicit isoformat() to be
                # JSON-serializable via the stdlib encoder used by log_audit.
                if hasattr(val, "isoformat"):
                    val = val.isoformat()
                data[k] = val
            return data

        if action == AuditAction.CREATE:
            return build_diff_details(
                before=None,
                after=_snapshot(instance),
            )
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before=_snapshot(old_instance),
                after=_snapshot(instance),
            )
        if action == AuditAction.DELETE:
            return build_diff_details(
                before=_snapshot(instance),
                after=None,
            )
        return {}

    def _validate_no_overlap(self, data: dict, exclude_id: int = None):
        """
        校验时间窗口不重叠。

        Delegates to ``SchedulerService.validate_time_window`` (Phase 1).

        Args:
            data: 包含 start_time, end_time, days_of_week 的字典
            exclude_id: 更新时排除自身的 ID
        """
        SchedulerService.validate_time_window(data, exclude_id=exclude_id)


@extend_schema(
    tags=['scheduler'],
    summary='Warmup config singleton upsert',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def warmup_config_view(request):
    """
    设备预热配置 Upsert API。

    GET: 获取当前预热配置（返回第一个或空）
    POST: 创建或更新预热配置（Upsert 模式）
    """
    # @api_view allowed: singleton upsert (one WarmupConfig row per deployment), not standard CRUD
    if request.method == "GET":
        config = WarmupConfig.objects.first()
        if config:
            serializer = WarmupConfigSerializer(config)
            return Response(serializer.data)
        return Response(
            {
                "steps": [],
                "global_timeout_seconds": 600,
                "failure_strategy": "skip_device",
            }
        )

    elif request.method == "POST":
        serializer = WarmupConfigSerializer(data=request.data)
        if serializer.is_valid():
            config = serializer.save()
            return Response(
                WarmupConfigSerializer(config).data,
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['scheduler'],
    summary='Auto-stop conditions bulk upsert',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def auto_stop_conditions_view(request):
    """
    自动停止条件 Upsert API。

    GET: 获取当前所有停止条件配置
    POST: 批量创建/更新停止条件（Upsert 模式）
    """
    # @api_view allowed: bulk upsert via AutoStopConditionBulkSerializer, not standard CRUD
    if request.method == "GET":
        conditions = AutoStopCondition.objects.all()
        serializer = AutoStopConditionSerializer(conditions, many=True)
        return Response({"conditions": serializer.data})

    elif request.method == "POST":
        serializer = AutoStopConditionBulkSerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            return Response(
                {"conditions": AutoStopConditionSerializer(result, many=True).data},
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['scheduler'],
    summary='Execution plan preview for next N days',
    responses={200: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter(
            name='days',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Lookahead window in days',
        ),
    ],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def execution_plan_view(request):
    """
    执行计划预览 API。

    GET /api/scheduler/execution-plan/?days=7
    返回未来 N 天的执行计划。

    Delegates to ``SchedulerService.get_execution_plan`` (Phase 1).
    """
    try:
        days = int(request.query_params.get("days", 7))
        result = SchedulerService.get_execution_plan(days)
        return Response(result)
    except ValueError as e:
        # invalid query param (e.g. days=abc) → 400 instead of 500
        logger.warning("execution_plan_view invalid params: %s", e)
        return Response(
            {"error": f"无效的查询参数: {str(e)}", "events": []},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        logger.exception("execution_plan_view failed")
        return Response(
            {"error": f"生成执行计划失败: {str(e)}", "events": []},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    tags=['scheduler'],
    summary='Today schedule from execution plan',
    responses={200: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def today_schedule_view(request):
    """
    今日日程 API。

    GET /api/v2/scheduler/today/
    返回今日的无人值守执行日程（基于 Device + GameProfile.default_task_chain）。

    Delegates to ``SchedulerService.get_today_schedule`` (Phase 1).
    """
    try:
        result = SchedulerService.get_today_schedule()
        return Response(result)
    except Exception as e:
        logger.exception("today_schedule_view failed")
        return Response(
            {
                "date": timezone.now().date().isoformat(),
                "total": 0,
                "completed": 0,
                "failed": 0,
                "items": [],
                "error": str(e),
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@extend_schema(
    tags=['scheduler'],
    summary='List scheduled task execution history',
    responses={200: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter(
            name='page',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Page number (1-indexed)',
        ),
        OpenApiParameter(
            name='page_size',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Items per page (max 100)',
        ),
    ],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def executions_view(request):
    """List scheduled task execution history (paginated).

    GET /api/v2/scheduler/executions/?page=1&page_size=20
    Returns paginated ScheduledExecutionRecord list. Maps TaskExecution rows
    to the ScheduledExecutionRecord shape expected by the frontend, joining
    ScheduledTask via task.schedules to populate scheduled_task_id when
    available.

    Delegates to ``SchedulerService.list_executions`` (Phase 1).

    Response: {
        "count": int,
        "page": int,
        "page_size": int,
        "results": [
            {
                "id": str, "task_name": str, "scheduled_task_id": str,
                "status": "success"|"failed"|"timeout"|"running",
                "started_at": str, "finished_at": str|null,
                "duration_seconds": float|null, "error_message": str|null
            }
        ]
    }
    """
    try:
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        result = SchedulerService.list_executions(page, page_size)
        return Response(result)
    except Exception as e:
        logger.exception("executions_view failed")
        return Response(
            {"count": 0, "page": 1, "page_size": 20, "results": [], "error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
