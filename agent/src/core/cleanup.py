"""Cleanup manager — priority-ordered resource cleanup stack.

Phase 6.2 implements the ``CleanupManager`` class per
``task-cancel-design.md`` §4.2. It maintains a stack of
``(priority, cleanup_fn)`` tuples and executes them in priority order
(highest first) on ``cleanup()``.

Use case: ``TaskOrchestrator.execute_task()`` registers cleanup
callbacks as resources are acquired (device locks, monitor threads,
temp directories), then calls ``cleanup()`` in a ``finally`` block
to guarantee release even on cancellation or exception.

Design §4.1 cleanup priorities:
  * 10 — device locks (highest)
  *  5 — monitor threads
  *  3 — temp files
  *  1 — memory caches (lowest)

Each cleanup function is called exactly once. Errors in one function
do not prevent subsequent cleanups from running — failures are
recorded in the result list and the stack is cleared regardless.

This module is the agent-side cleanup manager. Server-side cleanup
(resource locks in Redis, Celery task state) is handled separately
in ``backend/tasks/resource_lock.py`` and ``backend/tasks/services.py``.
"""

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Standard priority levels per design §4.1.
PRIORITY_DEVICE_LOCK = 10
PRIORITY_MONITOR_THREAD = 5
PRIORITY_TEMP_FILE = 3
PRIORITY_MEMORY_CACHE = 1


class CleanupManager:
    """Priority-ordered resource cleanup stack.

    Example::

        cleanup = CleanupManager()
        try:
            device_lock = resource_lock.acquire(device_id, task_id)
            cleanup.register(PRIORITY_DEVICE_LOCK,
                             lambda: resource_lock.release(device_id, task_id),
                             name="release_device_lock")

            monitor_thread = monitor_manager.start(...)
            cleanup.register(PRIORITY_MONITOR_THREAD,
                             monitor_manager.stop,
                             name="stop_monitor")

            result = engine.execute()
        finally:
            results = cleanup.cleanup()
            for r in results:
                logger.info("cleanup: %s", r)
    """

    def __init__(self):
        self._cleanup_stack: list[tuple[int, Callable[[], None], str]] = []

    def register(
        self,
        priority: int,
        cleanup_fn: Callable[[], None],
        name: str = "",
    ) -> None:
        """Register a cleanup function at the given priority.

        Higher priority functions run first (e.g. device locks release
        before temp files are deleted).

        Args:
            priority: Integer priority (higher = earlier execution).
                Use the ``PRIORITY_*`` constants for consistency.
            cleanup_fn: Zero-argument callable. Will be called exactly
                once during ``cleanup()``.
            name: Optional human-readable name for diagnostics. If
                empty, falls back to ``cleanup_fn.__name__``.
        """
        if not callable(cleanup_fn):
            raise TypeError(f"cleanup_fn must be callable, got {type(cleanup_fn)}")
        display_name = name or getattr(cleanup_fn, "__name__", "<anonymous>")
        self._cleanup_stack.append((priority, cleanup_fn, display_name))

    def cleanup(self) -> list[str]:
        """Execute all registered cleanup functions in priority order.

        Runs highest-priority first. Each function is wrapped in a
        try/except so one failure doesn't block subsequent cleanups.
        The stack is cleared at the end regardless of failures.

        Returns:
            List of result strings, one per registered cleanup:
            ``"✓ <name>"`` on success or ``"✗ <name>: <error>"`` on
            failure. Ordered by execution (highest priority first).
        """
        # Sort by priority descending (highest first)
        sorted_cleanups = sorted(
            self._cleanup_stack, key=lambda x: x[0], reverse=True
        )
        results: list[str] = []

        for priority, cleanup_fn, name in sorted_cleanups:
            try:
                cleanup_fn()
                results.append(f"✓ {name}")
                logger.debug("cleanup success: %s (priority=%d)", name, priority)
            except Exception as exc:
                results.append(f"✗ {name}: {exc}")
                logger.warning(
                    "cleanup failed: %s (priority=%d): %s", name, priority, exc,
                    exc_info=True,
                )

        self._cleanup_stack.clear()
        return results

    @property
    def pending_count(self) -> int:
        """Number of cleanup functions registered but not yet executed."""
        return len(self._cleanup_stack)

    def is_empty(self) -> bool:
        """Return ``True`` if no cleanups are pending."""
        return len(self._cleanup_stack) == 0

    def clear(self) -> None:
        """Discard all registered cleanups without executing them.

        Useful for tests or when the caller decides the resources are
        being managed by someone else.
        """
        self._cleanup_stack.clear()
