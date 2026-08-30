"""Worker thread pool imitating trio.to_thread.start_thread_soon().

Alas-style 8-thread WorkerPool with idle-timeout self-retirement and
Job-based result retrieval with timeout+kill capability.

Reference: AzurLaneAutoScript/module/device/method/pool.py (580 lines)

Key components:
    - Outcome (ABC) / Value / Error: result wrapper (trio-style)
    - capture(sync_fn, *args, **kwargs): run fn, return Value or Error
    - Job[ResultT]: one-shot queue, get() blocks, get_or_kill(timeout) kills
    - WorkerThread: daemon thread looping on worker_lock.acquire(timeout)
    - WorkerPool(pool_size=8): manages idle_workers + all_workers
    - WaitJobsWrapper / GatherJobsWrapper: batched job submission
    - WORKER_POOL: module-level singleton
"""

import abc
import contextlib
import ctypes
import logging
import subprocess
from collections import deque
from collections.abc import Callable
from functools import wraps
from itertools import count
from threading import Lock, Thread
from typing import Any, Generic, NoReturn, TypeVar

logger = logging.getLogger(__name__)

ValueT = TypeVar("ValueT", covariant=True)
ResultT = TypeVar("ResultT")


def remove_tb_frames(exc: BaseException, n: int) -> BaseException:
    """Strip n frames from exception traceback for cleaner error reports.

    Args:
        exc: The exception whose traceback should be trimmed.
        n: Number of frames to remove from the top of the traceback.

    Returns:
        The exception with trimmed traceback.
    """
    tb = exc.__traceback__
    for _ in range(n):
        assert tb is not None
        tb = tb.tb_next
    return exc.with_traceback(tb)


class Outcome(abc.ABC, Generic[ValueT]):
    """Abstract result wrapper — either a Value or an Error."""

    @abc.abstractmethod
    def unwrap(self) -> ValueT:
        """Return the contained value or raise the contained exception."""
        raise NotImplementedError


class Value(Outcome[ValueT], Generic[ValueT]):
    """Concrete Outcome representing a successful return value."""

    __slots__ = ("value",)

    def __init__(self, value: ValueT):
        self.value: ValueT = value

    def __repr__(self) -> str:
        return f"Value({self.value!r})"

    def unwrap(self) -> ValueT:
        return self.value


class Error(Outcome[NoReturn]):
    """Concrete Outcome representing a raised exception."""

    __slots__ = ("error",)

    def __init__(self, error: BaseException):
        self.error: BaseException = error

    def __repr__(self) -> str:
        return f"Error({self.error!r})"

    def unwrap(self):
        captured_error = self.error
        try:
            raise captured_error
        finally:
            # Avoid reference cycle (captured_error.__traceback__ -> self)
            del captured_error, self


def capture(sync_fn: Callable[..., ResultT], *args: Any, **kwargs: Any) -> Outcome[ResultT]:
    """Run ``sync_fn(*args, **kwargs)`` and capture the result.

    Args:
        sync_fn: The function to execute.
        *args: Positional arguments to pass to sync_fn.
        **kwargs: Keyword arguments to pass to sync_fn.

    Returns:
        Value[ResultT] if the function succeeded, Error if it raised.
    """
    try:
        return Value(sync_fn(*args, **kwargs))
    except BaseException as exc:  # noqa: BLE001 — capture everything
        exc = remove_tb_frames(exc, 1)
        return Error(exc)


class JobError(Exception):
    """Raised when a job fails."""


class JobTimeout(Exception):  # noqa: N818 - matches Alas naming for compatibility
    """Raised when get_or_kill() times out and the worker is killed."""


class _JobKill(Exception):  # noqa: N818 - internal sentinel, not a public error
    """Internal sentinel exception used to kill a worker thread."""


