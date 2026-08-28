"""weekly_summary.py — M2.E 每周汇总: 扫 .trash/.e2e-failures.log + meta/why-skipped.md → 提议转 lessons/失败模式

按 spec/tasks.md §3.5.3 实施: 每周跑一次汇总本周失败场景, 统计高频 + 提议提升到 lessons/ 或 failure-modes.

Usage:
    python scripts/lessons/weekly_summary.py           # 汇总当前 + 输出建议
    python scripts/lessons/weekly_summary.py --days 7  # 自定义窗口 (默认 7)
    python scripts/lessons/weekly_summary.py --apply   # 自动追加到 lessons/ (P0 only)
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path
_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: F401  (UTF-8 stdout for Windows cp936)

import argparse
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]
AI_MEMORY = REPO_ROOT_DEFAULT / ".ai-memory"
E2E_FAILURES_LOG = REPO_ROOT_DEFAULT / ".trash" / ".e2e-failures.log"
WHY_SKIPPED = AI_MEMORY / "meta" / "why-skipped.md"
LESSONS_DIR = AI_MEMORY / "lessons"

# Block marker: a run record begins with ``# e2e run @ <timestamp>``.
_RUN_HEADER_RE = re.compile(r"^# e2e run @ (?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})$")
# Failure line: ``- FAIL  <name>: <detail>``
_FAIL_LINE_RE = re.compile(r"^- FAIL\s+(?P<name>\S+):\s*(?P<detail>.+)$")


def _parse_window(log: Path, days: int) -> List[Tuple[datetime, str, str]]:
    """Return [(timestamp, scenario_name, detail), ...] inside the window."""
    if not log.exists():
        return []
    cutoff = datetime.now() - timedelta(days=days)
    out: List[Tuple[datetime, str, str]] = []
    cur_ts: datetime | None = None
    raw = log.read_text(encoding="utf-8-sig", errors="replace")  # strip BOM
    for line in raw.splitlines():
        m = _RUN_HEADER_RE.match(line)
        if m:
            cur_ts = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S")
            continue
        m = _FAIL_LINE_RE.match(line)
        if m and cur_ts is not None and cur_ts >= cutoff:
            out.append((cur_ts, m.group("name"), m.group("detail")))
    return out


def _aggregate(records: List[Tuple[datetime, str, str]]) -> Dict[str, int]:
    """Count failures by scenario name (top-N later)."""
    return Counter(name for _, name, _ in records)


def _propose_lessons(counter: Counter, threshold: int) -> List[str]:
    """Return a list of 'candidate' scenario names that crossed ``threshold``."""
    return [name for name, count in counter.most_common() if count >= threshold]


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GAF weekly e2e summary (M2.E)")
    parser.add_argument(
        "--days", type=int, default=7, help="Window in days (default 7)"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        help="Min failure count to propose a lesson (default 3)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Append stub lessons to lessons/ for P0 candidates (off by default)",
    )
    args = parser.parse_args(argv)

    records = _parse_window(E2E_FAILURES_LOG, args.days)
    if not records:
        print(f"✅ No e2e failures in the last {args.days} day(s).")
        return 0

    counter = _aggregate(records)
    print(f"📊 Weekly summary (last {args.days} day, {len(records)} failure records):\n")
    print("| scenario | count | propose-lesson? |")
    print("|----------|------:|:---------------:|")
    for name, count in counter.most_common():
        propose = "✅" if count >= args.threshold else "·"
        print(f"| `{name}` | {count} | {propose} |")
    print()

    candidates = _propose_lessons(counter, args.threshold)
    if not candidates:
        print(f"ℹ️  No scenario crossed the {args.threshold}-failure threshold.")
        return 0

    print(f"🚨 {len(candidates)} scenario(s) crossed the threshold:")
    for name in candidates:
        print(f"  - `{name}` ({counter[name]} failures)")

    if not args.apply:
        print(
            "\nℹ️  Re-run with --apply to append stub lessons to .ai-memory/lessons/."
        )
        return 0

    # --apply: write stub lessons for each candidate.
    written: List[str] = []
    today = datetime.now().strftime("%Y-%m-%d")
    for name in candidates:
        target = LESSONS_DIR / f"{today}-m2e-{name.replace('_', '-')}-recurring.md"
        if target.exists():
            continue
        target.write_text(
            f"""---
id: m2e-{name}-recurring
date: {today}
priority: high
symptom: e2e scenario `{name}` failed {counter[name]} times in the last {args.days} days
root_cause: TBD (run `python scripts/lessons/weekly_summary.py --days 30` for richer signal)
trigger: "python scripts/e2e/run_all.py {name}" exits non-zero
solution: |
  AI MUST investigate recurring failure:
  1. Re-run the failing scenario with --strict and capture the traceback
  2. Read meta/why-skipped.md for the latest triage hint
  3. Apply the fix per the N91 mapping table or spec/tasks.md §<relevant>
  4. Re-run the full suite to confirm green
related_files:
  - .ai-memory/ops/why-skipped.md
  - .trash/.e2e-failures.log
  - scripts/e2e/run_all.py
created_by: weekly_summary.py
---
## 背景

{counter[name]} 次失败, 触发 weekly review (M2.E)。

## 行动清单
- [ ] 跑 `python scripts/e2e/run_all.py {name} --strict` 复现
- [ ] 读 meta/why-skipped.md 最新 triage hint
- [ ] 修复并 5 层分发 (N95)
""",
            encoding="utf-8",
        )
        written.append(str(target.relative_to(REPO_ROOT_DEFAULT)))

    if written:
        print("\n✍️  Wrote stub lessons:")
        for w in written:
            print(f"  - {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
