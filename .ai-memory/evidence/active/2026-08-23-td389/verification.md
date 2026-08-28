---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反模式 写教训]
priority: high
symptom: [kb:evidence-template, 3-step-template, verification-step, evidence-verification]
solution: Verification 模板 — 跑过的命令 + 实际输出 + 截图;gaf-3step-evidence hook 校验占位符必须替换
related_files:
  - .ai-memory/evidence/templates/problem.md
  - .ai-memory/evidence/templates/solution.md
  - scripts/check_3step_evidence.py
created_by: AI
last_updated: 2026-08-23
---
## Verification（验证）

$ "D:\code\environment\conda\envs\gaf\python.exe" -m pytest backend/tasks/tests/test_analytics_views.py -q --create-db

预期：3 passed（覆盖 weekly-report recovery 字段非空、无恢复时 success_rate=None、task-stats 按任务 recovery 聚合）

$ "D:\code\environment\conda\envs\gaf\python.exe" -m ruff check backend/executions/views.py backend/tasks/tests/test_analytics_views.py

预期：All checks passed!

$ npx tsc -b

预期：前端类型检查无错误（恢复字段已加入 `ops.ts` 与 `AnalyticsDashboard.tsx` 内联 `WeeklyReport` 接口）
