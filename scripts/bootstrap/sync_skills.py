"""sync_skills.py — v9.0 skill+rule 4+1 synchronizer (renamed from sync_decision_tree).

v9.0 修订: 决策树单一权威源 — 只 gaf-orchestrator 保留决策树, 其他 3 个 SKILL.md 改为引用.
M1.H 修订: 加 --changelog 命令 (N117 — 决策树 hash 变更追踪 + 季度 review 提示)
v8.4 N124 修订: 移除 gaf-dev-workflow (业务命令速查已迁到 project_rules.md §1)
v8.5 restructure 修订: GAF 提升为 workspace 根,移除父级双向同步 (默认 --workspace-root none)
v9.4 multi-IDE 修订: 权威源迁移到 .skills/ (skills|rules), .trae/ .opencode/ 为 junction

分发层级 (v9.4 简化):
  - GAF 根(workspace root) .skills/skills/{name}/SKILL.md (4 份, 唯一权威源)
  - GAF 根(workspace root) .skills/rules/project_rules.md (1 份, 唯一权威源)
  - .trae/skills|rules 和 .opencode/skills|rules 是 junction → .skills/, 无需额外分发
  - 不再向 workspace 父级同步 (GAF 即 workspace 根)

分发目标 (4 skills + 1 rule):
  - 4 gaf-* skills: gaf-orchestrator (含决策树) / gaf-knowledge-base / gaf-task-execution / gaf-reflect-and-evolve
  - 1 规则文件:   project_rules.md

校验策略 (v9.0):
  - 4 gaf-* skills: 检查存在 + 必要 markers (header)
  - gaf-orchestrator: 额外检查决策树 block 存在 + 6 个必要 sections
  - project_rules.md: 检查存在 + 必要 markers

Run:
    python sync_skills.py                 # force sync (GAF root only, v8.5)
    python sync_skills.py --check         # CI mode (exit 0/1)
    python sync_skills.py --root <path>   # GAF repo root
    python sync_skills.py --workspace-root none    # v8.5 default: no parent sync
    python sync_skills.py --changelog               # 🆕 M1.H: 追加决策树 hash 变更到 changelog
    python sync_skills.py --changelog --note 'M1.H init'  # 带 note 追加

v9.0 note:
    Decision tree is now single-source (gaf-orchestrator only).
    Other 3 SKILL.md files reference it instead of duplicating.
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable when this file lives in a subdir.
import sys as _sys
from pathlib import Path as _Path

_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
_BOOTSTRAP_DIR = _Path(__file__).resolve().parents[0]
for _d in (_BOOTSTRAP_DIR, _SCRIPTS_DIR):
    if str(_d) not in _sys.path:
        _sys.path.insert(0, str(_d))

import _encoding_safe  # noqa: F401  (must be first; reconfigures stdout to UTF-8)

# s39: multi-context registration (N202 18) — register self as top-level
# 'sync_skills' in every loading context (__main__ / scripts.bootstrap /
# bootstrap / sys.path hack). Child modules never re-import this module.
_sys.modules.setdefault("sync_skills", _sys.modules[__name__])

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# =============================================================================
# 🆕 TD-323 (spec-85, 2026-07-21): SKILL.md frontmatter timestamp helpers
# =============================================================================

def get_skill_last_commit_date(skill_md_path: Path) -> str:
    """Return git last commit date (YYYY-MM-DD) for ``skill_md_path``.

    Calls ``git log -1 --format=%cs -- <path>`` (committer date short).
    Returns ``""`` if git is unavailable, file is not tracked, or any error occurs.
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(skill_md_path)],
            cwd=str(skill_md_path.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return ""



# =============================================================================
# Core inspection logic
# =============================================================================

def inspect_skill(skill_path: Path, source_path: Path, source_text: str) -> Tuple[str, str, str]:
    """Inspect a single skill copy.

    Returns (status, expected_hash, actual_hash).
    status ∈ {"ok", "missing", "broken", "drift", "marker-missing"}
    """
    if not skill_path.exists():
        return ("missing", _file_hash(source_path), "")

    actual_text = _read_text(skill_path)
    if not actual_text:
        return ("broken", _file_hash(source_path), "")

    actual = hashlib.sha256(actual_text.encode("utf-8")).hexdigest()[:16]
    expected = _file_hash(source_path)
    if actual != expected:
        # Check if it just has missing required markers (e.g., header not present).
        markers = SKILL_REQUIRED_MARKERS.get(skill_path.parent.name, [])
        missing_markers = [m for m in markers if m not in actual_text]
        if missing_markers:
            return ("marker-missing", expected, actual)
        return ("drift", expected, actual)
    return ("ok", expected, actual)


def inspect_rule(rule_path: Path, source_path: Path) -> Tuple[str, str, str]:
    """Inspect a single rule file. Same shape as inspect_skill()."""
    if not rule_path.exists():
        return ("missing", _file_hash(source_path), "")
    actual_text = _read_text(rule_path)
    if not actual_text:
        return ("broken", _file_hash(source_path), "")
    actual = hashlib.sha256(actual_text.encode("utf-8")).hexdigest()[:16]
    expected = _file_hash(source_path)
    if actual != expected:
        markers = RULE_REQUIRED_MARKERS.get(rule_path.name, [])
        missing_markers = [m for m in markers if m not in actual_text]
        if missing_markers:
            return ("marker-missing", expected, actual)
        return ("drift", expected, actual)
    return ("ok", expected, actual)


# =============================================================================
# Sync logic
# =============================================================================

def sync_skill(target: Path, source_path: Path, source_text: str) -> None:
    """Rewrite target so its content matches source_text."""
    if not target.exists():
        _write_text(target, _skill_minimal_scaffold(target.parent.name))
    target.write_text(source_text, encoding="utf-8")


def sync_rule(target: Path, source_path: Path) -> None:
    """Rewrite target rule file to match source."""
    source_text = _read_text(source_path)
    if not target.exists():
        _write_text(target, _rule_minimal_scaffold(target.name))
    target.write_text(source_text, encoding="utf-8")


# =============================================================================
# Workspace root detection (N94 fix)
# =============================================================================

def detect_workspace_root(repo_root: Path) -> Optional[Path]:
    """Auto-detect Trae IDE workspace root.

    Heuristic: walk up from `repo_root` looking for a directory that
    contains `.skills/skills/gaf-orchestrator/SKILL.md` (a marker file
    that should always be present in the IDE-recognized workspace).

    M0.L fix: skip repo_root itself, only check ancestors. The GAF
    repo has its own gaf-orchestrator, so returning repo_root would
    mean "GAF 仓库 = workspace 根" which defeats the purpose. We want
    the OUTER workspace, not the inner GAF repo.

    Returns None when no workspace root is detected.
    """
    marker = Path(".skills") / "skills" / "gaf-orchestrator" / "SKILL.md"
    parent = repo_root.parent
    if (parent / marker).exists():
        return parent
    ancestor = parent
    for _ in range(3):
        if (ancestor / marker).exists():
            return ancestor
        ancestor = ancestor.parent
    return None




def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync 5 SKILL.md + 1 rule.md to repo + workspace roots (M0.L 升级)."
    )
    parser.add_argument("--check", action="store_true",
                        help="Check consistency only; do not write (CI mode).")
    parser.add_argument("--root", default=str(REPO_ROOT_DEFAULT),
                        help="Path to the GAF repo root (default: %(default)s)")
    parser.add_argument("--workspace-root", default="none",
                        help=("Path to the Trae IDE workspace root. "
                              "v8.5: GAF is now workspace root, default 'none' (no parent sync). "
                              "Set explicit path only for legacy dual-root setups."))
    parser.add_argument("--changelog", action="store_true",
                        help="🆕 M1.H: append decision-tree block hash change to changelog.")
    parser.add_argument("--changelog-path", default=None,
                        help="🆕 M1.H: override changelog file path (default: gaf-orchestrator/_shared/decision-tree-changelog.md).")
    parser.add_argument("--note", default="",
                        help="🆕 M1.H: human-readable note for the changelog entry (e.g. 'N117 闭环').")
    parser.add_argument("--update-timestamps", action="store_true",
                        help="🆕 TD-323 (spec-85): sync SKILL.md frontmatter `updated` field with git log last commit date.")
    args = parser.parse_args(argv)

    if args.changelog:
        return cmd_changelog(args)

    if args.update_timestamps:
        return cmd_update_timestamps(args)

    root = Path(args.root).resolve()
    skills_dir = root / ".skills" / "skills"
    rules_dir = root / ".skills" / "rules"

    # Source-of-truth paths.
    sources: Dict[str, Path] = {}
    for skill in ALL_SKILLS:
        path = skills_dir / skill / "SKILL.md"
        if path.exists():
            sources[skill] = path
    for rule in RULE_FILES:
        path = rules_dir / rule
        if path.exists():
            sources[rule] = path

    # Resolve workspace root.
    # v8.5: GAF is now workspace root, so parent sync is disabled by default.
    # Only sync to parent when --workspace-root is explicitly set to a real path.
    workspace_root: Optional[Path] = None
    if args.workspace_root and args.workspace_root.lower() != "none":
        workspace_root = Path(args.workspace_root).resolve()

    # Compute all targets.
    targets: List[Tuple[str, str, Path, Path]] = []  # (kind, name, source, target)
    for skill in ALL_SKILLS:
        if skill not in sources:
            continue
        src = sources[skill]
        # repo copy
        targets.append(("skill", skill, src, src))  # identity for repo
        # workspace copy
        if workspace_root is not None:
            ws_target = workspace_root / ".skills" / "skills" / skill / "SKILL.md"
            targets.append(("skill", skill, src, ws_target))
    for rule in RULE_FILES:
        if rule not in sources:
            continue
        src = sources[rule]
        targets.append(("rule", rule, src, src))  # identity for repo
        if workspace_root is not None:
            ws_target = workspace_root / ".skills" / "rules" / rule
            targets.append(("rule", rule, src, ws_target))

    if not sources:
        print(f"❌ 仓库内无任何源文件: {skills_dir} {rules_dir}")
        return 1

    # Inspect all targets.
    issues: List[Tuple[Path, str, str, str, str]] = []
    for kind, name, src, tgt in targets:
        if kind == "skill":
            status, expected, actual = inspect_skill(tgt, src, _read_text(src))
        else:
            status, expected, actual = inspect_rule(tgt, src)
        if status != "ok":
            issues.append((tgt, kind, status, expected, actual))

    # Required-section check for source decision tree (N68) — only for decision tree copies.
    for skill in DECISION_TREE_COPIES:
        if skill not in sources:
            continue
        src_text = _read_text(sources[skill])
        block = _extract_decision_tree_block(src_text)
        if block:
            missing_sections = [s for s in REQUIRED_DECISION_TREE_SECTIONS if s not in block]
            if missing_sections:
                print(f"❌ 源决策树缺 section (in {sources[skill]}): {missing_sections}")
                return 1

    # P3 治本机制 (2026-07-16): N## 索引行只能在 failure-modes.md / archived-lessons.md 出现.
    # 其他文件出现 N## 索引行 = 单一权威源违反, 报错 (不自动修复, 需人工判断引用 vs 硬约束).
    n_index_violations = check_n_index_duplication(root)
    if n_index_violations:
        print("❌ N## 索引行出现在非权威文件 (单一权威源违反):")
        for rel, n_id in n_index_violations:
            print(f"  - {rel}: {n_id}")
        print()
        print("权威源: .ai-memory/meta/failure-modes.md / .ai-memory/meta/archived-lessons.md")
        print("修复: 将 N## 索引行从上述文件删除, 改为引用格式 (如 '见 failure-modes.md N112')")
        return 1

    # P3 fix (2026-07-16): L2 清单一致性检测 — 2 处引用 + 1 处存在性必须与 EXPECTED_L2_FILES 一致.
    # 治本: 防止 ai-operating-handbook.md / gaf_init.sh / gaf-orchestrator SKILL.md L2 清单漂移.
    l2_errors = check_l2_consistency(root)
    if l2_errors:
        print("❌ L2 清单不一致 (单一权威源违反):")
        for err in l2_errors:
            print(f"  - {err}")
        print()
        print(f"权威清单 (EXPECTED_L2_FILES): {EXPECTED_L2_FILES}")
        print("修复: 2 处引用 (gaf_init.sh L2_FILES / gaf-orchestrator SKILL.md L2 hard-load) + L2 权威源 ai-operating-handbook.md 存在性, 必须与 EXPECTED_L2_FILES 一致")
        return 1

    # spec-14 Phase 4 (2026-07-17): lessons_count 一致性检测 (防 lessons/README.md frontmatter 漂移)
    lessons_count_errors = check_lessons_count_consistency(root)
    if lessons_count_errors:
        print("❌ lessons_count 不一致 (lessons/README.md frontmatter 漂移):")
        for err in lessons_count_errors:
            print(f"  - {err}")
        print()
        print("修复: python scripts/bootstrap/sync_ai_memory.py (自动重算 lessons_count)")
        return 1

    # spec-14 Phase 4 (2026-07-17): Active N## 索引完整性检测 (防 failure-modes.md N## 不在 README)
    n_indexed_errors = check_n_indexed_in_readme(root)
    if n_indexed_errors:
        print("❌ Active N## 索引漂移 (failure-modes.md N## 缺于 lessons/README.md):")
        for err in n_indexed_errors:
            print(f"  - {err}")
        print()
        print("修复: 在 lessons/README.md topic 表或文件清单段补对应 N## 条目")
        return 1

    # spec-14 Phase 4 (2026-07-17): loading-strategy 过时引用检测 (防 v9.3 合并后遗留引用)
    ls_errors = check_loading_strategy_references(root)
    if ls_errors:
        print("❌ loading-strategy 过时引用 (v9.3 已合并到 ai-operating-handbook.md):")
        for err in ls_errors:
            print(f"  - {err}")
        print()
        print("修复: 将 'loading-strategy' 改为 'ai-operating-handbook.md (v9.3 合并自 loading-strategy + ai-behavior-redlines)'")
        print("      或在历史记录段标注 '已删除 v9.3' / '已合并' / 'history' 标记")
        return 1

    # 🆕 TD-323 (spec-85, 2026-07-21): frontmatter `updated` field vs git log consistency.
    # WARN-only (non-blocking): print warnings but do not return 1.
    timestamp_warnings: List[str] = []
    for skill in TIMESTAMP_SKILLS:
        skill_md = skills_dir / skill / "SKILL.md"
        if not skill_md.exists():
            continue
        text = _read_text(skill_md)
        if not text:
            continue
        current_updated = parse_frontmatter_updated(text)
        if not current_updated:
            timestamp_warnings.append(f"{skill}/SKILL.md: frontmatter 缺 updated 字段")
            continue
        last_commit = get_skill_last_commit_date(skill_md)
        if not last_commit:
            continue  # git log failed (e.g. untracked file), skip silently
        if current_updated != last_commit:
            timestamp_warnings.append(
                f"{skill}/SKILL.md: updated={current_updated} vs git log={last_commit} (stale)"
            )
    if timestamp_warnings:
        print("⚠️  SKILL.md frontmatter `updated` 滞后 (非阻塞, 跑 --update-timestamps 修复):")
        for w in timestamp_warnings:
            print(f"   - {w}")
        print()

    if not issues:
        total_skills = sum(1 for t in targets if t[0] == "skill")
        total_rules = sum(1 for t in targets if t[0] == "rule")
        print(f"✅ 4 skills + 1 rule 副本一致 ({total_skills} skill 副本 + {total_rules} rule 副本):")
        print(f"   GAF 根(workspace root): 4 skill + 1 rule")
        print(f"   决策树权威源: gaf-orchestrator (v9.0 单一权威源)")
        if workspace_root is not None:
            print(f"   额外同步到: {workspace_root} (legacy dual-root mode)")
        else:
            print(f"   父级同步: 已禁用 (v8.5: GAF 即 workspace 根)")
        return 0

    if args.check:
        print(_format_report(issues))
        return 1

    # Sync mode.
    print("🔄 自动同步 4 skills + 1 rule (双根)...")
    for kind, name, src, tgt in targets:
        source_text = _read_text(src)
        if kind == "skill":
            sync_skill(tgt, src, source_text)
        else:
            sync_rule(tgt, src)
        try:
            rel = tgt.relative_to(root)
        except ValueError:
            rel = tgt
        print(f"  ✅ [{kind}] {rel}")
    print()
    print("✅ 同步完成。重新跑 --check 验证:")
    print("   python scripts/bootstrap/sync_skills.py --check")
    return 0

