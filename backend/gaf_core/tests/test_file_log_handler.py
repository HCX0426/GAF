"""Tests for FileLogHandler (spec 阶段 4 — 任务 4.1 + B1 系统日志路径).

FileLogHandler replaces DatabaseLogHandler (spec §2.2). Records are
archived to ``<debug_dir>/<exec_dir>/run.log`` (N194 归一化 + 嵌套结构
2026-07-29) instead of the ``LogEntry`` table. ``execution_id`` is
sourced from the ``tracing.context.current_execution_id`` contextvar;
when unset, records fall back to ``<debug_dir>/<YYYYMMDD>/backend/system/<HH>/django.log``
(B1, spec 2026-07-30-debug-directory-restructure: 按日期+小时分桶, 与新五层
目录结构对齐; 替代旧 ``_global/<YYYYMMDD>/run.log`` 单文件路径).

N194 嵌套结构 (2026-07-29): 期望路径从旧扁平
``<tmpdir>/logs/<exec_id>/run.log`` 改为嵌套
``<tmpdir>/<YYYYMMDD>/<task_name>/<HHMMSS_suffix>/run.log``.
测试需先调 ``build_execution_debug_dir`` 预创建 exec 目录 (模拟
dispatch_task / pipeline.execute 的行为), FileLogHandler 才能通过
``find_exec_dir_by_id`` 反查到目录并写入.

Covers:
- emit() writes record to the per-execution log file
- fallback to <YYYYMMDD>/backend/system/<HH>/django.log when no execution_id is set (B1)
- trace_id from current_trace_id contextvar is included in the line
- exceptions are swallowed (no recursion)
- WebSocket broadcast remains best-effort (failures do not raise)
"""
import logging
import os
import tempfile
from datetime import datetime
from unittest import mock

from django.test import TestCase

from gaf_core.handlers import FileLogHandler
from gaf_core.tracing.context import current_execution_id, current_trace_id


def _make_record(msg: str, level: int = logging.WARNING, name: str = "test") -> logging.LogRecord:
    """Build a minimal LogRecord for handler.emit()."""
    return logging.LogRecord(
        name=name,
        level=level,
        pathname="",
        lineno=0,
        msg=msg,
        args=(),
        exc_info=None,
    )


def _precreate_exec_dir(tmpdir: str, execution_id: str, task_name: str = "TestTask") -> str:
    """Pre-create the per-execution dir like dispatch_task would.

    FileLogHandler._resolve_exec_log_dir() calls find_exec_dir_by_id()
    to reverse-lookup the exec dir from execution_id. Without pre-creation
    the handler falls back to _global/<YYYYMMDD>/run.log.
    """
    from gaf_core.debug_path import build_execution_debug_dir
    fixed_time = datetime(2026, 7, 28, 15, 30, 0)
    exec_dir = build_execution_debug_dir(
        tmpdir, execution_id, task_name, start_time=fixed_time,
    )
    os.makedirs(exec_dir, exist_ok=True)
    return exec_dir


