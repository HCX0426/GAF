"""Evidence lifecycle management — archive old evidence and prune stale archives.

Implements the forgetting mechanism for `.ai-memory/evidence/` described in
TD-252. Three modes (default: `archive`):

  archive  — move evidence dirs older than --archive-days (default 30) into
             `.ai-memory/evidence/archived/<YYYY-MM>/`. Git-tracked, so the
             move is reversible via git history.
  prune    — delete archived evidence dirs older than --prune-days (default
             90). Deletion is irreversible locally, but git history still
             retains the content.
  status   — print a summary: total dirs, archived dirs, oldest active,
             oldest archived, candidates for archive / prune.

Usage:
  python scripts/bootstrap/archive_evidence.py status
  python scripts/bootstrap/archive_evidence.py archive --dry-run
  python scripts/bootstrap/archive_evidence.py archive --apply
  python scripts/bootstrap/archive_evidence.py prune --dry-run
  python scripts/bootstrap/archive_evidence.py prune --apply

The script never touches the `templates/` directory (canonical evidence
templates must persist). It also refuses to prune without --apply (dry-run
is the default to prevent accidental data loss).
"""

from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

# Bootstrap — allow importing scripts.* libraries when run from repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts._encoding_safe import force_utf8_stdout  # noqa: E402

force_utf8_stdout()

EVIDENCE_DIR = _REPO_ROOT / ".ai-memory" / "evidence"
ARCHIVED_DIR = EVIDENCE_DIR / "archived"
TEMPLATES_DIR = EVIDENCE_DIR / "templates"
DEFAULT_ARCHIVE_DAYS = 30
DEFAULT_PRUNE_DAYS = 90


def _parse_dir_date(dir_path: Path) -> dt.date | None:
    """Extract the leading YYYY-MM-DD from an evidence dir name.

    Evidence dirs follow `<date>-<topic>` (e.g. `2026-07-15-p010-phase1-schema`).
    Returns None if the name doesn't start with a parseable date — callers
    treat None as "skip this dir" (e.g. `archived/`, `templates/`).
    """
    name = dir_path.name
    prefix = name[:10]
    try:
        return dt.datetime.strptime(prefix, "%Y-%m-%d").date()
    except ValueError:
        return None


def _list_evidence_dirs() -> list[Path]:
    """List top-level evidence dirs (exclude archived/ and templates/)."""
    if not EVIDENCE_DIR.is_dir():
        return []
    return [
        p
        for p in EVIDENCE_DIR.iterdir()
        if p.is_dir() and p.name not in ("archived", "templates")
    ]


def _list_archived_dirs() -> list[Path]:
    """List dirs under archived/ (expected layout: archived/<YYYY-MM>/<evidence>/)."""
    if not ARCHIVED_DIR.is_dir():
        return []
    out: list[Path] = []
    for month_dir in ARCHIVED_DIR.iterdir():
        if not month_dir.is_dir():
            continue
        out.extend(p for p in month_dir.iterdir() if p.is_dir())
    return out


def _age_days(d: dt.date) -> int:
    return (dt.date.today() - d).days


def _archive_month(d: dt.date) -> str:
    return d.strftime("%Y-%m")


def _display(path: Path) -> str:
    """Format a path for display.

    Prefers a path relative to EVIDENCE_DIR (so tests that patch
    EVIDENCE_DIR to a tempdir still get readable output). Falls back
    to the absolute path when the path is not under EVIDENCE_DIR.
    """
    try:
        return str(path.relative_to(EVIDENCE_DIR))
    except ValueError:
        return str(path)


