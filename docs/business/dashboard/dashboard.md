---
summary: 工作台 — 概览统计 / Agent 健康 / 快捷操作 / 趋势图表
applies_to: ['frontend', 'backend', 'design']
key_decisions:
  - 无独立 dashboard 后端 app, 数据跨 6 个后端 app 聚合
  - 9 个 Widget 可拖拽布局, localStorage 持久化
  - Agent 健康 WebSocket 实时推送 (agent_heartbeat / agent_status)
  - 4 项顶部统计: 在线 Agent / 运行中任务 / 今日执行 / 成功率
last_updated: 2026-07-29
---

# 工作台

> 模块路由 `/dashboard`，对应前端侧边栏"工作台"。系统首页，聚合显示 Agent 健康、任务执行统计、趋势、告警、快捷操作。

## 1. 整体架构

**无独立 dashboard 后端 app**，数据来自 6 个后端 app 聚合：

| 后端 app | 提供能力 |
|---|---|
| `executions` | daily-report / trend / step-heatmap / agent-performance / weekly-report / task-stats / unattended-logs |
| `agents` | Agent 列表 / Device 列表 + device_stats |
| `tasks` | 任务列表 / task-executions 列表 |
| `scheduler` | today_schedule（今日时间线） |
| `monitors` | fetchMonitorEvents（告警摘要） |
| `gaf_ai` | execution_analysis 调用的 LLM |

## 2. 前端页面

目录：[frontend/src/pages/Dashboard/](file:///d:/code/GAF/frontend/src/pages/Dashboard/)

### 2.1 主页 index.tsx
- **布局**: 纵向流式 + 可拖拽 Widget 卡片，顺序持久化到 `localStorage` key `gaf_dashboard_widgets`
- **并行数据加载**: `Promise.all([fetchAgents, fetchTasks, getDashboardDailyReport, fetchExecutions(running), fetchExecutions(recent 5)])`

### 2.2 顶部统计卡片（task_overview Widget）
4 项 Statistic：
- 在线 Agent 数（`agents.filter(a => a.status !== 'offline').length`）
- 运行中任务数（`fetchExecutions({ status: 'running' })`）
- 今日执行次数（`getDashboardDailyReport().overview.total_executions`）
- 成功率（`success_rate`，>=80% 绿色否则红色）

### 2.3 默认 Widget 布局（9 个）
| Widget | 数据源 | 用途 |
|---|---|---|
| `task_overview` | daily-report + executions | 顶部 4 统计卡片 |
| `progress_ring` | `getDashboardDailyReport` | 执行进度环 |
| `device_status` | `WorkerHealthPanel` | Worker 健康面板 |
| `execution_queue` | `@/api/scheduler` `fetchTodaySchedule` | 执行队列预览 |
| `recent_executions` | `fetchExecutions(page_size=5)` | 最近 5 条执行记录 |
| `trend_chart` | `@/api/ops` `fetchAnalyticsTrend` | 趋势图表 |
| `alert_summary` | `@/api/monitors` `fetchMonitorEvents` | 告警摘要 |
| `unattended_control` | `@/api/misc` | 无人值守控制 |
| `quick_actions` | 本地 | 快捷操作按钮 |

页面顶部还有 `<TodaySchedule />`（今日时间线）。

## 3. WorkerHealthPanel

文件：[WorkerHealthPanel.tsx](file:///d:/code/GAF/frontend/src/pages/Dashboard/WorkerHealthPanel.tsx)

### 数据源
- `useDeviceStore` 的 `agents` + `devices`
- 初始加载 + 60s 兜底轮询
- **WebSocket 实时推送**: 订阅 `agent_heartbeat` + `agent_status`，5 秒节流后触发 refresh

### 显示内容
按状态排序的 Agent 列表（online → busy → idle → offline），每个 AgentCard 显示：
- hostname / agent_id + 绑定 device.name
- 状态 Tag（online 绿 / offline 灰 / busy 蓝 / idle 黄）
- CPU 进度条（>90% 红）、内存进度条（>90% 红）、FPS 数值（<10 红）
- 异常时整卡边框 + 背景变红
- last_heartbeat 时间

### 异常判定
`isAbnormal`: CPU > 90 OR 内存 > 90 OR (FPS > 0 AND FPS < 10)

### 数据字段优先级
- CPU: `device.device_stats.cpu` → `agent.cpu_usage`
- Memory: `device.device_stats.memory` → `agent.memory_usage`
- FPS: `device.device_stats.fps` → `agent.screenshot_fps` → `device.screenshot_fps`

## 4. QuickActions

文件：[QuickActions.tsx](file:///d:/code/GAF/frontend/src/pages/Dashboard/QuickActions.tsx)

4 个快捷按钮 + 已启用任务展示：
1. **创建任务** → `/tasks`
2. **从市场导入** → `/tasks/marketplace`
3. **设备管理** → `/devices`
4. **快速执行** → 调 `useTaskStore.executeTask(enabledTasks[0].id)`，无启用任务时 `message.warning`

已启用任务列表：前 5 个 `is_enabled === true` 的任务。

## 5. Analytics API 端点

前缀 `/api/v2/analytics/`，详见 [executions/analytics_urls.py](file:///d:/code/GAF/backend/executions/analytics_urls.py)。所有端点需 `IsAuthenticated` + `view` 权限。

| 路径 | 方法 | 返回 |
|---|---|---|
| `trend/` | GET | `{days, period_start, period_end, trend: [{date, execution_count, success_rate, avg_duration}]}`，支持 `?days=N`（默认 7） |
| `step-heatmap/` | GET | `{results: [{step_name, total, success_rate, avg_duration}]}`，前 20 |
| `agent-performance/` | GET | `{results: [{agent_id, agent_name, device_name, total_executions, success_rate, last_seen}]}`，前 10 |
| `weekly-report/` | GET | `{week_start, week_end, summary, daily_breakdown: [{date, weekday, total, success, failed}]}` |
| `task-stats/` | GET | `{results: [{task_id, task_name, mode, is_enabled, total_executions, success_rate, last_execution}]}`，前 20 |

## 6. executions app 其他端点

前缀 `/api/v2/executions/`，详见 [executions/views.py](file:///d:/code/GAF/backend/executions/views.py)。executions app **无自有 model**，全部通过 `apps.get_model('tasks', 'TaskExecution')` 读取。

| 路径 | 方法 | 用途 |
|---|---|---|
| `<pk>/steps/` | GET | Pipeline 步骤详情列表 |
| `<pk>/intervene/` | POST | 手动干预（pause/resume/skip_step/fail_step/cancel） |
| `<pk>/analysis/` | GET | AI 分析执行记录（调 `gaf_ai.llm_service.call_llm`） |
| `daily-report/` | GET | 每日执行报告（admin 看全平台，其他看自己） |
| `unattended-logs/` | GET | 无人值守日志（从 `scheduler.RecoveryLog` 查询） |

## 7. 已知限制

- `trend_view` 在 `executions/urls.py` 和 `analytics_urls.py` 重复注册，前者实际不被前端调用
- `task_stats_view` 的 `mode` 字段实际取 `task.task_type` 回退到 `'manual'`
- WorkerHealthPanel **不调用** `analytics/agent-performance/`（前者实时状态，后者历史统计，互补不重叠）
