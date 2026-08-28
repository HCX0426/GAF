---
maintainer: manual
source: GAF/.ai-memory/evidence/2026-08-25-frontend-console-fixes/
created_by: AI
last_updated: 2026-08-25
---
## Problem（症状 / 触发条件）

控制台（browser console）存在多项错误与警告：antd v6 将 `Space.direction` 废弃导致全站 26 个文件触发 "direction is deprecated" 警告；`/ops/analytics` 因前端 `TrendItem` 使用后端不存在的 `total/success/failed` 字段，在无执行数据时 reduce 得 NaN（页面显示 NaN）；`/system/settings` 数据清理页因 `/analytics/task-stats/` 返回按任务列表而非聚合对象，数据量显示 "-"；Dashboard 与任务列表在导航/卸载时 axios 取消会误报 `CanceledError`。影响：浏览器控制台被噪音淹没，analytics 数据展示错误。

## Solution（解决步骤）

1. `frontend/src` 全量把 antd `direction="vertical"` 替换为 `orientation="vertical"`（26 个 tsx 文件）。
2. `frontend/src/api/ops.ts` 修正 `TrendItem` 为后端真实字段 `{date, execution_count, success_rate, avg_duration}`，`AnalyticsDashboard.tsx`/`TrendChart.tsx` 按 execution_count + success_rate 派生成功/失败数。
3. `frontend/src/api/settings.ts` 的 `fetchTaskStats` 改为聚合 `/analytics/task-stats/` 返回的 per-task 列表为 `total_executions`。
4. `Dashboard/index.tsx` 与 `stores/useTaskStore.ts` 的 catch 增加 `CanceledError`/`ERR_CANCELED` 静默处理。