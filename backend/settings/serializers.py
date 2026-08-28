"""
系统设置序列化器

包含无人值守策略配置的嵌套 JSON 序列化与校验。
"""

from rest_framework import serializers

from settings.models import AppSettings, FeatureFlag, LLMConfig, UnattendedStrategy


class StepLevelRecoverySerializer(serializers.Serializer):
    """步骤级恢复策略序列化器"""

    maxRetries = serializers.IntegerField(default=3, min_value=0, max_value=100)
    retryIntervalSeconds = serializers.IntegerField(default=5, min_value=0, max_value=3600)
    exponentialBackoff = serializers.BooleanField(default=False)


class TaskLevelRecoverySerializer(serializers.Serializer):
    """任务级恢复策略序列化器"""

    consecutiveFailureThreshold = serializers.IntegerField(default=3, min_value=1, max_value=100)
    failureAction = serializers.ChoiceField(
        choices=['skip', 'restart', 'switch_account'],
        default='skip',
    )


class AppLevelRecoverySerializer(serializers.Serializer):
    """应用级恢复策略序列化器"""

    freezeDetection = serializers.BooleanField(default=True)
    freezeTimeoutSeconds = serializers.IntegerField(default=120, min_value=10, max_value=3600)
    freezeAction = serializers.ChoiceField(
        choices=['restart_app', 'relogin', 'notify_only'],
        default='restart_app',
    )


class DeviceLevelRecoverySerializer(serializers.Serializer):
    """设备级恢复策略序列化器"""

    crashDetection = serializers.BooleanField(default=True)
    crashAction = serializers.ChoiceField(
        choices=['restart_emulator', 'reconnect_adb', 'switch_backup'],
        default='restart_emulator',
    )
    backupDeviceId = serializers.IntegerField(default=None, allow_null=True, required=False)
    maxRestartCount = serializers.IntegerField(default=2, min_value=0, max_value=100)


class SystemLevelRecoverySerializer(serializers.Serializer):
    """系统级恢复策略序列化器"""

    agentTimeoutSeconds = serializers.IntegerField(default=300, min_value=30, max_value=7200)
    timeoutActions = serializers.ListField(
        child=serializers.ChoiceField(choices=['notify', 'mark_offline', 'reassign']),
        default=['notify', 'mark_offline', 'reassign'],
    )


class RecoveryConfigSerializer(serializers.Serializer):
    """恢复策略总序列化器"""

    stepLevel = StepLevelRecoverySerializer(default=dict)
    taskLevel = TaskLevelRecoverySerializer(default=dict)
    appLevel = AppLevelRecoverySerializer(default=dict)
    deviceLevel = DeviceLevelRecoverySerializer(default=dict)
    systemLevel = SystemLevelRecoverySerializer(default=dict)


class NightModeConfigSerializer(serializers.Serializer):
    """夜间模式配置序列化器"""

    isEnabled = serializers.BooleanField(default=False)

    timeRange = serializers.DictField(
        child=serializers.CharField(),
        default=lambda: {'start': '00:00', 'end': '06:00'},
    )
    screenshotIntervalMultiplier = serializers.IntegerField(default=2, min_value=1, max_value=10)
    operationIntervalMultiplier = serializers.IntegerField(default=2, min_value=1, max_value=5)
    cpuThrottle = serializers.BooleanField(default=True)
    autoPauseNonCritical = serializers.BooleanField(default=False)

    def validate_timeRange(self, value):
        start = value.get('start', '00:00')
        end = value.get('end', '00:00')
        if start == end:
            raise serializers.ValidationError('夜间模式开始时间和结束时间不能相同')
        return value


class FrequencyLimitConfigSerializer(serializers.Serializer):
    """频率限制配置序列化器"""

    maxPerAccountPerDay = serializers.IntegerField(default=10, min_value=1, max_value=99)
    maxGlobalPerDay = serializers.IntegerField(default=100, min_value=1, max_value=999)
    minTaskIntervalSeconds = serializers.IntegerField(default=30, min_value=0, max_value=3600)
    mode = serializers.ChoiceField(choices=['fixed', 'adaptive'], default='fixed')
    todayExecuted = serializers.IntegerField(read_only=True, default=0)
    todayLimit = serializers.IntegerField(read_only=True, default=100)


class NotificationPolicySerializer(serializers.Serializer):
    """通知策略序列化器"""

    enabledEvents = serializers.ListField(
        child=serializers.ChoiceField(choices=[
            'task_failed', 'device_offline', 'account_blocked', 'game_updated',
            'consecutive_failures', 'auto_stop_triggered', 'night_mode_switch',
            'resource_expiring', 'recovery_triggered', 'daily_report_generated',
        ]),
        default=[
            'task_failed', 'device_offline', 'account_blocked',
            'game_updated', 'auto_stop_triggered', 'recovery_triggered',
        ],
    )


