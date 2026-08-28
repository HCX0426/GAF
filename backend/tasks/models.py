
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Task(models.Model):
    """任务模型，定义自动化任务的执行模式、参数和关联资源包。"""

    class ExecutionMode(models.TextChoices):
        # spec-2026-07-27-execution-path-unification 阶段 5: CHAIN 已废弃,
        # 所有任务统一走 PipelineEngine. 保留 PIPELINE 显式标识 + STATE_MACHINE
        # (走独立 Python 模块路径). 老 chain 任务由数据迁移转为 PIPELINE.
        PIPELINE = 'pipeline', 'Pipeline'
        STATE_MACHINE = 'state_machine', 'State Machine'

    class SourceType(models.TextChoices):
        MANUAL = 'manual', '手动创建'
        YAML_IMPORT = 'yaml_import', 'YAML导入'

    name = models.CharField(
        max_length=255,
        verbose_name='任务名称',
        help_text='任务的显示名称',
    )
    description = models.TextField(
        blank=True,
        verbose_name='描述',
        help_text='任务的详细描述',
    )
    execution_mode = models.CharField(
        max_length=20,
        choices=ExecutionMode.choices,
        default=ExecutionMode.PIPELINE,
        verbose_name='执行模式',
        help_text='执行模式: pipeline/state_machine (chain 已废弃，归一化到 pipeline)',
    )
    task_definition = models.JSONField(
        default=dict,
        verbose_name='任务定义',
        help_text='任务的完整定义 JSON',
    )
    params_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='参数配置',
        help_text='任务运行时参数配置',
    )
    game_profile = models.ForeignKey(
        'gamestate.GameProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name='tasks',
        verbose_name='所属游戏档案',
        help_text='R37-P1: 任务所属的游戏档案（nullable，兼容老任务）',
    )
    resource_pack = models.ForeignKey(
        'resources.ResourcePack',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        related_name='tasks',
        verbose_name='关联资源包',
        help_text='N197-8: 任务直接关联的资源包。任务运行时根据此资源包加载模板（图片/文字）用于识别。'
                  '不同服务器可共用同一资源包，通过 ResourcePack.config_data 按 server 区分文件。',
    )
    is_enabled = models.BooleanField(
        default=True,
        verbose_name='是否启用',
        help_text='标记任务是否处于启用状态',
    )
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.MANUAL,
        verbose_name='来源类型',
        help_text='来源: manual/yaml_import',
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
    tags = models.JSONField(
        default=list,
        blank=True,
        verbose_name='标签列表',
        help_text='任务的标签列表',
    )
    retry_policy = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='重试策略',
        help_text='任务失败时的重试策略配置',
    )
    preflight_config = models.JSONField(
        default=list,
        blank=True,
        verbose_name='预检配置',
        help_text='任务执行前的预检项配置',
    )
    recovery_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='恢复配置',
        help_text='任务异常时的恢复策略配置',
    )
    game_accounts = models.ManyToManyField(
        'accounts.GameAccount',
        blank=True,
        related_name='bound_tasks',
        verbose_name='游戏账户',
        help_text='任务绑定的多个游戏账户',
    )
    rotation_rule = models.ForeignKey(
        'scheduler.GameAccountRotation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bound_tasks',
        verbose_name='轮换规则',
        help_text='关联的游戏账户轮换规则',
    )
    parallel_mode = models.BooleanField(
        default=False,
        verbose_name='并行模式',
        help_text='是否启用并行执行模式',
    )
    max_concurrency = models.IntegerField(
        default=1,
        verbose_name='最大并发数',
        help_text='任务允许的最大并发执行数',
    )
    folder = models.ForeignKey(
        'TaskFolder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks',
        verbose_name='所属文件夹',
        help_text='任务所属的文件夹',
    )
    goal = models.TextField(
        blank=True,
        verbose_name='任务目标',
        help_text='高层语义目标 (spec 阶段 4.3)，如"完成 BD2 日常委托"。'
                  '供 LLM 诊断和任务设计文档化使用，不参与执行逻辑',
    )
    success_criteria = models.JSONField(
        default=list,
        blank=True,
        verbose_name='成功标准',
        help_text='任务完成的成功标准列表 (spec 阶段 4.3)，'
                  '如 ["daily_missions_completed", "email_collected"]',
    )

    class Meta:
        ordering = ['-id']
        verbose_name = '任务'
        verbose_name_plural = '任务'

    def __str__(self):
        return f'{self.name} ({self.get_execution_mode_display()})'


