"""Per-agent concurrency limiter for task dispatch.

✅ Status: wired into ``dispatch_task`` (acquire on dispatch) and
``AgentConsumer`` (release on task.completed / task.failed) plus the
force-terminate paths in ``tasks/services.py`` (cancel / execution /
heartbeat timeouts). Per-agent and global concurrency caps are now
enforced end-to-end.

Design
------
The controller tracks in-flight tasks per agent. Two backends are
supported:

1. **In-memory** (default, single-worker): a thread-safe ``dict``
   ``{ agent_id: { task_id, ... } }`` guarded by a single
   ``threading.Lock``. Matches the original implementation.
2. **Redis** (multi-worker): a ``RedisConcurrencyController`` subclass
   uses Redis ZSETs to track in-flight tasks across Celery workers.
   Each task is stored with an expiry timestamp (score) so orphaned
   entries auto-evict if a worker crashes mid-task.

Two caps are enforced:
- ``max_tasks_per_agent`` (default 3): per-agent concurrent task limit.
- ``max_total_tasks`` (default 20): global concurrency cap across all
  agents.

``can_assign(agent_id)`` returns True only when BOTH caps have room.
``assign`` / ``release`` update the underlying backend atomically.

Usage
-----
::

    from tasks.concurrency_controller import get_default_controller

    controller = get_default_controller()
    if controller.can_assign(agent.agent_id):
        controller.assign(agent.agent_id, str(execution.id))
        try:
            ...  # dispatch + run task
        finally:
            controller.release(agent.agent_id, str(execution.id))
    else:
        # Agent at capacity — retry later or pick another agent.
        ...
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class ConcurrencyController:
    """Thread-safe per-agent + global concurrency limiter.

    Args:
        max_tasks_per_agent: Maximum concurrent in-flight tasks per agent.
            Default 3 (matches ``concurrency-design.md`` §2.3).
        max_total_tasks: Global cap across all agents. Default 20.
            Set to a very large value (e.g. ``float('inf')``) to disable
            the global cap and only enforce the per-agent cap.
    """

    def __init__(
        self,
        max_tasks_per_agent: int = 3,
        max_total_tasks: int = 20,
    ):
        if max_tasks_per_agent < 0:
            raise ValueError(
                f"max_tasks_per_agent must be >= 0, got {max_tasks_per_agent}",
            )
        if isinstance(max_total_tasks, int) and max_total_tasks < 0:
            raise ValueError(
                f"max_total_tasks must be >= 0, got {max_total_tasks}",
            )
        self._max_per_agent = int(max_tasks_per_agent)
        self._max_total = max_total_tasks
        self._agent_tasks: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    # ── Public properties ──────────────────────────────────────
    @property
    def max_tasks_per_agent(self) -> int:
        """Per-agent concurrency cap."""
        return self._max_per_agent

    @property
    def max_total_tasks(self) -> int:
        """Global concurrency cap (int or float('inf'))."""
        return self._max_total

    @property
    def total_in_flight(self) -> int:
        """Current total in-flight task count (across all agents)."""
        with self._lock:
            return sum(len(tasks) for tasks in self._agent_tasks.values())

    @property
    def uses_redis(self) -> bool:
        """True if the backend is Redis (False = in-memory)."""
        return False

    # ── Public API ─────────────────────────────────────────────
    def can_assign(self, agent_id: str) -> bool:
        """Check whether a new task can be assigned to ``agent_id``.

        Returns True only when:
        - The global in-flight count is below ``max_total_tasks``.
        - The per-agent in-flight count is below ``max_tasks_per_agent``.

        Args:
            agent_id: Agent identifier (typically ``Agent.agent_id``).

        Returns:
            True if a task can be assigned without exceeding either cap.
        """
        if not agent_id:
            return False
        with self._lock:
            total = sum(len(tasks) for tasks in self._agent_tasks.values())
            if total >= self._max_total:
                return False
            agent_count = len(self._agent_tasks.get(agent_id, ()))
            return not agent_count >= self._max_per_agent

    def assign(self, agent_id: str, task_id: str) -> None:
        """Record that ``task_id`` has been assigned to ``agent_id``.

        Does NOT re-check the caps — callers should ``can_assign`` first.
        Idempotent: assigning the same (agent_id, task_id) pair twice is
        a no-op (the task_id set deduplicates).

        Args:
            agent_id: Agent identifier.
            task_id: Task execution identifier (typically str(execution.id)).
        """
        if not agent_id or not task_id:
            return
        with self._lock:
            tasks = self._agent_tasks.setdefault(agent_id, set())
            tasks.add(task_id)

    def release(self, agent_id: str, task_id: str) -> None:
        """Record that ``task_id`` on ``agent_id`` has completed.

        Safe to call even if the (agent_id, task_id) pair was never
        ``assign``-ed — discards silently.

        Args:
            agent_id: Agent identifier.
            task_id: Task execution identifier.
        """
        if not agent_id or not task_id:
            return
        with self._lock:
            tasks = self._agent_tasks.get(agent_id)
            if not tasks:
                return
            tasks.discard(task_id)
            # Clean up empty sets so total_in_flight stays accurate and
            # the dict doesn't grow unboundedly across agent churn.
            if not tasks:
                del self._agent_tasks[agent_id]

    def get_agent_load(self, agent_id: str) -> int:
        """Return the current in-flight task count for ``agent_id``.

        Args:
            agent_id: Agent identifier.

        Returns:
            Number of tasks currently assigned to this agent (0 if none).
        """
        if not agent_id:
            return 0
        with self._lock:
            return len(self._agent_tasks.get(agent_id, ()))

    def reset(self) -> None:
        """Clear all in-flight tracking (mainly for tests).

        Production code should NOT call this — it loses track of
        in-flight tasks and could cause cap overruns.
        """
        with self._lock:
            self._agent_tasks.clear()


# TTL (seconds) for Redis ZSET entries. Orphaned entries (worker crash
# mid-task) auto-evict after this timeout. 30 minutes matches
# ResourceLock's default TTL — long enough for legitimate tasks, short
# enough to recover from crashes within a reasonable window.
_REDIS_ENTRY_TTL_SECONDS = 1800


class RedisConcurrencyController(ConcurrencyController):
    """Redis-backed per-agent + global concurrency limiter.

    Uses Redis ZSETs to track in-flight tasks across Celery workers.
    Each task is stored as a ZSET member with its expiry timestamp as
    score; ``can_assign`` first evicts expired members so orphaned
    entries (from crashed workers) don't hold slots forever.

    Key layout:
    - ``gaf:concurrency:agent:{agent_id}`` — ZSET of task_ids with
      score = expiry_timestamp.
    - ``gaf:concurrency:global`` — ZSET of ``"{agent_id}:{task_id}"``
      with score = expiry_timestamp. Used to compute total_in_flight
      without scanning all agent keys.

    Atomicity: ``assign`` and ``release`` use Redis pipelines to update
    both keys in a single round-trip. ``can_assign`` does a best-effort
    cleanup + count; minor races between can_assign and assign are
    acceptable (a worker can still over-assign by 1 under contention,
    which the caller can detect and retry).

    Args:
        max_tasks_per_agent: Per-agent cap. Default 3.
        max_total_tasks: Global cap. Default 20.
        redis_client: Optional pre-built Redis client. When None, the
            shared client from ``tasks.redis_utils.get_redis_client()``
            is used. If that also returns None (Redis unavailable),
            instantiation raises ``RuntimeError`` — callers should use
            :func:`get_default_controller` which falls back to the
            in-memory backend automatically.
        key_prefix: Redis key prefix. Default ``"gaf:concurrency:"``.
        entry_ttl_seconds: TTL for each in-flight entry. Default 1800
            (30 minutes).
    """

    KEY_PREFIX = "gaf:concurrency:"

    def __init__(
        self,
        max_tasks_per_agent: int = 3,
        max_total_tasks: int = 20,
        redis_client: Any | None = None,
        key_prefix: str = KEY_PREFIX,
        entry_ttl_seconds: int = _REDIS_ENTRY_TTL_SECONDS,
    ):
        super().__init__(
            max_tasks_per_agent=max_tasks_per_agent,
            max_total_tasks=max_total_tasks,
        )
        if redis_client is None:
            from tasks.redis_utils import get_redis_client

            redis_client = get_redis_client()
        if redis_client is None:
            raise RuntimeError(
                "RedisConcurrencyController requires a Redis client, but "
                "Redis is unavailable. Use get_default_controller() for "
                "automatic fallback to the in-memory backend.",
            )
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._entry_ttl = int(entry_ttl_seconds)

    # ── Properties ─────────────────────────────────────────────
    @property
    def uses_redis(self) -> bool:
        """True if the backend is Redis."""
        return True

    @property
    def entry_ttl_seconds(self) -> int:
        """Per-entry TTL (seconds)."""
        return self._entry_ttl

    # ── Internal helpers ───────────────────────────────────────
    def _agent_key(self, agent_id: str) -> str:
        return f"{self._key_prefix}agent:{agent_id}"

    def _global_key(self) -> str:
        return f"{self._key_prefix}global"

    def _global_member(self, agent_id: str, task_id: str) -> str:
        return f"{agent_id}:{task_id}"

    def _evict_expired(self, key: str) -> None:
        """Remove ZSET members whose score (expiry ts) is in the past."""
        now = time.time()
        try:
            self._redis.zremrangebyscore(key, 0, now)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "RedisConcurrencyController: zremrangebyscore failed for "
                "key=%s: %s",
                key,
                exc,
            )

    # ── Public API overrides ───────────────────────────────────
    @property
    def total_in_flight(self) -> int:
        self._evict_expired(self._global_key())
        try:
            return int(self._redis.zcard(self._global_key()))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "RedisConcurrencyController: zcard(global) failed: %s — "
                "returning 0 (may cause cap overruns)",
                exc,
            )
            return 0

    def can_assign(self, agent_id: str) -> bool:
        if not agent_id:
            return False
        agent_key = self._agent_key(agent_id)
        global_key = self._global_key()
        self._evict_expired(agent_key)
        self._evict_expired(global_key)
        try:
            pipe = self._redis.pipeline()
            pipe.zcard(agent_key)
            pipe.zcard(global_key)
            agent_count, total = pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "RedisConcurrencyController: can_assign pipeline failed: %s "
                "— returning False (fail-closed)",
                exc,
            )
            return False
        if int(total) >= self._max_total:
            return False
        return not int(agent_count) >= self._max_per_agent

    def assign(self, agent_id: str, task_id: str) -> None:
        if not agent_id or not task_id:
            return
        expiry = time.time() + self._entry_ttl
        agent_key = self._agent_key(agent_id)
        global_key = self._global_key()
        global_member = self._global_member(agent_id, task_id)
        try:
            pipe = self._redis.pipeline()
            pipe.zadd(agent_key, {task_id: expiry})
            pipe.zadd(global_key, {global_member: expiry})
            # Refresh TTL on the keys themselves so they don't leak
            # after the last member is removed by eviction.
            pipe.expire(agent_key, self._entry_ttl)
            pipe.expire(global_key, self._entry_ttl)
            pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "RedisConcurrencyController: assign failed for "
                "agent=%s task=%s: %s — controller state may be inconsistent",
                agent_id,
                task_id,
                exc,
            )

    def release(self, agent_id: str, task_id: str) -> None:
        if not agent_id or not task_id:
            return
        agent_key = self._agent_key(agent_id)
        global_key = self._global_key()
        global_member = self._global_member(agent_id, task_id)
        try:
            pipe = self._redis.pipeline()
            pipe.zrem(agent_key, task_id)
            pipe.zrem(global_key, global_member)
            pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "RedisConcurrencyController: release failed for "
                "agent=%s task=%s: %s — entry will expire via TTL",
                agent_id,
                task_id,
                exc,
            )

    def get_agent_load(self, agent_id: str) -> int:
        if not agent_id:
            return 0
        agent_key = self._agent_key(agent_id)
        self._evict_expired(agent_key)
        try:
            return int(self._redis.zcard(agent_key))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "RedisConcurrencyController: zcard(agent=%s) failed: %s — "
                "returning 0",
                agent_id,
                exc,
            )
            return 0

    def reset(self) -> None:
        """Clear all in-flight tracking (mainly for tests).

        Deletes every ``agent:*`` key under the prefix plus the global
        key. Uses SCAN to avoid blocking on a large keyspace.
        """
        try:
            pattern = f"{self._key_prefix}agent:*"
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    self._redis.delete(*keys)
                if cursor == 0:
                    break
            self._redis.delete(self._global_key())
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "RedisConcurrencyController: reset failed: %s — "
                "entries will expire via TTL",
                exc,
            )


# ── Module-level singleton ─────────────────────────────────────────
# Single-worker deployment: an in-memory singleton is sufficient and
# avoids the Redis dependency. Multi-worker deployments should call
# ``configure_default_controller(use_redis=True)`` once at startup.
_default_controller: ConcurrencyController | None = None


def get_default_controller() -> ConcurrencyController:
    """Return the process-local default :class:`ConcurrencyController`.

    Lazily instantiated on first call. Prefers a Redis-backed controller
    when Redis is available; falls back to the in-memory backend
    otherwise. Tests that need a clean slate should call
    ``controller.reset()`` in ``setUp`` rather than replacing the
    singleton (so production code paths see the same instance).

    Returns:
        A :class:`ConcurrencyController` (in-memory fallback) or
        :class:`RedisConcurrencyController` (when Redis is reachable).
    """
    global _default_controller
    if _default_controller is None:
        _default_controller = _build_default_controller()
    return _default_controller


def _build_default_controller() -> ConcurrencyController:
    """Construct a controller, preferring Redis when available."""
    try:
        from tasks.redis_utils import get_redis_client

        client = get_redis_client()
        if client is not None:
            return RedisConcurrencyController(redis_client=client)
    except RuntimeError as exc:
        logger.info(
            "get_default_controller: Redis backend unavailable (%s) — "
            "falling back to in-memory (single-worker only)",
            exc,
        )
    except Exception as exc:  # noqa: BLE001 — defensive
        logger.warning(
            "get_default_controller: Redis backend init failed (%s) — "
            "falling back to in-memory (single-worker only)",
            exc,
        )
    return ConcurrencyController()


def configure_default_controller(controller: ConcurrencyController | None) -> None:
    """Replace the singleton (mainly for tests / startup wiring).

    Args:
        controller: The new controller, or ``None`` to force lazy
            re-initialization on the next ``get_default_controller`` call.
    """
    global _default_controller
    _default_controller = controller
