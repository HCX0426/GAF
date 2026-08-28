"""execution_rate.py — 自动追踪 N## 治理规则执行率

扫描 .ai-memory/session-traces/ 中的 thinking trace 文件, 统计每个 N## 规则的触发频次,
计算近 30 天的执行率, 生成治理效果报告.

Usage:
    python scripts/governance/execution_rate.py
    python scripts/governance/execution_rate.py --days 14
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
TRACES_DIR = REPO_ROOT / ".ai-memory" / "session-traces"
LESSONS_DIR = REPO_ROOT / ".ai-memory" / "lessons"
REPORT_DIR = REPO_ROOT / ".ai-memory" / "governance"
REPORT_FILE = REPORT_DIR / "execution-rate-report.md"

N_PATTERN = re.compile(r"N(\d{2,3})")

N_RATE_THRESHOLD_ACTIVE = 50
N_RATE_THRESHOLD_DORMANT = 10


def _find_n_lesson_title(n_id: str) -> str | None:
    """Find the display title for an N## rule from its lesson file."""
    n_int = int(n_id)
    for lesson_file in LESSONS_DIR.glob(f"N{n_int}-*.md"):
        if lesson_file.is_file():
            content = lesson_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    return stripped[2:].strip()
    return None


def _extract_n_ids_from_value(value: str) -> list[str]:
    """Extract all N## IDs from a string."""
    found = set()
    for match in N_PATTERN.finditer(value):
        found.add(match.group(1))
    return sorted(found)


def _extract_n_ids_from_obj(obj: Any) -> set[str]:
    """Recursively extract N## IDs from any JSON-serializable object."""
    found: set[str] = set()
    if isinstance(obj, str):
        found.update(_extract_n_ids_from_value(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            found.update(_extract_n_ids_from_obj(v))
    elif isinstance(obj, list):
        for item in obj:
            found.update(_extract_n_ids_from_obj(item))
    return found


def _parse_trace_json(file_path: Path) -> set[str]:
    """Parse a trace JSON file and extract all N## IDs referenced."""
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    return _extract_n_ids_from_obj(data)


def _parse_trace_text(file_path: Path) -> set[str]:
    """Fallback: scan raw text for N## patterns."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    return set(_extract_n_ids_from_value(content))


def scan_traces(days: int) -> dict[str, Any]:
    """Scan trace files from the last N days and compute execution rates."""
    if not TRACES_DIR.exists():
        return {"total_traces": 0, "n_stats": {}, "report": ""}

    cutoff = _dt.datetime.now().timestamp() - (days * 86400)

    trace_files = sorted(
        [f for f in TRACES_DIR.iterdir() if f.is_file() and f.suffix == ".json"],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    recent_files = [f for f in trace_files if f.stat().st_mtime >= cutoff]

    n_counts: dict[str, int] = defaultdict(int)
    n_cache: dict[str, str] = {}

    for trace_file in recent_files:
        n_ids = _parse_trace_json(trace_file)
        if not n_ids:
            n_ids = _parse_trace_text(trace_file)
        for n_id in n_ids:
            n_counts[n_id] += 1

    total = len(recent_files)

    n_stats: dict[str, dict[str, Any]] = {}
    for n_id in sorted(n_counts.keys(), key=lambda x: int(x)):
        count = n_counts[n_id]
        rate = (count / total * 100) if total > 0 else 0.0
        title = n_cache.get(n_id)
        if title is None:
            title = _find_n_lesson_title(n_id) or f"N{n_id}"
            n_cache[n_id] = title

        if rate >= N_RATE_THRESHOLD_ACTIVE:
            status = "有效治理"
        elif rate >= N_RATE_THRESHOLD_DORMANT:
            status = "形式化治理 ⚠️"
        else:
            status = "深度休眠"

        n_stats[f"N{n_id}"] = {
            "title": title,
            "count": count,
            "total": total,
            "rate": round(rate, 1),
            "status": status,
        }

    report = _generate_report(n_stats, total, days)

    return {
        "total_traces": total,
        "n_stats": n_stats,
        "report": report,
    }


def _generate_report(n_stats: dict[str, dict[str, Any]], total: int, days: int) -> str:
    """Generate formatted report string."""
    lines = [
        "=== GAF 治理规则执行率报告 ===",
        f"Period: last {days} days",
        f"Total tasks: {total}",
        "",
    ]

    if not n_stats:
        lines.append("(无 N## 规则执行数据 — session-traces 目录为空或无近 30 天记录)")
        return "\n".join(lines)

    for n_id, stat in sorted(n_stats.items(), key=lambda x: -x[1]["rate"]):
        pct = f"{stat['rate']:.0f}%"
        title = stat["title"]
        lines.append(
            f"{n_id} ({title}): {stat['count']}/{stat['total']} tasks → {pct} ({stat['status']})"
        )

    lines.append("")

    suggestions: list[str] = []
    for n_id, stat in sorted(n_stats.items(), key=lambda x: x[1]["rate"]):
        if stat["rate"] < N_RATE_THRESHOLD_ACTIVE:
            suggestions.append(
                f"建议: {n_id} 执行率 {stat['rate']:.0f}% < {N_RATE_THRESHOLD_ACTIVE}%, "
                f"建议降级为 Dormant 或补充触发条件"
            )

    if suggestions:
        lines.append("---")
        lines.append("建议:")
        lines.extend(suggestions)

    return "\n".join(lines)


def write_report_md(report: str, n_stats: dict[str, Any], total: int, days: int) -> Path:
    """Write report to .ai-memory/governance/execution-rate-report.md."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# GAF 治理规则执行率报告",
        "",
        f"_Generated: {now}_",
        f"_Period: last {days} days ({total} tasks)_",
        "",
        "## 执行率明细",
        "",
    ]

    if n_stats:
        lines.append("| N## | 规则名称 | 执行次数 | 总任务数 | 执行率 | 状态 |")
        lines.append("|-----|----------|----------|----------|--------|------|")
        for n_id, stat in sorted(n_stats.items(), key=lambda x: -x[1]["rate"]):
            pct_str = f"{stat['rate']:.1f}%"
            lines.append(
                f"| {n_id} | {stat['title']} | {stat['count']} | {stat['total']} | {pct_str} | {stat['status']} |"
            )
    else:
        lines.append("_无数据_")

    lines.append("")

    lines.append("## 建议")
    lines.append("")
    suggestions: list[str] = []
    for n_id, stat in sorted(n_stats.items(), key=lambda x: x[1]["rate"]):
        if stat["rate"] < N_RATE_THRESHOLD_ACTIVE:
            suggestions.append(
                f"- **{n_id}** ({stat['title']}): 执行率 {stat['rate']:.0f}% < {N_RATE_THRESHOLD_ACTIVE}%, "
                f"建议降级为 Dormant 或补充触发条件"
            )
    if suggestions:
        lines.extend(suggestions)
    else:
        lines.append("_所有规则执行率均达标_")

    lines.append("")
    lines.append("## 原始报告")
    lines.append("")
    lines.append("```")
    lines.append(report)
    lines.append("```")
    lines.append("")

    content = "\n".join(lines)
    REPORT_FILE.write_text(content, encoding="utf-8")
    return REPORT_FILE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="自动追踪 N## 治理规则执行率"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="统计周期 (天数, 默认: 30)",
    )
    args = parser.parse_args(argv)

    result = scan_traces(days=args.days)

    print(result["report"])

    path = write_report_md(
        result["report"], result["n_stats"], result["total_traces"], args.days
    )
    print(f"\n报告已写入: {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())