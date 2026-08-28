---
summary: 调度协调架构 — 从执行创建到 Agent 执行的完整链路
applies_to: ['backend', 'agent', 'architecture', 'dispatch']
last_updated: '2026-08-27 (B1: TaskChain 节点派发归一化到 dispatch_task / force_agent_id)'
---

# 调度协调架构

> **版本**: 1.9 | **日期**: 2026-08-17 | **修订**: §4.6.1 新增 (P3 出站队列 SQLite 持久化) | 变更: §4.5/§4.6 新增 (S1 派发 ack 语义 + S2 恢复链接线)

## 1. 调度链路全貌

从用户触发执行到 Agent 实际执行的完整链路：

```
用户触发执行
    ↓
① TaskExecution.create(status=PENDING)
    ↓
② transaction.on_commit(dispatch_task.delay)
    ↓
③ Celery 队列 (Redis, DB 1)
    ↓
④ Celery Worker 执行 dispatch_task
    ↓
⑤ AgentSelector 选 Agent (能力匹配 + 负载均衡)
    ↓
⑥ channel_layer.group_send (Redis Channel Layer, DB 1)
    ↓
⑦ AgentConsumer.task_assign (Daphne ASGI 进程)
    ↓
⑧ WebSocket 帧 → Agent 端接收 → 开始执行
```

### 各环节详解

| 环节 | 组件 | 说明 | 失败模式 |
|------|------|------|----------|
| ① 创建执行 | `tasks/services/task_service.py:execute_task` | 创建 `TaskExecution(status=PENDING)`，关联 task/device/game_account | DB 写入失败 → 500 返回前端 |
| ② 触发调度 | `transaction.on_commit` | Django 事务提交后异步触发 Celery 任务，确保 execution 已持久化 | on_commit 回调不执行（罕见 Django bug） |
| ③ 入队 | Redis (Celery) | `dispatch_task.delay(execution_id)` 将任务放入 Celery 队列 | Redis 不可用 → 任务丢失 |
| ④ 执行调度 | `tasks/tasks.py:dispatch_task` | Celery Worker 消费队列，加载 execution，执行 Agent 选择逻辑 | Worker 未启动 → 任务永久留在队列 |
| ⑤ 选 Agent | `AgentSelector` | `filter_by_capability` → `select_by_load`（空闲优先，心跳最新优先） | 无匹配 Agent → execution FAILED |
| ⑥ 发送 | Redis Channel Layer | `group_send(agent_group, task.assign)` 通过 Redis pub/sub 推送给 Daphne | Channel Layer 不可用 → 消息丢失 |
| ⑦ 转发 | `AgentConsumer.task_assign` | Daphne 进程接收 Channel Layer 消息，序列化为 WebSocket 帧发送给 Agent | Agent 断开 → 消息丢失，execution 悬空 |
| ⑧ 执行 | Agent 端 `handler.py` | 接收 `task.assign` 帧，解析 `task_definition`，开始执行 pipeline | 执行异常 → 卡住，依赖异常捕获 |

### 数据流的关键边界

```
┌─────────────────────────────────────────────────────────┐
│                     Backend 进程                          │
│  ┌──────────────┐    ┌──────────────┐                    │
│  │  Celery Beat  │    │ Celery Worker│                    │
│  │  (定时任务)    │    │ (消费队列)    │                    │
│  └──────┬───────┘    └──────┬───────┘                    │
│         │ 60s tick          │ dispatch_task               │
│         ▼                   ▼                             │
│  ┌──────────────────────────────────────────────────┐    │
│  │              Redis (DB 1)                         │    │
│  │  • Celery 队列 (任务调度)                         │    │
│  │  • Channel Layer (WebSocket 消息路由)              │    │
│  │  • Celery 结果后端 (ack 确认)                     │    │
│  └──────────────────────┬───────────────────────────┘    │
│                         │ group_send                      │
│                         ▼                                 │
│  ┌──────────────────────────────────────────────────┐    │
│  │          Daphne (ASGI 服务器)                     │    │
│  │  • AgentConsumer — 接收 Channel Layer 消息 → WS  │    │
│  │  • FrontendConsumer — 前端实时状态推送            │    │
│  └──────────────────────┬───────────────────────────┘    │
│                         │ WebSocket 帧                    │
└─────────────────────────┼─────────────────────────────────┘
                          │
                          ▼
                  ┌──────────────────┐
                  │  Agent 进程       │
                  │  (pipeline 执行)  │
                  │  • 接收 task.assign│
                  │  • 执行 pipeline   │
                  │  • 发送 task.result│
                  └──────────────────┘
```

## 2. 服务协调关系

GAF 调度系统由 5 个独立服务协同完成：

### 2.1 服务角色

