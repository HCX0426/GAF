"""Tests for spec-42 Phase 2: PatchPlanner + PatchVerifier (AI patch helpers).

Covers spec-42 §3.2.4 — 14 unit tests:
- PatchPlanner.get_patchable_issues: filter consumed / filter P2 / filter failed /
  respect max=10 / sort P0 first
- PatchPlanner.group_by_dimension: same-dimension grouping + order preservation
- PatchVerifier.rerun_check: parse rewritten report.json (monkeypatched subprocess)
- PatchVerifier.verify_patched: detect success / detect failure
- PatchVerifier.run_relevant_pytest: passes / fails / subprocess error /
  timeout / unknown dimension

All tests use ``tmp_path`` + ``monkeypatch`` so they do not depend on a
real .cache/ directory or run real subprocesses.
"""
from __future__ import annotations

import json
import subprocess
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
from governance.doc_health_patch import PatchPlanner, PatchVerifier
from governance.report_schema import Issue


# ---- Helpers ----


def _write_report(report_file: Path, issues: list[dict]) -> None:
    """Write a minimal doc_health_report.json with the given issues list."""
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
        "issues": issues,
    }
    report_file.write_text(json.dumps(payload), encoding="utf-8")


def _make_raw_issue(
    issue_id: str,
    *,
    dimension: str = "d4_path_drift",
    severity: str = "P0",
    evidence: str = "e",
    suggested_fix: str = "f",
    root_cause_hint: str = "r",
) -> dict:
    """Build a minimal issue dict matching report.json schema."""
    return {
        "id": issue_id,
        "dimension": dimension,
        "severity": severity,
        "evidence": evidence,
        "suggested_fix": suggested_fix,
        "root_cause_hint": root_cause_hint,
    }


# ---- PatchPlanner.get_patchable_issues ----


def test_get_patchable_issues_filters_consumed(tmp_path):
    """Issues successfully consumed (patch_failed=false) are excluded.

    The flywheel should skip already-patched issues at session start.
    """
    report_file = tmp_path / "report.json"
    consumed_file = tmp_path / "consumed.json"

    _write_report(report_file, [
        _make_raw_issue("consumed_id1", severity="P0"),
        _make_raw_issue("fresh_id_002", severity="P0"),
    ])

    # Mark consumed_id1 as successfully patched
    tracker = ConsumedTracker(consumed_file)
    tracker.mark_consumed(
        "consumed_id1", dimension="d4_path_drift", severity="P0",
        file="docs/x.md", line=1, commit_hash="abc1234",
        action_taken="patched in prior session",
    )

    planner = PatchPlanner(report_file, consumed_file)
    patchable = planner.get_patchable_issues()
    assert len(patchable) == 1
    assert patchable[0].id == "fresh_id_002"


def test_get_patchable_issues_filters_p2(tmp_path):
    """P2 issues are excluded from auto-patch (left for L3 循环)."""
    report_file = tmp_path / "report.json"
    consumed_file = tmp_path / "consumed.json"

    _write_report(report_file, [
        _make_raw_issue("p0_id_000001", severity="P0"),
        _make_raw_issue("p1_id_000002", severity="P1"),
        _make_raw_issue("p2_id_000003", severity="P2"),
    ])

    planner = PatchPlanner(report_file, consumed_file)
    patchable = planner.get_patchable_issues()
    assert len(patchable) == 2
    severities = {i.severity for i in patchable}
    assert severities == {"P0", "P1"}


def test_get_patchable_issues_filters_failed(tmp_path):
    """Issues with patch_failed=true are excluded (need TD escalation, not re-patch).

    Per spec §3.3.4, failed patches must not be retried automatically —
    they escalate to a TD instead.
    """
    report_file = tmp_path / "report.json"
    consumed_file = tmp_path / "consumed.json"

    _write_report(report_file, [
        _make_raw_issue("failed_id_01", severity="P0"),
        _make_raw_issue("fresh_id_002", severity="P0"),
    ])

    # Mark failed_id_01 as patch_failed=true (1 attempt failed)
    tracker = ConsumedTracker(consumed_file)
    tracker.mark_failed(
        "failed_id_01", dimension="d4_path_drift", severity="P0",
        file="docs/x.md", line=1, failure_reason="patch attempt failed",
    )

    planner = PatchPlanner(report_file, consumed_file)
    patchable = planner.get_patchable_issues()
    assert len(patchable) == 1
    assert patchable[0].id == "fresh_id_002"


