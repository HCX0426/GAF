from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """用户模型，继承 Django 内置 AbstractUser，增加角色、OAuth、2FA 和密码管理字段。"""

    class Role(models.TextChoices):
        VIEWER = 'viewer', 'Viewer'
        OPERATOR = 'operator', 'Operator'
        ADMIN = 'admin', 'Admin'

    class OAuthProvider(models.TextChoices):
        GITHUB = 'github', 'GitHub'
        GOOGLE = 'google', 'Google'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.VIEWER,
        verbose_name='角色',
        help_text='角色: viewer/operator/admin',
    )
    must_change_password = models.BooleanField(
        default=False,
        verbose_name='首次登录需修改密码',
        help_text='标记用户下次登录是否需修改密码',
    )
    oauth_provider = models.CharField(
        max_length=20,
        choices=OAuthProvider.choices,
        null=True,
        blank=True,
        verbose_name='OAuth 提供商',
        help_text='OAuth 登录的提供商',
    )
    oauth_uid = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='OAuth 用户ID',
        help_text='OAuth 提供商返回的用户唯一 ID',
    )
    totp_secret = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        verbose_name='TOTP 密钥',
        help_text='TOTP 2FA 的密钥',
    )
    totp_enabled = models.BooleanField(
        default=False,
        verbose_name='2FA 已启用',
        help_text='标记用户是否已启用 2FA',
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
        db_table = 'accounts_user'
        ordering = ['-id']
        verbose_name = '用户'
        verbose_name_plural = '用户'
        indexes = [
            models.Index(fields=['oauth_provider', 'oauth_uid'], name='idx_user_oauth'),
        ]

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'


class GameAccount(models.Model):
    """游戏账号模型，存储用户关联的游戏账号信息，密码以 AES-256-GCM 加密存储。"""

    LOGIN_METHODS = [
        ('password', '密码登录'),
        ('qr_scan', '扫码登录'),
        ('token', 'Token 登录'),
        ('steam', 'Steam 登录'),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='game_accounts',
        verbose_name='所有者',
        help_text='账号所属的用户',
    )
    # TD-259 #23 → spec 2026-08-29-game-account-game-name-retirement: game_name 字符串
    # 弱关联已退役 (P3 迁移 drop), 唯一游戏维度 = game_profile FK.
    game_profile = models.ForeignKey(
        'gamestate.GameProfile',
        on_delete=models.PROTECT,
        related_name='game_accounts',
        verbose_name='所属游戏档案',
        help_text='Window-centric 唯一游戏维度 (spec 2026-08-29-game-account-game-name-retirement 后非空)',
    )
    username = models.CharField(
        max_length=200,
        verbose_name='游戏用户名',
        help_text='游戏账号的用户名',
    )
    encrypted_password = models.TextField(
        max_length=512,
        verbose_name='加密密码',
        help_text='AES-256-GCM 加密后的密码',
    )
    server_region = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='区服',
        help_text='账号所在的游戏区服',
    )
    login_method = models.CharField(
        max_length=20,
        choices=LOGIN_METHODS,
        default='password',
        verbose_name='登录方式',
        help_text='登录方式: password/qr_scan/token/steam',
    )
    group = models.ForeignKey(
        'GameAccountGroup',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accounts',
        verbose_name='所属分组',
        help_text='账号所属的分组',
    )
    resource_pack = models.ForeignKey(
        'resources.ResourcePack',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bound_game_accounts',
        verbose_name='当前资源包',
        help_text='账户绑定的资源包，换服务器只改此字段',
    )
    status = models.CharField(
        max_length=20,
        default='unknown',
        verbose_name='账户状态',
        help_text='游戏账号的当前状态',
    )
    last_login_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='最后登录时间',
        help_text='账号最近一次登录游戏的时间',
    )
    last_check_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='最后检测时间',
        help_text='账号最近一次状态检测时间',
    )
    login_count = models.IntegerField(
        default=0,
        verbose_name='登录次数',
        help_text='账号累计登录次数',
    )
    execution_count = models.IntegerField(
        default=0,
        verbose_name='执行次数',
        help_text='账号累计被执行次数',
    )
    last_execution_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='最后执行时间',
        help_text='账号最近一次被执行的时间',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='是否启用',
        help_text='标记账号是否处于启用状态',
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
        db_table = 'accounts_gameaccount'
        ordering = ['-created_at']
        verbose_name = '游戏账号'
        verbose_name_plural = '游戏账号'
        # spec 2026-08-29-game-account-game-name-retirement: 唯一性由字符串 game_name
        # 收敛到 game_profile FK (P2 迁移); game_name 字段 P3 drop.
        unique_together = [('owner', 'game_profile', 'username')]

    def __str__(self):
        return f'{self.game_profile.game_name} - {self.username}'


