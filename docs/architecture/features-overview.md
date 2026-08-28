---
summary: GAF 功能总览（按前端侧边栏 9 模块组织，结合后端技术说明）
applies_to: ['features', 'overview', 'onboarding']
applies_to_code_paths:
  - frontend/
  - backend/
  - agent/
  - desktop/
last_updated: 2026-08-08
---

# GAF 功能总览

> **用途**: 以前端侧边栏 9 大模块为索引，说明每个功能"做什么 + 用什么技术"，便于快速理解系统全貌
> **范围**: 前端页面 ↔ 后端 App ↔ Agent 平台层 三层映射
> **配套文档**: 架构与数据模型见 [overview.md](./overview.md)；部署见 [deployment-design.md](./desktop/deployment-design.md)
> **状态**: 截至 2026-08-08 全量盘点有效（架构重构 Phase 1-3 已完成: 服务层/统一 LLM 客户端/设备发现注册表/EventBus/ArchiveService/GafDaemon）

---

## 全局技术栈

| 层 | 技术 | 关键版本 |
|------|------|---------|
| **前端** | React + TypeScript + Vite + Ant Design + Zustand + React Router + React Flow (Pipeline) + WebSocket | React 19.2 / TS 6.0 / Vite 8.0 / Antd 6.4 |
| **后端** | Django + DRF + Celery + Celery Beat + Redis + SQLite + WAL + Channels (Daphne) + drf-spectacular | Django 5.2 / DRF 3.15 / Channels 4.1 / Python 3.11 |
| **Agent** | Python 独立进程，WebSocket 连后端；平台抽象层 `agent/src/platforms/{windows,linux,macos}` + 设备发现注册表 DeviceDiscoveryRegistry + 统一执行引擎 TaskExecutor | Python 3.11 自研 |
| **Desktop** | Electron 桌面应用（封装前端 + 后端 + Agent 一体化分发） | 见 `desktop/` |
| **认证** | SimpleJWT + pyotp (TOTP 2FA) + OAuth2 (GitHub/Google) + AES-256-GCM (游戏账号密码加密) | — |
| **AI** | OpenAI 兼容 LLM (统一客户端 BaseLLMClient) + ChromaDB RAG + LangGraph Agent + WebSocket RPC | — |
| **API** | 统一前缀 `/api/v2/`，OpenAPI 文档 `/api/v2/docs/` | — |

**侧边栏 9 模块**: 工作台 / 游戏档案 / 任务 / 设备 / 资源 / 账户 / 运维 / AI / 系统

---

## 一、工作台 (Dashboard)

**路由**: `/dashboard`  **权限**: `dashboard.view`

总览页，聚合今日进度、设备状态、执行队列、告警摘要、趋势图。支持拖拽卡片自定义布局。

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 今日进度环 | `tasks/analytics/task-stats` | Django ORM 聚合 |
| 设备健康网格 | `monitors/device-health` | Agent 心跳 + 状态聚合 |
| 执行队列预览 | `scheduler/today` + `executions/trend` | Celery Beat 5s 心跳 |
| 告警摘要 | `monitors/alerts` | 告警升级链 (P1→P0) |
| 趋势图 | `tasks/analytics/trend` | 时序聚合 |
| Agent 健康面板 | `agents/` (AgentViewSet) | WebSocket 心跳 10s/30s |
| 无人值守控制 | `scheduler/unattended/*` | start/stop/pause/resume |
| 系统公告 | `notifications/` | Notification model |

---

## 二、游戏档案 (GameProfiles)

**路由**: `/game-profiles` / `/game-profiles/:id`  **权限**: `resource.view`

游戏档案管理，v3 窗口中心化架构的核心枢纽。后端由 `gamestate/` app 承载。

### 2.1 档案列表 `/game-profiles`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 档案 CRUD | `gamestate/game-profiles` (GameProfileViewSet) | 游戏产品定义 |
| 默认任务链 | GameProfile.default_routine (FK→TaskChain) | ✅ v3 新增: 新窗口绑 GameProfile 自动继承 |
| 默认截图方式 | GameProfile.default_screenshot_method | ✅ v3 新增: 'auto' 时由 Device 继承 |
| 默认输入方式 | GameProfile.default_input_method | ✅ v3 新增: 'auto' 时由 Device 继承 |
| 默认控制模式 | GameProfile.default_control_mode | ✅ v3 新增: 'auto' 时由 Device 继承 |
| OCR 语言 | GameProfile.ocr_language | 多语言 OCR |
| 分辨率策略 | GameProfile.resolution_strategy | 适配策略 |

### 2.2 档案详情 `/game-profiles/:id`

5 个 Tab（Spec v3 §2.5.2）。GameProfile 是聚合根，子资源通过 FK `game_profile` 指向它；详情页负责管理绑定/解绑关系，子资源创建在各自独立页面。

