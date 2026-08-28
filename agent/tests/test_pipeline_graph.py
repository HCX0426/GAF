"""PipelineGraph DAG engine tests.

Covers:
- compute_in_degree / compute_out_degree
- topological_sort (Kahn's algorithm, cycle detection)
- detect_cycles (DFS coloring)
- get_parallel_levels (wave grouping)
- get_reachable_nodes (BFS)
- get_critical_path (longest path)
- validate_dag (cycle + entry + edge validation)
- build_subgraph (reachable subgraph)
- ParallelExecutor (parallel wave execution, pause/cancel, continue_on_error)
- DAGExecutor (high-level load + execute)
"""

import sys
import threading
import time
from pathlib import Path

import pytest

# Ensure src on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.result import AutoResult, fail_result, success_result
from engine.context import PipelineContext, PipelineState
from engine.graph import (
    DAGCycleError,
    DAGExecutor,
    ParallelExecutionResult,
    ParallelExecutor,
    build_subgraph,
    compute_in_degree,
    compute_out_degree,
    detect_cycles,
    get_critical_path,
    get_parallel_levels,
    get_reachable_nodes,
    topological_sort,
    validate_dag,
)
from engine.node import PipelineNode
from engine.nodes import wait as _wait_module  # noqa: F401 — registers "wait" node type
from engine.parser import PipelineEdge, PipelineGraph

pytestmark = pytest.mark.integration

# ============================================================
# Helpers
# ============================================================

def make_node(node_id: str, node_type: str = "wait", config: dict | None = None) -> PipelineNode:
    """Create a minimal PipelineNode for testing."""
    return PipelineNode(
        id=node_id,
        name=node_id,
        node_type=node_type,
        config=config or {},
    )


def make_graph(
    nodes: list[str],
    edges: list[tuple[str, str]],
    entry: str = "",
) -> PipelineGraph:
    """Build a PipelineGraph from node IDs and edge tuples."""
    graph = PipelineGraph(entry_node=entry or (nodes[0] if nodes else ""))
    for nid in nodes:
        graph.nodes[nid] = make_node(nid)
    for from_node, to_node in edges:
        if from_node not in graph.edges:
            graph.edges[from_node] = []
        graph.edges[from_node].append(
            PipelineEdge(from_node=from_node, to_node=to_node)
        )
    return graph


class RecordingNode(PipelineNode):
    """Test node that records execution order and returns configurable result."""

    def __init__(self, node_id: str, recorder: list, delay: float = 0.0,
                 result: AutoResult | None = None):
        super().__init__(id=node_id, name=node_id, node_type="test_record")
        self._recorder = recorder
        self._delay = delay
        # Use explicit None check — AutoResult.__bool__ returns success, so
        # `result or success_result(...)` would discard a fail_result.
        self._result = result if result is not None else success_result(data={"node": node_id})

    def execute(self, context: PipelineContext) -> AutoResult:
        if self._delay:
            time.sleep(self._delay)
        self._recorder.append(self.id)
        return self._result


# ============================================================
# compute_in_degree / compute_out_degree
# ============================================================

