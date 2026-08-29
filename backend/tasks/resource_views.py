"""
任务资源管理视图 — split from tasks/views.py in spec-29d (2026-07-19).

Contains resource-style ViewSets that manage secondary task resources:
- CustomTaskViewSet: user-defined task templates
- ScheduledTaskViewSet: cron/schedule-bound tasks
- MarketplaceViewSet: published task marketplace
- TaskFolderViewSet: folder tree for task organization

Original 1464-line tasks/views.py split into:
- views.py: TaskViewSet + execute/clone/bulk/parallel-config/version FBVs
- execution_views.py: TaskExecutionViewSet + bind-devices + bind-accounts
- resource_views.py (this file): CustomTask + ScheduledTask + Marketplace + Folder
"""
import logging

from gaf_core.audit_constants import (
    AuditAction,
    AuditResourceType,
)
from gaf_core.mixins import AuditMixin, audit_action, build_diff_details
from pipeline.serializers import PipelineSerializer
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import RoleBasedPermission
from tasks.models import (
    CustomTask,
    MarketplaceItem,
    MarketplaceReview,
    ScheduledTask,
    TaskFolder,
)
from tasks.serializers import (
    CustomTaskSerializer,
    MarketplaceItemSerializer,
    MarketplaceReviewSerializer,
    ScheduledTaskSerializer,
    TaskFolderSerializer,
)
from tasks.services import (
    TaskBindingError,
    clone_pipeline_for_user,
    get_user_pipeline,
)

logger = logging.getLogger(__name__)


