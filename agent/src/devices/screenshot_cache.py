"""Screenshot cache with Redis backend and in-memory fallback.

✅ Status: wired into screenshot stream (handler.py screenshot capture
path). The screenshot stream queries the default cache before invoking
``cv2.imencode`` and stores the encoded JPEG on miss for future reuse.

Backend selection
-----------------
1. **Redis** (preferred for multi-client sharing): uses ``redis-py``
   (already a transitive dependency via ``django-redis``). The connection
   URL is read from the ``REDIS_URL`` env var, falling back to
   ``redis://127.0.0.1:6379/0``.
2. **In-memory** (fallback when Redis is unreachable): a simple dict
   mapping ``key → (bytes, expires_at)``. Entries are lazily expired on
   ``get()``.

Key format
----------
``screenshot:{device_id}:{frame_hash}`` where ``frame_hash`` is a stable
hash of the raw BGR pixel data (so identical frames hit the cache across
calls). The ``device_id`` prefix enables per-device eviction if needed.

API
---
::

    cache = ScreenshotCache(default_ttl=300)
    cache.set("dev1", frame_hash, jpeg_bytes)
    cached = cache.get("dev1", frame_hash)  # → bytes or None
    cache.clear(device_id="dev1")           # clear one device
    cache.clear()                            # clear all

``default_ttl`` should be sourced from ``config.cache_ttl`` (default 300s)
to activate the previously-dead config field per screenshot-optimization.md
§0.1.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import time

import numpy as np

logger = logging.getLogger(__name__)

# Module-level Redis client cache so all ScreenshotCache instances share
# the same connection pool. None = tried and failed; absent = not tried.
_REDIS_CLIENT = None  # type: ignore[type-arg]
_REDIS_TRIED = False


def _get_redis_client():
    """Return a shared redis.Redis client, or None if Redis is unavailable.

    Caches the result so we don't retry the connection on every call. The
    first failure logs a warning; subsequent failures are silent.
    """
    global _REDIS_CLIENT, _REDIS_TRIED
    if _REDIS_TRIED:
        return _REDIS_CLIENT
    _REDIS_TRIED = True
    try:
        import redis  # type: ignore[import-not-found]
    except ImportError:
        logger.info("ScreenshotCache: redis-py not installed, using in-memory backend")
        return None
    url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)
        client.ping()  # verify connection
        _REDIS_CLIENT = client
        logger.info("ScreenshotCache: connected to Redis at %s", url)
        return client
    except Exception as exc:
        logger.warning(
            "ScreenshotCache: Redis unavailable (%s), using in-memory backend", exc,
        )
        return None


def compute_frame_hash(image: np.ndarray) -> str:
    """Compute a stable SHA-256 hash of an image's pixel data.

    Args:
        image: BGR numpy array.

    Returns:
        Hex digest string (64 chars). Two identical images produce the
        same hash; even a 1-pixel difference produces a different hash.
    """
    if image is None:
        return ""
    try:
        # Use contiguous bytes for speed and stability across runs.
        return hashlib.sha256(image.tobytes()).hexdigest()
    except Exception as exc:
        logger.warning("compute_frame_hash failed: %s", exc)
        return ""


class ScreenshotCache:
    """Screenshot cache with Redis backend and in-memory fallback.

    Args:
        default_ttl: Default TTL in seconds for cache entries. Should be
            sourced from ``config.cache_ttl`` (default 300) to activate
            the previously-dead config field.
        max_memory_entries: Maximum entries kept in the in-memory backend
            (LRU eviction when full). Default 100. Ignored when Redis is
            available.
    """

    KEY_PREFIX = "screenshot"

    def __init__(self, default_ttl: float = 300.0, max_memory_entries: int = 100):
        if default_ttl < 0:
            raise ValueError(f"default_ttl must be >= 0, got {default_ttl}")
        if max_memory_entries < 1:
            raise ValueError(f"max_memory_entries must be >= 1, got {max_memory_entries}")
        self._default_ttl = float(default_ttl)
        self._max_memory_entries = int(max_memory_entries)
        # In-memory backend: dict[key] = (bytes, expires_at_monotonic)
        self._memory: dict[str, tuple[bytes, float]] = {}
        # Order tracking for LRU eviction (insertion-ordered dict)
        self._memory_order: list[str] = []
        self._redis = _get_redis_client()

    @property
    def backend(self) -> str:
        """Active backend name: 'redis' or 'memory'."""
        return "redis" if self._redis is not None else "memory"

    @property
    def default_ttl(self) -> float:
        """Configured default TTL (seconds)."""
        return self._default_ttl

    # ── Public API ──────────────────────────────────────────────
    def get(self, device_id: str, frame_hash: str) -> bytes | None:
        """Retrieve cached JPEG bytes for ``device_id`` + ``frame_hash``.

        Args:
            device_id: Device identifier (e.g. "emulator-01").
            frame_hash: SHA-256 hash of the frame (see ``compute_frame_hash``).

        Returns:
            Cached bytes, or None on miss / expiry.
        """
        key = self._make_key(device_id, frame_hash)
        if self._redis is not None:
            try:
                value = self._redis.get(key)
                if value is not None:
                    return bytes(value)
                # Redis miss (key absent / expired) — fall through to memory
                # in case a prior `set` failed Redis and was persisted there.
                # Symmetric with `set()`'s Redis-failure fallback.
            except Exception as exc:
                logger.warning("ScreenshotCache.get: Redis failed (%s), falling back to memory", exc)
                # Fall through to memory lookup
        return self._memory_get(key)

    def set(
        self,
        device_id: str,
        frame_hash: str,
        value: bytes,
        ttl: float | None = None,
    ) -> None:
        """Cache JPEG bytes for ``device_id`` + ``frame_hash``.

        Args:
            device_id: Device identifier.
            frame_hash: SHA-256 hash of the frame.
            value: JPEG-encoded bytes to cache.
            ttl: Override TTL in seconds. Defaults to ``default_ttl``.
        """
        if value is None:
            return
        key = self._make_key(device_id, frame_hash)
        effective_ttl = self._default_ttl if ttl is None else float(ttl)
        if effective_ttl < 0:
            raise ValueError(f"ttl must be >= 0, got {effective_ttl}")

        if self._redis is not None:
            try:
                # Redis setex requires integer seconds >= 1. Round to nearest
                # int and clamp to 1 to avoid `int(0.1)=0` triggering an
                # `ERR invalid expire time` rejection (which would silently
                # fall through to memory — masking real Redis issues).
                redis_ttl = max(1, int(round(effective_ttl)))
                self._redis.setex(key, redis_ttl, value)
                return
            except Exception as exc:
                logger.warning("ScreenshotCache.set: Redis failed (%s), falling back to memory", exc)
        self._memory_set(key, value, effective_ttl)

    def clear(self, device_id: str | None = None) -> int:
        """Clear cache entries.

        Args:
            device_id: If given, clear only entries for this device.
                If None, clear all entries.

        Returns:
            Number of entries cleared.
        """
        if self._redis is not None:
            return self._redis_clear(device_id)
        return self._memory_clear(device_id)

    def size(self, device_id: str | None = None) -> int:
        """Return current cache size (entry count).

        Args:
            device_id: If given, count only entries for this device.

        Returns:
            Entry count. For Redis, this is approximate (SCAN-based).
        """
        if self._redis is not None:
            return self._redis_size(device_id)
        return self._memory_size(device_id)

    # ── Internal: key construction ─────────────────────────────
    @classmethod
    def _make_key(cls, device_id: str, frame_hash: str) -> str:
        """Build the cache key: 'screenshot:{device_id}:{frame_hash}'."""
        return f"{cls.KEY_PREFIX}:{device_id}:{frame_hash}"

    # ── Internal: in-memory backend ────────────────────────────
    def _memory_get(self, key: str) -> bytes | None:
        """Look up key in the in-memory backend, evicting expired entries."""
        entry = self._memory.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at <= time.monotonic():
            # Expired — evict and report miss.
            self._memory_pop(key)
            return None
        # Refresh LRU order.
        self._memory_touch(key)
        return value

    def _memory_set(self, key: str, value: bytes, ttl: float) -> None:
        """Store key → (value, expires_at) in the in-memory backend."""
        expires_at = time.monotonic() + ttl if ttl > 0 else float("inf")
        if key in self._memory:
            # Update in place; refresh LRU order.
            self._memory_touch(key)
        else:
            self._memory_order.append(key)
        self._memory[key] = (value, expires_at)
        # Evict oldest if over capacity.
        while len(self._memory) > self._max_memory_entries and self._memory_order:
            oldest = self._memory_order.pop(0)
            self._memory.pop(oldest, None)

    def _memory_clear(self, device_id: str | None) -> int:
        """Clear in-memory entries, optionally scoped to a device."""
        if device_id is None:
            count = len(self._memory)
            self._memory.clear()
            self._memory_order.clear()
            return count
        prefix = f"{self.KEY_PREFIX}:{device_id}:"
        keys_to_remove = [k for k in self._memory if k.startswith(prefix)]
        for k in keys_to_remove:
            self._memory_pop(k)
        return len(keys_to_remove)

    def _memory_size(self, device_id: str | None) -> int:
        """Count in-memory entries, optionally scoped to a device."""
        if device_id is None:
            return len(self._memory)
        prefix = f"{self.KEY_PREFIX}:{device_id}:"
        return sum(1 for k in self._memory if k.startswith(prefix))

    def _memory_pop(self, key: str) -> None:
        """Remove a key from both the dict and the LRU order list."""
        self._memory.pop(key, None)
        with contextlib.suppress(ValueError):
            self._memory_order.remove(key)  # not in order list (shouldn't happen, but be defensive)

    def _memory_touch(self, key: str) -> None:
        """Move key to the end of the LRU order list."""
        try:
            self._memory_order.remove(key)
            self._memory_order.append(key)
        except ValueError:
            self._memory_order.append(key)

    # ── Internal: Redis backend ────────────────────────────────
    def _redis_clear(self, device_id: str | None) -> int:
        """Clear Redis entries, optionally scoped to a device."""
        pattern = f"{self.KEY_PREFIX}:*" if device_id is None else f"{self.KEY_PREFIX}:{device_id}:*"
        count = 0
        cursor = 0
        while True:
            cursor, keys = self._redis.scan(cursor=cursor, match=pattern, count=100)  # type: ignore[union-attr]
            if keys:
                self._redis.delete(*keys)  # type: ignore[union-attr]
                count += len(keys)
            if cursor == 0:
                break
        return count

    def _redis_size(self, device_id: str | None) -> int:
        """Count Redis entries, optionally scoped to a device."""
        pattern = f"{self.KEY_PREFIX}:*" if device_id is None else f"{self.KEY_PREFIX}:{device_id}:*"
        count = 0
        cursor = 0
        while True:
            cursor, keys = self._redis.scan(cursor=cursor, match=pattern, count=100)  # type: ignore[union-attr]
            count += len(keys)
            if cursor == 0:
                break
        return count


# Module-level singleton for use by the screenshot capture path.
# Lazily instantiated on first access to avoid constructing a Redis client
# at import time (which would slow test collection / cold starts and could
# spam logs if Redis is unavailable during import).
_default_cache: ScreenshotCache | None = None


def get_default_cache() -> ScreenshotCache:
    """Return the process-wide default ``ScreenshotCache`` singleton.

    The screenshot stream (``client.handler._capture_one_device``) calls
    this to look up encoded JPEG bytes by ``frame_hash`` before invoking
    ``cv2.imencode``. Construction is deferred to first call so that
    environments without Redis (e.g. unit tests) do not pay the connection
    attempt cost at import time.
    """
    global _default_cache
    if _default_cache is None:
        _default_cache = ScreenshotCache()
    return _default_cache
