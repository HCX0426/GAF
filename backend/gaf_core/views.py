"""Views for the core app.

LogEntryViewSet — read-only API for querying persisted log records.
Supports filtering by level, source, timestamp range, and associated
entity IDs (task_id, agent_id, device_id).

UnifiedLogTimelineView — UNION query across 6 specialized log models
(LogEntry + AuditLog + RecoveryLog + MessageFrameLog + LLMUsageLog +
CrashReport) for the LogCenterPage "统一时间线" Tab.

FrontendErrorReportView — POST endpoint receiving browser-side crashes
(window.onerror / unhandledrejection / React ErrorBoundary) so AI
debugging can correlate frontend failures with backend/agent errors.

FileLogQueryView — GET /api/v2/logs/files/ 统一文件日志检索 (spec
2026-08-29-logging-system-consolidation P2-1): 服务终端 + 原生日志文件
tail / 报错过滤, 前端日志中心 + 服务管理 + AI 调试共用.
"""
import logging

import django_filters
from django.conf import settings
from django.db.models import Case, CharField, F, Value, When
from django.db.models.functions import Concat
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import RoleBasedPermission
from gaf_core import log_files
from gaf_core.frontend_logger import FrontendConsoleLogger, _sanitize_page_slug
from gaf_core.models import LogEntry
from gaf_core.serializers import LogEntrySerializer

logger = logging.getLogger(__name__)


class HealthzView(APIView):
    """GET /api/v2/system/healthz/ — 应用级健康探针 (AllowAny).

    供 gaf_daemon 健康感知编排器轮询 (spec 2026-08-29 P1):
    - db:    SQLite/DB 只读连接检查
    - redis: cache 写读往返
    仅返回 pass/fail 状态码, 不暴露凭据/版本/路径等敏感信息.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="Liveness/readiness probe for service orchestration (DB + Redis).",
    )
    def get(self, request):
        from django.db import connections

        health = {"status": "pass", "checks": {}}

        # 数据库检查 (只读: 执行 SELECT 1)
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            health["checks"]["db"] = "pass"
        except Exception as exc:
            logger.warning("healthz db check failed: %s", exc, exc_info=True)
            health["checks"]["db"] = "fail"
            health["status"] = "fail"

        # Redis 检查 (cache set/get 往返)
        try:
            from django.core.cache import cache

            cache.set("healthz_probe", "ok", 5)
            if cache.get("healthz_probe") == "ok":
                health["checks"]["redis"] = "pass"
            else:
                health["checks"]["redis"] = "fail"
                health["status"] = "fail"
        except Exception as exc:
            logger.warning("healthz redis check failed: %s", exc, exc_info=True)
            health["checks"]["redis"] = "fail"
            health["status"] = "fail"

        status_code = 200 if health["status"] == "pass" else 503
        return Response(data=health, status=status_code)


class PerfAPIView(APIView):
    """GET /api/v2/system/perf — 返回 PerformanceMonitor 的内存聚合.

    Only available in development mode (``GAF_CELERY_MODE=eager``).
    In production mode, returns an empty response with
    ``{"mode": "production", "message": "perf monitoring disabled"}``.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="Return PerformanceMonitor aggregated statistics.",
    )
    def get(self, request):
        from gaf_core.perf_monitor import PerformanceMonitor

        mon = PerformanceMonitor.get_instance()
        aggregates = mon.get_aggregates()
        return Response({
            "mode": mon.mode,
            "uptime_seconds": round(mon.get_uptime_seconds(), 2),
            "aggregates": aggregates,
        })


def get_debug_root() -> str:
    """Return the debug root directory from Django settings.

    Thin wrapper around ``getattr(settings, "DEBUG_DIR", "./debug")`` so
    tests can patch ``gaf_core.views.get_debug_root`` to a tempdir without
    touching global settings. Used by ``FrontendErrorReportView`` to
    construct a per-request ``FrontendConsoleLogger``.
    """
    return getattr(settings, "DEBUG_DIR", "./debug")

