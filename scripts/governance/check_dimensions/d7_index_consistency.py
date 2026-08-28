"""d7_index_consistency.py - Spec-41 dimension 7: index consistency check.

Spec-41 §3.7: 3-way diff between failure-modes.md / lessons/README.md / yn-matrices/_*.md.
Spec-50 fix: b_minus_a uses all_known (Active + Retired + Dormant + Archived) instead of
just Active, to avoid false positives when README references family-merged / retired /
archived N## (e.g. "N126 合并 N14/N101/N128/N130" mentions in family-merge descriptions).
"""
from __future__ import annotations

import re
from pathlib import Path

from governance.report_schema import Issue

N_PATTERN = re.compile(r"\b(N\d+)\b")


def _active_n_in_failure_modes(repo_root: Path) -> set[str]:
    """Set A: Active N## in failure-modes.md (rows under "## Active N## 索引表").

    Section-scoped to exclude Retired/Dormant sections (which also use
    "| NXX |" table format but should not count as Active).
    """
    fm = repo_root / ".ai-memory/meta/failure-modes.md"
    if not fm.exists():
        return set()
    try:
        text = fm.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return set()
    result: set[str] = set()
    in_active = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_active = "Active" in line and "N##" in line
            continue
        if in_active:
            m = re.match(r"^\|\s*(N\d+)\s*\|", line)
            if m:
                result.add(m.group(1))
    return result


def _all_n_in_failure_modes(repo_root: Path) -> set[str]:
    """All N## in failure-modes.md across all sections (Active + Retired + Dormant).

    Spec-50: Used for b_minus_a check to avoid false positives when README references
    family-merged (Dormant) or M0.M-closed (Retired) N## in family-merge descriptions.
    Table-row scoped (lines starting with ``| NXX |``) to avoid matching N## in prose.
    """
    fm = repo_root / ".ai-memory/meta/failure-modes.md"
    if not fm.exists():
        return set()
    try:
        text = fm.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return set()
    result: set[str] = set()
    for line in text.splitlines():
        m = re.match(r"^\|\s*(N\d+)\s*\|", line)
        if m:
            result.add(m.group(1))
    return result


def _n_in_archived_lessons(repo_root: Path) -> set[str]:
    """N## mentioned in archived-lessons.md (true archived + dormant historical).

    Spec-50: Used for b_minus_a check to avoid false positives when README references
    N## that live only in archived-lessons.md (e.g. N30 archived, N14 dormant-historical).
    """
    al = repo_root / ".ai-memory/meta/archived-lessons.md"
    if not al.exists():
        return set()
    try:
        text = al.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return set()
    return set(N_PATTERN.findall(text))


def _n_in_lessons_readme(repo_root: Path) -> set[str]:
    """Set B: N## mentioned in lessons/README.md (body only).

    Frontmatter is excluded because metadata like ``next_n_id: 202`` would
    otherwise be matched by the N-pattern and reported as an orphan N##.
    """
    lr = repo_root / ".ai-memory/lessons/README.md"
    if not lr.exists():
        return set()
    try:
        text = lr.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return set()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            text = parts[2]
    return set(N_PATTERN.findall(text))


def _n_in_yn_matrices(repo_root: Path) -> set[str]:
    """Set C: N## referenced in yn-matrices/_*.md sub-files.

    Wave 2 (2026-07-26, spec-2026-07-26-ai-governance-execution-rate-fix):
    同时扫描 archived-yn-matrices/ 子目录, 因为 6 个归档 sub-file 仍含 N## 引用
    (作为历史 Y/N 矩阵的 evidence). 归档 sub-file 不再 active 但 N## 引用关系保留.
    """
    result: set[str] = set()
    # Active yn-matrices
    yn_dir = repo_root / ".ai-memory/meta/yn-matrices"
    if yn_dir.exists():
        for f in yn_dir.glob("_*.md"):
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            result.update(N_PATTERN.findall(text))
    # Archived yn-matrices (Wave 2 — 仍保留 N## 引用关系)
    archived_yn_dir = repo_root / ".ai-memory/meta/yn-matrices/archived-yn-matrices"
    if archived_yn_dir.exists():
        for f in archived_yn_dir.glob("_*.md"):
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            result.update(N_PATTERN.findall(text))
    return result


