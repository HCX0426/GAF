"""Common: issue id + report schema + run_all_dimensions Tests (split from test_doc_health_check.py, s40, TD-365 7/9)."""
from __future__ import annotations

import json
import sys
from governance.report_schema import Issue, ReportSummary, DocHealthReport
import sys
from pathlib import Path

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit


def test_issue_id_stable_hash():
    """Issue.id is a stable 12-char hash based on dimension+file+line+severity+evidence."""
    issue = Issue(
        dimension="d4_path_drift",
        severity="P0",
        file=".ai-memory/lessons/test.md",
        line=8,
        evidence="path does not exist",
        suggested_fix="update path",
        root_cause_hint="file moved",
    )
    assert len(issue.id) == 12
    # Same inputs → same id
    issue2 = Issue(
        dimension="d4_path_drift",
        severity="P0",
        file=".ai-memory/lessons/test.md",
        line=8,
        evidence="path does not exist",
        suggested_fix="different fix doesn't affect id",
        root_cause_hint="different hint doesn't affect id",
    )
    assert issue.id == issue2.id


def test_report_summary_computes_totals():
    """ReportSummary computes total + by_severity + by_dimension from issues list."""
    issues = [
        Issue(dimension="d1_overlap", severity="P2", evidence="e1", suggested_fix="f1", root_cause_hint="r1"),
        Issue(dimension="d1_overlap", severity="P1", evidence="e2", suggested_fix="f2", root_cause_hint="r2"),
        Issue(dimension="d2_bloat", severity="P0", evidence="e3", suggested_fix="f3", root_cause_hint="r3"),
    ]
    summary = ReportSummary.from_issues(issues)
    assert summary.total == 3
    assert summary.by_severity == {"P0": 1, "P1": 1, "P2": 1}
    assert summary.by_dimension["d1_overlap"] == 2
    assert summary.by_dimension["d2_bloat"] == 1


def test_doc_health_report_serializes_to_json():
    """DocHealthReport can be serialized to JSON with all required fields."""
    report = DocHealthReport(
        generated_at="2026-07-19T15:30:00+08:00",
        repo_root="d:/code/GAF",
        git_sha="34397b34",
        duration_seconds=1.82,
        summary=ReportSummary(total=0, by_severity={"P0": 0, "P1": 0, "P2": 0}, by_dimension={}),
        issues=[],
    )
    data = json.loads(report.to_json())
    assert data["generated_at"] == "2026-07-19T15:30:00+08:00"
    assert data["repo_root"] == "d:/code/GAF"
    assert data["git_sha"] == "34397b34"
    assert data["summary"]["total"] == 0
    assert data["issues"] == []


def test_doc_health_report_to_dict_returns_dict():
    """DocHealthReport.to_dict() returns a dict (not JSON string) for direct consumption."""
    report = DocHealthReport(
        generated_at="2026-07-19T15:30:00+08:00",
        repo_root="d:/code/GAF",
        git_sha="34397b34",
        duration_seconds=1.82,
        summary=ReportSummary(total=0, by_severity={"P0": 0, "P1": 0, "P2": 0}, by_dimension={}),
        issues=[],
    )
    d = report.to_dict()
    assert isinstance(d, dict)
    assert d["repo_root"] == "d:/code/GAF"
    assert d["git_sha"] == "34397b34"
    # to_json should be consistent with to_dict
    assert json.loads(report.to_json()) == d


def test_issue_to_dict_drops_none_values():
    """Issue.to_dict() should drop None fields to keep JSON compact."""
    issue = Issue(
        dimension="d1_overlap",
        severity="P2",
        evidence="e",
        suggested_fix="f",
        root_cause_hint="r",
        # file/line/files left as None
    )
    d = issue.to_dict()
    assert "file" not in d
    assert "line" not in d
    assert "files" not in d
    assert d["dimension"] == "d1_overlap"
    assert d["consumed"] is False  # bool False is not None, should be kept


def test_report_summary_from_empty_list():
    """ReportSummary.from_issues([]) should return zero counts with all severity keys."""
    summary = ReportSummary.from_issues([])
    assert summary.total == 0
    assert summary.by_severity == {"P0": 0, "P1": 0, "P2": 0}
    assert summary.by_dimension == {}


def test_run_all_dimensions_dispatches_to_seven_modules(tmp_path, monkeypatch):
    """run_all_dimensions should call check() on all 7 dimension modules."""
    from governance import doc_health_check
    call_count = {"n": 0}

    def fake_check(repo_root, thresholds):
        call_count["n"] += 1
        return []

    # Patch all 7 modules' check function
    for dim_name in ("d1_overlap", "d2_bloat", "d3_count_drift", "d4_path_drift",
                     "d5_frontmatter", "d6_staleness", "d7_index_consistency"):
        mod = __import__(f"governance.check_dimensions.{dim_name}", fromlist=[dim_name])
        monkeypatch.setattr(mod, "check", fake_check)

    issues = doc_health_check.run_all_dimensions(tmp_path, {})
    assert call_count["n"] == 7
    assert issues == []


def test_run_all_dimensions_crash_generates_p0_issue(tmp_path, monkeypatch):
    """If a dimension's check() crashes, a P0 issue should be generated instead of propagating."""
    from governance import doc_health_check

    def crashing_check(repo_root, thresholds):
        raise RuntimeError("simulated crash")

    # Patch first dimension to crash
    import governance.check_dimensions.d1_overlap as d1
    monkeypatch.setattr(d1, "check", crashing_check)
    # Patch others to return empty
    for dim_name in ("d2_bloat", "d3_count_drift", "d4_path_drift",
                     "d5_frontmatter", "d6_staleness", "d7_index_consistency"):
        mod = __import__(f"governance.check_dimensions.{dim_name}", fromlist=[dim_name])
        monkeypatch.setattr(mod, "check", lambda r, t: [])

    issues = doc_health_check.run_all_dimensions(tmp_path, {})
    assert len(issues) == 1
    assert issues[0].severity == "P0"
    assert "simulated crash" in issues[0].evidence
    assert issues[0].dimension == "d1_overlap"


def test_run_all_dimensions_missing_dim_key_uses_empty_dict(tmp_path, monkeypatch):
    """Regression: missing dim key in thresholds → dimension.check receives {} not full dict."""
    from governance import doc_health_check
    from governance.check_dimensions import d1_overlap
    captured_configs: list[dict] = []

    def spy(repo_root, cfg):
        captured_configs.append(cfg)
        return []

    monkeypatch.setattr(d1_overlap, 'check', spy)
    # Pass thresholds dict WITHOUT d1_overlap key
    thresholds = {"d2_bloat": {"max_lines": 1000}}  # missing d1_overlap
    doc_health_check.run_all_dimensions(tmp_path, thresholds)
    # d1_overlap.check should have received {} (empty dict), not the full thresholds
    assert len(captured_configs) == 1
    assert captured_configs[0] == {}


def test_issue_id_includes_severity():
    """Regression: same dimension/file/line/evidence but different severity → different id."""
    issue_p0 = Issue(
        dimension="d6_staleness",
        severity="P0",
        file=".ai-memory/test.md",
        evidence="last_updated=2025-01-01",
        suggested_fix="update",
        root_cause_hint="stale",
    )
    issue_p1 = Issue(
        dimension="d6_staleness",
        severity="P1",
        file=".ai-memory/test.md",
        evidence="last_updated=2025-01-01",
        suggested_fix="update",
        root_cause_hint="stale",
    )
    assert issue_p0.id != issue_p1.id
