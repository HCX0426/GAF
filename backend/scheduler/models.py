from django.db import models


class GameAccountRotation(models.Model):
    """
    游戏账户轮换规则

    定义多账户之间的切换策略，支持：
    - sequential: 顺序循环（账户A→B→C→A→...）
    - random: 随机选择
    - by_stamina: 按体力余量（优先选体力最多的）
    - by_last_executed: 最久未执行优先
    """
    class Strategy(models.TextChoices):
        SEQUENTIAL = 'sequential', '顺序循环'
        RANDOM = 'random', '随机'
        BY_STAMINA = 'by_stamina', '按体力余量'
        BY_LAST_EXECUTED = 'by_last_executed', '最久未执行优先'

    name = models.CharField(max_length=200, verbose_name='规则名称')
    rotation_strategy = models.CharField(
        max_length=50,
        choices=Strategy.choices,
        default=Strategy.SEQUENTIAL,
        verbose_name='轮换策略'
    )
    accounts = models.ManyToManyField(
        'accounts.GameAccount',
        related_name='rotation_rules',
        verbose_name='关联账户'
    )
    switch_interval_seconds = models.IntegerField(
        default=10,
        verbose_name='切换间隔（秒）'
    )
    auto_skip_blocked = models.BooleanField(
        default=True,
        verbose_name='自动跳过异常账户'
    )
    is_active = models.BooleanField(default=True, verbose_name='启用')
    owner = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        default=None,
        related_name='rotation_rules',
        verbose_name='所有者',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'scheduler_game_account_rotation'
        verbose_name = '游戏账户轮换规则'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.get_rotation_strategy_display()})'


