"""Device resource lock — prevents concurrent operations on the same device.

🔧 Status: helper class implemented and unit-tested; NOT yet wired into
``dispatch_task`` in ``tasks/tasks.py``. The current code relies on the
``TaskExecution`` state machine (a RUNNING execution implicitly holds
the device) to prevent double-assignment, but does not enforce a hard
lock at the device level. Wiring ``ResourceLock`` into the dispatch
path is tracked as a future task under ``concurrency-design.md`` §2.4.

Design
------
Two backends are supported, with Redis preferred:

1. **Redis** (preferred for multi-worker deployments):
   Uses ``SET key value NX EX seconds`` to atomically acquire a lock.
   The lock value is the ``task_id`` so we can verify ownership on
   release. Release uses a Lua script to atomically check ownership
   then delete — preventing a task from releasing a lock it no longer
   holds (e.g. after the TTL expired and another task acquired it).

2. **In-memory** (fallback for single-worker / tests):
   Uses ``threading.Lock`` per device_id with a holder dict mapping
   ``device_id → task_id``. Only correct within a single process.

The TTL (default 30 minutes) prevents orphaned locks if a worker
crashes mid-task: the lock auto-expires and other tasks can proceed.
Long-running tasks should call ``refresh(device_id, task_id)`` to
extend the TTL before it expires.

Usage
-----
::

    from tasks.resource_lock import ResourceLock

    lock = ResourceLock(ttl_seconds=1800)
    if lock.acquire(device_id, str(execution.id)):
        try:
            ...  # operate on device
        finally:
            lock.release(device_id, str(execution.id))
    else:
        # Device busy — pick another device or queue the task.
        ...
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


# Lua script for atomic "release only if I'm the holder" — runs inside Redis.
# If the stored value matches the given task_id, delete the key (return 1).
# Otherwise do nothing (return 0). This prevents releasing a lock that has
# already auto-expired and been re-acquired by another task.
_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""

# Lua script for atomic "refresh TTL only if I'm the holder" — same idea
# as release, but calls EXPIRE instead of DEL.
_REFRESH_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
else
    return 0
end
"""


def _get_redis_client() -> Any | None:
    """Return a shared Redis client, or None if Redis is unavailable.

    .. deprecated::
        Use :func:`tasks.redis_utils.get_redis_client` directly. This
        wrapper is retained only to keep the import graph stable for
        existing callers; it delegates to the shared helper.
    """
    from tasks.redis_utils import get_redis_client

    return get_redis_client()