def test_get_patchable_issues_respects_max(tmp_path):
    """Default cap of 10 issues per session (spec §3.2.1 red line).

    Construct 15 patchable P0 issues; expect only 10 returned.
    """
    report_file = tmp_path / "report.json"
    consumed_file = tmp_path / "consumed.json"

    raw_issues = [
        _make_raw_issue(f"id_{i:010d}", severity="P0")
        for i in range(15)
    ]
    _write_report(report_file, raw_issues)

    planner = PatchPlanner(report_file, consumed_file)
    patchable = planner.get_patchable_issues(max_issues=10)
    assert len(patchable) == 10
    # Should be the first 10 from the report (stable sort preserves order)
    expected_ids = [f"id_{i:010d}" for i in range(10)]
    assert [i.id for i in patchable] == expected_ids


def test_get_patchable_issues_sorts_p0_first(tmp_path):
    """P0 issues come before P1; within same severity, report order preserved.

    Input order: [P1, P0, P1, P0]
    Expected output: [P0, P0, P1, P1] (stable sort by severity rank).
    """
    report_file = tmp_path / "report.json"
    consumed_file = tmp_path / "consumed.json"

    _write_report(report_file, [
        _make_raw_issue("p1_first_01", severity="P1"),
        _make_raw_issue("p0_first_01", severity="P0"),
        _make_raw_issue("p1_second_2", severity="P1"),
        _make_raw_issue("p0_second_2", severity="P0"),
    ])

    planner = PatchPlanner(report_file, consumed_file)
    patchable = planner.get_patchable_issues()
    assert [i.id for i in patchable] == [
        "p0_first_01", "p0_second_2", "p1_first_01", "p1_second_2",
    ]


def test_get_patchable_issues_missing_report_returns_empty(tmp_path):
    """Missing report.json → empty list (graceful degradation).

    First-run scenario: doc_health_check.py has not been run yet.
    """
    planner = PatchPlanner(
        tmp_path / "nonexistent_report.json",
        tmp_path / "nonexistent_consumed.json",
    )
    assert planner.get_patchable_issues() == []


# ---- PatchPlanner.group_by_dimension ----


def test_group_by_dimension_batches_correctly(tmp_path):
    """Same-dimension issues group together; order preserved within group.

    Input: [d1/P0, d4/P0, d1/P1, d4/P1, d1/P1]
    Expected groups:
      d1_overlap:    [d1/P0, d1/P1, d1/P1]
      d4_path_drift: [d4/P0, d4/P1]
    """
    issues = [
        Issue(dimension="d1_overlap", severity="P0", evidence="e1",
              suggested_fix="f1", root_cause_hint="r1"),
        Issue(dimension="d4_path_drift", severity="P0", evidence="e2",
              suggested_fix="f2", root_cause_hint="r2"),
        Issue(dimension="d1_overlap", severity="P1", evidence="e3",
              suggested_fix="f3", root_cause_hint="r3"),
        Issue(dimension="d4_path_drift", severity="P1", evidence="e4",
              suggested_fix="f4", root_cause_hint="r4"),
        Issue(dimension="d1_overlap", severity="P1", evidence="e5",
              suggested_fix="f5", root_cause_hint="r5"),
    ]
    # Set explicit ids so we can verify order preservation
    issues[0].id = "d1_p0_000001"
    issues[1].id = "d4_p0_000001"
    issues[2].id = "d1_p1_000001"
    issues[3].id = "d4_p1_000001"
    issues[4].id = "d1_p1_000002"

    planner = PatchPlanner(tmp_path / "report.json", tmp_path / "consumed.json")
    groups = planner.group_by_dimension(issues)

    assert set(groups.keys()) == {"d1_overlap", "d4_path_drift"}
    assert len(groups["d1_overlap"]) == 3
    assert len(groups["d4_path_drift"]) == 2
    # Verify order preserved within each group
    assert [i.id for i in groups["d1_overlap"]] == [
        "d1_p0_000001", "d1_p1_000001", "d1_p1_000002",
    ]
    assert [i.id for i in groups["d4_path_drift"]] == [
        "d4_p0_000001", "d4_p1_000001",
    ]


