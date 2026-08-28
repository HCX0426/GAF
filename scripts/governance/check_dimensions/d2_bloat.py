"""d2_bloat.py - Spec-41 dimension 2: file bloat (line count) detection.

Spec-41 §3.2: severity = ratio-based (1.5x→P2, 2.0x→P1, 3.0x→P0).
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

from governance.report_schema import Issue


def _get_threshold(file_rel: str, thresholds: dict) -> int:
    """Get per-file threshold; supports glob patterns."""
    per_file = thresholds.get("per_file_thresholds", {})
    # Try exact match first
    if file_rel in per_file:
        return per_file[file_rel]
    # Try glob patterns
    for pattern, threshold in per_file.items():
        if pattern == "default":
            continue
        if fnmatch.fnmatch(file_rel, pattern):
            return threshold
    return per_file.get("default", 1000)


def _severity_for_ratio(ratio: float, mults: dict) -> str | None:
    """Return severity based on ratio and severity_multipliers."""
    if ratio >= mults.get("p0", 3.0):
        return "P0"
    if ratio >= mults.get("p1", 2.0):
        return "P1"
    if ratio >= mults.get("p2", 1.5):
        return "P2"
    return None


def check(repo_root: Path, thresholds: dict) -> list[Issue]:
    """Scan all .md files and report those exceeding line thresholds.

    ``thresholds`` is the d2_bloat sub-config (passed by run_all_dimensions),
    i.e. ``{"per_file_thresholds": {...}, "severity_multipliers": {...}}``.
    """
    issues: list[Issue] = []
    mults = thresholds.get("severity_multipliers", {"p2": 1.5, "p1": 2.0, "p0": 3.0})

    scan_dirs = [repo_root / "docs", repo_root / ".ai-memory", repo_root / ".skills"]
    # Skip entire subdirectories (trailing slash ensures prefix match is directory-scoped)
    skip_dir_prefixes = (".ai-memory/lessons/", ".ai-memory/evidence/")
    # Skip specific files (exact match only)
    skip_files = {".ai-memory/meta/archived-lessons.md"}

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for md_file in scan_dir.rglob("*.md"):
            rel = md_file.relative_to(repo_root).as_posix()
            # Skip whitelisted dirs (prefix match with trailing slash to avoid false positives)
            if any(rel.startswith(prefix) for prefix in skip_dir_prefixes):
                continue
            # Skip whitelisted files (exact match)
            if rel in skip_files:
                continue
            try:
                with md_file.open(encoding="utf-8") as f:
                    line_count = sum(1 for _ in f)
            except (UnicodeDecodeError, OSError):
                continue
            threshold = _get_threshold(rel, thresholds)
            ratio = line_count / threshold if threshold > 0 else 0
            severity = _severity_for_ratio(ratio, mults)
            if severity is None:
                continue
            issues.append(Issue(
                dimension="d2_bloat",
                severity=severity,
                file=rel,
                evidence=f"{line_count} lines, threshold={threshold}, ratio={ratio:.2f}x (severity={severity})",
                suggested_fix=f"Split file by topic or raise threshold in thresholds.yaml if intentional",
                root_cause_hint="Historical accumulation: multiple spec fixes appended content without splitting",
            ))
    return issues
