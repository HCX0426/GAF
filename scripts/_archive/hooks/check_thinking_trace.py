"""check_thinking_trace.py — R10 thinking trace validator.

Validates that a thinking trace was written for the current session
by scanning ``.ai-memory/session-traces/`` for the most recent ``.md``
file and checking it contains the required governance sections.

Validation rules:
  - No ``.md`` files in session-traces → WARN (non-blocking, exit 0)
  - Trace file exists but is stale (> 60 min) → WARN (non-blocking, exit 0)
  - Recent trace exists → must contain:
      * ``task_type`` (any non-empty content)
      * ``决策路径`` (decision path section)
      * ``执行的检查`` (checks performed section)
  - Missing any required section → FAIL (exit 1, blocks commit)

The 60-minute window matches the typical AI session duration; traces
older than that are considered "previous session" evidence and do not
satisfy the current-session requirement.

Usage:
    python check_thinking_trace.py
    python check_thinking_trace.py --root <path>
    python check_thinking_trace.py --window-min <minutes>
    python check_thinking_trace.py --no-strict

Exit codes:
    0 — Trace OK, or no recent trace (warning-only, non-blocking)
    1 — Recent trace found but missing required sections
    2 — Configuration error
"""
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import _encoding_safe  # noqa: E402,F401

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
SESSION_TRACES_DIR = Path(".ai-memory") / "session-traces"
DEFAULT_WINDOW_MIN = 60

REQUIRED_SECTIONS = (
    "task_type",
    "决策路径",
    "执行的检查",
)


def _detect_change_size() -> str:
    """Detect change size from staged git diff.

    Returns: 'small', 'medium', or 'big'.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--numstat"],
            capture_output=True,
            text=True, encoding="utf-8",
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            # Try unstaged diff
            result = subprocess.run(
                ["git", "diff", "--numstat"],
                capture_output=True,
                text=True, encoding="utf-8",
                timeout=5,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return "small"

        total_added = 0
        total_deleted = 0
        file_count = 0
        for line in result.stdout.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2:
                added = int(parts[0]) if parts[0] != "-" else 0
                deleted = int(parts[1]) if parts[1] != "-" else 0
                total_added += added
                total_deleted += deleted
                file_count += 1

        total_diff = total_added + total_deleted
        if total_diff > 500 or file_count >= 10:
            return "big"
        elif total_diff >= 50 or file_count >= 3:
            return "medium"
        return "small"
    except Exception:
        return "small"

# Case-insensitive heading match: ## task_type, ## 决策路径, etc.
# Also tolerates trailing colons and whitespace variations.
_SECTION_HEADING_RE = re.compile(
    r"^#{1,6}\s*"          # markdown heading (1-6 #)
    r"([^\n#]+?)"          # heading text (non-greedy, no #)
    r"\s*:?\s*$",          # optional trailing colon, end of line
    re.MULTILINE,
)


def _find_most_recent_trace(traces_dir: Path) -> Path | None:
    """Return the most recently modified ``.md`` file in `traces_dir`.

    Skips directories and non-``.md`` files. Returns ``None`` when
    the directory is empty or does not exist.
    """
    if not traces_dir.is_dir():
        return None
    md_files = [
        f for f in traces_dir.iterdir()
        if f.is_file()
        and f.suffix.lower() == ".md"
        and not f.name.startswith(("_", "."))
        and f.stem.lower() != "readme"
    ]
    if not md_files:
        return None
    md_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return md_files[0]


def _age_seconds(path: Path) -> float:
    """Return the age of `path` in seconds (mtime vs now)."""
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return float("inf")


def _extract_sections(text: str) -> set[str]:
    """Extract markdown heading texts from `text` as a normalised set.

    Normalisation: stripped, lowercased for ASCII, kept as-is for CJK.
    This allows case-insensitive matching for ``task_type`` while
    preserving exact CJK matching for ``决策路径`` and ``执行的检查``.
    """
    headings: set[str] = set()
    for match in _SECTION_HEADING_RE.finditer(text):
        heading = match.group(1).strip()
        headings.add(heading)
        headings.add(heading.lower())
    return headings


def _validate_trace(trace_path: Path) -> tuple[bool, list[str]]:
    """Validate a thinking trace file's required sections.

    Returns (passed, messages).
    """
    messages: list[str] = []
    try:
        text = trace_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        messages.append(f"FAIL  cannot read {trace_path.name}")
        return False, messages

    sections_found = _extract_sections(text)
    if not sections_found:
        messages.append(f"FAIL  {trace_path.name} has no markdown headings")
        return False, messages

    missing: list[str] = []
    for section in REQUIRED_SECTIONS:
        section_lower = section.lower()
        if section not in sections_found and section_lower not in sections_found:
            missing.append(section)
            messages.append(f"FAIL  missing required section: {section}")
        else:
            messages.append(f"PASS  found section: {section}")

    if missing:
        return False, messages
    return True, messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GAF R10 thinking trace validator",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT_DEFAULT),
        help="Path to the GAF repo root (default: %(default)s)",
    )
    parser.add_argument(
        "--window-min",
        type=int,
        default=DEFAULT_WINDOW_MIN,
        help="Freshness window in minutes (default: %(default)s)",
    )
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="Print report but never exit non-zero.",
    )
    parser.add_argument(
        "--require",
        action="store_true",
        help="FAIL (exit 1) when no recent trace found — for medium/big changes.",
    )
    args = parser.parse_args(argv)

    # Auto-detect change size: medium/big changes require thinking trace
    detected_size = _detect_change_size()
    auto_require = args.require or detected_size in ("medium", "big")
    if auto_require and detected_size != "small":
        print(f"[auto] change size detected: {detected_size} — enabling --require mode")

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"FAIL  root is not a directory: {root}")
        return 2

    traces_dir = root / SESSION_TRACES_DIR
    window_sec = args.window_min * 60

    if not traces_dir.is_dir():
        print(f"WARN  session-traces directory missing: {traces_dir}")
        if auto_require:
            print(f"FAIL  --require mode: thinking trace required but directory missing")
            return 1
        return 0

    latest = _find_most_recent_trace(traces_dir)
    if latest is None:
        print(f"WARN  no .md trace files found in {traces_dir}")
        print(f"WARN  no thinking trace written for this session")
        if auto_require:
            print(f"FAIL  --require mode: thinking trace required for medium/big change")
            print(f"FAIL  expected: .ai-memory/session-traces/<session_id>.md with task_type + 决策路径 + 执行的检查 sections")
            return 1
        return 0

    age = _age_seconds(latest)
    age_min = age / 60.0

    if age > window_sec:
        print(f"WARN  most recent trace {latest.name} is {age_min:.0f} min old (> {args.window_min} min window)")
        print(f"WARN  no recent thinking trace for current session")
        if auto_require:
            print(f"FAIL  --require mode: thinking trace too old ({age_min:.0f} min > {args.window_min} min)")
            return 1
        return 0

    print(f"PASS  recent trace found: {latest.name} ({age_min:.0f} min old)")
    passed, messages = _validate_trace(latest)
    for m in messages:
        print(f"  {m}")

    if passed:
        print(f"PASS  thinking trace validation OK")
        return 0

    print(f"FAIL  thinking trace validation failed — missing required sections")
    return 1 if not args.no_strict else 0


if __name__ == "__main__":
    sys.exit(main())