# P0-10 (AI 可调试性, 2026-07-27): dedicated logger for frontend crash reports.
# AI debugging greps this logger name to distinguish "前端渲染崩溃" from
# "后端 500" and "agent 执行失败" — all three previously mixed in backend logs.
frontend_error_logger = logging.getLogger('gaf_core.frontend_error')


class LogEntryFilter(django_filters.FilterSet):
    """Filter LogEntry by level, source, timestamp range, and trace_id.

    The ``start`` and ``end`` filters map to ``timestamp__gte`` and
    ``timestamp__lte`` respectively, enabling time-range queries.
    ``trace_id`` enables request-correlation lookups (LogEntry ↔ trace_id).
    """

    start = django_filters.DateTimeFilter(field_name='timestamp', lookup_expr='gte')
    end = django_filters.DateTimeFilter(field_name='timestamp', lookup_expr='lte')
    trace_id = django_filters.CharFilter(field_name='trace_id', lookup_expr='exact')

    class Meta:
        model = LogEntry
        fields = ['level', 'source', 'task_id', 'agent_id', 'device_id', 'trace_id']


class LogEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only LogEntry viewset — list and retrieve.

    Default ordering is ``-timestamp`` (newest first). Supports filtering
    via ``LogEntryFilter`` and full-text search on ``message`` /
    ``traceback`` / ``source`` via the ``search`` query parameter.
    """

    queryset = LogEntry.objects.all().order_by('-timestamp')
    serializer_class = LogEntrySerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    filterset_class = LogEntryFilter
    search_fields = ['message', 'traceback', 'source']
    ordering_fields = ['timestamp', 'level', 'source']
    ordering = ['-timestamp']


# === Unified timeline UNION fields ===
# Field names used in the normalized .values() list across all 6 model
# querysets. Each per-model queryset annotates its own columns onto these
# names so QuerySet.union() can stitch them together.
UNION_FIELDS = ('ref_type', 'ref_id', 'occurred_at', 'log_level',
                'log_source', 'log_message')

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


def _build_logentry_qs(start, end, level, source):
    """LogEntry → normalized timeline queryset."""
    qs = LogEntry.objects.annotate(
        ref_type=Value('LogEntry', output_field=CharField()),
        ref_id=F('id'),
        occurred_at=F('timestamp'),
        log_level=F('level'),
        log_source=F('source'),
        log_message=F('message'),
    ).values(*UNION_FIELDS).order_by()
    if start:
        qs = qs.filter(timestamp__gte=start)
    if end:
        qs = qs.filter(timestamp__lte=end)
    if level:
        qs = qs.filter(level=level)
    # log_source = source (raw field) — case-insensitive contains match.
    if source:
        qs = qs.filter(source__icontains=source)
    return qs


def _build_auditlog_qs(start, end, level, source):
    """AuditLog → normalized timeline queryset.

    AuditLog has no native 'level' — default to INFO (audit events are
    operational records, not error/fatal signals).
    """
    from accounts.models import AuditLog
    qs = AuditLog.objects.annotate(
        ref_type=Value('AuditLog', output_field=CharField()),
        ref_id=F('id'),
        occurred_at=F('created_at'),
        log_level=Value('INFO', output_field=CharField()),
        log_source=Concat(Value('audit.'), F('action'), output_field=CharField()),
        log_message=Concat(
            F('action'), Value(' '),
            F('resource_type'), Value('/'),
            F('resource_id'),
            output_field=CharField(),
        ),
    ).values(*UNION_FIELDS).order_by()
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)
    # AuditLog is always INFO — a non-INFO level filter excludes it.
    if level and level != 'INFO':
        qs = qs.none()
    # log_source = 'audit.' + action — match against action (without prefix)
    # so user typing 'login' matches 'audit.login'.
    if source:
        qs = qs.filter(action__icontains=source)
    return qs


def _build_recoverylog_qs(start, end, level, source):
    """RecoveryLog → normalized timeline queryset.

    Map success=True → INFO, success=False → WARNING (recovery actions
    that failed warrant attention but are not full errors).
    """
    from scheduler.models import RecoveryLog
    qs = RecoveryLog.objects.annotate(
        ref_type=Value('RecoveryLog', output_field=CharField()),
        ref_id=F('id'),
        occurred_at=F('created_at'),
        log_level=Case(
            When(success=True, then=Value('INFO')),
            default=Value('WARNING'),
            output_field=CharField(),
        ),
        log_source=Concat(Value('recovery.'), F('recovery_level'), output_field=CharField()),
        log_message=Concat(
            F('trigger_event'), Value(' → '),
            F('action_taken'),
            output_field=CharField(),
        ),
    ).values(*UNION_FIELDS).order_by()
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)
    if level:
        # Only INFO/WARNING possible — exclude otherwise.
        if level not in ('INFO', 'WARNING'):
            qs = qs.none()
        elif level == 'INFO':
            qs = qs.filter(success=True)
        elif level == 'WARNING':
            qs = qs.filter(success=False)
    # log_source = 'recovery.' + recovery_level
    if source:
        qs = qs.filter(recovery_level__icontains=source)
    return qs


def _build_messageframelog_qs(start, end, level, source):
    """MessageFrameLog → normalized timeline queryset (DEBUG level)."""
    from protocol.models import MessageFrameLog
    qs = MessageFrameLog.objects.annotate(
        ref_type=Value('MessageFrameLog', output_field=CharField()),
        ref_id=F('id'),
        occurred_at=F('created_at'),
        log_level=Value('DEBUG', output_field=CharField()),
        log_source=Concat(Value('protocol.'), F('message_type'), output_field=CharField()),
        log_message=Concat(
            F('direction'), Value(' '),
            F('message_type'),
            output_field=CharField(),
        ),
    ).values(*UNION_FIELDS).order_by()
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)
    if level and level != 'DEBUG':
        qs = qs.none()
    # log_source = 'protocol.' + message_type
    if source:
        qs = qs.filter(message_type__icontains=source)
    return qs


def _build_llmusagelog_qs(start, end, level, source):
    """LLMUsageLog → normalized timeline queryset (INFO level)."""
    from gaf_ai.models import LLMUsageLog
    qs = LLMUsageLog.objects.annotate(
        ref_type=Value('LLMUsageLog', output_field=CharField()),
        ref_id=F('id'),
        occurred_at=F('created_at'),
        log_level=Value('INFO', output_field=CharField()),
        log_source=Concat(Value('llm.'), F('model_name'), output_field=CharField()),
        log_message=Concat(
            Value('LLM call: '),
            F('call_type'), Value(' '),
            F('input_tokens'), Value('/'), F('output_tokens'), Value(' tokens'),
            output_field=CharField(),
        ),
    ).values(*UNION_FIELDS).order_by()
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)
    if level and level != 'INFO':
        qs = qs.none()
    # log_source = 'llm.' + model_name
    if source:
        qs = qs.filter(model_name__icontains=source)
    return qs


def _build_crashreport_qs(start, end, level, source):
    """CrashReport → normalized timeline queryset (ERROR level)."""
    from debug.models import CrashReport
    qs = CrashReport.objects.annotate(
        ref_type=Value('CrashReport', output_field=CharField()),
        ref_id=F('id'),
        occurred_at=F('created_at'),
        log_level=Value('ERROR', output_field=CharField()),
        log_source=Concat(Value('crash.'), F('component'), output_field=CharField()),
        log_message=Concat(
            F('error_type'), Value(': '),
            F('stack_trace'),
            output_field=CharField(),
        ),
    ).values(*UNION_FIELDS).order_by()
    if start:
        qs = qs.filter(created_at__gte=start)
    if end:
        qs = qs.filter(created_at__lte=end)
    if level and level != 'ERROR':
        qs = qs.none()
    # log_source = 'crash.' + component
    if source:
        qs = qs.filter(component__icontains=source)
    return qs


class UnifiedLogTimelineView(APIView):
    """UNION timeline across 6 specialized log models.

    GET /api/v2/logs/timeline/?start=&end=&level=&source=&page=&page_size=

    Returns a unified, timestamp-desc-sorted view combining:
      - LogEntry (gaf_core.LogEntry) — all levels
      - AuditLog (tasks.AuditLog) — INFO
      - RecoveryLog (scheduler.RecoveryLog) — INFO (success) / WARNING (fail)
      - MessageFrameLog (protocol.MessageFrameLog) — DEBUG
      - LLMUsageLog (qa.LLMUsageLog) — INFO
      - CrashReport (debug.CrashReport) — ERROR

    Each row is normalized to:
      {ref_type, ref_id, occurred_at, log_level, log_source, log_message}

    Pagination is manual because Django Paginator does not support
    QuerySet.union() reliably (count() + slicing need separate handling
    on some backends).
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'

    @extend_schema(
        request=None,
        responses={200: OpenApiTypes.OBJECT},
        description="UNION timeline across 6 specialized log models (LogEntry, AuditLog, RecoveryLog, MessageFrameLog, LLMUsageLog, CrashReport).",
    )
    def get(self, request):
        from django.utils.dateparse import parse_datetime

        start = parse_datetime(request.query_params.get('start', '')) if request.query_params.get('start') else None
        end = parse_datetime(request.query_params.get('end', '')) if request.query_params.get('end') else None
        level = (request.query_params.get('level') or '').upper() or None
        source = request.query_params.get('source') or None
        try:
            page = max(1, int(request.query_params.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = min(MAX_PAGE_SIZE, max(1, int(request.query_params.get('page_size', DEFAULT_PAGE_SIZE))))
        except (TypeError, ValueError):
            page_size = DEFAULT_PAGE_SIZE

        # Build all 6 per-model querysets with filters applied BEFORE union
        # (pushes filters down to each table — more efficient than filtering
        # the union result). QuerySet.filter() after union() is not supported
        # by Django, so all filtering must happen per-model here.
        qs_builders = [
            _build_logentry_qs,
            _build_auditlog_qs,
            _build_recoverylog_qs,
            _build_messageframelog_qs,
            _build_llmusagelog_qs,
            _build_crashreport_qs,
        ]
        querysets = [builder(start, end, level, source) for builder in qs_builders]

        # Filter out empty querysets — union() with a single .none() is fine
        # but skipping them reduces query complexity.
        non_empty = [q for q in querysets if q]
        if not non_empty:
            return Response({
                'count': 0, 'page': page, 'page_size': page_size,
                'results': [],
            })

        unified = non_empty[0]
        for q in non_empty[1:]:
            unified = unified.union(q)

        unified = unified.order_by('-occurred_at')

        # Manual pagination — QuerySet.union() supports slicing but count()
        # may be unreliable on some DBs; we use len(list(unified)) fallback.
        offset = (page - 1) * page_size
        page_items = list(unified[offset:offset + page_size])
        # Total count: try .count() first; fall back to a separate COUNT query.
        try:
            total = unified.count()
        except Exception:
            logger.warning("UnifiedLogTimeline: .count() failed, falling back to len(list)", exc_info=True)
            total = len(list(unified))

        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': page_items,
        })