1. 任务 (Tasks) — 该档案关联的任务列表。支持绑定/解绑：`+ 添加任务` 按钮打开搜索式弹窗选择未绑定的 Task，操作列`解绑`按钮（Popconfirm 确认）。后端 `gamestate/game-profiles/<id>/bind-task/` + `unbind-task/`。
2. 任务链 (Task Chains) — 该档案关联的 TaskChain 列表。支持绑定/解绑（同上模式）+ 设为默认任务链。后端 `bind-task-chain/` + `unbind-task-chain/`。TaskChain 新建入口在 `/ops/scheduler` 任务链 Tab。
3. 窗口 (Devices) — 该游戏档案绑定的窗口列表。窗口由 Agent 自动注册（Agent 启动时自动发现本机所有 Windows 窗口和模拟器实例），不支持手动绑定/解绑。每行显示窗口名称、类型（windows/emulator）、状态、ADB 序列号、分辨率等信息。支持单设备派发默认 routine。
4. 账户 (Accounts) — 该档案关联的游戏账户列表。支持绑定/解绑（同上模式）。后端 `bind-account/` + `unbind-account/`。
5. 资源包 (Resource Packs) — 只读概览。架构 §3.2：资源包绑定在 GameAccount 上（不绑 GameProfile），支持同游戏不同服务器使用不同资源包。如需调整请到「账户」Tab 修改账户的资源包。

**bind/unbind 端点**（6 个 `@action` POST，`gamestate/game-profiles/<id>/`，需 `manage` 权限）:

| 端点 | 请求体 | 行为 |
|------|--------|------|
| `bind-task/` | `{task_id}` | 将已存在 Task 的 game_profile FK 指向此 profile（若已绑其他 profile 返回 400） |
| `unbind-task/` | `{task_id}` | 将 Task 的 game_profile FK 置 NULL |
| `bind-task-chain/` | `{task_chain_id}` | 同上，针对 TaskChain |
| `unbind-task-chain/` | `{task_chain_id}` | 同上 |
| `bind-account/` | `{account_id}` | 同上，针对 GameAccount |
| `unbind-account/` | `{account_id}` | 同上 |

---

## 三、任务 (Tasks)

**路由**: `/tasks` / `/tasks/pipeline` / `/tasks/recordings` / `/tasks/marketplace`  **权限**: `task.view`

核心模块，管理自动化任务全生命周期。后端由 `tasks/` app 承载（29 个 Model，最大 app）。

### 2.1 任务列表 `/tasks`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 任务 CRUD | `tasks/` (TaskViewSet) | DRF ViewSet + 角色权限 |
| 任务绑定账户 | `tasks/<pk>/bind-accounts` | M2M TaskGameAccount |
| 任务分配设备 | `tasks/<pk>/bind-devices` | TaskDevice 中间表 |
| 任务执行 | `tasks/<pk>/execute` | Celery shared_task 异步 |
| 任务版本 | `tasks/versions` + `<pk>/save-version` | TaskVersion 模型 |
| 任务链 | `pipeline/task-chains` + `pipeline/chain-nodes/check-circular` | 环形检测算法 |
| 批量操作 | `tasks/bulk-action` | DRF action |
| 任务克隆 | `tasks/clone/<pk>/` | 深拷贝 |
| 标签管理 | Task.tags M2M | Tag 模型 |
| 任务文件夹 | `tasks/folders` | 树形 TaskFolder |

### 2.2 Pipeline 编辑器 `/tasks/pipeline`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| Pipeline CRUD | `pipeline/` (PipelineViewSet) | React Flow graph_data JSON |
| 校验 | `pipeline/validate` | `validators.py` |
| 耗时预估 | `pipeline/estimate-time` | `estimator.py` |
| 版本快照 | PipelineSnapshot (PUT 自动创建) | 版本管理 |
| 节点类型 | 18+ 节点（Click/Swipe/Wait/OCR/Template/Loop/SubPipeline 等） | `agent/engine/nodes/` |
| 实时预览 | WebSocket `/ws/dashboard/` 收 `screenshot_frame` 事件 | FrontendConsumer 转发（spec-35 Phase 4.2 C-063 已删除 `ws/devices/<id>/screenshot-stream/` 与 ScreenshotStreamConsumer，前端统一走 dashboard 频道） |
| 录制转 Pipeline | `pipeline/recordings/<pk>/convert-to-pipeline/` | `recording_converter.py` |

### 2.3 录制管理 `/tasks/recordings`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 录制列表 | `tasks/recordings` (RecordingViewSet) | Recording 模型 |
| 录制回放 | Agent WindowsEventCapture (pynput) | 录制 Stepper |
| 转 Pipeline | `pipeline/recordings/<pk>/convert-to-pipeline/` | `recording_converter.py` |
| 标注 Overlay | 前端 RecordingStepper 红色脉冲 | Canvas 渲染 |

