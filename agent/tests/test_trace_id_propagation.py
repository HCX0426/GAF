"""Tests for A3 (spec 2026-07-30-debug-directory-restructure): trace_id 全链路贯穿.

覆盖断点③④修复:
- 断点③: agent handler 从 WS 帧顶层读 ``frame["trace_id"]`` (而非 payload 的
  ``user_trace_id`` 字段), 并 set 到 ``current_user_trace_id`` ContextVar.
- 断点④: ``PipelineContext.emit_coord_trace`` 的 trace_id 参数从 ContextVar 取
  (而非 ``logger.execution_id`` 兜底).

依赖前置:
- A1 已完成: ``get_logger`` 支持 ``pipeline_name`` + ``trace_id`` 参数, 小时桶路径.
- A2 已完成: ``DebugImageSaver`` 文件名时间前缀.

本测试覆盖 A3 改动点:
1. ``_dispatch_to_handler`` 把帧顶层 ``trace_id`` 传给 handler (keyword arg).
2. ``handle_task_assign`` 用传入的 trace_id set
   ContextVar (不再从 ``data["user_trace_id"]`` 读).
3. ``PipelineContext.emit_coord_trace`` 从 ``current_user_trace_id`` ContextVar
   取 trace_id (不再用 ``logger.execution_id`` 兜底).
4. ``_init_orchestrator_logger`` 把 ``pipeline_name`` + ``trace_id`` 传给
   ``get_structured_logger``.
5. ``PipelineEngine.execute()`` 把 ``pipeline_name`` + ``trace_id`` 传给
   ``get_structured_logger``.
"""

import contextlib
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src on path (conftest also does this, but be explicit for direct runs)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest  # noqa: E402 - after sys.path setup above

pytestmark = pytest.mark.unit  # noqa: E402

from client.connection import AgentConnection  # noqa: E402
from client.handler import MessageHandler  # noqa: E402
from core.context_vars import (  # noqa: E402
    clear_current_execution,
    get_current_user_trace_id,
    set_current_execution,
)

# Shared fixtures -----------------------------------------------------------

_TRACE_ID = "550e8400-e29b-41d4-a716-446655440000"


class _FullStubHandler:
    """Stub handler that defines ALL methods accessed by ``handler_map``.

    ``_dispatch_to_handler`` builds the full ``handler_map`` eagerly at entry,
    accessing every ``handler.handle_*`` attribute. A stub that only defines
    one method would raise ``AttributeError`` during map construction. This
    base stub provides no-op defaults so tests can override only the method
    under test.
    """

    def handle_status_update(self, data, trace_id=""):
        pass

    def handle_task_assign(self, data, trace_id=""):
        pass

    def handle_task_cancel(self, data, trace_id=""):
        pass

    def handle_task_force_terminate(self, data, trace_id=""):
        pass

    def handle_monitor_rule_update(self, data, trace_id=""):
        pass

    def handle_screenshot_control(self, data, trace_id=""):
        pass

    def handle_device_command(self, data, trace_id=""):
        pass

    def handle_llm_result(self, data, trace_id=""):
        pass


def _make_task_assign_payload(**overrides) -> dict:
    """Build a minimal task.assign payload (NOT including trace_id at frame top)."""
    base = {
        "execution_id": "exec-A3-1",
        "task_id": 42,
        "task_name": "trace-id-test",
        "task_definition": {"nodes": []},
        "execution_mode": "pipeline",
        "device_info": {"id": 1, "name": "d", "device_type": "windows"},
    }
    base.update(overrides)
    return base


def _make_task_assign_frame(trace_id: str = _TRACE_ID, payload: dict | None = None) -> dict:
    """Build a complete WS frame with trace_id at top level (断点②后 serialize_frame 行为)."""
    return {
        "trace_id": trace_id,
        "type": "task.assign",
        "seq": 1,
        "timestamp": "2026-07-30T05:12:33Z",
        "payload": payload or _make_task_assign_payload(),
    }


