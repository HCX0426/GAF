from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q

User = get_user_model()


# Default device control method identifiers.
# 'auto' lets the platform handler pick the best method at runtime
# (e.g. WindowsScreenshotHandler falls back to BitBlt, WindowsInputHandler to SendInput).
# Aligns with agent/src/core/config.py default 'screenshot_method: "auto"'.
DEFAULT_SCREENSHOT_METHOD = 'auto'
DEFAULT_INPUT_METHOD = 'auto'


# P-011 multi-game parallel: methods that are safe to run in parallel
# (isolated by hwnd / adb_serial). Unsafe methods (SendInput,
# PseudoBackground, DXGI, minitouch, MaaTouch) rely on global state
# (foreground window / cursor / fixed port) and will collide when
# multiple sessions run concurrently. See Spec A
# (.trae/specs/2026-07-16-multi-game-mode-switch.md, 已随 trae-specs 合并迁移, 见 docs/specs/legacy-trae/) and
# TD-121~125 (docs/archive/active-tech-debt.md).
#
# Case convention (Spec A Phase 2 fix): all method identifiers are stored
# lowercase to match the frontend Select option values and the agent's
# config_generator.py schema. Comparison in resolve_device_methods() uses
# `.lower()` so legacy CamelCase values (e.g. CONTROL_MODE_DEFAULTS
# 'SendInput') are still matched correctly.
MULTI_GAME_SAFE_SCREENSHOT_METHODS = frozenset({
    # Windows: hwnd-isolated
    'printwindow', 'bitblt', 'gdi',
    # ADB: serial-isolated
    'screencap', 'screencap_png', 'nemuipe', 'bluestacks', 'droidcast', 'ld_opengl',
})

MULTI_GAME_SAFE_INPUT_METHODS = frozenset({
    # Windows: hwnd-targeted message posting
    'postmessage', 'sendmessage',
    # ADB: serial-scoped subprocess
    'adb', 'adb_input', 'sendevent',
})

# Methods allowed in single mode but blocked in multi mode.
# resolve_device_methods() will downgrade these to a safe default when
# multi-game mode is enabled.
MULTI_GAME_BLOCKED_SCREENSHOT_METHODS = frozenset({'dxgi'})
MULTI_GAME_BLOCKED_INPUT_METHODS = frozenset({
    'sendinput',          # global foreground + cursor
    'pseudobackground',   # temporary foreground switching
    # minitouch/maatouch: TD-123 fixed (per-serial CRC32 port allocation),
    # but kept blocked in multi mode as a conservative default — PostMessage
    # is the preferred hwnd-isolated method for multi-game scenarios.
    'minitouch',
    'maatouch',
})


