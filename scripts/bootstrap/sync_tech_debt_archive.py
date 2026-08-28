"""sync_tech_debt_archive.py — fixed.md 归档机制 (spec-2026-07-26-meta-governance-fix T2).

> **⚠️ 已休眠 (2026-08-09 迁移)**: 本脚本的使命对象 `docs/tech-debt/fixed.md`
> (579KB/268 段落) 已在 2026-08-09 归档迁移到 `docs/archive/fixed-tech-debt*.md`,
> 超大文件问题由迁移本身解决。本脚本保留仅供历史参考, 不再主动调用;
> 路径常量已更新指向 archive 以避免误操作旧结构。

Background (TD-309 REOPENED 2026-07-26):
    fixed.md 5695 行 / 579KB / 268 TD 段落, 人类 Read 整文件撞 128KB 限制.
    TD-309 wontfix 决策 (2026-07-21, 4596 行) 5 天后已过时, 重新评估为:
    "AI 用 Grep 适应" 仍成立, 但人类 Read 受限是新问题.

Modes:
    --archive --keep N   保留最近 N 个段落 (按文件顺序, 即最新), 历史迁 fixed-archive-YYYY.md
    --yearly             把上一年度的段落迁 fixed-archive-YYYY.md (每年 1 月 1 日跑)
    --check              只检查, 不修改 (返回 fixed.md 段落数 + 行数 + 是否需归档)
    --stats              打印统计信息

Archive file naming:
    docs/tech-debt/fixed-archive-YYYY.md (按段落登记时间年份)

段落识别:
    ^## TD-NNN: 开始, 到下一个 ^## TD-NNN: 或文件结束.

Integration:
    gaf_init.sh --full (archived 检查, 非阻塞警告) — 2026-08-09 后不再引用

Tests:
    scripts/tests/test_sync_tech_debt_archive.py
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

# Bootstrap: make scripts/ importable when this file lives in a subdir.
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import _encoding_safe  # noqa: E402,F401  (must be first; reconfigures stdout to UTF-8)

REPO_ROOT = _SCRIPTS_DIR.parent
FIXED_MD = REPO_ROOT / "docs" / "archive" / "fixed-tech-debt.md"
ARCHIVE_DIR = REPO_ROOT / "docs" / "archive"

# Paragraph pattern: ## TD-NNN: ... (标题行)
TD_HEADING_RE = re.compile(r"^## (TD-\d+):", re.MULTILINE)

# 修复时间提取 (用于年度归档) — 匹配 "修复时间: 2026" / "修复时间**: 2026" / "修复时间：2026"
FIX_TIME_RE = re.compile(r"修复时间\**\s*[：:]\s*(\d{4})")


def parse_fixed_md(content: str) -> tuple[str, list[tuple[int, int, str, str]]]:
    """Parse fixed.md into (header, paragraphs).

    header: frontmatter + 标题 + 说明, 到第一个 ## TD-NNN 之前.
    paragraphs: list of (start_offset, end_offset, td_id, raw_text)
        start_offset/end_offset are character offsets in content.
    """
    matches = list(TD_HEADING_RE.finditer(content))
    if not matches:
        return content, []

    header = content[: matches[0].start()]
    paragraphs = []
    for i, m in enumerate(matches):
        td_id = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        raw_text = content[start:end]
        paragraphs.append((start, end, td_id, raw_text))
    return header, paragraphs


def extract_year(paragraph_text: str) -> int | None:
    """Extract 修复时间年份 from a TD paragraph."""
    m = FIX_TIME_RE.search(paragraph_text)
    if m:
        return int(m.group(1))
    # Fallback: 登记时间
    m2 = re.search(r"登记时间\**\s*[：:]\s*(\d{4})", paragraph_text)
    if m2:
        return int(m2.group(1))
    return None


def build_index_table(paragraphs: list[tuple[int, int, str, str]]) -> str:
    """Build a compact index table: TD-NNN → 一句话摘要."""
    lines = [
        "<!-- fixed.md 索引表 (sync_tech_debt_archive.py 自动生成, 勿手改) -->",
        "",
        "| TD | 摘要 |",
        "|----|------|",
    ]
    for _, _, td_id, raw in paragraphs:
        # 提取标题行第一行 (## TD-NNN: 后的内容)
        first_line = raw.split("\n", 1)[0]
        # 去掉 ## TD-NNN: 前缀
        summary = re.sub(r"^## TD-\d+:\s*", "", first_line)
        # 截断到 80 字符
        if len(summary) > 80:
            summary = summary[:77] + "..."
        lines.append(f"| [{td_id}](#L) | {summary} |")
    lines.append("")
    return "\n".join(lines)


def archive_keep_n(fixed_md: Path, keep_n: int, dry_run: bool = False) -> dict:
    """Mode --archive --keep N: 保留最近 N 个段落, 历史迁 fixed-archive-YYYY.md.

    "最近" 定义: 按文件顺序的最后 N 个 (fixed.md 头部是最新 TD).
    """
    content = fixed_md.read_text(encoding="utf-8")
    header, paragraphs = parse_fixed_md(content)

    if len(paragraphs) <= keep_n:
        return {
            "action": "noop",
            "reason": f"paragraphs ({len(paragraphs)}) <= keep_n ({keep_n})",
            "total_paragraphs": len(paragraphs),
        }

    # 保留前 N 个 (fixed.md 头部 = 最新 TD), 归档后面 (历史)
    to_keep = paragraphs[:keep_n]
    to_archive = paragraphs[keep_n:]

    # 按 year 分组归档段落
    archive_by_year: dict[int, list[tuple[str, str]]] = {}
    for _, _, td_id, raw in to_archive:
        year = extract_year(raw) or datetime.now().year
        archive_by_year.setdefault(year, []).append((td_id, raw))

    stats = {
        "action": "archive",
        "total_paragraphs": len(paragraphs),
        "archived": len(to_archive),
        "kept": len(to_keep),
        "archive_files": [],
    }

    if dry_run:
        for year, items in archive_by_year.items():
            stats["archive_files"].append({
                "file": str(ARCHIVE_DIR / f"fixed-archive-{year}.md"),
                "paragraphs": len(items),
                "td_ids": [td for td, _ in items[:5]] + (["..."] if len(items) > 5 else []),
            })
        return stats

    # 写归档文件 (append, 不覆盖已有)
    for year, items in archive_by_year.items():
        archive_file = ARCHIVE_DIR / f"fixed-archive-{year}.md"
        existing = ""
        if archive_file.exists():
            existing = archive_file.read_text(encoding="utf-8")

        new_content = ""
        if not existing:
            # 新建归档文件, 加 frontmatter
            new_content = (
                f"---\n"
                f"summary: 已修复技术债务历史归档 — {year} 年 ✅ FIXED 条目\n"
                f"applies_to: [project]\n"
                f"last_updated: {datetime.now().strftime('%Y-%m-%d')}\n"
f"archived_from: docs/archive/fixed-tech-debt.md\n"
                f"---\n\n"
                f"# Fixed Tech Debts Archive — {year}\n\n"
                f"> 本文件是 {year} 年的 ✅ FIXED 历史归档, 由 sync_tech_debt_archive.py 从 fixed.md 迁出.\n"
                f"> 当前 fixed.md 只保留最近 {keep_n} 个段落, 历史段落按年度归档到此.\n"
                f"> 来源: TD-309 REOPENED (spec-2026-07-26-meta-governance-fix T2).\n\n"
                f"---\n\n"
            )

        # 追加段落 (按 TD 编号倒序, 与 fixed.md 一致)
        for td_id, raw in items:
            new_content += raw.rstrip() + "\n\n"

        # 写入 (追加到已有文件)
        archive_file.write_text(existing + new_content, encoding="utf-8")
        stats["archive_files"].append({
            "file": str(archive_file),
            "paragraphs": len(items),
        })

    # 重建 fixed.md: header + 索引表 + 保留段落
    index_table = build_index_table(to_keep)
    new_fixed = header.rstrip() + "\n\n" + index_table + "\n---\n\n"
    for _, _, td_id, raw in to_keep:
        new_fixed += raw.rstrip() + "\n\n"

    fixed_md.write_text(new_fixed, encoding="utf-8")
    return stats


def archive_yearly(fixed_md: Path, target_year: int, dry_run: bool = False) -> dict:
    """Mode --yearly: 把 target_year 年的段落迁到 fixed-archive-target_year.md.

    通常在每年 1 月 1 日跑, target_year = 上一年.
    """
    content = fixed_md.read_text(encoding="utf-8")
    header, paragraphs = parse_fixed_md(content)

    to_archive = []
    to_keep = []
    for _, _, td_id, raw in paragraphs:
        year = extract_year(raw)
        if year == target_year:
            to_archive.append((td_id, raw))
        else:
            # 重新构造 paragraph tuple for keep
            pass

    # 简化: 重新 parse, 按年份过滤
    to_keep_paragraphs = []
    for start, end, td_id, raw in paragraphs:
        year = extract_year(raw)
        if year == target_year:
            to_archive.append((td_id, raw))
        else:
            to_keep_paragraphs.append((start, end, td_id, raw))

    stats = {
        "action": "archive_yearly",
        "target_year": target_year,
        "total_paragraphs": len(paragraphs),
        "archived": len(to_archive),
        "kept": len(to_keep_paragraphs),
    }

    if dry_run:
        return stats

    if not to_archive:
        return {**stats, "action": "noop", "reason": f"no paragraphs in {target_year}"}

    # 写归档文件
    archive_file = ARCHIVE_DIR / f"fixed-archive-{target_year}.md"
    new_content = (
        f"---\n"
        f"summary: 已修复技术债务历史归档 — {target_year} 年 ✅ FIXED 条目\n"
        f"applies_to: [project]\n"
        f"last_updated: {datetime.now().strftime('%Y-%m-%d')}\n"
        f"archived_from: docs/archive/fixed-tech-debt.md\n"
        f"---\n\n"
        f"# Fixed Tech Debts Archive — {target_year}\n\n"
        f"> 本文件是 {target_year} 年的 ✅ FIXED 历史归档.\n"
        f"> 来源: sync_tech_debt_archive.py --yearly.\n\n"
        f"---\n\n"
    )
    for td_id, raw in to_archive:
        new_content += raw.rstrip() + "\n\n"
    archive_file.write_text(new_content, encoding="utf-8")

    # 重建 fixed.md
    index_table = build_index_table(to_keep_paragraphs)
    new_fixed = header.rstrip() + "\n\n" + index_table + "\n---\n\n"
    for _, _, td_id, raw in to_keep_paragraphs:
        new_fixed += raw.rstrip() + "\n\n"
    fixed_md.write_text(new_fixed, encoding="utf-8")
    return stats


def check(fixed_md: Path) -> dict:
    """Mode --check: 只检查, 不修改."""
    content = fixed_md.read_text(encoding="utf-8")
    header, paragraphs = parse_fixed_md(content)
    line_count = content.count("\n") + 1
    size_kb = len(content.encode("utf-8")) / 1024

    # 按年份统计
    by_year: dict[int, int] = {}
    for _, _, _, raw in paragraphs:
        year = extract_year(raw) or 0
        by_year[year] = by_year.get(year, 0) + 1

    return {
        "file": str(fixed_md),
        "lines": line_count,
        "size_kb": round(size_kb, 1),
        "paragraphs": len(paragraphs),
        "by_year": by_year,
        "needs_archive": len(paragraphs) > 100 or size_kb > 250,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="fixed.md 归档机制 (TD-309 REOPENED)")
    parser.add_argument("--archive", action="store_true", help="归档模式 (需配合 --keep N)")
    parser.add_argument("--yearly", action="store_true", help="年度归档模式 (迁上一年)")
    parser.add_argument("--keep", type=int, default=100, help="保留最近 N 个段落 (default: 100)")
    parser.add_argument("--year", type=int, help="指定年度归档的年份 (default: 上一年)")
    parser.add_argument("--check", action="store_true", help="只检查, 不修改")
    parser.add_argument("--stats", action="store_true", help="打印统计信息")
    parser.add_argument("--dry-run", action="store_true", help="预演, 不写文件")
    args = parser.parse_args()

    if args.check or args.stats:
        result = check(FIXED_MD)
        print(f"file: {result['file']}")
        print(f"lines: {result['lines']}")
        print(f"size: {result['size_kb']} KB")
        print(f"paragraphs: {result['paragraphs']}")
        print(f"by_year: {result['by_year']}")
        print(f"needs_archive: {result['needs_archive']}")
        return 0

    if args.archive:
        result = archive_keep_n(FIXED_MD, args.keep, dry_run=args.dry_run)
        print(f"action: {result['action']}")
        print(f"total_paragraphs: {result['total_paragraphs']}")
        print(f"archived: {result['archived']}")
        print(f"kept: {result['kept']}")
        for f in result.get("archive_files", []):
            print(f"  archive_file: {f}")
        return 0

    if args.yearly:
        target_year = args.year or (datetime.now().year - 1)
        result = archive_yearly(FIXED_MD, target_year, dry_run=args.dry_run)
        print(f"action: {result['action']}")
        print(f"target_year: {result['target_year']}")
        print(f"total_paragraphs: {result['total_paragraphs']}")
        print(f"archived: {result['archived']}")
        print(f"kept: {result['kept']}")
        return 0

    # 默认: --check
    result = check(FIXED_MD)
    print(f"file: {result['file']}")
    print(f"lines: {result['lines']}")
    print(f"size: {result['size_kb']} KB")
    print(f"paragraphs: {result['paragraphs']}")
    print(f"by_year: {result['by_year']}")
    print(f"needs_archive: {result['needs_archive']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
