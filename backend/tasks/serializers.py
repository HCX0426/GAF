import contextlib

from django.db import transaction
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from accounts.models import GameAccount
from gamestate.serializers import GameProfileSerializer
from tasks.models import (
    CustomTask,
    ExecutionStep,
    MarketplaceItem,
    MarketplaceReview,
    ScheduledTask,
    Task,
    TaskDevice,
    TaskExecution,
    TaskFolder,
    TaskStep,
    TaskVersion,
)
from tasks.schema_types import (
    DeviceDetailSchema,
    GameAccountDetailSchema,
    ResourcePackDetailSchema,
)


class TaskStepSerializer(serializers.ModelSerializer):
    """任务步骤序列化器，记录每个步骤的详细状态。

    注意: error_code 字段在 ExecutionStep 模型上 (不在 TaskStep),
    通过 WS broadcast_execution_step_update signal 实时透传给前端。
    REST /steps/ 端点 (TaskStep) 原本不含 error_code — 前端 initial load
    只能拿到 error_message; 实时监控时 error_code 通过 WS 到达。
    Task 3.6 (P2-6) 的 error_code 透传路径: agent → protocol/services
    → ExecutionStep.error_code → signals.py → WS → 前端 StepProgressBar。

    Task 4.5 (P1-10, 2026-07-28): 历史回看场景 (用户刷新页面查看历史执行)
    不走 WS, 只走 REST /steps/ 端点, error_code 丢失。通过 SerializerMethodField
    从关联 ExecutionStep (按 execution + step_index 关联) 读取 error_code,
    让 REST 端点也返回 error_code, 前端历史回看时能展示多语言错误码 Tag。
    """

    # Task 4.5: 从 ExecutionStep 读取 error_code (TaskStep 模型本身无此字段).
    # 避免新增 migration: TaskStep 是遗留模型, 生产代码不创建 (仅测试/seed),
    # 实际生产数据走 ExecutionStep. 用 SerializerMethodField 关联读取.
    error_code = serializers.SerializerMethodField(read_only=True)
    # N192 (B1/B2): 从 ExecutionStep 读取 user_message (错误码映射后的用户友好文案).
    user_message = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TaskStep
        fields = [
            'id', 'execution', 'step_index', 'step_name', 'step_type',
            'status', 'result_data', 'error_message', 'error_code', 'user_message',
            'screenshot_path', 'retry_count', 'duration', 'started_at', 'completed_at',
        ]
        read_only_fields = ['id']

    def get_error_code(self, obj: TaskStep) -> str:
        """Task 4.5: 从关联 ExecutionStep 读取 error_code.

        按 (task_result=obj.execution, step_index=obj.step_index) 关联.
        查不到返回空串 (老数据 / 成功步骤 / agent 未上报 error_code).
        """
        try:
            es = ExecutionStep.objects.filter(
                task_result=obj.execution,
                step_index=obj.step_index,
            ).only('error_code').first()
            return es.error_code if es else ''
        except Exception:
            return ''

    def get_user_message(self, obj: TaskStep) -> str:
        """N192: 从关联 ExecutionStep 读取 user_message (错误码映射后的用户文案).

        按 (task_result=obj.execution, step_index=obj.step_index) 关联.
        查不到返回空串 (老数据 / 成功步骤 / 未映射).
        """
        try:
            es = ExecutionStep.objects.filter(
                task_result=obj.execution,
                step_index=obj.step_index,
            ).only('user_message').first()
            return es.user_message if es else ''
        except Exception:
            return ''


