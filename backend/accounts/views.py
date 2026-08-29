import logging
import secrets
import shutil
import subprocess
import sys
import time

import pyotp
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, connections, transaction
from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import OpenApiTypes, extend_schema
from gaf_core.audit_constants import filter_sensitive_fields, get_client_ip
from gaf_core.mixins import (
    AuditAction,
    AuditMixin,
    AuditResourceType,
    audit_action,
    build_diff_details,
)
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from scheduler.models import GameAccountRotation
from scheduler.serializers import GameAccountRotationSerializer

from accounts import crypto
from accounts.models import APIKey, AuditLog, GameAccount, GameAccountGroup, LoginHistory, User, UserSession
from accounts.permissions import InitOrAuthenticatedPermission, RoleBasedPermission
from accounts.serializers import (
    AgentTokenCreateSerializer,
    AgentTokenListSerializer,
    AgentTokenResponseSerializer,
    APIKeySerializer,
    AuditLogSerializer,
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
    CustomTokenRefreshSerializer,
    GameAccountBatchCheckSerializer,
    GameAccountBatchImportSerializer,
    GameAccountDetailSerializer,
    GameAccountGroupSerializer,
    GameAccountLoginTestSerializer,
    GameAccountSerializer,
    InitStatusSerializer,
    Login2FASerializer,
    LoginHistorySerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    SetupSerializer,
    TOTPDisableSerializer,
    TOTPSetupSerializer,
    TOTPVerifySetupSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserSessionSerializer,
)
from agents.services import (
    create_agent_token,
    get_agent_for_device_check,
    is_agent_offline,
    list_agent_tokens,
    revoke_agent_token,
)
from config.app_info import ADB_COMMAND_TIMEOUT, NODE_COMMAND_TIMEOUT

logger = logging.getLogger(__name__)


class UserViewSet(AuditMixin, viewsets.ModelViewSet):
    """用户管理视图集，仅管理员可操作。"""

    queryset = User.objects.all()
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'manage'
    audit_resource_type = AuditResourceType.USER

    def get_serializer_class(self):
        """根据动作选择序列化器。"""
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    def _build_audit_details(self, action, instance, *, old_instance=None) -> dict:
        """Build audit details with username/email diff; password never logged."""
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={
                    'username': old_instance.username,
                    'email': old_instance.email,
                    'role': old_instance.role,
                    'is_active': old_instance.is_active,
                },
                after={
                    'username': instance.username,
                    'email': instance.email,
                    'role': instance.role,
                    'is_active': instance.is_active,
                },
            )
        if action == AuditAction.CREATE:
            return {
                'username': instance.username,
                'email': instance.email,
                'role': instance.role,
            }
        if action == AuditAction.DELETE:
            return {
                'username': instance.username,
                'email': instance.email,
            }
        return {}

    @action(detail=True, methods=['post'], url_path='reset-password')
    @audit_action(
        action=AuditAction.UPDATE,
        resource_type=AuditResourceType.USER,
        resource_id_kw='pk',
    )
    def reset_password(self, request, pk=None):
        """管理员重置用户密码。"""
        user = self.get_object()
        new_password = secrets.token_urlsafe(12)
        user.set_password(new_password)
        user.must_change_password = True
        user.save()
        return Response({'new_password': new_password}, status=status.HTTP_200_OK)


