#!/usr/bin/env python
"""Slim down active.md by migrating closed TD sections.

> **⚠️ 已休眠 (2026-08-09 迁移)**: 本脚本的使命对象 (active.md/fixed.md/wontfix.md)
> 已在 2026-08-09 归档迁移到 `docs/archive/active-tech-debt.md` 等文件, active
> 目录已清空。本脚本保留仅供历史参考, 不再主动调用; 路径常量已更新指向
> archive 以避免误操作。

Migrate `## TD-NNN:` sections from active.md based on the state marker in
the title line:

- title contains `✅ FIXED`  -> append to fixed.md
- title contains `❌`         -> append to wontfix.md
- otherwise (🔧/🚧/no marker) -> keep in active.md

Special cases:
- TD-XXX template (inside `<!-- Template:` block) stays in active.md head.
- TD-259 (🔧 待修, contains 32 [B] sub-items mostly ✅ FIXED) stays in active.md.

The script also:
- Inserts a slim-down date marker after the head intro.
- Rebuilds the priority list table to keep only rows whose TD is still active.

Performance target: < 1s (ideal) / < 3s (acceptable) per N171 baseline.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TD_DIR = REPO_ROOT / "docs" / "archive"
ACTIVE_MD = TD_DIR / "active-tech-debt.md"
FIXED_MD = TD_DIR / "fixed-tech-debt.md"
WONTFIX_MD = TD_DIR / "wontfix-tech-debt.md"

SLIM_DATE = "2026-07-19"

# Split on real TD sections only (digits, not the TD-XXX template).
SECTION_RE = re.compile(r"^## TD-\d+:", re.MULTILINE)
TD_ID_RE = re.compile(r"^## TD-(\d+):", re.MULTILINE)


def classify_section(section: str) -> str:
    """Classify a section by its title state marker.

    Returns one of: 'fixed', 'wontfix', 'keep'.
    """
    title = section.split("\n", 1)[0]
    if "✅ FIXED" in title:
        return "fixed"
    if "❌" in title:
        return "wontfix"
    return "keep"


def read_text(path: Path) -> str:
    # newline='' preserves original line endings (CRLF/LF mix).
    with path.open("r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(content)


def split_sections(content: str) -> tuple[str, list[str]]:
    """Split active.md into (head, [sections]).

    Head = everything before the first `## TD-NNN:` line (includes intro,
    priority list, and the TD-XXX template inside the HTML comment).
    Each section starts at its `## TD-NNN:` line and ends at the next
    section start or EOF.
    """
    matches = list(SECTION_RE.finditer(content))
    if not matches:
        return content, []
    head = content[: matches[0].start()]
    sections = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        sections.append(content[start:end])
    return head, sections


def _normalize_newlines(text: str) -> str:
    """Normalize all newline variants (CRLF/CR/LF) to plain LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def append_sections(target_path: Path, sections: list[str]) -> None:
    """Append sections to target file with `\\n\\n---\\n\\n` separators.

    Preserves existing content; only appends. Each new section is stripped
    of trailing whitespace and joined with the separator. Newline style of
    the target file (CRLF or LF) is detected and applied consistently to
    appended content (avoids producing `\r\r\n` double-CR sequences).
    """
    if not sections:
        return
    existing = read_text(target_path)
    # Detect dominant newline of existing file.
    nl = "\r\n" if "\r\n" in existing else "\n"
    # Normalize everything to \n first, then strip trailing newlines.
    existing_norm = _normalize_newlines(existing).rstrip("\n")
    cleaned = [_normalize_newlines(s).rstrip("\n") for s in sections]
    # Build new content with \n-only line endings.
    separator = "\n\n---\n\n"
    new_content = separator.join([existing_norm] + cleaned) + "\n"
    # Convert to target newline style in a single pass (no double-CR).
    if nl != "\n":
        new_content = new_content.replace("\n", nl)
    write_text(target_path, new_content)


