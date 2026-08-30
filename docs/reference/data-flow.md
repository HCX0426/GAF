---
maintainer: derived-manual
source: backend/, agent/, frontend/, desktop/
load_when: [必读]
priority: high
symptom:
- kb:data-flow
- data-pipeline
- end-to-end-flow
- system-architecture
solution: 4 层架构 (desktop + frontend + backend + agent) 数据流图 + 3 主路径 (任务执行 / 设备操作 / 监控)
related_files:
- docs/architecture/overview.md
- docs/architecture/cross-cutting/concurrency-design.md
- docs/architecture/cross-cutting/dispatch-flow.md
- docs/business/tasks/pipeline-design.md
- backend/protocol/consumers.py
- backend/protocol/routing.py
- backend/agents/routing.py
- backend/notifications/routing.py
- worker/src/client/connection.py
- worker/src/platforms/windows/
- worker/src/devices/adb/
created_by: AI
generated: 2026-06-16
auto_updated: 2026-08-01
last_manual_edit: 2026-08-01
---

# GAF Data Flow (v9.5 必读)

> **v9.5 (2026-08-01, N197)** — 更新: 单Agent多窗口架构澄清、调试目录结构归一化、URL 拼接归一化 (env-hardrules-contextual.md N197)
> **v9.4 (2026-07-19, spec-39 Phase 1)** — 全文重写, 同步 C-038 (gaf_ai/gaf_core 重命名) + C-045 (AuditLog 114 接入点) + C-048 (legacy /ws/agents/ 删除) + C-063 (ExecutionConsumer/ScreenshotStreamConsumer 删除) + C-025 (trace_middleware → tracing/middleware)
> **元规则**: 任何修改 `backend/` / `agent/` / `frontend/` / `protocol/` 都可能影响 .ai-memory/
> 4 层架构: `Desktop (Electron)` → `Frontend (React)` → `Backend (Django)` → `Agent (Python)`

## 0. 全局架构图

```
┌──────────────────────────────────────────────────────────────────┐
│  Desktop (Electron)            main: window/tray/updater        │
│  desktop/src/main/index.ts     IPC ↕ Frontend                    │
└──────────────────────────────────────────────────────────────────┘
                                 ↕ HTTP / WebSocket
┌──────────────────────────────────────────────────────────────────┐
│  Frontend (React 19.2 + Vite)                                       │
│  frontend/src/                 90+ pages + 27 api client         │
│                                /api/v2/*  ↕ Backend               │
└──────────────────────────────────────────────────────────────────┘
                                 ↕ /api/v2/* + /ws/protocol/agents/
┌──────────────────────────────────────────────────────────────────┐
│  Backend (Django 5.2 + DRF + Channels)                            │
│  backend/                      22 app + 23 urls.py                │
│                                REST + 5 active WebSocket routes  │
└──────────────────────────────────────────────────────────────────┘
                                 ↕ /ws/protocol/agents/ (WebSocket)
┌──────────────────────────────────────────────────────────────────┐
│  Agent (Python)                  standalone process               │
│  worker/src/                      **单 Agent 多窗口**              │
│                                - 一台机器 = 一个 Agent 进程       │
│                                - 每个可控窗口 = 一个 Device       │
│                                - 模拟器窗口 (ADB) 可并行          │
│                                - 非模拟器窗口 (Win32) 串行        │
│                                  37 pipeline node types            │
│                                Windows PC + Android emulator     │
└──────────────────────────────────────────────────────────────────┘

**17 backend apps** (按 config/urls.py include 顺序):
accounts, agents (含 /devices/ + /device-groups/), tasks, resources, monitors,
skills, notifications, debug, qa, plugins, protocol, metrics, gamestate, pipeline,
scheduler, executions (+ analytics_urls), settings, search, gaf_ai, i18n, tracing, gaf_core

**5 active WebSocket routes** (backend/config/asgi.py):
- `ws/protocol/agents/` — WorkerConsumer (backend ↔ agent 双向通信)
- `ws/dashboard/` — FrontendConsumer (后端推送任务/截图/执行步骤事件给前端)
- `ws/logs/` — LogStreamConsumer (统一日志中心实时推送)
- `ws/notifications/` — NotificationConsumer (告警/通知推送)
- `ws/devices/<device_id>/adb-logs/` — AdbLogStreamConsumer (ADB logcat 实时流)

> **已删除 (C-048/C-063)**: `/ws/agents/` legacy (2026-07-19 spec-29c)、`/ws/executions/<id>/` ExecutionConsumer (spec-35 Phase 4.1)、`/ws/devices/<id>/screenshot-stream/` ScreenshotStreamConsumer (spec-35 Phase 4.2 — 前端通过 `/ws/dashboard/` 收 screenshot_frame)

## 1. 三大主路径

### 1.1 路径 A: 任务执行 (核心闭环)

```
User (Frontend)
  │ 执行任务 → POST /api/v2/tasks/{id}/execute/（或 Pipeline: /pipeline/pipelines/{id}/execute/、TaskChain: /pipeline/task-chains/{id}/execute/）
  ▼