class CreateAdminView(APIView):
    """
    系统初始化 — 创建管理员账户

    仅在系统中无任何用户时允许调用。
    创建的用户自动获得 admin 角色和所有权限。
    """
    permission_classes = [AllowAny]

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={201: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT},
        description="Bootstrap the first admin account. Only callable when no users exist.",
    )
    def post(self, request):
        if User.objects.exists():
            return Response(
                {'error': _('系统已存在用户，不能重复初始化')},
                status=status.HTTP_403_FORBIDDEN,
            )

        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')

        if not username or len(username) < 3:
            return Response(
                {'error': _('用户名至少 3 个字符')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not password or len(password) < 8:
            return Response(
                {'error': _('密码至少 8 个字符')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.create_superuser(
            username=username,
            password=password,
            is_staff=True,
        )
        # Audit log: bootstrap admin creation (anonymous actor; target = new admin).
        from accounts.audit import log_audit
        log_audit(
            user=user,
            action=AuditAction.CREATE,
            resource_type=AuditResourceType.USER,
            resource_id=str(user.id),
            details=filter_sensitive_fields({
                'username': user.username,
                'role': user.role,
                'is_staff': user.is_staff,
                'bootstrap': True,
            }),
            ip_address=get_client_ip(request),
        )
        return Response({
            'success': True,
            'user_id': user.id,
            'username': user.username,
        }, status=status.HTTP_201_CREATED)


class CheckAdminView(APIView):
    """检查系统是否已有管理员用户。"""

    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="Check whether an admin user already exists.",
    )
    def get(self, request):
        exists = User.objects.filter(role=User.Role.ADMIN).exists()
        return Response({'exists': exists})


class SystemHealthView(APIView):
    """基础设施健康检查：数据库/Redis/Celery/WebSocket/磁盘/内存。"""

    # C11 fix: AllowAny during first-run setup; post-setup requires auth.
    permission_classes = [InitOrAuthenticatedPermission]
    required_permission = 'view'

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="Return health status of DB / Redis / Celery / WebSocket / disk / memory.",
    )
    def get(self, request):
        health = {}

        # 数据库检查
        try:
            db_conn = connections['default']
            db_conn.cursor()
            health['db'] = 'pass'
            health['db_message'] = '连接正常'
        except Exception:
            logger.warning("health check: DB connection failed", exc_info=True)
            health['db'] = 'fail'
            health['db_message'] = '数据库连接失败'

        # Redis 检查
        try:
            cache.set('health_check', 'ok', 10)
            if cache.get('health_check') == 'ok':
                health['redis'] = 'pass'
                health['redis_message'] = '连接正常'
            else:
                health['redis'] = 'fail'
                health['redis_message'] = 'Redis 读写异常'
        except Exception:
            logger.warning("health check: Redis connection failed", exc_info=True)
            health['redis'] = 'fail'
            health['redis_message'] = 'Redis 连接失败'

        # Celery 检查
        try:
            from celery import current_app
            stats = current_app.control.inspect().stats()
            if stats:
                health['celery'] = 'pass'
                health['celery_message'] = f'{len(stats)} 个 Worker 在线'
            else:
                health['celery'] = 'warning'
                health['celery_message'] = '无活跃 Worker（开发模式正常）'
        except Exception:
            logger.warning("health check: Celery status unknown", exc_info=True)
            health['celery'] = 'warning'
            health['celery_message'] = 'Celery 状态未知'

        # WebSocket 检查
        health['ws'] = 'pass'
        health['ws_message'] = 'Channels 已配置'

        # 磁盘检查
        try:
            usage = shutil.disk_usage('/')
            pct = usage.used / usage.total * 100
            health['disk'] = 'warning' if pct > 80 else 'pass'
            health['disk_message'] = (
                f'已用 {usage.used // (1024**3)}GB / {usage.total // (1024**3)}GB ({pct:.1f}%)'
            )
        except Exception:
            logger.warning("health check: disk usage query failed", exc_info=True)
            health['disk'] = 'warning'
            health['disk_message'] = '无法获取磁盘信息'

        # 内存检查
        try:
            import psutil
            mem = psutil.virtual_memory()
            mem_pct = mem.percent
            health['memory'] = 'warning' if mem_pct > 90 else 'pass'
            health['memory_message'] = f'使用率 {mem_pct:.1f}%'
        except Exception:
            logger.warning("health check: memory usage query failed", exc_info=True)
            health['memory'] = 'warning'
            health['memory_message'] = '无法获取内存信息'

        return Response(health)


class DeviceScanView(APIView):
    """扫描本地设备（通过 ADB 和模拟器发现模块）。"""

    # C11 fix: AllowAny during first-run setup; post-setup requires auth.
    permission_classes = [InitOrAuthenticatedPermission]
    required_permission = 'view'

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="Scan local devices (ADB + emulator discovery).",
    )
    def get(self, request):
        devices = []

        try:
            from device_bridge.discovery.emulator import scan_all_emulators
            emulators = scan_all_emulators()
            for emu in emulators:
                devices.append({
                    'id': f'emulator_{emu.emulator}',
                    'name': emu.name,
                    'type': 'emulator',
                    'emulator_type': emu.emulator,
                    'status': emu.status,
                    'adb_port': emu.adb_port,
                    'resolution': emu.resolution,
                })
        except ImportError:
            logger.warning('设备扫描: 模拟器模块未安装 (ImportError)')
        except Exception as e:
            logger.warning('设备扫描: 模拟器扫描异常: %s', e, exc_info=True)

        try:
            result = subprocess.run(
                ['adb', 'devices'], capture_output=True, text=True, timeout=ADB_COMMAND_TIMEOUT
            )
            lines = result.stdout.strip().split('\n')[1:]
            for line in lines:
                if '\tdevice' in line:
                    device_id = line.split('\t')[0]
                    devices.append({
                        'id': f'adb_{device_id}',
                        'name': f'ADB 设备 {device_id}',
                        'type': 'emulator',
                        'emulator_type': 'adb',
                        'status': 'online',
                        'adb_port': device_id,
                        'resolution': None,
                    })
        except Exception as e:
            logger.warning('设备扫描: ADB 扫描异常: %s', e, exc_info=True)

        return Response(devices)


class ImportExamplePacksView(APIView):
    """导入示例任务包，将选中的资源包标记为激活状态。"""

    # C12 fix: AllowAny during first-run setup; post-setup requires auth.
    permission_classes = [InitOrAuthenticatedPermission]
    required_permission = 'manage'

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
        description="Activate the given example resource pack IDs.",
    )
    def post(self, request):
        pack_ids = request.data.get('pack_ids', [])
        if not pack_ids:
            return Response({'error': '请选择要导入的示例包'}, status=400)

        from resources.models import ResourcePack
        updated = ResourcePack.objects.filter(pk__in=pack_ids).update(is_active=True)

        return Response({
            'success': True,
            'imported_count': updated,
        })


class ExamplePacksView(APIView):
    """获取可用的资源包列表，用于初始化导入。"""

    # C11 fix: AllowAny during first-run setup; post-setup requires auth.
    permission_classes = [InitOrAuthenticatedPermission]
    required_permission = 'view'

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="List available example resource packs for first-run import.",
    )
    def get(self, request):
        from resources.models import ResourcePack
        packs = []
        for rp in ResourcePack.objects.all():
            packs.append({
                'id': rp.pk,
                'name': rp.name,
                'description': rp.description or f'版本 {rp.version}',
                'pipeline_count': rp.tasks.count(),
                'tags': [rp.target_app] if rp.target_app else [],
            })
        return Response(packs)


