"""Tests for BackendTaskLogger (spec B2 — 任务级 JSONL).

BackendTaskLogger writes per-task structured events to
``<debug_dir>/<YYYYMMDD>/backend/tasks/<safe_pipeline>/<HH>/execution.jsonl``
(B2, spec 2026-07-30-debug-directory-restructure).

Each line is a JSON object containing at minimum:
``{timestamp, level, trace_id, execution_id, pipeline_name, event, ...payload}``
so the agent's structured logs (``structured.jsonl``) and the backend's
task-level events (``execution.jsonl``) share a parallel layout under
the new five-layer directory structure.

Covers:
- log() writes JSONL line to the correct path
- line includes trace_id / execution_id / pipeline_name / event / timestamp / level
- payload fields are merged into the JSON line
- multiple log() calls append to the same file (same hour)
- hour rollover creates a new file under the new HH directory
- pipeline_name is sanitized for directory safety
- empty pipeline_name falls back to "unnamed"
- log() swallows exceptions (best-effort, like FileLogHandler)
- level defaults to "info" when not provided
"""
import json
import os
import tempfile
from datetime import datetime
from unittest import mock

from django.test import TestCase

from gaf_core.task_logger import BackendTaskLogger


def _read_jsonl(path: str) -> list[dict]:
    """Read a JSONL file and return a list of parsed dicts."""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class BackendTaskLoggerPathTest(TestCase):
    """B2: log() writes to <debug_dir>/<YYYYMMDD>/backend/tasks/<pipeline>/<HH>/execution.jsonl."""

    def test_log_writes_to_backend_tasks_hour_bucket(self):
        """log() should write to the new five-layer path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = BackendTaskLogger(
                debug_root=tmpdir,
                pipeline_name="MyPipeline",
                trace_id="trace-abc-123",
                execution_id="exec-xyz",
            )
            logger.log("task_started", {"task_id": 42})
            logger.close()

            now = datetime.now()
            date_part = now.strftime("%Y%m%d")
            hour_part = now.strftime("%H")
            expected_path = os.path.join(
                tmpdir, date_part, "backend", "tasks", "MyPipeline", hour_part, "execution.jsonl",
            )
            self.assertTrue(
                os.path.exists(expected_path),
                f"execution.jsonl not at {expected_path}; tmpdir: {os.listdir(tmpdir)}",
            )

    def test_log_filename_is_execution_jsonl(self):
        """File name should be 'execution.jsonl' (parallel to agent's structured.jsonl)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = BackendTaskLogger(
                debug_root=tmpdir,
                pipeline_name="FilenameTest",
                trace_id="t",
                execution_id="e",
            )
            logger.log("event", {})
            logger.close()

            now = datetime.now()
            date_part = now.strftime("%Y%m%d")
            hour_part = now.strftime("%H")
            tasks_dir = os.path.join(
                tmpdir, date_part, "backend", "tasks", "FilenameTest", hour_part,
            )
            files = os.listdir(tasks_dir)
            self.assertIn("execution.jsonl", files)