class GameAccountGroup(models.Model):
    """游戏账户分组模型，支持自定义分组名和拖拽分类。"""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='account_groups',
        verbose_name='所有者',
        help_text='分组所属的用户',
    )
    name = models.CharField(
        max_length=200,
        verbose_name='分组名称',
        help_text='分组的显示名称',
    )
    slug = models.SlugField(
        max_length=200,
        verbose_name='分组标识',
        help_text='分组的 URL 标识',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
        help_text='记录创建的时间戳',
    )

    class Meta:
        db_table = 'accounts_gameaccount_group'
        ordering = ['name']
        verbose_name = '账户分组'
        verbose_name_plural = '账户分组'
        unique_together = [('owner', 'slug')]

    def __str__(self):
        return f'{self.name} ({self.owner.username})'


class APIKey(models.Model):
    """API 密钥模型，存储用户 API 密钥哈希、权限及调用统计。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='api_keys',
        verbose_name='用户',
        help_text='API 密钥所属的用户',
    )
    key_hash = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='密钥哈希',
        help_text='API 密钥的哈希值',
    )
    name = models.CharField(
        max_length=255,
        verbose_name='名称',
        help_text='API 密钥的显示名称',
    )
    permissions = models.JSONField(
        default=dict,
        verbose_name='权限',
        help_text='API 密钥的权限配置',
    )
    ip_whitelist = models.JSONField(
        default=list,
        verbose_name='IP白名单',
        help_text='允许调用 API 的 IP 白名单',
    )
    call_count = models.IntegerField(
        default=0,
        verbose_name='调用次数',
        help_text='API 密钥累计调用次数',
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='过期时间',
        help_text='API 密钥的过期时间',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='是否启用',
        help_text='标记 API 密钥是否启用',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
        help_text='记录创建的时间戳',
    )

    class Meta:
        db_table = 'accounts_apikey'
        ordering = ['-created_at']
        verbose_name = 'API密钥'
        verbose_name_plural = 'API密钥'

    def __str__(self):
        return f'{self.name} ({self.user})'


class LoginHistory(models.Model):
    """登录历史模型，记录用户的登录 IP、UA 和地理位置信息。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='login_history',
        verbose_name='用户',
        help_text='登录的用户',
    )
    ip_address = models.GenericIPAddressField(
        db_index=True,
        verbose_name='IP地址',
        help_text='登录时的 IP 地址',
    )
    # M5: bound the user_agent length. TextField keeps the TEXT column type but
    # max_length adds MaxLengthValidator at the serializer/form layer so overly
    # long payloads are rejected before persistence.
    user_agent = models.TextField(
        blank=True,
        max_length=1024,
        verbose_name='User-Agent',
        help_text='登录时的 User-Agent 字符串',
    )
    location = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='登录位置',
        help_text='IP 解析出的地理位置',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间',
        help_text='记录创建的时间戳',
    )

    class Meta:
        db_table = 'accounts_loginhistory'
        ordering = ['-created_at']
        verbose_name = '登录历史'
        verbose_name_plural = '登录历史'
        indexes = [
            models.Index(fields=['user', '-created_at'], name='idx_loginhist_user_created'),
        ]

    def __str__(self):
        return f'{self.user} - {self.ip_address} ({self.created_at})'


