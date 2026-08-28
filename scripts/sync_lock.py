"""sync_lock.py — GAF cross-platform file lock (v8.4 M1.G).

This module provides a small, robust file-lock context manager used by
`sync_ai_memory.py` (and friends) to coordinate concurrent runs of the
synchronizer. Without a lock, two AI agents running `python
scripts/bootstrap/sync_ai_memory.py` at the same time can race when both read
and write `sync-state.json`, which corrupts the appended history and
silently loses evidence (N106 family).

Backends (auto-selected per platform)
-------------------------------------
- **Linux / macOS** → `fcntl.flock(LOCK_EX | LOCK_NB)` on an open file
  descriptor. `flock` is advisory (cooperating processes only) but
  atomic on the same host; perfect for the GAF single-repo use case.
- **Windows** → `msvcrt.locking(fd, LK_NBLCK, 1)`. Locks a single
  byte at offset 0. We use a sidecar `.sync.lock` file dedicated to
  the lock so we never block the real state file.

Both backends raise `LockTimeout` if the lock cannot be acquired
within the configured timeout (default 5s). All errors are surfaced
with a clear remediation hint rather than the bare OSError traceback.

Threading note
--------------
A single OS file lock is **process-level** — it does NOT synchronize
threads within the same process. Callers that spawn worker threads
should additionally take a `threading.Lock` if their state mutation
is not naturally thread-safe. `sync_ai_memory.py` only forks the GIL
on I/O, so a single process-level lock is sufficient there.

Typical use::

    from sync_lock import SyncLock, LockTimeout

    try:
        with SyncLock(repo_root / ".ai-memory" / ".sync.lock", timeout=5.0) as lock:
            update_sync_state(repo_root, summary)
    except LockTimeout as e:
        print(f"❌ sync_ai_memory: {e}", file=sys.stderr)
        return 1
"""
from __future__ import annotations

import contextlib
import errno
import os
import sys
import time
from pathlib import Path
from typing import Iterator, Optional

# Reuse the cross-platform UTF-8 fix used by every other GAF script
# (see N92 in failure-modes.md). Importing it eagerly applies the
# reconfigure so subsequent `print()` calls don't mojibake on Windows.
import _encoding_safe  # noqa: F401  (side-effect import)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LockTimeout(RuntimeError):
    """Raised when the cross-platform file lock cannot be acquired
    within the configured timeout window.

    The message includes remediation guidance so the AI can decide
    whether to retry, fail, or escalate to the user.
    """


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class _LockBackend:
    """Abstract base for cross-platform lock backends."""

    def __init__(self, fd: int, path: Path) -> None:
        self._fd = fd
        self._path = path

    def try_acquire(self) -> bool:
        """Try to acquire the lock non-blocking. Return True on success."""
        raise NotImplementedError

    def release(self) -> None:
        """Release the lock. Idempotent — calling twice is a no-op."""
        raise NotImplementedError

    @property
    def fd(self) -> int:
        return self._fd


class _UnixBackend(_LockBackend):
    """fcntl.flock-based backend (Linux + macOS)."""

    def try_acquire(self) -> bool:
        import fcntl  # local import — only available on POSIX

        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                return False
            raise
        return True

    def release(self) -> None:
        import fcntl  # local import — only available on POSIX

        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        except OSError:
            # Best-effort; on process exit the kernel releases flock anyway.
            pass


class _WindowsBackend(_LockBackend):
    """msvcrt.locking-based backend (Windows).

    `msvcrt.locking(fd, LK_NBLCK, nbytes)` locks `nbytes` bytes
    starting at the current file position. We always lock exactly 1
    byte; the file is dedicated to locking (no other content).
    """

    def try_acquire(self) -> bool:
        import msvcrt  # local import — only available on Windows

        try:
            msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            # Windows raises PermissionError (EACCES, WinError 33/53)
            # when another process holds the lock.
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK):
                return False
            raise
        return True

    def release(self) -> None:
        import msvcrt  # local import — only available on Windows

        try:
            msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            # Best-effort; on process exit the kernel releases the lock.
            pass


def _select_backend(fd: int, path: Path) -> _LockBackend:
    """Return the platform-appropriate backend for `fd`."""
    if os.name == "nt":
        return _WindowsBackend(fd, path)
    return _UnixBackend(fd, path)


# ---------------------------------------------------------------------------
# Public context manager
# ---------------------------------------------------------------------------


