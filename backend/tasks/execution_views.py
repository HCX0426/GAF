"""
执行管理模块 - Phase 9 后端 API 视图
提供 Pipeline 步骤详情、手动干预、每日报告、无人值守日志等接口

(从 executions app 迁移，2026-08-04)
"""
import base64
import logging
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from gaf_core.audit_constants import AuditAction, AuditResourceType, get_client_ip
from gaf_core.error_codes import ErrorCode
from gaf_core.responses import unified_response
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import RoleBasedPermission
from tasks.serializers import TaskExecutionSerializer

# spec-59-E / TD-297: avoid top-level ``from tasks.models import ...``
# cross-app import. executions app is the view layer for tasks (no own
# models; all 9 view functions read TaskExecution / ExecutionStep). Migrating
# 35 use sites to a service layer would require 8+ wrapper functions —
# over-engineering per N178-A3. Use apps.get_model at module load time
# (apps registry is ready by the time URL config imports this module) so
# TaskExecution / ExecutionStep are available as module attributes for name
# lookup inside functions, without a top-level cross-app import statement.
TaskExecution = apps.get_model('tasks', 'TaskExecution')
ExecutionStep = apps.get_model('tasks', 'ExecutionStep')

logger = logging.getLogger(__name__)


# =============================================================================
# Task ↔ Device binding views
# =============================================================================


@extend_schema(tags=['tasks'], summary='Bind devices to a task')
class TaskBindDevicesView(APIView):
    """Bind/unbind devices to/from a task.

    POST /api/v2/tasks/bind-devices/<pk>/  — bind devices
    DELETE /api/v2/tasks/bind-devices/<pk>/<mapping_id>/ — unbind a device
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    def post(self, request, pk):
        """Bind devices to a task."""
        from tasks.models import Task, TaskDevice
        from tasks.serializers import BatchDeviceBindingSerializer

        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response({"detail": "任务不存在"}, status=status.HTTP_404_NOT_FOUND)

        serializer = BatchDeviceBindingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        mappings = serializer.validated_data["mappings"]
        with transaction.atomic():
            TaskDevice.objects.filter(task=task).delete()
            for mapping in mappings:
                TaskDevice.objects.create(task=task, device_id=mapping["device_id"])

        return Response({"detail": f"已绑定 {len(mappings)} 个设备", "count": len(mappings)})

    def delete(self, request, pk, mapping_id=None):
        """Unbind a device from a task."""
        from tasks.models import Task, TaskDevice

        try:
            Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response({"detail": "任务不存在"}, status=status.HTTP_404_NOT_FOUND)

        if mapping_id:
            deleted, _ = TaskDevice.objects.filter(pk=mapping_id, task_id=pk).delete()
            if deleted:
                return Response({"detail": "设备已解绑"})
            return Response({"detail": "绑定记录不存在"}, status=status.HTTP_404_NOT_FOUND)

        return Response({"detail": "缺少 mapping_id"}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['tasks'], summary='Bind accounts to a task')
class TaskBindAccountsView(APIView):
    """Bind/unbind game accounts to/from a task.

    POST /api/v2/tasks/bind-accounts/<pk>/  — bind accounts
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"

    def post(self, request, pk):
        """Bind game accounts to a task."""
        from tasks.models import Task
        from tasks.serializers import AccountBindingSerializer
        from tasks.services import bind_task_accounts

        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response({"detail": "任务不存在"}, status=status.HTTP_404_NOT_FOUND)

        serializer = AccountBindingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = bind_task_accounts(
            task=task,
            account_ids=serializer.validated_data["account_ids"],
            rotation_rule_id=serializer.validated_data.get("rotation_rule_id"),
            user=request.user,
        )

        return Response(result)


# =============================================================================
# Execution management views
# =============================================================================


