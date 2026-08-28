"""d6_staleness Tests (split from test_doc_health_check.py, s40, TD-365 7/9)."""
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

# ---- d6_staleness tests (Task 8) ----
from governance.check_dimensions import d6_staleness


def test_d6_staleness_skips_recent_files(tmp_path):
    """File updated today → no issue."""
    target = tmp_path / ".ai-memory/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"---\nlast_updated: 2026-07-19\napplies_to: [backend]\n---\n# Test\n",
        encoding="utf-8",
    )
    thresholds = {
        "stale_days_p2": 60, "stale_days_p1": 90, "stale_days_p0": 180,
        "commit_lookback": True,
        "applies_to_dir_mapping": {"backend": "backend/", "frontend": "frontend/src/"},
    }
    issues = d6_staleness.check(tmp_path, thresholds)
    assert len(issues) == 0


def test_d6_staleness_triggers_p2_for_old_file(tmp_path):
    """File updated 90+ days ago, no recent commits touching module → P2 (just stale)."""
    target = tmp_path / ".ai-memory/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nlast_updated: 2025-01-01\napplies_to: [backend]\n---\n# Test\n",
        encoding="utf-8",
    )
    thresholds = {
        "stale_days_p2": 60, "stale_days_p1": 90, "stale_days_p0": 180,
        "commit_lookback": True,
        "applies_to_dir_mapping": {"backend": "backend/", "frontend": "frontend/src/"},
    }
    # Note: without git history, commit_lookback returns 0 → still P2 because stale_days > 60
    issues = d6_staleness.check(tmp_path, thresholds)
    # May report P2 (stale > 60 days) regardless of commits
    assert any(i.dimension == "d6_staleness" for i in issues)


def test_d6_staleness_skips_files_without_last_updated(tmp_path):
    """File without last_updated frontmatter → no issue (can't evaluate)."""
    target = tmp_path / ".ai-memory/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("---\n---\n# Test\n", encoding="utf-8")
    thresholds = {
        "stale_days_p2": 60, "stale_days_p1": 90, "stale_days_p0": 180,
        "commit_lookback": True, "applies_to_dir_mapping": {},
    }
    issues = d6_staleness.check(tmp_path, thresholds)
    assert len(issues) == 0


def test_d6_staleness_handles_null_applies_to(tmp_path):
    """Regression: frontmatter `applies_to: null` must NOT crash with TypeError.

    YAML null parses to Python None. `dict.get(key, default)` returns None
    (not default) when key exists with None value, so `for module in None`
    raises TypeError. Fix uses `fm.get('applies_to') or []` to coerce None→[].
    """
    target = tmp_path / ".ai-memory/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    # 200 days old → triggers P0 by age, then lookback tries to iterate applies_to
    target.write_text(
        "---\n"
        "last_updated: 2025-01-01\n"
        "applies_to: null\n"
        "---\n# Test\n",
        encoding="utf-8",
    )
    thresholds = {
        "stale_days_p2": 60, "stale_days_p1": 90, "stale_days_p0": 180,
        "commit_lookback": True, "applies_to_dir_mapping": {},
    }
    # Must not raise; must produce 1 issue (downgraded to P2 because commit_count=0)
    issues = d6_staleness.check(tmp_path, thresholds)
    assert len(issues) == 1
    assert issues[0].dimension == "d6_staleness"
    # No related commits → P0 downgraded to P2 (just stale, not necessarily wrong)
    assert issues[0].severity == "P2"
    assert "0 commits" in issues[0].evidence
