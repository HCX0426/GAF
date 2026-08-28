---
summary: 已评估不修复 / 无效化的技术债务清单 — ❌ WONTFIX / ❌ INVALIDATED / ❌ EVALUATED 条目 (完整详情)
applies_to: [project]
last_updated: "2026-08-23 (TD-386 EVALUATED 迁移)"
---

# Wontfix / Evaluated Tech Debts

> 本文件包含所有 ❌ WONTFIX / ❌ INVALIDATED / ❌ EVALUATED 状态的技术债务条目。
>
> **来源**：从 `tech-debt-register.md` 拆分而来（2026-07-10）。

---

## TD-386: 业务级评测指标缺失（任务成功率/耗时/恢复率）（❌ EVALUATED）

- **状态**: ❌ EVALUATED（评估后不修，2026-08-22 代码核查）
- **优先级**: 原 P2 → 评估后不修
- **登记时间**: 2026-08-22
- **修复时间**: 2026-08-22 (评估)
- **来源**: 2026-08-22 AI 开发通病对照 GAF 方案分析（meta_audit 会话）
- **原症状/根因/方案**: 见 `git log` 历史修订版——原登记称 GAF 缺端到端业务指标（成功率/耗时/恢复率），`TaskExecution` 缺 duration/retry/recovery 字段。
- **evaluated 理由** (2026-08-22 代码核查):
  1. **指标字段已存在**: `TaskExecution` 已有 `duration`(DurationField) / `recovery_attempts`(int) / `recovery_layer`(int)；`TaskStep` 已有 `retry_count` / `duration`。无需加字段。
  2. **聚合 API 已存在**: `backend/tasks/analytics_views.py` 提供 `task_stats`(success_rate/avg_duration_seconds/common_errors) / `step_heatmap`(步骤耗时) / `trend`(按天) / `weekly_report` / `agent_performance`；路由 `/api/v2/analytics/{task-stats,step-heatmap,trend,weekly-report,agent-performance}/` 均就绪。
  3. **前端看板已存在**: `frontend/src/pages/Ops/AnalyticsDashboard.tsx`(`/ops/analytics`) 已渲染成功率/平均耗时/步骤排行/趋势/周报/Agent 性能卡片。
  4. **结论**: 原登记"缺业务级评测指标"前提不成立——该能力 2026 上半年已交付。唯一未覆盖的是 **recovery 恢复指标聚合**（success_rate/avg_duration 之外），已拆为 TD-389（TD-389 已于 2026-08-23 闭环）。
- **保留方案**: 若需 recovery 维度指标，按 TD-389 落地，不必重做整套 analytics。
- **关联**: TD-389（recovery 指标聚合，已 FIXED）