# === P0-10: Frontend error report endpoint ============================
# Receives browser-side crashes (window.onerror / unhandledrejection /
# React ErrorBoundary) reported by frontend/src/utils/reportFrontendError.ts.
# Writes to dedicated logger ``gaf_core.frontend_error`` so AI debugging
# can grep this logger name to find frontend failures and correlate them
# with backend/agent errors.

# Cap individual fields to prevent log-injection / disk exhaustion.
_MAX_FE_MESSAGE_LEN = 2000
_MAX_FE_STACK_LEN = 4000
_MAX_FE_SOURCE_LEN = 500
_MAX_FE_USER_AGENT_LEN = 500
_MAX_FE_PAGE_URL_LEN = 500
_MAX_FE_SESSION_ID_LEN = 64
_MAX_FE_TRACE_ID_LEN = 64
_MAX_FE_PAGE_SLUG_LEN = 40
_FE_ALLOWED_TRIGGERS = ('window.onerror', 'unhandledrejection', 'error_boundary')


def _truncate(value, max_len):
    """Truncate a string field to ``max_len`` (None-safe)."""
    if not value or not isinstance(value, str):
        return ''
    return value[:max_len]


class FrontendErrorReportView(APIView):
    """POST /api/v2/logs/frontend-errors/

    Receives a frontend crash report and logs it to
    ``gaf_core.frontend_error`` logger. Allows anonymous POST because the
    frontend may crash before/without a valid auth token (e.g. during
    login page render). The frontend dedups (1/min per error signature)
    and the global AnonRateThrottle (60/min/IP) provides additional abuse
    protection.

    Returns HTTP 204 with empty body on success — frontend doesn't act on
    the response, and 204 avoids the UnifiedResponseMiddleware envelope
    (no JSON body to wrap).
    """

    authentication_classes: list = []  # skip JWT auth — allow anonymous
    permission_classes = [AllowAny]
    # Inherit default throttle (AnonRateThrottle 60/min/IP).
    # No throttle_classes override needed.

    @extend_schema(
        request=OpenApiTypes.OBJECT,
        responses={204: None},
        description=(
            "Receive a frontend crash report (window.onerror / "
            "unhandledrejection / React ErrorBoundary). Logs to "
            "'gaf_core.frontend_error' logger. Anonymous POST allowed — "
            "frontend may crash before auth."
        ),
    )
    def post(self, request):
        data = request.data if hasattr(request, 'data') else {}
        if not isinstance(data, dict):
            data = {}

        message = _truncate(data.get('message'), _MAX_FE_MESSAGE_LEN)
        if not message:
            # Malformed payload — drop silently. Frontend shouldn't send
            # empty messages; if it does, we can't attribute the error anyway.
            return HttpResponse(status=204)

        trigger = data.get('trigger') if data.get('trigger') in _FE_ALLOWED_TRIGGERS else 'unknown'
        stack = _truncate(data.get('stack'), _MAX_FE_STACK_LEN)
        source = _truncate(data.get('source'), _MAX_FE_SOURCE_LEN)
        error_type = _truncate(data.get('error_type'), 200)
        page_url = _truncate(data.get('page_url'), _MAX_FE_PAGE_URL_LEN)
        user_agent = _truncate(data.get('user_agent'), _MAX_FE_USER_AGENT_LEN)
        session_id = _truncate(data.get('session_id'), _MAX_FE_SESSION_ID_LEN)
        lineno = data.get('lineno')
        colno = data.get('colno')

        # C3 (spec 2026-07-30): trace_id + page_slug for cross-tier correlation.
        # trace_id is the full UUID propagated from the originating HTTP
        # request (set by TracingMiddleware). Empty string when no request
        # scope (e.g. anonymous crash before trace_id is set) — AI debugging
        # treats empty trace_id as "no pipeline correlation".
        trace_id = _truncate(data.get('trace_id'), _MAX_FE_TRACE_ID_LEN)
        # page_slug is the sanitized frontend page identifier (e.g. "dashboard",
        # "tasks_pipeline"). Sanitize again on backend (defense in depth —
        # client cannot be trusted). _sanitize_page_slug returns "unknown"
        # for empty / unsanitizable input — never an empty string (would
        # create debug/<date>/frontend//HH/).
        page_slug_raw = _truncate(data.get('page_slug'), _MAX_FE_PAGE_SLUG_LEN)
        page_slug_safe = _sanitize_page_slug(page_slug_raw) if page_slug_raw else "unknown"

        # Build a structured single-line log record so file-based log
        # handlers (FileLogHandler) keep it on one line for grep.
        # Format: [trigger] error_type: message | src=lineno:colno | url=page_url
        #         | sess=session_id | ua=user_agent | trace=trace_id | page=page_slug
        #         | stack=...
        loc = ''
        if lineno:
            loc = f"{lineno}:{colno}" if colno else f"{lineno}"

        # Stack on a separate line below — preserves readability while
        # keeping the header line greppable. Use a single concatenated
        # string (ERROR level is always emitted, so lazy %-formatting
        # provides no benefit and complicates test assertions).
        header = (
            f"[{trigger}] {error_type}: {message} "
            f"| src={source}{' ' + loc if loc else ''} "
            f"| url={page_url} "
            f"| sess={session_id} "
            f"| trace={trace_id} "
            f"| page={page_slug_safe} "
            f"| ua={user_agent}"
        )
        if stack:
            frontend_error_logger.error(f"{header}\n{stack}")
        else:
            frontend_error_logger.error(header)

        # spec 2026-08-29-logging-system-consolidation P1-2: 结构化入库
        # CrashReport (日志中心"崩溃报告"tab + resolved 工作流数据源).
        # Best-effort: 失败不回滚 204.
        try:
            from debug.models import CrashReport

            CrashReport.objects.create(
                component=page_slug_safe,
                error_type=error_type or trigger,
                stack_trace=stack or 'N/A',
                system_info={
                    'message': message,
                    'source': source,
                    'url': page_url,
                    'user_agent': user_agent,
                    'session_id': session_id,
                    'trace_id': trace_id,
                    'trigger': trigger,
                    'lineno': lineno,
                    'colno': colno,
                },
            )
        except Exception as exc:
            logger.warning("前端错误入库 CrashReport 失败: %s", exc)

        # C3 (spec 2026-07-30): persist as JSONL under
        # <debug_root>/<YYYYMMDD>/frontend/<page_slug>/<HH>/console.jsonl
        # so AI debugging can browse frontend crashes by page alongside
        # agent/backend logs. Best-effort: failures here must NOT turn the
        # 204 into a 500 (FrontendConsoleLogger.log swallows internally,
        # but get_debug_root() / logger construction could still raise).
        try:
            fe_logger = FrontendConsoleLogger(
                debug_root=get_debug_root(),
                page_slug=page_slug_safe,
                trace_id=trace_id,
            )
            fe_logger.log(
                event="frontend.error",
                payload={
                    "trigger": trigger,
                    "message": message,
                    "stack": stack,
                    "error_type": error_type,
                    "source": source,
                    "lineno": lineno,
                    "colno": colno,
                    "page_url": page_url,
                    "user_agent": user_agent,
                    "session_id": session_id,
                },
                level="error",
            )
        except Exception:
            # Persistence failure is non-fatal — frontend still gets 204.
            # The original frontend crash is the priority; a backend disk
            # error must not mask it. Mirror BackendTaskLogger's swallow
            # contract (which writes to stderr inside log() too).
            logger.warning(
                "FrontendErrorReportView: FrontendConsoleLogger persistence failed "
                "(page_slug=%s, trace_id=%s)",
                page_slug_safe, trace_id,
                exc_info=True,
            )

        # No body returned — 204 is the correct "I processed your submission
        # and have nothing to say back" signal. Frontend code (reportFrontendError.ts)
        # awaits the promise but does not inspect the response.
        return HttpResponse(status=204)


