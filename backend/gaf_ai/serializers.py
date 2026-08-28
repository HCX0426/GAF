"""Serializers for AI module — custom skills and model evaluation (P-031)."""
from rest_framework import serializers

from .models import CustomSkill, ModelEvaluation, ModelEvaluationResult


class CustomSkillSerializer(serializers.ModelSerializer):
    """Serializer for user-defined YAML skills."""

    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default='')

    class Meta:
        model = CustomSkill
        fields = [
            'id',
            'name',
            'description',
            'category',
            'yaml_content',
            'is_active',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_by', 'created_by_name', 'created_at', 'updated_at']


class ModelEvaluationResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModelEvaluationResult
        fields = [
            'id',
            'test_case_index',
            'provider',
            'model_name',
            'output_text',
            'input_tokens',
            'output_tokens',
            'cost',
            'latency_ms',
            'scores',
            'average_score',
            'error',
            'is_success',
            'created_at',
        ]
        read_only_fields = fields


class ModelEvaluationSerializer(serializers.ModelSerializer):
    results = ModelEvaluationResultSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default='')

    class Meta:
        model = ModelEvaluation
        fields = [
            'id',
            'name',
            'description',
            'system_prompt',
            'test_cases',
            'models_config',
            'scoring_criteria',
            'status',
            'error_message',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
            'completed_at',
            'results',
        ]
        read_only_fields = ['id', 'status', 'error_message', 'created_by', 'created_at', 'updated_at', 'completed_at']


class ModelEvaluationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating evaluations — omits results and computed fields."""

    class Meta:
        model = ModelEvaluation
        fields = [
            'name',
            'description',
            'system_prompt',
            'test_cases',
            'models_config',
            'scoring_criteria',
        ]