| 服务 | 进程类型 | 职责 | 依赖 |
|------|----------|------|------|
| **Daphne** | ASGI 服务器 | 处理 HTTP API + WebSocket 连接；维护 Agent 和 Frontend 的 WS 长连接；接收 Channel Layer 消息转发给 Agent | Redis |
| **Celery Worker** | 任务消费者 | 执行 `dispatch_task` 等异步任务；从 Redis 队列消费消息；调用 AgentSelector 选 Agent 并通过 Channel Layer 发送 | Redis + Django ORM |
| **Celery Beat** | 定时调度器 | 定期触发 `beat_schedule` 中的任务（每 60s 扫描 PENDING 执行、每 5s 检查心跳等） | Redis + Django ORM |
| **Agent** | 任务执行器 | 通过 WebSocket 连接到 Daphne；接收 `task.assign` 帧执行 pipeline；发送 `task.result` 帧反馈执行结果 | Daphne (WS) |
| **Redis** | 消息代理 + 状态存储 | Celery 队列（DB 1）、Channel Layer（DB 1）、心跳状态、结果后端 | 无 |

### 2.2 消息路径

```
用户 HTTP 请求 → Daphne (HTTP) → Django View → services.py
    → TaskExecution.create → on_commit → dispatch_task.delay
    → Redis 队列 (Celery)
    → Celery Worker 消费 → AgentSelector.select → group_send
    → Redis Channel Layer
    → Daphne (ASGI) → AgentConsumer.task_assign
    → WebSocket 帧 → Agent 执行
```

### 2.3 响应路径

```
Agent 执行完成 → WebSocket task.result 帧
    → Daphne (ASGI) → AgentConsumer._handle_task_result
    → TaskExecution 状态更新 (DB)
    → 前端轮询/WebSocket 状态推送
```

### 2.4 开发模式 vs 生产模式

| 维度 | 开发模式 (GAF_CELERY_MODE=eager) | 生产模式 (默认) |
|------|----------------------------------|----------------|
| 任务队列 | APScheduler 内嵌 (无独立进程) | Celery Worker + Beat |
| 启动顺序 | 3 步: Redis → Backend → Agent + Frontend 并行 | 6 步: Redis → Backend → Worker → Beat → Agent → Frontend |
| 启动脚本 | `scripts/gaf_services.ps1` | 手动部署 (预留) |
| 进程数 | 4 (redis + daphne + agent + vite) | 7 (同上 + worker + beat + monitor) |

## 2.5 TaskChain 节点派发归一化 (B1, 2026-08-27)

> **背景**: dispatch_chain_node 曾手写第二套 `task.assign` WS 帧 (pipeline/tasks.py
> `_send_task_assign` / `_dispatch_*_node`)，与 dispatch_task 的 payload 构造重复，
> 且 chain 节点缺少设备串行/并发/ACK 统一兜底。spec-2026-08-02 的"统一入口"
> 声明与实际代码漂移。

**归一化后**: chain 节点不再直接发 WS，而是创建 TaskExecution（绑定 chain 预选的
agent/device/game_account，status=PENDING）后调用
`dispatch_task.delay(execution.id, force_agent_id=<chain agent>)`，由
`dispatch_task` 统一接管：

- **agent 固定**: `force_agent_id` 跳过 AgentSelector，整条链锁定在同一个 Agent
- **可靠性对齐**: 设备级串行检查 / 并发控制器 / S1 dispatch-ack (dispatch_sent_at)
  / device_info 构建 / resource_pack 透传 / debug 目录 + meta.json 全部统一生效
- **payload 单源**: 删除了 pipeline/tasks.py 的 `_send_task_assign` /
  `_build_device_info_for_device` 双套实现

```
TaskChain execute → TaskChainExecution(PENDING) → dispatch_chain_node
  → TaskExecution(PENDING, agent/device/game_account 绑定)
    → dispatch_task.delay(force_agent_id)  ← 统一入口
      → RUNNING + S1 ack 快照 + WS task.assign → Agent 执行
```

## 3. 启动顺序与依赖

### 3.1 启动顺序 (开发模式)

> 开发模式使用 `GAF_CELERY_MODE=eager`，Celery Worker 和 Beat 被 APScheduler 替代，无需独立启动。详见 `scripts/gaf_services.ps1`。

```
① Redis ────────────────┐
                         │
② Backend (Daphne) ─────┤
  └─ APScheduler 内嵌     │
                         │
③ Agent ────────────────┤
                         │
④ Frontend (Vite) ──────┘
```

### 3.2 为什么必须按此顺序

