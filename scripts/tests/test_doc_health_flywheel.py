"""Tests for spec-42 Phase 3: closed-loop flywheel (D2/D3/F2 + C1/C2 integration).

Covers spec-42 §3.3 — 17 integration tests organized in 4 groups:

D2 lesson sedimentation trigger (§3.3.2):
    - Below threshold (2 recurrences) → None
    - At threshold (3 recurrences) → trigger dict
    - Above threshold (5 recurrences) → trigger dict with all 5 issue_ids
    - Wrong dimension (recurrences in other dimensions) → None

D3 rules file mandatory sedimentation (§3.3.3):
    - patch project_rules.md → returned
    - patch lessons/x.md → empty list
    - patch mixed (rules + lessons + failure-modes) → only rules returned

F2 recurrence TD escalation (§3.3.4):
    - recurrence_count=1 → None
    - recurrence_count=2 → escalation dict
    - recurrence_count=3 → escalation dict with count=3
    - Wrong dimension → None

C1 + C2 closed-loop integration (§3.3.1):
    - Full flywheel e2e: create issue → patch → consumed → rerun → resolved
    - Patch failed 2x → mark_failed → recurrence_count=2 → TD escalation
    - Same dimension 3 distinct issue failures → D2 lesson trigger
    - consumed.json persists across sessions (save + reload)
    - Patch rules/handbook → D3 trigger
    - F1 next session skips consumed issue (filter_unconsumed)

All tests use ``tmp_path`` + ``monkeypatch`` so they do not depend on a real
.cache/ directory or run real subprocesses.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

from governance.doc_health_consumed import ConsumedTracker
from governance.doc_health_patch import PatchPlanner, PatchVerifier, RULES_FILES
from governance.report_schema import Issue


# ---- Helpers ----


def _make_issue(
    issue_id: str,
    *,
    dimension: str = "d4_path_drift",
    severity: str = "P0",
    evidence: str = "evidence text",
    suggested_fix: str = "fix suggestion",
    root_cause_hint: str = "root cause",
) -> Issue:
    """Build an Issue with a stable id (overrides __post_init__ id)."""
    issue = Issue(
        dimension=dimension,
        severity=severity,
        evidence=evidence,
        suggested_fix=suggested_fix,
        root_cause_hint=root_cause_hint,
    )
    issue.id = issue_id
    return issue


def _write_report(report_file: Path, issues: list[Issue]) -> None:
    """Write a minimal doc_health_report.json with the given Issue list."""
    report_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": "2026-07-19T15:30:00+08:00",
        "repo_root": str(report_file.parent),
        "git_sha": "abc1234",
        "duration_seconds": 0.5,
        "summary": {
            "total": len(issues),
            "by_severity": {"P0": 0, "P1": 0, "P2": 0},
            "by_dimension": {},
            "consumed_count": 0,
        },
        "issues": [
            {
                "id": i.id,
                "dimension": i.dimension,
                "severity": i.severity,
                "evidence": i.evidence,
                "suggested_fix": i.suggested_fix,
                "root_cause_hint": i.root_cause_hint,
            }
            for i in issues
        ],
    }
    report_file.write_text(json.dumps(payload), encoding="utf-8")


# ============================================================
# D2 lesson sedimentation trigger (spec-42 §3.3.2)
# ============================================================


def test_check_d2_lesson_trigger_below_threshold(tmp_path):
    """2 recurrences in dimension → None (threshold is >= 3)."""
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    # Two distinct issue_ids with recurrence_count >= 1
    tracker.mark_failed(
        "fail_id_0001", dimension="d4_path_drift", severity="P0",
        file="docs/a.md", line=1, failure_reason="r1",
    )
    tracker.mark_failed(
        "fail_id_0002", dimension="d4_path_drift", severity="P0",
        file="docs/b.md", line=1, failure_reason="r2",
    )
    assert tracker.check_d2_lesson_trigger("d4_path_drift") is None


def test_check_d2_lesson_trigger_at_threshold(tmp_path):
    """3 recurrences in dimension → trigger dict with all 3 issue_ids."""
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    for i in range(3):
        tracker.mark_failed(
            f"fail_id_{i:04d}", dimension="d4_path_drift", severity="P0",
            file=f"docs/{i}.md", line=1, failure_reason=f"r{i}",
        )
    result = tracker.check_d2_lesson_trigger("d4_path_drift")
    assert result is not None
    assert result["dimension"] == "d4_path_drift"
    assert set(result["recurrence_issue_ids"]) == {
        "fail_id_0000", "fail_id_0001", "fail_id_0002",
    }
    assert result["suggested_lesson_topic"] == "doc_health_d4_path_drift_recurrence"


def test_check_d2_lesson_trigger_above_threshold(tmp_path):
    """5 recurrences in dimension → trigger dict with all 5 issue_ids."""
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    for i in range(5):
        tracker.mark_failed(
            f"fail_id_{i:04d}", dimension="d4_path_drift", severity="P0",
            file=f"docs/{i}.md", line=1, failure_reason=f"r{i}",
        )
    result = tracker.check_d2_lesson_trigger("d4_path_drift")
    assert result is not None
    assert len(result["recurrence_issue_ids"]) == 5
    assert set(result["recurrence_issue_ids"]) == {
        f"fail_id_{i:04d}" for i in range(5)
    }


def test_check_d2_lesson_trigger_wrong_dimension(tmp_path):
    """Recurrences in other dimensions do not count toward this dimension."""
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    # 3 failures in d1_overlap, 0 in d4_path_drift
    for i in range(3):
        tracker.mark_failed(
            f"fail_id_{i:04d}", dimension="d1_overlap", severity="P0",
            file=f"docs/{i}.md", line=1, failure_reason=f"r{i}",
        )
    # d4_path_drift has 0 recurrences → None
    assert tracker.check_d2_lesson_trigger("d4_path_drift") is None
    # d1_overlap has 3 → triggers
    assert tracker.check_d2_lesson_trigger("d1_overlap") is not None


def test_check_d2_lesson_trigger_consumed_not_recurrence(tmp_path):
    """Issues with recurrence_count=0 (mark_consumed only) do NOT trigger D2.

    D2 requires recurrence_count >= 1 (patch failed at least once). A
    successfully patched issue (recurrence_count=0) does not count.
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    # 3 successful patches (recurrence_count=0) → no D2 trigger
    for i in range(3):
        tracker.mark_consumed(
            f"ok_id_{i:04d}", dimension="d4_path_drift", severity="P0",
            file=f"docs/{i}.md", line=1, commit_hash=f"hash{i}",
            action_taken="patched ok",
        )
    assert tracker.check_d2_lesson_trigger("d4_path_drift") is None


