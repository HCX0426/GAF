"""Agent session model — stores multi-turn reasoning history."""
from django.conf import settings
from django.db import models


class AgentSession(models.Model):
    """Agent (AI 智能体) session, storing multi-turn reasoning history.

    OQ-10: this is the AI-agent session — distinct from ``protocol.WorkerSession``
    (execution-node WS connection state). The Worker module's WS session is
    named ``WorkerSession``, never ``AgentSession``.
    """

    class SessionType(models.TextChoices):
        LOG_ANALYSIS = 'log_analysis', 'Log Analysis'
        QA = 'qa', 'Q&A'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='agent_sessions',
        verbose_name='User',
    )
    session_type = models.CharField(
        max_length=20,
        choices=SessionType.choices,
        default=SessionType.LOG_ANALYSIS,
        verbose_name='Session type',
    )
    target_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Target ID',
        help_text='Associated target ID (e.g. execution_id)',
    )
    messages = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Message history',
        help_text='LangGraph message history',
    )
    reasoning_steps = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Reasoning steps',
        help_text='List of {thought, action, action_input, observation}',
    )
    # Phase 2 (spec 2026-08-31-ai-tab-agent-learning-spec): observability trail
    # from the hand-written LangGraph StateGraph. Each record is
    # {"step", "type" (router/tools/responder), ...} with tool-call names and
    # per-node token usage, driving the frontend trajectory timeline.
    trajectory = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Trajectory',
        help_text='LangGraph node trajectory: step/type/tool calls/token usage',
    )
    final_summary = models.TextField(
        blank=True,
        default='',
        verbose_name='Final summary',
    )
    final_suggestions = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Final suggestions',
    )
    # S3 P5 (2026-08-16): 幻觉防线基础版 — LLM 诊断结论的证据条目.
    # 由 _parse_agent_result 从最终答案 JSON 的 evidence 数组提取.
    # 空 = 未提供证据 (弱校验提示, 不阻塞).
    evidence = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Evidence',
        help_text='Evidence items backing the diagnosis (from LLM final answer)',
    )
    # P2 (2026-08-17): 幻觉防线强校验 — evidence 条目与 ReAct 工具观测比对结果.
    # 结构: {"verified": [...], "unverified": [...]} (text_similarity >= 0.3).
    # None = 未运行强校验 (旧数据兼容).
    evidence_check = models.JSONField(
        default=None,
        null=True,
        blank=True,
        verbose_name='Evidence check',
        help_text='Strong-check result: evidence items vs tool observations',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='Status',
    )
    model_used = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='Model used',
    )
    total_tokens = models.IntegerField(
        default=0,
        verbose_name='Total tokens',
    )
    total_cost = models.FloatField(
        default=0.0,
        verbose_name='Total cost',
    )
    error_message = models.TextField(
        blank=True,
        default='',
        verbose_name='Error message',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Completed at',
    )

    class Meta:
        app_label = 'gaf_ai'
        ordering = ['-created_at']
        verbose_name = 'Agent session'
        verbose_name_plural = 'Agent sessions'
        indexes = [
            models.Index(fields=['user', 'session_type'], name='idx_agent_session_user'),
            models.Index(fields=['target_id'], name='idx_agent_session_target'),
        ]

    def __str__(self):
        return f'AgentSession #{self.id} ({self.session_type}, {self.status})'
