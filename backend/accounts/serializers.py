import contextlib
import time

from django.conf import settings
from django.contrib.auth import authenticate
from drf_spectacular.utils import OpenApiTypes, extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.tokens import RefreshToken

from accounts import crypto
from accounts.models import APIKey, AuditLog, GameAccount, GameAccountGroup, LoginHistory, User, UserSession
from gamestate.models import GameProfile
from resources.serializers import ResourcePackSerializer


class UserSerializer(serializers.ModelSerializer):
    """用户信息序列化器，用于展示用户详情。"""

    class Meta:
        model = User
        fields = [
            'id', 'username', 'role', 'must_change_password',
            'is_active', 'totp_enabled', 'last_login', 'created_at',
        ]
        read_only_fields = ['id', 'last_login', 'created_at']


class UserSessionSerializer(serializers.ModelSerializer):
    """用户会话序列化器，用于展示登录设备列表。

    `is_current` 字段通过对比请求中的 refresh token JTI 判定是否为当前会话。
    """

    is_current = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = [
            'id', 'device_name', 'device_type', 'ip_address',
            'location', 'last_activity', 'created_at', 'expires_at',
            'is_active', 'is_current',
        ]
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_is_current(self, obj):
        """判断是否为当前请求所在会话。"""
        current_jti = self.context.get('current_jti')
        if not current_jti:
            return False
        return obj.refresh_token_jti == current_jti


class LoginHistorySerializer(serializers.ModelSerializer):
    """登录历史序列化器，记录用户每次登录的 IP、UA 和位置信息 (M4)。"""

    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = LoginHistory
        fields = [
            'id', 'user', 'username', 'ip_address',
            'user_agent', 'location', 'created_at',
        ]
        read_only_fields = fields


class UserCreateSerializer(serializers.ModelSerializer):
    """用户创建序列化器，包含密码字段（仅写入）。"""

    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ['id', 'username', 'password', 'role', 'must_change_password', 'is_active']
        read_only_fields = ['id']

    def create(self, validated_data):
        """创建用户并加密密码。"""
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class ChangePasswordSerializer(serializers.Serializer):
    """修改密码序列化器，验证旧密码与新密码。"""

    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=6)
    confirm_password = serializers.CharField(required=True, min_length=6)

    def validate(self, data):
        """校验新密码与确认密码是否一致。"""
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': '两次输入的密码不一致'})
        return data

    def validate_old_password(self, value):
        """校验旧密码是否正确。"""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('旧密码不正确')
        return value


class TOTPSetupSerializer(serializers.Serializer):
    """2FA 设置序列化器，返回 TOTP secret 和 QR Code URI。"""

    pass


class RegisterSerializer(serializers.ModelSerializer):
    """用户注册序列化器，包含密码确认校验。"""

    password = serializers.CharField(write_only=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True, min_length=6)
    email = serializers.EmailField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'password', 'confirm_password']
        read_only_fields = ['id']

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': '两次输入的密码不一致'})
        return data

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        password = validated_data.pop('password')
        validated_data.setdefault('role', User.Role.VIEWER)
        validated_data.setdefault('must_change_password', False)
        validated_data.setdefault('is_active', True)
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class TOTPVerifySetupSerializer(serializers.Serializer):
    """2FA 验证设置序列化器，接收 TOTP 验证码确认启用。"""

    totp_code = serializers.CharField(required=True, min_length=6, max_length=6)


class TOTPDisableSerializer(serializers.Serializer):
    """2FA 禁用序列化器，需验证密码确认操作。"""

    password = serializers.CharField(required=True)


class Login2FASerializer(serializers.Serializer):
    """登录第二步 2FA 验证序列化器，使用 temp_token 和 TOTP 码换取 JWT。"""

    temp_token = serializers.CharField(required=True)
    totp_code = serializers.CharField(required=True, min_length=6, max_length=6)
    remember_me = serializers.BooleanField(default=False)


class PasswordResetRequestSerializer(serializers.Serializer):
    """密码重置请求序列化器，验证邮箱后生成重置 Token。

    Note: 不在 serializer 中校验邮箱是否存在，避免泄露邮箱注册状态（C13 修复）。
    邮箱存在性校验由 view 层处理 — 不存在时静默返回 200，防止邮箱枚举攻击。
    """

    email = serializers.EmailField(required=True)


