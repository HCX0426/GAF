"""
调度模块序列化器

包含时间窗口、预热配置、自动停止条件、执行计划等序列化器。
"""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from scheduler.models import AutoStopCondition, GameAccountRotation, RecoveryLog, TimeWindow, WarmupConfig


class RecoveryLogSerializer(serializers.ModelSerializer):
    """恢复操作日志序列化器 (P-020-A)

    Fields:
    - id, recovery_level, trigger_event, action_taken
    - success, details, created_at

    Read-only (系统写入,不允许 API 改写):
    - 全部字段, ViewSet 只暴露 list/retrieve
    """

    recovery_level_display = serializers.CharField(source="get_recovery_level_display", read_only=True)

    class Meta:
        model = RecoveryLog
        fields = [
            "id",
            "recovery_level",
            "recovery_level_display",
            "trigger_event",
            "action_taken",
            "success",
            "details",
            "created_at",
        ]
        read_only_fields = fields


class TimeWindowSerializer(serializers.ModelSerializer):
    """时间窗口序列化器，支持 CRUD 操作。"""

    class Meta:
        model = TimeWindow
        fields = [
            "id",
            "start_time",
            "end_time",
            "days_of_week",
            "is_enabled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class WarmupStepSerializer(serializers.Serializer):
    """预热步骤序列化器，用于校验步骤 JSON 结构。"""

    type = serializers.ChoiceField(
        choices=[
            ("start_emulator", "启动模拟器"),
            ("start_game", "启动游戏"),
            ("wait_loading", "等待加载"),
            ("auto_login", "自动登录"),
        ]
    )
    label = serializers.CharField(max_length=100)
    is_enabled = serializers.BooleanField(default=True)
    order = serializers.IntegerField()
    timeout_seconds = serializers.IntegerField(default=60)
    retry_count = serializers.IntegerField(default=1)
    wait_seconds = serializers.IntegerField(default=10, required=False)
    auto_login = serializers.BooleanField(default=False, required=False)


class WarmupConfigSerializer(serializers.ModelSerializer):
    """设备预热配置序列化器，Upsert 模式。"""

    steps = WarmupStepSerializer(many=True)

    class Meta:
        model = WarmupConfig
        fields = [
            "id",
            "steps",
            "global_timeout_seconds",
            "failure_strategy",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def create(self, validated_data):
        steps_data = validated_data.pop("steps", [])
        existing = WarmupConfig.objects.first()
        if existing:
            existing.steps = steps_data
            existing.global_timeout_seconds = validated_data.get(
                "global_timeout_seconds", existing.global_timeout_seconds
            )
            existing.failure_strategy = validated_data.get("failure_strategy", existing.failure_strategy)
            existing.save()
            return existing

        config = WarmupConfig.objects.create(steps=steps_data, **validated_data)
        return config


class AutoStopConditionSerializer(serializers.ModelSerializer):
    """自动停止条件序列化器。"""

    class Meta:
        model = AutoStopCondition
        fields = [
            "id",
            "condition_type",
            "is_enabled",
            "threshold",
            "action",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AutoStopConditionBulkSerializer(serializers.Serializer):
    """自动停止条件批量更新序列化器，Upsert 模式。"""

    conditions = AutoStopConditionSerializer(many=True)

    def save(self):
        conditions_data = self.validated_data["conditions"]
        result = []
        for cond_data in conditions_data:
            condition_type = cond_data["condition_type"]
            obj, _created = AutoStopCondition.objects.update_or_create(
                condition_type=condition_type,
                defaults={
                    "is_enabled": cond_data.get("is_enabled", True),
                    "threshold": cond_data.get("threshold"),
                    "action": cond_data.get("action", "stop_all"),
                },
            )
            result.append(obj)
        return result


class ExecutionPlanEventSerializer(serializers.Serializer):
    """执行计划事件序列化器。"""

    id = serializers.CharField()
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    device_name = serializers.CharField()
    device_id = serializers.IntegerField()
    account_name = serializers.CharField()
    account_id = serializers.IntegerField()
    task_name = serializers.CharField()
    task_type = serializers.ChoiceField(
        choices=[
            ("daily", "日常"),
            ("resource", "资源"),
            ("event", "活动"),
            ("weekly", "周常"),
        ]
    )
    estimated_duration = serializers.IntegerField()
    status = serializers.ChoiceField(
        choices=[
            ("scheduled", "已排程"),
            ("conflict", "冲突"),
            ("outside_window", "窗口外"),
        ]
    )


class ExecutionPlanSerializer(serializers.Serializer):
    """执行计划响应序列化器。"""

    days = serializers.IntegerField()
    total_events = serializers.IntegerField()
    device_count = serializers.IntegerField()
    account_count = serializers.IntegerField()
    events = ExecutionPlanEventSerializer(many=True)


class TodayScheduleItemSerializer(serializers.Serializer):
    """今日日程项序列化器。"""

    id = serializers.IntegerField()
    device_name = serializers.CharField()
    account_name = serializers.CharField()
    task_name = serializers.CharField()
    task_type = serializers.CharField()
    scheduled_time = serializers.DateTimeField()
    actual_start_time = serializers.DateTimeField(allow_null=True)
    actual_end_time = serializers.DateTimeField(allow_null=True)
    status = serializers.ChoiceField(
        choices=[
            ("planned", "计划中"),
            ("pending", "待执行"),
            ("running", "进行中"),
            ("completed", "已完成"),
            ("failed", "失败"),
            ("skipped", "已跳过"),
        ]
    )
    progress = serializers.IntegerField(default=0)
    error_message = serializers.CharField(allow_blank=True, allow_null=True)


class TodayScheduleSerializer(serializers.Serializer):
    """今日日程响应序列化器。"""

    date = serializers.DateField()
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    failed = serializers.IntegerField()
    items = TodayScheduleItemSerializer(many=True)


class GameAccountRotationSerializer(serializers.ModelSerializer):
    """轮换规则序列化器

    spec-29a #26: migrated from accounts/serializers.py to live alongside its
    GameAccountRotation model (same app). Eliminates the cross-app top-level
    import accounts.serializers -> scheduler.models.
    """

    account_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = GameAccountRotation
        fields = [
            'id', 'name', 'rotation_strategy', 'accounts', 'account_details',
            'switch_interval_seconds', 'auto_skip_blocked',
            'is_active', 'owner', 'created_at',
        ]
        read_only_fields = ['id', 'owner', 'created_at']

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_account_details(self, obj):
        return [
            # spec 2026-08-29-game-account-game-name-retirement P3: GameAccount.game_name
            # 已 drop, 游戏名唯一来源 = game_profile.game_name (P2 后 profile 非空).
            {'id': a.id, 'username': a.username, 'game_name': a.game_profile.game_name if a.game_profile_id else ''}
            for a in obj.accounts.all()
        ]

    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)

    def validate_accounts(self, value):
        if not value or len(value) < 1:
            raise serializers.ValidationError('至少需要关联 1 个账户')
        return value