| 步骤 | 关键前提 | 违反后果 |
|------|----------|----------|
| ① Redis 先启动 | Backend 依赖 Redis 作为 Channel Layer | Daphne Channel Layer 不可用，Agent 连接失败 |
| ② Daphne 后启动 | 需要 Redis 就绪后注册 Channel Layer；Agent 连接需要 WS 端口已监听 | Agent 连接失败，前端 API 不可用 |
| ③ Agent 后启动 | 需要 Daphne WS 端口已监听 | Agent 连接失败，WebSocket 重试循环 |
| ④ Frontend 后启动 | 需要 Backend API 已响应 | 前端白屏/API 请求失败 |

### 3.3 启动脚本 (开发模式)

> 开发环境使用 `scripts/gaf_daemon.py` 管理服务生命周期（启动/停止/状态检查）。`scripts/gaf_services.ps1` 作为兼容层，将命令委托给 `gaf_daemon.py`。

`gaf_daemon.py` 实现顺序启动，每个步骤包含：

1. 先停止旧实例（避免端口冲突/进程重复）
2. 启动服务进程
3. **等待验证** — 轮询端口监听 / Redis PING / 日志输出，超时则告警

```bash
# 启动守护进程（含看门狗自动重启）
python scripts/gaf_daemon.py daemon

# 查看状态
python scripts/gaf_daemon.py status
```

### 3.4 启动顺序 (生产模式)

> 生产模式使用 Celery Worker + Beat，需要额外的进程。

```
① Redis ────────────────┐
                         │
② Backend (Daphne) ─────┤
                         │
③ Celery Worker ────────┤
                         │
④ Celery Beat ──────────┤
                         │
⑤ Agent ────────────────┤
                         │
⑥ Frontend (Vite) ──────┘
```

## 4. 异常恢复机制

### 4.1 场景一：PENDING 超时自动恢复

**问题**: 执行卡在 `PENDING` 状态永久（如 Celery Worker 未启动、设备忙、所有 Agent 满载）。

**机制**: `retry_pending_executions` Celery Beat 任务（每 60s 扫描）

```python
# backend/tasks/tasks.py:482-506
def retry_pending_executions():
    """扫描 PENDING 超过 1 分钟的执行，自动重试调度。"""
    stuck = TaskExecution.objects.filter(
        status=PENDING,
        created_at__lt=now() - timedelta(minutes=5),
        recovery_attempts__lt=5,  # 最大 5 次
    )
    for exec in stuck:
        exec.recovery_attempts += 1
        exec.save(update_fields=['recovery_attempts'])
        dispatch_task.delay(exec.id)
```

**恢复路径**:
```
PENDING 超过 5 分钟 → Beat 扫描 → dispatch_task.delay → Worker 消费 → 选 Agent → 执行
```

**兜底**: 5 次重试后仍失败 → 保留 PENDING 状态，人工介入排查（Worker 是否运行、Agent 是否在线）。

### 4.2 场景二：服务挂了自动恢复

**问题**: 某个服务进程崩溃退出，导致调度链路中断。

**机制**: `gaf_daemon.py` Python 守护进程（2026-08-08 新增）

> 取代原外部 wrapper 脚本，内置 monitor 模式，支持服务自动重启和进程唯一性保证。

```bash
# 启动守护进程（看门狗模式，自动重启崩溃的服务）
python scripts/gaf_daemon.py daemon

# 查看所有服务状态
python scripts/gaf_daemon.py status

# 停止所有服务
python scripts/gaf_daemon.py stop
```

**恢复路径**:
```
服务崩溃 → 守护进程检测到端口未监听 → 自动重启服务 → 恢复正常
```

**注意**: 开发模式下 APScheduler 内嵌在 Daphne 进程中，Daphne 崩溃后 APScheduler 也随之不可用，需重启整个服务栈。`gaf_daemon.py` 会自动检测并重启 Daphne。

### 4.3 场景三：进程重复

**问题**: 多个 Worker 或 Beat 实例同时运行，导致调度冲突（任务被重复消费、Beat 重复触发）。

**机制**: `gaf_daemon.py` 启动前自动杀死旧实例（按端口 + 命令行匹配），确保唯一性

**恢复路径**:
```
启动服务 → gaf_daemon.py 杀旧实例 → 启动新实例 → 唯一性保证
```

### 4.4 其他恢复机制

| 机制 | 触发 | 说明 |
|------|------|------|
| `check_pending_timeout` | 每 60s (Celery Beat) | PENDING 超过 300s 且无 retry 机制 → 标记 FAILED |
| `check_execution_timeout` | 每 60s (Celery Beat) | RUNNING 超过 timeout 配置 → 标记 FAILED，释放 Agent/Device |
| `check_cancel_timeout` | 每 60s (Celery Beat) | CANCELLED 超过 10s 无响应 → 标记 FORCE_TERMINATED |
| `check_agent_heartbeats` | 每 5s (Celery Beat) | Agent 心跳超时 30s → 标记 OFFLINE，释放其执行 |
| `dispatch_task` 自重试 | `max_retries=3, countdown=30` | 设备忙/并发满时自动重试调度 |