class SyncLock:
    """Cross-platform blocking file lock with timeout.

    Parameters
    ----------
    path:
        Lock file path. The file is created if missing (parents too).
    timeout:
        Maximum time in seconds to wait for the lock. ``0.0`` means
        try-once-and-fail (non-blocking semantics).
    poll_interval:
        Seconds between retry attempts. Default 0.1s — fast enough
        that short-lived locks are not perceptible, slow enough that
        a busy spin does not pin a CPU core.

    Raises
    ------
    LockTimeout
        If the lock cannot be acquired within `timeout` seconds.
    """

    DEFAULT_TIMEOUT = 5.0
    DEFAULT_POLL_INTERVAL = 0.1

    def __init__(
        self,
        path: Path,
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        self._path = Path(path)
        self._timeout = max(0.0, float(timeout))
        self._poll_interval = max(0.01, float(poll_interval))
        self._fd: Optional[int] = None
        self._backend: Optional[_LockBackend] = None
        self._acquired = False

    # -- context-manager protocol ----------------------------------------

    def __enter__(self) -> "SyncLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

    # -- core API --------------------------------------------------------

    def acquire(self) -> None:
        """Block up to `timeout` seconds to acquire the lock.

        Idempotent: calling `acquire()` on an already-held lock is a
        no-op (does not deadlock, does not extend the timeout).
        """
        if self._acquired:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Open with O_RDWR so the kernel knows we may read/write.
        # We never actually write any content; the file is a marker.
        self._fd = os.open(
            str(self._path),
            os.O_RDWR | os.O_CREAT,
            0o644,
        )
        self._backend = _select_backend(self._fd, self._path)

        deadline = time.monotonic() + self._timeout
        while True:
            if self._backend.try_acquire():
                self._acquired = True
                return
            if time.monotonic() >= deadline:
                # Clean up the fd we opened so we don't leak it.
                self._close_fd_quietly()
                raise LockTimeout(
                    f"could not acquire lock at {self._path} within "
                    f"{self._timeout:.1f}s. Another `sync_ai_memory` "
                    f"process is probably still running. Wait for it "
                    f"to finish or remove the stale lock file (only if "
                    f"no other process is using it)."
                )
            time.sleep(self._poll_interval)

    def release(self) -> None:
        """Release the lock and close the underlying file descriptor.

        Safe to call when the lock was never acquired.
        """
        if self._backend is not None and self._acquired:
            self._backend.release()
        self._acquired = False
        self._close_fd_quietly()

    # -- helpers ---------------------------------------------------------

    def _close_fd_quietly(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
            self._backend = None


# ---------------------------------------------------------------------------
# CLI helper (for ad-hoc testing & hook usage)
# ---------------------------------------------------------------------------


def _default_lock_path(repo_root: Optional[Path] = None) -> Path:
    """Resolve the canonical lock file path under `<repo>/.ai-memory/`.

    `repo_root` defaults to the GAF repo inferred from this file's
    location (parents[1] is the repo root for `scripts/sync_lock.py`).
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]
    return Path(repo_root) / ".ai-memory" / ".sync.lock"


@contextlib.contextmanager
def acquire_repo_lock(
    repo_root: Optional[Path] = None,
    timeout: float = SyncLock.DEFAULT_TIMEOUT,
) -> Iterator[SyncLock]:
    """Context manager that locks the repo-wide `.ai-memory/.sync.lock`.

    Use as::

        with acquire_repo_lock(timeout=3.0) as lock:
            update_sync_state(root, summary)
    """
    lock = SyncLock(_default_lock_path(repo_root), timeout=timeout)
    try:
        lock.acquire()
        yield lock
    finally:
        lock.release()


def main(argv: Optional[list] = None) -> int:
    """Tiny CLI: try to acquire the default lock, sleep, then release.

    Used by hand to verify the backend is wired correctly on the
    current platform (`python scripts/sync_lock.py`). Exits 0 on
    success, 1 on timeout, 2 on other errors.
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--hold",
        type=float,
        default=0.5,
        help="Seconds to hold the lock before releasing (default: 0.5)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=SyncLock.DEFAULT_TIMEOUT,
        help="Lock-acquisition timeout in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="GAF repo root (default: inferred from script path)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve() if args.root else None
    lock_path = _default_lock_path(repo_root)
    print(f"🔒 attempting lock at {lock_path} (timeout={args.timeout:.1f}s)")

    try:
        lock = SyncLock(lock_path, timeout=args.timeout)
        with lock:
            print(f"✅ acquired; holding for {args.hold:.1f}s")
            time.sleep(args.hold)
            print("✅ released")
        return 0
    except LockTimeout as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"❌ unexpected OS error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