# ---- PatchVerifier.rerun_check ----


def test_rerun_check_returns_current_issues(tmp_path, monkeypatch):
    """rerun_check parses the rewritten .cache/doc_health_report.json.

    Monkeypatches subprocess.run so no real doc_health_check.py executes;
    pre-populates the report file with known content and verifies parsing.
    """
    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    report_file = cache_dir / "doc_health_report.json"

    _write_report(report_file, [
        _make_raw_issue("id0012345678", dimension="d1_overlap", severity="P0"),
        _make_raw_issue("id0098765432", dimension="d1_overlap", severity="P1"),
    ])

    # Stub subprocess.run to skip actual execution
    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout="ok", stderr="", returncode=0)
    monkeypatch.setattr("subprocess.run", fake_run)

    verifier = PatchVerifier(tmp_path)
    issues = verifier.rerun_check()
    assert len(issues) == 2
    ids = {i.id for i in issues}
    assert ids == {"id0012345678", "id0098765432"}


def test_rerun_check_missing_report_returns_empty(tmp_path, monkeypatch):
    """rerun_check returns [] when report file is missing after subprocess run.

    Covers the edge case where doc_health_check.py crashes before writing
    the report — verifier should not raise, just return empty list.
    """
    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout="ok", stderr="", returncode=0)
    monkeypatch.setattr("subprocess.run", fake_run)

    # tmp_path has no .cache/ directory — verifier should return []
    verifier = PatchVerifier(tmp_path)
    assert verifier.rerun_check() == []


def test_rerun_check_subprocess_error_returns_empty(tmp_path, monkeypatch):
    """rerun_check returns [] when subprocess raises CalledProcessError.

    Caller treats empty list as "verification not possible" — not as
    "all issues resolved".
    """
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0] if args else "python")
    monkeypatch.setattr("subprocess.run", fake_run)

    verifier = PatchVerifier(tmp_path)
    assert verifier.rerun_check() == []


# ---- PatchVerifier.verify_patched ----


def test_verify_patched_detects_success(tmp_path, monkeypatch):
    """verify_patched returns {id: True} when patched issue is no longer present."""
    issue2 = Issue(dimension="d1_overlap", severity="P1", evidence="e2",
                   suggested_fix="f2", root_cause_hint="r2")
    issue2.id = "issue2_id_001"

    # Stub rerun_check to return only issue2 (issue1 was patched successfully)
    def fake_rerun_check(self):
        return [issue2]
    monkeypatch.setattr(PatchVerifier, "rerun_check", fake_rerun_check)

    verifier = PatchVerifier(tmp_path)
    result = verifier.verify_patched(["issue1_id_001"])
    assert result == {"issue1_id_001": True}


def test_verify_patched_detects_failure(tmp_path, monkeypatch):
    """verify_patched returns {id: False} when patched issue is still present."""
    issue1 = Issue(dimension="d1_overlap", severity="P0", evidence="e1",
                   suggested_fix="f1", root_cause_hint="r1")
    issue1.id = "issue1_id_001"

    # Stub rerun_check to return issue1 (still present — patch failed)
    def fake_rerun_check(self):
        return [issue1]
    monkeypatch.setattr(PatchVerifier, "rerun_check", fake_rerun_check)

    verifier = PatchVerifier(tmp_path)
    result = verifier.verify_patched(["issue1_id_001"])
    assert result == {"issue1_id_001": False}


def test_verify_patched_mixed_results(tmp_path, monkeypatch):
    """verify_patched handles a mix of resolved and still-present issues."""
    issue1 = Issue(dimension="d1_overlap", severity="P0", evidence="e1",
                   suggested_fix="f1", root_cause_hint="r1")
    issue1.id = "issue1_id_001"
    issue3 = Issue(dimension="d4_path_drift", severity="P0", evidence="e3",
                   suggested_fix="f3", root_cause_hint="r3")
    issue3.id = "issue3_id_003"

    # issue1 still present, issue3 still present, issue2 gone
    def fake_rerun_check(self):
        return [issue1, issue3]
    monkeypatch.setattr(PatchVerifier, "rerun_check", fake_rerun_check)

    verifier = PatchVerifier(tmp_path)
    result = verifier.verify_patched(["issue1_id_001", "issue2_id_002", "issue3_id_003"])
    assert result == {
        "issue1_id_001": False,  # still present
        "issue2_id_002": True,   # gone → patched successfully
        "issue3_id_003": False,  # still present
    }