@extend_schema(
    tags=['logs'],
    summary='Unified file log query (service terminal + native logs)',
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter('service', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
        OpenApiParameter('date', type=OpenApiTypes.DATE, location=OpenApiParameter.QUERY),
        OpenApiParameter('lines', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
        OpenApiParameter('filter', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
def file_log_query_view(request):
    """统一文件日志检索 API (spec 2026-08-29-logging-system-consolidation P2-1).

    GET /api/v2/logs/files/?service=backend&date=2026-08-29&lines=300&filter=all|error
    读取文件层日志 (服务终端捕获 debug/system/services/<name>.log + 原生日志),
    AI 调试与前端日志中心共用同一检索层.
    """
    service = request.query_params.get('service', '').strip()
    if not service:
        return Response({'detail': 'service 参数必填'}, status=status.HTTP_400_BAD_REQUEST)
    if service not in log_files.SERVICE_ORDER:
        return Response(
            {'detail': f'service 必须是 {log_files.SERVICE_ORDER}'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        max_lines = min(int(request.query_params.get('lines', 300)), 2000)
    except ValueError:
        max_lines = 300
    filter_errors = request.query_params.get('filter', 'all').lower() == 'error'
    date = request.query_params.get('date') or None

    files = log_files.resolve_service_log_files(service, date=date)
    if filter_errors:
        lines = log_files.collect_error_lines(files, max_lines)
        error_count = len(lines)
    else:
        lines = log_files.read_log_tail(files, max_lines)
        error_count = None

    return Response({
        'service': service,
        'date': date,
        'path': str(files[0]) if files else None,
        'files': [str(f) for f in files],
        'filter': 'error' if filter_errors else 'all',
        'lines': lines,
        'error_count': error_count,
    })
