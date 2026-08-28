"""Agents app config: ready() orchestrates agent auto-start + heartbeat.

The runtime implementation (subprocess management, monitor thread,
heartbeat thread, platform helpers) lives in ``agents.agent_runtime``;
this module stays a thin orchestrator so AppConfig plumbing is easy to
read. Split out of the original ~520-line apps.py (TD-217).
"""
import logging
import os
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AgentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agents'

    def ready(self):
        # Register Device post_save signal for unified device.updated broadcasting.
        # Must be imported before the early return below so the signal is active
        # in all environments (runserver, Daphne, gunicorn, celery worker, tests).
        from . import signals  # noqa: F401

        # Identify the entry process. The original check only handled
        # ``runserver`` and silently skipped every other entry point
        # (Daphne / gunicorn / pytest / celery / management commands),
        # which meant the device heartbeat thread and the agent auto-start
        # monitor never spun up under Daphne. That left operators
        # hand-starting the agent subprocess and chasing token drift.
        # See N195-class root cause: Daphne → ``ready()`` early-returns,
        # backend never auto-starts agent, agent never appears ONLINE.
        entry = os.path.basename(sys.argv[0] if sys.argv else '').lower()
        argv_blob = ' '.join(sys.argv).lower()

        is_pytest = entry.startswith('pytest') or 'pytest' in argv_blob
        is_celery = entry.startswith('celery') or 'celery' in argv_blob
        is_management = entry == 'manage.py' and 'runserver' not in argv_blob
        is_gunicorn = entry.startswith('gunicorn')

        # 1) Pytest: never start background threads (test isolation).
        if is_pytest:
            return
        # 2) Celery worker: has its own task lifecycle, no device heartbeat.
        if is_celery:
            return
        # 3) One-off management commands (migrate, shell, loaddata, ...):
        #    no background work, just register signals above.
        if is_management:
            return
        # 4) Gunicorn: run device heartbeat (every worker has the DB),
        #    but DO NOT auto-start the agent — production should manage
        #    agent lifecycle via systemd / supervisor, not from a random
        #    gunicorn worker.
        if is_gunicorn:
            from . import agent_runtime
            agent_runtime.start_heartbeat_loop()
            return

        # 5) runserver (Django's WSGI dev server) and Daphne (ASGI prod/
        #    dev): both are single-process request handlers (runserver
        #    uses RUN_MAIN env to gate the autoreload child, Daphne is
        #    always the actual server). Run the full ready() suite.
        is_runserver = 'runserver' in argv_blob
        is_daphne = entry.startswith('daphne') or 'daphne' in argv_blob
        if not (is_runserver or is_daphne):
            return

        # In runserver's autoreload child, RUN_MAIN is 'true'. In the
        # parent process (and Daphne) RUN_MAIN is unset. Skip the parent
        # to avoid double-start, but allow Daphne through unconditionally.
        if is_runserver and os.environ.get('RUN_MAIN') != 'true':
            return

        # Device heartbeat thread: always started (low frequency, 30s default).
        # This is safe because it only calls `adb devices` once per cycle and
        # the interval is controlled by GAF_HEARTBEAT_INTERVAL.
        from . import agent_runtime
        agent_runtime.start_heartbeat_loop()

        # Agent auto-start: disabled by default since 2026-07-11 black screen
        # incident. The agent subprocess spawns its own device health checker
        # (5s adb polling), device auto-discovery, and monitor threads —
        # compounding with the backend heartbeat loop caused adb.exe crash
        # dialogs and GPU driver TDR.
        # To re-enable, set GAF_AUTO_START_AGENT=1 (or legacy GAF_SKIP_AUTO_AGENT
        # is not '1'). The legacy GAF_SKIP_AUTO_AGENT=1 env var still works as
        # a hard kill switch.
        if os.environ.get('GAF_SKIP_AUTO_AGENT') == '1':
            logger.info('GAF_SKIP_AUTO_AGENT=1, skipping agent auto-start')
            return

        from django.conf import settings as django_settings
        auto_start = getattr(django_settings, 'GAF_AUTO_START_AGENT', False)
        if not auto_start:
            logger.info(
                'Agent auto-start disabled (set GAF_AUTO_START_AGENT=1 to enable). '
                'Device heartbeat is still active.'
            )
            return

        # Singleton: only one Django process (parent + autoreload child) is
        # allowed to manage the agent. Without this guard, both processes
        # would race to start the agent and create duplicate windows.
        if agent_runtime.acquire_manager_lock() is None:
            logger.info('Agent Manager 锁已被其他进程持有（当前 PID=%s），跳过自启', os.getpid())
            return

        # N154 recurrence fix: kill stale agent processes before starting a
        # new one. Django autoreload kills the old Django process, but the
        # admin-elevated agent child (PID untrackable) survives. Without
        # this cleanup, N autoreload cycles = N stacked agents = adb storm
        # → GPU TDR → black screen.
        agent_runtime.kill_stale_agent_processes()
        agent_runtime.start_agent_monitor_loop()
