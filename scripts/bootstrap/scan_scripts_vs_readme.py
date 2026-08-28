#!/usr/bin/env python
"""CI scanner: detect scripts/ .py files not registered in scripts/README.md.

TD-259 #1 (P1) — project_rules.md §5.5 hard-constraint requires every new
script to be registered in scripts/README.md (Purpose / Invocation / Trigger
columns). This scanner enforces the rule at CI time so drift cannot
accumulate across specs.

Scope:
    - Walks scripts/ recursively, collects all .py files.
    - Excludes __init__.py (package init, no README registration needed).
    - Reads scripts/README.md as plain text.
    - For each .py file, checks if its basename appears as a whole word
      in README.md (word boundary excludes [a-zA-Z0-9_-] so that
      `sync_ai_memory.py` does not falsely match a substring of
      `sync_ai_memory_extra.py`).

Relation to audit_scripts.py:
    - audit_scripts.py: quarterly audit (stale mtime + frontmatter + README
      ref). Heavier, run quarterly.
    - scan_scripts_vs_readme.py: CI basename-set diff. Lightweight, run on
      every commit. Catches new unregistered scripts immediately.

Exit codes:
    0: All .py scripts registered in README.md.
    1: One or more .py scripts not registered (printed to stdout).
    2: README.md missing or unreadable.

Performance target: < 1s per N171 baseline.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
README_MD = SCRIPTS_DIR / "README.md"

# Files excluded from registration check.
# __init__.py is a package marker, not a standalone tool.
SKIP_BASENAMES = {"__init__.py"}


def collect_scripts(root: Path) -> list[Path]:
    """Collect standalone CLI scripts (.py with a __main__ guard).

    Excludes:
    - __init__.py (package marker)
    - package-internal library modules (no ``__main__`` guard, e.g.
      bootstrap/ai_memory_sync/*.py, hooks/doc_sync_rules.py) — these are
      imported by other scripts, not standalone tools.
    - hooks/ dir — pre-commit hooks are registered in .pre-commit-config.yaml
      (authoritative) + gaf_governance_batch CHECKS; README hooks table is
      descriptive only.
    - tests/ dir — collected by pytest, not standalone tools.
    - _archive/ dir (retired scripts don't need registration).
    """
    if not root.exists():
        return []
    main_re = re.compile(r"if __name__\s*==\s*['\"]__main__['\"]:")
    out: list[Path] = []
    for p in sorted(root.rglob("*.py")):
        if p.name in SKIP_BASENAMES:
            continue
        if any(seg in p.parts for seg in ("_archive", "tests", "hooks")):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not main_re.search(content):
            continue
        out.append(p)
    return out


def is_registered(basename: str, readme_content: str) -> bool:
    """Check if basename appears as a whole word in README.md.

    Word boundary excludes [a-zA-Z0-9_-] so substrings do not match.
    For example, `sync_ai_memory.py` will NOT match inside
    `sync_ai_memory_extra.py`.
    """
    pattern = rf"(?<![\w-]){re.escape(basename)}(?![\w-])"
    return re.search(pattern, readme_content) is not None


def scan(root: Path = SCRIPTS_DIR, readme: Path = README_MD) -> list[Path]:
    """Run scan, return list of unregistered script paths."""
    if not readme.exists():
        raise FileNotFoundError(f"README.md not found at {readme}")
    readme_text = readme.read_text(encoding="utf-8")
    scripts = collect_scripts(root)
    return [s for s in scripts if not is_registered(s.name, readme_text)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CI scanner: detect unregistered .py scripts in scripts/README.md",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Quiet mode for pre-commit/CI (only prints unregistered, "
             "suppresses summary header).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="Repo root (default: auto-detected from script location).",
    )
    args = parser.parse_args()

    scripts_root = args.root / "scripts"
    readme = scripts_root / "README.md"

    if not readme.exists():
        print(f"ERROR: {readme} not found", file=sys.stderr)
        return 2

    try:
        unregistered = scan(scripts_root, readme)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    scripts = collect_scripts(scripts_root)

    if not args.check:
        print("=" * 60)
        print("scan_scripts_vs_readme.py — scripts/ vs README.md audit")
        print("=" * 60)
        print(f"Scripts scanned       : {len(scripts)}")
        print(f"Registered in README  : {len(scripts) - len(unregistered)}")
        print(f"Unregistered          : {len(unregistered)}")
        print()

    if unregistered:
        if not args.check:
            print("Unregistered scripts (add to scripts/README.md):")
        for p in unregistered:
            rel = p.relative_to(args.root)
            print(f"  - {rel}")
        if not args.check:
            print()
            print("Fix: add each script to the appropriate section table in")
            print("scripts/README.md with Purpose / Invocation / Trigger.")
        return 1

    if not args.check:
        print("OK: all scripts registered in scripts/README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