# ============================================================
# D3 rules file mandatory sedimentation (spec-42 §3.3.3)
# ============================================================


def test_check_d3_sediment_trigger_with_rules(tmp_path):
    """Patching project_rules.md → returned (single match)."""
    planner = PatchPlanner(tmp_path / "report.json", tmp_path / "consumed.json")
    result = planner.check_d3_sediment_trigger([".skills/rules/project_rules.md"])
    assert result == [".skills/rules/project_rules.md"]


def test_check_d3_sediment_trigger_without_rules(tmp_path):
    """Patching lessons/x.md → empty list (lessons are not rules files).

    Lessons sedimentation is handled by the regular N166/L1-中 flow,
    not D3. D3 only fires for the 3 RULES_FILES.
    """
    planner = PatchPlanner(tmp_path / "report.json", tmp_path / "consumed.json")
    result = planner.check_d3_sediment_trigger([".ai-memory/lessons/x.md"])
    assert result == []


def test_check_d3_sediment_trigger_mixed(tmp_path):
    """Patching mixed files → only rules files returned, in input order."""
    planner = PatchPlanner(tmp_path / "report.json", tmp_path / "consumed.json")
    patched = [
        ".ai-memory/lessons/x.md",                          # not rules
        ".skills/rules/project_rules.md",                     # rules
        ".ai-memory/summaries/architecture.md",             # not rules
        ".ai-memory/meta/failure-modes.md",                 # rules
        ".ai-memory/meta/ai-operating-handbook.md",         # rules
    ]
    result = planner.check_d3_sediment_trigger(patched)
    assert result == [
        ".skills/rules/project_rules.md",
        ".ai-memory/meta/failure-modes.md",
        ".ai-memory/meta/ai-operating-handbook.md",
    ]


def test_check_d3_sediment_trigger_empty_input(tmp_path):
    """Empty patched_files list → empty result."""
    planner = PatchPlanner(tmp_path / "report.json", tmp_path / "consumed.json")
    assert planner.check_d3_sediment_trigger([]) == []


