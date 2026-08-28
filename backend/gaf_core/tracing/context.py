"""Shared contextvars for trace_id + execution_id propagation.

Provides the single source of truth for:

- ``current_trace_id`` — set by ``gaf_core.tracing.middleware.TracingMiddleware``
  (producer), read by ``gaf_core.handlers.FileLogHandler`` (consumer)
  so each log line can be correlated back to its originating HTTP request
  without coupling to the request object.
- ``current_execution_id`` — set by task execution entry points
  (producer), read by ``gaf_core.handlers.FileLogHandler`` (consumer)
  so log lines are archived to ``logs/<execution_id>/run.log`` instead
  of being written to the ``LogEntry`` table (spec §2.2).

Both contextvars are thread-safe and async-safe: ``ContextVar.set``
scopes the value to the current Python ``context``, which Django's
request/response cycle (sync or async) honors. Each request / task
execution gets its own scope, so concurrent requests in multi-threaded
/ async deployments do not clobber each other's trace_id or
execution_id.
"""

import contextvars

# Producer: TracingMiddleware.__call__ sets this after generating trace_id.
# Consumer: FileLogHandler.emit reads this when writing the log line.
# Default is None so log records emitted outside a request scope (e.g. CLI
# management commands, Celery workers without request context) simply get
# trace_id=None and remain persistence-friendly.
current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_trace_id", default=None
)

# Producer: TaskExecution entry points (orchestrator / pipeline runner)
# set this when a task starts running.
# Consumer: FileLogHandler.emit reads this to archive the record to
# ``<debug_dir>/<YYYYMMDD>/<pipeline>/<HHMMSS_suffix>/run.log`` (嵌套结构, 2026-07-29).
# Default is None so log records emitted outside a task execution scope fall back to
# ``<debug_dir>/_global/run.log`` (spec §2.2 / §8.1).
current_execution_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_execution_id", default=None
)
