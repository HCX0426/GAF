
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers

from gamestate.serializers import GameProfileSerializer
from workers.models import (
    DEFAULT_INPUT_METHOD,
    DEFAULT_SCREENSHOT_METHOD,
    MULTI_GAME_SAFE_INPUT_METHODS,
    MULTI_GAME_SAFE_SCREENSHOT_METHODS,
    Device,
    DeviceGroup,
    Worker,
)
from workers.schema_types import (
    DeviceStatsSchema,
    ResolutionSchema,
    ResolvedDeviceMethodsSchema,
    WorkerInfoSchema,
)


class WorkerSerializer(serializers.ModelSerializer):
    """Agent 信息序列化器，包含全部字段。"""

    capabilities = serializers.JSONField(default=dict)

    class Meta:
        model = Worker
        fields = [
            'id', 'agent_id', 'hostname', 'ip_address', 'os_info',
            'status', 'last_heartbeat', 'cpu_usage', 'memory_usage',
            'screenshot_fps', 'capabilities',
            'is_local', 'created_at', 'updated_at',
        ]
        # agent_token is a sensitive authentication credential; never expose it in
        # regular listing/detail responses. Token is returned only via dedicated
        # WorkerTokenSerializer at creation time.
        read_only_fields = ['id', 'created_at', 'updated_at']


class WorkerTokenSerializer(serializers.Serializer):
    """Worker 令牌序列化器，返回 Worker ID 和生成的令牌。"""

    agent_id = serializers.CharField()
    agent_token = serializers.CharField()


