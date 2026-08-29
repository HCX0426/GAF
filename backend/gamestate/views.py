"""游戏状态追踪 REST API — 游戏档案 + 规则管理 + 快照查询。"""

from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from gaf_core.audit_constants import AuditAction, AuditResourceType
from gaf_core.mixins import AuditMixin, audit_action, build_diff_details
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import RoleBasedPermission
from gamestate.models import (
    GameProfile,
    GameStateRule,
    GameStateSnapshot,
)


class GameProfileViewSet(AuditMixin, viewsets.ModelViewSet):
    """游戏档案 API，标准 CRUD。

    R37-P3 Stage 7: migrated from tasks app (TD-039).
    URL: /api/v2/gamestate/game-profiles/ (migrated from /api/v2/tasks/game-profiles/)

    Window-centric Stage 2: 5 detail sub-resource endpoints
    (tasks/task_chains/devices/accounts/resource_packs) return the
    resources bound to a given profile.
    """

    queryset = GameProfile.objects.all()
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "view"
    filterset_fields = ["game_name", "ocr_language", "resolution_strategy"]
    search_fields = ["game_name"]
    audit_resource_type = AuditResourceType.GAME_PROFILE

    def get_serializer_class(self):
        from gamestate.serializers import GameProfileSerializer
        return GameProfileSerializer

    def get_permissions(self):
        # default_task_chain mutates GameProfile + TaskChain state -> manage.
        # dispatch_routine triggers real TaskChain executions -> execute.
        if self.action in ('create', 'update', 'partial_update', 'destroy',
                           'default_task_chain',
                           'bind_task', 'unbind_task',
                           'bind_task_chain', 'unbind_task_chain',
                           'bind_account', 'unbind_account'):
            self.required_permission = 'manage'
        elif self.action == 'dispatch_routine':
            self.required_permission = 'execute'
        else:
            self.required_permission = 'view'
        return super().get_permissions()

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build before/after diff for audit log.

        ``known_popups`` / ``screenshot_methods`` are large JSON lists
        of internal template names; redact to avoid noise. ``routine_path``
        is an absolute filesystem path on the backend host — treat as
        sensitive. ``ui_reference_resolution`` is small and safe.
        """
        snapshot_keys = (
            "game_name",
            "ocr_language",
            "resolution_strategy",
            "default_screenshot_method",
            "default_input_method",
            "default_control_mode",
        )
        sensitive = {
            "known_popups",
            "screenshot_methods",
            "routine_path",
            "secret",
            "token",
        }

        def _snapshot(obj):
            data = {k: getattr(obj, k, None) for k in snapshot_keys}
            # default_task_chain is a FK to TaskChain; record only the id
            # so auditors can see when the default routine changes.
            data["default_task_chain_id"] = getattr(obj, "default_task_chain_id", None)
            return data

        if action == AuditAction.CREATE:
            return build_diff_details(
                before=None,
                after=_snapshot(instance),
                sensitive_extra=sensitive,
            )
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before=_snapshot(old_instance),
                after=_snapshot(instance),
                sensitive_extra=sensitive,
            )
        if action == AuditAction.DELETE:
            return build_diff_details(
                before=_snapshot(instance),
                after=None,
                sensitive_extra=sensitive,
            )
        return {}

    @action(detail=True, methods=['get'])
    def tasks(self, request, *args, **kwargs):
        # Lazy imports avoid circular imports between gamestate and tasks.
        from tasks.models import Task
        from tasks.serializers import TaskSerializer

        profile = self.get_object()
        qs = Task.objects.filter(game_profile=profile).select_related('game_profile').prefetch_related('device_mappings', 'game_accounts')
        page = self.paginate_queryset(qs)
        serializer = TaskSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=['get'])
    def task_chains(self, request, *args, **kwargs):
        from pipeline.models import TaskChain
        from pipeline.serializers import TaskChainSerializer

        profile = self.get_object()
        qs = TaskChain.objects.filter(game_profile=profile).select_related('created_by').prefetch_related('chain_nodes')
        page = self.paginate_queryset(qs)
        serializer = TaskChainSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=['get'])
    def devices(self, request, *args, **kwargs):
        from agents.models import Device
        from agents.serializers import DeviceSerializer

        profile = self.get_object()
        qs = Device.objects.filter(game_profile=profile).select_related('agent', 'locked_by', 'game_profile')
        page = self.paginate_queryset(qs)
        serializer = DeviceSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=['get'])
    def accounts(self, request, *args, **kwargs):
        from accounts.models import GameAccount
        from accounts.serializers import GameAccountSerializer

        profile = self.get_object()
        qs = GameAccount.objects.filter(game_profile=profile).select_related('group', 'resource_pack')
        page = self.paginate_queryset(qs)
        serializer = GameAccountSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=['get'])
    def resource_packs(self, request, *args, **kwargs):
        from resources.models import ResourcePack
        from resources.serializers import ResourcePackSerializer

        profile = self.get_object()
        # Resource packs bound to this profile via its accounts.
        pack_ids = profile.game_accounts.values_list('resource_pack_id', flat=True)
        qs = ResourcePack.objects.filter(id__in=pack_ids).select_related('game_profile').prefetch_related('custom_tasks', 'scheduled_tasks', 'templates').distinct()
        page = self.paginate_queryset(qs)
        serializer = ResourcePackSerializer(page, many=True, context={'request': request})
        return self.get_paginated_response(serializer.data)

    # ---- bind/unbind sub-resources (spec v3 §2.5.2) -------------------
    # Allow the GameProfile detail page to attach/detach existing child
    # resources (Task / TaskChain / GameAccount) without navigating to each
    # resource's own page. ResourcePack binding stays on GameAccount per
    # architecture §3.2 (resource packs are bound to accounts, not profiles,
    # so cross-server accounts can use different packs).

    def _bind_child(self, request, profile, model_cls, pk_field, pk_name, serializer_cls):
        """Shared bind logic: attach an existing child resource to this profile.

        Validates:
          - the target resource exists
          - it is not already bound to another GameProfile
        On success sets its game_profile FK to this profile.
        """
        resource_id = request.data.get(pk_name)
        if not resource_id:
            return Response(
                {'error': f'{pk_name} is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            obj = model_cls.objects.get(**{pk_field: resource_id})
        except model_cls.DoesNotExist:
            return Response(
                {'error': f'{model_cls.__name__} {resource_id} not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if obj.game_profile_id is not None and obj.game_profile_id != profile.pk:
            return Response(
                {
                    'error': (
                        f'{model_cls.__name__} [{obj}] is already bound to '
                        f'another GameProfile (id={obj.game_profile_id})'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.game_profile = profile
        obj.save(update_fields=['game_profile'])
        return Response(serializer_cls(obj, context={'request': request}).data)

    def _unbind_child(self, request, profile, model_cls, pk_field, pk_name, serializer_cls):
        """Shared unbind logic: detach a child resource from this profile."""
        resource_id = request.data.get(pk_name)
        if not resource_id:
            return Response(
                {'error': f'{pk_name} is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            obj = model_cls.objects.get(**{pk_field: resource_id})
        except model_cls.DoesNotExist:
            return Response(
                {'error': f'{model_cls.__name__} {resource_id} not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if obj.game_profile_id != profile.pk:
            return Response(
                {'error': f'{model_cls.__name__} [{obj}] is not bound to this GameProfile'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.game_profile = None
        obj.save(update_fields=['game_profile'])
        return Response({'status': 'ok', 'message': f'{model_cls.__name__} [{obj}] unbound'})

    @action(detail=True, methods=['post'], url_path='bind-task')
    @audit_action(AuditAction.UPDATE, AuditResourceType.GAME_PROFILE)
    def bind_task(self, request, pk=None):
        from tasks.models import Task
        from tasks.serializers import TaskSerializer
        return self._bind_child(request, self.get_object(), Task, 'id', 'task_id', TaskSerializer)

    @action(detail=True, methods=['post'], url_path='unbind-task')
    @audit_action(AuditAction.UPDATE, AuditResourceType.GAME_PROFILE)
    def unbind_task(self, request, pk=None):
        from tasks.models import Task
        from tasks.serializers import TaskSerializer
        return self._unbind_child(request, self.get_object(), Task, 'id', 'task_id', TaskSerializer)

    @action(detail=True, methods=['post'], url_path='bind-task-chain')
    @audit_action(AuditAction.UPDATE, AuditResourceType.GAME_PROFILE)
    def bind_task_chain(self, request, pk=None):
        from pipeline.models import TaskChain
        from pipeline.serializers import TaskChainSerializer
        return self._bind_child(request, self.get_object(), TaskChain, 'id', 'task_chain_id', TaskChainSerializer)

    @action(detail=True, methods=['post'], url_path='unbind-task-chain')
    @audit_action(AuditAction.UPDATE, AuditResourceType.GAME_PROFILE)
    def unbind_task_chain(self, request, pk=None):
        from pipeline.models import TaskChain
        from pipeline.serializers import TaskChainSerializer
        return self._unbind_child(request, self.get_object(), TaskChain, 'id', 'task_chain_id', TaskChainSerializer)

    @action(detail=True, methods=['post'], url_path='bind-account')
    @audit_action(AuditAction.UPDATE, AuditResourceType.GAME_PROFILE)
    def bind_account(self, request, pk=None):
        from accounts.models import GameAccount
        from accounts.serializers import GameAccountSerializer
        return self._bind_child(request, self.get_object(), GameAccount, 'id', 'account_id', GameAccountSerializer)

    @action(detail=True, methods=['post'], url_path='unbind-account')
    @audit_action(AuditAction.UPDATE, AuditResourceType.GAME_PROFILE)
    def unbind_account(self, request, pk=None):
        from accounts.models import GameAccount
        from accounts.serializers import GameAccountSerializer
        return self._unbind_child(request, self.get_object(), GameAccount, 'id', 'account_id', GameAccountSerializer)

    # ---- v3 §2.7.2 window-centric routine management ------------------

    @action(detail=True, methods=['patch'], url_path='default-task-chain')
    @audit_action(AuditAction.UPDATE, AuditResourceType.GAME_PROFILE)
    def default_task_chain(self, request, pk=None):
        """Set the default TaskChain for this GameProfile (spec v3 §2.7.2).

        Atomically:
            1. Validate the target TaskChain belongs to this GameProfile
            2. Clear is_default on other chains under the same profile
            3. Set the target chain's is_default=True
            4. Sync GameProfile.default_task_chain to the target chain

        This is the profile-side mirror of
        ``POST /api/v2/pipeline/task-chains/{id}/set-default/``: both keep
        GameProfile.default_task_chain and TaskChain.is_default consistent.
        Exposed as a PATCH on the profile so the frontend GameProfiles page
        can update it without navigating to the pipeline app.

        Body: ``{"task_chain_id": 123}``
        """
        from pipeline.models import TaskChain

        profile = self.get_object()
        task_chain_id = request.data.get('task_chain_id')
        if not task_chain_id:
            return Response(
                {'error': 'task_chain_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            chain = TaskChain.objects.get(pk=task_chain_id)
        except TaskChain.DoesNotExist:
            return Response(
                {'error': f'TaskChain {task_chain_id} not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if chain.game_profile_id != profile.pk:
            return Response(
                {
                    'error': (
                        f'TaskChain [{chain.name}] does not belong to '
                        f'GameProfile [{profile.game_name}]'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Clear other is_default=True chains under the same GameProfile.
            TaskChain.objects.filter(
                game_profile=profile,
                is_default=True,
            ).exclude(pk=chain.pk).update(is_default=False)

            chain.is_default = True
            chain.save(update_fields=['is_default'])

            profile.default_task_chain = chain
            profile.save(update_fields=['default_task_chain'])

        return Response({
            'status': 'ok',
            'game_profile_id': profile.pk,
            'game_name': profile.game_name,
            'default_task_chain_id': chain.pk,
            'default_task_chain_name': chain.name,
            'is_default': True,
            'message': (
                f'TaskChain [{chain.name}] set as default routine for '
                f'GameProfile [{profile.game_name}]'
            ),
        })

    @action(detail=True, methods=['post'], url_path='dispatch-routine')
    @audit_action(AuditAction.EXECUTE, AuditResourceType.GAME_PROFILE)
    def dispatch_routine(self, request, pk=None):
        """Dispatch the default routine to all online devices under this
        GameProfile (spec v3 §2.7.2 + §2.4.1).

        For every Device bound to this GameProfile whose Agent is online,
        create a TaskChainExecution (with device + device.game_account
        runtime binding) and dispatch the first node.

        Devices without an online Agent (or without a bound Agent) are
        skipped and reported in the response so the operator can see which
        windows were not dispatched.

        Body (optional): ``{"agent_id": "agent-xxx"}`` — force all
        dispatches through one specific Agent. When omitted, each device
        uses its own ``device.agent``.

        Response:
            ``{
                "status": "dispatched",
                "dispatched_count": N,
                "skipped_count": M,
                "failed_count": K,
                "dispatched": [{...chain_execution summary...}],
                "skipped": [{...device + reason...}],
                "failed": [{...device + error...}]
            }``
        """
        from pipeline.services import ChainDispatchError, create_chain_execution_and_dispatch

        from agents.models import Agent

        profile = self.get_object()
        chain = profile.default_task_chain
        if chain is None:
            return Response(
                {
                    'error': (
                        f'GameProfile [{profile.game_name}] has no default_task_chain; '
                        f'call PATCH default-task-chain first'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not chain.is_enabled:
            return Response(
                {'error': f'Default routine [{chain.name}] is disabled'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Optional override: force all dispatches through one Agent.
        forced_agent_id = request.data.get('agent_id')
        online_statuses = (Agent.Status.ONLINE, Agent.Status.IDLE)

        devices = (
            profile.devices
            .select_related('agent', 'game_account')
            .all()
        )

        dispatched = []
        skipped = []
        failed = []
        for device in devices:
            # Resolve the agent for this device.
            if forced_agent_id:
                agent_id = forced_agent_id
            else:
                agent = device.agent
                if agent is None:
                    skipped.append({
                        'device_id': device.pk,
                        'device_name': device.name or device.adb_serial,
                        'reason': 'no_agent_bound',
                    })
                    continue
                if agent.status not in online_statuses:
                    skipped.append({
                        'device_id': device.pk,
                        'device_name': device.name or device.adb_serial,
                        'reason': f'agent_offline (status={agent.status})',
                    })
                    continue
                agent_id = agent.agent_id

            try:
                chain_exec = create_chain_execution_and_dispatch(
                    chain_id=chain.id,
                    agent_id=agent_id,
                    device_id=device.pk,
                    game_account_id=device.game_account_id,
                    triggered_by=request.user,
                )
            except ChainDispatchError as exc:
                failed.append({
                    'device_id': device.pk,
                    'device_name': device.name or device.adb_serial,
                    'error': str(exc),
                })
                continue

            dispatched.append({
                'chain_execution_id': chain_exec.pk,
                'device_id': device.pk,
                'device_name': device.name or device.adb_serial,
                'agent_id': agent_id,
                'game_account_id': device.game_account_id,
                'status': chain_exec.status,
            })

        return Response({
            'status': 'dispatched',
            'dispatched_count': len(dispatched),
            'skipped_count': len(skipped),
            'failed_count': len(failed),
            'dispatched': dispatched,
            'skipped': skipped,
            'failed': failed,
            'game_profile_id': profile.pk,
            'default_task_chain_id': chain.pk,
            'default_task_chain_name': chain.name,
        })


class GameStateRuleViewSet(AuditMixin, viewsets.ModelViewSet):
    """游戏状态规则 CRUD。"""

    queryset = GameStateRule.objects.all()
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['game_profile', 'tracker_type', 'is_active']
    search_fields = ['name', 'game_profile__game_name']
    audit_resource_type = AuditResourceType.GAME_STATE_RULE

    def get_serializer_class(self):
        from gamestate.serializers import GameStateRuleSerializer
        return GameStateRuleSerializer

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            self.required_permission = 'manage'
        else:
            self.required_permission = 'view'
        return super().get_permissions()

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build before/after diff for audit log.

        ``ocr_region`` / ``ocr_regex`` / ``trigger_action`` define the
        detection logic and may include sensitive operational config
        (e.g. regex patterns that match internal state machine values).
        Treat as sensitive to avoid leaking detection logic to anyone
        reading AuditLog rows later.
        """
        snapshot_keys = ("name", "game_profile", "tracker_type", "is_active", "threshold")
        sensitive = {"ocr_region", "ocr_regex", "trigger_action", "secret", "token"}
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


class GameStateSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    """游戏状态快照查询。"""

    queryset = GameStateSnapshot.objects.select_related('rule').all()
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['rule', 'rule__game_profile', 'triggered']

    def get_serializer_class(self):
        from gamestate.serializers import GameStateSnapshotSerializer
        return GameStateSnapshotSerializer