# ===========================================================================
# 断点③: _dispatch_to_handler 传 trace_id 给 handler
# ===========================================================================


class TestDispatchToHandlerPassesTraceId:
    """验证 ``_dispatch_to_handler`` 把帧顶层 trace_id 传给 handler 方法."""

    def test_handle_task_assign_receives_trace_id_kwarg(self):
        """WS 帧 trace_id 应作为 keyword arg 传给 handle_task_assign."""
        config = MagicMock()
        config.server_url = "ws://localhost:8765"
        config.agent_token = "tok"
        config.heartbeat_interval = 30
        conn = AgentConnection(config)

        captured: dict = {}

        class _StubHandler(_FullStubHandler):
            def handle_task_assign(self, data, trace_id=""):
                captured["data"] = data
                captured["trace_id"] = trace_id

        frame = _make_task_assign_frame(trace_id=_TRACE_ID)
        conn._dispatch_to_handler(frame, _StubHandler())

        assert captured["trace_id"] == _TRACE_ID, (
            f"handler should receive frame top-level trace_id, got {captured.get('trace_id')!r}"
        )
        assert "trace_id" not in captured["data"], (
            "trace_id must NOT be injected into payload (spec G3: frame top-level only)"
        )

    def test_handle_pipeline_execute_receives_trace_id_kwarg(self):
        """WS 帧 trace_id 应作为 keyword arg 传给 handle_task_assign (替代已删除的 handle_pipeline_execute)."""
        config = MagicMock()
        config.server_url = "ws://localhost:8765"
        config.agent_token = "tok"
        config.heartbeat_interval = 30
        conn = AgentConnection(config)

        captured: dict = {}

        class _StubHandler(_FullStubHandler):
            def handle_task_assign(self, data, trace_id=""):
                captured["data"] = data
                captured["trace_id"] = trace_id

        frame = {
            "trace_id": _TRACE_ID,
            "type": "task.dispatch",
            "seq": 2,
            "timestamp": "2026-07-30T05:12:34Z",
            "payload": {"task_id": 7, "task_definition": {"nodes": []}, "execution_id": "exec-7", "execution_mode": "pipeline"},
        }
        conn._dispatch_to_handler(frame, _StubHandler())

        assert captured["trace_id"] == _TRACE_ID

    def test_handlers_without_trace_id_param_still_work(self):
        """Legacy handlers (no trace_id kwarg) must NOT break — fallback to positional only.

        Per spec F22: 方案 A 推荐 handler_method(msg_data, trace_id=...).
        但 _noop_ack 等内部 handler 不需要 trace_id, 必须能兼容.
        """
        config = MagicMock()
        config.server_url = "ws://localhost:8765"
        config.agent_token = "tok"
        config.heartbeat_interval = 30
        conn = AgentConnection(config)

        captured: dict = {}

        class _StubHandler(_FullStubHandler):
            # Override handle_status_update with legacy signature (no trace_id param)
            def handle_status_update(self, data):
                captured["data"] = data

        frame = {
            "trace_id": _TRACE_ID,
            "type": "agent.status",
            "seq": 3,
            "timestamp": "2026-07-30T05:12:35Z",
            "payload": {"status": "ok"},
        }
        # Should not raise TypeError even though handle_status_update lacks trace_id param
        conn._dispatch_to_handler(frame, _StubHandler())
        assert captured["data"] == {"status": "ok"}


# ===========================================================================
# 断点③: handle_task_assign 从 frame trace_id set ContextVar
# ===========================================================================


