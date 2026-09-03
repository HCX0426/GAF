"""
执行管理模块 - Phase 9 后端 API 视图
提供 Pipeline 步骤详情、手动干预、每日报告、无人值守日志等接口
"""
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from django.apps import apps
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from gaf_core.audit_constants import AuditAction, AuditResourceType, get_client_ip
from gaf_core.error_codes import ErrorCode
from gaf_core.responses import unified_response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from scheduler.models import RecoveryLog

from accounts.permissions import RoleBasedPermission, require_permission

# spec-59-E / TD-297: avoid top-level ``from tasks.models import ...``
# cross-app import. executions app is the view layer for tasks (no own
# models; all 9 view functions read TaskExecution / ExecutionStep). Migrating
# 35 use sites to a service layer would require 8+ wrapper functions —
# over-engineering per N178-A3. Use apps.get_model at module load time
# (apps registry is ready by the time URL config imports this module) so
# TaskExecution / ExecutionStep are available as module attributes for name
# lookup inside functions, without a top-level cross-app import statement.
TaskExecution = apps.get_model('tasks', 'TaskExecution')
ExecutionStep = apps.get_model('tasks', 'ExecutionStep')

logger = logging.getLogger(__name__)


@extend_schema(
    tags=['executions'],
    summary='List pipeline steps for an execution',
    responses={200: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter('step_index', OpenApiTypes.INT, description='Return only the step with this index.'),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission('view')
def execution_steps_view(request, pk):
    """
    获取指定执行的 Pipeline 步骤详情列表

    从 ExecutionStep 表查询步骤数据，按 step_index 排序。
    Admin 可查看任意执行；其他用户仅能查看自己触发的执行。
    """
    # @api_view allowed: custom aggregation over ExecutionStep with permission filtering, not model CRUD
    steps_qs = ExecutionStep.objects.filter(task_result_id=pk).order_by('step_index')
    step_index = request.query_params.get('step_index')

    try:
        execution = TaskExecution.objects.get(pk=pk)
    except TaskExecution.DoesNotExist:
        # Task 4.53 (P1-33, 2026-07-28): 改用 unified_response 信封
        return unified_response(
            message=f'执行记录 #{pk} 不存在',
            code=ErrorCode.NOT_FOUND,
            status=status.HTTP_404_NOT_FOUND,
        )

    # Non-admin users can only view their own executions
    if request.user.role != 'admin' and execution.triggered_by_id != request.user.id:
        return Response(
            {'error': '无权查看此执行记录'},
            status=status.HTTP_403_FORBIDDEN,
        )

    steps = []
    for s in steps_qs:
        steps.append({
            'id': s.id,
            'execution_id': s.task_result_id,
            'index': s.step_index,
            'name': s.step_name,
            'status': s.status,
            'started_at': s.started_at.isoformat() if s.started_at else None,
            'duration': s.duration if s.duration else None,
            'retries': s.retry_count,
            'error_message': s.error_message or None,
            'screenshot_url': s.screenshot_path or None,
        })

    if step_index is not None:
        try:
            idx = int(step_index)
            step = next((s for s in steps if s['index'] == idx), None)
            if step:
                return Response({'execution_id': pk, 'step': step})
            return Response(
                {'error': f'未找到索引为 {idx} 的步骤'},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (ValueError, TypeError):
            # Task 4.53 (P1-33, 2026-07-28): 改用 unified_response 信封
            return unified_response(
                message='step_index 参数必须为整数',
                code=ErrorCode.INVALID_PARAMS,
                status=status.HTTP_400_BAD_REQUEST,
            )

    return Response({
        'execution_id': pk,
        'total_steps': len(steps),
        'completed_steps': sum(1 for s in steps if s['status'] == 'success'),
        'running_steps': sum(1 for s in steps if s['status'] == 'running'),
        'pending_steps': sum(1 for s in steps if s['status'] == 'pending'),
        'steps': steps,
    })


@extend_schema(
    tags=['executions'],
    summary='Manually intervene a running execution (pause/resume/skip/cancel)',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
)
@api_view(['POST'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission('execute')
def execution_intervene_view(request, pk):
    """
    手动干预正在运行的执行任务

    支持 pause/resume/skip_step/fail_step/cancel 操作。
    尝试更新 TaskExecution 状态。Admin 可干预任意执行；其他用户仅能干预自己触发的执行。
    """
    # @api_view allowed: one-off state-machine action (pause/resume/skip/cancel), not CRUD
    valid_actions = {'pause', 'resume', 'skip_step', 'fail_step', 'cancel'}
    action = request.data.get('action')
    reason = request.data.get('reason', '')

    if not action:
        # Task 4.53 (P1-33, 2026-07-28): 改用 unified_response 信封
        return unified_response(
            message='缺少必要参数 action',
            code=ErrorCode.INVALID_PARAMS,
            status=status.HTTP_400_BAD_REQUEST,
        )
    if action not in valid_actions:
        # Task 4.53 (P1-33, 2026-07-28): 改用 unified_response 信封,
        # valid_actions 透传到 data 让前端展示可选项
        return unified_response(
            data={'valid_actions': sorted(valid_actions)},
            message=f'无效的 action 参数: {action}',
            code=ErrorCode.INVALID_PARAMS,
            status=status.HTTP_400_BAD_REQUEST,
        )

    action_labels = {
        'pause': '暂停执行',
        'resume': '恢复执行',
        'skip_step': '跳过当前步骤',
        'fail_step': '标记步骤失败',
        'cancel': '取消执行',
    }

    try:
        with transaction.atomic():
            # Lock the execution row to prevent concurrent intervention
            # race conditions (pause/resume/cancel/skip_step/fail_step).
            execution = TaskExecution.objects.select_for_update().get(pk=pk)

            # Non-admin users can only intervene on their own executions
            if request.user.role != 'admin' and execution.triggered_by_id != request.user.id:
                # Task 4.53 (P1-33, 2026-07-28): 改用 unified_response 信封
                return unified_response(
                    message='无权干预此执行记录',
                    code=ErrorCode.PERMISSION_DENIED,
                    status=status.HTTP_403_FORBIDDEN,
                )

            status_map = {
                'pause': TaskExecution.Status.PAUSED,
                'resume': TaskExecution.Status.RUNNING,
                'cancel': TaskExecution.Status.CANCELLED,
            }
            if action in status_map:
                execution.status = status_map[action]
                execution.save(update_fields=['status'])

            # L3 fix: handle skip_step/fail_step by updating the currently running
            # step's status. Previously these actions were accepted (in valid_actions)
            # but silently did nothing. The task executor should poll step status to
            # actually skip/fail the in-flight operation.
            step_status_map = {
                'skip_step': ExecutionStep.Status.SKIPPED,
                'fail_step': ExecutionStep.Status.FAILED,
            }
            if action in step_status_map:
                running_step = ExecutionStep.objects.filter(
                    task_result_id=execution.pk,
                    status=ExecutionStep.Status.RUNNING,
                ).order_by('step_index').first()
                if running_step:
                    running_step.status = step_status_map[action]
                    running_step.save(update_fields=['status'])
                    logger.info(
                        "步骤 #%s (%s) 已标记为 %s (执行 #%s)",
                        running_step.pk, running_step.step_name,
                        step_status_map[action].value, execution.pk,
                    )
                else:
                    logger.warning(
                        "执行 #%s 无 running 步骤，%s 操作无效果", execution.pk, action,
                    )

            logger.info(
                "用户 %s 对执行 #%s 执行干预操作: action=%s, reason=%s",
                request.user.username, pk, action, reason,
            )
    except TaskExecution.DoesNotExist:
        # Task 4.53 (P1-33, 2026-07-28): 改用 unified_response 信封
        return unified_response(
            message=f'执行记录 #{pk} 不存在',
            code=ErrorCode.NOT_FOUND,
            status=status.HTTP_404_NOT_FOUND,
        )

    # Audit log: record that the user manually intervened on this
    # execution. ``reason`` is operator-supplied free text and may
    # include sensitive context, so we record only action + a short
    # length (not the plaintext reason) to keep AuditLog compact.
    from accounts.audit import log_audit

    log_audit(
        user=request.user,
        action=AuditAction.EXECUTE,
        resource_type=AuditResourceType.TASK_EXECUTION,
        resource_id=str(pk),
        details={
            'execution_id': int(pk),
            'action': action,
            'action_label': action_labels.get(action, action),
            'reason_length': len(reason),
            'operator': request.user.username,
        },
        ip_address=get_client_ip(request),
    )

    return Response({
        'success': True,
        'message': f'已成功执行{action_labels.get(action, action)}操作',
        'intervention': {
            'id': pk,
            'execution_id': int(pk),
            'action': action,
            'action_label': action_labels.get(action, action),
            'operator': request.user.username,
            'reason': reason,
            'created_at': timezone.now().isoformat(),
            'status': 'success',
            'message': f'已成功执行{action_labels.get(action, action)}操作',
        },
    }, status=status.HTTP_200_OK)


@extend_schema(
    tags=['executions', 'analytics'],
    summary='Daily execution report with markdown',
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter('date', OpenApiTypes.STR, description='Report date in YYYY-MM-DD format (default: today).'),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission('view')
def daily_report_view(request):
    """
    获取每日执行报告

    从 TaskExecution 和 ExecutionStep 表聚合统计生成日报。
    Admin 看全平台数据；其他用户仅看自己触发的执行。
    """
    # @api_view allowed: analytics aggregation producing markdown report, not model CRUD
    date_param = request.query_params.get('date')
    target_date = date_param if date_param else timezone.now().strftime('%Y-%m-%d')

    try:
        report_dt = datetime.strptime(target_date, '%Y-%m-%d')
    except ValueError:
        return Response({'error': '日期格式错误，需为 YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

    tz_now = timezone.now()
    day_start = tz_now.replace(
        year=report_dt.year, month=report_dt.month, day=report_dt.day,
        hour=0, minute=0, second=0, microsecond=0,
    )
    day_end = day_start + timedelta(days=1)

    executions = TaskExecution.objects.filter(created_at__gte=day_start, created_at__lt=day_end).select_related('agent', 'triggered_by', 'task')
    # Non-admin users only see their own executions in the daily report
    if request.user.role != 'admin':
        executions = executions.filter(triggered_by=request.user)

    total = executions.count()
    successful = executions.filter(status='success').count()
    failed = executions.filter(status='failed').count()
    cancelled = executions.filter(status='cancelled').count()
    interrupted = executions.filter(
        Q(status='force_terminated') | Q(status='paused')
    ).count()

    durations = executions.filter(duration__isnull=False)
    avg_duration = durations.aggregate(avg=Avg('duration'))['avg']
    avg_duration_min = round(avg_duration.total_seconds() / 60, 1) if avg_duration else 0

    total_runtime = sum(
        (d.duration.total_seconds() / 3600) for d in durations
    )

    overview = {
        'date': target_date,
        'total_executions': total,
        'successful': successful,
        'failed': failed,
        'cancelled': cancelled,
        'interrupted': interrupted,
        'success_rate': round(successful / total * 100, 1) if total else 0,
        'avg_duration_minutes': avg_duration_min,
        'total_runtime_hours': round(total_runtime, 1),
    }

    agent_stats = []
    for agent_id, agent_name in executions.values_list('agent_id', 'agent__hostname').distinct():
        if agent_id is None:
            continue
        qs = executions.filter(agent_id=agent_id)
        cnt = qs.count()
        succ = qs.filter(status='success').count()
        fl = qs.filter(status='failed').count()
        agent_stats.append({
            'device_name': agent_name or f'Agent-{agent_id}',
            'executions': cnt,
            'success': succ,
            'failed': fl,
            'success_rate': round(succ / cnt * 100, 1) if cnt else 0,
        })

    account_stats = []
    for uid, uname in executions.values_list('triggered_by_id', 'triggered_by__username').distinct():
        if uid is None:
            continue
        qs = executions.filter(triggered_by_id=uid)
        cnt = qs.count()
        succ = qs.filter(status='success').count()
        fl = qs.filter(status='failed').count()
        account_stats.append({
            'account_alias': uname or f'User-{uid}',
            'executions': cnt,
            'success': succ,
            'failed': fl,
            'success_rate': round(succ / cnt * 100, 1) if cnt else 0,
        })

    step_stats = []
    step_aggregates = ExecutionStep.objects.filter(
        task_result__created_at__gte=day_start,
        task_result__created_at__lt=day_end,
    ).values('step_name').annotate(
        total_runs=Count('id'),
        fail_count=Count('id', filter=Q(status='failed')),
        avg_dur=Avg('duration'),
    ).order_by('step_name')

    for s in step_aggregates:
        avg_s = round(s['avg_dur'], 1) if s['avg_dur'] else 0
        fail_rate = round(s['fail_count'] / s['total_runs'] * 100, 1) if s['total_runs'] else 0
        step_stats.append({
            'step_name': s['step_name'] or '未命名步骤',
            'total_runs': s['total_runs'],
            'avg_duration_s': avg_s,
            'fail_count': s['fail_count'],
            'fail_rate': fail_rate,
        })

    failed_executions = executions.filter(status='failed').select_related('agent', 'triggered_by').prefetch_related('execution_steps').order_by('-created_at')[:5]
    failures = []
    for fe in failed_executions:
        last_step = fe.execution_steps.filter(status='failed').order_by('-step_index').first()
        failures.append({
            'execution_id': fe.id,
            'device': fe.agent.hostname if fe.agent else '',
            'account': fe.triggered_by.username if fe.triggered_by else '',
            'failed_step': last_step.step_name if last_step else '',
            'error': fe.error_message or '',
            'time': fe.created_at.isoformat(),
            'root_cause': fe.error_message or '待分析',
        })

    report_markdown = _build_report_markdown(target_date, overview, agent_stats, account_stats, step_stats, failures)

    # L3-1 Round 9 (spec 2026-07-17-l3-round9): add summary/items/generated_at
    # to align with frontend DailyReportData interface (frontend/src/api/executions.ts:123).
    # Original `data` block retained for analytics consumers.
    summary = {
        'date': target_date,
        'total_executions': total,
        'success_count': successful,
        'failed_count': failed,
        'avg_duration': f'{avg_duration_min} min',
    }

    items_qs = executions.select_related('task', 'agent', 'triggered_by').order_by('-started_at')
    items = []
    for fe in items_qs:
        duration = fe.duration.total_seconds() if fe.duration else 0
        # Format duration as "M:SS" or "H:MM:SS" to match frontend DailyReportItem.duration string
        if duration >= 3600:
            duration_str = f'{int(duration // 3600)}:{int((duration % 3600) // 60):02d}:{int(duration % 60):02d}'
        else:
            duration_str = f'{int(duration // 60)}:{int(duration % 60):02d}'
        items.append({
            'id': str(fe.id),
            'task_name': fe.task.name if fe.task else '',
            'device_name': fe.agent.hostname if fe.agent else '',
            'account_name': fe.triggered_by.username if fe.triggered_by else '',
            'status': fe.status,
            'started_at': fe.started_at.isoformat() if fe.started_at else None,
            'completed_at': fe.completed_at.isoformat() if fe.completed_at else None,
            'duration': duration_str,
            'error_message': fe.error_message,
        })

    return Response({
        'date': target_date,
        # Frontend DailyReportData fields ( DailyReportViewer.tsx consumes these)
        'summary': summary,
        'items': items,
        'generated_at': timezone.now().isoformat(),
        # Original rich payload retained for analytics/markdown consumers
        'report_markdown': report_markdown,
        'data': {
            'overview': overview,
            'device_stats': agent_stats,
            'account_stats': account_stats,
            'step_stats': step_stats,
            'failures': failures,
            'anomalies': _detect_anomalies(executions),
        },
    })


def _build_report_markdown(target_date, overview, device_stats, account_stats, step_stats, failures):
    """构建日报 Markdown 文本"""
    md = f"""# 📊 自动化执行日报 — {target_date}

## 一、执行概览

| 指标 | 数值 |
|------|------|
| 总执行次数 | {overview['total_executions']} 次 |
| 成功 | {overview['successful']} 次 ({overview['success_rate']}%) |
| 失败 | {overview['failed']} 次 |
| 已取消 | {overview['cancelled']} 次 |
| 已中断 | {overview['interrupted']} 次 |
| 平均耗时 | {overview['avg_duration_minutes']} 分钟 |
| 总运行时长 | {overview['total_runtime_hours']} 小时 |

## 二、设备统计

| 设备名称 | 执行数 | 成功 | 失败 | 成功率 |
|----------|--------|------|------|--------|
"""
    for ds in device_stats:
        md += f"| {ds['device_name']} | {ds['executions']} | {ds['success']} | {ds['failed']} | {ds['success_rate']}% |\n"

    if account_stats:
        md += "\n## 三、账号统计\n\n"
        md += "| 账号别名 | 执行数 | 成功 | 失败 | 成功率 |\n"
        md += "|----------|--------|------|------|--------|\n"
        for ac in account_stats:
            md += f"| {ac['account_alias']} | {ac['executions']} | {ac['success']} | {ac['failed']} | {ac['success_rate']}% |\n"

    if step_stats:
        md += "\n## 四、步骤级统计\n\n"
        md += "| 步骤名称 | 运行次数 | 平均耗时(s) | 失败数 | 失败率 |\n"
        md += "|----------|----------|-------------|--------|--------|\n"
        for ss in step_stats:
            md += f"| {ss['step_name']} | {ss['total_runs']} | {ss['avg_duration_s']} | {ss['fail_count']} | {ss['fail_rate']}% |\n"

    if failures:
        md += f"\n## 五、失败记录 ({len(failures)} 条)\n\n"
        for i, f in enumerate(failures, 1):
            md += f"""### 失败 #{i} — 执行 #{f['execution_id']}

- **设备**: {f['device']}
- **账号**: {f['account']}
- **失败步骤**: {f['failed_step']}
- **错误信息**: `{f['error']}`
- **发生时间**: {f['time']}
- **根因分析**: {f['root_cause']}

"""

    md += f"\n---\n*报告生成时间: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')} | 数据来源: GAF 执行引擎*\n"
    return md


def _detect_anomalies(executions):
    """基于执行数据检测异常模式"""
    anomalies = []
    total = executions.count()
    failed = executions.filter(status='failed').count()
    if total > 0 and failed / total >= 0.3:
        anomalies.append({
            'type': 'consecutive_failures',
            'description': f'全局失败率偏高 ({round(failed/total*100, 1)}%)，建议检查系统状态',
            'severity': 'critical',
            'affected_executions': list(executions.filter(status='failed').values_list('id', flat=True)[:3]),
        })
    return anomalies


@extend_schema(
    tags=['executions'],
    summary='Unattended mode logs grouped by device/account',
    responses={200: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter('date', OpenApiTypes.STR, description='Filter logs by date (YYYY-MM-DD).'),
        OpenApiParameter('level', OpenApiTypes.STR, description='Filter by log level (INFO/WARNING/ERROR).'),
        OpenApiParameter('search', OpenApiTypes.STR, description='Search keyword within action_taken.'),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission('view')
def unattended_logs_view(request):
    """
    获取无人值守模式的专用日志

    从 RecoveryLog 表查询恢复操作日志。Admin 看全部日志；其他用户仅看与自己相关的日志。
    """
    # @api_view allowed: custom grouping/aggregation over RecoveryLog, not model CRUD
    date_param = request.query_params.get('date')
    level_filter = request.query_params.get('level')
    search_param = request.query_params.get('search')

    logs_qs = RecoveryLog.objects.all()
    # Non-admin users only see logs whose details.account matches their username
    if request.user.role != 'admin':
        logs_qs = logs_qs.filter(details__account=request.user.username)

    if date_param:
        try:
            report_dt = datetime.strptime(date_param, '%Y-%m-%d')
            tz_now = timezone.now()
            day_start = tz_now.replace(
                year=report_dt.year, month=report_dt.month, day=report_dt.day,
                hour=0, minute=0, second=0, microsecond=0,
            )
            day_end = day_start + timedelta(days=1)
            logs_qs = logs_qs.filter(created_at__gte=day_start, created_at__lt=day_end)
        except ValueError:
            pass

    if search_param:
        logs_qs = logs_qs.filter(action_taken__icontains=search_param)

    all_logs = []
    for log in logs_qs.order_by('-created_at'):
        level = 'ERROR' if not log.success else 'INFO'
        if log.recovery_level in ('device', 'system'):
            level = 'WARNING' if log.success else 'ERROR'

        if level_filter and level_filter.upper() != level:
            continue

        all_logs.append({
            'id': log.id,
            'timestamp': log.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'device_name': log.details.get('device', ''),
            'account_alias': log.details.get('account', ''),
            'event_type': log.trigger_event,
            'level': level,
            'message': f'{log.trigger_event} → {log.action_taken}',
            'details': log.details,
        })

    grouped = defaultdict(list)
    for log in all_logs:
        key = f"{log['device_name']} / {log['account_alias']}"
        grouped[key].append(log)

    grouped_result = []
    for group_key, logs in grouped.items():
        device, account = group_key.split(' / ')
        error_count = sum(1 for log in logs if log['level'] == 'ERROR')
        warning_count = sum(1 for log in logs if log['level'] == 'WARNING')
        grouped_result.append({
            'device_name': device,
            'account_alias': account,
            'log_count': len(logs),
            'error_count': error_count,
            'warning_count': warning_count,
            'logs': logs,
        })

    event_type_summary = defaultdict(int)
    for log in all_logs:
        event_type_summary[log['event_type']] += 1

    return Response({
        'date': date_param or timezone.now().strftime('%Y-%m-%d'),
        'filters_applied': {
            'date': date_param or '(默认今天)',
            'level': level_filter or '(全部)',
            'search': search_param or '(无)',
        },
        'total_logs': len(all_logs),
        'grouped_by_device_account': grouped_result,
        'event_type_summary': dict(event_type_summary),
        'level_summary': {
            'INFO': sum(1 for log in all_logs if log['level'] == 'INFO'),
            'WARNING': sum(1 for log in all_logs if log['level'] == 'WARNING'),
            'ERROR': sum(1 for log in all_logs if log['level'] == 'ERROR'),
        },
    })


@extend_schema(
    tags=['analytics'],
    summary='7-day execution trend aggregation',
    responses={200: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter('days', OpenApiTypes.INT, description='Aggregation window in days (default 7).'),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission('view')
def trend_view(request):
    """
    7 日执行趋势数据 API。

    GET /api/analytics/trend/?days=7
    从 TaskExecution 表按日期聚合执行量、成功率、平均耗时趋势。
    """
    # @api_view allowed: analytics time-series aggregation, not model CRUD
    days = int(request.query_params.get('days', '7').rstrip('/'))
    today = timezone.now().date()
    cutoff = today - timedelta(days=days)

    daily_stats = defaultdict(lambda: {'count': 0, 'success': 0, 'duration_total': 0, 'duration_count': 0})
    executions = TaskExecution.objects.filter(created_at__date__gte=cutoff)

    for ex in executions:
        d = ex.created_at.strftime('%Y-%m-%d')
        daily_stats[d]['count'] += 1
        if ex.status == 'success':
            daily_stats[d]['success'] += 1
        if ex.duration:
            daily_stats[d]['duration_total'] += ex.duration.total_seconds()
            daily_stats[d]['duration_count'] += 1

    trend_data = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        stats = daily_stats.get(d, {'count': 0, 'success': 0, 'duration_total': 0, 'duration_count': 0})
        cnt = stats['count']
        trend_data.append({
            'date': d,
            'execution_count': cnt,
            'success_rate': round(stats['success'] / cnt * 100, 1) if cnt else 0,
            'avg_duration': round(stats['duration_total'] / stats['duration_count'], 1) if stats['duration_count'] else 0,
        })

    return Response({
        'days': days,
        'period_start': (today - timedelta(days=days - 1)).isoformat(),
        'period_end': today.isoformat(),
        'trend': trend_data,
    })


@extend_schema(
    tags=['analytics'],
    summary='Step-level heatmap data (avg duration and success rate)',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission('view')
def step_heatmap_view(request):
    """
    步骤级热力图数据 API

    GET /api/v2/analytics/step-heatmap/
    返回每个步骤名称的平均耗时和成功率，用于热力图展示
    """
    # @api_view allowed: analytics aggregation over ExecutionStep, not model CRUD
    from django.db.models import Avg, Count, Q

    steps = ExecutionStep.objects.values('step_name').annotate(
        total=Count('id'),
        success_count=Count('id', filter=Q(status='success')),
        avg_duration=Avg('duration'),
    ).order_by('-total')[:20]

    result = []
    for s in steps:
        name = s['step_name'] or 'unknown'
        result.append({
            'step_name': name,
            'total': s['total'],
            'success_rate': round(s['success_count'] / s['total'] * 100, 1) if s['total'] else 0,
            'avg_duration': round(s['avg_duration'], 2) if s['avg_duration'] else 0,
        })

    return Response({'results': result})


@extend_schema(
    tags=['analytics'],
    summary='Agent performance statistics',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission('view')
def agent_performance_view(request):
    """
    Agent 性能数据 API

    GET /api/v2/analytics/agent-performance/
    返回每个 Agent 的执行统计
    """
    # @api_view allowed: cross-model analytics (Agent + TaskExecution), not model CRUD
    from workers.models import Worker

    # 修复: 获取所有 Agent，不过滤 status 以显示全部
    agents = Worker.objects.all().prefetch_related('devices')[:10]
    result = []

    for agent in agents:
        executions = TaskExecution.objects.filter(agent_id=agent.id)
        total = executions.count()
        success = executions.filter(status='success').count()

        # 修复: Agent 没有直接 device 字段，通过 devices 反向查询
        device_name = 'unknown'
        if hasattr(agent, 'devices') and agent.devices.exists():
            device_name = agent.devices.first().name

        result.append({
            'agent_id': agent.id,
            'agent_name': agent.hostname,
            'device_name': device_name,
            'total_executions': total,
            'success_rate': round(success / total * 100, 1) if total else 0,
            'last_seen': agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
        })

    return Response({'results': result})


@extend_schema(
    tags=['analytics'],
    summary='Weekly execution report',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission('view')
def weekly_report_view(request):
    """
    每周执行报告 API

    GET /api/v2/analytics/weekly-report/
    返回本周的执行摘要
    """
    # @api_view allowed: analytics weekly aggregation, not model CRUD
    today = timezone.now().date()
    week_start = today - timedelta(days=today.weekday())

    week_executions = TaskExecution.objects.filter(
        created_at__date__gte=week_start,
        created_at__date__lte=today,
    )

    total = week_executions.count()
    success = week_executions.filter(status='success').count()
    failed = week_executions.filter(status='failed').count()

    daily_breakdown = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        if d > today:
            break
        day_exec = week_executions.filter(created_at__date=d)
        day_total = day_exec.count()
        day_success = day_exec.filter(status='success').count()
        daily_breakdown.append({
            'date': d.isoformat(),
            'weekday': ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][i],
            'total': day_total,
            'success': day_success,
            'failed': day_total - day_success,
        })

    # TD-389: 补充前端 WeeklyReport 期望的扁平字段 + 恢复(recovery)指标
    most_run = (
        week_executions.values('task__name')
        .annotate(count=Count('id'))
        .order_by('-count')
        .first()
    )
    raw_avg = ExecutionStep.objects.filter(
        task_result__created_at__date__gte=week_start,
        task_result__created_at__date__lte=today,
        status='success',
    ).aggregate(avg=Avg('duration'))['avg']
    if raw_avg is None:
        avg_step_ms = 0.0
    elif isinstance(raw_avg, timedelta):
        avg_step_ms = raw_avg.total_seconds() * 1000
    else:
        # SQLite 存储 DurationField 为微秒浮点
        avg_step_ms = float(raw_avg) / 1000
    recovery_triggered = week_executions.filter(recovery_attempts__gt=0).count()
    avg_recovery = week_executions.aggregate(avg=Avg('recovery_attempts'))['avg'] or 0
    recovered_ok = week_executions.filter(
        recovery_attempts__gt=0, status='success'
    ).count()
    recovery_success_rate = (
        round(recovered_ok / recovery_triggered * 100, 1) if recovery_triggered else None
    )

    return Response({
        'week_start': week_start.isoformat(),
        'week_end': today.isoformat(),
        'summary': {
            'total': total,
            'success': success,
            'failed': failed,
            'success_rate': round(success / total * 100, 1) if total else 0,
        },
        'daily_breakdown': daily_breakdown,
        # 扁平字段（与前端 WeeklyReport 接口对齐，修复此前取值为 undefined 的问题）
        'total_executions': total,
        'success_count': success,
        'failed_count': failed,
        'success_rate': round(success / total * 100, 1) if total else 0,
        'most_executed_task': most_run['task__name'] if most_run else '',
        'avg_step_duration_ms': round(avg_step_ms, 1),
        'recovery_triggered_count': recovery_triggered,
        'avg_recovery_attempts': round(avg_recovery, 2),
        'recovery_success_rate': recovery_success_rate,
    })


@extend_schema(
    tags=['analytics'],
    summary='Task-level aggregated statistics',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission('view')
def task_stats_view(request):
    """
    任务统计数据 API

    GET /api/v2/analytics/task-stats/
    返回任务级别的聚合统计
    """
    # @api_view allowed: cross-model analytics (Task + TaskExecution), not model CRUD
    from tasks.models import Task

    tasks = Task.objects.all()[:20]
    result = []

    for task in tasks:
        execs = TaskExecution.objects.filter(task_id=task.id)
        total = execs.count()
        success = execs.filter(status='success').count()

        recovery_triggered = execs.filter(recovery_attempts__gt=0).count()
        avg_recovery = execs.aggregate(avg=Avg('recovery_attempts'))['avg'] or 0
        recovered_ok = execs.filter(recovery_attempts__gt=0, status='success').count()
        recovery_success_rate = (
            round(recovered_ok / recovery_triggered * 100, 1) if recovery_triggered else None
        )

        result.append({
            'task_id': task.id,
            'task_name': task.name,
            'mode': getattr(task, 'task_type', 'manual') or 'manual',  # 修复: 使用 task_type 或默认值
            'is_enabled': getattr(task, 'is_enabled', True),
            'total_executions': total,
            'success_rate': round(success / total * 100, 1) if total else 0,
            'recovery_triggered_count': recovery_triggered,
            'avg_recovery_attempts': round(avg_recovery, 2),
            'recovery_success_rate': recovery_success_rate,
            'last_execution': execs.order_by('-created_at').first().created_at.isoformat() if execs.exists() else None,
        })

    return Response({'results': result})


@extend_schema(
    tags=['executions', 'ai'],
    summary='AI-analyze an execution record (step timeline + failure diagnosis)',
    responses={200: OpenApiTypes.OBJECT, 403: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated, RoleBasedPermission])
@require_permission('view')
def execution_analysis_view(request, pk):
    """
    AI 分析指定执行记录

    拉取 TaskExecution + ExecutionStep 列表，构建 prompt 调 LLM 生成分析摘要和修复建议。
    返回结构匹配前端 LogAnalysisResult 接口：
    {steps: [{name, status, duration_ms, error?}], summary: string, suggestions: string[]}

    spec 阶段 3.4: 如果 execution_snapshot.structured_log_path 指向的 JSONL 文件
    存在（本地开发场景 agent 和 backend 同机器），读取结构化日志加入 prompt，
    让 LLM 能基于 confidence/threshold/roi/screenshot_path 做精确诊断。
    """
    # @api_view allowed: AI analysis aggregation over TaskExecution + ExecutionStep, not model CRUD
    try:
        execution = TaskExecution.objects.get(pk=pk)
    except TaskExecution.DoesNotExist:
        return Response(
            {'error': f'执行记录 #{pk} 不存在'},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Non-admin users can only analyze their own executions
    if request.user.role != 'admin' and execution.triggered_by_id != request.user.id:
        return Response(
            {'error': '无权分析此执行记录'},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Pull steps ordered by step_index
    steps_qs = ExecutionStep.objects.filter(task_result_id=pk).order_by('step_index')

    # Build steps payload matching frontend LogAnalysisResult.steps
    steps = []
    for s in steps_qs:
        duration_ms = int(s.duration * 1000) if s.duration else 0
        steps.append({
            'name': s.step_name,
            'status': s.status,
            'duration_ms': duration_ms,
            'error': s.error_message or None,
        })

    # Read structured JSONL log if available (spec 阶段 3.4).
    # The path is stored by agents/consumers.py:_finalize_execution when
    # the agent reports task.result with structured_log_path. Only readable
    # when agent and backend share a filesystem (local dev scenario).
    structured_log_summary = ''
    structured_log_path = ''
    snapshot = execution.execution_snapshot if isinstance(execution.execution_snapshot, dict) else {}
    structured_log_path = snapshot.get('structured_log_path', '')
    if structured_log_path:
        structured_log_summary = _read_structured_log(structured_log_path)

    # If no steps AND no structured log, return early with a friendly message.
    if not steps and not structured_log_summary:
        return Response({
            'steps': [],
            'summary': f'执行记录 #{pk} 无步骤数据且无结构化日志，无法进行 AI 分析。',
            'suggestions': [],
            'structured_log_path': structured_log_path,
            'structured_log_available': False,
        })

    # Build analysis prompt (include structured log summary when available)
    prompt = _build_analysis_prompt(execution, steps, structured_log_summary)

    # Call LLM via the 4-level fallback router
    summary = ''
    suggestions: list[str] = []
    try:
        from gaf_ai.llm_service import call_llm

        llm_response = call_llm(
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'You are a game automation log analyzer. Analyze the execution '
                        'record and respond in Chinese. Return ONLY a JSON object with '
                        'keys "summary" (string) and "suggestions" (array of strings). '
                        'No markdown fences, no extra text.'
                    ),
                },
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.3,
            max_tokens=1024,
        )

        content = llm_response.get('content', '')
        if llm_response.get('route') == 'failed' or not content:
            logger.warning('execution_analysis LLM failed: %s', llm_response.get('error', 'no content'))
            summary = 'LLM 分析失败，请检查 LLM 配置后重试。'
        else:
            summary, suggestions = _parse_llm_analysis(content)

    except Exception as exc:
        logger.exception('execution_analysis_view LLM call failed for execution #%s: %s', pk, exc)
        summary = f'LLM 分析异常: {exc}。步骤数据已返回，可手动查看。'

    return Response({
        'steps': steps,
        'summary': summary,
        'suggestions': suggestions,
        'structured_log_path': structured_log_path,
        'structured_log_available': bool(structured_log_summary),
    })


def _read_structured_log(path: str) -> str:
    """Read and summarize a structured JSONL log file (spec 阶段 3.4).

    Parses each line as JSON and formats a compact summary for the LLM
    prompt. Failed nodes get full detail (confidence/threshold/roi/
    screenshot_path/error_msg); successful nodes get a one-liner.

    Args:
        path: Absolute path to the JSONL file on the backend host.

    Returns:
        Formatted summary string. Empty string if the file cannot be
        read (missing/inaccessible/invalid). Total length is capped at
        ~8000 chars to keep the LLM prompt within budget.
    """
    import json
    import os

    if not path or not os.path.isfile(path):
        return ''

    max_chars = 8000
    lines_out: list[str] = []
    total_chars = 0
    failed_count = 0
    success_count = 0

    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                success = entry.get('success', False)
                if success:
                    success_count += 1
                    # One-liner for successful nodes
                    node_id = entry.get('node_id', '?')
                    node_type = entry.get('node_type', '?')
                    elapsed_ms = entry.get('elapsed_ms', 0)
                    formatted = f"  ✅ step={entry.get('step_index', '?')} {node_type}({node_id}) {elapsed_ms}ms"
                else:
                    failed_count += 1
                    # Full detail for failed nodes
                    node_id = entry.get('node_id', '?')
                    node_type = entry.get('node_type', '?')
                    elapsed_ms = entry.get('elapsed_ms', 0)
                    confidence = entry.get('confidence')
                    threshold = entry.get('threshold')
                    roi = entry.get('roi_physical')
                    screenshot = entry.get('screenshot_path', '')
                    error_msg = entry.get('error_msg', '')
                    auto_heal = entry.get('auto_heal_attempts', [])

                    formatted = f"  ❌ step={entry.get('step_index', '?')} {node_type}({node_id}) {elapsed_ms}ms"
                    if confidence is not None:
                        formatted += f" confidence={confidence}"
                    if threshold is not None:
                        formatted += f" threshold={threshold}"
                    if roi:
                        formatted += f" roi={roi}"
                    if auto_heal:
                        formatted += f" auto_heal={auto_heal}"
                    if screenshot:
                        formatted += f" screenshot={screenshot}"
                    if error_msg:
                        formatted += f"\n     error: {error_msg[:300]}"

                if total_chars + len(formatted) > max_chars:
                    lines_out.append(f"  [日志已截断，共 {failed_count} 失败 / {success_count} 成功节点]")
                    break
                lines_out.append(formatted)
                total_chars += len(formatted) + 1

    except OSError as exc:
        logger.warning('Failed to read structured log %s: %s', path, exc)
        return ''

    if not lines_out:
        return ''

    header = (
        f'## 结构化日志摘要 (JSONL, {failed_count} 失败 / {success_count} 成功)\n'
        f'来源: {path}\n'
    )
    return header + '\n'.join(lines_out)


def _build_analysis_prompt(execution: TaskExecution, steps: list[dict], structured_log_summary: str = '') -> str:
    """Build the LLM analysis prompt from execution + steps data.

    Args:
        execution: TaskExecution instance.
        steps: List of step dicts {name, status, duration_ms, error}.
        structured_log_summary: Optional structured JSONL log summary
            (spec 阶段 3.4). When non-empty, appended to the prompt so
            the LLM can reason about confidence/threshold/roi/screenshot_path.
    """
    lines = [
        '# 执行记录分析',
        '',
        '## 执行概览',
        f'- 执行 ID: {execution.id}',
        f'- 任务名: {execution.task.name if execution.task else "未知"}',
        f'- 执行状态: {execution.status}',
        f'- 开始时间: {execution.started_at.isoformat() if execution.started_at else "未开始"}',
        f'- 完成时间: {execution.completed_at.isoformat() if execution.completed_at else "未完成"}',
    ]

    if execution.duration:
        lines.append(f'- 总耗时: {execution.duration.total_seconds():.1f}s')
    else:
        lines.append('- 总耗时: 未知')

    last_err = execution.error_message or '无'
    lines.append(f'- 最近错误: {last_err}')
    lines.append('')

    if steps:
        lines.append(f'## 步骤时间线 ({len(steps)} 步)')
        for i, step in enumerate(steps, 1):
            duration_s = step['duration_ms'] / 1000
            status_icon = {'success': '✅', 'failed': '❌', 'running': '🔄', 'pending': '⏳'}.get(step['status'], '⚪')
            lines.append(f'{i}. {status_icon} {step["name"]} [{step["status"]}] ({duration_s:.1f}s)')
            if step.get('error'):
                lines.append(f'   错误: {step["error"][:200]}')

        # Highlight failed steps
        failed_steps = [s for s in steps if s['status'] == 'failed']
        if failed_steps:
            lines.append('')
            lines.append(f'## 失败步骤 ({len(failed_steps)} 个)')
            for fs in failed_steps:
                lines.append(f'- {fs["name"]}: {fs.get("error", "无错误信息")}')

    # Structured JSONL log summary (spec 阶段 3.4) — contains per-node
    # confidence/threshold/roi/screenshot_path/error_msg/auto_heal_attempts.
    # This is the key data source for LLM diagnosis of template_match
    # failures (e.g. "confidence 0.72 < threshold 0.8 → template not found").
    if structured_log_summary:
        lines.append('')
        lines.append(structured_log_summary)

    lines.append('')
    lines.append('## 请分析')
    lines.append('1. 总结执行情况（哪些步骤正常，哪些异常）')
    lines.append('2. 如有结构化日志，结合 confidence/threshold 分析失败原因')
    lines.append('3. 给出可操作的修复建议')
    lines.append('')
    lines.append('返回 JSON: {"summary": "...", "suggestions": ["...", "..."]}')

    return '\n'.join(lines)


def _parse_llm_analysis(content: str) -> tuple[str, list[str]]:
    """Parse LLM response into (summary, suggestions). Falls back gracefully."""
    import json

    # Strip markdown fences if present
    text = content.strip()
    if text.startswith('```'):
        # Remove opening fence (```json or ```)
        first_newline = text.find('\n')
        if first_newline != -1:
            text = text[first_newline + 1:]
        # Remove closing fence
        if text.rstrip().endswith('```'):
            text = text.rstrip()[:-3].rstrip()

    try:
        parsed = json.loads(text)
        summary = str(parsed.get('summary', '')).strip()
        suggestions_raw = parsed.get('suggestions', [])
        suggestions = (
            [str(s) for s in suggestions_raw]
            if isinstance(suggestions_raw, list)
            else [str(suggestions_raw)]
        )
        return summary or '分析完成，但未返回摘要。', suggestions
    except (json.JSONDecodeError, TypeError):
        # Fallback: use raw content as summary, no suggestions
        logger.warning('Failed to parse LLM analysis as JSON, using raw content as summary')
        return content.strip()[:500], []
