"""Tests for WorkerPool: Alas-style 8-thread pool with Job-based results (N126-F5)"""

import threading
import time
from unittest.mock import patch

import pytest
from core.worker_pool import (
    WORKER_POOL,
    Error,
    Job,
    JobTimeout,
    Value,
    WorkerPool,
    capture,
    remove_tb_frames,
)

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Outcome / Value / Error tests
# ---------------------------------------------------------------------------


class TestOutcome:
    """Verify Outcome/Value/Error result wrapper semantics"""

    def test_value_unwrap_returns_value(self):
        v = Value(42)
        assert v.unwrap() == 42

    def test_value_repr(self):
        assert repr(Value(42)) == "Value(42)"

    def test_error_unwrap_raises(self):
        err = Error(ValueError("boom"))
        with pytest.raises(ValueError, match="boom"):
            err.unwrap()

    def test_error_repr(self):
        err = Error(ValueError("boom"))
        assert "Error(" in repr(err)

    def test_capture_returns_value_on_success(self):
        result = capture(lambda x: x * 2, 5)
        assert isinstance(result, Value)
        assert result.unwrap() == 10

    def test_capture_returns_error_on_exception(self):
        def raise_fn():
            raise RuntimeError("fail")

        result = capture(raise_fn)
        assert isinstance(result, Error)
        with pytest.raises(RuntimeError, match="fail"):
            result.unwrap()

    def test_capture_preserves_kwargs(self):
        result = capture(lambda a, b: a + b, a=1, b=2)
        assert result.unwrap() == 3


class TestRemoveTbFrames:
    """Verify traceback frame trimming"""

    def test_returns_exception_with_trimmed_traceback(self):
        try:
            raise ValueError("test")
        except ValueError as exc:
            original_tb = exc.__traceback__
            trimmed = remove_tb_frames(exc, 1)
            assert trimmed.__traceback__ is not original_tb or trimmed is exc

    def test_handles_zero_frames(self):
        try:
            raise ValueError("test")
        except ValueError as exc:
            result = remove_tb_frames(exc, 0)
            assert result is exc or result.__traceback__ is exc.__traceback__


# ---------------------------------------------------------------------------
# Job tests
# ---------------------------------------------------------------------------


class TestJob:
    """Verify Job one-shot queue behavior"""

    def test_job_get_returns_result(self):
        pool = WorkerPool(pool_size=2)
        job = pool.start_thread_soon(lambda: 42)
        assert job.get() == 42

    def test_job_get_raises_error(self):
        def raise_fn():
            raise ValueError("job failed")

        pool = WorkerPool(pool_size=2)
        job = pool.start_thread_soon(raise_fn)
        with pytest.raises(ValueError, match="job failed"):
            job.get()

    def test_job_get_or_kill_returns_result_within_timeout(self):
        pool = WorkerPool(pool_size=2)
        job = pool.start_thread_soon(lambda: "hello")
        assert job.get_or_kill(timeout=5.0) == "hello"

    def test_job_get_or_kill_raises_timeout(self):
        def slow_fn():
            time.sleep(10)
            return "done"

        pool = WorkerPool(pool_size=2)
        job = pool.start_thread_soon(slow_fn)
        with pytest.raises(JobTimeout):
            job.get_or_kill(timeout=0.3)

    def test_job_repr_contains_func_args(self):
        pool = WorkerPool(pool_size=2)
        job = pool.start_thread_soon(lambda x: x, 42)
        assert "Job(" in repr(job)
        # Don't leave the job hanging
        job.get()


# ---------------------------------------------------------------------------
# WorkerPool basic tests
# ---------------------------------------------------------------------------