class PreflightCheck(models.Model):
    """
    启动前预热检查记录

    无人值守启动前的逐项预检，每项检查产生一条记录：
    - device_online: 设备是否在线
    - account_valid: 账户是否有效
    - resource_ready: 资源包是否加载就绪
    - agent_connected: Agent 连接是否正常
    - schedule_valid: 调度规则是否有效
    """
    class CheckType(models.TextChoices):
        DEVICE_ONLINE = 'device_online', '设备在线'
        ACCOUNT_VALID = 'account_valid', '账户有效'
        RESOURCE_READY = 'resource_ready', '资源就绪'
        AGENT_CONNECTED = 'agent_connected', 'Agent 连接'
        SCHEDULE_VALID = 'schedule_valid', '调度规则有效'

    class Status(models.TextChoices):
        PENDING = 'pending', '等待检查'
        PASS = 'pass', '通过'
        FAIL = 'fail', '失败'
        WARNING = 'warning', '警告'

    check_type = models.CharField(
        max_length=50,
        choices=CheckType.choices,
        verbose_name='检查类型'
    )
    target_id = models.CharField(max_length=100, verbose_name='目标 ID')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='检查状态'
    )
    message = models.TextField(blank=True, verbose_name='检查信息')
    checked_at = models.DateTimeField(auto_now_add=True, verbose_name='检查时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'scheduler_preflight_check'
        verbose_name = '预热检查记录'
        verbose_name_plural = verbose_name
        ordering = ['-checked_at']

    def __str__(self):
        return f'{self.get_check_type_display()} → {self.get_status_display()}'


class RecoveryLog(models.Model):
    """
    无人值守恢复操作日志

    五层恢复机制：
    - step（步骤级）：单步失败→重试 N 次
    - task（任务级）：连续失败→跳过/重启/切换
    - app（应用级）：游戏卡死→重启/重新登录
    - device（设备级）：ADB 断开→重启模拟器
    - system（系统级）：Agent 无响应→通知/离线标记
    """
    class Level(models.TextChoices):
        STEP = 'step', '步骤级'
        TASK = 'task', '任务级'
        APP = 'app', '应用级'
        DEVICE = 'device', '设备级'
        SYSTEM = 'system', '系统级'

    recovery_level = models.CharField(
        max_length=20,
        choices=Level.choices,
        verbose_name='恢复级别'
    )
    trigger_event = models.CharField(max_length=100, verbose_name='触发事件')
    action_taken = models.CharField(max_length=100, verbose_name='执行动作')
    success = models.BooleanField(default=False, verbose_name='是否成功')
    details = models.JSONField(default=dict, verbose_name='详细信息')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'scheduler_recovery_log'
        verbose_name = '恢复操作日志'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        status = '✅' if self.success else '❌'
        return f'[{self.get_recovery_level_display()}] {self.trigger_event} → {self.action_taken} {status}'


class TimeWindow(models.Model):
    """
    无人值守时间窗口

    定义无人值守执行的有效时间段，窗口外的任何触发将被忽略或排队。
    支持多个时间窗口，每个窗口可指定适用的星期几。
    """

    start_time = models.TimeField(verbose_name='窗口开始时间')
    end_time = models.TimeField(verbose_name='窗口结束时间')
    days_of_week = models.JSONField(
        default=list,
        verbose_name='适用星期',
        help_text='星期几列表，0=周日 6=周六，空数组表示每天',
    )
    is_enabled = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'scheduler_time_window'
        verbose_name = '时间窗口'
        verbose_name_plural = verbose_name
        ordering = ['start_time']

    def __str__(self):
        days = ','.join(str(d) for d in self.days_of_week) if self.days_of_week else '每天'
        return f'{self.start_time}-{self.end_time} [{days}] {"✓" if self.is_enabled else "✗"}'


class WarmupConfig(models.Model):
    """
    设备预热配置

    定义无人值守启动前对设备执行的预热流程。
    Upsert 模式：整个系统只有一条配置记录。
    """

    class FailureStrategy(models.TextChoices):
        SKIP_DEVICE = 'skip_device', '跳过该设备'
        RETRY_THEN_SKIP = 'retry_then_skip', '重试后跳过'
        ABORT_ALL = 'abort_all', '中止全部'

    steps = models.JSONField(
        default=list,
        verbose_name='预热步骤列表',
    )
    global_timeout_seconds = models.IntegerField(
        default=600,
        verbose_name='全局超时（秒）',
    )
    failure_strategy = models.CharField(
        max_length=20,
        choices=FailureStrategy.choices,
        default=FailureStrategy.SKIP_DEVICE,
        verbose_name='失败策略',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'scheduler_warmup_config'
        verbose_name = '设备预热配置'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'预热配置 ({len(self.steps)} 步骤, {self.get_failure_strategy_display()})'


class AutoStopCondition(models.Model):
    """
    自动停止条件

    定义自动停止无人值守执行的条件规则。
    Upsert 模式：每个条件类型一条记录。
    """

    class ConditionType(models.TextChoices):
        CONSECUTIVE_FAILURES = 'consecutive_failures', '连续失败 N 次'
        DEVICE_OFFLINE = 'device_offline', '设备离线超过 N 分钟'
        ALL_COMPLETED = 'all_completed', '所有账户均已执行完毕'
        WINDOW_END = 'window_end', '时间窗口结束'
        MANUAL_STOP = 'manual_stop', '手动停止'
        RESOURCE_INSUFFICIENT = 'resource_insufficient', '资源包不足'

    class Action(models.TextChoices):
        STOP_ALL = 'stop_all', '停止所有'
        STOP_DEVICE = 'stop_device', '仅停止该设备'
        NOTIFY_CONTINUE = 'notify_continue', '发送通知并继续'

    condition_type = models.CharField(
        max_length=50,
        choices=ConditionType.choices,
        unique=True,
        verbose_name='条件类型',
    )
    is_enabled = models.BooleanField(default=True, verbose_name='是否启用')
    threshold = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='阈值',
        help_text='连续失败次数、离线分钟数等',
    )
    action = models.CharField(
        max_length=20,
        choices=Action.choices,
        default=Action.STOP_ALL,
        verbose_name='触发动作',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'scheduler_auto_stop_condition'
        verbose_name = '自动停止条件'
        verbose_name_plural = verbose_name
        ordering = ['condition_type']

    def __str__(self):
        return f'{self.get_condition_type_display()} → {self.get_action_display()}'


class UnattendedSession(models.Model):
    """Unattended mode session state (P-009 Phase 1, P-011 multi-session).

    Replaces the in-memory ``_unattended_session`` dict so that state
    survives worker restarts and is consistent across Celery + Daphne +
    runserver workers.

    P-011 multi-session: the singleton constraint has been lifted. Multiple
    RUNNING/PAUSED sessions may coexist, scoped by ``game_profile`` — at
    most one RUNNING/PAUSED session per game_profile (enforced in
    ``unattended_start_view`` via 409 check). Sessions without a
    game_profile (legacy data) are still tolerated.
    """

    class Status(models.TextChoices):
        INIT = 'init', '初始化'
        RUNNING = 'running', '运行中'
        PAUSED = 'paused', '已暂停'
        STOPPING = 'stopping', '停止中'
        STOPPED = 'stopped', '已停止'
        FAILED = 'failed', '异常终止'

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INIT,
        verbose_name='会话状态',
    )
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='启动时间')
    stopped_at = models.DateTimeField(null=True, blank=True, verbose_name='停止时间')
    stop_reason = models.CharField(
        max_length=200, blank=True, default='', verbose_name='停止原因',
    )
    total_devices = models.IntegerField(default=0, verbose_name='设备总数')
    total_accounts = models.IntegerField(default=0, verbose_name='派发账户数')
    triggered_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='unattended_sessions',
        verbose_name='触发用户',
    )
    # P-011: scope this session to a GameProfile. Nullable for backward
    # compatibility with legacy sessions (pre-P-011 data has no FK).
    # Uniqueness constraint: at most one RUNNING/PAUSED session per
    # game_profile (enforced in unattended_start_view via 409 check, not
    # via DB unique_together because status is non-unique).
    game_profile = models.ForeignKey(
        'gamestate.GameProfile',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='unattended_sessions',
        verbose_name='关联游戏档案',
        help_text='P-011: 多 session 并行分组边界，按游戏档案隔离',
    )
    paused_at = models.DateTimeField(null=True, blank=True, verbose_name='暂停时间')
    # P-009 Phase 2: rotation + dispatch tracking
    # Accounts already dispatched in this session (JSON list of account IDs).
    # Used to skip already-dispatched accounts in the rotation loop.
    dispatched_account_ids = models.JSONField(
        default=list, blank=True, verbose_name='已派发账户 ID 列表',
    )
    # Active chain executions dispatched by this session. Completed ones
    # are removed via the post_save signal (scheduler/signals.py).
    active_chain_executions = models.ManyToManyField(
        'pipeline.TaskChainExecution',
        blank=True,
        related_name='unattended_sessions',
        verbose_name='活跃任务链执行',
    )
    # Rotation rule snapshot at start time. If None, tick falls back to
    # device.game_account (legacy one-shot behavior).
    rotation_rule = models.ForeignKey(
        'scheduler.GameAccountRotation',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='sessions',
        verbose_name='轮换规则',
    )
    # TD-400 (2026-08-26): loop rotation — when enabled, an account whose
    # chain execution finished is returned to the rotation pool so the same
    # session keeps dispatching rounds (persistent unattended grinding).
    # all_completed AutoStop is disabled in loop mode (a finished round must
    # NOT stop the session); stop via manual / time-window / consecutive
    # failures instead.
    loop_rotation = models.BooleanField(
        default=False, verbose_name='循环轮换',
        help_text='完成一轮后归还账户继续派发，配合轮换规则使用；循环模式不触发 all_completed 自动停止',
    )
    rotation_index = models.IntegerField(
        default=0, verbose_name='轮换游标',
        help_text='loop_rotation 模式下的公平轮换游标：每次派发后自增，保证多账户轮流而非总选队首',
    )
    # P-009 Phase 3: consecutive chain-execution failure counter.
    # Incremented when a dispatched chain execution reaches FAILED state,
    # reset to 0 when one reaches SUCCESS. Fed into check_auto_stop_conditions
    # to decide whether to stop the session.
    failed_count = models.IntegerField(
        default=0, verbose_name='连续失败计数',
    )
    # P-009 Phase 3: count of chain executions that reached a terminal state
    # (SUCCESS/FAILED/CANCELLED). Used by the all_completed AutoStop check
    # together with dispatched_account_ids to determine if the session has
    # finished dispatching every account.
    completed_chain_count = models.IntegerField(
        default=0, verbose_name='已完成任务链数',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        db_table = 'scheduler_unattended_session'
        verbose_name = '无人值守会话'
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        gp = self.game_profile.game_name if self.game_profile else 'global'
        return f'UnattendedSession#{self.id} ({self.status}, {gp})'