class TestHandleTaskAssignSetsContextVar:
    """验证 ``handle_task_assign`` 用传入的 trace_id set ``current_user_trace_id``."""

    def test_task_assign_sets_user_trace_id_from_frame(self):
        """handle_task_assign(trace_id=<UUID>) 应 set ContextVar 为该 UUID (非 execution_id)."""
        handler = MessageHandler(MagicMock())
        data = _make_task_assign_payload()
        mock_device = MagicMock()
        mock_device.device_id = "dev-1"

        captured: dict = {}

        def _capture_exec_id(*args, **kwargs):
            # 在 _run 线程内读取 ContextVar, 应为 frame 顶层 trace_id
            captured["trace_id_in_thread"] = get_current_user_trace_id()
            return MagicMock(success=True, data={}, elapsed_time=0.1,
                             structured_log_path="")

        with patch.object(handler, "_orchestrator") as mock_orch, \
             patch.object(handler, "_resolve_target_device", return_value=mock_device), \
             patch.object(handler, "_send_to_server"):
            mock_orch.execute_pipeline.side_effect = _capture_exec_id
            handler.handle_task_assign(data, trace_id=_TRACE_ID)
            # 等待 _run 线程执行
            for _ in range(50):
                if mock_orch.execute_pipeline.called:
                    break
                time.sleep(0.01)

        assert mock_orch.execute_pipeline.called, "execute_pipeline should be called"
        assert captured.get("trace_id_in_thread") == _TRACE_ID, (
            f"ContextVar in _run thread should be frame trace_id, "
            f"got {captured.get('trace_id_in_thread')!r}"
        )

    def test_task_assign_does_not_read_user_trace_id_from_payload(self):
        """handle_task_assign 不应再从 payload 的 ``user_trace_id`` 字段读 trace_id.

        回归测试: 即使 payload 含 user_trace_id (旧 backend 发的), 也应以 frame
        顶层 trace_id 为准. 当 frame trace_id 为空时才回退到 payload.
        """
        handler = MessageHandler(MagicMock())
        # payload 含旧字段 user_trace_id (应被忽略)
        data = _make_task_assign_payload(user_trace_id="stale-legacy-id")
        mock_device = MagicMock()
        mock_device.device_id = "dev-1"

        captured: dict = {}

        def _capture(*args, **kwargs):
            captured["trace_id_in_thread"] = get_current_user_trace_id()
            return MagicMock(success=True, data={}, elapsed_time=0.1,
                             structured_log_path="")

        with patch.object(handler, "_orchestrator") as mock_orch, \
             patch.object(handler, "_resolve_target_device", return_value=mock_device), \
             patch.object(handler, "_send_to_server"):
            mock_orch.execute_pipeline.side_effect = _capture
            # frame trace_id 是权威源
            handler.handle_task_assign(data, trace_id=_TRACE_ID)
            for _ in range(50):
                if mock_orch.execute_pipeline.called:
                    break
                time.sleep(0.01)

        assert captured.get("trace_id_in_thread") == _TRACE_ID, (
            "frame trace_id must take precedence over payload user_trace_id"
        )

    def test_task_assign_empty_trace_id_falls_back_to_payload(self):
        """当 frame 顶层 trace_id 为空 (老服务器未实现断点②), 回退到 payload 字段."""
        handler = MessageHandler(MagicMock())
        data = _make_task_assign_payload(user_trace_id="legacy-payload-id")
        mock_device = MagicMock()
        mock_device.device_id = "dev-1"

        captured: dict = {}

        def _capture(*args, **kwargs):
            captured["trace_id_in_thread"] = get_current_user_trace_id()
            return MagicMock(success=True, data={}, elapsed_time=0.1,
                             structured_log_path="")

        with patch.object(handler, "_orchestrator") as mock_orch, \
             patch.object(handler, "_resolve_target_device", return_value=mock_device), \
             patch.object(handler, "_send_to_server"):
            mock_orch.execute_pipeline.side_effect = _capture
            # frame trace_id 为空 → 回退到 payload.user_trace_id
            handler.handle_task_assign(data, trace_id="")
            for _ in range(50):
                if mock_orch.execute_pipeline.called:
                    break
                time.sleep(0.01)

        assert captured.get("trace_id_in_thread") == "legacy-payload-id", (
            "empty frame trace_id should fall back to payload user_trace_id"
        )


# ===========================================================================
# 断点④: emit_coord_trace 从 ContextVar 取 trace_id
# ===========================================================================