class FileLogHandlerBasicTest(TestCase):
    """FileLogHandler — file emission + per-execution archiving."""

    def test_emit_writes_to_execution_dir(self):
        """emit() should write to <exec_dir>/run.log (嵌套结构)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exec_dir = _precreate_exec_dir(tmpdir, "exec-abc", "WriteTestTask")
            handler = FileLogHandler(debug_dir=tmpdir)
            token = current_execution_id.set("exec-abc")
            try:
                handler.emit(_make_record("hello world"))
            finally:
                current_execution_id.reset(token)
            handler.close()

            log_path = os.path.join(exec_dir, "run.log")
            self.assertTrue(os.path.exists(log_path),
                            f"run.log not at {log_path}; tmpdir: {os.listdir(tmpdir)}")
            with open(log_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("hello world", content)

    def test_emit_falls_back_to_system_dir_without_execution_id(self):
        """Without execution_id, records go to <debug_dir>/<YYYYMMDD>/backend/system/<HH>/django.log (B1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = FileLogHandler(debug_dir=tmpdir)
            # No execution_id set
            handler.emit(_make_record("no exec context"))
            handler.close()

            # B1: 系统日志路径 YYYYMMDD/backend/system/HH/django.log (按日期+小时分桶)
            now = datetime.now()
            date_part = now.strftime("%Y%m%d")
            hour_part = now.strftime("%H")
            log_path = os.path.join(tmpdir, date_part, "backend", "system", hour_part, "django.log")
            self.assertTrue(os.path.exists(log_path),
                            f"django.log not at {log_path}; tmpdir: {os.listdir(tmpdir)}")
            with open(log_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("no exec context", content)

    def test_emit_appends_to_existing_file(self):
        """Multiple emit() calls append to the same file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exec_dir = _precreate_exec_dir(tmpdir, "exec-append", "AppendTestTask")
            handler = FileLogHandler(debug_dir=tmpdir)
            token = current_execution_id.set("exec-append")
            try:
                handler.emit(_make_record("line 1"))
                handler.emit(_make_record("line 2"))
            finally:
                current_execution_id.reset(token)
            handler.close()

            log_path = os.path.join(exec_dir, "run.log")
            with open(log_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("line 1", content)
            self.assertIn("line 2", content)

    def test_emit_includes_trace_id_when_set(self):
        """When current_trace_id is set, the line includes [trace_id]."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exec_dir = _precreate_exec_dir(tmpdir, "exec-trace", "TraceTestTask")
            handler = FileLogHandler(debug_dir=tmpdir)
            token_exec = current_execution_id.set("exec-trace")
            token_trace = current_trace_id.set("trace-xyz-789")
            try:
                handler.emit(_make_record("with trace"))
            finally:
                current_trace_id.reset(token_trace)
                current_execution_id.reset(token_exec)
            handler.close()

            log_path = os.path.join(exec_dir, "run.log")
            with open(log_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("trace-xyz-789", content)
            self.assertIn("with trace", content)

    def test_emit_does_not_include_trace_id_when_unset(self):
        """Without current_trace_id, the line should not contain [None]."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exec_dir = _precreate_exec_dir(tmpdir, "exec-no-trace", "NoTraceTestTask")
            handler = FileLogHandler(debug_dir=tmpdir)
            # Make sure trace_id is None
            self.assertIsNone(current_trace_id.get())
            token = current_execution_id.set("exec-no-trace")
            try:
                handler.emit(_make_record("clean line"))
            finally:
                current_execution_id.reset(token)
            handler.close()

            log_path = os.path.join(exec_dir, "run.log")
            with open(log_path, encoding="utf-8") as f:
                content = f.read()
            # Should not literally contain "None" as trace_id placeholder
            self.assertNotIn("[trace_id=None]", content)
            self.assertIn("clean line", content)

    def test_emit_swallows_exceptions_to_prevent_recursion(self):
        """If file write fails, emit() must not raise.

        B1: trigger failure by making ``<YYYYMMDD>/backend/`` a file (not a dir)
        so ``os.makedirs(<YYYYMMDD>/backend/system/HH, exist_ok=True)`` raises
        FileExistsError when traversing the file as a directory.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-create <YYYYMMDD>/ dir, then a FILE where backend/ dir would be —
            # forces makedirs to fail when handler tries to create the system subdir.
            date_part = datetime.now().strftime("%Y%m%d")
            date_dir = os.path.join(tmpdir, date_part)
            os.makedirs(date_dir, exist_ok=True)
            backend_blocker = os.path.join(date_dir, "backend")
            with open(backend_blocker, "w") as f:
                f.write("blocker")

            handler = FileLogHandler(debug_dir=tmpdir)
            # No execution_id → handler resolves to <YYYYMMDD>/backend/system/HH/
            # but backend/ is a file, so makedirs fails.
            try:
                # Should not raise despite the path being blocked by a file
                handler.emit(_make_record("will fail silently"))
            finally:
                handler.close()
            # If we got here without exception, the test passes.

    def test_emit_handles_traceback_when_exc_info_set(self):
        """Records with exc_info should include traceback text in the line."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exec_dir = _precreate_exec_dir(tmpdir, "exec-tb", "TbTestTask")
            handler = FileLogHandler(debug_dir=tmpdir)
            token = current_execution_id.set("exec-tb")
            try:
                try:
                    raise ValueError("boom")
                except ValueError:
                    import sys
                    record = logging.LogRecord(
                        name="test", level=logging.ERROR, pathname="",
                        lineno=0, msg="error occurred",
                        args=(), exc_info=sys.exc_info(),
                    )
                    handler.emit(record)
            finally:
                current_execution_id.reset(token)
            handler.close()

            log_path = os.path.join(exec_dir, "run.log")
            with open(log_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("ValueError", content)
            self.assertIn("boom", content)

    def test_broadcast_to_logs_group_is_best_effort(self):
        """Broadcast failures (no channel layer) should not raise."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _precreate_exec_dir(tmpdir, "exec-broadcast", "BroadcastTestTask")
            handler = FileLogHandler(debug_dir=tmpdir)
            token = current_execution_id.set("exec-broadcast")
            try:
                # Mock get_channel_layer to return None — broadcast
                # should silently skip. The import lives inside the
                # method, so we patch the source module directly.
                with mock.patch(
                    "channels.layers.get_channel_layer", return_value=None,
                ):
                    handler.emit(_make_record("broadcast test"))
            finally:
                current_execution_id.reset(token)
            handler.close()
            # If we got here without exception, the test passes.


class FileLogHandlerLevelTest(TestCase):
    """FileLogHandler — level threshold via LOG_DB_LEVEL env."""

    def test_default_level_is_warning(self):
        """Without LOG_DB_LEVEL set, handler level defaults to WARNING."""
        handler = FileLogHandler()
        self.assertEqual(handler.level, logging.WARNING)
        handler.close()

    def test_level_configurable_via_env(self):
        """LOG_DB_LEVEL env var should configure the handler level."""
        with mock.patch.dict(os.environ, {"LOG_DB_LEVEL": "ERROR"}):
            handler = FileLogHandler()
            self.assertEqual(handler.level, logging.ERROR)
        handler.close()


class FileLogHandlerSystemLogDirTest(TestCase):
    """B1 (spec 2026-07-30-debug-directory-restructure): system log path.

    Non-execution logs (no ``execution_id``) now write to
    ``debug/YYYYMMDD/backend/system/HH/django.log`` instead of the old
    ``_global/<YYYYMMDD>/run.log`` path. Hour-bucketing rotates files
    automatically.
    """

    def test_system_log_writes_to_backend_system_hour_bucket(self):
        """Without execution_id, records go to debug/YYYYMMDD/backend/system/HH/django.log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = FileLogHandler(debug_dir=tmpdir)
            # No execution_id set — system log path
            handler.emit(_make_record("system log entry"))
            handler.close()

            now = datetime.now()
            date_part = now.strftime("%Y%m%d")
            hour_part = now.strftime("%H")
            expected_path = os.path.join(
                tmpdir, date_part, "backend", "system", hour_part, "django.log",
            )
            self.assertTrue(
                os.path.exists(expected_path),
                f"django.log not at {expected_path}; tmpdir: {os.listdir(tmpdir)}",
            )
            with open(expected_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("system log entry", content)

    def test_system_log_filename_is_django_log(self):
        """System log file name should be 'django.log' (not 'run.log')."""
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = FileLogHandler(debug_dir=tmpdir)
            handler.emit(_make_record("check filename"))
            handler.close()

            now = datetime.now()
            date_part = now.strftime("%Y%m%d")
            hour_part = now.strftime("%H")
            system_dir = os.path.join(
                tmpdir, date_part, "backend", "system", hour_part,
            )
            files = os.listdir(system_dir)
            self.assertIn("django.log", files)
            self.assertNotIn("run.log", files)

    def test_system_log_hour_rollover_creates_new_file(self):
        """Hour change creates a new file under the new HH directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            handler = FileLogHandler(debug_dir=tmpdir)

            # Emit at hour 05
            fixed_time_1 = datetime(2026, 7, 30, 5, 12, 33)
            with mock.patch("gaf_core.handlers.datetime") as mock_dt:
                mock_dt.now.return_value = fixed_time_1
                mock_dt.fromtimestamp = datetime.fromtimestamp
                handler.emit(_make_record("hour 05 log"))

            # Emit at hour 06 (hour rollover)
            fixed_time_2 = datetime(2026, 7, 30, 6, 5, 10)
            with mock.patch("gaf_core.handlers.datetime") as mock_dt:
                mock_dt.now.return_value = fixed_time_2
                mock_dt.fromtimestamp = datetime.fromtimestamp
                handler.emit(_make_record("hour 06 log"))

            handler.close()

            # Both hour buckets should exist
            path_05 = os.path.join(tmpdir, "20260730", "backend", "system", "05", "django.log")
            path_06 = os.path.join(tmpdir, "20260730", "backend", "system", "06", "django.log")
            self.assertTrue(os.path.exists(path_05), f"hour 05 file missing: {os.listdir(tmpdir)}")
            self.assertTrue(os.path.exists(path_06), f"hour 06 file missing: {os.listdir(tmpdir)}")

            with open(path_05, encoding="utf-8") as f:
                content_05 = f.read()
            with open(path_06, encoding="utf-8") as f:
                content_06 = f.read()
            self.assertIn("hour 05 log", content_05)
            self.assertIn("hour 06 log", content_06)

    def test_execution_log_still_uses_exec_dir(self):
        """With execution_id set, records still go to <exec_dir>/run.log (unchanged)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            exec_dir = _precreate_exec_dir(tmpdir, "exec-b1", "B1TestTask")
            handler = FileLogHandler(debug_dir=tmpdir)
            token = current_execution_id.set("exec-b1")
            try:
                handler.emit(_make_record("exec log entry"))
            finally:
                current_execution_id.reset(token)
            handler.close()

            log_path = os.path.join(exec_dir, "run.log")
            self.assertTrue(os.path.exists(log_path))
            with open(log_path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("exec log entry", content)
