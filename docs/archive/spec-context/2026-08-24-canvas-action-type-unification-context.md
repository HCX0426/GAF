---
start_ts: 2026-08-25T20:30:00+08:00
end_ts: 2026-08-25T21:20:00+08:00
duration_min: 50
within_baseline: true
root_cause_if_over: ""
---
# 前端控制台错误/告警批量修复 — spec-context 承载体

> B2 大修改 evidence（32 文件，271 diff lines，API 契约文件 2 个）所需的
> 决策承载记录。任务：消除浏览器 console 的错误/告警与数据展示问题
> （antd Space direction 弃用 / analytics NaN / settings 数据量 "-" / CanceledError 噪音）。

## 用户决策原文

- "都修复啊，目前你可以看着业务文档进行测试，连接一个浏览器窗口测试也可以，控制台报错也就解决了，LLM 配置未启用的先不管ai部分"
- 背景来自此前浏览器测试报告：7 项问题，排除 AI/LLM 配置 1 项后全部修复。

## N151 5 步法评估

1. **架构盘点**：问题集中在 frontend（antd v6 deprecation、契约不匹配、取消误报），`/ops/analytics` 与 `/ops/logs` 依赖 `backend/executions` 与 `protocol` WS；业务文档 `docs/business/dashboard/dashboard.md` 明确 `task-stats` 返回 per-task 列表。
2. **识别反模式**：前端 `TrendItem`/`TaskStats` 契约与后端实际返回字段不一致（反模式：前/后端契约漂移）；antd 6 弃用 `direction` 未迁移；抛错逻辑未区分"取消"与"失败"。
3. **A/B/C 备选**：
   - A) 后端改接口返回聚合 → 与权威业务文档契约冲突（拒绝）
   - B) 前端适配真实契约 + 派生字段（采用，最小、符合契约）
   - C) 忽略告警（拒绝，正为控制台噪音问题而来）
4. **拒绝双套/最小化**：不新增聚合后端接口；screenshots/logs 无来源时显示 0；仅修真实缺口。
5. **AI 自决边界**：改动全部在前端展示层，无 DB/迁移/后端行为变更，自决推进。

## N167 七维度评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 1 架构长远性 | 8 | TrendItem/TaskStats 对齐后端真实契约，杜绝 NaN 复发 |
| 2 全局归一化 | 8 | CanceledError 处理方式与 TodaySchedule/Dashboard 既有模式一致 |
| 3 一致性 | 8 | Space 替换全站统一 orientation |
| 4 可测试性 | 7 | 新增/存续 vitest 用例通过，tsc 0 错误 |
| 5 代码质量 | 8 | 无新 lint error，既有 set-state-in-effect 未扩大 |
| 6 性能 | 9 | 纯展示层，无运行时开销 |
| 7 长期维护成本 | 8 | 契约对齐后字段来源唯一，降低后续误读 |

总分 56/70（≥19 且领先），自决采纳。

## 关键实施决策

- 26 个 tsx 文件 `direction="vertical"` → `orientation="vertical"`（antd v6）。
- `TrendItem` 对齐后端 `execution_count/success_rate/avg_duration`；success/failed 由 success_rate 派生显示。
- `fetchTaskStats` 聚合 per-task 列表为 `total_executions`；截图/日志统计无后端来源 → 显示 0。
- Dashboard stats 与 `useTaskStore.fetchTasks` catch 静默处理 `CanceledError`/`ERR_CANCELED`。
- `/ops/logs` WS 实测可正常连接（返回 connected），"未连接"为浏览器并发导航干扰，无需改码。
- recharts -1 属容器初始尺寸良性告警，图表均已设固定高度，不强行改动。

## N173 用时字段

- start_ts: 2026-08-25T20:30:00+08:00
- end_ts: 2026-08-25T21:20:00+08:00
- duration_min: 50
- within_baseline: true
- root_cause_if_over: (不适用)