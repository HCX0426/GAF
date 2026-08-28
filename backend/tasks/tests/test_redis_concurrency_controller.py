"""Unit tests for RedisConcurrencyController.

These tests use a minimal in-process FakeRedis (no external Redis
dependency) to verify the ZSET-based in-flight tracking, TTL-based
auto-eviction, per-agent + global cap enforcement, and idempotent
release semantics.

The wiring tests in ``test_concurrency_controller_wiring.py`` cover
the in-memory backend end-to-end through dispatch_task; here we focus
on the Redis code path that wiring tests can't exercise without a real
Redis instance.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from django.test import SimpleTestCase

from tasks.concurrency_controller import (
    ConcurrencyController,
    RedisConcurrencyController,
    configure_default_controller,
    get_default_controller,
)

pytestmark = pytest.mark.unit


class FakeRedis:
    """Minimal in-process Redis for RedisConcurrencyController tests.

    Implements only the ZSET + key operations the controller uses:
    ``zadd``, ``zrem``, ``zcard``, ``zremrangebyscore``, ``scan``,
    ``delete``, ``expire``, ``pipeline``. Members are stored with
    float scores; TTL on the key itself is a no-op (we rely on
    ZSET-score-based eviction, mirroring the controller's design).
    """

    def __init__(self) -> None:
        # key -> {member: score}
        self._zsets: dict[str, dict[str, float]] = {}

    # ── ZSET operations ────────────────────────────────────────
    def zadd(self, key: str, mapping: dict[str, float]) -> int:
        zset = self._zsets.setdefault(key, {})
        added = 0
        for member, score in mapping.items():
            if member not in zset:
                added += 1
            zset[member] = float(score)
        return added

    def zrem(self, key: str, *members: str) -> int:
        zset = self._zsets.get(key)
        if not zset:
            return 0
        removed = 0
        for m in members:
            if m in zset:
                del zset[m]
                removed += 1
        if not zset:
            del self._zsets[key]
        return removed

    def zcard(self, key: str) -> int:
        return len(self._zsets.get(key, {}))

    def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        zset = self._zsets.get(key)
        if not zset:
            return 0
        to_remove = [m for m, s in zset.items() if min_score <= s <= max_score]
        for m in to_remove:
            del zset[m]
        if not zset:
            del self._zsets[key]
        return len(to_remove)

    # ── Key operations ─────────────────────────────────────────
    def delete(self, *keys: str) -> int:
        deleted = 0
        for k in keys:
            if k in self._zsets:
                del self._zsets[k]
                deleted += 1
        return deleted

    def expire(self, key: str, seconds: int) -> bool:
        # No-op: TTL is enforced via ZSET score eviction, not key expiry.
        # We return True so the controller's pipeline thinks the expire
        # succeeded (matches real Redis behavior on existing keys).
        return key in self._zsets

    def scan(self, cursor: int = 0, match: str | None = None, count: int = 100):
        # Simplified: return all matching keys in one batch (cursor=0).
        import fnmatch

        if cursor != 0:
            return 0, []
        keys = []
        for k in self._zsets:
            if match is None or fnmatch.fnmatch(k, match):
                keys.append(k)
        return 0, keys

    # ── Pipeline ───────────────────────────────────────────────
    def pipeline(self) -> FakeRedisPipeline:
        return FakeRedisPipeline(self)


class FakeRedisPipeline:
    """Queues Redis commands and executes them in order, returning a list."""

    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._queue: list[tuple[str, tuple, dict]] = []

    def zadd(self, key: str, mapping: dict[str, float]) -> FakeRedisPipeline:
        self._queue.append(("zadd", (key, mapping), {}))
        return self

    def zrem(self, key: str, *members: str) -> FakeRedisPipeline:
        self._queue.append(("zrem", (key, *members), {}))
        return self

    def zcard(self, key: str) -> FakeRedisPipeline:
        self._queue.append(("zcard", (key,), {}))
        return self

    def expire(self, key: str, seconds: int) -> FakeRedisPipeline:
        self._queue.append(("expire", (key, seconds), {}))
        return self

    def execute(self) -> list[Any]:
        results: list[Any] = []
        for method, args, _kwargs in self._queue:
            fn = getattr(self._redis, method)
            results.append(fn(*args))
        self._queue.clear()
        return results


class RedisConcurrencyControllerTest(SimpleTestCase):
    """Verify Redis-backed concurrency caps + eviction semantics."""

    def setUp(self) -> None:
        self.fake = FakeRedis()
        # Use a short TTL so we can test eviction without sleeping 30 min.
        self.controller = RedisConcurrencyController(
            max_tasks_per_agent=2,
            max_total_tasks=5,
            redis_client=self.fake,
            entry_ttl_seconds=1,  # 1 second — fast eviction tests
        )

    def tearDown(self) -> None:
        # Reset the singleton so other tests get a fresh default.
        configure_default_controller(None)

    # ── Basic cap enforcement ──────────────────────────────────
    def test_uses_redis_property_is_true(self) -> None:
        self.assertTrue(self.controller.uses_redis)

    def test_can_assign_when_below_both_caps(self) -> None:
        self.assertTrue(self.controller.can_assign("agent-A"))

    def test_can_assign_rejects_empty_agent_id(self) -> None:
        self.assertFalse(self.controller.can_assign(""))
        self.assertFalse(self.controller.can_assign(None))  # type: ignore[arg-type]

    def test_per_agent_cap_blocks_after_max(self) -> None:
        agent = "agent-A"
        # Cap is 2 — two assigns fit, third should be rejected.
        self.controller.assign(agent, "task-1")
        self.controller.assign(agent, "task-2")
        self.assertEqual(self.controller.get_agent_load(agent), 2)
        self.assertFalse(self.controller.can_assign(agent))

    def test_global_cap_blocks_when_total_exceeded(self) -> None:
        # global cap is 5; spread across agents so per-agent cap doesn't bind.
        # per-agent cap is 2, so we need 3 agents to reach 5 total.
        self.controller.assign("agent-A", "t1")
        self.controller.assign("agent-A", "t2")
        self.controller.assign("agent-B", "t3")
        self.controller.assign("agent-B", "t4")
        self.controller.assign("agent-C", "t5")
        self.assertEqual(self.controller.total_in_flight, 5)
        # agent-D has room per-agent but global is full.
        self.controller.assign("agent-D", "t6")  # over-cap — should still record
        # can_assign on agent-D should now be False (global cap exceeded).
        # Note: assign() does not re-check, mirroring the in-memory contract;
        # callers must can_assign() first. So we verify via can_assign on a
        # fresh agent that has per-agent room.
        self.assertFalse(self.controller.can_assign("agent-E"))

    # ── Release semantics ──────────────────────────────────────
    def test_release_decrements_load(self) -> None:
        self.controller.assign("agent-A", "t1")
        self.controller.assign("agent-A", "t2")
        self.assertEqual(self.controller.get_agent_load("agent-A"), 2)
        self.controller.release("agent-A", "t1")
        self.assertEqual(self.controller.get_agent_load("agent-A"), 1)
        # can_assign is True again after one release.
        self.assertTrue(self.controller.can_assign("agent-A"))

    def test_release_unknown_pair_is_silent(self) -> None:
        # Releasing a pair that was never assigned must not raise.
        self.controller.release("never-assigned-agent", "no-such-task")
        self.assertEqual(self.controller.get_agent_load("never-assigned-agent"), 0)

    def test_release_twice_is_idempotent(self) -> None:
        self.controller.assign("agent-A", "t1")
        self.controller.release("agent-A", "t1")
        self.controller.release("agent-A", "t1")  # second release — no-op
        self.assertEqual(self.controller.get_agent_load("agent-A"), 0)

    def test_assign_is_idempotent_for_same_pair(self) -> None:
        # Re-assigning the same (agent, task) pair should not double-count.
        self.controller.assign("agent-A", "t1")
        self.controller.assign("agent-A", "t1")
        self.assertEqual(self.controller.get_agent_load("agent-A"), 1)
        self.assertEqual(self.controller.total_in_flight, 1)

    # ── TTL-based eviction ─────────────────────────────────────
    def test_expired_entries_auto_evict_on_can_assign(self) -> None:
        # Assign with 1s TTL, then sleep past TTL and verify can_assign
        # evicts the expired entry and returns True.
        self.controller.assign("agent-A", "t1")
        self.controller.assign("agent-A", "t2")
        self.assertFalse(self.controller.can_assign("agent-A"))
        # Sleep 1.1s so entries are now past expiry.
        time.sleep(1.1)
        # can_assign should evict and return True.
        self.assertTrue(self.controller.can_assign("agent-A"))
        self.assertEqual(self.controller.get_agent_load("agent-A"), 0)

    def test_expired_entries_evict_from_global_count(self) -> None:
        self.controller.assign("agent-A", "t1")
        self.controller.assign("agent-B", "t2")
        self.assertEqual(self.controller.total_in_flight, 2)
        time.sleep(1.1)
        # total_in_flight getter also evicts; count should drop to 0.
        self.assertEqual(self.controller.total_in_flight, 0)

    # ── reset() ────────────────────────────────────────────────
    def test_reset_clears_all_agents_and_global(self) -> None:
        self.controller.assign("agent-A", "t1")
        self.controller.assign("agent-B", "t2")
        self.controller.assign("agent-C", "t3")
        self.assertEqual(self.controller.total_in_flight, 3)
        self.controller.reset()
        self.assertEqual(self.controller.total_in_flight, 0)
        self.assertEqual(self.controller.get_agent_load("agent-A"), 0)
        self.assertEqual(self.controller.get_agent_load("agent-B"), 0)
        self.assertEqual(self.controller.get_agent_load("agent-C"), 0)

    # ── get_default_controller fallback ────────────────────────
    def test_get_default_controller_returns_in_memory_when_redis_unavailable(self) -> None:
        # Without REDIS_URL set and no Redis listening on localhost (or
        # with redis-py absent), get_default_controller must fall back to
        # the in-memory backend. We force this by clearing the singleton
        # and the redis_utils probe cache, then re-fetching.
        from tasks.redis_utils import reset_redis_client_cache

        configure_default_controller(None)
        reset_redis_client_cache()
        # Force the probe to fail by temporarily replacing get_redis_client
        # with one that returns None.
        import tasks.redis_utils as ru

        original = ru.get_redis_client
        ru.get_redis_client = lambda: None  # type: ignore[assignment]
        try:
            controller = get_default_controller()
            self.assertFalse(controller.uses_redis)
            self.assertIsInstance(controller, ConcurrencyController)
            self.assertNotIsInstance(controller, RedisConcurrencyController)
        finally:
            ru.get_redis_client = original  # type: ignore[assignment]
            reset_redis_client_cache()
            configure_default_controller(None)

    def test_redis_backend_uses_distinct_keys_per_agent(self) -> None:
        # Verify the controller doesn't mix up per-agent ZSETs.
        self.controller.assign("agent-A", "t1")
        self.controller.assign("agent-B", "t2")
        self.controller.assign("agent-B", "t3")
        self.assertEqual(self.controller.get_agent_load("agent-A"), 1)
        self.assertEqual(self.controller.get_agent_load("agent-B"), 2)
        self.assertEqual(self.controller.total_in_flight, 3)
        # Releasing agent-B's task must not affect agent-A's load.
        self.controller.release("agent-B", "t2")
        self.assertEqual(self.controller.get_agent_load("agent-A"), 1)
        self.assertEqual(self.controller.get_agent_load("agent-B"), 1)
        self.assertEqual(self.controller.total_in_flight, 2)
