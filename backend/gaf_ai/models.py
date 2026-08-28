"""Models for AI module — model performance evaluation (P-031)."""
from django.conf import settings
from django.db import models


class CustomSkill(models.Model):
    """User-defined YAML skill definition for the AI skill editor."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    category = models.CharField(max_length=64, default='analysis')
    yaml_content = models.TextField()
    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        related_name='custom_skills',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_custom_skill'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['created_by', '-updated_at'], name='idx_cskill_user_updated'),
            models.Index(fields=['category'], name='idx_cskill_category'),
        ]

    def __str__(self):
        return f'{self.name} ({self.category})'


class ModelEvaluation(models.Model):
    """Model performance evaluation — compares multiple LLMs on the same test cases."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')

    # Test prompt template — can contain {input} placeholder for test case interpolation
    system_prompt = models.TextField(blank=True, default='')
    test_cases = models.JSONField(default=list, help_text='List of test input strings')

    # Models to compare — list of {provider, model, api_base, api_key?, temperature?}
    models_config = models.JSONField(default=list, help_text='List of model configs to evaluate')

    # Scoring criteria — list of {name, weight, description}
    scoring_criteria = models.JSONField(
        default=list,
        help_text='List of scoring criteria: [{name, weight, description}]',
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True, default='')

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='model_evaluations',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ai_model_evaluation'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status'], name='idx_modelev_status'),
            models.Index(fields=['created_by', '-created_at'], name='idx_modelev_user_created'),
        ]

    def __str__(self):
        return f'{self.name} ({self.status})'


class ModelEvaluationResult(models.Model):
    """Result of evaluating one model on one test case."""

    evaluation = models.ForeignKey(
        ModelEvaluation,
        on_delete=models.CASCADE,
        related_name='results',
    )
    test_case_index = models.IntegerField(default=0, help_text='Index into evaluation.test_cases')

    # Model identity
    provider = models.CharField(max_length=50)
    model_name = models.CharField(max_length=100)

    # LLM response
    output_text = models.TextField(blank=True, default='')
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latency_ms = models.IntegerField(default=0, help_text='Response latency in milliseconds')

    # Scoring (JSON: {criterion_name: score_0_to_10})
    scores = models.JSONField(default=dict)
    average_score = models.FloatField(default=0, help_text='Weighted average score (0-10)')

    # Error tracking
    error = models.TextField(blank=True, default='')
    is_success = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_model_evaluation_result'
        ordering = ['test_case_index', 'model_name']
        indexes = [
            models.Index(fields=['evaluation', 'test_case_index'], name='idx_modelevr_eval_case'),
            models.Index(fields=['evaluation', 'model_name'], name='idx_modelevr_eval_model'),
        ]
        unique_together = [('evaluation', 'test_case_index', 'model_name')]

    def __str__(self):
        status = 'OK' if self.is_success else 'FAIL'
        return f'[{status}] {self.model_name} case#{self.test_case_index} score={self.average_score:.2f}'


# Re-export AgentSession so Django discovers it under the 'gaf_ai' app.
from gaf_ai.agent.models import AgentSession  # noqa: E402,F401

# ============================================================================
# QA models (migrated from qa app — 2026-08-04)
# ============================================================================

class QASession(models.Model):
    """技术问答会话模型 (migrated from qa app)."""

    question = models.TextField(verbose_name='问题')
    title = models.CharField(max_length=200, blank=True, default='', verbose_name='标题')
    context_snapshot = models.JSONField(default=dict, verbose_name='上下文快照')
    answer = models.TextField(blank=True, verbose_name='回答')
    is_knowledge_entry = models.BooleanField(default=False, verbose_name='是否为知识条目')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='qa_sessions', verbose_name='提问用户',
    )
    model_name = models.CharField(max_length=100, blank=True, verbose_name='模型名称')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'gaf_ai_qa_session'
        ordering = ['-created_at']
        verbose_name = '问答会话'
        verbose_name_plural = '问答会话'
        indexes = [
            models.Index(fields=['is_knowledge_entry'], name='idx_gafai_qasession_knowledge'),
        ]

    def __str__(self):
        return f'{self.question[:50]}...' if len(self.question) > 50 else self.question


class QAMessage(models.Model):
    """单条问答消息 (migrated from qa app)."""

    class Role(models.TextChoices):
        USER = 'user', 'User'
        ASSISTANT = 'assistant', 'Assistant'
        SYSTEM = 'system', 'System'

    session = models.ForeignKey(
        QASession, on_delete=models.CASCADE, related_name='messages',
        verbose_name='所属会话',
    )
    role = models.CharField(max_length=20, choices=Role.choices, verbose_name='角色')
    content = models.TextField(verbose_name='内容')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'gaf_ai_qa_message'
        ordering = ['created_at']
        verbose_name = '问答消息'
        verbose_name_plural = '问答消息'
        indexes = [
            models.Index(fields=['session', 'created_at'], name='idx_gafai_qamessage_session'),
        ]

    def __str__(self):
        return f'{self.role}: {self.content[:50]}'


class LLMUsageLog(models.Model):
    """LLM 用量日志模型 (migrated from qa app)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='llm_usage_logs', verbose_name='用户',
    )
    model_name = models.CharField(max_length=100, verbose_name='模型名称')
    input_tokens = models.IntegerField(default=0, verbose_name='输入 Token 数')
    output_tokens = models.IntegerField(default=0, verbose_name='输出 Token 数')
    cost_estimate = models.DecimalField(max_digits=10, decimal_places=6, default=0, verbose_name='成本估算')
    call_type = models.CharField(max_length=50, blank=True, verbose_name='调用类型')
    route = models.CharField(max_length=20, blank=True, default='', verbose_name='降级路由')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'gaf_ai_llmusagelog'
        ordering = ['-created_at']
        verbose_name = 'LLM 用量日志'
        verbose_name_plural = 'LLM 用量日志'
        indexes = [
            models.Index(fields=['user', 'created_at'], name='idx_gafai_llmu_user_created'),
        ]

    def __str__(self):
        return f'{self.user} - {self.model_name} ({self.input_tokens}/{self.output_tokens})'