class CustomTaskViewSet(AuditMixin, viewsets.ModelViewSet):
    """自定义任务管理视图集。"""

    queryset = CustomTask.objects.all()
    serializer_class = CustomTaskSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"
    filterset_fields = ["is_enabled", "created_by"]
    search_fields = ["name", "description"]
    audit_resource_type = AuditResourceType.CUSTOM_TASK

    def get_queryset(self):
        qs = CustomTask.objects.all()
        return qs

    def perform_create(self, serializer):
        """创建自定义任务时自动设置创建者。"""
        serializer.save(created_by=self.request.user)
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, serializer.instance)

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build before/after diff for audit log.

        ``params_config`` / ``json_schema`` may carry sensitive caller-
        supplied data; redact defensively.
        """
        snapshot_keys = ("name", "is_enabled")
        sensitive_extra = {"password", "encrypted_password", "token"}
        if action == AuditAction.CREATE:
            return build_diff_details(
                before=None,
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=sensitive_extra,
            )
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k, None) for k in snapshot_keys},
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=sensitive_extra,
            )
        if action == AuditAction.DELETE:
            return build_diff_details(
                before={k: getattr(instance, k, None) for k in snapshot_keys},
                after=None,
                sensitive_extra=sensitive_extra,
            )
        return {}

    @action(detail=True, methods=["post"], url_path="validate")
    def validate(self, request, pk=None):
        """验证自定义任务的定义是否合法（含 JSON Schema 校验）。"""

        custom_task = self.get_object()
        task_definition = custom_task.task_definition
        if not task_definition:
            return Response(
                {"valid": False, "detail": "任务定义不能为空"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        errors = []

        if not isinstance(task_definition, dict):
            return Response(
                {"valid": False, "detail": "任务定义必须是 JSON 对象"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        required_fields = ["name"]
        for field_name in required_fields:
            if field_name not in task_definition:
                errors.append(f"缺少必需字段: {field_name}")

        # spec-2026-07-27-execution-path-unification: 同时接受
        # pipeline schema ({nodes: [{node_type: ...}]}) 和 legacy chain
        # schema ({steps: [{action: ...}]}). 新数据应使用 nodes.
        nodes = task_definition.get("nodes")
        steps = task_definition.get("steps")
        if nodes is None and steps is None:
            errors.append("缺少必需字段: nodes 或 steps")
        else:
            node_list = nodes if nodes is not None else steps
            field_label = "nodes" if nodes is not None else "steps"
            if not isinstance(node_list, list):
                errors.append(f"{field_label} 必须是数组")
            elif len(node_list) == 0:
                errors.append(f"{field_label} 不能为空数组")
            else:
                for i, node in enumerate(node_list):
                    if not isinstance(node, dict):
                        errors.append(f"{field_label}[{i}] 必须是对象")
                        continue
                    # pipeline schema: node_type; legacy chain: action.
                    if "node_type" not in node and "action" not in node:
                        errors.append(
                            f"{field_label}[{i}] 缺少 node_type 字段"
                            f" (pipeline schema) 或 action 字段 (legacy chain)"
                        )

        if custom_task.json_schema:
            try:
                from jsonschema import ValidationError
                from jsonschema import validate as jsonschema_validate

                jsonschema_validate(instance=task_definition, schema=custom_task.json_schema)
            except ImportError:
                pass
            except ValidationError as exc:
                errors.append(f"JSON Schema 校验失败: {exc.message}")

        if errors:
            return Response(
                {"valid": False, "detail": "; ".join(errors), "errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"valid": True, "detail": "任务定义验证通过"}, status=status.HTTP_200_OK)


class ScheduledTaskViewSet(AuditMixin, viewsets.ModelViewSet):
    """定时任务管理视图集。"""

    queryset = ScheduledTask.objects.all()
    serializer_class = ScheduledTaskSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"
    filterset_fields = ["schedule_type", "is_enabled"]
    search_fields = ["task__name", "custom_task__name"]
    audit_resource_type = AuditResourceType.SCHEDULED_TASK

    def get_queryset(self):
        qs = ScheduledTask.objects.all()
        return qs

    def perform_create(self, serializer):
        """创建定时任务时自动设置创建者。"""
        serializer.save(created_by=self.request.user)
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, serializer.instance)

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build before/after diff for audit log.

        ``cron_expression`` is included so auditors can spot schedule
        tampering; sensitive cron payloads (rare) are still redacted by
        the default deny-list.
        """
        snapshot_keys = (
            "schedule_type",
            "cron_expression",
            "is_enabled",
            "scheduled_time",
        )
        sensitive_extra = {"password", "encrypted_password", "token"}
        if action == AuditAction.CREATE:
            return build_diff_details(
                before=None,
                after={k: str(getattr(instance, k, None)) for k in snapshot_keys},
                sensitive_extra=sensitive_extra,
            )
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: str(getattr(old_instance, k, None)) for k in snapshot_keys},
                after={k: str(getattr(instance, k, None)) for k in snapshot_keys},
                sensitive_extra=sensitive_extra,
            )
        if action == AuditAction.DELETE:
            return build_diff_details(
                before={k: str(getattr(instance, k, None)) for k in snapshot_keys},
                after=None,
                sensitive_extra=sensitive_extra,
            )
        return {}

    @action(detail=True, methods=["post"], url_path="toggle")
    @audit_action(AuditAction.UPDATE, AuditResourceType.SCHEDULED_TASK)
    def toggle(self, request, pk=None):
        """切换定时任务的启用/禁用状态。"""
        scheduled_task = self.get_object()
        scheduled_task.is_enabled = not scheduled_task.is_enabled
        scheduled_task.save(update_fields=["is_enabled", "updated_at"])
        return Response(
            {"is_enabled": scheduled_task.is_enabled},
            status=status.HTTP_200_OK,
        )


