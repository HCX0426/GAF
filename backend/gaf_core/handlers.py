"""Custom logging handlers for the GAF Django backend.

FileLogHandler archives log records to ``<debug_dir>/<exec_dir>/run.log``
(N194 归一化, 2026-07-28) instead of the ``LogEntry`` table (spec §2.2).
``execution_id`` is sourced from ``tracing.context.current_execution_id`` so
records emitted during a task execution land in the per-execution directory;
records emitted outside any execution (CLI, Celery without context, request
scope) fall back to ``<debug_dir>/<YYYYMMDD>/backend/system/<HH>/django.log``
(B1, spec 2026-07-30-debug-directory-restructure: 按日期+小时分桶, 与新五层
目录结构对齐; 替代旧 ``_global/<YYYYMMDD>/run.log`` 单文件路径).

归一化前: 写入 ``<debug_dir>/logs/<execution_id>/run.log``, 与 agent 的
``<debug_dir>/structured/<exec_id>.jsonl`` + ``<debug_dir>/<node_type>/screenshots/``
不归集, 用户调试要跨 5+ 个目录翻找.

归一化后: backend FileLogHandler 写入 ``<debug_dir>/<exec_dir>/run.log``,
agent StructuredLogger 写入 ``<debug_dir>/<exec_dir>/structured.jsonl``,
agent DebugImageSaver 写入 ``<debug_dir>/<exec_dir>/screenshots/{annotated,raw}/``.
一次执行的所有日志和图片都在同一个目录下, 用户和 AI 都能"一起看".

Backend 通过 ``dispatch_task`` / ``pipeline.execute`` 主动调用
``gaf_core.debug_path.build_execution_debug_dir`` 创建 ``<exec_dir>`` 并写
``meta.json``, 再通过 WS payload 把完整路径传给 agent. Agent 用同一逻辑
生成路径 (mirror ``agent.utils.debug_path.build_execution_debug_dir``), 双方
写入同一目录, 不需要 WS 反向通知.

Each emitted line is stamped with the current request's ``trace_id``
(sourced from ``tracing.context.current_trace_id``) so the record can
still be correlated back to its originating HTTP request — the trace
chain (HTTP → contextvar → log line) is preserved.

Real-time push: after writing, the handler broadcasts a slim payload to
``LOGS_GROUP`` via the Channels layer so that ``LogStreamConsumer`` can
push it to connected frontend LogCenterPage clients in real time. The
broadcast is best-effort — failures (no channel layer, redis down) are
silently dropped, since the file write already succeeded.

Backward compatibility: ``DatabaseLogHandler`` is retained as an alias
for ``FileLogHandler`` so legacy imports continue to work, but new code
should use ``FileLogHandler`` directly. The ``LogEntry`` table is no
longer written to by this handler (spec §2.2 — table kept read-only for
historical queries).
"""
import contextlib
import logging
import os
import sys
import time
import traceback as tb_module
from datetime import datetime

# Default debug directory — overridable via settings.DEBUG_DIR or constructor.
# Used as the root for per-execution directories.
_DEFAULT_DEBUG_DIR = "./debug"


def _resolve_debug_dir(debug_dir: str | None) -> str:
    """Resolve the debug_dir root, falling back to settings.DEBUG_DIR then default."""
    if debug_dir:
        return debug_dir
    try:
        from django.conf import settings  # type: ignore[import]
        return getattr(settings, "DEBUG_DIR", _DEFAULT_DEBUG_DIR)
    except Exception:
        # Django not ready / not configured — use default.
        return _DEFAULT_DEBUG_DIR