### 2.4 任务市场 `/tasks/marketplace`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 市场列表 | `tasks/marketplace` (MarketplaceViewSet) | MarketplaceItem + 评分 |
| 发布/导入 | `marketplace/<pk>/publish` + `import` | DRF action |
| 评分评论 | MarketplaceReview | 评分聚合 |
| Skill 市场 | `skills/market` (SkillMarketViewSet) | SkillMarketItem |

---

## 四、设备 (Devices)

**路由**: `/devices` / `/devices/emulators` / `/devices/windows` / `/devices/adb-logs`  **权限**: `device.view`

设备中心，管理 Agent 与设备。后端由 `agents/` app + `agent/` 平台抽象层共同承载。

### 4.1 设备列表 `/devices`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 设备 CRUD | `agents/devices` (DeviceViewSet) | DRF ViewSet |
| 设备扫描 | `devices/scan/` | ADB + Win32 窗口发现 |
| 设备注册 | `devices/register/` | 3 级查重（serial/同名/同模拟器）|
| 设备截图 | `devices/<id>/screenshot/` | 5 层降级链 |
| 模板匹配 | `agents/<pk>/template-match` | OpenCV cv2.matchTemplate |
| 颜色检测 | `agents/<pk>/color-detect` | 像素采样 |
| 点击/输入 | `agents/<pk>/click` + `/input` | Win32 SendInput / ADB |
| 设备锁 | `agents/<pk>/lock` + `/unlock` | locked_by 字段 + 竞态保护 |
| 兼容性检查 | `devices/check-compatibility/` | 平台能力矩阵 |
| 设备分组 | `device-groups/` (DeviceGroupViewSet) | 树形结构 parent FK |
| Agent 自动关联 | WebSocket `device.sync` | Agent 启动上报 → Server 创建/更新 |

### 4.2 模拟器管理 `/devices/emulators`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 模拟器生命周期 | `devices/emulator-lifecycle/` | LDPlayer/MuMu/BlueStacks 启停 |
| ADB 连接池 | Agent `WorkerPool` | 线程安全单例 + 自动重连 |
| LDPlayer 14 截图 | `ld_opengl.py` v3 IReadPixelsClass | GDI 共享内存 ~26ms/帧 |
| NemuIpc (MuMu) | `nemu_ipc.py` + keepalive | 25s 心跳 + 错误码映射 |

### 4.3 窗口管理 `/devices/windows`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 窗口截图 | BitBlt/PrintWindow/WGC/DXGI | 5 层降级链 (DXGI 支持 per-window crop, Spec E TD-124; backend WGC delegate 到 PrintWindow, TD-125) |
| 子窗口合成 | `SubWindowCompositor` | EnumChildWindows + DPI 修正 + BitBlt |
| 后台输入 | `BackgroundManagedKeyInput` | RegisterHotKey + WM_HOTKEY |
| 3 方法输入 | `input.py` + `input_variants.py` (兼容性查询) | SendInput/PostMessage/PseudoBackground (TD-090 已删除 9 变体死代码; SendInput/PseudoBackground 串行化 Spec C TD-121; PostMessage 使用 client 坐标 Spec B TD-122) |
| Multi-game 模式开关 | `UnattendedControlBar` Segmented + `DeviceForm` 模式选择器约束 | FeatureFlag `unattended_multi_game_mode` + `resolve_device_methods` 白名单降级 (Spec A) |

> **窗口行为差异**：非模拟器窗口（`device_type=windows`）受控制模式限制 — foreground 必须前台、background 可后台操作、pseudo_background 折中。模拟器窗口（`device_type=emulator`）通过 ADB 控制，可最小化运行。详见架构文档 §4.3。

### 4.4 ADB 日志查看器 `/devices/adb-logs`

> **TD-099 fix 3**: 从隐藏路由暴露到侧边栏

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 实时日志流 | WebSocket `ws/devices/<id>/adb-logs/` | AdbLogStreamConsumer |
| 设备选择 | `agents/devices` | 设备列表 |
| 日志过滤 | 前端过滤 | 关键字/级别 |
| 历史日志 | `devices/adb-logs/:deviceId` | 指定设备日志 |

---

## 五、资源 (Resources)

**路由**: `/resources` / `/resources/template-effectiveness` / `/resources/annotation`  **权限**: `resource.view`

资源管理，后端由 `resources/` app 承载。

### 5.1 资源包 `/resources`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 资源包 CRUD | `resources/resource-packs` (ResourcePackViewSet) | name+version 唯一 |
| 深度导入 | YAML→Task + PNG→Template | `import_utils.py` |
| 版本历史 | `resource-packs/<pk>/version-history` | TemplateVersion |
| 一键修复 | `monitors/diagnose` + `fix` | 自动诊断 + 修复 |
| 新建资源包 | 前端表单 → 后端生成目录 + manifest.json | 自动化脚手架 |

