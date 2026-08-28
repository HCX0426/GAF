"""d3_count_drift Tests (split from test_doc_health_check.py, s40, TD-365 7/9)."""
from __future__ import annotations

import sys
import sys
from pathlib import Path

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

# ---- d3_count_drift tests (Task 3) ----
from governance.check_dimensions import d3_count_drift


def test_d3_count_drift_detects_hardcoded_n_count(tmp_path):
    """File says '2 条 Active N##' but failure-modes has 3 → P1."""
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text("## Active N## 索引表\n\n| N1 | x | y |\n| N2 | x | y |\n| N3 | x | y |\n", encoding="utf-8")
    target = tmp_path / "docs/x.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("We have 2 条 Active N## in the system.\n", encoding="utf-8")
    thresholds = {
        "patterns": [{"regex": r"(\d+)\s+(?:条\s+)?Active\s+N##",
                       "counter": "count_active_n_in_failure_modes"}],
        "allow_dynamic_marker": "动态计数",
    }
    issues = d3_count_drift.check(tmp_path, thresholds)
    assert len(issues) == 1
    assert issues[0].severity == "P1"
    # Strict assertion: evidence must mention hardcoded '2' and actual 3
    assert "hardcoded '2'" in issues[0].evidence
    assert "vs actual 3" in issues[0].evidence


def test_d3_count_drift_skips_dynamic_marker(tmp_path):
    """Line with hardcoded number AND '动态计数' marker → skipped (no issue)."""
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text("| N1 | x | y |\n", encoding="utf-8")
    target = tmp_path / "docs/x.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    # Line has hardcoded 99 (would drift from actual=1) but also has the marker → must be skipped
    target.write_text("We have 99 条 Active N## (动态计数, by gaf_init.sh)\n", encoding="utf-8")
    thresholds = {
        "patterns": [{"regex": r"(\d+)\s+(?:条\s+)?Active\s+N##",
                       "counter": "count_active_n_in_failure_modes"}],
        "allow_dynamic_marker": "动态计数",
    }
    issues = d3_count_drift.check(tmp_path, thresholds)
    # Marker present → line skipped → no issue (despite hardcoded 99 != actual 1)
    assert len(issues) == 0


def test_d3_count_drift_no_issue_when_count_matches(tmp_path):
    """Hardcoded count matches actual count → no issue (no drift)."""
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text("## Active N## 索引表\n\n| N1 | x | y |\n| N2 | x | y |\n| N3 | x | y |\n", encoding="utf-8")
    target = tmp_path / "docs/x.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    # Hardcoded 3 matches actual count (3 N## rows) → no drift
    target.write_text("We have 3 条 Active N## in the system.\n", encoding="utf-8")
    thresholds = {
        "patterns": [{"regex": r"(\d+)\s+(?:条\s+)?Active\s+N##",
                       "counter": "count_active_n_in_failure_modes"}],
        "allow_dynamic_marker": "动态计数",
    }
    issues = d3_count_drift.check(tmp_path, thresholds)
    assert len(issues) == 0


def test_d3_count_drift_handles_missing_failure_modes(tmp_path):
    """If failure-modes.md missing, hardcoded count → P2 (can't verify)."""
    target = tmp_path / "docs/x.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("We have 51 条 Active N##.\n", encoding="utf-8")
    thresholds = {
        "patterns": [{"regex": r"(\d+)\s+(?:条\s+)?Active\s+N##",
                       "counter": "count_active_n_in_failure_modes"}],
        "allow_dynamic_marker": "动态计数",
    }
    issues = d3_count_drift.check(tmp_path, thresholds)
    assert len(issues) == 1
    assert issues[0].severity == "P2"  # Can't verify, but still hardcoded