class TaskExecutionSerializer(serializers.ModelSerializer):
    """任务执行记录序列化器，包含嵌套的步骤信息。

    Window-centric v3 §2.10: exposes ``chain_execution`` / ``chain_node`` /
    ``game_account`` / ``device`` FKs so the frontend can render the
    runtime binding (which window + which account ran this task) without
    a second round-trip. Display strings are included for the same reason.
    """

    steps = TaskStepSerializer(many=True, read_only=True)
    # The Channels group name used for routing screenshot stream control
    # messages is `agent_{agent_id}` where agent_id is the Agent.agent_id
    # string (e.g. "td010-repro-agent"), NOT the DB primary key. Expose it
    # here so the frontend ExecutionMonitorPanel can subscribe to the
    # correct agent group via useScreenshotStream.startStream(agentId).
    # Without this, the panel would pass the DB id (e.g. "4") and the
    # backend would route the request_screenshot_stream message to
    # group "agent_4" — which no agent ever joined — so the stream
    # would stay in "等待截图数据" forever.
    agent_identifier = serializers.SerializerMethodField(read_only=True)
    # v3 §2.10: runtime binding display fields (read-only)
    device_name = serializers.SerializerMethodField(read_only=True)
    game_account_username = serializers.CharField(
        source='game_account.username', read_only=True, default='',
    )
    chain_execution_status = serializers.CharField(
        source='chain_execution.status', read_only=True, default='',
    )
    # TD-407 (2026-08-27): display names for the executions list — previously
    # the list showed raw FK ids for task/agent, making rows indistinguishable.
    task_name = serializers.CharField(source='task.name', read_only=True, default='')
    agent_hostname = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TaskExecution
        fields = [
            'id', 'task', 'pipeline', 'agent', 'agent_identifier', 'triggered_by', 'status', 'log',
            'result_data', 'error_message', 'error_code', 'cancel_reason', 'screenshot_path',
            'started_at', 'completed_at', 'duration', 'created_at', 'steps',
            # v3 §2.10: window-centric runtime binding
            'chain_execution', 'chain_execution_status', 'chain_node',
            'game_account', 'game_account_username',
            'device', 'device_name',
            # TD-407: display names
            'task_name', 'agent_hostname',
        ]
        read_only_fields = ['id', 'triggered_by', 'created_at']

    @extend_schema_field(OpenApiTypes.STR)
    def get_agent_hostname(self, obj):
        """TD-407: agent display hostname for the executions list."""
        agent = getattr(obj, 'agent', None)
        if agent is not None:
            return agent.hostname or agent.agent_id
        return ''

    @extend_schema_field(OpenApiTypes.STR)
    def get_agent_identifier(self, obj):
        """Return the Agent.agent_id string for screenshot stream routing."""
        if obj.agent_id is None:
            return None
        # obj.agent_id here is the FK value (Agent.id DB pk). We need the
        # related instance's agent_id string. Use the cached related instance
        # if available; fall back to a cheap query otherwise.
        agent = getattr(obj, 'agent', None)
        if agent is not None:
            return agent.agent_id
        from agents.models import Agent
        return Agent.objects.filter(pk=obj.agent_id).values_list('agent_id', flat=True).first()

    @extend_schema_field(OpenApiTypes.STR)
    def get_device_name(self, obj):
        """Return a human-readable device label for runtime binding display.

        Prefers user-defined Device.name, falls back to adb_serial for
        Android emulators, and returns '' when no device is bound.
        """
        device = getattr(obj, 'device', None)
        if device is None:
            return ''
        return device.name or device.adb_serial or ''


class TaskSerializer(serializers.ModelSerializer):
    """Task 序列化器 — Phase 5 全字段版本"""

    device_count = serializers.SerializerMethodField(read_only=True)
    account_count = serializers.SerializerMethodField(read_only=True)
    name = serializers.CharField(max_length=200, help_text='任务名称，最大200字符')
    game_accounts = serializers.PrimaryKeyRelatedField(
        queryset=GameAccount.objects.all(),
        many=True,
        required=False,
        write_only=True,
    )
    game_account_details = serializers.SerializerMethodField(read_only=True)
    device_details = serializers.SerializerMethodField(read_only=True)
    devices = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        write_only=True,
        help_text='设备ID列表',
    )
    # R37-P1: nested GameProfile summary so the frontend can render Tag
    # columns without extra round-trips. With fields='__all__' explicitly
    # declared SerializerMethodFields are auto-included.
    game_profile_detail = serializers.SerializerMethodField(read_only=True)
    # N197-8: nested ResourcePack summary for the frontend to display pack name
    # without a second round-trip. The FK field `resource_pack` is auto-included
    # by fields='__all__' (writable, accepts resource_pack_id).
    resource_pack_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Task
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        game_accounts = validated_data.pop('game_accounts', [])
        devices = validated_data.pop('devices', [])
        # N197-8: resource_pack FK is now auto-handled by DRF via fields='__all__',
        # no need to manually pop resource_pack_id.
        # spec-58-A (TD-296): wrap multi-step DB write (parent + M2M set +
        # TaskDevice bulk create) in a transaction so a partial failure
        # cannot leave orphaned M2M rows or TaskDevice rows.
        with transaction.atomic():
            instance = super().create(validated_data)
            if game_accounts:
                instance.game_accounts.set(game_accounts)
            if devices:
                from tasks.models import TaskDevice
                TaskDevice.objects.filter(task=instance).delete()
                for device_id in devices:
                    TaskDevice.objects.create(task=instance, device_id=device_id)
        return instance

    def update(self, instance, validated_data):
        game_accounts = validated_data.pop('game_accounts', None)
        devices = validated_data.pop('devices', None)
        # spec-58-A (TD-296): wrap multi-step DB write in a transaction so
        # a partial failure cannot leave inconsistent M2M / TaskDevice state.
        with transaction.atomic():
            result = super().update(instance, validated_data)
            if game_accounts is not None:
                result.game_accounts.set(game_accounts)
            if devices is not None:
                from tasks.models import TaskDevice
                TaskDevice.objects.filter(task=result).delete()
                for device_id in devices:
                    TaskDevice.objects.create(task=result, device_id=device_id)
        return result

    @extend_schema_field(OpenApiTypes.INT)
    def get_device_count(self, obj):
        try:
            return obj.device_mappings.count()
        except Exception:
            return 0

    @extend_schema_field(OpenApiTypes.INT)
    def get_account_count(self, obj):
        return obj.game_accounts.count()

    @extend_schema_field(GameAccountDetailSchema(many=True))
    def get_game_account_details(self, obj):
        accounts = []
        for acc in obj.game_accounts.all():
            accounts.append({
                'id': acc.id,
                # P3: GameAccount.game_name 已 drop; 游戏名恒取自 game_profile.
                'game_name': acc.game_profile.game_name if acc.game_profile_id else '',
                'username': acc.username,
            })
        return accounts

    @extend_schema_field(DeviceDetailSchema(many=True))
    def get_device_details(self, obj):
        devices = []
        for mapping in obj.device_mappings.all():
            with contextlib.suppress(Exception):
                devices.append({
                    'id': mapping.device.id,
                    'name': mapping.device.name or mapping.device.adb_serial,
                })
        return devices

    @extend_schema_field(GameProfileSerializer)
    def get_game_profile_detail(self, obj):
        """Return nested GameProfile summary for frontend Tag rendering.

        R37-P3 Stage 7: GameProfileSerializer migrated to gamestate.serializers.

        spec-29f (TD-266 Phase 2a): top-level import is safe — gamestate
        only depends on gamestate.models (no circular import).
        """
        if not obj.game_profile_id:
            return None
        return GameProfileSerializer(obj.game_profile).data

    @extend_schema_field(ResourcePackDetailSchema)
    def get_resource_pack_detail(self, obj):
        """Return nested ResourcePack summary for frontend display.

        N197-8: The frontend task list renders the resource pack name as a Tag
        without a second round-trip to /resources/resource-packs/.
        """
        if not obj.resource_pack_id:
            return None
        from resources.serializers import ResourcePackSerializer
        return ResourcePackSerializer(obj.resource_pack).data


