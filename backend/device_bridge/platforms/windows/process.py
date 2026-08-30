"""Win32 process management helpers (liveness check, admin elevation).

B002 fix: agents/apps.py previously called kernel32/shell32 directly
via `import ctypes`, with `except Exception: pass` swallowing errors.
This module wraps those calls behind a platform-safe API and logs
failures instead of silently swallowing them.
"""
from __future__ import annotations

import logging
import os
import subprocess

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == 'nt'

# STILL_ACTIVE exit code returned by GetExitCodeProcess for running processes.
STILL_ACTIVE = 259

# PROCESS_QUERY_LIMITED_INFORMATION — lower privilege than QUERY_INFORMATION,
# works for processes owned by other users with restricted tokens.
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Windows error code returned by OpenProcess when the caller's integrity level
# is too low (typical for UAC-elevated children inspected by non-elevated parents).
ERROR_ACCESS_DENIED = 5


def _get_kernel32():
    """Return (kernel32, wintypes, ctypes) on Windows or (None, None, None) otherwise."""
    if not _IS_WINDOWS:
        return None, None, None
    try:
        import ctypes
        from ctypes import wintypes
        return ctypes.windll.kernel32, wintypes, ctypes
    except (ImportError, AttributeError) as exc:
        logger.warning('Win32 kernel32 unavailable: %s', exc)
        return None, None, None


def _get_shell32():
    """Return (shell32, ctypes) on Windows or (None, None) otherwise."""
    if not _IS_WINDOWS:
        return None, None
    try:
        import ctypes
        return ctypes.windll.shell32, ctypes
    except (ImportError, AttributeError) as exc:
        logger.warning('Win32 shell32 unavailable: %s', exc)
        return None, None


def is_process_alive(pid: int) -> bool:
    """Check if a Windows process with the given PID is still running.

    Uses OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) + GetExitCodeProcess.

    When OpenProcess fails with ERROR_ACCESS_DENIED (e.g. agent was launched
    with admin elevation and current process runs unelevated due to UAC
    integrity level isolation), the process is assumed alive to avoid
    spurious restarts — the cross-process liveness check otherwise cannot
    distinguish "elevated process is fine" from "process just exited".

    Non-Windows: returns False. Callers on non-Windows must implement
    their own liveness check (e.g. via /proc/<pid> or `kill -0`).
    """
    kernel32, wintypes, ctypes = _get_kernel32()
    if kernel32 is None:
        return False
    try:
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            err = kernel32.GetLastError()
            if err == ERROR_ACCESS_DENIED:
                logger.debug('Process %s inaccessible (likely elevated), assuming alive', pid)
                return True
            return False
        try:
            exit_code = wintypes.DWORD(0)
            kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    except Exception as exc:
        # B002 fix: log instead of `except: pass` so process-management
        # failures are diagnosable.
        logger.warning('is_process_alive failed for pid=%s: %s', pid, exc)
        return False


def is_admin() -> bool:
    """Return True if the current process runs with admin privileges.

    Wraps shell32.IsUserAnAdmin(). Non-Windows or unexpected error: False.
    """
    shell32, _ = _get_shell32()
    if shell32 is None:
        return False
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception as exc:
        # B002 fix: log instead of `except: pass` — admin detection failures
        # should be visible during deployment debugging.
        logger.warning('is_admin check failed: %s', exc)
        return False


def run_as_admin(
    cmd_args: list[str],
    cwd: str | None = None,
    log_file: str | None = None,
) -> bool:
    """Launch cmd_args with admin privileges via ShellExecute 'runas' verb.

    Args:
        cmd_args: [exe, arg1, arg2, ...]
        cwd: working directory passed to ShellExecuteW
        log_file: optional path appended as `--log-file=<path>` so the
            hidden elevated child can persist its logs to disk instead
            of disappearing into a hidden window.

    Returns:
        True if the elevated process was launched successfully.
    """
    shell32, _ = _get_shell32()
    if shell32 is None:
        logger.warning('run_as_admin not available on this platform')
        return False
    if not cmd_args:
        return False

    exe = cmd_args[0]
    extra_args = list(cmd_args[1:])
    if log_file:
        extra_args.append(f'--log-file={log_file}')
    args_str = ' '.join(f'"{a}"' if ' ' in a else a for a in extra_args)

    try:
        # SW_HIDE=0 keeps the elevated child process invisible so the user
        # is not bombarded with extra console windows on every restart.
        result = shell32.ShellExecuteW(
            None,         # parent window handle
            'runas',      # verb: request elevation
            exe,          # executable
            args_str,     # command line arguments
            cwd,          # working directory
            0,            # SW_HIDE
        )
        if result > 32:
            logger.info('已以管理员权限启动: %s %s', exe, args_str)
            return True
        logger.warning('ShellExecute 返回 %d（可能用户取消了提权）', result)
        return False
    except Exception as exc:
        # B002 fix: log instead of swallowing — ShellExecuteW failures
        # are usually meaningful (cancelled UAC prompt, missing exe, etc.).
        logger.warning('ShellExecute 提权失败: %s', exc)
        return False


def kill_processes_by_commandline(pattern: str) -> int:
    """Kill all processes whose command line matches ``pattern``.

    Used by agents/apps.py ready() to kill stale agent processes before
    starting a new one. Without this, Django autoreload spawns a new
    agent while the old admin-elevated one (PID untrackable) keeps
    running, causing multi-agent stacking → adb storm → GPU TDR.

    Uses ``wmic`` (Windows Management Instrumentation) to find PIDs by
    command-line match, then ``taskkill /F`` to terminate them.

    Args:
        pattern: Substring to match in process command line (e.g.
            ``worker\\src\\__main__.py``). Case-insensitive.

    Returns:
        Number of processes killed.
    """
    if not _IS_WINDOWS:
        return 0

    try:
        # wmic is deprecated in Win11 but still available; fallback to
        # PowerShell Get-CimInstance if wmic fails.
        result = subprocess.run(
            ['wmic', 'process', 'where',
             f'commandline like "%{pattern}%"', 'get', 'processid'],
            capture_output=True, text=True, timeout=10,
        )
        pids = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))

        killed = 0
        current_pid = os.getpid()
        for pid in pids:
            if pid == current_pid:
                continue  # Don't kill ourselves
            try:
                subprocess.run(
                    ['taskkill', '/F', '/PID', str(pid)],
                    capture_output=True, timeout=10,
                )
                killed += 1
                logger.info('Killed stale agent process (PID=%s)', pid)
            except Exception as exc:
                logger.warning('Failed to kill PID %s: %s', pid, exc)

        return killed
    except Exception as exc:
        logger.warning('kill_processes_by_commandline failed: %s', exc)
        return 0
