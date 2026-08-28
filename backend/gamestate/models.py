from django.db import models


class GameProfile(models.Model):
    """游戏适配档案，存储游戏相关的自动化配置信息。

    R37-P3 Stage 7 Task 20b: migrated from tasks app (TD-039). Belongs in
    gamestate because it is game-wide configuration (screenshot methods, OCR
    language, popup templates, resolution strategy) consumed by the game-state
    tracking layer, device auto-binding, and resource-pack association.
    db_table kept as 'game_profile' — zero data migration.
    """

    game_name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='游戏名称',
        help_text='游戏的唯一名称',
    )
    screenshot_methods = models.JSONField(
        default=list,
        verbose_name='推荐截图方式排序列表',
        help_text='按优先级排序的截图方式列表',
    )
    ocr_language = models.CharField(
        max_length=50,
        default='ch',
        verbose_name='OCR 语言',
        help_text='OCR 识别使用的语言代码',
    )
    ui_reference_resolution = models.JSONField(
        default=dict,
        verbose_name='UI参考分辨率 {w, h}',
        help_text='UI 设计的参考分辨率',
    )
    known_popups = models.JSONField(
        default=list,
        verbose_name='已知弹窗模板列表',
        help_text='游戏中已知弹窗的模板列表',
    )
    resolution_strategy = models.CharField(
        max_length=50,
        default='scale',
        verbose_name='分辨率适配策略',
        help_text='分辨率适配策略标识',
    )

    class ControlMode(models.TextChoices):
        FOREGROUND = 'foreground', '前台模式'
        BACKGROUND = 'background', '后台模式'
        PSEUDO_BACKGROUND = 'pseudo_background', '伪后台模式'

    default_routine = models.ForeignKey(
        'pipeline.TaskChain',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='default_for_profiles',
        verbose_name='默认任务链',
        help_text='Window-centric: 日常默认任务链，'
                  '新窗口绑 GameProfile 后自动继承',
    )
    routine_path = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='routine.json 路径',
        help_text='TD-113: 该档案对应的 routine.json 文件路径，'
                  '如 resources/BrownDust-II/routine.json。'
                  'convert_routine_to_chain 从此字段读取，'
                  '支持多 GameProfile 指向不同 routine.json',
    )
    default_screenshot_method = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='默认截图方式',
        help_text='Window-centric: 该游戏推荐的默认截图方式，'
                  'Device.screenshot_method 为空时继承',
    )
    default_input_method = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='默认输入方式',
        help_text='Window-centric: 该游戏推荐的默认输入方式，'
                  'Device.input_method 为空时继承',
    )
    default_control_mode = models.CharField(
        max_length=30,
        blank=True,
        default='',
        choices=ControlMode.choices,
        verbose_name='默认控制模式',
        help_text='Window-centric: 前台/后台/伪后台，'
                  'Device.control_mode 为空时继承',
    )
    device_type_hint = models.CharField(
        max_length=20,
        blank=True,
        default='',
        choices=[('windows', 'Windows 窗口游戏'), ('emulator', '模拟器游戏')],
        verbose_name='设备类型提示',
        help_text='明确该游戏运行的设备类型，避免设备绑定误选。'
                  'windows = 原生 Windows 窗口游戏 (通过 window_title/hwnd 匹配)；'
                  'emulator = 安卓模拟器游戏 (通过 adb_serial 匹配)。'
                  '留空表示未指定，由 Agent 上报的 device_type 决定。',
    )
    allowed_device_types = models.JSONField(
        default=list,
        blank=True,
        verbose_name='可操作的窗口类型列表',
        help_text='N197: 该游戏档案允许操作的窗口类型列表。'
                  '如 ["windows", "emulator"] 表示同时支持 Windows 窗口和模拟器。'
                  '空列表表示不限制（兼容所有类型）。'
                  '设备绑定和任务分发时据此校验设备类型是否匹配。',
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
        db_table = 'game_profile'
        ordering = ['game_name']
        verbose_name = '游戏档案'
        verbose_name_plural = '游戏档案'

    def __str__(self):
        return self.game_name


class GameStateRule(models.Model):
    """游戏状态规则模型，定义用于检测游戏状态的识别规则和触发动作。"""

    name = models.CharField(
        max_length=255,
        verbose_name='规则名称',
    )
    game_name = models.CharField(
        max_length=255,
        verbose_name='游戏名称',
    )
    tracker_type = models.CharField(
        max_length=50,
        verbose_name='跟踪器类型',
    )
    ocr_region = models.JSONField(
        default=dict,
        verbose_name='OCR 区域',
    )
    ocr_regex = models.CharField(
        max_length=500,
        blank=True,
        verbose_name='OCR 正则',
    )
    threshold = models.FloatField(
        null=True,
        blank=True,
        verbose_name='阈值',
    )
    threshold_direction = models.CharField(
        max_length=10,
        blank=True,
        verbose_name='阈值方向',
    )
    trigger_action = models.JSONField(
        default=dict,
        verbose_name='触发动作',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='是否启用',
    )

    class Meta:
        db_table = 'gamestate_gamestaterule'
        ordering = ['-id']
        verbose_name = '游戏状态规则'
        verbose_name_plural = '游戏状态规则'

    def __str__(self):
        return f'{self.name} ({self.game_name})'


class GameStateSnapshot(models.Model):
    """游戏状态快照模型，记录规则触发时的游戏状态数据和识别结果。"""

    rule = models.ForeignKey(
        GameStateRule,
        on_delete=models.CASCADE,
        related_name='snapshots',
        verbose_name='关联规则',
    )
    value = models.FloatField(
        verbose_name='检测值',
    )
    raw_text = models.TextField(
        blank=True,
        verbose_name='原始文本',
    )
    triggered = models.BooleanField(
        default=False,
        verbose_name='是否触发',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
    )

    class Meta:
        db_table = 'gamestate_gamestatesnapshot'
        ordering = ['-created_at']
        verbose_name = '游戏状态快照'
        verbose_name_plural = '游戏状态快照'

    def __str__(self):
        return f'{self.rule.name} - {"触发" if self.triggered else "未触发"}'


class GameVersionCheck(models.Model):
    """
    游戏版本更新检测

    检测游戏客户端更新（EXE/资源文件变化），自动标记受影响的模板为"待验证"。
    用于无人值守场景：游戏更新后自动暂停相关任务，避免使用过期模板。
    """
    game_name = models.CharField(max_length=100, verbose_name='游戏名称')
    resource_pack = models.ForeignKey(
        'resources.ResourcePack',
        on_delete=models.CASCADE,
        verbose_name='关联资源包'
    )
    previous_version_hash = models.CharField(
        max_length=64,
        verbose_name='更新前版本 Hash'
    )
    current_version_hash = models.CharField(
        max_length=64,
        verbose_name='更新后版本 Hash'
    )
    files_changed = models.JSONField(
        default=list,
        verbose_name='变更文件列表'
    )
    detected_at = models.DateTimeField(auto_now_add=True, verbose_name='检测时间')
    affected_templates = models.ManyToManyField(
        'resources.Template',
        related_name='version_checks',
        verbose_name='受影响模板'
    )

    class Meta:
        db_table = 'gamestate_game_version_check'
        verbose_name = '游戏版本更新检测'
        verbose_name_plural = verbose_name
        ordering = ['-detected_at']

    def __str__(self):
        return f'{self.game_name} v{self.previous_version_hash[:8]} → v{self.current_version_hash[:8]}'