def _resolve_exec_log_dir(debug_dir_root: str, execution_id: str) -> str:
    """Resolve the per-execution log directory for FileLogHandler.

    B1 (spec 2026-07-30-debug-directory-restructure): 系统日志 (无 execution_id)
    改为写入 ``debug/YYYYMMDD/backend/system/HH/``, 与新五层目录结构对齐:
    - 按日期分桶 (YYYYMMDD) 便于按天清理, 与 agent 目录的日期层级一致
    - 按小时分桶 (HH) 自动轮转, 避免单文件无限增长 (替代旧 _global/<YYYYMMDD>/)
    - 环境标识 (backend) 区分 agent / frontend 日志, 与目录结构 §0 中
      ``{agent,backend,frontend}`` 段对齐
    - 子段 ``system`` 表示非执行级日志 (Django 请求/CLI/Celery 无上下文)
    - 文件名 ``django.log`` (在 emit 中根据 execution_id 决定, 与 run.log 区分)

    执行日志 (有 execution_id) 仍走反查 agent 已创建的 ``<exec_dir>``,
    找不到时降级到系统日志路径 (不再用旧 ``_global/<YYYYMMDD>/`` 路径).

    Args:
        debug_dir_root: Debug root directory (e.g. ``"d:/code/GAF/debug"``).
        execution_id: Execution identifier from contextvar.

    Returns:
        Per-execution directory path (NOT yet created — caller creates lazily).
    """
    now = datetime.now()
    date_part = now.strftime("%Y%m%d")
    hour_part = now.strftime("%H")
    system_dir = os.path.join(debug_dir_root, date_part, "backend", "system", hour_part)

    if not execution_id or execution_id == "_global":
        # B1: 系统日志路径 debug/YYYYMMDD/backend/system/HH/
        return system_dir

    # 反查已存在的目录: <debug_dir_root>/*<exec_id_suffix>/
    # dispatch_task / pipeline.execute 已在 task.start 前创建该目录,
    # agent 也用同一逻辑生成路径, 所以这里 os.listdir + 后缀匹配能命中.
    from gaf_core.debug_path import find_exec_dir_by_id
    found = find_exec_dir_by_id(debug_dir_root, execution_id)
    if found:
        return found

    # 极短窗口期: dispatch_task 还没执行 (执行栈还没到), 但日志已先 emit.
    # 降级到系统日志路径, 等 dispatch_task 创建目录后, 后续 emit 会命中反查.
    return system_dir


def _resolve_backend_mirror_dir(execution_id: str) -> str | None:
    """Resolve the backend-local mirror directory for dual-write (N194 双写).

    Backend 本地镜像路径: ``<BASE_DIR>/debug/<exec_dir_name>/run.log``.
    BASE_DIR 是 backend/ 工作目录, 与归一化目录 d:/code/GAF/debug 同级但隔离,
    让 backend 自己排查时也能在本地翻日志, 不必去归一化目录跨应用找.

    dispatch_task 会同步创建镜像目录 (目录名与归一化目录一致), 所以这里反查
    命中即可. 找不到说明 dispatch_task 还没执行或 BASE_DIR 未就绪 → 返回 None
    让 caller 跳过镜像写入 (只写归一化目录).

    Args:
        execution_id: Execution identifier from contextvar.

    Returns:
        Backend 本地镜像目录路径, 或 None 当:
        - execution_id 为空 / "_global" (无执行上下文, 不需要镜像)
        - Django settings 未就绪 (无法读 BASE_DIR)
        - 镜像目录尚未创建 (dispatch_task 还没执行到镜像创建步骤)
    """
    if not execution_id or execution_id == "_global":
        return None
    try:
        from django.conf import settings  # type: ignore[import]
        base_dir = getattr(settings, "BASE_DIR", None)
        if base_dir is None:
            return None
        # BASE_DIR 是 Path 对象, 指向 backend/ 工作目录
        # 镜像根目录: <backend>/debug/, 子目录名与归一化目录一致 (由 dispatch_task 创建)
        mirror_root = os.path.join(str(base_dir), "debug")
        from gaf_core.debug_path import find_exec_dir_by_id
        return find_exec_dir_by_id(mirror_root, execution_id)
    except Exception:
        return None


