import contextlib
import logging
import os

from django.conf import settings
from django.http import FileResponse
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from gaf_core.audit_constants import AuditAction, AuditResourceType, get_client_ip
from gaf_core.error_codes import ErrorCode
from gaf_core.mixins import AuditMixin, audit_action, build_diff_details
from gaf_core.responses import unified_response
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from workers.auth import WorkerTokenAuthentication

from accounts.permissions import RoleBasedPermission
from pipeline.estimator import PipelineTimeEstimator
from pipeline.models import Pipeline, PipelineSnapshot, Recording, TaskChain, TaskChainExecution, TaskChainNode
from pipeline.serializers import (
    PipelineListSerializer,
    PipelineSerializer,
    PipelineSnapshotSerializer,
    RecordingListSerializer,
    RecordingSerializer,
    TaskChainExecutionSerializer,
    TaskChainNodeSerializer,
    TaskChainSerializer,
)
from pipeline.validators import PipelineValidator

logger = logging.getLogger(__name__)


class PipelineViewSet(AuditMixin, viewsets.ModelViewSet):
    """
    Pipeline CRUD ViewSet (TD-061 Plan B Stage 2: canonical Pipeline ViewSet).

    列表 GET  /api/v2/pipeline/pipelines/
    创建 POST /api/v2/pipeline/pipelines/
    详情 GET  /api/v2/pipeline/pipelines/{id}/
    更新 PUT  /api/v2/pipeline/pipelines/{id}/
    删除 DELETE /api/v2/pipeline/pipelines/{id}/

    Stage 2: TaskExecution.pipeline FK now points to pipeline.Pipeline (after
    tasks 0038 re-pointed it), so execute action creates a TaskExecution row
    to track pipeline runs (previously sent WS only and silently lost
    progress/completion tracking).
    """
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "view"
    audit_resource_type = AuditResourceType.PIPELINE

    def get_permissions(self):
        """H5 fix: viewer can read pipelines; operator+ required for writes."""
        if self.action in ("create", "update", "partial_update", "destroy", "execute", "restore"):
            self.required_permission = "execute"
        else:
            self.required_permission = "view"
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == 'list':
            return PipelineListSerializer
        return PipelineSerializer

    def get_queryset(self):
        """Admin sees all pipelines; other users only see their own."""
        if getattr(self, 'swagger_fake_view', False):
            return Pipeline.objects.none()
        qs = Pipeline.objects.all().order_by('-updated_at')
        # TD-061 Stage 1: user-scoped queryset (matches tasks.Pipeline behavior)
        if self.request.user.role != "admin":
            qs = qs.filter(user=self.request.user)
        search = self.request.query_params.get('search', '')
        if search:
            qs = qs.filter(name__icontains=search)
        is_template = self.request.query_params.get('is_template')
        if is_template is not None:
            qs = qs.filter(is_template=is_template == 'true')
        return qs

    def perform_create(self, serializer):
        """创建时自动设置 version=1 并绑定当前用户。"""
        # Bypass AuditMixin.perform_create (which calls super().perform_create
        # with no kwargs) so we can inject version/user. We log the audit
        # entry manually after the save succeeds. Mirrors the
        # DeviceGroupViewSet pattern in agents/views.py.
        instance = serializer.save(version=1, user=self.request.user)
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, instance)

    def perform_update(self, serializer):
        """更新时 version 自增并创建 Snapshot。"""
        old_instance = self.get_object()
        old_nodes = old_instance.graph_data.get('nodes', [])
        new_nodes = serializer.validated_data.get('graph_data', {}).get('nodes', [])

        old_count = len(old_nodes)
        new_count = len(new_nodes)
        change_summary = f'节点数: {old_count} → {new_count}'

        PipelineSnapshot.objects.create(
            pipeline=old_instance,
            version=old_instance.version,
            graph_data=old_instance.graph_data,
            change_summary=change_summary,
        )
        instance = serializer.save(version=old_instance.version + 1)
        if self.audit_log_update:
            self._log_audit(AuditAction.UPDATE, instance, old_instance=old_instance)

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build audit details for Pipeline writes.

        ``graph_data`` is intentionally excluded — it can be very large
        (React Flow canvas JSON) and is not auditable field-by-field.
        Version + name + is_template captures the meaningful change.
        """
        snapshot_keys = ("name", "version", "is_template", "user_id")
        if action == AuditAction.CREATE:
            return {"after": {k: getattr(instance, k) for k in snapshot_keys}}
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k) for k in snapshot_keys},
                after={k: getattr(instance, k) for k in snapshot_keys},
            )
        if action == AuditAction.DELETE:
            return {"before": {k: getattr(instance, k) for k in snapshot_keys}}
        return {}

    @extend_schema(
        operation_id="pipeline_pipelines_snapshots_list",
        description="List all version snapshots for a Pipeline.",
    )
    @action(detail=True, methods=['get'])
    def snapshots(self, request, pk=None):
        """获取 Pipeline 的版本快照列表。"""
        pipeline = self.get_object()
        snapshots = pipeline.snapshots.all()
        serializer = PipelineSnapshotSerializer(snapshots, many=True)
        return Response(serializer.data)

    @extend_schema(
        operation_id="pipeline_pipelines_snapshot_detail_retrieve",
        description="Retrieve a specific Pipeline snapshot by version.",
        parameters=[
            OpenApiParameter(
                name='version',
                type=OpenApiTypes.INT,
                location=OpenApiParameter.PATH,
                description='Snapshot version number',
                required=True,
            ),
        ],
    )
    @action(detail=True, methods=['get'], url_path='snapshots/(?P<version>[^/.]+)')
    def snapshot_detail(self, request, pk=None, version=None):
        """获取指定版本快照详情。"""
        pipeline = self.get_object()
        try:
            snapshot = pipeline.snapshots.get(version=int(version))
        except PipelineSnapshot.DoesNotExist:
            return Response({'error': 'Snapshot not found'}, status=404)
        serializer = PipelineSnapshotSerializer(snapshot)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='restore/(?P<version>[^/.]+)')
    @audit_action(AuditAction.UPDATE, AuditResourceType.PIPELINE)
    def restore(self, request, pk=None, version=None):
        """恢复到指定版本。"""
        from django.db import transaction

        pipeline = self.get_object()
        try:
            snapshot = pipeline.snapshots.get(version=int(version))
        except PipelineSnapshot.DoesNotExist:
            return Response({'error': f'没有找到版本 {version} 的快照'}, status=404)

        # Snapshot creation and pipeline update must be atomic: a failure
        # between them would leave an orphan snapshot or lose graph_data.
        with transaction.atomic():
            old_graph = pipeline.graph_data
            PipelineSnapshot.objects.create(
                pipeline=pipeline,
                version=pipeline.version,
                graph_data=old_graph,
                change_summary=f'恢复到版本 {version}',
            )
            pipeline.graph_data = snapshot.graph_data
            pipeline.version += 1
            pipeline.save(update_fields=['graph_data', 'version', 'updated_at'])

        serializer = PipelineSerializer(pipeline)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    @audit_action(AuditAction.EXECUTE, AuditResourceType.PIPELINE)
    def execute(self, request, pk=None):
        """Execute a Pipeline on a chosen device/agent.

        spec-2026-08-02-backend-execution-unification: 改为走 dispatch_task
        统一入口，不再直接发 WS。这样 Pipeline 执行也能获得自动选设备、
        meta.json、run.log 等能力，与 Task 执行路径一致。
        """
        from tasks.models import TaskExecution

        pipeline = self.get_object()
        device_id = request.data.get('device_id')
        agent_id = request.data.get('agent_id')

        agent = self._get_online_agent(agent_id)
        if agent is None:
            return unified_response(
                message='没有在线 Agent，请先启动 Agent 或指定 agent_id',
                code=ErrorCode.INVALID_PARAMS,
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 自动检测 device: 优先指定 device_id，否则选 agent 绑定的非 ADB 在线设备
        device = None
        if device_id:
            from workers.models import Device
            with contextlib.suppress(Device.DoesNotExist):
                device = Device.objects.get(pk=device_id)
        if device is None:
            device = self._resolve_best_device(agent)

        # B3-4: 从 ContextVar 取 trace_id
        from gaf_core.tracing.context import current_trace_id
        ctx_trace_id = current_trace_id.get() or ""

        # 创建 TaskExecution，pipeline FK 保留，task=None
        execution = TaskExecution.objects.create(
            task=None,
            pipeline=pipeline,
            agent=agent,
            device=device,
            triggered_by=request.user,
            status=TaskExecution.Status.PENDING,
            trace_id=ctx_trace_id,
        )

        # 走统一入口 dispatch_task（开发模式 CELERY_TASK_ALWAYS_EAGER 同步执行）
        from tasks.tasks import dispatch_task
        try:
            dispatch_task.delay(execution.id, trace_id=ctx_trace_id)
        except Exception as e:
            logger.exception("dispatch_task.delay failed for execution %s", execution.id)
            return Response(
                {'error': f'Failed to dispatch task: {e}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({
            'pipeline_id': str(pipeline.id),
            'execution_id': execution.id,
            'pipeline_name': pipeline.name,
            'agent_id': agent.agent_id,
            'device_id': device.id if device else None,
            'status': 'dispatched',
            'message': f'Pipeline [{pipeline.name}] 已通过 dispatch_task 分发',
        })

    def _resolve_best_device(self, agent):
        """自动检测 agent 绑定的最佳设备——优先选 Windows 在线设备。

        spec-2026-08-02-backend-execution-unification: 避免不传 device_id
        时 agent 连到断连的 ADB 模拟器。
        """
        from workers.models import Device
        return Device.objects.filter(
            agent=agent,
            status='online',
        ).exclude(
            device_type='adb',
        ).exclude(
            device_type='emulator',
        ).first()

    def _get_online_agent(self, agent_id=None):
        # B1 (2026-08-27): delegate to the shared resolver so Task /
        # Pipeline / CLI entry points select workers identically (see
        # tasks/services/worker_resolver.py).
        from tasks.services.worker_resolver import resolve_online_worker

        return resolve_online_worker(agent_id)


class PipelineValidateView(APIView):
    """Pipeline 结构校验接口 POST /api/pipelines/validate/。"""
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT},
        description="Validate a Pipeline graph_data structure against the JSON schema.",
    )
    def post(self, request):
        graph_data = request.data.get('graph_data', {})
        validator = PipelineValidator()
        results = validator.validate(graph_data)
        return Response({'results': results})


class PipelineEstimateTimeView(APIView):
    """Pipeline 执行时间预估接口 POST /api/pipelines/estimate-time/。"""
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT},
        description="Estimate the execution time of a Pipeline based on its graph_data.",
    )
    def post(self, request):
        graph_data = request.data.get('graph_data', {})
        estimator = PipelineTimeEstimator()
        result = estimator.estimate(graph_data)
        return Response(result)


class TaskChainViewSet(AuditMixin, viewsets.ModelViewSet):
    """任务链视图集，管理 DAG 任务链的 CRUD（R37-P3 Stage 7: 从 tasks 迁入）。"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "execute"
    serializer_class = TaskChainSerializer
    audit_resource_type = AuditResourceType.TASK_CHAIN

    def get_permissions(self):
        """TD-078: viewer can read task chains; operator+ required for writes/execute."""
        if self.action in ("create", "update", "partial_update", "destroy", "execute", "set_default"):
            self.required_permission = "execute"
        else:
            self.required_permission = "view"
        return super().get_permissions()

    def get_queryset(self):
        """Admin sees all task chains; other users only see their own."""
        if getattr(self, 'swagger_fake_view', False):
            return TaskChain.objects.none()
        qs = TaskChain.objects.all().select_related("created_by").prefetch_related("chain_nodes")
        if self.request.user.role != "admin":
            qs = qs.filter(created_by=self.request.user)
        return qs

    def perform_create(self, serializer):
        """Create chain with current user, then log audit."""
        # Custom save kwargs (created_by) — bypass AuditMixin.perform_create
        # and log manually after success. Mirrors PipelineViewSet pattern.
        instance = serializer.save(created_by=self.request.user)
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, instance)

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build audit details for TaskChain writes."""
        snapshot_keys = ("name", "is_default", "game_profile_id", "created_by_id")
        if action == AuditAction.CREATE:
            return {"after": {k: getattr(instance, k) for k in snapshot_keys}}
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k) for k in snapshot_keys},
                after={k: getattr(instance, k) for k in snapshot_keys},
            )
        if action == AuditAction.DELETE:
            return {"before": {k: getattr(instance, k) for k in snapshot_keys}}
        return {}

    @action(detail=True, methods=['post'])
    @audit_action(AuditAction.EXECUTE, AuditResourceType.TASK_CHAIN)
    def execute(self, request, pk=None):
        """Execute a TaskChain on a chosen device/agent.

        (spec 阶段 5 — TD-096 + v3 §2.10 window-centric runtime binding)

        Creates a TaskChainExecution and dispatches the first node (lowest
        order). Each node's task is dispatched sequentially — when one
        completes, advance_chain_execution dispatches the next.

        POST /api/v2/pipeline/task-chains/{id}/execute/
        Body (v3): {
            "device_id": 1,            # Device ID for runtime binding
            "agent_id": "agent-xxx",   # Agent.agent_id (optional, auto-pick if omitted)
            "game_account_id": 123     # GameAccount ID for runtime binding (spec §2.10)
        }
        """
        from pipeline.services import ChainDispatchError, create_chain_execution_and_dispatch

        chain = self.get_object()

        device_id = request.data.get('device_id')
        agent_id = request.data.get('agent_id')
        game_account_id = request.data.get('game_account_id')

        try:
            chain_exec = create_chain_execution_and_dispatch(
                chain_id=chain.id,
                agent_id=agent_id,
                device_id=device_id,
                game_account_id=game_account_id,
                triggered_by=request.user,
            )
        except ChainDispatchError as e:
            # Task 4.52 (P1-32, 2026-07-28): 改用 unified_response 信封
            return unified_response(
                message=str(e),
                code=ErrorCode.INVALID_PARAMS,
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fetch first node for response (service already dispatched it).
        # TD-110: select_related pipeline too — node may be PIPELINE type.
        first_node = chain_exec.chain.chain_nodes.select_related(
            'task', 'pipeline',
        ).order_by('order').first()

        # TD-110: render the right ref name based on node_type
        if first_node and first_node.node_type == TaskChainNode.NodeType.PIPELINE:
            first_ref_name = first_node.pipeline.name if first_node.pipeline_id else 'N/A'
        elif first_node:
            first_ref_name = first_node.task.name if first_node.task_id else 'N/A'
        else:
            first_ref_name = 'N/A'

        return Response({
            'chain_id': chain.id,
            'chain_name': chain.name,
            'chain_execution_id': chain_exec.id,
            'agent_id': chain_exec.agent_id,
            'device_id': chain_exec.device_id,
            'game_account_id': chain_exec.game_account_id,
            'first_node_order': first_node.order if first_node else None,
            'first_node_type': first_node.node_type if first_node else None,
            'first_ref_name': first_ref_name,
            'status': 'dispatched',
            'message': f'任务链 [{chain.name}] 已开始执行，首节点: {first_ref_name}',
        })

    @action(detail=True, methods=['post'])
    @audit_action(AuditAction.UPDATE, AuditResourceType.TASK_CHAIN)
    def set_default(self, request, pk=None):
        """Mark this TaskChain as the default for its GameProfile (v3 §2.7.5).

        Atomically:
            1. Set this chain's is_default=True
            2. Set GameProfile.default_task_chain=this chain
            3. Clear is_default on other chains under the same GameProfile

        POST /api/v2/pipeline/task-chains/{id}/set-default/
        """
        from django.db import transaction


        chain = self.get_object()

        if not chain.game_profile_id:
            # Task 4.52 (P1-32, 2026-07-28): 改用 unified_response 信封
            return unified_response(
                message='该 TaskChain 未绑定 GameProfile，无法设为默认链',
                code=ErrorCode.INVALID_PARAMS,
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Clear other is_default=True chains under the same GameProfile
            TaskChain.objects.filter(
                game_profile=chain.game_profile_id,
                is_default=True,
            ).exclude(pk=chain.pk).update(is_default=False)

            # Set this chain as default
            chain.is_default = True
            chain.save(update_fields=['is_default'])

            # Sync GameProfile.default_task_chain
            profile = chain.game_profile
            profile.default_task_chain = chain
            profile.save(update_fields=['default_task_chain'])

        return Response({
            'status': 'ok',
            'chain_id': chain.id,
            'chain_name': chain.name,
            'game_profile_id': chain.game_profile_id,
            'is_default': True,
            'message': f'TaskChain [{chain.name}] 已设为 GameProfile [{profile.game_name}] 的默认链',
        })

    @action(detail=False, methods=['post'], url_path='import_routine')
    @audit_action(AuditAction.IMPORT, AuditResourceType.TASK_CHAIN, resource_id_kw="")
    def import_routine(self, request):
        """Import a routine.json file and convert it to a TaskChain.

        TD-113: reads routine_path from the GameProfile (no longer passed
        in the request body). TD-110 Phase 3: creates a TaskChain with
        PIPELINE nodes (one per routine entry). Idempotent — re-importing
        replaces existing chain nodes.

        POST /api/v2/pipeline/task-chains/import_routine/
        Body: {
            "game_profile_id": 1
        }
        Response: 201 + TaskChainSerializer(chain)
        """
        from django.shortcuts import get_object_or_404

        from gamestate.models import GameProfile
        from pipeline.services import RoutineImportError, convert_routine_to_chain

        game_profile_id = request.data.get('game_profile_id')
        if not game_profile_id:
            return Response(
                {'error': 'game_profile_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        game_profile = get_object_or_404(GameProfile, pk=game_profile_id)

        try:
            chain = convert_routine_to_chain(
                game_profile=game_profile,
                user=request.user,
            )
        except RoutineImportError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TaskChainSerializer(chain, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def executions(self, request, pk=None):
        """Get execution history for a TaskChain.

        GET /api/v2/pipeline/task-chains/{id}/executions/
        """
        chain = self.get_object()
        executions = chain.executions.select_related('chain', 'current_node', 'triggered_by', 'device', 'game_account').prefetch_related('node_executions').all()
        serializer = TaskChainExecutionSerializer(executions, many=True)
        return Response(serializer.data)

    def _get_online_agent(self, agent_id=None):
        """Find an online/idle agent for chain execution."""
        from workers.models import Worker
        online_statuses = (Worker.Status.ONLINE, Worker.Status.IDLE)
        if agent_id:
            try:
                agent = Worker.objects.get(agent_id=agent_id)
                if agent.status in online_statuses:
                    return agent
            except Worker.DoesNotExist:
                logger.debug("_get_online_agent: worker %s not found", agent_id)
            return None
        return Worker.objects.filter(status__in=online_statuses).first()


class TaskChainNodeSchema(AutoSchema):
    """Custom schema for TaskChainNodeView.

    Generates per-URL operation_ids AND excludes unsupported (URL, method)
    combinations so spectacular does not emit operationId collision warnings
    when the same APIView is mounted on multiple URL patterns (TD-268).

    Background: ``/chain-nodes/`` and ``/chain-nodes/{id}/`` both tokenize
    to ``['pipeline', 'chain_nodes']`` (path variables are stripped), so
    spectacular auto-generates the same operation_id for every method on
    every URL — even methods that the view does not really support on a
    given URL (e.g. DELETE on ``/`` with no pk). Excluding those spurious
    combinations at the source is cleaner than minting fake operation_ids.
    """

    # URL suffix -> set of HTTP methods actually supported on that URL.
    # Other (URL, method) pairs are excluded via is_excluded().
    _SUPPORTED = {
        '/': {'get', 'post'},
        '/check-circular/': {'post'},
        '/{id}/': {'get', 'delete'},
    }

    # (path_suffix, method) -> operation_id
    _OP_IDS = {
        ('/', 'get'): 'pipeline_chain_nodes_list',
        ('/', 'post'): 'pipeline_chain_nodes_create',
        ('/check-circular/', 'post'): 'pipeline_chain_nodes_check_circular',
        ('/{id}/', 'get'): 'pipeline_chain_nodes_retrieve',
        ('/{id}/', 'delete'): 'pipeline_chain_nodes_destroy',
    }

    def _url_suffix(self):
        from config.app_info import API_PREFIX, APP_ROUTES
        prefix = f'/{API_PREFIX}/{APP_ROUTES["pipeline"]}/chain-nodes'
        # self.path is the URL path with path variables in {var} form, e.g.
        # '/api/v2/pipeline/chain-nodes/' or '/api/v2/pipeline/chain-nodes/{id}/'.
        if self.path and self.path.startswith(prefix):
            return self.path[len(prefix):]
        return None

    def is_excluded(self) -> bool:
        suffix = self._url_suffix()
        if suffix is None:
            return super().is_excluded()
        method = (self.method or '').lower()
        return method not in self._SUPPORTED.get(suffix, set())

    def get_operation_id(self) -> str:
        suffix = self._url_suffix()
        method = (self.method or '').lower()
        op_id = self._OP_IDS.get((suffix, method))
        if op_id:
            return op_id
        return super().get_operation_id()



class TaskChainNodeView(APIView):
    """任务链节点视图，管理多任务编排的依赖关系（R37-P3 Stage 7: 从 tasks 迁入）。

    Mounted on 3 URL patterns (see pipeline/urls.py): list / check-circular /
    detail. ``TaskChainNodeSchema`` generates per-URL operation_ids so
    spectacular does not emit collision warnings (TD-268).
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "view"
    schema = TaskChainNodeSchema()

    def get_permissions(self):
        """H5 fix: viewer can read chain nodes; operator+ required for writes."""
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            self.required_permission = "execute"
        else:
            self.required_permission = "view"
        return super().get_permissions()

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="List TaskChainNode dependencies, optionally filtered by chain_id/task_id.",
    )
    def get(self, request):
        """获取链节点列表"""
        chain_id = request.query_params.get("chain_id")
        task_id = request.query_params.get("task_id")
        queryset = TaskChainNode.objects.select_related("task", "pipeline", "parent", "parent__task", "parent__pipeline", "chain").all()
        if chain_id:
            queryset = queryset.filter(chain_id=chain_id)
        if task_id:
            queryset = queryset.filter(task_id=task_id)
        return Response(TaskChainNodeSerializer(queryset, many=True).data)

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        description="Create a TaskChainNode dependency or check for circular dependencies.",
    )
    def post(self, request):
        """创建链节点依赖关系或检测循环依赖"""
        if "check-circular" in request.path or request.data.get("action") == "check_circular":
            return self._check_circular(request)

        serializer = TaskChainNodeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        instance = serializer.save()
        # Manual audit log (APIView — no AuditMixin). Skip when the POST
        # is a circular-dependency check (no DB write).
        self._log_audit_node(request, AuditAction.CREATE, instance)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Delete a TaskChainNode dependency by id.",
    )
    def delete(self, request, pk=None):
        """删除链节点依赖关系"""
        pk = pk or self.kwargs.get("pk")
        if not pk:
            return Response({"error": "需要指定节点ID"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            node = TaskChainNode.objects.get(pk=pk)
        except TaskChainNode.DoesNotExist:
            return Response({"error": "链节点不存在"}, status=status.HTTP_404_NOT_FOUND)
        # Snapshot before deletion for the audit "before" payload.
        audit_before = {
            "id": node.id,
            "chain_id": node.chain_id,
            "task_id": node.task_id,
            "parent_id": node.parent_id,
            "order": node.order,
        }
        node.delete()
        self._log_audit_node(
            request,
            AuditAction.DELETE,
            resource_id=str(pk),
            details={"before": audit_before},
        )
        return Response({"deleted": pk}, status=status.HTTP_200_OK)

    def _log_audit_node(self, request, action, instance=None, *, resource_id="", details=None):
        """Write an audit log row for TaskChainNode writes.

        ``resource_type`` is ``TASK_CHAIN`` (parent resource) rather than a
        dedicated ``task_chain_node`` constant — node operations are
        meaningful only in the context of their parent chain, and the
        frontend AuditLogPage i18n keys are scoped to chain-level.
        """
        from accounts.audit import log_audit

        if not resource_id and instance is not None:
            resource_id = str(instance.pk)
        log_audit(
            user=getattr(request, "user", None),
            action=action,
            resource_type=AuditResourceType.TASK_CHAIN,
            resource_id=resource_id,
            details=details or {},
            ip_address=get_client_ip(request),
        )

    def _check_circular(self, request):
        """检测循环依赖"""
        chain_id = request.data.get("chain_id")
        task_id = request.data.get("task_id")

        nodes = TaskChainNode.objects.all()
        if chain_id:
            nodes = nodes.filter(chain_id=chain_id)
        if task_id:
            nodes = nodes.filter(task_id=task_id)

        adj = {}
        for node in nodes:
            parent_id = node.parent_id
            if parent_id is not None:
                if parent_id not in adj:
                    adj[parent_id] = []
                adj[parent_id].append(node.id)

        cycle = self._detect_cycle(adj)
        return Response({"has_cycle": cycle is not None, "cycle_path": cycle})

    def _detect_cycle(self, adj):
        """DFS 检测有向图中的环"""
        visited = set()
        rec_stack = set()
        path = []

        def dfs(node):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    path.append(neighbor)
                    return True
            rec_stack.discard(node)
            path.pop()
            return False

        for node in adj:
            if node not in visited and dfs(node):
                return path
        return None


class IsAgentOrRecordingOwner(BasePermission):
    """Allow an authenticated agent (request.agent) or the recording owner."""

    def has_permission(self, request, view):
        if getattr(request, "agent", None) is not None:
            return True
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if getattr(request, "agent", None) is not None:
            return True
        return bool(request.user and request.user.is_authenticated and obj.user_id == request.user.id)


class RecordingViewSet(AuditMixin, viewsets.ModelViewSet):
    """录制管理 API (P-008: migrated from tasks app).

    Recording belongs in the pipeline app because it is the source material
    for generating Pipelines (via convert_to_pipeline action). The physical
    table ``recording`` is preserved (7 existing rows); the move is state-only.

    列表 GET  /api/v2/pipeline/recordings/
    创建 POST /api/v2/pipeline/recordings/
    详情 GET  /api/v2/pipeline/recordings/{id}/
    更新 PUT  /api/v2/pipeline/recordings/{id}/
    删除 DELETE /api/v2/pipeline/recordings/{id}/
    转换 POST /api/v2/pipeline/recordings/{id}/convert-to-pipeline/
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "view"
    audit_resource_type = AuditResourceType.RECORDING

    def get_permissions(self):
        """H5 fix: viewer can read own recordings; operator+ required for writes."""
        if self.action in ("create", "update", "partial_update", "destroy"):
            self.required_permission = "execute"
        else:
            self.required_permission = "view"
        return super().get_permissions()

    def get_queryset(self):
        """仅返回当前用户的录制"""
        if getattr(self, 'swagger_fake_view', False):
            return Recording.objects.none()
        return Recording.objects.filter(user=self.request.user)

    def get_serializer_class(self):
        """列表使用简化序列化器"""
        if self.action == "list":
            return RecordingListSerializer
        return RecordingSerializer

    def perform_create(self, serializer):
        """创建录制时自动绑定当前用户"""
        # Custom save kwarg (user) — bypass AuditMixin.perform_create and
        # log manually. Mirrors PipelineViewSet / TaskChainViewSet pattern.
        instance = serializer.save(user=self.request.user)
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, instance)

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build audit details for Recording writes."""
        snapshot_keys = ("name", "user_id")
        if action == AuditAction.CREATE:
            return {"after": {k: getattr(instance, k) for k in snapshot_keys}}
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k) for k in snapshot_keys},
                after={k: getattr(instance, k) for k in snapshot_keys},
            )
        if action == AuditAction.DELETE:
            return {"before": {k: getattr(instance, k) for k in snapshot_keys}}
        return {}

    @action(detail=True, methods=["post"], url_path="screenshots",
            authentication_classes=[JWTAuthentication, WorkerTokenAuthentication],
            permission_classes=[IsAgentOrRecordingOwner])
    def upload_screenshot(self, request, pk=None):
        """Upload one screenshot for a recording event.

        multipart form: event_index=<int> + file=<png>. Stored under
        MEDIA_ROOT/screenshots/recordings/<id>/<event_index>.png and the
        event's ``screenshot_url`` is written back to recording_data so the
        detail endpoint serves it automatically.
        """
        recording = Recording.objects.filter(pk=pk).first()
        if recording is None:
            return Response({"error": "recording not found"}, status=status.HTTP_404_NOT_FOUND)

        if getattr(request, "agent", None) is None and recording.user_id != request.user.id:
            return Response({"error": "forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            event_index = int(request.data.get("event_index", -1))
        except (TypeError, ValueError):
            return Response({"error": "event_index must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        events = recording.recording_data.get("events", []) if isinstance(recording.recording_data, dict) else []
        if not (0 <= event_index < len(events)):
            return Response({"error": f"event_index {event_index} out of range"}, status=status.HTTP_400_BAD_REQUEST)

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"error": "file field is required"}, status=status.HTTP_400_BAD_REQUEST)

        dest_dir = os.path.join(settings.MEDIA_ROOT, "screenshots", "recordings", str(recording.pk))
        os.makedirs(dest_dir, exist_ok=True)
        filename = f"{event_index}.png"
        dest = os.path.join(dest_dir, filename)
        with open(dest, "wb") as fh:
            for chunk in upload.chunks():
                fh.write(chunk)

        url = f"/{settings.MEDIA_URL.strip('/')}/screenshots/recordings/{recording.pk}/{filename}"
        events[event_index]["screenshot_url"] = url
        recording.recording_data["events"] = events
        recording.save(update_fields=["recording_data"])
        return Response({"event_index": event_index, "url": url}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="screenshots/(?P<filename>[^/]+)", url_name="screenshot-file",
            authentication_classes=[JWTAuthentication])
    def screenshot_file(self, request, pk=None, filename=None):
        """Serve a recording screenshot file (owner/viewer only)."""
        recording = self.get_object()
        safe = os.path.basename(filename)
        path = os.path.join(settings.MEDIA_ROOT, "screenshots", "recordings", str(recording.pk), safe)
        if not os.path.isfile(path):
            return Response({"error": "screenshot not found"}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(open(path, "rb"), content_type="image/png")

    @action(detail=True, methods=["post"], url_path="convert-to-pipeline")
    @audit_action(AuditAction.IMPORT, AuditResourceType.RECORDING)
    def convert_to_pipeline(self, request, pk=None):
        """将录制转换为 Pipeline

        如果录制已有 pipeline_json 则直接使用；否则从 recording_data 实时转换。
        """
        recording = self.get_object()

        # If pipeline_json already exists, use it directly
        if recording.pipeline_json and recording.pipeline_json.get("nodes"):
            pipeline = Pipeline.objects.create(
                user=request.user,
                name=f"{recording.name}_录制导入",
                description=f"从录制 {recording.id} 转换",
                graph_data=recording.pipeline_json,
                version=1,
            )
            return Response(PipelineSerializer(pipeline).data)

        # Otherwise, convert from recording_data on the fly
        if recording.recording_data and recording.recording_data.get("events"):
            from pipeline.recording_converter import convert_recording_to_pipeline

            pipeline_json = convert_recording_to_pipeline(
                recording.recording_data,
                pipeline_name=f"{recording.name}_录制导入",
            )
            if pipeline_json.get("nodes"):
                # Cache the converted pipeline_json for future use
                recording.pipeline_json = pipeline_json
                recording.save(update_fields=["pipeline_json"])
                pipeline = Pipeline.objects.create(
                    user=request.user,
                    name=f"{recording.name}_录制导入",
                    description=f"从录制 {recording.id} 转换",
                    graph_data=pipeline_json,
                    version=1,
                )
                return Response(PipelineSerializer(pipeline).data)

        return Response(
            {"error": "录制数据为空或无事件，无法转换"},
            status=400,
        )


class TaskChainExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    """TaskChainExecution 列表/详情 API (spec v3 §2.7.2 — window-centric).

    Read-only by design: TaskChainExecutions are created exclusively via
    ``POST /api/v2/pipeline/task-chains/{id}/execute/`` (which delegates to
    ``pipeline.services.create_chain_execution_and_dispatch``). Exposing
    direct create/update/delete would bypass chain validation and agent
    resolution, so they are intentionally not provided here.

    列表 GET  /api/v2/pipeline/task-chain-executions/
    详情 GET  /api/v2/pipeline/task-chain-executions/{id}/  (含嵌套 node_executions)

    Filters: chain / status / triggered_by / device / game_account / agent_id
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "view"
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['chain', 'status', 'triggered_by', 'device', 'game_account', 'agent_id']
    search_fields = ['chain__name', 'agent_id', 'error_message']

    def get_queryset(self):
        """Return chain executions with related data prefetched.

        ``select_related`` covers the FK fields used by both the list and
        detail serializers (chain / current_node / triggered_by / device /
        game_account). ``prefetch_related`` pulls the nested node_executions
        so the detail endpoint's ``TaskChainExecutionDetailSerializer`` does
        not issue N+1 queries.
        """
        return (
            TaskChainExecution.objects
            .select_related('chain', 'current_node', 'current_node__task', 'triggered_by', 'device', 'game_account')
            .prefetch_related('node_executions')
            .all()
        )

    def get_serializer_class(self):
        """List uses the lightweight serializer; retrieve embeds node_executions."""
        if self.action == 'retrieve':
            from pipeline.serializers import TaskChainExecutionDetailSerializer
            return TaskChainExecutionDetailSerializer
        return TaskChainExecutionSerializer
