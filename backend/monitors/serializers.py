from rest_framework import serializers

from monitors.models import MonitorEvent, MonitorRule, SLAMetric


class MonitorRuleSerializer(serializers.ModelSerializer):
    """监控规则序列化器，包含全部字段。"""

    class Meta:
        model = MonitorRule
        fields = [
            'id', 'name', 'rule_kind', 'rule_definition', 'resource_pack',
            'is_enabled', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class MonitorEventSerializer(serializers.ModelSerializer):
    """监控事件序列化器，severity/acknowledged/escalated 字段支持 P-024 告警升级策略。"""

    acknowledged_by_username = serializers.CharField(
        source='acknowledged_by.username',
        read_only=True,
        default=None,
    )

    class Meta:
        model = MonitorEvent
        fields = [
            'id', 'event_type', 'severity', 'handling_result', 'screenshot_path',
            'event_data', 'agent', 'resource_pack', 'created_at',
            'acknowledged_at', 'acknowledged_by', 'acknowledged_by_username',
            'escalated_at',
        ]
        read_only_fields = [
            'id', 'created_at',
            'acknowledged_at', 'acknowledged_by', 'acknowledged_by_username',
            'escalated_at',
        ]


class SLAMetricSerializer(serializers.ModelSerializer):
    """SLA 指标序列化器。"""

    agent_name = serializers.CharField(
        source='agent.hostname',
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = SLAMetric
        fields = ['id', 'agent', 'agent_name', 'metric_name', 'value', 'labels', 'timestamp']
        read_only_fields = ['id', 'timestamp']


class SLAMetricReportSerializer(serializers.Serializer):
    """SLA 指标上报序列化器。"""

    metric_name = serializers.CharField(max_length=100)
    value = serializers.FloatField()
    labels = serializers.DictField(default=dict, required=False)