class Job(Generic[ResultT]):
    """A one-shot queue — can only put() once and get() once.

    Faster than queue.Queue() for single-producer/single-consumer use.
    """

    def __init__(self, worker: "WorkerThread", func_args_kwargs: tuple):
        # Having attribute "worker" means job is ongoing.
        # Not having attribute "worker" means job is finished or killed.
        self.worker: WorkerThread = worker
        self.func_args_kwargs = func_args_kwargs

        self.queue: deque[Outcome[ResultT]] = deque()
        self.put_lock = Lock()
        self.notify_get = Lock()
        self.notify_get.acquire()

    def __repr__(self) -> str:
        return f"Job({self.func_args_kwargs})"

    def get(self) -> ResultT:
        """Block until the job completes, then return its result or raise its error."""
        self.notify_get.acquire()
        item = self.queue.popleft()
        return item.unwrap()

    def get_or_kill(self, timeout: float) -> ResultT:
        """Try to get the result within ``timeout`` seconds.

        If the result is available, return it (or raise the captured error).
        If the timeout expires, kill the worker thread and raise JobTimeout.

        Args:
            timeout: Maximum seconds to wait for the result.

        Raises:
            JobTimeout: If the result is not available within timeout.
        """
        if self.notify_get.acquire(timeout=timeout):
            item = self.queue.popleft()
            return item.unwrap()
        self._kill()
        raise JobTimeout

    def _kill(self) -> None:
        with self.put_lock:
            try:
                worker = self.worker
            except AttributeError:
                # Trying to kill a finished job — do nothing
                return
            worker.kill()
            del self.worker


_name_counter = count()


class WorkerThread:
    """A daemon thread that loops waiting for jobs from its parent WorkerPool.

    The thread self-retires after WorkerPool.IDLE_TIMEOUT seconds of no job.
    """

    def __init__(self, thread_pool: "WorkerPool"):
        self.job: Job | None = None
        self.thread_pool = thread_pool
        # "Unlocked" means we have a pending job assigned to us.
        # "Locked" means we don't. Initially no job, so starts locked.
        self.worker_lock = Lock()
        self.worker_lock.acquire()
        self.default_name = f"GAFio thread {next(_name_counter)}"

        self.thread = Thread(target=self._work, name=self.default_name, daemon=True)
        self.thread.start()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.default_name})"

    def _handle_job(self) -> None:
        # Convert to local variable; self.job may be reassigned mid-execution
        job = self.job
        del self.job
        func, args, kwargs = job.func_args_kwargs

        result = capture(func, *args, **kwargs)

        # Tell the pool we're available for a new job BEFORE delivering,
        # so a job triggered by deliver() can be assigned to us.
        self.thread_pool.idle_workers[self] = None
        self.thread_pool.release_full_lock()

        # Deliver result to the waiting get() caller
        if isinstance(result, Error) and isinstance(result.error, _JobKill):
            # Job was killed
            pass
        else:
            with job.put_lock:
                job.queue.append(result)
                del job.worker
                job.notify_get.release()

    def _work(self) -> None:
        while True:
            if self.worker_lock.acquire(timeout=WorkerPool.IDLE_TIMEOUT):
                # Got a job
                self._handle_job()
            else:
                # Timeout acquiring lock — try to exit, but watch for races
                try:
                    del self.thread_pool.idle_workers[self]
                except KeyError:
                    # Someone else removed us from idle — they're assigning a job
                    self.thread_pool.release_full_lock()
                    continue
                else:
                    # Successfully removed ourselves — safe to exit
                    del self.thread_pool.all_workers[self]
                    self.thread_pool.release_full_lock()
                    return

    def kill(self) -> bool:
        """Kill the worker thread by injecting _JobKill via ctypes.

        This is unsafe but necessary when a job function blocks indefinitely.
        Must be called under ``job.put_lock`` to avoid races with _handle_job().

        Returns:
            True if the kill signal was sent successfully, False otherwise.
        """
        thread_id = ctypes.c_long(self.thread.ident)
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            thread_id, ctypes.py_object(_JobKill)
        )
        if res <= 1:
            self.thread_pool.all_workers.pop(self, None)
            self.thread_pool.release_full_lock()
            return True
        # Failed to send — reset the exception state
        try:
            job = self.job
        except AttributeError:
            job = None
        logger.error("Failed to kill thread %s from job %s", self.thread.ident, job)
        ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
        return False