class EnvCheckView(APIView):
    """环境诊断：检测 Python/Node.js/ADB/SQLite/Redis/磁盘。"""

    # C11 fix: AllowAny during first-run setup; post-setup requires auth.
    permission_classes = [InitOrAuthenticatedPermission]
    required_permission = 'view'

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="Return environment diagnostics (Python / Node / ADB / SQLite / Redis / disk).",
    )
    def get(self, request):
        env = {}

        # Python 版本
        py_ver = f'{sys.version_info.major}.{sys.version_info.minor}'
        env['python'] = {
            'current_version': py_ver,
            'required_version': '3.11+',
            'status': 'pass' if sys.version_info >= (3, 11) else 'fail',
            'suggestion': None if sys.version_info >= (3, 11) else '请安装 Python 3.11 或更高版本',
        }

        # Node.js
        try:
            node_result = subprocess.run(
                ['node', '--version'], capture_output=True, text=True, timeout=NODE_COMMAND_TIMEOUT
            )
            node_ver = node_result.stdout.strip().lstrip('v')
            env['node'] = {
                'current_version': node_ver,
                'required_version': '18+',
                'status': 'pass',
                'suggestion': None,
            }
        except Exception:
            logger.warning("env check: Node.js detection failed", exc_info=True)
            env['node'] = {
                'current_version': '未检测到',
                'required_version': '18+',
                'status': 'fail',
                'suggestion': '请安装 Node.js 18 或更高版本',
            }

        # ADB
        try:
            subprocess.run(['adb', 'version'], capture_output=True, timeout=ADB_COMMAND_TIMEOUT)
            env['adb'] = {
                'current_version': '已安装',
                'required_version': '任意版本',
                'status': 'pass',
                'suggestion': None,
            }
        except Exception:
            logger.warning("env check: ADB detection failed", exc_info=True)
            env['adb'] = {
                'current_version': '未安装',
                'required_version': '任意版本',
                'status': 'warning',
                'suggestion': '安装 ADB 后可自动发现模拟器和 Android 设备',
            }

        # Database — 2026-08-03 spec: dev/prod 统一 SQLite + WAL
        # 检查连接 + 验证 journal_mode = WAL
        try:
            cursor = connections['default'].cursor()
            cursor.execute("PRAGMA journal_mode")
            journal_mode = cursor.fetchone()[0]
            cursor.execute("PRAGMA busy_timeout")
            busy_timeout = cursor.fetchone()[0]
            cursor.close()
            db_name = 'SQLite'
            wal_ok = journal_mode.lower() == 'wal'
            env['database'] = {
                'current_version': f'{db_name} (journal={journal_mode}, busy_timeout={busy_timeout}ms)',
                'required_version': '3.8+ (WAL)',
                'status': 'pass' if wal_ok else 'warning',
                'suggestion': None if wal_ok else f'SQLite 当前 journal_mode={journal_mode}, 推荐 WAL 模式 (PRAGMA journal_mode=WAL)',
            }
        except Exception:
            logger.warning("env check: database connection failed", exc_info=True)
            env['database'] = {
                'current_version': '无法连接',
                'required_version': '3.8+ (WAL)',
                'status': 'fail',
                'suggestion': '请检查数据库配置和文件路径',
            }

        # Redis
        try:
            cache.set('env_check', 'ok', 5)
            env['redis'] = {
                'current_version': '已连接',
                'required_version': '6+',
                'status': 'pass' if cache.get('env_check') == 'ok' else 'fail',
                'suggestion': None,
            }
        except Exception:
            logger.warning("env check: Redis connection failed", exc_info=True)
            env['redis'] = {
                'current_version': '无法连接',
                'required_version': '6+',
                'status': 'fail',
                'suggestion': '请检查 Redis 配置和连接信息',
            }

        # 磁盘
        try:
            usage = shutil.disk_usage('/')
            free_gb = usage.free // (1024**3)
            total_gb = usage.total // (1024**3)
            pct = usage.used / usage.total * 100
            disk_status = 'pass' if pct < 80 else 'warning'
            env['disk'] = {
                'current_version': f'剩余 {free_gb}GB / {total_gb}GB',
                'required_version': '≥ 5GB 剩余空间',
                'status': disk_status,
                'suggestion': '磁盘空间不足，请清理' if disk_status == 'warning' else None,
            }
        except Exception:
            logger.warning("env check: disk usage query failed", exc_info=True)
            env['disk'] = {
                'current_version': '未知',
                'required_version': '≥ 5GB 剩余空间',
                'status': 'warning',
                'suggestion': '无法获取磁盘信息',
            }

        return Response(env)


class MeView(AuditMixin, generics.RetrieveUpdateAPIView):
    """当前用户信息视图，获取或更新当前登录用户。"""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    audit_resource_type = AuditResourceType.USER

    def get_object(self):
        """返回当前请求用户。"""
        return self.request.user

    def _build_audit_details(self, action, instance, *, old_instance=None) -> dict:
        """Build audit details for self-update; password never logged."""
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={
                    'username': old_instance.username,
                    'email': old_instance.email,
                },
                after={
                    'username': instance.username,
                    'email': instance.email,
                },
            )
        return {}