### 4.5 派发 ack 语义 (S1, 2026-08-16)

**问题**: 派发帧经 Channel Layer + WebSocket 是"发后即忘"——agent 是否真正收到任务、任务是否悬空，backend 无感知。agent 断线瞬间派发 → 帧静默丢失 → execution 永久 PENDING。

**机制**: 派发-确认 (dispatch-ack) 闭环

| 组件 | 位置 | 说明 |
|------|------|------|
| 快照 | `tasks/tasks.py:dispatch_task` | 派发前写 `execution_snapshot` (dispatch_sent_at / dispatch_attempts)，同一帧携带 `trace_id` |
| agent ack | `agent/src/client/handler.py` | 收到 task.assign 后回发 dispatch_ack 帧（含 execution_id + trace_id） |
| backend 落盘 | `protocol/consumers.py:_record_dispatch_ack` | 收到 ack 写 `dispatch_ack_at`，标记派发闭环 |
| 兜底扫描 | `tasks/heartbeat.py:check_dispatch_acks` | Celery Beat 每 10s 扫描 `dispatch_sent_at` 超 15s 且无 ack 的执行：重派 (attempts < DISPATCH_MAX_ATTEMPTS=3) 或标记 FAILED (error 含 "dispatch-ack") |
| 幂等 | `heartbeat.py:_mark_dispatch_failed` | 重派前先置 FAILED 再创建新 execution，保留 trace_id 防重入 |

**恢复路径**:
```
派发 → 15s 无 ack → Beat 扫描 → 重派 (≤3 次) → 仍无 ack → FAILED (可诊断)
```

### 4.6.1 出站队列持久化 (P3, 2026-08-17)

**问题**: agent 出站队列 (S1 引入) 是内存 deque——进程崩溃/重启即丢失，断线期间积压的 task.result 随进程一起消失，backend 执行永久 RUNNING。

**机制**: 可选 SQLite 旁路存储 (`agent/src/client/outbox_store.py`)，注入 `AgentConnection(outbox_store=...)` 后启用：

| 环节 | 行为 |
|------|------|
| 启动 | `load_all()` 恢复上次未重放的帧 (FIFO) 灌入内存 deque |
| 入队 | `_enqueue_outbox` 同步 `INSERT` 落盘；容量满丢弃最旧帧时同步删最旧行 |
| 重放 | `_flush_outbox` 逐条 send，成功帧累计 `sent_count`，结束后 `delete_first_n(sent_count)` |
| 中断 | 剩余帧仅回内存 deque (store 行保留，`persist=False` 不重复写)，下次重连继续重放 |
| 降级 | store 打开失败 (磁盘满/损坏) → 捕获降级内存模式，不阻塞主链路 |

**幂等保障**: 重复发送安全 — backend `update_task_execution_result` 终态守卫 (S1 P2) 拒绝覆盖 SUCCESS/FAILED/CANCELLED；task.progress 重放无害。

**不注入 store** → 行为与 S1 完全一致 (零变化)。

### 4.6 恢复链接线接线 (S2, 2026-08-16)

**问题**: P-020-B 恢复引擎 (ActionChain) 动作"看起来执行了"，但结果未接线到执行链路：reassign 不补派发、device.command 无 consumer 转发、语义动作返回假 success、signal 回调同步 sleep、freeze 检测无 beat。

**修复** (`backend/scheduler/recovery_engine.py` + `backend/protocol/consumers.py`):

| 动作 | 修复前 | 修复后 |
|------|--------|--------|
| `reassign` | 只改 agent + 重置 step，任务永远卡 PENDING | 非终态时 `dispatch_task.delay(execution.id)` 重新派发 (recovery_layer=5) |
| `device.command` | group_send 无 consumer 路由方法 → Channels 静默丢弃 | `AgentConsumer.device_command` (consumers.py:1187) serialize 成 WS 帧发给 agent |
| `retry` | 假 success | 重置 ExecutionStep 为 PENDING + 清 error_message (task_result 非终态时) |
| `skip` | 假 success | step 级标记 SKIPPED；task 级宽容成功 (execution 不存在或 FAILED 都 success) |
| `restart` / `switch_account` | 假 success | S2 (2026-08-16): 显式 error 诚实降级；**S2-2.7 (2026-08-17)**: 解析执行 agent 的 ONLINE 设备 → 派发 `device.command` (restart → restart_app)，agent 端 `handle_device_command` 执行后经 `device.action_result` 上报真实结果 (P-048 写 RecoveryLog)；**executors spec (2026-08-17)**: `restart_app`/`notify_only` 由 agent 真实执行 (restart_app 复用 start_app/stop_app 节点能力, ADB force-stop+monkey / Windows taskkill+Popen；notify_only logger 输出)，`relogin`/`switch_account`/`switch_backup` 仍显式 not-implemented (凭据下发设计待定) |
| `handle_step_failure` | signal on_commit 回调 `time.sleep(min(wait,60))` 阻塞 | sleep 移除，退避语义交给调用方 (Celery task) |
| `detect_app_freeze` | 无 beat 注册 | `config/celery.py` beat 每 60s |
| `timeout_seconds` | 未实现 | `_execute_single_action` 用 `time.monotonic` + 循环检查 per-attempt 超时 |

