"""gaf_ai admin — merged from gaf_ai + qa (2026-08-04)."""

from django.contrib import admin

from gaf_ai.models import LLMUsageLog, QASession


@admin.register(QASession)
class QASessionAdmin(admin.ModelAdmin):
    """问答会话管理后台配置 (migrated from qa app)."""

    list_display = ('id', 'question', 'user', 'is_knowledge_entry', 'model_name', 'created_at')
    list_filter = ('is_knowledge_entry',)
    search_fields = ('question', 'answer')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(LLMUsageLog)
class LLMUsageLogAdmin(admin.ModelAdmin):
    """LLM 用量日志管理后台配置 (migrated from qa app)."""

    list_display = ('id', 'user', 'model_name', 'input_tokens', 'output_tokens', 'cost_estimate', 'call_type', 'created_at')
    list_filter = ('model_name', 'call_type')
    search_fields = ('user__username', 'model_name')
    readonly_fields = ('created_at',)
