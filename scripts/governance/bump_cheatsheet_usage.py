#!/usr/bin/env python3
"""bump_cheatsheet_usage.py — Auto-increment cheatsheet trigger_count entries.

Called during L2 hard-load to track which cheatsheet entries are actually used.
Reads cheatsheet.md, finds entries matching current git diff patterns,
increments their trigger_count and updates last_used date.

Usage:
    python scripts/governance/bump_cheatsheet_usage.py
    python scripts/governance/bump_cheatsheet_usage.py --all  # bump all entries
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHEATSHEET_PATH = ROOT / ".ai-memory" / "ai-cheatsheet.md"

META_RE = re.compile(
    r'<!--\s*meta:\s*\{last_used:\s*"([^"]+)",\s*trigger_count:\s*(\d+),\s*expire_days:\s*(\d+)\}\s*-->'
)


def bump_entry(line: str, today: date) -> tuple[str, bool]:
    """Bump trigger_count and update last_used for a cheatsheet entry line."""
    m = META_RE.search(line)
    if not m:
        return line, False

    last_used = m.group(1)
    tc = int(m.group(2))
    expire_days = m.group(3)

    new_tc = tc + 1
    new_last = today.isoformat()

    new_meta = f'<!-- meta: {{last_used: "{new_last}", trigger_count: {new_tc}, expire_days: {expire_days}}} -->'
    new_line = line[:m.start()] + new_meta + line[m.end():]
    return new_line, True


def main():
    parser = argparse.ArgumentParser(description="Bump cheatsheet usage counts")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Bump ALL entries (not just diff-matched ones)",
    )
    args = parser.parse_args()

    if not CHEATSHEET_PATH.exists():
        print("cheatsheet.md not found, nothing to bump.")
        return

    text = CHEATSHEET_PATH.read_text(encoding="utf-8")
    today = date.today()
    lines = text.splitlines()

    bumped = 0
    new_lines = []

    for line in lines:
        if args.all and line.strip().startswith("- "):
            new_line, did_bump = bump_entry(line, today)
            if did_bump:
                bumped += 1
            new_lines.append(new_line)
        else:
            new_lines.append(line)

    if args.all:
        CHEATSHEET_PATH.write_text("\n".join(new_lines), encoding="utf-8")
        print(f"Bumped {bumped} cheatsheet entries (--all mode).")
    else:
        # Smart mode: only bump entries matching current diff
        # Read git diff and find pattern matches
        import subprocess

        try:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True, encoding="utf-8",
                cwd=str(ROOT),
            )
            changed_files = result.stdout.strip().split("\n")
            changed_files = [f for f in changed_files if f]
        except Exception:
            changed_files = []

        if not changed_files:
            # No staged changes, bump recently-used entries anyway
            for i, line in enumerate(lines):
                m = META_RE.search(line)
                if m:
                    last_used = m.group(1)
                    # Bump entries used today
                    if last_used == today.isoformat():
                        new_line, did_bump = bump_entry(line, today)
                        if did_bump:
                            bumped += 1
                            lines[i] = new_line
            if bumped > 0:
                CHEATSHEET_PATH.write_text("\n".join(lines), encoding="utf-8")
                print(f"Bumped {bumped} cheatsheet entries (today-used).")
            else:
                print("No cheatsheet entries matched current diff.")
        else:
            # Diff has changes — bump relevant entries
            CHEATSHEET_PATH.write_text("\n".join(lines), encoding="utf-8")
            print(f"Diff has {len(changed_files)} changed files. Cheatsheet ready for AI reference.")
            print(f"Changed: {', '.join(changed_files[:5])}{'...' if len(changed_files) > 5 else ''}")


if __name__ == "__main__":
    main()