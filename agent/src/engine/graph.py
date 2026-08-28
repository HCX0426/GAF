"""PipelineGraph DAG engine — topological sort, parallel execution, branch merge.

Extends the linear PipelineEngine with DAG-aware operations:
- topological_sort: Kahn's algorithm for linear ordering
- detect_cycles: DFS-based cycle detection
- get_parallel_levels: group nodes into parallel-executable waves
- get_critical_path: longest-path analysis for bottleneck detection
- ParallelExecutor: ThreadPoolExecutor-based parallel node execution
- DAGExecutor: high-level DAG execution with branch merge synchronization

Branch merge is handled automatically via wave barriers: all nodes in the
same topological level must complete before the next level starts, so any
node with in-degree > 1 acts as a synchronization (merge) point.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

from core.result import AutoResult, fail_result
from engine.context import PipelineContext, PipelineState
from engine.node import PipelineNode
from engine.parser import PipelineGraph

logger = logging.getLogger(__name__)


class DAGCycleError(Exception):
    """Raised when the graph contains a cycle (not a DAG)."""


# ── Graph analysis functions ──────────────────────────────────────────


def compute_in_degree(graph: PipelineGraph) -> dict[str, int]:
    """Compute in-degree (number of incoming edges) for each node.

    Args:
        graph: PipelineGraph instance.

    Returns:
        Dict mapping node_id to in-degree.
    """
    in_degree: dict[str, int] = dict.fromkeys(graph.nodes, 0)
    for edge_list in graph.edges.values():
        for edge in edge_list:
            if edge.to_node in in_degree:
                in_degree[edge.to_node] += 1
    return in_degree


def compute_out_degree(graph: PipelineGraph) -> dict[str, int]:
    """Compute out-degree (number of outgoing edges) for each node.

    Args:
        graph: PipelineGraph instance.

    Returns:
        Dict mapping node_id to out-degree.
    """
    out_degree: dict[str, int] = dict.fromkeys(graph.nodes, 0)
    for from_node, edge_list in graph.edges.items():
        if from_node in out_degree:
            out_degree[from_node] = len(edge_list)
    return out_degree


def _get_predecessors(graph: PipelineGraph, node_id: str) -> list[str]:
    """Get all predecessor node IDs for a given node."""
    preds: list[str] = []
    for from_node, edge_list in graph.edges.items():
        for edge in edge_list:
            if edge.to_node == node_id:
                preds.append(from_node)
                break
    return preds


def _build_adjacency(graph: PipelineGraph) -> dict[str, list[str]]:
    """Build adjacency list from graph edges."""
    adj: dict[str, list[str]] = {nid: [] for nid in graph.nodes}
    for from_node, edge_list in graph.edges.items():
        if from_node in adj:
            for edge in edge_list:
                if edge.to_node in adj:
                    adj[from_node].append(edge.to_node)
    return adj


def topological_sort(graph: PipelineGraph) -> list[str]:
    """Kahn's algorithm topological sort.

    Args:
        graph: PipelineGraph instance.

    Returns:
        List of node IDs in topological order.

    Raises:
        DAGCycleError: If the graph contains a cycle.
    """
    in_degree = compute_in_degree(graph)
    adj = _build_adjacency(graph)

    queue: list[str] = [nid for nid, deg in in_degree.items() if deg == 0]
    result: list[str] = []

    while queue:
        node_id = queue.pop(0)
        result.append(node_id)
        for next_id in adj.get(node_id, []):
            in_degree[next_id] -= 1
            if in_degree[next_id] == 0:
                queue.append(next_id)

    if len(result) != len(graph.nodes):
        remaining = set(graph.nodes.keys()) - set(result)
        raise DAGCycleError(f"Graph contains a cycle involving nodes: {sorted(remaining)}")

    return result


def detect_cycles(graph: PipelineGraph) -> list[list[str]]:
    """Detect all cycles in the graph using DFS with coloring.

    Returns:
        List of cycles, each cycle is a list of node IDs forming the path.
    """
    white, gray, black = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(graph.nodes, white)
    cycles: list[list[str]] = []

    def dfs(node_id: str, path: list[str]) -> None:
        color[node_id] = gray
        path.append(node_id)
        for edge in graph.edges.get(node_id, []):
            if edge.to_node not in color:
                continue
            if color[edge.to_node] == gray:
                cycle_start = path.index(edge.to_node)
                cycle = path[cycle_start:] + [edge.to_node]
                cycles.append(cycle)
            elif color[edge.to_node] == white:
                dfs(edge.to_node, path)
        path.pop()
        color[node_id] = black

    for node_id in graph.nodes:
        if color[node_id] == white:
            dfs(node_id, [])

    return cycles


def get_parallel_levels(graph: PipelineGraph) -> list[list[str]]:
    """Group nodes into parallel-executable levels (waves).

    Nodes in the same level have no dependencies among them and can be
    executed in parallel. Level 0 contains all source nodes (in-degree 0).
    Level k contains nodes whose predecessors are all in levels < k.

    Args:
        graph: PipelineGraph instance.

    Returns:
        List of levels, each level is a list of node IDs.

    Raises:
        DAGCycleError: If the graph contains a cycle.
    """
    levels: list[list[str]] = []
    remaining = set(graph.nodes.keys())
    processed: set[str] = set()

    while remaining:
        current_level = [nid for nid in remaining if all(pred in processed for pred in _get_predecessors(graph, nid))]
        if not current_level:
            raise DAGCycleError(f"Cannot compute parallel levels: cycle detected among {sorted(remaining)}")
        levels.append(current_level)
        processed.update(current_level)
        remaining -= set(current_level)

    return levels


def get_reachable_nodes(graph: PipelineGraph, start_id: str) -> set[str]:
    """Get all nodes reachable from start_id via BFS.

    Args:
        graph: PipelineGraph instance.
        start_id: Starting node ID.

    Returns:
        Set of reachable node IDs (including start_id if it exists).
    """
    if start_id not in graph.nodes:
        return set()
    visited: set[str] = set()
    queue: list[str] = [start_id]
    while queue:
        node_id = queue.pop(0)
        if node_id in visited:
            continue
        visited.add(node_id)
        for edge in graph.edges.get(node_id, []):
            if edge.to_node not in visited:
                queue.append(edge.to_node)
    return visited


def get_critical_path(
    graph: PipelineGraph,
    node_costs: dict[str, float] | None = None,
) -> tuple[list[str], float]:
    """Compute the critical path (longest path) in the DAG.

    Args:
        graph: PipelineGraph instance.
        node_costs: Optional dict mapping node_id to execution cost.
            Defaults to 1.0 for each node.

    Returns:
        Tuple of (critical_path_node_ids, total_cost).

    Raises:
        DAGCycleError: If the graph contains a cycle.
    """
    if node_costs is None:
        node_costs = dict.fromkeys(graph.nodes, 1.0)

    topo_order = topological_sort(graph)
    dist: dict[str, float] = {}
    pred: dict[str, str | None] = {}

    for node_id in topo_order:
        dist[node_id] = node_costs.get(node_id, 1.0)
        pred[node_id] = None
        for p in _get_predecessors(graph, node_id):
            if p in dist:
                candidate = dist[p] + node_costs.get(node_id, 1.0)
                if candidate > dist[node_id]:
                    dist[node_id] = candidate
                    pred[node_id] = p

    if not dist:
        return [], 0.0
    end_node = max(dist, key=dist.get)
    total_cost = dist[end_node]

    path: list[str] = []
    current: str | None = end_node
    while current is not None:
        path.append(current)
        current = pred[current]
    path.reverse()

    return path, total_cost


def validate_dag(graph: PipelineGraph) -> list[str]:
    """Validate that the graph is a proper DAG.

    Returns:
        List of validation error messages (empty if valid).
    """
    errors: list[str] = []

    cycles = detect_cycles(graph)
    if cycles:
        for cycle in cycles:
            errors.append(f"Cycle detected: {' -> '.join(cycle)}")

    if graph.entry_node and graph.entry_node not in graph.nodes:
        errors.append(f"Entry node '{graph.entry_node}' does not exist in nodes")

    for from_node, edge_list in graph.edges.items():
        if from_node not in graph.nodes:
            errors.append(f"Edge source '{from_node}' is not a valid node")
        for edge in edge_list:
            if edge.to_node not in graph.nodes:
                errors.append(f"Edge target '{edge.to_node}' is not a valid node")

    return errors


def build_subgraph(graph: PipelineGraph, start_id: str) -> PipelineGraph:
    """Build a subgraph containing only nodes reachable from start_id.

    Args:
        graph: Source PipelineGraph.
        start_id: Entry node for the subgraph.

    Returns:
        A new PipelineGraph containing only reachable nodes and edges.
    """
    reachable = get_reachable_nodes(graph, start_id)
    sub_nodes = {nid: graph.nodes[nid] for nid in reachable if nid in graph.nodes}
    sub_edges = {f: [e for e in elist if e.to_node in reachable] for f, elist in graph.edges.items() if f in reachable}
    return PipelineGraph(
        nodes=sub_nodes,
        edges=sub_edges,
        entry_node=start_id,
    )


# ── Parallel execution ────────────────────────────────────────────────


@dataclass
class ParallelExecutionResult:
    """Result of parallel DAG execution.

    Attributes:
        success: Whether all nodes succeeded.
        state: Final pipeline state.
        node_results: Dict mapping node_id to AutoResult.
        elapsed_time: Total elapsed time in seconds.
        failed_nodes: List of node IDs that failed.
    """

    success: bool
    state: PipelineState
    node_results: dict[str, AutoResult] = field(default_factory=dict)
    elapsed_time: float = 0.0
    failed_nodes: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.success


class ParallelExecutor:
    """Parallel DAG executor using ThreadPoolExecutor.

    Executes nodes in topological waves: all nodes in the same level run
    in parallel, and the next level starts only after all nodes in the
    current level complete. This provides automatic branch merge
    synchronization — any node with in-degree > 1 waits for all
    predecessors (a merge point).

    Supports:
    - pause/resume/cancel
    - continue_on_error per node (config flag)
    - callbacks for step completion and error
    """

    def __init__(self, max_workers: int = 4):
        """Initialize the parallel executor.

        Args:
            max_workers: Maximum number of parallel worker threads.
        """
        self._max_workers = max_workers
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        self._state: PipelineState = PipelineState.PENDING
        self._on_step_complete: Callable[[str, AutoResult], None] | None = None
        self._on_error: Callable[[str, Exception], None] | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> PipelineState:
        """Current executor state."""
        return self._state

    def set_callbacks(
        self,
        on_step_complete: Callable[[str, AutoResult], None] | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        """Set step completion and error callbacks."""
        self._on_step_complete = on_step_complete
        self._on_error = on_error

    def cancel(self) -> None:
        """Request cancellation. Completes current atomic operations then stops."""
        self._cancel_event.set()

    def pause(self) -> None:
        """Request pause. Stops before next level."""
        self._pause_event.set()

    def resume(self) -> None:
        """Clear pause request."""
        self._pause_event.clear()

    def execute(
        self,
        graph: PipelineGraph,
        context: PipelineContext,
        entry_node: str | None = None,
    ) -> ParallelExecutionResult:
        """Execute the DAG in parallel waves.

        Args:
            graph: PipelineGraph to execute.
            context: Pipeline execution context.
            entry_node: Optional entry node (defaults to graph.entry_node).

        Returns:
            ParallelExecutionResult with per-node results.
        """
        self._cancel_event.clear()
        self._pause_event.clear()
        self._state = PipelineState.RUNNING

        start_time = time.monotonic()
        node_results: dict[str, AutoResult] = {}
        failed_nodes: list[str] = []

        # Validate DAG
        errors = validate_dag(graph)
        if errors:
            self._state = PipelineState.FAILED
            logger.error("DAG validation failed: %s", "; ".join(errors))
            return ParallelExecutionResult(
                success=False,
                state=PipelineState.FAILED,
                node_results=node_results,
                elapsed_time=time.monotonic() - start_time,
                failed_nodes=failed_nodes,
            )

        start = entry_node or graph.entry_node
        if not start:
            self._state = PipelineState.FAILED
            return ParallelExecutionResult(
                success=False,
                state=PipelineState.FAILED,
                node_results=node_results,
                elapsed_time=time.monotonic() - start_time,
                failed_nodes=failed_nodes,
            )

        # Build subgraph of reachable nodes from entry
        try:
            sub_graph = build_subgraph(graph, start)
            levels = get_parallel_levels(sub_graph)
        except DAGCycleError as exc:
            self._state = PipelineState.FAILED
            logger.error("DAG cycle error: %s", exc)
            return ParallelExecutionResult(
                success=False,
                state=PipelineState.FAILED,
                node_results=node_results,
                elapsed_time=time.monotonic() - start_time,
                failed_nodes=failed_nodes,
            )

        try:
            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                for level_nodes in levels:
                    if self._cancel_event.is_set():
                        self._state = PipelineState.CANCELLED
                        break

                    # Handle pause
                    while self._pause_event.is_set():
                        if self._cancel_event.is_set():
                            break
                        self._state = PipelineState.PAUSED
                        time.sleep(0.1)
                    if self._cancel_event.is_set():
                        self._state = PipelineState.CANCELLED
                        break
                    self._state = PipelineState.RUNNING

                    level_failed = self._execute_level(
                        executor,
                        graph,
                        context,
                        level_nodes,
                        node_results,
                        failed_nodes,
                    )
                    if level_failed:
                        self._state = PipelineState.FAILED
                        break

            elapsed = time.monotonic() - start_time
            if self._state == PipelineState.CANCELLED:
                return ParallelExecutionResult(
                    success=False,
                    state=PipelineState.CANCELLED,
                    node_results=node_results,
                    elapsed_time=elapsed,
                    failed_nodes=failed_nodes,
                )
            if self._state == PipelineState.FAILED:
                return ParallelExecutionResult(
                    success=False,
                    state=PipelineState.FAILED,
                    node_results=node_results,
                    elapsed_time=elapsed,
                    failed_nodes=failed_nodes,
                )

            self._state = PipelineState.COMPLETED
            return ParallelExecutionResult(
                success=len(failed_nodes) == 0,
                state=PipelineState.COMPLETED,
                node_results=node_results,
                elapsed_time=elapsed,
                failed_nodes=failed_nodes,
            )
        except Exception as exc:
            self._state = PipelineState.FAILED
            logger.error("ParallelExecutor unexpected error: %s", exc)
            return ParallelExecutionResult(
                success=False,
                state=PipelineState.FAILED,
                node_results=node_results,
                elapsed_time=time.monotonic() - start_time,
                failed_nodes=failed_nodes,
            )

    def _execute_level(
        self,
        executor: ThreadPoolExecutor,
        graph: PipelineGraph,
        context: PipelineContext,
        level_nodes: list[str],
        node_results: dict[str, AutoResult],
        failed_nodes: list[str],
    ) -> bool:
        """Execute all nodes in a single level in parallel.

        Returns:
            True if a non-recoverable failure occurred (should stop execution).
        """
        futures: dict[Future, str] = {}
        for node_id in level_nodes:
            node = graph.nodes.get(node_id)
            if node is None:
                continue
            future = executor.submit(self._execute_node, node, context)
            futures[future] = node_id

        level_should_stop = False
        for future in as_completed(futures):
            node_id = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = fail_result(error_msg=str(exc))
                if self._on_error:
                    self._on_error(node_id, exc)

            with self._lock:
                node_results[node_id] = result
                if not result.success:
                    failed_nodes.append(node_id)

            if self._on_step_complete:
                self._on_step_complete(node_id, result)

            if not result.success:
                node = graph.nodes.get(node_id)
                if node and not node.config.get("continue_on_error", False):
                    level_should_stop = True

        if level_should_stop:
            # Cancel any not-yet-started futures in this level
            for f in futures:
                f.cancel()

        return level_should_stop

    def _execute_node(self, node: PipelineNode, context: PipelineContext) -> AutoResult:
        """Execute a single node (called in worker thread)."""
        try:
            return node.execute(context)
        except Exception as exc:
            logger.error("Node %s execution failed: %s", node.id, exc)
            return fail_result(error_msg=str(exc))


# ── DAG Executor (high-level with branch merge) ───────────────────────


class DAGExecutor:
    """High-level DAG executor with branch merge synchronization.

    Combines topological analysis with parallel execution. Branch merge
    points (nodes with in-degree > 1) are automatically synchronized via
    wave barriers in ParallelExecutor.

    This executor complements PipelineEngine (linear) for DAG-structured
    pipelines that benefit from parallel execution of independent branches.
    """

    def __init__(self, max_workers: int = 4, max_iterations: int = 10000):
        """Initialize the DAG executor.

        Args:
            max_workers: Maximum number of parallel worker threads.
            max_iterations: Safety limit for iterative execution (reserved).
        """
        self._parallel_executor = ParallelExecutor(max_workers=max_workers)
        self._max_iterations = max_iterations
        self._graph: PipelineGraph | None = None
        self._context: PipelineContext | None = None
        self._state: PipelineState = PipelineState.PENDING

    @property
    def state(self) -> PipelineState:
        """Current executor state."""
        return self._state

    @property
    def context(self) -> PipelineContext | None:
        """Current execution context."""
        return self._context

    def set_callbacks(
        self,
        on_step_complete: Callable[[str, AutoResult], None] | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        """Set step completion and error callbacks."""
        self._parallel_executor.set_callbacks(on_step_complete, on_error)

    def cancel(self) -> None:
        """Request cancellation."""
        self._parallel_executor.cancel()

    def pause(self) -> None:
        """Request pause."""
        self._parallel_executor.pause()

    def resume(self) -> None:
        """Clear pause request."""
        self._parallel_executor.resume()

    def load(self, pipeline_json: dict, device: Any = None) -> None:
        """Load Pipeline JSON configuration.

        Args:
            pipeline_json: Pipeline configuration dict.
            device: Optional device instance to inject into PipelineContext.
        """
        from engine.parser import PipelineParser

        self._graph = PipelineParser.parse_dict(pipeline_json)
        self._context = PipelineContext(
            device=device,
            pipeline_snapshot=pipeline_json,
        )
        self._state = PipelineState.PENDING
        logger.info(
            "DAGExecutor loaded: entry=%s, nodes=%d",
            self._graph.entry_node,
            len(self._graph.nodes),
        )

    def execute(self) -> ParallelExecutionResult:
        """Execute the loaded DAG.

        Returns:
            ParallelExecutionResult with per-node results.

        Raises:
            RuntimeError: If no pipeline has been loaded.
        """
        if self._graph is None:
            raise RuntimeError("Pipeline 未加载，请先调用 load()")
        if self._context is None:
            self._context = PipelineContext()

        result = self._parallel_executor.execute(self._graph, self._context, self._graph.entry_node)
        self._state = result.state
        return result
