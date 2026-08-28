# spec-2026-08-18-s39-sync-skills-split

> **类型**: refactor（大文件拆分，TD-365 6/9）
> **目标**: `scripts/bootstrap/sync_skills.py` 1064 行 → 拆分到 `scripts/bootstrap/skill_sync/` 域包，主文件 < 550 行
> **模式**: 复用 N202 ⑰⑱ 检查项（s38 闭环经验）

## 阶段状态表

| Phase | 状态 | 完成时间 | commit | 验收 evidence |
|-------|------|---------|--------|--------------|
| P1 结构分析 + spec | ✅ | 21:30 | - | 6 功能域识别 + 拆分设计定稿 |
| P2 拆分实现 | ✅ | 21:55 | - | 主文件 457 行 + skill_sync/ 5 模块 |
| P3 验证 + commit | ✅ | 22:15 | - | 25 passed + governance 13/13 + 580 passed 全量 |
| P4 归档 + TD-365 更新 | ✅ | 22:20 | - | 6/9 + evidence + N202 ⑲-㉓ |

## 1. 结构分析（P1）

sync_skills.py 1064 行，6 个清晰功能域：

| 行区间 | 内容 | 行数 |
|--------|------|------|
| L1-55 | docstring + bootstrap + imports | 55 |
| L56-125 | 模块级常量 + 正则（REPO_ROOT_DEFAULT/SKILLS_DIR_DEFAULT/RULES_DIR_DEFAULT/DECISION_TREE_*/CHANGELOG_PATH_DEFAULT/DECISION_TREE_COPIES/ALL_SKILLS/TIMESTAMP_SKILLS/_FRONTMATTER_RE/_FRONTMATTER_UPDATED_RE/RULE_FILES/N_INDEX_*/EXPECTED_L2_FILES） | 70 |
| L127-345 | 5 个 check_* 一致性检查函数 | 219 |
| L348-369 | 常量块 2（REQUIRED_DECISION_TREE_SECTIONS/SKILL_REQUIRED_MARKERS/RULE_REQUIRED_MARKERS） | 22 |
| L371-417 | 文件/文本工具（_read_text/_file_hash/_extract_decision_tree_block/_block_hash/_write_text/_skill_minimal_scaffold/_rule_minimal_scaffold） | 47 |
| L423-443 | get_skill_last_commit_date（git log，**留主文件**，main timestamp 检查用） | 21 |
| L445-480 | frontmatter 工具（parse_frontmatter_updated/update_frontmatter_updated） | 36 |
| L486-529 | inspect_skill/inspect_rule（**留主文件**） | 44 |
| L533-548 | sync_skill/sync_rule（**留主文件**） | 16 |
| L552-578 | detect_workspace_root（**留主文件**） | 27 |
| L582-780 | changelog 域（_format_report/_extract_decision_tree_block_hash/_read_changelog_last_hash/_build_changelog_entry/append_changelog_entry/cmd_changelog） | 199 |
| L786-847 | timestamps 域（cmd_update_timestamps） | 62 |
| L849-1064 | main() + 入口点（**留主文件**） | 216 |

## 2. 拆分设计（P2）

目标目录 `scripts/bootstrap/skill_sync/`（对齐 s38 `ai_memory_sync/` 风格，专属顶层名避免通用名冲突）：

| 文件 | 内容 | 预估行数 | 依赖 |
|------|------|---------|------|
| `skill_sync/__init__.py` | 包标记 + 版本注释 | 5 | 无 |
| `skill_sync/constants.py` | 全部常量 + 正则（L56-125 + L348-369） | 95 | 无 |
| `skill_sync/io_utils.py` | 7 个工具函数 + 2 个 frontmatter 函数（L371-417 + L445-480） | 90 | constants |
| `skill_sync/checks.py` | 5 个 check_*（L127-345） | 225 | constants |
| `skill_sync/changelog.py` | changelog 域 6 函数（L582-780） | 205 | constants + io_utils |
| `skill_sync/timestamps.py` | cmd_update_timestamps（L786-847） | 68 | constants + io_utils |

**依赖图无循环**：constants → io_utils → checks/changelog/timestamps → 主文件（只单向 import 子模块）。子模块**零主文件依赖**，不需要 s38 的 `_main.` 运行时常量模式。

**主文件（~500 行）**：docstring + bootstrap + 头部注册 + import 子模块 + get_skill_last_commit_date/inspect_skill/inspect_rule/sync_skill/sync_rule/detect_workspace_root/main + 入口点 + 尾部 re-export（对齐 N202 ⑰：插入在 `if __name__` 块**之前**）。

**N202 ⑱ 检查项**：主文件头部**无条件** `sys.modules.setdefault("sync_skills", sys.modules[__name__])`（4 种加载上下文统一注册：__main__/scripts.bootstrap.sync_skills/bootstrap.sync_skills/sys.path-hack 顶层）；子模块 import 用 `from sync_skills_lib...`——**不对，用 `skill_sync`**。

**governance 上下文 import 注意（N202 ⑱ 深坑）**：governance batch 以 `bootstrap.sync_skills` 加载 → 主文件 `from skill_sync.constants import ...`（顶层名）→ sys.path 含 scripts/（主文件 L41-43 bootstrap 段 + governance _ensure_scripts_on_path 双保险）→ `import skill_sync` 命中 `scripts/skill_sync/` ✅。**不依赖顶层 `scripts` 包**（win32/scripts 冲突规避，s38 教训）。

## 3. 验证标准（P3）

1. **依赖测试全绿**：`test_decision_tree_sync.py`（5 测试，含 re-export 访问）+ `test_sync_skills_timestamps.py`（monkeypatch TIMESTAMP_SKILLS）+ `test_sync_changelog.py` + `test_bootstrap_gaf.py`（skills bootstrap）
2. **governance batch 13/13**：`python scripts/hooks/gaf_governance_batch.py`（sync_skills --check 子项必过）
3. **三上下文冒烟**：CLI `--check` rc 0 / `from scripts.bootstrap import sync_skills` re-exports NONE missing / `python -c "import bootstrap.sync_skills"`（governance 等价）
4. **ruff**：新文件 0 errors（预存风格错误除外）
5. 主文件 < 550 行

## 4. 归档（P4）

- evidence 三件套 → `.ai-memory/evidence/active/2026-08-18-s39-sync-skills-split/`
- spec-context → `docs/archive/spec-context/2026-08-18-s39-sync-skills-split-context.md`
- N202 lesson 追加（如新坑）
- TD-365 6/9 更新（sync_skills.py 划线）
- spec 归档 → `docs/specs/archived/2026-08/`

## 验收标准（P0）

- [ ] 主文件 1064 → < 550 行，功能零变化
- [ ] 依赖测试 + governance batch 13/13 全绿
- [ ] 三上下文加载冒烟通过
- [ ] re-export 完整（测试访问的符号全部可用）
- [ ] TD-365 更新 6/9

## Deviation Log

- **D1（N202 ⑲）**: constants.py parents[2] → parents[3]（文件移入 skill_sync/ 子包深一层）
- **D2（N202 ⑳）**: changelog.py 补 import re; checks.py 补 rom .io_utils import _read_text; 主文件补 import hashlib
- **D3（N202 ㉑）**: ruff --fix 删除裸 from-import re-export 绑定（F401 误判）→ 恢复 + # noqa: E402, F401 每行标注
- **D4（N202 ㉒）**: 测试 monkeypatch 目标改 skill_sync.constants（真实持有者）+ timestamps.py 改模块属性访问
- **N202 ㉓**: 子包相对导入统一 + 主文件 bootstrap 段双目录（parents[0] + parents[1]）
