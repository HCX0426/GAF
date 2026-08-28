"""skill_sync.changelog — --changelog command + report helpers (s39 split, TD-365 6/9)."""
from __future__ import annotations

import argparse
import datetime
import re
from pathlib import Path
from typing import List, Optional, Tuple

from .constants import (
    CHANGELOG_PATH_DEFAULT,
    REPO_ROOT_DEFAULT,
)
from .io_utils import (
    _block_hash,
    _extract_decision_tree_block,
    _read_text,
    _write_text,
)

# =============================================================================
# Reporting
# =============================================================================

def _format_report(
    issues: List[Tuple[Path, str, str, str, str]],
) -> str:
    """O1-friendly report. Each issue: (path, kind, status, expected, actual)."""
    lines: List[str] = ["❌ 4 skills + 1 rule 副本不一致："]
    for i, (path, kind, status, expected, actual) in enumerate(issues, 1):
        lines.append(f"  [{i}] {path}")
        if status == "missing":
            lines.append(f"      status: 缺失 (运行 sync_skills.py 自动生成)")
        elif status == "broken":
            lines.append(f"      status: 文件无法读取 (权限/编码)")
            lines.append(f"      修复: python scripts/bootstrap/sync_skills.py")
        elif status == "marker-missing":
            lines.append(f"      status: 缺关键标记 (文件可能是旧版本)")
            lines.append(f"      修复: python scripts/bootstrap/sync_skills.py")
        else:  # drift
            lines.append(f"      status: 哈希不一致")
            lines.append(f"      expected: {expected}")
            lines.append(f"      actual:   {actual}")
            lines.append(f"      修复: python scripts/bootstrap/sync_skills.py")
    lines.append("")
    lines.append("一键修复命令: python scripts/bootstrap/sync_skills.py")
    return "\n".join(lines)


# =============================================================================
# Main
# =============================================================================

def _extract_decision_tree_block_hash(skill_path: Path) -> str:
    """Extract decision tree block from a SKILL.md and return its SHA-256 (16-char prefix).

    🆕 M1.H helper. Returns '' if the file is missing or the block is not found.
    """
    text = _read_text(skill_path)
    block = _extract_decision_tree_block(text)
    if not block:
        return ""
    return _block_hash(block)


def _read_changelog_last_hash(changelog_path: Path) -> str:
    """Read the last ``new_hash`` recorded in the changelog table.

    🆕 M1.H helper. Scans the markdown table after the heading
    ``## 1. 决策树 hash 变更记录`` and returns the right-most hash in
    the most recent data row. Returns ``""`` if the file is missing
    or the table is empty.
    """
    if not changelog_path.exists():
        return ""
    content = _read_text(changelog_path)
    if not content:
        return ""
    # Find rows like: | 1 | 2026-06-16 | (initial) | a1b2c3d4 | note | AI |
    pattern = re.compile(
        r"^\|\s*\d+\s*\|\s*\d{4}-\d{2}-\d{2}\s*\|[^|]*\|\s*([0-9a-f]{16}|[^|]*)\s*\|",
        re.MULTILINE,
    )
    matches = pattern.findall(content)
    if not matches:
        return ""
    last = matches[-1].strip()
    return last if last and last != "(init)" else ""


def _build_changelog_entry(
    entry_no: int, today: str, old_hash: str, new_hash: str, note: str, author: str = "AI"
) -> str:
    """Build a single table-row entry for the changelog."""
    old = old_hash if old_hash else "(initial)"
    new = new_hash if new_hash else "(init)"
    safe_note = (note or "(no note)").replace("|", "\\|")
    return (
        f"| {entry_no} | {today} | {old} | {new} | "
        f"{safe_note} | {author} |\n"
    )


