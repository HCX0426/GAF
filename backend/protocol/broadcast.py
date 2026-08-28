"""Broadcast helpers for Channels group_send with trace_id injection.

F37 (spec 2026-07-30-debug-directory-restructure): All ``channel_layer.group_send``
calls to ``DASHBOARD_GROUP`` should go through this helper so the event payload
carries an explicit ``trace_id`` field. Per-event trace_id is the primary mechanism;
per-connection ``TracingChannelsMiddleware`` (F25) serves only as a fallback.

Usage::

    from protocol.broadcast import broadcast_to_dashboard

    # From a sync context (DRF view, Celery task, etc.)
    broadcast_to_dashboard("task.progress", {"execution_id": "exec-123"})

    # From an async context (Channels consumer)
    await broadcast_to_dashboard("task.progress", {"execution_id": "exec-123"})

    # With explicit trace_id
    broadcast_to_dashboard("task.progress", {...}, trace_id="...")
"""

from __future__ import annotations

import datetime
import decimal
import enum
import typing
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from gaf_core.tracing.context import current_trace_id

from protocol.constants import DASHBOARD_GROUP

if typing.TYPE_CHECKING:
    pass


def _json_safe(value):
    """Recursively coerce non-JSON-native values so channels_redis (msgpack)
    can serialize the event payload over the Redis channel layer.

    Without this, a UUID (e.g. an injected ``trace_id``) or datetime inside a
    broadcast payload raises ``TypeError: can not serialize 'UUID' object``
    inside ``channels_redis.core.group_send``. That exception breaks the
    consumer coroutine and can wedge the daphne event loop (observed as the
    backend process staying alive but rejecting new connections).
    """
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (uuid.UUID, datetime.datetime, datetime.date, datetime.time, decimal.Decimal)):
        return str(value)
    if isinstance(value, enum.Enum):
        return _json_safe(value.value)
    return value


def _inject_trace_id(payload: dict, trace_id: str | None) -> dict:
    """Inject trace_id into payload if not already present."""
    if trace_id is not None:
        payload.setdefault("trace_id", trace_id)
    else:
        payload.setdefault("trace_id", current_trace_id.get() or "")
    return payload


def broadcast_to_dashboard(
    event_type: str,
    payload: dict | None = None,
    *,
    trace_id: str | None = None,
    group: str = DASHBOARD_GROUP,
) -> None:
    """Broadcast an event to the dashboard group with trace_id injected.

    Synchronous (blocking) version — uses ``async_to_sync`` internally.
    Safe to call from DRF views, Celery tasks, management commands, etc.

    Args:
        event_type: Channels event type (routed to consumer method).
        payload: Event payload dict. Will have ``trace_id`` injected.
        trace_id: Explicit trace_id. If ``None``, read from ``current_trace_id``
            ContextVar (set by ``TracingMiddleware`` or ``TracingChannelsMiddleware``).
        group: Channels group name. Defaults to ``DASHBOARD_GROUP``.
    """
    _payload = _json_safe(_inject_trace_id(payload or {}, trace_id))
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        group,
        {
            "type": event_type,
            "payload": _payload,
        },
    )


async def async_broadcast_to_dashboard(
    event_type: str,
    payload: dict | None = None,
    *,
    trace_id: str | None = None,
    group: str = DASHBOARD_GROUP,
) -> None:
    """Async version of :func:`broadcast_to_dashboard`.

    Use from Channels consumers or any async context to avoid ``async_to_sync``
    overhead.

    Args:
        event_type: Channels event type (routed to consumer method).
        payload: Event payload dict. Will have ``trace_id`` injected.
        trace_id: Explicit trace_id. If ``None``, read from ``current_trace_id``
            ContextVar (set by ``TracingMiddleware`` or ``TracingChannelsMiddleware``).
        group: Channels group name. Defaults to ``DASHBOARD_GROUP``.
    """
    _payload = _json_safe(_inject_trace_id(payload or {}, trace_id))
    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        group,
        {
            "type": event_type,
            "payload": _payload,
        },
    )
