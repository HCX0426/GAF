"""post_commit_reflection_check.py — N134 post-commit reflection evidence guard.

Runs as a `post-commit` hook. For commits whose diff is 50+ lines, checks
whether reflection evidence exists in `.ai-memory/evidence/<date>-<task>/`
and whether that evidence contains the A/B/C classification required by
`project_rules.md` §4.6 (循环迭代反思) and the gaf-reflect-and-evolve skill.

Git limitation: post-commit hooks run AFTER the commit is created, so they
cannot block it. This script therefore only prints WARNINGS to stderr and
always exits 0. The warnings are meant to remind the developer to run the
reflection checklist (N134: "每段 commit 后必跑反思清单").

Diff-size threshold (50 lines) matches the "中修改" boundary in §4.6:
  - < 50 lines  → small change, reflection optional, exit silently
  - >= 50 lines → medium/large change, reflection required → warn if missing

Evidence is considered "present" for the current commit when a file in
today's evidence directory EITHER:
  - mentions the commit hash (full or short), OR
  - was modified within the last hour (loose coupling — the reflection
    may not cite the hash but was clearly written for this commit).

Usage:
    python scripts/hooks/post_commit_reflection_check.py

Exits 0 always (post-commit hooks cannot fail a commit).
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import datetime as _dt  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout to UTF-8)

REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = REPO_ROOT / ".ai-memory" / "evidence"

DIFF_THRESHOLD = 50  # lines (insertions + deletions) — "中修改" boundary
RECENT_WINDOW_SEC = 3600  # 1 hour — evidence file mtime window

# A/B/C classification keywords (project_rules.md §4.6).
# Evidence must reference at least one of these to be considered complete.
CLASSIFICATION_KEYWORDS = (
    "A/B/C",
    "立即修复",
    "后续 Phase",
    "无法解决",
)


# ---------------------------------------------------------------------------
# Git helpers (subprocess, no shell=True for Windows compatibility)
# ---------------------------------------------------------------------------
def _git(args: list[str]) -> str:
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


def _head_hashes() -> tuple[str, str]:
    """Return (full_hash, short_hash) of the latest commit."""
    full = _git(["rev-parse", "HEAD"])
    short = _git(["rev-parse", "--short", "HEAD"])
    return full, short


def _diff_line_count() -> int:
    """Return total lines changed (insertions + deletions) in the latest commit.

    Uses `git show --shortstat --format= HEAD` which prints a single summary
    line like ` 2 files changed, 20 insertions(+), 15 deletions(-)`.
    Returns 0 if the stat cannot be parsed (e.g. initial commit, merge).
    """
    out = _git(["show", "--shortstat", "--format=", "HEAD"])
    if not out:
        return 0
    ins = 0
    dele = 0
    ins_match = re.search(r"(\d+)\s+insertions?\b", out)
    dele_match = re.search(r"(\d+)\s+deletions?\b", out)
    if ins_match:
        ins = int(ins_match.group(1))
    if dele_match:
        dele = int(dele_match.group(1))
    return ins + dele


# ---------------------------------------------------------------------------
# Evidence discovery
# ---------------------------------------------------------------------------
def _today_evidence_dirs() -> list[Path]:
    """Return today's evidence directories matching ``<date>-<task>``."""
    today_str = _dt.date.today().isoformat()
    if not EVIDENCE_DIR.is_dir():
        return []
    prefix = f"{today_str}-"
    return sorted(
        d for d in EVIDENCE_DIR.iterdir()
        if d.is_dir() and d.name.startswith(prefix)
    )


def _find_commit_evidence(full_hash: str, short_hash: str) -> list[Path]:
    """Return evidence files in today's dirs that relate to this commit.

    A file relates to the commit if it mentions the commit hash (full or
    short) OR was modified within the last hour.
    """
    today_dirs = _today_evidence_dirs()
    if not today_dirs:
        return []

    now = time.time()
    matches: list[Path] = []
    for today_dir in today_dirs:
        for entry in sorted(today_dir.iterdir()):
            if not entry.is_file():
                continue
            # Loose coupling: file modified within the last hour.
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                mtime = 0
            recent = (now - mtime) <= RECENT_WINDOW_SEC

            mentions_hash = False
            try:
                text = entry.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            if full_hash and full_hash in text or short_hash and short_hash in text:
                mentions_hash = True

            if recent or mentions_hash:
                matches.append(entry)
    return matches


def _evidence_has_classification(files: list[Path]) -> bool:
    """Return True if the combined evidence text contains A/B/C keywords."""
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for kw in CLASSIFICATION_KEYWORDS:
            if kw in text:
                return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    full_hash, short_hash = _head_hashes()
    if not full_hash:
        # No commit (empty repo) or git unavailable — nothing to check.
        return 0

    diff_lines = _diff_line_count()
    if diff_lines < DIFF_THRESHOLD:
        # Small change — reflection optional (§4.6 small-change tier).
        return 0

    evidence_files = _find_commit_evidence(full_hash, short_hash)

    warnings: list[str] = []
    warnings.append("")
    warnings.append("=" * 60)
    warnings.append("⚠️  N134 post-commit reflection reminder")
    warnings.append(f"   commit: {short_hash} ({full_hash[:12]}...)")
    warnings.append(f"   diff:   {diff_lines} lines changed (>= {DIFF_THRESHOLD} threshold)")
    warnings.append("")

    if not evidence_files:
        warnings.append(
            "   ❌ No reflection evidence found for this commit."
        )
        warnings.append(
            f"   Expected evidence in: {EVIDENCE_DIR}/{_dt.date.today().isoformat()}-<task>/"
        )
        warnings.append("")
        warnings.append("   Per project_rules.md §4.6 (N134), medium/large")
        warnings.append("   commits require the 4-question reflection with")
        warnings.append("   A/B/C classification:")
        warnings.append("     [A] 立即修复 / [B] 后续 Phase / [C] 无法解决")
        warnings.append("")
        warnings.append("   Fix: run the reflection checklist now and record")
        warnings.append("   evidence citing this commit hash.")
        warnings.append("=" * 60)
        sys.stderr.write("\n".join(warnings) + "\n")
        return 0

    # Evidence exists — verify A/B/C classification present.
    if not _evidence_has_classification(evidence_files):
        warnings.append(
            f"   ⚠️ Reflection evidence found ({len(evidence_files)} file(s)) "
            f"but missing A/B/C classification."
        )
        warnings.append(
            f"   Files: {', '.join(f.name for f in evidence_files)}"
        )
        warnings.append("")
        warnings.append("   Per project_rules.md §4.6, reflection must classify")
        warnings.append("   findings as one of:")
        warnings.append("     [A] 立即修复 / [B] 后续 Phase / [C] 无法解决")
        warnings.append("")
        warnings.append("   Fix: add the A/B/C classification to your evidence.")
        warnings.append("=" * 60)
        sys.stderr.write("\n".join(warnings) + "\n")
        return 0

    # Evidence present AND classified — all good.
    notes: list[str] = []
    notes.append("")
    notes.append("=" * 60)
    notes.append(f"✅ N134 reflection evidence OK for {short_hash}")
    notes.append(f"   diff: {diff_lines} lines | evidence: {len(evidence_files)} file(s)")
    notes.append("=" * 60)
    sys.stderr.write("\n".join(notes) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
