"""
系统设置模型

包含无人值守策略配置模型（Upsert 单例模式）、LLM 配置、功能开关、应用全局设置。
"""

from django.conf import settings as django_settings
from django.db import models


class UnattendedStrategy(models.Model):
    """
    无人值守策略配置

    包含 5 层恢复策略、夜间模式、频率限制、通知策略、冷却时间。
    Upsert 单例模式：全局只有一条记录。
    """

    recovery_config = models.JSONField(default=dict, verbose_name='恢复策略配置', help_text='5 层恢复策略的配置数据')
    night_mode_config = models.JSONField(default=dict, verbose_name='夜间模式配置', help_text='夜间模式的时段和限制配置')
    frequency_limit_config = models.JSONField(default=dict, verbose_name='频率限制配置', help_text='执行频率限制的配置数据')
    notification_policy = models.JSONField(default=dict, verbose_name='通知策略', help_text='告警通知的策略配置')
    cooldown_config = models.JSONField(default=dict, verbose_name='冷却时间配置', help_text='任务冷却时间的配置数据')
    is_active = models.BooleanField(default=True, verbose_name='是否激活', help_text='标记该策略是否处于激活状态')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间', help_text='记录创建的时间戳')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间', help_text='记录最近一次更新的时间戳')

    class Meta:
        db_table = 'settings_unattended_strategy'
        verbose_name = '无人值守策略配置'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'无人值守策略配置 ({ "激活" if self.is_active else "停用" })'


class LLMConfig(models.Model):
    """
    LLM 大模型配置

    Upsert 单例模式，全局只有一条记录。
    支持 OpenAI 兼容 API（OpenAI / DeepSeek / Ollama / 自定义）。
    """

    provider = models.CharField(
        max_length=50,
        default='openai',
        verbose_name='LLM 提供商',
        help_text='openai / deepseek / ollama / custom',
    )
    api_key = models.CharField(
        max_length=512,
        blank=True,
        default='',
        verbose_name='API Key',
        help_text='LLM 服务的 API 密钥',
    )
    api_base = models.CharField(
        max_length=512,
        blank=True,
        default='https://api.openai.com/v1',
        verbose_name='API Base URL',
        help_text='LLM 服务的 API 基础 URL',
    )
    default_model = models.CharField(
        max_length=100,
        default='gpt-4o-mini',
        verbose_name='默认模型',
        help_text='默认使用的 LLM 模型名称',
    )
    temperature = models.FloatField(default=0.3, verbose_name='温度参数', help_text='LLM 采样温度, 越高越随机')
    max_tokens = models.IntegerField(default=4096, verbose_name='最大 Token 数', help_text='LLM 单次响应的最大 Token 数')
    available_models = models.JSONField(
        default=list,
        blank=True,
        verbose_name='模型列表',
        help_text='该 provider 下可用的模型名称列表',
    )
    # Custom per-provider pricing (USD per 1K tokens). When set, overrides the
    # static pricing table (gaf_ai.pricing) for cost estimation. Null = fall
    # back to the built-in table (TD-424 / usage cost accuracy).
    input_price = models.FloatField(
        null=True,
        blank=True,
        verbose_name='输入单价',
        help_text='每 1K tokens 的输入价格 (USD)，留空使用内置定价表',
    )
    output_price = models.FloatField(
        null=True,
        blank=True,
        verbose_name='输出单价',
        help_text='每 1K tokens 的输出价格 (USD)，留空使用内置定价表',
    )
    is_active = models.BooleanField(default=False, verbose_name='是否启用 LLM', help_text='标记 LLM 功能是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间', help_text='记录创建的时间戳')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间', help_text='记录最近一次更新的时间戳')

    class Meta:
        db_table = 'settings_llm_config'
        verbose_name = 'LLM 配置'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'LLM 配置 ({self.provider} / {self.default_model})'

    def save(self, *args, **kwargs):
        """Encrypt api_key on save if encryption is configured.

        If the key is already encrypted (starts with 'gAAAAA'), it
        is kept as-is to avoid double encryption. If encryption is
        not configured, the key is stored as plaintext (backward compat).
        """
        from settings.crypto import encrypt_api_key
        self.api_key = encrypt_api_key(self.api_key)
        super().save(*args, **kwargs)

    def get_api_key(self) -> str:
        """Return the decrypted API key for use in LLM calls."""
        from settings.crypto import decrypt_api_key
        return decrypt_api_key(self.api_key)


class FeatureFlag(models.Model):
    """功能开关模型，控制功能的启用/禁用、灰度发布和角色/IP 白名单。

    R37-P3 Stage 7 Task 20a: migrated from tasks app (TD-039).
    db_table kept as 'feature_flag' — zero data migration.
    """

    name = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='功能名称',
        help_text='功能开关的唯一名称',
    )
    description = models.TextField(
        blank=True,
        default='',
        verbose_name='描述',
        help_text='功能开关的说明描述',
    )
    enabled = models.BooleanField(
        default=True,
        verbose_name='是否启用',
        help_text='标记功能是否全局启用',
    )
    rollout_percentage = models.IntegerField(
        default=100,
        verbose_name='灰度百分比 (0-100)',
        help_text='灰度发布的百分比, 0-100',
    )
    allowed_roles = models.JSONField(
        default=list,
        blank=True,
        verbose_name='允许的角色列表',
        help_text='允许使用该功能的角色列表',
    )
    allowed_ips = models.JSONField(
        default=list,
        blank=True,
        verbose_name='允许的 IP 列表',
        help_text='允许使用该功能的 IP 白名单',
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
        db_table = 'feature_flag'
        ordering = ['name']
        verbose_name = '功能开关'
        verbose_name_plural = '功能开关'

    def __str__(self):
        return f'{self.name} ({"启用" if self.enabled else "禁用"})'


class AppSettings(models.Model):
    """应用全局设置模型，存储系统配置、设备配置和 OCR 引擎配置。

    R37-P3 Stage 7 Task 20b: migrated from tasks app (TD-039).
    AppSettings is a system-wide key/value configuration store (register toggle,
    device_config, llm_config, ...). It was previously in the tasks app, but
    three call sites in accounts/views.py had to cross-import it from tasks —
    a clear boundary violation since app settings are not a task-execution
    concern. Moving it here consolidates all system configuration models
    (UnattendedStrategy, LLMConfig, FeatureFlag, AppSettings) in one app.
    db_table kept as 'tasks_appsettings' — zero data migration.
    """

    setting_key = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='配置键',
        help_text='配置项的唯一键名',
    )
    setting_value = models.JSONField(
        default=dict,
        verbose_name='配置值',
        help_text='配置项的值',
    )
    category = models.CharField(
        max_length=100,
        default='general',
        verbose_name='配置分类',
        help_text='配置项所属分类',
    )
    description = models.CharField(
        max_length=512,
        blank=True,
        verbose_name='配置说明',
        help_text='配置项的说明描述',
    )
    updated_by = models.ForeignKey(
        django_settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='更新者',
        help_text='最近更新该配置的用户',
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
        db_table = 'tasks_appsettings'
        verbose_name = '应用设置'
        verbose_name_plural = '应用设置'
        ordering = ['category', 'setting_key']

    def __str__(self):
        return f'{self.category}.{self.setting_key}'
