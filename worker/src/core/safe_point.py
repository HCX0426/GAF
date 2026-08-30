"""Safe-point checker — cancellation-aware pause/resume abstraction.

Phase 6.1 implements the ``SafePointChecker`` class per
``task-cancel-design.md`` §3.2. It wraps a ``threading.Event`` and
provides three convenience methods used by chain / state-machine
executors:

  * ``check()`` — non-blocking poll
  * ``wait_for_safe_point(timeout)`` — blocking wait
  * ``raise_if_cancelled()`` — raise ``TaskCancelledError`` if set

The existing ``PipelineEngine`` (``worker/src/engine/engine.py``) inlines
``if self._cancel_event.is_set():`` checks at multiple safe points
(lines 261, 275, 317, 366). ``SafePointChecker`` is offered as a
reusable wrapper for new executors that want a uniform abstraction
without re-implementing the same Event introspection. ``PipelineEngine``
is NOT refactored in this phase — its inline checks remain unchanged
(they work, and refactoring a hot path without benchmarking is risky).
"""

import logging
import threading

logger = logging.getLogger(__name__)


class TaskCancelledError(Exception):
    """Raised when a task is cancelled at a safe point.

    Caught by ``TaskOrchestrator.execute_pipeline()`` to translate
    cancellation into a ``CANCELLED`` task result rather than a
    ``FAILED`` one.
    """


class SafePointChecker:
    """Safe-point checker wrapping a ``threading.Event`` for cancellation.

    Example::

        cancel_event = threading.Event()
        checker = SafePointChecker(cancel_event)

        # In an execute loop:
        while step_index < len(steps):
            checker.raise_if_cancelled()
            ...  # execute step
            checker.raise_if_cancelled()

        # Or to wait for a safe point with timeout:
        if checker.wait_for_safe_point(timeout=5.0):
            raise TaskCancelledError("Cancelled during wait")
    """

    def __init__(self, cancel_event: threading.Event):
        """Construct the checker.

        Args:
            cancel_event: The ``threading.Event`` to wrap. Typically
                ``PipelineEngine._cancel_event`` or
                ``TaskOrchestrator``'s cancel event.
        """
        self._cancel_event = cancel_event

    @property
    def cancel_event(self) -> threading.Event:
        """The underlying ``threading.Event`` (read-only)."""
        return self._cancel_event

    def check(self) -> bool:
        """Non-blocking check whether cancellation has been requested.

        Returns:
            ``True`` if ``cancel_event`` is set, ``False`` otherwise.
        """
        return self._cancel_event.is_set()

    def wait_for_safe_point(self, timeout: float = 5.0) -> bool:
        """Block until cancellation arrives or ``timeout`` elapses.

        Used to interrupt ``wait`` / ``delay`` nodes: call this with
        the remaining wait time. If it returns ``True``, cancellation
        arrived; if ``False``, the timeout elapsed cleanly.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            ``True`` if ``cancel_event`` is set (cancellation arrived),
            ``False`` if the timeout elapsed without cancellation.
        """
        return self._cancel_event.wait(timeout=timeout)

    def raise_if_cancelled(self, message: str | None = None) -> None:
        """Raise ``TaskCancelledError`` if cancellation has been requested.

        Called at safe points (node boundaries, loop iterations, state
        transitions). If the cancel event is set, raises immediately;
        otherwise returns normally.

        Args:
            message: Optional override for the exception message.
                Defaults to ``"Task cancelled at safe point"``.

        Raises:
            TaskCancelledError: If ``cancel_event.is_set()`` is True.
        """
        if self._cancel_event.is_set():
            raise TaskCancelledError(
                message or "Task cancelled at safe point"
            )

    def reset(self) -> None:
        """Clear the cancel event.

        Useful when reusing the checker across multiple executions
        (e.g. orchestrator runs a new task after the previous one was
        cancelled).
        """
        self._cancel_event.clear()
