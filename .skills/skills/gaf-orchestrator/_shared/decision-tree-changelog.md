---
maintainer: auto
source: .skills/skills/gaf-orchestrator/_shared/decision-tree-changelog.md
load_when:
- 决策树变更 review
- 季度 review
- hash 漂移排查
- 旧决策树引用
priority: medium
symptom:
- decision-tree-changelog
- decision-tree-hash-drift
- 决策树历史
solution: 每次 sync_skills.py --changelog 自动追加一行 (date + old_hash + new_hash + note)
related_files:
- scripts/bootstrap/sync_skills.py
created_by: AI
last_updated: 2026-06-17
---
# Decision Tree Changelog (M1.H 闭环)

> **自动追踪**: `../gaf-orchestrator/SKILL.md` 中 `## Decision Tree` ↔ `## End Decision Tree` 块的 SHA-256 (16-char prefix)
> **更新命令**: `python scripts/bootstrap/sync_skills.py --changelog`
> **触发逻辑**: 当 block hash 与上次记录不一致时, 自动追加一行

## 1. 决策树 hash 变更记录

| # | date | old_hash | new_hash | note | author |
|:-:|:----:|:--------:|:--------:|------|:------:|
| 1 | 2026-06-17 | (initial) | 104b599d7f744018 | M1.H init - 决策树 changelog + 季度 review 闭环 | AI |
| 2 | 2026-06-21 | 104b599d7f744018 | e94d002a4bf994e5 | Add gaf-lesson-router skill to decision tree | AI |
| 3 | 2026-06-21 | e94d002a4bf994e5 | c83df9e1cb6cf8a9 | N122 scripts maintenance checklist added | AI |
| 4 | 2026-06-22 | c83df9e1cb6cf8a9 | 31b83c9070950273 | Add playwright-best-practices to frontend browser automation skill stack | AI |
| 5 | 2026-07-06 | 31b83c9070950273 | 5fa2258012df7bb1 | 修复 ai-lessons 路径迁移后残留引用 (P0 冲突 A 闭环) | AI |
| 6 | 2026-07-17 | 5fa2258012df7bb1 | 762f67ebfb2a7f30 | N166 L3 循环段 + N167 七维度评分同步 (spec 2026-07-17-ai-thinking-workflow-rules-sync Phase 1-4) | AI |
| 7 | 2026-07-18 | 762f67ebfb2a7f30 | eb68668caeca8fde | unknown 分支闭环修复 (step_1b/2/3/4/5 + L3 query) | AI |
