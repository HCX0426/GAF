"""Agent runtime: process supervision, heartbeat, and platform helpers.

This module owns the agent subprocess lifecycle and the device heartbeat
background thread, plus the singleton cross-process manager lock that
gates auto-start. Module-level state (threads, events, lock handle)
lives here so that ``agents.apps.AgentsConfig.ready()`` stays a thin
orchestrator.

External callers (e.g. ``agents.views``) MUST use the public
``is_xxx_alive()`` / ``is_xxx_started()`` helpers instead of touching
the private globals directly, so the encapsulation is preserved across
future refactors.

Split out of ``agents/apps.py`` (TD-217): the original apps.py grew to
~520 lines mixing Django AppConfig plumbing with subprocess management;
this module holds the runtime, apps.py holds only the ready() hook.
"""

import logging
import os
import subprocess
import sys
import tempfile
import threading
import time

logger = logging.getLogger(__name__)

if os.name == 'nt':
    import msvcrt  # Windows file locking for the singleton manager lock

_AGENT_LOCK_DIR = os.path.join(tempfile.gettempdir(), 'gaf_agent_lock')
_heartbeat_thread = None
_heartbeat_stop_event = threading.Event()
_agent_monitor_thread = None
_agent_monitor_stop_event = threading.Event()

# Holds the file handle for the singleton manager lock so the lock stays
# alive for the lifetime of the managing process. The OS auto-releases
# the lock when the file handle is closed (process exit).
_manager_lock_handle = None


# ---------------------------------------------------------------------------
# Internal helpers (private)
# ---------------------------------------------------------------------------

def _try_acquire_manager_lock():
    """Try to acquire a cross-platform singleton file lock for agent management.

    Only one Django process (including the autoreload child) may become the
    agent manager; subsequent processes see the lock held and skip startup.

    Returns:
        The open file handle on success, or None if another process holds it.
    """
    global _manager_lock_handle
    os.makedirs(_AGENT_LOCK_DIR, exist_ok=True)
    lock_path = os.path.join(_AGENT_LOCK_DIR, 'manager.lock')
    try:
        f = open(lock_path, 'w+')  # noqa: SIM115
    except OSError:
        return None

    try:
        if os.name == 'nt':
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None

    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    _manager_lock_handle = f
    return f


def _is_process_alive(pid):
    """Check if a Windows process with the given PID is still running.

    B002 fix: delegates to agent.platforms.windows.process.is_process_alive
    so the Win32 calls live behind the platform abstraction layer and
    failures are logged instead of swallowed by `except: pass`.
    """
    from device_bridge.platforms.windows.process import is_process_alive
    return is_process_alive(pid)


def _get_agent_pid():
    """Read the agent PID from the lock file."""
    lock_file = os.path.join(_AGENT_LOCK_DIR, 'agent.pid')
    try:
        if os.path.exists(lock_file):
            with open(lock_file) as f:
                return int(f.read().strip())
    except (ValueError, FileNotFoundError):
        pass
    return None


def _remove_agent_lock():
    """Remove the agent lock file."""
    lock_file = os.path.join(_AGENT_LOCK_DIR, 'agent.pid')
    try:
        if os.path.exists(lock_file):
            os.remove(lock_file)
    except OSError:
        pass


def _is_admin() -> bool:
    """Check if the current process is running with admin privileges.

    B002 fix: delegates to agent.platforms.windows.process.is_admin so
    the Win32 shell32 call lives behind the platform abstraction layer
    and failures are logged instead of swallowed.
    """
    from device_bridge.platforms.windows.process import is_admin
    return is_admin()


def _run_as_admin(cmd_args: list, cwd: str = None, log_file: str = None) -> bool:
    """Run a command with admin privileges using ShellExecute (runas).

    B002 fix: delegates to agent.platforms.windows.process.run_as_admin
    so the Win32 ShellExecuteW call lives behind the platform abstraction
    layer. See that module for the full docstring.
    """
    from device_bridge.platforms.windows.process import run_as_admin
    return run_as_admin(cmd_args, cwd=cwd, log_file=log_file)


def _get_or_create_local_agent_token():
    """Get or create a token for the local agent.

    Finds the local Agent record (is_local=True) and generates a new token
    if it doesn't have a token hash. Returns the plaintext token for passing
    to the agent subprocess, or None if no local agent exists.
    """
    try:
        import secrets as _secrets

        from gaf_core.utils.tokens import hash_token, make_token_preview

        from workers.models import Worker

        agent = Worker.objects.filter(is_local=True).first()
        if not agent:
            logger.warning('No local Agent record found in DB; token skipped')
            return None

        # Always generate a fresh token on startup. The agent subprocess is
        # short-lived (killed when runserver stops), so we don't need to
        # persist the token across restarts. This avoids the 403 error when
        # a previously-saved token has been revoked or never existed.
        token = _secrets.token_urlsafe(32)
        agent.worker_token_hash = hash_token(token)
        agent.worker_token_preview = make_token_preview(token)
        # TD-141 (2026-07-18): agent_token plaintext field removed.
        agent.save(update_fields=['worker_token_hash',
                                  'worker_token_preview', 'updated_at'])
        logger.info('Generated token for local agent %s', agent.agent_id)
        return token
    except Exception as e:
        logger.warning('Failed to generate local agent token: %s', e)
        return None


