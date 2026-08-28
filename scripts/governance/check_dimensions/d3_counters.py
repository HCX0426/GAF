"""d3_counters.py - actual count functions for d3_count_drift."""
from __future__ import annotations

import re
from pathlib import Path


def count_active_n(repo_root: Path) -> int:
    """Count Active N## entries in failure-modes.md (excludes Retired/Dormant).

    Section-scoped: only counts rows under "## Active N## 索引表" section,
    excluding Retired/Dormant sections (which also use "| NXX |" table format).
    """
    fm = repo_root / ".ai-memory/meta/failure-modes.md"
    if not fm.exists():
        return 0
    text = fm.read_text(encoding="utf-8")
    count = 0
    in_active = False
    for line in text.splitlines():
        if line.startswith("## "):
            # Toggle: "## Active N## 索引表" opens capture; any other "## " closes it.
            in_active = "Active" in line and "N##" in line
            continue
        if in_active and re.match(r"^\|\s*N\d+\s*\|", line):
            count += 1
    return count


def count_docs(repo_root: Path) -> int:
    """Count .md files under docs/."""
    docs_dir = repo_root / "docs"
    if not docs_dir.exists():
        return 0
    return sum(1 for _ in docs_dir.rglob("*.md"))


def count_yn_subfiles(repo_root: Path) -> int:
    """Count _*.md sub-files under .ai-memory/meta/yn-matrices/."""
    yn_dir = repo_root / ".ai-memory/meta/yn-matrices"
    if not yn_dir.exists():
        return 0
    return sum(1 for f in yn_dir.glob("_*.md") if f.is_file())