**消息类型**: `MessageType.DEVICE_COMMAND = "device.command"`（server→agent 下行，已加入 `all_types()` / `server_to_agent_types()`）。

## 5. 进程唯一性约束

### 5.1 架构约束

每个服务必须有且只有一个实例运行。这是 GAF 调度架构的**硬约束**，违反会导致：

| 服务 | 多实例后果 |
|------|-----------|
| **Celery Worker** | 同一任务被两个 Worker 消费 → 两次 agent.assign → 冲突 |
| **Celery Beat** | 定时任务被重复触发 → PENDING 扫描双倍、心跳检查双倍 |
| **Daphne** | 端口冲突、Channel Layer 消息路由错乱 |
| **Agent** | 同一 agent_id 两个 WS 连接 → 消息路由到错误连接 |
| **Redis** | 多实例导致数据不一致（GAF 单 Redis 实例） |
| **Frontend** | 端口冲突（Vite 默认单一实例） |

### 5.2 实现方式

`gaf_daemon.py` 通过两个层面保证唯一性：

1. **启动前杀旧实例**: 按命令行匹配 + 端口匹配，强制杀死
2. **启动后验证**: 轮询端口监听或 Redis PING，确认新实例已取代旧实例

```bash
# 进程匹配规则（简化，gaf_daemon.py 内部逻辑）
stop_service:
  redis:    按命令行 redis-server 匹配, 再按端口 6379 匹配
  backend:  按命令行 daphne 匹配, 再按端口 8000 匹配
  frontend: 按命令行 vite 匹配, 再按端口 5173 匹配
  agent:    按命令行 python -m src 匹配
```

### 5.3 特殊情况：Agent 锁文件

Agent 启动时使用 `--skip-singleton-check` 跳过内置锁文件检查，依赖 `gaf_daemon.py` 的停止旧实例逻辑确保唯一性。启动前清理残留锁文件（由 `gaf_daemon.py` 的 `ServiceManager` 自动处理）。

## 6. 故障排查指南

当系统"卡住"（任务提交后无响应）时，按以下步骤排查：

### 6.1 快速检查清单

```
□ 1. python scripts/gaf_daemon.py status → 所有服务是否都在运行？
   （检查 redis / backend / agent / frontend）
□ 2. Celery Worker 是否注册到 Redis？（生产模式）
   → redis-cli SMEMBERS "celery.worker-online" 应返回 worker1@...
□ 3. Celery Beat 是否存活？（生产模式）
   → 检查进程是否存在，检查 beat_schedule 任务是否触发
□ 4. Redis 是否响应？
   → redis-cli ping → PONG
□ 5. Daphne 端口是否监听？
   → netstat -ano 2>/dev/null | grep ":8000 " | grep LISTENING
□ 6. Agent 是否通过 WebSocket 连接？
   → grep "已连接到 Server" agent/logs/agent.log
□ 7. 任务是否卡在 PENDING？
   → 检查 TaskExecution 表，是否有 PENDING 超过 5 分钟的执行
```

### 6.2 分场景排查

#### 场景 A：任务提交后一直 PENDING

```
可能原因：
  ① Celery Worker 未启动 → 启动 Worker
  ② Worker 启动但未注册到 Redis → 检查 Worker 日志
  ③ 无可用 Agent（Agent 全 OFFLINE）→ 检查 Agent 连接
  ④ 所有 Agent 并发满载 → 等待或添加更多 Agent
  ⑤ 设备忙（同一设备已有 RUNNING 执行）→ 等待设备释放
  ⑥ retry_pending_executions 未触发 → 检查 Beat 是否运行

排查命令：
  # 检查 Worker 是否注册
  redis-cli -h 127.0.0.1 -p 6379 SELECT 1 ; SMEMBERS "celery.worker-online"

  # 检查 Agent 状态
  conda run -n gaf python -c "
  from agents.models import Agent
  for a in Agent.objects.all(): print(a.agent_id, a.status, a.last_heartbeat)
  "

  # 检查 PENDING 执行
  conda run -n gaf python -c "
  from tasks.models import TaskExecution
  stuck = TaskExecution.objects.filter(status='pending')
  for e in stuck: print(e.id, e.created_at, e.recovery_attempts, e.error_message)
  "
```

