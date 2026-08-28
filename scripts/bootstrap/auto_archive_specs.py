"""auto_archive_specs.py — Auto-archive completed specs from active/ to archived/.

Scans `docs/specs/active/` for markdown files that meet archive criteria and
moves them to `docs/specs/archived/<YYYY-MM>/`.

Archive triggers (any one is sufficient):
    1. Frontmatter: `archived: true`
    2. Frontmatter: `status` in (FIXED, COMPLETED, DONE, ARCHIVED, CLOSED)
       AND last modified > 1 day ago (cooldown to avoid premature archiving)

Safety:
    - Prints a plan before moving (supports --dry-run / --plan-only).
    - Verifies source exists and target does not exist before moving.
    - Supports --force to ignore the cooldown period.

Usage:
    python scripts/bootstrap/auto_archive_specs.py          # normal run
    python scripts/bootstrap/auto_archive_specs.py --plan   # show plan only
    python scripts/bootstrap/auto_archive_specs.py --force  # ignore cooldown
    python scripts/bootstrap/auto_archive_specs.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import shutil
import sys
from pathlib import Path

# N105 hook infra fix (2026-08-16): GBK console crashes on emoji/ℹ️ output
# (UnicodeEncodeError in pre-commit). Force UTF-8 so the hook is locale-safe.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACTIVE_DIR = _REPO_ROOT / "docs" / "specs" / "active"
_ARCHIVED_DIR = _REPO_ROOT / "docs" / "specs" / "archived"

# Status values that indicate completion
_COMPLETED_STATUSES = {"FIXED", "COMPLETED", "DONE", "ARCHIVED", "CLOSED", "✅ FIXED", "✅ COMPLETED", "✅ DONE"}

# Cooldown in days: a file must be stable for this long before auto-archiving
_DEFAULT_COOLDOWN_DAYS = 1


def _parse_frontmatter(text: str) -> dict:
    """Extract YAML-like frontmatter from text if present."""
    if not text.startswith("---\n"):
        return {}
    end_idx = text.find("\n---\n", 4)
    if end_idx == -1:
        return {}
    raw_fm = text[4:end_idx]
    result = {}
    for line in raw_fm.splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def _is_archive_candidate(file_path: Path, force: bool = False) -> bool:
    """Check if a single spec file is ready to be archived."""
    if not file_path.exists():
        return False

    text = file_path.read_text(encoding="utf-8")
    fm = _parse_frontmatter(text)

    # Condition 1: Explicitly marked for archiving
    if fm.get("archived", "").lower() == "true":
        return True

    # Condition 2: Status indicates completion
    status = fm.get("status", "").upper()
    if status in _COMPLETED_STATUSES:
        if force:
            return True
        # Apply cooldown: file must not be modified in last N days
        mtime = _dt.datetime.fromtimestamp(file_path.stat().st_mtime)
        if (_dt.datetime.now() - mtime).days >= _DEFAULT_COOLDOWN_DAYS:
            return True

    return False


def _move_spec_to_archive(file_path: Path) -> tuple[bool, str]:
    """Move a spec file to its monthly archive directory."""
    if not file_path.exists():
        return False, f"Source not found: {file_path}"

    # Determine target subdirectory based on file mtime
    mtime = _dt.datetime.fromtimestamp(file_path.stat().st_mtime)
    year_month = mtime.strftime("%Y-%m")
    target_dir = _ARCHIVED_DIR / year_month
    target_file = target_dir / file_path.name

    if target_file.exists():
        # If target exists, do not overwrite — skip
        return False, f"Target already exists: {target_file}, skipping to avoid overwriting."

    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(file_path), str(target_file))
    return True, f"Moved {file_path.name} -> {year_month}/{file_path.name}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-archive completed specs.")
    parser.add_argument("--plan", action="store_true", help="Show what would be done without moving files.")
    parser.add_argument("--dry-run", action="store_true", help="Same as --plan.")
    parser.add_argument("--force", action="store_true", help="Ignore the cooldown period (archive immediately).")
    args = parser.parse_args(argv)

    if not _ACTIVE_DIR.exists():
        print(f"ℹ️  No active specs directory found: {_ACTIVE_DIR}")
        return 0

    candidates = []
    for f in sorted(_ACTIVE_DIR.glob("*.md")):
        if _is_archive_candidate(f, force=args.force):
            candidates.append(f)

    if not candidates:
        print("ℹ️  No specs ready for archiving.")
        return 0

    print(f"📋 Plan to archive {len(candidates)} spec(s):")
    for c in candidates:
        mtime = _dt.datetime.fromtimestamp(c.stat().st_mtime)
        print(f"   - {c.name} (last modified: {mtime.strftime('%Y-%m-%d %H:%M')})")

    if args.plan or args.dry_run:
        print("\n(Plan only — no files were moved.)")
        return 0

    print("\n📦 Moving files...")
    success_count = 0
    for c in candidates:
        ok, msg = _move_spec_to_archive(c)
        if ok:
            print(f"   ✅ {msg}")
            success_count += 1
        else:
            print(f"   ⚠️  {msg}")

    print(f"\n✅ Archived {success_count}/{len(candidates)} spec(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
