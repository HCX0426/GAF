from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Pipeline(models.Model):
    """Pipeline 数据模型 (TD-061 Plan B Stage 2: canonical Pipeline).

    Stage 2 consolidates tasks.Pipeline into pipeline.Pipeline via
    SeparateDatabaseAndState (pipeline migration 0004 + tasks migration 0038).
    The physical table is now ``pipeline`` (was ``pipeline_pipeline``), with
    PK as BigAutoField (was UUIDField). ``graph_data`` is the model field name
    while the physical column remains ``pipeline_data`` (bridged via
    db_column) to preserve the 5 real user rows + 26 TaskExecution FK
    references that already live in the ``pipeline`` table.

    graph_data stores React Flow nodes + edges + viewport JSON. Each PUT
    bumps version and archives the previous graph_data as a PipelineSnapshot.
    """
    name = models.CharField(max_length=255, verbose_name='Pipeline 名称')
    description = models.TextField(blank=True, default='', verbose_name='描述')
    graph_data = models.JSONField(
        default=dict, verbose_name='画布数据', db_column='pipeline_data',
    )
    version = models.IntegerField(default=1, verbose_name='版本号')
    is_template = models.BooleanField(default=False, verbose_name='是否为快速模板')
    estimated_duration_ms = models.IntegerField(default=0, verbose_name='预估耗时(ms)')
    # TD-061 Stage 2: user FK is NOT NULL (matches tasks.Pipeline schema and
    # the existing ``pipeline.user_id`` column). related_name reverted from
    # 'pipeline_pipelines' (Stage 1 clash-avoidance) to 'pipelines' now that
    # tasks.Pipeline is gone.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pipelines',
        verbose_name='所属用户',
    )
    sub_pipeline = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='used_by_pipelines',
        verbose_name='子流水线',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'pipeline'
        verbose_name = 'Pipeline'
        verbose_name_plural = verbose_name
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.name} (v{self.version})'


class PipelineSnapshot(models.Model):
    """Pipeline 版本快照 (TD-061 Plan B Stage 2: consolidated model).

    Stage 2 switches db_table from ``pipeline_version_snapshot`` to
    ``pipeline_snapshot`` (the physical table tasks.PipelineSnapshot created,
    which carries the matching schema). graph_data bridges to the physical
    ``pipeline_data`` column; change_summary bridges to ``comment`` (and is
    narrowed from TextField to CharField(500) to match the existing column).
    unique_together dropped because the physical table lacks the constraint;
    can be re-added in a follow-up migration if needed.
    """
    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.CASCADE,
        related_name='snapshots',
        verbose_name='关联 Pipeline',
    )
    version = models.IntegerField(verbose_name='快照版本号')
    graph_data = models.JSONField(
        verbose_name='画布数据快照', db_column='pipeline_data',
    )
    change_summary = models.CharField(
        max_length=500, blank=True, default='',
        verbose_name='变更摘要', db_column='comment',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'pipeline_snapshot'
        verbose_name = 'Pipeline 版本快照'
        verbose_name_plural = verbose_name
        ordering = ['-version']

    def __str__(self):
        return f'{self.pipeline.name} snapshot v{self.version}'


class TaskChain(models.Model):
    """任务链模型，定义一组任务之间的 DAG 依赖关系（串行/并行编排）。

    Migrated from tasks app (R37-P3 Stage 7 Task 20a) — TaskChain is a
    pipeline/DAG orchestration concept, so it belongs in the pipeline app.
    db_table kept as 'tasks_taskchain' to avoid a data migration; the move
    is state-only (SeparateDatabaseAndState).
    """

    name = models.CharField(
        max_length=255,
        verbose_name='任务链名称',
        help_text='任务链的显示名称',
    )
    description = models.TextField(
        blank=True,
        default='',
        verbose_name='描述',
        help_text='任务链的详细描述',
    )
    dag_data = models.JSONField(
        default=dict,
        verbose_name='DAG 图数据 (React Flow nodes + edges)',
        help_text='任务链的 DAG 节点和边数据',
    )
    is_enabled = models.BooleanField(
        default=True,
        verbose_name='是否启用',
        help_text='标记任务链是否处于启用状态',
    )
    game_profile = models.ForeignKey(
        'gamestate.GameProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_chains',
        verbose_name='所属游戏档案',
        help_text='Window-centric: 任务链归属游戏档案',
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name='是否默认链',
        help_text='Window-centric: 标记为该 GameProfile 的默认任务链，'
                  '一个 GameProfile 下最多一个 is_default=True',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='task_chains',
        verbose_name='创建者',
        help_text='创建该任务链的用户',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
        help_text='记录创建的时间戳',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间',
        help_text='记录最近一次更新的时间戳',
    )

    class Meta:
        db_table = 'tasks_taskchain'
        ordering = ['-created_at']
        verbose_name = '任务链'
        verbose_name_plural = '任务链'

    def __str__(self):
        return self.name

    def clean(self):
        """Validate that only one is_default=True per GameProfile."""
        if self.is_default and self.game_profile_id:
            qs = TaskChain.objects.filter(
                game_profile=self.game_profile_id,
                is_default=True,
            ).exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    '该 GameProfile 下已有默认 TaskChain，'
                    '请先取消其 is_default 标记'
                )

    def has_circular_dependency(self):
        """检测当前 DAG 是否存在循环依赖"""
        nodes = self.chain_nodes.all().select_related('parent').values_list('id', 'parent_id')
        adj = {}
        for node_id, parent_id in nodes:
            if parent_id is not None:
                if parent_id not in adj:
                    adj[parent_id] = []
                adj[parent_id].append(node_id)

        visited = set()
        rec_stack = set()

        def dfs(node):
            visited.add(node)
            rec_stack.add(node)
            for neighbor in adj.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        return any(node_id not in visited and dfs(node_id) for node_id in adj)


