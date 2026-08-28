"""migrate_lessons_p1.py — P1 一次性迁移脚本 (spec §6.2).

执行 P1-1 (改名) + P1-2 (无 N 编号归档) + P1-3 (frontmatter 加 topic 字段).

改名规则:
- `<topic>_<date>-n<N>-<slug>.md` → `N<N>-<slug>.md`
- `<topic>_<date>-n<N1>-n<N2>-<slug>.md` (家族合并) → `N<N1>-n<N2>-<slug>.md`
  (主编号大写 N, 次编号小写 n 保留在 slug 中, 便于 grep "N150" 仍能命中)
- 无 N 编号文件 → 移到 archived-early/ 保留原名

frontmatter topic 字段:
- 从原文件名前缀解析 topic, 写入 frontmatter
- 不修改其他 frontmatter 字段

Usage:
    python scripts/migrate_lessons_p1.py --dry-run  # 预览
    python scripts/migrate_lessons_p1.py --apply    # 实际执行
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LESSONS_DIR = REPO_ROOT / ".ai-memory" / "lessons"
ARCHIVED_EARLY_DIR = LESSONS_DIR / "archived-early"

# 文件名正则: <topic>_<date>-n<N>-<slug>.md 或 <topic>_<date>-n<N1>-n<N2>-<slug>.md
# topic 含字母数字和连字符; date YYYY-MM-DD; N 编号小写 n + 数字
FILENAME_RE = re.compile(
    r"^(?P<topic>[a-z][a-z0-9-]*)_"
    r"(?P<date>\d{4}-\d{2}-\d{2})-"
    r"(?P<n_ids>n\d+(?:-n\d+)*)-"
    r"(?P<slug>.+)\.md$"
)


def parse_filename(filename: str) -> dict | None:
    """解析文件名, 返回 dict 或 None (无 N 编号)."""
    m = FILENAME_RE.match(filename)
    if not m:
        return None
    n_ids = m.group("n_ids").split("-")  # ['n150', 'n153'] 或 ['n188']
    primary_n = n_ids[0].upper()  # 'N150'
    return {
        "topic": m.group("topic"),
        "date": m.group("date"),
        "n_ids": n_ids,
        "primary_n": primary_n,
        "slug": m.group("slug"),
    }


def derive_new_filename(parsed: dict) -> str:
    """根据解析结果生成新文件名.

    家族合并: n150-n153 → N150-n153-<slug>.md (主编号大写, 次编号小写保留)
    单编号: n188 → N188-<slug>.md
    """
    if len(parsed["n_ids"]) > 1:
        # 家族合并: 主编号大写, 次编号保留小写 n 前缀
        secondary = "-".join(parsed["n_ids"][1:])  # 'n153'
        return f"{parsed['primary_n']}-{secondary}-{parsed['slug']}.md"
    return f"{parsed['primary_n']}-{parsed['slug']}.md"


def add_topic_to_frontmatter(path: Path, topic: str) -> bool:
    """在 frontmatter 中加 topic 字段. 返回是否修改.

    若已有 topic 字段则跳过; 否则在 n_id 字段后插入 (若无 n_id 则在 created_by 后).
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        print(f"  ⚠️  {path.name}: no frontmatter, skip topic injection")
        return False
    # 找 frontmatter 结束
    end_match = re.search(r"\n---\n", text)
    if not end_match:
        print(f"  ⚠️  {path.name}: frontmatter end not found, skip")
        return False
    fm_text = text[: end_match.start() + 1]  # 含开头 ---\n, 不含结束 \n---\n
    # 检查是否已有 topic 字段
    if re.search(r"^topic:\s*", fm_text, re.MULTILINE):
        return False
    # 找插入位置: n_id 后, 若无则 created_by 后, 若无则末尾
    insert_after = None
    for field in ["n_id", "created_by", "level"]:
        m = re.search(rf"^{field}:.*\n", fm_text, re.MULTILINE)
        if m:
            insert_after = m
            break
    new_fm = fm_text
    insertion = f"topic: {topic}\n"
    if insert_after:
        idx = insert_after.end()
        new_fm = fm_text[:idx] + insertion + fm_text[idx:]
    else:
        # 在结束 --- 前插
        new_fm = fm_text.rstrip("\n") + "\n" + insertion
    new_text = new_fm + text[end_match.start() + 1:]
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def _git_mv_impl(src: Path, dst: Path, dry_run: bool) -> bool:
    """执行 git mv, 处理未跟踪文件回退到普通 mv."""
    rel_src = src.relative_to(REPO_ROOT).as_posix()
    rel_dst = dst.relative_to(REPO_ROOT).as_posix()
    # 检查 src 是否被 git 跟踪
    code, _ = _run_git(["ls-files", "--error-unmatch", rel_src], check=False)
    if code == 0:
        cmd = ["git", "mv", rel_src, rel_dst]
    else:
        # 未跟踪文件, 用普通 mv
        cmd = ["cmd", "/c", "move", str(src), str(dst)]
    if dry_run:
        print(f"  [DRY-RUN] {' '.join(cmd)}")
        return False
    result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"  ❌ FAIL: {' '.join(cmd)}")
        print(f"     stderr: {result.stderr.strip()}")
        return False
    return True


def git_mv(src: Path, dst: Path, dry_run: bool) -> bool:
    """执行 git mv (向后兼容包装)."""
    return _git_mv_impl(src, dst, dry_run)


def _run_git(args: list[str], check: bool = True) -> tuple[int, str]:
    result = subprocess.run(
        ["git"] + args, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {args} failed: {result.stderr}")
    return result.returncode, result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="P1 lessons 迁移")
    parser.add_argument("--dry-run", action="store_true", help="预览不执行")
    parser.add_argument("--apply", action="store_true", help="实际执行")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("需要 --dry-run 或 --apply")
    if args.dry_run and args.apply:
        parser.error("--dry-run 和 --apply 互斥")

    ARCHIVED_EARLY_DIR.mkdir(parents=True, exist_ok=True)

    renamed = 0
    archived = 0
    topic_added = 0
    skipped = 0
    errors = 0

    for md_file in sorted(LESSONS_DIR.glob("*.md")):
        if md_file.name == "README.md":
            continue
        parsed = parse_filename(md_file.name)
        if parsed is None:
            # 无 N 编号 → 移到 archived-early/
            dst = ARCHIVED_EARLY_DIR / md_file.name
            print(f"📦 ARCHIVE: {md_file.name} → archived-early/")
            if git_mv(md_file, dst, args.dry_run):
                archived += 1
            continue
        new_name = derive_new_filename(parsed)
        if new_name == md_file.name:
            skipped += 1
            continue
        dst = LESSONS_DIR / new_name
        if dst.exists():
            print(f"  ⚠️  SKIP (target exists): {md_file.name} → {new_name}")
            errors += 1
            continue
        print(f"✏️  RENAME: {md_file.name} → {new_name}")
        if git_mv(md_file, dst, args.dry_run):
            renamed += 1
            # 加 topic 字段 (操作新文件)
            if not args.dry_run:
                if add_topic_to_frontmatter(dst, parsed["topic"]):
                    topic_added += 1

    print()
    print("=" * 60)
    print(f"renamed:       {renamed}")
    print(f"archived:      {archived}")
    print(f"topic_added:   {topic_added}")
    print(f"skipped:       {skipped}")
    print(f"errors:        {errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
