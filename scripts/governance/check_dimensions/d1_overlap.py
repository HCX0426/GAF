"""d1_overlap.py - Spec-41 dimension 1: responsibility overlap (Jaccard similarity).

Spec-41 §3.1: compute pairwise Jaccard on summary keywords, report P2/P1.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import yaml

from governance.report_schema import Issue

# CJK-aware stop words
STOP_WORDS = {
    # English
    "the", "a", "an", "is", "are", "of", "in", "on", "to", "for", "and", "or", "with",
    # Chinese common
    "的", "和", "在", "是", "与", "为", "或", "等", "由", "及",
}


def _tokenize(text: str) -> set[str]:
    """Tokenize: split on non-alphanumeric/CJK, lowercase, strip stop words."""
    # Match: English words, Chinese chars (1+), numbers
    tokens = re.findall(r"[A-Za-z]+|[一-鿿]+|[0-9]+", text)
    result: set[str] = set()
    for t in tokens:
        t_lower = t.lower()
        if t_lower in STOP_WORDS:
            continue
        if len(t_lower) < 2:
            continue
        result.add(t_lower)
    return result


def _extract_summary(content: str) -> str:
    """Extract frontmatter summary field."""
    if not content.startswith("---"):
        return ""
    parts = content.split("---", 2)
    if len(parts) < 3:
        return ""
    try:
        fm = yaml.safe_load(parts[1])
        if isinstance(fm, dict):
            return str(fm.get("summary", ""))
    except yaml.YAMLError:
        pass
    return ""


def _is_whitelisted(rel_path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, p) for p in patterns)


def check(repo_root: Path, thresholds: dict) -> list[Issue]:
    """Pairwise Jaccard similarity on frontmatter summary tokens.

    ``thresholds`` is the d1_overlap sub-config (passed by run_all_dimensions),
    i.e. ``{"summary_jaccard_p2": 0.6, "summary_jaccard_p1": 0.8, "whitelist": [...]}``.
    """
    issues: list[Issue] = []
    p2_threshold = thresholds.get("summary_jaccard_p2", 0.6)
    p1_threshold = thresholds.get("summary_jaccard_p1", 0.8)
    whitelist = thresholds.get("whitelist", [])

    scan_dirs = [repo_root / "docs", repo_root / ".ai-memory"]
    # Skip entire subdirectories (trailing slash ensures prefix match is directory-scoped)
    skip_dir_prefixes = (".ai-memory/evidence/", ".ai-memory/lessons/")
    # Skip specific files (exact match only)
    skip_files = {".ai-memory/meta/archived-lessons.md"}

    # Collect (file, tokens) pairs
    files_tokens: list[tuple[str, set[str]]] = []
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
            if _is_whitelisted(rel, whitelist):
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            summary = _extract_summary(content)
            if not summary:
                continue
            tokens = _tokenize(summary)
            if len(tokens) < 2:
                continue
            files_tokens.append((rel, tokens))

    # Pairwise Jaccard (whitelisted files already filtered at collection stage)
    for i, (rel_a, tokens_a) in enumerate(files_tokens):
        for rel_b, tokens_b in files_tokens[i + 1:]:
            union = tokens_a | tokens_b
            if not union:
                continue
            intersection = tokens_a & tokens_b
            jaccard = len(intersection) / len(union)
            if jaccard < p2_threshold:
                continue
            severity = "P1" if jaccard >= p1_threshold else "P2"
            shared = sorted(intersection)[:5]  # top 5 shared keywords
            issues.append(Issue(
                dimension="d1_overlap",
                severity=severity,
                files=[rel_a, rel_b],
                evidence=f"summary Jaccard={jaccard:.2f}, shared keywords: {shared}",
                suggested_fix="Check if files should be merged, or differentiate summaries",
                root_cause_hint="Possible historical split: one for users (docs/), one for AI (.ai-memory/), but summary not differentiated",
            ))
    return issues
