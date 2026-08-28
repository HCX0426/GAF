"""Bounded async-call helpers for the sync side of the backend (TD-396).

channels_redis can wedge on a half-open TCP connection: ``group_send``
awaits forever and the coroutine may ignore ``asyncio.wait_for``
cancellation (the underlying socket read never reaches an await point
that accepts CancelledError). From a sync context (request thread,
logging handler, dispatch_task) that hang stalls the whole thread.

Rather than relying on cooperative cancellation, we park the stuck
coroutine on a shared worker thread and give the *caller* a hard
wall-clock deadline via ``concurrent.futures.Future.result(timeout=)``.
On timeout the worker thread is abandoned (it can never finish) — the
calling thread returns and the service keeps responding. Callers must
back off after a timeout so abandoned threads stay bounded (~1 every
60-300s at most, per call site).
"""

import concurrent.futures

from asgiref.sync import async_to_sync

_logger = None


def __getattr__(name: str):
    """Lazy logger import to avoid a circular import at module load."""
    if name == "logger":
        global _logger
        if _logger is None:
            import logging
            _logger = logging.getLogger(__name__)
        return _logger
    raise AttributeError(name)


# Shared workers. max_workers=2 so a wedged broadcast doesn't block a
# concurrent dispatch; calls queue up but each caller still enforces its
# own timeout (queued time counts toward it).
_ASYNC_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="gaf-async-bounded",
)


def call_async_with_timeout(coro_factory, timeout: float = 3.0):
    """Run ``coro_factory()`` (a zero-arg coroutine factory) on a worker
    thread and wait up to ``timeout`` seconds for it.

    Returns the coroutine's result. Raises ``TimeoutError`` if the call
    exceeds ``timeout`` — the worker thread is left to hang on its own,
    never blocking the caller. Other exceptions propagate as-is.
    """
    future = _ASYNC_EXECUTOR.submit(lambda: async_to_sync(coro_factory)())
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        raise TimeoutError(
            f"async call exceeded {timeout}s (worker abandoned)"
        ) from None
