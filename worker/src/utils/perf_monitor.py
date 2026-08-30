"""Performance monitoring for GAF agent.

Provides ``Timer`` (context manager) and ``PerfMonitor`` (singleton)
for measuring and recording execution times across the agent pipeline.

Usage::

    from utils.perf_monitor import Timer, PerfMonitor

    with Timer("pipeline.node.screenshot", tags={"node_id": "n1"}):
        img = device.capture()

    # Get aggregates at any point
    mon = PerfMonitor.get_instance()
    aggregates = mon.get_aggregates()
    print(aggregates["pipeline.node.screenshot"]["p95_ms"])
"""

from __future__ import annotations

import math
import os
import threading
import time
from typing import Any


class PerfMonitor:
    """Per-process singleton for recording and aggregating performance metrics.

    **Modes** (auto-detected from ``GAF_CELERY_MODE``):

    - **development** (``GAF_CELERY_MODE=eager``, default): every measurement
      is recorded to memory **and** written as a ``perf.timer`` event to the
      structured JSONL log (via ``StructuredLogger.log_orchestrator_event``).
    - **production** (``GAF_CELERY_MODE=celery``): only in-memory aggregation;
      no JSONL perf events are written.

    Thread-safe: all public methods use a per-instance lock.
    """

    MODE_PRODUCTION = "production"
    MODE_DEVELOPMENT = "development"

    _instance: PerfMonitor | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._mode = self._detect_mode()
        self._records: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        # StructuredLogger reference (set per-pipeline-execution).
        self._structured_logger: Any = None
        self._start_time = time.monotonic()

    # ------------------------------------------------------------------
    # Singleton management
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> PerfMonitor:
        """Return the global PerfMonitor singleton."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Replace the singleton with a fresh instance (for testing)."""
        with cls._instance_lock:
            cls._instance = cls()

    # ------------------------------------------------------------------
    # Mode detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_mode() -> str:
        mode = os.environ.get("GAF_CELERY_MODE", "eager")
        return (
            PerfMonitor.MODE_PRODUCTION
            if mode == "celery"
            else PerfMonitor.MODE_DEVELOPMENT
        )

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_development(self) -> bool:
        return self._mode == self.MODE_DEVELOPMENT

    # ------------------------------------------------------------------
    # StructuredLogger integration
    # ------------------------------------------------------------------

    def set_structured_logger(self, logger: Any) -> None:
        """Set the StructuredLogger for perf event output (dev mode only).

        Called once per pipeline execution so perf events are written to
        the same JSONL file as node events.
        """
        self._structured_logger = logger

    def clear_structured_logger(self) -> None:
        """Clear the StructuredLogger reference (e.g. after pipeline ends)."""
        self._structured_logger = None

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self, name: str, elapsed_ms: float, tags: dict[str, Any] | None = None,
    ) -> None:
        """Record a performance measurement.

        Args:
            name: Measurement name (e.g. ``"pipeline.node.screenshot"``).
            elapsed_ms: Elapsed time in milliseconds.
            tags: Optional tags (e.g. ``{"node_id": "n1", "node_type": "tmpl"}``).
        """
        with self._lock:
            if name not in self._records:
                self._records[name] = []
            self._records[name].append(elapsed_ms)

        # Development mode: write perf event to structured JSONL.
        if self.is_development and self._structured_logger is not None:
            self._write_perf_event(name, elapsed_ms, tags)

    def _write_perf_event(
        self, name: str, elapsed_ms: float, tags: dict[str, Any] | None,
    ) -> None:
        """Best-effort write of a perf.timer event to the structured logger."""
        try:
            extra: dict[str, Any] = {
                "perf_name": name,
                "elapsed_ms": round(elapsed_ms, 2),
            }
            if tags:
                # Merge tags into extra, prefixing with ``perf_`` to avoid
                # collision with ``log_orchestrator_event`` reserved fields.
                for k, v in tags.items():
                    extra[f"perf_{k}"] = v
            self._structured_logger.log_orchestrator_event(
                event="perf.timer",
                success=True,
                elapsed_ms=round(elapsed_ms, 2),
                extra=extra,
            )
        except Exception:
            pass  # Best-effort: never block pipeline for perf logging.

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def get_aggregates(self) -> dict[str, dict[str, float]]:
        """Return aggregated statistics for all recorded measurements.

        Returns:
            Dict mapping measurement name → ``{count, avg_ms, p50_ms,
            p95_ms, p99_ms, max_ms}``.
        """
        with self._lock:
            return {
                name: _compute_stats(values)
                for name, values in self._records.items()
            }

    def get_uptime_seconds(self) -> float:
        """Return seconds since this monitor was created."""
        return time.monotonic() - self._start_time

    def reset(self) -> None:
        """Clear all recorded measurements (preserves mode and logger)."""
        with self._lock:
            self._records.clear()
        self._start_time = time.monotonic()


class Timer:
    """Context manager that measures elapsed time and records to PerfMonitor.

    Usage::

        with Timer("pipeline.node.screenshot", tags={"node_id": "n1"}):
            img = device.capture()

        # Access elapsed time after the block
        with Timer("my.op") as t:
            do_something()
        print(f"Took {t.elapsed_ms:.1f}ms")
    """

    def __init__(
        self, name: str, tags: dict[str, Any] | None = None,
    ) -> None:
        self._name = name
        self._tags = tags or {}
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> Timer:
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: object) -> None:
        self.elapsed_ms = (time.monotonic() - self._start) * 1000.0
        PerfMonitor.get_instance().record(
            self._name, self.elapsed_ms, self._tags,
        )


def _compute_stats(values: list[float]) -> dict[str, float]:
    """Compute summary statistics for a list of elapsed times.

    Args:
        values: Elapsed times in milliseconds (unsorted ok).

    Returns:
        Dict with ``count``, ``avg_ms``, ``p50_ms``, ``p95_ms``,
        ``p99_ms``, ``max_ms``.
    """
    if not values:
        return {
            "count": 0, "avg_ms": 0.0, "p50_ms": 0.0,
            "p95_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0,
        }

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    avg = sum(sorted_vals) / n

    def _percentile(p: float) -> float:
        """Linear-interpolation percentile."""
        if n == 1:
            return sorted_vals[0]
        k = (p / 100.0) * (n - 1)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_vals[int(k)]
        return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)

    return {
        "count": n,
        "avg_ms": round(avg, 2),
        "p50_ms": round(_percentile(50), 2),
        "p95_ms": round(_percentile(95), 2),
        "p99_ms": round(_percentile(99), 2),
        "max_ms": round(sorted_vals[-1], 2),
    }
