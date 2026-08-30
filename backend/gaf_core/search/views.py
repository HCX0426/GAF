"""
全局搜索 API

跨模块全文搜索，搜索范围包含：
- 任务（Task）
- 设备（Device）
- 账户（GameAccount）
- 执行日志（RecoveryLog）
- 设置项（UnattendedStrategy）
"""


import logging

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def _search_tasks(keyword: str, limit: int) -> list:
    """搜索任务名称。"""
    try:
        from tasks.models import Task

        queryset = Task.objects.filter(name__icontains=keyword)[:limit]
        return [
            {
                'id': t.id,
                'title': t.name,
                'subtitle': '任务',
                'tag': t.get_task_type_display() if hasattr(t, 'get_task_type_display') else '任务',
                'tagColor': 'blue',
                'url': f'/tasks/{t.id}',
                'icon': 'task',
            }
            for t in queryset
        ]
    except Exception:
        logger.warning("search: _search_tasks failed (keyword=%r, limit=%s)", keyword, limit, exc_info=True)
        return []


def _search_devices(keyword: str, limit: int) -> list:
    """搜索设备名称。"""
    try:
        from workers.models import Device

        queryset = Device.objects.filter(name__icontains=keyword)[:limit]
        return [
            {
                'id': d.id,
                'title': d.name,
                'subtitle': f'设备 | {d.device_type or "通用"}',
                'tag': '在线' if getattr(d, 'is_online', False) else '离线',
                'tagColor': 'green' if getattr(d, 'is_online', False) else 'default',
                'url': f'/devices/{d.id}',
                'icon': 'device',
            }
            for d in queryset
        ]
    except Exception:
        logger.warning("search: _search_devices failed (keyword=%r, limit=%s)", keyword, limit, exc_info=True)
        return []


def _search_accounts(keyword: str, limit: int) -> list:
    """搜索账户名称。"""
    try:
        from accounts.models import GameAccount

        queryset = GameAccount.objects.filter(
            Q(username__icontains=keyword) | Q(game_name__icontains=keyword)
        )[:limit]
        return [
            {
                'id': a.id,
                'title': a.username,
                'subtitle': f'游戏: {a.game_name} | {a.server_region}',
                'tag': a.status,
                'tagColor': 'green' if a.status == 'ok' else 'orange' if a.status == 'warn' else 'red',
                'url': f'/accounts/{a.id}',
                'icon': 'account',
            }
            for a in queryset
        ]
    except Exception:
        logger.warning("search: _search_accounts failed (keyword=%r, limit=%s)", keyword, limit, exc_info=True)
        return []


def _search_recovery_logs(keyword: str, limit: int) -> list:
    """搜索恢复日志。"""
    try:
        from scheduler.models import RecoveryLog

        queryset = RecoveryLog.objects.filter(
            Q(trigger_event__icontains=keyword) | Q(action_taken__icontains=keyword)
        )[:limit]
        return [
            {
                'id': r.id,
                'title': r.trigger_event[:50],
                'subtitle': f'{r.get_recovery_level_display()} → {r.action_taken}',
                'tag': '成功' if r.success else '失败',
                'tagColor': 'green' if r.success else 'red',
                'url': f'/logs/{r.id}',
                'icon': 'log',
            }
            for r in queryset
        ]
    except Exception:
        logger.warning("search: _search_recovery_logs failed (keyword=%r, limit=%s)", keyword, limit, exc_info=True)
        return []


def _search_settings(keyword: str, limit: int) -> list:
    """搜索设置项。"""
    try:
        from settings.models import UnattendedStrategy

        strategy = UnattendedStrategy.objects.first()
        if not strategy:
            return []

        searchable_keys = [
            ('恢复策略', '恢复策略配置 — 无人值守异常恢复'),
            ('夜间模式', '夜间模式配置 — 低功耗降频策略'),
            ('频率限制', '频率限制配置 — 执行频率与每日上限'),
            ('通知策略', '通知策略配置 — 异常事件推送通知'),
            ('冷却时间', '冷却时间配置 — 重启与切换间隔'),
        ]

        results = []
        for key, desc in searchable_keys:
            if keyword.lower() in key.lower() or keyword.lower() in desc.lower():
                results.append({
                    'id': key,
                    'title': key,
                    'subtitle': desc,
                    'tag': '设置项',
                    'tagColor': 'purple',
                    'url': '/settings/unattended-strategy',
                    'icon': 'setting',
                })
        return results[:limit]
    except Exception:
        logger.warning("search: _search_settings failed (keyword=%r, limit=%s)", keyword, limit, exc_info=True)
        return []


@extend_schema(
    tags=['search'],
    summary='Global cross-module search',
    responses={200: OpenApiTypes.OBJECT},
    parameters=[
        OpenApiParameter(
            name='q',
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description='Search keyword',
            required=True,
        ),
        OpenApiParameter(
            name='limit',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Per-category result cap (legacy alias)',
        ),
        OpenApiParameter(
            name='page_size',
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description='Per-category result cap (preferred)',
        ),
    ],
)
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def global_search_view(request):
    """
    全局搜索 API。

    GET /api/search/?q=keyword&limit=5
    跨 5 个模块并行搜索，返回分组结果。
    """
    # @api_view allowed: cross-module search (Task + Device + GameAccount + RecoveryLog + UnattendedStrategy)
    keyword = request.query_params.get('q', '').strip()
    if not keyword:
        return Response({
            'query': '',
            'totalCount': 0,
            'tasks': [],
            'devices': [],
            'accounts': [],
            'logs': [],
            'settings': [],
        })

    # A026 fix: accept both `limit` (legacy) and `page_size` (per spec §3).
    # The global search endpoint is an aggregate (not a paginated list), so
    # `page_size` here acts as a per-category result cap, not true pagination.
    limit = int(request.query_params.get('page_size', request.query_params.get('limit', 5)))

    tasks = _search_tasks(keyword, limit)
    devices = _search_devices(keyword, limit)
    accounts = _search_accounts(keyword, limit)
    logs = _search_recovery_logs(keyword, limit)
    settings_items = _search_settings(keyword, limit)

    total = sum(len(r) for r in [tasks, devices, accounts, logs, settings_items])

    return Response({
        'query': keyword,
        'totalCount': total,
        'tasks': tasks,
        'devices': devices,
        'accounts': accounts,
        'logs': logs,
        'settings': settings_items,
    })
