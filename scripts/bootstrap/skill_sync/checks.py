"""skill_sync.checks — consistency check functions (s39 split, TD-365 6/9)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from .constants import (
    EXPECTED_L2_FILES,
    N_INDEX_ROW_PATTERN,
    N_INDEX_SCAN_PATHS,
)
from .io_utils import _read_text


def check_l2_consistency(root: Path) -> List[str]:
    """P3 治本机制: 检测 L2 清单在 2 处引用是否与 EXPECTED_L2_FILES 一致.

    Returns list of error messages for inconsistencies.
    2 处 (v9.3 瘦身): gaf_init.sh L2_FILES / gaf-orchestrator SKILL.md L2 hard-load.
    (原 loading-strategy.md 已合并入 ai-operating-handbook.md, 不再单独检测)
    """
    errors: List[str] = []
    # 1. ai-operating-handbook.md — 必须存在 (L2 权威源)
    handbook_path = root / ".ai-memory" / "meta" / "ai-operating-handbook.md"
    if not handbook_path.exists():
        errors.append("ai-operating-handbook.md 不存在 (L2 清单权威源, v9.3 合并自 loading-strategy + ai-behavior-redlines)")

    # 2. gaf_init.sh — L2_FILES 数组应包含 1 文件 (按 basename 匹配)
    gaf_init = root / "scripts" / "gaf_init.sh"
    if gaf_init.exists():
        gi_text = _read_text(gaf_init)
        # Extract L2_FILES=( ... ) block
        m = re.search(r"L2_FILES=\(\s*\n([^)]+)\n\s*\)", gi_text)
        if m:
            block = m.group(1)
            for f in EXPECTED_L2_FILES:
                basename = f.split("/")[-1]
                if basename not in block:
                    errors.append(
                        f"gaf_init.sh L2_FILES 数组缺: {basename} (期望与 EXPECTED_L2_FILES 一致)"
                    )
        else:
            errors.append("gaf_init.sh 未找到 L2_FILES=( ... ) 数组定义")

    # 3. gaf-orchestrator SKILL.md — L2 hard-load 段应包含 ai-operating-handbook.md
    orch = root / ".skills" / "skills" / "gaf-orchestrator" / "SKILL.md"
    if orch.exists():
        orch_text = _read_text(orch)
        # Restrict to L2 hard-load hooks section (between "L2 hard-load" and "L3 按需")
        l2_section = ""
        idx = orch_text.find("L2 hard-load")
        if idx >= 0:
            l3_idx = orch_text.find("L3 按需", idx)
            l2_section = orch_text[idx : l3_idx if l3_idx > 0 else len(orch_text)]
        if not l2_section:
            errors.append("gaf-orchestrator/SKILL.md 未找到 'L2 hard-load' 段")
        else:
            for f in EXPECTED_L2_FILES:
                basename = f.split("/")[-1]
                if basename not in l2_section:
                    errors.append(
                        f"gaf-orchestrator/SKILL.md L2 hard-load 段缺: {basename} (期望与 EXPECTED_L2_FILES 一致)"
                    )
    else:
        errors.append("gaf-orchestrator/SKILL.md 不存在")

    return errors


def check_n_index_duplication(root: Path) -> List[Tuple[str, str]]:
    """P3 治本机制: 检测 N## 索引行是否在非权威文件出现.

    Returns list of (file_path, n_id) tuples for violations.
    """
    violations: List[Tuple[str, str]] = []
    # Scan fixed paths
    for rel in N_INDEX_SCAN_PATHS:
        path = root / rel
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in N_INDEX_ROW_PATTERN.finditer(text):
            n_id = match.group(1)
            violations.append((rel, n_id))
    # Scan yn-matrices/ sub-files (history recurrence tables allowed, but
    # N## index rows with lessons/ or 闭环 marker are not)
    yn_dir = root / ".ai-memory" / "meta" / "yn-matrices"
    if yn_dir.exists():
        for sub in yn_dir.glob("_*.md"):
            rel = str(sub.relative_to(root)).replace("\\", "/")
            try:
                text = sub.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for match in N_INDEX_ROW_PATTERN.finditer(text):
                n_id = match.group(1)
                violations.append((rel, n_id))
    return violations


def check_lessons_count_consistency(root: Path) -> List[str]:
    """spec-14 Phase 4: verify lessons/README.md frontmatter lessons_count matches actual file count.

    Returns list of error messages for inconsistencies.
    """
    errors: List[str] = []
    readme = root / ".ai-memory" / "lessons" / "README.md"
    if not readme.exists():
        return errors  # Other checks handle missing README
    lessons_dir = root / ".ai-memory" / "lessons"
    actual_count = sum(1 for f in lessons_dir.glob("*.md") if f.name != "README.md")
    text = readme.read_text(encoding="utf-8")
    fm_match = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not fm_match:
        errors.append("lessons/README.md frontmatter missing (cannot verify lessons_count)")
        return errors
    fm = fm_match.group(1)
    count_match = re.search(r"^lessons_count:\s*(\d+)", fm, re.MULTILINE)
    if not count_match:
        errors.append("lessons/README.md frontmatter missing 'lessons_count' field")
        return errors
    declared = int(count_match.group(1))
    if declared != actual_count:
        errors.append(
            f"lessons/README.md lessons_count={declared} but actual lessons/*.md count={actual_count} "
            f"(excluding README.md). Run: python scripts/bootstrap/sync_ai_memory.py to auto-fix."
        )
    return errors


def check_n_indexed_in_readme(root: Path) -> List[str]:
    """spec-14 Phase 4: verify all Active N## in failure-modes.md are referenced in lessons/README.md topic table.

    Returns list of error messages for N## that are in failure-modes.md Active section
    but missing from lessons/README.md (prevents N## index drift like R6-6).
    """
    errors: List[str] = []
    fm_path = root / ".ai-memory" / "meta" / "failure-modes.md"
    readme_path = root / ".ai-memory" / "lessons" / "README.md"
    if not fm_path.exists() or not readme_path.exists():
        return errors
    fm_text = fm_path.read_text(encoding="utf-8")
    # Extract Active section (between "## Active N##" and next "## " header)
    active_match = re.search(r"## Active N##(.+?)(?=\n## )", fm_text, re.DOTALL)
    if not active_match:
        errors.append("failure-modes.md: cannot locate '## Active N##' section")
        return errors
    active_section = active_match.group(1)
    # Find all N## in Active section index rows (| NXXX | format)
    active_n_ids = set(re.findall(r"^\|\s*(N\d+)\s*\|", active_section, re.MULTILINE))
    if not active_n_ids:
        errors.append("failure-modes.md Active section: no N## index rows found")
        return errors
    # Read README.md and extract all N## mentions in topic table + file list
    readme_text = readme_path.read_text(encoding="utf-8")
    readme_n_ids = set(re.findall(r"\b(N\d+)\b", readme_text))
    # Find active N## missing from README
    missing = active_n_ids - readme_n_ids
    for n_id in sorted(missing, key=lambda x: int(x[1:])):
        errors.append(
            f"failure-modes.md Active N## '{n_id}' missing from lessons/README.md "
            f"(topic table or file list). Add N## to architecture/agent-impl/etc topic row."
        )
    return errors


def check_loading_strategy_references(root: Path) -> List[str]:
    """spec-14 Phase 4: detect stale 'loading-strategy' references in current content (not history records).

    Returns list of error messages for files referencing loading-strategy as current content.
    Exceptions (history records, allowed):
      - .ai-memory/meta/spec-evolution.md (v8.0 history)
      - .ai-memory/meta/archived-lessons.md (archived)
      - .ai-memory/README.md (history annotation with "已删除" marker)
      - docs/specs/legacy-trae/*.md (spec history records, describe past fixes; spec-2026-07-26-trae-specs-plans-merge 迁移自旧 trae-specs 目录)
      - lessons/*.md (history recurrence tables)
      - Lines with merge/delete markers (合并自/原 loading-strategy/已删除/v9.3 合并/etc.)
    """
    errors: List[str] = []
    # Files where loading-strategy is allowed (history records)
    allowed_paths = {
        ".ai-memory/meta/spec-evolution.md",
        ".ai-memory/meta/archived-lessons.md",
        ".ai-memory/README.md",
    }
    # Markers indicating the line is a history/merge annotation (not current reference)
    history_markers = [
        "已删除", "已合并", "合并自", "合并入", "合并到", "原 loading-strategy",
        "v9.3 合并", "v9.3合并", "deleted", "merged", "history", "历史",
        "loading-strategy + ai-behavior-redlines",  # merge description
    ]
    # Scan root for .md files containing 'loading-strategy'
    # v9.4: scan .skills/ (authoritative source) instead of .trae/ (junction, would double-scan)
    scan_dirs = [root / ".ai-memory", root / "docs", root / ".skills", root / "scripts"]
    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for md_file in scan_dir.rglob("*.md"):
            rel = str(md_file.relative_to(root)).replace("\\", "/")
            # Skip allowed history files
            if rel in allowed_paths:
                continue
            # Skip spec files (historical records of past fixes; 迁移到 docs/specs/legacy-trae/)
            if rel.startswith("docs/specs/legacy-trae/"):
                continue
            # Skip lessons/ history files (recurrence tables)
            if rel.startswith(".ai-memory/lessons/"):
                continue
            # Skip evidence/ (historical verification records)
            if rel.startswith(".ai-memory/evidence/"):
                continue
            # Skip .trash/
            if rel.startswith(".trash/"):
                continue
            try:
                text = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            # Find lines with 'loading-strategy' that are NOT history annotations
            for line_num, line in enumerate(text.split("\n"), 1):
                if "loading-strategy" not in line:
                    continue
                # Allow lines that explicitly mark as deleted/merged (history annotation)
                if any(marker in line for marker in history_markers):
                    continue
                errors.append(
                    f"{rel} L{line_num}: stale 'loading-strategy' reference (should be 'ai-operating-handbook.md'). "
                    f"Line: {line.strip()[:120]}"
                )
    return errors
