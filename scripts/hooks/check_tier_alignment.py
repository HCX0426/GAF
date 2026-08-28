"""check_tier_alignment.py — v9.2 Spec C-3: 修改判级 hook 后验 (warn-only).

背景: 小/中/大修改判级此前完全靠 AI 自评行数, 规则层无法发现"把中修改
当小修改跳过评估/反思"的静默降级. 此 hook 在 commit 时按 staged diff 实际
行数机械判定级别并输出该级别的强制清单, 提供后验反馈.

语义:
- <50 行   → 小修改 (快速路径, 无要求), 静默通过
- 50-500 行 → 中修改: 输出 3 维评估 + 5 项反思 + 分级测试提醒; 若 staged
  同时未触及任何测试文件, 追加 ⚠️ 提醒 (不阻塞)
- >500 行  → 大修改: 交给 check_big_change_hook.py 强制 B2 evidence (本
  hook 只打印一行提示, 不重复阻塞)

退出码恒 0 (warn-only): 判级反馈是提示, 强制力仍由既有 hooks 承担
(B2 evidence / 分级测试由 CI 或阶段验收兜底).

Usage:
    python scripts/hooks/check_tier_alignment.py            # pre-commit
    python scripts/hooks/check_tier_alignment.py --no-fail  # 同义 (恒 warn)
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout)

import argparse  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[2]

MEDIUM_THRESHOLD = 50
BIG_THRESHOLD = 500

TEST_PATH_HINTS = ("tests/", "test_", "_test", "conftest", "testing")


def _staged_numstat(repo_root: Path) -> tuple[int, int, list[str]]:
    """Return (added, deleted, changed_paths) for staged changes."""
    try:
        r = subprocess.run(
            ["git", "diff", "--cached", "--numstat"],
            cwd=repo_root, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return 0, 0, []
    added = deleted = 0
    paths: list[str] = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, d, p = parts[0], parts[1], parts[2]
        added += int(a) if a.isdigit() else 0
        deleted += int(d) if d.isdigit() else 0
        paths.append(p)
    return added, deleted, paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="v9.2 Spec C-3: 修改判级后验 (staged diff 行数 → 级别清单)",
    )
    parser.add_argument(
        "--root", default=str(REPO_ROOT_DEFAULT),
        help="GAF repo root (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    repo_root = Path(args.root).resolve()

    added, deleted, paths = _staged_numstat(repo_root)
    total = added + deleted
    if total == 0:
        return 0  # empty stage (e.g. commit -a handled by git before hooks)

    if total > BIG_THRESHOLD:
        print(f"📊 tier-check: 大修改 ({total} 行) — B2 evidence 由 check_big_change_hook 强制")
        return 0

    if total >= MEDIUM_THRESHOLD:
        has_tests = any(any(h in p for h in TEST_PATH_HINTS) for p in paths)
        print(f"📊 tier-check: 中修改 ({total} 行) — 要求: 七维度 3 维 (1/2/7；bug 修复 1/2/4/7)"
              f" + 反思 5 项 + 相关 pytest + lint (<60s)")
        if not has_tests:
            print("  ⚠️  staged 未触及任何测试文件 — 请确认已跑相关 pytest 或说明豁免理由")
        return 0

    return 0  # 小修改: 快速路径, 静默


if __name__ == "__main__":
    sys.exit(main())
