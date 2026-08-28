"""track_n_trigger.py — count real N## trigger counts from git log / spec / lesson cross_refs.

Background
----------
`.ai-memory/meta/failure-modes.md` keeps a 6-column Active N## table:

    | N## | 主题 | 硬约束 | Lesson 链接 | trigger_count | last_triggered |

All rows ship with trigger_count=0 and last_triggered="-". This script scans
three real sources to populate true counts:

  1. git log commit messages (git log --all --pretty=format:"%ad|%s" --date=short)
  2. spec files (docs/specs/active/*.md + docs/specs/archived/**/*.md)
  3. lesson frontmatter cross_refs fields (.ai-memory/lessons/*.md)

last_triggered is derived from the latest git commit date referencing that N##.

Usage
-----
    conda run -n gaf python scripts/bootstrap/track_n_trigger.py
    conda run -n gaf python scripts/bootstrap/track_n_trigger.py --dry-run
    conda run -n gaf python scripts/bootstrap/track_n_trigger.py --verbose
    conda run -n gaf python scripts/bootstrap/track_n_trigger.py --failure-modes <path>

Exit codes: 0 on success, 1 on error.
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: F401  (must be first; reconfigures stdout to UTF-8)

import argparse
import re
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
FAILURE_MODES_DEFAULT = (
    REPO_ROOT_DEFAULT / ".ai-memory" / "meta" / "failure-modes.md"
)
SPECS_ACTIVE_DIR_DEFAULT = REPO_ROOT_DEFAULT / "docs" / "specs" / "active"
SPECS_ARCHIVED_DIR_DEFAULT = REPO_ROOT_DEFAULT / "docs" / "specs" / "archived"
LESSONS_DIR_DEFAULT = REPO_ROOT_DEFAULT / ".ai-memory" / "lessons"

# Match a single N## token (2-3 digits) with word boundaries.
# 2 digits covers N91..N99; 3 digits covers N100..N999. Word boundary
# prevents matching N1234 (4 digits) or N12 (1 digit).
N_REF_RE = re.compile(r"\b(N\d{2,3})\b")

# Match Active table row: `| N91 | ...` (literal N## + digits in first cell).
ACTIVE_ROW_RE = re.compile(r"^\|\s*(N\d{2,3})\s*\|")

# Match the last 2 columns `| <count> | <date> |` at end of an Active row.
# count column is all digits; date column is non-pipe chars (date or "-").
LAST_TWO_COLS_RE = re.compile(r"\|\s*\d+\s*\|\s*[^|]*\|\s*$")

# Section markers delimiting the Active N## table in failure-modes.md.
ACTIVE_SECTION_START = "## Active N## 索引表"
ACTIVE_SECTION_END = "## Retired N## 索引"


def parse_active_section(content: str) -> Tuple[int, int]:
    """Find line range [start, end) of the Active N## section.

    Returns (start_line_idx, end_line_idx) suitable for slicing `lines`.
    `end` is the index of the line starting with ACTIVE_SECTION_END,
    or len(lines) if no end marker found. Returns (0, 0) if start not found.
    """
    lines = content.split("\n")
    start: int = -1
    end: int = -1
    for i, line in enumerate(lines):
        if start < 0 and line.startswith(ACTIVE_SECTION_START):
            start = i
        elif start >= 0 and line.startswith(ACTIVE_SECTION_END):
            end = i
            break
    if start < 0:
        return (0, 0)
    if end < 0:
        end = len(lines)
    return (start, end)


def collect_git_triggers(repo_root: Path) -> Dict[str, List[Tuple[str, str]]]:
    """Scan git log for N## references in commit subjects.

    Returns {N##: [(date_iso, subject), ...]}.
    """
    result: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    try:
        proc = subprocess.run(
            [
                "git",
                "-c",
                "i18n.logoutputencoding=utf-8",
                "log",
                "--all",
                "--pretty=format:%ad|%s",
                "--date=short",
            ],
            cwd=str(repo_root),
            capture_output=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return result
    if proc.returncode != 0:
        return result
    stdout = proc.stdout.decode("utf-8", errors="replace")
    for line in stdout.splitlines():
        # Split on first `|` only — commit subjects may contain `|`.
        parts = line.split("|", 1)
        if len(parts) != 2:
            continue
        date_str, subject = parts
        date_str = date_str.strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            continue
        for m in N_REF_RE.finditer(subject):
            n_id = m.group(1)
            result[n_id].append((date_str, subject.strip()))
    return result


def collect_spec_triggers(active_dir: Path, archived_dir: Path) -> Dict[str, List[Path]]:
    """Scan spec files for N## references.

    Returns {N##: [file_path, ...]} (unique file per N##).
    """
    result: Dict[str, List[Path]] = defaultdict(list)
    candidates: List[Path] = []
    if active_dir.exists():
        candidates.extend(sorted(active_dir.glob("*.md")))
    if archived_dir.exists():
        # archived/<year-month>/*.md (and any deeper nesting)
        candidates.extend(sorted(archived_dir.glob("**/*.md")))
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        seen: Set[str] = set()
        for m in N_REF_RE.finditer(text):
            n_id = m.group(1)
            if n_id not in seen:
                seen.add(n_id)
                result[n_id].append(path)
    return result


def parse_lesson_cross_refs(text: str) -> List[str]:
    """Extract N## refs from a lesson file's frontmatter cross_refs field.

    Supports both inline (`cross_refs: [N151, N167]`) and block style:
        cross_refs:
          - N151
          - N167
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return []
    fm_end: int = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_end = i
            break
    if fm_end < 0:
        return []
    fm_lines = lines[1:fm_end]

    refs: List[str] = []
    in_cross_refs = False
    for line in fm_lines:
        m = re.match(r"^cross_refs:\s*(.*)$", line)
        if m:
            in_cross_refs = True
            inline = m.group(1).strip()
            if inline:
                # Inline style: `cross_refs: [N151, N167]` or `cross_refs: []`
                refs.extend(N_REF_RE.findall(inline))
                if inline.startswith("["):
                    # Inline array form — block list does not follow.
                    in_cross_refs = False
            # Empty inline value → block list may follow.
            continue
        if in_cross_refs:
            if re.match(r"^\s*-\s+", line):
                refs.extend(N_REF_RE.findall(line))
            elif line.strip() == "":
                # Blank line — assume end of cross_refs block.
                in_cross_refs = False
            else:
                # Non-list line → end of cross_refs block.
                in_cross_refs = False
    return refs


def collect_lesson_triggers(lessons_dir: Path) -> Dict[str, List[Path]]:
    """Scan lesson files for cross_refs fields referencing N##.

    Returns {N##: [lesson_file_path, ...]} (unique lesson per N##).
    """
    result: Dict[str, List[Path]] = defaultdict(list)
    if not lessons_dir.exists():
        return result
    for path in sorted(lessons_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        refs = parse_lesson_cross_refs(text)
        seen: Set[str] = set()
        for n_id in refs:
            if n_id not in seen:
                seen.add(n_id)
                result[n_id].append(path)
    return result


def update_failure_modes(
    content: str,
    counts: Dict[str, int],
    last_dates: Dict[str, str],
) -> Tuple[str, int]:
    """Update Active N## rows in failure-modes.md content.

    Returns (new_content, num_rows_updated). Only rows within the Active
    section (between ACTIVE_SECTION_START and ACTIVE_SECTION_END) are
    modified; Retired/Dormant tables are left untouched.
    """
    lines = content.split("\n")
    start, end = parse_active_section(content)
    if start == end:
        return (content, 0)
    updated = 0
    for i in range(start, end):
        line = lines[i]
        m = ACTIVE_ROW_RE.match(line)
        if not m:
            continue
        n_id = m.group(1)
        count = counts.get(n_id, 0)
        last_date = last_dates.get(n_id, "-")
        new_line = re.sub(
            LAST_TWO_COLS_RE,
            f"| {count} | {last_date} |",
            line,
        )
        if new_line != line:
            lines[i] = new_line
            updated += 1
    return ("\n".join(lines), updated)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Count real N## trigger counts in failure-modes.md",
    )
    parser.add_argument(
        "--failure-modes",
        type=Path,
        default=FAILURE_MODES_DEFAULT,
        help=f"Path to failure-modes.md (default: {FAILURE_MODES_DEFAULT})",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT_DEFAULT,
        help=f"Repo root for git log / spec / lesson scans (default: {REPO_ROOT_DEFAULT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print stats only; do not write back to failure-modes.md",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-N## trigger source details",
    )
    args = parser.parse_args()

    t0 = time.perf_counter()

    failure_modes_path: Path = args.failure_modes
    repo_root: Path = args.repo_root

    if not failure_modes_path.exists():
        print(f"[ERROR] failure-modes.md not found: {failure_modes_path}")
        return 1

    # Read current failure-modes.md
    try:
        content = failure_modes_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[ERROR] Failed to read {failure_modes_path}: {e}")
        return 1

    # Collect triggers from 3 sources
    git_triggers = collect_git_triggers(repo_root)
    spec_triggers = collect_spec_triggers(
        SPECS_ACTIVE_DIR_DEFAULT,
        SPECS_ARCHIVED_DIR_DEFAULT,
    )
    lesson_triggers = collect_lesson_triggers(LESSONS_DIR_DEFAULT)

    # Aggregate counts per N## across all 3 sources
    all_n_ids: Set[str] = set()
    all_n_ids.update(git_triggers.keys())
    all_n_ids.update(spec_triggers.keys())
    all_n_ids.update(lesson_triggers.keys())

    counts: Dict[str, int] = {}
    last_dates: Dict[str, str] = {}
    for n_id in all_n_ids:
        git_count = len(git_triggers.get(n_id, []))
        spec_count = len(spec_triggers.get(n_id, []))
        lesson_count = len(lesson_triggers.get(n_id, []))
        counts[n_id] = git_count + spec_count + lesson_count
        # last_triggered = latest git commit date referencing this N##
        git_dates = [d for d, _ in git_triggers.get(n_id, [])]
        last_dates[n_id] = max(git_dates) if git_dates else "-"

    # Update failure-modes.md content
    new_content, updated_rows = update_failure_modes(content, counts, last_dates)

    # Write back if not dry-run and there are changes
    if not args.dry_run and updated_rows > 0:
        try:
            failure_modes_path.write_text(new_content, encoding="utf-8")
        except OSError as e:
            print(f"[ERROR] Failed to write {failure_modes_path}: {e}")
            return 1

    # Build summary — only count N## rows that are actually in the Active section
    start, end = parse_active_section(content)
    active_lines = content.split("\n")[start:end]
    active_n_ids_in_file: List[str] = []
    for line in active_lines:
        m = ACTIVE_ROW_RE.match(line)
        if m:
            active_n_ids_in_file.append(m.group(1))

    total_active = len(active_n_ids_in_file)
    triggered = [n for n in active_n_ids_in_file if counts.get(n, 0) > 0]

    print("=" * 72)
    print("track_n_trigger.py — N## trigger count summary")
    print("=" * 72)
    print(f"failure-modes.md: {failure_modes_path}")
    print(f"repo root:       {repo_root}")
    print(f"dry-run:         {args.dry_run}")
    print()
    print(f"Total Active N## in file:        {total_active}")
    print(f"Active N## with trigger_count>0: {len(triggered)}")
    print()

    # Top 10 high-frequency N## (sorted by count desc, then by numeric ID asc)
    if active_n_ids_in_file:
        def n_sort_key(n: str):
            num = int(n[1:])
            return (-counts.get(n, 0), num)

        sorted_active = sorted(active_n_ids_in_file, key=n_sort_key)
        top10 = sorted_active[:10]
        print("Top 10 high-frequency N## (among Active rows in file):")
        print(f"{'N##':<8} {'count':>6}  {'last':<12}  sources")
        print("-" * 72)
        for n_id in top10:
            count = counts.get(n_id, 0)
            last = last_dates.get(n_id, "-")
            g = len(git_triggers.get(n_id, []))
            s = len(spec_triggers.get(n_id, []))
            l = len(lesson_triggers.get(n_id, []))
            sources = f"git={g} spec={s} lesson={l}"
            print(f"{n_id:<8} {count:>6}  {last:<12}  {sources}")
        print()

    if args.verbose:
        print("=" * 72)
        print("Per-N## trigger source details (verbose)")
        print("=" * 72)
        for n_id in active_n_ids_in_file:
            count = counts.get(n_id, 0)
            if count == 0:
                continue
            print(f"\n{n_id} (total={count}, last={last_dates.get(n_id, '-')})")
            git_list = git_triggers.get(n_id, [])
            if git_list:
                print(f"  git ({len(git_list)}):")
                for date, subj in git_list[:5]:
                    print(f"    {date}  {subj[:80]}")
                if len(git_list) > 5:
                    print(f"    ... +{len(git_list) - 5} more")
            spec_list = spec_triggers.get(n_id, [])
            if spec_list:
                print(f"  spec ({len(spec_list)}):")
                for p in spec_list[:5]:
                    print(f"    {p}")
                if len(spec_list) > 5:
                    print(f"    ... +{len(spec_list) - 5} more")
            lesson_list = lesson_triggers.get(n_id, [])
            if lesson_list:
                print(f"  lesson cross_refs ({len(lesson_list)}):")
                for p in lesson_list[:5]:
                    print(f"    {p}")
                if len(lesson_list) > 5:
                    print(f"    ... +{len(lesson_list) - 5} more")

    elapsed = time.perf_counter() - t0
    print()
    print(f"Elapsed: {elapsed:.2f}s")
    if args.dry_run:
        print("[DRY-RUN] No file modifications made.")
    else:
        print(f"Updated {updated_rows} rows in {failure_modes_path.name}.")

    return 0


if __name__ == "__main__":
    _sys.exit(main())
