"""check_section_numbers.py — 规范文档章节序号一致性检查 (2026-08-29).

背景: api-contract.md / backend-conventions.md 等规范文档按 ``## N.`` 编号组织,
历史多次出现"新增章节时重号/跳号" (本次 TD-420/421 追加时即与既有 §19 冲突).
本检查器对所有含 ``## <int>.`` 顶层章节的规范文档验证:

  - error   : 重复章节号 (两个不同标题使用同一数字) → 阻断
  - warning : 章节号不连续 (跳号, 允许 1..N 含空号但提示人工确认)

Usage::

    python scripts/hooks/check_section_numbers.py
    python scripts/hooks/check_section_numbers.py --no-fail

Exit codes
----------
    0 - 无 error (warning 允许存在)
    1 - 发现重复章节号
    2 - 配置/参数错误
"""
# ruff: noqa: I001  # _encoding_safe must stay first; do not reorder imports
from __future__ import annotations

import re
import sys as _sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: E402,E401,F401  (must be first; reconfigures stdout to UTF-8)

import argparse  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

# 需要章节号强制一致的规范文档 (相对 repo 根)。
# 新增规范文档时在此登记, 避免漏检。
DOCUMENTED_DOCS = [
    "docs/standards/api-contract.md",
    "docs/standards/backend-conventions.md",
    "docs/standards/frontend-conventions.md",
]

# 匹配顶层章节: "## 19. 标题"
_TOP_HEADING = re.compile(r"^##\s+(\d+)\s*\.\s+", re.MULTILINE)


def _scan_doc(path: Path) -> tuple[list[str], list[str]]:
    """扫描单个文档, 返回 (errors, warnings).

    error: 重复章节号; warning: 跳号 (存在空洞, 仅提示)。
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    numbers = [int(m.group(1)) for m in _TOP_HEADING.finditer(text)]

    errors: list[str] = []
    warnings: list[str] = []

    seen: dict[int, str] = {}
    for num in numbers:
        if num in seen:
            errors.append(
                f"重复章节号 {num} (标题 '{seen[num]}' 与后续章节共用)",
            )
        else:
            seen[num] = f"## {num}."

    if numbers:
        max_num = max(numbers)
        present = set(numbers)
        missing = [n for n in range(1, max_num + 1) if n not in present]
        if missing:
            warnings.append(
                f"章节号不连续, 缺失: {missing} (若为按需跳号可忽略)",
            )

    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="规范文档章节序号一致性检查")
    parser.add_argument("--root", type=str, default=str(REPO_ROOT), help="repo 根目录")
    parser.add_argument("--no-fail", action="store_true", help="warn-only 模式, 不阻断")
    args = parser.parse_args(argv)

    root = Path(args.root)
    all_errors: list[str] = []
    all_warnings: list[str] = []

    for rel in DOCUMENTED_DOCS:
        path = root / rel
        if not path.exists():
            all_warnings.append(f"登记文档缺失 (跳过): {rel}")
            continue
        errors, warnings = _scan_doc(path)
        for e in errors:
            all_errors.append(f"{rel}: {e}")
        for w in warnings:
            all_warnings.append(f"{rel}: {w}")

    for w in all_warnings:
        print(f"  [WARN] {w}")
    for e in all_errors:
        print(f"  [ERROR] {e}")

    if all_errors:
        print(f"[check-section-numbers] 发现 {len(all_errors)} 个重复章节号")
        return 0 if args.no_fail else 1
    if all_warnings:
        print("[check-section-numbers] 无重复, 有跳号警告 (可忽略)")
    else:
        print("[check-section-numbers] 全部规范文档章节号一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