class WorkerPool:
    """A thread pool imitating trio.to_thread.start_thread_soon().

    Default pool_size=8 (Alas-style). Workers self-retire after IDLE_TIMEOUT
    seconds of inactivity. Supports timeout+kill via Job.get_or_kill().
    """

    # Thread exits after 10s of idling.
    IDLE_TIMEOUT = 10

    def __init__(self, pool_size: int = 8):
        self.pool_size = pool_size
        self.idle_workers: dict[WorkerThread, None] = {}
        self.all_workers: dict[WorkerThread, None] = {}

        self.notify_worker = Lock()
        self.notify_worker.acquire()
        self.notify_pool = Lock()
        self.notify_pool.acquire()

    def release_full_lock(self) -> None:
        """Hand-off protocol: worker notifies pool that a slot is free.

        When pool is full, pool tells all workers "any worker finishing
        their job should notify me" via notify_worker.release(), then
        blocks on notify_pool.acquire(). The fastest idle worker receives
        the message and releases notify_pool to unblock the pool.
        """
        if self.notify_worker.acquire(blocking=False):
            self.notify_pool.release()

    def _get_thread_worker(self) -> WorkerThread:
        """Get an idle worker, or create a new one if pool is not full."""
        try:
            worker, _ = self.idle_workers.popitem()
            return worker
        except KeyError:
            pass

        # Wait if reached max thread count
        if len(self.all_workers) >= self.pool_size:
            self.notify_worker.release()
            self.notify_pool.acquire()
            # A worker just became idle
            try:
                worker, _ = self.idle_workers.popitem()
                return worker
            except KeyError:
                # A worker just exited — fall through to create new
                pass

        # Create new worker
        worker = WorkerThread(self)
        self.all_workers[worker] = None
        return worker

    def start_thread_soon(
        self, func: Callable[..., ResultT], *args: Any, **kwargs: Any
    ) -> Job[ResultT]:
        """Run a function on a worker thread.

        Args:
            func: The function to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            A Job whose result can be retrieved via job.get() or
            job.get_or_kill(timeout).
        """
        worker = self._get_thread_worker()
        job = Job(worker=worker, func_args_kwargs=(func, args, kwargs))

        worker.job = job
        worker.worker_lock.release()
        return job

    def run_on_thread(self, func: Callable[..., ResultT]) -> Callable[..., Job[ResultT]]:
        """Decorator: run the decorated function on a worker thread.

        The decorated function returns a Job instead of the result directly.
        """

        @wraps(func)
        def thread_wrapper(*args: Any, **kwargs: Any) -> Job[ResultT]:
            return self.start_thread_soon(func, *args, **kwargs)

        return thread_wrapper

    @staticmethod
    def _subprocess_execute(cmd: list[str], timeout: float = 10) -> bytes:
        """Helper: run cmd in subprocess with timeout, return stdout bytes.

        Args:
            cmd: Command list to execute.
            timeout: Maximum seconds to wait.

        Returns:
            stdout bytes from the subprocess.
        """
        logger.info("Execute: %s", cmd)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=False)
        try:
            stdout, _stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, _stderr = process.communicate()
            logger.warning(
                "TimeoutExpired calling %s, stdout=%s", cmd, stdout
            )
        except BaseException:
            # Ensure the child process is reaped on any non-timeout failure
            # (e.g. KeyboardInterrupt, MemoryError). Without this, the process
            # would keep running and its stdout pipe would leak until the OS
            # reaps the orphan after the interpreter exits.
            with contextlib.suppress(Exception):
                process.kill()
            with contextlib.suppress(Exception):
                process.communicate()
            raise
        return stdout

    def start_cmd_soon(self, cmd: list[str], timeout: float = 10) -> Job[bytes]:
        """Run cmd on a subprocess, communicating on a worker thread.

        Args:
            cmd: Command list to execute.
            timeout: Maximum seconds to wait.

        Returns:
            A Job whose result is the stdout bytes.
        """
        worker = self._get_thread_worker()
        job = Job(
            worker=worker,
            func_args_kwargs=(
                self._subprocess_execute,
                (cmd,),
                {"timeout": timeout},
            ),
        )
        worker.job = job
        worker.worker_lock.release()
        return job

    def wait_jobs(self) -> "WaitJobsWrapper":
        """Context manager: auto-wait for all jobs started inside the block.

        Example::

            with WORKER_POOL.wait_jobs() as pool:
                pool.start_thread_soon(func1)
                pool.start_thread_soon(func2)
            # All jobs complete before exiting the block
        """
        return WaitJobsWrapper(self)

    def gather_jobs(self) -> "GatherJobsWrapper":
        """Context manager: auto-wait and collect results from all jobs.

        Example::

            with WORKER_POOL.gather_jobs() as pool:
                pool.start_thread_soon(func1)
                pool.start_thread_soon(func2)
            print(pool.results)  # list of return values
        """
        return GatherJobsWrapper(self)

    def thread_map(
        self, func: Callable[..., ResultT], iterables: list
    ) -> list[ResultT]:
        """Like ThreadPoolExecutor.map(func, iterables) but using this pool.

        Args:
            func: Function to apply to each item.
            iterables: Iterable of items to map over.

        Returns:
            List of results in the same order as iterables.
        """
        jobs = [self.start_thread_soon(func, arg) for arg in iterables]
        return [job.get() for job in jobs]

    def thread_starmap(
        self, func: Callable[..., ResultT], iterables: list
    ) -> list[ResultT]:
        """Like multiprocessing.pool.Pool().starmap(func, iterables) but on threads.

        Args:
            func: Function taking multiple positional args.
            iterables: Iterable of arg-tuples to unpack into func.

        Returns:
            List of results.
        """
        jobs = [self.start_thread_soon(func, *arg) for arg in iterables]
        return [job.get() for job in jobs]

    def thread_funcmap(
        self, func_iterables: list[Callable[..., ResultT]]
    ) -> list[ResultT]:
        """Run a list of zero-arg functions on threads.

        Args:
            func_iterables: Iterable of callables.

        Returns:
            List of results.
        """
        jobs = [self.start_thread_soon(func) for func in func_iterables]
        return [job.get() for job in jobs]