# =============================================================================
# =============================================================================
# s39: re-exports from skill_sync/ package (split 2026-08-18, TD-365 6/9).
# Public/private names are re-bound here so all existing callers
# (tests, governance batch, scripts) keep working unchanged.
# NOTE: noqa: F401 — these bindings ARE the public API of this module.
# =============================================================================
from skill_sync.changelog import (  # noqa: E402, F401
    _build_changelog_entry,
    _extract_decision_tree_block_hash,
    _format_report,
    _read_changelog_last_hash,
    append_changelog_entry,
    cmd_changelog,
)
from skill_sync.checks import (  # noqa: E402, F401
    check_l2_consistency,
    check_lessons_count_consistency,
    check_loading_strategy_references,
    check_n_index_duplication,
    check_n_indexed_in_readme,
)
from skill_sync.constants import (  # noqa: E402, F401
    _FRONTMATTER_RE,
    _FRONTMATTER_UPDATED_RE,
    ALL_SKILLS,
    CHANGELOG_PATH_DEFAULT,
    DECISION_TREE_COPIES,
    DECISION_TREE_END,
    DECISION_TREE_START,
    EXPECTED_L2_FILES,
    N_INDEX_AUTHORIZED_FILES,
    N_INDEX_ROW_PATTERN,
    N_INDEX_SCAN_PATHS,
    REPO_ROOT_DEFAULT,
    REQUIRED_DECISION_TREE_SECTIONS,
    RULE_FILES,
    RULE_REQUIRED_MARKERS,
    RULES_DIR_DEFAULT,
    SKILL_REQUIRED_MARKERS,
    SKILLS_DIR_DEFAULT,
    TIMESTAMP_SKILLS,
)
from skill_sync.io_utils import (  # noqa: E402, F401
    _block_hash,
    _extract_decision_tree_block,
    _file_hash,
    _read_text,
    _rule_minimal_scaffold,
    _skill_minimal_scaffold,
    _write_text,
    parse_frontmatter_updated,
    update_frontmatter_updated,
)
from skill_sync.timestamps import cmd_update_timestamps  # noqa: E402, F401

if __name__ == "__main__":
    sys.exit(main())
