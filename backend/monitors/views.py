import json
import logging
import os
import time
from pathlib import Path

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Avg, Count, Max, Min
from django.utils import timezone  # noqa: I001
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from gaf_core.audit_constants import AuditAction, AuditResourceType
from gaf_core.log_files import (
    collect_error_lines,
)
from gaf_core.log_files import (
    read_log_tail as _read_log_tail,
)
from gaf_core.log_files import (
    resolve_service_log_files as _resolve_service_log_files,
)
from gaf_core.mixins import AuditMixin, audit_action, build_diff_details
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from workers.models import Worker

from accounts.permissions import RoleBasedPermission
from monitors.models import MonitorEvent, MonitorRule, SLAMetric
from monitors.serializers import (
    MonitorEventSerializer,
    MonitorRuleSerializer,
    SLAMetricReportSerializer,
    SLAMetricSerializer,
)

logger = logging.getLogger(__name__)


class MonitorRuleViewSet(AuditMixin, viewsets.ModelViewSet):
    """监控规则管理视图集。"""

    queryset = MonitorRule.objects.all().select_related('resource_pack')
    serializer_class = MonitorRuleSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'execute'
    filterset_fields = ['resource_pack', 'is_enabled', 'rule_kind']
    search_fields = ['name']
    audit_resource_type = AuditResourceType.MONITOR_RULE

    def get_permissions(self):
        """读操作降低权限要求。"""
        if self.action in ('list', 'retrieve'):
            self.required_permission = 'view'
        else:
            self.required_permission = 'execute'
        return super().get_permissions()

    def _build_audit_details(self, action, instance, *, old_instance=None):
        """Build before/after diff for audit log.

        ``rule_definition`` is a JSON blob that may embed screenshot
        templates / OCR config; treat as sensitive to avoid leaking
        operational config to anyone reading AuditLog rows later.
        """
        snapshot_keys = ("name", "is_enabled")
        sensitive = {"rule_definition", "config", "secret", "token"}
        if action == AuditAction.CREATE:
            return build_diff_details(
                before=None,
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=sensitive,
            )
        if action == AuditAction.UPDATE and old_instance is not None:
            return build_diff_details(
                before={k: getattr(old_instance, k, None) for k in snapshot_keys},
                after={k: getattr(instance, k, None) for k in snapshot_keys},
                sensitive_extra=sensitive,
            )
        if action == AuditAction.DELETE:
            return build_diff_details(
                before={k: getattr(instance, k, None) for k in snapshot_keys},
                after=None,
                sensitive_extra=sensitive,
            )
        return {}

    @action(detail=False, methods=['post'], url_path='push-to-agent')
    @audit_action(AuditAction.EXECUTE, AuditResourceType.MONITOR_RULE, resource_id_kw="")
    def push_to_agent(self, request):
        """Push enabled monitor rules to one or all connected agents.

        POST /api/v2/monitor-rules/push-to-agent/
        Body (optional): {"agent_id": "<agent_id>"} — omit to broadcast to
        all online agents.

        Triggers ``WorkerConsumer.monitor_rule_update`` via the channel layer
        (``group_send({"type": "monitor.rule.update", ...})``). The agent
        receives the frame and calls ``MonitorManager.update_rules(rules)``
        to hot-swap the active rule set without restarting the process.

        Returns:
            {"pushed_count": <int>, "rules_count": <int>, "agent_id": <str|None>}
        """
        agent_id = request.data.get('agent_id')
        # Filter by is_enabled when no resource_pack filter is provided; allow
        # callers to scope by resource_pack via query param for targeted pushes.
        queryset = self.get_queryset().filter(is_enabled=True)
        resource_pack = request.query_params.get('resource_pack')
        if resource_pack:
            queryset = queryset.filter(resource_pack_id=resource_pack)

        serializer = self.get_serializer(queryset, many=True)
        rules_payload = serializer.data
        channel_layer = get_channel_layer()

        pushed = 0
        if agent_id:
            # Targeted push to a single agent's channel group.
            group_name = f'agent_{agent_id}'
            try:
                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {
                        'type': 'monitor.rule.update',
                        'payload': {'rules': rules_payload, 'agent_id': agent_id},
                    },
                )
                pushed = 1
            except Exception as exc:
                logger.error("推送监控规则到 agent %s 失败: %s", agent_id, exc)
                return Response(
                    {'detail': f'推送失败: {exc}', 'agent_id': agent_id},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            # Broadcast to all online agents. Walk the Agent table to enumerate
            # known agent_ids rather than relying on a channel-layer registry
            # (which differs between InMemoryChannelLayer and RedisChannelLayer).
            online_agents = Worker.objects.filter(status='online')
            for agent in online_agents:
                group_name = f'agent_{agent.agent_id}'
                try:
                    async_to_sync(channel_layer.group_send)(
                        group_name,
                        {
                            'type': 'monitor.rule.update',
                            'payload': {'rules': rules_payload, 'agent_id': agent.agent_id},
                        },
                    )
                    pushed += 1
                except Exception as exc:
                    logger.warning("广播监控规则到 agent %s 失败: %s", agent.agent_id, exc)

        logger.info(
            "监控规则推送完成: pushed=%d, rules=%d, agent_id=%s",
            pushed, len(rules_payload), agent_id,
        )
        return Response({
            'pushed_count': pushed,
            'rules_count': len(rules_payload),
            'agent_id': agent_id,
        })


class MonitorEventViewSet(viewsets.ReadOnlyModelViewSet):
    """监控事件只读视图集，支持过滤 + P-024 acknowledge 动作。"""

    queryset = MonitorEvent.objects.all().select_related('agent', 'resource_pack', 'acknowledged_by')
    serializer_class = MonitorEventSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    filterset_fields = ['event_type', 'severity', 'agent', 'resource_pack']
    search_fields = ['event_type', 'handling_result']

    @action(detail=True, methods=['post'], url_path='acknowledge')
    def acknowledge(self, request, pk=None):
        """确认告警, P-024 升级策略的一部分。

        POST /api/monitor-events/{id}/acknowledge/
        Body (可选): {"note": "处理说明"}
        效果: acknowledged_at = now, acknowledged_by = request.user
        """
        event = self.get_object()
        if event.acknowledged_at is not None:
            return Response(
                {'detail': '该告警已被确认', 'acknowledged_at': event.acknowledged_at.isoformat()},
                status=status.HTTP_409_CONFLICT,
            )
        event.acknowledged_at = timezone.now()
        event.acknowledged_by = request.user
        note = request.data.get('note', '')
        if note:
            existing = event.handling_result or ''
            event.handling_result = f'{existing} [确认备注] {note}'.strip() if existing else f'[确认备注] {note}'
        event.save(update_fields=['acknowledged_at', 'acknowledged_by', 'handling_result'])
        return Response(
            MonitorEventSerializer(event).data,
            status=status.HTTP_200_OK,
        )


class SLAMetricViewSet(viewsets.ReadOnlyModelViewSet):
    """SLA 指标视图集，只读查询 (migrated from metrics app — 2026-08-04)."""

    queryset = SLAMetric.objects.all().select_related('agent')
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'view'
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['agent', 'metric_name']
    search_fields = ['metric_name']

    def get_serializer_class(self):
        return SLAMetricSerializer

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """获取各指标的统计摘要（平均值、最大、最小、数量）。"""
        metric_name = request.query_params.get('metric_name')
        qs = SLAMetric.objects.all()
        if metric_name:
            qs = qs.filter(metric_name=metric_name)

        agg = qs.aggregate(
            avg=Avg('value'),
            max=Max('value'),
            min=Min('value'),
            count=Count('id'),
        )
        return Response({
            'metric_name': metric_name or 'all',
            'average': round(agg['avg'], 2) if agg['avg'] else 0,
            'max': agg['max'],
            'min': agg['min'],
            'count': agg['count'],
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='by-name')
    def by_name(self, request):
        """按指标名称分组列出最新值。"""
        from django.db.models import OuterRef, Subquery

        latest = SLAMetric.objects.filter(
            metric_name=OuterRef('metric_name')
        ).order_by('-timestamp')

        records = SLAMetric.objects.filter(
            id=Subquery(latest.values('id')[:1])
        ).select_related('agent').order_by('metric_name')

        return Response({
            'items': SLAMetricSerializer(records, many=True).data,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='report')
    def report(self, request):
        """Agent 上报 SLA 指标数据。"""
        serializer = SLAMetricReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        metric = SLAMetric.objects.create(
            metric_name=serializer.validated_data['metric_name'],
            value=serializer.validated_data['value'],
            labels=serializer.validated_data.get('labels', {}),
        )
        return Response(SLAMetricSerializer(metric).data, status=status.HTTP_201_CREATED)


def _load_service_health() -> list[dict]:
    """读取 gaf_daemon 写入的健康快照 (debug/health-status.json).

    spec 2026-08-29 P3: 快照由 daemon 看门狗每轮写入; 文件不存在或损坏时
    返回空列表, 由 frontend 显示为 N/A (不阻塞状态灯).
    """
    health_file = Path(__file__).resolve().parents[2] / "debug" / "health-status.json"
    try:
        if not health_file.exists():
            return []
        data = json.loads(health_file.read_text(encoding="utf-8"))
        services = data.get("services", {})
        updated_at = data.get("updated_at", "")
        return [
            {
                "name": name,
                "healthy": bool(h.get("healthy")),
                "detail": h.get("detail", ""),
                "ts": h.get("ts"),
            }
            for name, h in services.items()
        ] + ([{"name": "daemon", "healthy": True, "detail": f"快照 {updated_at}", "ts": None}] if services else [])
    except Exception as exc:
        logger.warning("读取服务健康快照失败: %s", exc)
        return []


@extend_schema(
    tags=['monitors'],
    summary='System global status summary',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def system_status_view(request):
    """
    系统全局状态摘要 API。

    GET /api/system/status/
    返回系统整体运行状态，供 Header 状态灯使用。
    """
    # @api_view allowed: cross-model aggregation (Agent + TaskExecution + RecoveryLog), not model CRUD
    agent_error = None
    try:
        from workers.models import Worker

        agents = Worker.objects.all()
        devices_online = agents.filter(status='online').count()
        devices_idle = agents.filter(status='idle').count()
        devices_total = agents.count()
    except Exception as e:
        devices_online = None
        devices_idle = None
        devices_total = None
        agent_error = f'Agent 统计查询失败: {str(e)}'
        logger.error('system_status Agent 统计失败: %s', e, exc_info=True)

    task_error = None
    try:
        from tasks.models import TaskExecution

        active_executions = TaskExecution.objects.filter(
            status__in=['pending', 'running'],
        ).count()
        from django.utils import timezone

        today = timezone.now().date()
        today_start = timezone.make_aware(
            __import__('datetime').datetime.combine(today, __import__('datetime').time.min),
        )
        today_completed = TaskExecution.objects.filter(
            status=TaskExecution.Status.SUCCESS,
            completed_at__gte=today_start,
        ).count()
    except Exception as e:
        active_executions = None
        today_completed = None
        task_error = f'任务统计查询失败: {str(e)}'
        logger.error('system_status 任务统计失败: %s', e, exc_info=True)

    warnings = []
    errors = []
    try:
        from scheduler.models import RecoveryLog

        recent_warnings_qs = RecoveryLog.objects.filter(
            success=False,
        ).order_by('-created_at')[:3]
        for log in recent_warnings_qs:
            warnings.append({
                'id': log.id,
                'timestamp': log.created_at.isoformat(),
                'type': 'warning',
                'source': 'scheduler',
                'message': log.trigger_event[:100] if log.trigger_event else '恢复操作失败',
            })

        recent_errors_qs = RecoveryLog.objects.filter(
            success=False,
            recovery_level='system',
        ).order_by('-created_at')[:3]
        for log in recent_errors_qs:
            errors.append({
                'id': log.id,
                'timestamp': log.created_at.isoformat(),
                'type': 'error',
                'source': 'agents',
                'message': log.trigger_event[:100] if log.trigger_event else '系统级恢复触发',
            })
    except Exception as e:
        logger.warning('system_status 恢复日志查询失败: %s', e, exc_info=True)

    if errors:
        overall = 'error'
    elif warnings:
        overall = 'warning'
    elif devices_online is not None and (devices_online > 0 or (devices_idle and devices_idle > 0)):
        overall = 'running'
    elif agent_error or task_error:
        overall = 'error'
    else:
        overall = 'idle'

    from django.utils import timezone

    # spec 2026-08-29 P3: 服务健康矩阵 (daemon 快照)
    services = _load_service_health()

    response_data = {
        'overall': overall,
        'devicesOnline': devices_online,
        'devicesIdle': devices_idle,
        'devicesTotal': devices_total,
        'activeExecutions': active_executions,
        'todayCompleted': today_completed,
        'unattendedActive': overall == 'running',
        'recentWarnings': warnings,
        'recentErrors': errors,
        'updatedAt': timezone.now().isoformat(),
        'services': services,
    }
    if services:
        # 任一服务不健康 → 降级为 warning (服务编排健康感知, spec P3)
        unhealthy_services = [s for s in services if not s['healthy']]
        if unhealthy_services and overall in ('running', 'idle'):
            response_data['overall'] = 'warning'
    if agent_error:
        response_data['agentError'] = agent_error
    if task_error:
        response_data['taskError'] = task_error

    return Response(response_data)


# ===========================================================================
# spec 2026-08-29-services-management-monitor P3: 服务管理 API
# 文件定位/报错过滤逻辑委托 gaf_core.log_files (spec 2026-08-29-logging-
# system-consolidation P2-1 统一检索层, 消除跨 app 双份漂移)
# ===========================================================================

_DEBUG_ROOT = Path(__file__).resolve().parents[2] / "debug"
_DAEMON_PID_FILE = _DEBUG_ROOT / "gaf_daemon.pid"

SERVICE_ORDER = ["redis", "backend", "worker", "frontend"]


@extend_schema(
    tags=['monitors'],
    summary='Service management status list (health + process + log errors)',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
def services_view(request):
    """
    服务管理状态列表 API (spec 2026-08-29-services-management-monitor).

    GET /api/v2/monitors/services/
    数据源: daemon 写入的 debug/health-status.json (services/processes/log_errors)
    + debug/gaf_daemon.pid. 供系统页签"服务管理"页展示.
    """
    # 读健康快照 (services + processes + log_errors)
    snapshot_services: dict = {}
    processes: dict = {}
    log_errors: dict = {}
    updated_at = None
    health_file = _DEBUG_ROOT / "health-status.json"
    try:
        if health_file.exists():
            data = json.loads(health_file.read_text(encoding="utf-8"))
            snapshot_services = data.get("services", {})
            processes = data.get("processes", {})
            log_errors = data.get("log_errors", {})
            updated_at = data.get("updated_at")
    except Exception as exc:
        logger.warning("读取服务健康快照失败: %s", exc)

    # daemon 运行信息
    daemon_running = False
    daemon_pid = None
    try:
        if _DAEMON_PID_FILE.exists():
            pid = _DAEMON_PID_FILE.read_text().strip()
            if pid.isdigit():
                daemon_pid = int(pid)
                daemon_running = True
    except OSError as exc:
        logger.warning("读取 daemon PID 失败: %s", exc)

    services: list[dict] = []
    for name in SERVICE_ORDER:
        h = snapshot_services.get(name, {})
        proc = processes.get(name, {})
        err = log_errors.get(name, {})
        services.append({
            'name': name,
            'healthy': h.get('healthy'),
            'detail': h.get('detail'),
            'ts': h.get('ts'),
            'running': proc.get('running'),
            'pid': proc.get('pid'),
            'port': proc.get('port'),
            'restart_count': proc.get('restart_count'),
            'error_count': err.get('count'),
            'latest_error': err.get('latest'),
            'log_files': err.get('files'),
        })
    services.append({
        'name': 'daemon',
        'healthy': daemon_running,
        'detail': f"daemon PID={daemon_pid}" if daemon_pid else 'daemon 未运行',
        'ts': None,
        'running': daemon_running,
        'pid': daemon_pid,
        'port': None,
        'restart_count': None,
        'error_count': None,
        'latest_error': None,
        'log_files': [],
    })

    return Response({
        'updatedAt': updated_at,
        'daemon': {'running': daemon_running, 'pid': daemon_pid},
        'services': services,
    })


@extend_schema(
    tags=['monitors'],
    summary='Restart a single service or all services (daemon control)',
    responses={202: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
def service_restart_view(request):
    """
    服务重启控制 API (spec 2026-08-30-services-restart-control).

    POST /api/v2/monitors/services/restart/
    body: {"service": "backend"|"agent"|"frontend"|"redis"|"all"} (默认 all)
    写入 daemon 控制文件 (debug/daemon-ctl.json), daemon 看门狗下一轮消费执行.
    返回 202 (已受理), 实际重启由 daemon 异步完成, 状态经 services/ 轮询可见.
    """
    service = (request.data.get('service') or 'all').strip().lower()
    if service != 'all' and service not in SERVICE_ORDER:
        return Response(
            {'detail': f"未知服务: {service}, 可选: {', '.join(SERVICE_ORDER)} 或 all"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ctl_file = _DEBUG_ROOT / 'daemon-ctl.json'
    try:
        ctl_file.write_text(json.dumps({
            'action': 'restart',
            'service': service,
            'ts': int(time.time()),
        }, ensure_ascii=False), encoding='utf-8')
    except OSError as exc:
        logger.warning("写入 daemon 控制文件失败 (%s): %s", ctl_file, exc)
        return Response({'detail': '控制文件写入失败, daemon 未消费指令'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    logger.info("[restart-ctl] 已下发服务重启指令: %s", service)
    return Response({
        'detail': f"服务 {service} 重启指令已下发 (daemon 异步执行)",
        'service': service,
    }, status=status.HTTP_202_ACCEPTED)


@extend_schema(
    tags=['monitors'],
    summary='Service terminal log tail (unified error resolution view)',
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter('service', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY, required=True),
        OpenApiParameter('lines', type=OpenApiTypes.INT, location=OpenApiParameter.QUERY),
        OpenApiParameter('filter', type=OpenApiTypes.STR, location=OpenApiParameter.QUERY),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
def service_logs_view(request):
    """
    服务终端日志尾部 API (统一排查报错).

    GET /api/v2/monitors/services/logs/?service=backend&lines=300&filter=error
    读取服务日志文件尾部; filter=error 时仅返回报错匹配行.
    """
    service = request.query_params.get('service', '').strip()
    if not service:
        return Response({'detail': 'service 参数必填'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        max_lines = min(int(request.query_params.get('lines', 300)), 2000)
    except ValueError:
        max_lines = 300
    filter_errors = request.query_params.get('filter', 'all').lower() == 'error'

    files = _resolve_service_log_files(service)
    lines = collect_error_lines(files, max_lines) if filter_errors else _read_log_tail(files, max_lines)

    return Response({
        'service': service,
        'path': str(files[0]) if files else None,
        'files': [str(f) for f in files],
        'lines': lines,
    })


@extend_schema(
    tags=['monitors'],
    summary='Notification chain health (TD-421)',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def notification_chain_health_view(request):
    """
    通知中心"链路健康"指标 (TD-421 2026-08-29).

    GET /api/v2/monitors/chain-health/
    让用户区分"没有告警" vs "告警链路断了":
    - last_event_at / event_count_24h: 近 24h 监控事件 (bus→MonitorEvent)
      是否在产生, 无事件时提示"链路可能未打点"
    - last_escalated_at / escalation_count: 升级任务 (P-024, 每 5min)
      最近运行痕迹, 无则提示"升级任务可能未启用"
    - next_escalation_in_seconds: 距下次升级扫描的时间
    """
    # @api_view allowed: read-only aggregation over MonitorEvent, not model CRUD
    from datetime import timedelta

    from django.utils import timezone as tz

    now = tz.now()
    cutoff = now - timedelta(days=1)

    last_event = MonitorEvent.objects.order_by('-created_at').first()
    last_escalated = MonitorEvent.objects.exclude(escalated_at__isnull=True).order_by('-escalated_at').first()

    event_count_24h = MonitorEvent.objects.filter(created_at__gte=cutoff).count()

    # 升级任务调度时距 (config/celery.py: 每 300s 一次; 取基线)
    escalation_interval_sec = 300
    next_escalation_in = None
    if last_escalated:
        elapsed = (now - last_escalated.escalated_at).total_seconds()
        next_escalation_in = max(0, escalation_interval_sec - (elapsed % escalation_interval_sec))

    return Response({
        'last_event_at': last_event.created_at.isoformat() if last_event else None,
        'event_count_24h': event_count_24h,
        'last_escalated_at': last_escalated.escalated_at.isoformat() if last_escalated else None,
        'escalation_count': MonitorEvent.objects.exclude(escalated_at__isnull=True).count(),
        'escalation_interval_seconds': escalation_interval_sec,
        'next_escalation_in_seconds': next_escalation_in,
    })


@extend_schema(
    tags=['monitors'],
    summary='Unread alerts summary',
    responses={200: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter(
            name='limit',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Max number of alerts to return',
        ),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def alerts_summary_view(request):
    """
    未处理告警摘要 API。

    GET /api/monitors/alerts/?unread=true&limit=5
    从 MonitorEvent 表查询最近事件，按级别汇总为告警摘要。
    """
    # @api_view allowed: alerts summary aggregation with severity mapping, not model CRUD
    limit = int(request.query_params.get('limit', 5))
    from datetime import timedelta

    from django.utils import timezone as tz

    cutoff = tz.now() - timedelta(days=7)
    events = MonitorEvent.objects.filter(created_at__gte=cutoff).order_by('-created_at')[:limit]

    severity_map = {
        'error': 'critical', 'failure': 'critical', 'critical': 'critical',
        'timeout': 'warning', 'warning': 'warning',
        'degraded': 'warning',
    }

    alerts = []
    for ev in events:
        ev_type = ev.event_type.lower()
        level = 'info'
        for key, sev in severity_map.items():
            if key in ev_type:
                level = sev
                break
        source = 'agents' if ev.agent_id else 'scheduler'
        if ev.resource_pack_id:
            source = 'resources'

        alerts.append({
            'id': ev.id,
            'level': level,
            'message': ev.handling_result or ev.event_type,
            'created_at': ev.created_at.isoformat(),
            'source': source,
        })

    return Response({
        'total': MonitorEvent.objects.filter(created_at__gte=cutoff).count(),
        'unread': len(alerts),
        'alerts': alerts,
    })


@extend_schema(
    tags=['monitors'],
    summary='Alert history trend by day and severity',
    responses={200: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter(
            name='days',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Lookback window in days',
        ),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def alert_history_view(request):
    """
    告警历史趋势 API。

    GET /api/monitors/alerts/history/?days=7
    从 MonitorEvent 表按日期和严重级别聚合，返回历史趋势数据。
    """
    # @api_view allowed: time-series analytics aggregation over MonitorEvent, not model CRUD
    days = int(request.query_params.get('days', 7))
    from collections import defaultdict
    from datetime import timedelta

    from django.utils import timezone as tz

    today = tz.now().date()
    cutoff = today - timedelta(days=days)
    events = MonitorEvent.objects.filter(created_at__date__gte=cutoff)

    daily_counts = defaultdict(lambda: {'critical': 0, 'warning': 0, 'info': 0, 'resolved': 0})
    severity_map = {
        'error': 'critical', 'failure': 'critical',
        'timeout': 'warning',
    }

    for ev in events:
        d = ev.created_at.strftime('%Y-%m-%d')
        ev_type = ev.event_type.lower()
        level = 'info'
        for key, sev in severity_map.items():
            if key in ev_type:
                level = sev
                break
        if ev.handling_result and '处理' in ev.handling_result:
            daily_counts[d]['resolved'] += 1
        else:
            daily_counts[d][level] += 1

    history = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        counts = daily_counts.get(d, {'critical': 0, 'warning': 0, 'info': 0, 'resolved': 0})
        history.append({
            'date': d,
            'critical': counts['critical'],
            'warning': counts['warning'],
            'info': counts['info'],
            'resolved': counts['resolved'],
        })

    return Response({'history': history})


@extend_schema(
    tags=['monitors'],
    summary='Device health details from Agent capabilities',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def device_health_view(request):
    """
    设备健康度详情 API。

    GET /api/monitors/device-health/
    从 Agent 表查询所有注册设备的实时健康数据。
    若 Agent 未上报性能指标，返回基础状态信息。
    """
    # @api_view allowed: computes per-device health score from Agent capabilities, not model CRUD
    from workers.models import Worker

    agents = Worker.objects.all()
    devices = []
    for agent in agents:
        caps = agent.capabilities or {}
        is_online = getattr(agent, 'is_online', False) or agent.status == 'online'

        cpu = caps.get('cpu_percent')
        memory = caps.get('memory_percent')
        disk = caps.get('disk_percent')
        fps = caps.get('fps')
        network_latency = caps.get('network_latency_ms')
        frame_time = caps.get('frame_time_ms')
        score = caps.get('health_score')

        if is_online:
            if score is not None:
                status_label = 'healthy' if score >= 80 else 'warning' if score >= 60 else 'critical'
            elif cpu and cpu > 80:
                status_label = 'critical'
            elif cpu and cpu > 60:
                status_label = 'warning'
            else:
                status_label = 'healthy'
            if score is None:
                score = 95 if status_label == 'healthy' else 71 if status_label == 'warning' else 38
        else:
            status_label = 'offline'
            score = 0

        devices.append({
            'name': agent.hostname or agent.agent_id,
            'cpu': cpu,
            'memory': memory,
            'disk': disk,
            'network_latency': network_latency,
            'fps': fps,
            'frame_time': frame_time,
            'status': status_label,
            'score': score,
        })

    return Response({'devices': devices})


@extend_schema(
    tags=['monitors'],
    summary='One-click diagnose (ADB/port/DB/Agent checks)',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def diagnose_view(request):
    """
    一键诊断 API，检测系统常见问题。

    GET /api/v2/monitors/diagnose/
    检测 ADB 连接、端口占用、Redis、数据库、Agent 进程等常见问题。
    """
    # @api_view allowed: multi-check running subprocess (adb), sockets, DB probes, not model CRUD
    import shutil
    import socket
    import subprocess

    results = []

    # 1. ADB 检测
    adb_status = 'ok'
    adb_message = 'ADB 正常'
    try:
        adb_path = shutil.which('adb')
        if adb_path:
            proc = subprocess.run(
                ['adb', 'devices'],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            devices_output = proc.stdout.strip()
            device_count = sum(
                1 for line in devices_output.splitlines()[1:]
                if '\tdevice' in line
            )
            adb_message = f'ADB 已连接，{device_count} 台设备'
            if device_count == 0:
                adb_status = 'warning'
                adb_message = 'ADB 正常，但未检测到设备'
        else:
            adb_status = 'error'
            adb_message = 'ADB 未安装或未加入 PATH'
    except Exception as e:
        logger.warning("system_status: ADB detection failed: %s", e, exc_info=True)
        adb_status = 'error'
        adb_message = f'ADB 检测失败: {str(e)}'

    results.append({
        'category': 'adb',
        'name': 'ADB 连接',
        'status': adb_status,
        'message': adb_message,
        'fixable': adb_status == 'error' and '未安装' in adb_message,
    })

    # 2. 后端端口占用检测（从 BACKEND_PORT 环境变量读取，默认 8000）
    backend_port = int(os.environ.get("BACKEND_PORT", "8000"))
    port_status = 'ok'
    port_message = f'端口 {backend_port} 正常'
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex(('127.0.0.1', backend_port))
            if result == 0:
                port_message = f'端口 {backend_port} 已被占用（后端运行中）'
            else:
                port_status = 'warning'
                port_message = f'端口 {backend_port} 未占用（后端未运行）'
    except Exception as e:
        logger.warning("system_status: port detection failed: %s", e, exc_info=True)
        port_status = 'error'
        port_message = f'端口检测失败: {str(e)}'

    results.append({
        'category': 'port',
        'name': '后端端口',
        'status': port_status,
        'message': port_message,
        'fixable': False,
    })

    # 3. 数据库检测 (spec-59-E: raw SQL → ORM, 用 connection.is_usable() 替代 SELECT 1)
    db_status = 'ok'
    db_message = '数据库连接正常'
    try:
        from django.db import connection
        connection.ensure_connection()
        if not connection.is_usable():
            raise RuntimeError("connection.is_usable() returned False")
    except Exception as e:
        logger.warning("system_status: DB connection failed: %s", e, exc_info=True)
        db_status = 'error'
        db_message = f'数据库连接失败: {str(e)}'

    results.append({
        'category': 'database',
        'name': '数据库',
        'status': db_status,
        'message': db_message,
        'fixable': False,
    })

    # 4. Agent 进程检测
    agent_status = 'ok'
    agent_message = 'Agent 进程正常'
    try:
        from workers.models import Worker
        online_agents = Worker.objects.filter(status='online').count()
        total_agents = Worker.objects.count()
        if total_agents == 0:
            agent_status = 'warning'
            agent_message = '未注册 Agent，请启动 Agent 进程'
        elif online_agents == 0:
            agent_status = 'warning'
            agent_message = f'已注册 {total_agents} 个 Agent，但均未在线'
        else:
            agent_message = f'{online_agents}/{total_agents} 个 Agent 在线'
    except Exception as e:
        logger.warning("system_status: agent detection failed: %s", e, exc_info=True)
        agent_status = 'error'
        agent_message = f'Agent 检测失败: {str(e)}'

    results.append({
        'category': 'agent',
        'name': 'Agent 进程',
        'status': agent_status,
        'message': agent_message,
        'fixable': agent_status == 'warning' and '未注册' in agent_message,
    })

    # 计算总体状态
    error_count = sum(1 for r in results if r['status'] == 'error')
    warning_count = sum(1 for r in results if r['status'] == 'warning')
    fixable_count = sum(1 for r in results if r['fixable'])

    overall = 'ok'
    if error_count > 0:
        overall = 'error'
    elif warning_count > 0:
        overall = 'warning'

    return Response({
        'overall': overall,
        'total_issues': error_count + warning_count,
        'error_count': error_count,
        'warning_count': warning_count,
        'fixable_count': fixable_count,
        'results': results,
    })


@extend_schema(
    tags=['monitors'],
    summary='One-click auto fix (restart ADB, rescan devices)',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 500: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def auto_fix_view(request):
    """
    一键修复 API，自动修复可修复的问题。

    POST /api/v2/monitors/fix/
    自动执行修复操作，如重启 ADB、释放端口等。
    """
    # @api_view allowed: multi-step fix running subprocess (adb restart, device scan), not model CRUD
    import os
    import shutil
    import subprocess
    import time

    fixed = []
    failed = []

    # 1. 修复 ADB
    try:
        adb_path = shutil.which('adb')
        if adb_path:
            subprocess.run(
                ['adb', 'kill-server'],
                capture_output=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            time.sleep(1)
            proc = subprocess.run(
                ['adb', 'start-server'],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            if proc.returncode == 0:
                fixed.append({'category': 'adb', 'message': 'ADB 服务已重启'})
            else:
                failed.append({'category': 'adb', 'message': f'ADB 重启失败: {proc.stderr}'})
        else:
            failed.append({'category': 'adb', 'message': 'ADB 未安装，无法修复'})
    except Exception as e:
        logger.warning("auto_fix: ADB fix failed: %s", e, exc_info=True)
        failed.append({'category': 'adb', 'message': f'ADB 修复失败: {str(e)}'})

    # 2. 重新探测设备
    try:
        from workers.views import DeviceScanView
        scan_view = DeviceScanView()
        scan_view.request = request
        scan_result = scan_view.get(request)
        device_count = len(scan_result.data) if hasattr(scan_result, 'data') else 0
        fixed.append({'category': 'devices', 'message': f'已扫描 {device_count} 台设备'})
    except Exception as e:
        logger.warning("auto_fix: device scan failed: %s", e, exc_info=True)
        failed.append({'category': 'devices', 'message': f'设备扫描失败: {str(e)}'})

    # 3. 检查 Agent 连接
    try:
        from workers.models import Worker
        offline_agents = Worker.objects.filter(status='offline')
        if offline_agents.exists():
            fixed.append({
                'category': 'agent',
                'message': f'{offline_agents.count()} 个 Agent 离线，请检查 Agent 进程',
            })
        else:
            online_count = Worker.objects.filter(status='online').count()
            fixed.append({'category': 'agent', 'message': f'{online_count} 个 Agent 在线'})
    except Exception as e:
        logger.warning("auto_fix: agent check failed: %s", e, exc_info=True)
        failed.append({'category': 'agent', 'message': f'Agent 检查失败: {str(e)}'})

    return Response({
        'success': len(failed) == 0,
        'fixed': fixed,
        'failed': failed,
    })
