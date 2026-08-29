"""Tests for the frontend crash report endpoint (P0-10 + C3 spec 2026-07-30).

POST /api/v2/logs/frontend-errors/ — receives browser-side crashes
(window.onerror / unhandledrejection / React ErrorBoundary) and writes
them to the ``gaf_core.frontend_error`` logger so AI debugging can
correlate frontend failures with backend/agent errors.

C3 (spec 2026-07-30-debug-directory-restructure): the endpoint additionally
receives ``trace_id`` and ``page_slug`` and persists the report as JSONL
to ``debug/<YYYYMMDD>/frontend/<page_slug>/<HH>/console.jsonl`` so AI
debugging can browse frontend crashes by page alongside agent/backend logs.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def anon_client() -> APIClient:
    """Unauthenticated API client — frontend may crash before login."""
    return APIClient()


class TestFrontendErrorReport:
    """Functional tests for the FrontendErrorReportView endpoint."""

    url = "/api/v2/logs/frontend-errors/"

    def test_anonymous_post_accepted(self, anon_client: APIClient) -> None:
        """Anonymous POST is allowed — frontend may crash before auth."""
        with patch("gaf_core.views.frontend_error_logger") as mock_logger:
            resp = anon_client.post(
                self.url,
                {
                    "message": "TypeError: Cannot read properties of undefined",
                    "trigger": "window.onerror",
                    "source": "http://localhost:5173/assets/index.js",
                    "lineno": 42,
                    "colno": 17,
                    "error_type": "TypeError",
                    "stack": "TypeError: ...\n    at foo (index.js:42:17)",
                    "page_url": "http://localhost:5173/dashboard",
                    "user_agent": "Mozilla/5.0",
                    "session_id": "fsess-test-123",
                },
                format="json",
            )
        assert resp.status_code == 204
        # Logger received the error with a single concatenated message arg.
        assert mock_logger.error.call_count == 1
        logged_msg = mock_logger.error.call_args.args[0]
        assert len(mock_logger.error.call_args.args) == 1
        # Header line contains trigger + error_type + message
        assert "[window.onerror]" in logged_msg
        assert "TypeError" in logged_msg
        assert "Cannot read properties of undefined" in logged_msg
        # Stack appears on a separate line within the same message arg.
        assert "at foo (index.js:42:17)" in logged_msg

    def test_react_error_boundary_trigger(self, anon_client: APIClient) -> None:
        """React ErrorBoundary reports use trigger='error_boundary'."""
        with patch("gaf_core.views.frontend_error_logger") as mock_logger:
            resp = anon_client.post(
                self.url,
                {
                    "message": "Render failed",
                    "trigger": "error_boundary",
                    "error_type": "Error",
                    "stack": "Error: Render failed\n    at Component",
                    "page_url": "http://localhost:5173/tasks",
                },
                format="json",
            )
        assert resp.status_code == 204
        logged_msg = mock_logger.error.call_args.args[0]
        assert "[error_boundary]" in logged_msg

    def test_unhandled_rejection_trigger(self, anon_client: APIClient) -> None:
        """unhandledrejection trigger is accepted."""
        with patch("gaf_core.views.frontend_error_logger") as mock_logger:
            resp = anon_client.post(
                self.url,
                {
                    "message": "Promise rejected",
                    "trigger": "unhandledrejection",
                },
                format="json",
            )
        assert resp.status_code == 204
        assert "[unhandledrejection]" in mock_logger.error.call_args.args[0]

    def test_empty_message_returns_204_silently(self, anon_client: APIClient) -> None:
        """Empty message — drop silently (can't attribute without message)."""
        with patch("gaf_core.views.frontend_error_logger") as mock_logger:
            resp = anon_client.post(
                self.url,
                {"trigger": "window.onerror"},
                format="json",
            )
        assert resp.status_code == 204
        # Logger NOT called — we dropped the malformed payload
        assert mock_logger.error.call_count == 0

    def test_unknown_trigger_normalized_to_unknown(self, anon_client: APIClient) -> None:
        """Unknown trigger value is normalized to 'unknown' in log header."""
        with patch("gaf_core.views.frontend_error_logger") as mock_logger:
            resp = anon_client.post(
                self.url,
                {
                    "message": "weird error",
                    "trigger": "made_up_trigger",
                },
                format="json",
            )
        assert resp.status_code == 204
        assert "[unknown]" in mock_logger.error.call_args.args[0]

    def test_missing_trigger_normalized_to_unknown(self, anon_client: APIClient) -> None:
        """Missing trigger field is normalized to 'unknown'."""
        with patch("gaf_core.views.frontend_error_logger") as mock_logger:
            resp = anon_client.post(
                self.url,
                {"message": "no trigger"},
                format="json",
            )
        assert resp.status_code == 204
        assert "[unknown]" in mock_logger.error.call_args.args[0]

    def test_no_stack_logs_header_only(self, anon_client: APIClient) -> None:
        """Without a stack, only the header line is logged (single-arg call)."""
        with patch("gaf_core.views.frontend_error_logger") as mock_logger:
            resp = anon_client.post(
                self.url,
                {
                    "message": "no stack error",
                    "trigger": "window.onerror",
                },
                format="json",
            )
        assert resp.status_code == 204
        call_args = mock_logger.error.call_args.args
        assert len(call_args) == 1
        assert "no stack error" in call_args[0]
        # Header line should NOT have a trailing newline (no stack appended).
        assert not call_args[0].endswith("\n")

    def test_long_fields_truncated(self, anon_client: APIClient) -> None:
        """Long fields are truncated to prevent log-injection / disk exhaustion."""
        with patch("gaf_core.views.frontend_error_logger") as mock_logger:
            resp = anon_client.post(
                self.url,
                {
                    "message": "x" * 10_000,  # exceeds _MAX_FE_MESSAGE_LEN (2000)
                    "trigger": "window.onerror",
                    "stack": "y" * 10_000,  # exceeds _MAX_FE_STACK_LEN (4000)
                    "source": "s" * 10_000,
                    "page_url": "u" * 10_000,
                },
                format="json",
            )
        assert resp.status_code == 204
        logged_msg = mock_logger.error.call_args.args[0]
        # Message is header + "\n" + stack. Verify both parts are truncated:
        # - total length < 10_000 (truncation took effect)
        # - stack portion (after newline) <= _MAX_FE_STACK_LEN (4000)
        assert len(logged_msg) < 10_000
        if "\n" in logged_msg:
            stack_part = logged_msg.split("\n", 1)[1]
            assert len(stack_part) <= 4000

    def test_lineno_colno_formatting(self, anon_client: APIClient) -> None:
        """lineno:colno is formatted correctly in the header."""
        with patch("gaf_core.views.frontend_error_logger") as mock_logger:
            resp = anon_client.post(
                self.url,
                {
                    "message": "err",
                    "trigger": "window.onerror",
                    "source": "http://x/main.js",
                    "lineno": 100,
                    "colno": 25,
                },
                format="json",
            )
        assert resp.status_code == 204
        header = mock_logger.error.call_args.args[0]
        assert "100:25" in header

    def test_response_has_no_body(self, anon_client: APIClient) -> None:
        """204 response has no body — frontend doesn't act on response."""
        with patch("gaf_core.views.frontend_error_logger"):
            resp = anon_client.post(
                self.url,
                {"message": "x", "trigger": "window.onerror"},
                format="json",
            )
        assert resp.status_code == 204
        # DRF Response.content is b"" for 204
        assert resp.content in (b"", None)


class TestFrontendErrorReportC3Persistence:
    """C3 (spec 2026-07-30): endpoint persists reports as JSONL under
    ``debug/<YYYYMMDD>/frontend/<page_slug>/<HH>/console.jsonl``.

    Each line carries trace_id / page_slug / level / trigger / message /
    stack / page_url / session_id so AI debugging can correlate frontend
    failures with agent/backend logs via grep trace_id.
    """

    url = "/api/v2/logs/frontend-errors/"

    def test_c3_persists_report_to_page_slug_hour_bucket(self, anon_client: APIClient) -> None:
        """POST with trace_id + page_slug lands a JSONL line under
        debug/<YYYYMMDD>/frontend/<page_slug>/<HH>/console.jsonl."""
        with tempfile.TemporaryDirectory() as tmp_debug_root:
            with patch("gaf_core.views.frontend_error_logger"), patch(
                "gaf_core.views.get_debug_root",
                return_value=tmp_debug_root,
            ):
                resp = anon_client.post(
                    self.url,
                    {
                        "message": "TypeError: x is undefined",
                        "trigger": "error_boundary",
                        "error_type": "TypeError",
                        "stack": "TypeError: x is undefined\n    at Foo (a.js:1:2)",
                        "page_url": "http://localhost:5173/dashboard",
                        "user_agent": "Mozilla/5.0",
                        "session_id": "fsess-test-c3",
                        "trace_id": "11111111-2222-4333-8444-555555555555",
                        "page_slug": "dashboard",
                    },
                    format="json",
                )
            assert resp.status_code == 204

            now = datetime.now()
            date_part = now.strftime("%Y%m%d")
            hour_part = now.strftime("%H")
            expected_path = os.path.join(
                tmp_debug_root, date_part, "frontend", "dashboard", hour_part, "console.jsonl",
            )
            assert os.path.isfile(expected_path), f"Expected JSONL at {expected_path}"

            with open(expected_path, encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            assert len(lines) == 1
            rec = lines[0]
            # Required identity fields
            assert rec["trace_id"] == "11111111-2222-4333-8444-555555555555"
            assert rec["page_slug"] == "dashboard"
            assert rec["level"] == "error"
            assert rec["trigger"] == "error_boundary"
            assert rec["event"] == "frontend.error"
            assert rec["message"] == "TypeError: x is undefined"
            assert "TypeError: x is undefined" in rec["stack"]
            assert rec["page_url"] == "http://localhost:5173/dashboard"
            assert rec["session_id"] == "fsess-test-c3"
            # timestamp is ISO-format sortable
            assert "T" in rec["timestamp"]

    def test_c3_missing_trace_id_writes_empty_string(self, anon_client: APIClient) -> None:
        """Missing trace_id still persists the report with trace_id="".
        AI debugging treats empty trace_id as "no pipeline correlation" —
        the report is still useful for page-level UX debugging."""
        with tempfile.TemporaryDirectory() as tmp_debug_root:
            with patch("gaf_core.views.frontend_error_logger"), patch(
                "gaf_core.views.get_debug_root",
                return_value=tmp_debug_root,
            ):
                resp = anon_client.post(
                    self.url,
                    {
                        "message": "no trace error",
                        "trigger": "window.onerror",
                        "page_slug": "tasks_pipeline",
                    },
                    format="json",
                )
            assert resp.status_code == 204

            now = datetime.now()
            expected_path = os.path.join(
                tmp_debug_root,
                now.strftime("%Y%m%d"),
                "frontend",
                "tasks_pipeline",
                now.strftime("%H"),
                "console.jsonl",
            )
            assert os.path.isfile(expected_path)
            with open(expected_path, encoding="utf-8") as f:
                rec = json.loads(f.read().strip())
            assert rec["trace_id"] == ""
            assert rec["page_slug"] == "tasks_pipeline"

    def test_c3_missing_page_slug_uses_unknown_bucket(self, anon_client: APIClient) -> None:
        """Missing page_slug falls back to 'unknown' bucket — never write
        to a path with empty segment (would create debug/<date>/frontend//HH/)."""
        with tempfile.TemporaryDirectory() as tmp_debug_root:
            with patch("gaf_core.views.frontend_error_logger"), patch(
                "gaf_core.views.get_debug_root",
                return_value=tmp_debug_root,
            ):
                resp = anon_client.post(
                    self.url,
                    {
                        "message": "no slug error",
                        "trigger": "window.onerror",
                        "trace_id": "trace-c3-no-slug",
                    },
                    format="json",
                )
            assert resp.status_code == 204

            now = datetime.now()
            expected_path = os.path.join(
                tmp_debug_root,
                now.strftime("%Y%m%d"),
                "frontend",
                "unknown",
                now.strftime("%H"),
                "console.jsonl",
            )
            assert os.path.isfile(expected_path)
            with open(expected_path, encoding="utf-8") as f:
                rec = json.loads(f.read().strip())
            assert rec["page_slug"] == "unknown"
            assert rec["trace_id"] == "trace-c3-no-slug"

    def test_c3_page_slug_sanitized_for_directory_safety(self, anon_client: APIClient) -> None:
        """page_slug with path separators / unsafe chars is sanitized
        before being used as a directory name (defense in depth — frontend
        also sanitizes, but backend cannot trust the client)."""
        with tempfile.TemporaryDirectory() as tmp_debug_root:
            with patch("gaf_core.views.frontend_error_logger"), patch(
                "gaf_core.views.get_debug_root",
                return_value=tmp_debug_root,
            ):
                resp = anon_client.post(
                    self.url,
                    {
                        "message": "evil slug",
                        "trigger": "window.onerror",
                        "page_slug": "../etc/passwd",
                    },
                    format="json",
                )
            assert resp.status_code == 204

            # Sanitized to a single safe directory segment — no path escape.
            now = datetime.now()
            frontend_dir = os.path.join(tmp_debug_root, now.strftime("%Y%m%d"), "frontend")
            subdirs = [
                d for d in os.listdir(frontend_dir)
                if os.path.isdir(os.path.join(frontend_dir, d))
            ]
            assert len(subdirs) == 1
            assert subdirs[0] not in ("..", ".", "")
            assert "/" not in subdirs[0]
            assert "\\" not in subdirs[0]

    def test_c3_multiple_reports_same_page_same_hour_append_to_same_file(
        self, anon_client: APIClient
    ) -> None:
        """Two reports for the same page_slug within the same hour append
        to the same console.jsonl — hour-bucketing mirrors agent/backend."""
        with tempfile.TemporaryDirectory() as tmp_debug_root:
            with patch("gaf_core.views.frontend_error_logger"), patch(
                "gaf_core.views.get_debug_root",
                return_value=tmp_debug_root,
            ):
                for i in range(2):
                    anon_client.post(
                        self.url,
                        {
                            "message": f"err {i}",
                            "trigger": "window.onerror",
                            "page_slug": "dashboard",
                            "trace_id": f"trace-{i}",
                        },
                        format="json",
                    )

            now = datetime.now()
            expected_path = os.path.join(
                tmp_debug_root,
                now.strftime("%Y%m%d"),
                "frontend",
                "dashboard",
                now.strftime("%H"),
                "console.jsonl",
            )
            with open(expected_path, encoding="utf-8") as f:
                lines = [json.loads(line) for line in f if line.strip()]
            assert len(lines) == 2
            assert lines[0]["message"] == "err 0"
            assert lines[1]["message"] == "err 1"
            assert lines[0]["trace_id"] == "trace-0"
            assert lines[1]["trace_id"] == "trace-1"

    def test_c3_persistence_failure_does_not_block_endpoint(self, anon_client: APIClient) -> None:
        """If FrontendConsoleLogger raises (disk full / permission denied),
        the endpoint still returns 204 — persistence is best-effort.
        Mirrors BackendTaskLogger's swallow-all-exceptions contract."""
        with (
            patch("gaf_core.views.frontend_error_logger"),
            patch("gaf_core.views.get_debug_root", side_effect=OSError("disk full")),
        ):
            resp = anon_client.post(
                self.url,
                {
                    "message": "disk full test",
                    "trigger": "window.onerror",
                    "page_slug": "dashboard",
                    "trace_id": "trace-disk-full",
                },
                format="json",
            )
        # Endpoint still returns 204 — frontend doesn't act on response,
        # and a persistence failure must not turn into a 500 (which would
        # mask the original frontend crash).
        assert resp.status_code == 204


class TestCrashReportPersistence:
    """spec 2026-08-29-logging-system-consolidation P1-2: 前端错误同时落
    CrashReport 表 (日志中心"崩溃报告" tab 数据源), 保留 resolved 工作流。"""

    url = "/api/v2/logs/frontend-errors/"

    def test_populates_crash_report(self, anon_client: APIClient) -> None:
        from debug.models import CrashReport

        with patch("gaf_core.views.frontend_error_logger"):
            resp = anon_client.post(
                self.url,
                {
                    "message": "TypeError: x is undefined",
                    "trigger": "error_boundary",
                    "error_type": "TypeError",
                    "stack": "TypeError: x is undefined\n    at Foo (a.js:1:2)",
                    "page_url": "http://localhost:5173/dashboard",
                    "trace_id": "11111111-2222-4333-8444-555555555555",
                    "page_slug": "dashboard",
                    "session_id": "fsess-crash-1",
                },
                format="json",
            )
        assert resp.status_code == 204

        crash = CrashReport.objects.filter(component="dashboard").latest("created_at")
        assert crash.error_type == "TypeError"
        assert crash.stack_trace.startswith("TypeError")
        assert crash.system_info["message"] == "TypeError: x is undefined"
        assert crash.system_info["trace_id"] == "11111111-2222-4333-8444-555555555555"
        assert crash.system_info["session_id"] == "fsess-crash-1"
        assert crash.system_info["trigger"] == "error_boundary"
        assert crash.resolved is False
