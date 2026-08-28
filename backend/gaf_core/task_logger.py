"""Backend task-level structured JSONL logger (B2, spec 2026-07-30-debug-directory-restructure).

``BackendTaskLogger`` writes per-task structured events to::

    <debug_dir>/<YYYYMMDD>/backend/tasks/<safe_pipeline>/<HH>/execution.jsonl

Parallel to the agent's ``structured.jsonl`` under the new five-layer
directory structure — both share the ``<YYYYMMDD>/<env>/<pipeline>/<HH>/``
layout so backend task events and agent execution events for the same
pipeline can be browsed side-by-side.

Each emitted line is a JSON object::

    {"timestamp": "...", "level": "info", "trace_id": "...",
     "execution_id": "...", "pipeline_name": "...", "event": "...",
     ...payload}

Required fields (always present):
- ``timestamp`` — ISO-format local time (sortable, with ms precision)
- ``level`` — log level string (``info`` / ``warning`` / ``error`` / ...)
- ``trace_id`` — full UUID, propagated from the originating HTTP request
- ``execution_id`` — backend execution identifier (e.g. ``exec-<pk>``)
- ``pipeline_name`` — sanitized pipeline name (also encoded in the path)
- ``event`` — short event identifier (e.g. ``task_started`` / ``node_completed``)

Payload fields are merged into the JSON line at the top level so consumers
can read them without an extra ``payload.`` prefix.

Hour-bucketing: writes are appended to the same ``execution.jsonl`` within
the same hour; when the hour changes, a new file is created under the new
``<HH>/`` directory. This caps file growth and aligns with the agent's
hour-bucketing scheme.

Robustness: ``log()`` swallows all exceptions (OSError, etc.) to ensure
task execution is never blocked by logging failures — mirroring
``FileLogHandler``'s best-effort semantics.
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

# Mirror of gaf_core.debug_path._MAX_TASK_NAME_LEN / _sanitize_task_name.
# Duplicated here to avoid circular imports (debug_path imports nothing from
# task_logger, but task_logger importing debug_path would create a tight
# coupling that F段 will归一化).
_MAX_PIPELINE_NAME_LEN = 40
_PIPELINE_NAME_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_pipeline_name(name: str) -> str:
    """Make pipeline_name safe for use as a directory name.

    Mirror of ``gaf_core.debug_path._sanitize_task_name``. F段 will归一化
    the duplication.
    """
    if not name:
        return "unnamed"
    safe = _PIPELINE_NAME_UNSAFE_CHARS.sub("_", name)
    safe = safe.replace(" ", "_")
    safe = safe.strip("._")
    if not safe:
        return "unnamed"
    return safe[:_MAX_PIPELINE_NAME_LEN]


class BackendTaskLogger:
    """Per-task structured JSONL logger.

    Writes events to ``<debug_root>/<YYYYMMDD>/backend/tasks/<safe_pipeline>/<HH>/execution.jsonl``.

    Construction captures the immutable identity fields (``trace_id``,
    ``execution_id``, ``pipeline_name``) so each ``log()`` call only needs
    the event name and payload. This matches the agent's
    ``StructuredLogger`` construction pattern (set identity once, log many).

    Args:
        debug_root: Debug root directory (e.g. ``"d:/code/GAF/debug"``).
        pipeline_name: Pipeline name (sanitized for directory use).
        trace_id: Full trace_id UUID (propagated from HTTP request).
        execution_id: Backend execution identifier (e.g. ``exec-<pk>``).
    """

    def __init__(
        self,
        debug_root: str,
        pipeline_name: str,
        trace_id: str,
        execution_id: str,
    ):
        self._debug_root = debug_root or "./debug"
        self._pipeline_name_raw = pipeline_name or ""
        self._pipeline_name_safe = _sanitize_pipeline_name(self._pipeline_name_raw)
        self._trace_id = str(trace_id or "")
        self._execution_id = str(execution_id or "")

        # Cached current-hour state — when the hour changes, we re-resolve
        # the file path so a new ``execution.jsonl`` is created under the
        # new ``<HH>/`` directory.
        self._current_hour: str | None = None
        self._current_log_path: str | None = None

    def log(self, event: str, payload: dict[str, Any] | None = None, level: str = "info") -> None:
        """Write a single JSONL event line to the per-hour execution log.

        Best-effort: swallows all exceptions (OSError, etc.) so logging
        failures never block task execution. Mirrors ``FileLogHandler``'s
        robustness contract.

        Args:
            event: Short event identifier (e.g. ``"task_started"``).
            payload: Optional dict merged into the JSON line at top level.
            level: Log level string (default ``"info"``).
        """
        try:
            now = datetime.now()
            hour_part = now.strftime("%H")

            # Hour rollover: re-resolve the file path so the new hour's
            # events land in a fresh execution.jsonl under the new <HH>/.
            if hour_part != self._current_hour or self._current_log_path is None:
                date_part = now.strftime("%Y%m%d")
                log_dir = os.path.join(
                    self._debug_root,
                    date_part,
                    "backend",
                    "tasks",
                    self._pipeline_name_safe,
                    hour_part,
                )
                self._current_log_path = os.path.join(log_dir, "execution.jsonl")
                self._current_hour = hour_part

            # Build the JSONL line. Required fields first, then payload
            # merged at top level so consumers can read ``rec["node_id"]``
            # instead of ``rec["payload"]["node_id"]``.
            record: dict[str, Any] = {
                "timestamp": now.isoformat(timespec="milliseconds"),
                "level": level,
                "trace_id": self._trace_id,
                "execution_id": self._execution_id,
                "pipeline_name": self._pipeline_name_raw,
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
            # Swallow all errors to prevent task execution blocking.
            # Write a fallback to stderr (NOT via logging framework) to
            # avoid recursion — mirrors FileLogHandler's pattern.
            with contextlib.suppress(Exception):
                import sys
                sys.stderr.write(
                    f"[BackendTaskLogger] Failed to write event "
                    f"'{event}' for execution_id={self._execution_id}: "
                    f"pipeline={self._pipeline_name_raw}\n"
                )

    def close(self) -> None:
        """Release any cached state.

        Currently a no-op since we don't hold open file handles (each
        ``log()`` call opens, writes, and closes the file). Kept for API
        symmetry with ``FileLogHandler.close()`` and to give a future
        optimization hook (e.g. keep file handle open across calls).
        """
        # Reset cached path so a subsequent log() call re-resolves the
        # hour bucket — useful if close() is followed by more calls in
        # test scenarios.
        self._current_hour = None
        self._current_log_path = None