class TaskDevice(models.Model):
    """任务与设备的中间表，定义任务可以在哪些设备上执行"""

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='device_mappings',
        verbose_name='关联任务',
        help_text='关联的任务记录',
    )
    device = models.ForeignKey(
        'agents.Device',
        on_delete=models.CASCADE,
        related_name='task_mappings',
        verbose_name='关联设备',
        help_text='关联的设备记录',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间', help_text='记录创建的时间戳')

    class Meta:
        db_table = 'tasks_taskdevice'
        verbose_name = '任务设备映射'
        verbose_name_plural = '任务设备映射'
        unique_together = [('task', 'device')]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.task.name} → {self.device}'


class TaskExecution(models.Model):
    """任务执行记录模型，记录每次任务执行的完整状态和结果。"""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        PAUSED = 'paused', 'Paused'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'
        FORCE_TERMINATED = 'force_terminated', 'Force Terminated'

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='executions',
        verbose_name='关联任务',
        help_text='关联的任务记录（Pipeline 执行时可为空，改用 pipeline 字段）',
    )
    pipeline = models.ForeignKey(
        'pipeline.Pipeline',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executions',
        verbose_name='关联 Pipeline',
        help_text='Pipeline 执行时关联的 Pipeline 记录（链式任务执行时为空）',
    )
    agent = models.ForeignKey(
        'agents.Agent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executions',
        verbose_name='执行 Agent',
        help_text='执行该任务的 Agent',
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='triggered_executions',
        verbose_name='触发用户',
        help_text='触发该次执行的用户',
    )
    chain_execution = models.ForeignKey(
        'pipeline.TaskChainExecution',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='node_executions',
        verbose_name='关联链执行',
        help_text='(spec 阶段 5) 当此执行是 TaskChain 的一部分时，指向链执行记录',
    )
    chain_node = models.ForeignKey(
        'pipeline.TaskChainNode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executions',
        verbose_name='关联链节点',
        help_text='(spec 阶段 5) 当此执行是 TaskChain 的一部分时，指向具体的链节点',
    )
    game_account = models.ForeignKey(
        'accounts.GameAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='executions',
        verbose_name='运行时游戏账户',
        help_text='Window-centric: 本次执行绑定的游戏账户，dispatch_task 从此读取 resource_pack',
    )
    device = models.ForeignKey(
        'agents.Device',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_executions',
        verbose_name='执行设备',
        help_text='Window-centric: 本次执行的具体设备（一个 task 可关联多设备，execution 记录具体在哪台执行）',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='执行状态',
        help_text='状态: pending/running/paused/success/failed/cancelled/force_terminated',
    )
    paused_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='暂停时间',
        help_text='任务被暂停的时间',
    )
    resumed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='恢复时间',
        help_text='任务从暂停恢复的时间',
    )
    recovery_attempts = models.IntegerField(
        default=0,
        verbose_name='恢复尝试次数',
        help_text='当前层级的恢复尝试次数',
    )
    recovery_layer = models.IntegerField(
        default=0,
        verbose_name='当前恢复层级',
        help_text='当前所处的恢复策略层级',
    )
    trace_id = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        verbose_name='Trace ID',
        help_text=(
            'B3-3 (spec 2026-07-30-debug-directory-restructure): HTTP 请求级 '
            'trace_id (完整 UUID), 由 TracingMiddleware 注入到 ContextVar, '
            'dispatch_task 时从 current_trace_id.get() 取. 全链路贯穿: '
            'HTTP → WS 帧 → backend log → agent log → meta.json. '
            '便于按 trace_id 反查所有相关执行记录.'
        ),
    )
    log = models.TextField(
        blank=True,
        verbose_name='执行日志',
        help_text='任务执行的完整日志',
    )
    result_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='结果数据',
        help_text='任务执行的结果数据',
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='错误信息',
        help_text='任务执行失败的错误信息',
    )
    error_code = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='错误码',
        help_text='任务级错误码 (DEVICE_DISCONNECTED/UNKNOWN/...), 与 agent NodeErrorCode 对齐',
    )
    cancel_reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='取消原因',
        help_text='任务被取消的原因说明',
    )
    screenshot_path = models.CharField(
        max_length=512,
        blank=True,
        verbose_name='截图路径',
        help_text='执行时的截图文件路径',
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='开始时间',
        help_text='任务实际开始执行的时间',
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='完成时间',
        help_text='任务执行完成的时间',
    )
    duration = models.DurationField(
        null=True,
        blank=True,
        verbose_name='执行耗时',
        help_text='任务执行的总耗时',
    )
    execution_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='执行快照',
        help_text='执行时的配置和环境快照',
    )
    is_archived = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name='已归档',
        help_text='TD-351: 标记该执行为已归档状态，默认查询会过滤',
    )
    archived_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='归档时间',
        help_text='TD-351: 记录被归档的时间戳',
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
        db_table = 'tasks_taskexecution'
        ordering = ['-created_at']
        verbose_name = '任务执行记录'
        verbose_name_plural = '任务执行记录'
        indexes = [
            models.Index(fields=['task', 'status'], name='idx_taskexec_task_status'),
            models.Index(fields=['agent', 'status'], name='idx_taskexec_agent_status'),
            models.Index(fields=['created_at'], name='idx_taskexec_created'),
            models.Index(fields=['chain_execution', 'status'], name='idx_taskexec_chain_status'),
            models.Index(fields=['device', 'status'], name='idx_taskexec_device_status'),
            models.Index(fields=['game_account', 'status'], name='idx_taskexec_account_status'),
        ]

    def __str__(self):
        return f'{self.task.name} - {self.get_status_display()} ({self.pk})'


