"""QA serializers (migrated from qa app — 2026-08-04)."""

from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from gaf_ai.models import LLMUsageLog, QAMessage, QASession


class QAMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = QAMessage
        fields = ['id', 'session', 'role', 'content', 'created_at']
        read_only_fields = ['id', 'created_at']


class QASessionSerializer(serializers.ModelSerializer):
    message_count = serializers.SerializerMethodField()
    last_message_at = serializers.SerializerMethodField()

    class Meta:
        model = QASession
        fields = [
            'id', 'title', 'question', 'context_snapshot', 'answer',
            'is_knowledge_entry', 'user', 'model_name',
            'message_count', 'last_message_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'user', 'answer', 'created_at', 'updated_at']

    @extend_schema_field(OpenApiTypes.INT)
    def get_message_count(self, obj):
        return obj.messages.count()

    @extend_schema_field(OpenApiTypes.STR)
    def get_last_message_at(self, obj):
        last = obj.messages.order_by('-created_at').first()
        return last.created_at.isoformat() if last else None


class AskSerializer(serializers.Serializer):
    question = serializers.CharField()
    context = serializers.JSONField(required=False, default=dict)
    session_id = serializers.IntegerField(required=False, allow_null=True)


class LLMUsageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = LLMUsageLog
        fields = [
            'id', 'user', 'model_name', 'input_tokens', 'output_tokens',
            'cost_estimate', 'call_type', 'created_at',
        ]
        read_only_fields = fields