class UserSession(models.Model):
    """用户活跃会话模型，记录每个 refresh token 对应的设备信息，支持踢下线。"""

    class DeviceType(models.TextChoices):
        WEB = 'web', 'Web'
        MOBILE = 'mobile', 'Mobile'
        DESKTOP = 'desktop', 'Desktop'
        API = 'api', 'API'
        UNKNOWN = 'unknown', 'Unknown'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sessions',
        verbose_name='用户',
        help_text='会话所属的用户',
    )
    refresh_token_jti = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='Refresh Token JTI',
        help_text='关联 simplejwt OutstandingToken 的 jti claim',
    )
    device_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='设备名称',
        help_text='从 User-Agent 解析，如 "Chrome 120 on Windows 10"',
    )
    device_type = models.CharField(
        max_length=20,
        choices=DeviceType.choices,
        default=DeviceType.UNKNOWN,
        verbose_name='设备类型',
        help_text='设备类型: web/mobile/desktop/api/unknown',
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP地址',
        help_text='会话登录时的 IP 地址',
    )
    # M5: bound the user_agent length (see LoginHistory.user_agent for rationale).
    user_agent = models.TextField(
        blank=True,
        max_length=1024,
        verbose_name='User-Agent',
        help_text='会话登录时的 User-Agent 字符串',
    )
    location = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='登录位置',
        help_text='IP 解析出的地理位置',
    )
    last_activity = models.DateTimeField(
        auto_now=True,
        verbose_name='最后活动时间',
        help_text='用户最近一次活动的时间',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='登录时间',
        help_text='会话创建(登录)的时间',
    )
    expires_at = models.DateTimeField(
        verbose_name='过期时间',
        help_text='跟随 refresh token 过期时间',
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name='是否活跃',
        help_text='踢下线后置 False',
    )

    class Meta:
        db_table = 'accounts_usersession'
        ordering = ['-created_at']
        verbose_name = '用户会话'
        verbose_name_plural = '用户会话'
        indexes = [
            models.Index(fields=['user', '-created_at'], name='idx_usersess_user_created'),
            models.Index(fields=['refresh_token_jti'], name='idx_usersess_jti'),
            models.Index(fields=['is_active'], name='idx_usersess_active'),
        ]

    def __str__(self):
        return f'{self.user} - {self.device_name or self.ip_address} ({self.created_at})'


class AuditLog(models.Model):
    """系统审计日志 — 自动记录所有敏感操作。

    历史归属：早期定义在 tasks app（tasks/migrations/0010 创建 audit_log 表），
    R37-P3 Stage 7 Task 20a（2026-07-08）迁移到 accounts app，因 AuditLog 的
    FK 指向 User 且记录的是用户操作（login/logout/create/...），归 accounts
    更内聚。物理表 db_table='audit_log' 保持不变（零数据迁移）。
    """

    # TD-225 (2026-07-18): migrated from inline list-of-tuples ACTION_CHOICES
    # to nested TextChoices enum, matching Django 3+ best practices and
    # aligning with TaskExecution.Status / ExecutionStep.Status / Agent.Status
    # / Device.Status (all already use TextChoices).
    class Action(models.TextChoices):
        LOGIN = 'login', '登录'
        LOGOUT = 'logout', '登出'
        CREATE = 'create', '创建'
        UPDATE = 'update', '更新'
        DELETE = 'delete', '删除'
        EXECUTE = 'execute', '执行'
        IMPORT = 'import', '导入'
        EXPORT = 'export', '导出'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='task_audit_logs', verbose_name="用户", help_text='执行操作的用户')
    action = models.CharField(max_length=20, choices=Action.choices, verbose_name="操作", help_text='操作: login/logout/create/update/delete/execute/import/export')
    resource_type = models.CharField(max_length=100, verbose_name="资源类型", help_text='被操作资源的类型')
    resource_id = models.CharField(max_length=255, blank=True, default='', verbose_name="资源ID", help_text='被操作资源的标识')
    details = models.JSONField(default=dict, verbose_name="详情", help_text='操作的详细信息')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="IP地址", help_text='操作发起的 IP 地址')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="操作时间", help_text='操作发生的时间')

    class Meta:
        db_table = 'audit_log'
        ordering = ['-created_at']
        verbose_name = '审计日志'
        verbose_name_plural = '审计日志'


