"""d7_index_consistency Tests (split from test_doc_health_check.py, s40, TD-365 7/9)."""
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

# ---- d7_index_consistency tests (Task 6) ----
from governance.check_dimensions import d7_index_consistency


def test_d7_n_in_failure_modes_missing_from_lessons_readme(tmp_path):
    """N176 in failure-modes Active but not in lessons/README.md topic → P1."""
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text("## Active N## 索引表\n\n| N176 | x | y |\n", encoding="utf-8")
    lr = tmp_path / ".ai-memory/lessons/README.md"
    lr.parent.mkdir(parents=True, exist_ok=True)
    lr.write_text("| `workflow` | desc | N95, N105 | 2 | x |\n", encoding="utf-8")
    thresholds = {"a_minus_b_severity": "P1", "b_minus_a_severity": "P2", "a_minus_c_severity": "P2"}
    issues = d7_index_consistency.check(tmp_path, thresholds)
    assert any(i.severity == "P1" and "N176" in i.evidence for i in issues)


def test_d7_archived_n_still_in_lessons_readme(tmp_path):
    """N in lessons/README.md but not in failure-modes → P2."""
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text("## Active N## 索引表\n\n| N176 | x | y |\n", encoding="utf-8")
    lr = tmp_path / ".ai-memory/lessons/README.md"
    lr.parent.mkdir(parents=True, exist_ok=True)
    lr.write_text("| `workflow` | desc | N176, N999 | 2 | x |\n", encoding="utf-8")  # N999 not in failure-modes
    thresholds = {"a_minus_b_severity": "P1", "b_minus_a_severity": "P2", "a_minus_c_severity": "P2"}
    issues = d7_index_consistency.check(tmp_path, thresholds)
    assert any(i.severity == "P2" and "N999" in i.evidence for i in issues)


def test_d7_no_drift_no_issues(tmp_path):
    """All N## in sync → no issues."""
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text("## Active N## 索引表\n\n| N176 | x | y |\n", encoding="utf-8")
    lr = tmp_path / ".ai-memory/lessons/README.md"
    lr.parent.mkdir(parents=True, exist_ok=True)
    lr.write_text("| `workflow` | desc | N176 | 1 | x |\n", encoding="utf-8")
    thresholds = {"a_minus_b_severity": "P1", "b_minus_a_severity": "P2", "a_minus_c_severity": "P2"}
    issues = d7_index_consistency.check(tmp_path, thresholds)
    assert len(issues) == 0


def test_d7_active_n_missing_from_yn_matrices(tmp_path):
    """N## in failure-modes Active but not referenced in yn-matrices/_*.md → P2.

    Covers the A-C drift path (yn_dir.exists() guard enters, _n_in_yn_matrices
    helper exercised). This is the 3rd leg of the 3-way diff per spec-41 §3.7.
    """
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text("## Active N## 索引表\n\n| N176 | x | y |\n| N999 | x | y |\n", encoding="utf-8")
    lr = tmp_path / ".ai-memory/lessons/README.md"
    lr.parent.mkdir(parents=True, exist_ok=True)
    # B contains both N176 and N999 (so A-B is empty, isolating A-C drift)
    lr.write_text("| `workflow` | desc | N176, N999 | 2 | x |\n", encoding="utf-8")
    # yn-matrices dir exists but only references N176 (N999 is the drift)
    yn_dir = tmp_path / ".ai-memory/meta/yn-matrices"
    yn_dir.mkdir(parents=True, exist_ok=True)
    (yn_dir / "_workflow.md").write_text("- N176 (some ref)\n", encoding="utf-8")
    thresholds = {"a_minus_b_severity": "P1", "b_minus_a_severity": "P2", "a_minus_c_severity": "P2"}
    issues = d7_index_consistency.check(tmp_path, thresholds)
    # N999 in A but not in C → P2 (a_minus_c drift)
    assert any(i.severity == "P2" and "N999" in i.evidence and "yn-matrices" in i.evidence for i in issues), \
        f"Expected P2 issue for N999 A-C drift, got: {issues}"
    # N176 should NOT be reported (it's in all 3 sets)
    assert all("N176" not in i.evidence for i in issues), \
        f"N176 should not be reported (in sync), got: {issues}"


