"""StepRecorder unit tests.

Covers StepRecord dataclass behaviour (duration / to_dict) and
StepRecorder main paths: start_step, record_recognition,
record_screenshot, complete_step, fail_step, skip_step, _report_step
(mocked requests.post), get_summary, and edge cases (no current step,
empty summary, report failure swallowed).
"""

from unittest.mock import patch

import pytest
from core.step_recorder import StepRecord, StepRecorder

pytestmark = pytest.mark.unit


@pytest.fixture
def recorder():
    """Fresh StepRecorder with a stub execution id."""
    return StepRecorder(execution_id="exec-123")


# ---------------------------------------------------------------------------
# StepRecord dataclass
# ---------------------------------------------------------------------------


class TestStepRecordDataclass:
    """Verify StepRecord derived fields and serialization."""

    def test_duration_returns_milliseconds_when_complete(self):
        rec = StepRecord(
            step_index=0,
            started_at=100.0,
            completed_at=100.5,
        )
        # 0.5s -> 500ms
        assert rec.duration == pytest.approx(500.0, abs=0.001)

    def test_duration_zero_when_not_timed(self):
        rec = StepRecord(step_index=0)
        # No started_at / completed_at -> 0.0
        assert rec.duration == 0.0

    def test_duration_zero_when_only_started(self):
        rec = StepRecord(step_index=0, started_at=100.0)
        assert rec.duration == 0.0

    def test_to_dict_contains_all_fields(self):
        rec = StepRecord(
            step_index=1,
            node_id="n1",
            node_type="click",
            node_name="ClickBtn",
            status="completed",
            screenshot_path="/tmp/s.png",
            recognition_result={"x": 1},
            error_message="",
            started_at=10.0,
            completed_at=10.2,
        )
        d = rec.to_dict()
        assert d["step_index"] == 1
        assert d["node_id"] == "n1"
        assert d["node_type"] == "click"
        assert d["node_name"] == "ClickBtn"
        assert d["status"] == "completed"
        assert d["screenshot_path"] == "/tmp/s.png"
        assert d["recognition_result"] == {"x": 1}
        assert d["error_message"] == ""
        assert d["started_at"] == 10.0
        assert d["completed_at"] == 10.2
        # duration is derived but included in dict
        assert "duration" in d


# ---------------------------------------------------------------------------
# StepRecorder initialization
# ---------------------------------------------------------------------------


class TestStepRecorderInit:
    """Verify initial state."""

    def test_default_api_base_url(self):
        rec = StepRecorder(execution_id="e1")
        assert rec.execution_id == "e1"
        assert rec.api_base_url == "http://127.0.0.1:8000/api/v2"
        assert rec.steps == []
        assert rec.current_step is None

    def test_custom_api_base_url(self):
        rec = StepRecorder(execution_id="e1", server_url="ws://other:9000/ws/protocol/agents/")
        assert rec.api_base_url == "http://other:9000/api/v2"


# ---------------------------------------------------------------------------
# Step lifecycle
# ---------------------------------------------------------------------------