class WaitJobsWrapper:
    """Wrapper that auto-waits for all jobs started inside its context."""

    def __init__(self, pool: WorkerPool):
        self.pool = pool
        self.jobs: list[Job[Any]] = []

    def get(self) -> None:
        """Block until all queued jobs complete."""
        for job in self.jobs:
            job.get()
        self.jobs.clear()

    def __enter__(self) -> "WaitJobsWrapper":
        self.jobs.clear()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.get()

    def start_thread_soon(
        self, func: Callable[..., ResultT], *args: Any, **kwargs: Any
    ) -> Job[ResultT]:
        """Start a job and track it for later waiting."""
        job = self.pool.start_thread_soon(func, *args, **kwargs)
        self.jobs.append(job)
        return job


class GatherJobsWrapper(WaitJobsWrapper):
    """Wrapper that auto-waits and collects results from all jobs."""

    def __init__(self, pool: WorkerPool):
        super().__init__(pool)
        self.results: list[Any] = []

    def get(self) -> None:
        """Block until all queued jobs complete, collecting their results."""
        for job in self.jobs:
            result = job.get()
            self.results.append(result)
        self.jobs.clear()

    def __enter__(self) -> "GatherJobsWrapper":
        self.jobs.clear()
        self.results.clear()
        return self


# Module-level singleton — use this throughout the codebase
WORKER_POOL = WorkerPool()
