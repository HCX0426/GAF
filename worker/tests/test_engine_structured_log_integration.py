"""Integration test: PipelineEngine writes structured JSONL logs.

Verifies that running a small pipeline through PipelineEngine produces
a structured_log.jsonl file with one entry per node execution, and that
the entries carry the expected fields (node_id, success, elapsed_ms).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure worker/src is on sys.path (parent conftest normally handles this,
# but we add it explicitly for self-contained runs).
_AGENT_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(_AGENT_SRC))

import engine.nodes  # noqa: F401, E402  (populates PIPELINE_NODE_REGISTRY)
import pytest  # noqa: E402 - after sys.path setup above
from engine.pipeline_engine import PipelineEngine  # noqa: E402

pytestmark = pytest.mark.unit


def _read_jsonl(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class TestEngineStructuredLogIntegration:
    def test_pipeline_writes_one_entry_per_node(self, tmp_path):
        """Run a 2-node pipeline (wait fixed + wait fixed), verify 2 JSONL entries."""
        pipeline_json = {
            "name": "structured_log_test",
            "entry_node": "w1",
            "nodes": [
                {
                    "id": "w1",
                    "type": "wait",
                    "config": {"mode": "fixed", "seconds": 0.01},
                    "next_node_id": "w2",
                },
                {
                    "id": "w2",
                    "type": "wait",
                    "config": {"mode": "fixed", "seconds": 0.01},
                },
            ],
        }
        engine = PipelineEngine()
        engine.load(pipeline_json, debug_dir=str(tmp_path))
        result = engine.execute()

        assert result.success, f"pipeline should succeed: {result.error_msg}"

        # The JSONL file should be at <debug_dir>/structured/<execution_id>.jsonl
        structured_dir = tmp_path / "structured"
        assert structured_dir.is_dir()
        files = list(structured_dir.glob("exec-*.jsonl"))
        assert len(files) == 1, f"expected 1 JSONL file, got {files}"
        entries = _read_jsonl(str(files[0]))

        # Task 3.3 (N192 A3 P2): 每个节点产生 start+complete 两个事件,
        # 2 个节点共 4 个 entries. 这里只校验 complete 事件.
        complete_entries = [e for e in entries if e.get("event") == "node.execute.complete"]
        assert len(complete_entries) == 2
        assert complete_entries[0]["node_id"] == "w1"
        assert complete_entries[1]["node_id"] == "w2"
        assert complete_entries[0]["node_type"] == "wait"
        assert complete_entries[0]["success"] is True
        # execution_id in entries matches filename
        eid = files[0].stem  # e.g. "exec-abc123def456"
        for e in entries:
            assert e["execution_id"] == eid

    def test_failed_node_logs_failure(self, tmp_path):
        """A pipeline with a failing node should still log the failure event."""
        # wait(template) without device fails immediately with "no device"
        pipeline_json = {
            "name": "structured_log_fail_test",
            "entry_node": "w1",
            "nodes": [
                {
                    "id": "w1",
                    "type": "wait",
                    "config": {"mode": "template", "max_wait": 0.5, "template": "x.png"},
                },
            ],
        }
        engine = PipelineEngine()
        engine.load(pipeline_json, debug_dir=str(tmp_path))
        result = engine.execute()

        # Should fail because no device
        assert not result.success

        structured_dir = tmp_path / "structured"
        files = list(structured_dir.glob("exec-*.jsonl"))
        assert len(files) == 1
        entries = _read_jsonl(str(files[0]))

        # Task 3.3: 节点会产生 start+complete 两个事件.
        # 只校验 complete 事件 (含 success/error_msg 字段).
        complete_entries = [e for e in entries if e.get("event") == "node.execute.complete"]
        assert len(complete_entries) == 1
        e = complete_entries[0]
        assert e["success"] is False
        assert e["node_id"] == "w1"
        assert "no device" in e["error_msg"]

    def test_execution_id_property_set(self, tmp_path):
        """After execute(), engine.execution_id should be a non-empty string."""
        pipeline_json = {
            "name": "eid_test",
            "entry_node": "w1",
            "nodes": [
                {"id": "w1", "type": "wait", "config": {"mode": "fixed", "seconds": 0.01}},
            ],
        }
        engine = PipelineEngine()
        # Before execute, execution_id is empty
        assert engine.execution_id == ""
        engine.load(pipeline_json, debug_dir=str(tmp_path))
        engine.execute()
        # After execute, execution_id is set
        assert engine.execution_id.startswith("exec-")
        assert len(engine.execution_id) == len("exec-") + 12

    def test_two_executions_get_different_ids(self, tmp_path):
        """Two consecutive execute() calls should produce different execution_ids."""
        pipeline_json = {
            "name": "two_run_test",
            "entry_node": "w1",
            "nodes": [
                {"id": "w1", "type": "wait", "config": {"mode": "fixed", "seconds": 0.01}},
            ],
        }
        engine = PipelineEngine()
        engine.load(pipeline_json, debug_dir=str(tmp_path))
        engine.execute()
        eid1 = engine.execution_id
        engine.execute()
        eid2 = engine.execution_id
        assert eid1 != eid2

        # And two separate JSONL files
        structured_dir = tmp_path / "structured"
        files = list(structured_dir.glob("exec-*.jsonl"))
        assert len(files) == 2