### 5.2 模板有效性 `/resources/template-effectiveness`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 模板 CRUD | `resources/templates` | Template + TemplateVersion |
| 批量导入 | `templates/batch-import` | ZIP 解压 |
| 引用检查 | `templates/check-references` | 反向查找 Task 引用 |
| 标签系统 | `resources/tags` (TagViewSet) | M2M Template.tags |
| 有效性统计 | `resources/template-effectiveness` | TemplateEffectiveness 模型 |
| 识别器基准 | `RecognizerBenchmark` | 识别器对比测试 |

### 5.3 模板标注 `/resources/annotation`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 标注 CRUD | `resources/annotations` | TemplateAnnotation |
| COCO 导出 | 增强导出 | COCO 格式 |
| Canvas 标注 | 前端 GafCanvasOverlay | 坐标拾取 + 区域绘制 |

---

## 六、账户 (Accounts)

**路由**: `/accounts/users` / `/accounts/game-accounts`  **权限**: `account.view` + 角色 `admin/operator`

账户管理，后端由 `accounts/` app 承载。

### 6.1 用户管理 `/accounts/users`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 用户 CRUD | `accounts/users` (UserViewSet) | 角色权限 RoleBasedPermission |
| 角色管理 | User.role (viewer/operator/admin) | 三级角色 |
| 2FA (TOTP) | `accounts/auth/2fa/setup/` + `accounts/auth/login-2fa/` | pyotp QR 码 |
| OAuth 登录 | `accounts/auth/oauth/github/` + `accounts/auth/oauth/google/` | OAuth2 |
| 会话管理 | `accounts/auth/sessions/` (UserSessionViewSet) | 活跃会话踢出 |
| 登录历史 | `accounts/login-history` | LoginHistory |
| API Key | `accounts/api-keys` (APIKeyViewSet) | 哈希存储 + IP 白名单 + 权限 JSON |
| 密码强度 | 前端 zxcvbn | 评分 + 改进建议 |

### 6.2 游戏账户 `/accounts/game-accounts`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 游戏账户 CRUD | `accounts/game-accounts` (GameAccountViewSet) | AES-256-GCM 密码加密 |
| 资源包绑定 | GameAccount.resource_pack FK | 换服只改此字段 |
| 账户分组 | `accounts/groups` (GameAccountGroupViewSet) | 分组管理 |
| 轮换规则 | `accounts/rotation-rules` (GameAccountRotationViewSet) | sequential/random/by_stamina |
| 登录方式 | password/qr_scan/token/steam | 多种登录支持 |
| 账户自动处理 | AccountAutoHandler / BatchChecker / LoginTester | 批量操作 |
| BD2 导入 | （已移除） | 后端无对应端点（`accounts/urls.py` 未注册） |

---

## 七、运维 (Ops)

**路由**: `/ops/unattended` / `/ops/executions` / `/ops/scheduler` / `/ops/monitors` / `/ops/analytics` / `/ops/sla` / `/ops/logs`  **权限**: `execution.view` / `schedule.view` / `monitor.view` / `debug.view`

运维监控，跨 4 个后端 app: `scheduler/` + `monitors/` + `executions/` + `debug/`（tracing/metrics 已并入 gaf_core/monitors）。

### 7.1 无人值守 `/ops/unattended`

> 双 tab 架构: Control tab（启停/状态/队列）+ Strategy tab（5 层恢复/夜间模式/频率限制）。归一化后策略从 `/system/settings/unattended-strategy` 合并到此页。

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 启停/暂停/恢复 | `scheduler/unattended/start|stop|pause|resume` | 状态机编排 |
| 预检 | `scheduler/unattended/preflight` | 5 项预检 (device_online/account_valid/resource_ready/agent_connected/schedule_valid) |
| 状态/队列/进度 | `scheduler/unattended/status|queue|progress` | 实时查询 |
| 恢复策略 | UnattendedStrategy (单例) | 5 层恢复 + 夜间模式 + 频率限制 |
| 恢复引擎 | `recovery_engine.py` | ActionChain + Celery |
| 恢复日志 | `scheduler/recovery-logs` | RecoveryLog |
| 预热配置 | `scheduler/warmup-config` | WarmupConfig |
| 自动停止条件 | `scheduler/auto-stop-conditions` | AutoStopCondition |

