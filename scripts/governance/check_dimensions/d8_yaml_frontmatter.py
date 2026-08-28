"""d8_yaml_frontmatter.py - s31: frontmatter YAML parseability dimension.

Scans all markdown files under .ai-memory/ and docs/ that start with `---`
and verifies the frontmatter parses as YAML. Broken YAML (e.g. unquoted
`: ` inside a scalar value, unescaped `"`) silently degrades every consumer
(sync_ai_memory, lesson-router, promote_lessons), so it must be surfaced
by the doc_health flywheel.

Distinct from d5_frontmatter: d5 checks 3-mode field compliance for
maintainer=auto/derived-manual/manual files and skips lessons/; d8 checks
syntactic parseability everywhere and never checks field presence.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from governance.report_schema import Issue


def check(repo_root: Path, thresholds: dict) -> list[Issue]:
    """Scan .md files for unparseable frontmatter YAML.

    ``thresholds`` is the d8_yaml_frontmatter sub-config, i.e.
    ``{"severity": "P1", "scan_dirs": [...], "skip_dirs": [...]}``.
    """
    issues: list[Issue] = []
    severity = thresholds.get("severity", "P1")
    scan_dirs = thresholds.get("scan_dirs") or [
        ".ai-memory",
        "docs",
        ".skills",
    ]
    skip_dir_prefixes = tuple(
        thresholds.get("skip_dirs") or [
            ".ai-memory/evidence/",  # structured snapshots, no frontmatter by design
        ]
    )

    for scan_dir in scan_dirs:
        d = repo_root / scan_dir
        if not d.exists():
            continue
        for md_file in d.rglob("*.md"):
            rel = md_file.relative_to(repo_root).as_posix()
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
                yaml.safe_load(parts[1])
            except yaml.YAMLError as exc:
                mark = getattr(exc, "problem_mark", None)
                line = mark.line + 1 if mark else None
                evidence = f"frontmatter YAML parse error: {exc}"
                if line:
                    evidence += f" (line {line})"
                issues.append(Issue(
                    dimension="d8_yaml_frontmatter",
                    severity=severity,
                    file=rel,
                    line=line,
                    evidence=evidence,
                    suggested_fix=(
                        "Quote the offending scalar value with single quotes "
                        "('...') or fix the syntax; run sync_ai_memory.py to verify"
                    ),
                    root_cause_hint=(
                        "Unquoted ': ' or '\"' inside a frontmatter scalar value "
                        "breaks YAML parsing (s31)"
                    ),
                ))
    return issues
