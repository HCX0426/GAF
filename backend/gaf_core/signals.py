"""Signal handlers for performance monitoring.

Registered in ``gaf_core.apps.GafCoreConfig.ready()``.

Provides:
- Database query timing via ``django.db.backends.signals``
- Celery task timing via Celery's ``task_prerun`` / ``task_postrun`` signals
"""

from __future__ import annotations

import logging
import time

from django.db.backends.signals import connection_created

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Database query timing
# ------------------------------------------------------------------

# Threshold for slow query logging (milliseconds)
SLOW_QUERY_THRESHOLD_MS = 50.0


def install_db_query_timing() -> None:
    """Install database query timing via Django ``execute_wrapper``.

    Uses Django 4.2+ ``connection.execute_wrapper()`` API to wrap every
    ``execute()`` / ``executemany()`` call on all connections with timing.
    """

    def _register_wrapper(connection=None, **kwargs):  # noqa: ARG001
        """Register a timing wrapper on a single connection."""
        if connection is None:
            return

        try:
            wrapper = connection.execute_wrapper
        except AttributeError:
            return

        def _timing_wrapper(execute, sql, params, many, context):  # noqa: ARG001
            """Wrap a single execute/executemany call with timing."""
            start = time.monotonic()
            try:
                return execute(sql, params, many, context)
            finally:
                elapsed_ms = (time.monotonic() - start) * 1000.0
                from gaf_core.perf_monitor import PerformanceMonitor

                PerformanceMonitor.get_instance().record(
                    "db.query", elapsed_ms, {"sql": str(sql)[:200]},
                )
                if elapsed_ms > SLOW_QUERY_THRESHOLD_MS:
                    batch_note = f" (batch={len(params)})" if many and params else ""
                    logger.info(
                        "SLOW QUERY (%.1fms > %s%s): %s",
                        elapsed_ms, f"{SLOW_QUERY_THRESHOLD_MS:.0f}ms",
                        batch_note, str(sql)[:300],
                    )

        wrapper(_timing_wrapper)

    # Register on every new connection.
    connection_created.connect(_register_wrapper, weak=False)


# ------------------------------------------------------------------
# Celery task timing
# ------------------------------------------------------------------


def install_celery_task_timing() -> None:
    """Install Celery task timing via ``task_prerun`` / ``task_postrun``.

    Measures queue wait time and execution time for each Celery task.
    """
    try:
        from celery.signals import task_postrun, task_prerun
    except ImportError:
        logger.debug("Celery not available, skipping task timing")
        return

    # Store task start times in a thread-local dict
    import threading
    _task_start_times: dict[str, float] = {}
    _task_lock = threading.Lock()

    @task_prerun.connect(weak=False)
    def _on_task_prerun(task_id=None, task=None, **kwargs):  # noqa: ARG001
        """Record task start time."""
        with _task_lock:
            _task_start_times[task_id] = time.monotonic()

    @task_postrun.connect(weak=False)
    def _on_task_postrun(task_id=None, task=None, **kwargs):  # noqa: ARG001
        """Record task execution time."""
        with _task_lock:
            start = _task_start_times.pop(task_id, None)
        if start is None:
            return
        elapsed_ms = (time.monotonic() - start) * 1000.0
        from gaf_core.perf_monitor import PerformanceMonitor

        task_name = task.name if task else "unknown"
        PerformanceMonitor.get_instance().record(
            "celery.task.execute", elapsed_ms,
            {"task": task_name, "task_id": task_id},
        )
