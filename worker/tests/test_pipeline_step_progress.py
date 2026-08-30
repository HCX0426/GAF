"""Tests for P-010: per-step progress callback wiring.

Verifies that ``TaskOrchestrator.execute_pipeline`` accepts an
``on_step_progress`` callback and forwards each node's completion (success
or failure) to it. Also verifies that ``MessageHandler.handle_task_assign``
sends ``task.progress`` frames with step-level fields (``step_index``,
``step_name``, ``status``, ``error_msg``, ``elapsed_time``) so the backend
can persist ``ExecutionStep(status=FAILED)`` and trigger
``recovery_engine.handle_step_failure``.

Scope: agent-side callback wiring only. Backend ``ExecutionStep`` write +
signal hook are covered by Phase 2/3 tests.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src on path (conftest already does this, but be explicit for direct runs)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from core.orchestrator import TaskOrchestrator
from core.result import AutoResult, fail_result, success_result
from engine.context import PipelineState
from engine.pipeline_engine import PipelineResult

pytestmark = pytest.mark.integration


def _make_pipeline_result(
    success: bool,
    elapsed_time: float = 0.1,
    error_msg: str = "",
    data: object = None,
) -> PipelineResult:
    """Helper: build a PipelineResult with the correct PipelineState."""
    state = PipelineState.COMPLETED if success else PipelineState.FAILED
    return PipelineResult(
        success=success,
        state=state,
        data=data,
        error_msg=error_msg,
        elapsed_time=elapsed_time,
        step_results=[],
        structured_log_path="",
    )


class TestExecutePipelineStepProgressCallback:
    """Verify execute_pipeline forwards per-step status via on_step_progress."""

    def test_on_step_complete_invokes_callback_with_success(self):
        """Successful node → on_step_progress(node_id, success_result, idx)."""
        orchestrator = TaskOrchestrator(MagicMock(), MagicMock())
        # Stub device so execute_pipeline doesn't fail on device lookup.
        orchestrator._device_manager.get_active_device.return_value = MagicMock(device_id="dev-1")

        captured: list[tuple[str, AutoResult, int]] = []

        def on_step_progress(node_id: str, result: AutoResult, step_index: int) -> None:
            captured.append((node_id, result, step_index))

        # Patch PipelineEngine to avoid real graph parsing; emit one success.
        fake_engine = MagicMock()
        fake_engine.execute.return_value = _make_pipeline_result(True, elapsed_time=0.5, data={"steps": 1})
        fake_engine._cancel_event = MagicMock()
        fake_engine._pause_event = MagicMock()
        fake_engine.structured_log_path = ""

        def fake_set_callbacks(on_step_complete=None, on_error=None):
            fake_engine._cb_step = on_step_complete
            fake_engine._cb_error = on_error

        fake_engine.set_callbacks.side_effect = fake_set_callbacks

        with patch("engine.pipeline_engine.PipelineEngine", return_value=fake_engine):
            result = orchestrator.execute_pipeline(
                {"nodes": [{"id": "n1"}], "edges": []},
                on_step_progress=on_step_progress,
            )

        assert result.success
        # Simulate the engine firing on_step_complete for the one node.
        assert fake_engine._cb_step is not None
        fake_engine._cb_step("n1", success_result(data={"ok": True}, elapsed_time=0.1))

        assert len(captured) == 1
        node_id, step_result, step_index = captured[0]
        assert node_id == "n1"
        assert step_result.success is True
        assert step_index == 0  # first step

    def test_on_error_invokes_callback_with_failure(self):
        """Failed node → on_step_progress(node_id, fail_result, idx)."""
        orchestrator = TaskOrchestrator(MagicMock(), MagicMock())
        orchestrator._device_manager.get_active_device.return_value = MagicMock(device_id="dev-1")

        captured: list[tuple[str, AutoResult, int]] = []

        def on_step_progress(node_id: str, result: AutoResult, step_index: int) -> None:
            captured.append((node_id, result, step_index))

        fake_engine = MagicMock()
        fake_engine.execute.return_value = _make_pipeline_result(False, elapsed_time=0.1, error_msg="boom")
        fake_engine._cancel_event = MagicMock()
        fake_engine._pause_event = MagicMock()
        fake_engine.structured_log_path = ""

        def fake_set_callbacks(on_step_complete=None, on_error=None):
            fake_engine._cb_step = on_step_complete
            fake_engine._cb_error = on_error

        fake_engine.set_callbacks.side_effect = fake_set_callbacks

        with patch("engine.pipeline_engine.PipelineEngine", return_value=fake_engine):
            orchestrator.execute_pipeline(
                {"nodes": [{"id": "n1"}], "edges": []},
                on_step_progress=on_step_progress,
            )

        # Simulate the engine firing on_error for the one node.
        assert fake_engine._cb_error is not None
        fake_engine._cb_error("n1", RuntimeError("kaboom"))

        assert len(captured) == 1
        node_id, step_result, step_index = captured[0]
        assert node_id == "n1"
        assert step_result.success is False
        assert "kaboom" in step_result.error_msg
        assert step_index == 0

    def test_step_index_increments_across_nodes(self):
        """Multiple nodes → step_index goes 0, 1, 2, ..."""
        orchestrator = TaskOrchestrator(MagicMock(), MagicMock())
        orchestrator._device_manager.get_active_device.return_value = MagicMock(device_id="dev-1")

        captured: list[int] = []

        def on_step_progress(node_id: str, result: AutoResult, step_index: int) -> None:
            captured.append(step_index)

        fake_engine = MagicMock()
        fake_engine.execute.return_value = _make_pipeline_result(True, elapsed_time=0.1)
        fake_engine._cancel_event = MagicMock()
        fake_engine._pause_event = MagicMock()
        fake_engine.structured_log_path = ""

        def fake_set_callbacks(on_step_complete=None, on_error=None):
            fake_engine._cb_step = on_step_complete
            fake_engine._cb_error = on_error

        fake_engine.set_callbacks.side_effect = fake_set_callbacks

        with patch("engine.pipeline_engine.PipelineEngine", return_value=fake_engine):
            orchestrator.execute_pipeline(
                {"nodes": [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}], "edges": []},
                on_step_progress=on_step_progress,
            )

        # Simulate three sequential node completions.
        for _i, nid in enumerate(["n1", "n2", "n3"]):
            fake_engine._cb_step(nid, success_result(elapsed_time=0.05))

        assert captured == [0, 1, 2]

    def test_callback_exception_does_not_crash_pipeline(self):
        """If on_step_progress raises, pipeline must continue (logged warning)."""
        orchestrator = TaskOrchestrator(MagicMock(), MagicMock())
        orchestrator._device_manager.get_active_device.return_value = MagicMock(device_id="dev-1")

        call_count = [0]

        def bad_callback(node_id: str, result: AutoResult, step_index: int) -> None:
            call_count[0] += 1
            raise RuntimeError("callback exploded")

        fake_engine = MagicMock()
        fake_engine.execute.return_value = _make_pipeline_result(True, elapsed_time=0.1)
        fake_engine._cancel_event = MagicMock()
        fake_engine._pause_event = MagicMock()
        fake_engine.structured_log_path = ""

        def fake_set_callbacks(on_step_complete=None, on_error=None):
            fake_engine._cb_step = on_step_complete
            fake_engine._cb_error = on_error

        fake_engine.set_callbacks.side_effect = fake_set_callbacks

        with patch("engine.pipeline_engine.PipelineEngine", return_value=fake_engine):
            result = orchestrator.execute_pipeline(
                {"nodes": [{"id": "n1"}], "edges": []},
                on_step_progress=bad_callback,
            )

        # Engine callback should still be wired even though our callback raises.
        assert fake_engine._cb_step is not None
        # Firing the callback must NOT raise (orchestrator catches).
        fake_engine._cb_step("n1", success_result(elapsed_time=0.01))
        assert call_count[0] == 1
        assert result.success  # pipeline result unaffected

    def test_no_callback_does_not_break(self):
        """When on_step_progress=None, default empty behavior must still work."""
        orchestrator = TaskOrchestrator(MagicMock(), MagicMock())
        orchestrator._device_manager.get_active_device.return_value = MagicMock(device_id="dev-1")

        fake_engine = MagicMock()
        fake_engine.execute.return_value = _make_pipeline_result(True, elapsed_time=0.1)
        fake_engine._cancel_event = MagicMock()
        fake_engine._pause_event = MagicMock()
        fake_engine.structured_log_path = ""

        with patch("engine.pipeline_engine.PipelineEngine", return_value=fake_engine):
            result = orchestrator.execute_pipeline(
                {"nodes": [{"id": "n1"}], "edges": []},
                # on_step_progress omitted (None)
            )

        assert result.success
        # Callbacks still set (engine uses them internally); just no external forwarder.
        assert fake_engine.set_callbacks.called


class TestHandlerStepProgressFrame:
    """Verify handler.handle_task_assign sends task.progress frames
    with step-level fields when on_step_progress fires."""

    def test_handler_sends_step_progress_frame_on_success(self):
        """handler should send task.progress with status=success for a node."""
        from client.handler import MessageHandler

        handler = MessageHandler(MagicMock())
        # Stub _resolve_target_device so handler doesn't fail on device lookup
        with patch.object(handler, "_resolve_target_device", return_value=MagicMock()), \
             patch.object(handler, "_send_to_server") as mock_send, \
             patch.object(handler, "_orchestrator") as mock_orch:
            # Make execute_pipeline synchronously invoke on_step_progress so
            # we can capture the frame the handler builds.
            def fake_execute(graph, **kwargs):
                cb = kwargs.get("on_step_progress")
                if cb:
                    cb("node-1", success_result(elapsed_time=0.42), 0)
                return success_result(elapsed_time=0.5)

            mock_orch.execute_pipeline.side_effect = fake_execute

            handler.handle_task_assign({
                "execution_id": "exec-1",
                "task_id": 1,
                "task_name": "test",
                "task_definition": {"nodes": [{"id": "node-1"}]},
                "execution_mode": "pipeline",
                "device_info": {"device_type": "windows"},
            })

            # Give the daemon thread a moment to run.
            time.sleep(0.1)

        # _send_to_server should have been called with task.progress frames.
        # Filter to step-level progress frames (those with step_index key).
        step_frames = [
            call for call in mock_send.call_args_list
            if call.args and call.args[0] == "task.progress"
            and isinstance(call.args[1], dict)
            and "step_index" in call.args[1]
        ]
        assert len(step_frames) == 1, f"expected 1 step frame, got {len(step_frames)}"
        _, payload = step_frames[0].args
        assert payload["execution_id"] == "exec-1"
        assert payload["task_id"] == 1
        assert payload["step_index"] == 0
        assert payload["step_name"] == "node-1"
        assert payload["status"] == "success"
        assert payload["error_msg"] == ""
        assert payload["elapsed_time"] == 0.42

    def test_handler_sends_step_progress_frame_on_failure(self):
        """handler should send task.progress with status=failed for a failed node."""
        from client.handler import MessageHandler

        handler = MessageHandler(MagicMock())
        with patch.object(handler, "_resolve_target_device", return_value=MagicMock()), \
             patch.object(handler, "_send_to_server") as mock_send, \
             patch.object(handler, "_orchestrator") as mock_orch:
            def fake_execute(graph, **kwargs):
                cb = kwargs.get("on_step_progress")
                if cb:
                    cb("node-fail", fail_result(error_msg="template not found", elapsed_time=0.3), 2)
                return fail_result(error_msg="pipeline failed", elapsed_time=0.4)

            mock_orch.execute_pipeline.side_effect = fake_execute

            handler.handle_task_assign({
                "execution_id": "exec-2",
                "task_id": 2,
                "task_name": "test-fail",
                "task_definition": {"nodes": [{"id": "node-fail"}]},
                "execution_mode": "pipeline",
                "device_info": {"device_type": "windows"},
            })

            time.sleep(0.1)

        step_frames = [
            call for call in mock_send.call_args_list
            if call.args and call.args[0] == "task.progress"
            and isinstance(call.args[1], dict)
            and "step_index" in call.args[1]
        ]
        assert len(step_frames) == 1
        _, payload = step_frames[0].args
        assert payload["execution_id"] == "exec-2"
        assert payload["step_index"] == 2
        assert payload["step_name"] == "node-fail"
        assert payload["status"] == "failed"
        assert payload["error_msg"] == "template not found"
        assert payload["elapsed_time"] == 0.3