class TestComputeDegrees:
    """In-degree and out-degree computation."""

    def test_empty_graph(self):
        graph = PipelineGraph()
        assert compute_in_degree(graph) == {}
        assert compute_out_degree(graph) == {}

    def test_single_node_no_edges(self):
        graph = make_graph(["a"], [])
        assert compute_in_degree(graph) == {"a": 0}
        assert compute_out_degree(graph) == {"a": 0}

    def test_linear_chain(self):
        graph = make_graph(["a", "b", "c"], [("a", "b"), ("b", "c")])
        assert compute_in_degree(graph) == {"a": 0, "b": 1, "c": 1}
        assert compute_out_degree(graph) == {"a": 1, "b": 1, "c": 0}

    def test_diamond_shape(self):
        graph = make_graph(
            ["a", "b", "c", "d"],
            [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
        )
        assert compute_in_degree(graph) == {"a": 0, "b": 1, "c": 1, "d": 2}
        assert compute_out_degree(graph) == {"a": 2, "b": 1, "c": 1, "d": 0}

    def test_edge_to_unknown_node_ignored(self):
        graph = make_graph(["a"], [("a", "unknown")])
        in_deg = compute_in_degree(graph)
        assert in_deg == {"a": 0}


# ============================================================
# topological_sort
# ============================================================

class TestTopologicalSort:
    """Kahn's algorithm topological sort."""

    def test_empty_graph(self):
        assert topological_sort(PipelineGraph()) == []

    def test_single_node(self):
        graph = make_graph(["a"], [])
        assert topological_sort(graph) == ["a"]

    def test_linear_chain_preserves_order(self):
        graph = make_graph(["a", "b", "c"], [("a", "b"), ("b", "c")])
        result = topological_sort(graph)
        assert result == ["a", "b", "c"]

    def test_diamond_shape(self):
        graph = make_graph(
            ["a", "b", "c", "d"],
            [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
        )
        result = topological_sort(graph)
        # a must come first, d must come last, b and c in between
        assert result[0] == "a"
        assert result[-1] == "d"
        assert set(result[1:3]) == {"b", "c"}

    def test_cycle_raises(self):
        graph = make_graph(
            ["a", "b", "c"],
            [("a", "b"), ("b", "c"), ("c", "a")],
        )
        with pytest.raises(DAGCycleError):
            topological_sort(graph)

    def test_self_loop_raises(self):
        graph = make_graph(["a"], [("a", "a")])
        with pytest.raises(DAGCycleError):
            topological_sort(graph)

    def test_all_nodes_present(self):
        graph = make_graph(
            ["a", "b", "c", "d", "e"],
            [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e")],
        )
        result = topological_sort(graph)
        assert set(result) == {"a", "b", "c", "d", "e"}
        assert len(result) == 5


# ============================================================
# detect_cycles
# ============================================================

class TestDetectCycles:
    """DFS-based cycle detection."""

    def test_no_cycles_in_dag(self):
        graph = make_graph(
            ["a", "b", "c"],
            [("a", "b"), ("b", "c")],
        )
        assert detect_cycles(graph) == []

    def test_simple_cycle(self):
        graph = make_graph(
            ["a", "b", "c"],
            [("a", "b"), ("b", "c"), ("c", "a")],
        )
        cycles = detect_cycles(graph)
        assert len(cycles) >= 1
        # The cycle should contain a, b, c
        cycle_nodes = set(cycles[0])
        assert cycle_nodes == {"a", "b", "c"}

    def test_self_loop(self):
        graph = make_graph(["a"], [("a", "a")])
        cycles = detect_cycles(graph)
        assert len(cycles) >= 1

    def test_disconnected_with_cycle(self):
        graph = make_graph(
            ["a", "b", "c", "d"],
            [("a", "b"), ("c", "d"), ("d", "c")],
        )
        cycles = detect_cycles(graph)
        assert len(cycles) >= 1
        cycle_nodes = set()
        for cycle in cycles:
            cycle_nodes.update(cycle)
        assert {"c", "d"}.issubset(cycle_nodes)

    def test_empty_graph(self):
        assert detect_cycles(PipelineGraph()) == []


# ============================================================
# get_parallel_levels
# ============================================================

class TestGetParallelLevels:
    """Wave-based parallel level grouping."""

    def test_empty_graph(self):
        assert get_parallel_levels(PipelineGraph()) == []

    def test_single_node(self):
        graph = make_graph(["a"], [])
        assert get_parallel_levels(graph) == [["a"]]

    def test_linear_chain(self):
        graph = make_graph(["a", "b", "c"], [("a", "b"), ("b", "c")])
        assert get_parallel_levels(graph) == [["a"], ["b"], ["c"]]

    def test_diamond_shape(self):
        graph = make_graph(
            ["a", "b", "c", "d"],
            [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
        )
        levels = get_parallel_levels(graph)
        assert len(levels) == 3
        assert levels[0] == ["a"]
        assert set(levels[1]) == {"b", "c"}
        assert levels[2] == ["d"]

    def test_two_independent_chains(self):
        graph = make_graph(
            ["a", "b", "c", "d"],
            [("a", "b"), ("c", "d")],
        )
        levels = get_parallel_levels(graph)
        # Level 0: a and c (both in-degree 0)
        assert set(levels[0]) == {"a", "c"}
        # Level 1: b and d
        assert set(levels[1]) == {"b", "d"}

    def test_cycle_raises(self):
        graph = make_graph(
            ["a", "b"],
            [("a", "b"), ("b", "a")],
        )
        with pytest.raises(DAGCycleError):
            get_parallel_levels(graph)


# ============================================================
# get_reachable_nodes
# ============================================================

class TestGetReachableNodes:
    """BFS reachability."""

    def test_start_not_in_graph(self):
        graph = make_graph(["a"], [])
        assert get_reachable_nodes(graph, "unknown") == set()

    def test_single_node(self):
        graph = make_graph(["a"], [])
        assert get_reachable_nodes(graph, "a") == {"a"}

    def test_linear_chain(self):
        graph = make_graph(["a", "b", "c"], [("a", "b"), ("b", "c")])
        assert get_reachable_nodes(graph, "a") == {"a", "b", "c"}
        assert get_reachable_nodes(graph, "b") == {"b", "c"}
        assert get_reachable_nodes(graph, "c") == {"c"}

    def test_diamond_shape(self):
        graph = make_graph(
            ["a", "b", "c", "d"],
            [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
        )
        assert get_reachable_nodes(graph, "a") == {"a", "b", "c", "d"}
        assert get_reachable_nodes(graph, "b") == {"b", "d"}

    def test_disconnected_graph(self):
        graph = make_graph(
            ["a", "b", "c", "d"],
            [("a", "b"), ("c", "d")],
        )
        assert get_reachable_nodes(graph, "a") == {"a", "b"}
        assert get_reachable_nodes(graph, "c") == {"c", "d"}


# ============================================================
# get_critical_path
# ============================================================

class TestGetCriticalPath:
    """Longest path (critical path) analysis."""

    def test_empty_graph(self):
        path, cost = get_critical_path(PipelineGraph())
        assert path == []
        assert cost == 0.0

    def test_single_node(self):
        graph = make_graph(["a"], [])
        path, cost = get_critical_path(graph)
        assert path == ["a"]
        assert cost == 1.0

    def test_linear_chain(self):
        graph = make_graph(["a", "b", "c"], [("a", "b"), ("b", "c")])
        path, cost = get_critical_path(graph)
        assert path == ["a", "b", "c"]
        assert cost == 3.0

    def test_diamond_picks_longer_branch(self):
        graph = make_graph(
            ["a", "b", "c", "d"],
            [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
        )
        # With default cost 1.0 each, both paths are equal length (3)
        path, cost = get_critical_path(graph)
        assert cost == 3.0
        assert path[0] == "a"
        assert path[-1] == "d"

    def test_with_custom_costs(self):
        graph = make_graph(
            ["a", "b", "c", "d"],
            [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
        )
        # Make b branch longer
        costs = {"a": 1.0, "b": 5.0, "c": 1.0, "d": 1.0}
        path, cost = get_critical_path(graph, costs)
        assert path == ["a", "b", "d"]
        assert cost == 7.0

    def test_cycle_raises(self):
        graph = make_graph(
            ["a", "b"],
            [("a", "b"), ("b", "a")],
        )
        with pytest.raises(DAGCycleError):
            get_critical_path(graph)


# ============================================================
# validate_dag
# ============================================================

class TestValidateDag:
    """DAG validation."""

    def test_valid_dag(self):
        graph = make_graph(
            ["a", "b", "c"],
            [("a", "b"), ("b", "c")],
            entry="a",
        )
        assert validate_dag(graph) == []

    def test_cycle_detected(self):
        graph = make_graph(
            ["a", "b"],
            [("a", "b"), ("b", "a")],
        )
        errors = validate_dag(graph)
        assert len(errors) >= 1
        assert any("Cycle" in e for e in errors)

    def test_entry_node_missing(self):
        graph = make_graph(["a", "b"], [("a", "b")], entry="nonexistent")
        errors = validate_dag(graph)
        assert any("Entry node" in e for e in errors)

    def test_edge_to_invalid_node(self):
        graph = PipelineGraph(entry_node="a")
        graph.nodes["a"] = make_node("a")
        graph.edges["a"] = [PipelineEdge(from_node="a", to_node="ghost")]
        errors = validate_dag(graph)
        assert any("ghost" in e for e in errors)

    def test_edge_from_invalid_node(self):
        graph = PipelineGraph(entry_node="a")
        graph.nodes["a"] = make_node("a")
        graph.edges["ghost"] = [PipelineEdge(from_node="ghost", to_node="a")]
        errors = validate_dag(graph)
        assert any("ghost" in e for e in errors)


# ============================================================
# build_subgraph
# ============================================================

class TestBuildSubgraph:
    """Reachable subgraph construction."""

    def test_full_graph_reachable(self):
        graph = make_graph(
            ["a", "b", "c"],
            [("a", "b"), ("b", "c")],
            entry="a",
        )
        sub = build_subgraph(graph, "a")
        assert set(sub.nodes.keys()) == {"a", "b", "c"}
        assert sub.entry_node == "a"

    def test_partial_subgraph(self):
        graph = make_graph(
            ["a", "b", "c", "d"],
            [("a", "b"), ("b", "c"), ("c", "d")],
            entry="a",
        )
        sub = build_subgraph(graph, "b")
        assert set(sub.nodes.keys()) == {"b", "c", "d"}
        assert sub.entry_node == "b"

    def test_disconnected_subgraph(self):
        graph = make_graph(
            ["a", "b", "c", "d"],
            [("a", "b"), ("c", "d")],
            entry="a",
        )
        sub = build_subgraph(graph, "a")
        assert set(sub.nodes.keys()) == {"a", "b"}
        sub2 = build_subgraph(graph, "c")
        assert set(sub2.nodes.keys()) == {"c", "d"}

    def test_start_not_in_graph(self):
        graph = make_graph(["a"], [])
        sub = build_subgraph(graph, "unknown")
        assert len(sub.nodes) == 0


# ============================================================
# ParallelExecutor
# ============================================================

class TestParallelExecutor:
    """Parallel wave-based execution."""

    def test_linear_execution(self):
        graph = make_graph(
            ["a", "b", "c"],
            [("a", "b"), ("b", "c")],
            entry="a",
        )
        recorder: list = []
        for nid in ["a", "b", "c"]:
            graph.nodes[nid] = RecordingNode(nid, recorder)

        executor = ParallelExecutor(max_workers=4)
        result = executor.execute(graph, PipelineContext())

        assert result.success
        assert result.state == PipelineState.COMPLETED
        assert set(result.node_results.keys()) == {"a", "b", "c"}
        assert recorder == ["a", "b", "c"]

    def test_parallel_branches(self):
        graph = make_graph(
            ["a", "b", "c", "d"],
            [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
            entry="a",
        )
        recorder: list = []
        # b and c have delay to verify they run in parallel
        graph.nodes["a"] = RecordingNode("a", recorder)
        graph.nodes["b"] = RecordingNode("b", recorder, delay=0.1)
        graph.nodes["c"] = RecordingNode("c", recorder, delay=0.1)
        graph.nodes["d"] = RecordingNode("d", recorder)

        executor = ParallelExecutor(max_workers=4)
        start = time.monotonic()
        result = executor.execute(graph, PipelineContext())
        elapsed = time.monotonic() - start

        assert result.success
        # If b and c ran in parallel, total time should be < 0.2s (sequential would be 0.2s+)
        assert elapsed < 0.18, f"Parallel execution too slow: {elapsed}s"
        # a first, d last, b and c in between
        assert recorder[0] == "a"
        assert recorder[-1] == "d"
        assert set(recorder[1:3]) == {"b", "c"}

    def test_branch_merge_synchronization(self):
        """Node d (in-degree 2) must wait for both b and c."""
        graph = make_graph(
            ["a", "b", "c", "d"],
            [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
            entry="a",
        )
        recorder: list = []
        graph.nodes["a"] = RecordingNode("a", recorder)
        graph.nodes["b"] = RecordingNode("b", recorder, delay=0.05)
        graph.nodes["c"] = RecordingNode("c", recorder, delay=0.15)
        graph.nodes["d"] = RecordingNode("d", recorder)

        executor = ParallelExecutor(max_workers=4)
        result = executor.execute(graph, PipelineContext())

        assert result.success
        # d must come after both b and c
        assert recorder.index("d") > recorder.index("b")
        assert recorder.index("d") > recorder.index("c")

    def test_node_failure_stops_execution(self):
        graph = make_graph(
            ["a", "b", "c"],
            [("a", "b"), ("b", "c")],
            entry="a",
        )
        recorder: list = []
        graph.nodes["a"] = RecordingNode("a", recorder)
        graph.nodes["b"] = RecordingNode(
            "b", recorder, result=fail_result(error_msg="b failed")
        )
        graph.nodes["c"] = RecordingNode("c", recorder)

        executor = ParallelExecutor(max_workers=4)
        result = executor.execute(graph, PipelineContext())

        assert not result.success
        assert result.state == PipelineState.FAILED
        assert "b" in result.failed_nodes
        assert "c" not in result.node_results  # c should not execute

    def test_continue_on_error(self):
        graph = make_graph(
            ["a", "b", "c"],
            [("a", "b"), ("b", "c")],
            entry="a",
        )
        recorder: list = []
        graph.nodes["a"] = RecordingNode("a", recorder)
        graph.nodes["b"] = RecordingNode(
            "b", recorder,
            result=fail_result(error_msg="b failed"),
        )
        graph.nodes["b"].config["continue_on_error"] = True
        graph.nodes["c"] = RecordingNode("c", recorder)

        executor = ParallelExecutor(max_workers=4)
        result = executor.execute(graph, PipelineContext())

        # b failed but continue_on_error=True, so c should still execute
        assert "b" in result.failed_nodes
        assert "c" in result.node_results
        assert recorder == ["a", "b", "c"]

    def test_cancel(self):
        graph = make_graph(
            ["a", "b", "c"],
            [("a", "b"), ("b", "c")],
            entry="a",
        )
        recorder: list = []
        graph.nodes["a"] = RecordingNode("a", recorder, delay=0.05)
        graph.nodes["b"] = RecordingNode("b", recorder, delay=0.2)
        graph.nodes["c"] = RecordingNode("c", recorder)

        executor = ParallelExecutor(max_workers=4)

        # Cancel after a short delay
        def cancel_after():
            time.sleep(0.1)
            executor.cancel()

        t = threading.Thread(target=cancel_after)
        t.start()
        result = executor.execute(graph, PipelineContext())
        t.join()

        assert result.state == PipelineState.CANCELLED

    def test_callbacks_invoked(self):
        graph = make_graph(["a", "b"], [("a", "b")], entry="a")
        recorder: list = []
        graph.nodes["a"] = RecordingNode("a", recorder)
        graph.nodes["b"] = RecordingNode("b", recorder)

        completed: list = []
        errors: list = []

        executor = ParallelExecutor(max_workers=4)
        executor.set_callbacks(
            on_step_complete=lambda nid, res: completed.append(nid),
            on_error=lambda nid, exc: errors.append((nid, exc)),
        )
        result = executor.execute(graph, PipelineContext())

        assert result.success
        assert set(completed) == {"a", "b"}
        assert errors == []

    def test_cycle_returns_failure(self):
        graph = make_graph(
            ["a", "b"],
            [("a", "b"), ("b", "a")],
            entry="a",
        )
        executor = ParallelExecutor(max_workers=4)
        result = executor.execute(graph, PipelineContext())
        assert not result.success
        assert result.state == PipelineState.FAILED

    def test_no_entry_node(self):
        graph = make_graph(["a", "b"], [("a", "b")], entry="")
        executor = ParallelExecutor(max_workers=4)
        result = executor.execute(graph, PipelineContext())
        assert not result.success
        assert result.state == PipelineState.FAILED

    def test_validation_failure(self):
        """Graph with edge to non-existent node fails validation."""
        graph = PipelineGraph(entry_node="a")
        graph.nodes["a"] = make_node("a")
        graph.edges["a"] = [PipelineEdge(from_node="a", to_node="ghost")]
        executor = ParallelExecutor(max_workers=4)
        result = executor.execute(graph, PipelineContext())
        assert not result.success
        assert result.state == PipelineState.FAILED


# ============================================================
# ParallelExecutor pause/resume
# ============================================================

class TestParallelExecutorPauseResume:
    """Pause and resume functionality."""

    def test_pause_resume(self):
        graph = make_graph(
            ["a", "b", "c"],
            [("a", "b"), ("b", "c")],
            entry="a",
        )
        recorder: list = []
        graph.nodes["a"] = RecordingNode("a", recorder)
        graph.nodes["b"] = RecordingNode("b", recorder, delay=0.1)
        graph.nodes["c"] = RecordingNode("c", recorder)

        executor = ParallelExecutor(max_workers=4)

        # Pause after a starts, resume before b finishes
        def control():
            time.sleep(0.02)
            executor.pause()
            time.sleep(0.15)
            executor.resume()

        t = threading.Thread(target=control)
        t.start()
        result = executor.execute(graph, PipelineContext())
        t.join()

        assert result.success
        assert set(recorder) == {"a", "b", "c"}


# ============================================================
# DAGExecutor
# ============================================================

class TestDAGExecutor:
    """High-level DAG executor."""

    def test_load_and_execute(self):
        pipeline_json = {
            "entry_node": "a",
            "nodes": [
                {"id": "a", "node_type": "wait", "config": {"seconds": 0}},
                {"id": "b", "node_type": "wait", "config": {"seconds": 0}},
                {"id": "c", "node_type": "wait", "config": {"seconds": 0}},
            ],
            "edges": [
                {"from": "a", "to": "b"},
                {"from": "b", "to": "c"},
            ],
        }
        executor = DAGExecutor(max_workers=4)
        executor.load(pipeline_json)
        assert executor.state == PipelineState.PENDING

        result = executor.execute()
        assert result.success
        assert result.state == PipelineState.COMPLETED
        assert executor.state == PipelineState.COMPLETED
        assert set(result.node_results.keys()) == {"a", "b", "c"}

    def test_execute_without_load_raises(self):
        executor = DAGExecutor()
        with pytest.raises(RuntimeError):
            executor.execute()

    def test_cancel(self):
        pipeline_json = {
            "entry_node": "a",
            "nodes": [
                {"id": "a", "node_type": "wait", "config": {"seconds": 0.5}},
                {"id": "b", "node_type": "wait", "config": {"seconds": 0}},
            ],
            "edges": [{"from": "a", "to": "b"}],
        }
        executor = DAGExecutor(max_workers=4)
        executor.load(pipeline_json)

        def cancel_after():
            time.sleep(0.1)
            executor.cancel()

        t = threading.Thread(target=cancel_after)
        t.start()
        result = executor.execute()
        t.join()

        assert result.state == PipelineState.CANCELLED

    def test_callbacks(self):
        pipeline_json = {
            "entry_node": "a",
            "nodes": [
                {"id": "a", "node_type": "wait", "config": {"seconds": 0}},
                {"id": "b", "node_type": "wait", "config": {"seconds": 0}},
            ],
            "edges": [{"from": "a", "to": "b"}],
        }
        executor = DAGExecutor(max_workers=4)
        completed: list = []
        executor.set_callbacks(
            on_step_complete=lambda nid, res: completed.append(nid),
        )
        executor.load(pipeline_json)
        result = executor.execute()

        assert result.success
        assert set(completed) == {"a", "b"}

    def test_context_available(self):
        pipeline_json = {
            "entry_node": "a",
            "nodes": [
                {"id": "a", "node_type": "wait", "config": {"seconds": 0}},
            ],
        }
        executor = DAGExecutor()
        executor.load(pipeline_json)
        assert executor.context is not None
        result = executor.execute()
        assert result.success


# ============================================================
# ParallelExecutionResult
# ============================================================

class TestParallelExecutionResult:
    """Result dataclass behavior."""

    def test_success_bool(self):
        r = ParallelExecutionResult(success=True, state=PipelineState.COMPLETED)
        assert bool(r) is True

    def test_failure_bool(self):
        r = ParallelExecutionResult(success=False, state=PipelineState.FAILED)
        assert bool(r) is False

    def test_default_values(self):
        r = ParallelExecutionResult(success=True, state=PipelineState.COMPLETED)
        assert r.node_results == {}
        assert r.elapsed_time == 0.0
        assert r.failed_nodes == []