class CooldownConfigSerializer(serializers.Serializer):
    """冷却时间配置序列化器"""

    emulatorRestartSeconds = serializers.IntegerField(default=120, min_value=60, max_value=600)
    gameRestartSeconds = serializers.IntegerField(default=60, min_value=30, max_value=300)
    consecutiveLoginSeconds = serializers.IntegerField(default=10, min_value=5, max_value=120)
    recoveryPauseSeconds = serializers.IntegerField(default=180, min_value=60, max_value=600)


class UnattendedStrategySerializer(serializers.ModelSerializer):
    """无人值守策略序列化器"""

    recovery = RecoveryConfigSerializer(source='recovery_config')
    nightMode = NightModeConfigSerializer(source='night_mode_config')
    frequencyLimit = FrequencyLimitConfigSerializer(source='frequency_limit_config')
    notificationPolicy = NotificationPolicySerializer(source='notification_policy')
    cooldown = CooldownConfigSerializer(source='cooldown_config')

    class Meta:
        model = UnattendedStrategy
        fields = [
            'id', 'recovery', 'nightMode', 'frequencyLimit',
            'notificationPolicy', 'cooldown', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        """
        Upsert 模式：POST 覆盖现有记录而不是新建多条。

        Args:
            validated_data: 已校验的嵌套配置数据

        Returns:
            更新或创建的 UnattendedStrategy 实例
        """
        recovery = validated_data.pop('recovery_config', {})
        night_mode = validated_data.pop('night_mode_config', {})
        frequency_limit = validated_data.pop('frequency_limit_config', {})
        notification_policy = validated_data.pop('notification_policy', {})
        cooldown = validated_data.pop('cooldown_config', {})

        existing = UnattendedStrategy.objects.first()
        if existing:
            for attr, val in [
                ('recovery_config', recovery),
                ('night_mode_config', night_mode),
                ('frequency_limit_config', frequency_limit),
                ('notification_policy', notification_policy),
                ('cooldown_config', cooldown),
                ('is_active', validated_data.get('is_active', existing.is_active)),
            ]:
                setattr(existing, attr, val)
            existing.save()
            return existing

        strategy = UnattendedStrategy.objects.create(
            recovery_config=recovery,
            night_mode_config=night_mode,
            frequency_limit_config=frequency_limit,
            notification_policy=notification_policy,
            cooldown_config=cooldown,
            is_active=validated_data.get('is_active', True),
        )
        return strategy


class LLMConfigSerializer(serializers.ModelSerializer):
    """LLM 配置序列化器

    api_key is write-only: clients submit plaintext when creating/updating,
    but it is never returned in responses. Instead, ``api_key_masked``
    shows a redacted preview (e.g. ``sk-***...vpce``) so the UI can
    confirm a key is set without exposing it. Storage encryption is
    handled by ``LLMConfig.save()`` / ``get_api_key()`` (see crypto.py).
    """

    api_key_masked = serializers.SerializerMethodField()

    class Meta:
        model = LLMConfig
        fields = [
            'id', 'provider', 'api_key', 'api_key_masked',
            'api_base', 'default_model',
            'temperature', 'max_tokens', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            # Never expose the stored (possibly encrypted) key in responses.
            # Clients send plaintext on write; save() encrypts it.
            'api_key': {'write_only': True, 'required': False, 'allow_blank': True},
        }

    def get_api_key_masked(self, obj) -> str:
        """Return a redacted preview of the API key for display.

        Shows the first 3 and last 4 chars with ``***`` in between,
        or ``''`` if no key is set. Uses ``get_api_key()`` so the
        preview reflects the decrypted value regardless of whether
        encryption is enabled.
        """
        try:
            key = obj.get_api_key()
        except Exception:
            key = ''
        if not key:
            return ''
        if len(key) <= 8:
            return '***'
        return f"{key[:3]}***{key[-4:]}"


class FeatureFlagSerializer(serializers.ModelSerializer):
    """功能开关序列化器（R37-P3 Stage 7: 从 tasks 迁入）。"""

    class Meta:
        model = FeatureFlag
        fields = [
            'id', 'name', 'description', 'enabled',
            'rollout_percentage', 'allowed_roles', 'allowed_ips',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AppSettingsSerializer(serializers.ModelSerializer):
    """应用全局设置序列化器（R37-P3 Stage 7: 从 tasks 迁入）。"""

    class Meta:
        model = AppSettings
        fields = [
            'id', 'setting_key', 'setting_value', 'category',
            'description', 'updated_by', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
