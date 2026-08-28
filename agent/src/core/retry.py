"""Alas-style retry decorator with exception classification.

Reference: AzurLaneAutoScript module/base/retry.py + module/device/method/utils.py

Features:
- Retry on specified exception types (`exception` tuple)
- Exception handler dispatch: `exception_handlers[type]` called before retry
  for recovery (e.g. ConnectionResetError -> adb_reconnect)
- Optional `on_retry` callback for logging/metrics
- Optional interrupt check (threading.Event or callable) for graceful shutdown
- Preserves function return type (no StepResult wrapping)

Difference from core.retry_decorator.with_retry_and_check:
- with_retry_and_check wraps chain-step methods and returns StepResult
- @retry here is a generic decorator that returns the function's native value
  and re-raises the last exception on exhaustion (Alas semantics).
"""

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

ExceptionTypes = type[BaseException] | tuple[type[BaseException], ...]

# ---------------------------------------------------------------------------
# Exception taxonomies for retry policies
# ---------------------------------------------------------------------------

# Network/IO exceptions that are usually transient and worth retrying.
NETWORK_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionError,
    BrokenPipeError,
    TimeoutError,
    OSError,
    ConnectionClosed,
)

# Screenshot paths may also raise RuntimeError from ctypes/DLL transient failures.
SCREENSHOT_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    NETWORK_RETRY_EXCEPTIONS + (RuntimeError,)
)

# Input paths may also raise RuntimeError from injection/DLL transient failures.
INPUT_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    NETWORK_RETRY_EXCEPTIONS + (RuntimeError,)
)


def retry(
    retries: int = 3,
    delay: float = 1.0,
    exception: ExceptionTypes = (Exception,),
    exception_handlers: dict | None = None,
    on_retry: Callable[[int, BaseException], None] | None = None,
    check_interrupt: Callable[[], bool] | None = None,
) -> Callable:
    """Alas-style retry decorator with exception classification.

    Args:
        retries: Max retry count (not counting the first attempt). Default 3.
        delay: Seconds to wait between retries. Default 1.0.
        exception: Exception type or tuple of types that trigger a retry.
            Other exceptions propagate immediately. Default (Exception,).
        exception_handlers: Dict mapping exception type -> recovery callback.
            The callback is invoked before retrying; if it raises, that
            exception propagates immediately (used to abort on unrecoverable
            errors or to perform reconnect before next attempt).
            Callback signature: handler(*args, **kwargs) -> None.
        on_retry: Optional callback(attempt, exc) invoked after each failure
            but before the sleep. Use for metrics/logging.
        check_interrupt: Optional callable returning True to abort retries.

    Returns:
        Decorator that retries the wrapped function on `exception` types.

    Examples:
        # Basic retry on ConnectionError
        @retry(retries=3, delay=1.0, exception=ConnectionError)
        def fetch(url): ...

        # Retry with handler dispatch (Alas pattern)
        @retry(
            retries=5,
            delay=2.0,
            exception=(ConnectionError, TimeoutError),
            exception_handlers={
                ConnectionResetError: lambda self: self.adb_reconnect(),
            },
        )
        def capture(self): ...
    """

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            return _async_retry_wrapper(
                func,
                retries=retries,
                delay=delay,
                exception=exception,
                exception_handlers=exception_handlers,
                on_retry=on_retry,
                check_interrupt=check_interrupt,
            )

        @wraps(func)
        def wrapper(*args, **kwargs):
            stop_event = _resolve_stop_event(args)
            last_exc: BaseException | None = None
            for attempt in range(retries + 1):
                if _should_interrupt(stop_event, check_interrupt):
                    if last_exc is not None:
                        raise last_exc
                    raise RuntimeError(
                        f"{func.__name__} interrupted before execution"
                    )
                try:
                    return func(*args, **kwargs)
                except exception as exc:
                    last_exc = exc
                    # Handler dispatch — recovery callback before retry
                    handler = _find_handler(exc, exception_handlers)
                    if handler is not None:
                        logger.debug(
                            "[%s] invoking handler %s for %s",
                            func.__name__,
                            getattr(handler, "__name__", repr(handler)),
                            type(exc).__name__,
                        )
                        handler(*args, **kwargs)  # may raise to abort
                    if attempt >= retries:
                        logger.warning(
                            "[%s] retries exhausted (%d): %s",
                            func.__name__,
                            retries,
                            exc,
                        )
                        raise
                    if on_retry is not None:
                        try:
                            on_retry(attempt + 1, exc)
                        except Exception:
                            logger.exception("on_retry callback failed")
                    logger.info(
                        "[%s] attempt %d/%d failed: %s; retrying in %.2fs",
                        func.__name__,
                        attempt + 1,
                        retries + 1,
                        exc,
                        delay,
                    )
                    _interruptible_sleep(delay, stop_event)
            # Should be unreachable
            if last_exc is not None:
                raise last_exc
            raise RuntimeError(
                f"{func.__name__} exited retry loop unexpectedly"
            )

        return wrapper

    return decorator


