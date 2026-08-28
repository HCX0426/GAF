---
date: 2026-06-21
symptom: [ai-memory, restructure, directory, migration]
solution: '拆分 .ai-memory/ 子目录时,必须同步更新所有依赖脚本的硬编码路径,并给移出 lessons/ 的汇总文件加 maintainer: manual 防止被 sync_ai_memory 覆盖'
diff_keywords: ["architecture", "mistakes", "architecture-mistakes", "code", "rules", "code-rules", "library", "conflicts", "library-conflicts", "sync", "ai", "memory"]
related_files:
  - .ai-memory/summaries/architecture-mistakes.md
  - .ai-memory/summaries/code-rules.md
  - .ai-memory/summaries/library-conflicts.md
  - scripts/bootstrap/sync_ai_memory.py
  - scripts/lessons/extract_lessons.py
  - scripts/tests/test_extract_lessons.py
created_by: AI
level: L1
n_id: N123
topic: workflow
---


# N123: .ai-memory/ 目录重组教训

## 症状

将 `.ai-memory/` 从 3 子目录 (meta/lessons/rules) 重组为 5 子目录 (meta/ops/checklists/lessons/summaries + knowledge) 时,遗漏了多处依赖:

1. **3 个汇总文件缺 maintainer 字段**: `architecture-mistakes.md` / `code-rules.md` / `library-conflicts.md` 从 `lessons/` 移到 `summaries/` 后,失去 lesson 的 implicit manual 保护,会被 `sync_ai_memory.py` 自动覆盖为 stub
2. **extract_lessons.py 硬编码路径**: `SOURCE_PATHS` 仍指向 `.ai-memory/summaries/code-rules.md` 和 `bug-tracker (已删除)`,导致 `test_4_data_sources` 测试失败 (0 items)
3. **test_e2e_run_all.py 硬编码路径**: `why_path` 仍指向 `why-skipped (已删除)` (已移到 `ops/`)
4. **3 份决策树副本 load_skills 缺 gaf-lesson-router**: `sync_skills.py` 只检查整文件 hash,不检查副本间 Decision Tree 内容一致性

## 根因

- **路径迁移无全局扫描**: 移文件后只改了主要脚本,漏了测试文件和次要脚本
- **maintainer 保护机制隐式**: lesson 文件靠 `"lessons" in path.parts` 隐式判断,移到 `summaries/` 后需显式加 `maintainer: manual` 或扩展 `is_summary` 逻辑
- **sync_skills.py 检测盲区**: 只检测 GAF 仓库内文件与 workspace 副本的整文件 hash,不检测 4 份决策树副本之间的 Decision Tree 块内容一致性

## 修复

1. 给 3 个汇总文件添加 `maintainer: manual` 字段
2. `sync_ai_memory.py` 添加 `is_summary = "summaries" in path.parts` 逻辑
3. `extract_lessons.py` 的 `SOURCE_PATHS` 改为 `SUMMARIES_DIR` 和 `OPS_DIR`
4. `test_extract_lessons.py` 和 `test_e2e_run_all.py` 的 fake repo 路径同步更新
5. 手动修复 3 份决策树副本的 `load_skills` 行

## 5 层分发

| # | 层级 | 路径 | 状态 |
|:-:|------|------|:----:|
| ① | .ai-memory/ 教训层 | `.ai-memory/lessons/N123-ai-memory-restructure.md` (本文件) | ✅ |
| ② | docs/ 架构教训层 | `.ai-memory/summaries/architecture-mistakes.md` (自动生成) | ✅ |
| ③ | spec/ 计划文档层 | 无对应 spec (本次为用户直接指令,非 spec 驱动) | N/A |
| ④ | SKILL.md 工作流层 | `.trae/skills/gaf-lesson-router/SKILL.md` taxonomy 表新增 N123 | ✅ |
| ⑤ | project_rules.md 用户规则层 | §5.1 L1/L2/L3 加载机制已覆盖路径迁移要求 | ✅ |

## 验证

- `ruff check`: 125 个 pre-existing 错误 (typing.List 现代化建议,非本次引入)
- `pytest scripts/tests/`: 145 passed, 0 failed
- `sync_skills.py --check`: 5 skills + 1 rule 副本一致
- `check_path_consistency.py`: 0 error, 66 warning (全为 pre-existing 硬编码路径)
