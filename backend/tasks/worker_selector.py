"""Agent selection: filter agents by capability and select by load.

✅ Status: helper class with unit tests (spec-40). ``dispatch_task`` in
``tasks/tasks.py`` is the primary consumer. ``WorkerSelector``
owns the capability + load selection logic directly (no delegation to tasks.py).

Two-step selection
------------------
1. ``filter_by_capability(agents, required_capabilities)`` — returns the
   subset of agents whose declared capabilities satisfy the task's
   requirements.
2. ``select_by_load(matched_agents)`` — picks the best agent from a list
   of capability-matched agents using load metrics:
   - Idle agents always preferred over busy/online agents.
   - Among idle agents: pick the one with the most recent heartbeat
     (freshest state).
   - Among non-idle agents: pick the lowest ``cpu_usage`` (with
     ``memory_usage`` as a tiebreaker), to spread load evenly.

The convenience method ``select(agents, required_capabilities)`` runs
both steps in sequence and returns a single Agent (or None).

Usage
-----
::

    from tasks.worker_selector import WorkerSelector

    selector = WorkerSelector()
    matched = selector.filter_by_capability(available_agents, {"adb", "ocr"})
    agent = selector.select_by_load(matched)
    if agent is None:
        # No matching agent — fail the execution.
        ...
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)


# Capability keyword map — single source of truth for capability inference.
# Keys are canonical capability tags; values are keyword lists that, when
# found in a task step's ``action`` or ``type`` field, indicate the task
# requires that capability. Same map backs ``_get_required_capabilities``
# (task → required caps) and ``_agent_matches_capabilities`` (agent caps →
# satisfied? via fuzzy match).
CAPABILITY_MAP = {
    "adb": ["adb", "android", "device_control"],
    "windows": ["win32", "windows", "window_control", "pywinauto", "click", "key_press", "screenshot", "wait"],
    "ocr": ["ocr", "rapidocr", "paddleocr", "tesseract"],
    "image_match": ["image_match", "template_match", "cv2"],
}


def _get_required_capabilities(task_definition: Any) -> set[str]:
    """Extract required capability tags from a task definition.

    Infers required capabilities from the action types used in the task
    steps:
    - adb-related actions → adb capability
    - window actions → windows capability
    - OCR actions → ocr capability
    - image match actions → image_match capability

    Args:
        task_definition: task_definition JSON field of a Task.

    Returns:
        Set of required capability tags.
    """
    required: set[str] = set()
    # BD2-AUTO / legacy chain style: task_definition.steps[] with {action, type}
    # GAF Pipeline style (canonical): task_definition.nodes[] with {node_type, config}
    # PipelineParser 也接受 type/action 作为 node_type 别名, 这里同步处理.
    steps = task_definition.get("steps", [])
    nodes = task_definition.get("nodes", [])
    # Merge both formats into a single iterable of {type, action, node_type} dicts
    unified = list(steps) + list(nodes)

    for step in unified:
        action = step.get("action", "").lower()
        # spec-2026-07-27-execution-path-unification: 优先 node_type (pipeline
        # canonical), 退回到 type (legacy/BD2-AUTO).
        step_type = (
            step.get("node_type") or step.get("type") or ""
        ).lower()

        for cap_key, keywords in CAPABILITY_MAP.items():
            if any(kw in action for kw in keywords) or any(kw in step_type for kw in keywords):
                required.add(cap_key)

    if not required:
        required.add("adb")

    return required


def _agent_matches_capabilities(agent: Any, required_capabilities: set[str]) -> bool:
    """Check whether an agent's capabilities satisfy the task requirements.

    Args:
        agent: Agent model instance (or any object with a ``capabilities``
            attribute).
        required_capabilities: set of required capability tags.

    Returns:
        True if the agent has all required capabilities, False otherwise.
    """
    agent_caps = agent.capabilities or {}
    agent_cap_set: set[str] = set()

    if isinstance(agent_caps, dict):
        for key, value in agent_caps.items():
            if value is True or value == "true" or value == "1":
                agent_cap_set.add(key.lower())
    elif isinstance(agent_caps, list):
        agent_cap_set = {str(c).lower() for c in agent_caps}

    for req_cap in required_capabilities:
        cap_keywords = CAPABILITY_MAP.get(req_cap, [req_cap])
        if not any(kw in agent_cap_set for kw in cap_keywords):
            return False

    return True


class WorkerSelector:
    """Select agents by capability + load.

    Owns capability filtering and load-based selection. The capability
    helpers (``_get_required_capabilities`` / ``_agent_matches_capabilities``)
    live in this module as the single source of truth.

    The constructor accepts no arguments — the selector is stateless and
    safe to instantiate per-request or as a module-level singleton.
    """

    def __init__(self):
        # Stateless selector — capability helpers are module-level
        # functions in this same module, so no lazy import is needed.
        # Listing them as instance attrs keeps the public method bodies
        # stable and makes them trivial to monkeypatch in unit tests.
        self._matches_capabilities = _agent_matches_capabilities
        self._get_required_capabilities = _get_required_capabilities

    # ── Public API ──────────────────────────────────────────────
    def get_required_capabilities(self, task_definition: Any) -> set[str]:
        """Extract required capability tags from a task definition."""
        return self._get_required_capabilities(task_definition)

    def filter_by_capability(
        self,
        agents: Iterable[Any],
        required_capabilities: set[str],
    ) -> list[Any]:
        """Return agents whose capabilities satisfy ``required_capabilities``.

        Args:
            agents: Iterable of Agent model instances (or any object with
                a ``capabilities`` attribute).
            required_capabilities: Set of capability tags (e.g. {"adb", "ocr"}).

        Returns:
            List of matching agents (preserves input order). Empty list if
            no agent matches.
        """
        matched: list[Any] = []
        for agent in agents:
            try:
                if self._matches_capabilities(agent, required_capabilities):
                    matched.append(agent)
            except Exception as exc:
                # Defensive: a single bad agent shouldn't fail the whole
                # selection. Log and skip.
                agent_id = getattr(agent, "agent_id", "<unknown>")
                logger.warning(
                    "WorkerSelector.filter_by_capability: agent %r check failed: %s",
                    agent_id, exc,
                )
        return matched

    def select_by_load(self, agents: list[Any]) -> Any | None:
        """Pick the best agent from a list of capability-matched agents.

        Selection order:
        1. Idle agents preferred over non-idle.
        2. Among idle agents: most recent ``last_heartbeat`` wins.
        3. Among non-idle agents: lowest ``cpu_usage`` wins, with
           ``memory_usage`` as tiebreaker.

        Args:
            agents: List of agents (typically the output of
                ``filter_by_capability``).

        Returns:
            Best agent, or None if the list is empty.
        """
        if not agents:
            return None

        idle = [a for a in agents if self._agent_status(a) == "idle"]
        if idle:
            # Among idle agents, pick the one with the most recent heartbeat
            # (freshest state = most likely to actually be ready).
            return max(idle, key=self._heartbeat_key)

        # All agents are busy/online — pick the least-loaded.
        return min(agents, key=self._load_key)

    def select(
        self,
        agents: Iterable[Any],
        required_capabilities: set[str],
    ) -> Any | None:
        """Convenience: filter by capability + select by load in one call.

        Args:
            agents: Iterable of Agent model instances.
            required_capabilities: Set of capability tags.

        Returns:
            Best matching agent, or None if no agent matches.
        """
        matched = self.filter_by_capability(agents, required_capabilities)
        return self.select_by_load(matched)

    # ── Internal helpers ───────────────────────────────────────
    @staticmethod
    def _agent_status(agent: Any) -> str:
        """Read agent.status as lowercase string (defensive against None)."""
        status = getattr(agent, "status", None)
        if status is None:
            return ""
        # Agent.Status enum (Django choices) — coerce to str then lowercase.
        return str(status).lower()

    @staticmethod
    def _heartbeat_key(agent: Any) -> float:
        """Sort key: most recent heartbeat wins (larger = more recent).

        Returns a float so min/max work even when last_heartbeat is None
        or a datetime. Falls back to 0.0 (oldest) on any error.
        """
        hb = getattr(agent, "last_heartbeat", None)
        if hb is None:
            return 0.0
        try:
            # Django DateTimeField → datetime; convert to POSIX timestamp.
            import datetime
            if isinstance(hb, datetime.datetime):
                return hb.timestamp()
            return float(hb)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _load_key(agent: Any) -> tuple:
        """Sort key: lowest cpu_usage wins, memory_usage as tiebreaker.

        Returns a tuple (cpu_usage, memory_usage) so min() picks the
        least-loaded agent. Falls back to (float('inf'), float('inf'))
        on any error — i.e. agents with unknown load sort last.
        """
        try:
            cpu = float(getattr(agent, "cpu_usage", 0.0) or 0.0)
        except (TypeError, ValueError):
            cpu = float("inf")
        try:
            mem = float(getattr(agent, "memory_usage", 0.0) or 0.0)
        except (TypeError, ValueError):
            mem = float("inf")
        return (cpu, mem)
