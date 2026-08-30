"""消息帧序列化/反序列化工具：DRF Serializer + Schema 校验。"""

import json
import logging
import uuid
from datetime import UTC, datetime

from rest_framework import serializers

from protocol.constants import MessageType

logger = logging.getLogger(__name__)


class MessageFrameSerializer(serializers.Serializer):
    """消息帧 DRF 序列化器，用于对消息帧结构进行 Schema 校验。"""

    trace_id = serializers.UUIDField(format="hex_verbose")
    type = serializers.ChoiceField(choices=MessageType.all_types())
    seq = serializers.IntegerField(min_value=1)
    timestamp = serializers.DateTimeField()
    payload = serializers.DictField(default=dict)
    sent_at = serializers.FloatField(required=False, allow_null=True)

    def validate(self, attrs):
        """额外 Schema 校验：禁止附加字段，字段类型必须匹配。"""
        allowed_fields = set(self.fields.keys())
        received_fields = set(self.initial_data.keys())
        extra_fields = received_fields - allowed_fields
        if extra_fields:
            raise serializers.ValidationError(
                {"_schema": f"不允许的附加字段: {', '.join(sorted(extra_fields))}"}
            )
        if not isinstance(attrs.get("payload"), dict):
            raise serializers.ValidationError({"payload": "payload 必须为 object 类型"})
        return attrs


def serialize_frame(msg_type, payload=None, trace_id=None, seq=1):
    """将消息内容序列化为标准 JSON 消息帧字符串。

    B3-1 (spec 2026-07-30-debug-directory-restructure) 断点②修复:
    ``trace_id=None`` 时优先从 ``current_trace_id`` ContextVar 取
    (HTTP 请求经由 ``TracingMiddleware`` 注入), ContextVar 也未设置时
    才回退到 ``uuid.uuid4()``. 这样 15 个调用点零改动即可让所有 WS 帧
    自动携带当前请求的 trace_id, 实现 HTTP → WS trace 全链路贯穿.

    优先级 (高 → 低):
    1. 显式传入的 ``trace_id`` 参数 (调用方明确指定时覆盖一切)
    2. ``current_trace_id`` ContextVar (HTTP 请求 scope 内)
    3. ``uuid.uuid4()`` 兜底 (CLI / 测试 / 无请求上下文)
    """
    if msg_type not in MessageType.all_types():
        raise ValueError(f"无效的消息类型: {msg_type}")
    # B3-1: 优先用显式参数, 其次 ContextVar, 最后 uuid 兜底.
    if trace_id is None:
        # Lazy import to avoid circular dependency at module load time
        # (tracing.context has no dependency on protocol, but importing
        # at module level would couple the two packages tighter than
        # necessary — F段 will归一化 the trace_id resolution into a
        # shared helper).
        from gaf_core.tracing.context import current_trace_id
        trace_id = current_trace_id.get()
    frame = {
        "trace_id": str(trace_id or uuid.uuid4()),
        "type": msg_type,
        "seq": seq,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "payload": payload or {},
    }
    return json.dumps(frame, ensure_ascii=False)


def deserialize_frame(raw_data):
    """将 JSON 字符串或 dict 反序列化为消息帧，执行 Schema + DRF 双重校验。"""
    if isinstance(raw_data, str):
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            logger.warning("消息帧 JSON 解析失败")
            raise
    elif isinstance(raw_data, dict):
        data = raw_data
    else:
        raise ValueError(f"不支持的数据类型: {type(raw_data)}")
    serializer = MessageFrameSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def build_error_frame(message, trace_id=None):
    """构建标准错误响应帧。"""
    return serialize_frame(
        msg_type=MessageType.AGENT_STATUS,
        payload={"status": "error", "message": message},
        trace_id=trace_id,
    )


class WorkerRegisterPayloadSerializer(serializers.Serializer):
    """Worker 注册消息负载校验器，校验 agent_id、能力声明、资源配额等字段。"""

    agent_id = serializers.CharField(max_length=64)
    hostname = serializers.CharField(max_length=255, required=False, default="")
    ip_address = serializers.IPAddressField(required=False, allow_null=True)
    os_info = serializers.CharField(max_length=255, required=False, default="")
    version = serializers.CharField(max_length=32, required=False, default="")
    capabilities = serializers.DictField(required=False, default=dict)
    resource_quota = serializers.DictField(required=False, default=dict)


