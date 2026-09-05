import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("gaf")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()
# N197 fix: tasks/heartbeat.py 不是 tasks.py, autodiscover_tasks() 不自动发现.
# 手动 import 确保 Worker 注册 tasks.heartbeat.check_agent_heartbeats.
app.conf.imports = ['tasks.heartbeat']

app.conf.beat_schedule = {
    'check-agent-heartbeats': {
        'task': 'tasks.heartbeat.check_agent_heartbeats',
        'schedule': 5.0,
    },
    # S1 (2026-08-16): 派发确认扫描 — group_send 无 ack, 帧丢失时执行永久
    # RUNNING 卡死. 每 10s 扫 RUNNING + dispatch_sent_at 无 ack 的执行,
    # agent 在线 → 重派, 离线 → fail (与 check-agent-heartbeats 互补).
    'check-dispatch-acks': {
        'task': 'tasks.heartbeat.check_dispatch_acks',
        'schedule': 10.0,
    },
    # TD-425 (2026-09-05): 链执行卡死清理 — TaskChainExecution 卡 running
    # 超阈值且无活跃节点执行 → 僵尸, 置 FAILED 解除 device_busy 阻塞.
    # (链完成依赖 advance 钩子, 节点执行从未终态/advance 未触发时链永久
    # running, 会永久阻塞该设备后续所有派发.)
    'check-stuck-chains': {
        'task': 'tasks.heartbeat.check_stuck_chains',
        'schedule': 60.0,
    },
    # TD-425 邻域 (2026-09-05): DB ScheduledTask 启用/禁用/删除与 APScheduler
    # 同步 — 否则前端禁用定时任务后 APScheduler job 仍触发 (实测 exec 460-475).
    'sync-db-scheduled-tasks': {
        'task': 'config.scheduler.sync_db_scheduled_tasks',
        'schedule': 60.0,
    },
    # S2 (2026-08-16): 应用级卡死检测 — RUNNING ExecutionStep 超
    # freezeTimeoutSeconds 触发 handle_app_freeze (restart_app 等).
    # scheduler/tasks.py 是标准 tasks.py 命名, autodiscover_tasks()
    # 可发现 (与 tasks/heartbeat.py 不同, 后者已手动 import).
    'detect-app-freeze': {
        'task': 'scheduler.tasks.detect_app_freeze',
        'schedule': 60.0,
    },
    'escalate-unhandled-alerts': {
        'task': 'monitors.tasks.escalate_unhandled_alerts',
        'schedule': 300.0,  # 5 分钟扫一次, 升级 P1 30 分钟未确认的告警为 P0 (P-024)
    },
    # F12 (2026-07-31): LogEntry 表已为真只读 — 移除 cleanup-old-logs 调度.
    # LogEntry 清理定时任务已删除 (gaf_core.tasks.cleanup_old_logs 已移除).
    'cleanup-old-archives': {
        'task': 'gaf_core.tasks.cleanup_old_archives',
        'schedule': crontab(hour=3, minute=30),  # 每天凌晨 3:30 清理 30 天前的 tar.gz 归档 (spec §8.3)
    },
    'flush-expired-tokens': {
        'task': 'tasks.tasks.flush_expired_tokens',
        'schedule': 86400.0,  # 24h: flush blacklisted/expired tokens from OutstandingToken table
    },
    'rag-auto-index': {
        'task': 'gaf_ai.tasks_rag.auto_index_rag',
        'schedule': 300.0,  # 5 min: re-index agent/ and backend/gaf_ai source into ChromaDB (P2-1)
    },
    'tick-unattended-session': {
        'task': 'scheduler.tasks.tick_unattended_session',
        'schedule': 60.0,  # 60s: drive the unattended loop (P-009 Phase 2)
    },
    'daily-anomaly-scan': {
        'task': 'gaf_ai.tasks.daily_anomaly_scan',
        'schedule': crontab(hour=2, minute=0),  # 每天凌晨 2 点扫 JSONL 异常模式 (spec 阶段 4 — 任务 4.2)
    },
    # S3 P4 (2026-08-16): 过期 AI session 清理 — RUNNING/PENDING 超时
    # 标记 FAILED (前端轮询不再永久 pending), 无消息的旧 QASession 删除.
    'cleanup-stale-sessions': {
        'task': 'gaf_ai.tasks.cleanup_stale_sessions',
        'schedule': crontab(hour=3, minute=0),  # 每天凌晨 3:00
    },
    'retry-pending-executions': {
        'task': 'tasks.tasks.retry_pending_executions',
        'schedule': 60.0,  # 每 60s 扫描一次 PENDING 超时执行, 自动重试调度
    },
    'archive-old-executions': {
        'task': 'tasks.tasks.archive_old_executions',
        'schedule': crontab(hour=4, minute=0, day_of_week=0),  # 每周日凌晨 4:00 归档 30 天前的终态记录 (TD-351)
    },
    # 定时自动备份 (D7): 每天 02:30 全量快照存盘 MEDIA_ROOT/backups/, 保留 7 份.
    'scheduled-backup': {
        'task': 'gaf_core.tasks.scheduled_backup',
        'schedule': crontab(hour=2, minute=30),
    },
}