def test_rules_files_constant_is_complete():
    """RULES_FILES must contain exactly the 3 rules files per spec §3.3.3."""
    assert RULES_FILES == {
        ".skills/rules/project_rules.md",
        ".ai-memory/meta/ai-operating-handbook.md",
        ".ai-memory/meta/failure-modes.md",
    }


# ============================================================
# F2 recurrence TD escalation (spec-42 §3.3.4)
# ============================================================


def test_check_td_escalation_below_threshold(tmp_path):
    """recurrence_count=1 → None (threshold is >= 2)."""
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    tracker.mark_failed(
        "fail_id_0001", dimension="d4_path_drift", severity="P0",
        file="docs/x.md", line=1, failure_reason="first failure",
    )
    # recurrence_count=1 → no escalation
    assert tracker.check_td_escalation("d4_path_drift") is None


def test_check_td_escalation_at_threshold(tmp_path):
    """recurrence_count=2 → escalation dict (TD escalation triggers at 2)."""
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    iid = "fail_id_0001"
    # First failure (recurrence_count=1)
    tracker.mark_failed(
        iid, dimension="d4_path_drift", severity="P0",
        file="docs/x.md", line=1, failure_reason="attempt 1",
    )
    # Second failure (recurrence_count=2) → TD escalation
    tracker.mark_failed(
        iid, dimension="d4_path_drift", severity="P0",
        file="docs/x.md", line=1, failure_reason="attempt 2",
    )
    result = tracker.check_td_escalation("d4_path_drift")
    assert result is not None
    assert result["dimension"] == "d4_path_drift"
    assert result["issue_id"] == iid
    assert result["recurrence_count"] == 2
    assert result["suggested_td_title"] == (
        "doc_health d4_path_drift issue fail_id_0001 auto-patch failed 2x"
    )


def test_check_td_escalation_above_threshold(tmp_path):
    """recurrence_count=3 → escalation dict with count=3 (still triggers)."""
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    iid = "fail_id_0001"
    for i in range(3):
        tracker.mark_failed(
            iid, dimension="d4_path_drift", severity="P0",
            file="docs/x.md", line=1, failure_reason=f"attempt {i + 1}",
        )
    result = tracker.check_td_escalation("d4_path_drift")
    assert result is not None
    assert result["recurrence_count"] == 3
    assert "failed 3x" in result["suggested_td_title"]


def test_check_td_escalation_wrong_dimension(tmp_path):
    """recurrence_count=2 in different dimension → None for this dimension."""
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    iid = "fail_id_0001"
    for _ in range(2):
        tracker.mark_failed(
            iid, dimension="d1_overlap", severity="P0",
            file="docs/x.md", line=1, failure_reason="attempt",
        )
    # d4_path_drift has no failures → None
    assert tracker.check_td_escalation("d4_path_drift") is None
    # d1_overlap has recurrence_count=2 → triggers
    assert tracker.check_td_escalation("d1_overlap") is not None


# ============================================================
# C1 + C2 closed-loop integration (spec-42 §3.3.1)
# ============================================================


def test_full_flywheel_e2e(tmp_path, monkeypatch):
    """Full flywheel: create issue → patch → consumed → rerun → resolved.

    Verifies the spec-42 §2.1 happy-path:
    1. report.json has P0 issue
    2. PatchPlanner.get_patchable_issues returns it
    3. AI "patches" (simulated: remove issue from report)
    4. mark_consumed updates consumed.json
    5. PatchVerifier.verify_patched returns {id: True}
    6. Next get_patchable_issues call skips it (already consumed)
    """
    report_file = tmp_path / "report.json"
    consumed_file = tmp_path / "consumed.json"

    issue = _make_issue("fly_e2e_0001", dimension="d4_path_drift", severity="P0")
    _write_report(report_file, [issue])

    # 1. Planner sees the unconsumed P0 issue
    planner = PatchPlanner(report_file, consumed_file)
    patchable = planner.get_patchable_issues()
    assert len(patchable) == 1
    assert patchable[0].id == "fly_e2e_0001"

    # 2. AI applies patch (simulated: rewrite report without the issue)
    _write_report(report_file, [])

    # 3. mark_consumed records the patch
    tracker = ConsumedTracker(consumed_file)
    tracker.mark_consumed(
        "fly_e2e_0001", dimension="d4_path_drift", severity="P0",
        file=".ai-memory/lessons/x.md", line=8,
        commit_hash="patch_hash_1", action_taken="updated related_files",
    )

    # 4. Verify: rerun_check sees no issues → patched issue is "resolved"
    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout="", stderr="", returncode=0)
    monkeypatch.setattr("subprocess.run", fake_run)

    verifier = PatchVerifier(tmp_path)
    verify_result = verifier.verify_patched(["fly_e2e_0001"])
    assert verify_result == {"fly_e2e_0001": True}

    # 5. Next session: planner skips the consumed issue
    # (Even if report.json still had the issue, it would be filtered)
    _write_report(report_file, [issue])
    patchable_after = planner.get_patchable_issues()
    assert patchable_after == []


