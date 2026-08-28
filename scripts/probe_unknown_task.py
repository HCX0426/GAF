"""probe_unknown_task.py — B4 治本机制: unknown 分支探测流程

Collect 3 types of signals to help AI determine task_type when unknown:
1. Active pending-roadmap entries (P-NNN with ⏳/🔧/🚧 status)
2. Recent spec files (by mtime, top 3)
3. Conversation keywords (skipped — AI self-extracts from recent turns)

Output: JSON {roadmap_hints, recent_specs, suggested_task_type}

Usage:
    python scripts/probe_unknown_task.py
    python scripts/probe_unknown_task.py --json

治本机制 (B4, 2026-07-16):
- 旧机制: unknown 仅 2 步 (读 failure-modes + lessons), 探测维度严重不足
- 新机制: 3 类信号自动收集, 覆盖 §3.6 "已计划任务"5 种来源中的 3 种
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
ROADMAP_PATH = REPO_ROOT / "docs" / "pending-roadmap.md"
SPECS_DIR = REPO_ROOT / "docs" / "specs" / "active"

# Active status markers in pending-roadmap.md (per docs/pending-roadmap.md)
ACTIVE_STATUS_MARKERS = ("⏳", "🔧", "🚧")

# Roadmap table row pattern: | P-NNN | priority | module | item | status | when | ref |
ROADMAP_ROW_RE = re.compile(
    r"^\|\s*(P-\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]*)\|"
)


def collect_roadmap_hints() -> List[Dict[str, str]]:
    """Parse pending-roadmap.md and return active P-NNN entries.

    Returns list of dicts: {id, priority, module, item, status, when, ref}.
    Only entries with active status markers (⏳/🔧/🚧) are returned.
    """
    if not ROADMAP_PATH.exists():
        return []
    text = ROADMAP_PATH.read_text(encoding="utf-8")
    hints: List[Dict[str, str]] = []
    for line in text.splitlines():
        m = ROADMAP_ROW_RE.match(line)
        if not m:
            continue
        p_id = m.group(1).strip()
        priority = m.group(2).strip()
        module = m.group(3).strip()
        item = m.group(4).strip()
        status = m.group(5).strip()
        when = m.group(6).strip()
        ref = m.group(7).strip()
        # Only active status markers
        if not any(marker in status for marker in ACTIVE_STATUS_MARKERS):
            continue
        hints.append(
            {
                "id": p_id,
                "priority": priority,
                "module": module,
                "item": item,
                "status": status,
                "when": when,
                "ref": ref,
            }
        )
    return hints


def collect_recent_specs(top_n: int = 3) -> List[Dict[str, str]]:
    """Glob specs/*.md and return top N by mtime.

    Returns list of dicts: {path, mtime, title}.
    """
    if not SPECS_DIR.exists():
        return []
    spec_files = sorted(SPECS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    specs: List[Dict[str, str]] = []
    for path in spec_files[:top_n]:
        mtime = _dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        # Extract title from first `# ` heading
        title = path.name
        try:
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
        except (OSError, UnicodeDecodeError):
            pass
        specs.append({"path": str(path.relative_to(REPO_ROOT)), "mtime": mtime, "title": title})
    return specs


def suggest_task_type(roadmap_hints: List[Dict[str, str]], recent_specs: List[Dict[str, str]]) -> str:
    """Heuristic suggestion based on collected signals.

    Returns one of: new_feature / bug_fix / refactor / documentation / unknown.
    Confidence is low — AI should still verify against conversation context.
    """
    # If recent spec has "Phase" + ⏳/🔄 markers → likely new_feature/bug_fix continuation
    for spec in recent_specs[:1]:
        try:
            text = (REPO_ROOT / spec["path"]).read_text(encoding="utf-8")
            if "⏳" in text or "🔄" in text:
                return "new_feature"  # spec continuation
        except (OSError, UnicodeDecodeError):
            pass
    # If roadmap has active entries → likely new_feature
    if roadmap_hints:
        return "new_feature"
    return "unknown"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="B4 治本机制: unknown 分支探测流程")
    parser.add_argument("--json", action="store_true", help="Output as JSON (default: human-readable)")
    args = parser.parse_args(argv)

    roadmap_hints = collect_roadmap_hints()
    recent_specs = collect_recent_specs()
    suggested = suggest_task_type(roadmap_hints, recent_specs)

    result: Dict[str, Any] = {
        "roadmap_hints": roadmap_hints,
        "recent_specs": recent_specs,
        "suggested_task_type": suggested,
        "note": "Conversation keywords not auto-collected; AI should self-extract from recent 3 turns.",
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"# B4 unknown 分支探测结果 ({_dt.date.today()})")
        print()
        print(f"## 建议任务类型: {suggested}")
        print()
        print(f"## Roadmap 活跃条目 ({len(roadmap_hints)}):")
        if roadmap_hints:
            for h in roadmap_hints:
                print(f"  - {h['id']} [{h['priority']}] {h['module']}: {h['item']} ({h['status']})")
        else:
            print("  (无活跃条目)")
        print()
        print(f"## 最近 Spec 文件 ({len(recent_specs)}):")
        for s in recent_specs:
            print(f"  - {s['path']} ({s['mtime']})")
            print(f"    {s['title']}")
        print()
        print("## 对话关键词:")
        print("  (AI 自取最近 3 轮用户消息关键词, 脚本无对话访问权)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