class TaskStep(models.Model):
    """任务步骤模型，记录任务执行中每个步骤的详细状态。"""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        SKIPPED = 'skipped', 'Skipped'

    execution = models.ForeignKey(
        TaskExecution,
        on_delete=models.CASCADE,
        related_name='steps',
        verbose_name='关联执行记录',
        help_text='关联的任务执行记录',
    )
    step_index = models.IntegerField(
        verbose_name='步骤序号',
        help_text='步骤在任务中的执行序号',
    )
    step_name = models.CharField(
        max_length=255,
        verbose_name='步骤名称',
        help_text='步骤的显示名称',
    )
    step_type = models.CharField(
        max_length=50,
        verbose_name='步骤类型',
        help_text='步骤的类型标识',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='步骤状态',
        help_text='状态: pending/running/success/failed/skipped',
    )
    result_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='结果数据',
        help_text='步骤执行的结果数据',
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='错误信息',
        help_text='步骤执行失败的错误信息',
    )
    screenshot_path = models.CharField(
        max_length=512,
        blank=True,
        verbose_name='截图路径',
        help_text='步骤截图文件路径',
    )
    retry_count = models.IntegerField(
        default=0,
        verbose_name='重试次数',
        help_text='步骤已重试的次数',
    )
    duration = models.DurationField(
        null=True,
        blank=True,
        verbose_name='步骤耗时',
        help_text='步骤执行的总耗时',
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='开始时间',
        help_text='步骤开始执行的时间',
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='完成时间',
        help_text='步骤执行完成的时间',
    )

    class Meta:
        db_table = 'tasks_taskstep'
        ordering = ['step_index']
        verbose_name = '任务步骤'
        verbose_name_plural = '任务步骤'
        unique_together = [('execution', 'step_index')]

    def __str__(self):
        return f'{self.execution.task.name} - 步骤{self.step_index}: {self.step_name}'


