"""事件总线 — 跨进程监控事件分发。

Task 3.1 (2026-08-08): 提供 ``EventBus`` 类，将 ``MonitoringEvent``
通过 WebSocket Channels 广播到 Dashboard 前端，并可选持久化到
``models.MonitorEvent``。

Usage::

    from monitors.bus import EventBus
    from monitors.events import MonitoringEvent

    # 创建并广播事件
    event = MonitoringEvent.error(
        source="agent", category="resource",
        message="CPU usage exceeded 90%",
        device_id=5, cpu_usage=95,
    )
    EventBus.broadcast(event)  # 同步广播 (DRF view / Celery task)
    await EventBus.async_broadcast(event)  # 异步广播 (Channels consumer)
"""

from __future__ import annotations

import logging
from typing import Any

from monitors.events import MonitoringEvent
from protocol.broadcast import async_broadcast_to_dashboard, broadcast_to_dashboard

logger = logging.getLogger(__name__)

# Channels event type used for monitoring events on the dashboard group.
_MONITOR_EVENT_TYPE = "monitor.event"


class EventBus:
    """跨进程事件总线 — 广播 ``MonitoringEvent`` 到 Dashboard。

    所有方法均为类方法/静态方法，无需实例化。
    """

    @staticmethod
    def broadcast(
        event: MonitoringEvent,
        persist: bool = False,
        **kwargs: Any,
    ) -> None:
        """同步广播监控事件到 Dashboard。

        Args:
            event: ``MonitoringEvent`` 实例。
            persist: 是否同时持久化到数据库 (``models.MonitorEvent``)。
            **kwargs: 传递给 ``broadcast_to_dashboard`` 的额外参数。
        """
        payload = event.to_broadcast_payload()
        broadcast_to_dashboard(
            _MONITOR_EVENT_TYPE,
            payload,
            trace_id=event.trace_id or None,
            **kwargs,
        )
        logger.debug(
            "EventBus broadcast: %s/%s [%s] %s",
            event.source, event.category, event.level,
            event.payload.get("message", ""),
        )

        if persist:
            _persist_event(event)

    @staticmethod
    async def async_broadcast(
        event: MonitoringEvent,
        persist: bool = False,
        **kwargs: Any,
    ) -> None:
        """异步广播监控事件到 Dashboard (Channels consumer 中使用)。

        Args:
            event: ``MonitoringEvent`` 实例。
            persist: 是否同时持久化到数据库。
            **kwargs: 传递给 ``async_broadcast_to_dashboard`` 的额外参数。
        """
        payload = event.to_broadcast_payload()
        await async_broadcast_to_dashboard(
            _MONITOR_EVENT_TYPE,
            payload,
            trace_id=event.trace_id or None,
            **kwargs,
        )
        logger.debug(
            "EventBus async_broadcast: %s/%s [%s] %s",
            event.source, event.category, event.level,
            event.payload.get("message", ""),
        )

        if persist:
            await _async_persist_event(event)


# ── Persistence helpers ───────────────────────────────────────────────

def _persist_event(event: MonitoringEvent) -> None:
    """将 ``MonitoringEvent`` 持久化到 ``models.MonitorEvent``。

    Args:
        event: 监控事件实例。
    """
    from monitors.models import MonitorEvent

    try:
        MonitorEvent.objects.create(
            event_type=f"{event.source}.{event.category}",
            severity=_map_level_to_severity(event.level),
            handling_result=event.payload.get("message", ""),
            event_data=event.payload,
        )
    except Exception as exc:
        logger.warning("Failed to persist MonitoringEvent: %s", exc)


async def _async_persist_event(event: MonitoringEvent) -> None:
    """异步版本，使用 ``database_sync_to_async`` 持久化。"""
    from channels.db import database_sync_to_async

    await database_sync_to_async(_persist_event)(event)


def _map_level_to_severity(level: str) -> str:
    """将 EventLevel 映射到 ``MonitorEvent.Severity``。

    Args:
        level: EventLevel 值 (INFO / WARNING / ERROR / CRITICAL)。

    Returns:
        MonitorEvent.Severity 枚举值 (P0 / P1 / P2 / P3)。
    """
    mapping = {
        "CRITICAL": "P0",
        "ERROR": "P1",
        "WARNING": "P2",
        "INFO": "P3",
    }
    return mapping.get(level, "P3")