def test_patch_failed_escalates_td_pattern(tmp_path):
    """Patch fails 2x → mark_failed → recurrence_count=2 → check_td_escalation.

    Verifies the spec-42 §3.3.4 escalation pattern:
    1. AI attempts patch, fails → mark_failed (recurrence_count=1)
    2. AI retries, fails again → mark_failed (recurrence_count=2)
    3. check_td_escalation returns dict → caller escalates to TD
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    iid = "fail_pattern_1"

    # First attempt fails
    tracker.mark_failed(
        iid, dimension="d4_path_drift", severity="P0",
        file=".ai-memory/lessons/x.md", line=10,
        failure_reason="patch caused pytest failure",
    )
    # First failure alone → no escalation yet
    assert tracker.check_td_escalation("d4_path_drift") is None

    # Second attempt also fails
    tracker.mark_failed(
        iid, dimension="d4_path_drift", severity="P0",
        file=".ai-memory/lessons/x.md", line=10,
        failure_reason="retry also failed",
    )
    # Now recurrence_count=2 → escalation
    escalation = tracker.check_td_escalation("d4_path_drift")
    assert escalation is not None
    assert escalation["issue_id"] == iid
    assert escalation["recurrence_count"] == 2
    assert "auto-patch failed 2x" in escalation["suggested_td_title"]


def test_recurrence_3_triggers_lesson_pattern(tmp_path):
    """3 distinct issues fail in same dimension → D2 lesson trigger fires.

    Verifies the spec-42 §3.3.2 pattern:
    1. Three different issues in d4_path_drift each fail once
    2. Each mark_failed sets recurrence_count=1 for its issue_id
    3. check_d2_lesson_trigger sees 3 distinct recurrences → triggers lesson
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")

    # Three distinct issues, each fails once
    for i in range(3):
        tracker.mark_failed(
            f"distinct_{i:04d}", dimension="d4_path_drift", severity="P0",
            file=f"docs/{i}.md", line=1, failure_reason=f"failure {i}",
        )

    trigger = tracker.check_d2_lesson_trigger("d4_path_drift")
    assert trigger is not None
    assert trigger["dimension"] == "d4_path_drift"
    assert set(trigger["recurrence_issue_ids"]) == {
        "distinct_0000", "distinct_0001", "distinct_0002",
    }
    assert trigger["suggested_lesson_topic"] == "doc_health_d4_path_drift_recurrence"


