"""Shared Redis client factory for tasks app.

Provides a single ``get_redis_client()`` helper used by:
- ``tasks.resource_lock`` (device-level distributed lock)
- ``tasks.concurrency_controller.RedisConcurrencyController`` (per-agent
  + global concurrency caps across Celery workers)

Centralizing the client factory avoids divergent connection logic and
ensures both modules fall back to in-memory mode consistently when Redis
is unavailable (single-worker deployments / tests without Redis).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


_REDIS_CLIENT: Any | None = None
_REDIS_PROBED: bool = False


def get_redis_client() -> Any | None:
    """Return a shared Redis client, or ``None`` if Redis is unavailable.

    Reads ``REDIS_URL`` from the environment (same convention as Django
    CACHES in ``config/settings/prod.py``). When unset, falls back to
    ``localhost:6379``. The connection attempt is cached at module scope
    so repeated calls don't retry.

    Returns:
        A ``redis.Redis`` client with a verified ``ping()``, or ``None``
        if ``redis-py`` is not installed or the connection failed. Callers
        are responsible for providing an in-memory fallback when ``None``
        is returned.
    """
    global _REDIS_CLIENT, _REDIS_PROBED
    if _REDIS_PROBED:
        return _REDIS_CLIENT
    _REDIS_PROBED = True
    try:
        import os

        import redis  # type: ignore[import-not-found]

        # TD-313 fix (spec-67, 2026-07-21): bind short socket timeouts so
        # ``ping()`` fails fast (≤ 0.2s) when Redis is not running, instead
        # of blocking ~4s on the default connect timeout. Without this,
        # tests that touch ``_release_resources_for_execution`` (e.g.
        # ``test_task_result_returns_ack``) exceed the 1s
        # ``WebsocketCommunicator.receive_from()`` timeout and raise
        # ``TimeoutError`` even though the InMemoryChannelLayer is in use.
        # 0.2s is plenty for a healthy local Redis; production deployments
        # with a remote Redis can override via ``REDIS_URL``.
        url = os.environ.get("REDIS_URL")
        if url:  # noqa: SIM108
            _REDIS_CLIENT = redis.Redis.from_url(
                url,
                socket_timeout=0.2,
                socket_connect_timeout=0.2,
            )
        else:
            _REDIS_CLIENT = redis.Redis(
                host="localhost",
                port=6379,
                db=0,
                socket_timeout=0.2,
                socket_connect_timeout=0.2,
            )
        _REDIS_CLIENT.ping()
        logger.info("Redis client connected: %s", url or "localhost:6379")
    except ImportError:
        logger.info(
            "redis-py not installed; modules relying on Redis will fall back "
            "to in-memory mode (not safe for multi-worker deployments)",
        )
        _REDIS_CLIENT = None
    except Exception as exc:  # noqa: BLE001 — broad on purpose, connection issues vary
        logger.info(
            "Redis unavailable (%s); modules relying on Redis will fall back "
            "to in-memory mode (not safe for multi-worker deployments)",
            exc,
        )
        _REDIS_CLIENT = None
    return _REDIS_CLIENT


def reset_redis_client_cache() -> None:
    """Clear the cached Redis client (mainly for tests).

    Production code should NOT call this — it forces the next
    ``get_redis_client()`` call to re-probe the connection.
    """
    global _REDIS_CLIENT, _REDIS_PROBED
    _REDIS_CLIENT = None
    _REDIS_PROBED = False
