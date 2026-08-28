"""sync_session_context.py — L2 session-context.md auto-generator.

Generates `.ai-memory/ref/session-context.md`, a compact snapshot of the project
state that AI loads at the start of each session (L2 hard-load). Called from
`scripts/gaf_init.sh --full` and safe to run standalone.

Sections produced:
  - Environment   : conda env, backend/frontend ports, current git branch
  - Backend Apps  : all Django apps discovered under `backend/`
  - Recent Commits: `git log --oneline -5`
  - Active Tech Debt   : rows from docs/archive/active-tech-debt.md with 🔧/🚧 status
  - Active Roadmap     : rows from pending-roadmap.md that are not ✅/❌

Design notes:
  - Stdlib only (no external deps) so it runs in the bare conda env.
  - Uses `subprocess.run(["git", ...])` (no shell=True) for Windows safety.
  - Imports `_encoding_safe` first to fix CJK mojibake on Windows PowerShell
    (N92 project convention for all scripts/*.py).
  - Idempotent: overwrites the file on every run.
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
import datetime as _dt
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv

# 加载根目录 .env 文件
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

STALE_THRESHOLD_DAYS = 7

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_MEMORY = REPO_ROOT / ".ai-memory"
OUTPUT_FILE = AI_MEMORY / "ref" / "session-context.md"
# Tech debt was consolidated into archive/active-tech-debt.md on 2026-08-09.
# Active items are scanned for ## TD-NNN: format.
TECH_DEBT_FILE = REPO_ROOT / "docs" / "archive" / "active-tech-debt.md"
# Roadmap was merged into project-status.md on 2026-08-09.
ROADMAP_FILE = REPO_ROOT / "docs" / "project-status.md"

CONDA_ENV = "gaf"
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8000"))
FRONTEND_PORT = int(os.environ.get("FRONTEND_PORT", "5173"))


# ---------------------------------------------------------------------------
# Git helpers (subprocess, no shell=True for Windows compatibility)
# ---------------------------------------------------------------------------
def _git(args: List[str]) -> str:
    """Run a git command in REPO_ROOT and return stdout as text.

    Returns an empty string on failure so callers can degrade gracefully.
    """
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""


def _current_branch() -> str:
    return _git(["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"


def _recent_commits(n: int = 5) -> List[str]:
    out = _git(["log", f"-{n}", "--oneline"])
    if not out:
        return []
    return [line for line in out.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Backend apps discovery
# ---------------------------------------------------------------------------
def _backend_apps() -> List[str]:
    """Return sorted list of Django app directory names under `backend/`.

    An app is identified by the presence of `apps.py` (the canonical Django
    AppConfig marker). Directory name is used as the app label.
    """
    backend_dir = REPO_ROOT / "backend"
    if not backend_dir.is_dir():
        return []
    apps: List[str] = []
    for apps_py in sorted(backend_dir.glob("*/apps.py")):
        apps.append(apps_py.parent.name)
    return apps


# ---------------------------------------------------------------------------
# Tech-debt/active-tech-debt.md parser
# ---------------------------------------------------------------------------
# Entry format (since 2026-07-10 split):
#   ## TD-NNN: <title>
#   - **状态**: 🔧 待修 | 🚧 进行中
#   - **优先级**: P0..P3
#   ...
# Older table-row format (| TD-NNN | ... |) is also accepted for back-compat.
_TD_HEADING_RE = re.compile(r"^##\s+(TD-\d+):\s*(.+)$", re.MULTILINE)
_TD_ROW_RE = re.compile(r"^\|\s*(TD-\d+)\s*\|(.*)$", re.MULTILINE)
_TD_STATUS_RE = re.compile(r"^\s*-\s*\*\*状态\*\*\s*:\s*(.+)$", re.MULTILINE)
_TD_PRIO_RE = re.compile(r"^\s*-\s*\*\*优先级\*\*\s*:\s*(.+)$", re.MULTILINE)


def _parse_active_tech_debt() -> List[Tuple[str, str, str, str]]:
    """Parse docs/archive/active-tech-debt.md and return active TD rows.

    A TD is "active" when its status cell contains 🔧 or 🚧 (待修 / 进行中).
    Entries with ✅ / ❌ should not appear in active-tech-debt.md at all, but we
    filter defensively in case of drift.

    Returns list of (id, severity, status, title) tuples.
    """
    if not TECH_DEBT_FILE.exists():
        return []
    text = TECH_DEBT_FILE.read_text(encoding="utf-8", errors="replace")
    active: List[Tuple[str, str, str, str]] = []

    # New format: ## TD-NNN: <title> followed by attribute list.
    for match in _TD_HEADING_RE.finditer(text):
        td_id = match.group(1)
        title = match.group(2).strip()
        # Scan the block after this heading for status/priority.
        block_start = match.end()
        next_heading = _TD_HEADING_RE.search(text, pos=block_start)
        block_end = next_heading.start() if next_heading else len(text)
        block = text[block_start:block_end]
        status_m = _TD_STATUS_RE.search(block)
        prio_m = _TD_PRIO_RE.search(block)
        status = status_m.group(1).strip() if status_m else ""
        severity = prio_m.group(1).strip() if prio_m else ""
        if "🔧" in status or "🚧" in status:
            active.append((td_id, severity, status, title))

    # Back-compat: legacy table-row format (| TD-NNN | title | ... |).
    for match in _TD_ROW_RE.finditer(text):
        td_id = match.group(1)
        rest = match.group(2)
        cols = [c.strip() for c in rest.split("|")]
        if len(cols) < 4:
            continue
        title = cols[0]
        severity = cols[1]
        status = cols[2]
        if "🔧" in status or "🚧" in status:
            # Deduplicate: skip if the heading-format pass already added this TD.
            if not any(t[0] == td_id for t in active):
                active.append((td_id, severity, status, title))
    return active


# ---------------------------------------------------------------------------
# pending-roadmap.md parser
# ---------------------------------------------------------------------------
# Table row: | P-NNN | module | item | priority | status | when | ref |
_P_ROW_RE = re.compile(r"^\|\s*(P-\d+)\s*\|(.*)$", re.MULTILINE)


def _parse_active_roadmap() -> List[Tuple[str, str, str, str, str]]:
    """Parse pending-roadmap.md and return active P-NNN rows.

    A roadmap item is "active" when its status is NOT ✅ and NOT ❌
    (i.e. ⏳ / 🔧 / 🚧 / ⏸️ — pending, partial, in-progress, or paused).

    The canonical table format is: | P-NNN | module | item | status | when | ref |
    Priority is not a separate column — it's embedded in the item text.
    We detect status by scanning cols[2..] for the first cell containing
    a status emoji (✅/❌/⏳/🔧/🚧/⏸️). This is robust to column-count
    variation across historical table layouts.

    Returns list of (id, module, priority, status, item) tuples.
    """
    if not ROADMAP_FILE.exists():
        return []
    text = ROADMAP_FILE.read_text(encoding="utf-8", errors="replace")
    active: List[Tuple[str, str, str, str, str]] = []
    for match in _P_ROW_RE.finditer(text):
        p_id = match.group(1)
        rest = match.group(2)
        cols = [c.strip() for c in rest.split("|")]
        if len(cols) < 3:
            continue
        module = cols[0]
        item = cols[1]
        # Scan the remaining cols for the first status cell.
        status = ""
        for c in cols[2:]:
            if any(emoji in c for emoji in ("✅", "❌", "⏳", "🔧", "🚧", "⏸️")):
                status = c
                break
        if not status:
            # No status emoji found — skip (likely a header or separator row).
            continue
        if "✅" in status or "❌" in status:
            continue
        # Priority is not in its own column; leave blank for rendering.
        active.append((p_id, module, "", status, item))
    return active


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------
def _render() -> str:
    today = _dt.date.today().isoformat()
    branch = _current_branch()
    commits = _recent_commits(5)
    apps = _backend_apps()
    active_td = _parse_active_tech_debt()
    active_roadmap = _parse_active_roadmap()

    lines: List[str] = []
    lines.append("---")
    lines.append("summary: Auto-generated session context for AI L2 loading")
    lines.append("applies_to: [project]")
    lines.append(f"last_updated: {today}")
    lines.append("auto_updated: true")
    lines.append("---")
    lines.append("")
    lines.append("# GAF Session Context (Auto-generated)")
    lines.append("")
    lines.append(
        "> This file is auto-generated by `scripts/bootstrap/sync_session_context.py` "
        "(called from `scripts/gaf_init.sh --full`)."
    )
    lines.append(
        "> Do not edit manually — run `python scripts/bootstrap/sync_session_context.py` "
        "to regenerate."
    )
    lines.append("")

    # Environment
    lines.append("## Environment")
    lines.append("")
    lines.append(f"- **Conda env**: `{CONDA_ENV}`")
    lines.append(f"- **Backend**: http://localhost:{BACKEND_PORT}")
    lines.append(f"- **Frontend**: http://localhost:{FRONTEND_PORT}")
    lines.append(f"- **Git branch**: `{branch}`")
    lines.append("")

    # Backend Apps
    lines.append("## Backend Apps")
    lines.append("")
    lines.append(f"({len(apps)} apps)")
    lines.append("")
    if apps:
        lines.append(", ".join(f"`{a}`" for a in apps))
        lines.append("")

    # Recent Commits
    lines.append("## Recent Commits (5)")
    lines.append("")
    if commits:
        for c in commits:
            lines.append(f"- {c}")
    else:
        lines.append("- _(git log unavailable)_")
    lines.append("")

    # Active Tech Debt
    lines.append("## Active Tech Debt")
    lines.append("")
    lines.append(f"({len(active_td)} active — status 🔧/🚧)")
    lines.append("")
    if active_td:
        lines.append("| ID | Severity | Status | Title |")
        lines.append("|:---|:---:|:---:|:---|")
        for td_id, severity, status, title in active_td:
            # Escape pipes in title to avoid breaking the table
            safe_title = title.replace("|", "\\|")
            lines.append(f"| {td_id} | {severity} | {status} | {safe_title} |")
    else:
        lines.append("_No active tech debt._")
    lines.append("")

    # Active Roadmap
    lines.append("## Active Roadmap")
    lines.append("")
    lines.append(f"({len(active_roadmap)} active — not ✅/❌)")
    lines.append("")
    if active_roadmap:
        lines.append("| ID | Module | Priority | Status | Item |")
        lines.append("|:---|:---|:---:|:---:|:---|")
        for p_id, module, priority, status, item in active_roadmap:
            safe_item = item.replace("|", "\\|")
            lines.append(
                f"| {p_id} | {module} | {priority} | {status} | {safe_item} |"
            )
    else:
        lines.append("_No active roadmap items._")
    lines.append("")

    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate .ai-memory/ref/session-context.md (L2 auto-loaded snapshot)."
    )
    parser.add_argument(
        "--check-stale",
        action="store_true",
        help="Only check if session-context.md is stale (> %d days). "
             "Exit 1 if stale/missing. Does not write." % STALE_THRESHOLD_DAYS,
    )
    args = parser.parse_args(argv)

    if args.check_stale:
        return _check_stale_only()

    # Default: regenerate, but warn if the previous file was stale so
    # developers notice when sync_session_context.py has not run in a while.
    stale_warning = _existing_file_age_warning()
    content = _render()
    # Ensure .ai-memory exists
    AI_MEMORY.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(content, encoding="utf-8")
    print(f"✅ session-context.md generated: {OUTPUT_FILE}")
    print(f"   - branch: {_current_branch()}")
    print(f"   - backend apps: {len(_backend_apps())}")
    print(f"   - active TD: {len(_parse_active_tech_debt())}")
    print(f"   - active roadmap: {len(_parse_active_roadmap())}")
    if stale_warning:
        print(stale_warning)
    return 0


def _parse_last_updated(text: str) -> _dt.date | None:
    """Extract the last_updated date from session-context.md frontmatter."""
    m = re.search(r"^last_updated:\s*(\d{4}-\d{2}-\d{2})", text, re.MULTILINE)
    if not m:
        return None
    try:
        return _dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _existing_file_age_warning() -> str:
    """Return a warning string if the existing session-context.md is stale.

    Returns empty string if file is fresh, missing, or has no parseable date.
    """
    if not OUTPUT_FILE.exists():
        return ""
    text = OUTPUT_FILE.read_text(encoding="utf-8", errors="replace")
    last_date = _parse_last_updated(text)
    if last_date is None:
        return ""
    age_days = (_dt.date.today() - last_date).days
    if age_days <= STALE_THRESHOLD_DAYS:
        return ""
    return (
        f"⚠️  Previous session-context.md was {age_days} days stale "
        f"(last_updated: {last_date}). Regenerated now."
    )


def _check_stale_only() -> int:
    """CI-friendly check: exit 1 if session-context.md is stale or missing."""
    if not OUTPUT_FILE.exists():
        print(
            f"❌ {OUTPUT_FILE} does not exist. "
            "Run `python scripts/bootstrap/sync_session_context.py` to generate."
        )
        return 1
    text = OUTPUT_FILE.read_text(encoding="utf-8", errors="replace")
    last_date = _parse_last_updated(text)
    if last_date is None:
        print(f"❌ {OUTPUT_FILE}: last_updated field missing or malformed.")
        return 1
    age_days = (_dt.date.today() - last_date).days
    if age_days > STALE_THRESHOLD_DAYS:
        print(
            f"❌ {OUTPUT_FILE} is {age_days} days stale "
            f"(last_updated: {last_date}, threshold: {STALE_THRESHOLD_DAYS} days)."
        )
        print(
            "   Run `python scripts/bootstrap/sync_session_context.py` to regenerate."
        )
        return 1
    print(
        f"✅ {OUTPUT_FILE} is fresh "
        f"(last_updated: {last_date}, {age_days} days old)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
