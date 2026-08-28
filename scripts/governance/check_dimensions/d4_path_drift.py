"""d4_path_drift.py - Spec-41 dimension 4: path drift detection.

Spec-41 §3.4: scan frontmatter related_files + body paths, check existence.

Implementation note: We implement path checking directly (not subprocess to
check_path_consistency.py) because that script's main() prints unstructured
text and is geared toward pre-commit inline-path-construction checks, not
frontmatter related_files validation. Pure-Python implementation is cleaner
and faster (~0.1s vs ~0.3s subprocess).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from governance.report_schema import Issue

# Patterns for paths in markdown body (not frontmatter)
BODY_PATH_PATTERNS = [
    re.compile(r"file:///(?:/)?([^\s)]+)"),       # [link](file:///path)
    re.compile(r"`([a-zA-Z0-9_/.-]+\.(?:py|md|ts|tsx|sh|yaml|yml))`"),  # `path/to/file.py`
]


def _extract_frontmatter_paths(content: str) -> list[str]:
    """Extract paths from frontmatter related_files field."""
    if not content.startswith("---"):
        return []
    parts = content.split("---", 2)
    if len(parts) < 3:
        return []
    try:
        fm = yaml.safe_load(parts[1])
        if not isinstance(fm, dict):
            return []
        related = fm.get("related_files", [])
        if not isinstance(related, list):
            return []
        return [str(p) for p in related if isinstance(p, str)]
    except yaml.YAMLError:
        return []


def _extract_body_paths(content: str) -> list[tuple[int, str]]:
    """Extract paths from body, returning (line_no, path) tuples."""
    results: list[tuple[int, str]] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        for pattern in BODY_PATH_PATTERNS:
            for match in pattern.finditer(line):
                results.append((line_no, match.group(1)))
    return results


def check(repo_root: Path, thresholds: dict) -> list[Issue]:
    """Scan .md files for paths that point to non-existent files.

    Body-path scanning is restricted to directories whose body has "should
    exist" semantics (`.ai-memory/lessons/`, `.ai-memory/summaries/`).
    Historical record files like `docs/completed-features.md` and
    `docs/archive/active-tech-debt.md` frequently reference code paths that
    were renamed/deleted after the record was written; scanning them produces
    false positives. Frontmatter `related_files` is scanned as a contract
    (should exist), except for ``.ai-memory/evidence/`` where it is a
    historical record (spec-53: ``skip_evidence_frontmatter``).

    Spec-46: ``.ai-memory/evidence/`` uses ``evidence_severity`` (default P2)
    because evidence files are historical snapshots — ``related_files`` records
    what was changed at the time, and subsequent code refactoring should not
    require retroactive updates to evidence frontmatter.

    Spec-53: ``skip_evidence_frontmatter`` (default true) skips frontmatter
    ``related_files`` check for evidence/ files entirely. Revises spec-46:
    evidence/ ``related_files`` is a historical record (what was changed at
    the time), not a current contract (what should exist now). Path drift in
    evidence/ is expected behavior, not a defect.
    """
    issues: list[Issue] = []
    default_severity = thresholds.get("severity", "P0")
    evidence_severity = thresholds.get("evidence_severity", default_severity)
    skip_evidence_frontmatter = thresholds.get("skip_evidence_frontmatter", True)
    scan_dirs = [repo_root / "docs", repo_root / ".ai-memory", repo_root / ".skills"]
    # Only these directories have body paths with "should exist" semantics
    body_scan_prefixes = (".ai-memory/lessons/", ".ai-memory/summaries/")
    # Historical archives: related_files cite paths valid at write time; drift
    # after the fact is expected, not a defect (mirrors d3 skip semantics, s30).
    skip_dir_prefixes = (
        "docs/specs/legacy-trae/",
        "docs/specs/archived/",
    )

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for md_file in scan_dir.rglob("*.md"):
            rel = md_file.relative_to(repo_root).as_posix()
            if any(rel.startswith(prefix) for prefix in skip_dir_prefixes):
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            # Spec-46: evidence/ is a historical snapshot, use lower severity
            is_evidence = rel.startswith(".ai-memory/evidence/")
            if is_evidence:
                severity = evidence_severity
            else:
                severity = default_severity

            # Spec-53: evidence/ related_files is historical record, not contract.
            # Skip frontmatter check entirely when skip_evidence_frontmatter=true.
            skip_frontmatter = is_evidence and skip_evidence_frontmatter
            if not skip_frontmatter:
                # Check frontmatter related_files (contract — should exist)
                for path_str in _extract_frontmatter_paths(content):
                    # Normalize: strip leading ./ or /
                    # Use removeprefix (not lstrip which treats chars as a set, would truncate ".ai-memory/")
                    clean = path_str.removeprefix("./").removeprefix("/")
                    target = repo_root / clean
                    if not target.exists():
                        issues.append(Issue(
                            dimension="d4_path_drift",
                            severity=severity,
                            file=rel,
                            evidence=f"related_files entry '{path_str}' does not exist (resolved: {clean})",
                            suggested_fix="Update path or remove from related_files",
                            root_cause_hint="File moved/deleted but frontmatter not synced (spec-39 TD-281 pattern)",
                        ))

            # Check body paths only in directories with "should exist" semantics
            if not any(rel.startswith(prefix) for prefix in body_scan_prefixes):
                continue
            for line_no, path_str in _extract_body_paths(content):
                # Skip absolute system paths and URLs
                if path_str.startswith(("http://", "https://", "/")):
                    continue
                # Skip paths that look like Windows absolute (C:\)
                if len(path_str) > 1 and path_str[1] == ":":
                    continue
                target = repo_root / path_str
                if not target.exists():
                    # Only report if path looks like a real repo path (contains /)
                    # (require / to avoid false positives on bare filenames with dots)
                    if "/" in path_str:
                        issues.append(Issue(
                            dimension="d4_path_drift",
                            severity=severity,
                            file=rel,
                            line=line_no,
                            evidence=f"body path '{path_str}' does not exist",
                            suggested_fix="Update path or convert to descriptive text",
                            root_cause_hint="Stale path reference in doc body",
                        ))
    return issues