class TestEmitCoordTraceFromContextVar:
    """验证 ``PipelineContext.emit_coord_trace`` 从 ContextVar 取 trace_id."""

    def test_emit_coord_trace_uses_contextvar_trace_id(self):
        """emit_coord_trace 应从 ``current_user_trace_id`` 取 trace_id, 非 logger.execution_id."""
        from engine.context import PipelineContext

        ctx = PipelineContext()
        mock_logger = MagicMock()
        mock_logger.execution_id = "exec-should-not-be-used"
        ctx.structured_logger = mock_logger

        # Set ContextVar to a known UUID
        tokens = set_current_execution(
            execution_id="exec-test",
            task_id="t1",
            user_trace_id=_TRACE_ID,
        )
        try:
            ctx.emit_coord_trace(
                node_id="n1",
                step="test_step",
                raw=(10, 20),
                converted=(100, 200),
                formula="logical_to_physical(x, y)",
                coord_system_in="logical",
                coord_system_out="physical",
            )
        finally:
            clear_current_execution(tokens)

        mock_logger.emit_coord_trace.assert_called_once()
        _, kwargs = mock_logger.emit_coord_trace.call_args
        assert kwargs.get("trace_id") == _TRACE_ID, (
            f"emit_coord_trace should read trace_id from ContextVar, "
            f"got {kwargs.get('trace_id')!r}"
        )

    def test_emit_coord_trace_empty_contextvar_uses_empty_string(self):
        """当 ContextVar 为空 (CLI 模式 / 非任务上下文), trace_id 应为空串 (非 execution_id)."""
        from engine.context import PipelineContext

        ctx = PipelineContext()
        mock_logger = MagicMock()
        mock_logger.execution_id = "exec-should-not-leak"
        ctx.structured_logger = mock_logger

        # Ensure ContextVar is empty (default)
        assert get_current_user_trace_id() == ""

        ctx.emit_coord_trace(
            node_id="n1",
            step="cli_step",
            raw=(0, 0),
            converted=(0, 0),
            formula="identity",
            coord_system_in="physical",
            coord_system_out="physical",
        )

        mock_logger.emit_coord_trace.assert_called_once()
        _, kwargs = mock_logger.emit_coord_trace.call_args
        assert kwargs.get("trace_id") == "", (
            f"empty ContextVar should yield empty trace_id, "
            f"got {kwargs.get('trace_id')!r}"
        )


# ===========================================================================
# A3 改动点 3: _init_orchestrator_logger 传 pipeline_name + trace_id
# ===========================================================================


class TestOrchestratorLoggerPassesTraceId:
    """验证 ``_init_orchestrator_logger`` 把 pipeline_name + trace_id 传给 get_structured_logger."""

    def test_init_orchestrator_logger_passes_pipeline_name_and_trace_id(self, tmp_path, monkeypatch):
        from core.orchestrator import TaskOrchestrator
        from utils.structured_logger import StructuredLogger

        # 模拟配置
        mock_config = MagicMock()
        mock_config.debug_dir = str(tmp_path)

        # 捕获 get_structured_logger 调用参数
        captured: dict = {}

        def _capture_logger(execution_id, debug_dir="./debug", **kwargs):
            captured["execution_id"] = execution_id
            captured["debug_dir"] = debug_dir
            captured["pipeline_name"] = kwargs.get("pipeline_name", "")
            captured["trace_id"] = kwargs.get("trace_id", "")
            # 返回一个 mock logger
            mock = MagicMock(spec=StructuredLogger)
            mock.file_path = str(tmp_path / "fake.jsonl")
            return mock

        # 用真实 TaskOrchestrator 构造, 但 mock 掉 get_structured_logger
        with patch("core.orchestrator.get_structured_logger", side_effect=_capture_logger):
            orch = TaskOrchestrator.__new__(TaskOrchestrator)
            orch._config = mock_config
            orch._orchestrator_logger = None
            orch._orchestrator_exec_id = ""

            # Set ContextVar with a known trace_id
            tokens = set_current_execution(
                execution_id="exec-orch-1",
                task_id="t1",
                user_trace_id=_TRACE_ID,
            )
            try:
                pipeline_json = {
                    "nodes": [],
                    "metadata": {"pipeline_name": "get_email"},
                }
                orch._init_orchestrator_logger(
                    debug_dir=str(tmp_path),
                    pipeline_json=pipeline_json,
                    execution_id_override="exec-orch-1",
                )
            finally:
                clear_current_execution(tokens)

        assert captured.get("pipeline_name") == "get_email", (
            f"pipeline_name should be extracted from metadata, "
            f"got {captured.get('pipeline_name')!r}"
        )
        assert captured.get("trace_id") == _TRACE_ID, (
            f"trace_id should be read from ContextVar, got {captured.get('trace_id')!r}"
        )