def insert_slim_marker(head: str, stats: dict) -> str:
    """Insert slim-down date marker after the head intro (after L8-L9)."""
    marker = (
        f"> **瘦身日期**: {SLIM_DATE} (从 {stats['orig_size_kb']:.0f}KB/"
        f"{stats['orig_lines']} 行瘦身至 {stats['new_size_kb']:.0f}KB/"
        f"{stats['new_lines']} 行, 迁出 {stats['migrated_fixed']} 个 ✅ FIXED + "
        f"{stats['migrated_wontfix']} 个 ❌ wontfix 段落到 fixed.md / wontfix.md)"
    )
    # Insert after the "来源" line and the following blank line.
    # Match the line that starts with "> **来源**：" up to the next blank line.
    pattern = re.compile(
        r"(> \*\*来源\*\*[^\n]*\n)(\r?\n)+",
    )
    m = pattern.search(head)
    if not m:
        # Fallback: insert before "## TD 处理顺序".
        pattern2 = re.compile(r"(## TD 处理顺序)")
        m2 = pattern2.search(head)
        if not m2:
            return head  # give up, no insertion
        return head[: m2.start()] + marker + "\n\n" + head[m2.start():]
    insertion_point = m.end()
    # Detect newline style at insertion point.
    nl = "\r\n" if "\r\n" in head else "\n"
    return head[:insertion_point] + marker + nl + nl + head[insertion_point:]


def rebuild_priority_table(head: str, kept_td_ids: set[str]) -> str:
    """Remove rows from the priority list table whose TD is not in kept set.

    The table starts at `**当前待修 TD 优先级清单**` and ends at the next
    blank line after the last table row. Rows look like:
        | TD-NNN | priority | date | description |
    """
    table_start_pat = re.compile(r"\*\*当前待修 TD 优先级清单\*\*[^\n]*\n")
    m = table_start_pat.search(head)
    if not m:
        return head
    start = m.end()
    # Collect contiguous lines starting with `|` (the table rows + separator).
    lines = head.splitlines(keepends=True)
    # Find the line index corresponding to `start`.
    char_idx = 0
    line_idx = 0
    for i, ln in enumerate(lines):
        if char_idx >= start:
            line_idx = i
            break
        char_idx += len(ln)
    # Walk forward collecting table rows.
    table_end_idx = line_idx
    kept_rows = []
    header_seen = False
    separator_seen = False
    footer = "**完整待修 TD 清单见 tech-debt/README.md 总览表**"
    while table_end_idx < len(lines):
        ln = lines[table_end_idx]
        stripped = ln.lstrip()
        if not stripped.startswith("|"):
            break
        # Match a table row like "| TD-NNN | ... |"
        row_match = re.match(r"\|\s*(TD-\d+)\s*\|", stripped)
        if row_match:
            td_id = row_match.group(1)
            if td_id in kept_td_ids:
                kept_rows.append(ln)
        else:
            # Header row or separator row (| TD | 优先级 | ... | or |---|---|...)
            if not header_seen:
                header_seen = True
                kept_rows.append(ln)
            elif not separator_seen:
                separator_seen = True
                kept_rows.append(ln)
        table_end_idx += 1
    # Build replacement: header + separator + kept_rows + footer + blank.
    if not header_seen or not separator_seen:
        return head  # malformed table, skip
    # Detect head's dominant newline for footer consistency.
    head_nl = "\r\n" if "\r\n" in head else "\n"
    # Compose new table block.
    new_block_lines = kept_rows[:]
    new_block_lines.append(footer + head_nl)
    new_block_lines.append(head_nl)
    new_block = "".join(new_block_lines)
    # Replace original table rows (line_idx .. table_end_idx-1) with new block.
    new_lines = lines[:line_idx] + [new_block] + lines[table_end_idx:]
    return "".join(new_lines)


def count_lines(content: str) -> int:
    """Count lines in content (matching how `Get-Content` counts)."""
    if not content:
        return 0
    # Match PowerShell Get-Content behavior: count of \n.
    return content.count("\n") + (0 if content.endswith("\n") else 1)