class CustomTaskSerializer(serializers.ModelSerializer):
    """自定义任务序列化器。"""

    class Meta:
        model = CustomTask
        fields = [
            'id', 'name', 'description', 'task_definition', 'params_config',
            'json_schema', 'is_enabled', 'created_by',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class ScheduledTaskSerializer(serializers.ModelSerializer):
    """定时任务序列化器。"""

    class Meta:
        model = ScheduledTask
        fields = [
            'id', 'task', 'custom_task', 'schedule_type', 'cron_expression',
            'scheduled_time', 'is_enabled', 'last_executed_at',
            'created_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'last_executed_at', 'created_at', 'updated_at']


class TaskExecuteSerializer(serializers.Serializer):
    """任务执行序列化器，指定执行 Agent 和可选参数。"""

    agent_id = serializers.CharField(required=False, allow_null=True)
    params = serializers.JSONField(required=False, default=dict)
    # N197: 资源包测试端点通过此字段传入 Task ID
    task_id = serializers.IntegerField(required=False, allow_null=True)
    # Window-centric (R37): TaskExecution.device 是单 FK, 一次执行绑定一台设备。
    # 前端可显式指定; 省略时由 execute_task 从 task.device_mappings 取第一个作为默认。
    device_id = serializers.IntegerField(required=False, allow_null=True)
    # N194 fix: TaskExecution.game_account 必须绑定, 否则 dispatch_task 无法
    # 派发 resource_pack 给 agent. 前端可显式指定; 省略时由 execute_task
    # 从 task.game_accounts 取第一个作为默认.
    game_account_id = serializers.IntegerField(required=False, allow_null=True)
    # N197: 直接指定资源包 ID, 用于「已登录, 直接测试资源包」场景.
    # 传入时覆盖 game_account_id 携带的 resource_pack; 若 game_account_id 未传,
    # 自动创建默认账号绑定此资源包.
    resource_pack_id = serializers.IntegerField(required=False, allow_null=True)


# TD-061 Plan B Stage 2: PipelineSerializer / PipelineListSerializer /
# PipelineSnapshotSerializer / PipelineValidateSerializer moved to
# pipeline.serializers. tasks app no longer owns Pipeline model.


class MarketplaceItemSerializer(serializers.ModelSerializer):
    """市场条目序列化器"""

    publisher_name = serializers.CharField(source='publisher.username', read_only=True)
    pipeline_name = serializers.CharField(source='pipeline.name', read_only=True, allow_null=True)
    # P7: 游戏维度唯一权威 = game_profile; 展示名恒来自 profile, 无 profile = '通用'.
    game_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MarketplaceItem
        fields = [
            'id', 'publisher', 'publisher_name', 'pipeline', 'pipeline_name',
            'game_profile', 'game_name', 'title', 'description', 'screenshot_urls', 'tags',
            'status', 'download_count', 'rating_avg', 'rating_count',
            'version', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'publisher', 'download_count', 'rating_avg',
            'rating_count', 'created_at', 'updated_at',
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_game_name(self, obj):
        return obj.game_profile.game_name if obj.game_profile_id else '通用'


class MarketplaceReviewSerializer(serializers.ModelSerializer):
    """市场评价序列化器"""

    user_name = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = MarketplaceReview
        fields = ['id', 'item', 'user', 'user_name', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']


# P-008: RecordingSerializer / RecordingListSerializer migrated to
# pipeline.serializers. tasks app no longer owns Recording model.


class TaskDeviceSerializer(serializers.ModelSerializer):
    """Task ↔ Device mapping serializer"""

    device_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TaskDevice
        fields = ['id', 'task', 'device', 'device_name', 'created_at']
        read_only_fields = ['id', 'created_at']

    @extend_schema_field(OpenApiTypes.STR)
    def get_device_name(self, obj):
        try:
            return obj.device.name or obj.device.adb_serial
        except Exception:
            return ''


class BatchDeviceBindingSerializer(serializers.Serializer):
    """批量设备绑定请求序列化器"""

    mappings = serializers.ListField(child=serializers.DictField())

    def validate_mappings(self, value):
        if not value:
            raise serializers.ValidationError('至少需要1条映射')
        device_ids = []
        for item in value:
            did = item.get('device_id')
            if did is None:
                raise serializers.ValidationError('每条映射必须包含 device_id')
            if did in device_ids:
                raise serializers.ValidationError(f'设备 {did} 重复')
            device_ids.append(did)
        return value


class AccountBindingSerializer(serializers.Serializer):
    """账户绑定请求序列化器"""

    account_ids = serializers.ListField(child=serializers.IntegerField())
    rotation_rule_id = serializers.IntegerField(required=False, allow_null=True, default=None)


class ParallelConfigSerializer(serializers.Serializer):
    """并行执行配置请求序列化器"""

    parallel_mode = serializers.BooleanField(required=False, default=False)
    max_concurrency = serializers.IntegerField(required=False, default=1, min_value=1)


class BulkActionSerializer(serializers.Serializer):
    """批量操作请求序列化器"""

    action = serializers.ChoiceField(choices=['enable', 'disable', 'delete', 'export'])
    task_ids = serializers.ListField(child=serializers.IntegerField(), min_length=1)


class TaskFolderSerializer(serializers.ModelSerializer):
    """任务文件夹序列化器"""

    task_count = serializers.SerializerMethodField(read_only=True)
    children = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TaskFolder
        fields = ['id', 'owner', 'name', 'slug', 'parent', 'children', 'task_count', 'created_at']
        read_only_fields = ['id', 'owner', 'created_at']

    @extend_schema_field(OpenApiTypes.INT)
    def get_task_count(self, obj):
        return obj.tasks.count()

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_children(self, obj):
        children = obj.children.all()
        if children.exists():
            return TaskFolderTreeSerializer(children, many=True).data
        return []


class TaskVersionSerializer(serializers.ModelSerializer):
    """Task version serializer for version history CRUD operations."""

    created_by_username = serializers.SerializerMethodField(read_only=True)
    snapshot_summary = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TaskVersion
        fields = [
            'id', 'task', 'version_number', 'snapshot', 'change_description',
            'created_by', 'created_by_username', 'created_at', 'snapshot_summary',
        ]
        read_only_fields = ['id', 'created_at', 'created_by', 'created_by_username']

    def get_created_by_username(self, obj):
        """Return creator username."""
        return obj.created_by.username if obj.created_by else None

    def get_snapshot_summary(self, obj):
        """Return a brief summary of the snapshot (first 200 chars of name/description)."""
        if isinstance(obj.snapshot, dict):
            name = obj.snapshot.get('name', '')
            desc = obj.snapshot.get('description', '')
            return f'{name}: {desc[:150]}...' if len(desc) > 150 else f'{name}: {desc}'
        return str(obj.snapshot)[:200] if obj.snapshot else None


class TaskVersionCreateSerializer(serializers.Serializer):
    """Serializer for creating a new task version snapshot."""

    change_description = serializers.CharField(
        required=False,
        allow_blank=True,
        default='',
        max_length=500,
        help_text='Description of changes in this version',
    )


class TaskFolderTreeSerializer(serializers.ModelSerializer):
    """文件夹树序列化器（简化版递归）"""

    children = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TaskFolder
        fields = ['id', 'name', 'slug', 'children']

    def get_children(self, obj):
        children = obj.children.all()
        if children.exists():
            return TaskFolderTreeSerializer(children, many=True).data
        return []