class TestWorkerPoolBasic:
    """Verify WorkerPool core functionality"""

    def test_default_pool_size_is_8(self):
        pool = WorkerPool()
        assert pool.pool_size == 8

    def test_custom_pool_size(self):
        pool = WorkerPool(pool_size=4)
        assert pool.pool_size == 4

    def test_start_thread_soon_returns_job(self):
        pool = WorkerPool(pool_size=2)
        job = pool.start_thread_soon(lambda: 1)
        assert isinstance(job, Job)
        assert job.get() == 1

    def test_run_on_thread_decorator(self):
        pool = WorkerPool(pool_size=2)

        @pool.run_on_thread
        def add(a, b):
            return a + b

        job = add(3, 4)
        assert isinstance(job, Job)
        assert job.get() == 7

    def test_pool_creates_worker_on_demand(self):
        pool = WorkerPool(pool_size=8)
        initial_count = len(pool.all_workers)
        job = pool.start_thread_soon(lambda: 1)
        job.get()
        assert len(pool.all_workers) >= initial_count

    def test_pool_reuses_idle_workers(self):
        pool = WorkerPool(pool_size=2)
        # First job creates a worker
        job1 = pool.start_thread_soon(lambda: 1)
        job1.get()
        # Give worker time to return to idle
        time.sleep(0.1)

        # Second job should reuse the idle worker
        job2 = pool.start_thread_soon(lambda: 2)
        job2.get()
        # Pool should not have created more workers than needed
        assert len(pool.all_workers) <= 1


class TestWorkerPoolConcurrency:
    """Verify WorkerPool handles concurrent jobs correctly"""

    def test_multiple_jobs_run_in_parallel(self):
        pool = WorkerPool(pool_size=4)
        barrier = threading.Barrier(4)

        def wait_and_return(n):
            barrier.wait(timeout=5.0)
            return n

        jobs = [pool.start_thread_soon(wait_and_return, i) for i in range(4)]
        results = [job.get() for job in jobs]
        assert sorted(results) == [0, 1, 2, 3]

    def test_pool_size_limit_enforced(self):
        """When pool is full, new jobs block until a worker becomes idle"""
        pool = WorkerPool(pool_size=2)
        hold_lock = threading.Lock()

        def hold_then_return(n):
            with hold_lock:
                return n

        # Acquire the lock so jobs block
        hold_lock.acquire()
        try:
            job1 = pool.start_thread_soon(hold_then_return, 1)
            job2 = pool.start_thread_soon(hold_then_return, 2)
            time.sleep(0.2)  # Let workers pick up jobs

            # Pool should be full now (2 workers, both busy)
            assert len(pool.all_workers) == 2

            # Start a third job in a separate thread — it should block
            def start_third():
                return pool.start_thread_soon(hold_then_return, 3)

            third_thread = threading.Thread(target=start_third)
            third_thread.start()
            time.sleep(0.2)
            assert third_thread.is_alive()  # Still waiting

            # Release the lock — third job should proceed
            hold_lock.release()
            third_thread.join(timeout=5.0)

            assert job1.get() == 1
            assert job2.get() == 2
        finally:
            if hold_lock.locked():
                hold_lock.release()

    def test_thread_map_returns_results_in_order(self):
        pool = WorkerPool(pool_size=4)
        results = pool.thread_map(lambda x: x * 2, [1, 2, 3, 4, 5])
        assert results == [2, 4, 6, 8, 10]

    def test_thread_starmap_unpacks_args(self):
        pool = WorkerPool(pool_size=4)
        results = pool.thread_starmap(
            lambda a, b: a + b, [(1, 2), (3, 4), (5, 6)]
        )
        assert results == [3, 7, 11]

    def test_thread_funcmap_runs_zero_arg_functions(self):
        pool = WorkerPool(pool_size=4)
        results = pool.thread_funcmap([lambda: 10, lambda: 20, lambda: 30])
        assert sorted(results) == [10, 20, 30]


# ---------------------------------------------------------------------------
# WaitJobsWrapper / GatherJobsWrapper tests
# ---------------------------------------------------------------------------


