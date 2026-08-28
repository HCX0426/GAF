"""d3_count_drift.py - Spec-41 dimension 3: hardcoded count drift detection.

Spec-41 §3.3: grep hardcoded counts and compare to actual.
"""
from __future__ import annotations

import re
from pathlib import Path

from governance.report_schema import Issue

# Map counter name → function(repo_root) -> int
from governance.check_dimensions.d3_counters import count_active_n, count_docs, count_yn_subfiles

COUNTERS = {
    "count_active_n_in_failure_modes": count_active_n,
    "count_docs_in_directory": count_docs,
    "count_yn_matrices_subfiles": count_yn_subfiles,
}


def check(repo_root: Path, thresholds: dict) -> list[Issue]:
    """Scan .md files for hardcoded counts that drift from actual.

    ``thresholds`` is the d3_count_drift sub-config (passed by run_all_dimensions),
    i.e. ``{"patterns": [...], "allow_dynamic_marker": "..."}``.
    """
    issues: list[Issue] = []
    allow_marker = thresholds.get("allow_dynamic_marker", "动态计数")
    patterns = thresholds.get("patterns", [])
    scan_dirs = [repo_root / "docs", repo_root / ".ai-memory", repo_root / ".skills"]
    # Skip historical record dirs (their hardcoded counts were correct at write
    # time but drift as the codebase evolves — false positives). Mirror d1/d2/d5/d6.
    skip_dir_prefixes = (
        ".ai-memory/evidence/",
        ".ai-memory/lessons/",  # lesson narrative often cites historical N## counts
        "docs/specs/legacy-trae/",  # spec-2026-07-26-trae-specs-plans-merge 迁移自旧 trae-specs 目录
        "docs/plans/legacy-trae/",  # spec-2026-07-26-trae-specs-plans-merge 迁移自旧 trae-plans 目录
        "docs/specs/archived/",  # archived specs cite counts valid at write time (s30)
        "docs/specs/archived-2026-07/",
    )
    skip_files = {
        "docs/archive/fixed-tech-debt.md",
        "docs/archive/wontfix-tech-debt.md",
        "docs/archive/fixed-tech-debt-details.md",  # historical TD detail snapshots (s30)
    }

    # Cache counter results within a single check() call to avoid repeated IO
    # (e.g. 100 files × 5 hardcoded counts × read failure-modes.md = 500 reads).
    counter_cache: dict[str, int] = {}

    def _get_actual(counter_name: str) -> int:
        if counter_name not in counter_cache:
            fn = COUNTERS.get(counter_name)
            counter_cache[counter_name] = fn(repo_root) if fn else 0
        return counter_cache[counter_name]

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for md_file in scan_dir.rglob("*.md"):
            rel = md_file.relative_to(repo_root).as_posix()
            if any(rel.startswith(prefix) for prefix in skip_dir_prefixes):
                continue
            if rel in skip_files:
                continue
            try:
                content = md_file.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for line_no, line in enumerate(content.splitlines(), start=1):
                if allow_marker in line:
                    continue
                for pat in patterns:
                    regex = pat["regex"]
                    counter_name = pat["counter"]
                    for match in re.finditer(regex, line):
                        # Skip matches inside git commit hashes (e.g. "3caded47 docs"
                        # where "47" is the hash tail, not a count). Check the longest
                        # hex-only run ending right before the match (s30).
                        hex_run = re.search(r"[0-9a-f]+$", line[:match.start()])
                        if hex_run and len(hex_run.group()) >= 5:
                            continue
                        # Skip "docs/..." path fragments (e.g. "L3 docs/reference/...")
                        # — the digit is a level number, not a count (s30).
                        after = line[match.end():]
                        if after.startswith("/"):
                            continue
                        hardcoded = int(match.group(1))
                        actual = _get_actual(counter_name)
                        if actual == hardcoded:
                            continue  # No drift
                        # Drift detected
                        if actual == 0:
                            # Can't verify (source file missing)
                            severity = "P2"
                            evidence = f"hardcoded '{hardcoded}' but counter '{counter_name}' returned 0 (source file missing?)"
                        else:
                            severity = "P1"
                            evidence = f"hardcoded '{hardcoded}' vs actual {actual} (counter={counter_name})"
                        issues.append(Issue(
                            dimension="d3_count_drift",
                            severity=severity,
                            file=rel,
                            line=line_no,
                            evidence=evidence,
                            suggested_fix=f"Replace hardcoded '{hardcoded}' with '{allow_marker}, by sync_ai_memory.py auto-stat' or update to {actual}",
                            root_cause_hint="New N##/doc added but hardcoded count not synced (spec-39 fixed 3, but new ones recur)",
                        ))
    return issues