class CustomTask(models.Model):
    """自定义任务模型，用户自行创建的灵活任务定义。"""

    name = models.CharField(
        max_length=255,
        verbose_name='任务名称',
        help_text='自定义任务的显示名称',
    )
    description = models.TextField(
        blank=True,
        verbose_name='描述',
        help_text='自定义任务的详细描述',
    )
    task_definition = models.JSONField(
        default=dict,
        verbose_name='任务定义',
        help_text='自定义任务的完整定义 JSON',
    )
    params_config = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='参数配置',
        help_text='自定义任务运行时参数配置',
    )
    json_schema = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='JSON Schema',
        help_text='参数配置的 JSON Schema 校验规则',
    )
    resource_pack = models.ForeignKey(
        'resources.ResourcePack',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='custom_tasks',
        verbose_name='Associated resource pack',
        help_text='关联的资源包记录',
    )
    is_enabled = models.BooleanField(
        default=True,
        verbose_name='是否启用',
        help_text='标记自定义任务是否处于启用状态',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='custom_tasks',
        verbose_name='创建者',
        help_text='创建该自定义任务的用户',
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
        ordering = ['-id']
        verbose_name = '自定义任务'
        verbose_name_plural = '自定义任务'

    def __str__(self):
        return f'{self.name} (自定义)'


class ScheduledTask(models.Model):
    """定时任务模型，支持一次性定时和周期性调度。"""

    class ScheduleType(models.TextChoices):
        ONE_TIME = 'one_time', 'One Time'
        PERIODIC = 'periodic', 'Periodic'

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='schedules',
        verbose_name='关联任务',
        help_text='关联的任务记录',
    )
    custom_task = models.ForeignKey(
        CustomTask,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='schedules',
        verbose_name='关联自定义任务',
        help_text='关联的自定义任务记录',
    )
    schedule_type = models.CharField(
        max_length=20,
        choices=ScheduleType.choices,
        verbose_name='调度类型',
        help_text='调度类型: one_time/periodic',
    )
    cron_expression = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Cron 表达式',
        help_text='周期性调度的 Cron 表达式',
    )
    scheduled_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='计划执行时间',
        help_text='一次性任务的计划执行时间',
    )
    is_enabled = models.BooleanField(
        default=True,
        verbose_name='是否启用',
        help_text='标记定时任务是否处于启用状态',
    )
    last_executed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='上次执行时间',
        help_text='定时任务最近一次触发执行的时间',
    )
    resource_pack = models.ForeignKey(
        'resources.ResourcePack',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scheduled_tasks',
        verbose_name='Associated resource pack',
        help_text='关联的资源包记录',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='scheduled_tasks',
        verbose_name='创建者',
        help_text='创建该定时任务的用户',
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
        db_table = 'tasks_scheduledtask'
        ordering = ['-id']
        verbose_name = '定时任务'
        verbose_name_plural = '定时任务'

    def __str__(self):
        task_name = self.task.name if self.task else (self.custom_task.name if self.custom_task else '未指定')
        return f'{task_name} ({self.get_schedule_type_display()})'


class TaskVersion(models.Model):
    """Task version snapshot model, stores task configuration history for rollback support."""

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='versions',
        verbose_name='关联任务',
        help_text='关联的任务记录',
    )
    version_number = models.IntegerField(
        verbose_name='版本号',
        help_text='任务的版本序号',
    )
    snapshot = models.JSONField(
        verbose_name='任务配置快照',
        help_text='Complete task configuration JSON at the time of version save',
    )
    change_description = models.TextField(
        blank=True,
        verbose_name='变更描述',
        help_text='该版本的变更说明',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='task_versions',
        verbose_name='创建者',
        help_text='创建该版本的用户',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
        help_text='记录创建的时间戳',
    )

    class Meta:
        db_table = 'tasks_taskversion'
        ordering = ['-version_number']
        unique_together = [('task', 'version_number')]
        verbose_name = '任务版本'
        verbose_name_plural = '任务版本'

    def __str__(self):
        return f'{self.task.name} v{self.version_number}'


