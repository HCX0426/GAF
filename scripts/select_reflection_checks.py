"""select_reflection_checks.py — P4 治本机制: 按 git diff 自动选 Y/N 反思项.

治本理由 (spec 2026-07-16-ai-thinking-chain-slim.md P4):
- 旧机制: 24 项 Y/N 让 AI 自决跑哪些 → 走形式 / 漏检查
- 新机制: 脚本按 diff 关键词自动选 3-6 项 → 既不漏也不走形式

关键词映射表 (spec P4 §关键词映射表 + 2026-07-17 N166/N167 扩展):
| 关键词 (diff 路径/内容)         | 自动激活 Y/N                  | yn-matrices sub-file      |
|--------------------------------|-------------------------------|---------------------------|
| backend/*/models.py            | N112 跨层同步 + N128 状态 3 步 | _cross-layer-sync.md      |
| backend/*/serializers.py       | N112 跨层同步 + N128 状态 3 步 | _cross-layer-sync.md      |
| scripts/sync_*.py              | N116 并发 + N117 决策树 log   | _misc.md §concurrency     |
| frontend/src/types/models.ts   | N112 跨层同步                 | _cross-layer-sync.md      |
| pytest/mypy/ruff 命令          | N111 命令使用                 | _ai-autonomy.md           |
| git add/commit                 | N150/N153 pre-commit stash    | _workflow.md §7           |
| .skills/rules/*.md               | N166 L3 循环 + N167 七维度    | _refactor-dimensions.md   |
| .skills/skills/*.md              | N166 L3 循环 + N167 七维度    | _refactor-dimensions.md   |
| docs/standards/*.md            | N167 七维度                   | _refactor-dimensions.md   |
| docs/specs/active/*.md         | N160 范围外关注               | _workflow.md              |
| 默认 (无匹配)                  | 3 项核心兜底                  | 多个                      |

Run:
    python scripts/select_reflection_checks.py              # 默认 diff HEAD~1
    python scripts/select_reflection_checks.py --diff HEAD~3
    python scripts/select_reflection_checks.py --diff <ref>
    python scripts/select_reflection_checks.py --no-default # 不补默认核心
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

# Path patterns: (regex, [N## ...], yn-matrices sub-file)
# git diff --name-only 输出用正斜杠, 正则按 POSIX 路径匹配
PATH_PATTERNS: List[Tuple[str, List[str], str]] = [
    (r"^backend/.*/models\.py$", ["N112", "N128"], "_cross-layer-sync.md"),
    (r"^backend/.*/serializers\.py$", ["N112", "N128"], "_cross-layer-sync.md"),
    (r"^scripts/sync_.*\.py$", ["N116", "N117"], "_misc.md"),
    # sync_ai_memory.py lives under scripts/bootstrap/ after the reorg; the
    # generic `^scripts/sync_.*\.py$` pattern above does not match it, so we
    # add an explicit pattern to keep N116/N117 coverage.
    (r"^scripts/bootstrap/sync_ai_memory\.py$", ["N116", "N117"], "_misc.md"),
    (r"^scripts/bootstrap/sync_skills\.py$", ["N117"], "_workflow.md"),
    (r"^scripts/lessons/promote_lessons\.py$", ["N95"], "_workflow.md"),
    (r"^frontend/src/types/models\.ts$", ["N112"], "_cross-layer-sync.md"),
    (r"^docs/specs/active/.*\.md$", ["N160"], "_workflow.md"),
(r"^\.skills/rules/.*\.md$", ["N166", "N167"], "_refactor-dimensions.md"),
(r"^\.skills/skills/.*SKILL\.md$", ["N117", "N124", "N166", "N167"], "_refactor-dimensions.md"),
    (r"^docs/standards/.*\.md$", ["N167"], "_refactor-dimensions.md"),
    (r"^\.ai-memory/meta/failure-modes\.md$", ["N95", "N132"], "_workflow.md"),
]

# Content patterns: (regex, [N## ...], sub-file) — search diff body
CONTENT_PATTERNS: List[Tuple[str, List[str], str]] = [
    (r"\bpytest\b|\bmypy\b|\bruff\b", ["N111"], "_ai-autonomy.md"),
    (r"\bgit add\b|\bgit commit\b", ["N150", "N153"], "_workflow.md"),
    (r"pre-commit|pre_commit", ["N91", "N150"], "_workflow.md"),
    (r"evidence/", ["N97"], "_workflow.md"),
]

# Default 3 core checks (fallback when no path/content matches)
# v9.3 瘦身 (2026-07-16): 从 6 项减到 3 项, 降低中小修改反思负担
# 保留最核心的 3 项: evidence commit / AI 自决 / 诚实标记
DEFAULT_CORE_CHECKS: List[Tuple[str, str]] = [
    ("N97", "_workflow.md"),           # evidence commit (飞轮读侧断裂)
    ("N109", "_ai-autonomy.md"),       # AI self-decision (计划内任务不停不问)
    ("N128", "_honest-status.md"),     # honest status 3-step verification
]

MAX_CHECKS = 6
MIN_CHECKS = 3
DIFF_CONTENT_LIMIT = 50000  # 50KB cap to avoid huge diff parsing


def run_git_diff_names(ref: str) -> List[str]:
    """Run ``git diff --name-only <ref>``. Returns [] on any failure."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", ref],
            cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode != 0:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return []


