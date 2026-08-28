"""d4_path_drift Tests (split from test_doc_health_check.py, s40, TD-365 7/9)."""
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

# ---- d4_path_drift tests (Task 4) ----
from governance.check_dimensions import d4_path_drift


def test_d4_path_drift_detects_missing_related_file(tmp_path):
    """frontmatter related_files entry points to non-existent file → P0."""
    target = tmp_path / ".ai-memory/lessons/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nrelated_files:\n  - docs/standards/nonexistent.md\n---\n# Test\n",
        encoding="utf-8",
    )
    issues = d4_path_drift.check(tmp_path, {"severity": "P0"})
    assert len(issues) == 1
    assert issues[0].dimension == "d4_path_drift"
    assert issues[0].severity == "P0"
    assert "related_files" in issues[0].evidence
    assert "nonexistent.md" in issues[0].evidence


def test_d4_path_drift_valid_path_no_issue(tmp_path):
    """frontmatter related_files entry points to existing file → no issue."""
    target = tmp_path / ".ai-memory/lessons/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    real_file = tmp_path / "docs/standards/real.md"
    real_file.parent.mkdir(parents=True, exist_ok=True)
    real_file.write_text("# Real\n", encoding="utf-8")
    target.write_text(
        f"---\nrelated_files:\n  - docs/standards/real.md\n---\n# Test\n",
        encoding="utf-8",
    )
    issues = d4_path_drift.check(tmp_path, {"severity": "P0"})
    # Should not report the existing path
    assert all("real.md" not in i.evidence for i in issues)


def test_d4_path_drift_body_file_protocol_missing(tmp_path):
    """body file:/// path pointing to non-existent file → P0.

    Body scanning is restricted to .ai-memory/lessons/ and .ai-memory/summaries/
    (see d4_path_drift.check docstring), so the test file must live there.
    """
    target = tmp_path / ".ai-memory/lessons/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "See [link](file:///docs/standards/missing.md) for details.\n",
        encoding="utf-8",
    )
    issues = d4_path_drift.check(tmp_path, {"severity": "P0"})
    assert len(issues) == 1
    assert issues[0].severity == "P0"
    assert "body path" in issues[0].evidence
    assert "missing.md" in issues[0].evidence
    assert issues[0].line == 1


def test_d4_path_drift_body_backtick_path_existing_no_issue(tmp_path):
    """body `path/to/file.md` pointing to existing file → no issue.

    Body scanning is restricted to .ai-memory/lessons/ and .ai-memory/summaries/.
    """
    real_file = tmp_path / "docs/standards/real.md"
    real_file.parent.mkdir(parents=True, exist_ok=True)
    real_file.write_text("# Real\n", encoding="utf-8")
    target = tmp_path / ".ai-memory/lessons/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "See `docs/standards/real.md` for details.\n",
        encoding="utf-8",
    )
    issues = d4_path_drift.check(tmp_path, {"severity": "P0"})
    # Should not report the existing path
    assert all("real.md" not in i.evidence for i in issues)


def test_d4_path_drift_body_http_url_skipped(tmp_path):
    """body http:// URL should be skipped (not checked for existence).

    Body scanning is restricted to .ai-memory/lessons/ and .ai-memory/summaries/.
    """
    target = tmp_path / ".ai-memory/lessons/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "See https://example.com/missing.md for details.\n",
        encoding="utf-8",
    )
    issues = d4_path_drift.check(tmp_path, {"severity": "P0"})
    # URL should be skipped (note: https:// URL contains ".md" so regex matches,
    # but startswith http:// check in body loop should skip it)
    assert all("example.com" not in i.evidence for i in issues)


def test_d4_path_drift_body_skipped_in_docs_dir(tmp_path):
    """body paths in docs/ (historical record files) should NOT be scanned.

    Regression: docs/completed-features.md mentions renamed/deleted
    code paths as historical mentions; scanning them produces false positives.
    Only frontmatter related_files is checked in docs/.
    """
    target = tmp_path / "docs/completed-features.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "Past work touched `backend/ai/old_module.py` and `backend/ai/deleted.py`.\n",
        encoding="utf-8",
    )
    issues = d4_path_drift.check(tmp_path, {"severity": "P0"})
    # No frontmatter related_files → no issues from docs/ body
    assert all("old_module.py" not in i.evidence for i in issues)
    assert all("deleted.py" not in i.evidence for i in issues)


def test_d4_path_drift_ai_memory_path_not_truncated(tmp_path):
    """frontmatter related_files entry starting with .ai-memory/ should not be truncated.

    Regression test for lstrip("./") bug that treated '.' as a char-set member,
    truncating '.ai-memory/foo.md' to 'ai-memory/foo.md' (false positive).
    """
    # Create the actual file at .ai-memory/lessons/real.md
    real_file = tmp_path / ".ai-memory/lessons/real.md"
    real_file.parent.mkdir(parents=True, exist_ok=True)
    real_file.write_text("# Real\n", encoding="utf-8")
    # frontmatter references it as .ai-memory/lessons/real.md (with leading .)
    target = tmp_path / "docs/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nrelated_files:\n  - .ai-memory/lessons/real.md\n---\n# Test\n",
        encoding="utf-8",
    )
    issues = d4_path_drift.check(tmp_path, {"severity": "P0"})
    # The path EXISTS, so should NOT be reported (lstrip bug would truncate
    # .ai-memory/ to ai-memory/ and falsely report non-existence)
    assert all("real.md" not in i.evidence for i in issues), \
        f"False positive: .ai-memory/ path was truncated by lstrip bug. Issues: {issues}"