class DeviceSerializer(serializers.ModelSerializer):
    """Device 序列化器，包含设备全部字段及关联 Agent 摘要信息。"""

    # spec-29f (TD-266 Phase 1): `allow_null=True` on method fields whose
    # getters can return None, so DRF Spectacular emits `T | null` instead
    # of just `T` in the OpenAPI schema.
    agent_info = serializers.SerializerMethodField(read_only=True, allow_null=True)
    locked_by_username = serializers.SerializerMethodField(read_only=True)
    resolution = serializers.SerializerMethodField(read_only=True, allow_null=True)
    resolution_display = serializers.SerializerMethodField(read_only=True)
    # R37-P1: nested GameProfile summary so the frontend can render the game
    # name Tag without a second round-trip to /api/v2/tasks/game-profiles/.
    game_profile_detail = serializers.SerializerMethodField(read_only=True)
    # v3 §2.8.1: resolved methods after GameProfile inheritance.
    # Frontend WindowManagementPage uses this to display "继承/自定义" tags.
    resolved_methods = serializers.SerializerMethodField(read_only=True)
    # P-011 Spec A: multi-game mode fields for frontend mode-selector binding.
    # `multi_game_restricted` mirrors resolved_methods.multi_game_restricted
    # as a top-level field for convenience; `allowed_*_methods` tells the
    # DeviceForm Select which options to disable.
    multi_game_restricted = serializers.SerializerMethodField(read_only=True)
    allowed_screenshot_methods = serializers.SerializerMethodField(read_only=True, allow_null=True)
    allowed_input_methods = serializers.SerializerMethodField(read_only=True, allow_null=True)
    # spec-29k (TD-259 #7 Phase 2d): override model JSONField with a
    # SerializerMethodField backed by `DeviceStatsSchema` so Spectacular
    # emits precise typed fields (`screenshot_latency_avg_ms: number | null`
    # etc.) instead of `{ [key: string]: unknown }`. The getter just
    # returns the raw dict — `DeviceStatsSchema` declares the known keys;
    # unknown keys are silently dropped by Spectacular (acceptable since
    # only the 10 declared keys are consumed by the frontend).
    device_stats = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Device
        fields = [
            'id', 'name', 'device_type', 'status', 'agent', 'agent_info',
            'resolution_width', 'resolution_height', 'resolution', 'resolution_display',
            'screenshot_fps', 'extra_info',
            'locked_by', 'locked_by_username', 'locked_at',
            'control_mode', 'screenshot_method', 'input_method', 'device_stats',
            'adb_serial', 'window_handle', 'emulator_brand', 'game_profile', 'game_profile_detail',
            'game_account',
            'system_version', 'battery_level', 'last_heartbeat',
            'resolved_methods',
            'multi_game_restricted', 'allowed_screenshot_methods', 'allowed_input_methods',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'locked_by', 'locked_by_username', 'locked_at']

    def validate(self, data):
        """Derive concrete methods from control_mode when no explicit override.

        v3 §2.8.1: when control_mode is 'auto', screenshot/input stay 'auto'
        so resolve_device_methods inherits from GameProfile at runtime.
        Only concrete control modes (foreground/background/pseudo_background)
        populate screenshot/input from CONTROL_MODE_DEFAULTS.
        """
        validated = super().validate(data)
        control_mode = validated.get('control_mode', Device.ControlMode.AUTO)
        if control_mode == Device.ControlMode.AUTO:
            # 'auto' = inherit; keep screenshot/input as 'auto' for runtime resolution
            if 'screenshot_method' not in validated:
                validated['screenshot_method'] = DEFAULT_SCREENSHOT_METHOD
            if 'input_method' not in validated:
                validated['input_method'] = DEFAULT_INPUT_METHOD
        else:
            defaults = Device.get_control_mode_defaults(control_mode)
            sm = validated.get('screenshot_method')
            if sm in (None, '', 'auto'):
                validated['screenshot_method'] = defaults['screenshot_method']
            im = validated.get('input_method')
            if im in (None, '', 'auto'):
                validated['input_method'] = defaults['input_method']
        return validated

    @extend_schema_field(DeviceStatsSchema)
    def get_device_stats(self, obj):
        """Return device performance stats dict.

        spec-29k (TD-259 #7 Phase 2d): the underlying model field is a
        `JSONField` populated incrementally by `Device.update_screenshot_stats`
        and `DevicePerformanceStatsView`. Returns the raw dict —
        `DeviceStatsSchema` (applied via `@extend_schema_field`) declares
        the 10 known keys so DRF Spectacular emits precise types. Unknown
        keys remain in the runtime response but are not typed.
        """
        return obj.device_stats or {}

    @extend_schema_field(ResolvedDeviceMethodsSchema)
    def get_resolved_methods(self, obj):
        """Return resolved screenshot/input/control_mode after GameProfile inheritance.

        v3 §2.8.1: 'auto' values inherit from GameProfile defaults; concrete
        values override. Frontend uses this to show "继承/自定义" tags.
        P-011 Spec A: also includes multi_game_restricted + original_* keys.
        """
        from workers.models import resolve_device_methods
        return resolve_device_methods(obj)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_multi_game_restricted(self, obj):
        """Return True if multi-game parallel mode is enabled (Spec A).

        When True, the frontend DeviceForm should disable unsafe method
        options in the input/screenshot Select dropdowns.
        """
        from settings.feature_flags import is_multi_game_mode_enabled
        return is_multi_game_mode_enabled()

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_allowed_screenshot_methods(self, obj):
        """Return the whitelist of screenshot methods allowed in multi-game mode.

        Returns None in single mode (no restriction). In multi mode the
        DeviceForm uses this to disable non-whitelisted Select options.
        """
        from settings.feature_flags import is_multi_game_mode_enabled
        if not is_multi_game_mode_enabled():
            return None
        return sorted(MULTI_GAME_SAFE_SCREENSHOT_METHODS)

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_allowed_input_methods(self, obj):
        """Return the whitelist of input methods allowed in multi-game mode.

        Returns None in single mode (no restriction). In multi mode the
        DeviceForm uses this to disable non-whitelisted Select options.
        """
        from settings.feature_flags import is_multi_game_mode_enabled
        if not is_multi_game_mode_enabled():
            return None
        return sorted(MULTI_GAME_SAFE_INPUT_METHODS)

    @extend_schema_field(WorkerInfoSchema)
    def get_agent_info(self, obj):
        """返回关联 Worker 的摘要信息。"""
        if obj.agent:
            return {
                'id': obj.agent.id,
                'agent_id': obj.agent.agent_id,
                'hostname': obj.agent.hostname,
                'ip_address': obj.agent.ip_address,
                'status': obj.agent.status,
                'last_heartbeat': obj.agent.last_heartbeat,
            }
        return None

    @extend_schema_field(GameProfileSerializer)
    def get_game_profile_detail(self, obj):
        """Return nested GameProfile summary for frontend Tag rendering.

        R37-P3 Stage 7: GameProfileSerializer migrated to gamestate.serializers.

        spec-29f (TD-266 Phase 2a): top-level import is safe — gamestate
        only depends on gamestate.models (no circular import).
        """
        if not obj.game_profile_id:
            return None
        return GameProfileSerializer(obj.game_profile).data

    @extend_schema_field(OpenApiTypes.STR)
    def get_locked_by_username(self, obj):
        """返回锁定者用户名。"""
        if obj.locked_by:
            return obj.locked_by.username
        return None

    @extend_schema_field(ResolutionSchema)
    def get_resolution(self, obj):
        """返回分辨率对象格式。"""
        if obj.resolution_width and obj.resolution_height:
            return {
                'width': obj.resolution_width,
                'height': obj.resolution_height,
            }
        return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_resolution_display(self, obj):
        """返回人类可读的分辨率字符串，如 '1920x1080'。"""
        if obj.resolution_width and obj.resolution_height:
            return f'{obj.resolution_width}x{obj.resolution_height}'
        return None