def test_d7_a_minus_c_whitelist_skips_l1_small_medium(tmp_path):
    """Spec-53: L1-小/中 N## don't require yn-matrices (project_rules §6.2).

    a_minus_c_whitelist removes N## from the A-C drift check. L1-小/中 lessons
    only update rules + handbook (2-3 layers), not yn-matrices. Without the
    whitelist, these N## would produce false positive a_minus_c P2 issues.
    """
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    # N121 (L1-中, whitelisted) + N999 (not whitelisted, should be reported)
    fm.write_text("## Active N## 索引表\n\n| N121 | x | y |\n| N999 | x | y |\n", encoding="utf-8")
    lr = tmp_path / ".ai-memory/lessons/README.md"
    lr.parent.mkdir(parents=True, exist_ok=True)
    lr.write_text("| `workflow` | desc | N121, N999 | 2 | x |\n", encoding="utf-8")
    yn_dir = tmp_path / ".ai-memory/meta/yn-matrices"
    yn_dir.mkdir(parents=True, exist_ok=True)
    (yn_dir / "_workflow.md").write_text("# empty\n", encoding="utf-8")
    thresholds = {
        "a_minus_b_severity": "P1",
        "b_minus_a_severity": "P2",
        "a_minus_c_severity": "P2",
        "a_minus_c_whitelist": ["N121"],  # spec-53 whitelist
    }
    issues = d7_index_consistency.check(tmp_path, thresholds)
    # N121 in whitelist → NOT reported
    assert all("N121" not in i.evidence for i in issues), \
        f"N121 is whitelisted (L1-中), should not be reported, got: {issues}"
    # N999 not in whitelist → still reported as P2
    assert any(i.severity == "P2" and "N999" in i.evidence and "yn-matrices" in i.evidence for i in issues), \
        f"N999 not whitelisted, should be reported as P2, got: {issues}"

# ===== TD-283/284/285/286 regression tests (Spec-41 final code review) =====


def test_count_active_n_excludes_retired_section(tmp_path):
    """Regression: count_active_n must only count Active section, not Retired/Dormant."""
    from governance.check_dimensions.d3_counters import count_active_n
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text(
        "# failure-modes.md\n\n"
        "## Active N## 索引表\n\n"
        "| N## | 主题 | 硬约束 | Lesson 链接 |\n"
        "|:---:|------|--------|-------------|\n"
        "| N1 | active one | constraint | lesson.md |\n"
        "| N2 | active two | constraint | lesson.md |\n"
        "\n"
        "## Retired N## 索引\n\n"
        "| N## | 主题 | 沉淀位置 | 闭环原因 |\n"
        "|:---:|------|---------|---------|\n"
        "| N96 | retired one | rules | M0.M |\n"
        "| N97 | retired two | rules | M0.M |\n"
        "\n"
        "## Dormant N## 索引\n\n"
        "| N## | 主题 | 家族主条目 | Y/N 矩阵 |\n"
        "|:---:|------|-----------|----------|\n"
        "| N119 | dormant one | N95 | _workflow.md |\n",
        encoding="utf-8",
    )
    assert count_active_n(tmp_path) == 2  # only N1 + N2, not N96/N97/N119


def test_d7_excludes_retired_section_from_set_a(tmp_path):
    """Regression: d7 Set A must only include Active section N##."""
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text(
        "## Active N## 索引表\n\n"
        "| N## | 主题 |\n"
        "|:---:|------|\n"
        "| N1 | active |\n"
        "\n"
        "## Retired N## 索引\n\n"
        "| N## | 主题 |\n"
        "|:---:|------|\n"
        "| N96 | retired |\n",
        encoding="utf-8",
    )
    # Set A should contain N1 only, not N96
    from governance.check_dimensions.d7_index_consistency import _active_n_in_failure_modes
    a = _active_n_in_failure_modes(tmp_path)
    assert "N1" in a
    assert "N96" not in a


def test_d7_b_minus_a_uses_all_known_not_just_active(tmp_path):
    """Spec-50 regression: b_minus_a must use all_known (Active + Retired + Dormant + Archived),
    not just Active. Otherwise family-merge mentions in README (e.g. "N126 合并 N14/N101")
    trigger false positives when N14/N101 live in §Dormant/§Retired/archived-lessons.md.
    """
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text(
        "## Active N## 索引表\n\n"
        "| N## | 主题 |\n"
        "|:---:|------|\n"
        "| N126 | active |\n"
        "\n"
        "## Retired N## 索引\n\n"
        "| N## | 主题 |\n"
        "|:---:|------|\n"
        "| N101 | retired |\n"
        "\n"
        "## Dormant N## 索引\n\n"
        "| N## | 主题 |\n"
        "|:---:|------|\n"
        "| N14 | dormant |\n",
        encoding="utf-8",
    )
    # README mentions N126 (Active) + N101 (Retired) + N14 (Dormant) — all legitimate
    lr = tmp_path / ".ai-memory/lessons/README.md"
    lr.parent.mkdir(parents=True, exist_ok=True)
    lr.write_text(
        "| `honest-status` | desc | N126 | 1 | x |\n"
        "- N126 family (合并 N14/N101)\n",
        encoding="utf-8",
    )
    # No archived-lessons.md in tmp_path → _n_in_archived_lessons returns empty set
    thresholds = {"a_minus_b_severity": "P1", "b_minus_a_severity": "P2", "a_minus_c_severity": "P2"}
    issues = d7_index_consistency.check(tmp_path, thresholds)
    # N14 (Dormant) + N101 (Retired) should NOT trigger b_minus_a
    b_minus_a_issues = [i for i in issues if "orphan" in i.evidence]
    assert all("N14" not in i.evidence for i in b_minus_a_issues), \
        f"N14 (Dormant) should not be flagged as orphan, got: {b_minus_a_issues}"
    assert all("N101" not in i.evidence for i in b_minus_a_issues), \
        f"N101 (Retired) should not be flagged as orphan, got: {b_minus_a_issues}"