def test_consumed_persists_across_sessions(tmp_path):
    """consumed.json survives across "sessions" (save → reload).

    Simulates: session 1 marks consumed → file written → session 2 reads file
    and confirms issue is still marked consumed.
    """
    consumed_file = tmp_path / "consumed.json"

    # Session 1: mark consumed
    tracker1 = ConsumedTracker(consumed_file)
    tracker1.mark_consumed(
        "persist_id_001", dimension="d4_path_drift", severity="P0",
        file=".ai-memory/lessons/x.md", line=8,
        commit_hash="hash_session_1", action_taken="patched in session 1",
    )

    # Verify file was actually written to disk
    assert consumed_file.exists()
    raw = json.loads(consumed_file.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert "persist_id_001" in raw["consumed_issues"]

    # Session 2: new tracker instance reads same file
    tracker2 = ConsumedTracker(consumed_file)
    assert tracker2.is_consumed("persist_id_001") is True
    loaded = tracker2.load()
    assert loaded["persist_id_001"]["commit_hash"] == "hash_session_1"
    assert loaded["persist_id_001"]["action_taken"] == "patched in session 1"


def test_patch_involves_rules_triggers_d3(tmp_path):
    """Patch that modifies rules/handbook files → D3 trigger fires.

    Verifies spec-42 §3.3.3: when AI patches any of RULES_FILES, the caller
    must sync sedimentation to the corresponding sections (§3.8 边执行边沉淀).
    """
    planner = PatchPlanner(tmp_path / "report.json", tmp_path / "consumed.json")

    # AI patches a rules file as part of fixing a d7_index_consistency issue
    patched_files = [
        ".ai-memory/meta/failure-modes.md",  # rules file → D3 triggers
        ".ai-memory/lessons/d7_recurrence.md",  # lesson file → not D3
    ]
    triggered = planner.check_d3_sediment_trigger(patched_files)
    assert ".ai-memory/meta/failure-modes.md" in triggered
    assert ".ai-memory/lessons/d7_recurrence.md" not in triggered
    # Caller (main session AI) must now sync failure-modes.md sections
    # per §3.8 边执行边沉淀 (e.g. add N## index row if new anti-pattern).


def test_f1_flywheel_next_session_skips_consumed(tmp_path):
    """F1: next session's filter_unconsumed skips successfully-consumed issue.

    Verifies spec-42 §2.1 flywheel property: once an issue is consumed
    (patch_failed=false), it does not re-enter the patch queue.
    """
    consumed_file = tmp_path / "consumed.json"
    tracker = ConsumedTracker(consumed_file)

    # Session 1: patch succeeds
    tracker.mark_consumed(
        "f1_skip_00001", dimension="d4_path_drift", severity="P0",
        file=".ai-memory/lessons/x.md", line=8,
        commit_hash="hash1", action_taken="patched",
    )

    # Session 2: same issue_id appears in report.json again (e.g. due to
    # check_id stability — Issue.__post_init__ computes id from fields).
    # filter_unconsumed should skip it.
    issues_session2 = [
        _make_issue("f1_skip_00001", dimension="d4_path_drift", severity="P0"),
        _make_issue("f1_new_000002", dimension="d4_path_drift", severity="P1"),
    ]
    tracker2 = ConsumedTracker(consumed_file)
    filtered = tracker2.filter_unconsumed(issues_session2)
    # Only the new unconsumed issue should remain
    assert len(filtered) == 1
    assert filtered[0].id == "f1_new_000002"


def test_failed_issue_still_visible_for_td_escalation(tmp_path):
    """Failed patch (recurrence_count >= 2) is excluded from auto-patch queue
    but visible to check_td_escalation for human intervention.

    Verifies spec-42 §3.3.4 + get_patchable_issues interaction:
    1. mark_failed twice → recurrence_count=2
    2. get_patchable_issues excludes it (no auto re-patch)
    3. check_td_escalation returns dict (caller escalates to TD)
    """
    report_file = tmp_path / "report.json"
    consumed_file = tmp_path / "consumed.json"

    issue = _make_issue("td_vis_000001", dimension="d4_path_drift", severity="P0")
    _write_report(report_file, [issue])

    tracker = ConsumedTracker(consumed_file)
    # Fail twice
    for _ in range(2):
        tracker.mark_failed(
            "td_vis_000001", dimension="d4_path_drift", severity="P0",
            file=".ai-memory/lessons/x.md", line=8,
            failure_reason="patch failed",
        )

    # get_patchable_issues should exclude the failed issue
    planner = PatchPlanner(report_file, consumed_file)
    patchable = planner.get_patchable_issues()
    assert patchable == []

    # But check_td_escalation should report it for TD escalation
    escalation = tracker.check_td_escalation("d4_path_drift")
    assert escalation is not None
    assert escalation["issue_id"] == "td_vis_000001"
    assert escalation["recurrence_count"] == 2


def test_d2_and_f2_can_coexist(tmp_path):
    """D2 and F2 triggers are independent: both can fire for same dimension.

    Scenario: 3 distinct issues, each failed 2 times.
    - D2 (>= 3 recurrences with count >= 1) → triggers (3 distinct)
    - F2 (any issue with count >= 2) → triggers (all 3 qualify)
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    for i in range(3):
        iid = f"both_{i:04d}"
        for _ in range(2):
            tracker.mark_failed(
                iid, dimension="d4_path_drift", severity="P0",
                file=f"docs/{i}.md", line=1, failure_reason="fail",
            )

    d2 = tracker.check_d2_lesson_trigger("d4_path_drift")
    f2 = tracker.check_td_escalation("d4_path_drift")
    assert d2 is not None
    assert f2 is not None
    # D2 reports all 3 issue_ids
    assert len(d2["recurrence_issue_ids"]) == 3
    # F2 reports the first one it finds (any one is sufficient for escalation)
    assert f2["issue_id"] in {"both_0000", "both_0001", "both_0002"}
    assert f2["recurrence_count"] == 2