def _write_log_line(log_path: str, line: str) -> None:
    """Append a single log line to ``log_path``, creating parent dirs lazily.

    Shared helper for dual-write (归一化 + backend 本地镜像). Failures are
    swallowed by the caller (emit) — this helper just does the file write.
    """
    log_dir = os.path.dirname(log_path)
    os.makedirs(log_dir, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


class FileLogHandler(logging.Handler):
    """Archive log records to ``<debug_dir>/<exec_dir>/run.log``.

    Replaces the legacy ``DatabaseLogHandler`` (spec §2.2). Records are
    written to per-execution files instead of the ``LogEntry`` table —
    the table is kept read-only for historical queries.

    Location selection (N194 归一化 + B1 系统日志路径):
    - If ``current_execution_id`` contextvar is set →
      ``<debug_dir>/<YYYYMMDD_HHMMSS>_<safe_task_name>_<exec_id_suffix>/run.log``
      (反查 agent 已创建的目录)
    - Otherwise → ``<debug_dir>/<YYYYMMDD>/backend/system/<HH>/django.log``
      (B1: CLI, request-scope logs; 按日期+小时分桶, 自动轮转; 文件名 django.log
      与执行日志 run.log 区分)

    Line format (single line, append-friendly):
    ``[<timestamp>] [<level>] [<source>] [<trace_id>] <message>\\n<traceback>``

    Only records at or above ``LOG_DB_LEVEL`` (default ``WARNING``) are
    archived, matching the legacy threshold. The threshold is
    configurable via the ``LOG_DB_LEVEL`` environment variable.

    Real-time push: after writing, broadcasts a slim payload to
    ``LOGS_GROUP`` so ``LogStreamConsumer`` at ``/ws/logs/`` can push to
    frontend clients. Best-effort — channel layer failures are silently
    dropped since the file write already succeeded.

    Errors during emission are written to stderr (NOT via the logging
    framework) to prevent recursion.
    """

    LEVEL_CHOICES = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')

    def __init__(self, level=None, debug_dir: str | None = None):
        super().__init__()
        env_level = os.getenv('LOG_DB_LEVEL', 'WARNING').upper()
        if env_level in self.LEVEL_CHOICES:
            self.setLevel(getattr(logging, env_level))
        else:
            self.setLevel(logging.WARNING)
        # Resolve debug_dir lazily at emit() time if not provided, so
        # settings changes after handler construction are honored.
        self._debug_dir_override = debug_dir

    def emit(self, record):
        """Write the record to the per-execution log file.

        Catches ALL exceptions to prevent logging recursion. On failure,
        writes a fallback message to stderr.
        """
        try:
            # Lazy imports to avoid AppConfig readiness issues at import time
            # (this handler may be instantiated during LOGGING dict setup,
            # before the Django app registry is fully loaded).
            from gaf_core.tracing.context import current_execution_id, current_trace_id

            level = record.levelname if record.levelname in self.LEVEL_CHOICES else 'INFO'
            message = record.getMessage()

            tb_text = ''
            if record.exc_info:
                tb_text = ''.join(tb_module.format_exception(*record.exc_info))

            # Read the current request's trace_id (None outside request scope).
            trace_id = current_trace_id.get()

            # Read the current execution_id — None means "no task in scope"
            # (CLI, request-scope logs). Falls back to "_global" so the
            # records still land somewhere queryable.
            execution_id = current_execution_id.get() or "_global"

            debug_dir_root = _resolve_debug_dir(self._debug_dir_override)
            # N194 归一化: 反查 agent 已创建的 <exec_dir>, 找不到则降级到系统日志路径.
            log_dir = _resolve_exec_log_dir(debug_dir_root, execution_id)
            # B1: 系统日志 (无 execution_id) 文件名为 django.log, 执行日志为 run.log.
            # 用文件名区分两类日志, 避免 system 目录混入执行日志, 也避免 exec 目录
            # 混入系统日志 (dispatch_task 未就绪的极短窗口期降级写入).
            log_filename = "django.log" if execution_id == "_global" else "run.log"
            log_path = os.path.join(log_dir, log_filename)

            # Format the timestamp from record.created (float epoch seconds)
            # so all lines share a consistent format regardless of locale.
            timestamp = datetime.fromtimestamp(record.created).strftime(
                "%Y-%m-%d %H:%M:%S.%f"[:-3],  # truncate microseconds to ms
            )

            # Build the line. trace_id is omitted entirely when None so
            # the line stays clean for non-request-scope logs (CLI etc.).
            parts = [
                f"[{timestamp}]",
                f"[{level}]",
                f"[{record.name}]",
            ]
            if trace_id:
                parts.append(f"[trace_id={trace_id}]")
            parts.append(message)
            line = " ".join(parts)

            if tb_text:
                line += "\n" + tb_text.rstrip()
            line += "\n"

            # N194 双写 (2026-07-28): 主写归一化目录, 镜像写 backend 本地目录.
            # 归一化目录是前端查询入口 + 跨应用聚合点; 镜像目录让 backend 自身
            # 排错时不必跨应用找日志. 镜像失败不影响主写 (best-effort).
            _write_log_line(log_path, line)

            mirror_dir = _resolve_backend_mirror_dir(execution_id)
            if mirror_dir:
                mirror_path = os.path.join(mirror_dir, "run.log")
                with contextlib.suppress(OSError):
                    # 镜像写入失败不阻塞主流程 — 归一化目录已写成功, 前端能查到.
                    _write_log_line(mirror_path, line)

            # Broadcast to /ws/logs/ subscribers for real-time push.
            # Failures here (no channel layer, redis down) are silently
            # dropped — the file write already succeeded.
            self._broadcast_to_logs_group(
                timestamp=timestamp,
                level=level,
                source=record.name,
                message=message,
                traceback=tb_text,
                trace_id=trace_id,
                execution_id=execution_id,
            )

        except Exception:
            # Swallow all errors (OSError, ImportError, etc.) to prevent
            # recursion. Write fallback to stderr directly — do NOT use
            # the logging framework here.
            with contextlib.suppress(Exception):
                sys.stderr.write(
                    f'[FileLogHandler] Failed to archive log: '
                    f'{record.getMessage()}\n'
                )

    # Redis 广播不可用缓存: 每次失败后延迟重试, 避免频繁超时
    _redis_broadcast_disabled_until = 0.0
    # 重试间隔 (秒): 第一次失败后等 60s 再试, 之后每次翻倍 (最长 300s)
    _redis_broadcast_retry_interval = 60.0

    def _broadcast_to_logs_group(
        self,
        timestamp: str,
        level: str,
        source: str,
        message: str,
        traceback: str,
        trace_id: str | None,
        execution_id: str,
    ):
        """Broadcast a slim log payload to the LOGS_GROUP for real-time push.

        ``LogStreamConsumer`` at ``/ws/logs/`` picks this up and echoes
        it to all connected frontend LogCenterPage clients. The payload
        mirrors the legacy ``LogEntry`` shape so the frontend stays
        backward-compatible without needing to know whether the record
        came from the DB or a file.

        N198 优化: 缓存 Redis 不可用状态, 避免每次 emit 都重试 4s 超时.
        首次失败后等待 60s 再试, 后续指数退避至最长 300s. Redis 恢复后
        自动恢复正常广播 (下一次 group_send 成功时重置缓存).
        """
        now = time.time()
        if now < FileLogHandler._redis_broadcast_disabled_until:
            return

        try:
            from channels.layers import get_channel_layer

            from gaf_core.async_utils import call_async_with_timeout

            channel_layer = get_channel_layer()
            if channel_layer is None:
                return
            # TD-396 跟进: 日志广播也走 channels group_send. channels_redis 半开
            # 连接 (服务端关闭而客户端 socket 不自知) 会让 group_send await 永久
            # 挂起且忽略取消 — 日志路径无兜底的话, 任何一行日志都会卡死请求线程
            # 导致假死. call_async_with_timeout 把调用挪到 worker 线程并按墙钟
            # 超时返回; 超时抛 TimeoutError 进入下方 N198 退避分支.
            async def _send_log_message():
                await channel_layer.group_send(
                    'logs',
                    {
                        'type': 'log.entry',
                        'payload': {
                            # No DB PK available — use a synthetic id so the
                            # frontend payload shape stays consistent.
                            'id': None,
                            'timestamp': timestamp,
                            'level': level,
                            'source': source,
                            'message': message,
                            'traceback': traceback,
                            'trace_id': trace_id,
                            'execution_id': execution_id,
                            # Legacy fields kept for frontend compat; null
                            # since we no longer read from LogEntry.
                            'task_id': None,
                            'agent_id': None,
                            'device_id': None,
                            'occurrence_count': 1,
                            'first_seen': timestamp,
                            'last_seen': timestamp,
                        },
                    },
                )

            call_async_with_timeout(_send_log_message, timeout=2.0)
            # 广播成功 → 重置退避, 下次正常广播
            FileLogHandler._redis_broadcast_disabled_until = 0.0
            FileLogHandler._redis_broadcast_retry_interval = 60.0
        except Exception:
            # Channel layer unavailable (redis down, not configured).
            # The file write already succeeded; real-time push is
            # best-effort. 缓存失败状态, 避免频繁重试超时.
            FileLogHandler._redis_broadcast_disabled_until = now + FileLogHandler._redis_broadcast_retry_interval
            # 指数退避: 60s → 120s → 240s → 300s (max)
            FileLogHandler._redis_broadcast_retry_interval = min(
                FileLogHandler._redis_broadcast_retry_interval * 2,
                300.0,
            )


# Backward-compat alias — legacy imports (LOGGING dict, tests, views)
# continue to work but new code should use FileLogHandler directly.
# The LogEntry table is no longer written to by this handler (spec §2.2).
DatabaseLogHandler = FileLogHandler