### 7.2 执行监控 `/ops/executions`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 执行列表 | `tasks/task-executions` (TaskExecutionViewSet) | DRF ViewSet |
| 执行步骤 | `executions/<pk>/steps` | ExecutionStep |
| 手动干预 | `executions/<pk>/intervene` | 暂停/恢复/终止 |
| 每日报告 | `executions/daily-report` | Django ORM 聚合 |
| 无人值守日志 | `executions/unattended-logs` | 日志查询 |
| 执行对比 | 前端 Diff View | 版本对比 |
| 链路追踪 | `gaf_core/tracing` (trace_id) | trace_id 贯穿 (HTTP+WS ContextVar) |

### 7.3 定时任务 `/ops/scheduler`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 定时任务 CRUD | `tasks/scheduled-tasks` (ScheduledTaskViewSet) | Celery Beat |
| 时间窗口 | `scheduler/time-windows` (TimeWindowViewSet) | 时间段调度 |
| 执行计划预览 | `scheduler/execution-plan` | 计划生成 |
| DAG 编辑器 | 前端 DagEditorPage | React Flow |
| 账户轮换 | GameAccountRotation | 4 种策略 |
| Cron 编辑器 | 前端 CronExpressionEditor | Cron 解析 |

### 7.4 监控告警 `/ops/monitors`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 监控规则 | `monitors/rules` (MonitorRuleViewSet) | 规则定义 |
| 监控事件 | `monitors/events` (MonitorEventViewSet) | 事件流 |
| 系统状态 | `monitors/status` | 聚合 (null 容错) |
| 告警摘要 | `monitors/alerts` | 告警分级 |
| 告警历史 | `monitors/alerts/history` | 历史查询 |
| 确认告警 | `monitors/events/<pk>/acknowledge` | DRF action |
| 告警升级 | Celery Beat 300s | P1 30min 未确认 → P0 |
| 静默期 | AlertRule quiet_end | Timer 静默 |
| 恢复日志 | `monitors/recovery-logs` | RecoveryLog Tab |

### 7.5 数据分析 `/ops/analytics`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 趋势分析 | `analytics/trend` | ORM 聚合 |
| 步骤热力图 | `analytics/step-heatmap` | 步骤耗时统计 |
| Agent 性能 | `analytics/agent-performance` | 性能对比 |
| 周报 | `analytics/weekly-report` | 自动生成 |
| 任务统计 | `analytics/task-stats` | 统计聚合 |
| 执行回放 | `/ops/executions/:executionId/replay` | ScreenshotFrame 回放 |

### 7.6 SLA 监控 `/ops/sla`

> **TD-099 fix 3**: 从隐藏路由暴露到侧边栏

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| SLA 指标 | `monitors/sla` (SLAMetricViewSet) | 时序指标 |
| 截图延迟 | SLAMetric (screenshot_latency) | 性能监控 |
| OCR 延迟 | SLAMetric (ocr_latency) | 性能监控 |
| 模板匹配延迟 | SLAMetric (template_match_latency) | 性能监控 |

### 7.7 日志中心 `/ops/logs`

> 归一化后 8 个 Tab 统一日志查看器：原 `/ops/crash-reports` 已合并为第 7 tab；原 `/ops/log-analysis` 归档功能已合并为第 8 tab（LLM 分析迁移到 `/ai/log-analysis`）。

8 个 Tab：
1. 统一时间线 — UNION query across 6 log models via `/api/v2/logs/timeline/`
2. 应用日志 — LogEntry records (DatabaseLogHandler persistence layer)
3. 审计日志 — AuditLog (user actions: login/create/update/delete/...)
4. 恢复日志 — RecoveryLog (5-layer recovery mechanism history)
5. 消息帧日志 — MessageFrameLog (agent ↔ backend protocol frames)
6. LLM 调用日志 — LLMUsageLog (token usage + cost per LLM call)
7. 崩溃报告 — CrashReport (component crashes with stack traces)
8. 日志归档 — DebugLogArchive (ZIP 上传 + 列表 + 过滤，原 DebugPage 功能)

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 统一时间线 | `logs/timeline` | UNION 聚合 |
| 应用日志 | `logs/` | LogEntry + WebSocket `/ws/logs/` |
| 审计日志 | `accounts/audit-logs` | AuditLog |
| 恢复日志 | `scheduler/recovery-logs` | RecoveryLog |
| 消息帧日志 | `protocol/message-frame-logs` | MessageFrameLog |
| LLM 调用日志 | `qa/llm-usage-logs` | LLMUsageLog |
| 崩溃报告 | `debug/crash-reports` | CrashReport |
| 日志归档 | `debug/archives` (DebugLogArchiveViewSet) | ZIP 打包 + 上传 |

---

## 八、AI

**路由**: `/ai/assistant` / `/ai/qa` / `/ai/anomaly` / `/ai/skill-editor` / `/ai/skill-market` / `/ai/log-analysis` / `/ai/config` / `/ai/usage`  **权限**: `ai.view` + 角色 `admin/operator`

