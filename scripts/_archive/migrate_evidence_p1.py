"""migrate_evidence_p1.py — P1-5/6 evidence 目录迁移.

规则 (spec §4.1):
- < 30 天的 evidence 目录 → active/
- > 30 天的 evidence 目录 → archived/YYYY-MM/ (按目录名前缀日期归档月份)
- templates/ 保持原位

Usage:
    python scripts/migrate_evidence_p1.py --dry-run
    python scripts/migrate_evidence_p1.py --apply
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / ".ai-memory" / "evidence"
ACTIVE_DIR = EVIDENCE_DIR / "active"
ARCHIVED_DIR = EVIDENCE_DIR / "archived"

DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[-_]")


def git_mv(src: Path, dst: Path, dry_run: bool) -> bool:
    """git mv, 未跟踪文件回退普通 mv."""
    rel_src = src.relative_to(REPO_ROOT).as_posix()
    rel_dst = dst.relative_to(REPO_ROOT).as_posix()
    code = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel_src],
        cwd=REPO_ROOT, capture_output=True
    ).returncode
    if code == 0:
        cmd = ["git", "mv", rel_src, rel_dst]
    else:
        cmd = ["cmd", "/c", "move", str(src), str(dst)]
    if dry_run:
        print(f"  [DRY-RUN] {' '.join(cmd)}")
        return False
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"  ❌ FAIL: {result.stderr.strip()}")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("需要 --dry-run 或 --apply")

    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVED_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    cutoff = today - timedelta(days=30)

    moved_active = 0
    moved_archived = 0
    skipped = 0

    for entry in sorted(EVIDENCE_DIR.iterdir()):
        if not entry.is_dir():
            skipped += 1
            continue
        if entry.name in ("active", "archived", "templates"):
            skipped += 1
            continue
        # 解析日期前缀
        m = DATE_PREFIX_RE.match(entry.name)
        if not m:
            print(f"⚠️  SKIP (no date prefix): {entry.name}")
            skipped += 1
            continue
        entry_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        # 目标路径
        if entry_date >= cutoff:
            dst_dir = ACTIVE_DIR
            label = "active"
        else:
            month_folder = m.group(1)[:7]  # YYYY-MM
            dst_dir = ARCHIVED_DIR / month_folder
            label = f"archived/{month_folder}"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / entry.name
        if dst.exists():
            print(f"⚠️  SKIP (target exists): {entry.name} → {dst.relative_to(EVIDENCE_DIR)}")
            skipped += 1
            continue
        print(f"📦 {label}: {entry.name}")
        if git_mv(entry, dst, args.dry_run):
            if label == "active":
                moved_active += 1
            else:
                moved_archived += 1

    print()
    print("=" * 60)
    print(f"moved to active:   {moved_active}")
    print(f"moved to archived: {moved_archived}")
    print(f"skipped:           {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
