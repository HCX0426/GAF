---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反模式 写教训]
priority: high
symptom: [kb:evidence-template, 3-step-template, problem-step, evidence-problem]
solution: Problem 模板 — 描述症状/触发条件/影响范围;gaf-3step-evidence hook 校验占位符必须替换
related_files:
  - .ai-memory/evidence/templates/solution.md
  - .ai-memory/evidence/templates/verification.md
  - scripts/check_3step_evidence.py
created_by: AI
last_updated: 2026-08-23
---
## Problem（症状 / 触发条件 / 影响范围）

GAF 自诩的"5 层异常恢复"机制从未被量化：`TaskExecution.recovery_attempts` / `recovery_layer` 字段已落库，但 analytics 聚合（后端 `weekly_report_view`/`task_stats_view`）与前端 `AnalyticsDashboard` 全量 grep `recovery` 零命中 —— "多少次执行触发了恢复 / 平均恢复尝试次数 / 恢复后成功率"从未被聚合或展示，恢复有效性不可观测。

触发条件：运营想从 `/ops/analytics` 周报卡片看恢复健康度时，相关指标不存在。
影响范围：`backend/executions/views.py`（analytics 聚合）、`frontend/src/pages/Ops/AnalyticsDashboard.tsx`（周报卡片）、`frontend/src/api/ops.ts`（API 契约）。