class ResourceLock:
    """Device-level distributed lock backed by Redis (with in-memory fallback).

    Args:
        ttl_seconds: Lock TTL in seconds. Default 1800 (30 minutes). The
            TTL auto-expires orphaned locks if a worker crashes mid-task.
            Long-running tasks should call ``refresh`` before the TTL
            expires to extend it.
        key_prefix: Redis key prefix. Default ``"resource_lock:"``.
    """

    KEY_PREFIX = "resource_lock"

    def __init__(self, ttl_seconds: int = 1800, key_prefix: str = KEY_PREFIX):
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")
        self._ttl = int(ttl_seconds)
        self._key_prefix = key_prefix
        self._redis = _get_redis_client()
        # In-memory fallback state (only used when self._redis is None).
        self._mem_locks: dict[str, threading.Lock] = {}
        self._mem_holders: dict[str, str] = {}
        self._mem_meta: dict[str, dict[str, float]] = {}  # device_id → {acquired_at, expires_at}
        self._mem_guard = threading.Lock()

    # ── Public properties ──────────────────────────────────────
    @property
    def uses_redis(self) -> bool:
        """True if Redis backend is active (False = in-memory fallback)."""
        return self._redis is not None

    @property
    def ttl_seconds(self) -> int:
        """Configured lock TTL (seconds)."""
        return self._ttl

    # ── Public API ─────────────────────────────────────────────
    def acquire(self, device_id: str, task_id: str, timeout: float = 30.0) -> bool:
        """Acquire the lock for ``device_id`` on behalf of ``task_id``.

        Args:
            device_id: Device identifier (e.g. ``Device.device_id``).
            task_id: Task execution identifier — stored as the lock value
                so ownership can be verified on release.
            timeout: For the in-memory backend, max seconds to block
                waiting for ``threading.Lock.acquire``. Ignored for the
                Redis backend (Redis ``SET NX`` is non-blocking — returns
                immediately if the lock is held).

        Returns:
            True if the lock was acquired, False if it is held by another
            task (or device_id/task_id is empty).
        """
        if not device_id or not task_id:
            return False

        if self._redis is not None:
            return self._acquire_redis(device_id, task_id)
        return self._acquire_memory(device_id, task_id, timeout)

    def release(self, device_id: str, task_id: str) -> bool:
        """Release the lock for ``device_id`` if held by ``task_id``.

        Safe to call even if the lock is not held by ``task_id`` —
        returns False without raising. This prevents a task from
        releasing a lock that has auto-expired and been re-acquired
        by another task.

        Args:
            device_id: Device identifier.
            task_id: Task execution identifier (must match the value
                passed to ``acquire``).

        Returns:
            True if the lock was held by ``task_id`` and successfully
            released. False if the lock was not held by ``task_id``
            (or device_id/task_id is empty).
        """
        if not device_id or not task_id:
            return False

        if self._redis is not None:
            return self._release_redis(device_id, task_id)
        return self._release_memory(device_id, task_id)

    def refresh(self, device_id: str, task_id: str) -> bool:
        """Extend the lock TTL for ``device_id`` if held by ``task_id``.

        Call this periodically on long-running tasks to prevent the lock
        from auto-expiring before the task completes.

        Args:
            device_id: Device identifier.
            task_id: Task execution identifier (must match the value
                passed to ``acquire``).

        Returns:
            True if the TTL was extended. False if the lock is not held
            by ``task_id`` (or device_id/task_id is empty).
        """
        if not device_id or not task_id:
            return False

        if self._redis is not None:
            return self._refresh_redis(device_id, task_id)
        return self._refresh_memory(device_id, task_id)

    def is_locked(self, device_id: str) -> bool:
        """Check whether ``device_id`` is currently locked by any task.

        Note: the result is a point-in-time snapshot — the lock state
        may change immediately after this call returns. For critical
        sections, use ``acquire`` directly and handle the False return.

        As a side effect, this call cleans up stale in-memory locks
        (locks whose TTL has expired) — including releasing the
        underlying ``threading.Lock`` so the device becomes
        re-acquirable.

        Args:
            device_id: Device identifier.

        Returns:
            True if the device is locked. False otherwise (or if
            device_id is empty).
        """
        if not device_id:
            return False
        if self._redis is not None:
            return self._redis.exists(self._key(device_id)) == 1
        with self._mem_guard:
            if device_id not in self._mem_holders:
                return False
            # Check TTL — has the lock auto-expired?
            expires_at = self._mem_meta.get(device_id, {}).get("expires_at", 0.0)
            if expires_at and time.time() > expires_at:
                # Stale lock — clean it up (metadata + underlying lock).
                self._mem_holders.pop(device_id, None)
                self._mem_meta.pop(device_id, None)
                lock = self._mem_locks.get(device_id)
                if lock is not None:
                    with contextlib.suppress(RuntimeError):
                        # Lock not held by this thread — already released.
                        lock.release()
                return False
            return True

    # ── Redis backend ─────────────────────────────────────────
    def _key(self, device_id: str) -> str:
        """Build the Redis key for ``device_id``."""
        return f"{self._key_prefix}:{device_id}"

    def _acquire_redis(self, device_id: str, task_id: str) -> bool:
        """Acquire via ``SET key value NX EX ttl``."""
        try:
            # SET key value NX EX seconds — atomic acquire with TTL.
            result = self._redis.set(  # type: ignore[union-attr]
                self._key(device_id),
                task_id,
                nx=True,
                ex=self._ttl,
            )
            return bool(result)
        except Exception as exc:  # noqa: BLE001 — Redis errors vary
            logger.warning(
                "ResourceLock.acquire: Redis error for device %s: %s",
                device_id, exc,
            )
            return False

    def _release_redis(self, device_id: str, task_id: str) -> bool:
        """Release via Lua script (atomic check-and-del)."""
        try:
            result = self._redis.eval(  # type: ignore[union-attr]
                _RELEASE_SCRIPT, 1, self._key(device_id), task_id,
            )
            return bool(result)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ResourceLock.release: Redis error for device %s: %s",
                device_id, exc,
            )
            return False

    def _refresh_redis(self, device_id: str, task_id: str) -> bool:
        """Refresh TTL via Lua script (atomic check-and-expire)."""
        try:
            result = self._redis.eval(  # type: ignore[union-attr]
                _REFRESH_SCRIPT, 1, self._key(device_id), task_id, self._ttl,
            )
            return bool(result)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ResourceLock.refresh: Redis error for device %s: %s",
                device_id, exc,
            )
            return False

    # ── In-memory backend ─────────────────────────────────────
    def _acquire_memory(self, device_id: str, task_id: str, timeout: float) -> bool:
        """Acquire via ``threading.Lock`` (single-process only)."""
        with self._mem_guard:
            lock = self._mem_locks.get(device_id)
            if lock is None:
                lock = threading.Lock()
                self._mem_locks[device_id] = lock

        # Try to acquire without blocking first — if a stale lock has
        # auto-expired, we can reclaim it.
        with self._mem_guard:
            expires_at = self._mem_meta.get(device_id, {}).get("expires_at", 0.0)
            if expires_at and time.time() > expires_at:
                # Stale lock — clean it up so the new task can acquire.
                holder = self._mem_holders.pop(device_id, None)
                self._mem_meta.pop(device_id, None)
                if holder is not None:
                    # Best-effort release of the underlying threading.Lock
                    # (only the original holder thread can do this safely,
                    # but threading.Lock.release on an un-held lock raises
                    # RuntimeError — we swallow it).
                    with contextlib.suppress(RuntimeError):
                        lock.release()

        acquired = lock.acquire(timeout=timeout if timeout > 0 else -1)
        if not acquired:
            return False
        with self._mem_guard:
            self._mem_holders[device_id] = task_id
            self._mem_meta[device_id] = {
                "acquired_at": time.time(),
                "expires_at": time.time() + self._ttl,
            }
        return True

    def _release_memory(self, device_id: str, task_id: str) -> bool:
        """Release the in-memory lock if held by ``task_id``."""
        with self._mem_guard:
            holder = self._mem_holders.get(device_id)
            if holder != task_id:
                return False
            lock = self._mem_locks.get(device_id)
            self._mem_holders.pop(device_id, None)
            self._mem_meta.pop(device_id, None)
        if lock is None:
            return False
        try:
            lock.release()
        except RuntimeError:
            # Lock not held by this thread — already cleaned up above.
            return False
        return True

    def _refresh_memory(self, device_id: str, task_id: str) -> bool:
        """Extend the in-memory lock's TTL if held by ``task_id``."""
        with self._mem_guard:
            holder = self._mem_holders.get(device_id)
            if holder != task_id:
                return False
            self._mem_meta[device_id]["expires_at"] = time.time() + self._ttl
        return True