class ExecutionStep(models.Model):
    """执行步骤模型，记录任务执行中每个步骤的详细识别结果和耗时。"""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'
        SKIPPED = 'skipped', 'Skipped'

    task_result = models.ForeignKey(
        TaskExecution,
        on_delete=models.CASCADE,
        related_name='execution_steps',
        verbose_name='关联执行记录',
        help_text='关联的任务执行记录',
    )
    step_index = models.IntegerField(
        verbose_name='步骤序号',
        help_text='步骤在执行中的序号',
    )
    node_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='节点ID',
        help_text='步骤对应的节点标识',
    )
    step_type = models.CharField(
        max_length=50,
        verbose_name='步骤类型',
        help_text='步骤的类型标识',
    )
    step_name = models.CharField(
        max_length=255,
        verbose_name='步骤名称',
        help_text='步骤的显示名称',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='步骤状态',
        help_text='状态: pending/running/success/failed/skipped',
    )
    screenshot_path = models.CharField(
        max_length=512,
        blank=True,
        verbose_name='截图路径',
        help_text='步骤截图文件路径',
    )
    recognition_result = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='识别结果',
        help_text='图像识别结果数据',
    )
    duration_ms = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='耗时(ms)',
        help_text='步骤执行耗时(毫秒)',
    )
    duration = models.FloatField(
        default=0,
        verbose_name='耗时(秒)',
        help_text='步骤执行耗时(秒)',
    )
    error_message = models.TextField(
        blank=True,
        verbose_name='错误信息',
        help_text='步骤执行失败的错误信息',
    )
    # Task 3.6 (P2-6): 节点错误码, 与 agent AutoResult.error_code 对齐。
    # 用途: WS broadcast 时透传给前端, 前端按 error.codes.<CODE> 映射多语言,
    # 而非把后端 businessMessage (中文) 原文甩给多语言用户 (N192 B1/B2)。
    # 允许为空: 老数据 / 成功步骤 / agent 未上报 error_code 的场景。
    error_code = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='错误码',
        help_text='节点级错误码 (NO_MATCH/LOW_CONFIDENCE/TIMEOUT/...), 与 agent AutoResult.error_code 对齐',
    )
    user_message = models.CharField(
        max_length=512,
        blank=True,
        default='',
        verbose_name='用户友好文案',
        help_text='错误码映射后的用户可读文案, 由 get_user_message() 生成',
    )
    trace_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name='追踪ID',
        help_text='分布式追踪的 Span ID',
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='开始时间',
        help_text='步骤开始执行的时间',
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='完成时间',
        help_text='步骤执行完成的时间',
    )

    class Meta:
        db_table = 'tasks_executionstep'
        ordering = ['step_index']
        verbose_name = '执行步骤'
        verbose_name_plural = '执行步骤'
        unique_together = [('task_result', 'step_index')]

    def __str__(self):
        return f'{self.task_result.task.name} - 步骤{self.step_index}: {self.step_name}'


class ScreenshotFrame(models.Model):
    """截图帧模型，记录执行步骤中的逐帧截图和叠加数据。"""

    execution_step = models.ForeignKey(
        ExecutionStep,
        on_delete=models.CASCADE,
        related_name='screenshot_frames',
        verbose_name='关联执行步骤',
        help_text='关联的执行步骤记录',
    )
    frame_index = models.IntegerField(
        verbose_name='帧序号',
        help_text='帧在步骤中的序号',
    )
    image_path = models.CharField(
        max_length=512,
        verbose_name='图片路径',
        help_text='截图帧图片文件路径',
    )
    timestamp_ms = models.IntegerField(
        verbose_name='时间戳(ms)',
        help_text='帧采集的相对时间戳(毫秒)',
    )
    overlay_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='叠加数据',
        help_text='帧上叠加的标注数据',
    )

    class Meta:
        db_table = 'tasks_screenshotframe'
        ordering = ['frame_index']
        verbose_name = '截图帧'
        verbose_name_plural = '截图帧'
        unique_together = [('execution_step', 'frame_index')]

    def __str__(self):
        return f'{self.execution_step.step_name} - 帧{self.frame_index}'