#### 场景 B：Agent 已分配任务但未执行

```
可能原因：
  ① Agent 进程崩溃 → 检查 agent.log
  ② WebSocket 连接断开 → 检查 Agent 重连日志
  ③ Agent 内 pipeline 执行异常 → 检查 debug 目录下的 run.log

排查命令：
  # 检查 Agent 日志
  tail -20 agent/logs/agent.log 2>/dev/null || grep -n "" agent/logs/agent.log | tail -20

  # 检查执行 debug 目录
  ls -dt debug/*/ 2>/dev/null | head -5
```

#### 场景 C：服务频繁重启

```
可能原因：
  ① 端口冲突（旧进程未杀死）→ 手动 taskkill /F 后重启
  ② 内存不足 → 检查系统资源
  ③ 代码错误导致崩溃 → 检查事件查看器或进程日志

排查命令：
  # 查看进程启动历史
  wmic process where "Name='python.exe'" get ProcessId,CommandLine /format:list 2>/dev/null | grep -E "celery|daphne|src"
```

### 6.3 恢复命令速查

```bash
# 查看所有服务状态
python scripts/gaf_daemon.py status

# 重启所有服务（先杀旧实例，再按顺序启动）
python scripts/gaf_daemon.py restart

# 启动守护进程（看门狗模式，自动重启崩溃的服务）
python scripts/gaf_daemon.py daemon

# 停止所有服务
python scripts/gaf_daemon.py stop

# 兼容层：也支持通过 gaf_services.ps1 操作
.\scripts\gaf_services.ps1 status
```

### 6.4 已知限制

- Redis 崩溃后，开发模式 (APScheduler) 需重启 Daphne 进程，生产模式 (Celery) 需重启 Worker/Beat
- `retry_pending_executions` 最大重试 5 次，超过后需人工介入
- `gaf_daemon.py` 已内置 monitor 模式，`scripts/gaf_services.ps1` 不再需要外部 wrapper
- 多 Agent 场景下，concurrency controller 跨进程状态不同步（N197 已跳过设备绑定场景）
- 开发模式下 APScheduler 内嵌在 Daphne 进程中，Daphne 崩溃后 APScheduler 随即不可用

---

## 7. Pipeline 引擎执行优化 (2026-08-02)

### 7.1 执行架构

Agent 端 Pipeline 执行由 `PipelineEngine` (agent/src/engine/pipeline_engine.py) 驱动，线性执行节点图中的每个节点，支持 pause/resume/cancel 控制。

```
PipelineEngine.execute()
    ↓
while 循环 (遍历节点图)
    ↓
执行节点: 预检查 → 前置延迟 → 节点执行 → 重试 → 回退 → 后验证 → 后置延迟
    ↓
JSONL 结构化日志 (node.execute.start / complete)
    ↓
解析下一个节点 (branch/goto/loop/默认边)
    ↓
继续循环 / 结束
```

### 7.2 性能瓶颈 (优化前)

| 瓶颈 | 模块 | 每节点开销 | 20 节点 Pipeline 累计 |
|------|------|-----------|---------------------|
| **ThreadPoolExecutor 新建/销毁** | pipeline_engine.py L871-L899 | ~10-50ms | 200-1000ms |
| `_truncate_dict` 重复计算 | pipeline_engine.py L857 (start 事件) | ~1-5ms | 20-100ms |
| **JSONL 文件 open/close 每事件** | structured_logger.py L373-L410 | ~2-5ms | 40-100ms (主写) + 40-100ms (镜像) |
| `_vars_snapshot` 全量迭代 | pipeline_engine.py L938-L962 | ~1-3ms | 20-60ms |
| `_truncate_result_data_priority` | pipeline_engine.py L992-L994 | ~1-3ms | 20-60ms |

### 7.3 优化措施 (2026-08-02)

#### 7.3.1 复用 ThreadPoolExecutor (高收益)

**问题**: 每个节点执行都创建 `concurrent.futures.ThreadPoolExecutor(max_workers=1)`，提交任务、等待结果、关闭线程池。Python 线程池创建/销毁开销约 10-50ms。

**解决方案**: 
- 在 `execute()` 方法开始前创建一个可复用线程池，整个 Pipeline 执行期间共享
- 仅当节点显式配置了 `timeout` 字段时才使用线程池执行（超时保护）
- 无自定义 timeout 的节点在主线程直接执行，完全避免线程池开销

