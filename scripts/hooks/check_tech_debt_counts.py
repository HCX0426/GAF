"""check_tech_debt_counts.py — TD-319 pre-commit hook: tech-debt count drift guard.

When ``docs/archive/{active-tech-debt,fixed-tech-debt,wontfix-tech-debt}.md``
are staged for commit, this hook runs ``sync_tech_debt_counts.py --check``
to verify the tech-debt-README.md overview table still matches the actual
``^## TD-`` counts. If drift is detected, the commit is blocked with a
remediation hint.

The hook is a no-op (exit 0) when no tech-debt file is staged, so it does
not slow down unrelated commits.

Usage
-----
    python scripts/hooks/check_tech_debt_counts.py            # auto-detect staged
    python scripts/hooks/check_tech_debt_counts.py --force    # always check
    python scripts/hooks/check_tech_debt_counts.py --no-fail  # warn only

Exit codes
----------
    0 - no tech-debt files staged, OR counts consistent
    1 - drift detected (blocks commit unless --no-fail)
    2 - configuration / argument error
"""
# ruff: noqa: I001  # _encoding_safe must stay first; do not reorder imports
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout to UTF-8)

import argparse  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
SYNC_SCRIPT = REPO_ROOT_DEFAULT / "scripts" / "governance" / "sync_tech_debt_counts.py"

# Files that, when staged, should trigger the count check.
TECH_DEBT_TRIGGER_FILES = frozenset(
    {"active-tech-debt.md", "fixed-tech-debt.md", "wontfix-tech-debt.md"}
)
TECH_DEBT_PREFIX = "docs/archive/"


def _tech_debt_files_staged(repo_root: Path) -> list[str]:
    """Return the list of staged tech-debt files (relative paths).

    Uses ``git diff --cached --name-only`` so the hook only fires when a
    tech-debt file is actually part of the commit. Returns an empty list
    on any git error (fail-open: do not block unrelated commits).
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    staged: list[str] = []
    for line in result.stdout.splitlines():
        # Normalize Windows backslashes to forward slashes for prefix matching.
        normalized = line.replace("\\", "/").lstrip("./")
        if not normalized.startswith(TECH_DEBT_PREFIX):
            continue
        basename = Path(normalized).name
        if basename in TECH_DEBT_TRIGGER_FILES:
            staged.append(normalized)
    return staged


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="TD-319 pre-commit hook: tech-debt count drift guard",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run the check even when no tech-debt files are staged",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Warn-only mode: print drift but do not exit 1",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="GAF repo root (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    repo_root = Path(args.root).resolve()

    if not args.force:
        staged = _tech_debt_files_staged(repo_root)
        if not staged:
            # No tech-debt files in this commit — skip the check entirely.
            return 0

    if not SYNC_SCRIPT.is_file():
        print(
            f"ERROR: sync script not found at {SYNC_SCRIPT}",
            file=sys.stderr,
        )
        return 2

    # Delegate the consistency check to sync_tech_debt_counts.py --check.
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--check", "--root", str(repo_root)],
        cwd=str(repo_root),
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0 and not args.no_fail:
        print("", file=sys.stderr)
        print("💡 Tech-debt counts drifted. Fix with:", file=sys.stderr)
        print("   python scripts/governance/sync_tech_debt_counts.py", file=sys.stderr)
        print("   then re-stage README.md and retry the commit.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
