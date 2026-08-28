"""check_change_scope.py — 客观判定 git 变更范围 (small / medium / big)

基于量化指标自动判断变更规模, 为治理流程提供决策依据:
- big:   diff_lines > 1500 OR apps_affected > 5 OR has_migration OR api_contract_changed
- medium: diff_lines > 50  OR apps_affected > 2
- small:  其余

Usage:
    python scripts/governance/check_change_scope.py
    python scripts/governance/check_change_scope.py --staged-only
    python scripts/governance/check_change_scope.py --diff-lines 230
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

APP_PREFIXES = ["backend/", "agent/", "frontend/", "scripts/"]

DIFF_LINES_BIG = 1500
DIFF_LINES_MEDIUM = 50
APPS_AFFECTED_BIG = 5
APPS_AFFECTED_MEDIUM = 2


def _run_git_diff(name_only: bool, staged_only: bool) -> tuple[int, list[str]]:
    """Run git diff and return (total_diff_lines, changed_files)."""
    cmd = ["git", "diff"]
    if staged_only:
        cmd.append("--cached")

    try:
        if name_only:
            result = subprocess.run(
                cmd + ["--name-only"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            return 0, files
        else:
            result = subprocess.run(
                cmd + ["--shortstat"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            stdout = result.stdout
            ins = 0
            dele = 0
            m = re.search(r"(\d+) insertion", stdout)
            if m:
                ins = int(m.group(1))
            m = re.search(r"(\d+) deletion", stdout)
            if m:
                dele = int(m.group(1))
            return ins + dele, []
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"git diff failed: {e}", file=sys.stderr)
        return 0, []


def get_changed_files(staged_only: bool) -> list[str]:
    """Return list of changed file paths."""
    _, files = _run_git_diff(name_only=True, staged_only=staged_only)
    return files


def get_diff_lines(staged_only: bool) -> int:
    """Return total diff line count (insertions + deletions)."""
    diff_lines, _ = _run_git_diff(name_only=False, staged_only=staged_only)
    return diff_lines


def detect_apps(files: list[str]) -> list[str]:
    """Detect affected apps by file path prefix."""
    apps: set[str] = set()
    for f in files:
        for prefix in APP_PREFIXES:
            if f.startswith(prefix):
                apps.add(prefix.rstrip("/"))
                break
    return sorted(apps)


def has_migration(files: list[str]) -> bool:
    """Check if any migration files changed."""
    return any("migrations/" in f for f in files)


def has_api_contract_changes(files: list[str]) -> bool:
    """Check if any API contract files changed."""
    return any(
        f.endswith("urls.py") or f.endswith("serializers.py")
        for f in files
    )


def determine_scope(
    diff_lines: int,
    apps_affected: list[str],
    migration: bool,
    api_contract: bool,
) -> str:
    """Determine scope based on quantitative thresholds."""
    if (
        diff_lines > DIFF_LINES_BIG
        or len(apps_affected) > APPS_AFFECTED_BIG
        or migration
        or api_contract
    ):
        return "big"
    if diff_lines > DIFF_LINES_MEDIUM or len(apps_affected) > APPS_AFFECTED_MEDIUM:
        return "medium"
    return "small"


def compute_required_checks(scope: str) -> dict[str, bool]:
    """Compute required governance checks based on scope."""
    return {
        "seven_dim": scope == "big",
        "dual_debug": scope in ("big", "medium"),
        "l3_scan": scope == "big",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="客观判定 git 变更范围 (small / medium / big)"
    )
    parser.add_argument(
        "--diff-lines",
        type=int,
        default=None,
        help="绕过 git diff 计算, 直接指定 diff 总行数",
    )
    parser.add_argument(
        "--staged-only",
        action="store_true",
        default=False,
        help="仅检查 staged 改动 (默认: staged + unstaged)",
    )
    args = parser.parse_args(argv)

    files = get_changed_files(staged_only=args.staged_only)

    if args.diff_lines is not None:
        diff_lines = args.diff_lines
    else:
        diff_lines = get_diff_lines(staged_only=args.staged_only)

    apps_affected = detect_apps(files)
    migration = has_migration(files)
    api_contract = has_api_contract_changes(files)

    scope = determine_scope(
        diff_lines, apps_affected, migration, api_contract
    )

    required_checks = compute_required_checks(scope)

    result: dict[str, Any] = {
        "scope": scope,
        "diff_lines": diff_lines,
        "files_changed": len(files),
        "apps_affected": apps_affected,
        "has_migration": migration,
        "api_contract_changed": api_contract,
        "required_checks": required_checks,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())