def test_d3_count_drift_skips_git_hash_tail(tmp_path):
    """Regression (s30): digits that are the tail of a git commit hash
    (e.g. "3caded47 docs" — "47" is the hash tail) must not be reported as
    a hardcoded count. Also "docs/..." path fragments (e.g. "L3 docs/reference/")
    where the digit is a level number must be skipped."""
    target = tmp_path / "docs/x.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "- 3caded47 docs(tech-debt): sync status\n"
        "- fd4021d6 docs(tech-debt): clean up\n"
        "- L3 docs/reference/data-flow.md (level marker, not count)\n"
        "- There are 12 docs total.\n",
        encoding="utf-8",
    )
    thresholds = {
        "patterns": [{"regex": r"(\d+)\s+docs",
                       "counter": "count_docs_in_directory"}],
        "allow_dynamic_marker": "动态计数",
    }
    issues = d3_count_drift.check(tmp_path, thresholds)
    # Only "12 docs" is a real count; hash tails and path fragments are skipped
    assert len(issues) == 1, f"expected 1 issue (12 vs actual), got: {issues}"
    assert "12" in issues[0].evidence

def test_d3_count_drift_skips_historical_dirs(tmp_path):
    """Regression: d3 must skip .ai-memory/evidence/, .trae/specs/, fixed.md."""
    # Set up: 1 hardcoded count in evidence/ (historical, should be skipped)
    # + 1 hardcoded count in meta/ (current, should be checked)
    evidence_file = tmp_path / ".ai-memory/evidence/2026-07-17-test/solution.md"
    evidence_file.parent.mkdir(parents=True, exist_ok=True)
    evidence_file.write_text(
        "All 51 条 Active N## are listed.\n", encoding="utf-8",
    )
    meta_file = tmp_path / ".ai-memory/meta/test.md"
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(
        "Currently 99 条 Active N## are listed.\n", encoding="utf-8",
    )
    # Set up: failure-modes.md with 1 Active N## (actual count = 1)
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.write_text(
        "## Active N## 索引表\n\n| N## |\n|:---:|\n| N1 |\n",
        encoding="utf-8",
    )
    thresholds = {
        "patterns": [{"regex": r"(\d+)\s*条\s*Active\s*N##", "counter": "count_active_n_in_failure_modes"}],
        "allow_dynamic_marker": "动态计数",
    }
    issues = d3_count_drift.check(tmp_path, thresholds)
    # Only meta/test.md should be checked; evidence/ must be skipped
    files_reported = {i.file for i in issues}
    assert ".ai-memory/meta/test.md" in files_reported
    assert ".ai-memory/evidence/2026-07-17-test/solution.md" not in files_reported


def test_d3_count_drift_skips_archived_snapshot_files(tmp_path):
    """Regression (s30): d3 must skip archived spec dirs and fixed-tech-debt-details.md
    — historical snapshots cite counts valid at write time."""
    archived_spec = tmp_path / "docs/specs/archived/2026-07/x.md"
    archived_spec.parent.mkdir(parents=True, exist_ok=True)
    archived_spec.write_text("We have 51 条 Active N##.\n", encoding="utf-8")
    details = tmp_path / "docs/archive/fixed-tech-debt-details.md"
    details.parent.mkdir(parents=True, exist_ok=True)
    details.write_text("We have 51 条 Active N##.\n", encoding="utf-8")
    active_file = tmp_path / "docs/archive/active-tech-debt.md"
    active_file.write_text("We have 51 条 Active N##.\n", encoding="utf-8")
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text("## Active N## 索引表\n\n| N1 |\n", encoding="utf-8")
    thresholds = {
        "patterns": [{"regex": r"(\d+)\s*条\s*Active\s*N##", "counter": "count_active_n_in_failure_modes"}],
        "allow_dynamic_marker": "动态计数",
    }
    issues = d3_count_drift.check(tmp_path, thresholds)
    files_reported = {i.file for i in issues}
    assert "docs/specs/archived/2026-07/x.md" not in files_reported, \
        f"archived spec must be skipped, got: {files_reported}"
    assert "docs/archive/fixed-tech-debt-details.md" not in files_reported, \
        f"fixed-tech-debt-details.md must be skipped, got: {files_reported}"
    assert "docs/archive/active-tech-debt.md" in files_reported
