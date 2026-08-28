"""archive_low_trigger_lessons.py — Archive N## entries with trigger_count ≤ 1 to archived-early/.

Background
----------
TD-343 (P3, 2026-07-26): ~20 out of 73 active lessons have trigger_count ≤ 1,
exceeding N189's <10% target. These low-trigger N## bloat the Active index
and waste AI L1 load budget.

This script:
  1. Parses failure-modes.md Active N## table
  2. Identifies entries with trigger_count ≤ 1
  3. Moves their lesson files to archived-early/
  4. Updates failure-modes.md (remove rows from Active, add archived marker)
  5. Updates lessons/README.md counts
  6. Updates archived-lessons.md index

Usage
-----
    python scripts/bootstrap/archive_low_trigger_lessons.py --dry-run
    python scripts/bootstrap/archive_low_trigger_lessons.py --execute
    python scripts/bootstrap/archive_low_trigger_lessons.py --threshold 1 --dry-run
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import namedtuple
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
FAILURE_MODES = REPO_ROOT / ".ai-memory" / "meta" / "failure-modes.md"
LESSONS_DIR = REPO_ROOT / ".ai-memory" / "lessons"
ARCHIVED_DIR = LESSONS_DIR / "archived-early"
README_MD = LESSONS_DIR / "README.md"
ARCHIVED_LESSONS_MD = REPO_ROOT / ".ai-memory" / "meta" / "archived-lessons.md"

ACTIVE_SECTION_START = "## Active N## 索引表"
ACTIVE_SECTION_END = "## Retired N## 索引"
ARCHIVED_EARLY_SECTION = "### Archived-Early N## 索引（低触发归档）"


ActiveEntry = namedtuple("ActiveEntry", [
    "n_id", "topic", "constraint", "lesson_link", "trigger_count", "last_triggered", "raw_line"
])


def parse_active_table(content: str) -> Tuple[int, int, List[ActiveEntry]]:
    """Parse Active N## table from failure-modes.md.

    Returns (section_start, section_end, list_of_entries).
    """
    lines = content.split("\n")
    start = end = -1
    for i, line in enumerate(lines):
        if start < 0 and line.startswith(ACTIVE_SECTION_START):
            start = i
        elif start >= 0 and line.startswith(ACTIVE_SECTION_END):
            end = i
            break
    if start < 0:
        return (0, 0, [])
    if end < 0:
        end = len(lines)

    # Skip header lines (##, >, blank, | N## | topic | ... |, |:---:|:---:|...)
    entries: List[ActiveEntry] = []
    for i in range(start, end):
        line = lines[i]
        # Match table data row: | N### | ... | ... | `lessons/...` | count | date |
        m = re.match(r"^\|\s*(N\d{2,3})\s*\|", line)
        if not m:
            continue

        n_id = m.group(1)

        # Robust parsing: split by |, but topic/constraint may contain | chars.
        # Strategy: parse from right (fixed format) then left.
        # Rightmost columns are always: ... | lesson_link | trigger_count | last_triggered |
        # Split by | and work from right.
        all_parts = line.split("|")
        # all_parts[0] = "" (empty before first |)
        # all_parts[-1] = "" (empty after last |)
        # all_parts[-2] = last_triggered
        # all_parts[-3] = trigger_count
        # all_parts[-4] = lesson_link
        # all_parts[1] to all_parts[-5] = everything (N## + topic + constraint)

        if len(all_parts) < 7:  # minimum: | N## | topic | constraint | lesson | count | date |
            continue

        last_triggered = all_parts[-2].strip()
        try:
            trigger_count = int(all_parts[-3].strip())
        except ValueError:
            trigger_count = 0
        lesson_link = all_parts[-4].strip().strip("`")

        # Now parse the left side: N## | topic | constraint
        # N## is already known from regex match
        left_parts = all_parts[1:-4]  # everything between N## and lesson_link
        # left_parts[0] should be N##, remaining are topic + constraint
        if len(left_parts) >= 3:
            # left_parts = [N##, topic_part1, topic_part2, ..., constraint_part1, constraint_part2, ...]
            # Hard to separate topic from constraint when they contain |
            # Use the lesson_link position as anchor:
            # Everything between N## and lesson_link is topic + constraint
            # Try to split: the constraint usually contains "硬约束" or starts with backtick-less text
            # Heuristic: topic usually starts with Chinese text without backticks
            # constraint is the segment closest to lesson_link that doesn't contain 'lessons/'

            # Simpler: if left_parts has 3+ elements, join and try to find the split
            # The constraint column typically ends right before | `lessons/...`
            # So everything except the last 1-2 segments should be topic
            topic = "|".join(left_parts[1:-1]).strip()  # join all between N## and last segment
            constraint = left_parts[-1].strip()
        elif len(left_parts) == 2:
            topic = left_parts[0].strip()
            constraint = left_parts[1].strip()
        elif len(left_parts) == 1:
            topic = left_parts[0].strip()
            constraint = ""
        else:
            continue

        entries.append(ActiveEntry(
            n_id=n_id,
            topic=topic,
            constraint=constraint,
            lesson_link=lesson_link,
            trigger_count=trigger_count,
            last_triggered=last_triggered,
            raw_line=line,
        ))
    return (start, end, entries)


def find_lesson_file(n_id: str, lesson_link: str) -> Optional[Path]:
    """Find the actual lesson file path from a lesson link."""
    if not lesson_link or lesson_link.startswith("_("):
        return None
    # Only handle files under lessons/ directory
    if lesson_link.startswith("docs/") or lesson_link.startswith("plans/"):
        return None  # not a lesson file, skip archiving
    # lesson_link is like `lessons/N123-lesson-name.md` or just the filename
    link_path = Path(lesson_link)
    # Try directly
    direct = LESSONS_DIR / link_path.name
    if direct.exists():
        return direct
    # Try as-is (strip lessons/ prefix if present)
    clean_link = lesson_link.replace("lessons/", "").replace("`", "")
    full = LESSONS_DIR / clean_link
    if full.exists():
        return full
    # Search by N## prefix
    for f in LESSONS_DIR.glob(f"{n_id.lower()}*.md"):
        if f.name != "README.md":
            return f
    return None


def is_recent_entry(entry: ActiveEntry, recent_cutoff_days: int = 14) -> bool:
    """Check if an entry is too recent (within cutoff_days) to archive.

    - If last_triggered == "-" (never triggered), return False (allow archiving).
    - If last_triggered is a date within the last ``recent_cutoff_days`` days,
      return True (skip archiving).
    - Otherwise return False (allow archiving).
    """
    if entry.last_triggered == "-":
        return False  # never triggered → allow archiving
    try:
        from datetime import date, datetime
        last_date = datetime.strptime(entry.last_triggered, "%Y-%m-%d").date()
        delta = (date.today() - last_date).days
        return delta <= recent_cutoff_days
    except (ValueError, TypeError):
        return False  # unparseable date → allow archiving (conservative)


def should_archive(entry: ActiveEntry, threshold: int) -> Tuple[bool, str]:
    """Determine if an entry should be archived."""
    if entry.trigger_count > threshold:
        return (False, f"trigger_count ({entry.trigger_count}) > threshold ({threshold})")
    if is_recent_entry(entry):
        return (False, f"recent/never-triggered entry (last_triggered={entry.last_triggered})")
    if not entry.lesson_link or entry.lesson_link.startswith("_("):
        return (False, f"no independent lesson file ({entry.lesson_link})")
    # L0 hard constraints should never be archived — they are loaded every session
    constraint_lower = entry.constraint.lower()
    if "l0" in constraint_lower and ("硬约束" in entry.constraint or "hardrule" in constraint_lower):
        return (False, f"L0 hard constraint ({entry.n_id}) — always loaded")
    # Entries with lesson_link pointing outside lessons/ (e.g. docs/plans/)
    if entry.lesson_link.startswith("docs/"):
        return (False, f"lesson_link is not in lessons/ ({entry.lesson_link})")
    return (True, "meets archive criteria")


def update_failure_modes(
    content: str,
    section_start: int,
    section_end: int,
    archive_ids: List[str],
) -> str:
    """Update failure-modes.md: remove archived rows from Active, add archived-early marker."""
    lines = content.split("\n")
    archive_set = set(archive_ids)

    # Rebuild the Active section
    new_active_lines: List[str] = []
    archived_entries: List[ActiveEntry] = []

    for i in range(section_start, section_end):
        line = lines[i]
        m = re.match(r"^\|\s*(N\d{2,3})\s*\|", line)
        if m and m.group(1) in archive_set:
            # Parse this entry for the archived section
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 6:
                archived_entries.append(ActiveEntry(
                    n_id=cells[0], topic=cells[1], constraint=cells[2],
                    lesson_link=cells[3].strip("`"), trigger_count=int(cells[4]) if cells[4].isdigit() else 0,
                    last_triggered=cells[5], raw_line=line,
                ))
            continue  # skip this row
        new_active_lines.append(line)

    # Replace the section
    new_lines = (
        lines[:section_start]
        + new_active_lines
        + lines[section_end:]
    )

    # Add Archived-Early section before Retired
    archived_section = [
        "",
        ARCHIVED_EARLY_SECTION,
        "",
        "> 以下 N## trigger_count ≤ 1, 按 TD-343 归档标准迁移。保留 lesson 文件在 `lessons/archived-early/`，按需 grep 加载。",
        "> 归档标准: trigger_count ≤ 1 且不是 very-recent (last_triggered ≠ '-')",
        "",
        "| N## | 主题 | 归档原因 | Lesson 路径 | 归档日期 |",
        "|:---:|------|---------|------------|---------|",
    ]
    for e in archived_entries:
        archived_section.append(
            f"| {e.n_id} | {e.topic} | trigger_count={e.trigger_count} | `lessons/archived-early/{Path(e.lesson_link).name}` | {_today()} |"
        )
    archived_section.append("")

    # Find the Retired section insertion point
    retired_idx = -1
    for i, line in enumerate(new_lines):
        if line.startswith(ACTIVE_SECTION_END):
            retired_idx = i
            break

    if retired_idx >= 0:
        new_lines = new_lines[:retired_idx] + archived_section + new_lines[retired_idx:]

    return "\n".join(new_lines)


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def update_readme_counts(content: str, archived_count: int) -> str:
    """Update lessons/README.md frontmatter counts."""
    import re as _re

    # Update lessons_count
    content = _re.sub(
        r"^(lessons_count:\s*)\d+",
        lambda m: f"{m.group(1)}{int(m.group(0).split(':')[1].strip()) - archived_count}",
        content,
        flags=_re.MULTILINE,
    )
    # Update active_n_count
    content = _re.sub(
        r"^(active_n_count:\s*)\d+",
        lambda m: f"{m.group(1)}{int(m.group(0).split(':')[1].strip()) - archived_count}",
        content,
        flags=_re.MULTILINE,
    )
    # Update archived_n_count
    content = _re.sub(
        r"^(archived_n_count:\s*)\d+",
        lambda m: f"{m.group(1)}{int(m.group(0).split(':')[1].strip()) + archived_count}",
        content,
        flags=_re.MULTILINE,
    )
    return content


def update_archived_lessons(
    content: str, archived_entries: List[ActiveEntry]
) -> str:
    """Update archived-lessons.md with newly archived entries."""
    if not archived_entries:
        return content

    # Find the Archived N## 索引表 section
    marker = "## 归档 N## 索引表"
    lines = content.split("\n")

    # Find the table end (next ## header or EOF)
    insert_idx = -1
    in_table = False
    for i, line in enumerate(lines):
        if line.startswith(marker):
            in_table = True
            continue
        if in_table and line.startswith("| N"):
            insert_idx = i + 1  # after last table row
        elif in_table and insert_idx > 0 and line.startswith("##"):
            break  # end of table

    if insert_idx < 0:
        # Append at end
        insert_idx = len(lines)

    new_rows = []
    for e in archived_entries:
        lesson_filename = Path(e.lesson_link).name if e.lesson_link else f"{e.n_id}.md"
        new_rows.append(
            f"| {e.n_id} | {e.topic} | trigger_count={e.trigger_count}, TD-343 归档 | `lessons/archived-early/{lesson_filename}` |"
        )

    new_content = "\n".join(lines[:insert_idx] + new_rows + lines[insert_idx:])
    return new_content


def main():
    parser = argparse.ArgumentParser(description="Archive low-trigger N## lessons (TD-343)")
    parser.add_argument("--threshold", type=int, default=1, help="trigger_count threshold (≤ = archive)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be archived without doing it")
    parser.add_argument("--execute", action="store_true", help="Actually perform the archive")
    args = parser.parse_args()

    if not args.dry_run and not args.execute:
        print("Use --dry-run or --execute")
        sys.exit(1)

    print(f"{'[DRY RUN] ' if args.dry_run else '[EXECUTE] '}TD-343: Archiving lessons with trigger_count ≤ {args.threshold}")
    print()

    # 1. Parse failure-modes.md
    content = FAILURE_MODES.read_text(encoding="utf-8")
    section_start, section_end, entries = parse_active_table(content)
    print(f"Parsed {len(entries)} Active N## entries from failure-modes.md")

    # 2. Filter for archiving
    to_archive: List[ActiveEntry] = []
    skip_reasons: Dict[str, str] = {}

    for e in entries:
        should, reason = should_archive(e, args.threshold)
        if should:
            to_archive.append(e)
        else:
            skip_reasons[e.n_id] = reason

    print(f"\nCandidates for archive: {len(to_archive)}")
    for e in to_archive:
        print(f"  {e.n_id}: trigger_count={e.trigger_count}, lesson={e.lesson_link}")

    print(f"\nSkipped: {len(skip_reasons)}")
    for n_id, reason in skip_reasons.items():
        print(f"  {n_id}: {reason}")

    if not args.execute:
        print("\n[DRY RUN] No changes made. Use --execute to archive.")
        return

    # 3. Execute archive
    print(f"\n{'='*60}")
    print("Executing archive...")
    print(f"{'='*60}")

    archived_ids: List[str] = []
    archived_entries: List[ActiveEntry] = []

    for e in to_archive:
        lesson_file = find_lesson_file(e.n_id, e.lesson_link)
        if lesson_file and lesson_file.exists():
            dest = ARCHIVED_DIR / lesson_file.name
            if dest.exists():
                print(f"  [SKIP] {e.n_id}: {dest.name} already exists in archived-early/")
                continue
            shutil.move(str(lesson_file), str(dest))
            print(f"  [MOVED] {e.n_id}: {lesson_file.name} → archived-early/")
            archived_ids.append(e.n_id)
            archived_entries.append(e)
        else:
            print(f"  [NO FILE] {e.n_id}: lesson file not found for '{e.lesson_link}'")
            # Still mark for table removal
            archived_ids.append(e.n_id)
            archived_entries.append(e)

    # 4. Update failure-modes.md
    if archived_ids:
        new_content = update_failure_modes(content, section_start, section_end, archived_ids)
        FAILURE_MODES.write_text(new_content, encoding="utf-8")
        print(f"\n[UPDATED] failure-modes.md: removed {len(archived_ids)} rows from Active, added Archived-Early section")

    # 5. Update lessons/README.md
    readme_content = README_MD.read_text(encoding="utf-8")
    new_readme = update_readme_counts(readme_content, len(archived_ids))
    README_MD.write_text(new_readme, encoding="utf-8")
    print(f"[UPDATED] lessons/README.md: counts adjusted (-{len(archived_ids)} active, +{len(archived_ids)} archived)")

    # 6. Update archived-lessons.md
    if archived_entries:
        al_content = ARCHIVED_LESSONS_MD.read_text(encoding="utf-8")
        new_al = update_archived_lessons(al_content, archived_entries)
        ARCHIVED_LESSONS_MD.write_text(new_al, encoding="utf-8")
        print(f"[UPDATED] archived-lessons.md: added {len(archived_entries)} entries")

    # 7. Summary
    print(f"\n{'='*60}")
    print(f"Archive complete: {len(archived_ids)} N## entries archived")
    print(f"{'='*60}")

    # Show new active count
    updated_content = FAILURE_MODES.read_text(encoding="utf-8")
    _, _, remaining = parse_active_table(updated_content)
    low_trigger = [e for e in remaining if e.trigger_count <= args.threshold]
    print(f"\nRemaining Active N##: {len(remaining)}")
    print(f"  With trigger_count ≤ {args.threshold}: {len(low_trigger)}")
    for e in low_trigger:
        reason = "recent/never" if is_recent_entry(e) else "no-lesson"
        print(f"    {e.n_id}: count={e.trigger_count}, status={reason}")

    # Target check
    total_active = len(remaining)
    low_count = len([e for e in remaining if e.trigger_count <= args.threshold])
    pct = (low_count / total_active * 100) if total_active > 0 else 0
    print(f"\nTarget: trigger_count ≤ {args.threshold} entries = {pct:.1f}% (target < 10%)")
    if pct < 10:
        print("✅ Target achieved!")
    else:
        print(f"⚠️  Still above 10% target ({pct:.1f}%)")


if __name__ == "__main__":
    main()
