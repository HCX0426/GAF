---
summary: TD-389 — 恢复（recovery）指标纳入 analytics 聚合
applies_to: ['backend', 'frontend']
applies_to_code_paths:
  - backend/executions/views.py
  - frontend/src/api/ops.ts
  - frontend/src/pages/Ops/AnalyticsDashboard.tsx
last_updated: 2026-08-23
---

# TD-389: 恢复指标纳入 analytics 聚合

> 来源: TD-386 代码核查残留（原 TD-386 误判"整体缺失"，核查后仅此切片真实缺）。
> 优先级: P3（低优先，纯增量，不加字段、不碰模型）。
> 修正: 前端真实消费的是 `executions/views.py` 的 `weekly_report_view` / `task_stats_view`
> （挂载于 `/api/v2/analytics/`），而非 `tasks/analytics_views.py`（legacy，未被前端使用）。
> 故 recovery 指标落在 executions/views.py，并顺带补齐前端 `WeeklyReport` 期望的扁平字段
> （此前该卡片取值为 undefined，因后端返回 `summary` 包装结构）。

## 阶段状态表

| 阶段 | 状态 | 完成时间 | commit | 验收 evidence |
|------|------|----------|--------|---------------|
| P1 后端聚合 (task_stats_view + weekly_report_view, executions) | ✅ 完成 | 2026-08-23 | - | 端点返回 recovery 三字段 |
| P2 前端展示 (ops.ts/本地接口 + Dashboard 卡片) | ✅ 完成 | 2026-08-23 | - | `/ops/analytics` 显示恢复指标 |
| P3 测试 + lint + 提交 | ✅ 完成 | 2026-08-23 | - | pytest + ruff + tsc 通过 |

## 背景

`TaskExecution` 已有 `recovery_attempts` / `recovery_layer` 字段（5 层异常恢复机制产物），
但 `tasks/analytics_views.py` 与 `AnalyticsDashboard.tsx` 全量 grep `recovery` 零命中——
"多少次执行触发了恢复 / 平均恢复尝试次数 / 恢复后成功率"从未被聚合或展示。
这恰好能量化 GAF 最自豪的"5 层恢复"是否真有效。

## 修复方案

### 后端 (`backend/executions/views.py`)
在 `task_stats_view` 与 `weekly_report_view` 两个聚合视图中，基于已有 `executions` queryset 增加：

- `recovery_triggered_count` = `executions.filter(recovery_attempts__gt=0).count()`
- `avg_recovery_attempts` = `executions.aggregate(avg=Avg('recovery_attempts'))['avg'] or 0`（保留 2 位）
- `recovery_success_rate` = 触发过恢复且最终 `SUCCESS` 的占比（无触发样本时返回 `None`）

### 前端
- `api/ops.ts` 的 `WeeklyReport` 接口增加三字段。
- `AnalyticsDashboard.tsx` 在周报卡片内新增恢复指标展示（触发次数 + 恢复成功率）。

## 验证标准
- `GET /api/v2/analytics/task-stats/?days=30` 与 `weekly-report/` 返回 recovery 三字段
- 前端 `/ops/analytics` 周报卡片显示恢复触发次数与恢复成功率
- 新增 `test_analytics_views.py` 覆盖 recovery 字段非空（构造触发恢复的执行）
- ruff + 相关 pytest 通过
