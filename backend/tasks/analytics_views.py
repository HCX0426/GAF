"""
性能分析 API — 任务统计、步骤热力图、趋势图、周报
"""
from datetime import timedelta

from django.db.models import Avg, Count
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from tasks.models import ExecutionStep, TaskExecution


@extend_schema(
    tags=['analytics'],
    summary='Task-level statistics aggregation',
    responses={200: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter('days', OpenApiTypes.INT, description='Aggregation window in days (default 30).'),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def task_stats(request):
    """任务级统计"""
    # @api_view allowed: analytics aggregation over TaskExecution, not model CRUD
    days = int(request.GET.get('days', 30))
    since = timezone.now() - timedelta(days=days)
    executions = TaskExecution.objects.filter(started_at__gte=since)

    total = executions.count()
    completed = executions.filter(status=TaskExecution.Status.SUCCESS).count()
    failed = executions.filter(status='failed').count()

    success_rate = round(completed / total * 100, 1) if total > 0 else 0

    avg_duration = 0
    completed_execs = executions.filter(status=TaskExecution.Status.SUCCESS, completed_at__isnull=False, started_at__isnull=False)
    if completed_execs.exists():
        total_seconds = sum(
            (e.completed_at - e.started_at).total_seconds()
            for e in completed_execs
        )
        avg_duration = round(total_seconds / completed_execs.count(), 1)

    common_errors = (
        executions.filter(status='failed')
        .exclude(error_message='')
        .values('error_message')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )

    return Response({
        'total': total,
        'completed': completed,
        'failed': failed,
        'running': executions.filter(status='running').count(),
        'success_rate': success_rate,
        'avg_duration_seconds': avg_duration,
        'period_days': days,
        'common_errors': list(common_errors),
    })


@extend_schema(
    tags=['analytics'],
    summary='Step duration heatmap data',
    responses={200: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter('days', OpenApiTypes.INT, description='Aggregation window in days (default 7).'),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def step_heatmap(request):
    """步骤耗时热力图数据"""
    # @api_view allowed: analytics aggregation over ExecutionStep, not model CRUD
    days = int(request.GET.get('days', 7))
    since = timezone.now() - timedelta(days=days)
    steps = ExecutionStep.objects.filter(
        task_result__started_at__gte=since,
        status=ExecutionStep.Status.SUCCESS,
        duration__gt=0,
    )

    step_data = steps.values('step_type').annotate(
        avg_duration=Avg('duration'),
        count=Count('id'),
    ).order_by('-avg_duration')

    return Response({
        'steps': list(step_data),
        'period_days': days,
    })


@extend_schema(
    tags=['analytics'],
    summary='Execution trend by day',
    responses={200: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter('days', OpenApiTypes.INT, description='Aggregation window in days (default 30).'),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def trend(request):
    """执行趋势（按天聚合）"""
    # @api_view allowed: time-series analytics aggregation, not model CRUD
    days = int(request.GET.get('days', 30))
    since = timezone.now() - timedelta(days=days)
    executions = TaskExecution.objects.filter(started_at__gte=since)

    trend_data = []
    for i in range(days):
        day = since + timedelta(days=i)
        next_day = day + timedelta(days=1)
        day_execs = executions.filter(started_at__gte=day, started_at__lt=next_day)
        total = day_execs.count()
        completed = day_execs.filter(status=TaskExecution.Status.SUCCESS).count()
        trend_data.append({
            'date': day.strftime('%Y-%m-%d'),
            'total': total,
            'completed': completed,
            'failed': day_execs.filter(status='failed').count(),
            'success_rate': round(completed / total * 100, 1) if total > 0 else 0,
        })

    return Response({'trend': trend_data, 'period_days': days})


@extend_schema(
    tags=['analytics'],
    summary='Auto-generated weekly report',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def weekly_report(request):
    """自动周报生成"""
    # @api_view allowed: weekly analytics aggregation across TaskExecution + ExecutionStep
    since = timezone.now() - timedelta(days=7)
    executions = TaskExecution.objects.filter(started_at__gte=since)

    total = executions.count()
    completed = executions.filter(status=TaskExecution.Status.SUCCESS).count()
    failed = executions.filter(status='failed').count()

    avg_duration = 0
    completed_execs = executions.filter(status=TaskExecution.Status.SUCCESS, completed_at__isnull=False, started_at__isnull=False)
    if completed_execs.exists():
        avg_duration = round(
            sum((e.completed_at - e.started_at).total_seconds() for e in completed_execs) / completed_execs.count(), 1
        )

    most_run_task = (
        executions.values('task__name')
        .annotate(count=Count('id'))
        .order_by('-count')
        .first()
    )

    steps = ExecutionStep.objects.filter(task_result__started_at__gte=since, status=ExecutionStep.Status.SUCCESS, duration__gt=0)
    avg_step = steps.aggregate(avg=Avg('duration'))['avg'] or 0

    return Response({
        'period': f"{since.strftime('%Y-%m-%d')} ~ {timezone.now().strftime('%Y-%m-%d')}",
        'total_executions': total,
        'completed': completed,
        'failed': failed,
        'success_rate': round(completed / total * 100, 1) if total > 0 else 0,
        'avg_duration_seconds': avg_duration,
        'avg_step_duration_ms': round(avg_step, 1),
        'most_run_task': most_run_task['task__name'] if most_run_task else '',
    })
