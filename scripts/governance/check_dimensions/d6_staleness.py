"""d6_staleness.py - Spec-41 dimension 6: document staleness via git log.

Spec-41 §3.6: last_updated + applies_to → commit lookback.
"""
from __future__ import annotations

import subprocess
from datetime import date, datetime
from pathlib import Path

import yaml

from governance.report_schema import Issue


def _parse_date(s: str) -> date | None:
    """Parse YYYY-MM-DD or ISO datetime."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _count_commits_since(repo_root: Path, since_date: date, dir_rel: str) -> int:
    """Count commits touching dir_rel since given date (commits, not file touches)."""
    try:
        result = subprocess.run(
            ["git", "log", "--since", since_date.isoformat(),
             "--pretty=format:%H", "--", dir_rel],
            cwd=repo_root, capture_output=True, text=True, encoding="utf-8", timeout=5,
        )
        # Count non-empty commit hash lines (one per commit)
        return sum(1 for line in result.stdout.splitlines() if line.strip())
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return 0


def check(repo_root: Path, thresholds: dict) -> list[Issue]:
    """Scan .md files for staleness based on last_updated + applies_to commit lookback.

    ``thresholds`` is the d6_staleness sub-config (passed by run_all_dimensions),
    i.e. ``{"stale_days_p2": 60, "stale_days_p1": 90, "stale_days_p0": 180,
            "commit_lookback": True, "applies_to_dir_mapping": {...}}``.
    """
    issues: list[Issue] = []
    p2_days = thresholds.get("stale_days_p2", 60)
    p1_days = thresholds.get("stale_days_p1", 90)
    p0_days = thresholds.get("stale_days_p0", 180)
    lookback = thresholds.get("commit_lookback", True)
    dir_mapping = thresholds.get("applies_to_dir_mapping", {})

    today = date.today()
    scan_dirs = [repo_root / "docs", repo_root / ".ai-memory"]
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
            last_updated = fm.get("last_updated")
            if not last_updated:
                continue
            lu_date = _parse_date(str(last_updated))
            if lu_date is None:
                continue
            days_since = (today - lu_date).days

            # Determine severity based on age alone
            severity: str | None = None
            if days_since >= p0_days:
                severity = "P0"
            elif days_since >= p1_days:
                severity = "P1"
            elif days_since >= p2_days:
                severity = "P2"
            if severity is None:
                continue

            # If lookback enabled, check commits touching applies_to modules
            commit_count = 0
            if lookback:
                # Use `or []` instead of `get(key, [])` because YAML `applies_to: null`
                # parses to Python None, and dict.get returns None (not default) when
                # key exists with None value — `for module in None` raises TypeError.
                applies_to = fm.get("applies_to") or []
                if isinstance(applies_to, str):
                    applies_to = [applies_to]
                for module in applies_to:
                    dir_rel = dir_mapping.get(module)
                    if dir_rel is None or dir_rel == "*":
                        continue
                    commit_count += _count_commits_since(repo_root, lu_date, dir_rel)

            # Refine severity based on commits
            if commit_count == 0:
                # No related commits → downgrade to P2 (just stale, not necessarily wrong)
                if severity in ("P0", "P1"):
                    severity = "P2"
            elif commit_count >= 5:
                severity = "P0"
            elif commit_count >= 1:
                if severity == "P2":
                    severity = "P1"

            evidence = f"last_updated={last_updated} ({days_since} days ago), {commit_count} commits touch applies_to modules since"
            issues.append(Issue(
                dimension="d6_staleness",
                severity=severity,
                file=rel,
                evidence=evidence,
                suggested_fix="Read doc + compare with recent commit diffs, update last_updated",
                root_cause_hint="Code change did not trigger doc sync (spec-42 self-evolution will close the loop)",
            ))
    return issues