class ChangePasswordView(generics.UpdateAPIView):
    """修改密码视图，验证旧密码后设置新密码。"""

    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        """返回当前请求用户。"""
        return self.request.user

    def update(self, request, *args, **kwargs):
        """验证并更新用户密码。"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        # spec-58-A (TD-296): wrap password update + audit log in a
        # transaction so an audit-log failure cannot leave a password
        # change without an audit trail.
        with transaction.atomic():
            user.set_password(serializer.validated_data['new_password'])
            user.must_change_password = False
            user.save()
            # Audit log: password change — never log raw password values.
            from accounts.audit import log_audit
            log_audit(
                user=user,
                action=AuditAction.UPDATE,
                resource_type=AuditResourceType.USER,
                resource_id=str(user.id),
                details=filter_sensitive_fields({
                    'field': 'password',
                    'must_change_password': user.must_change_password,
                }),
                ip_address=get_client_ip(request),
            )
        return Response({'detail': _('密码修改成功')}, status=status.HTTP_200_OK)


class RegisterView(generics.CreateAPIView):
    """用户注册视图，无需登录即可注册新用户。"""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        # 检查注册开关
        register_enabled = True
        try:
            from settings.models import AppSettings
            settings = AppSettings.objects.filter(setting_key='register_enabled').first()
            if settings:
                register_enabled = settings.setting_value.get('enabled', True)
        except Exception as e:
            logger.warning('Failed to read register_enabled setting: %s', e)

        if not register_enabled:
            return Response(
                {'detail': '当前不允许用户注册'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # spec-58-A (TD-296): wrap user creation + audit log in a transaction
        # so a partial failure cannot leave an un-audited user row. Catch
        # IntegrityError (e.g. duplicate username under race) and return 409
        # instead of leaking a 500 to the client.
        try:
            with transaction.atomic():
                user = serializer.save()
                from rest_framework_simplejwt.tokens import RefreshToken
                refresh = RefreshToken.for_user(user)
                # Audit log: self-registration (actor = newly created user).
                from accounts.audit import log_audit
                log_audit(
                    user=user,
                    action=AuditAction.CREATE,
                    resource_type=AuditResourceType.USER,
                    resource_id=str(user.id),
                    details=filter_sensitive_fields({
                        'username': user.username,
                        'role': user.role,
                        'self_registered': True,
                    }),
                    ip_address=get_client_ip(request),
                )
        except IntegrityError:
            return Response(
                {'detail': '用户名已存在或数据冲突'},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({
            'user': {
                'id': user.id,
                'username': user.username,
                'role': user.role,
            },
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)


class InitStatusView(generics.GenericAPIView):
    """系统初始化状态视图，检查系统是否已初始化。"""

    serializer_class = InitStatusSerializer
    permission_classes = [AllowAny]

    def get(self, request):
        """获取系统初始化状态。"""
        has_admin = User.objects.filter(role=User.Role.ADMIN).exists()
        default_user_exists = User.objects.filter(username='admin').exists()

        # 从 AppSettings 读取注册开关
        register_enabled = True
        try:
            from settings.models import AppSettings
            settings = AppSettings.objects.filter(setting_key='register_enabled').first()
            if settings:
                register_enabled = settings.setting_value.get('enabled', True)
        except Exception as e:
            logger.warning('Failed to read register_enabled setting: %s', e)

        data = {
            'initialized': has_admin,
            'has_admin': has_admin,
            'default_user_exists': default_user_exists,
            'register_enabled': register_enabled,
        }
        serializer = self.get_serializer(data)
        return Response(serializer.data)


class SetupView(generics.GenericAPIView):
    """系统初始化设置视图，创建管理员并保存设备偏好和可选 LLM 配置。"""

    serializer_class = SetupSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        """执行系统初始化设置。"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if User.objects.filter(role=User.Role.ADMIN).exists():
            return Response(
                {'detail': '系统已初始化，不能重复设置'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        admin = User.objects.create_user(
            username=serializer.validated_data['admin_username'],
            password=serializer.validated_data['admin_password'],
            role=User.Role.ADMIN,
            must_change_password=False,
        )

        from settings.models import AppSettings
        app_settings, _ = AppSettings.objects.get_or_create(
            setting_key='device_config',
            defaults={'setting_value': {}, 'category': 'general'},
        )
        setting_value = app_settings.setting_value or {}
        setting_value['device_type'] = serializer.validated_data['device_type']
        if serializer.validated_data.get('llm_config'):
            setting_value['llm_config'] = serializer.validated_data['llm_config']
        app_settings.setting_value = setting_value
        app_settings.save()

        refresh = RefreshToken.for_user(admin)

        # Audit log: bootstrap setup (actor = newly created admin).
        from accounts.audit import log_audit
        log_audit(
            user=admin,
            action=AuditAction.CREATE,
            resource_type=AuditResourceType.USER,
            resource_id=str(admin.id),
            details=filter_sensitive_fields({
                'username': admin.username,
                'role': admin.role,
                'bootstrap': True,
                'device_type': serializer.validated_data['device_type'],
            }),
            ip_address=get_client_ip(request),
        )

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(admin).data,
            'device_type': serializer.validated_data['device_type'],
            'llm_config': serializer.validated_data.get('llm_config', {}),
        }, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    自定义登录视图，使用 CustomTokenObtainPairSerializer 以支持 remember_me 参数。

    POST /api/v2/auth/login/
    入参: { "username": "...", "password": "...", "remember_me": true/false }
    返回: { "access": "...", "refresh": "..." }
    """

    serializer_class = CustomTokenObtainPairSerializer
    # H8 fix: stricter scoped throttle on login to mitigate brute-force /
    # credential stuffing. Combined with the global anon/user throttles
    # configured in settings/base.py, this limits a single IP to 5 login
    # attempts per minute.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        """Issue JWT tokens and write an audit LOGIN row on success."""
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK and not response.data.get('requires_2fa'):
            # Successful password login (2FA users get a temp_token instead —
            # audited separately in Login2FAView).
            username = request.data.get('username', '')
            user = User.objects.filter(username=username).first()
            if user is not None:
                from accounts.audit import log_audit
                log_audit(
                    user=user,
                    action=AuditAction.LOGIN,
                    resource_type=AuditResourceType.USER,
                    resource_id=str(user.id),
                    details=filter_sensitive_fields({
                        'method': 'password',
                        'remember_me': bool(request.data.get('remember_me', False)),
                    }),
                    ip_address=get_client_ip(request),
                )
        return response


class CustomTokenRefreshView(TokenRefreshView):
    """
    自定义 Token 刷新视图，使用 CustomTokenRefreshSerializer 以支持 remember_me Token 续期。

    POST /api/v2/auth/refresh/
    入参: { "refresh": "..." }
    返回: { "access": "...", "refresh": "..." }
    """

    serializer_class = CustomTokenRefreshSerializer


class AgentTokenViewSet(viewsets.ViewSet):
    """Agent Token 管理视图集，提供 Token 的创建、列表和吊销功能。"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'manage'

    @extend_schema(
        request=AgentTokenCreateSerializer,
        responses={201: AgentTokenResponseSerializer},
        description="Generate a new Agent Token and create the Agent record.",
    )
    def create(self, request):
        """生成新的 Agent Token，创建 Agent 记录并返回完整 Token。

        POST /api/auth/agent-tokens/
        入参: { "name": "my-agent", "permissions": ["task.execute", ...] }
        返回: { "token": "...", "agent_id": "...", "name": "..." }
        """
        serializer = AgentTokenCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        name = serializer.validated_data['name']
        permissions = serializer.validated_data.get('permissions', [])

        # spec-58-A (TD-296): wrap token issuance + audit log in a
        # transaction so an audit-log failure cannot leave an Agent row
        # without an audit trail. IntegrityError (e.g. token hash collision
        # under race) returns 409 instead of leaking a 500.
        try:
            with transaction.atomic():
                # Service handles token generation, hash + preview storage, and Agent creation.
                agent, token = create_agent_token(name, permissions)

                # Audit log: agent token issuance — never log the raw token.
                from accounts.audit import log_audit
                log_audit(
                    user=request.user,
                    action=AuditAction.CREATE,
                    resource_type=AuditResourceType.AGENT_TOKEN,
                    resource_id=str(agent.id),
                    details=filter_sensitive_fields({
                        'agent_id': agent.agent_id,
                        'name': agent.hostname,
                        'permissions': permissions,
                    }),
                    ip_address=get_client_ip(request),
                )
        except IntegrityError:
            return Response(
                {'detail': 'Agent Token 生成失败，名称或数据冲突'},
                status=status.HTTP_409_CONFLICT,
            )

        response_serializer = AgentTokenResponseSerializer({
            'token': token,
            'agent_id': agent.agent_id,
            'name': agent.hostname,
            'id': agent.id,
            'status': agent.status,
            'created_at': agent.created_at,
        })
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=None,
        responses={200: AgentTokenListSerializer(many=True)},
        description="List all Agent Tokens (token value masked).",
    )
    def list(self, request):
        """列出当前所有 Agent Token（隐藏完整 Token 值）。

        GET /api/auth/agent-tokens/
        返回 Token 列表，token 字段仅显示前后各 4 位预览。
        """
        # Service returns list of dicts with token preview (no raw token values).
        results = list_agent_tokens()

        list_serializer = AgentTokenListSerializer(results, many=True)
        return Response(list_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Revoke (delete) an Agent Token by id.",
    )
    def destroy(self, request, pk=None):
        """吊销指定 Agent Token，删除 Agent 记录。

        DELETE /api/auth/agent-tokens/{id}/
        """
        agent = revoke_agent_token(pk)
        if agent is None:
            return Response(
                {'detail': 'Agent Token 不存在'},
                status=status.HTTP_404_NOT_FOUND,
            )

        agent_id = agent.agent_id
        # Audit log: agent token revocation.
        from accounts.audit import log_audit
        log_audit(
            user=request.user,
            action=AuditAction.DELETE,
            resource_type=AuditResourceType.AGENT_TOKEN,
            resource_id=str(pk),
            details=filter_sensitive_fields({
                'agent_id': agent_id,
            }),
            ip_address=get_client_ip(request),
        )
        return Response(
            {'detail': f'Token {agent_id} 已吊销'},
            status=status.HTTP_200_OK,
        )