def cmd_status() -> int:
    active = _list_evidence_dirs()
    archived = _list_archived_dirs()
    active_dates = [d for d in (_parse_dir_date(p) for p in active) if d]
    archived_dates = [d for d in (_parse_dir_date(p) for p in archived) if d]

    archive_candidates = [p for p in active if (d := _parse_dir_date(p)) and _age_days(d) >= DEFAULT_ARCHIVE_DAYS]
    prune_candidates = [p for p in archived if (d := _parse_dir_date(p)) and _age_days(d) >= DEFAULT_PRUNE_DAYS]

    print(f"Evidence root: {EVIDENCE_DIR}")
    print(f"Active dirs:   {len(active)} (oldest: {min(active_dates) if active_dates else 'n/a'})")
    print(f"Archived dirs: {len(archived)} (oldest: {min(archived_dates) if archived_dates else 'n/a'})")
    print(f"Archive candidates (>= {DEFAULT_ARCHIVE_DAYS} days): {len(archive_candidates)}")
    print(f"Prune candidates   (>= {DEFAULT_PRUNE_DAYS} days): {len(prune_candidates)}")
    return 0


def cmd_archive(dry_run: bool) -> int:
    candidates = [
        p
        for p in _list_evidence_dirs()
        if (d := _parse_dir_date(p)) and _age_days(d) >= DEFAULT_ARCHIVE_DAYS
    ]
    if not candidates:
        print(f"No evidence dirs older than {DEFAULT_ARCHIVE_DAYS} days. Nothing to archive.")
        return 0

    print(f"Archiving {len(candidates)} dir(s) to {ARCHIVED_DIR}:")
    moved = 0
    for src in sorted(candidates):
        d = _parse_dir_date(src)
        if d is None:
            continue
        dest_parent = ARCHIVED_DIR / _archive_month(d)
        dest = dest_parent / src.name
        print(f"  {src.name} -> {_display(dest)}")
        if dry_run:
            continue
        dest_parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            print(f"    SKIP (dest already exists): {dest}", file=sys.stderr)
            continue
        shutil.move(str(src), str(dest))
        moved += 1
    if dry_run:
        print(f"Dry-run: 0 dirs moved (use --apply to move {len(candidates)}).")
    else:
        print(f"Moved {moved} dir(s) to {ARCHIVED_DIR}.")
    return 0


def cmd_prune(dry_run: bool) -> int:
    candidates = [
        p
        for p in _list_archived_dirs()
        if (d := _parse_dir_date(p)) and _age_days(d) >= DEFAULT_PRUNE_DAYS
    ]
    if not candidates:
        print(f"No archived dirs older than {DEFAULT_PRUNE_DAYS} days. Nothing to prune.")
        return 0

    print(f"Pruning {len(candidates)} archived dir(s) (irreversible; git retains history):")
    deleted = 0
    for p in sorted(candidates):
        print(f"  rm -r {_display(p)}")
        if dry_run:
            continue
        shutil.rmtree(p)
        deleted += 1
    # Clean up empty month dirs.
    if not dry_run:
        for month_dir in sorted(ARCHIVED_DIR.iterdir()) if ARCHIVED_DIR.is_dir() else []:
            if month_dir.is_dir() and not any(month_dir.iterdir()):
                month_dir.rmdir()
    if dry_run:
        print(f"Dry-run: 0 dirs deleted (use --apply to delete {len(candidates)}).")
    else:
        print(f"Deleted {deleted} dir(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="Print evidence lifecycle summary.")
    a = sub.add_parser("archive", help=f"Move evidence dirs older than {DEFAULT_ARCHIVE_DAYS} days to archived/.")
    a.add_argument("--dry-run", action="store_true", help="List candidates without moving (default).")
    a.add_argument("--apply", action="store_true", help="Actually move dirs.")
    p = sub.add_parser("prune", help=f"Delete archived dirs older than {DEFAULT_PRUNE_DAYS} days.")
    p.add_argument("--dry-run", action="store_true", help="List candidates without deleting (default).")
    p.add_argument("--apply", action="store_true", help="Actually delete dirs.")
    args = parser.parse_args(argv)

    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "archive":
        if args.apply and args.dry_run:
            print("error: --apply and --dry-run are mutually exclusive", file=sys.stderr)
            return 2
        return cmd_archive(dry_run=not args.apply)
    if args.cmd == "prune":
        if args.apply and args.dry_run:
            print("error: --apply and --dry-run are mutually exclusive", file=sys.stderr)
            return 2
        return cmd_prune(dry_run=not args.apply)
    return 2


if __name__ == "__main__":
    sys.exit(main())