def _rotate_log_if_needed(log_path: str, max_size_mb: int = 10) -> None:
    """Rotate log file if it exceeds max_size_mb.

    Renames the current log to .1 (overwriting any existing .1) so the
    agent always writes to a fresh file. Without this, agent_stderr.log
    can grow to hundreds of MB over days of runserver uptime.
    """
    try:
        if not os.path.exists(log_path):
            return
        size_mb = os.path.getsize(log_path) / (1024 * 1024)
        if size_mb < max_size_mb:
            return
        backup = log_path + '.1'
        if os.path.exists(backup):
            os.remove(backup)
        os.rename(log_path, backup)
        logger.info('Rotated agent log %s (%.1f MB -> backup)', log_path, size_mb)
    except Exception as e:
        logger.warning('Log rotation failed for %s: %s', log_path, e)


def _start_agent_process():
    """Start the agent subprocess and write its PID to the lock file.

    If the current process is not running with admin privileges, the agent
    will be launched with admin privileges via ShellExecute (runas verb).
    """
    agent_script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'agent', 'src', '__main__.py',
    )
    if not os.path.exists(agent_script):
        logger.warning('Agent 脚本未找到: %s', agent_script)
        return None

    agent_dir = os.path.dirname(agent_script)
    log_dir = os.path.join(_AGENT_LOCK_DIR, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    stderr_log_path = os.path.join(log_dir, 'agent_stderr.log')

    # Rotate log if it's too large (prevents unbounded log growth)
    _rotate_log_if_needed(stderr_log_path, max_size_mb=10)

    # Generate a token for the local agent so it can authenticate via WebSocket
    agent_token = _get_or_create_local_agent_token()

    # Check if we need admin elevation for the agent
    is_admin = _is_admin()
    cmd_args = [sys.executable, agent_script]
    if agent_token:
        cmd_args.extend(['--agent-token', agent_token])
    success = False

    if not is_admin:
        # Try to launch with admin privileges; pass the stderr log path so
        # the hidden child can still persist its logs to disk.
        success = _run_as_admin(cmd_args, cwd=agent_dir, log_file=stderr_log_path)
        if not success:
            logger.warning('管理员权限启动失败，尝试普通权限')

    if is_admin or not success:
        # Fallback: start without admin (or current process is already admin)
        try:
            env = os.environ.copy()
            env['PYTHONPATH'] = agent_dir
            # Use a context manager so the parent's file handle is closed
            # after Popen has dup'd the descriptor to the child. Keeping it
            # open in the parent leaks a file descriptor on every restart.
            with open(stderr_log_path, 'a') as stderr_log:
                proc = subprocess.Popen(
                    cmd_args,
                    cwd=agent_dir,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                )
            lock_file = os.path.join(_AGENT_LOCK_DIR, 'agent.pid')
            os.makedirs(_AGENT_LOCK_DIR, exist_ok=True)
            with open(lock_file, 'w') as f:
                f.write(str(proc.pid))
            logger.info('本地 Agent 已启动 (PID=%s, admin=%s, token=%s)',
                        proc.pid, is_admin, 'yes' if agent_token else 'no')
            return proc.pid
        except Exception as e:
            logger.warning('本地 Agent 启动失败: %s', e)
            return None

    # Admin elevation succeeded. ShellExecuteW does not return the child PID,
    # so we cannot write agent.pid or track it via _is_process_alive. Return a
    # sentinel (-1) so the caller knows the launch succeeded — the supervisor
    # relies on _is_agent_connected_via_db() for liveness checks instead.
    # Previously this path fell through with no return, implicitly returning
    # None, which the supervisor mistook for a launch failure. After 3 such
    # "failures" the monitor thread gave up ("Agent 连续启动失败 3 次，停止监控")
    # and never restarted the agent again.
    logger.info('本地 Agent 已以管理员权限启动 (PID 不可追踪, 靠 DB 心跳检查存活)')
    return -1


def _is_agent_connected_via_db():
    """Check DB for any agent that is currently connected via WebSocket.

    When the agent is launched with admin elevation (ShellExecuteW 'runas'),
    the supervisor cannot track its PID — ``agent.pid`` is never written and
    ``_get_agent_pid()`` returns None. Without this DB check the supervisor
    would false-positive restart every 10s, killing the WebSocket connection
    and making Pipeline group_send messages land in a disconnected window.

    The DB is the source of truth for "is an agent connected right now":
    AgentConsumer._db_update_heartbeat updates ``status`` and
    ``last_heartbeat`` on every heartbeat frame, and disconnect() marks the
    agent OFFLINE. So if any Agent row is ONLINE/IDLE with a heartbeat
    younger than 30s, a live consumer is bound to it.

    Returns:
        True if at least one agent appears connected (skip restart).
    """
    try:
        from django.db import connection
        from django.utils import timezone

        from workers.models import Worker

        if connection.connection is not None:
            connection.close_if_unusable_or_obsolete()

        threshold = timezone.now() - timezone.timedelta(seconds=30)
        return Worker.objects.filter(
            status__in=[Worker.Status.ONLINE, Worker.Status.IDLE],
            last_heartbeat__gte=threshold,
        ).exists()
    except Exception as e:
        logger.warning('_is_agent_connected_via_db 查询失败: %s', e)
        return False


def _kill_stale_agent_processes():
    """Kill any existing agent processes before starting a new one.

    N154 recurrence fix: Django autoreload kills the old Django process,
    but the admin-elevated agent child (launched via ShellExecuteW 'runas')
    survives because its PID is untrackable. Without this cleanup, each
    autoreload cycle stacks another agent → N agents × MonitorManager
    screenshots = adb storm → GPU TDR → black screen.

    Uses wmic to find python.exe processes with 'agent\\src\\__main__.py'
    in the command line, then taskkill /F to terminate them.
    """
    if os.name != 'nt':
        return
    try:
        from device_bridge.platforms.windows.process import kill_processes_by_commandline
        killed = kill_processes_by_commandline('agent\\src\\__main__.py')
        if killed:
            logger.info('Killed %d stale agent process(es) before auto-start', killed)
            time.sleep(2)  # Give OS time to release resources
    except Exception as e:
        logger.warning('Failed to kill stale agent processes: %s', e)


def _agent_monitor_loop():
    """Background thread: monitor agent process health and restart if needed.

    Restart decision uses two signals:
      1. PID file (``agent.pid``) — written when the agent starts WITHOUT
         admin elevation. If the PID is alive, the agent is healthy.
      2. DB agent status — consulted when the PID is None or dead (the
         admin-elevated case). If any agent is ONLINE/IDLE with a fresh
         heartbeat, the supervisor skips restart instead of false-positive
         killing the live WebSocket connection.

    Rate limiting (N154 recurrence fix):
      - Exponential backoff: 10s → 30s → 60s → 120s → 300s between restarts
      - Crash-loop detection: >5 restarts in 5-min window → stop monitor
      - Prevents adb storm when agent crash-loops (each restart triggers
        device discovery + health checker + monitor threads)
    """
    logger.info('Agent monitor thread: starting...')
    consecutive_failures = 0
    max_failures = 3

    # N154 recurrence: exponential backoff + crash-loop detection
    backoff_schedule = [10, 30, 60, 120, 300]  # seconds
    restart_history = []  # timestamps of recent restarts
    crash_loop_window = 300  # 5 minutes
    crash_loop_threshold = 5  # max restarts in window

    while not _agent_monitor_stop_event.is_set():
        try:
            pid = _get_agent_pid()
            pid_alive = pid is not None and _is_process_alive(pid)
            if not pid_alive:
                # PID untrackable or dead. Before restarting, confirm via DB
                # that no agent is actually connected — admin-elevated agents
                # have no PID file but still hold a live WebSocket.
                if _is_agent_connected_via_db():
                    logger.debug(
                        'Agent PID 不可追踪 (PID=%s) 但 DB 显示 agent 已连接，跳过重启',
                        pid,
                    )
                else:
                    # N154: crash-loop detection — if we've restarted too many
                    # times in a short window, stop to prevent adb storm.
                    now = time.time()
                    restart_history = [t for t in restart_history
                                       if now - t < crash_loop_window]
                    if len(restart_history) >= crash_loop_threshold:
                        logger.error(
                            'Agent 在 %d 秒内重启 %d 次，疑似崩溃循环，停止监控 '
                            '(防止 adb 风暴 → GPU TDR)',
                            crash_loop_window, len(restart_history),
                        )
                        break

                    # N154: exponential backoff between restarts
                    backoff_idx = min(len(restart_history), len(backoff_schedule) - 1)
                    backoff = backoff_schedule[backoff_idx]
                    logger.warning(
                        'Agent 进程已退出 (PID=%s)，%d 秒后重启 (第 %d 次, backoff=%ds)',
                        pid, backoff, len(restart_history) + 1, backoff,
                    )
                    _remove_agent_lock()

                    # Wait with backoff (interruptible)
                    if _agent_monitor_stop_event.wait(backoff):
                        break

                    # _start_agent_process will handle admin elevation automatically
                    new_pid = _start_agent_process()
                    if new_pid is None:
                        consecutive_failures += 1
                        if consecutive_failures >= max_failures:
                            logger.error('Agent 连续启动失败 %d 次，停止监控', consecutive_failures)
                            break
                    else:
                        consecutive_failures = 0
                        restart_history.append(time.time())
                        logger.info('Agent 重启成功 (新 PID=%s)', new_pid)
        except Exception as e:
            logger.warning('Agent 监控异常: %s', e, exc_info=True)

        # Poll interval (10s, interruptible)
        if _agent_monitor_stop_event.wait(10):
            break

    logger.info('Agent monitor thread stopped')


def _device_heartbeat_loop():
    """Background thread: check device status periodically and update DB silently.

    Interval is controlled by settings.GAF_HEARTBEAT_INTERVAL (default 30s).
    The previous 2s interval caused excessive adb subprocess spawning — one
    `adb devices` per emulator device per 2s — which led to adb.exe crash
    dialogs and GPU driver TDR (black screen incident 2026-07-11).
    """
    from django.conf import settings as django_settings
    from django.db import connection

    from workers.models import Device
    from workers.views import DeviceViewSet

    interval = getattr(django_settings, 'GAF_HEARTBEAT_INTERVAL', 30)
    logger.info('Device heartbeat loop: starting (interval=%ds)', interval)
    try:
        checker = DeviceViewSet()
        checker.request = None
        logger.info('Device heartbeat loop: DeviceViewSet created')
    except Exception as e:
        logger.error('Device heartbeat loop: failed to create DeviceViewSet: %s', e)
        return

    while not _heartbeat_stop_event.is_set():
        try:
            if connection.connection is not None:
                connection.close_if_unusable_or_obsolete()

            devices = Device.objects.all()
            for device in devices:
                if _heartbeat_stop_event.is_set():
                    break
                try:
                    checker._check_single_device(device)
                except Exception as e:
                    logger.debug('Heartbeat error for device %s: %s', device.id, e)

        except Exception as e:
            logger.warning('Heartbeat loop error: %s', e, exc_info=True)

        # Sleep in 1-second increments so stop_event is responsive
        for _ in range(interval):
            if _heartbeat_stop_event.is_set():
                break
            time.sleep(1)

    logger.info('Device heartbeat thread stopped')


# ---------------------------------------------------------------------------
# Public API: lifecycle helpers used by AgentsConfig.ready() and agents.views
# ---------------------------------------------------------------------------

def start_heartbeat_loop() -> None:
    """Start the device heartbeat background thread (idempotent).

    Safe to call multiple times — if the thread is already running, this
    is a no-op. The thread polls devices every GAF_HEARTBEAT_INTERVAL
    seconds (default 30) and updates Device.status in the DB.
    """
    global _heartbeat_thread, _heartbeat_stop_event
    if _heartbeat_thread is None or not _heartbeat_thread.is_alive():
        _heartbeat_stop_event.clear()
        _heartbeat_thread = threading.Thread(target=_device_heartbeat_loop, daemon=True)
        _heartbeat_thread.start()
        logger.info('Device heartbeat background thread started')


def start_agent_monitor_loop() -> None:
    """Start the agent monitor background thread (idempotent).

    Safe to call multiple times — if the thread is already running, this
    is a no-op. The thread polls the agent subprocess every 10s and
    restarts it with exponential backoff if it has died.
    """
    global _agent_monitor_thread, _agent_monitor_stop_event
    if _agent_monitor_thread is None or not _agent_monitor_thread.is_alive():
        _agent_monitor_stop_event.clear()
        _agent_monitor_thread = threading.Thread(target=_agent_monitor_loop, daemon=True)
        _agent_monitor_thread.start()
        logger.info('Agent monitor background thread started (interval=10s)')


def acquire_manager_lock():
    """Try to acquire the singleton cross-process manager lock.

    Returns the open file handle on success, or None if another process
    already holds the lock (caller should skip agent auto-start).
    """
    return _try_acquire_manager_lock()


def kill_stale_agent_processes() -> None:
    """Kill any existing agent subprocesses before starting a new one."""
    _kill_stale_agent_processes()


def is_heartbeat_alive() -> bool:
    """Return True if the device heartbeat thread exists and is alive."""
    return _heartbeat_thread is not None and _heartbeat_thread.is_alive()


def is_heartbeat_started() -> bool:
    """Return True if the device heartbeat thread has been started.

    The thread may have since died; use is_heartbeat_alive() for liveness.
    """
    return _heartbeat_thread is not None


def is_agent_monitor_alive() -> bool:
    """Return True if the agent monitor thread exists and is alive."""
    return _agent_monitor_thread is not None and _agent_monitor_thread.is_alive()