# ---- PatchVerifier.run_relevant_pytest ----


def test_run_relevant_pytest_passes(tmp_path, monkeypatch):
    """run_relevant_pytest returns (passed, 0) on a clean pytest run."""
    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            stdout="===== 5 passed in 2.34s =====",
            stderr="",
            returncode=0,
        )
    monkeypatch.setattr("subprocess.run", fake_run)

    verifier = PatchVerifier(tmp_path)
    passed, failed = verifier.run_relevant_pytest("d4_path_drift")
    assert (passed, failed) == (5, 0)


def test_run_relevant_pytest_fails(tmp_path, monkeypatch):
    """run_relevant_pytest returns (passed, failed) when some tests fail."""
    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            stdout="===== 3 passed, 2 failed in 3.45s =====",
            stderr="some errors",
            returncode=1,
        )
    monkeypatch.setattr("subprocess.run", fake_run)

    verifier = PatchVerifier(tmp_path)
    passed, failed = verifier.run_relevant_pytest("d4_path_drift")
    assert (passed, failed) == (3, 2)


def test_run_relevant_pytest_subprocess_error(tmp_path, monkeypatch):
    """run_relevant_pytest returns (0, 0) when subprocess raises CalledProcessError.

    (0, 0) means "verification not possible" — caller should treat it as
    failed verification, not passing.
    """
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0] if args else "conda")
    monkeypatch.setattr("subprocess.run", fake_run)

    verifier = PatchVerifier(tmp_path)
    passed, failed = verifier.run_relevant_pytest("d4_path_drift")
    assert (passed, failed) == (0, 0)


def test_run_relevant_pytest_timeout(tmp_path, monkeypatch):
    """run_relevant_pytest returns (0, 0) on subprocess.TimeoutExpired.

    Covers the 10s timeout red line — verifier must not hang.
    """
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0] if args else "conda", timeout=10)
    monkeypatch.setattr("subprocess.run", fake_run)

    verifier = PatchVerifier(tmp_path)
    passed, failed = verifier.run_relevant_pytest("d4_path_drift")
    assert (passed, failed) == (0, 0)


def test_run_relevant_pytest_unknown_dimension(tmp_path):
    """run_relevant_pytest returns (0, 0) for unknown dimension (no test file mapping)."""
    verifier = PatchVerifier(tmp_path)
    passed, failed = verifier.run_relevant_pytest("unknown_dimension")
    assert (passed, failed) == (0, 0)


def test_run_relevant_pytest_consumed_dimension(tmp_path, monkeypatch):
    """run_relevant_pytest maps 'consumed' → test_doc_health_consumed.py."""
    captured_args: list = []

    def fake_run(*args, **kwargs):
        captured_args.append(args[0] if args else kwargs.get("args"))
        return SimpleNamespace(
            stdout="===== 11 passed in 1.50s =====",
            stderr="",
            returncode=0,
        )
    monkeypatch.setattr("subprocess.run", fake_run)

    verifier = PatchVerifier(tmp_path)
    passed, failed = verifier.run_relevant_pytest("consumed")
    assert (passed, failed) == (11, 0)
    # Verify the correct test file was targeted
    cmd = captured_args[0]
    assert "scripts/tests/test_doc_health_consumed.py" in cmd


def test_run_relevant_pytest_patch_dimension(tmp_path, monkeypatch):
    """run_relevant_pytest maps 'patch' → test_doc_health_patch.py."""
    captured_args: list = []

    def fake_run(*args, **kwargs):
        captured_args.append(args[0] if args else kwargs.get("args"))
        return SimpleNamespace(
            stdout="===== 14 passed in 2.00s =====",
            stderr="",
            returncode=0,
        )
    monkeypatch.setattr("subprocess.run", fake_run)

    verifier = PatchVerifier(tmp_path)
    passed, failed = verifier.run_relevant_pytest("patch")
    assert (passed, failed) == (14, 0)
    cmd = captured_args[0]
    assert "scripts/tests/test_doc_health_patch.py" in cmd