AI 模块，跨 2 个后端 app: `gaf_ai/` (C-038 重命名, 2026-07-15, 原 `ai/`; 2026-08-04 并入原 `qa` app) + `skills/`。

### 8.1 AI 助手 `/ai/assistant`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 对话 | `ai/chat` | LLM Service |
| 生成 Pipeline | `ai/generate-pipeline` | LLM + Schema |
| 流式生成 | `ai/generate-pipeline-stream` | SSE |
| 优化 Pipeline | `ai/optimize-pipeline` | LLM 建议 |
| 多轮对话记忆 | 前端 ChatBubble | 上下文管理 |

### 8.2 智能问答 `/ai/qa`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 提问 | `qa/ask` (AskView) | LLM + 上下文构建 |
| 会话历史 | `qa/qa-sessions` (QASessionViewSet) | QASession |
| 知识沉淀 | QASession.is_knowledge | 标记为知识条目 |
| 用量统计 | `qa/llm-usage-logs` (LLMUsageLogViewSet) | Token + 成本 |
| 成本控制 | `cost_control.py` | 配额管理 |

### 8.3 异常发现 `/ai/anomaly`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 异常检测 | `ai/anomaly-detection` | LLM 分析执行日志 |
| 模式识别 | AnomalyPatternPanel | 异常模式聚类 |

### 8.4 Skill 编辑器 `/ai/skill-editor`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 自定义 Skill | `ai/custom-skills` (CustomSkillViewSet) | YAML 编辑 |
| Skill 加载 | `skills/loader.py` | 动态加载 |
| 代码编辑器 | 前端 GafCodeEditor | 语法高亮 |
| 内置 Skill | `skills/` (SkillDefinitionViewSet) | Skill 引擎 |
| 启停 | `skills/<pk>/toggle` | 启用/禁用 |

### 8.5 Skill 市场 `/ai/skill-market`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 市场列表 | `skills/market` (SkillMarketViewSet) | SkillMarketItem |
| 发布/导入 | `skills/market/<pk>/publish` + `import` | DRF action |
| 评分评论 | SkillMarketReview | 评分聚合 |

### 8.6 日志分析 `/ai/log-analysis`

> 归一化后合并了原 `/ops/log-analysis`（DebugPage）的 LLM 分析触发功能。双 tab 架构: ExecutionAnalysisTab（触发分析 + 查看结果）+ ArchiveAnalysisTab（归档关联分析）。

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| LLM 日志分析 | `debug/llm-analysis` (LLMAnalysisResultViewSet) | LLM + 审核 |
| 归档上传触发 | `debug/archives` + `debug/llm-analysis` | 上传 ZIP → 触发 LLM 分析 |
| 采纳/忽略 | LLMAnalysisResult 状态 | adopted/ignored |
| 分析结果审核 | `debug/llm-analysis/<pk>/review` | ReviewStatus 流转 |

### 8.7 AI 配置 `/ai/config`

> **v3 §2.8.1**: 从 `/system/ai-config` 迁移到 `/ai/config`（AI 模块内聚）

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| LLM 配置 | `settings/llm-config` (LLMConfig 单例) | provider openai/deepseek/ollama/custom |
| 模型选择 | LLMConfig.default_model | 多模型 |
| 参数调优 | temperature + max_tokens | 参数配置 |
| 模型评测 | `ai/model-evaluations` (ModelEvaluationViewSet) | 多模型对比 |

### 8.8 AI 用量 `/ai/usage`

> **v3 §2.8.1**: 从 `/system/ai-usage` 迁移到 `/ai/usage`（AI 模块内聚）

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 用量统计 | `ai/usage-stats` + `qa/llm-usage-logs` | Token + 成本 |
| 用量仪表盘 | 前端 AIUsageDashboard | 可视化 |
| 模型对比 | ModelComparisonPanel | 性能对比 |

---

## 九、系统 (System)

**路由**: `/system/settings` / `/system/config` / `/system/api-keys` / `/system/backup` / `/system/feature-flags` / `/system/audit-log` / `/system/notifications` / `/system/plugins`  **权限**: `settings.view` / `notification.view` / `plugin.view` + 角色 `admin/operator`

> **TD-099 fix 3**: `/ops/backup` 迁移到 `/system/backup`（系统级管理功能）；`/system/game-profiles` 已迁至 §二 GameProfiles；`/system/ai-config` + `/system/ai-usage` 已迁至 §八 AI 模块

系统设置，跨 3 个后端 app: `settings/` + `notifications/` + `plugins/`（i18n 已并入 gaf_core）+ 部分 `accounts/`/`tasks/`。

### 9.1 系统设置 `/system/settings`

