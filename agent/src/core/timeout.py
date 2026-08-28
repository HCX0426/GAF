"""Timeout protection for DLL calls and other blocking operations.

Provides `call_with_timeout()` — a thread-based timeout wrapper that can
interrupt any callable, including ctypes DLL calls that don't natively
support timeouts.

Reference: MaaFramework SeizeInput timeout mechanism + Alas WorkerPool
           (module/device/method/pool.py Job.get_or_kill).

Usage:
    from core.timeout import call_with_timeout, TimeoutError

    # Call a ctypes DLL function with a 5-second timeout
    pixels = call_with_timeout(
        lib.nemu_capture_display,
        timeout_sec=5.0,
        connect_id, display_id, length, w_ptr, h_ptr, px_ptr,
    )

    # Apply via decorator
    from core.timeout import with_timeout

    @with_timeout(timeout_sec=5.0)
    def capture(self): ...
"""

import logging
import threading
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TimeoutError(Exception):
    """Raised when a call exceeds its timeout.

    Note: subclasses the built-in TimeoutError alias to remain compatible
    with `except TimeoutError` blocks. We define our own so that callers
    can `from core.timeout import TimeoutError` and catch both.
    """


def call_with_timeout(
    func: Callable[..., T],
    timeout_sec: float,
    *args,
    **kwargs,
) -> T:
    """Call `func(*args, **kwargs)` with a hard timeout.

    Implementation: runs `func` in a daemon thread; if it doesn't return
    within `timeout_sec`, raises TimeoutError. The daemon thread continues
    running in the background (cannot be hard-killed in CPython), but the
    caller is unblocked.

    For socket-based calls, prefer `socket.settimeout()` directly — it
    releases the GIL and is cheaper. This utility is intended for
    non-interruptible calls (e.g. ctypes DLL functions like
    `nemu_capture_display` and `ldopengl_capture`).

    Args:
        func: The callable to invoke.
        timeout_sec: Maximum seconds to wait. <= 0 means no timeout
            (call `func` directly).
        *args, **kwargs: Forwarded to `func`.

    Returns:
        The return value of `func`.

    Raises:
        TimeoutError: If `func` doesn't return within `timeout_sec`.
        Any exception raised by `func` (propagated to caller).
    """
    if timeout_sec <= 0:
        return func(*args, **kwargs)

    result_container: dict = {}
    done_event = threading.Event()

    def _runner() -> None:
        try:
            result_container["value"] = func(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 — re-raised below
            result_container["error"] = exc
        finally:
            done_event.set()

    thread = threading.Thread(
        target=_runner,
        name=f"timeout-{getattr(func, '__name__', 'call')}",
        daemon=True,
    )
    thread.start()
    done_event.wait(timeout=timeout_sec)

    if not done_event.is_set():
        func_name = getattr(func, "__name__", repr(func))
        logger.warning(
            "[%s] timed out after %.2fs (thread continues in background)",
            func_name,
            timeout_sec,
        )
        raise TimeoutError(
            f"{func_name} did not return within {timeout_sec}s"
        )

    if "error" in result_container:
        raise result_container["error"]
    return result_container.get("value")


def with_timeout(timeout_sec: float) -> Callable:
    """Decorator form of `call_with_timeout`.

    Args:
        timeout_sec: Maximum seconds to wait. The decorated function's
            own return value or exception is propagated.

    Example:
        @with_timeout(timeout_sec=5.0)
        def capture(self): ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return call_with_timeout(func, timeout_sec, *args, **kwargs)

        return wrapper

    return decorator