def test_d7_b_minus_a_catches_true_orphan(tmp_path):
    """Spec-50 regression: b_minus_a still catches true orphan N## (not in any section
    of failure-modes.md, not in archived-lessons.md).
    """
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text(
        "## Active N## 索引表\n\n"
        "| N## | 主题 |\n"
        "|:---:|------|\n"
        "| N126 | active |\n",
        encoding="utf-8",
    )
    # README mentions N999 which is nowhere in failure-modes.md or archived-lessons.md
    lr = tmp_path / ".ai-memory/lessons/README.md"
    lr.parent.mkdir(parents=True, exist_ok=True)
    lr.write_text("| `topic` | desc | N126, N999 | 2 | x |\n", encoding="utf-8")
    thresholds = {"a_minus_b_severity": "P1", "b_minus_a_severity": "P2", "a_minus_c_severity": "P2"}
    issues = d7_index_consistency.check(tmp_path, thresholds)
    # N999 should trigger b_minus_a (true orphan)
    assert any("N999" in i.evidence and "orphan" in i.evidence for i in issues), \
        f"N999 (true orphan) should be flagged, got: {issues}"


def test_d7_b_minus_a_uses_archived_lessons(tmp_path):
    """Spec-50 regression: N## only in archived-lessons.md should not trigger b_minus_a."""
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text("## Active N## 索引表\n\n| N126 | active |\n", encoding="utf-8")
    # N30 only in archived-lessons.md (true archived)
    al = tmp_path / ".ai-memory/meta/archived-lessons.md"
    al.parent.mkdir(parents=True, exist_ok=True)
    al.write_text("## 归档 N## 索引表\n\n| N30 | archived |\n", encoding="utf-8")
    lr = tmp_path / ".ai-memory/lessons/README.md"
    lr.parent.mkdir(parents=True, exist_ok=True)
    lr.write_text("- N30 (archived reference in README)\n", encoding="utf-8")
    thresholds = {"a_minus_b_severity": "P1", "b_minus_a_severity": "P2", "a_minus_c_severity": "P2"}
    issues = d7_index_consistency.check(tmp_path, thresholds)
    b_minus_a_issues = [i for i in issues if "orphan" in i.evidence]
    assert all("N30" not in i.evidence for i in b_minus_a_issues), \
        f"N30 (in archived-lessons.md) should not be flagged as orphan, got: {b_minus_a_issues}"


def test_d7_readme_frontmatter_next_n_id_not_orphan(tmp_path):
    """Regression (s30): lessons/README.md frontmatter ``next_n_id: 202`` must not
    be reported as an orphan N##. Frontmatter metadata is not a lesson reference.
    """
    fm = tmp_path / ".ai-memory/meta/failure-modes.md"
    fm.parent.mkdir(parents=True, exist_ok=True)
    fm.write_text(
        "## Active N## 索引表\n\n"
        "| N## | 主题 |\n"
        "|:---:|------|\n"
        "| N126 | active |\n",
        encoding="utf-8",
    )
    lr = tmp_path / ".ai-memory/lessons/README.md"
    lr.parent.mkdir(parents=True, exist_ok=True)
    lr.write_text(
        "---\n"
        "next_n_id: 202\n"
        "---\n"
        "| `topic` | desc | N126 | 1 | x |\n",
        encoding="utf-8",
    )
    thresholds = {"a_minus_b_severity": "P1", "b_minus_a_severity": "P2", "a_minus_c_severity": "P2"}
    issues = d7_index_consistency.check(tmp_path, thresholds)
    orphan_issues = [i for i in issues if "orphan" in i.evidence]
    assert all("N202" not in i.evidence for i in orphan_issues), \
        f"N202 (frontmatter next_n_id) should not be flagged as orphan, got: {orphan_issues}"