> 归一化后无人值守策略 tab 已迁移到 `/ops/unattended` Strategy tab。本页保留: 安全设置 / 设备会话 / 基础设施健康 / 调试 / 语言 / 数据清理 / 配置导入导出 / 诊断包。

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 安全设置 | 前端 SecuritySettings | 2FA + 密码修改 |
| 设备会话 | DeviceSessionPanel | 会话管理 |
| 基础设施健康 | InfraHealthPanel | 健康检查 |

### 9.2 配置管理 `/system/config`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 配置 CRUD | `settings/config-generator` | JSON 配置块 |
| 配置迁移 | `settings/config-migration` | 版本迁移 |
| 诊断 | `settings/diagnostic` | 配置诊断 |
| 动态表单 | 前端 ConfigManagementPage | schema 驱动 |

### 9.3 API Key 管理 `/system/api-keys`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| API Key CRUD | `accounts/api-keys` (APIKeyViewSet) | 哈希存储 |
| 权限配置 | APIKey.permissions JSON | 细粒度权限 |
| IP 白名单 | APIKey.ip_whitelist | IP 限制 |
| 调用统计 | APIKey 调用计数 | 用量追踪 |

### 9.4 备份与恢复 `/system/backup`

> **TD-099 fix 3**: 从 `/ops/backup` 迁移到 `/system/backup`（系统级管理功能，非运维监控）

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 备份任务 CRUD | `settings/backups` (BackupViewSet) | BackupJob 模型 |
| 手动备份 | `settings/backups/<pk>/run` | 立即执行 |
| 恢复 | `settings/backups/<pk>/restore` | 数据恢复 |
| 定时备份 | Celery Beat 调度 | 自动备份 |
| 备份下载 | `settings/backups/<pk>/download` | 文件下载 |
| 备份目标 | 本地 / S3 / SFTP | 多目标支持 |

### 9.5 功能开关 `/system/feature-flags`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 开关 CRUD | `settings/feature-flags` (FeatureFlagViewSet) | FeatureFlag 模型 |
| 灰度发布 | FeatureFlag.rollout_percentage | 百分比控制 |
| 角色白名单 | FeatureFlag.allowed_roles | 角色限制 |
| IP 白名单 | FeatureFlag.allowed_ips | IP 限制 |
| 注册开关 | `accounts/init/status` → register_enabled | 动态控制 |

### 9.6 审计日志 `/system/audit-log`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 日志查询 | `accounts/audit-logs` (AuditLogViewSet) | AuditLog 模型 |
| 资源类型筛选 | AuditLog.resource_type | 分类筛选 |
| 详情查看 | AuditLog.metadata JSON | 操作详情 |
| 操作时间线 | 前端时间线 | 可视化 |

### 9.7 通知中心 `/system/notifications`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 通知 CRUD | `notifications/` (NotificationViewSet) | Notification 模型 |
| 已读管理 | `notifications/<pk>/mark-read` | DRF action |
| Webhook 配置 | `notifications/webhooks` (WebhookConfigViewSet) | WebhookConfig |
| 多渠道通知 | 7 渠道 (邮件/Webhook/钉钉/飞书/企业微信/Telegram/自定义) | 渠道适配器 |
| 通知偏好 | NotificationPreferences | 用户偏好 |

### 9.8 插件管理 `/system/plugins`

| 功能点 | 后端 API | 技术 |
|--------|---------|------|
| 插件列表 | `plugins/` (PluginListView) | PluginPackage |
| 上传安装 | `plugins/upload` + `install` | ZIP 上传 |
| 启停/重载 | `plugins/<pk>/toggle` + `reload` | 热重载 |
| 沙箱执行 | `plugins/<pk>/sandbox-exec` | PluginSandbox |
| 钩子机制 | PluginHook (event + priority) | 事件钩子 |

---

## 附录 A: 基础设施层（无侧边栏）

| 模块 | 后端 App | 说明 |
|------|---------|------|
| WebSocket 协议 | `protocol/` | 消息帧协议 + 心跳 + 配额 (与 `agents/` 的同步+ACK 实现并存) |
| 全局搜索 | `search/` | 跨 app 聚合搜索 (顶部搜索框) |
| 国际化 | `gaf_core/i18n` | 4 语言 (en/zh_Hans/ja/ko) + Django locale |
| 链路追踪 | `gaf_core/tracing` | trace_id 贯穿 (HTTP+WS ContextVar) |
| 指标 | `monitors/` (SLAMetric) | 时序存储 |
| 文档服务 | `docs/` (Django app) | API 文档托管 (非文档目录) |
| 游戏状态 | `gamestate/` | OCR 区域识别 + 阈值触发 |

---

## 附录 B: Agent 平台抽象层

Agent 是独立 Python 进程，通过 WebSocket 连接后端，提供跨平台能力。