def main() -> int:
    # Read active.md
    active = read_text(ACTIVE_MD)
    orig_size = len(active.encode("utf-8"))
    orig_lines = count_lines(active)

    head, sections = split_sections(active)
    if not sections:
        print("ERROR: no TD sections found in active.md", file=sys.stderr)
        return 1

    fixed_sections: list[str] = []
    wontfix_sections: list[str] = []
    keep_sections: list[str] = []
    kept_td_ids: set[str] = set()

    for s in sections:
        bucket = classify_section(s)
        if bucket == "fixed":
            fixed_sections.append(s)
        elif bucket == "wontfix":
            wontfix_sections.append(s)
        else:
            keep_sections.append(s)
            # Extract TD-NNN id for priority table filtering.
            m = TD_ID_RE.match(s)
            if m:
                kept_td_ids.add(f"TD-{m.group(1)}")

    # Append migrated sections to fixed.md and wontfix.md (preserve existing).
    append_sections(FIXED_MD, fixed_sections)
    append_sections(WONTFIX_MD, wontfix_sections)

    # Build new active.md with all head modifications:
    # 1. Use a placeholder slim marker first (stats not yet known).
    # 2. Rebuild priority table.
    # 3. Compute final stats from final content.
    # 4. Replace placeholder slim marker with actual stats.
    placeholder_stats = {
        "orig_size_kb": orig_size / 1024,
        "orig_lines": orig_lines,
        "new_size_kb": 0.0,  # placeholder, replaced below
        "new_lines": 0,      # placeholder, replaced below
        "migrated_fixed": len(fixed_sections),
        "migrated_wontfix": len(wontfix_sections),
        "kept": len(keep_sections),
    }
    # Insert slim marker with placeholder zeros.
    new_head = insert_slim_marker(head, placeholder_stats)
    # Rebuild priority table.
    new_head = rebuild_priority_table(new_head, kept_td_ids)
    # Build final content with placeholder.
    new_active_placeholder = new_head + "".join(keep_sections)
    # Compute actual final stats.
    final_lines = count_lines(new_active_placeholder)
    final_size_kb = len(new_active_placeholder.encode("utf-8")) / 1024
    # Replace placeholder "瘦身至 0KB/0 行" with actual values in the slim marker.
    # Only the "new" stats are placeholder zeros; orig stats are already filled in.
    placeholder_tail = f"瘦身至 0KB/0 行"
    actual_tail = f"瘦身至 {final_size_kb:.0f}KB/{final_lines} 行"
    new_active = new_active_placeholder.replace(placeholder_tail, actual_tail, 1)
    write_text(ACTIVE_MD, new_active)

    # Verify by re-reading the written file.
    final_content = read_text(ACTIVE_MD)
    stats = {
        "orig_size_kb": orig_size / 1024,
        "orig_lines": orig_lines,
        "new_size_kb": len(final_content.encode("utf-8")) / 1024,
        "new_lines": count_lines(final_content),
        "migrated_fixed": len(fixed_sections),
        "migrated_wontfix": len(wontfix_sections),
        "kept": len(keep_sections),
    }

    # Print stats.
    print("=" * 60)
    print("split_active_tech_debts.py — Stats")
    print("=" * 60)
    print(f"Original active.md : {stats['orig_size_kb']:7.1f} KB / {stats['orig_lines']:5d} lines")
    print(f"  Sections total   : {len(sections)}")
    print(f"  -> fixed.md      : {len(fixed_sections):3d} sections migrated")
    print(f"  -> wontfix.md    : {len(wontfix_sections):3d} sections migrated")
    print(f"  -> kept in active: {len(keep_sections):3d} sections")
    print(f"New active.md      : {stats['new_size_kb']:7.1f} KB / {stats['new_lines']:5d} lines")
    print(f"Kept TD IDs        : {sorted(kept_td_ids)}")
    # Verify file sizes.
    for p in (ACTIVE_MD, FIXED_MD, WONTFIX_MD):
        size = p.stat().st_size
        with p.open("r", encoding="utf-8", newline="") as f:
            ln = count_lines(f.read())
        print(f"  {p.name:14s}: {size/1024:7.1f} KB / {ln:5d} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