Backend (tasks app)
  │ TaskService.dispatch (execute_task) → TaskExecution.create(PENDING)
  │ → transaction.on_commit → dispatch_task.delay
  ▼
Celery Worker (dispatch_task 统一入口)
  │ 设备忙/并发/能力检查 → resolve_online_agent 或 AgentSelector.select
  │   （TaskChain 节点用 force_agent_id 固定链 Agent, B1 2026-08-27）
  │ → 写 S1 dispatch_sent_at 快照 → group_send task.assign
  ▼
Backend WorkerConsumer.send() → Agent
  │ 14 字段 task.dispatch frame (+ device_info / resource_pack)
  │ ws://host/ws/protocol/agents/
  ▼
Agent (Python)
  │ connection.py 收 frame → handler.py 路由 task.dispatch
  │ → pipeline_engine.py 执行 pipeline (37 节点类型, 见 auto-kb/pipeline-nodes.md)
  │ → 每步 task.progress 上报 (含 step_index)
  │ → 完成 task.result 上报
  ▼
Backend 写 execution state + AuditLog 持久化 → gaf_core/mixins/audit.py (114 接入点, C-045)
Frontend /ws/dashboard/ 收 execution_step_update + screenshot_frame
```

**关键文件**:
- `backend/tasks/views.py: TaskViewSet`
- `backend/scheduler/engine.py`
- `backend/protocol/consumers.py: WorkerConsumer.send`
- `backend/gaf_core/mixins/audit.py: AuditMixin` (C-045, 114 接入点)
- `worker/src/engine/pipeline_engine.py: PipelineEngine.execute`
- `worker/src/client/handler.py: handle_task_dispatch`

### 1.2 路径 B: 设备操作 (远程 click/input)

```
User (Frontend 设备中心页)
  │ 点击 → POST /api/v2/devices/<id>/click/
  ▼
Backend (agents app)
  │ DeviceClickView → 选对应 Agent 的 channel_name
  │ WorkerConsumer.send(device.action)
  ▼
Agent
  │ handler.py: handle_device_action
  │ → Device.click(x, y) / Device.input(text)
  │ → device.action_result 上报
  ▼
Backend 转发到 Frontend (/ws/dashboard/)
  │ 前端 toast 提示成功/失败
```

**关键文件**:
- `backend/agents/views.py: DeviceClickView` / `DeviceInputView`
- `backend/agents/urls.py: devices/<id>/click/`
- `worker/src/devices/base.py: Device.click` / `Device.input`
- 平台分发 (实际代码, 2026-07-19):
  - `worker/src/platforms/windows/` — Windows PC 控制 (discovery/screenshot/input, agent 侧)
  - `worker/src/devices/adb/` — Android 模拟器控制 (ADB, agent 侧)
  - `backend/device_bridge/platforms/{windows,macos,linux}/` — backend 侧跨平台抽象层 (P-028 ✅, 纯 Python 包非 Django app, 不在 INSTALLED_APPS)

### 1.3 路径 C: 监控与告警

```
Agent (持续)
  │ 资源监控 → monitor/manager.py
  │ CPU > 90% 或 memory > 80% → event.alert 上报
  ▼
Backend (monitors + notifications)
  │ 写 monitor/models.py 记录
  │ → AlertRule 匹配 → notifications/urls.py 发通知
  ▼
Frontend Dashboard
  │ /api/v2/monitors/ + /api/v2/analytics/trend/
  │ → TrendChart 渲染 + 邮件/Webhook
  │ /ws/notifications/ 实时推送告警
```

## 2. 认证 / 鉴权 数据流

```
User 登录 (Frontend Login 页)
  │ POST /api/v2/accounts/login/ → JWT access + refresh
  ▼
Backend (accounts app)
  │ accounts/views.py: login → JWT encode (HS256)
  │ 存 refresh token → accounts/models.py: RefreshToken
  │ AuditMixin.perform_create → accounts/models.py: AuditLog (C-045)
  ▼
Frontend 存 access (memory) + refresh (httpOnly cookie)
  │ 后续请求 Header: Authorization: Bearer <access>
  │ 401 → POST /api/v2/accounts/refresh/
  ▼
Backend (accounts app)
  │ accounts/views.py: refresh → 验签 + 滚动 access