def test_d4_path_drift_dot_slash_prefix_normalized(tmp_path):
    """frontmatter related_files entry with ./ prefix should be normalized correctly."""
    real_file = tmp_path / "docs/standards/real.md"
    real_file.parent.mkdir(parents=True, exist_ok=True)
    real_file.write_text("# Real\n", encoding="utf-8")
    target = tmp_path / "docs/test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nrelated_files:\n  - ./docs/standards/real.md\n---\n# Test\n",
        encoding="utf-8",
    )
    issues = d4_path_drift.check(tmp_path, {"severity": "P0"})
    # The path EXISTS (after ./ normalization), so should NOT be reported
    assert all("real.md" not in i.evidence for i in issues)


def test_d4_path_drift_evidence_dir_skipped_by_default(tmp_path):
    """Spec-53: .ai-memory/evidence/ frontmatter skipped by default.

    skip_evidence_frontmatter defaults to true. evidence/ related_files is a
    historical record (what was changed at the time), not a current contract
    (what should exist now). Path drift in evidence/ is expected, not a defect.
    """
    target = tmp_path / ".ai-memory/evidence/2026-07-20-test/solution.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nrelated_files:\n  - scripts/nonexistent.py\n---\n# Test\n",
        encoding="utf-8",
    )
    # Default: skip_evidence_frontmatter=True → no frontmatter check
    issues = d4_path_drift.check(tmp_path, {
        "severity": "P0",
        "evidence_severity": "P2",
    })
    assert len(issues) == 0, \
        "evidence/ frontmatter must be skipped by default (skip_evidence_frontmatter=True)"


def test_d4_path_drift_evidence_frontmatter_checked_when_disabled(tmp_path):
    """Spec-53: when skip_evidence_frontmatter=False, evidence/ frontmatter is checked.

    Backward compatibility: existing configs that set skip_evidence_frontmatter=False
    keep the spec-46 behavior (evidence_severity applies to frontmatter drift).
    """
    target = tmp_path / ".ai-memory/evidence/2026-07-20-test/solution.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nrelated_files:\n  - scripts/nonexistent.py\n---\n# Test\n",
        encoding="utf-8",
    )
    issues = d4_path_drift.check(tmp_path, {
        "severity": "P0",
        "evidence_severity": "P2",
        "skip_evidence_frontmatter": False,
    })
    assert len(issues) == 1
    assert issues[0].severity == "P2", \
        "with skip_evidence_frontmatter=False, evidence/ must use evidence_severity (P2)"
    assert "nonexistent.py" in issues[0].evidence


def test_d4_path_drift_lessons_dir_keeps_default_severity(tmp_path):
    """Spec-46: .ai-memory/lessons/ keeps default severity (P0) — it is a contract.

    Lessons are "currently valid teachings"; their related_files must point to
    existing code. Path drift in lessons/ is a real contract violation (P0).
    """
    target = tmp_path / ".ai-memory/lessons/test_2026-07-20-n200-test.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nrelated_files:\n  - scripts/nonexistent.py\n---\n# Test\n",
        encoding="utf-8",
    )
    issues = d4_path_drift.check(tmp_path, {
        "severity": "P0",
        "evidence_severity": "P2",
    })
    assert len(issues) == 1
    assert issues[0].severity == "P0", \
        "lessons/ path drift must use default severity (P0), not evidence_severity"
    assert "nonexistent.py" in issues[0].evidence


def test_d4_path_drift_skips_legacy_trae_and_archived(tmp_path):
    """Regression (s30): d4 must skip legacy-trae specs and archived specs —
    their related_files cite paths valid at write time; drift is expected."""
    for rel in [
        "docs/specs/legacy-trae/2026-07-20-spec44-x.md",
        "docs/specs/archived/2026-07/2026-07-26-x.md",
    ]:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "---\nrelated_files:\n  - docs/general/nonexistent.md\n---\n# Test\n",
            encoding="utf-8",
        )
    issues = d4_path_drift.check(tmp_path, {"severity": "P0"})
    assert len(issues) == 0, f"archived/legacy specs must be skipped, got: {issues}"


def test_d4_path_drift_evidence_severity_defaults_to_severity(tmp_path):
    """Spec-46: if evidence_severity not configured, fall back to default severity.

    Backward compatibility: existing configs without evidence_severity should
    behave exactly as before (all path drift = default severity). Spec-53:
    requires skip_evidence_frontmatter=False to actually trigger the check.
    """
    target = tmp_path / ".ai-memory/evidence/2026-07-20-test/solution.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\nrelated_files:\n  - scripts/nonexistent.py\n---\n# Test\n",
        encoding="utf-8",
    )
    # No evidence_severity + skip_evidence_frontmatter=False → fall back to severity (P0)
    issues = d4_path_drift.check(tmp_path, {
        "severity": "P0",
        "skip_evidence_frontmatter": False,
    })
    assert len(issues) == 1
    assert issues[0].severity == "P0", \
        "without evidence_severity config, evidence/ should use default severity (P0)"