def _async_retry_wrapper(
    func: Callable,
    retries: int,
    delay: float,
    exception: ExceptionTypes,
    exception_handlers: dict | None,
    on_retry: Callable[[int, BaseException], None] | None,
    check_interrupt: Callable[[], bool] | None,
) -> Callable:
    """Async variant of the retry decorator for coroutine functions."""

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        stop_event = _resolve_stop_event(args)
        last_exc: BaseException | None = None
        for attempt in range(retries + 1):
            if _should_interrupt(stop_event, check_interrupt):
                if last_exc is not None:
                    raise last_exc
                raise RuntimeError(
                    f"{func.__name__} interrupted before execution"
                )
            try:
                return await func(*args, **kwargs)
            except exception as exc:
                last_exc = exc
                handler = _find_handler(exc, exception_handlers)
                if handler is not None:
                    logger.debug(
                        "[%s] invoking handler %s for %s",
                        func.__name__,
                        getattr(handler, "__name__", repr(handler)),
                        type(exc).__name__,
                    )
                    handler(*args, **kwargs)
                if attempt >= retries:
                    logger.warning(
                        "[%s] retries exhausted (%d): %s",
                        func.__name__,
                        retries,
                        exc,
                    )
                    raise
                if on_retry is not None:
                    try:
                        on_retry(attempt + 1, exc)
                    except Exception:
                        logger.exception("on_retry callback failed")
                logger.info(
                    "[%s] attempt %d/%d failed: %s; retrying in %.2fs",
                    func.__name__,
                    attempt + 1,
                    retries + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(
            f"{func.__name__} exited retry loop unexpectedly"
        )

    return async_wrapper


def _resolve_stop_event(args: tuple) -> threading.Event | None:
    """Look for self._stop_event on the bound instance, if any."""
    if not args:
        return None
    self_obj = args[0]
    return getattr(self_obj, "_stop_event", None)


def _find_handler(
    exc: BaseException,
    exception_handlers: dict | None,
) -> Callable | None:
    """Find the most specific handler for `exc` in `exception_handlers`."""
    if not exception_handlers:
        return None
    # Match the most specific exception type first
    matching = [
        (exc_type, handler)
        for exc_type, handler in exception_handlers.items()
        if isinstance(exc, exc_type)
    ]
    if not matching:
        return None
    # Pick the most derived class (deepest in MRO)
    matching.sort(key=lambda pair: len(pair[0].__mro__), reverse=True)
    return matching[0][1]


def _should_interrupt(
    stop_event: threading.Event | None,
    check_interrupt: Callable[[], bool] | None,
) -> bool:
    """Check whether retries should be aborted."""
    if check_interrupt is not None:
        try:
            return bool(check_interrupt())
        except Exception:
            return False
    if stop_event is not None:
        return stop_event.is_set()
    return False


def _interruptible_sleep(
    seconds: float,
    stop_event: threading.Event | None,
) -> None:
    """Sleep that can be interrupted by stop_event."""
    if stop_event is not None:
        stop_event.wait(timeout=seconds)
    else:
        time.sleep(seconds)


# ---------------------------------------------------------------------------
# Preset retry decorators for common GAF operation categories
# ---------------------------------------------------------------------------


def retry_screenshot(
    retries: int = 2,
    delay: float = 0.5,
    **kwargs: Any,
) -> Callable:
    """Preset @retry for screenshot capture paths.

    Tuned for low-latency visual capture: short delay, few retries, and
    retries on network/IO plus transient RuntimeError from ctypes/DLL calls.

    Example:
        @retry_screenshot()
        def _capture_screencap(self) -> np.ndarray | None: ...
    """
    return retry(
        retries=retries,
        delay=delay,
        exception=SCREENSHOT_RETRY_EXCEPTIONS,
        **kwargs,
    )


def retry_input(
    retries: int = 2,
    delay: float = 0.2,
    **kwargs: Any,
) -> Callable:
    """Preset @retry for input injection paths.

    Tuned for click/swipe/key operations: very short delay so retries do not
    perturb timing-sensitive gesture sequences.

    Example:
        @retry_input()
        def _input_adb_click(self, x: int, y: int) -> None: ...
    """
    return retry(
        retries=retries,
        delay=delay,
        exception=INPUT_RETRY_EXCEPTIONS,
        **kwargs,
    )


def retry_network(
    retries: int = 3,
    delay: float = 1.0,
    **kwargs: Any,
) -> Callable:
    """Preset @retry for network/WebSocket/API client calls.

    Tuned for server/agent communication: longer backoff and more attempts
    because the remote peer may be restarting or transiently unreachable.

    Example:
        @retry_network()
        def send_message(self, msg_type: str, data: dict) -> None: ...
    """
    return retry(
        retries=retries,
        delay=delay,
        exception=NETWORK_RETRY_EXCEPTIONS,
        **kwargs,
    )