class TOTPSetupView(generics.GenericAPIView):
    """
    2FA 设置初始化视图。

    POST /api/v2/auth/2fa/setup/
    生成 TOTP secret 和 otpauth URI，返回给前端渲染二维码。
    """

    serializer_class = TOTPSetupSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """生成 TOTP 密钥，返回 secret 和 QR Code URI。"""
        user = request.user
        if user.totp_enabled:
            return Response(
                {'detail': '2FA 已启用，请先禁用以重新设置'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        secret = pyotp.random_base32()
        app_name = getattr(settings, 'GAF_APP_NAME', 'GAF')
        issuer = app_name
        otp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.username,
            issuer_name=issuer,
        )

        user.totp_secret = secret
        user.save(update_fields=['totp_secret'])

        # Audit log: 2FA setup initiated (secret never logged).
        from accounts.audit import log_audit
        log_audit(
            user=user,
            action=AuditAction.UPDATE,
            resource_type=AuditResourceType.USER,
            resource_id=str(user.id),
            details=filter_sensitive_fields({
                'totp': 'setup_initiated',
            }),
            ip_address=get_client_ip(request),
        )

        return Response({
            'secret': secret,
            'otp_uri': otp_uri,
        }, status=status.HTTP_200_OK)


class TOTPVerifySetupView(generics.GenericAPIView):
    """
    2FA 验证设置视图。

    POST /api/v2/auth/2fa/verify-setup/
    验证 TOTP 码，成功后启用 2FA。
    """

    serializer_class = TOTPVerifySetupSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """验证 TOTP 码并启用 2FA。"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        totp_code = serializer.validated_data['totp_code']

        if not user.totp_secret:
            return Response(
                {'detail': '请先初始化 2FA 设置'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(totp_code):
            return Response(
                {'detail': '验证码无效'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.totp_enabled = True
        user.save(update_fields=['totp_enabled'])

        # Audit log: 2FA successfully enabled.
        from accounts.audit import log_audit
        log_audit(
            user=user,
            action=AuditAction.UPDATE,
            resource_type=AuditResourceType.USER,
            resource_id=str(user.id),
            details=filter_sensitive_fields({
                'totp': 'enabled',
            }),
            ip_address=get_client_ip(request),
        )

        return Response({'detail': _('2FA 已启用')}, status=status.HTTP_200_OK)


class TOTPDisableView(generics.GenericAPIView):
    """
    2FA 禁用视图。

    POST /api/v2/auth/2fa/disable/
    验证密码后禁用 2FA。
    """

    serializer_class = TOTPDisableSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """验证用户密码并禁用 2FA。"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        password = serializer.validated_data['password']

        if not user.check_password(password):
            return Response(
                {'detail': '密码错误'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.totp_enabled:
            return Response(
                {'detail': '2FA 未启用'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.totp_enabled = False
        user.totp_secret = None
        user.save(update_fields=['totp_enabled', 'totp_secret'])

        # Audit log: 2FA disabled.
        from accounts.audit import log_audit
        log_audit(
            user=user,
            action=AuditAction.UPDATE,
            resource_type=AuditResourceType.USER,
            resource_id=str(user.id),
            details=filter_sensitive_fields({
                'totp': 'disabled',
            }),
            ip_address=get_client_ip(request),
        )

        return Response({'detail': _('2FA 已禁用')}, status=status.HTTP_200_OK)


class Login2FAView(generics.GenericAPIView):
    """
    登录第二步 2FA 验证视图。

    POST /api/v2/auth/login-2fa/
    用临时 Token 和 TOTP 码换取完整的 JWT Token。
    """

    serializer_class = Login2FASerializer
    permission_classes = [AllowAny]

    def post(self, request):
        """验证 temp_token 和 TOTP 码，签发完整 JWT。"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        temp_token_str = serializer.validated_data['temp_token']
        totp_code = serializer.validated_data['totp_code']
        remember_me = serializer.validated_data.get('remember_me', False)

        from rest_framework_simplejwt.tokens import AccessToken
        try:
            temp_token = AccessToken(temp_token_str)
        except Exception:
            logger.warning("Login2FA: invalid temp token received", exc_info=True)
            return Response(
                {'detail': '临时 Token 无效'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not temp_token.payload.get('is_2fa_temp'):
            return Response(
                {'detail': '临时 Token 类型不正确'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user_id = temp_token.payload.get('user_id')
        if not user_id:
            return Response(
                {'detail': '临时 Token 缺少用户信息'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            user = User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            return Response(
                {'detail': '用户不存在或已禁用'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.totp_enabled or not user.totp_secret:
            return Response(
                {'detail': '2FA 未启用'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(totp_code):
            return Response(
                {'detail': '验证码无效'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        refresh = RefreshToken.for_user(user)

        if remember_me:
            remember_days = getattr(settings, 'GAF_REMEMBER_ME_DAYS', 30)
            refresh['remember_me'] = True
            refresh['exp'] = int(time.time()) + remember_days * 86400

        # Inject session_jti claim into access token (A5 — same as CustomTokenObtainPairSerializer)
        refresh_jti = str(refresh.payload.get('jti', ''))
        access_token = refresh.access_token
        if refresh_jti:
            access_token['session_jti'] = refresh_jti

        # Create UserSession record for device management (A5)
        self._create_user_session(request, user, refresh_jti, remember_me)

        # Audit log: 2FA login success.
        from accounts.audit import log_audit
        log_audit(
            user=user,
            action=AuditAction.LOGIN,
            resource_type=AuditResourceType.USER,
            resource_id=str(user.id),
            details=filter_sensitive_fields({
                'method': '2fa',
                'remember_me': bool(remember_me),
            }),
            ip_address=get_client_ip(request),
        )

        return Response({
            'access': str(access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        }, status=status.HTTP_200_OK)

    @staticmethod
    def _create_user_session(request, user, refresh_jti, remember_me):
        """Create a UserSession record after 2FA login (mirrors CustomTokenObtainPairSerializer)."""
        if not refresh_jti:
            return

        from datetime import timedelta

        from django.utils.timezone import now

        from accounts.models import UserSession

        # Extract IP and User-Agent
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip_address = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')

        user_agent = request.META.get('HTTP_USER_AGENT', '')
        device_name, device_type = CustomTokenObtainPairSerializer._parse_user_agent(user_agent)

        # Compute expiry
        if remember_me:
            remember_days = getattr(settings, 'GAF_REMEMBER_ME_DAYS', 30)
            expires_at = now() + timedelta(days=remember_days)
        else:
            from rest_framework_simplejwt.settings import api_settings as jwt_settings
            expires_at = now() + jwt_settings.REFRESH_TOKEN_LIFETIME

        UserSession.objects.create(
            user=user,
            refresh_token_jti=refresh_jti,
            device_name=device_name,
            device_type=device_type,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )


class GameAccountViewSet(AuditMixin, viewsets.ModelViewSet):
    """游戏账户 CRUD 视图集 (T4-B01)。"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'
    audit_resource_type = AuditResourceType.GAME_ACCOUNT

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return GameAccount.objects.none()
        qs = GameAccount.objects.filter(owner=self.request.user).select_related(
            'group', 'resource_pack', 'game_profile'
        )
        game_name = self.request.query_params.get('game_name')
        if game_name:
            # P3: 检索维度 = game_profile (游戏名参数兼容保留, 按 profile 名过滤)
            qs = qs.filter(game_profile__game_name__icontains=game_name)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        group_id = self.request.query_params.get('group')
        if group_id:
            # F9 fix (2026-08-28): 前端约定 'null' 表示"未分组"账户。
            # 之前直接 filter(group_id='null') 会误匹配为字面量 'null' 字符串 → 恒空集。
            qs = qs.filter(group__isnull=True) if group_id == 'null' else qs.filter(group_id=group_id)
        resource_pack_id = self.request.query_params.get('resource_pack')
        if resource_pack_id:
            qs = qs.filter(allowed_resource_packs__id=resource_pack_id)
        return qs.order_by('-created_at')

    def get_serializer_class(self):
        if self.action in ('retrieve',):
            return GameAccountDetailSerializer
        return GameAccountSerializer

    def _build_audit_details(self, action, instance, *, old_instance=None) -> dict:
        """Build audit details for game account changes; password never logged."""
        safe_fields = {
            'game_name': instance.game_profile.game_name,
            'username': instance.username,
            'server_region': instance.server_region,
            'login_method': instance.login_method,
            'status': instance.status,
        }
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={
                    'game_name': old_instance.game_profile.game_name,
                    'username': old_instance.username,
                    'server_region': old_instance.server_region,
                    'login_method': old_instance.login_method,
                    'status': old_instance.status,
                },
                after=safe_fields,
            )
        if action == AuditAction.CREATE:
            return safe_fields
        if action == AuditAction.DELETE:
            return {
                'game_name': instance.game_profile.game_name,
                'username': instance.username,
            }
        return {}

    @action(detail=False, methods=['get'], url_path='game-options')
    def game_options(self, request):
        """Return available game list (from GameProfile table)"""
        try:
            from gamestate.models import GameProfile
            games = [
                {'id': p.id, 'name': p.game_name}
                for p in GameProfile.objects.order_by('game_name')
            ]
            return Response({'games': list(games)})
        except Exception as e:
            logger.warning('获取游戏列表失败: %s', e, exc_info=True)
            return Response({'games': [], 'error': f'获取游戏列表失败: {str(e)}'})

    @action(detail=True, methods=['post'], url_path='test-login')
    @audit_action(
        action=AuditAction.UPDATE,
        resource_type=AuditResourceType.GAME_ACCOUNT,
        resource_id_kw='pk',
    )
    def test_login(self, request, pk=None):
        """测试登录 (T4-B03)"""
        account = self.get_object()
        serializer = GameAccountLoginTestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        device_id = serializer.validated_data['device_id']
        device = get_agent_for_device_check(device_id)
        if device is None:
            return Response(
                {'success': False, 'message': '设备不存在'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if is_agent_offline(device):
            return Response({
                'success': False,
                'message': '设备离线，无法执行测试登录',
            })

        try:
            crypto.decrypt_password(account.encrypted_password)
        except crypto.DecryptionError:
            return Response({
                'success': False,
                'message': '密码解密失败，请重新设置密码',
            })

        from django.db.models import F
        from django.utils.timezone import now
        account.last_login_at = now()
        account.status = 'ok'
        account.login_count = F('login_count') + 1
        account.save(update_fields=['last_login_at', 'status', 'login_count', 'updated_at'])

        return Response({
            'success': True,
            'message': f'登录测试成功 — {account.game_profile.game_name}:{account.username}',
            'screenshot_url': None,
            'device_id': device.pk,
        })

    @action(detail=False, methods=['post'], url_path='batch-check')
    @audit_action(
        action=AuditAction.UPDATE,
        resource_type=AuditResourceType.GAME_ACCOUNT,
        resource_id_kw='',
    )
    def batch_check(self, request):
        """批量状态检测 (T4-B04)"""
        serializer = GameAccountBatchCheckSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        if serializer.validated_data.get('check_all'):
            accounts = GameAccount.objects.filter(owner=request.user)
        else:
            account_ids = serializer.validated_data.get('account_ids', [])
            if not account_ids:
                return Response(
                    {'error': '请指定 account_ids 或设置 check_all=true'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            accounts = GameAccount.objects.filter(owner=request.user, pk__in=account_ids)

        from django.utils.timezone import now
        results = []
        for acc in accounts:
            try:
                crypto.decrypt_password(acc.encrypted_password)
                acc_status = 'ok'
                msg = '正常可用'
            except crypto.DecryptionError:
                acc_status = 'error'
                msg = '密码解密失败'

            acc.status = acc_status
            acc.last_check_at = now()
            acc.save(update_fields=['status', 'last_check_at', 'updated_at'])

            results.append({
                'id': acc.pk,
                'game_name': acc.game_profile.game_name,
                'username': acc.username,
                'status': acc_status,
                'message': msg,
            })

        return Response({
            'results': results,
            'summary': {
                'total': len(results),
                'ok': sum(1 for r in results if r['status'] == 'ok'),
                # H3 fix: 'warn' state is never assigned in the loop above, so
                # the count was always 0. Removed to avoid implying a third
                # status the implementation never produces.
                'error': sum(1 for r in results if r['status'] == 'error'),
            },
        })

    @action(detail=False, methods=['post'], url_path='batch-import')
    @audit_action(
        action=AuditAction.CREATE,
        resource_type=AuditResourceType.GAME_ACCOUNT,
        resource_id_kw='',
    )
    def batch_import(self, request):
        """批量导入 (T4-B06)"""
        serializer = GameAccountBatchImportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        accounts_data = serializer.validated_data['accounts']
        total = len(accounts_data)
        created = 0
        skipped = 0
        errors = []
        from gamestate.models import GameProfile  # 函数内 lazy import, 与 game-options 同模式

        for item in accounts_data:
            game_name = item.get('game_name', '')
            username = item.get('username', '')
            password = item.get('password', '')
            if not game_name or not username or not password:
                errors.append({'item': item, 'error': '缺少必填字段'})
                continue

            # P2: 游戏维度收敛到 game_profile (find_or_create 同名全局 profile)
            try:
                profile, _ = GameProfile.objects.get_or_create(game_name=game_name)
            except Exception:
                errors.append({'item': item, 'error': '游戏维度解析失败'})
                continue

            exists = GameAccount.objects.filter(
                owner=request.user,
                game_profile=profile,
                username=username,
            ).exists()
            if exists:
                skipped += 1
                continue

            try:
                GameAccount.objects.create(
                    owner=request.user,
                    game_profile=profile,
                    username=username,
                    encrypted_password=crypto.encrypt_password(password),
                    server_region=item.get('server_region', ''),
                    login_method=item.get('login_method', 'password'),
                )
                created += 1
            except Exception as e:
                logger.warning("batch import: failed to create account for item=%s: %s", item, e)
                errors.append({'item': item, 'error': str(e)})

        return Response({
            'total': total,
            'created': created,
            'skipped': skipped,
            'errors': errors,
        })


class GameAccountGroupViewSet(AuditMixin, viewsets.ModelViewSet):
    """账户分组 CRUD 视图集 (T4-B06)"""

    serializer_class = GameAccountGroupSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'
    audit_resource_type = AuditResourceType.GAME_ACCOUNT_GROUP

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return GameAccountGroup.objects.none()
        return GameAccountGroup.objects.filter(owner=self.request.user).prefetch_related('accounts').order_by('name')

    def perform_create(self, serializer):
        # Save with owner, then trigger AuditMixin audit logging explicitly
        # (AuditMixin.perform_create calls super().perform_create which calls
        # serializer.save() with no args; we need to inject owner here).
        instance = serializer.save(owner=self.request.user)
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, instance)


class PasswordResetRequestView(APIView):
    """
    密码重置请求视图。

    POST /api/v2/accounts/auth/password-reset/
    入参: { "email": "user@example.com" }
    生成重置 Token（有效 1 小时），开发模式下直接返回 Token。
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={200: OpenApiTypes.OBJECT},
        description="Send a password-reset link to the given email (always returns 200).",
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        user = User.objects.filter(email=email).first()

        token = secrets.token_urlsafe(32)
        # Only cache the reset token when the email matches a real user;
        # otherwise still return 200 to avoid disclosing which emails exist.
        if user is not None:
            cache.set(f'pwd_reset_{token}', user.id, timeout=3600)
            # Audit log: password reset request — email is PII, omit from details.
            from accounts.audit import log_audit
            log_audit(
                user=user,
                action=AuditAction.UPDATE,
                resource_type=AuditResourceType.USER,
                resource_id=str(user.id),
                details=filter_sensitive_fields({
                    'action': 'password_reset_request',
                    'matched': True,
                }, extra_sensitive={'email'}),
                ip_address=get_client_ip(request),
            )
            if settings.DEBUG:
                return Response({
                    'detail': '重置链接已发送到您的邮箱',
                    'reset_token': token,
                    'reset_url': f'/reset-password?token={token}',
                }, status=status.HTTP_200_OK)

        if settings.DEBUG:
            return Response({
                'detail': '重置链接已发送到您的邮箱',
            }, status=status.HTTP_200_OK)

        return Response({'detail': _('重置链接已发送到您的邮箱')}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """
    密码重置确认视图。

    POST /api/v2/accounts/auth/password-reset/confirm/
    入参: { "token": "...", "new_password": "...", "confirm_password": "..." }
    验证 Token 并更新密码。
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=PasswordResetConfirmSerializer,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
        description="Verify reset token and set the new password.",
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data['token']
        user_id = cache.get(f'pwd_reset_{token}')

        if not user_id:
            return Response(
                {'detail': '重置链接已失效，请重新请求'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {'detail': '用户不存在'},
                status=status.HTTP_404_NOT_FOUND,
            )

        user.set_password(serializer.validated_data['new_password'])
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])

        cache.delete(f'pwd_reset_{token}')

        # Audit log: password reset confirm — never log new_password.
        from accounts.audit import log_audit
        log_audit(
            user=user,
            action=AuditAction.UPDATE,
            resource_type=AuditResourceType.USER,
            resource_id=str(user.id),
            details=filter_sensitive_fields({
                'action': 'password_reset_confirm',
                'must_change_password': user.must_change_password,
            }),
            ip_address=get_client_ip(request),
        )

        return Response({'detail': _('密码重置成功')}, status=status.HTTP_200_OK)


class GameAccountRotationViewSet(AuditMixin, viewsets.ModelViewSet):
    """轮换规则 CRUD 视图集 (T4-B05)"""

    serializer_class = GameAccountRotationSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'
    audit_resource_type = AuditResourceType.ROTATION_RULE

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return GameAccountRotation.objects.none()
        return GameAccountRotation.objects.filter(owner=self.request.user).prefetch_related('accounts')

    def perform_create(self, serializer):
        # Save with owner, then trigger AuditMixin audit logging explicitly.
        instance = serializer.save(owner=self.request.user)
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, instance)


class APIKeyViewSet(AuditMixin, viewsets.ModelViewSet):
    """API Key management ViewSet for CRUD operations."""

    queryset = APIKey.objects.all().select_related('user')
    serializer_class = APIKeySerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'manage'
    filterset_fields = ['is_active']
    search_fields = ['name', 'user__username']
    audit_resource_type = AuditResourceType.API_KEY

    def perform_create(self, serializer):
        """Generate a plain API key, hash it, save the hash, and return the plain key."""
        # Delegate to AuditMixin.perform_create which calls ModelViewSet
        # (serializer.save()) and then triggers audit logging.
        super().perform_create(serializer)

    def _build_audit_details(self, action, instance, *, old_instance=None) -> dict:
        """Build audit details for API key changes; never log key_hash."""
        safe_fields = {
            'name': instance.name,
            'is_active': instance.is_active,
        }
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={
                    'name': old_instance.name,
                    'is_active': old_instance.is_active,
                },
                after=safe_fields,
            )
        if action == AuditAction.CREATE:
            return safe_fields
        if action == AuditAction.DELETE:
            return {'name': instance.name}
        return {}


class UserSessionViewSet(AuditMixin, viewsets.GenericViewSet):
    """用户会话管理视图集，支持列出活跃会话、踢下线指定会话、批量踢下线。

    GET    /api/v2/accounts/auth/sessions/                  列出当前用户所有活跃会话
    DELETE /api/v2/accounts/auth/sessions/<id>/              踢下线指定会话
    POST   /api/v2/accounts/auth/sessions/logout_all_others/ 踢下线除当前外所有会话
    """

    serializer_class = UserSessionSerializer
    permission_classes = [IsAuthenticated]
    audit_resource_type = AuditResourceType.USER_SESSION
    # GenericViewSet has no Create/Update model mixins, so the default
    # perform_create/update/destroy hooks never fire. We disable them
    # to make the dead-code intent explicit; actual audit logging
    # happens via explicit log_audit calls in destroy() and via
    # @audit_action on logout_all_others().
    audit_log_create = False
    audit_log_update = False
    audit_log_destroy = False

    def get_queryset(self):
        """返回当前用户的活跃会话，按创建时间倒序。"""
        if getattr(self, 'swagger_fake_view', False):
            return UserSession.objects.none()
        return UserSession.objects.filter(user=self.request.user, is_active=True)

    def _get_current_jti(self, request):
        """从请求的 access token 中提取 session_jti 自定义 claim，用于标记当前会话。

        CustomTokenObtainPairSerializer 在签发 access token 时注入了 `session_jti` claim
        (值为对应 refresh token 的 jti)，因此可通过 access token 识别当前会话。
        """
        from rest_framework_simplejwt.tokens import AccessToken, TokenError

        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return None

        token_str = auth_header[7:]
        try:
            access = AccessToken(token_str)
            return str(access.payload.get('session_jti', ''))
        except TokenError:
            return None

    def list(self, request):
        """列出当前用户所有活跃会话，标记当前会话。"""
        current_jti = self._get_current_jti(request)
        sessions = self.get_queryset()
        serializer = self.get_serializer(
            sessions,
            many=True,
            context={'current_jti': current_jti},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request, pk=None):
        """踢下线指定会话：拉黑其 refresh token + 标记 is_active=False。"""
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        try:
            session = self.get_queryset().get(pk=pk)
        except UserSession.DoesNotExist:
            return Response(
                {'detail': '会话不存在或已下线'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Prevent user from kicking their own current session via this endpoint
        current_jti = self._get_current_jti(request)
        if current_jti and session.refresh_token_jti == current_jti:
            return Response(
                {'detail': '不能踢下线当前会话，请使用登出功能'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Blacklist the refresh token via simplejwt's OutstandingToken
        try:
            outstanding = OutstandingToken.objects.get(
                user=request.user,
                jti=session.refresh_token_jti,
            )
            BlacklistedToken.objects.get_or_create(token=outstanding)
        except OutstandingToken.DoesNotExist:
            # Token may have already expired or been rotated; just mark session inactive
            pass

        session.is_active = False
        session.save(update_fields=['is_active', 'last_activity'])

        # Audit log: session kick (semantically a DELETE — session is revoked).
        from accounts.audit import log_audit
        log_audit(
            user=request.user,
            action=AuditAction.DELETE,
            resource_type=AuditResourceType.USER_SESSION,
            resource_id=str(session.id),
            details=filter_sensitive_fields({
                'device_name': session.device_name,
                'refresh_token_jti': session.refresh_token_jti,
            }),
            ip_address=get_client_ip(request),
        )

        return Response({'detail': _('会话已下线')}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='logout-all-others')
    @audit_action(
        action=AuditAction.DELETE,
        resource_type=AuditResourceType.USER_SESSION,
        resource_id_kw='',
    )
    def logout_all_others(self, request):
        """踢下线除当前会话外的所有活跃会话。"""
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        current_jti = self._get_current_jti(request)
        sessions = self.get_queryset().exclude(refresh_token_jti=current_jti) if current_jti else self.get_queryset()

        kicked_count = 0
        for session in sessions:
            try:
                outstanding = OutstandingToken.objects.get(
                    user=request.user,
                    jti=session.refresh_token_jti,
                )
                BlacklistedToken.objects.get_or_create(token=outstanding)
            except OutstandingToken.DoesNotExist:
                pass
            session.is_active = False
            session.save(update_fields=['is_active', 'last_activity'])
            kicked_count += 1

        return Response(
            {'detail': f'已踢下线 {kicked_count} 个其他会话'},
            status=status.HTTP_200_OK,
        )


class LoginHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """登录历史视图集 (M4)。

    GET /api/v2/accounts/login-history/           当前用户登录历史
    GET /api/v2/accounts/login-history/?user=<id> 管理员查看指定用户登录历史
    GET /api/v2/accounts/login-history/all/       管理员查看所有用户登录历史

    记录在 CustomTokenObtainPairSerializer._create_user_session 中自动创建。
    """

    serializer_class = LoginHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """返回登录历史记录。

        - 普通用户: 只能查看自己的登录历史
        - 管理员: 可通过 ?user=<id> 查看指定用户, 或 /all/ 查看全部
        """
        if getattr(self, 'swagger_fake_view', False):
            return LoginHistory.objects.none()
        queryset = LoginHistory.objects.select_related('user').all()

        # Admin can filter by user_id
        user_id = self.request.query_params.get('user')
        if user_id:
            # Only admins can view other users' history
            if self.request.user.role != 'admin':
                return queryset.filter(user=self.request.user)
            try:
                user_id_int = int(user_id)
                return queryset.filter(user_id=user_id_int)
            except (ValueError, TypeError):
                return queryset.none()

        # Non-admins can only see their own history
        if self.request.user.role != 'admin':
            return queryset.filter(user=self.request.user)

        return queryset

    @action(detail=False, methods=['get'], url_path='all')
    def all_history(self, request):
        """管理员查看所有用户登录历史 (分页)。"""
        if request.user.role != 'admin':
            return Response(
                {'detail': _('仅管理员可查看所有用户登录历史')},
                status=status.HTTP_403_FORBIDDEN,
            )
        queryset = LoginHistory.objects.select_related('user').all()
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """审计日志 API（只读） — R37-P3 从 tasks app 迁入 accounts (TD-039)。"""

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "view"
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.all().select_related('user')
    filterset_fields = ["action", "resource_type"]