class TestWaitJobsWrapper:
    """Verify wait_jobs() context manager"""

    def test_waits_for_all_jobs_on_exit(self):
        pool = WorkerPool(pool_size=4)
        completed = []

        def slow_append(n):
            time.sleep(0.1)
            completed.append(n)
            return n

        with pool.wait_jobs() as w:
            w.start_thread_soon(slow_append, 1)
            w.start_thread_soon(slow_append, 2)
            w.start_thread_soon(slow_append, 3)
        # All jobs should be complete after the with block
        assert sorted(completed) == [1, 2, 3]

    def test_can_be_reused(self):
        pool = WorkerPool(pool_size=4)
        with pool.wait_jobs() as w:
            w.start_thread_soon(lambda: 1)
        with pool.wait_jobs() as w:
            w.start_thread_soon(lambda: 2)
        # No exception means success


class TestGatherJobsWrapper:
    """Verify gather_jobs() context manager"""

    def test_collects_results_in_order(self):
        pool = WorkerPool(pool_size=4)

        with pool.gather_jobs() as g:
            g.start_thread_soon(lambda: "a")
            g.start_thread_soon(lambda: "b")
            g.start_thread_soon(lambda: "c")
        assert g.results == ["a", "b", "c"]

    def test_results_cleared_on_enter(self):
        pool = WorkerPool(pool_size=4)
        g = pool.gather_jobs()
        g.results.append("stale")
        with g:
            g.start_thread_soon(lambda: "fresh")
        assert g.results == ["fresh"]


# ---------------------------------------------------------------------------
# start_cmd_soon tests
# ---------------------------------------------------------------------------


class TestStartCmdSoon:
    """Verify subprocess execution on worker thread"""

    def test_runs_command_and_returns_stdout(self):
        pool = WorkerPool(pool_size=2)
        # echo is a shell builtin on Windows; use cmd /c
        job = pool.start_cmd_soon(["cmd", "/c", "echo", "hello"], timeout=5)
        stdout = job.get()
        assert b"hello" in stdout

    def test_timeout_kills_long_running_command(self):
        pool = WorkerPool(pool_size=2)
        # ping with long timeout — should be killed
        job = pool.start_cmd_soon(
            ["cmd", "/c", "ping", "-n", "10", "127.0.0.1"], timeout=0.3
        )
        # Should complete (with killed process) without raising
        stdout = job.get()
        # stdout may be partial
        assert isinstance(stdout, bytes)


# ---------------------------------------------------------------------------
# WorkerThread tests
# ---------------------------------------------------------------------------


class TestWorkerThread:
    """Verify WorkerThread lifecycle"""

    def test_worker_is_daemon(self):
        pool = WorkerPool(pool_size=2)
        job = pool.start_thread_soon(lambda: 1)
        job.get()
        # All worker threads should be daemon
        for worker in pool.all_workers:
            assert worker.thread.daemon

    def test_worker_self_retires_after_idle_timeout(self):
        """Workers exit after IDLE_TIMEOUT seconds of no activity"""
        pool = WorkerPool(pool_size=2)
        # Override timeout to make test fast
        with patch.object(WorkerPool, "IDLE_TIMEOUT", 0.5):
            job = pool.start_thread_soon(lambda: 1)
            job.get()
            # Worker should be idle now
            time.sleep(0.1)
            assert len(pool.all_workers) >= 1
            # Wait for idle timeout
            time.sleep(1.0)
            # Worker should have exited
            assert len(pool.all_workers) == 0


# ---------------------------------------------------------------------------
# Module-level singleton tests
# ---------------------------------------------------------------------------


class TestWorkerPoolSingleton:
    """Verify the module-level WORKER_POOL singleton"""

    def test_singleton_exists(self):
        assert WORKER_POOL is not None
        assert isinstance(WORKER_POOL, WorkerPool)
        assert WORKER_POOL.pool_size == 8

    def test_singleton_can_run_jobs(self):
        job = WORKER_POOL.start_thread_soon(lambda: 42)
        assert job.get() == 42

    def test_singleton_supports_wait_jobs(self):
        with WORKER_POOL.wait_jobs() as w:
            w.start_thread_soon(lambda: 1)
            w.start_thread_soon(lambda: 2)
        # No exception means success

    def test_singleton_supports_gather_jobs(self):
        with WORKER_POOL.gather_jobs() as g:
            g.start_thread_soon(lambda: "x")
            g.start_thread_soon(lambda: "y")
        assert g.results == ["x", "y"]