class WorkerHeartbeatPayloadSerializer(serializers.Serializer):
    """Worker 心跳消息负载校验器，校验资源统计字段。"""

    agent_id = serializers.CharField(max_length=64, required=False)
    resource_stats = serializers.DictField(required=False, default=dict)
    status = serializers.ChoiceField(
        choices=["idle", "busy", "online"],
        required=False,
        default="idle",
    )


class TaskDispatchPayloadSerializer(serializers.Serializer):
    """任务分发消息负载校验器，校验执行ID、管道定义、选项等字段。"""

    execution_id = serializers.CharField(max_length=64)
    task_id = serializers.CharField(max_length=64)
    pipeline = serializers.ListField(child=serializers.DictField())
    options = serializers.DictField(required=False, default=dict)
    game_account = serializers.DictField(required=False, default=dict)
    device_constraints = serializers.DictField(required=False, default=dict)
    game_account_id = serializers.IntegerField(allow_null=True, required=False)
    game_account_name = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    resource_pack = serializers.JSONField(allow_null=True, required=False)


class TaskProgressPayloadSerializer(serializers.Serializer):
    """任务进度消息负载校验器，校验步骤序号、状态、耗时等字段。"""

    execution_id = serializers.CharField(max_length=64)
    step_index = serializers.IntegerField(min_value=0)
    status = serializers.ChoiceField(
        choices=["pending", "running", "success", "failed", "skipped"],
    )
    screenshot = serializers.CharField(required=False, allow_null=True)
    duration_ms = serializers.IntegerField(min_value=0, required=False)
    message = serializers.CharField(required=False, default="")


class TaskResultPayloadSerializer(serializers.Serializer):
    """任务结果消息负载校验器，校验最终状态、完成步骤数、错误详情等字段。"""

    execution_id = serializers.CharField(max_length=64)
    status = serializers.ChoiceField(choices=["completed", "failed", "cancelled"])
    steps_completed = serializers.IntegerField(min_value=0)
    total_steps = serializers.IntegerField(min_value=1)
    error = serializers.DictField(required=False)
    result_data = serializers.DictField(required=False, default=dict)
    duration_ms = serializers.IntegerField(min_value=0, required=False)


class TaskCancelPayloadSerializer(serializers.Serializer):
    """任务取消消息负载校验器，校验执行ID、取消原因等字段。"""

    execution_id = serializers.CharField(max_length=64)
    reason = serializers.CharField(required=False, default="")
    force = serializers.BooleanField(required=False, default=False)


def validate_payload(msg_type, payload):
    """根据消息类型校验负载，返回校验通过的数据。"""
    serializer_map = {
        MessageType.AGENT_REGISTER: WorkerRegisterPayloadSerializer,
        MessageType.AGENT_HEARTBEAT: WorkerHeartbeatPayloadSerializer,
        MessageType.TASK_DISPATCH: TaskDispatchPayloadSerializer,
        MessageType.TASK_PROGRESS: TaskProgressPayloadSerializer,
        MessageType.TASK_RESULT: TaskResultPayloadSerializer,
        MessageType.TASK_CANCEL: TaskCancelPayloadSerializer,
    }
    serializer_cls = serializer_map.get(msg_type)
    if serializer_cls is None:
        return payload
    serializer = serializer_cls(data=payload)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


from protocol.models import MessageFrameLog, WorkerSession  # noqa: E402


class WorkerSessionSerializer(serializers.ModelSerializer):
    """Agent 会话详情序列化器。"""

    class Meta:
        model = WorkerSession
        fields = [
            'id', 'agent_id', 'name', 'hostname', 'ip_address',
            'capabilities', 'resource_quota', 'status',
            'last_heartbeat', 'cpu_usage', 'memory_usage', 'screenshot_fps',
            'connected_at', 'disconnected_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['agent_id', 'connected_at']


class WorkerSessionListSerializer(serializers.ModelSerializer):
    """Agent 会话列表序列化器（轻量版）。"""

    class Meta:
        model = WorkerSession
        fields = [
            'id', 'agent_id', 'name', 'hostname', 'status',
            'last_heartbeat', 'cpu_usage', 'memory_usage', 'connected_at',
        ]


class MessageFrameLogSerializer(serializers.ModelSerializer):
    """消息帧日志序列化器。"""

    agent_name = serializers.CharField(source='agent_session.name', read_only=True, default='')

    class Meta:
        model = MessageFrameLog
        fields = [
            'id', 'trace_id', 'message_type', 'direction',
            'payload', 'agent_session', 'agent_name', 'created_at',
        ]
