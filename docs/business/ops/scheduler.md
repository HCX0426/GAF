---
summary: 任务调度 — 无人值守会话 / 时间窗口 / 5 层恢复 / 自动停止 / DAG 任务链
applies_to: ['backend', 'frontend', 'design']
key_decisions:
  - scheduler 不直接派发任务, 通过 pipeline.services.create_chain_execution_and_dispatch 间接派发
  - UnattendedSession 按 game_profile 边界隔离 (P-011 多 session)
  - 5 层恢复 ActionChain 架构 (step/task/app/device/system)
  - Celery Beat 60s 周期 tick + post_save 信号双路径触发
  - DAG 任务链编辑器基于 @xyflow/react
last_updated: 2026-07-29
---

# 任务调度

> 模块路由 `/ops/unattended` / `/ops/scheduler`，对应前端侧边栏"运维"下的无人值守与定时任务。会话级调度 + 5 层恢复 + 多账号轮换。

## 1. 数据模型

文件：[scheduler/models.py](file:///d:/code/GAF/backend/scheduler/models.py)，共 7 个模型。

### 1.1 会话域
**UnattendedSession**（无人值守会话，P-011 多 session）
- `status`: init / running / paused / stopping / stopped / failed
- `game_profile` FK → `gamestate.GameProfile`（CASCADE，P-011 分组边界）
- `triggered_by` FK → User
- `rotation_rule` FK → `GameAccountRotation`（启动时快照）
- `loop_rotation`: bool（默认 False）— 循环轮换（TD-400, 2026-08-26）：链完成后把账户归还轮换池继续派发，支撑持续挂机；循环模式不触发 `all_completed` 自动停止（手动/时间窗口/连续失败仍可停）
- `active_chain_executions` M2M → `pipeline.TaskChainExecution`
- 统计：`total_devices` / `total_accounts` / `failed_count` / `completed_chain_count`
- 约束：每个 game_profile 至多一个 RUNNING/PAUSED session（由 `unattended_start_view` 409 强制）

### 1.2 账户轮换域
**GameAccountRotation**（轮换规则，详见 [accounts.md](../accounts/accounts.md#L33)）
- 4 策略：`sequential` / `random` / `by_stamina` / `by_last_executed`
- 字段：`accounts` (M2M) / `switch_interval_seconds` (默认 10) / `auto_skip_blocked` (默认 True)

### 1.3 时间窗口与预热域
- **TimeWindow**: `start_time` / `end_time` / `days_of_week` (JSON 0=周日~6=周六) / `is_enabled`，支持跨夜窗口
- **WarmupConfig**（单例）: `steps` (JSON list) / `global_timeout_seconds` (默认 600) / `failure_strategy`: skip_device/retry_then_skip/abort_all
- **AutoStopCondition**（每类型一条）: `condition_type` (consecutive_failures/device_offline/all_completed/window_end/manual_stop/resource_insufficient) + `action` (stop_all/stop_device/notify_continue)

### 1.4 预检与恢复域
- **PreflightCheck**: 5 种 check_type（device_online/account_valid/resource_ready/agent_connected/schedule_valid），status: pending/pass/fail/warning
- **RecoveryLog**: 5 层 `recovery_level`（step/task/app/device/system）+ `trigger_event` / `action_taken` / `success` / `details` (JSON)

## 2. 调度引擎

文件：[scheduler/engine.py](file:///d:/code/GAF/backend/scheduler/engine.py)，5 个核心函数。

| 函数 | 作用 |
|---|---|
| `check_time_window(dt)` | 检查时间是否落在启用 TimeWindow 内（无配置返回 True） |
| `calculate_account_order(rule, accounts)` | 按 4 策略排序账户，`auto_skip_blocked=True` 过滤 status='error' |
| `execute_warmup(device_id, config)` | 按 steps 依次执行预热（MVP 占位实现） |
| `check_auto_stop_conditions(...)` | 逐条评估 AutoStopCondition，返回触发列表 |
| `generate_execution_plan(days=7)` | 从 `Device.game_profile.default_routine`（TaskChain）派生计划 |

**关键**：engine 不直接派发任务，真正派发在 [scheduler/tasks.py](file:///d:/code/GAF/backend/scheduler/tasks.py) 的 `tick_unattended_session` 调用 `pipeline.services.create_chain_execution_and_dispatch`。

## 3. 调用链全景

### 3.1 主动派发路径
```
[Celery Beat 60s]
    │
    ▼
scheduler.tasks.tick_unattended_session
    │
    ├─ engine.check_time_window()  → 窗口外跳过
    ├─ select_for_update(skip_locked) 锁 RUNNING sessions
    └─ _tick_session(session)
        │
        ├─ 筛选 devices: agent.status IN (ONLINE, IDLE) AND game_profile_id=X AND default_routine__isnull=False
        ├─ engine.calculate_account_order()  → 轮换排序
        ├─ 检查 device 是否有 active TaskChainExecution → 有则跳过
        └─ pipeline.services.create_chain_execution_and_dispatch(chain_id, agent_id, device_id, game_account_id, triggered_by)
                │
                ├─ 创建 TaskChainExecution (status=PENDING)
                └─ pipeline.tasks.dispatch_chain_node.delay(chain_exec.id, first_node.id)
                        │
                        └─ 按 node_type 分发:
                            ├─ TASK → tasks.app 任务派发
                            └─ PIPELINE → pipeline.execute WS 消息（agent 执行）
```

### 3.2 完成回调路径
```
TaskChainExecution.status → SUCCESS/FAILED/CANCELLED
    │
    ▼
scheduler.signals.on_chain_execution_status_change (post_save)
    │
    └─ transaction.on_commit → scheduler.tasks.on_chain_execution_completed.delay(chain_execution_id)
            │
            └─ _process_chain_completion(session, chain_exec)
                │
                ├─ session.active_chain_executions.remove(chain_exec)
                ├─ session.completed_chain_count += 1
                ├─ 失败: session.failed_count += 1; 成功: session.failed_count = 0
                ├─ 失败时: _trigger_chain_recovery
                │       └─ recovery_engine.handle_task_failure(task_exec_id, session.failed_count)
                └─ _check_auto_stop(session)
                        └─ engine.check_auto_stop_conditions(...)
                        └─ 触发则 session.status=STOPPED, stop_reason='AutoStop: ...'
```

## 4. 5 层恢复引擎

文件：[scheduler/recovery_engine.py](file:///d:/code/GAF/backend/scheduler/recovery_engine.py)

### 4.1 配置读取链
```
settings.UnattendedStrategy (singleton DB)
  └── recovery_config (JSONField)
        ├── stepLevel     {maxRetries, retryIntervalSeconds, exponentialBackoff}
        ├── taskLevel     {consecutiveFailureThreshold, failureAction}
        ├── appLevel      {freezeDetection, freezeTimeoutSeconds, freezeAction}
        ├── deviceLevel   {crashDetection, crashAction, backupDeviceId, maxRestartCount}
        └── systemLevel   {agentTimeoutSeconds, timeoutActions[]}
```

`get_strategy_config()` 是 recovery 与 strategy 的唯一耦合点，`is_active=False` 或异常时返回硬编码默认值。配置项完整定义见 [system.md §2.1](../system/system.md#L41)。

### 4.2 ActionChain 架构（P-020-B 重构版）
- **OnFailurePolicy**: `abort`（中止整个 chain）/ `continue`（继续下一步，chain 标失败）/ `skip`（跳过剩余，chain 标成功）
- **ActionSpec**: `type` / `target` / `params` / `on_failure` / `max_retries` / `timeout_seconds`
- **ChainStepResult**: `action_type` / `success` / `attempts` / `error` / `duration_ms` / `output`

每层默认 actions：
| 层级 | 默认 actions | on_failure |
|---|---|---|
| step | `[retry(target, max_retries=N)]` | ABORT |
| task | `[{failureAction}(target)]` | SKIP |
| app | `[{freezeAction}(target), notify('admin')]` | CONTINUE |
| device | `[{crashAction}(target, backup_device_id)]` | ABORT |
| system | `[{a}(target) for a in timeoutActions]` | CONTINUE |

### 4.3 5 个 handler
| Handler | 触发条件 | 接信号源 |
|---|---|---|
| `handle_step_failure` | 单步失败 | ✅ tasks/signals.py |
| `handle_task_failure` | `consecutive_failures >= threshold` | ✅ scheduler/tasks.py + tasks/signals.py（双重触发，threshold 兜底） |
| `handle_app_freeze` | `freeze_duration >= freezeTimeoutSeconds` | ✅ 已接线 |
| `handle_device_crash` | `crashDetection=True` | ✅ 已接线 |
| `handle_agent_timeout` | `timeout >= agentTimeoutSeconds` | ✅ 已接线 |

> 注记：L3/L4/L5 三层原标 "❌ 预留" 已更新为 "✅ 已接线"（P-048 已落地：L3 detect_app_freeze(60s)、L4 agents/signals.py::trigger_device_crash_recovery、L5 tasks/heartbeat.py::check_agent_heartbeats(5s)，详见 §9.1）。

## 5. 无人值守 API

前缀 `/api/v2/scheduler/unattended/`，详见 [scheduler/unattended_views.py](file:///d:/code/GAF/backend/scheduler/unattended_views.py)。

| 路径 | 方法 | 用途 |
|---|---|---|
| `start/` | POST | 启动会话（必填 game_profile_id，409 检查同 profile 已运行） |
| `stop/` | POST | 停止会话（必填 session_id） |
| `pause/` | POST | 暂停（仅 RUNNING） |
| `resume/` | POST | 恢复（仅 PAUSED） |
| `preflight/` | GET | 5 项预检（ThreadPoolExecutor 并发） |
| `status/` | GET | 设备×账户状态矩阵 |
| `queue/` | GET | 执行队列预览 |
| `progress/` | GET | 今日进度 + ETA |
| `sessions/` | GET | 历史会话列表（最多 50） |

### 5.1 启动流程
1. 必填 `game_profile_id`，409 检查同 profile 已有 RUNNING/PAUSED
2. 筛选设备：`agent.status IN (ONLINE, IDLE) AND game_profile_id=X AND default_routine IS NOT NULL`
3. **P-011 多游戏安全检查**：`is_multi_game_mode_enabled()` 时检查 `original_input_method` 是否在 `MULTI_GAME_BLOCKED_INPUT_METHODS` 黑名单 → 400 `unsafe_method_for_multi_game`
4. 遍历设备派发：调 `pipeline.services.create_chain_execution_and_dispatch`
5. 可选 `rotation_rule_id` 快照到 session；可选 `loop_rotation`（bool，TD-400）— 开启后链完成即归还账户，同 session 持续循环轮换
6. 创建 `UnattendedSession` (status=RUNNING)

### 5.2 预检 5 项
| 检查 | 失败等级 |
|---|---|
| `check_device_online` — 设备 != online | fail |
| `check_account_valid` — 账户 status == banned | fail |
| `check_resource_ready` — 激活资源包缺模板 | warning |
| `check_agent_connection` — Agent 心跳超时 | warning |
| `check_scheduler_rules` — 时间窗口配置 | warning |

### 5.3 配套配置 API（scheduler/views.py）
| 路径 | 用途 |
|---|---|
| `time-windows/` | 时间窗口 CRUD（含不重叠校验） |
| `recovery-logs/` | 恢复日志只读（支持 ?recovery_level=&success=） |
| `warmup-config/` | 预热配置 Upsert |
| `auto-stop-conditions/` | 自动停止条件批量 Upsert |
| `execution-plan/` | N 天执行计划预览 |
| `today/` | 今日日程 |
| `executions/` | 执行历史（分页） |

## 6. 前端页面

### 6.1 UnattendedControlPage
文件：[Ops/UnattendedControlPage.tsx](file:///d:/code/GAF/frontend/src/pages/Ops/UnattendedControlPage.tsx)

双 Tab：
- **Control Tab**: `UnattendedControlBar`（启动/暂停/恢复/紧急停止）+ `PreflightChecklist` + 执行队列 Table + 状态矩阵 Table（12 设备 × 10 账户，右键派发 routine）
- **Strategy Tab**: `UnattendedStrategySettings`（5 层恢复 + 夜间 + 频率 + 通知 + 冷却）

状态管理：`useUnattendedStore`（Zustand），session isRunning 时 30s 轮询刷新 matrix + queue。

### 6.2 UnattendedControlBar（P-011 多 session）
文件：[UnattendedControlBar.tsx](file:///d:/code/GAF/frontend/src/pages/Ops/UnattendedControlBar.tsx)

- 顶部：活跃会话数 + 多游戏模式开关（Segmented single/multi）+ GameProfile Select + "Start new session"
- Sessions 列表：每 session 独立控制按钮（Pause/Resume/紧急停止）
- 紧急停止 Modal：5 个预设原因（device_error/account_risk/manual_intervention/maintenance/other）

### 6.3 ScheduledTasks（定时任务）
文件：[Ops/ScheduledTasks/index.tsx](file:///d:/code/GAF/frontend/src/pages/Ops/ScheduledTasks/index.tsx)

三 Tab：
- **Tasks**: List/Calendar 视图切换，CRUD（name/task/schedule_type/cron 或 run_at/is_enabled）
- **History**: 执行历史 + 执行对比（选两个 execution diff）
- **Chains**: 任务链列表 + 创建 → 跳 DAG 编辑器

### 6.4 DagEditorPage
文件：[Ops/ScheduledTasks/DagEditorPage.tsx](file:///d:/code/GAF/frontend/src/pages/Ops/ScheduledTasks/DagEditorPage.tsx)
- 基于 `@xyflow/react`（React Flow）拖拽式多任务编排
- 节点双类型：`task`（蓝色）/ `pipeline`（紫色）
- 侧边栏拖拽到画布（HTML5 原生 drag）
- 构建 `TaskChain.dag_data`（nodes + edges）

## 7. 跨 app 调用关系

scheduler 不直接调用 tasks 的 Task 模型，而是通过 `pipeline.services.create_chain_execution_and_dispatch` 间接派发。

**解耦边界**：
- **scheduler 负责**: "哪个 device 在哪个 session 用哪个 account 跑哪个 chain"
- **pipeline 负责**: "chain 内节点如何串起来跑"

**触发器双路径**：
1. 主动派发：`unattended_start_view`（启动时一次性）+ `tick_unattended_session`（60s 周期补派）
2. 被动回调：`signals.on_chain_execution_status_change` → `on_chain_execution_completed`（chain 完成时更新 session + 触发恢复 + 检查 AutoStop）

**双重恢复触发**：`tasks/signals.py` 单 TaskExecution 失败调 `handle_task_failure`（任务级），`scheduler/tasks.py` chain 完成时也调（session 级），threshold 默认 3 使低 count 调用 no-op，二者互补。

## 8. 已知限制

> 以下未实现项已登记到 `docs/archive/pending-roadmap.md`,此处仅作概要说明。

- `calculate_account_order` 自定义顺序策略 → **P-055** (TD-111)

### 8.1 测试隔离问题 (2026-07-29 已修复)

> 历史问题已修复, 此处仅作记录避免重复排查.

- **gaf_ai 测试 28 个断言不匹配**: `GAF_UNIFIED_RESPONSE_ENABLED=True` 中间件把 `Response.data` 包装成 `{code, message, data}` 信封, 旧测试断言 `resp.data['field']` 失败. 修复: 在 `backend/gaf_ai/tests/__init__.py` 加 `unwrap(resp)` helper, 6 个测试文件断言改为 `unwrap(resp)['field']` (成功路径) 或 `resp.data['message']` (错误路径).
- **P-048 测试 25 个并行隔离失败**: `test_p048_device_command_result.py` 用 `TransactionTestCase` (truncate 表), 在 `pytest -n auto` 并行时删除其他 worker 的测试数据. 修复: 改为 `TestCase` (savepoint 隔离), 因 `database_sync_to_async` 不依赖 `transaction.on_commit`.

## 9. P-048 实现状态 (5 层恢复接线 + device_command 协议, 2026-07-29)

> P-048 已完成. 5 层恢复引擎的 3 个 handler 信号源接入 + `execute_recovery_action` 全部真实动作 + `_execute_warmup_step` 接入 device_command + 新增 `device.command` WS 协议消息类型, 5 层链路全部闭环.

### 9.1 5 层恢复信号源

| 层级 | Handler | 信号源 | 状态 |
|------|---------|--------|------|
| L1 步骤级 | `handle_step_failure` | `tasks/signals.py::ExecutionStep post_save` (status=FAILED) | ✅ 既有 (P-020-D) |
| L2 任务级 | `handle_task_failure` | `tasks/signals.py::TaskExecution post_save` (status=FAILED) | ✅ 既有 (P-020-D) |
| L3 应用级 | `handle_app_freeze` | `scheduler/tasks.py::detect_app_freeze` Celery beat (60s) | ✅ P-048 |
| L4 设备级 | `handle_device_crash` | `agents/signals.py::trigger_device_crash_recovery` (Device post_save, status→ERROR) | ✅ P-048 |
| L5 系统级 | `handle_agent_timeout` | `tasks/heartbeat.py::check_agent_heartbeats` Celery beat (5s) | ✅ P-048 |

### 9.2 `execute_recovery_action` 全部真实动作

| action_type | 实现 | 说明 |
|-------------|------|------|
| `notify` | `_action_notify` | channel_layer.group_send 广播 dashboard 告警 (FrontendEventType.NOTIFICATION) |
| `mark_offline` | `_action_mark_offline` | Agent.status = OFFLINE + save (幂等, heartbeat 已先标记一次) |
| `reassign` | `_action_reassign` | 找备用 ONLINE agent + 切换 TaskExecution.agent + 重置 RUNNING step 为 PENDING + recovery_layer=5 |
| `retry`/`skip`/`restart`/`switch_account` | (语义性) | scheduler 自身处理, recovery_engine 仅记录 |
| `restart_app` | `_action_device_command` → WS `device.command` 帧 → agent `handle_device_command` (spec 2026-08-17-s27-device-command-executors) | agent 真实执行: Android/emulator = `am force-stop` + `monkey` 启动; Windows = `taskkill /IM <process> /F` + `subprocess.Popen(command)`; config 参数 `package` (android) / `command` (+可选 `process`) (windows) / `timeout` / `wait_seconds`; 结果经 `device.action_result` 上报 |
| `restart_emulator` | `_action_device_command` → WS `device.command` 帧 → `EmulatorController.restart_emulator` | kill + start + wait_for_boot 完整流程, 支持 6 种模拟器 (ldplayer/mumu/bluestacks/nox/memu/xiaoyao) |
| `reconnect_adb` | `_action_device_command` → WS `device.command` 帧 → `ADBDevice.reboot` | adb reboot + wait-for-device + getprop sys.boot_completed 轮询 |
| `relogin` | `_action_device_command` → WS `device.command` 帧 → agent 返回 not_implemented | 当前 agent 端不直接执行, 需 backend 通过 pipeline.execute 重跑登录节点 (warmup 中已降级处理); 凭据下发设计待定 (spec 已知限制) |
| `notify_only` | `_action_device_command` → WS `device.command` 帧 → agent `handle_device_command` | agent 真实执行: logger 按 `level` (info/warning/error) 输出 `message`; config 参数 `message` (必填) / `level` (默认 info); 结果经 `device.action_result` 上报 |
| `switch_backup` | `_action_device_command` → WS `device.command` 帧 → `DeviceManager.set_active_device` | 切换 DeviceManager 的 active device |

### 9.3 `device.command` WS 协议消息类型 (P-048 新增)

- 常量: `protocol/constants.py::MessageType.DEVICE_COMMAND = "device.command"`
- backend 转发: `protocol/consumers.py::AgentConsumer.device_command`
- backend 发送: `scheduler/recovery_engine.py::_action_device_command` (通过 `channel_layer.group_send(f"agent_{agent_id}", {"type": "device.command", ...})`)
- agent 路由: `agent/src/client/connection.py::handler_map["device.command"]`
- agent 处理: `agent/src/client/handler.py::handle_device_command` (异步线程执行 + `device.action_result` 帧上报)
- agent 路由实现: `agent/src/client/handler.py::_execute_device_command` (按 command 路由到 EmulatorController/ADBDevice/WindowsDevice)

### 9.4 `_execute_warmup_step` 真实化 (P-048 升级)

`scheduler/engine.py::_execute_warmup_step` 不再占位, 通过 device_command 委托 agent:

> ⚠️ 实查(2026-08-28): engine.py::_execute_warmup_step 仍为占位(直接 return True / sleep)，未真正转发 device_command；行为以代码为准。
- `start_emulator` / `start_game` → `restart_emulator` device_command → agent EmulatorController
- `auto_login` → `relogin` device_command (agent not_implemented, warmup 降级返回 True)
- `wait_loading` → scheduler 端 sleep (不委托)

### 9.5 测试覆盖

- `backend/scheduler/tests/test_recovery_link_wiring.py` (29 个测试): signal transition / dedup / fallback / 真实 action 执行 / device_command 派发 / 端到端 RecoveryLog 写入
- `agent/tests/test_s27_recovery_wiring.py` (17 个测试): 6 种 command 路由 + 异常路径 + action_result 帧上报
- `backend/protocol/tests/test_protocol.py` (常量数量更新): all_types=22 / server_to_agent=12