class Recording(models.Model):
    """录制数据模型 (P-008: migrated from tasks app).

    Recording conceptually belongs to the pipeline app: it is the source
    material for generating Pipelines (via convert_to_pipeline action). The
    physical table ``recording`` is preserved (7 existing rows); the move is
    state-only (SeparateDatabaseAndState — pipeline 0005 + tasks 0039).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='recordings',
        verbose_name='用户',
        help_text='录制所属的用户',
    )
    name = models.CharField(
        max_length=255,
        verbose_name='名称',
        help_text='录制的显示名称',
    )
    recording_data = models.JSONField(
        default=dict,
        verbose_name='录制数据JSON',
        help_text='录制的原始数据 JSON',
    )
    pipeline_json = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='转换后的Pipeline JSON',
        help_text='录制转换后的 Pipeline JSON',
    )
    duration = models.FloatField(
        default=0,
        verbose_name='录制时长(秒)',
        help_text='录制的总时长(秒)',
    )
    screenshot_count = models.IntegerField(
        default=0,
        verbose_name='截图数量',
        help_text='录制过程中截图的总数',
    )
    resolution = models.CharField(
        max_length=50,
        default='1920x1080',
        verbose_name='分辨率',
        help_text='录制的屏幕分辨率',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
        help_text='记录创建的时间戳',
    )

    class Meta:
        db_table = 'recording'
        ordering = ['-created_at']
        verbose_name = '录制'
        verbose_name_plural = '录制'

    def __str__(self):
        return self.name


class TaskChainNode(models.Model):
    """任务链节点模型，定义链式任务中的节点顺序和条件。

    Migrated from tasks app (R37-P3 Stage 7 Task 20a) — belongs in pipeline
    app alongside TaskChain. The FK to tasks.Task is a legitimate cross-app
    reference (orchestrator depends on executor). db_table kept as
    'tasks_taskchainnode' (state-only migration).

    TD-110 (2026-07-14): node_type + pipeline FK added so a node can
    reference either a Task (legacy path) or a Pipeline (new path).
    Mirrors TaskExecution.pipeline FK — Pipeline is now a first-class
    chain citizen, no wrapper Task needed. dispatch_chain_node branches
    on node_type (see pipeline/tasks.py).
    """

    class NodeType(models.TextChoices):
        TASK = 'task', 'Task'
        PIPELINE = 'pipeline', 'Pipeline'

    node_type = models.CharField(
        max_length=10,
        choices=NodeType.choices,
        default=NodeType.TASK,
        verbose_name='节点类型',
        help_text='节点引用的是 Task 还是 Pipeline',
    )
    chain = models.ForeignKey(
        TaskChain,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='chain_nodes',
        verbose_name='关联任务链',
        help_text='节点所属的任务链',
    )
    task = models.ForeignKey(
        'tasks.Task',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='chain_nodes',
        verbose_name='关联任务',
        help_text='节点关联的任务记录 (node_type=task 时必填)',
    )
    pipeline = models.ForeignKey(
        'pipeline.Pipeline',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='chain_nodes',
        verbose_name='关联 Pipeline',
        help_text='节点引用的 Pipeline (node_type=pipeline 时必填)',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='父节点',
        help_text='父节点, 用于构建 DAG 结构',
    )
    condition = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='条件配置',
        help_text='节点执行的条件配置',
    )
    order = models.IntegerField(
        verbose_name='排序',
        help_text='节点在链中的执行顺序',
    )

    class Meta:
        db_table = 'tasks_taskchainnode'
        ordering = ['order']
        verbose_name = '任务链节点'
        verbose_name_plural = '任务链节点'

    def __str__(self):
        chain_info = f'[{self.chain.name}] ' if self.chain else ''
        # TD-110: node may reference either task or pipeline
        ref_name = ''
        if self.node_type == self.NodeType.PIPELINE:
            ref_name = self.pipeline.name if self.pipeline_id else '(missing pipeline)'
        else:
            ref_name = self.task.name if self.task_id else '(missing task)'
        return f'{chain_info}{ref_name} - 节点{self.order}'

    def clean(self):
        """Validate that node_type matches the populated FK (TD-110).

        - node_type=TASK  → task FK must be set
        - node_type=PIPELINE → pipeline FK must be set
        """
        from django.core.exceptions import ValidationError

        if self.node_type == self.NodeType.TASK and not self.task_id:
            raise ValidationError({'task': 'node_type=task 但 task FK 未设置'})
        if self.node_type == self.NodeType.PIPELINE and not self.pipeline_id:
            raise ValidationError({'pipeline': 'node_type=pipeline 但 pipeline FK 未设置'})


class TaskChainExecution(models.Model):
    """任务链执行记录，跟踪一次 TaskChain 执行的整体状态和进度。

    (spec 阶段 5 — TD-096 TaskChain 执行器)

    当用户调用 ``POST /api/v2/pipeline/task-chains/{id}/execute/`` 时创建。
    每个 TaskChainNode 的 Task 会创建独立的 TaskExecution，通过
    ``TaskExecution.chain_execution`` FK 关联回本记录。

    执行流程：
        1. execute API → 创建 TaskChainExecution (status=RUNNING)
        2. dispatch_chain_node → 为第一个节点创建 TaskExecution + dispatch_task
        3. Agent 完成 → _db_update_execution_result → 检查 chain_execution FK
        4. advance_chain_execution → 检查 condition → 派发下一节点或终止链

    Condition 语义 (TaskChainNode.condition JSON):
        - {"on_failure": "abort"}  — 默认，失败则终止整条链
        - {"on_failure": "skip"}   — 跳过失败节点，继续下一节点
        - {"on_failure": "retry", "max_retries": 3} — 重试失败节点
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    chain = models.ForeignKey(
        TaskChain,
        on_delete=models.CASCADE,
        related_name='executions',
        verbose_name='关联任务链',
        help_text='执行的任务链',
    )
    current_node = models.ForeignKey(
        TaskChainNode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='active_in_executions',
        verbose_name='当前执行节点',
        help_text='当前正在执行的 TaskChainNode',
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='triggered_chain_executions',
        verbose_name='触发用户',
    )
    agent_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='执行 Agent ID',
        help_text='链执行绑定的 Agent（整条链在同一 Agent 上执行）',
    )
    # v3: device FK (was IntegerField). FK preserves referential integrity
    # and allows ORM joins. Migration 0008 copies old device_id values.
    device = models.ForeignKey(
        'agents.Device',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chain_executions',
        verbose_name='执行设备',
        help_text='Window-centric: 链执行绑定的设备（整条链在同一设备上执行）',
    )
    # v3: game_account FK — runtime account binding (spec §2.10)
    game_account = models.ForeignKey(
        'accounts.GameAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chain_executions',
        verbose_name='运行时游戏账户',
        help_text='Window-centric: 链执行绑定的游戏账户（从 device.game_account 取）',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='链执行状态',
    )
    started_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='开始时间',
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='完成时间',
    )
    error_message = models.TextField(
        blank=True,
        default='',
        verbose_name='错误信息',
        help_text='链执行失败时的错误信息',
    )
    # N192: 链执行级错误码, 从失败节点的 TaskExecution.error_code 传播.
    # 用于前端按错误类型分类展示链执行失败原因.
    error_code = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='错误码',
        help_text='链级错误码 (DEVICE_DISCONNECTED/UNKNOWN/...), 与失败节点 error_code 对齐',
    )

    class Meta:
        db_table = 'pipeline_task_chain_execution'
        ordering = ['-started_at']
        verbose_name = '任务链执行记录'
        verbose_name_plural = '任务链执行记录'

    def __str__(self):
        return f'[{self.chain.name}] {self.get_status_display()} ({self.pk})'
