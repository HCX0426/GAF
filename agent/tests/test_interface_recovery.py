"""InterfaceRecovery 模块测试 (spec 阶段 3 — 任务 3.3).

Covers:
  - find_path with exclude_edges (换路径策略)
  - recover() with attempt + exclude_edges (第二次走替代路径)
  - infer_expected_state (3 级优先级)
  - Backward compat: find_path() / recover() 不传新参数时行为不变
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure src on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.interface_recovery import (
    InterfaceRecoveryManager,
    RecoveryOutcome,
)

pytestmark = pytest.mark.unit

# ============================================================
# YAML fixtures
# ============================================================

YAML_DIAMOND = textwrap.dedent("""
    states:
      A: {description: state A, is_safe_state: true}
      B: {description: state B}
      C: {description: state C}
      D: {description: state D, is_safe_state: true}
    transitions:
      - {from: A, to: B, action: {type: click, template: a_to_b.png}}
      - {from: A, to: C, action: {type: click, template: a_to_c.png}}
      - {from: B, to: D, action: {type: click, template: b_to_d.png}}
      - {from: C, to: D, action: {type: click, template: c_to_d.png}}
""")


@pytest.fixture
def yaml_file(tmp_path):
    """Write the diamond YAML to a temp file and return its path."""
    p = tmp_path / "interface_states.yaml"
    p.write_text(YAML_DIAMOND, encoding="utf-8")
    return str(p)


@pytest.fixture
def recovery_manager(yaml_file):
    """Build InterfaceRecoveryManager with mock deps."""
    return InterfaceRecoveryManager(
        states_config_path=yaml_file,
        screenshot_fn=MagicMock(return_value=None),
        template_match_fn=MagicMock(return_value=None),
        action_executor_fn=MagicMock(return_value=True),
        popup_handler=None,
        archive_dir=str(Path(yaml_file).parent / "unknown_states"),
        max_recovery_steps=5,
    )


# ============================================================
# find_path — exclude_edges (换路径策略)
# ============================================================

class TestFindPathExcludeEdges:
    """find_path 支持 exclude_edges 跳过指定边."""

    def test_default_returns_shortest_path(self, recovery_manager):
        """无 exclude_edges 时返回 BFS 最短路径."""
        path = recovery_manager.find_path("A", "D")
        # Diamond: A->B->D or A->C->D, both length 3
        assert path is not None
        assert len(path) == 3
        assert path[0] == "A"
        assert path[-1] == "D"

    def test_exclude_first_shortest_returns_alternative(self, recovery_manager):
        """排除第一条最短路径的边后, BFS 返回替代路径."""
        # First call: get the default shortest path
        first_path = recovery_manager.find_path("A", "D")
        assert first_path is not None
        # Convert to edges
        exclude_edges = list(zip(first_path[:-1], first_path[1:], strict=True))
        # e.g. [("A","B"), ("B","D")] if first path was A->B->D

        # Second call with exclude_edges — must return the OTHER path
        second_path = recovery_manager.find_path("A", "D", exclude_edges=exclude_edges)
        assert second_path is not None
        assert len(second_path) == 3
        assert second_path[0] == "A"
        assert second_path[-1] == "D"
        # The two paths must differ (different intermediate)
        assert second_path[1] != first_path[1]

    def test_exclude_all_paths_returns_none(self, recovery_manager):
        """排除所有可能路径的边后返回 None."""
        # Exclude both A->B and A->C, no path remains
        result = recovery_manager.find_path(
            "A", "D",
            exclude_edges=[("A", "B"), ("A", "C")],
        )
        assert result is None

    def test_exclude_nonexistent_edge_no_effect(self, recovery_manager):
        """排除不存在的边不影响结果."""
        path1 = recovery_manager.find_path("A", "D")
        path2 = recovery_manager.find_path(
            "A", "D",
            exclude_edges=[("X", "Y")],  # not in graph
        )
        assert path1 == path2

    def test_exclude_empty_list_no_effect(self, recovery_manager):
        """空 exclude_edges 列表等同于 None."""
        path1 = recovery_manager.find_path("A", "D")
        path2 = recovery_manager.find_path("A", "D", exclude_edges=[])
        assert path1 == path2

    def test_exclude_none_default_no_effect(self, recovery_manager):
        """exclude_edges=None 等同于不传 (向后兼容)."""
        path1 = recovery_manager.find_path("A", "D")
        path2 = recovery_manager.find_path("A", "D", exclude_edges=None)
        assert path1 == path2


# ============================================================
# recover — attempt + exclude_edges
# ============================================================

class TestRecoverAttemptWithExcludeEdges:
    """recover() 接受 attempt + exclude_edges 参数."""

    def test_recover_accepts_attempt_parameter(self, recovery_manager):
        """recover() 必须接受 attempt 参数 (默认 0)."""
        # Just verify the signature doesn't raise
        # We'll mock screenshot_fn to return None so identify fails fast
        recovery_manager._screenshot_fn = MagicMock(return_value=None)
        result = recovery_manager.recover(
            expected_state="D",
            pipeline_name="test",
            node_id="step_1",
            node_config={},
            execution_context={},
            attempt=0,
        )
        # With no screenshot → identify_state returns (None, 0.0) → archive
        assert result.outcome == RecoveryOutcome.NEEDS_HUMAN

    def test_recover_accepts_exclude_edges_parameter(self, recovery_manager):
        """recover() 必须接受 exclude_edges 参数."""
        # Make template_match_fn return a match for state A so identification succeeds
        recovery_manager._screenshot_fn = MagicMock(return_value=b"screen")
        recovery_manager._template_match_fn = MagicMock(
            return_value={"confidence": 0.9},
        )
        # Force action_executor to fail so RECOVERY_FAILED
        recovery_manager._action_executor_fn = MagicMock(return_value=False)

        # First call without exclude_edges
        result1 = recovery_manager.recover(
            expected_state="D",
            pipeline_name="test",
            node_id="step_1",
            node_config={},
            execution_context={},
            attempt=0,
        )
        # Should have tried some path; either RECOVERED or RECOVERY_FAILED
        assert result1.outcome in (
            RecoveryOutcome.RECOVERED,
            RecoveryOutcome.RECOVERY_FAILED,
            RecoveryOutcome.NEEDS_HUMAN,
        )
        first_path = result1.path_taken

        # Second call with exclude_edges from first_path
        exclude_edges = (
            list(zip(first_path[:-1], first_path[1:], strict=True))
            if first_path and len(first_path) >= 2 else None
        )
        result2 = recovery_manager.recover(
            expected_state="D",
            pipeline_name="test",
            node_id="step_1",
            node_config={},
            execution_context={},
            attempt=1,
            exclude_edges=exclude_edges,
        )
        # Just verify it doesn't crash and returns a result
        assert isinstance(result2.outcome, RecoveryOutcome)


# ============================================================
# infer_expected_state (3 级优先级)
# ============================================================

class TestInferExpectedState:
    """infer_expected_state 静态方法 — 3 级优先级推断."""

    def test_priority_1_manual_annotation(self):
        """node_config["expected_state"] 显式标注优先."""
        state, source = InterfaceRecoveryManager.infer_expected_state(
            node_config={"expected_state": "main_menu"},
        )
        assert state == "main_menu"
        assert source == "manual"

    def test_priority_2a_template_path_inference(self):
        """模板类节点从 template 路径推断 (PATH_STATE_MAPPING)."""
        state, source = InterfaceRecoveryManager.infer_expected_state(
            node_config={
                "node_type": "template_match",
                "template": "public/主界面.png",
            },
        )
        assert state == "main_menu"
        assert source == "auto_inferred"

    def test_priority_2a_template_path_fallback_task_state(self):
        """模板路径不在 PATH_STATE_MAPPING 时, 用 <task>_state fallback."""
        state, source = InterfaceRecoveryManager.infer_expected_state(
            node_config={
                "node_type": "template_match",
                "template": "BrownDust-II/templates/get_email/邮箱.png",
            },
        )
        assert state == "get_email_state"
        assert source == "auto_inferred"

    def test_priority_2b_previous_node_chain(self):
        """非识别类节点回溯 previous_node_chain 找标注."""
        state, source = InterfaceRecoveryManager.infer_expected_state(
            node_config={"node_type": "click"},
            previous_node_chain=[
                {"id": "step_1", "config": {"node_type": "template_match", "template": "public/主界面.png"}},
            ],
        )
        assert state == "main_menu"
        assert source == "previous_node_chain"

    def test_priority_3_safe_fallback(self):
        """无任何线索时降级到 safe_states[0]."""
        state, source = InterfaceRecoveryManager.infer_expected_state(
            node_config={"node_type": "click"},
            safe_states=["main_menu", "map_view"],
        )
        assert state == "main_menu"
        assert source == "safe_fallback"

    def test_priority_3_no_safe_states_uses_main_menu(self):
        """safe_states 为空时用 main_menu 作为最后防线."""
        state, source = InterfaceRecoveryManager.infer_expected_state(
            node_config={"node_type": "click"},
            safe_states=[],
        )
        assert state == "main_menu"
        assert source == "safe_fallback"


# ============================================================
# Backward compat
# ============================================================

class TestBackwardCompat:
    """旧调用方不传新参数时行为不变."""

    def test_find_path_old_signature_works(self, recovery_manager):
        """find_path(from, to) 旧签名仍然有效."""
        path = recovery_manager.find_path("A", "D")
        assert path is not None
        assert path[0] == "A"
        assert path[-1] == "D"

    def test_recover_old_signature_works(self, recovery_manager):
        """recover() 不传 attempt / exclude_edges 仍能运行."""
        recovery_manager._screenshot_fn = MagicMock(return_value=None)
        result = recovery_manager.recover(
            expected_state="D",
            pipeline_name="test",
            node_id="step_1",
            node_config={},
            execution_context={},
        )
        assert isinstance(result.outcome, RecoveryOutcome)


# ============================================================
# spec §4.4.2 — transient 参数从 node_config 读取
# ============================================================

class TestTransientParamsFromNodeConfig:
    """recover() 应从 node_config 读取 transient_wait_s / transient_max_retries.

    验证:
      1. node_config 提供自定义值时, _identify_with_transient_retry 用自定义值.
      2. node_config 不提供时, 用默认值 (1.5s / 2 次).
    """

    def test_node_config_overrides_transient_params(
        self, recovery_manager, monkeypatch,
    ):
        """node_config 中 transient_wait_s=0.01, transient_max_retries=3 应被采用."""
        sleep_calls: list[float] = []
        monkeypatch.setattr(
            "core.interface_recovery.time.sleep",
            lambda s: sleep_calls.append(s),
        )
        # screenshot_fn 第一次返回非 None 截图, 后续每次返回非 None (触发重试)
        recovery_manager._screenshot_fn = MagicMock(return_value=b"screen")
        # template_match_fn 永远返回 None (让识别始终失败, 走完所有重试)
        recovery_manager._template_match_fn = MagicMock(return_value=None)

        recovery_manager.recover(
            expected_state="D",
            pipeline_name="test",
            node_id="step_1",
            node_config={
                "transient_wait_s": 0.01,
                "transient_max_retries": 3,
            },
            execution_context={},
        )
        # 应 sleep 3 次, 每次 0.01s
        assert sleep_calls == [0.01, 0.01, 0.01]

    def test_node_config_defaults_when_missing(
        self, recovery_manager, monkeypatch,
    ):
        """node_config 不提供 transient_* 时, 用默认值 1.5s / 2 次."""
        sleep_calls: list[float] = []
        monkeypatch.setattr(
            "core.interface_recovery.time.sleep",
            lambda s: sleep_calls.append(s),
        )
        recovery_manager._screenshot_fn = MagicMock(return_value=b"screen")
        recovery_manager._template_match_fn = MagicMock(return_value=None)

        recovery_manager.recover(
            expected_state="D",
            pipeline_name="test",
            node_id="step_1",
            node_config={},  # 不提供 transient_*
            execution_context={},
        )
        # 应 sleep 2 次 (默认 max_retries=2), 每次 1.5s (默认 wait_s)
        assert sleep_calls == [1.5, 1.5]

    def test_init_no_longer_sets_transient_attrs(self, recovery_manager):
        """__init__ 不再设置 self._transient_wait_s / _transient_max_retries."""
        assert not hasattr(recovery_manager, "_transient_wait_s")
        assert not hasattr(recovery_manager, "_transient_max_retries")
