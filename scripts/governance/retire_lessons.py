#!/usr/bin/env python3
"""Auto-retire L3 lessons based on 4 triggers:
1. trigger_count=0 (never triggered)
2. >300 lines (too long for quick reference)
3. 90+ days since last trigger
4. Hard limit: active L3 lessons ≤ 15

Lessons matching triggers are moved to archived-early/.
Corresponding N## entries in failure-modes.md get link updated.
"""
import argparse
import re
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # scripts/ → GAF/
LESSONS_DIR = ROOT / '.ai-memory' / 'lessons'
ARCH_DIR = LESSONS_DIR / 'archived-early'
FM_PATH = ROOT / '.ai-memory' / 'meta' / 'failure-modes.md'

MAX_ACTIVE_LESSONS = 15
MAX_LINES = 300
SILENCE_DAYS = 90


def load_n_metadata():
    """Load N## metadata from failure-modes.md."""
    fm_text = FM_PATH.read_text(encoding='utf-8')
    active_re = re.compile(
        r'^\|\s*(N\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|$'
    )
    n_meta = {}
    in_active = False
    for line in fm_text.splitlines():
        s = line.strip()
        if s.startswith('## Active N##'):
            in_active = True
            continue
        if s.startswith('## ') and in_active:
            in_active = False
        if in_active:
            m = active_re.match(s)
            if m:
                n_id = m.group(1)
                n_meta[n_id] = {
                    'topic': m.group(2).strip(),
                    'trigger_count': int(m.group(5)),
                    'last_triggered': m.group(6).strip(),
                    'link': m.group(4).strip(),
                }
    return n_meta


def assess_lessons(n_meta):
    """Assess all active lessons for retirement eligibility."""
    now = date.today()
    lessons = []

    for f in LESSONS_DIR.glob('*.md'):
        if not f.is_file() or f.name == 'README.md':
            continue
        stem = f.stem
        lines = f.read_text(encoding='utf-8').splitlines()
        line_count = len(lines)

        m = re.match(r'(N\d+)', stem)
        if not m:
            continue
        n_id = m.group(1)

        meta = n_meta.get(n_id, {})
        tc = meta.get('trigger_count', 0)
        lt = meta.get('last_triggered', '-')

        triggers = []
        if tc == 0:
            # Only archive if never triggered AND created >30 days ago
            # (grace period for new rules that haven't had chance to trigger)
            fstat = f.stat()
            created = date.fromtimestamp(fstat.st_ctime)
            age_days = (now - created).days
            if age_days > 30:
                triggers.append(f'never triggered ({age_days}d)')
        if line_count > MAX_LINES:
            triggers.append(f'>{MAX_LINES} lines ({line_count})')
        if lt != '-':
            try:
                lt_date = date.fromisoformat(lt)
                age = (now - lt_date).days
                if age > SILENCE_DAYS:
                    triggers.append(f'{age}d since last trigger')
            except ValueError:
                pass

        lessons.append({
            'file': f.name,
            'stem': stem,
            'n_id': n_id,
            'line_count': line_count,
            'trigger_count': tc,
            'triggers': triggers,
        })

    return lessons


def apply_hard_limit(lessons):
    """If active lessons > MAX, mark lowest-value for archival."""
    if len(lessons) <= MAX_ACTIVE_LESSONS:
        return lessons, []

    over = len(lessons) - MAX_ACTIVE_LESSONS
    sorted_by_value = sorted(lessons, key=lambda x: (x['trigger_count'], -x['line_count']))
    to_archive = sorted_by_value[:over]
    keep = sorted_by_value[over:]

    for l in to_archive:
        l['triggers'].append(f'hard limit (>{MAX_ACTIVE_LESSONS})')

    return keep, to_archive


def archive_lessons(to_archive, n_meta, dry_run=False):
    """Move lessons to archived-early and update failure-modes.md."""
    archived_stems = {l['stem'] for l in to_archive}

    if dry_run:
        return len(to_archive)

    # Move files
    for l in to_archive:
        src = LESSONS_DIR / l['file']
        dst = ARCH_DIR / l['file']
        if src.exists():
            src.rename(dst)

    # Update failure-modes.md
    fm_text = FM_PATH.read_text(encoding='utf-8')
    lines = fm_text.splitlines()
    active_re = re.compile(
        r'^\|\s*(N\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|$'
    )

    for i, line in enumerate(lines):
        s = line.strip()
        m = active_re.match(s)
        if not m:
            continue
        n_id = m.group(1)
        link = m.group(4).strip()

        if n_id in archived_stems and not link.startswith('_archived'):
            archived_match = [stem for stem in archived_stems if n_id in stem]
            if archived_match:
                cols = line.split('|')
                cols[4] = f" _archived {archived_match[0]}.md "
                lines[i] = '|'.join(cols)

    FM_PATH.write_text('\n'.join(lines), encoding='utf-8')
    return len(to_archive)


def main():
    parser = argparse.ArgumentParser(description='Retire L3 lessons')
    parser.add_argument('--dry-run', action='store_true', help='Show candidates without archiving')
    args = parser.parse_args()

    n_meta = load_n_metadata()
    lessons = assess_lessons(n_meta)

    # First pass: lessons matching triggers
    triggered = [l for l in lessons if l['triggers']]
    clean = [l for l in lessons if not l['triggers']]

    # Apply hard limit
    keep, limit_archive = apply_hard_limit(clean)

    # Combine: trigger-matched + hard-limit-exceeded
    to_archive = triggered + limit_archive

    print(f"=== L3 Lessons Status ===")
    print(f"  Active: {len(lessons)}")
    print(f"  To archive (triggers): {len(triggered)}")
    print(f"  To archive (hard limit): {len(limit_archive)}")
    print(f"  Total to archive: {len(to_archive)}")

    if to_archive:
        print(f"\n=== Retirement Candidates ===")
        for l in to_archive:
            print(f"  {l['file']}: {', '.join(l['triggers'])}")

    if not args.dry_run and to_archive:
        count = archive_lessons(to_archive, n_meta, dry_run=False)
        print(f"\nArchived {count} lessons.")
    elif args.dry_run:
        print("\n[DRY RUN] No files moved.")

    # Final status
    final_active = len([f for f in LESSONS_DIR.glob('*.md') if f.is_file() and f.name != 'README.md'])
    final_archived = len([f for f in ARCH_DIR.glob('*.md') if f.is_file() and f.name != 'README.md'])
    print(f"\n=== Final Status ===")
    print(f"  Active lessons: {final_active}")
    print(f"  Archived lessons: {final_archived}")
    print(f"  Total: {final_active + final_archived}")


if __name__ == '__main__':
    main()