> **v9.4 (2026-07-19, spec-39 Phase 4)** — 同步 P-028 ✅ 实际落地位置: macOS/Linux 在 `backend/device_bridge/platforms/{macos,linux}/` (非 agent 侧)

| 平台 | 截图 | 输入 | 发现 | 实现位置 |
|------|------|------|------|---------|
| **Windows** | BitBlt / PrintWindow / WGC / DXGI (支持 hwnd crop, Spec E TD-124) / LDOpenGL / NemuIpc / ADB screencap | SendInput (串行化 Spec C TD-121) / PostMessage (client 坐标 Spec B TD-122) / RegisterHotKey / minitouch (动态端口 Spec D TD-123) / ADB input | EnumWindows + ADB devices | `agent/src/platforms/windows/` (agent 侧, 完整) + `backend/device_bridge/platforms/windows/` (backend 侧抽象) |
| **macOS** | CGWindowListCreateImage (Quartz) + screencapture CLI 双方式 | CGEventPost (Quartz Event) | 待补充 | `backend/device_bridge/platforms/macos/` (P-028 ✅, backend 侧; agent 侧暂无 macOS 实现) |
| **Linux** | XGetImage + xdg_portal (grim/gnome-screenshot); XShmGetImage 回退到 XGetImage (python-xlib 限制, N129 审计) | XTest (python-xlib) | 待补充 | `backend/device_bridge/platforms/linux/` (P-028 ✅, backend 侧; agent 侧暂无 Linux 实现) |

**核心模块**:
- `agent/src/engine/` — DAG 并行执行 + StateMachine + 断点续跑
- `agent/src/devices/` — 设备抽象 + ADB + 模拟器 (adb/ 子目录)
- `agent/src/platforms/windows/` — Win32 截图/输入 + LDPlayer/MuMu 专用 (agent 侧仅 Windows)
- `backend/device_bridge/platforms/{windows,macos,linux}/` — backend 侧跨平台抽象层 (P-028 ✅, 纯 Python 包非 Django app)
- `agent/src/core/` — retry / timeout / 配置
- `agent/src/client/` — WebSocket 连接 + 设备同步 (走 `/ws/protocol/agents/`)

---

## 附录 C: 关键技术决策

| 决策 | 内容 | 原因 |
|------|------|------|
| 资源包绑账户 | GameAccount.resource_pack FK | 换服务器只换资源包，任务不变 |
| 设备不绑资源包 | Device 只负责执行方式 | 设备与游戏无关 |
| 轮换按账户维度 | 一个账户所有任务完成后换下一个 | 资源包一致 |
| 设备并行执行 | 多开模拟器同时跑不同账户 | 吞吐量最大化 |
| TaskDevice 中间表 | M2M Task ↔ Device | 任务指定执行设备 |
| Agent 自动关联 | Agent 启动上报 → Server 创建/更新 Device | 减少手动配置 |
| 5 层截图降级 | scrcpy→droidcast→nemuipe→ld_opengl→screencap | 容错最大化 |
| 3 方法输入 | SendInput/PostMessage/PseudoBackground × 鼠标/键盘/滚轮 | 兼容各种窗口 (TD-090 统一) |
| Multi-game 模式开关 + 白名单降级 (Spec A) | FeatureFlag `unattended_multi_game_mode` + `resolve_device_methods` 过滤 | 多游戏并行时禁用非 hwnd-isolated 方法, 防止串台 |
| PostMessage client 坐标 (Spec B / TD-122) | 4 个非 scroll 方法移除 `_client_to_screen` | Win32 spec: WM_LBUTTONDOWN/UP/MOUSEMOVE lParam 期望 client 坐标 |
| SendInput/PseudoBackground 串行化 (Spec C / TD-121) | `WindowsInputHandler` 实例级 `threading.RLock` | SendInput 依赖全局前台/光标, 并发会串台; RLock 因 PseudoBackground 内部调 `_sendinput` 需重入 |
| minitouch/MaaTouch 动态端口 (Spec D / TD-123) | per-serial CRC32 哈希端口分配 + 线性探测 | 多模拟器并行时固定端口会冲突; 同 serial 同端口确保 adb forward 规则稳定 |
| DXGI per-window crop (Spec E / TD-124) | `DXGICapture.capture_window(hwnd)` — GetWindowRect + numpy slice | DXGI 截全桌面, 多游戏并行串台; hwnd crop 实现隔离 |
| Backend WGC mock 移除 (Spec E / TD-125) | 删除 `_wgc.py`, `_capture_wgc` delegate 到 PrintWindow | backend WGC 一直是 mock 返回假图, 误导用户; agent 端 WGC 仍真实可用 |
| 两套 WebSocket | agents (同步+ACK) + protocol (异步+帧协议) | 控制流 vs 协议化通信 |
| Celery Beat | 5s 心跳 + 300s 告警升级 | 定时任务调度 |