class DeviceRegisterSerializer(serializers.Serializer):
    """设备注册序列化器，支持 Android(ADB/模拟器) 和 Windows 设备注册。"""

    name = serializers.CharField(max_length=255)
    agent_type = serializers.ChoiceField(choices=['android', 'windows'])
    adb_serial = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    hwnd = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    window_title = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    emulator_brand = serializers.CharField(max_length=32, required=False, allow_blank=True, default='')
    resolution = serializers.DictField(required=False, allow_null=True, default=dict)
    resolution_width = serializers.IntegerField(required=False, allow_null=True, default=None)
    resolution_height = serializers.IntegerField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        """校验注册参数，根据 agent_type 检查必填字段。"""
        agent_type = attrs.get('agent_type')
        if agent_type == 'android':
            if not attrs.get('adb_serial'):
                raise serializers.ValidationError({'adb_serial': 'Android 设备必须提供 ADB 序列号'})
            existing = Device.objects.filter(adb_serial=attrs['adb_serial']).first()
            if existing:
                raise serializers.ValidationError(
                    {'adb_serial': f'该 ADB 设备已注册 (ID: {existing.id}, 名称: {existing.name})'},
                    code='conflict',
                )
        elif agent_type == 'windows':
            if not attrs.get('hwnd') and not attrs.get('window_title'):
                raise serializers.ValidationError({'hwnd': 'Windows 设备必须提供窗口句柄或窗口标题'})
            if attrs.get('hwnd'):
                existing = Device.objects.filter(window_handle=attrs['hwnd']).first()
                if existing:
                    raise serializers.ValidationError(
                        {'hwnd': f'该窗口设备已注册 (ID: {existing.id}, 名称: {existing.name})'},
                        code='conflict',
                    )
        return attrs


class DeviceGroupSerializer(serializers.ModelSerializer):
    """DeviceGroup 序列化器，包含分组及设备列表（支持树形结构）。"""

    device_count = serializers.SerializerMethodField(read_only=True)
    devices_detail = DeviceSerializer(source='devices', many=True, read_only=True)
    children = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DeviceGroup
        fields = [
            'id', 'name', 'user', 'parent', 'children',
            'devices', 'device_count', 'devices_detail',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'user', 'device_count', 'created_at', 'updated_at']

    @extend_schema_field(OpenApiTypes.INT)
    def get_device_count(self, obj):
        """返回分组内的设备数量。"""
        return obj.devices.count()

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_children(self, obj):
        """返回子分组列表。"""
        children = obj.children.all()
        if children.exists():
            return DeviceGroupTreeSerializer(children, many=True).data
        return []


class DeviceGroupTreeSerializer(serializers.ModelSerializer):
    """DeviceGroup 树形序列化器（简化版，用于嵌套渲染）。"""

    children = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DeviceGroup
        fields = ['id', 'name', 'children']

    def get_children(self, obj):
        """递归返回子分组。"""
        children = obj.children.all()
        if children.exists():
            return DeviceGroupTreeSerializer(children, many=True).data
        return []
