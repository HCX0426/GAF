"""
系统设置视图

包含无人值守策略配置的 Upsert API、LLM 配置 API、诊断包生成 API。
"""

import importlib.util
import io
import json
import logging
import sys
import zipfile
from pathlib import Path

import django
from django.conf import settings
from django.db import transaction
from django.db.migrations.recorder import MigrationRecorder
from django.forms.models import model_to_dict
from django.utils.timezone import now as django_now
from drf_spectacular.utils import OpenApiTypes, extend_schema
from gaf_core.audit_constants import get_client_ip
from gaf_core.mixins import (
    AuditAction,
    AuditMixin,
    AuditResourceType,
    build_diff_details,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import RoleBasedPermission, require_permission
from settings.models import AppSettings, FeatureFlag, LLMConfig, UnattendedStrategy
from settings.serializers import (
    AppSettingsSerializer,
    FeatureFlagSerializer,
    LLMConfigSerializer,
    UnattendedStrategySerializer,
)

logger = logging.getLogger(__name__)


def _load_agent_module(module_path: str, attr_name: str | None = None):
    """Load a module from worker/src by file path, avoiding package name clashes.

    Historical note (TD-116 resolved 2026-07-15): the agent code lives under
    ``worker/src/core/...``. Before TD-116, Django had a ``backend/core`` app
    registered as the ``core`` package, so ``from core.xxx`` resolved to
    ``backend/core`` and raised ``ModuleNotFoundError``. The backend app was
    renamed to ``backend/gaf_core/`` to eliminate the collision; this helper
    is retained for robustness but the original collision no longer exists.
    """
    from config.settings.base import BASE_DIR

    file_path = BASE_DIR.parent / 'worker' / 'src' / module_path
    module_name = f'_agent_loaded_{Path(module_path).stem}'
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if attr_name:
        return getattr(module, attr_name)
    return module


class LLMConfigViewSet(AuditMixin, viewsets.ModelViewSet):
    """LLM 大模型配置 CRUD ViewSet (multi-provider support).

    Replaces the former ``llm_config_view`` function-based view. URL paths
    are preserved via ``router.register(r'llm-config', ...)``:
      GET    /llm-config/         — list all configs
      POST   /llm-config/         — create a new config
      GET    /llm-config/{id}/    — retrieve a config
      PUT    /llm-config/{id}/    — update a config
      PATCH  /llm-config/{id}/    — partial update
      DELETE /llm-config/{id}/    — delete a config
    """

    queryset = LLMConfig.objects.all().order_by('-created_at')
    serializer_class = LLMConfigSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'manage'
    audit_resource_type = AuditResourceType.LLM_CONFIG

    @action(detail=True, methods=['post'], url_path='set-active')
    def set_active(self, request, pk=None):
        """Set this LLMConfig as the single active provider.

        Multi-provider exclusivity: marking one row active demotes all
        other rows to inactive, so exactly one provider is in effect.
        URL: POST /llm-config/{id}/set-active/
        """
        obj = self.get_object()
        LLMConfig.objects.filter(is_active=True).exclude(pk=obj.pk).update(is_active=False)
        if not obj.is_active:
            obj.is_active = True
            obj.save(update_fields=['is_active', 'updated_at'])
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=['post'], url_path='test')
    def test_connection(self, request, pk=None):
        """Test connectivity to this provider's LLM API.

        Sends a minimal chat request (10 max_tokens) and returns
        success/failure with latency.  URL: POST /llm-config/{id}/test/
        """
        import time

        obj = self.get_object()
        api_key = obj.get_api_key()
        if not api_key:
            return Response(
                {'success': False, 'message': 'API key is not configured'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from gaf_ai.qa_llm_client import OpenAIClient

        client = OpenAIClient(
            api_key=api_key,
            provider=obj.provider,
            base_url=obj.api_base or None,
            model=obj.default_model,
            timeout=15,
        )
        start = time.monotonic()
        try:
            result = client.chat(
                messages=[{'role': 'user', 'content': 'Hello, this is a connection test. Reply with "OK" only.'}],
                max_tokens=10,
                temperature=0,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            return Response({
                'success': True,
                'latency_ms': latency_ms,
                'model': result.get('model', obj.default_model),
                'message': 'Connection successful',
            })
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Response({
                'success': False,
                'latency_ms': latency_ms,
                'model': obj.default_model,
                'message': str(exc),
            }, status=status.HTTP_502_BAD_GATEWAY)

    def _build_audit_details(self, action, instance, *, old_instance=None) -> dict:
        """Build audit details with api_key redacted.

        ``model_to_dict`` returns editable fields only (excludes id/auto
        timestamps). ``api_key`` is in ``SENSITIVE_FIELD_NAMES`` so
        ``build_diff_details`` redacts it to ``"<redacted>"`` automatically;
        the ``sensitive_extra`` is defense-in-depth.
        """
        before = model_to_dict(old_instance) if old_instance else None
        after = model_to_dict(instance) if instance else None
        return build_diff_details(before, after, sensitive_extra={"api_key"})


class FeatureFlagViewSet(AuditMixin, viewsets.ModelViewSet):
    """功能开关 API，标准 CRUD，仅管理员可操作（R37-P3 Stage 7: 从 tasks 迁入）。

    URL: /api/v2/settings/feature-flags/ (migrated from /api/v2/tasks/feature-flags/)
    """

    queryset = FeatureFlag.objects.all()
    serializer_class = FeatureFlagSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "manage"
    filterset_fields = ["enabled"]
    search_fields = ["name", "description"]
    audit_resource_type = AuditResourceType.FEATURE_FLAG

    def _build_audit_details(self, action, instance, *, old_instance=None) -> dict:
        """Build audit details for feature flag changes."""
        before = model_to_dict(old_instance) if old_instance else None
        after = model_to_dict(instance) if instance else None
        return build_diff_details(before, after)


class AppSettingsViewSet(AuditMixin, viewsets.ModelViewSet):
    """应用全局设置 API，仅管理员可操作（R37-P3 Stage 7: 从 tasks 迁入）。

    URL: /api/v2/settings/app-settings/ (migrated from /api/v2/tasks/app-settings/)
    """

    queryset = AppSettings.objects.all()
    serializer_class = AppSettingsSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = "manage"
    filterset_fields = ["category"]
    search_fields = ["setting_key", "description"]
    audit_resource_type = AuditResourceType.APP_SETTINGS

    def perform_update(self, serializer):
        """更新设置时自动记录更新者，并写审计日志 (AuditMixin).

        We inline ``AuditMixin.perform_update``'s logic because we need to
        pass ``updated_by`` to ``serializer.save()`` — AuditMixin calls
        ``super().perform_update(serializer)`` which calls ``save()`` with
        no kwargs. Inlining avoids the wrapping indirection.
        """
        old_instance = None
        if self.audit_log_update:
            try:
                old_instance = self.get_object()
            except Exception:
                logger.warning("audit_log_update: get_object() failed", exc_info=True)
                old_instance = None
        serializer.save(updated_by=self.request.user)
        if self.audit_log_update:
            self._log_audit(
                AuditAction.UPDATE,
                serializer.instance,
                old_instance=old_instance,
            )

    def _build_audit_details(self, action, instance, *, old_instance=None) -> dict:
        """Build audit details for app settings changes.

        ``setting_value`` is a JSON field; ``filter_sensitive_fields``
        (called inside ``build_diff_details``) will redact any top-level
        keys matching ``SENSITIVE_FIELD_NAMES`` (password/token/api_key/...).
        """
        before = model_to_dict(old_instance) if old_instance else None
        after = model_to_dict(instance) if instance else None
        return build_diff_details(before, after)


@extend_schema(
    tags=['settings'],
    summary='Unattended strategy singleton upsert',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def unattended_strategy_view(request):
    """
    无人值守策略配置 Upsert API。

    GET: 获取当前策略配置（返回第一条或空默认值）
    POST: 创建或更新策略配置（Upsert 模式）

    M6: removed PUT/DELETE from allowed methods — this is a singleton upsert
    endpoint (one row per deployment); POST handles both create and update.
    """
    # @api_view allowed: singleton upsert (one row per deployment), not standard collection CRUD
    if request.method == 'GET':
        strategy = UnattendedStrategy.objects.first()
        if strategy:
            serializer = UnattendedStrategySerializer(strategy)
            return Response(serializer.data)
        return Response({
            'recovery': {
                'stepLevel': {'maxRetries': 3, 'retryIntervalSeconds': 5, 'exponentialBackoff': False},
                'taskLevel': {'consecutiveFailureThreshold': 3, 'failureAction': 'skip'},
                'appLevel': {'freezeDetection': True, 'freezeTimeoutSeconds': 120, 'freezeAction': 'restart_app'},
                'deviceLevel': {'crashDetection': True, 'crashAction': 'restart_emulator', 'backupDeviceId': None, 'maxRestartCount': 2},
                'systemLevel': {'agentTimeoutSeconds': 300, 'timeoutActions': ['notify', 'mark_offline', 'reassign']},
            },
            'nightMode': {
                'isEnabled': False, 'timeRange': {'start': '00:00', 'end': '06:00'},
                'screenshotIntervalMultiplier': 2, 'operationIntervalMultiplier': 2,
                'cpuThrottle': True, 'autoPauseNonCritical': False,
            },
            'frequencyLimit': {
                'maxPerAccountPerDay': 10, 'maxGlobalPerDay': 100,
                'minTaskIntervalSeconds': 30, 'mode': 'fixed',
            },
            'notificationPolicy': {
                'enabledEvents': ['task_failed', 'device_offline', 'account_blocked', 'game_updated', 'auto_stop_triggered', 'recovery_triggered'],
            },
            'cooldown': {
                'emulatorRestartSeconds': 120, 'gameRestartSeconds': 60,
                'consecutiveLoginSeconds': 10, 'recoveryPauseSeconds': 180,
            },
        })

    elif request.method == 'POST':
        serializer = UnattendedStrategySerializer(data=request.data)
        if serializer.is_valid():
            # Detect create vs update for audit action (singleton upsert).
            existing = UnattendedStrategy.objects.first()
            audit_action = AuditAction.UPDATE if existing else AuditAction.CREATE
            strategy = serializer.save()
            # Audit log (non-blocking). resource_type is the dedicated
            # UNATTENDED_STRATEGY constant (not APP_SETTINGS) so audit
            # queries can distinguish strategy changes from key/value
            # AppSettings changes.
            from accounts.audit import log_audit
            log_audit(
                user=request.user,
                action=audit_action,
                resource_type=AuditResourceType.UNATTENDED_STRATEGY,
                resource_id=str(strategy.pk),
                details={
                    'endpoint': request.path,
                    'method': request.method,
                    'upsert': True,
                },
                ip_address=get_client_ip(request),
            )
            return Response(
                UnattendedStrategySerializer(strategy).data,
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    tags=['settings'],
    summary='Agent debug mode singleton upsert',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission("manage")
def agent_debug_view(request):
    """Agent debug mode configuration API (singleton upsert).

    GET: Get current debug mode config (returns defaults if not set)
    POST: Create or update debug mode config

    Stored in AppSettings(setting_key='agent_debug') as JSON:
      {"enabled": bool, "dir": str}

    When enabled, pipeline execution sends debug_mode=True to the agent via
    WS pipeline.execute message, and the agent saves annotated debug
    screenshots to debug/{timestamp}_{pipeline_name}/.
    """
    # @api_view allowed: singleton upsert (one row per deployment), not standard collection CRUD
    defaults = {'enabled': False, 'dir': 'debug'}

    if request.method == 'GET':
        obj = AppSettings.objects.filter(setting_key='agent_debug').first()
        if obj:
            return Response(obj.setting_value)
        return Response(defaults)

    # POST: upsert
    data = request.data
    enabled = bool(data.get('enabled', False))
    debug_dir = str(data.get('dir', 'debug') or 'debug')
    value = {'enabled': enabled, 'dir': debug_dir}

    obj, created = AppSettings.objects.update_or_create(
        setting_key='agent_debug',
        defaults={
            'setting_value': value,
            'category': 'agent',
            'description': 'Agent debug mode: save annotated screenshots during pipeline execution',
            'updated_by': request.user,
        },
    )
    return Response(value, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@extend_schema(
    tags=['settings'],
    summary='Window background wait singleton upsert',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission("manage")
def wait_when_background_view(request):
    """Window background wait configuration API (singleton upsert).

    GET: Get current config (returns defaults if not set)
    POST: Create or update config

    Stored in AppSettings(setting_key='wait_when_background') as JSON:
      {"enabled": bool, "timeout_seconds": int, "check_interval_ms": int}

    When enabled, pipeline execution sends the config to the agent via
    WS pipeline.execute message. The agent monitors the target window's
    foreground state during task execution:
    - Window loses foreground → pause pipeline + notify frontend
    - Window regains foreground → resume pipeline + notify frontend
    - Timeout exceeded → cancel pipeline + notify failure
    """
    # @api_view allowed: singleton upsert (one row per deployment), not standard collection CRUD
    defaults = {
        'enabled': False,
        'timeout_seconds': 1800,
        'check_interval_ms': 500,
    }

    if request.method == 'GET':
        obj = AppSettings.objects.filter(setting_key='wait_when_background').first()
        if obj:
            return Response(obj.setting_value)
        return Response(defaults)

    # POST: upsert
    data = request.data
    value = {
        'enabled': bool(data.get('enabled', False)),
        'timeout_seconds': int(data.get('timeout_seconds', 1800)),
        'check_interval_ms': int(data.get('check_interval_ms', 500)),
    }

    obj, created = AppSettings.objects.update_or_create(
        setting_key='wait_when_background',
        defaults={
            'setting_value': value,
            'category': 'agent',
            'description': 'Window background wait: pause pipeline when target window loses foreground',
            'updated_by': request.user,
        },
    )
    return Response(value, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@extend_schema(
    tags=['settings'],
    summary='Config generator: schema/validate/export/import',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def config_generator_view(request):
    """Config Generator API: form schema generation, validation, import/export

    GET /schema/<task_type>/  — Get form schema for a task type
    POST /validate/          — Validate values against schema
    POST /export/            — Export values as structured config
    POST /import/            — Import config and fill defaults
    GET /task-types/         — List available task type templates
    """
    # @api_view allowed: multi-action tool wrapping agent ConfigGenerator (schema/validate/export/import), not model CRUD
    ConfigGenerator = _load_agent_module('core/config_generator.py', 'ConfigGenerator')  # noqa: N806

    gen = ConfigGenerator()
    action = request.data.get('action', request.GET.get('action', ''))

    if action == 'schema' or (request.method == 'GET' and not action):
        task_type = request.data.get('task_type', request.GET.get('task_type', 'general'))
        schema = gen.generate_form_schema(task_type)
        fields = gen.schema_to_fields(schema)
        return Response({
            'success': True,
            'schema': schema,
            'fields': fields,
        })

    elif action == 'validate':
        values = request.data.get('values', {})
        task_type = request.data.get('task_type', 'general')
        schema = gen.generate_form_schema(task_type)
        is_valid, errors = gen.validate_values(values, schema)
        return Response({
            'success': is_valid,
            'errors': errors,
        })

    elif action == 'export':
        values = request.data.get('values', {})
        task_type = request.data.get('task_type', 'general')
        config = gen.export_config(values, task_type)
        return Response({
            'success': True,
            'config': config,
        })

    elif action == 'import':
        config = request.data.get('config', {})
        values = gen.import_config(config)
        return Response({
            'success': True,
            'values': values,
            'task_type': config.get('__task_type__', 'general'),
        })

    elif action == 'task-types' or (request.method == 'GET' and request.GET.get('action') == 'task-types'):
        types = ['pipeline', 'scheduler', 'device_config', 'ocr_task', 'general']
        schemas = {}
        for t in types:
            try:
                schemas[t] = {
                    'field_count': len(gen.generate_form_schema(t).get('fields', [])),
                }
            except Exception:
                logger.warning("task_type_schemas: generate_form_schema failed for %s", t, exc_info=True)
                schemas[t] = {'error': 'Failed to generate'}
        return Response({
            'success': True,
            'task_types': schemas,
        })

    else:
        return Response(
            {'success': False, 'message': f'Unknown action: {action}'},
            status=status.HTTP_400_BAD_REQUEST,
        )


@extend_schema(
    tags=['settings'],
    summary='Config migration: version detect and migrate',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def config_migration_view(request):
    """Config Migration API: version detection and incremental migration

    GET /                  — Get migration system info (latest version, available versions)
    POST / action=detect   — Detect config version (explicit __config_version__ + heuristic)
    POST / action=migrate  — Migrate config from detected/explicit version to target version

    Reuses worker/src/core/config_migrator.py (Alas-style chained migration with backup/rollback).
    Stateless: each call creates a fresh ConfigMigrator instance; migration_log is returned
    in the response so the frontend can display the audit trail.
    """
    # @api_view allowed: multi-action tool wrapping agent ConfigMigrator (detect/migrate), not model CRUD
    create_default_migrator = _load_agent_module('core/config_migrator.py', 'create_default_migrator')

    migrator = create_default_migrator()

    if request.method == 'GET':
        # Build version descriptions from registered migration docstrings
        version_descriptions = {}
        for ver in sorted(migrator._migrations.keys()):
            fn = migrator._migrations[ver]
            doc = (fn.__doc__ or '').strip().split('\n')[0]
            version_descriptions[str(ver)] = doc or f'Migrate to version {ver}'
        return Response({
            'success': True,
            'latest_version': migrator.get_latest_version(),
            'available_versions': sorted(migrator._migrations.keys()),
            'version_descriptions': version_descriptions,
        })

    # POST: detect or migrate
    action = request.data.get('action', '')
    config = request.data.get('config', None)

    if action == 'detect':
        if not isinstance(config, dict):
            return Response(
                {'success': False, 'message': 'config (dict) is required for detect action'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # detect_version uses explicit __config_version__ first, then heuristic
        explicit = config.get('__config_version__')
        detected = migrator.detect_version(config)
        method = 'explicit' if explicit is not None else ('heuristic' if detected > 1 else 'default')
        return Response({
            'success': True,
            'detected_version': detected,
            'method': method,
            'latest_version': migrator.get_latest_version(),
            'needs_migration': detected < migrator.get_latest_version(),
        })

    elif action == 'migrate':
        if not isinstance(config, dict):
            return Response(
                {'success': False, 'message': 'config (dict) is required for migrate action'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from_ver = request.data.get('from_ver')
        to_ver = request.data.get('to_ver')

        # Auto-detect from_ver if not provided
        if from_ver is None:
            from_ver = migrator.detect_version(config)
        try:
            from_ver_int = int(from_ver)
        except (TypeError, ValueError):
            return Response(
                {'success': False, 'message': f'from_ver must be an integer, got {from_ver!r}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Default to_ver to latest
        if to_ver is None:
            to_ver_int = migrator.get_latest_version()
        else:
            try:
                to_ver_int = int(to_ver)
            except (TypeError, ValueError):
                return Response(
                    {'success': False, 'message': f'to_ver must be an integer, got {to_ver!r}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if from_ver_int == to_ver_int:
            return Response({
                'success': True,
                'migrated_config': config,
                'from_version': from_ver_int,
                'to_version': to_ver_int,
                'migration_log': [],
                'message': 'Config already at target version, no migration needed',
            })

        if from_ver_int > to_ver_int:
            return Response(
                {
                    'success': False,
                    'message': f'Downgrade not supported (from_ver={from_ver_int} > to_ver={to_ver_int}). '
                               f'Migration is forward-only.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            migrated = migrator.migrate(config, from_ver_int, to_ver_int)
            return Response({
                'success': True,
                'migrated_config': migrated,
                'from_version': from_ver_int,
                'to_version': to_ver_int,
                'migration_log': migrator.migration_log,
            })
        except (ValueError, RuntimeError, TypeError) as exc:
            return Response(
                {
                    'success': False,
                    'message': f'Migration failed: {exc}',
                    'migration_log': migrator.migration_log,
                    'from_version': from_ver_int,
                    'to_version': to_ver_int,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    else:
        return Response(
            {'success': False, 'message': f'Unknown action: {action!r}. Use "detect" or "migrate".'},
            status=status.HTTP_400_BAD_REQUEST,
        )


@extend_schema(
    tags=['settings'],
    summary='Generate diagnostic ZIP package',
    request=OpenApiTypes.NONE,
    responses={
        (200, 'application/zip'): OpenApiTypes.BINARY,
        500: OpenApiTypes.OBJECT,
    },
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_diagnostic(request):
    """
    生成诊断包（ZIP 文件）。

    收集系统信息、数据库状态、已安装应用列表等，打包为 ZIP 返回。
    """
    # @api_view allowed: assembles system info + DB queries into a ZIP artifact, not model CRUD
    # B004 fix: use timezone-aware now() to avoid naive datetime warnings
    # under USE_TZ=True and to keep timestamps consistent across deployments.
    ts = django_now().strftime('%Y%m%d_%H%M%S')
    filename = f'diagnostic_{ts}.zip'
    zip_buffer = io.BytesIO()

    try:
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            info = {
                'generated_at': django_now().isoformat(),
                'django_version': django.VERSION,
                'python_version': sys.version,
                'debug_mode': settings.DEBUG,
                'database_engine': settings.DATABASES['default']['ENGINE'],
                'user': str(request.user) if request.user.is_authenticated else 'anonymous',
            }

            # spec-59-E: raw SQL → ORM (MigrationRecorder.Migration)
            migration_count = MigrationRecorder.Migration.objects.count()
            info['applied_migrations'] = migration_count

            installed_apps = list(settings.INSTALLED_APPS)
            info['installed_apps'] = installed_apps
            info['installed_apps_count'] = len(installed_apps)

            middleware = list(settings.MIDDLEWARE)
            info['middleware'] = middleware

            zf.writestr('system_info.json', json.dumps(info, indent=2, ensure_ascii=False, default=str))

            try:
                # spec-59-E: raw SQL → ORM (MigrationRecorder.Migration)
                migrations_rows = list(
                    MigrationRecorder.Migration.objects.order_by('app', 'name')
                    .values('name', 'app', 'applied')
                )
                zf.writestr('migrations.json', json.dumps(migrations_rows, indent=2, ensure_ascii=False, default=str))
            except Exception:
                logger.warning("generate_diagnostic: migrations query failed", exc_info=True)
                zf.writestr('migrations.json', '{"error": "Could not query migrations"}')

        zip_buffer.seek(0)
        from django.http import HttpResponse
        response = HttpResponse(zip_buffer.read(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        # Audit log (non-blocking, success only): diagnostic ZIP contains
        # sensitive system info (Django version, DB engine, installed apps,
        # migration list) — record who generated it and when for traceability.
        from accounts.audit import log_audit
        log_audit(
            user=request.user,
            action=AuditAction.EXECUTE,
            resource_type=AuditResourceType.APP_SETTINGS,
            resource_id='',
            details={
                'endpoint': request.path,
                'method': request.method,
                'filename': filename,
            },
            ip_address=get_client_ip(request),
        )
        return response
    except Exception as e:
        logger.error("generate_diagnostic: failed: %s", e, exc_info=True)
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(
    tags=['settings'],
    summary='Data cleanup with retention policy',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission("manage")
def cleanup_view(request):
    """Run data cleanup with the given retention policy.

    POST /api/v2/settings/cleanup/
    Body: {
        "execution_retention_days": int,   # delete TaskExecution older than N days
        "screenshot_retention_gb": float,  # delete oldest screenshots when total size exceeds N GB
        "log_retention_days": int          # delete gaf_core.LogEntry older than N days
    }

    Returns: {
        "deleted_executions": int,
        "deleted_steps": int,
        "deleted_logs": int,
        "deleted_screenshots": int,
        "freed_screenshot_bytes": int,
        "skipped": [...]
    }
    """
    # @api_view allowed: bulk delete operation with retention policy, not model CRUD
    import os
    from datetime import timedelta

    from tasks.models import ExecutionStep, TaskExecution

    data = request.data
    execution_days = int(data.get('execution_retention_days', 30))
    log_days = int(data.get('log_retention_days', 30))
    screenshot_gb = float(data.get('screenshot_retention_gb', 10.0))
    skipped: list[str] = []

    cutoff_exec = django_now() - timedelta(days=execution_days)
    # Delete ExecutionStep rows belonging to old TaskExecution first (FK CASCADE
    # would handle this, but explicit delete makes the count accurate).
    # spec-58-A (TD-296): wrap both deletes in a transaction so a partial
    # failure cannot leave orphaned ExecutionStep rows pointing at deleted
    # TaskExecution rows.
    with transaction.atomic():
        old_exec_ids = list(
            TaskExecution.objects.filter(created_at__lt=cutoff_exec).values_list('id', flat=True)
        )
        deleted_steps, _ = ExecutionStep.objects.filter(task_result_id__in=old_exec_ids).delete()
        deleted_execs, _ = TaskExecution.objects.filter(id__in=old_exec_ids).delete()

    # LogEntry 表已废弃 (spec §2.2) — 不再写入/删除, 保留只读查询.
    # F12 (2026-07-31): 移除 LogEntry 清理路径, 表为真只读.
    deleted_logs = 0

    # Screenshot retention: walk MEDIA_ROOT/screenshots/ and delete oldest
    # files (by mtime) until total size <= screenshot_gb threshold. Avoids
    # disk bloat from accumulated debug/step screenshots.
    deleted_screenshots = 0
    freed_bytes = 0
    try:
        screenshot_dir = Path(settings.MEDIA_ROOT) / 'screenshots'
        if screenshot_dir.is_dir():
            files: list[tuple[float, int, Path]] = []
            for root, _dirs, fnames in os.walk(screenshot_dir):
                for fname in fnames:
                    fpath = Path(root) / fname
                    try:
                        stat = fpath.stat()
                        files.append((stat.st_mtime, stat.st_size, fpath))
                    except OSError:
                        continue
            # Sort by mtime ascending (oldest first)
            files.sort(key=lambda x: x[0])
            total_size = sum(s for _, s, _ in files)
            threshold_bytes = int(screenshot_gb * 1024 ** 3)
            # Delete oldest files until total_size <= threshold
            for _mtime, size, fpath in files:
                if total_size <= threshold_bytes:
                    break
                try:
                    fpath.unlink()
                    total_size -= size
                    deleted_screenshots += 1
                    freed_bytes += size
                except OSError:
                    continue
    except Exception:
        logger.warning("cleanup_with_retention: screenshots cleanup failed", exc_info=True)
        skipped.append('screenshots (cleanup failed)')

    # Audit log (non-blocking): bulk delete is a sensitive operation that
    # affects task execution history and system logs — record retention
    # params + deleted counts so auditors can trace data loss events.
    from accounts.audit import log_audit
    log_audit(
        user=request.user,
        action=AuditAction.EXECUTE,
        resource_type=AuditResourceType.APP_SETTINGS,
        resource_id='',
        details={
            'endpoint': request.path,
            'method': request.method,
            'execution_retention_days': execution_days,
            'log_retention_days': log_days,
            'screenshot_retention_gb': screenshot_gb,
            'deleted_executions': deleted_execs,
            'deleted_steps': deleted_steps,
            'deleted_logs': deleted_logs,
            'deleted_screenshots': deleted_screenshots,
            'freed_screenshot_bytes': freed_bytes,
            'skipped': skipped,
        },
        ip_address=get_client_ip(request),
    )

    return Response({
        'deleted_executions': deleted_execs,
        'deleted_steps': deleted_steps,
        'deleted_logs': deleted_logs,
        'deleted_screenshots': deleted_screenshots,
        'freed_screenshot_bytes': freed_bytes,
        'skipped': skipped,
    })