@extend_schema(
    tags=['executions'],
    summary='List pipeline steps for an execution',
    responses={200: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter('step_index', OpenApiTypes.INT, description='Return only the step with this index.'),
    ],
)
def execution_steps_view(request, pk):
    """获取指定执行的 Pipeline 步骤详情列表。

    ⚠️ 此函数被 **两种方式** 调用:
      1. 从 ``TaskExecutionViewSet`` 的 steps action 直接调用
         — request 是 DRF Request, 权限已在 ViewSet 层检查。
      2. 从 ``executions/urls.py`` 的独立 URL 端点调用
         — request 是 Django HttpRequest, 由 ``@api_view`` 自动包装。

    因此本函数**不**加 ``@api_view`` / ``@permission_classes`` 装饰器,
    由调用方负责 URL 路由和权限检查。

    从 ExecutionStep 表查询步骤数据，按 step_index 排序。
    Admin 可查看任意执行；其他用户仅能查看自己触发的执行。
    """
    steps_qs = ExecutionStep.objects.filter(task_result_id=pk).order_by('step_index')
    step_index = request.query_params.get('step_index')

    try:
        execution = TaskExecution.objects.get(pk=pk)
    except TaskExecution.DoesNotExist:
        # Task 4.53 (P1-33, 2026-07-28): 改用 unified_response 信封
        return unified_response(
            message=f'执行记录 #{pk} 不存在',
            code=ErrorCode.NOT_FOUND,
            status=status.HTTP_404_NOT_FOUND,
        )

    # Non-admin users can only view their own executions
    if request.user.role != 'admin' and execution.triggered_by_id != request.user.id:
        return Response(
            {'error': '无权查看此执行记录'},
            status=status.HTTP_403_FORBIDDEN,
        )

    steps = []
    for s in steps_qs:
        steps.append({
            'id': s.id,
            'execution_id': s.task_result_id,
            'index': s.step_index,
            'name': s.step_name,
            'status': s.status,
            'started_at': s.started_at.isoformat() if s.started_at else None,
            'duration': s.duration.total_seconds() if s.duration else None,
            'retries': s.retry_count,
            'error_message': s.error_message or None,
            'screenshot_url': s.screenshot_path or None,
        })

    if step_index is not None:
        try:
            idx = int(step_index)
            step = next((s for s in steps if s['index'] == idx), None)
            if step:
                return Response({'execution_id': pk, 'step': step})
            return Response(
                {'error': f'未找到索引为 {idx} 的步骤'},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (ValueError, TypeError):
            # Task 4.53 (P1-33, 2026-07-28): 改用 unified_response 信封
            return unified_response(
                message='step_index 参数必须为整数',
                code=ErrorCode.INVALID_PARAMS,
                status=status.HTTP_400_BAD_REQUEST,
            )

    return Response({
        'execution_id': pk,
        'total_steps': len(steps),
        'completed_steps': sum(1 for s in steps if s['status'] == 'success'),
        'running_steps': sum(1 for s in steps if s['status'] == 'running'),
        'pending_steps': sum(1 for s in steps if s['status'] == 'pending'),
        'steps': steps,
    })


def execution_intervene_view(request, pk):
    """手动干预正在运行的执行任务。

    ⚠️ 此函数被 **两种方式** 调用:
      1. 从 ``TaskExecutionViewSet`` 的 action (cancel/pause/resume/skip) 直接调用
         — request 是 DRF Request, 权限已在 ViewSet 层检查。
      2. 从 ``executions/urls.py`` 的独立 URL 端点调用
         — request 是 Django HttpRequest, 由 ``@api_view`` 自动包装。

    因此本函数**不**加 ``@api_view`` / ``@permission_classes`` 装饰器,
    由调用方负责 URL 路由和权限检查。

    支持 pause/resume/skip_step/fail_step/cancel 操作。
    尝试更新 TaskExecution 状态。Admin 可干预任意执行；其他用户仅能干预自己触发的执行。
    """
    valid_actions = {'pause', 'resume', 'skip_step', 'fail_step', 'cancel'}
    action = request.data.get('action')
    reason = request.data.get('reason', '')

    if not action:
        # Task 4.53 (P1-33, 2026-07-28): 改用 unified_response 信封
        return unified_response(
            message='缺少必要参数 action',
            code=ErrorCode.INVALID_PARAMS,
            status=status.HTTP_400_BAD_REQUEST,
        )
    if action not in valid_actions:
        # Task 4.53 (P1-33, 2026-07-28): 改用 unified_response 信封,
        # valid_actions 透传到 data 让前端展示可选项
        return unified_response(
            data={'valid_actions': sorted(valid_actions)},
            message=f'无效的 action 参数: {action}',
            code=ErrorCode.INVALID_PARAMS,
            status=status.HTTP_400_BAD_REQUEST,
        )

    action_labels = {
        'pause': '暂停执行',
        'resume': '恢复执行',
        'skip_step': '跳过当前步骤',
        'fail_step': '标记步骤失败',
        'cancel': '取消执行',
    }

    try:
        with transaction.atomic():
            # Lock the execution row to prevent concurrent intervention
            # race conditions (pause/resume/cancel/skip_step/fail_step).
            execution = TaskExecution.objects.select_for_update().get(pk=pk)

            # Non-admin users can only intervene on their own executions
            if request.user.role != 'admin' and execution.triggered_by_id != request.user.id:
                # Task 4.53 (P1-33, 2026-07-28): 改用 unified_response 信封
                return unified_response(
                    message='无权干预此执行记录',
                    code=ErrorCode.PERMISSION_DENIED,
                    status=status.HTTP_403_FORBIDDEN,
                )

            # ── 状态有效性校验 ──────────────────────────────────────────
            terminal_states = {
                TaskExecution.Status.SUCCESS,
                TaskExecution.Status.FAILED,
                TaskExecution.Status.CANCELLED,
            }
            if action in ('cancel', 'pause', 'resume', 'skip_step', 'fail_step'):
                if action in ('cancel',) and execution.status in terminal_states:
                    return unified_response(
                        message=f'执行记录 #{pk} 已处于 {execution.status} 状态，不可取消',
                        code=ErrorCode.INVALID_PARAMS,
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if action == 'pause' and execution.status != TaskExecution.Status.RUNNING:
                    return unified_response(
                        message=f'仅可暂停运行中的执行 (当前: {execution.status})',
                        code=ErrorCode.INVALID_PARAMS,
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if action == 'resume' and execution.status != TaskExecution.Status.PAUSED:
                    return unified_response(
                        message=f'仅可恢复已暂停的执行 (当前: {execution.status})',
                        code=ErrorCode.INVALID_PARAMS,
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            status_map = {
                'pause': TaskExecution.Status.PAUSED,
                'resume': TaskExecution.Status.RUNNING,
                'cancel': TaskExecution.Status.CANCELLED,
            }
            if action in status_map:
                execution.status = status_map[action]
                execution.save(update_fields=['status'])

            # L3 fix: handle skip_step/fail_step by updating the currently running
            # step's status. Previously these actions were accepted (in valid_actions)
            # but silently did nothing. The task executor should poll step status to
            # actually skip/fail the in-flight operation.
            step_status_map = {
                'skip_step': ExecutionStep.Status.SKIPPED,
                'fail_step': ExecutionStep.Status.FAILED,
            }
            if action in step_status_map:
                running_step = ExecutionStep.objects.filter(
                    task_result_id=execution.pk,
                    status=ExecutionStep.Status.RUNNING,
                ).order_by('step_index').first()
                if running_step:
                    running_step.status = step_status_map[action]
                    running_step.save(update_fields=['status'])
                    logger.info(
                        "步骤 #%s (%s) 已标记为 %s (执行 #%s)",
                        running_step.pk, running_step.step_name,
                        step_status_map[action].value, execution.pk,
                    )
                else:
                    logger.warning(
                        "执行 #%s 无 running 步骤，%s 操作无效果", execution.pk, action,
                    )

            logger.info(
                "用户 %s 对执行 #%s 执行干预操作: action=%s, reason=%s",
                request.user.username, pk, action, reason,
            )
    except TaskExecution.DoesNotExist:
        # Task 4.53 (P1-33, 2026-07-28): 改用 unified_response 信封
        return unified_response(
            message=f'执行记录 #{pk} 不存在',
            code=ErrorCode.NOT_FOUND,
            status=status.HTTP_404_NOT_FOUND,
        )

    # Audit log: record that the user manually intervened on this
    # execution. ``reason`` is operator-supplied free text and may
    # include sensitive context, so we record only action + a short
    # length (not the plaintext reason) to keep AuditLog compact.
    from accounts.audit import log_audit

    log_audit(
        user=request.user,
        action=AuditAction.EXECUTE,
        resource_type=AuditResourceType.TASK_EXECUTION,
        resource_id=str(pk),
        details={
            'execution_id': int(pk),
            'action': action,
            'action_label': action_labels.get(action, action),
            'reason_length': len(reason),
            'operator': request.user.username,
        },
        ip_address=get_client_ip(request),
    )

    return Response({
        'success': True,
        'message': f'已成功执行{action_labels.get(action, action)}操作',
        'intervention': {
            'id': pk,
            'execution_id': int(pk),
            'action': action,
            'action_label': action_labels.get(action, action),
            'operator': request.user.username,
            'reason': reason,
            'created_at': timezone.now().isoformat(),
            'status': 'success',
            'message': f'已成功执行{action_labels.get(action, action)}操作',
        },
    }, status=status.HTTP_200_OK)

# =============================================================================
# TaskExecution ViewSet — restored in Phase 1 (2026-08-08) after being
# accidentally removed during the executions → tasks app consolidation.
# Provides CRUD + custom actions (cancel, pause, resume, skip, retry, etc.)
# that are registered at /api/v2/tasks/task-executions/ via the router.
# =============================================================================


class TaskExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """TaskExecution ViewSet — list, retrieve, and manage executions.

    Custom actions:
    - GET /{pk}/steps/ — list steps for an execution
    - POST /{pk}/cancel/ — cancel a running/pending execution
    - POST /{pk}/pause/ — pause a running execution
    - POST /{pk}/resume/ — resume a paused execution
    - POST /{pk}/skip/<step_index>/ — skip a step
    - POST /{pk}/retry-from-step/ — retry from a failed step
    - GET /{pk}/node-trace/<step_index>/ — get node trace for a step
    """

    serializer_class = TaskExecutionSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "view"
    # N218 (2026-08-29): 补回 status/task/device 过滤 — 此前无 filter_backends,
    # ``?status=running`` 被静默忽略, 工作台"运行任务"恒显示全表 count (91).
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [
        "status", "task", "device", "game_account",
        "triggered_by",
    ]
    search_fields = ["error_message", "result_data"]
    ordering_fields = ["created_at", "started_at", "completed_at", "duration"]
    # 使用全局默认分页 (PageNumberPagination, PAGE_SIZE=20)

    def get_queryset(self):
        qs = TaskExecution.objects.all().order_by("-created_at")
        # TD-351: 默认排除归档记录，支持 ?include_archived=true 查询参数
        include_archived = self.request.query_params.get("include_archived", "false").lower() == "true"
        if not include_archived:
            qs = qs.filter(is_archived=False)
        # Non-admin users see only their own executions
        if self.request.user.role != "admin":
            qs = qs.filter(triggered_by=self.request.user)
        return qs

    @extend_schema(
        tags=["executions"],
        summary="List execution steps",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="steps")
    def steps(self, request, pk=None):
        """List steps for a TaskExecution.

        Delegates to ``execution_steps_view`` for the actual logic.
        """
        return execution_steps_view(request, pk)

    @extend_schema(
        tags=["executions"],
        summary="Execution replay data (step timeline + screenshot frames)",
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="replay")
    def replay(self, request, pk=None):
        """Return replay data for an execution: step timeline + screenshot frames.

        Frames are built from ``ExecutionStep.screenshot_path`` files (base64).
        Steps without a readable screenshot still appear in ``steps`` with an
        estimated frame window so the player timeline stays valid (the frontend
        ``ExecutionReplayPage`` renders empty frames/steps as an empty state).
        """
        execution = self.get_object()
        steps = list(execution.execution_steps.all().order_by("step_index"))

        frames: list[dict] = []
        frame_at_step: dict[int, int] = {}

        for step in steps:
            if not step.screenshot_path:
                continue
            try:
                path = Path(step.screenshot_path)
                if not path.is_file():
                    # Fall back to MEDIA_ROOT-relative path.
                    path = Path(settings.MEDIA_ROOT) / step.screenshot_path
                if not path.is_file():
                    continue
                content = base64.b64encode(path.read_bytes()).decode("ascii")
                frame_at_step[step.step_index] = len(frames)
                frames.append({
                    "index": len(frames),
                    "imageBase64": content,
                    "timestamp": execution.updated_at.isoformat() if execution.updated_at else "",
                    "stepIndex": step.step_index,
                })
            except (OSError, TypeError, ValueError):
                logger.warning(
                    "ExecutionReplay: skip unreadable screenshot for exec=%s step=%s path=%s",
                    execution.pk, step.step_index, step.screenshot_path,
                )
                continue

        total = max(len(frames), 1)
        n_steps = len(steps)
        step_rows: list[dict] = []
        for i, step in enumerate(steps):
            last = total - 1
            start = int(round((i / n_steps) * last)) if n_steps else 0
            end = int(round(((i + 1) / n_steps) * last)) if n_steps else 0
            # A step owning a real screenshot pins its frame window to that frame.
            if step.step_index in frame_at_step:
                start = end = frame_at_step[step.step_index]
            step_rows.append({
                "index": step.step_index,
                "name": step.step_name or step.step_type or f"step-{step.step_index}",
                "status": step.status,
                "duration": step.duration_ms,
                "frameStart": start,
                "frameEnd": end,
            })

        return Response({"steps": step_rows, "frames": frames})

    @extend_schema(
        tags=["executions"],
        summary="Intervene on an execution (pause/resume/skip/cancel)",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Cancel a running/pending execution.

        Delegates to ``execution_intervene_view`` with action=cancel.
        """
        # Inject action into request data (safe for both QueryDict and dict)
        if hasattr(request.data, "_mutable"):
            request.data._mutable = True
            request.data["action"] = "cancel"
            request.data._mutable = False
        else:
            request.data["action"] = "cancel"
        return execution_intervene_view(request, pk)

    @action(detail=True, methods=["post"], url_path="pause")
    def pause(self, request, pk=None):
        """Pause a running execution."""
        if hasattr(request.data, "_mutable"):
            request.data._mutable = True
            request.data["action"] = "pause"
            request.data._mutable = False
        else:
            request.data["action"] = "pause"
        return execution_intervene_view(request, pk)

    @action(detail=True, methods=["post"], url_path="resume")
    def resume(self, request, pk=None):
        """Resume a paused execution."""
        if hasattr(request.data, "_mutable"):
            request.data._mutable = True
            request.data["action"] = "resume"
            request.data._mutable = False
        else:
            request.data["action"] = "resume"
        return execution_intervene_view(request, pk)

    @action(detail=True, methods=["post"], url_path="skip")
    def skip(self, request, pk=None):
        """Skip a step in a running execution.

        Expects ``step_index`` in request body.
        """
        if hasattr(request.data, "_mutable"):
            request.data._mutable = True
            request.data["action"] = "skip_step"
            request.data._mutable = False
        else:
            request.data["action"] = "skip_step"
        return execution_intervene_view(request, pk)

    @extend_schema(
        tags=["executions"],
        summary="Retry execution from a specific step",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], url_path="retry-from-step")
    def retry_from_step(self, request, pk=None):
        """Retry an execution from a specific step index.

        Creates a new TaskExecution copying the successful steps' results
        and dispatches with ``start_step_index`` and ``previous_results``.
        """
        try:
            execution = TaskExecution.objects.get(pk=pk)
        except TaskExecution.DoesNotExist:
            return Response(
                {"error": f"执行记录 #{pk} 不存在"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if execution.status != TaskExecution.Status.FAILED:
            return Response(
                {"error": "只能重试已失败的执行"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        step_index = request.data.get("step_index")
        if step_index is None:
            return Response(
                {"error": "缺少 step_index 参数"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            step_index = int(step_index)
        except (ValueError, TypeError):
            return Response(
                {"error": "step_index 必须为整数"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate that the step_index exists in the execution's steps
        target_step = ExecutionStep.objects.filter(task_result_id=pk, step_index=step_index).first()
        if not target_step:
            return Response(
                {"error": f"执行记录 #{pk} 中不存在索引为 {step_index} 的步骤"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Only allow retry from a FAILED step
        if target_step.status != ExecutionStep.Status.FAILED:
            return Response(
                {"error": f"只能从失败的步骤重试 (步骤 {step_index} 当前状态: {target_step.status})"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build previous_results from successful steps before the retry index
        previous_results = []
        for step in ExecutionStep.objects.filter(
            task_result_id=pk, step_index__lt=step_index,
        ).order_by("step_index"):
            if step.status == ExecutionStep.Status.SUCCESS:
                entry = step.recognition_result or {}
                entry["node_id"] = step.step_name
                previous_results.append(entry)

        # Create new execution
        new_execution = TaskExecution.objects.create(
            task=execution.task,
            pipeline=execution.pipeline,
            device=execution.device,
            game_account=execution.game_account,
            status=TaskExecution.Status.PENDING,
            triggered_by=execution.triggered_by,
        )

        # Dispatch with retry params
        from tasks.tasks import dispatch_task as _dispatch_task

        _dispatch_task.delay(
            new_execution.id,
            start_step_index=step_index,
            previous_results=previous_results,
        )

        return Response(
            {
                "new_execution_id": str(new_execution.id),
                "start_step_index": step_index,
                "previous_results_count": len(previous_results),
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        tags=["executions"],
        summary="Get node trace for a step",
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["get"], url_path="node-trace")
    def node_trace(self, request, pk=None):
        """Get the node trace (screenshot, result, logs) for a specific step.

        Expects ``step_index`` as a query parameter (e.g. ``?step_index=0``).
        Looks up the ExecutionStep by execution + step_index and returns its
        result_data, screenshot_path, error_message, and timing info.
        """
        step_index = request.query_params.get("step_index")
        try:
            step_index = int(step_index)
        except (ValueError, TypeError):
            return Response(
                {"error": "step_index 必须为整数"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            step = ExecutionStep.objects.get(task_result_id=pk, step_index=step_index)
        except ExecutionStep.DoesNotExist:
            return Response(
                {"error": f"未找到索引为 {step_index} 的步骤"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "execution_id": pk,
            "step_index": step_index,
            "step_name": step.step_name,
            "status": step.status,
            "result_data": step.recognition_result or {},
            "screenshot_path": step.screenshot_path or None,
            "error_message": step.error_message or None,
            "started_at": step.started_at.isoformat() if step.started_at else None,
            "duration_ms": int(step.duration * 1000) if step.duration else 0,
            "retry_count": step.retry_count,
        })
