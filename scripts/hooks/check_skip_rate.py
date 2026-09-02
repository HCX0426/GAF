#!/usr/bin/env python3
"""
check_skip_rate.py — v8.3 bypass rate monitor.

Rules:
- Rolling window: last 30 effective commits.
- Minimum sample size: 10 effective commits (development grace period).
- Threshold: >= 30% bypass rate blocks push.
- Merge and rollback commits do not count toward the window.

Data sources:
- Git log for commit timestamps and subjects.
- GAF/.gaf_audit.log for BYPASS records.
"""
# ruff: noqa: I001  # _encoding_safe must stay first; do not reorder imports
# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout to UTF-8)

import argparse  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

# Window and threshold constants.
WINDOW = 30
MIN_COMMITS = 10
THRESHOLD = 0.30

# Repository paths.
REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_LOG = REPO_ROOT / ".gaf_audit.log"


def _git_log_commits(window: int) -> list[tuple[str, int, str]]:
    """Return recent commits as (hash, timestamp, subject) tuples."""
    cmd = [
        "git",
        "--no-pager",
        "log",
        f"-n{window}",
        "--format=%H|%ct|%s",
    ]
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        print(f"⚠️  git log failed: {result.stderr.strip()}")
        return []

    commits: list[tuple[str, int, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        commit_hash, ts_str, subject = parts
        try:
            ts = int(ts_str)
        except ValueError:
            continue
        commits.append((commit_hash, ts, subject))
    return commits


def _filter_effective_commits(
    commits: list[tuple[str, int, str]],
) -> list[tuple[str, int, str]]:
    """Exclude merge and rollback commits from the window."""
    effective = []
    for commit_hash, ts, subject in commits:
        lower = subject.lower()
        if subject.startswith("Merge") or lower.startswith("merge"):
            continue
        if "rollback" in lower or "revert" in lower:
            continue
        effective.append((commit_hash, ts, subject))
    return effective


def _load_bypass_timestamps(log_path: Path) -> list[int]:
    """Parse BYPASS lines from the audit log and return UTC timestamps."""
    if not log_path.exists():
        return []

    timestamps: list[int] = []
    # BYPASS ts=2026-06-15T18:57:59Z user=... reason=... args=...
    pattern = re.compile(r"^BYPASS\s+ts=(\S+)")
    text = log_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        ts_str = match.group(1)
        try:
            dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC
            )
            timestamps.append(int(dt.timestamp()))
        except ValueError:
            continue
    return timestamps


def compute_bypass_rate(
    effective_commits: list[tuple[str, int, str]], bypass_ts_list: list[int]
) -> tuple[int, float]:
    """Return (bypass_count, rate) for the given effective commit window."""
    if not effective_commits:
        return 0, 0.0

    commit_timestamps = [ts for _, ts, _ in effective_commits]
    min_ts = min(commit_timestamps)
    max_ts = max(commit_timestamps)

    bypass_in_window = sum(
        1 for ts in bypass_ts_list if min_ts <= ts <= max_ts
    )
    rate = bypass_in_window / len(effective_commits)
    return bypass_in_window, rate


def main(argv: list[str] = None) -> int:
    """Entry point for the bypass rate checker."""
    parser = argparse.ArgumentParser(
        description="Monitor AI bypass rate over the last N commits."
    )
    parser.add_argument(
        "--window",
        type=int,
        default=WINDOW,
        help=f"Rolling commit window (default: {WINDOW}).",
    )
    parser.add_argument(
        "--min-commits",
        type=int,
        default=MIN_COMMITS,
        help=f"Minimum effective commits before enforcing threshold (default: {MIN_COMMITS}).",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=THRESHOLD,
        help=f"Bypass rate threshold (default: {THRESHOLD}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print statistics and exit 0 without blocking.",
    )
    args = parser.parse_args(argv)

    commits = _git_log_commits(args.window)
    effective = _filter_effective_commits(commits)

    if len(effective) < args.min_commits:
        print(
            f"⚠️  Effective commit count < {args.min_commits} "
            f"({len(effective)}/{args.min_commits}), skip rate check skipped."
        )
        return 0

    bypass_ts_list = _load_bypass_timestamps(AUDIT_LOG)
    bypass_in_window, rate = compute_bypass_rate(effective, bypass_ts_list)

    print(
        f"📊 AI bypass rate: {rate:.1%} "
        f"({bypass_in_window}/{len(effective)}, window {args.window})"
    )

    if args.dry_run:
        print("🔍 Dry run mode — would not block push.")
        return 0

    if rate >= args.threshold:
        print(f"❌ Bypass rate >= {args.threshold:.0%}, push blocked.")
        print("   Suggestion: run python scripts/lessons/bypass_weekly_review.py")
        return 1

    print("✅ Bypass rate below threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
