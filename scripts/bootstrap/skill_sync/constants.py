"""skill_sync.constants — shared constants/regexes for sync_skills (s39 split, TD-365 6/9).

Imported by sync_skills.py (main) and skill_sync submodules. Zero main-file
dependency (N202 18: no import cycles).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[3]
SKILLS_DIR_DEFAULT = REPO_ROOT_DEFAULT / ".skills" / "skills"
RULES_DIR_DEFAULT = REPO_ROOT_DEFAULT / ".skills" / "rules"

# Section markers (decision tree block).
DECISION_TREE_START = "## Decision Tree"
DECISION_TREE_END = "## End Decision Tree"

# 🆕 M1.H: changelog file location.
CHANGELOG_PATH_DEFAULT = (
    REPO_ROOT_DEFAULT
    / ".skills" / "skills" / "gaf-orchestrator" / "_shared" / "decision-tree-changelog.md"
)

# v9.0: Only gaf-orchestrator holds the decision tree (single source of truth).
DECISION_TREE_COPIES = [
    "gaf-orchestrator",
]

# All 4 gaf-* skills are checked for existence + required markers.
ALL_SKILLS = [
    "gaf-orchestrator",
    "gaf-knowledge-base",
    "gaf-task-execution",
    "gaf-reflect-and-evolve",
]

# 🆕 TD-323 (spec-85, 2026-07-21): SKILL.md frontmatter timestamp sync scope.
# Includes gaf-lesson-router (not in ALL_SKILLS for legacy sync scope, but part
# of the 5-skill framework and also needs `updated` field maintenance).
TIMESTAMP_SKILLS = ALL_SKILLS + ["gaf-lesson-router"]

# 🆕 TD-323: frontmatter regex for `updated` field parsing/replacement.
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
_FRONTMATTER_UPDATED_RE = re.compile(r"^updated:\s*(\S+)\s*$", re.MULTILINE)

# Rule file (also distributed, but no decision tree block to check).
RULE_FILES = [
    "project_rules.md",
]

# P3 治本机制 (2026-07-16): N## 索引行只能在 failure-modes.md / archived-lessons.md 出现
# 其他文件 (rules.md / SKILL.md / yn-matrices/ 等) 出现 N## 索引行 → 报错
# N## 索引行 = 4 列表格 + 第 4 列含 lessons/ 或闭环标记
N_INDEX_AUTHORIZED_FILES = {
    ".ai-memory/meta/failure-modes.md",
    ".ai-memory/meta/archived-lessons.md",
}
# Regex to detect N## index rows (4-column table with N## + lesson/closure marker)
N_INDEX_ROW_PATTERN = re.compile(
    r"^\|\s*(N\d+)\s*\|[^|]+\|[^|]+\|[^|]*(?:lessons/|闭环|dormant|已合并)[^|]*\|$",
    re.MULTILINE,
)
# Files scanned for N## index duplication (relative to repo root)
N_INDEX_SCAN_PATHS: List[str] = [
    ".skills/rules/project_rules.md",
    ".skills/skills/gaf-orchestrator/SKILL.md",
    ".skills/skills/gaf-task-execution/SKILL.md",
    ".skills/skills/gaf-reflect-and-evolve/SKILL.md",
    ".skills/skills/gaf-knowledge-base/SKILL.md",
    ".skills/skills/gaf-lesson-router/SKILL.md",
]

# P3 fix (2026-07-16, v9.3 update) + v9.5 (spec-65): L2 清单单一权威源 — v9.5 从 1 文件扩展为 2 文件 (handbook + tech-stack).
# 权威源: .ai-memory/meta/ai-operating-handbook.md (Part 1 L1/L2/L3 加载策略) + docs/reference/tech-stack.md.
# 2 处引用必须与常量一致: gaf_init.sh L2_FILES / gaf-orchestrator SKILL.md L2 hard-load.
EXPECTED_L2_FILES: List[str] = [
    ".ai-memory/meta/ai-operating-handbook.md",
    "docs/reference/tech-stack.md",
]

# Required substrings (N68) inside each decision tree copy's block.
REQUIRED_DECISION_TREE_SECTIONS = [
    "step_1_identify_task_type",
    "new_feature",
    "bug_fix",
    "documentation",
    "refactor",
    "unknown",
]

# Per-skill required substrings (loose check, mainly for "skill loaded correctly").
SKILL_REQUIRED_MARKERS: Dict[str, List[str]] = {
    "gaf-orchestrator": ["# gaf-orchestrator", "step_1_identify_task_type"],
    "gaf-knowledge-base": ["# gaf-knowledge-base"],
    "gaf-task-execution": ["# gaf-task-execution"],
    "gaf-reflect-and-evolve": ["# gaf-reflect-and-evolve"],
}

RULE_REQUIRED_MARKERS: Dict[str, List[str]] = {
    "project_rules.md": ["# GAF 项目开发规则"],
}

