"""Agents app config: ready() orchestrates agent auto-start + heartbeat.

The runtime implementation (subprocess management, monitor thread,
heartbeat thread, platform helpers) lives in ``workers.worker_runtime``;
this module stays a thin orchestrator so AppConfig plumbing is easy to
read. Split out of the original ~520-line apps.py (TD-217).
"""
import logging
import os
import sys

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class WorkersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'workers'

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
            from . import worker_runtime
            worker_runtime.start_heartbeat_loop()
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
        from . import worker_runtime
        worker_runtime.start_heartbeat_loop()

        # spec 2026-08-29 P4: agent 生命周期单一 Owner — daemon 唯一管理.
        # 移除 backend 自启 agent 分支 (原 GAF_AUTO_START_AGENT) 以避免双 Owner
        # 竞争导致僵尸连接/黑屏 (N154/N216). 设备心跳线程仍保留 (backend 职责).
        logger.info(
            'Worker 由 gaf_daemon 统一管理 (单一 Owner, spec P4). '
            'Device heartbeat is active.'
        )