class Worker(models.Model):
    """Worker 模型，管理远程/本地 Worker 的注册、心跳和能力信息。"""

    class Status(models.TextChoices):
        ONLINE = 'online', 'Online'
        OFFLINE = 'offline', 'Offline'
        BUSY = 'busy', 'Busy'
        IDLE = 'idle', 'Idle'

    agent_id = models.CharField(
        max_length=64,
        unique=True,
        verbose_name='Agent 唯一标识',
        help_text='Agent 注册时分配的唯一标识符',
    )
    hostname = models.CharField(
        max_length=255,
        verbose_name='主机名',
        help_text='Worker 所在主机的名称',
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP 地址',
        help_text='Worker 所在主机的 IP 地址',
    )
    os_info = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='操作系统信息',
        help_text='Worker 主机的操作系统描述',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OFFLINE,
        verbose_name='状态',
        help_text='状态: online/offline/busy/idle',
    )
    last_heartbeat = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='最后心跳时间',
        help_text='最近一次心跳上报时间',
    )
    active_channel = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='当前活跃 WS channel',
        help_text='spec 2026-08-29 P4: Channels channel_name 唯一连接指纹; '
                  '僵尸连接写入校验: heartbeat/offline 仅当 active_channel 匹配自身才生效',
    )
    cpu_usage = models.FloatField(
        null=True,
        blank=True,
        verbose_name='CPU 使用率 (%)',
        help_text='Worker 进程 CPU 占用百分比',
    )
    memory_usage = models.FloatField(
        null=True,
        blank=True,
        verbose_name='内存使用率 (%)',
        help_text='Worker 进程内存占用百分比',
    )
    screenshot_fps = models.FloatField(
        null=True,
        blank=True,
        verbose_name='截图帧率 (FPS)',
        help_text='Worker 支持的截图帧率',
    )
    capabilities = models.JSONField(
        default=dict,
        verbose_name='能力标签',
        help_text='Worker 支持的能力标签字典',
    )
    worker_token_hash = models.CharField(
        max_length=64,
        db_index=True,
        null=True,
        blank=True,
        verbose_name='鉴权 Token 哈希 (SHA-256)',
        help_text='C4: SHA-256(token) 十六进制摘要，用于数据库查找。',
    )
    worker_token_preview = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='Token 预览',
        help_text='C4: 前后各 4 位字符预览，用于列表展示，不暴露完整 Token。',
    )
    is_local = models.BooleanField(
        default=False,
        verbose_name='是否本地 Worker',
        help_text='标记是否为本地 Worker',
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
        app_label = 'workers'
        db_table = 'workers_worker'
        ordering = ['-id']
        verbose_name = 'Worker'
        verbose_name_plural = 'Worker'
        indexes = [
            models.Index(fields=['status'], name='idx_agent_status'),
        ]

    def __str__(self):
        return f'{self.agent_id} ({self.get_status_display()})'


class Device(models.Model):
    """Device 模型，管理接入的自动化设备（Windows 窗口 + 模拟器/ADB）。"""

    class DeviceType(models.TextChoices):
        WINDOWS = 'windows', 'Windows'
        EMULATOR = 'emulator', '模拟器'

    class Status(models.TextChoices):
        ONLINE = 'online', '在线'
        OFFLINE = 'offline', '离线'
        BUSY = 'busy', '忙碌'
        ERROR = 'error', '错误'

    class ControlMode(models.TextChoices):
        # v3 §2.8.1: 'auto' = inherit from GameProfile; concrete modes override.
        AUTO = 'auto', '自动（继承）'
        FOREGROUND = 'foreground', '前台'
        BACKGROUND = 'background', '后台'
        PSEUDO_BACKGROUND = 'pseudo_background', '伪后台'

    # Default concrete method mappings for each control mode.
    # screenshot_method: 'auto' lets the platform handler pick at runtime.
    # pseudo_background pairs PrintWindow (occlusion-resistant screenshot)
    # with SendInput (foreground input) because the handler temporarily
    # foregrounds the window on every click.
    CONTROL_MODE_DEFAULTS = {
        ControlMode.FOREGROUND: {
            'screenshot_method': 'auto',
            'input_method': 'SendInput',
        },
        ControlMode.BACKGROUND: {
            'screenshot_method': 'auto',
            'input_method': 'PostMessage',
        },
        ControlMode.PSEUDO_BACKGROUND: {
            'screenshot_method': 'printwindow',
            'input_method': 'SendInput',
        },
    }

    name = models.CharField(
        max_length=255,
        verbose_name='设备名称',
        help_text='用户自定义的设备显示名称',
    )
    device_type = models.CharField(
        max_length=20,
        choices=DeviceType.choices,
        verbose_name='设备类型',
        help_text='设备类型: windows/emulator',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OFFLINE,
        verbose_name='状态',
        help_text='状态: online/offline/busy/error',
    )
    agent = models.ForeignKey(
        "workers.Worker",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='devices',
        verbose_name='关联 Agent',
        help_text='设备所属的 Agent 记录',
    )
    resolution_width = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='分辨率宽',
        help_text='设备屏幕水平像素数',
    )
    resolution_height = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='分辨率高',
        help_text='设备屏幕垂直像素数',
    )
    screenshot_fps = models.FloatField(
        default=0,
        verbose_name='截图帧率',
        help_text='设备支持的截图帧率',
    )
    extra_info = models.JSONField(
        default=dict,
        verbose_name='扩展信息',
        help_text='设备的额外扩展信息',
    )
    locked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='locked_devices',
        verbose_name='锁定者',
        help_text='当前锁定设备的用户',
    )
    locked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='锁定时间',
        help_text='设备被锁定的时间戳',
    )
    control_mode = models.CharField(
        max_length=32,
        choices=ControlMode.choices,
        default=ControlMode.AUTO,
        verbose_name='控制模式',
        help_text='设备控制模式：auto（继承 GameProfile）/前台/后台/伪后台。'
                  '伪后台会在点击时临时前台目标窗口并恢复',
    )
    screenshot_method = models.CharField(
        max_length=64,
        blank=True,
        default=DEFAULT_SCREENSHOT_METHOD,
        verbose_name='截图方式',
        help_text='设备使用的截图方式标识，"auto" 表示由平台 handler 自动选择；空值时由控制模式派生',
    )
    input_method = models.CharField(
        max_length=64,
        blank=True,
        default=DEFAULT_INPUT_METHOD,
        verbose_name='输入方式',
        help_text='设备使用的输入方式标识，"auto" 表示由平台 handler 自动选择；空值时由控制模式派生',
    )
    device_stats = models.JSONField(
        default=dict,
        verbose_name='设备性能统计',
        help_text='设备性能统计数据',
    )
    adb_serial = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='ADB 序列号',
        help_text='模拟器 ADB 设备序列号',
    )
    window_handle = models.CharField(
        max_length=64,
        blank=True,
        default='',
        verbose_name='窗口句柄',
        help_text='Windows 窗口句柄标识',
    )
    emulator_brand = models.CharField(
        max_length=32,
        blank=True,
        default='',
        verbose_name='模拟器品牌',
        help_text='模拟器品牌, 如 LDPlayer/Nox',
    )
    system_version = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='系统版本',
        help_text='设备操作系统版本号',
    )
    battery_level = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='电池电量 (0-100)',
        help_text='设备电池电量百分比',
    )
    last_heartbeat = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='最后心跳时间',
        help_text='设备最近一次心跳上报时间',
    )
    game_profile = models.ForeignKey(
        'gamestate.GameProfile',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='devices',
        verbose_name='所属游戏档案',
        help_text='R37-P1: 设备所属的游戏档案（nullable，兼容未识别窗口）',
    )
    game_account = models.ForeignKey(
        'accounts.GameAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='devices',
        verbose_name='运行时绑定账户',
        help_text='Window-centric: 运行时绑定当前执行的账户，'
                  '可随时切换（如换服、换号）',
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
        app_label = 'workers'
        db_table = 'devices'
        ordering = ['-id']
        verbose_name = '设备'
        verbose_name_plural = '设备'
        indexes = [
            models.Index(fields=['device_type'], name='idx_device_type'),
            models.Index(fields=['status'], name='idx_device_status'),
            models.Index(fields=['agent'], name='idx_device_agent'),
            models.Index(fields=['locked_by'], name='idx_device_locked_by'),
            models.Index(fields=['game_profile'], name='idx_device_game_profile'),
            models.Index(fields=['game_account'], name='idx_device_game_account'),
        ]
        constraints = [
            # R37-P0: prevent duplicate Windows devices by window_handle.
            # Partial unique index — only enforced when window_handle is non-empty.
            # Empty window_handle (emulator or unidentified window) is allowed to repeat.
            models.UniqueConstraint(
                fields=['device_type', 'window_handle'],
                condition=~Q(window_handle=''),
                name='unique_device_type_window_handle',
            ),
            # R37-P0: prevent duplicate emulator devices by adb_serial.
            # Partial unique index — only enforced when adb_serial is non-empty.
            models.UniqueConstraint(
                fields=['device_type', 'adb_serial'],
                condition=~Q(adb_serial=''),
                name='unique_device_type_adb_serial',
            ),
        ]

    def __str__(self):
        return f'{self.name} ({self.get_device_type_display()})'

    # ------------------------------------------------------------------
    # Domain methods — thin wrappers that set fields and call save().
    # The agents.signals.broadcast_device_update post_save signal fires
    # automatically on each save, broadcasting device.updated to WS clients
    # so the frontend refetches without explicit broadcast calls.
    # ------------------------------------------------------------------

    def update_status(self, new_status: 'Device.Status') -> None:
        """Update device status and persist.

        The post_save signal broadcasts device.updated so the frontend
        refreshes the device list automatically.

        Args:
            new_status: A ``Device.Status`` enum member (or its string
                value). ``ValueError`` is raised for values outside the
                enum's allowed choices (``online``/``offline``/``busy``/
                ``error``), preventing typos like ``"erorr"`` from being
                silently persisted.
        """
        valid_values = {choice[0] for choice in Device.Status.choices}
        if new_status not in valid_values:
            raise ValueError(
                f"Invalid device status: {new_status!r}. "
                f"Must be one of {sorted(valid_values)}."
            )
        self.status = new_status
        self.save(update_fields=["status", "updated_at"])

    def update_resolution(self, width: int, height: int) -> None:
        """Update device resolution and persist."""
        self.resolution_width = width
        self.resolution_height = height
        self.save(update_fields=["resolution_width", "resolution_height", "updated_at"])

    def update_window_handle(self, hwnd: str) -> None:
        """Update device window handle and persist."""
        self.window_handle = hwnd
        self.save(update_fields=["window_handle", "updated_at"])

    def update_screenshot_stats(self, method: str, fps: float, latency_ms: float) -> None:
        """Update screenshot method/fps/latency and persist.

        Also writes device_stats so the DeviceCard displays consistent
        latency/fps values (both read from device_stats, not 1000/fps).
        """
        self.screenshot_method = method
        self.screenshot_fps = fps
        stats = dict(self.device_stats or {})
        stats["screenshot_latency_avg_ms"] = latency_ms
        stats["screenshot_fps"] = fps
        stats["screenshot_method"] = method
        self.device_stats = stats
        self.save(update_fields=[
            "screenshot_method", "screenshot_fps", "device_stats", "updated_at",
        ])

    def update_capabilities(self, methods: list) -> None:
        """Cache available screenshot methods to extra_info and persist."""
        extra = dict(self.extra_info or {})
        extra["available_methods"] = methods
        self.extra_info = extra
        self.save(update_fields=["extra_info", "updated_at"])

    @classmethod
    def get_control_mode_defaults(cls, control_mode: str | ControlMode) -> dict:
        """Return default concrete methods for a control mode.

        Returns a dict with ``screenshot_method`` and ``input_method``.
        Unknown modes fall back to pseudo_background.
        """
        # Normalize str input to ControlMode enum so the lookup is type-safe
        # (CONTROL_MODE_DEFAULTS is keyed by ControlMode, not str).
        if isinstance(control_mode, str):
            try:
                control_mode = cls.ControlMode(control_mode)
            except ValueError:
                control_mode = cls.ControlMode.PSEUDO_BACKGROUND
        return cls.CONTROL_MODE_DEFAULTS.get(control_mode, cls.CONTROL_MODE_DEFAULTS[cls.ControlMode.PSEUDO_BACKGROUND])

    @classmethod
    def derive_control_mode(cls, screenshot_method: str, input_method: str) -> str:
        """Derive a control mode from existing concrete method values.

        Used by the data migration to populate ``control_mode`` for rows
        that predate the field. The heuristic prefers background when
        PostMessage is used, pseudo_background when SendInput is paired
        with occlusion-resistant screenshot methods, and foreground for
        the remaining SendInput cases.
        """
        sm = (screenshot_method or '').lower()
        im = (input_method or '').lower()
        if im == 'postmessage':
            return cls.ControlMode.BACKGROUND
        if im == 'sendinput' and sm in ('printwindow', 'print', 'auto', ''):
            return cls.ControlMode.PSEUDO_BACKGROUND
        if im == 'sendinput':
            return cls.ControlMode.FOREGROUND
        # Fallback for unexpected/empty combinations: safest game-automation default
        return cls.ControlMode.PSEUDO_BACKGROUND

    def apply_control_mode_defaults(self) -> None:
        """Populate empty screenshot_method/input_method from control_mode.

        Call this before saving when the user only supplied control_mode.
        Existing overrides are preserved.
        """
        defaults = self.get_control_mode_defaults(self.control_mode)
        if not self.screenshot_method:
            self.screenshot_method = defaults['screenshot_method']
        if not self.input_method:
            self.input_method = defaults['input_method']


def _multi_game_safe_fallback(device: 'Device') -> tuple[str, str]:
    """Return (screenshot_method, input_method) safe defaults for the device type.

    Used by resolve_device_methods() when multi-game mode blocks the
    resolved method. Windows devices fall back to PostMessage + PrintWindow
    (hwnd-isolated); emulator devices fall back to adb_input + screencap
    (serial-isolated).

    Values are lowercase to match the frontend Select option convention
    (Spec A Phase 2 case fix).
    """
    if device.device_type == Device.DeviceType.WINDOWS:
        return 'printwindow', 'postmessage'
    return 'screencap', 'adb_input'


def resolve_device_methods(device: 'Device') -> dict:
    """Resolve device screenshot/input/control methods with GameProfile inheritance.

    v3 §2.8.1 unified 'auto' semantics: when a Device field is 'auto' and the
    Device is bound to a GameProfile, inherit the GameProfile's default value.
    Concrete values on the Device always override. When no GameProfile is bound
    (or the profile has no default), the Device's own value is returned as-is
    so the platform handler picks at runtime.

    P-011 multi-game parallel (Spec A): when the `unattended_multi_game_mode`
    FeatureFlag is enabled, methods that are unsafe for parallel execution
    (SendInput, PseudoBackground, DXGI, minitouch, MaaTouch) are downgraded
    to a parallel-safe default (PostMessage/SendMessage + PrintWindow/BitBlt
    for Windows; adb_input + screencap for emulator). The original resolved
    value is preserved in `original_*` keys for diagnostics.

    Returns a dict with keys: screenshot_method, input_method, control_mode,
    multi_game_restricted, original_screenshot_method, original_input_method.
    """
    profile = device.game_profile
    if not profile:
        # No profile → use Device's own values (platform picks at runtime)
        screenshot = device.screenshot_method
        input_method = device.input_method
        control_mode = device.control_mode
    else:
        # 'auto' inherits from GameProfile; specific value overrides
        screenshot = (
            profile.default_screenshot_method
            if device.screenshot_method == DEFAULT_SCREENSHOT_METHOD and profile.default_screenshot_method
            else device.screenshot_method
        )
        input_method = (
            profile.default_input_method
            if device.input_method == DEFAULT_INPUT_METHOD and profile.default_input_method
            else device.input_method
        )
        # control_mode: v3 unified 'auto' inheritance
        control_mode = (
            profile.default_control_mode
            if device.control_mode == Device.ControlMode.AUTO and profile.default_control_mode
            else device.control_mode
        )

    # P-011 multi-game parallel: enforce safety whitelist.
    # Lazy import to avoid circular import (settings app may import agents).
    # Comparison uses `.lower()` so both lowercase (frontend convention) and
    # legacy CamelCase (CONTROL_MODE_DEFAULTS) values are matched.
    from settings.feature_flags import is_multi_game_mode_enabled

    multi_game_restricted = is_multi_game_mode_enabled()
    original_screenshot = screenshot
    original_input = input_method

    if multi_game_restricted:
        safe_screenshot, safe_input = _multi_game_safe_fallback(device)
        if (screenshot or '').lower() in MULTI_GAME_BLOCKED_SCREENSHOT_METHODS:
            screenshot = safe_screenshot
        if (input_method or '').lower() in MULTI_GAME_BLOCKED_INPUT_METHODS:
            input_method = safe_input

    return {
        'screenshot_method': screenshot,
        'input_method': input_method,
        'control_mode': control_mode,
        'multi_game_restricted': multi_game_restricted,
        'original_screenshot_method': original_screenshot,
        'original_input_method': original_input,
    }


class DeviceGroup(models.Model):
    """DeviceGroup 模型，管理用户自定义的设备分组（支持树形结构）。"""

    name = models.CharField(
        max_length=255,
        verbose_name='分组名称',
        help_text='设备分组的显示名称',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='device_groups',
        verbose_name='所属用户',
        help_text='分组所属的用户',
    )
    parent = models.ForeignKey(
        "workers.DeviceGroup",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='父分组',
        help_text='父级分组, 用于构建树形结构',
    )
    devices = models.ManyToManyField(
        "workers.Device",
        related_name='groups',
        blank=True,
        verbose_name='设备列表',
        help_text='分组包含的设备集合',
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
        app_label = 'workers'
        db_table = 'workers_devicegroup'
        ordering = ['-id']
        verbose_name = '设备分组'
        verbose_name_plural = '设备分组'

    def __str__(self):
        return f'{self.name} ({self.user.username})'