class PasswordResetConfirmSerializer(serializers.Serializer):
    """密码重置确认序列化器，验证 Token 并设置新密码。"""

    token = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=6)
    confirm_password = serializers.CharField(required=True, min_length=6)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({'confirm_password': '两次输入的密码不一致'})
        return data


class GameAccountCreateSerializer(serializers.ModelSerializer):
    """
    游戏账户创建序列化器
    接收明文密码，自动 AES-256-GCM 加密后存储到 encrypted_password
    """

    password = serializers.CharField(write_only=True, min_length=1, max_length=255)
    # spec 2026-08-29-game-account-game-name-retirement P1: game_profile 成为唯一
    # 游戏维度; game_name 仅作兼容输入 (自动 get_or_create 解析), P3 后退役写路径.
    game_name = serializers.CharField(required=False, allow_blank=False, max_length=200)
    game_profile_id = serializers.PrimaryKeyRelatedField(
        queryset=GameProfile.objects.all(),
        source='game_profile',
        required=False,
        allow_null=False,
        write_only=True,
    )

    class Meta:
        model = GameAccount
        fields = [
            'id', 'game_profile_id', 'game_name', 'username', 'password',
            'server_region', 'login_method', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def _resolve_profile(self, validated_data):
        """把 game_profile_id / game_name 解析并写入 validated (profile 优先)."""
        profile = validated_data.pop('game_profile', None)
        raw_name = validated_data.pop('game_name', None)
        if profile is None and raw_name:
            profile, _ = GameProfile.objects.get_or_create(game_name=raw_name)
        if profile is not None:
            validated_data['game_profile'] = profile
            validated_data['game_name'] = profile.game_name  # P3 drop 前同步字符串快照
        elif raw_name:
            validated_data['game_name'] = raw_name
        return validated_data

    def create(self, validated_data):
        """创建游戏账户，对密码进行加密存储。"""
        plain_password = validated_data.pop('password')
        encrypted = crypto.encrypt_password(plain_password)
        validated_data['encrypted_password'] = encrypted
        validated_data['owner'] = self.context['request'].user
        self._resolve_profile(validated_data)
        return super().create(validated_data)


class GameAccountListSerializer(serializers.ModelSerializer):
    """
    游戏账户列表序列化器
    密码字段脱敏显示为 ******，不暴露加密后的密码
    """

    password_display = serializers.SerializerMethodField()
    # P1: 展示层游戏名统一来自 game_profile (profile 缺失时 fallback 旧字符串, P2 回填后恒 new)
    game_name = serializers.SerializerMethodField()

    class Meta:
        model = GameAccount
        fields = [
            'id', 'game_name', 'username', 'password_display',
            'server_region', 'login_method', 'is_active',
            'status', 'last_login_at', 'login_count', 'execution_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'status', 'last_login_at', 'login_count', 'execution_count', 'created_at', 'updated_at']

    def get_password_display(self, obj):
        """返回脱敏密码，始终显示 ********。"""
        return '********'

    def get_game_name(self, obj):
        return obj.game_profile.game_name if obj.game_profile_id else obj.game_name


class GameAccountUpdateSerializer(serializers.ModelSerializer):
    """
    游戏账户更新序列化器
    password 字段可选：留空不修改密码，有值则重新加密存储
    """

    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=255
    )
    # P1: 更新同样以 game_profile 为游戏维度 (game_name 仅兼容输入)
    game_name = serializers.CharField(required=False, allow_blank=False, max_length=200)
    game_profile_id = serializers.PrimaryKeyRelatedField(
        queryset=GameProfile.objects.all(),
        source='game_profile',
        required=False,
        allow_null=False,
        write_only=True,
    )

    class Meta:
        model = GameAccount
        fields = [
            'id', 'game_profile_id', 'game_name', 'username', 'password',
            'server_region', 'login_method', 'is_active',
        ]
        read_only_fields = ['id']

    def update(self, instance, validated_data):
        """更新游戏账户，若密码字段有值则重新加密存储。"""
        plain_password = validated_data.pop('password', None)
        if plain_password:
            instance.encrypted_password = crypto.encrypt_password(plain_password)
        profile = validated_data.pop('game_profile', None)
        raw_name = validated_data.pop('game_name', None)
        if profile is None and raw_name:
            profile, _ = GameProfile.objects.get_or_create(game_name=raw_name)
        if profile is not None:
            validated_data['game_profile'] = profile
            validated_data['game_name'] = profile.game_name
        return super().update(instance, validated_data)


class LoginResponseSerializer(serializers.Serializer):
    """登录响应序列化器，包含令牌和用户信息。"""

    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()


class InitStatusSerializer(serializers.Serializer):
    """系统初始化状态序列化器，返回初始化相关标志。"""

    initialized = serializers.BooleanField()
    has_admin = serializers.BooleanField()
    default_user_exists = serializers.BooleanField()
    register_enabled = serializers.BooleanField(default=True)


class SetupSerializer(serializers.Serializer):
    """系统初始化设置序列化器，用于创建管理员和保存配置。"""

    admin_username = serializers.CharField(min_length=3, max_length=150)
    admin_password = serializers.CharField(min_length=6, write_only=True)
    device_type = serializers.CharField(max_length=100)
    llm_config = serializers.JSONField(required=False, default=dict)


class AgentTokenCreateSerializer(serializers.Serializer):
    """Agent Token 创建序列化器，校验名称和权限列表。"""

    name = serializers.CharField(max_length=255, required=True, help_text='Agent 名称')
    permissions = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
        help_text='权限列表',
    )


