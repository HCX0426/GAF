---
maintainer: manual
source: GAF/.ai-memory/evidence/templates/
load_when: [evidence, 3-step-evidence, 反模式 写教训]
priority: high
symptom: [kb:evidence-template, 3-step-template, solution-step, evidence-solution]
solution: Solution 模板 — 列步骤 + 涉及文件 + 命令;gaf-3step-evidence hook 校验占位符必须替换
related_files:
  - .ai-memory/evidence/templates/problem.md
  - .ai-memory/evidence/templates/verification.md
  - scripts/check_3step_evidence.py
created_by: AI
last_updated: 2026-08-23
---
## Solution（解决步骤）

1. 在 `backend/executions/views.py` 的 `weekly_report_view` 返回体新增扁平字段 `total_executions`/`success_count`/`failed_count`/`most_executed_task`/`avg_step_duration_ms`/`success_rate` 与 recovery 三字段 `recovery_triggered_count`/`avg_recovery_attempts`/`recovery_success_rate`（保留既有 `summary`/`daily_breakdown`）。
2. 在 `backend/executions/views.py` 的 `task_stats_view` 每个任务聚合项中新增 recovery 三字段。
3. 同步前端 `frontend/src/api/ops.ts` 的 `WeeklyReport` 接口与 `frontend/src/pages/Ops/AnalyticsDashboard.tsx` 内联 `WeeklyReport` 接口新增 recovery 三字段，并在周报卡片渲染触发次数与恢复成功率。
4. 在 `frontend/src/i18n/locales/analytics.ts` 的 zh-CN/en-US/ja-JP/ko-KR 四语言新增 `analytics.weekly_recovery_triggered` 与 `analytics.weekly_recovery_success_rate`。
5. 新增测试 `backend/tasks/tests/test_analytics_views.py`，用 `APIClient` + `force_authenticate` 命中真实 `/api/v2/analytics/weekly-report/` 与 `/api/v2/analytics/task-stats/`，断言 recovery 字段。
