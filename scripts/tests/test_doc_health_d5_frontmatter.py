"""d5_frontmatter Tests (split from test_doc_health_check.py, s40, TD-365 7/9)."""
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

# ---- d5_frontmatter tests (Task 5) ----
from governance.check_dimensions import d5_frontmatter


def _fm_md(frontmatter: str, body: str = "# Test\n") -> str:
    return f"---\n{frontmatter}\n---\n{body}"


def test_d5_frontmatter_auto_missing_field(tmp_path):
    """auto mode missing 'auto_updated' → P1."""
    target = tmp_path / ".ai-memory/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_fm_md(
        "maintainer: auto\nsource: foo.py\ngenerated: 2026-07-19\n"
    ), encoding="utf-8")
    thresholds = {
        "modes": {
            "auto": {"required": ["maintainer", "source", "generated", "auto_updated"]},
            "derived-manual": {"required": ["maintainer", "source", "load_when"]},
            "manual": {"required": ["maintainer", "source", "created_by"]},
        },
        "missing_field_severity": "P1",
        "wrong_type_severity": "P2",
    }
    issues = d5_frontmatter.check(tmp_path, thresholds)
    assert len(issues) == 1
    assert issues[0].severity == "P1"
    assert "auto_updated" in issues[0].evidence


def test_d5_frontmatter_manual_missing_created_by(tmp_path):
    """manual mode missing 'created_by' → P1."""
    target = tmp_path / ".ai-memory/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_fm_md(
        "maintainer: manual\nsource: foo.py\nload_when: [x]\n"
    ), encoding="utf-8")
    thresholds = {
        "modes": {
            "auto": {"required": ["maintainer", "source", "generated", "auto_updated"]},
            "derived-manual": {"required": ["maintainer", "source", "load_when"]},
            "manual": {"required": ["maintainer", "source", "load_when", "created_by"]},
        },
        "missing_field_severity": "P1",
        "wrong_type_severity": "P2",
    }
    issues = d5_frontmatter.check(tmp_path, thresholds)
    assert len(issues) == 1
    assert issues[0].severity == "P1"
    assert "created_by" in issues[0].evidence


def test_d5_frontmatter_all_fields_present_no_issue(tmp_path):
    """All required fields present → no issue."""
    target = tmp_path / ".ai-memory/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_fm_md(
        "maintainer: auto\nsource: foo.py\ngenerated: 2026-07-19\nauto_updated: 2026-07-19\n"
    ), encoding="utf-8")
    thresholds = {
        "modes": {
            "auto": {"required": ["maintainer", "source", "generated", "auto_updated"]},
            "derived-manual": {"required": ["maintainer", "source"]},
            "manual": {"required": ["maintainer", "source"]},
        },
        "missing_field_severity": "P1",
        "wrong_type_severity": "P2",
    }
    issues = d5_frontmatter.check(tmp_path, thresholds)
    assert len(issues) == 0


def test_d5_frontmatter_skips_files_without_frontmatter(tmp_path):
    """File without frontmatter → no issue (not in scope)."""
    target = tmp_path / "docs/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# No frontmatter\n", encoding="utf-8")
    thresholds = {
        "modes": {"auto": {"required": ["maintainer"]}, "derived-manual": {"required": ["maintainer"]}, "manual": {"required": ["maintainer"]}},
        "missing_field_severity": "P1", "wrong_type_severity": "P2",
    }
    issues = d5_frontmatter.check(tmp_path, thresholds)
    assert len(issues) == 0