def check(repo_root: Path, thresholds: dict) -> list[Issue]:
    """3-way diff: failure-modes.md (A) vs lessons/README.md (B) vs yn-matrices (C).

    ``thresholds`` is the d7_index_consistency sub-config (passed by run_all_dimensions),
    i.e. ``{"a_minus_b_severity": "P1", "b_minus_a_severity": "P2", "a_minus_c_severity": "P2"}``.

    A-C drift is only checked when the yn-matrices directory exists; an absent
    directory is treated as "no constraint" rather than "empty set" to avoid
    false positives on repos that don't yet have yn-matrices sub-files.

    Spec-50: b_minus_a uses ``all_known`` (Active ∪ Retired ∪ Dormant ∪ Archived)
    instead of just ``a`` (Active). This avoids false positives when README
    references family-merged (Dormant) / M0.M-closed (Retired) / archived N## in
    family-merge descriptions (e.g. "N126 合并 N14/N101/N128/N130"). a_minus_b
    and a_minus_c still use ``a`` (Active) because new Active N## must be added
    to README and (optionally) yn-matrices.
    """
    issues: list[Issue] = []
    a = _active_n_in_failure_modes(repo_root)
    b = _n_in_lessons_readme(repo_root)

    a_minus_b = a - b
    # Spec-50: b_minus_a uses all_known to avoid false positives on
    # family-merge / retired / archived N## references in README.
    all_known = _all_n_in_failure_modes(repo_root) | _n_in_archived_lessons(repo_root)
    b_minus_a = b - all_known

    for n in sorted(a_minus_b):
        issues.append(Issue(
            dimension="d7_index_consistency",
            severity=thresholds.get("a_minus_b_severity", "P1"),
            evidence=f"{n} in failure-modes.md Active but missing from lessons/README.md",
            suggested_fix=f"Add {n} to lessons/README.md topic table",
            root_cause_hint="New N## sedimented but lessons/README.md not synced (spec-39 N176 pattern)",
        ))

    for n in sorted(b_minus_a):
        issues.append(Issue(
            dimension="d7_index_consistency",
            severity=thresholds.get("b_minus_a_severity", "P2"),
            evidence=f"{n} in lessons/README.md but not in any failure-modes.md section or archived-lessons.md (orphan)",
            suggested_fix=f"Investigate orphan N##: add {n} to failure-modes.md or remove from lessons/README.md",
            root_cause_hint="README references an N## unknown to all N## indexes (Active/Retired/Dormant/Archived)",
        ))

    # A-C drift: only check when yn-matrices dir exists (skip degenerate case)
    yn_dir = repo_root / ".ai-memory/meta/yn-matrices"
    if yn_dir.exists():
        c = _n_in_yn_matrices(repo_root)
        # Spec-53: L1-小/中 N## don't require yn-matrices (project_rules §6.2).
        # Whitelist them to avoid false positive a_minus_c P2.
        whitelist = set(thresholds.get("a_minus_c_whitelist", []))
        a_minus_c = a - c - whitelist
        for n in sorted(a_minus_c):
            issues.append(Issue(
                dimension="d7_index_consistency",
                severity=thresholds.get("a_minus_c_severity", "P2"),
                evidence=f"{n} in failure-modes.md Active but not referenced in yn-matrices/_*.md",
                suggested_fix=f"Add {n} to appropriate yn-matrices sub-file (if L1-大) or accept (L1-小/中)",
                root_cause_hint="L1-小/中 lessons don't require yn-matrices entry; verify classification",
            ))

    return issues
