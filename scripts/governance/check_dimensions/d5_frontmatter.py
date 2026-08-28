"""d5_frontmatter.py - Spec-41 dimension 5: frontmatter 3-mode compliance.

Spec-41 §3.5 / .ai-memory/README.md §1: 3 modes (auto/derived-manual/manual)
each have required fields.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from governance.report_schema import Issue


def check(repo_root: Path, thresholds: dict) -> list[Issue]:
    """Scan .md files for frontmatter not matching 3-mode spec.

    ``thresholds`` is the d5_frontmatter sub-config (passed by run_all_dimensions),
    i.e. ``{"modes": {...}, "missing_field_severity": "P1", "wrong_type_severity": "P2"}``.
    """
    issues: list[Issue] = []
    modes = thresholds.get("modes", {})
    missing_sev = thresholds.get("missing_field_severity", "P1")
    # wrong_sev reserved for future type-checking (not implemented in v1)
    # wrong_sev = thresholds.get("wrong_type_severity", "P2")

    scan_dirs = [repo_root / ".ai-memory", repo_root / "docs/standards"]
    # Skip entire subdirectories (trailing slash ensures prefix match is directory-scoped)
    skip_dir_prefixes = (".ai-memory/evidence/", ".ai-memory/lessons/")

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for md_file in scan_dir.rglob("*.md"):
            rel = md_file.relative_to(repo_root).as_posix()
            # Skip whitelisted dirs (prefix match with trailing slash to avoid false positives)
            if any(rel.startswith(prefix) for prefix in skip_dir_prefixes):
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                continue
            if not isinstance(fm, dict):
                continue
            mode = fm.get("maintainer")
            if mode not in modes:
                continue
            required = modes[mode].get("required", [])
            for field in required:
                if field not in fm:
                    issues.append(Issue(
                        dimension="d5_frontmatter",
                        severity=missing_sev,
                        file=rel,
                        evidence=f"maintainer={mode} but missing '{field}' field",
                        suggested_fix=f"Add '{field}: <value>' to frontmatter or change maintainer mode",
                        root_cause_hint="Lesson written without following 3-mode spec (spec-39 Phase 7)",
                    ))
    return issues
