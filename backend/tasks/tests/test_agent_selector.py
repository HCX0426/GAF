"""Unit tests for AgentSelector (spec-40 Phase 1 / TD-288).

Covers:
- get_required_capabilities: steps + nodes formats, cap_key matching, empty fallback
- _agent_matches_capabilities: dict caps, list caps, partial match (False), full match (True)
- filter_by_capability: multi agent, 1 throws exception (skipped), order preserved
- select_by_load: all idle (most recent heartbeat wins), all busy (lowest cpu wins), empty list (None)
- select: end-to-end filter + load
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from tasks.agent_selector import (
    CAPABILITY_MAP,
    AgentSelector,
    _agent_matches_capabilities,
    _get_required_capabilities,
)


@dataclass
class FakeAgent:
    """Minimal mock for AgentSelector — no Django model needed."""
    agent_id: str = "test-1"
    status: str = "idle"
    capabilities: Any = None
    last_heartbeat: datetime.datetime | None = None
    cpu_usage: float = 0.0
    memory_usage: float = 0.0


# ── get_required_capabilities ───────────────────────────────────

class TestGetRequiredCapabilities:
    def test_steps_with_adb_action(self):
        task_def = {"steps": [{"action": "adb_shell", "type": ""}]}
        result = _get_required_capabilities(task_def)
        assert "adb" in result

    def test_steps_with_windows_action(self):
        task_def = {"steps": [{"action": "click", "type": "win32"}]}
        result = _get_required_capabilities(task_def)
        assert "windows" in result

    def test_nodes_with_ocr_type(self):
        task_def = {"nodes": [{"type": "ocr", "action": ""}]}
        result = _get_required_capabilities(task_def)
        assert "ocr" in result

    def test_nodes_with_image_match_type(self):
        task_def = {"nodes": [{"type": "template_match", "action": ""}]}
        result = _get_required_capabilities(task_def)
        assert "image_match" in result

    def test_nodes_with_canonical_node_type_field(self):
        # spec-2026-07-27-execution-path-unification: pipeline canonical
        # schema uses "node_type" (not legacy "type"/"action"). Verify
        # the canonical field is recognized.
        task_def = {"nodes": [{"node_type": "ocr"}]}
        result = _get_required_capabilities(task_def)
        assert "ocr" in result

    def test_node_type_takes_precedence_over_type(self):
        # spec-2026-07-27: node_type 优先于 legacy type 字段。
        task_def = {"nodes": [{"node_type": "ocr", "type": "click"}]}
        result = _get_required_capabilities(task_def)
        assert "ocr" in result
        assert "windows" not in result  # "click" 不映射到 windows

    def test_empty_task_definition_falls_back_to_adb(self):
        # No steps, no nodes → fallback {"adb"}
        result = _get_required_capabilities({})
        assert result == {"adb"}

    def test_both_steps_and_nodes_merged(self):
        task_def = {
            "steps": [{"action": "adb_shell", "type": ""}],
            "nodes": [{"type": "ocr", "action": ""}],
        }
        result = _get_required_capabilities(task_def)
        assert "adb" in result
        assert "ocr" in result

    def test_unknown_action_falls_back_to_adb(self):
        task_def = {"steps": [{"action": "unknown_action", "type": "unknown_type"}]}
        result = _get_required_capabilities(task_def)
        assert result == {"adb"}

    def test_selector_method_delegates(self):
        selector = AgentSelector()
        task_def = {"steps": [{"action": "click", "type": "win32"}]}
        result = selector.get_required_capabilities(task_def)
        assert "windows" in result


# ── _agent_matches_capabilities ──────────────────────────────────

class TestAgentMatchesCapabilities:
    def test_dict_caps_all_true(self):
        agent = FakeAgent(capabilities={"adb": True, "windows": True})
        assert _agent_matches_capabilities(agent, {"adb", "windows"}) is True

    def test_dict_caps_partial_match(self):
        agent = FakeAgent(capabilities={"adb": True, "windows": False})
        assert _agent_matches_capabilities(agent, {"adb", "windows"}) is False

    def test_dict_caps_string_true(self):
        agent = FakeAgent(capabilities={"adb": "true", "windows": "1"})
        assert _agent_matches_capabilities(agent, {"adb", "windows"}) is True

    def test_list_caps(self):
        agent = FakeAgent(capabilities=["adb", "windows"])
        assert _agent_matches_capabilities(agent, {"adb", "windows"}) is True

    def test_list_caps_partial(self):
        agent = FakeAgent(capabilities=["adb"])
        assert _agent_matches_capabilities(agent, {"adb", "windows"}) is False

    def test_capability_map_fuzzy_match(self):
        # "win32" in agent caps should satisfy "windows" required cap via CAPABILITY_MAP
        agent = FakeAgent(capabilities=["win32"])
        assert _agent_matches_capabilities(agent, {"windows"}) is True

    def test_empty_required_capabilities(self):
        agent = FakeAgent(capabilities={"adb": True})
        # Empty required set → all() of empty = True
        assert _agent_matches_capabilities(agent, set()) is True

    def test_none_capabilities(self):
        agent = FakeAgent(capabilities=None)
        # capabilities=None → agent_caps = {} → no match
        assert _agent_matches_capabilities(agent, {"adb"}) is False


# ── filter_by_capability ─────────────────────────────────────────

class TestFilterByCapability:
    def test_empty_agents(self):
        selector = AgentSelector()
        assert selector.filter_by_capability([], {"adb"}) == []

    def test_all_match(self):
        selector = AgentSelector()
        a1 = FakeAgent(agent_id="1", capabilities={"adb": True})
        a2 = FakeAgent(agent_id="2", capabilities={"adb": True})
        result = selector.filter_by_capability([a1, a2], {"adb"})
        assert len(result) == 2

    def test_partial_match(self):
        selector = AgentSelector()
        a1 = FakeAgent(agent_id="1", capabilities={"adb": True})
        a2 = FakeAgent(agent_id="2", capabilities={"windows": True})
        result = selector.filter_by_capability([a1, a2], {"adb"})
        assert len(result) == 1
        assert result[0].agent_id == "1"

    def test_order_preserved(self):
        selector = AgentSelector()
        a1 = FakeAgent(agent_id="first", capabilities={"adb": True})
        a2 = FakeAgent(agent_id="second", capabilities={"adb": True})
        a3 = FakeAgent(agent_id="third", capabilities={"adb": True})
        result = selector.filter_by_capability([a1, a2, a3], {"adb"})
        assert [a.agent_id for a in result] == ["first", "second", "third"]

    def test_agent_throws_exception_is_skipped(self):
        selector = AgentSelector()

        class BrokenAgent:
            agent_id = "broken"
            @property
            def capabilities(self):
                raise RuntimeError("simulated attribute error")

        good = FakeAgent(agent_id="good", capabilities={"adb": True})
        result = selector.filter_by_capability([BrokenAgent(), good], {"adb"})
        assert len(result) == 1
        assert result[0].agent_id == "good"


# ── select_by_load ───────────────────────────────────────────────

class TestSelectByLoad:
    def test_empty_list_returns_none(self):
        selector = AgentSelector()
        assert selector.select_by_load([]) is None

    def test_single_idle_agent(self):
        selector = AgentSelector()
        a = FakeAgent(status="idle")
        assert selector.select_by_load([a]) is a

    def test_multiple_idle_picks_most_recent_heartbeat(self):
        selector = AgentSelector()
        old = FakeAgent(
            agent_id="old",
            status="idle",
            last_heartbeat=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        )
        new = FakeAgent(
            agent_id="new",
            status="idle",
            last_heartbeat=datetime.datetime(2026, 7, 20, tzinfo=datetime.UTC),
        )
        result = selector.select_by_load([old, new])
        assert result is new

    def test_busy_agents_pick_lowest_cpu(self):
        selector = AgentSelector()
        a1 = FakeAgent(agent_id="high", status="busy", cpu_usage=80.0, memory_usage=50.0)
        a2 = FakeAgent(agent_id="low", status="busy", cpu_usage=20.0, memory_usage=90.0)
        result = selector.select_by_load([a1, a2])
        assert result is a2

    def test_busy_agents_cpu_tie_picks_lowest_memory(self):
        selector = AgentSelector()
        a1 = FakeAgent(agent_id="high-mem", status="busy", cpu_usage=50.0, memory_usage=80.0)
        a2 = FakeAgent(agent_id="low-mem", status="busy", cpu_usage=50.0, memory_usage=20.0)
        result = selector.select_by_load([a1, a2])
        assert result is a2

    def test_idle_preferred_over_busy(self):
        selector = AgentSelector()
        busy = FakeAgent(agent_id="busy", status="busy", cpu_usage=1.0, memory_usage=1.0)
        idle = FakeAgent(agent_id="idle", status="idle", last_heartbeat=datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC))
        result = selector.select_by_load([busy, idle])
        assert result is idle

    def test_none_heartbeat_treated_as_oldest(self):
        selector = AgentSelector()
        a1 = FakeAgent(agent_id="none-hb", status="idle", last_heartbeat=None)
        a2 = FakeAgent(
            agent_id="has-hb",
            status="idle",
            last_heartbeat=datetime.datetime(2026, 7, 20, tzinfo=datetime.UTC),
        )
        result = selector.select_by_load([a1, a2])
        assert result is a2

    def test_status_case_insensitive(self):
        selector = AgentSelector()
        a = FakeAgent(status="IDLE")
        # _agent_status lowercases — should be treated as "idle"
        result = selector.select_by_load([a])
        assert result is a


# ── select (end-to-end) ──────────────────────────────────────────

class TestSelect:
    def test_no_matching_agent_returns_none(self):
        selector = AgentSelector()
        a = FakeAgent(capabilities={"windows": True})
        result = selector.select([a], {"adb"})
        assert result is None

    def test_matching_idle_agent_selected(self):
        selector = AgentSelector()
        a = FakeAgent(
            agent_id="match",
            status="idle",
            capabilities={"adb": True},
            last_heartbeat=datetime.datetime(2026, 7, 20, tzinfo=datetime.UTC),
        )
        result = selector.select([a], {"adb"})
        assert result is a

    def test_picks_idle_over_busy_when_both_match(self):
        selector = AgentSelector()
        busy = FakeAgent(
            agent_id="busy",
            status="busy",
            capabilities={"adb": True},
            cpu_usage=1.0,
            memory_usage=1.0,
        )
        idle = FakeAgent(
            agent_id="idle",
            status="idle",
            capabilities={"adb": True},
            last_heartbeat=datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC),
        )
        result = selector.select([busy, idle], {"adb"})
        assert result is idle


# ── CAPABILITY_MAP sanity ────────────────────────────────────────

class TestCapabilityMap:
    def test_capability_map_has_4_keys(self):
        assert set(CAPABILITY_MAP.keys()) == {"adb", "windows", "ocr", "image_match"}

    def test_capability_map_values_are_lists(self):
        for v in CAPABILITY_MAP.values():
            assert isinstance(v, list)
            assert len(v) > 0