class BackendTaskLoggerLineFormatTest(TestCase):
    """B2: each JSONL line contains required fields."""

    def test_line_includes_required_fields(self):
        """Line should include trace_id, execution_id, pipeline_name, event, timestamp, level."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = BackendTaskLogger(
                debug_root=tmpdir,
                pipeline_name="FieldsTest",
                trace_id="trace-fields-001",
                execution_id="exec-fields-001",
            )
            logger.log("node_completed", {"node_id": "n1"})
            logger.close()

            now = datetime.now()
            date_part = now.strftime("%Y%m%d")
            hour_part = now.strftime("%H")
            path = os.path.join(
                tmpdir, date_part, "backend", "tasks", "FieldsTest", hour_part, "execution.jsonl",
            )
            records = _read_jsonl(path)
            self.assertEqual(len(records), 1)
            rec = records[0]
            self.assertEqual(rec["trace_id"], "trace-fields-001")
            self.assertEqual(rec["execution_id"], "exec-fields-001")
            self.assertEqual(rec["pipeline_name"], "FieldsTest")
            self.assertEqual(rec["event"], "node_completed")
            self.assertIn("timestamp", rec)
            self.assertIn("level", rec)

    def test_payload_fields_merged_into_line(self):
        """payload dict fields should appear at the top level of the JSON line."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = BackendTaskLogger(
                debug_root=tmpdir,
                pipeline_name="PayloadTest",
                trace_id="t",
                execution_id="e",
            )
            logger.log("node_completed", {"node_id": "n1", "duration_ms": 123, "success": True})
            logger.close()

            now = datetime.now()
            path = os.path.join(
                tmpdir, now.strftime("%Y%m%d"), "backend", "tasks", "PayloadTest",
                now.strftime("%H"), "execution.jsonl",
            )
            rec = _read_jsonl(path)[0]
            self.assertEqual(rec["node_id"], "n1")
            self.assertEqual(rec["duration_ms"], 123)
            self.assertIs(rec["success"], True)

    def test_level_defaults_to_info(self):
        """When level is not provided, it should default to 'info'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = BackendTaskLogger(
                debug_root=tmpdir,
                pipeline_name="LevelDefault",
                trace_id="t",
                execution_id="e",
            )
            logger.log("event", {})  # no level arg
            logger.close()

            now = datetime.now()
            path = os.path.join(
                tmpdir, now.strftime("%Y%m%d"), "backend", "tasks", "LevelDefault",
                now.strftime("%H"), "execution.jsonl",
            )
            rec = _read_jsonl(path)[0]
            self.assertEqual(rec["level"], "info")

    def test_level_passed_through(self):
        """Explicit level should be recorded in the line."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = BackendTaskLogger(
                debug_root=tmpdir,
                pipeline_name="LevelExplicit",
                trace_id="t",
                execution_id="e",
            )
            logger.log("node_failed", {"node_id": "n2"}, level="error")
            logger.close()

            now = datetime.now()
            path = os.path.join(
                tmpdir, now.strftime("%Y%m%d"), "backend", "tasks", "LevelExplicit",
                now.strftime("%H"), "execution.jsonl",
            )
            rec = _read_jsonl(path)[0]
            self.assertEqual(rec["level"], "error")


class BackendTaskLoggerAppendTest(TestCase):
    """B2: multiple log() calls append to the same file (same hour)."""

    def test_multiple_logs_append_to_same_file(self):
        """Two log() calls in the same hour should append to the same execution.jsonl."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = BackendTaskLogger(
                debug_root=tmpdir,
                pipeline_name="AppendTest",
                trace_id="t",
                execution_id="e",
            )
            logger.log("event_a", {"seq": 1})
            logger.log("event_b", {"seq": 2})
            logger.log("event_c", {"seq": 3})
            logger.close()

            now = datetime.now()
            path = os.path.join(
                tmpdir, now.strftime("%Y%m%d"), "backend", "tasks", "AppendTest",
                now.strftime("%H"), "execution.jsonl",
            )
            records = _read_jsonl(path)
            self.assertEqual(len(records), 3)
            self.assertEqual([r["event"] for r in records], ["event_a", "event_b", "event_c"])
            self.assertEqual([r["seq"] for r in records], [1, 2, 3])


class BackendTaskLoggerHourRolloverTest(TestCase):
    """B2: hour rollover creates a new file under the new HH directory."""

    def test_hour_rollover_creates_new_file(self):
        """Hour change creates a new execution.jsonl under the new HH directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = BackendTaskLogger(
                debug_root=tmpdir,
                pipeline_name="RolloverTest",
                trace_id="t",
                execution_id="e",
            )

            # Emit at hour 05
            fixed_time_1 = datetime(2026, 7, 30, 5, 12, 33)
            with mock.patch("gaf_core.task_logger.datetime") as mock_dt:
                mock_dt.now.return_value = fixed_time_1
                mock_dt.fromtimestamp = datetime.fromtimestamp
                logger.log("hour_05_event", {})

            # Emit at hour 06 (rollover)
            fixed_time_2 = datetime(2026, 7, 30, 6, 5, 10)
            with mock.patch("gaf_core.task_logger.datetime") as mock_dt:
                mock_dt.now.return_value = fixed_time_2
                mock_dt.fromtimestamp = datetime.fromtimestamp
                logger.log("hour_06_event", {})

            logger.close()

            path_05 = os.path.join(tmpdir, "20260730", "backend", "tasks", "RolloverTest", "05", "execution.jsonl")
            path_06 = os.path.join(tmpdir, "20260730", "backend", "tasks", "RolloverTest", "06", "execution.jsonl")
            self.assertTrue(os.path.exists(path_05), f"hour 05 file missing: {os.listdir(tmpdir)}")
            self.assertTrue(os.path.exists(path_06), "hour 06 file missing")

            recs_05 = _read_jsonl(path_05)
            recs_06 = _read_jsonl(path_06)
            self.assertEqual(len(recs_05), 1)
            self.assertEqual(len(recs_06), 1)
            self.assertEqual(recs_05[0]["event"], "hour_05_event")
            self.assertEqual(recs_06[0]["event"], "hour_06_event")


