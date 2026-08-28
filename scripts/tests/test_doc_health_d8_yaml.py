"""d8_yaml_frontmatter Tests (split from test_doc_health_check.py, s40, TD-365 7/9)."""
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

# ---- d8_yaml_frontmatter tests (s31) ----
from governance.check_dimensions import d8_yaml_frontmatter


def test_d8_detects_broken_yaml_scalar(tmp_path):
    """Unquoted ': ' inside a scalar value must be reported (s31)."""
    target = tmp_path / ".ai-memory/lessons/test_2026-08-17-n202-test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nsolution: 6 步超时应对: 5 段判别 → 换方式继续\n---\n# Test\n",
        encoding="utf-8",
    )
    issues = d8_yaml_frontmatter.check(tmp_path, {"severity": "P1"})
    assert len(issues) == 1
    assert issues[0].dimension == "d8_yaml_frontmatter"
    assert issues[0].severity == "P1"
    assert "YAML" in issues[0].evidence or "mapping" in issues[0].evidence


def test_d8_valid_yaml_no_issue(tmp_path):
    """Properly quoted scalar and normal frontmatter → no issues."""
    target = tmp_path / ".ai-memory/lessons/test_2026-08-17-n202-ok.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nsolution: '6 步超时应对: 5 段判别 → 换方式继续'\nrelated_files:\n  - scripts/x.py\n---\n# Test\n",
        encoding="utf-8",
    )
    issues = d8_yaml_frontmatter.check(tmp_path, {"severity": "P1"})
    assert len(issues) == 0


def test_d8_skips_evidence_dir(tmp_path):
    """evidence/ snapshots have no frontmatter by design → skipped (s31)."""
    target = tmp_path / ".ai-memory/evidence/active/test-session/problem.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# problem\n", encoding="utf-8")
    issues = d8_yaml_frontmatter.check(tmp_path, {"severity": "P1"})
    assert len(issues) == 0
