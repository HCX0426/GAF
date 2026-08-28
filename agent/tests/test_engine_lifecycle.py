"""P1-8 Node lifecycle fields tests — pre_delay / post_delay /
pre_wait_freezes / post_wait_freezes / repeat.

Tests the engine-level wrapping added to PipelineEngine.execute() around
node.execute() calls. Uses real PipelineEngine with a tiny graph that
runs a single mock node, verifying that lifecycle fields are honored.
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# Register nodes.
import engine.nodes.click  # noqa: F401
from core.result import success_result
from engine.node import PipelineNode, register_node
from engine.pipeline_engine import PipelineEngine

pytestmark = pytest.mark.unit


def _build_engine_with_single_node(
    node_config: dict, device=None
) -> PipelineEngine:
    """Build an engine with a one-node pipeline graph.

    Uses the public PipelineEngine.load(pipeline_json, device) API —
    NOT load_graph() or execute(context=).
    """
    pipeline_json = {
        "nodes": [
            {
                "id": "n1",
                "name": "n1",
                "node_type": "noop_test",
                "config": node_config,
            },
        ],
        "edges": [],
        "entry_node": "n1",
    }
    engine = PipelineEngine()
    engine.load(pipeline_json, device=device)
    return engine


# A test-only node that records execute calls and sleeps.
EXEC_CALLS: list = []


@register_node("noop_test")
class _NoopTestNode(PipelineNode):
    """Test node: appends timestamp to EXEC_CALLS and returns success."""
    node_type: str = "noop_test"

    def execute(self, context):
        EXEC_CALLS.append(time.monotonic())
        return success_result(data={"call": len(EXEC_CALLS)})


@pytest.fixture(autouse=True)
def _clear_exec_calls():
    EXEC_CALLS.clear()
    yield
    EXEC_CALLS.clear()


# ============================================================
# pre_delay / post_delay
# ============================================================

class TestPrePostDelay:
    def test_pre_delay_delays_execute(self):
        engine = _build_engine_with_single_node({"pre_delay": 0.1})
        start = time.monotonic()
        engine.execute()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.08
        assert len(EXEC_CALLS) == 1

    def test_post_delay_delays_after_execute(self):
        engine = _build_engine_with_single_node({"post_delay": 0.1})
        start = time.monotonic()
        engine.execute()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.08

    def test_zero_pre_delay_no_wait(self):
        engine = _build_engine_with_single_node({"pre_delay": 0})
        start = time.monotonic()
        engine.execute()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1  # Should be near-instant.

    def test_negative_delay_treated_as_no_wait(self):
        engine = _build_engine_with_single_node({"pre_delay": -1, "post_delay": -1})
        start = time.monotonic()
        engine.execute()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1


# ============================================================
# repeat
# ============================================================

class TestRepeat:
    def test_repeat_3_executes_3_times(self):
        engine = _build_engine_with_single_node({"repeat": 3})
        engine.execute()
        assert len(EXEC_CALLS) == 3

    def test_repeat_1_default(self):
        engine = _build_engine_with_single_node({})
        engine.execute()
        assert len(EXEC_CALLS) == 1

    def test_repeat_invalid_falls_back_to_1(self):
        engine = _build_engine_with_single_node({"repeat": 0})
        engine.execute()
        assert len(EXEC_CALLS) == 1

    def test_repeat_negative_falls_back_to_1(self):
        engine = _build_engine_with_single_node({"repeat": -5})
        engine.execute()
        assert len(EXEC_CALLS) == 1


# ============================================================
# pre_wait_freezes / post_wait_freezes
# ============================================================

class TestWaitFreezesHooks:
    def test_pre_wait_freezes_calls_wait_freezes(self):
        """When pre_wait_freezes is set and a device is bound, WaitFreezes.wait() is called."""
        dev = MagicMock()
        import numpy as np
        dev.capture_screen.return_value = np.zeros((10, 10, 3), dtype=np.uint8)

        engine = _build_engine_with_single_node(
            {"pre_wait_freezes": 0.5}, device=dev
        )
        with patch("core.wait_freezes.WaitFreezes") as mock_wf:
            mock_wf_inst = MagicMock()
            mock_wf.return_value = mock_wf_inst
            engine.execute()
            mock_wf.assert_called_once()
            mock_wf_inst.wait.assert_called_once()

    def test_post_wait_freezes_calls_wait_freezes(self):
        dev = MagicMock()
        import numpy as np
        dev.capture_screen.return_value = np.zeros((10, 10, 3), dtype=np.uint8)

        engine = _build_engine_with_single_node(
            {"post_wait_freezes": 0.5}, device=dev
        )
        with patch("core.wait_freezes.WaitFreezes") as mock_wf:
            mock_wf_inst = MagicMock()
            mock_wf.return_value = mock_wf_inst
            engine.execute()
            mock_wf_inst.wait.assert_called_once()

    def test_wait_freezes_skipped_without_device(self):
        """When no device is bound, wait_freezes is a no-op (no exception)."""
        engine = _build_engine_with_single_node({"pre_wait_freezes": 0.5})
        # Should not raise.
        engine.execute()
        assert len(EXEC_CALLS) == 1

    def test_wait_freezes_dict_config(self):
        """pre_wait_freezes accepts a dict config with timeout/similarity/etc."""
        dev = MagicMock()
        import numpy as np
        dev.capture_screen.return_value = np.zeros((10, 10, 3), dtype=np.uint8)

        wf_cfg = {"timeout": 1.0, "similarity": 0.95, "interval_ms": 30, "stable_frames": 2}
        engine = _build_engine_with_single_node(
            {"pre_wait_freezes": wf_cfg}, device=dev
        )
        with patch("core.wait_freezes.WaitFreezes") as mock_wf:
            mock_wf_inst = MagicMock()
            mock_wf.return_value = mock_wf_inst
            engine.execute()
            # Verify constructor args were drawn from dict config.
            _, kwargs = mock_wf.call_args
            assert kwargs["default_similarity"] == 0.95
            assert kwargs["interval_ms"] == 30.0
            assert kwargs["stable_frames"] == 2


# ============================================================
# Combined lifecycle
# ============================================================

class TestCombinedLifecycle:
    def test_pre_and_post_delay_both_applied(self):
        engine = _build_engine_with_single_node({"pre_delay": 0.05, "post_delay": 0.05})
        start = time.monotonic()
        engine.execute()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.08  # ~0.10s total.

    def test_repeat_with_delay(self):
        engine = _build_engine_with_single_node({"repeat": 2, "pre_delay": 0.03})
        start = time.monotonic()
        engine.execute()
        elapsed = time.monotonic() - start
        # pre_delay is applied once before the repeat loop, so total ≈ 0.03s.
        assert elapsed >= 0.025
        assert len(EXEC_CALLS) == 2