class BackendTaskLoggerSanitizationTest(TestCase):
    """B2: pipeline_name is sanitized for directory safety."""

    def test_pipeline_name_sanitized(self):
        """Unsafe characters in pipeline_name should be replaced with '_'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = BackendTaskLogger(
                debug_root=tmpdir,
                pipeline_name='bad/name:with*chars',
                trace_id="t",
                execution_id="e",
            )
            logger.log("event", {})
            logger.close()

            now = datetime.now()
            # bad/name:with*chars → bad_name_with_chars (sanitized)
            tasks_root = os.path.join(tmpdir, now.strftime("%Y%m%d"), "backend", "tasks")
            entries = os.listdir(tasks_root)
            self.assertEqual(len(entries), 1)
            self.assertNotIn("/", entries[0])
            self.assertNotIn(":", entries[0])
            self.assertNotIn("*", entries[0])

    def test_empty_pipeline_name_uses_unnamed(self):
        """Empty pipeline_name should fall back to 'unnamed'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = BackendTaskLogger(
                debug_root=tmpdir,
                pipeline_name="",
                trace_id="t",
                execution_id="e",
            )
            logger.log("event", {})
            logger.close()

            now = datetime.now()
            tasks_root = os.path.join(tmpdir, now.strftime("%Y%m%d"), "backend", "tasks")
            entries = os.listdir(tasks_root)
            self.assertIn("unnamed", entries)


class BackendTaskLoggerRobustnessTest(TestCase):
    """B2: log() swallows exceptions (best-effort, like FileLogHandler)."""

    def test_log_swallows_oserror(self):
        """If file write fails, log() must not raise (best-effort)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Block the tasks dir by creating a file where the pipeline dir would be
            now = datetime.now()
            date_part = now.strftime("%Y%m%d")
            date_dir = os.path.join(tmpdir, date_part)
            os.makedirs(os.path.join(date_dir, "backend", "tasks"), exist_ok=True)
            blocker = os.path.join(date_dir, "backend", "tasks", "BlockTest")
            with open(blocker, "w") as f:
                f.write("blocker")

            logger = BackendTaskLogger(
                debug_root=tmpdir,
                pipeline_name="BlockTest",
                trace_id="t",
                execution_id="e",
            )
            # Should not raise despite the path being blocked by a file
            try:
                logger.log("event", {})
            finally:
                logger.close()
            # If we got here without exception, the test passes.

    def test_log_with_empty_trace_id_and_execution_id(self):
        """Empty trace_id/execution_id should still produce a valid JSONL line."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = BackendTaskLogger(
                debug_root=tmpdir,
                pipeline_name="EmptyIds",
                trace_id="",
                execution_id="",
            )
            logger.log("event", {})
            logger.close()

            now = datetime.now()
            path = os.path.join(
                tmpdir, now.strftime("%Y%m%d"), "backend", "tasks", "EmptyIds",
                now.strftime("%H"), "execution.jsonl",
            )
            rec = _read_jsonl(path)[0]
            self.assertEqual(rec["trace_id"], "")
            self.assertEqual(rec["execution_id"], "")
            self.assertEqual(rec["event"], "event")
