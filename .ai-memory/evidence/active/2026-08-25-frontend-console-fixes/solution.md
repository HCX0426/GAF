---
maintainer: manual
source: GAF/.ai-memory/evidence/2026-08-25-frontend-console-fixes/
created_by: AI
last_updated: 2026-08-25
---
## Solution（解决步骤）

1. PowerShell 批量替换：`Get-ChildItem frontend/src -Recurse -Include *.tsx,*.ts | Select-String 'direction="vertical"'` → `Replace('direction="vertical"','orientation="vertical"')`，共 26 文件。
2. `frontend/src/api/ops.ts` 的 `TrendItem` 改为 `{date, execution_count, success_rate, avg_duration}`。
3. `frontend/src/pages/Ops/AnalyticsDashboard.tsx` 的 stats 计算与 trend 表格列改用 `execution_count` + `success_rate` 推算 success/failed，删除本地重复的 `TrendItem` 定义并 `import { type TrendItem } from '@/api/ops'`。
4. `frontend/src/components/Dashboard/TrendChart.tsx` 的 chartData 用 `execution_count`/`success_rate` 派生 total/success/failed。
5. `frontend/src/api/settings.ts` 的 `fetchTaskStats` 聚合 `{results:[...]}` 的 per-task `total_executions`。
6. `frontend/src/pages/Dashboard/index.tsx` 与 `frontend/src/stores/useTaskStore.ts` 的 catch 过滤 `CanceledError`/`ERR_CANCELED`。