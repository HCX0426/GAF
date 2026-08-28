"""Frontend console JSONL logger (C3, spec 2026-07-30-debug-directory-restructure).

``FrontendConsoleLogger`` writes frontend crash reports (and future
frontend-originated log events) to::

    <debug_dir>/<YYYYMMDD>/frontend/<safe_page_slug>/<HH>/console.jsonl

Why per-page_slug bucketing (not per-pipeline):
  1. Most frontend errors happen during page interaction (form validation,
     routing, render), not during pipeline execution.
  2. The same page may trigger multiple pipelines (Dashboard quick-run),
     and the same pipeline may be triggered from multiple pages
     (TaskEditor preview + Dashboard quick-run).
  3. "Where did the user encounter the problem" is the most useful
     first-cut filter for frontend UX debugging — page_slug matches that
     mental model.

Each emitted line is a JSON object::

    {"timestamp": "...", "level": "error", "trace_id": "...",
     "page_slug": "...", "event": "frontend.error",
     "trigger": "error_boundary", "message": "...", "stack": "...",
     "page_url": "...", "session_id": "..."}

trace_id is propagated from the originating HTTP request (set by
``TracingMiddleware``) so AI debugging can ``grep trace-xxx`` across
agent/backend/frontend logs to correlate a single user flow.

Hour-bucketing: writes append to the same ``console.jsonl`` within the
same hour; when the hour changes, a new file is created under the new
``<HH>/`` directory. Mirrors ``BackendTaskLogger`` / ``StructuredLogger``.

Robustness: ``log()`` swallows all exceptions (OSError, etc.) so a
logging failure never blocks the ``FrontendErrorReportView`` endpoint
from returning 204 to the browser — mirrors ``BackendTaskLogger``'s
best-effort contract.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Mirror of gaf_core.task_logger._MAX_PIPELINE_NAME_LEN / _sanitize_pipeline_name.
# Duplicated here to avoid cross-module coupling; F段归一化 will consolidate.
_MAX_PAGE_SLUG_LEN = 40
_PAGE_SLUG_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_page_slug(slug: str) -> str:
    """Make page_slug safe for use as a directory name.

    Defense in depth: frontend ``pageSlug.ts`` already sanitizes, but the
    backend cannot trust the client. Strips path separators / control
    chars so an attacker-supplied ``../etc/passwd`` cannot escape the
    ``frontend/`` bucket.

    Returns ``"unknown"`` for empty / unsanitizable input — never an
    empty string (would create ``debug/<date>/frontend//HH/``).
    """
    if not slug or not isinstance(slug, str):
        return "unknown"
    safe = _PAGE_SLUG_UNSAFE_CHARS.sub("_", slug)
    safe = safe.replace(" ", "_")
    safe = safe.strip("._")
    if not safe:
        return "unknown"
    return safe[:_MAX_PAGE_SLUG_LEN]


class FrontendConsoleLogger:
    """Per-page_slug structured JSONL logger for frontend-originated events.

    Writes events to
    ``<debug_root>/<YYYYMMDD>/frontend/<safe_page_slug>/<HH>/console.jsonl``.

    Construction captures the immutable identity field (``page_slug``) so
    each ``log()`` call only needs the event name, level, and payload.
    Matches the agent's ``StructuredLogger`` construction pattern (set
    identity once, log many).

    Args:
        debug_root: Debug root directory (e.g. ``"d:/code/GAF/debug"``).
        page_slug: Frontend page slug (sanitized for directory use).
        trace_id: Full trace_id UUID propagated from the originating HTTP
            request (empty string when no request scope, e.g. anonymous
            crash before trace_id is set).
    """

    def __init__(
        self,
        debug_root: str,
        page_slug: str,
        trace_id: str = "",
    ):
        self._debug_root = debug_root or "./debug"
        self._page_slug_raw = page_slug or ""
        self._page_slug_safe = _sanitize_page_slug(self._page_slug_raw)
        self._trace_id = str(trace_id or "")

        # Cached current-hour state — when the hour changes, we re-resolve
        # the file path so a new ``console.jsonl`` is created under the
        # new ``<HH>/`` directory.
        self._current_hour: str | None = None
        self._current_log_path: str | None = None

    def log(
        self,
        event: str,
        payload: dict[str, Any] | None = None,
        level: str = "error",
    ) -> None:
        """Write a single JSONL event line to the per-hour console log.

        Best-effort: swallows all exceptions (OSError, etc.) so logging
        failures never block the FrontendErrorReportView endpoint.
        Mirrors ``BackendTaskLogger``'s robustness contract.

        Args:
            event: Short event identifier (e.g. ``"frontend.error"``).
            payload: Optional dict merged into the JSON line at top level.
                Expected keys for ``frontend.error``: ``trigger``,
                ``message``, ``stack``, ``page_url``, ``session_id``,
                ``error_type``, ``source``, ``lineno``, ``colno``,
                ``user_agent``, ``component_stack``.
            level: Log level string (default ``"error"`` — frontend
                reports are crash-level by default; future
                ``frontend.console`` events may use ``"info"``).
        """
        try:
            now = datetime.now()
            hour_part = now.strftime("%H")

            # Hour rollover: re-resolve the file path so the new hour's
            # events land in a fresh console.jsonl under the new <HH>/.
            if hour_part != self._current_hour or self._current_log_path is None:
                date_part = now.strftime("%Y%m%d")
                log_dir = os.path.join(
                    self._debug_root,
                    date_part,
                    "frontend",
                    self._page_slug_safe,
                    hour_part,
                )
                self._current_log_path = os.path.join(log_dir, "console.jsonl")
                self._current_hour = hour_part

            # Build the JSONL line. Required identity fields first, then
            # payload merged at top level so consumers can read
            # ``rec["message"]`` instead of ``rec["payload"]["message"]``.
            record: dict[str, Any] = {
                "timestamp": now.isoformat(timespec="milliseconds"),
                "level": level,
                "trace_id": self._trace_id,
                "page_slug": self._page_slug_raw,
                "event": event,
            }
            if payload:
                # payload wins on key conflicts — caller-supplied fields
                # are more specific than the logger's identity fields.
                record.update(payload)

            line = json.dumps(record, ensure_ascii=False, default=str) + "\n"

            # Lazy dir creation — caller may construct the logger before
            # the debug_root exists (e.g. tests with temp dirs).
            log_dir = os.path.dirname(self._current_log_path)
            os.makedirs(log_dir, exist_ok=True)
            with open(self._current_log_path, "a", encoding="utf-8") as f:
                f.write(line)

        except Exception:
            # Swallow all errors to prevent endpoint blocking.
            # Write a fallback to stderr (NOT via logging framework) to
            # avoid recursion — mirrors BackendTaskLogger's pattern.
            with contextlib.suppress(Exception):
                import sys
                sys.stderr.write(
                    f"[FrontendConsoleLogger] Failed to write event "
                    f"'{event}' for page_slug={self._page_slug_raw}: "
                    f"trace_id={self._trace_id}\n"
                )

    def close(self) -> None:
        """Release any cached state.

        Currently a no-op since we don't hold open file handles (each
        ``log()`` call opens, writes, and closes the file). Kept for API
        symmetry with ``BackendTaskLogger.close()``.
        """
        # Reset cached path so a subsequent log() call re-resolves the
        # hour bucket — useful if close() is followed by more calls in
        # test scenarios.
        self._current_hour = None
        self._current_log_path = None
