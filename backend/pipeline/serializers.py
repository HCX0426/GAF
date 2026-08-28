
import jsonschema
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from pipeline.models import Pipeline, PipelineSnapshot, Recording, TaskChain, TaskChainExecution, TaskChainNode
from pipeline.schema import PIPELINE_GRAPH_SCHEMA


class PipelineSnapshotSerializer(serializers.ModelSerializer):
    """"PipelineSnapshot 序列化器。"""

    class Meta:
        model = PipelineSnapshot
        fields = ['id', 'version', 'graph_data', 'change_summary', 'created_at']
        read_only_fields = ['id', 'created_at']


class PipelineListSerializer(serializers.ModelSerializer):
    """Pipeline 列表序列化器（不含 graph_data 详情）。"""

    class Meta:
        model = Pipeline
        fields = ['id', 'name', 'description', 'version', 'is_template',
                   'estimated_duration_ms', 'user', 'created_at', 'updated_at']
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class PipelineSerializer(serializers.ModelSerializer):
    """Pipeline 详情序列化器（含 graph_data）。"""

    class Meta:
        model = Pipeline
        fields = ['id', 'name', 'description', 'graph_data', 'version',
                   'is_template', 'estimated_duration_ms', 'user',
                   'created_at', 'updated_at']
        read_only_fields = ['id', 'version', 'user', 'created_at', 'updated_at']

    def validate_graph_data(self, value: dict) -> dict:
        """执行 JSON Schema 结构校验 (支持 canvas 和 nested 两种 schema)."""
        try:
            jsonschema.validate(instance=value, schema=PIPELINE_GRAPH_SCHEMA)
        except jsonschema.ValidationError as e:
            path = '.'.join(str(p) for p in e.absolute_path) or '(root)'
            raise serializers.ValidationError(
                f'graph_data 校验失败 at {path}: {e.message}'
            ) from e
        return value


class TaskChainSerializer(serializers.ModelSerializer):
    """任务链序列化器，管理 DAG 任务链的 CRUD（R37-P3 Stage 7: 从 tasks 迁入）。"""

    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    node_count = serializers.SerializerMethodField()

    class Meta:
        model = TaskChain
        fields = [
            'id', 'name', 'description', 'dag_data', 'is_enabled',
            'game_profile', 'is_default',
            'created_by', 'created_by_username', 'node_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    @extend_schema_field(OpenApiTypes.INT)
    def get_node_count(self, obj):
        return obj.chain_nodes.count()

    def create(self, validated_data):
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class TaskChainNodeSerializer(serializers.ModelSerializer):
    """任务链节点序列化器（R37-P3 Stage 7: 从 tasks 迁入; TD-110 加 pipeline 字段）。"""

    task_name = serializers.CharField(source='task.name', read_only=True)
    pipeline_name = serializers.CharField(source='pipeline.name', read_only=True)
    parent_task_name = serializers.CharField(source='parent.task.name', read_only=True)
    parent_pipeline_name = serializers.CharField(source='parent.pipeline.name', read_only=True)

    class Meta:
        model = TaskChainNode
        fields = [
            'id', 'chain', 'node_type',
            'task', 'task_name',
            'pipeline', 'pipeline_name',
            'parent', 'parent_task_name', 'parent_pipeline_name',
            'condition', 'order',
        ]
        read_only_fields = ['id']


class TaskChainExecutionSerializer(serializers.ModelSerializer):
    """任务链执行记录序列化器 (spec 阶段 5 — TD-096 + v3 §2.10)."""

    chain_name = serializers.CharField(source='chain.name', read_only=True)
    current_node_order = serializers.SerializerMethodField()
    node_execution_count = serializers.SerializerMethodField()
    triggered_by_username = serializers.CharField(source='triggered_by.username', read_only=True)
    # v3: device + game_account display fields (read-only)
    device_name = serializers.CharField(source='device.name', read_only=True)
    game_account_username = serializers.CharField(source='game_account.username', read_only=True)

    class Meta:
        model = TaskChainExecution
        fields = [
            'id', 'chain', 'chain_name', 'current_node', 'current_node_order',
            'triggered_by', 'triggered_by_username', 'agent_id',
            'device', 'device_name',
            'game_account', 'game_account_username',
            'status', 'started_at', 'completed_at', 'error_message',
            # N192: 链级错误码, 从失败节点 TaskExecution.error_code 传播
            'error_code',
            'node_execution_count',
        ]
        read_only_fields = ['id', 'started_at', 'completed_at']

    @extend_schema_field(OpenApiTypes.INT)
    def get_current_node_order(self, obj):
        return obj.current_node.order if obj.current_node else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_node_execution_count(self, obj):
        return obj.node_executions.count()


class TaskChainExecutionDetailSerializer(TaskChainExecutionSerializer):
    """TaskChainExecution 详情序列化器 (spec §2.7.2).

    与列表版差异: 嵌套 ``node_executions`` 数组, 让前端 retrieve 端点
    一次拿到关联的 TaskExecution 列表 (含 status / device / game_account
    runtime binding), 避免列表页 N+1 查询。

    Lazy import TaskExecutionSerializer 避免 pipeline <-> tasks 循环导入。
    """

    node_executions = serializers.SerializerMethodField()

    class Meta(TaskChainExecutionSerializer.Meta):
        fields = TaskChainExecutionSerializer.Meta.fields + ['node_executions']

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_node_executions(self, obj):
        from tasks.serializers import TaskExecutionSerializer

        # Prefetched by ViewSet's get_queryset (select_related + prefetch_related)
        return TaskExecutionSerializer(obj.node_executions.all(), many=True).data


class RecordingSerializer(serializers.ModelSerializer):
    """录制详情序列化器 (P-008: migrated from tasks app)."""

    class Meta:
        model = Recording
        fields = [
            'id', 'name', 'recording_data', 'pipeline_json', 'duration',
            'screenshot_count', 'resolution', 'created_at',
        ]
        read_only_fields = ['id', 'user', 'created_at']

    def create(self, validated_data):
        """创建录制时自动绑定当前用户"""
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class RecordingListSerializer(serializers.ModelSerializer):
    """录制列表序列化器 (P-008: migrated from tasks app)."""

    event_count = serializers.SerializerMethodField()

    class Meta:
        model = Recording
        fields = [
            'id', 'name', 'duration', 'event_count', 'screenshot_count',
            'resolution', 'created_at',
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.INT)
    def get_event_count(self, obj):
        """获取录制数据中的事件数量"""
        events = obj.recording_data.get('events', []) if isinstance(obj.recording_data, dict) else []
        return len(events)