class AgentTokenResponseSerializer(serializers.Serializer):
    """Agent Token 响应序列化器，返回完整 Token 信息（仅创建时返回完整 token）。"""

    token = serializers.CharField()
    agent_id = serializers.CharField()
    name = serializers.CharField()
    id = serializers.IntegerField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()


class AgentTokenListSerializer(serializers.Serializer):
    """Agent Token 列表序列化器，隐藏完整 Token 值。"""

    id = serializers.IntegerField()
    agent_id = serializers.CharField()
    name = serializers.CharField()
    status = serializers.CharField()
    token_preview = serializers.CharField()
    permissions = serializers.ListField(child=serializers.CharField())
    created_at = serializers.DateTimeField()


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    自定义 Token 获取序列化器，支持"记住我"和 2FA。

    当 remember_me=True 时，Refresh Token 有效期使用 GAF_REMEMBER_ME_DAYS 配置。
    若用户启用了 2FA，返回 temp_token 而非完整 JWT。
    登录成功后创建 UserSession 记录，并将 refresh token 的 jti 注入 access token 的 session_jti claim。
    """

    remember_me = serializers.BooleanField(default=False, write_only=True,
                                           help_text='是否开启记住我（延长 Refresh Token 有效期）')

    def validate(self, attrs):
        """
        认证用户并生成 Token。

        若用户启用了 2FA，返回 temp_token 提示需要 2FA 验证。
        """
        remember_me = attrs.pop('remember_me', False)
        authenticate_kwargs = {
            self.username_field: attrs[self.username_field],
            'password': attrs['password'],
        }
        with contextlib.suppress(KeyError):
            authenticate_kwargs['request'] = self.context['request']

        self.user = authenticate(**authenticate_kwargs)

        from rest_framework_simplejwt.settings import api_settings
        if not api_settings.USER_AUTHENTICATION_RULE(self.user):
            from rest_framework_simplejwt.exceptions import AuthenticationFailed
            raise AuthenticationFailed(
                self.error_messages['no_active_account'],
                'no_active_account',
            )

        # Capture first-login flag before updating last_login
        is_first_login = self.user.last_login is None

        # Update last_login timestamp (JWT login does not call django's auth.login())
        from django.utils.timezone import now
        self.user.last_login = now()
        self.user.save(update_fields=['last_login'])

        if self.user.totp_enabled:
            temp_token = RefreshToken.for_user(self.user)
            temp_token['is_2fa_temp'] = True
            temp_token['exp'] = int(time.time()) + 300
            return {
                'requires_2fa': True,
                'temp_token': str(temp_token.access_token),
            }

        refresh = RefreshToken.for_user(self.user)

        if remember_me:
            remember_days = getattr(settings, 'GAF_REMEMBER_ME_DAYS', 30)
            refresh['remember_me'] = True
            refresh['exp'] = int(time.time()) + remember_days * 86400

        # Inject session_jti claim into access token so UserSessionViewSet can identify current session
        refresh_jti = str(refresh.payload.get('jti', ''))
        access_token = refresh.access_token
        if refresh_jti:
            access_token['session_jti'] = refresh_jti

        # Create UserSession record for device management (A5)
        self._create_user_session(refresh_jti, remember_me)

        user_data = UserSerializer(self.user).data
        user_data['is_first_login'] = is_first_login
        return {
            'access': str(access_token),
            'refresh': str(refresh),
            'user': user_data,
        }

    def _create_user_session(self, refresh_jti, remember_me):
        """Create a UserSession record for tracking active sessions (A5).

        Also creates a LoginHistory record for audit trail (M4).
        """
        if not refresh_jti:
            return

        from datetime import timedelta

        from django.utils.timezone import now

        from accounts.models import LoginHistory, UserSession

        request = self.context.get('request')
        if request is None:
            return

        # Extract IP and User-Agent
        ip_address = self._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        device_name, device_type = self._parse_user_agent(user_agent)

        # Compute expiry
        if remember_me:
            remember_days = getattr(settings, 'GAF_REMEMBER_ME_DAYS', 30)
            expires_at = now() + timedelta(days=remember_days)
        else:
            from rest_framework_simplejwt.settings import api_settings as jwt_settings
            expires_at = now() + jwt_settings.REFRESH_TOKEN_LIFETIME

        UserSession.objects.create(
            user=self.user,
            refresh_token_jti=refresh_jti,
            device_name=device_name,
            device_type=device_type,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )

        # Create LoginHistory record for audit trail (M4)
        LoginHistory.objects.create(
            user=self.user,
            ip_address=ip_address,
            user_agent=user_agent,
            location='',  # GeoIP lookup not implemented; reserved for future
        )

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP from request, considering X-Forwarded-For proxy header."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    @staticmethod
    def _parse_user_agent(user_agent):
        """Parse User-Agent string into (device_name, device_type).

        Simple heuristic without external dependencies.
        """
        if not user_agent:
            return ('Unknown', UserSession.DeviceType.UNKNOWN)

        ua_lower = user_agent.lower()

        # Determine device type
        if any(k in ua_lower for k in ('mobile', 'android', 'iphone', 'ipad')):
            device_type = UserSession.DeviceType.MOBILE
        elif any(k in ua_lower for k in ('electron', 'desktop app')):
            device_type = UserSession.DeviceType.DESKTOP
        elif 'python-requests' in ua_lower or 'curl' in ua_lower or 'axios' in ua_lower:
            device_type = UserSession.DeviceType.API
        else:
            device_type = UserSession.DeviceType.WEB

        # Extract browser name and version
        browser = 'Unknown'
        if 'edg/' in ua_lower:
            browser = 'Edge'
        elif 'chrome/' in ua_lower and 'chromium' not in ua_lower:
            browser = 'Chrome'
        elif 'firefox/' in ua_lower:
            browser = 'Firefox'
        elif 'safari/' in ua_lower:
            browser = 'Safari'

        # Extract OS
        os_name = 'Unknown'
        if 'windows nt 10' in ua_lower:
            os_name = 'Windows 10/11'
        elif 'windows nt' in ua_lower:
            os_name = 'Windows'
        elif 'mac os x' in ua_lower or 'macintosh' in ua_lower:
            os_name = 'macOS'
        elif 'linux' in ua_lower and 'android' not in ua_lower:
            os_name = 'Linux'
        elif 'android' in ua_lower:
            os_name = 'Android'
        elif 'iphone' in ua_lower or 'ipad' in ua_lower:
            os_name = 'iOS'

        device_name = f'{browser} on {os_name}' if browser != 'Unknown' else os_name
        return (device_name, device_type)


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    """
    自定义 Token 刷新序列化器，支持"记住我" Token 的刷新。

    当检测到原 Token 包含 remember_me 标记时，
    新生成的 Refresh Token 也会沿用 GAF_REMEMBER_ME_DAYS 有效期。
    """

    def validate(self, attrs):
        """
        刷新 Token，若原 Token 为"记住我" Token，则新 Token 沿用延长有效期。
        """
        from rest_framework_simplejwt.settings import api_settings

        refresh = RefreshToken(attrs['refresh'])
        was_remember_me = refresh.payload.get('remember_me', False)

        data = {'access': str(refresh.access_token)}

        if api_settings.ROTATE_REFRESH_TOKENS:
            if api_settings.BLACKLIST_AFTER_ROTATION:
                with contextlib.suppress(AttributeError):
                    refresh.blacklist()

            refresh.set_jti()
            refresh.set_exp()

            if was_remember_me:
                remember_days = getattr(settings, 'GAF_REMEMBER_ME_DAYS', 30)
                refresh['remember_me'] = True
                refresh['exp'] = int(time.time()) + remember_days * 86400

            data['refresh'] = str(refresh)

        return data


class GameAccountSerializer(serializers.ModelSerializer):
    """游戏账户序列化器 — Phase 4 完整版，包含 CRUD、加解密、分组。"""

    password = serializers.CharField(write_only=True, required=False, min_length=1)
    group_name = serializers.SerializerMethodField(read_only=True)
    # spec 2026-08-29-game-account-game-name-retirement P1:
    # - game_name 保留为兼容写字段 (字符串输入 → get_or_create profile 并绑定)
    # - game_name_display 为权威展示 (始终 = game_profile.game_name), 前端 P3 切换
    game_name = serializers.CharField(required=False, allow_blank=False, max_length=200)
    game_name_display = serializers.SerializerMethodField(read_only=True)
    # spec-29f (TD-266 Phase 3a): nested ResourcePack summary so the
    # frontend GameAccountEditor can render the bound pack name/version
    # without a second round-trip to /api/v2/resources/resource-packs/{id}/.
    # Mirrors the game_profile / game_profile_detail pattern. The plain
    # `resource_pack` PrimaryKeyRelatedField (FK id, write-capable) is
    # kept so existing PATCH/POST payloads that send an id still work.
    resource_pack_detail = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = GameAccount
        fields = [
            'id', 'owner', 'game_name', 'game_name_display', 'game_profile', 'username', 'password',
            'server_region', 'login_method', 'group', 'group_name',
            'resource_pack', 'resource_pack_detail',
            'status', 'last_login_at', 'last_check_at',
            'login_count', 'execution_count', 'last_execution_time',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'owner', 'status', 'last_login_at', 'last_check_at',
                            'login_count', 'execution_count', 'last_execution_time',
                            'created_at', 'updated_at']

    @extend_schema_field(ResourcePackSerializer)
    def get_resource_pack_detail(self, obj):
        """Return nested ResourcePack summary for frontend display.

        spec-29f (TD-266 Phase 3a): top-level import is safe —
        resources.models depends on settings.AUTH_USER_MODEL (string FK)
        not accounts.serializers, so no circular import.
        """
        if not obj.resource_pack_id:
            return None
        return ResourcePackSerializer(obj.resource_pack).data

    @extend_schema_field(OpenApiTypes.STR)
    def get_group_name(self, obj):
        if obj.group:
            return obj.group.name
        return None

    @extend_schema_field(OpenApiTypes.STR)
    def get_game_name_display(self, obj):
        """权威展示: 游戏名恒来自 game_profile (P2 回填前对未绑定数据 fallback 字符串)."""
        return obj.game_profile.game_name if obj.game_profile_id else obj.game_name

    def _resolve_profile(self, validated_data):
        """game_profile 优先, 兼容字符串 game_name → get_or_create 绑定 (P1 双轨)."""
        profile = validated_data.pop('game_profile', None)
        raw_name = validated_data.pop('game_name', None)
        if profile is None and raw_name:
            profile, _ = GameProfile.objects.get_or_create(game_name=raw_name)
        if profile is not None:
            validated_data['game_profile'] = profile
            validated_data['game_name'] = profile.game_name  # P3 drop 前同步字符串快照
        elif raw_name:
            validated_data['game_name'] = raw_name
        return validated_data

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        if not password:
            raise serializers.ValidationError({'password': '密码不能为空'})
        validated_data['owner'] = self.context['request'].user
        validated_data['encrypted_password'] = crypto.encrypt_password(password)
        self._resolve_profile(validated_data)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        if password:
            instance.encrypted_password = crypto.encrypt_password(password)
        self._resolve_profile(validated_data)
        return super().update(instance, validated_data)


class GameAccountDetailSerializer(GameAccountSerializer):
    """游戏账户详情序列化器 — 密码字段不返回

    M2: removed redundant ``to_representation`` override. The parent's
    ``password`` field is ``write_only=True`` so it is never present in the
    serialized representation, making the manual ``pop`` a no-op.
    """

    class Meta(GameAccountSerializer.Meta):
        pass


class GameAccountLoginTestSerializer(serializers.Serializer):
    """测试登录请求序列化器"""

    device_id = serializers.IntegerField()


class GameAccountBatchCheckSerializer(serializers.Serializer):
    """批量检测请求序列化器"""

    account_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    check_all = serializers.BooleanField(default=False)


class GameAccountBatchImportSerializer(serializers.Serializer):
    """批量导入请求序列化器"""

    accounts = serializers.ListField(child=serializers.DictField())


class GameAccountGroupSerializer(serializers.ModelSerializer):
    """账户分组序列化器"""

    account_count = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = GameAccountGroup
        fields = ['id', 'owner', 'name', 'slug', 'account_count', 'created_at']
        read_only_fields = ['id', 'owner', 'created_at']

    @extend_schema_field(OpenApiTypes.INT)
    def get_account_count(self, obj):
        return obj.accounts.count()

    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        slug = validated_data.get('slug', '')
        if not slug:
            import re
            slug = re.sub(r'[^a-z0-9_\u4e00-\u9fff]+', '_', validated_data['name'].lower().strip())
        validated_data['slug'] = slug
        return super().create(validated_data)


class APIKeySerializer(serializers.ModelSerializer):
    """API Key serializer for CRUD operations.

    On create, generates a plain key using secrets.token_urlsafe(32),
    hashes it with SHA-256 for storage, and returns the plain key in the response.
    On list/retrieve, the key_hash is masked (first 8 chars + '...').
    """

    key_display = serializers.SerializerMethodField(read_only=True)
    plain_key = serializers.CharField(read_only=True, required=False)

    class Meta:
        model = APIKey
        fields = [
            'id', 'name', 'permissions', 'ip_whitelist',
            'call_count', 'expires_at', 'is_active', 'created_at',
            'key_display', 'plain_key',
        ]
        read_only_fields = ['id', 'created_at']

    @extend_schema_field(OpenApiTypes.STR)
    def get_key_display(self, obj):
        """Return a masked version of key_hash (first 8 chars + '...')."""
        if obj.key_hash:
            return f"{obj.key_hash[:8]}..."
        return ''

    def create(self, validated_data):
        """Generate a plain API key, hash it, and save the hash."""
        import hashlib
        import secrets

        plain_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(plain_key.encode()).hexdigest()

        validated_data['key_hash'] = key_hash
        validated_data['user'] = self.context['request'].user
        instance = super().create(validated_data)

        # Attach plain_key to instance for response serialization
        instance._plain_key = plain_key
        return instance

    def to_representation(self, instance):
        """Include plain_key in the response only for newly created instances."""
        data = super().to_representation(instance)
        if hasattr(instance, '_plain_key') and instance._plain_key:
            data['plain_key'] = instance._plain_key
        return data


class AuditLogSerializer(serializers.ModelSerializer):
    """审计日志序列化器 — R37-P3 从 tasks app 迁入 accounts (TD-039)。"""

    username = serializers.CharField(source='user.username', read_only=True, allow_null=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'user', 'username', 'action', 'resource_type', 'resource_id', 'details', 'ip_address', 'created_at']
        read_only_fields = ['id', 'created_at']