def append_changelog_entry(
    changelog_path: Path,
    orchestrator_skill: Path,
    note: str = "",
    today: Optional[str] = None,
) -> Tuple[bool, str, str]:
    """Append a decision-tree hash change to the changelog if it changed.

    🆕 M1.H main entry point. Returns (appended, old_hash, new_hash).
    Does nothing if the current block hash matches the last recorded hash.
    Creates the file with a header when missing.
    """
    current_hash = _extract_decision_tree_block_hash(orchestrator_skill)
    if not current_hash:
        return (False, "", "")

    changelog_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine next entry number by counting existing rows.
    existing_text = _read_text(changelog_path) if changelog_path.exists() else ""
    if not existing_text:
        # Initialise the changelog file with header + first entry.
        try:
            source_rel = changelog_path.relative_to(REPO_ROOT_DEFAULT).as_posix()
        except ValueError:
            # changelog_path is outside REPO_ROOT_DEFAULT (e.g. tests in tmpdir);
            # fall back to absolute path so the header still points to a real file.
            source_rel = changelog_path.as_posix()
        header = (
            "---\n"
            "maintainer: auto\n"
            f"source: {source_rel}\n"
            "load_when:\n"
            "- 决策树变更 review\n"
            "- 季度 review\n"
            "- hash 漂移排查\n"
            "- 旧决策树引用\n"
            "priority: medium\n"
            "symptom:\n"
            "- decision-tree-changelog\n"
            "- decision-tree-hash-drift\n"
            "- 决策树历史\n"
            "solution: 每次 sync_skills.py --changelog 自动追加一行 (date + old_hash + new_hash + note)\n"
            "related_files:\n"
            "- ../SKILL.md\n"
            "- ../../../scripts/bootstrap/sync_skills.py\n"
            "created_by: AI\n"
            f"last_updated: {today or datetime.date.today().isoformat()}\n"
            "---\n"
            "# Decision Tree Changelog (M1.H 闭环)\n\n"
            "> **自动追踪**: `gaf-orchestrator/SKILL.md` 中 "
            "`## Decision Tree` ↔ `## End Decision Tree` 块的 SHA-256 (16-char prefix)\n"
            "> **更新命令**: `python scripts/bootstrap/sync_skills.py --changelog`\n"
            "> **触发逻辑**: 当 block hash 与上次记录不一致时, 自动追加一行\n\n"
            "## 1. 决策树 hash 变更记录\n\n"
            "| # | date | old_hash | new_hash | note | author |\n"
            "|:-:|:----:|:--------:|:--------:|------|:------:|\n"
        )
        _write_text(changelog_path, header)
        existing_text = header
        next_no = 1
    else:
        # Count existing data rows (lines starting with "| <digit> |").
        row_pattern = re.compile(r"^\|\s*\d+\s*\|\s*\d{4}-\d{2}-\d{2}\s*\|", re.MULTILINE)
        next_no = len(row_pattern.findall(existing_text)) + 1

    last_hash = _read_changelog_last_hash(changelog_path)
    if last_hash == current_hash:
        return (False, last_hash, current_hash)

    today_str = today or datetime.date.today().isoformat()
    entry = _build_changelog_entry(
        entry_no=next_no, today=today_str,
        old_hash=last_hash, new_hash=current_hash, note=note,
    )

    with changelog_path.open("a", encoding="utf-8") as fh:
        fh.write(entry)
    return (True, last_hash, current_hash)


def cmd_changelog(args: argparse.Namespace) -> int:
    """🆕 M1.H: handle ``--changelog`` mode.

    Computes the current decision-tree block hash from the
    gaf-orchestrator SKILL.md and appends a row to the changelog if
    the hash has changed. Useful for both manual quarterly reviews
    and CI pre-commit hooks.
    """
    root = Path(args.root).resolve()
    orchestrator_skill = root / ".skills" / "skills" / "gaf-orchestrator" / "SKILL.md"
    if not orchestrator_skill.exists():
        print(f"❌ gaf-orchestrator/SKILL.md 不存在: {orchestrator_skill}")
        return 1

    changelog_path = (
        Path(args.changelog_path).resolve()
        if args.changelog_path
        else CHANGELOG_PATH_DEFAULT
    )

    appended, old_hash, new_hash = append_changelog_entry(
        changelog_path, orchestrator_skill, note=args.note or "",
    )

    if not new_hash:
        print(f"❌ 无法从 {orchestrator_skill.name} 提取决策树 block")
        return 1

    if appended:
        print(
            f"✅ Changelog 已更新 ({changelog_path.relative_to(root)}):\n"
            f"   old_hash: {old_hash or '(initial)'} → new_hash: {new_hash}"
        )
    else:
        print(
            f"✅ Changelog 无需更新 (当前 hash {new_hash} 与上次记录一致)"
        )
    return 0