# ===========================================================================
# A3 改动点 4: PipelineEngine.execute() 传 pipeline_name + trace_id
# ===========================================================================


class TestEngineExecutePassesTraceId:
    """验证 ``PipelineEngine.execute()`` 把 pipeline_name + trace_id 传给 get_structured_logger."""

    def test_engine_execute_passes_pipeline_name_and_trace_id(self, tmp_path, monkeypatch):
        from engine.context import PipelineContext
        from engine.pipeline_engine import PipelineEngine
        from utils.structured_logger import StructuredLogger

        # 捕获 get_structured_logger 调用参数
        captured: dict = {}

        def _capture_logger(execution_id, debug_dir="./debug", **kwargs):
            captured["execution_id"] = execution_id
            captured["debug_dir"] = debug_dir
            captured["pipeline_name"] = kwargs.get("pipeline_name", "")
            captured["trace_id"] = kwargs.get("trace_id", "")
            mock = MagicMock(spec=StructuredLogger)
            mock.file_path = str(tmp_path / "fake.jsonl")
            mock.log_node_event = MagicMock()
            mock.emit_coord_trace = MagicMock()
            mock.close = MagicMock()
            return mock

        # Build a minimal engine
        mock_device = MagicMock()
        mock_device.device_id = "dev-1"
        mock_device.device_type = "windows"

        context = PipelineContext()
        context.debug_dir = str(tmp_path)
        context.device = mock_device
        context.pipeline_name = "login_flow"

        # Patch get_structured_logger in engine module
        monkeypatch.setattr("engine.pipeline_engine.get_structured_logger", _capture_logger)
        # Mock PipelineValidator.validate to return no errors so execute()
        # proceeds past the validation check to the get_structured_logger call.
        monkeypatch.setattr("engine.pipeline_engine.PipelineValidator.validate", staticmethod(lambda g: []))

        engine = PipelineEngine.__new__(PipelineEngine)
        engine._graph = MagicMock()  # non-None so the "not loaded" check passes
        engine._context = context
        engine._device = mock_device
        engine._device_type = "windows"
        engine._transformer_id = "win-dpi-1.0"
        engine._execution_id_override = ""
        engine._structured_logger = None
        engine._last_structured_log_path = ""
        engine._step_results = []
        engine._previous_node_id = ""
        engine._previous_node_type = ""
        engine._previous_node_end_time = 0.0
        engine._state = None
        engine._cancel_event = MagicMock()
        engine._pause_event = MagicMock()

        # Set ContextVar with a known trace_id
        tokens = set_current_execution(
            execution_id="exec-engine-1",
            task_id="t1",
            user_trace_id=_TRACE_ID,
        )
        try:
            with contextlib.suppress(Exception):
                # execute() will fail fast after get_structured_logger because
                # we didn't set up the full pipeline graph, but the logger call
                # is what we're verifying.
                engine.execute()
        finally:
            clear_current_execution(tokens)

        assert captured.get("pipeline_name") == "login_flow", (
            f"pipeline_name should come from context.pipeline_name, "
            f"got {captured.get('pipeline_name')!r}"
        )
        assert captured.get("trace_id") == _TRACE_ID, (
            f"trace_id should be read from ContextVar, got {captured.get('trace_id')!r}"
        )
