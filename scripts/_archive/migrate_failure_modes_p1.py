"""migrate_failure_modes_p1.py — P1-4 + P1-14 (failure-modes.md 部分).

执行:
1. §Active 表格加 2 列: trigger_count + last_triggered (初始 0 + -)
2. 所有 lessons/<old>.md 链接替换为新文件名

Usage:
    python scripts/migrate_failure_modes_p1.py --dry-run
    python scripts/migrate_failure_modes_p1.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LESSONS_DIR = REPO_ROOT / ".ai-memory" / "lessons"
FM_PATH = REPO_ROOT / ".ai-memory" / "meta" / "failure-modes.md"

FILENAME_RE = re.compile(
    r"^(?P<topic>[a-z][a-z0-9-]*)_"
    r"(?P<date>\d{4}-\d{2}-\d{2})-"
    r"(?P<n_ids>n\d+(?:-n\d+)*)-"
    r"(?P<slug>.+)\.md$"
)


def derive_new_filename(filename: str) -> str | None:
    m = FILENAME_RE.match(filename)
    if not m:
        return None
    n_ids = m.group("n_ids").split("-")
    primary_n = n_ids[0].upper()
    if len(n_ids) > 1:
        secondary = "-".join(n_ids[1:])
        return f"{primary_n}-{secondary}-{m.group('slug')}.md"
    return f"{primary_n}-{m.group('slug')}.md"


def build_rename_map_from_text(text: str) -> dict[str, str]:
    """从文本中扫描所有 lessons/<filename>.md, 推导新文件名.

    返回 old_basename → new_basename (含 archived-early/ 前缀的, 加前缀).
    """
    pattern = re.compile(r"lessons/([a-z][a-z0-9_-]*\.md)")
    matches = pattern.findall(text)
    m: dict[str, str] = {}
    for old_basename in matches:
        if old_basename in m:
            continue
        new = derive_new_filename(old_basename)
        if new:
            m[old_basename] = new
        else:
            # 无 N 编号文件 → 检查是否已移到 archived-early/
            archived_path = LESSONS_DIR / "archived-early" / old_basename
            if archived_path.exists():
                m[old_basename] = f"archived-early/{old_basename}"
    return m


def replace_lesson_links(text: str, rename_map: dict[str, str]) -> tuple[str, int]:
    """替换 `lessons/<old>.md` → `lessons/<new>.md`. 返回 (新文本, 替换次数)."""
    count = 0
    for old, new in rename_map.items():
        pattern = f"lessons/{old}"
        if pattern in text:
            new_text = text.replace(pattern, f"lessons/{new}")
            count += text.count(pattern)
            text = new_text
    return text, count


def add_two_columns(text: str) -> tuple[str, int]:
    """§Active 表格加 2 列. 返回 (新文本, 修改行数)."""
    lines = text.split("\n")
    new_lines: list[str] = []
    in_active_table = False
    modified = 0
    for i, line in enumerate(lines):
        # 检测表头
        if line.startswith("| N## |") and "Lesson 链接" in line:
            # 加 2 列
            line = line.rstrip("|").rstrip() + " | trigger_count | last_triggered |"
            in_active_table = True
            new_lines.append(line)
            continue
        # 检测分隔符
        if in_active_table and line.startswith("|:---"):
            # 加 2 列对齐符
            line = line.rstrip("|").rstrip() + " |:---:|:---:|"
            new_lines.append(line)
            continue
        # 检测数据行 | N91 | ...
        if in_active_table and re.match(r"^\| N\d+", line):
            # 末尾加 | 0 | - |
            line = line.rstrip("|").rstrip() + " | 0 | - |"
            modified += 1
            new_lines.append(line)
            continue
        # 空行或非表格行 → 退出表格
        if in_active_table and line and not line.startswith("|"):
            in_active_table = False
        new_lines.append(line)
    return "\n".join(new_lines), modified


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("需要 --dry-run 或 --apply")

    text = FM_PATH.read_text(encoding="utf-8")
    rename_map = build_rename_map_from_text(text)
    print(f"rename_map entries: {len(rename_map)}")

    new_text, link_count = replace_lesson_links(text, rename_map)
    # 加列前检测是否已加 (幂等)
    if "trigger_count" in new_text:
        col_count = 0
        print("trigger_count 列已存在, 跳过加列")
    else:
        new_text, col_count = add_two_columns(new_text)

    print(f"links replaced: {link_count}")
    print(f"rows added 2 columns: {col_count}")

    if args.apply:
        FM_PATH.write_text(new_text, encoding="utf-8")
        print(f"✅ written: {FM_PATH}")
    else:
        # dry-run: 显示前 5 个替换
        print("[DRY-RUN] 不写入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
