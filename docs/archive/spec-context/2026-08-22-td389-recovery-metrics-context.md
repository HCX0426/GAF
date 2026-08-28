# Spec-Context: TD-389 Recovery Metrics into Analytics Aggregation (2026-08-22)

## 用户决策原文
- "TD-389 (P3): recovery 指标纳入 analytics 聚合" — 由 TD-386 代码核查残留拆出（TD-386 原误判 analytics 整体缺失，核查后仅此切片真实缺）
- "直接开 spec 落地 TD-389，提交"（2026-08-22）— 授权直接开 spec、实现并 commit

## N151 5 步法评估
1. **架构盘点**: `TaskExecution` 已含 `recovery_attempts` / `recovery_layer`（5 层恢复机制产物），`TaskStep` 已含 `recovery_layer`。前端 `/ops/analytics` 真实消费的是 `backend/executions/views.py` 的 `weekly_report_view` / `task_stats_view`（挂载 `/api/v2/analytics/`）；`backend/tasks/analytics_views.py` 为 legacy、前端未使用。全局 grep `recovery` 在 analytics 后端 + 前端零命中 → recovery 从未被聚合/展示。
2. **识别反模式**: (a) 误改 legacy `tasks/analytics_views.py`（前端不消费，属"下游 workaround / 双套并存"反模式）; (b) `weekly_report_view` 返回 `summary` 包装结构，而前端 `WeeklyReport` 接口按扁平字段读取 → 卡片取值 undefined（既有契约错位）。
3. **备选方案**: A) 在真实端点 `executions/views.py` 加 recovery + 补齐前端期望的扁平字段（修复卡片契约） B) 仅改 legacy 端点（前端无感，拒绝） C) 只加 weekly_report 不加 task_stats（不完整，拒绝）。
4. **拒绝反模式**: 拒绝 B（双套/无效改动）、C（半途）；选 A（单点真实端点，归一化）。
5. **AI 自决边界**: 纯增量、不加模型字段、不动 schema；recovery 聚合基于已有 queryset；`DurationField` 用 `timedelta`/`float` 双分支防御（SQLite 存微秒浮点），无触发样本时 `recovery_success_rate` 返回 `None`。

## N167 七维度评分
- **架构长远性**: recovery 指标归一化到唯一真实 analytics 端点，无第二套契约 — 4
- **全局归一化**: 前端消费路径与后端返回结构对齐（扁平字段），消除此前 undefined 错位 — 4
- **新旧兼容**: 仅新增字段，旧 `summary`/`daily_breakdown` 保留；前端 `WeeklyReport` 新增 3 字段向后兼容 — 4
- **现有业务完善**: "5 层恢复是否真有效"首次可量化（触发次数/平均尝试/成功率）— 4
- **性能资源优化**: 仅聚合查询（count/aggregate），无 N+1 放大 — 3
- **安全合规加固**: 无涉（只读聚合，沿用 `IsAuthenticated + RoleBasedPermission`）— 2
- **长期维护成本**: recovery 聚合逻辑集中于 2 个视图，语义清晰 — 4
- **总分**: 25（方案 A，≥19 且领先 ≥5 → AI 自决）

## 关键实施决策
- **真实端点定位**: 前端 `fetchWeeklyReport`/`fetchTaskStats` → `/api/v2/analytics/weekly-report/`、`/api/v2/analytics/task-stats/` → `executions/views.py`（非 `tasks/analytics_views.py`）。改动必须落在 `executions/views.py`。
- **契约修复**: `weekly_report_view` 在保留 `summary`/`daily_breakdown` 前提下新增扁平字段 `total_executions`/`success_count`/`failed_count`/`most_executed_task`/`avg_step_duration_ms`/`success_rate` + recovery 三字段，使前端卡片正确渲染（此前因 `summary` 包装而取值 undefined）。
- **recovery 三字段**: `recovery_triggered_count` = `filter(recovery_attempts__gt=0).count()`；`avg_recovery_attempts` = `aggregate(Avg('recovery_attempts'))` 保留 2 位；`recovery_success_rate` = 触发过恢复且最终 `success` 占比，无触发样本返回 `None`。
- **DurationField 防御**: `TaskStep.duration` 为 `DurationField`，过滤/聚合用 `timedelta(0)` 比较并双分支转换（`isinstance(raw, timedelta)` → `total_seconds()*1000`，否则 SQLite 微秒浮点 `/1000`）。
- **前端双接口**: `ops.ts WeeklyReport` 与 `AnalyticsDashboard.tsx` 内联 `WeeklyReport` 接口均需同步新增 recovery 三字段（已两处对齐）；i18n 4 语言（zh-CN/en-US/ja-JP/ko-KR）新增 `weekly_recovery_triggered`/`weekly_recovery_success_rate`。
- **测试**: 新增 `backend/tasks/tests/test_analytics_views.py`（`APIClient` + `force_authenticate`，命中真实 `/api/v2/analytics/*` 端点，响应经 unified-response 包装 → 取 `resp.data['data']`）。

## 已知限制（spec 记录，非本次实现）
- `tasks/analytics_views.py` legacy 端点未同步 recovery（前端不消费，保持单源，避免双套）。
- `avg_step_duration_ms` 在无成功步骤时返回 0.0（合理默认）。

## N173 用时字段
- start_ts: 2026-08-22T10:00:00+08:00
- end_ts: 2026-08-23T15:00:00+08:00
- duration_min: ~累计实现（含端点定位纠偏），分类属中修改（落地阶段），基线 < 15 min 超出因前期误判 legacy 端点需返工
- within_baseline: false（纠偏开销，非异常 — 端点定位属真实核查工作量）