```python
# 优化前: 每个节点新建/销毁线程池
executor = ThreadPoolExecutor(max_workers=1)
try:
    future = executor.submit(self._execute_node_step, node)
    result = future.result(timeout=step_timeout)
finally:
    executor.shutdown(wait=False)

# 优化后: 复用线程池，仅自定义 timeout 时使用
if "timeout" in node.config:
    future = _reusable_executor.submit(self._execute_node_step, node)
    result = future.result(timeout=step_timeout)
else:
    # 主线程直接执行，0 线程池开销
    result = self._execute_node_step(node)
```

**预期收益**: 20 节点 Pipeline 减少 200-1000ms 调度开销。

#### 7.3.2 缓存截断的 node config (中收益)

**问题**: 每个节点的 `node.execute.start` 事件都调用 `_truncate_dict(node.config, max_chars=2000)`，循环节点中同一节点反复截断。

**解决方案**: 在 `execute()` 局部缓存 `_truncated_config_cache: dict[str, Any]`，按 node.id 缓存截断结果。

**预期收益**: 循环节点减少 50%+ 重复计算。

#### 7.3.3 JSONL 文件句柄保持打开 (中收益)

**问题**: 每次 `_write_line` 调用都 `open(self._file_path, "a", encoding="utf-8")` 打开文件、写入一行、关闭文件。Windows 下文件 open/close 开销约 2-5ms/次。40+ 次写入 (20 节点 × 2 事件) + 镜像双写 = 80+ 次 open/close，累计 ~160-400ms。

**解决方案**: 
- `StructuredLogger.__init__` 预打开文件句柄并缓存到 `self._file`
- `_write_line` 使用缓存句柄直接写入 (`self._file.write(line)`)，仅当句柄失效时重新打开
- `_maybe_rotate_for_hour` 小时切换时关闭旧句柄 (新句柄在下次写入时打开)
- `close()` 时关闭缓存句柄
- 镜像写保持 open/close 模式 (频率低，不影响主路径)

```python
# 优化前: 每次写入 open/close
with self._lock, open(self._file_path, "a", encoding="utf-8") as f:
    f.write(line)

# 优化后: 使用缓存句柄
with self._lock:
    if self._file is None:
        self._file = open(self._file_path, "a", encoding="utf-8")
    self._file.write(line)
    self._file.flush()
```

**预期收益**: 20 节点 Pipeline 减少 ~160-400ms 文件 I/O 开销 (主写 + 镜像)。

#### 7.3.4 其他优化

- **Pipeline 执行模式**: `PipelineEngine` 保持线性执行（与 `ParallelExecutor` 的 DAG 并行执行互补），确保简单 pipeline 的开销最小

### 7.4 适用场景

| 场景 | 优化前耗时 | 优化后耗时 | 提升 |
|------|-----------|-----------|------|
| 10 节点线性 Pipeline (无自定义 timeout) | ~500ms + 节点执行时间 | ~100ms + 节点执行时间 | ~5x 调度开销降低 |
| 20 节点线性 Pipeline (无自定义 timeout) | ~1000ms + 节点执行时间 | ~200ms + 节点执行时间 | ~5x 调度开销降低 |
| 10 节点 Pipeline (含 3 个自定义 timeout 节点) | ~500ms + 节点执行时间 | ~200ms + 节点执行时间 | ~2.5x 调度开销降低 |
| 循环节点 (5 次迭代, 同一节点重复执行) | ~250ms 线程池开销 | ~50ms 线程池开销 | ~5x |

### 7.5 已知限制

- 无自定义 timeout 的节点放弃超时保护，依赖节点内部自身超时机制
- `executor.shutdown(wait=False)` 不等待后台线程，挂起的线程在进程退出时清理
- JSONL 缓存句柄在进程异常退出时可能丢失最后几行（与 `flush()` 间隔有关），但通常不影响 LLM 诊断
- `PipelineEngine` 不支持 DAG 并行执行（`ParallelExecutor` 在 `graph.py` 中独立实现，供需要并行分支的 pipeline 使用）

---

## 8. 性能计量系统 (2026-08-02)

### 8.1 概述

GAF 提供全链路性能计量能力，覆盖 Agent 端和 Backend 端的关键环节。核心组件：

- **Timer**: 上下文管理器，自动测量代码块执行时间并记录到 PerformanceMonitor
- **PerformanceMonitor**: 按进程隔离的全局单例，支持开发模式（JSONL 输出 + 内存聚合）和生产模式（仅内存聚合）

### 8.2 架构图

