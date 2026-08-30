"""Tests for agent handle_task_assign retry-from-step parameter forwarding.

Task 1.1 (B7 重试单节点, P0-1): verifies that MessageHandler.handle_task_assign
reads ``start_step_index`` and ``previous_results`` from the task-assign
payload and forwards them to ``orchestrator.execute_pipeline`` so the agent
re-executes only the failed step (and subsequent steps) instead of the whole
pipeline.

Background
----------
N192 视角 B 评估发现 B7 复现路径最弱 (4/10): 用户拿到错误后无法自行修复,
必须重新跑整个 pipeline。Task 1.1 在 agent 端的 PipelineEngine.execute() 已
支持 ``start_step_index`` + ``previous_results`` 参数 (跳过前 N 个节点, 保留
前驱节点的 result 让分支决策与最终 step_results 完整). 本测试覆盖
handle_task_assign → orchestrator.execute_pipeline 的参数透传链路, 确保后端
通过 WS payload 传的字段不会被丢弃.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src on path (conftest already does this, but be explicit for direct runs)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from client.handler import MessageHandler

pytestmark = pytest.mark.unit


class TestHandleTaskAssignRetryFromStep:
    """Verify handle_task_assign forwards start_step_index + previous_results."""

    def _make_payload(self, **overrides):
        """Build a minimal task.assign payload with retry-from-step fields."""
        base = {
            "execution_id": "exec-retry-1",
            "task_id": 42,
            "task_name": "retry-test",
            "task_definition": {"nodes": []},
            "execution_mode": "pipeline",
            "device_info": {"id": 1, "name": "d", "device_type": "windows"},
            "start_step_index": 2,
            "previous_results": [
                {
                    "success": True,
                    "data": {"x": 10, "y": 20},
                    "node_id": "step_1",
                    "node_type": "click",
                },
                {
                    "success": True,
                    "data": {"x": 30, "y": 40},
                    "node_id": "step_2",
                    "node_type": "click",
                },
            ],
        }
        base.update(overrides)
        return base

    def test_forwards_start_step_index_to_orchestrator(self):
        """handle_task_assign should pass start_step_index to execute_pipeline.

        覆盖: 当 WS payload 包含 start_step_index=2 时, orchestrator.execute_pipeline
        被调用时也应收到 start_step_index=2.
        """
        handler = MessageHandler(MagicMock())
        data = self._make_payload()
        mock_device = MagicMock()
        mock_device.device_id = "dev-1"

        with patch.object(handler, "_orchestrator") as mock_orch, \
             patch.object(handler, "_resolve_target_device", return_value=mock_device), \
             patch.object(handler, "_send_to_server"):
            # Stub execute_pipeline so the run thread does not actually execute.
            mock_orch.execute_pipeline.return_value = MagicMock(
                success=True, data={}, elapsed_time=0.1,
                structured_log_path="",
            )
            handler.handle_task_assign(data)
            # Wait for the spawned daemon thread to call execute_pipeline.
            # The handler spawns a thread, so we use assert_called_with which
            # is satisfied once the call completes. Tests run synchronously
            # because execute_pipeline is mocked.
            import time as _time
            for _ in range(50):
                if mock_orch.execute_pipeline.called:
                    break
                _time.sleep(0.01)
            assert mock_orch.execute_pipeline.called, \
                "orchestrator.execute_pipeline should be called"
            _, kwargs = mock_orch.execute_pipeline.call_args
            assert kwargs.get("start_step_index") == 2, \
                f"expected start_step_index=2 forwarded, got {kwargs.get('start_step_index')}"

    def test_forwards_previous_results_to_orchestrator(self):
        """handle_task_assign should pass previous_results list to execute_pipeline.

        覆盖: 当 WS payload 包含 previous_results (list[dict]) 时, handler
        应把每个 dict 转成 AutoResult (typed object) 再转发给
        orchestrator.execute_pipeline. 这让 orchestrator/engine 始终
        操作 typed objects, 不必处理 dict ↔ AutoResult 边界.
        """
        from core.result import AutoResult

        handler = MessageHandler(MagicMock())
        data = self._make_payload()
        mock_device = MagicMock()
        mock_device.device_id = "dev-1"

        with patch.object(handler, "_orchestrator") as mock_orch, \
             patch.object(handler, "_resolve_target_device", return_value=mock_device), \
             patch.object(handler, "_send_to_server"):
            mock_orch.execute_pipeline.return_value = MagicMock(
                success=True, data={}, elapsed_time=0.1,
                structured_log_path="",
            )
            handler.handle_task_assign(data)
            import time as _time
            for _ in range(50):
                if mock_orch.execute_pipeline.called:
                    break
                _time.sleep(0.01)
            assert mock_orch.execute_pipeline.called
            _, kwargs = mock_orch.execute_pipeline.call_args
            prev = kwargs.get("previous_results")
            assert prev is not None, "previous_results should be forwarded (not None)"
            assert len(prev) == 2, f"expected 2 previous_results, got {len(prev)}"
            # handler 应把 WS payload 的 list[dict] 转成 list[AutoResult]
            # (typed object), 让 orchestrator/engine 不必处理 dict 边界.
            assert isinstance(prev[0], AutoResult), \
                f"expected AutoResult, got {type(prev[0])}"
            assert prev[0].node_id == "step_1"
            assert prev[1].node_id == "step_2"
            assert prev[0].success is True

    def test_defaults_to_zero_start_step_index_when_missing(self):
        """handle_task_assign should default start_step_index=0 when payload lacks it.

        覆盖: 老服务器不发送 start_step_index 时, agent 应默认 0 (从头跑),
        保持向后兼容.
        """
        handler = MessageHandler(MagicMock())
        data = self._make_payload(start_step_index=None)
        del data["start_step_index"]
        mock_device = MagicMock()
        mock_device.device_id = "dev-1"

        with patch.object(handler, "_orchestrator") as mock_orch, \
             patch.object(handler, "_resolve_target_device", return_value=mock_device), \
             patch.object(handler, "_send_to_server"):
            mock_orch.execute_pipeline.return_value = MagicMock(
                success=True, data={}, elapsed_time=0.1,
                structured_log_path="",
            )
            handler.handle_task_assign(data)
            import time as _time
            for _ in range(50):
                if mock_orch.execute_pipeline.called:
                    break
                _time.sleep(0.01)
            assert mock_orch.execute_pipeline.called
            _, kwargs = mock_orch.execute_pipeline.call_args
            assert kwargs.get("start_step_index") == 0, \
                f"expected default 0, got {kwargs.get('start_step_index')}"

    def test_defaults_to_none_previous_results_when_missing(self):
        """handle_task_assign should default previous_results=None when payload lacks it.

        覆盖: 老服务器不发送 previous_results 时, agent 应默认 None (engine
        内部 None → 不追加任何前驱 result).
        """
        handler = MessageHandler(MagicMock())
        data = self._make_payload()
        del data["previous_results"]
        mock_device = MagicMock()
        mock_device.device_id = "dev-1"

        with patch.object(handler, "_orchestrator") as mock_orch, \
             patch.object(handler, "_resolve_target_device", return_value=mock_device), \
             patch.object(handler, "_send_to_server"):
            mock_orch.execute_pipeline.return_value = MagicMock(
                success=True, data={}, elapsed_time=0.1,
                structured_log_path="",
            )
            handler.handle_task_assign(data)
            import time as _time
            for _ in range(50):
                if mock_orch.execute_pipeline.called:
                    break
                _time.sleep(0.01)
            assert mock_orch.execute_pipeline.called
            _, kwargs = mock_orch.execute_pipeline.call_args
            assert "previous_results" in kwargs, \
                "previous_results key should always be passed (None when absent)"
            assert kwargs["previous_results"] is None, \
                f"expected None default, got {kwargs['previous_results']}"
