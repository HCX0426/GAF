"""step_checkpoint.py — B1 治本机制: 决策树 step checkpoint

Write per-step checkpoint files so interrupted tasks can resume at the
exact step (not the spec phase level).

Checkpoint file: .ai-memory/session/<task_id>.json
Format: {task_id, task_type, last_step, timestamp, status}

Usage:
    python scripts/step_checkpoint.py mark <task_id> <task_type> <step>
    python scripts/step_checkpoint.py next <task_id>
    python scripts/step_checkpoint.py list
    python scripts/step_checkpoint.py done <task_id>      # mark complete
    python scripts/step_checkpoint.py --json              # with list action

治本机制 (B1, 2026-07-16):
- 旧机制: spec 阶段状态表是粗粒度 (P1-P6), 决策树 step 级打断后只能从阶段开头重跑
- 新机制: step 级 checkpoint 写文件, 恢复时脚本输出下一步, AI 精确续接
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSION_DIR = REPO_ROOT / ".ai-memory" / "session"

# Step order per task_type (from gaf-orchestrator decision tree)
STEP_ORDER: Dict[str, List[str]] = {
    "new_feature": [
        "step_1", "step_2_read_context", "step_3_load_kb",
        "step_4_check_lessons", "step_5_implement", "step_6_verify_before_commit",
    ],
    "bug_fix": [
        "step_1", "step_2_read_context", "step_3_search_lessons",
        "step_4_diagnose", "step_5_fix_and_reflect", "step_6_verify_before_commit",
    ],
    "documentation": [
        "step_1", "step_2_read_context", "step_3_route_to_target",
        "step_4_write", "step_5_sync", "step_6_verify_before_commit",
    ],
    "refactor": [
        "step_1", "step_2_read_context", "step_3_assess_impact",
        "step_4_plan", "step_5_execute", "step_6_verify_before_commit",
    ],
    "unknown": [
        "step_1_probe_signals", "step_2_read_context", "step_3_clarify_or_ask",
    ],
}


def checkpoint_path(task_id: str) -> Path:
    """Return checkpoint file path for a task_id."""
    safe_id = task_id.replace("/", "_").replace("\\", "_")
    return SESSION_DIR / f"{safe_id}.json"


def write_checkpoint(task_id: str, task_type: str, step: str, status: str = "in_progress") -> Path:
    """Write a checkpoint file. Creates SESSION_DIR if needed."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    path = checkpoint_path(task_id)
    data: Dict[str, Any] = {
        "task_id": task_id,
        "task_type": task_type,
        "last_step": step,
        "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
        "status": status,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_checkpoint(task_id: str) -> Optional[Dict[str, Any]]:
    """Read a checkpoint file. Returns None if not found."""
    path = checkpoint_path(task_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def next_step(task_id: str) -> Optional[str]:
    """Return the next step after the last completed step, or None if done."""
    cp = read_checkpoint(task_id)
    if not cp:
        return None
    task_type = cp["task_type"]
    last_step = cp["last_step"]
    steps = STEP_ORDER.get(task_type, [])
    if last_step not in steps:
        return steps[0] if steps else None
    idx = steps.index(last_step)
    if idx + 1 < len(steps):
        return steps[idx + 1]
    return None  # last step completed


def list_active() -> List[Dict[str, Any]]:
    """List all active (non-done) checkpoints."""
    if not SESSION_DIR.exists():
        return []
    active = []
    for path in sorted(SESSION_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("status") != "done":
                active.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return active


def mark_done(task_id: str) -> bool:
    """Mark a task as done (status=done, keeps file for history)."""
    cp = read_checkpoint(task_id)
    if not cp:
        return False
    write_checkpoint(task_id, cp["task_type"], cp["last_step"], status="done")
    return True


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="B1 治本机制: 决策树 step checkpoint")
    sub = parser.add_subparsers(dest="action", required=True)

    p_mark = sub.add_parser("mark", help="Write a checkpoint")
    p_mark.add_argument("task_id", help="Task identifier (e.g. spec-phase-P3)")
    p_mark.add_argument("task_type", choices=list(STEP_ORDER.keys()), help="Task type")
    p_mark.add_argument("step", help="Step name (e.g. step_3_load_kb)")

    p_next = sub.add_parser("next", help="Get next step for a task")
    p_next.add_argument("task_id")

    p_done = sub.add_parser("done", help="Mark task complete")
    p_done.add_argument("task_id")

    sub.add_parser("list", help="List active checkpoints")

    parser.add_argument("--json", action="store_true", help="JSON output (with list action)")

    args = parser.parse_args(argv)

    if args.action == "mark":
        path = write_checkpoint(args.task_id, args.task_type, args.step)
        print(f"✅ Checkpoint written: {path.relative_to(REPO_ROOT)}")
        print(f"   task_id={args.task_id} task_type={args.task_type} step={args.step}")
        return 0

    if args.action == "next":
        cp = read_checkpoint(args.task_id)
        if not cp:
            print(f"❌ No checkpoint for task_id={args.task_id}")
            return 1
        ns = next_step(args.task_id)
        if ns:
            print(f"# 任务恢复: {args.task_id}")
            print(f"  上次完成: {cp['last_step']} ({cp['timestamp']})")
            print(f"  下一步: {ns}")
            print(f"  task_type: {cp['task_type']}")
            print(f"  → Read gaf-orchestrator/SKILL.md {cp['task_type']} 分支 {ns}")
        else:
            print(f"# 任务已完成最后一步: {cp['last_step']}")
            print(f"  → 若需结束, 跑: python scripts/step_checkpoint.py done {args.task_id}")
        return 0

    if args.action == "done":
        if mark_done(args.task_id):
            print(f"✅ Marked done: {args.task_id}")
            return 0
        print(f"❌ No checkpoint for task_id={args.task_id}")
        return 1

    if args.action == "list":
        active = list_active()
        if args.json:
            print(json.dumps(active, ensure_ascii=False, indent=2))
        elif not active:
            print("# 活跃任务: (无)")
        else:
            print(f"# 活跃任务 ({len(active)}):")
            for cp in active:
                ns = next_step(cp["task_id"]) or "(last step)"
                print(f"  - {cp['task_id']} [{cp['task_type']}] last={cp['last_step']} next={ns} ({cp['timestamp']})")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