```

**Agent 鉴权 (不同路径)**:
```
Agent 启动 (Python)
  │ WebSocket connect: ws://host/ws/protocol/agents/?token=<JWT>
  ▼
Backend (protocol/middleware.py)
  │ TokenAuthMiddleware 解析 token
  │ → AgentGroupMiddleware 加入 agent_<id> group
  │ → QuotaGuardMiddleware 检查超额
  ▼
WorkerConsumer.connect()
  │ agent_id 绑定到 self.agent_id
  │ → 后续消息走 message routing
```

## 3. 异步与消息队列

```
触发方式                              队列                       消费者
─────────────────────────────         ──────                     ──────
Celery beat (周期)                    Redis/RabbitMQ             celery worker
tasks/beat.py                                                        │
                                                                       │
Django signals (model 变更)           Celery                        tasks.tasks
accounts/signals.py → 邮件/Webhook                                     │
                                                                       │
WebSocket (实时)                       Channels (in-memory)         WorkerConsumer
protocol/consumers.py                                                 │
                                                                       │
SSE 推送 (进度)                        StreamingHttpResponse       Frontend hook
executions/views.py: progress_view                                  useSSEStream

Celery 异步 AI 分析 (C-031)
gaf_ai/tasks.py: run_agent_analysis_task → LangGraph ReAct Agent
gaf_ai/agent/views.py: agent_analyze_view → .delay() + 202
gaf_ai/agent/views.py: agent_session_status_view → 轮询查 PENDING/RUNNING/COMPLETED/FAILED
```

## 4. 持久化与数据存储

```
┌──────────────────────────────────────────────────────────────────┐
│  SQLite + WAL (主库)           backend/*/models.py                 │
│  - 业务数据: 任务/设备/账号/审计/告警/通知/链/管                 │
│  - AuditLog (accounts/models.py:454) — C-045, 114 接入点          │
│  - LogEntry (gaf_core/models.py:14) — 统一日志中心                │
│  - 22 个 app 共 ~60+ 表                                          │
└──────────────────────────────────────────────────────────────────┘
                                 ↕ migrations
┌──────────────────────────────────────────────────────────────────┐
│  Redis (缓存 + 队列)           CELERY_BROKER_URL                 │
│  - Celery 任务队列                                               │
│  - Channels layer (WebSocket group)                              │
│  - Session cache                                                 │
└──────────────────────────────────────────────────────────────────┘
                                 ↕
┌──────────────────────────────────────────────────────────────────┐
│  文件系统 (本地)                                                 │
│  - resources/ (图标/模板)                                        │
│  - recordings/ (录制)                                            │
│  - logs/ (agent + backend + frontend)                           │
│  - debug/ (调试日志 — 三端归一化五层结构)                        │
│    └── YYYYMMDD/agent/<pipeline>/HH/structured.jsonl            │
│    └── YYYYMMDD/backend/tasks/<pipeline>/HH/execution.jsonl     │
│    └── YYYYMMDD/frontend/<page_slug>/HH/console.jsonl           │
│  - sqlite (开发 DB)                                              │
└──────────────────────────────────────────────────────────────────┘
                                 ↕
┌──────────────────────────────────────────────────────────────────┐
│  Object Storage (S3 兼容)                                        │
│  - 备份归档                                                      │
│  - 资源包 (跨实例共享)                                          │
└──────────────────────────────────────────────────────────────────┘
```

## 5. 跨层追踪 (Trace ID)

```
Frontend 生成 trace_id (UUID)
  │ 写入所有 HTTP request header
  ▼
Backend (tracing/middleware.py)
  │ context var 注入 Django request (C-025, 2026-07-09 从 tasks/trace_middleware.py 迁移)
  │ → 所有 SQL query 携带 trace_id
  │ → WebSocket frame 的 trace_id 一致
  ▼
Agent (connection.py)
  │ 收到 frame 的 trace_id → 注入到所有 log
  │ → ocr / click 等节点返回的 AutoResult 带 trace_id
  ▼
tracing app (backend/gaf_core/tracing/)
  │ 收集全链路 (backend + agent)
  │ GET /api/v2/tracing/<trace_id>/
  ▼
Frontend 渲染链路追踪图
```

## 6. 错误处理与重试

```
节点失败 → AutoResult(success=False, error_code=...)
  │
  ├─ on_error=stop → 终止 pipeline
  │  → task.result 上报
  │  → 写 execution log + AuditLog (C-045)
  │  → User 看前端错误页
  │
  ├─ on_error=continue → 跳过,继续下一个节点
  │
  └─ on_error=goto:<label> → 跳转到 label 节点
     └─ 配合 retry_count 字段 (失败 N 次后才触发)
```

**重试机制** (`worker/src/core/retry_decorator.py`):
- 节点级: `retry_count` 字段
- 任务级: `tasks/tasks.py:dispatch_task` Celery 重试 (max_retries=3, countdown=30s) + `tasks/services/monitor_service.py:check_pending_timeout` PENDING 超时重试
- 全局: `celery` 任务 auto-retry (3 次, 指数退避)
- Debug 模式 LLM auto-heal (C-030): `worker/src/ai/llm_client.py: diagnose_failure()` 解析 DIAGNOSIS:/FIX: 格式, 不抛异常

## 7. 部署 / 网络拓扑

```
生产环境 (docker-compose)

[nginx:80/443]
  │
  ├─ /api/v2/*  → backend:8000 (gunicorn + daphne)
  ├─ /ws/protocol/agents/* → backend:8000 (daphne)
  ├─ /ws/dashboard/ → backend:8000 (daphne)
  ├─ /ws/logs/ → backend:8000 (daphne)
  ├─ /ws/notifications/ → backend:8000 (daphne)
  ├─ /ws/devices/<id>/adb-logs/ → backend:8000 (daphne)
  ├─ / → frontend:80 (静态 + Vite preview)
  └─ /admin/ → backend:8000

backend:8000
  ├─ gunicorn workers (HTTP)
  └─ daphne workers (WebSocket)

celery worker (1+ 进程)
celery beat (1 进程, 周期任务)

agent (独立 Python 进程, 可多个)
  └─ 与 backend 通过 /ws/protocol/agents/ 通信

[SQLite:db.sqlite3]
[Redis:6379]
[S3 / MinIO:9000]
```

## 8. AI 速查决策树

```
查数据流? (load data-flow.md)
├─ 任务从哪创建 → 路径 A → tasks/views.py: TaskViewSet
├─ 设备怎么远程操作 → 路径 B → agents/views.py: DeviceClickView
├─ 监控怎么上报 → 路径 C → monitors/views.py
├─ 鉴权走哪 → 章节 2 (Frontend JWT / Agent WS token)
├─ 异步任务在哪 → 章节 3 (Celery / Channels / SSE)
├─ 数据存哪 → 章节 4 (SQLite / Redis / FS / S3)
├─ AuditLog 怎么写 → gaf_core/mixins/audit.py: AuditMixin (C-045)
├─ 调试日志在哪 → debug/<YYYYMMDD>/{agent,backend,frontend}/.../HH/
├─ URL 版本号在哪改 → .env GAF_API_PREFIX (N197, 见 env-hardrules-contextual.md)
├─ 路由路径段在哪改 → .env GAF_ROUTE_* 变量 (N197, 见 env-hardrules-contextual.md)
└─ 错误怎么处理 → 章节 6 (节点 on_error / 任务 retry / LLM auto-heal)

架构修改? (必读本文件 + 通知)
⚠️ 改 backend/*/models.py → 加 migration + 通知 frontend/types
⚠️ 改 worker/src/* 协议 → 通知 backend + 升 version-compat
⚠️ 改 protocol/constants.py → 加 14 消息类型需同步 5 处
⚠️ 改 backend app 内 ViewSet → 加 AuditMixin 自动接入 AuditLog (C-045)
⚠️ 改 API 路径 / URL 版本号 → 改 .env GAF_API_PREFIX + GAF_ROUTE_* (N197)

## 9. 已知问题与状态标记

- **N91** pre-commit hook 失败处理 (active, 见 `meta/failure-modes.md` N## 索引)
- **macOS/Linux 路径漂移** (新登记 TD-281, 2026-07-19):
  - 多份 docs 引用 `worker/src/devices/{macos,linux}/` 或 `worker/src/platforms/{macos,linux}/`, 但实际路径是 `backend/device_bridge/platforms/{macos,linux}/` (P-028 ✅ 已实现)
  - 影响: AI 按文档去找代码会找不到; tech-stack.md §4 L175-177 + GAF-optimal-solution.md L105-106 路径需校正
  - 修复: spec-39 Phase 4 + Phase 8 联动校正路径 (P-028 ✅ 状态保留)
- **C-063 ExecutionConsumer/ScreenshotStreamConsumer 已删除** (2026-07-19 spec-35 Phase 4.1/4.2):
  - 前端通过 `/ws/dashboard/` 收 screenshot_frame + execution_step_update, 不再走单独 stream
  - executions/routing.py + executions/consumers.py 已删
- **C-048 legacy /ws/agents/ 已删除** (2026-07-19 spec-29c): 改走 `/ws/protocol/agents/`