def run_git_diff_content(ref: str) -> str:
    """Run ``git diff <ref>``. Returns '' on failure. Capped at 50KB."""
    try:
        result = subprocess.run(
            ["git", "diff", ref],
            cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode != 0:
            return ""
        return result.stdout[:DIFF_CONTENT_LIMIT]
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return ""


def select_checks(paths: List[str], diff_content: str) -> List[Tuple[str, str]]:
    """Select Y/N checks by path + content patterns.

    Returns list of (N##, yn-matrices sub-file). First match wins per N##.
    Pads to MIN_CHECKS with DEFAULT_CORE_CHECKS; trims to MAX_CHECKS.
    """
    selected: Dict[str, str] = {}  # N## -> sub-file (first match wins)

    # Path patterns
    for path in paths:
        for pattern, n_ids, sub_file in PATH_PATTERNS:
            if re.search(pattern, path):
                for n_id in n_ids:
                    if n_id not in selected:
                        selected[n_id] = sub_file

    # Content patterns
    for pattern, n_ids, sub_file in CONTENT_PATTERNS:
        if re.search(pattern, diff_content, re.MULTILINE):
            for n_id in n_ids:
                if n_id not in selected:
                    selected[n_id] = sub_file

    result: List[Tuple[str, str]] = list(selected.items())

    # Pad to MIN_CHECKS with default core checks
    if len(result) < MIN_CHECKS:
        for n_id, sub_file in DEFAULT_CORE_CHECKS:
            if n_id not in selected:
                result.append((n_id, sub_file))
                if len(result) >= MIN_CHECKS:
                    break

    # Trim to MAX_CHECKS
    if len(result) > MAX_CHECKS:
        result = result[:MAX_CHECKS]

    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="P4 治本机制: 按 git diff 自动选 Y/N 反思项 (3-6 项)"
    )
    parser.add_argument("--diff", default="HEAD~1",
                        help="git diff ref (default: HEAD~1)")
    parser.add_argument("--no-default", action="store_true",
                        help="Do not pad with default 3 core checks (output matched only)")
    args = parser.parse_args(argv)

    paths = run_git_diff_names(args.diff)
    diff_content = run_git_diff_content(args.diff)

    if not paths and not diff_content:
        print(f"⚠️ git diff {args.diff} 无输出 (可能是首次 commit 或 ref 不存在)",
              file=sys.stderr)
        if args.no_default:
            print("# --no-default 模式: 无匹配, 不输出默认项")
            return 0
        print("# 使用默认 3 项核心兜底:")
        for n_id, sub_file in DEFAULT_CORE_CHECKS:
            print(f"- [ ] {n_id}: Read .ai-memory/meta/yn-matrices/{sub_file}")
        return 0

    selected = select_checks(paths, diff_content)

    # --no-default: strip padded default checks (keep only matched)
    if args.no_default:
        matched_only = [(n, s) for n, s in selected
                        if any(n in n_ids for _, n_ids, _ in PATH_PATTERNS + CONTENT_PATTERNS)]
        selected = matched_only if matched_only else selected

    print(f"# P4 反思清单自动选择 (diff: {args.diff})")
    print(f"# 扫描 {len(paths)} 个文件改动, 选中 {len(selected)} 项 Y/N:")
    print()
    for n_id, sub_file in selected:
        print(f"- [ ] {n_id}: Read .ai-memory/meta/yn-matrices/{sub_file}")
    print()
    print("# AI 按上述清单 Read sub-file → 跑 Y/N 检查 → 填反思矩阵")
    return 0


if __name__ == "__main__":
    sys.exit(main())