```
┌─ Agent 进程 ──────────────────────────────────────────┐
│  PipelineEngine.execute()                              │
│    ├─ Timer("pipeline.node.screenshot")                │
│    ├─ Timer("pipeline.node.template_match")            │
│    ├─ Timer("pipeline.node.ocr")                       │
│    ├─ Timer("pipeline.node.coord_transform")           │
│    └─ perf_summary 事件 (Pipeline 结束时)              │
│                                                        │
│  PerformanceMonitor (单例)                             │
│    ├─ 开发模式: 写入 JSONL + 内存聚合                   │
│    └─ 生产模式: 仅内存聚合                              │
└────────────────────────────────────────────────────────┘

┌─ Backend 进程 ────────────────────────────────────────┐
│  PerfMiddleware (API 请求)                             │
│    └─ Timer("api.request.{method}:{path}")             │
│                                                        │
│  AgentConsumer.receive (WebSocket 消息)                │
│    └─ Timer("ws.message.e2e_latency")                  │
│                                                        │
│  Cursor 包装 (数据库查询)                               │
│    └─ Timer("db.query") + 慢查询日志 (>50ms)           │
│                                                        │
│  Celery 信号 (task_prerun / task_postrun)              │
│    └─ Timer("celery.task.execute")                     │
│                                                        │
│  PerformanceMonitor (单例)                             │
│    └─ API 端点 GET /api/v2/system/perf/ 暴露聚合数据    │
└────────────────────────────────────────────────────────┘
```

### 8.3 测量点清单

| 测量点 | 所在层 | 实现位置 | 触发方式 |
|--------|--------|----------|----------|
| `pipeline.node.screenshot` | Agent | `nodes/template_match.py`, `nodes/ocr.py` | Timer 包装 device.capture_screen() |
| `pipeline.node.template_match` | Agent | `nodes/template_match.py` | Timer 包装 _match_with_scaling() |
| `pipeline.node.ocr` | Agent | `nodes/ocr.py` | Timer 包装 detector.detect() |
| `pipeline.node.coord_transform` | Agent | `utils/coord_transformer.py` | Timer 包装 process_roi() |
| `pipeline.perf_summary` | Agent | `engine/pipeline_engine.py` | Pipeline 结束时汇总 |
| `api.request.*` | Backend | `middleware.py:PerfMiddleware` | 每个 HTTP 请求 |
| `ws.message.e2e_latency` | Backend | `protocol/consumers.py:receive` | Agent 帧附带 sent_at 时间戳 |
| `db.query` | Backend | `signals.py:install_db_query_timing` | 每个 SQL execute() 调用 |
| `celery.task.execute` | Backend | `signals.py:install_celery_task_timing` | task_prerun / task_postrun 信号 |
| `startup.*` | 启动脚本 | `scripts/gaf_daemon.py` | 服务启动计时 |

### 8.4 模式区分

| 维度 | 开发模式 (GAF_CELERY_MODE=eager) | 生产模式 (默认) |
|------|----------------------------------|----------------|
| 粒度 | 全量，每个环节计时 | 仅内存聚合统计 |
| JSONL 输出 | 是 (Agent 端 perf.timer 事件) | 否 |
| API 端点 | 可用 `GET /api/v2/system/perf/` | 可用 (返回 `{mode: "production"}`) |
| 文件写入 | 是 (JSONL 结构化日志) | 否 |

### 8.5 文件结构

```
agent/src/utils/perf_monitor.py       → Timer + PerformanceMonitor (~200 行)
backend/gaf_core/perf_monitor.py       → 后端 PerformanceMonitor (~200 行)
backend/gaf_core/middleware.py         → PerfMiddleware (新增, ~50 行)
backend/gaf_core/views.py              → PerfAPIView (新增, ~30 行)
backend/gaf_core/system_urls.py        → 系统级端点路由 (新增)
backend/gaf_core/signals.py            → DB 查询 + Celery 信号计时 (新增)
backend/gaf_core/apps.py               → ready() 注册信号处理器
```

### 8.6 API 端点

```
GET /api/v2/system/perf/

响应示例:
{
  "mode": "development",
  "uptime_seconds": 3600,
  "aggregates": {
    "pipeline.node.screenshot": {"count": 10, "avg_ms": 123.4, "p50_ms": 100, "p95_ms": 200, "max_ms": 300},
    "api.request.POST:/api/v2/executions/": {"count": 5, "avg_ms": 89.1, "p50_ms": 80, "p95_ms": 120, "max_ms": 150},
    "db.query": {"count": 120, "avg_ms": 5.2, "p50_ms": 3, "p95_ms": 20, "max_ms": 150}
  }
}
```

### 8.7 已知限制

- Agent 端和 Backend 端的 PerformanceMonitor 各自独立，无法跨进程合并
- `ws.message.e2e_latency` 受 `time.time()` 时钟调整影响 (非 monotonic)，但 Agent 和 Backend 在同一台机器上，偏差可忽略
- 生产模式仅内存聚合，重启后丢失
- 数据库查询计时不覆盖 SQLite 的 WAL 合并耗时