class MarketplaceViewSet(AuditMixin, viewsets.ModelViewSet):
    """任务市场 API

    AuditMixin wired with ``AuditResourceType.MARKETPLACE`` (Phase 2 fix:
    constant was added to ``gaf_core.audit_constants`` after subagent C
    flagged the Phase 1 gap).
    """

    audit_resource_type = AuditResourceType.MARKETPLACE
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "view"

    def get_permissions(self):
        """H5 fix: viewer can browse marketplace; operator+ to publish, admin to moderate."""
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.required_permission = "manage"
        else:
            self.required_permission = "view"
        return super().get_permissions()

    def get_queryset(self):
        """仅返回已发布的条目"""
        return MarketplaceItem.objects.filter(status="approved")

    def get_serializer_class(self):
        return MarketplaceItemSerializer

    @action(detail=True, methods=["post"], url_path="import-item")
    @audit_action(action=AuditAction.EXECUTE, resource_type=AuditResourceType.MARKETPLACE, resource_id_kw="pk")
    def import_item(self, request, pk=None):
        """一键导入市场任务"""
        item = self.get_object()
        pipeline = item.pipeline
        if not pipeline:
            return Response({"error": "该条目没有关联 Pipeline"}, status=400)

        # Cross-app Pipeline lookup + clone is delegated to the service
        # layer (TD-265) so this view no longer imports pipeline.models.
        # TaskBindingError carries the HTTP status + extra context (e.g.
        # existing pipeline_id on 409) so the response shape is preserved.
        try:
            new_pipeline = clone_pipeline_for_user(pipeline, request.user)
        except TaskBindingError as exc:
            return Response({"error": exc.message, **exc.extra}, status=exc.status_code)

        item.download_count = item.download_count + 1
        item.save(update_fields=["download_count"])
        return Response(PipelineSerializer(new_pipeline).data)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """评分与评论"""
        item = self.get_object()
        rating = request.data.get("rating", 5)
        comment = request.data.get("comment", "")

        if rating < 1 or rating > 5:
            return Response({"error": "评分范围 1-5"}, status=400)

        review, created = MarketplaceReview.objects.update_or_create(
            item=item,
            user=request.user,
            defaults={"rating": rating, "comment": comment},
        )

        reviews = item.reviews.all()
        item.rating_count = reviews.count()
        item.rating_avg = round(sum(r.rating for r in reviews) / item.rating_count, 1) if item.rating_count > 0 else 0
        item.save(update_fields=["rating_count", "rating_avg"])

        return Response(MarketplaceReviewSerializer(review).data)

    @action(detail=False, methods=["post"])
    def publish(self, request):
        """发布任务到市场"""
        pipeline_id = request.data.get("pipeline_id")
        if not pipeline_id:
            return Response({"error": "需要 pipeline_id"}, status=400)

        # Cross-app Pipeline lookup is delegated to the service layer
        # (TD-265) so this view no longer imports pipeline.models.
        try:
            pipeline = get_user_pipeline(pipeline_id, request.user)
        except TaskBindingError as exc:
            return Response({"error": exc.message}, status=exc.status_code)

        item = MarketplaceItem.objects.create(
            publisher=request.user,
            pipeline=pipeline,
            title=request.data.get("title", pipeline.name),
            description=request.data.get("description", pipeline.description or ""),
            game_profile_id=request.data.get("game_profile") or None,
            tags=request.data.get("tags", []),
            screenshot_urls=request.data.get("screenshot_urls", []),
            version=request.data.get("version", "1.0"),
            status=MarketplaceItem.Status.PENDING,
        )
        return Response(MarketplaceItemSerializer(item).data, status=201)

    @action(detail=False, methods=["get"], url_path="my-published")
    def my_published(self, request):
        """我的发布"""
        items = MarketplaceItem.objects.filter(publisher=request.user)
        return Response(MarketplaceItemSerializer(items, many=True).data)


# P-008: RecordingViewSet migrated to pipeline.views.RecordingViewSet.


class TaskFolderViewSet(AuditMixin, viewsets.ModelViewSet):
    """文件夹 CRUD API (T5-B06)"""

    serializer_class = TaskFolderSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"
    audit_resource_type = AuditResourceType.TASK_FOLDER

    def get_queryset(self):
        # swagger_fake_view is set by drf-spectacular during schema generation;
        # return .none() so request.user (AnonymousUser) doesn't blow up.
        if getattr(self, "swagger_fake_view", False):
            return TaskFolder.objects.none()
        return TaskFolder.objects.filter(owner=self.request.user).prefetch_related("children")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, serializer.instance)

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return TaskFolderSerializer
        return TaskFolderSerializer

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build before/after diff for task folder audit log."""
        snapshot_keys = ("name", "slug")
        sensitive_extra = {"password", "encrypted_password", "token"}
        if action == AuditAction.CREATE:
            return build_diff_details(
                before=None,
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=sensitive_extra,
            )
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k, None) for k in snapshot_keys},
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=sensitive_extra,
            )
        if action == AuditAction.DELETE:
            return build_diff_details(
                before={k: getattr(instance, k, None) for k in snapshot_keys},
                after=None,
                sensitive_extra=sensitive_extra,
            )
        return {}
