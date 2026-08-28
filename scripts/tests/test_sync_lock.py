"""test_sync_lock.py — Tests for the M1.G cross-platform file lock.

These tests cover the four contract promises of `SyncLock`:

1. **Acquisition + release** — a single holder gets the lock and
   releases it cleanly via context-manager protocol.
2. **Mutual exclusion** — a second holder on the same path blocks
   (raises `LockTimeout` once the timeout elapses).
3. **Idempotent re-acquire** — calling `acquire()` on an already-held
   lock is a no-op (does not deadlock).
4. **Concurrent processes** — fork/spawn a child that holds the lock
   and verify the parent is blocked. This is the actual M1.G use
   case: two AI agents running `sync_ai_memory.py` simultaneously.
"""
from __future__ import annotations

import multiprocessing
import sys
import tempfile
import time
import unittest
from pathlib import Path

import pytest

# Make the scripts package importable when pytest runs from the repo root.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from sync_lock import LockTimeout, SyncLock  # noqa: E402

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Pure-Python tests (no child process)
# ---------------------------------------------------------------------------


class SyncLockBasicTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.lock_path = self.tmp_path / "test.lock"

    def test_acquire_release(self):
        """Single holder acquires and releases cleanly via `with`."""
        with SyncLock(self.lock_path, timeout=1.0):
            # Lock file should exist while the context is active
            self.assertTrue(self.lock_path.exists())
        # After exit, the underlying fd was closed (file may still
        # exist as a side effect, but the lock is no longer held)
        self.assertTrue(self.lock_path.exists())

    def test_reentrant_acquire_is_noop(self):
        """Calling `acquire()` twice on the same instance must not deadlock."""
        lock = SyncLock(self.lock_path, timeout=1.0)
        lock.acquire()
        try:
            lock.acquire()  # second call returns immediately
            lock.acquire()  # and a third
        finally:
            lock.release()
        # And we can take it again after release
        with SyncLock(self.lock_path, timeout=1.0):
            pass

    def test_release_without_acquire_is_safe(self):
        """`release()` on a never-acquired lock is a no-op (no AttributeError)."""
        lock = SyncLock(self.lock_path, timeout=1.0)
        lock.release()  # must not raise

    def test_two_holders_serialized(self):
        """Sequential acquires (after release) work; second waits for first."""
        with SyncLock(self.lock_path, timeout=1.0):
            pass
        # The lock is now free; another holder should get it immediately
        with SyncLock(self.lock_path, timeout=1.0):
            pass


# ---------------------------------------------------------------------------
# Mutual-exclusion tests (require child process to actually contend)
# ---------------------------------------------------------------------------


def _child_hold_then_exit(lock_path: str, hold_seconds: float, ready_q) -> None:
    """Helper run in a child process: acquire lock, signal ready, hold, release."""
    from sync_lock import SyncLock  # local import — fresh interpreter

    lock = SyncLock(Path(lock_path), timeout=2.0)
    try:
        lock.acquire()
    except LockTimeout:
        ready_q.put(("timeout",))
        return
    ready_q.put(("acquired",))
    time.sleep(hold_seconds)
    lock.release()
    ready_q.put(("released",))


class SyncLockMutualExclusionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_path = Path(self._tmp.name)
        self.lock_path = self.tmp_path / "contend.lock"

    def test_second_holder_times_out(self):
        """A second `SyncLock` on a held path raises `LockTimeout`."""
        ctx = multiprocessing.get_context("spawn")
        ready_q = ctx.Queue()
        proc = ctx.Process(
            target=_child_hold_then_exit,
            args=(str(self.lock_path), 1.0, ready_q),
        )
        proc.start()
        try:
            # Wait for the child to confirm it has the lock
            kind, *_ = ready_q.get(timeout=5.0)
            self.assertEqual(kind, "acquired")

            # Now try to acquire in the parent — short timeout
            start = time.monotonic()
            with self.assertRaises(LockTimeout):
                with SyncLock(self.lock_path, timeout=0.3, poll_interval=0.05):
                    pass
            elapsed = time.monotonic() - start
            # Should have waited ~timeout, not blocked indefinitely
            self.assertGreaterEqual(elapsed, 0.2)
        finally:
            # Wait for the child to release
            kind, *_ = ready_q.get(timeout=5.0)
            self.assertEqual(kind, "released")
            proc.join(timeout=5.0)
            self.assertFalse(proc.is_alive(), "child process should have exited")

    def test_second_holder_eventually_succeeds(self):
        """If the first holder releases, the second can acquire."""
        ctx = multiprocessing.get_context("spawn")
        ready_q = ctx.Queue()
        proc = ctx.Process(
            target=_child_hold_then_exit,
            args=(str(self.lock_path), 0.5, ready_q),
        )
        proc.start()
        try:
            kind, *_ = ready_q.get(timeout=5.0)
            self.assertEqual(kind, "acquired")
            # Wait for the child to release (total ~0.5s)
            kind, *_ = ready_q.get(timeout=5.0)
            self.assertEqual(kind, "released")
            proc.join(timeout=5.0)

            # Now the parent should get the lock with a short timeout
            with SyncLock(self.lock_path, timeout=1.0):
                pass  # success
        finally:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2.0)


if __name__ == "__main__":
    unittest.main()