# TD-061 Plan B Stage 2: Pipeline + PipelineSnapshot moved to pipeline app.
# The physical tables (``pipeline`` and ``pipeline_snapshot``) remain in DB
# and are now owned by pipeline.Pipeline / pipeline.PipelineSnapshot via
# SeparateDatabaseAndState migrations (tasks 0038 + pipeline 0004). FKs on
# TaskExecution.pipeline and MarketplaceItem.pipeline now point to
# 'pipeline.Pipeline'.


class MarketplaceItem(models.Model):
    """任务市场条目"""

    class Status(models.TextChoices):
        PENDING = 'pending', '待审核'
        APPROVED = 'approved', '已发布'
        REJECTED = 'rejected', '已拒绝'
        REMOVED = 'removed', '已下架'

    # Backwards-compat alias for existing query/filter code
    STATUS_CHOICES = Status.choices
    publisher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='published_items',
        verbose_name='发布者',
        help_text='发布该市场条目的用户',
    )
    pipeline = models.ForeignKey(
        'pipeline.Pipeline',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='market_items',
        verbose_name='关联Pipeline',
        help_text='关联的 Pipeline 记录',
    )
    game_name = models.CharField(
        max_length=100,
        default='通用',
        verbose_name='游戏名称',
        help_text='条目所属的游戏名称',
    )
    title = models.CharField(
        max_length=255,
        verbose_name='标题',
        help_text='市场条目的标题',
    )
    description = models.TextField(
        verbose_name='描述',
        help_text='市场条目的详细描述',
    )
    screenshot_urls = models.JSONField(
        default=list,
        verbose_name='截图URL列表',
        help_text='条目展示截图的 URL 列表',
    )
    tags = models.JSONField(
        default=list,
        verbose_name='标签',
        help_text='条目的标签列表',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='状态',
        help_text='状态: pending/approved/rejected/removed',
    )
    download_count = models.IntegerField(
        default=0,
        verbose_name='下载次数',
        help_text='条目被下载的次数',
    )
    rating_avg = models.FloatField(
        default=0,
        verbose_name='平均评分',
        help_text='条目的平均评分',
    )
    rating_count = models.IntegerField(
        default=0,
        verbose_name='评分人数',
        help_text='参与评分的用户数',
    )
    version = models.CharField(
        max_length=50,
        default='1.0',
        verbose_name='版本',
        help_text='条目的版本号',
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
        db_table = 'marketplace_item'
        ordering = ['-download_count', '-rating_avg']
        verbose_name = '市场条目'
        verbose_name_plural = '市场条目'


class MarketplaceReview(models.Model):
    """市场评分与评论"""

    item = models.ForeignKey(
        MarketplaceItem,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name='市场条目',
        help_text='关联的市场条目',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name='用户',
        help_text='发表评论的用户',
    )
    rating = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name='评分(1-5)',
        help_text='用户给出的评分, 范围 1-5',
    )
    comment = models.TextField(
        blank=True,
        default='',
        verbose_name='评论',
        help_text='用户的评论内容',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
        help_text='记录创建的时间戳',
    )

    class Meta:
        db_table = 'marketplace_review'
        unique_together = [['item', 'user']]
        verbose_name = '市场评价'
        verbose_name_plural = '市场评价'


# P-008: Recording migrated to pipeline app (see pipeline.models.Recording).
# F13 (2026-07-31): TraceSpan 表已完全移除 — 模型、API、表均已删除.


class TaskFolder(models.Model):
    """任务文件夹模型，支持嵌套结构。"""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='task_folders',
        verbose_name='所有者',
        help_text='文件夹所属的用户',
    )
    name = models.CharField(
        max_length=200,
        verbose_name='文件夹名称',
        help_text='文件夹的显示名称',
    )
    slug = models.SlugField(
        max_length=200,
        verbose_name='文件夹标识',
        help_text='文件夹的 URL 标识',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='父文件夹',
        help_text='父文件夹, 用于构建嵌套结构',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
        help_text='记录创建的时间戳',
    )

    class Meta:
        db_table = 'tasks_taskfolder'
        ordering = ['name']
        verbose_name = '任务文件夹'
        verbose_name_plural = '任务文件夹'
        unique_together = [('owner', 'slug', 'parent')]

    def __str__(self):
        return self.name