class TestStepRecorderLifecycle:
    """Verify start/record/complete/fail/skip flows."""

    def test_start_step_sets_current_step_running(self, recorder):
        recorder.start_step(0, "n1", "click", "Btn")
        assert recorder.current_step is not None
        assert recorder.current_step.step_index == 0
        assert recorder.current_step.node_id == "n1"
        assert recorder.current_step.node_type == "click"
        assert recorder.current_step.node_name == "Btn"
        assert recorder.current_step.status == "running"
        assert recorder.current_step.started_at is not None

    @patch("requests.post")
    def test_complete_step_success_appends_and_reports(self, mock_post, recorder):
        recorder.start_step(0, "n1", "click", "Btn")
        result = recorder.complete_step(success=True)

        assert result is not None
        assert result.status == "completed"
        assert result.completed_at is not None
        assert recorder.steps == [result]
        assert recorder.current_step is None
        # report called with execution-scoped URL
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        assert "exec-123" in url
        assert url.endswith("/steps/")

    @patch("requests.post")
    def test_complete_step_failure_marks_failed(self, mock_post, recorder):
        recorder.start_step(1, "n2", "swipe", "Panel")
        result = recorder.complete_step(success=False)

        assert result.status == "failed"
        assert recorder.steps == [result]

    @patch("requests.post")
    def test_complete_step_without_current_returns_none(self, mock_post, recorder):
        # Edge case: calling complete_step with no active step
        result = recorder.complete_step()
        assert result is None
        mock_post.assert_not_called()

    @patch("requests.post")
    def test_fail_step_sets_error_message(self, mock_post, recorder):
        recorder.start_step(0, "n1", "click", "Btn")
        result = recorder.fail_step("boom")

        assert result.status == "failed"
        assert result.error_message == "boom"
        assert result.completed_at is not None
        assert recorder.steps == [result]
        assert recorder.current_step is None

    @patch("requests.post")
    def test_fail_step_without_current_returns_none(self, mock_post, recorder):
        result = recorder.fail_step("err")
        assert result is None
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# Record helpers (recognition / screenshot)
# ---------------------------------------------------------------------------


class TestStepRecorderRecordHelpers:
    """Verify record_recognition / record_screenshot mutate current_step."""

    def test_record_recognition_writes_to_current_step(self, recorder):
        recorder.start_step(0, "n1", "click", "Btn")
        recorder.record_recognition({"match": "ok"})
        assert recorder.current_step.recognition_result == {"match": "ok"}

    def test_record_recognition_no_current_step_is_noop(self, recorder):
        # Edge case: no active step -> silent no-op
        recorder.record_recognition({"x": 1})
        assert recorder.current_step is None

    def test_record_screenshot_writes_to_current_step(self, recorder):
        recorder.start_step(0, "n1", "click", "Btn")
        recorder.record_screenshot("/tmp/shot.png")
        assert recorder.current_step.screenshot_path == "/tmp/shot.png"

    def test_record_screenshot_no_current_step_is_noop(self, recorder):
        recorder.record_screenshot("/tmp/shot.png")
        assert recorder.current_step is None


# ---------------------------------------------------------------------------
# skip_step
# ---------------------------------------------------------------------------


class TestStepRecorderSkip:
    """Verify skip_step creates a skipped record directly."""

    @patch("requests.post")
    def test_skip_step_creates_skipped_record(self, mock_post, recorder):
        result = recorder.skip_step(5)
        assert result.step_index == 5
        assert result.status == "skipped"
        assert result.completed_at is not None
        assert recorder.steps == [result]
        mock_post.assert_called_once()


# ---------------------------------------------------------------------------
# _report_step error swallowing
# ---------------------------------------------------------------------------


class TestStepRecorderReportFailure:
    """Verify _report_step swallows exceptions (must not break execution)."""

    @patch("requests.post", side_effect=RuntimeError("net down"))
    def test_report_failure_does_not_propagate(self, mock_post, recorder):
        # complete_step should not raise even if requests.post raises
        recorder.start_step(0, "n1", "click", "Btn")
        result = recorder.complete_step()
        assert result is not None
        assert recorder.steps == [result]


# ---------------------------------------------------------------------------
# get_summary
# ---------------------------------------------------------------------------


class TestStepRecorderSummary:
    """Verify get_summary aggregation logic."""

    def test_summary_empty_when_no_steps(self, recorder):
        summary = recorder.get_summary()
        assert summary == {
            "total_steps": 0,
            "completed": 0,
            "failed": 0,
            "total_duration_ms": 0,
        }

    @patch("requests.post")
    def test_summary_counts_mixed_statuses(self, mock_post, recorder):
        # One completed, one failed, one skipped
        recorder.start_step(0, "n1", "click", "A")
        recorder.complete_step(success=True)
        recorder.start_step(1, "n2", "click", "B")
        recorder.fail_step("err")
        recorder.skip_step(2)

        summary = recorder.get_summary()
        assert summary["total_steps"] == 3
        assert summary["completed"] == 1
        assert summary["failed"] == 1
        # skipped is not counted in completed/failed
        assert summary["total_duration_ms"] >= 0
