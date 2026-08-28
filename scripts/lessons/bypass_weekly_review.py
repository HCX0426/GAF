#!/usr/bin/env python3
"""Weekly review of bypass reasons written to ``.gaf_audit.log``.

Scans ``GAF/.gaf_audit.log`` for ``BYPASS`` entries within a sliding window
(default 7 days), aggregates the most frequent bypass reasons, and appends a
review section to ``GAF/.ai-memory/ops/bypass-patterns.md``.
"""

from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path
_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import argparse
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Default paths are resolved relative to this script so the tool works
# regardless of the current working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUDIT_LOG = _REPO_ROOT / ".gaf_audit.log"
DEFAULT_OUTPUT = _REPO_ROOT / ".ai-memory" / "ops" / "bypass-patterns.md"
DEFAULT_DAYS = 7
DEFAULT_TOP_N = 5

# Regex for a single BYPASS audit line.
# Example: BYPASS ts=2026-06-15T18:57:59Z user=foo reason=... args=...
_BYPASS_RE = re.compile(
    r"^BYPASS\s+"
    r"ts=(?P<ts>\S+)\s+"
    r"user=(?P<user>\S+)\s+"
    r"reason=(?P<reason>.+?)\s+"
    r"args=(?P<args>.*)$"
)


def _now_utc() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(timezone.utc)


def _parse_iso_timestamp(raw: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp (with trailing ``Z``) to a UTC datetime."""
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def parse_audit_line(line: str) -> Optional[Dict[str, str]]:
    """Parse one ``BYPASS`` audit log line.

    Args:
        line: A single line from ``.gaf_audit.log``.

    Returns:
        A dictionary with keys ``ts``, ``user``, ``reason``, ``args`` or
        ``None`` if the line is not a valid ``BYPASS`` record.
    """
    line = line.strip()
    if not line.startswith("BYPASS "):
        return None
    m = _BYPASS_RE.match(line)
    if not m:
        return None
    return m.groupdict()


def load_bypasses(
    log_path: Path,
    days: int,
    now: Optional[datetime] = None,
) -> List[Tuple[datetime, Dict[str, str]]]:
    """Load bypass records from the audit log within the last ``days`` days.

    Args:
        log_path: Path to ``.gaf_audit.log``.
        days: Sliding window size in days.
        now: Optional reference time (defaults to UTC now).

    Returns:
        A list of ``(timestamp, record)`` tuples, sorted by timestamp ascending.
    """
    if now is None:
        now = _now_utc()
    cutoff = now - timedelta(days=days)
    out: List[Tuple[datetime, Dict[str, str]]] = []

    if not log_path.exists():
        return out

    # Use utf-8-sig to tolerate BOMs and 'replace' to tolerate GBK leftovers.
    text = log_path.read_text(encoding="utf-8-sig", errors="replace")
    for line in text.splitlines():
        record = parse_audit_line(line)
        if not record:
            continue
        ts = _parse_iso_timestamp(record["ts"])
        if ts is None:
            continue
        if ts >= cutoff:
            out.append((ts, record))

    out.sort(key=lambda x: x[0])
    return out


def summarize_bypasses(
    bypasses: List[Tuple[datetime, Dict[str, str]]],
    top_n: int,
) -> List[Tuple[str, int]]:
    """Return the ``top_n`` most frequent bypass reasons.

    Args:
        bypasses: Records produced by :func:`load_bypasses`.
        top_n: Maximum number of reasons to return.

    Returns:
        A list of ``(reason, count)`` tuples ordered by count descending.
    """
    counter = Counter(record["reason"] for _, record in bypasses)
    return counter.most_common(top_n)


def _format_review_section(
    start: datetime,
    end: datetime,
    total: int,
    top_reasons: List[Tuple[str, int]],
) -> str:
    """Generate a markdown review section for ``bypass-patterns.md``."""
    header = (
        f"\n## 每周复盘 @ {end.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"- **统计窗口**: {start.strftime('%Y-%m-%d %H:%M UTC')} ~ "
        f"{end.strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"- **总 bypass 数**: {total}\n"
        f"- **高频原因 Top {len(top_reasons)}**:\n"
    )
    lines = [header]
    for idx, (reason, count) in enumerate(top_reasons, start=1):
        safe_reason = reason.replace("|", "\\|").replace("\n", " ")
        lines.append(f"  {idx}. `{safe_reason}` — {count} 次\n")

    lines.append("\n### 转化决策\n")
    if not top_reasons:
        lines.append("- 本周无 bypass 记录，无需转化。\n")
    else:
        for reason, count in top_reasons:
            safe_reason = reason.replace("|", "\\|").replace("\n", " ")
            decision = "提议修工具/写 lesson" if count >= 3 else "继续观察"
            lines.append(
                f"- `{safe_reason}` ({count} 次) → **{decision}** "
                f"(见 §2 已记录绕过清单跟踪)\n"
            )
    lines.append("---\n")
    return "".join(lines)


def update_bypass_patterns(
    output_path: Path,
    bypasses: List[Tuple[datetime, Dict[str, str]]],
    top_reasons: List[Tuple[str, int]],
    days: int,
    now: datetime,
    dry_run: bool = False,
) -> str:
    """Append a weekly review section to ``bypass-patterns.md``.

    Args:
        output_path: Path to ``bypass-patterns.md``.
        bypasses: Records within the review window.
        top_reasons: Top reasons from :func:`summarize_bypasses`.
        days: Window size used for the review.
        now: Reference time for the review.
        dry_run: If ``True``, do not write to disk.

    Returns:
        The markdown section that was (or would be) appended.
    """
    start = now - timedelta(days=days)
    section = _format_review_section(start, now, len(bypasses), top_reasons)

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.write_text(
                output_path.read_text(encoding="utf-8", errors="replace") + section,
                encoding="utf-8",
            )
        else:
            output_path.write_text(
                "---\nmaintainer: manual\n---\n# GAF 绕过模式 (Bypass Patterns) 速查\n" + section,
                encoding="utf-8",
            )

    return section


def main(argv: Optional[List[str]] = None) -> int:
    """Command-line entry point for the weekly bypass review."""
    parser = argparse.ArgumentParser(
        description="Weekly review of bypass reasons from .gaf_audit.log"
    )
    parser.add_argument(
        "--audit-log",
        type=Path,
        default=DEFAULT_AUDIT_LOG,
        help="Path to .gaf_audit.log (default: GAF/.gaf_audit.log)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path to bypass-patterns.md (default: GAF/.ai-memory/ops/bypass-patterns.md)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help="Review window in days (default: 7)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
        help="Number of top reasons to report (default: 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the review section without writing to disk",
    )
    args = parser.parse_args(argv)

    now = _now_utc()
    bypasses = load_bypasses(args.audit_log, args.days, now=now)
    top_reasons = summarize_bypasses(bypasses, args.top_n)

    print(f"📊 bypass 复盘窗口: 最近 {args.days} 天")
    print(f"   记录数: {len(bypasses)}")
    print(f"   Top {len(top_reasons)} 原因:")
    for reason, count in top_reasons:
        print(f"   - {count}x {reason[:80]}")

    section = update_bypass_patterns(
        args.output,
        bypasses,
        top_reasons,
        args.days,
        now,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        print("\n--- dry-run 输出 ---")
        print(section)
        print("--- 结束 ---")
    else:
        print(f"\n✅ 已追加到 {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
