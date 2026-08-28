---
date: 2026-06-21
symptom:
- skill
- deletion
- decision-tree
- sync
- marker-collision
solution: 删除 skill 时必须同步更新所有引用脚本 (sync_skills/promote_lessons/gaf_init) 的 marker 和计数;
  决策树块同步脚本不能用 find() 匹配 "## Decision Tree" 因为注释中也可能出现该字符串, 必须用行首匹配
diff_keywords: [skill-deletion, decision-tree, sync_skills, marker-collision]
related_files:
- .trae/rules/project_rules.md
- .trae/skills/gaf-orchestrator/SKILL.md
- .trae/skills/gaf-knowledge-base/SKILL.md
- .trae/skills/gaf-task-execution/SKILL.md
- .trae/skills/gaf-reflect-and-evolve/SKILL.md
- scripts/bootstrap/sync_skills.py
- scripts/lessons/promote_lessons.py
- scripts/gaf_init.sh
created_by: AI
level: L1
n_id: N124
topic: workflow
---



# N124: skill 删除 + 决策树扩展 + 同步脚本 marker 冲突

## 症状

1. **gaf-dev-workflow skill 删除后引用残留**: 删除 skill 目录后, sync_skills.py / promote_lessons.py / gaf_init.sh 仍引用 gaf-dev-workflow 作为 marker, 导致同步和验证失败
2. **决策树块同步脚本 marker 冲突**: 临时脚本 `_temp_sync_dt.py` 用 `text.find("## Decision Tree")` 匹配决策树块起始位置, 但 gaf-orchestrator/SKILL.md 的注释行 `# 4. 读本 SKILL.md 顶部决策树副本（下面 ## Decision Tree）` 也包含该字符串, 导致 find() 匹配到注释中的 "## Decision Tree" 而非真正的 header
3. **后果**: 同步脚本误删了注释后面的 L2 hard-load hooks yaml 块, 并把 "## Decision Tree" header 合并到注释行 (丢失换行)

## 根因

- **skill 删除无全局引用扫描**: 删除 skill 时只删了目录, 没扫描所有脚本中的 marker 引用
- **find() 匹配过于宽松**: `str.find()` 匹配子串而非行首, 注释中的 "## Decision Tree" 文本被误认为 header
- **决策树块边界定义不严谨**: 应该用 `\n## Decision Tree\n` (行首匹配) 而非 `## Decision Tree` (子串匹配)

## 修复

1. **skill 删除引用清理**:
   - sync_skills.py: WORKFLOW_SKILLS 删除, ALL_SKILLS = DECISION_TREE_COPIES, marker gaf-dev-workflow → gaf-orchestrator
   - promote_lessons.py: skill target path gaf-dev-workflow → gaf-orchestrator
   - gaf_init.sh: 5 skills → 4 skills, ls 命令移除 gaf-dev-workflow
2. **决策树块同步修复**:
   - 手动修复 gaf-orchestrator/SKILL.md: 恢复 "## Decision Tree" 为独立 header 行
   - 教训: 未来决策树块同步脚本应使用 `\n## Decision Tree\n` 行首匹配, 或用正则 `^## Decision Tree$`
3. **高价值内置 skill 集成**:
   - new_feature: + test-driven-development
   - bug_fix: + systematic-debugging
   - documentation: + doc-coauthoring
   - refactor: + python-design-patterns
   - 所有分支: + step_6_verify_before_commit (verification-before-completion)
   - 按需调用: python-testing-patterns / django-patterns / api-design / database-design / vercel-react-best-practices / browser-use

## 5 层分发

| # | 层级 | 路径 | 状态 |
|:-:|------|------|:----:|
| ① | .ai-memory/ 教训层 | `.ai-memory/lessons/N124-skill-deletion-and-decision-tree-sync.md` (本文件) | ✅ |
| ② | docs/ 架构教训层 | `.ai-memory/summaries/architecture-mistakes.md` (新增 #29 条目) | ✅ |
| ③ | spec/ 计划文档层 | 无对应 spec (本次为用户直接指令,非 spec 驱动) | N/A |
| ④ | SKILL.md 工作流层 | `.trae/skills/gaf-orchestrator/SKILL.md` + `.trae/skills/gaf-reflect-and-evolve/SKILL.md` 引用已更新 "gaf-dev-workflow 已删除 (N124)" | ✅ |
| ⑤ | project_rules.md 用户规则层 | §0 开发工作流 + §5.3 promote target 已更新 "gaf-dev-workflow 已删除 (N124)" | ✅ |

## 验证

- `pytest scripts/tests/`: 15 passed (test_decision_tree_sync + test_gaf_init_shell + test_bootstrap_gaf)
- `sync_skills.py --check`: 4 skills + 1 rule 副本一致 (8 skill 副本 + 2 rule 副本)
- `check_path_consistency.py`: 0 error, 66 warning (全为 pre-existing 硬编码路径)
- 4 commits: - + - + - + -
