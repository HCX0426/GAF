---
solution_type: refactor
scope: hooks + rules + lessons
effort: 213 insertions
---

1. 归档 2 个已完成 spec (pipeline-task-diagnosis + governance-redundancy-consolidation) → `docs/specs/archived/2026-08/` (commit -)
2. 合并 main 分支: 解决 .trae/rules|skills junction 阻塞 checkout 问题 (临时移 junction → ff merge → 恢复)
3. N201 复盘触发闭环: check_claimed_rules.py rate 排除 unknowable (N/A 语义) + 记录加 no-evidence 列 + check_review_trigger (累计 ≥3 且最近 3 条 ≥2 条 <50% → 🔴 警告 + REVIEW_TRIGGERED 标记)
4. 沉淀: lesson N201 + failure-modes N201 索引 + ai-operating-handbook M2 复盘处理红线 + project_rules N201 数据驱动闭环段
