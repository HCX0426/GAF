#!/usr/bin/env python3

from pathlib import Path
import re
import datetime
import argparse
import sys

CHEATSHEET_PATH = Path(".ai-memory/ai-cheatsheet.md")

WARN_LINES = 120
FORCE_LINES = 150
WARN_SECTIONS = 8
WARN_ENTRIES = 40

DORMANCY_THRESHOLD_DAYS = 30

META_RE = re.compile(
    r'<!--\s*meta:\s*\{last_used:\s*"([^"]+)",\s*trigger_count:\s*(\d+),\s*expire_days:\s*(\d+)\}\s*-->'
)
SECTION_RE = re.compile(r'^##\s+')
ENTRY_RE = re.compile(r'^\s*[-*]\s+')
DORMANT_RE = re.compile(r'<!--\s*DORMANT:\s*(\d{4}-\d{2}-\d{2})\s*-->')

DORMANT_MARKER = "<!-- DORMANT: {} -->"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Scan cheatsheet for dormant entries and mark them"
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Report dormant entries without modifying (default)",
    )
    mode_group.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually mark dormant entries in the file",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DORMANCY_THRESHOLD_DAYS,
        help=f"Dormancy threshold in days (default: {DORMANCY_THRESHOLD_DAYS})",
    )
    args = parser.parse_args(argv)

    if not CHEATSHEET_PATH.exists():
        print("[OK] cheatsheet: file not found (skipping)")
        return 0

    text = CHEATSHEET_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    total_lines = len(lines)

    sections = sum(1 for ln in lines if SECTION_RE.match(ln))
    entries = [ln for ln in lines if ENTRY_RE.match(ln)]
    entry_count = len(entries)

    warnings = []
    force = False

    if total_lines > FORCE_LINES:
        force = True
        warnings.append(f"[FORCE] cheatsheet: {total_lines} lines (threshold: {FORCE_LINES}) — must trim")
    elif total_lines > WARN_LINES:
        warnings.append(f"[WARN] cheatsheet: {total_lines} lines (threshold: {WARN_LINES}) — consider trimming")

    if sections > WARN_SECTIONS:
        warnings.append(f"[WARN] cheatsheet: {sections} sections (threshold: {WARN_SECTIONS}) — reduce topics")

    if entry_count > WARN_ENTRIES:
        warnings.append(f"[WARN] cheatsheet: {entry_count} entries (threshold: {WARN_ENTRIES}) — prune stale items")

    now = datetime.datetime.now().date()
    dormant_candidates = []
    expired = []

    for i, entry_line in enumerate(lines):
        if not ENTRY_RE.match(entry_line):
            continue

        dormant_already = DORMANT_RE.search(entry_line)
        if dormant_already:
            continue

        m = META_RE.search(entry_line)
        if not m:
            continue

        last_used_str = m.group(1)
        trigger_count = int(m.group(2))
        expire_days = int(m.group(3))

        try:
            last_used = datetime.date.fromisoformat(last_used_str)
        except ValueError:
            continue

        age = (now - last_used).days

        if age > expire_days:
            title = entry_line.strip().lstrip("-* ").strip()
            expired.append((title, age, expire_days, trigger_count))

        if age > args.days:
            title = entry_line.strip().lstrip("-* ").strip()
            dormant_candidates.append((i, title, age, last_used_str))

    if expired:
        titles = ", ".join(e[0][:60] for e in expired)
        warnings.append(
            f"[WARN] {len(expired)} expired entries found (last_used > expire_days): {titles}"
        )

    for w in warnings:
        print(w)

    if not warnings:
        print(f"[OK] cheatsheet: {total_lines} lines, {sections} sections, {entry_count} entries")

    print()
    print(f"=== Dormant Cheatsheet Entries (unused > {args.days} days) ===")
    if dormant_candidates:
        today_str = now.isoformat()
        print(f"Found {len(dormant_candidates)} dormant candidate(s):")
        for idx, title, age, last_used in dormant_candidates:
            print(f"  Line {idx + 1}: {title[:80]}... (age={age}d, last_used={last_used})")
        print()

        if args.execute:
            modified_lines = list(lines)
            offset = 0
            for idx, title, age, last_used in sorted(dormant_candidates, key=lambda x: -x[0]):
                adjusted_idx = idx + offset
                marker = DORMANT_MARKER.format(today_str)
                line_to_modify = modified_lines[adjusted_idx]
                if DORMANT_RE.search(line_to_modify):
                    continue
                modified_lines[adjusted_idx] = line_to_modify.rstrip() + " " + marker
                offset += 1

            new_text = "\n".join(modified_lines) + "\n"
            CHEATSHEET_PATH.write_text(new_text, encoding="utf-8")
            print(f"[EXECUTE] Marked {len(dormant_candidates)} entries as dormant (threshold={args.days}d)")
            print(f"  Added marker: {marker}")
        else:
            print(f"[DRY-RUN] Would mark {len(dormant_candidates)} entries as dormant (threshold={args.days}d)")
            print(f"  Run with --execute to actually modify the file")
    else:
        print("No dormant entries found.")
        if not args.dry_run:
            pass

    print(f"\nSummary: {len(dormant_candidates)} dormant / {entry_count} total entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())