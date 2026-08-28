"""跨进程监控事件数据模型 — ``MonitoringEvent``

Task 3.1 (2026-08-08): 提供跨进程事件总线的数据契约。``MonitoringEvent``
使用 Pydantic 模型确保序列化/反序列化的一致性，支持通过 WebSocket Channels
从 Agent/Backend 广播到 Frontend Dashboard。

与 ``monitors.models.MonitorEvent`` 的关系：
- ``models.MonitorEvent``: Django ORM 模型，持久化到数据库。
- ``events.MonitoringEvent``: Pydantic 数据模型，用于进程间传输。
  事件总线接收后，可选择持久化到 ``models.MonitorEvent``。

Usage::

    from monitors.events import MonitoringEvent, EventCategory, EventLevel

    event = MonitoringEvent(
        source="agent",
        level="ERROR",
        category="resource",
        payload={"device_id": 5, "cpu_usage": 95, "message": "CPU overload"},
    )
    # Serialize for WebSocket transport:
    json_str = event.model_dump_json()
    # Deserialize from WebSocket:
    event = MonitoringEvent.model_validate_json(json_str)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── Event levels ──────────────────────────────────────────────────────

EventLevel = Literal["INFO", "WARNING", "ERROR", "CRITICAL"]

# ── Event categories ──────────────────────────────────────────────────

EventCategory = Literal[
    "resource",       # CPU / memory / disk / network
    "task_execution", # Task / pipeline execution status
    "device",         # Device connect / disconnect / error
    "llm",            # LLM call / fallback / error
    "system",         # Service start / stop / heartbeat
    "security",       # Auth / permission / access
    "custom",         # User-defined categories
]


class MonitoringEvent(BaseModel):
    """跨进程监控事件数据模型。

    Attributes:
        event_id: 全局唯一事件 ID (自动生成 UUID v4)。
        timestamp: 事件发生时间戳 (UTC)。
        source: 事件来源 (agent / backend / frontend)。
        level: 严重级别 (INFO / WARNING / ERROR / CRITICAL)。
        category: 事件分类 (resource / task_execution / device / llm / system / security / custom)。
        payload: 事件负载 (任意 JSON 可序列化数据)。
        trace_id: 可选的追踪 ID，用于关联分布式调用链。
    """

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: Literal["agent", "backend", "frontend"]
    level: EventLevel
    category: EventCategory
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = ""

    # ── Quick constructors ────────────────────────────────────────────

    @classmethod
    def info(
        cls,
        source: Literal["agent", "backend", "frontend"],
        category: EventCategory,
        message: str,
        **extra: Any,
    ) -> MonitoringEvent:
        """创建 INFO 级别事件。"""
        return cls(
            source=source,
            level="INFO",
            category=category,
            payload={"message": message, **extra},
        )

    @classmethod
    def warning(
        cls,
        source: Literal["agent", "backend", "frontend"],
        category: EventCategory,
        message: str,
        **extra: Any,
    ) -> MonitoringEvent:
        """创建 WARNING 级别事件。"""
        return cls(
            source=source,
            level="WARNING",
            category=category,
            payload={"message": message, **extra},
        )

    @classmethod
    def error(
        cls,
        source: Literal["agent", "backend", "frontend"],
        category: EventCategory,
        message: str,
        **extra: Any,
    ) -> MonitoringEvent:
        """创建 ERROR 级别事件。"""
        return cls(
            source=source,
            level="ERROR",
            category=category,
            payload={"message": message, **extra},
        )

    @classmethod
    def critical(
        cls,
        source: Literal["agent", "backend", "frontend"],
        category: EventCategory,
        message: str,
        **extra: Any,
    ) -> MonitoringEvent:
        """创建 CRITICAL 级别事件。"""
        return cls(
            source=source,
            level="CRITICAL",
            category=category,
            payload={"message": message, **extra},
        )

    # ── Helpers ───────────────────────────────────────────────────────

    @property
    def is_error(self) -> bool:
        """是否为 ERROR 或 CRITICAL 级别。"""
        return self.level in ("ERROR", "CRITICAL")

    def to_broadcast_payload(self) -> dict[str, Any]:
        """转换为 ``broadcast_to_dashboard`` 兼容的 payload。

        Returns:
            包含 ``event_id``, ``timestamp``, ``source``, ``level``,
            ``category``, ``payload``, ``trace_id`` 的字典。
        """
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "level": self.level,
            "category": self.category,
            "payload": self.payload,
            "trace_id": self.trace_id,
        }
