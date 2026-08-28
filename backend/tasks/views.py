"""
任务管理主视图 — split in spec-29d (2026-07-19).

Original 1464-line tasks/views.py split into:
- views.py (this file): TaskViewSet + execute/clone/bulk/parallel-config/version FBVs
- execution_views.py: TaskExecutionViewSet + bind-devices + bind-accounts
- resource_views.py: CustomTask + ScheduledTask + Marketplace + Folder
"""
import copy
import logging
from pathlib import Path

from django.db import models, transaction
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from gaf_core.audit_constants import (
    AuditAction,
    AuditResourceType,
    filter_sensitive_fields,
    get_client_ip,
)
from gaf_core.mixins import AuditMixin, audit_action, build_diff_details
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import RoleBasedPermission
from tasks.models import (
    Task,
    TaskDevice,
    TaskExecution,
    TaskVersion,
)
from tasks.serializers import (
    BulkActionSerializer,
    ParallelConfigSerializer,
    TaskExecuteSerializer,
    TaskExecutionSerializer,
    TaskSerializer,
    TaskVersionCreateSerializer,
    TaskVersionSerializer,
)
from tasks.services import TaskBindingError, TaskService

logger = logging.getLogger(__name__)


class TaskViewSet(AuditMixin, viewsets.ModelViewSet):
    """任务管理视图集，viewer 只读 / operator 可执行。"""

    queryset = Task.objects.select_related(
        "game_profile",
        "rotation_rule",
        "folder",
        "resource_pack",  # N197-8: for resource pack filter + column
    ).prefetch_related("game_accounts", "device_mappings__device")
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "view"
    filterset_fields = ["execution_mode", "is_enabled", "game_profile", "resource_pack"]
    search_fields = ["name", "description"]
    audit_resource_type = AuditResourceType.TASK

    def get_queryset(self):
        qs = Task.objects.select_related(
            "game_profile",
            "rotation_rule",
            "folder",
            "resource_pack",  # N197-8: for resource pack filter + column
        ).prefetch_related("game_accounts", "device_mappings__device")
        return qs

    def get_permissions(self):
        """根据动作动态调整权限要求。"""
        if self.action in ("create", "update", "partial_update", "destroy", "execute", "cancel"):
            self.required_permission = "execute"
        else:
            self.required_permission = "view"
        return super().get_permissions()

    def _get_resource_pack(self, instance):
        """Find the resource pack for a Task instance.

        Priority:
        1. instance.resource_pack (FK, set by serializer via resource_pack_id)
        2. resource_pack_id from the request (explicitly specified during create)
        3. ResourcePack matching the task's game_profile

        N197-8: The FK field is now the primary source. Old paths kept for
        backward compatibility during migration.

        Returns:
            ResourcePack or None.
        """
        # 1. FK field (set by serializer via resource_pack_id)
        if instance.resource_pack_id:
            return instance.resource_pack

        # 2. From request data (backward compat)
        if hasattr(self, 'request') and self.request:
            rp_id = self.request.data.get('resource_pack_id')
            if rp_id:
                from resources.models import ResourcePack
                try:
                    return ResourcePack.objects.get(pk=rp_id)
                except ResourcePack.DoesNotExist:
                    logger.warning("resource_pack_id %s not found", rp_id)

        # 3. Fall back to game_profile match
        if instance.game_profile_id:
            from resources.models import ResourcePack
            pack = ResourcePack.objects.filter(
                game_profile=instance.game_profile
            ).first()
            if pack:
                return pack

        return None

    def perform_create(self, serializer):
        """Create a task, write to JSON file, then sync to DB.

        N197-2: The JSON file in ``resources/<pack>/tasks/<name>.json``
        is the source of truth. After saving to DB, we write the JSON file
        and run import_pipelines to ensure consistency.
        """
        instance = serializer.save()
        resource_pack = self._get_resource_pack(instance)
        if resource_pack:
            from resources.import_utils import import_pipelines, write_task_to_json_file
            write_task_to_json_file(instance, resource_pack)
            pack_dir = Path(resource_pack.directory_path)
            import_pipelines(pack_dir, resource_pack)

    def perform_update(self, serializer):
        """Update a task, re-write the JSON file, then sync to DB."""
        instance = serializer.save()
        resource_pack = self._get_resource_pack(instance)
        if resource_pack:
            from resources.import_utils import import_pipelines, write_task_to_json_file
            write_task_to_json_file(instance, resource_pack)
            pack_dir = Path(resource_pack.directory_path)
            import_pipelines(pack_dir, resource_pack)

    def perform_destroy(self, instance):
        """Delete the JSON file first, then delete the DB record."""
        resource_pack = self._get_resource_pack(instance)
        if resource_pack:
            from resources.import_utils import delete_task_json_file, import_pipelines
            delete_task_json_file(instance, resource_pack)
            pack_dir = Path(resource_pack.directory_path)
            import_pipelines(pack_dir, resource_pack)
        instance.delete()

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build before/after diff for audit log.

        - CREATE: snapshot key fields (no ``before``)
        - UPDATE: before/after diff of name / execution_mode / is_enabled
        - DELETE: snapshot ``before`` only
        """
        # Defensive: params_config / task_definition may carry secrets in
        # custom action payloads; never include them in audit details.
        snapshot_keys = ("name", "execution_mode", "is_enabled")
        if action == AuditAction.CREATE:
            return build_diff_details(
                before=None,
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra={"password", "encrypted_password", "token"},
            )
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k, None) for k in snapshot_keys},
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra={"password", "encrypted_password", "token"},
            )
        if action == AuditAction.DELETE:
            return build_diff_details(
                before={k: getattr(instance, k, None) for k in snapshot_keys},
                after=None,
                sensitive_extra={"password", "encrypted_password", "token"},
            )
        return {}

    @action(detail=True, methods=["post"], url_path="execute")
    @audit_action(AuditAction.EXECUTE, AuditResourceType.TASK)
    def execute(self, request, pk=None):
        """执行指定任务，可选择指定 Agent、Device 和 GameAccount。

        委托给 ``TaskService.dispatch`` 处理跨 App 的 Agent/Device/
        GameAccount 查找和校验逻辑 (TD-265, Phase 1)。
        """
        task = self.get_object()
        serializer = TaskExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        agent_id = serializer.validated_data.get("agent_id")
        device_id = serializer.validated_data.get("device_id")
        game_account_id = serializer.validated_data.get("game_account_id")
        resource_pack_id = serializer.validated_data.get("resource_pack_id")

        # Cross-app Agent/Device lookup + task binding validation is
        # delegated to the service layer. TaskBindingError carries the
        # HTTP status so we don't need to inspect the cause.
        try:
            execution = TaskService().dispatch(
                task, agent_id, request.user,
                device_id=device_id,
                game_account_id=game_account_id,
                resource_pack_id=resource_pack_id,
            )
        except TaskBindingError as exc:
            return Response(
                {"detail": exc.message},
                status=exc.status_code,
            )

        return Response(
            TaskExecutionSerializer(execution).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="cancel")
    @audit_action(AuditAction.UPDATE, AuditResourceType.TASK)
    def cancel(self, request, pk=None):
        """取消指定任务的执行。

        委托给 ``TaskService.cancel`` 处理状态更新、Agent 通知和资源释放。
        """
        task = self.get_object()
        running_executions = list(
            task.executions.filter(
                status__in=[TaskExecution.Status.PENDING, TaskExecution.Status.RUNNING]
            ).select_related("agent")
        )
        if not running_executions:
            return Response(
                {"detail": "没有正在运行或等待中的执行记录"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cancel_reason = request.data.get("reason", "用户手动取消")
        task_service = TaskService()
        for execution in running_executions:
            task_service.cancel(execution, reason=cancel_reason)
        return Response({"detail": f"已取消 {len(running_executions)} 条执行记录"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="validate")
    def validate(self, request, pk=None):
        """Validate ``task_definition`` structure for a Task.

        POST /api/v2/tasks/<pk>/validate/
        Returns ``{"valid": bool, "detail": str, "errors": list[dict]}``.

        N192 B3 P1: errors 改为返回 CheckItem dict 列表 (含 check/status/message/
        node_id/suggestion), 不再压成 list[str], 让前端能定位到具体节点。

        早期结构错误 (task_definition 空 / 不是 dict / nodes 缺失等) 也用 CheckItem
        dict 格式, 保持响应结构一致。

        pipeline 模式调用 PipelineValidator 跑完整校验 (必填字段 + 模板引用 +
        Pipeline 引用 + 孤立节点 + 入口出口)。state_machine 模式保留原有结构校验
        (states 数组 + name/transitions 字段), 但 errors 同样用 CheckItem dict 格式。

        spec-2026-07-27-execution-path-unification 阶段 6: chain 模式已废弃,
        默认分支改为 pipeline schema 校验 (nodes 数组).
        """
        from pipeline.validators import PipelineValidator

        task = self.get_object()
        task_definition = task.task_definition

        def _early_error(message: str) -> dict:
            """早期结构错误也包装成 CheckItem dict, 保持响应结构一致."""
            return {
                "check": "structure",
                "status": "fail",
                "message": message,
                "node_id": None,
                "suggestion": "",
            }

        if not task_definition:
            return Response(
                {"valid": False, "detail": "任务定义不能为空",
                 "errors": [_early_error("任务定义不能为空")]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(task_definition, dict):
            return Response(
                {"valid": False, "detail": "任务定义必须是 JSON 对象",
                 "errors": [_early_error("任务定义必须是 JSON 对象")]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        execution_mode = (task.execution_mode or "pipeline").lower()

        if execution_mode == "state_machine":
            # state_machine 模式保留原有结构校验, 但 errors 改为 CheckItem dict 列表
            early_errors: list[dict] = []
            states = task_definition.get("states")
            if not isinstance(states, list):
                early_errors.append(_early_error("state_machine 模式需要 states 数组"))
            elif len(states) == 0:
                early_errors.append(_early_error("states 不能为空数组"))
            else:
                for i, state in enumerate(states):
                    if not isinstance(state, dict):
                        early_errors.append(_early_error(f"states[{i}] 必须是对象"))
                        continue
                    if "name" not in state:
                        early_errors.append(_early_error(f"states[{i}] 缺少 name 字段"))
                    if "transitions" not in state:
                        early_errors.append(_early_error(f"states[{i}] 缺少 transitions 字段"))

            if early_errors:
                detail = "; ".join(e["message"] for e in early_errors)
                return Response(
                    {"valid": False, "detail": detail, "errors": early_errors},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(
                {"valid": True, "detail": "任务定义验证通过", "errors": []},
                status=status.HTTP_200_OK,
            )

        # pipeline 模式 (默认) — spec-2026-07-27 阶段 6: chain 已废弃
        nodes = task_definition.get("nodes")
        if not isinstance(nodes, list):
            return Response(
                {"valid": False, "detail": "pipeline 模式需要 nodes 数组",
                 "errors": [_early_error("pipeline 模式需要 nodes 数组")]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(nodes) == 0:
            return Response(
                {"valid": False, "detail": "nodes 不能为空数组",
                 "errors": [_early_error("nodes 不能为空数组")]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 调用 PipelineValidator 跑结构 + 必填字段 + 模板引用 + Pipeline 引用 等检查
        graph_data = {"nodes": nodes, "edges": task_definition.get("edges", [])}
        validator = PipelineValidator()
        check_items = validator.validate(graph_data)

        # 过滤出 fail 和 warn (pass 不返回, 减少前端噪音)
        errors_and_warnings = [item for item in check_items if item["status"] in ("fail", "warn")]

        valid = all(item["status"] != "fail" for item in check_items)
        return Response(
            {"valid": valid,
             "detail": "任务定义验证通过" if valid else "校验未通过",
             "errors": errors_and_warnings},
            status=status.HTTP_200_OK if valid else status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=False, methods=["post"], url_path="validate-payload")
    def validate_payload(self, request):
        """校验 inline task_definition, 不写库, 返回 CheckItem 列表。

        POST /api/v2/tasks/validate-payload/
        Body: {"task_definition": {...}, "execution_mode": "pipeline"|"state_machine"}
        Query: ?strict=true — Task 4.26 (P0-6) strict mode 拒绝任何旧 schema 字段
        Returns: {"valid": bool, "detail": str, "errors": list[dict], "warnings": list[dict]}

        与 validate action 的区别:
        - validate action: 校验已存在的 Task (需要 pk), 从 task.task_definition 读取
        - validate_payload action: 校验 inline payload (无需 pk), 从 request.data 读取

        Task 1.4 (P1-6): 用于前端 Editor 在 createTask 之前预校验, 统一校验口径,
        避免 createTask 后 validate 失败再 deleteTask 的 race condition。

        Task 4.26 (P0-6): strict mode 用于主动验证 schema 完全归一化, 拒绝新旧
        字段共存 (templateId/action/type/next_step/retry_interval/fallback_action
        等旧字段在 strict 模式下返回 fail)。默认宽松模式 (strict=false), 兼容历史。

        响应结构与 validate action 略有不同: errors 只含 fail 项, warnings 只含
        warn 项 (validate action 的 errors 同时含 fail + warn)。这样前端可以
        分别展示错误和警告。
        """
        from pipeline.validators import PipelineValidator

        task_definition = request.data.get("task_definition", {})
        execution_mode = (request.data.get("execution_mode") or "pipeline").lower()
        # Task 4.26 (P0-6): strict mode 拒绝旧 schema 字段
        strict = request.query_params.get("strict", "false").lower() == "true"

        def _early_error(message: str) -> dict:
            """早期结构错误也包装成 CheckItem dict, 保持响应结构一致."""
            return {
                "check": "structure",
                "status": "fail",
                "message": message,
                "node_id": None,
                "suggestion": "",
            }

        if not task_definition:
            return Response(
                {"valid": False, "detail": "任务定义不能为空",
                 "errors": [_early_error("任务定义不能为空")], "warnings": []},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(task_definition, dict):
            return Response(
                {"valid": False, "detail": "任务定义必须是 JSON 对象",
                 "errors": [_early_error("任务定义必须是 JSON 对象")], "warnings": []},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if execution_mode == "state_machine":
            # state_machine 模式保留原有结构校验, errors 用 CheckItem dict 列表
            early_errors: list[dict] = []
            states = task_definition.get("states")
            if not isinstance(states, list):
                early_errors.append(_early_error("state_machine 模式需要 states 数组"))
            elif len(states) == 0:
                early_errors.append(_early_error("states 不能为空数组"))
            else:
                for i, state in enumerate(states):
                    if not isinstance(state, dict):
                        early_errors.append(_early_error(f"states[{i}] 必须是对象"))
                        continue
                    if "name" not in state:
                        early_errors.append(_early_error(f"states[{i}] 缺少 name 字段"))
                    if "transitions" not in state:
                        early_errors.append(_early_error(f"states[{i}] 缺少 transitions 字段"))

            if early_errors:
                detail = "; ".join(e["message"] for e in early_errors)
                return Response(
                    {"valid": False, "detail": detail,
                     "errors": early_errors, "warnings": []},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(
                {"valid": True, "detail": "任务定义验证通过",
                 "errors": [], "warnings": []},
                status=status.HTTP_200_OK,
            )

        # pipeline 模式 (默认) — spec-2026-07-27 阶段 6: chain 已废弃
        nodes = task_definition.get("nodes")
        if not isinstance(nodes, list):
            return Response(
                {"valid": False, "detail": "pipeline 模式需要 nodes 数组",
                 "errors": [_early_error("pipeline 模式需要 nodes 数组")],
                 "warnings": []},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(nodes) == 0:
            return Response(
                {"valid": False, "detail": "nodes 不能为空数组",
                 "errors": [_early_error("nodes 不能为空数组")], "warnings": []},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 调用 PipelineValidator 跑结构 + 必填字段 + 模板引用 + Pipeline 引用 等检查
        # Task 4.26 (P0-6): strict=true 时追加 _check_legacy_fields 检查
        graph_data = {"nodes": nodes, "edges": task_definition.get("edges", [])}
        validator = PipelineValidator()
        check_items = validator.validate(graph_data, strict=strict)

        # 拆分 fail / warn (pass 不返回, 减少前端噪音)
        errors = [item for item in check_items if item["status"] == "fail"]
        warnings = [item for item in check_items if item["status"] == "warn"]

        valid = len(errors) == 0
        return Response(
            {"valid": valid,
             "detail": "任务定义验证通过" if valid else "校验未通过",
             "errors": errors,
             "warnings": warnings},
            status=status.HTTP_200_OK if valid else status.HTTP_400_BAD_REQUEST,
        )


class TaskParallelConfigView(APIView):
    """并行执行配置 API (T5-B03 部分)"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=ParallelConfigSerializer,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Update parallel execution config (parallel_mode + max_concurrency) for a Task.",
    )
    def put(self, request, pk):
        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response({"detail": "任务不存在"}, status=status.HTTP_404_NOT_FOUND)

        config_serializer = ParallelConfigSerializer(data=request.data)
        if not config_serializer.is_valid():
            return Response(config_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Snapshot before-state for audit diff.
        before_parallel_mode = task.parallel_mode
        before_max_concurrency = task.max_concurrency

        task.parallel_mode = config_serializer.validated_data["parallel_mode"]
        task.max_concurrency = config_serializer.validated_data["max_concurrency"]
        task.save(update_fields=["parallel_mode", "max_concurrency", "updated_at"])

        # Audit: parallel-config change is a sensitive UPDATE on the task
        # resource (affects execution throughput / scheduling).
        from accounts.audit import log_audit

        log_audit(
            user=request.user,
            action=AuditAction.UPDATE,
            resource_type=AuditResourceType.TASK,
            resource_id=str(task.pk),
            details=build_diff_details(
                before={
                    "parallel_mode": before_parallel_mode,
                    "max_concurrency": before_max_concurrency,
                },
                after={
                    "parallel_mode": task.parallel_mode,
                    "max_concurrency": task.max_concurrency,
                },
                sensitive_extra={"password", "encrypted_password", "token"},
            ),
            ip_address=get_client_ip(request),
        )

        return Response({"parallel_mode": task.parallel_mode, "max_concurrency": task.max_concurrency})


class TaskBulkActionView(APIView):
    """批量操作 API (T5-B05)"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @staticmethod
    def _delete_task_json(task):
        """Delete the JSON file for a task, if it belongs to a resource pack."""
        from resources.import_utils import delete_task_json_file
        from resources.models import ResourcePack

        if task.game_profile_id:
            pack = ResourcePack.objects.filter(
                game_profile=task.game_profile
            ).first()
            if pack:
                delete_task_json_file(task, pack)

    # Map bulk-action slug → AuditAction constant. ``export`` is read-only
    # but still logged so auditors can trace large data exfiltration.
    _BULK_ACTION_TO_AUDIT = {
        "enable": AuditAction.UPDATE,
        "disable": AuditAction.UPDATE,
        "delete": AuditAction.DELETE,
        "export": AuditAction.EXPORT,
    }

    @extend_schema(
        request=BulkActionSerializer,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        description="Perform a bulk action (enable/disable/delete/export) across multiple tasks.",
    )
    def post(self, request):
        serializer = BulkActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        action = serializer.validated_data["action"]
        task_ids = serializer.validated_data["task_ids"]

        if action == "export":
            # Read-only export does not need row locks.
            tasks = Task.objects.filter(pk__in=task_ids)
            affected = tasks.count()
            tasks_data = []
            for t in tasks:
                tasks_data.append(
                    {
                        "id": t.pk,
                        "name": t.name,
                        "execution_mode": t.execution_mode,
                        "task_definition": t.task_definition,
                        "is_enabled": t.is_enabled,
                    }
                )
            self._log_bulk_audit(request, action, task_ids, affected)
            return Response(
                {
                    "action": "export",
                    "count": affected,
                    "tasks": tasks_data,
                }
            )


        # Lock matched rows so count + mutation is atomic and concurrent
        # bulk requests cannot interleave (TOCTOU race on task_ids set).
        with transaction.atomic():
            tasks = Task.objects.select_for_update().filter(pk__in=task_ids)
            affected = tasks.count()

            if action == "enable":
                tasks.update(is_enabled=True)
                msg = f"已启用 {affected} 个任务"
            elif action == "disable":
                tasks.update(is_enabled=False)
                msg = f"已禁用 {affected} 个任务"
            elif action == "delete":
                # N197-2: Delete JSON files before deleting DB records
                for task in tasks:
                    self._delete_task_json(task)
                tasks.delete()
                msg = f"已删除 {affected} 个任务"
            else:
                return Response({"detail": "无效操作"}, status=status.HTTP_400_BAD_REQUEST)

        self._log_bulk_audit(request, action, task_ids, affected)
        return Response({"action": action, "affected": affected, "message": msg})

    def _log_bulk_audit(self, request, action, task_ids, affected):
        """Record an audit log entry for bulk task operations.

        ``resource_id`` is empty because bulk actions span multiple
        resources; ``details.task_ids`` carries the affected IDs.
        """
        from accounts.audit import log_audit

        audit_action = self._BULK_ACTION_TO_AUDIT.get(action, AuditAction.UPDATE)
        log_audit(
            user=request.user,
            action=audit_action,
            resource_type=AuditResourceType.TASK,
            resource_id="",
            details=filter_sensitive_fields(
                {
                    "endpoint": request.path,
                    "method": request.method,
                    "bulk_action": action,
                    "task_ids": [str(tid) for tid in task_ids],
                    "affected": affected,
                },
                extra_sensitive={"password", "encrypted_password", "token"},
            ),
            ip_address=get_client_ip(request),
        )


class TaskCloneView(APIView):
    """任务克隆 API (T5-B07)"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    @extend_schema(
        request=None,
        responses={201: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Clone a Task (deep-copy task_definition, params_config, tags, etc.).",
    )
    def post(self, request, pk):
        try:
            task = (
                Task.objects.select_related("rotation_rule")
                .prefetch_related("game_accounts", "device_mappings")
                .get(pk=pk)
            )
        except Task.DoesNotExist:
            return Response({"detail": "任务不存在"}, status=status.HTTP_404_NOT_FOUND)


        with transaction.atomic():
            new_task = Task(
                name=f"{task.name}_副本",
                description=task.description,
                execution_mode=task.execution_mode,
                task_definition=copy.deepcopy(task.task_definition),
                params_config=copy.deepcopy(task.params_config),
                is_enabled=False,
                tags=copy.deepcopy(task.tags),
                retry_policy=copy.deepcopy(task.retry_policy),
                preflight_config=copy.deepcopy(task.preflight_config),
                recovery_config=copy.deepcopy(task.recovery_config),
                parallel_mode=task.parallel_mode,
                max_concurrency=task.max_concurrency,
                folder=task.folder,
                rotation_rule=task.rotation_rule,
            )
            new_task.save()

            new_task.game_accounts.set(task.game_accounts.all())

            for mapping in task.device_mappings.all():
                TaskDevice.objects.create(
                    device=mapping.device,
                    task=new_task,
                )

        # Audit: clone is a CREATE on the new task resource; log both
        # source and new task IDs so auditors can trace the lineage.
        from accounts.audit import log_audit

        log_audit(
            user=request.user,
            action=AuditAction.CREATE,
            resource_type=AuditResourceType.TASK,
            resource_id=str(new_task.pk),
            details=filter_sensitive_fields(
                {
                    "endpoint": request.path,
                    "method": request.method,
                    "source_task_id": task.pk,
                    "source_task_name": task.name,
                    "new_task_id": new_task.pk,
                    "new_task_name": new_task.name,
                },
                extra_sensitive={"password", "encrypted_password", "token"},
            ),
            ip_address=get_client_ip(request),
        )

        # N197-2: Write the cloned task to a JSON file in the resource pack
        if task.game_profile_id:
            from pathlib import Path

            from resources.import_utils import import_pipelines, write_task_to_json_file
            from resources.models import ResourcePack

            pack = ResourcePack.objects.filter(
                game_profile=task.game_profile
            ).first()
            if pack:
                write_task_to_json_file(new_task, pack)
                pack_dir = Path(pack.directory_path)
                import_pipelines(pack_dir, pack)

        return Response(
            {
                "id": new_task.pk,
                "name": new_task.name,
                "message": f"任务已复制: {new_task.name}",
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["tasks"],
    summary="List all versions for a task",
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter(
            name='task_id',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Task primary key',
            required=True,
        ),
    ],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def task_version_list_view(request):
    """
    List all versions for a specific task.

    GET /api/v2/tasks/{id}/versions/
    Returns paginated version history with snapshot summaries.
    """
    # @api_view allowed: custom response shape (task_id + task_name + total_versions + versions list)
    task_id = request.query_params.get("task_id")
    if not task_id:
        return Response(
            {"detail": "Missing task_id parameter"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        return Response(
            {"detail": f"Task {task_id} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    versions = TaskVersion.objects.filter(task=task)
    serializer = TaskVersionSerializer(versions, many=True)
    return Response(
        {
            "task_id": task.id,
            "task_name": task.name,
            "total_versions": versions.count(),
            "versions": serializer.data,
        }
    )


@extend_schema(
    tags=["tasks"],
    summary="Save current task config as a new version snapshot",
    request=OpenApiTypes.OBJECT,
    responses={201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def task_version_save_view(request, pk=None):
    """
    Save current task configuration as a new version snapshot.

    POST /api/v2/tasks/{id}/save-version/
    Body: { "change_description": "optional description" }
    Creates a new version with auto-incremented version number.
    """
    # @api_view allowed: creates version snapshot from current Task state (cross-model write)
    try:
        task = Task.objects.get(pk=pk)
    except Task.DoesNotExist:
        return Response(
            {"detail": f"Task {pk} not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = TaskVersionCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    task_serializer = TaskSerializer(task)
    snapshot_data = task_serializer.data

    max_version = (
        TaskVersion.objects.filter(task=task).aggregate(models.Max("version_number"))["version_number__max"] or 0
    )

    version = TaskVersion.objects.create(
        task=task,
        version_number=max_version + 1,
        snapshot=snapshot_data,
        change_description=serializer.validated_data.get("change_description", ""),
        created_by=request.user,
    )

    return Response(
        {
            "id": version.id,
            "version_number": version.version_number,
            "change_description": version.change_description,
            "created_at": version.created_at.isoformat(),
            "message": f"Version {version.version_number} saved successfully",
        },
        status=status.HTTP_201_CREATED,
    )
