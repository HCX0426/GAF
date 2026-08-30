"""P1-3 MuMu emulator NemuIpc keepalive — background heartbeat thread.

MuMu12's NemuIpc connection drops after ~30s of inactivity because the
emulator-side IPC endpoint reaps idle connections. Long-running pipelines
that don't take screenshots continuously (e.g., waiting for user input,
long sleeps, OCR processing) will hit "RPC invalid binding handle" (1783)
errors when they next try to capture.

This module provides a background thread that periodically pings the
emulator with a no-op `nemu_capture_display(display_id=0, length=0, nullptr)`
call to keep the connection alive. The ping reads zero bytes, so it's
near-instant (~1ms) and doesn't allocate a buffer.

Reference: Alas `nemu_ipc.py` keepalive mechanism.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# Default keepalive interval: 25 seconds (less than MuMu12's ~30s idle
# timeout, with a 5s safety margin for system load spikes).
DEFAULT_KEEPALIVE_INTERVAL_SEC = 25.0

# Minimum interval to prevent abuse.
MIN_KEEPALIVE_INTERVAL_SEC = 5.0


class NemuIpcKeepalive:
    """Background-thread keepalive for NemuIpc connections.

    Starts a daemon thread that pings the emulator periodically to keep
    the IPC connection alive during idle periods. Thread-safe: the
    ping loop uses a threading.Event for interruptible sleeps and a
    lock around connection state changes.

    Usage:
        keeper = NemuIpcKeepalive(
            ping_fn=my_device._nemu_ipc_ping,
            interval_sec=25.0,
        )
        keeper.start()
        # ... long-running operations ...
        keeper.stop()
    """

    def __init__(
        self,
        ping_fn: Callable[[], int],
        interval_sec: float = DEFAULT_KEEPALIVE_INTERVAL_SEC,
        on_failure: Callable[[int], None] | None = None,
    ) -> None:
        """Initialize the keepalive controller.

        Args:
            ping_fn: Callable that performs a no-op NemuIpc ping and
                returns the integer return code (0 = success). Typically
                a bound method like `device._nemu_ipc_ping`.
            interval_sec: Seconds between pings. Default 25s. Clamped
                to MIN_KEEPALIVE_INTERVAL_SEC.
            on_failure: Optional callback invoked when a ping returns
                a non-zero code. Receives the return code as argument.
        """
        self._ping_fn = ping_fn
        self._interval = max(interval_sec, MIN_KEEPALIVE_INTERVAL_SEC)
        self._on_failure = on_failure
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._running = False

    @property
    def interval(self) -> float:
        """Current keepalive interval (seconds)."""
        return self._interval

    @property
    def is_running(self) -> bool:
        """True if the keepalive thread is currently running."""
        return self._running and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start the keepalive thread (idempotent).

        If already running, this is a no-op. The thread is a daemon so
        it won't block process exit.
        """
        with self._lock:
            if self._running and self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="NemuIpcKeepalive",
                daemon=True,
            )
            self._running = True
            self._thread.start()
            logger.debug(
                "NemuIpc keepalive started (interval=%.1fs)", self._interval,
            )

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the keepalive thread and wait for it to exit.

        Args:
            timeout: Maximum seconds to wait for the thread to exit.
        """
        with self._lock:
            if not self._running:
                return
            self._stop_event.set()
            self._running = False
            thread = self._thread
            self._thread = None

        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
            if thread.is_alive():
                logger.warning(
                    "NemuIpc keepalive thread did not exit within %.1fs",
                    timeout,
                )
        logger.debug("NemuIpc keepalive stopped")

    def _run_loop(self) -> None:
        """Main keepalive loop — runs in background thread."""
        while not self._stop_event.is_set():
            # Interruptible sleep: returns True if event was set during wait.
            if self._stop_event.wait(timeout=self._interval):
                break

            try:
                ret = self._ping_fn()
                if ret != 0:
                    logger.warning(
                        "NemuIpc keepalive ping returned non-zero: %d", ret,
                    )
                    if self._on_failure is not None:
                        try:
                            self._on_failure(ret)
                        except Exception as exc:
                            logger.error(
                                "NemuIpc keepalive on_failure callback error: %s",
                                exc,
                            )
            except Exception as exc:
                # Don't kill the loop on ping errors — emulator may recover.
                logger.warning("NemuIpc keepalive ping error: %s", exc)

    def __enter__(self) -> NemuIpcKeepalive:
        """Context manager entry — starts the keepalive thread."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit — stops the keepalive thread."""
        self.stop()


def make_ping_fn(
    lib: ctypes.CDLL,
    connect_id_getter: Callable[[], int],
    timeout_sec: float = 5.0,
) -> Callable[[], int]:
    """Build a ping callable for NemuIpcKeepalive.

    The returned function calls `lib.nemu_capture_display` with
    length=0 and a null pixels pointer, which the emulator treats as a
    no-op query. This is the same call used by _nemu_ipc_get_resolution
    but with all output pointers nulled.

    Args:
        lib: Loaded external_renderer_ipc.dll CDLL instance.
        connect_id_getter: Callable that returns the current connect_id
            (e.g., lambda: device._nemu_ipc_connect_id). Returning 0
            means "not connected"; the ping will skip in that case.
        timeout_sec: DLL call timeout (passed to call_with_timeout).

    Returns:
        A callable that returns the integer return code from
        nemu_capture_display. Returns 0 (success) when connect_id is 0
        (no active connection — nothing to keep alive).
    """
    from core.timeout import TimeoutError, call_with_timeout

    def _ping() -> int:
        connect_id = connect_id_getter()
        if connect_id == 0:
            # Not connected — nothing to ping. Treat as success.
            return 0

        width_ptr = ctypes.pointer(ctypes.c_int(0))
        height_ptr = ctypes.pointer(ctypes.c_int(0))
        nullptr = ctypes.POINTER(ctypes.c_int)()

        try:
            ret = call_with_timeout(
                lib.nemu_capture_display,
                timeout_sec,
                connect_id,
                0,  # display_id
                0,  # length=0 → no-op query
                width_ptr,
                height_ptr,
                nullptr,
            )
            return int(ret)
        except TimeoutError:
            logger.warning("NemuIpc keepalive ping timed out")
            return -1  # Sentinel: timeout.
        except Exception as exc:
            logger.warning("NemuIpc keepalive ping exception: %s", exc)
            return -2  # Sentinel: exception.

    return _ping
