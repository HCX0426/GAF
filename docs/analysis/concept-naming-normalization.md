---
summary: GAF 概念关系与命名归一化评估（最优方案稿；已结合 docs/architecture 全量文档 + backend/agent/frontend 代码核实，结论 = 最优方案，七维 31 分）
applies_to: ['architecture', 'naming', 'concept', 'evaluation']
status: final-archived | 创建: 2026-08-29 | 扩展盘点: 2026-08-29 | 重新整理: 2026-08-29 | 决策采纳: 2026-08-29 | 二次复核+影响面: 2026-08-29 | 结构核查+七维: 2026-08-29 | 融合重整理: 2026-08-29 | 三 agent 目录审计+批 F: 2026-08-29 | Worker/Agent 术语拆分: 2026-08-29 | **全部落地: 2026-08-30（A/B/C/G/E/D/F + OQ-9 spec 完成；本稿随行归档）**
how_to_use: >
  本文档是"评估稿"，非最终规范。结论稳定后：
  (1) 拆为 docs/specs/active/ 下的归一化 spec（含阶段表）；
  (2) 据此更新 docs/architecture/overview.md（概念章节 + 决策记录）；
  (3) 执行代码/文件重命名与 UI 文案修正。
  本稿只记录"现状 + 差异 + 目标态 + 已锁定决策 + 影响面 + 七维"，不做最终决断。
  范围：仅 docs/architecture/ 下的概念定义（docs/analysis/ 下 evaluation-zxcvbn-replacement.md 与 GAF-vs-* 为对比/评估类文档，不纳入）。
verified_baseline: >
  所有结论均经双重核实：① docs 侧 grep 核对 overview.md(806行)/features-overview.md/concurrency-design.md(§3)/deployment-design.md(§4.2)/
  debug-logging-structure.md/pre-commit-stages.md/coordinate-transform-pipeline.md/cancel-design.md(docs/business/tasks)/architechure-debt-refactor.md(docs/specs/archived/2026-08)；
  ② code 侧全仓 grep 计数（backend/agent/frontend，排除 .git/node_modules/.cache/.trash）+ 模型字段/serializer/migration 核实。
---

# 概念与命名归一化评估（Concept & Naming Normalization — 最优方案稿）

> 协作方式：本稿为迭代评估用。每轮对话补充/修正下方表格与"决策"，稳定后转为 spec。

## 0. 结论速览

- **7 核心概念（Device/Worker/Agent/Window/Emulator/Service/链式/循环）文档 ≈80% 正确**，仅命名层问题。
- **术语拆分（2026-08-29 锁定）**：当前 "Agent" 一词既指"自动化执行节点/进程"又将被未来 AI 模块占用 → **"Agent" 保留给 AI 智能体（未来 `backend/gaf_ai` LangGraph agent），执行节点/进程改称 "Worker"**。三者清晰：**Device**(被控 PC/模拟器) / **Worker**(执行节点/进程) / **Agent**(AI 智能体)。详细见 §1/§2/§5(17)/§9(OQ-10)。
- **全架构概念盘点**：`docs/architecture/` 定义约 80 个概念；除 7 核心外，大量概念存在命名层问题（详见 §3/§5）。
- **最高风险是"同词异义"与"幽灵符号"**：四"chain"并存、`AgentSession`×2（现拆 WorkerSession / AgentSession）、`TaskStep`/`ExecutionStep` 双运行期模型、`ChainManager` 名不副实、`TaskDispatcher`/`TraceSpan`/`graph.py` DAG 文档指向不存在/未接线的代码。
- **已结合代码核实的结构性决策（最优，非权宜）**：
  - `TaskStep` 为遗留死模型（生产零写入），`ExecutionStep` 为事实权威 → **MERGE**（无生产数据丢失）。
  - `GameAccountRotation`（共享配置）与 `loop_rotation`+`rotation_index`（每会话运行时游标）处不同抽象层 → **KEEP 双模型**（合并会破坏复用语义）。
  - `protocol.AgentSession`(Worker WS 会话) → `WorkerSession`；`gaf_ai.agent.AgentSession`(AI 会话) **保留 `AgentSession`**（干净名给 AI）；agent 端 `AgentConnection`→`WorkerConnection`，故无碰撞（批 E-1 已消）。
  - `backend/device_bridge/` 与 `backend/agents/`(→`workers`) 的 Device 抽象三义、`consumers.py` 名不副实、`GAME_PROCESS_NAMES` 重复、docstring 错称等经审计发现（三 agent 目录审计 2026-08-29），新增批 F（见 §9/OQ-9 与 spec naming-f-*）。
- **最优方案七维评分 31（次优 23 / 现状 12），达自决阈值**（§8）。执行顺序 §7 分阶段（先低危 A/B，后高危 C/G 带迁移 + 前端类型重生成）。

## 1. 目标态映射表（code + doc 融合，本稿核心）

> 每个概念：代码现状 → 代码最优；文档现状 → 文档最优；风险（是否触及 API/迁移/前端生成类型）；分批（§7）。"证据"为代码/文档核实锚点。

| 概念/符号 | 代码现状 | 文档现状 | 代码最优 | 文档最优 | 风险 | 分批 | 证据 |
|------|------|------|------|------|------|------|------|
| `ChainManager`(agent) | `chain_manager.py` 类 | "ChainManager 链式执行" | `StateMachineEngine`(+`state_machine_engine.py`) | 链式任务=`TaskChain`，与引擎无关 | 中 | B | agent 内部 102 命中；API/迁移/前端=无 |
| `task_type='chain'` | 字面 52（多无关） | — | `'state_machine'` + 别名 shim | — | 中 | B | 代码已 49 处 `state_machine` |
| `graph.py` DAG | 死代码 | "DAG 执行(ParallelExecutor/DAGExecutor)" | **删除** `graph.py`+测试 | 改指 `PipelineGraph`(`parser.py`) | 低 | A | 外部生产 import=0 |
| `TaskStep` | 遗留死模型（生产零 create） | "TaskStep" | **合并入 `ExecutionStep` 后删** | 执行步骤=`ExecutionStep` | 高 | C | `serializers.py:46` 明文"生产数据走 ExecutionStep" |
| `ExecutionStep` | 运行时唯一写入方 | "ExecutionStep" | 保留为权威（补 `retry_count`） | 保留 | 高(合并方) | C | `protocol/services.py:785` update_or_create |
| `protocol.AgentSession`(WS) | WS 会话模型(服务端, Worker 连接) | 列 gaf_ai/protocol | `WorkerSession`（Worker WS 会话） | Worker WS 会话 | 高 | C-3 | 235 命中含 API/迁移/前端类型 |
| `gaf_ai.agent.AgentSession`(AI) | AI 会话模型 | 同上 | `AgentSession`（**保留干净名给 AI 智能体**） | AI 智能体会话 | 高 | C-3(实际不改名) | 同 235 区域 |
| `Agent`(模型, 执行节点) | `agents/models.py:58` | "Agent（机器/进程）" | `Worker` | 执行节点/Worker | 高 | G | GAF 全仓(agents app 重命名最重) |
| `agent/`(进程目录) | `worker/src/__main__.py` | — | `worker/` | Worker 进程目录 | 高 | G | 目录改名+import |
| `AgentConnection`(agent 端 WS 客户端) | `worker/src/client/connection.py:153` | — | `WorkerConnection` | Worker 连接客户端 | 中 | G | 与 WorkerSession 无碰撞(E-1) |
| `AgentStatus`(agent 端) | `worker/src/core/constants.py:141` | — | `WorkerStatus` | Worker 状态 | 低 | G | |
| `AgentConsumer`(protocol) | `protocol/consumers.py:123` | — | `WorkerConsumer` | Worker WS 消费者 | 中 | G | |
| `AgentToken` | `agents/models.py:134`+端点 | — | `WorkerToken` | Worker 令牌 | 中 | G | |
| `agent_runtime` | `agents/agent_runtime.py` | — | `worker_runtime` | Worker 进程管理器 | 低 | G | |
| `AgentViewSet` | `agents/view_sets/crud.py:38` | — | `WorkerViewSet` | Worker 管理视图 | 中 | G | |
| `run_agent` | `worker/src/__main__.py:436` | — | `run_worker` | 启动 Worker | 低 | G | |
| `AgentLLMClient` | `worker/src/ai/llm_client.py:92` | — | `WorkerLlmClient` | Worker 侧 LLM 客户端 | 低 | G | |
| `AgentSelector` | `tasks/agent_selector.py:132` | — | `WorkerSelector` | 选 Worker | 中 | G | |
| `backend/agents`(app) | Django app `agents` | — | `backend/workers` | Worker app | 高 | G | app 重命名(迁移最重) |
| `Device.emulator`(字段) | `agents/models.py:323` | 与 `device_type='emulator'` 值混淆 | `emulator_brand` | 模拟器品牌 | 高 | C | 40 命中 + `device_type` 值 26 |
| `PerformanceMonitor` | **后端类**(`gaf_core`/`agent`) | 误称前端 TS | 消歧义（如 `PerfMonitor`） | 后端性能监视器 | 中 | B | 53 命中后端为主，前端仅 1 |
| `GameProfile.default_routine` | 字段 | Routine/`routine.json` | `default_task_chain` | 默认任务链 | 高 | C | 183 命中 |
| `default-routine`(端点) | URL | — | `default-task-chain` | — | 高 | C | 21 命中 |
| `GameAccountRotation` | 共享配置模型 | "RotationRule"标签+3类型 | 保留（弃 "RotationRule" 叫法） | 轮换规则（4 选含 by_last_executed） | 中 | D | 跨 4 app 复用 |
| `loop_rotation`/`rotation_index` | 会话运行时游标 | — | 保留（可选改名 `rotation_loop_enabled`） | 循环模式 | 中 | B/D | `scheduler/tasks.py:120/374` 嵌套于 `if rotation_rule:` |
| `GafDaemon`/`gaf_daemon`/`gaf_services` | 守护进程层 | 三渲染 | `GafDaemon` 权威 / `.py` 实现 / `.ps1` 兼容层 | 统一 | 中 | A | 153/57 命中 |
| `TaskDispatcher` | 幽灵（仅 docs 画框） | 架构图框 | **去框** → `dispatch_task` | — | 低 | A | 5 命中全 docs |
| `TraceSpan` | 代码已删残骸 | 无此词（用 trace_id） | 已清 | 链路追踪/`trace_id` | 低 | A | 43 处移除残骸 |
| `task.assign`(WS 帧)/`handle_task_assign`(方法) | 协议帧 `task.assign` ↔ 方法下划线 | 记为文档矛盾 | **统一帧名 + alias 兼容**（wire-contract） | — | 高(协议) | C | `connection.py:870` `"task.assign": handle_task_assign`；`task.dispatch` 亦别名 |
| `TaskChainNode`(backend)/`PipelineNode`(agent) | 两结构（持久化链节点 vs 运行时节点） | "Node"过载 | **保留双结构 + 文档显式区分**（可选 agent `PipelineNode`→`AgentNode`） | 明确三层节点(backend Pipeline/TaskChainNode + agent PipelineNode) | 中(可选高) | D | `pipeline/models.py:274` vs `engine/node.py`；不同层非同物 |
| `get_unified_logical_rect`(方法)/`publish_match_pos`(trace step) | 方法名 vs 追踪 step 值 | 记为"名不一致" | **不改名**（异物） | 文档说明：转换③=`get_unified_logical_rect`，追踪 step=`publish_match_pos` | 低(文档) | D | `coord_transformer.py:454` vs `target.py:111` |
| `DeviceInfo`(DTO×3) | `device_bridge/platforms/base.py:32` + `worker/src/devices/discovery/base.py:13` + `DeviceInfoView`(`backend/agents/view_sets/app_info.py:406`) | 三义(2 DTO + 1 端点) | 端点 `DeviceInfoView`→`DeviceDetailView`；两 DTO 文档区分 | 中 | F | 三处同名词(审计 F-1) |
| `DeviceCenter`(agent)/`PlatformDeviceDiscoverer`(bridge) | agent 运行时设备管理 vs backend 设备发现接口 | center/bridge/discovery 分词 | 文档显式区分两层发现 | 中 | F | 互补非同物(审计 F-2) |
| `backend/agents/consumers.py` | 仅 `AdbLogStreamConsumer` | 名不副实(无 AgentConsumer) | 改名 `worker_consumers.py`(路由更新) + 注 WorkerConsumer 在 protocol | 中 | F | 审计 F-5 |
| `GAME_PROCESS_NAMES` | `device_bridge/discovery/windows.py:17` + `platforms/windows/discovery.py:14` | 重复 | 单一来源 | 低 | F | 审计 F-3 |
| `device_bridge/__init__.py` docstring | "GAF Agent 模块" | 错称 | 改设备抽象层说明 | 低(文档) | F | 审计 F-4 |

> 说明：`get_unified_logical_rect` 与 `publish_match_pos` 不是同一符号（前者是坐标转换方法，后者是识别节点发布匹配位置的 trace step 值），**不应重命名**，仅文档澄清。

## 2. 概念关系梳理（7 核心，与代码对照）

| 概念 | 代码实际所指 | 文档 | 备注 |
|------|------------|:---:|------|
| **Device** | `backend/agents/models.py:178` `Device`（改名后 `workers.Device`）；`device_type ∈ {windows, emulator}` | ✅ | 被控设备，正确 |
| **Window** | `device_type='windows'` 子类型；靠 `window_handle` | ✅ | 一致 |
| **Emulator** | `device_type='emulator'` + 自由文本 `Device.emulator`（品牌字段 L323）；Android 真机归入 emulator | ✅ | 一致 |
| **Worker（执行节点/进程）** | `agents/models.py:58` `Agent`→`Worker` 模型；`agent/`→`worker/` 进程；WS 客户端 `WorkerConnection` | ✅(改名后) | 自动化执行节点；连 backend、持令牌、在 Device 上跑 Pipeline |
| **Agent（AI 智能体）** | `backend/gaf_ai` LangGraph agent；其会话 `gaf_ai.agent.AgentSession`→保留 `AgentSession` | ⚠️ 待建 | **未来 AI 模块**；与 Worker 不同物（OQ-10） |
| **Service** | 无 DB 模型；`SERVICE_ORDER=[redis,backend,agent,frontend]` | ✅ | 一致 |
| **链式任务 chain** | ① backend `TaskChain`（`pipeline/models.py:96`，持久化序列）；② agent `ChainManager`（`engine/chain_manager.py:20`，实为 `StateMachine` 封装） | ⚠️ | 同名异物，见 §5/§1 |
| **循环任务 loop** | ① Pipeline `LoopNode`；② 无人值守 `loop_rotation`（UnattendedSession 布尔）+ `rotation_index`；③ TaskChain 循环依赖检测 | ⚠️ | 三义，见 §5 |

### 2.1 任务分类口径（线性/链式/循环 → 归一执行）

| 用户分类 | 代码所指 | 归一执行点 |
|---------|---------|-----------|
| **线性** | 普通 `Task`（定义=单线性 Pipeline，`PipelineEngine` 线性执行） | `TaskExecutor` + `dispatch_task` |
| **链式** | backend `TaskChain`（有序 `TaskChainNode`，node_type∈task/pipeline） | 同上 |
| **循环** | Pipeline `LoopNode` + 无人值守 `loop_rotation` | 同上 |

> **GAP**：文档未用"线性/链式/循环"分类，而用引擎"三模式"（`PipelineEngine`/`ChainManager`/`StateMachine`）。两轴不同；"链式"被引擎三模式的 `ChainManager` 抢注。overview 新增"任务分类"章，引擎层改写 `PipelineEngine`/`StateMachineEngine`（§5）。

## 3. 全概念盘点（高信号项状态表）

| 概念 | 文档名 | 代码符号 | 状态 | 备注 |
|------|--------|---------|:---:|------|
| **Routine** | `default_routine`/`routine.json` | `GameProfile.default_routine` FK→`TaskChain`（`gamestate/models.py:53`） | ✅ D11 已解 | C 批已改 `default_task_chain`；文档无 Routine 残留 |
| **RotationRule** | 核心表"轮换规则(RotationRule)" | 模型 `GameAccountRotation`（`scheduler/models.py:4`） | ❌ 标签≠模型 | 见 §5 |
| **轮换策略** | overview 3 种 / features 3 种+松散"4 种" | 代码 **4 选** `sequential`/`random`/`by_stamina`/`by_last_executed` | ❌ 两文档均漏 by_last_executed | 见 §4-D7 |
| **loop_rotation** | — | `UnattendedSession.loop_rotation`+`rotation_index`（每会话运行时）FK→`GameAccountRotation` | ✅ 互补 | 与 GameAccountRotation 非冗余（代码核实最优 KEEP） |
| **TaskStep / ExecutionStep** | overview "TaskStep" / features "ExecutionStep" | `TaskStep`=遗留死模型；`ExecutionStep`=运行期权威 | ❌ 双运行期模型 | 代码核实：MERGE（§5/§1） |
| **BackupRecord / BackupJob** | overview/features 各一 | **均无 ORM 模型**；备份=ZIP 快照 API（`tasks/backup_views.py`） | ❌ 文档捏造 | 文档应改备份 API |
| **WorkerSession / AgentSession** | 列于 gaf_ai + protocol | `protocol.AgentSession`(Worker WS 会话)→`WorkerSession`；`gaf_ai.agent.AgentSession`(AI 会话)→保留 `AgentSession` | ❌ 双重归属 | 见 §5/§1/OQ-10 |
| **Session×4** | UserSession/WorkerSession/AgentSession/UnattendedSession | 均存在 | ⚠️ 过载 | 同词 4 义（OQ-4 已解） |
| **Account** | "账户"兼 User/GameAccount | `accounts/models.py` | ⚠️ 过载 | — |
| **Node** | TaskChainNode / Pipeline 引擎 nodes | 后端 `TaskChainNode`；agent `PipelineNode`（`engine/node.py:75`） | ⚠️ 过载(两套层) | 见 §1（非同物，文档区分） |
| **Recovery** | recovery.py/RecoveryLog/RecoveryStrategy/recovery_engine.py | `RecoveryLog`(scheduler)/`recovery_engine`(scheduler)/`recovery` 模块存在 | ⚠️ 过载 | — |
| **PerformanceMonitor** | dispatch-flow(Py) / concurrency-design(TS) | **后端类** `gaf_core/perf_monitor.py` + agent `utils/perf_monitor.py` | ❌ 同名异物(实为后端) | 见 §1/§5 |
| **Dispatcher / TaskDispatcher** | concurrency-design 画框 "TaskDispatcher" | 无此类；实为 `dispatch_task`+`WorkerSelector` | ❌ 幽灵符号 | 见 §5/§1 |
| **TraceSpan** | — | 代码已删（残骸 43） | ❌ 死概念(仅代码) | 文档无此词，无需改 |
| **WorkerToken**(原 AgentToken) | 似实体 | `Agent.agent_token_hash`→`Worker.worker_token_hash` 字段 + 端点 | ✅ D15 已解（G 批 `worker_token_hash`） | 与 AI `AgentSession.token_hash` 不同物(审计 E-2 修订) |
| **ChainManager** | "链式执行" | `StateMachine` 封装（`chain_manager.py:20`） | ❌ 名不副实 | 见 §5/§1 |
| **StateMachine** | optimal-solution "373 行" | 实际 `worker/src/core/state_machine.py:64`（现 374 行） | ✅ D16 已解（不再断言动态行数） | — |
| **AuditLog** | overview "models.py:454" | 实际 `accounts/models.py:450` | ✅ D17 已解 | — |
| **ScheduledTask** | 列 tasks app | `tasks/models.py:603` | ⚠️ 归属歧义 | — |
| **Pipeline** | Pipeline(JSON)/PipelineEngine/模式/node_type | 均存在 | ⚠️ 一词四义 | — |
| **Tag** | overview 在 tasks/resources 两 app 均列裸 `Tag` | **仅 `resources.Tag`（`resources/models.py:166`）** | ⚠️ 文档暗示双 Tag | 单一模型 |
| **DeviceDiscovery** | `DeviceDiscoveryRegistry` | agent `DeviceCenter.auto_discover`/`EmulatorDiscovery`/`WindowDiscovery` | ⚠️ 双机制 | — |
| **GafDaemon** | overview "GafDaemon" | `gaf_daemon.py`；`gaf_services.ps1` 委托它 | ✅ D19 已解（A 批归一：GafDaemon 权威/.py 实现/.ps1 兼容层） | 见 §1/§5 |
| **Device 抽象三层** | Device(ORM)/DeviceInfo(DTO×2)/DeviceCenter(BaseDevice) | `agents.Device`(`models.py:178`) + `device_bridge`/`agent` 各 DTO | ⚠️ 三抽象 | 见 §1/F 批(审计 F-1/F-2) |
| **AnomalyPattern** | features `AnomalyPatternPanel` | 无模型（用 `LLMAnalysisResult`） | ✅ D13 已解（overview §9.7 注前端-only） | 前端-only |
| **9 个 features-only 概念** | UnattendedStrategy/.../AnomalyPattern | 未在 overview §9 枚举 | ✅ D13 已解（overview §9.7 面板/概念表 2026-08-30） | — |

## 4. 差异与问题清单（统一，带严重度，已逐条 doc+code 核实）

| # | 位置 | 文档说法 | 代码/实际 | 类型 | 级 |
|---|------|---------|---------|------|----|
| D1 | overview:529 / dispatch-flow:609 | `graph.py` DAG 执行 | `PipelineGraph` 在 `parser.py`；`graph.py` DAG 执行+工具**仅测试 import，生产零引用**（外部生产 import=0） | 死路径/未接线 | P0 |
| D2 | overview:559,790 | `ChainManager 链式执行` | `StateMachine` 封装 | 名不副实 | P0 |
| D3 | overview:737 | "Windows + Android + 模拟器" | Android 归入 emulator | 措辞不精确 | P1 ✅ 2026-08-30 已改（device_type∈{windows,emulator}） |
| D4 | overview:505 | gamestate 列 GameState/GameVersionCheck/GameProfile（评估稿曾误记 GameStateRule） | 已收敛 `game_profile` FK（spec 已归档） | 时序滞后 | 已解 |
| D5 | （缺章） | 无"线性/链式/循环" | 用户分类口径 | 缺口 | P1 ✅ 2026-08-30（overview §11.7 任务分类章） |
| D7 | overview:121,207（"RotationRule"标签+3 中文类型）/ features:269,317（sequential/random/by_stamina + 松散"4 种策略"） | 文档两处均列 3 种且 **缺失 `by_last_executed`**；代码实际 **4 选**（scheduler/migrations/0001） | 标签≠模型 + 两文档均漏 1 类型 | P1 |
| D8 | overview:474 vs features:302 | TaskStep / ExecutionStep | `TaskStep`=遗留死模型；`ExecutionStep`=运行期权威（代码核实 MERGE） | 双模型债 | P0 |
| D9 | overview:496 vs features:526 | BackupRecord / BackupJob | 均无 ORM 模型（ZIP API） | 捏造 | P1 |
| D10 | overview:482 vs :502 | AgentSession 属 gaf_ai/protocol | 两独立模型：Worker WS 会话(protocol) / AI 会话(gaf_ai)（代码核实改名） | 双重归属 | P0 |
| D11 | overview:149,464,739 | Routine / routine.json | = 默认 TaskChain | 别名 | P1 ✅（C 批 `default_task_chain`；overview 已无 Routine/default_routine 残留） |
| D12 | overview §9.1 tasks app 与 resources app 两处均列裸 `Tag` | 仅 resources.Tag 一个（tasks 复用） | 文档暗示双 Tag | P2 ✅ |
| D13 | overview §9 | 缺 9 概念 | features 当真 | 文档缺口 | P1 ✅ 2026-08-30（overview §9.7 前端面板/概念表，含 AnomalyPattern 前端-only 注） |
| D14 | 评估稿曾称 overview/features 提 "TraceSpan" | 复核：overview/features/子文档**均无 "TraceSpan" 一词**（用 链路追踪/trace_id）；死模型仅存**代码**(已删，43 残骸) | 文档无此词→文档无需改；代码清理项 | P0(代码) |
| D15 | 隐含 AgentToken 实体 | `Agent.agent_token_hash` 字段+端点 | 字段≠实体（改名 `WorkerToken` 后更清） | P1 ✅（G 批 `worker_token_hash`；overview 已清） |
| D16 | optimal-solution:144 "373 行" | state_machine.py 现 374 行 | 数字过时 | P2 ✅ 2026-08-30（去掉行数断言，注明动态） |
| D17 | overview:747 "models.py:454" | accounts/models.py:450 | 数字过时 | P2 ✅ 2026-08-30（改 :450） |
| D18 | concurrency-design:70 "TaskDispatcher" 框 | 框存在；无类，真实 `dispatch_task` | 幽灵符号 | P0 |
| D19 | overview "GafDaemon" / gaf_daemon.py / gaf_services.ps1 | 三渲染（GafDaemon 权威/.py 实现/.ps1 兼容） | 命名不一 | P1 ✅（A 批归一） |
| D20 | debug-logging S1-S4 | 死 hour-bucket(✓)/chain-mode 路径(✓跨废弃文档)/路径 key task_name vs safe_pipeline(§8.1 已统一为 `<task_name>` ✅ 2026-08-30 D 批 P2)/`_status`(✗架构树无) | 内部矛盾（4 中 3 有据） | P2 ✅ |
| D21 | concurrency-design **§3**（非 S7） | ScreenshotCache 50ms vs RedisScreenshotCache 100ms | TTL 口径已归一（本地秒级 config.cache_ttl=300 vs Redis 毫秒级，50ms 标示意）✅ 2026-08-30 D 批 P2 | P2 |
| D22 | deployment-design **§4.2**（非 S8） | SQLite 配置带 Postgres 字段 | 已改默认 SQLite+WAL（base.py 实参），PG 字段仅 DB_ENGINE 切换时 ✅ 2026-08-30 D 批 P2 | P2 |
| D23 | coordinate-transform / WS 帧 | ① `task.assign`(WS 帧) vs `handle_task_assign`(方法) = **代码级协议命名漂移**（见 §1）；② `get_unified_logical_rect`(方法) vs `step=publish_match_pos`(trace 值) = **异物，仅文档澄清** | 命名不一(①)/文档精度(②) | P2 |
| D24 | pre-commit-stages **§1/§4.2/§3.1**（非 S5/S6） | post-commit 1 vs 2 hook；"24" vs "17" | 计数已归一：24 总 / commit 热路径 18（6 模块）✅ 2026-08-30 D 批 P2（含 batch docstring） | P2 |
| X1 | docs/specs/archived/2026-08/architechure-debt-refactor.md 写 `TaskService.dispatch_task(...)` | 代码确证（D 批 P2，2026-08-30）：`TaskService.execute_task` 经 `tasks.tasks.dispatch_task` 模块函数派发（B1 收敛 2026-08-27，`worker_resolver.py`/`dispatch-flow.md`）；归档 spec 表述成立，归档文件冻结不改 | 旧 spec 表述存疑 | P2 ✅ 已确证 |

> 子文档内部不一致 S1–S11 明细已并入 D20–D24。

## 5. 已锁定决策（code+doc 核实，待落 spec；用户授权不拘改动量）

> 以下决策经代码复核实为最优（非权宜），可直接进入 spec 实现阶段。

1. **`ChainManager` → `StateMachineEngine`**（文件 `chain_manager.py`→`state_machine_engine.py`）；文档明确"链式任务=`TaskChain`，与 StateMachineEngine 无关"。`task_type` `'chain'`→`'state_machine'`+别名 shim（不破坏既有帧）。
2. **四 chain 收敛口径**：`TaskChain`(保留) / `chain mode`(标 DEPRECATED) / `ChainManager`→`StateMachineEngine` / `ActionChain`(加"恢复"定语)。
3. **任务分类采纳线性/链式/循环**（overview 新增章）；引擎层改写 `PipelineEngine`/`StateMachineEngine`。
4. **字段/类名改名**：`Device.emulator`(模型字段)→`emulator_brand`（注意与 `device_type='emulator'` 字符串值区分）；后端 `PerformanceMonitor` 类（`gaf_core`/`agent`，实测为后端类非前端 TS）统一命名消歧义；`GameProfile.default_routine`→`default_task_chain`（端点 `default-routine`→`default-task-chain`）。三者均高危（API/迁移/前端类型），见 §7 C 批。
5. **轮换策略对齐代码 4 选**（`sequential`/`random`/`by_stamina`/`by_last_executed`）；术语用 `GameAccountRotation`（弃 "RotationRule"）。文档补 `by_last_executed`（两文档均漏）。
6. **`loop_rotation` 保留**（与 GameAccountRotation 互补，非冗余；**代码核实 KEEP 双模型为最优**，见 §1 OQ-6）。可选表面改名 `rotation_loop_enabled`。
7. **`Tag` 单一 `resources.Tag`**；文档撤销"tasks/resources 双 Tag"暗示。
8. **备份无 ORM 模型**：文档改称"ZIP 快照 API（`/tasks/backup/`）"，删 `BackupRecord`/`BackupJob` 模型名。
9. **`TraceSpan` 从文档删除**（文档本就用 trace_id，无此词），代码移除残骸清理。
10. **子文档 S1–S11 / D19 / D23② / D24 修文档**；`GafDaemon` 为权威名，`gaf_daemon.py` 实现，`gaf_services.ps1` 标"Windows 启停兼容层"。
11. **overview §9 补 9 概念**（AnomalyPattern 注前端-only）。
12. **UI/目录收敛**：TaskChain UI→`pages/Ops/TaskChains/`；`ScanModal`→`pages/Devices/`；设备发现 `DeviceDiscoveryRegistry` 为权威。
13. **（OQ-1~OQ-5 已采纳）**：`graph.py` 删除（OQ-1）；`ChainManager`→`StateMachineEngine`+`task_type` 别名 shim（OQ-2）；`ExecutionStep` 为权威、`TaskStep` 弃用合并（OQ-3，**代码核实 MERGE 最优**：`TaskStep` 生产零写入，`serializers.py:46` 明文）；全量代码归一化分阶段 A→D/G（OQ-5）；`rotation_rule` 不改（OQ-6，**代码核实 KEEP 最优**）。—— OQ-3 为高危（`TaskStep` 192/`ExecutionStep` 218 含 API/迁移/前端），须按 §7 C 批带迁移 + 前端类型重生成。
14. **F1 — "循环任务" ≠ "监控任务"**：代码无"监控任务"类型；"监控"=monitors 子系统 + agent `MonitorManager`（`docs/business/tasks/cancel-design.md:22`）+ pipeline 监控触发节点，与循环任务(`LoopNode`/`loop_rotation`)不同域。文档新增"概念速查"澄清边界（OQ-7）。
15. **F2 — "系统运行标志"非"服务全部在线"**：Header "系统运行状态/运行中"（`HeaderStatusIndicator.tsx`）反映 `system_status_view`（`monitors/views.py:305`）聚合 `overall`：`running` 当且仅当 (a) 全部服务健康 **且** (b) ≥1 Worker/Device online/idle **且** (c) 无 `RecoveryLog` 失败/系统级恢复错误。另有 `InfraHealthPanel`（`/accounts/init/health/`）与 `ServicesPage` 两块独立健康面。文档明确三块语义；前端 Header 标签"系统运行状态"→"系统综合状态"（纯 UI 文案，零 API/代码冲击）；`overall` 逻辑不动（OQ-8）。
16. **（OQ-9 关联）Device 抽象与 device_bridge 命名**：审计 `backend/device_bridge/` + `backend/agents/`(→`workers`) 发现 `DeviceInfo` 三义、`consumers.py` 名不副实、`GAME_PROCESS_NAMES` 重复、device_bridge docstring 错称；新增批 F（spec `naming-f-device-bridge`）收口 F-1~F-9，F-10 双发现权威为设计决策单独立项（OQ-9）。同时校正：`WorkerConsumer`(原 AgentConsumer) 位于 `backend/protocol/consumers.py:123`，**非** `workers` app。
17. **（OQ-10）Worker / Agent 术语拆分（2026-08-29 锁定）**：当前 "Agent" 一词既指执行节点又将被未来 AI 模块占用 → **"Agent" 保留给 AI 智能体（未来 `backend/gaf_ai` LangGraph agent，其会话 `gaf_ai.agent.AgentSession` 保留 `AgentSession`）**；执行节点/进程/客户端/状态/令牌/消费者/视图/运行时/选择器/目录/app 全部改称 **Worker**（见 §1/§2/§9 OQ-10 与批 G）。此拆分消 `AgentConnection` 与 `AgentSession`(后端) 的历史碰撞（E-1），并使 `WorkerToken` 与 `AgentSession.token_hash` 区分清晰（E-2 修订）。

## 6. 严重度总览

| 级 | 项 |
|----|----|
| **P0 正确性** | D1(死 DAG 路径) / D2(ChainManager 名不副实) / D8(双运行期步骤模型→MERGE) / D10(两 AgentSession→WorkerSession/AgentSession) / D14(TraceSpan 死概念→代码已移除,文档无此词) / D18(TaskDispatcher 幽灵符号) |
| **P1 清晰度** | D3/D5/D7/D9/D11/D13/D15/D19 + §3.1 双关 |
| **P2 UI/i18n/文档** | D12/D16/D17/D20–D24/X1 + §3.4 |

## 7. 重命名/删除影响面（实测 grep 计数，2026-08-29）

> 风险 = 是否触及 API 契约(serializers/views/urls) + DB 迁移 + 前端生成类型(`api.generated.ts`/`models/*.ts`)。计数排除 .git/node_modules/.cache/.trash。

| 目标 | 总命中(区域) | API/迁移/前端 | 风险 | 分批 | 处置 |
|------|------|------|------|------|------|
| `graph.py` DAG 符号 | 外部生产 import=0 | 无/无/无 | 低 | A | 直接删 `graph.py`+测试（OQ-1） |
| `ChainManager` | 102(agent14/docs69/tests19) | 无/无/无 | 中 | B | 改名 + 69 处文档同步 |
| `task_type='chain'` | 显式=1(doc)；字面52 多无关 | 需 shim | 中 | B | 代码已 mostly `state_machine`(49)；补 shim+doc |
| `protocol.AgentSession`(WS) | 63 + 前端50 + 文档46 | 有/有/有 | **高** | C-3 | →`WorkerSession` + 迁移 + 前端类型重生成 |
| `gaf_ai.agent.AgentSession`(AI) | 72 + 前端 + 文档 | 有/有/有 | **高** | C-3(不改名) | 保留 `AgentSession`(AI 干净名) |
| `TaskStep` | 192(backend66/front43/test44/doc42) | 有/有/有 | **高** | C | 合并入 `ExecutionStep`，writer/reader 迁移 |
| `ExecutionStep` | 218 | 有/有/有 | **高** | C | 作为权威，吸收 `TaskStep`（补 `retry_count`） |
| `Device.emulator`(字段) | 40 + `device_type='emulator'`值26(易混) | 有/有/有 | **高** | C | →`emulator_brand`；与 device_type 值区分 |
| `PerformanceMonitor` | 53(后端22/agent18/doc12/前端1) | 后端view/url | 中 | B | 实为后端类，统一命名消歧义 |
| `default_routine`(字段)+`default-routine`(URL) | 183 + 21 | 有/有/有 | **高** | C | →`default_task_chain` + 端点 + 前端类型重生成 |
| `TraceSpan` | 43(全代码移除残骸) | 已删 | 低 | A | 代码已移除；文档本用 trace_id，无需改(D14) |
| `TaskDispatcher` | 5(全 docs) | 无 | 低 | A | 文档去幽灵框→`dispatch_task`(X1) |
| `GafDaemon`/`gaf_daemon`/`gaf_services` | 7/153/57 | 无 | 中 | A | `GafDaemon` 权威；`.py` 实现；`.ps1` 兼容层(D19) |
| `Agent`(模型)/`agents`(app)/`agent`(目录)/`Agent*`(符号) | 全仓(agents app 重命名最重) | 有/有/有 | **高** | G | 统称 Worker（见 §1 多行） |
| `loop_rotation`/`rotation_index` | 74(scheduler+前端) | 有/有/有 | 中 | B/D | 保留(OQ-6 最优)；可选改名 `rotation_loop_enabled` |
| `rotation_rule` | 127(scheduler+tasks+audit+前端) | 有/有/有 | **高** | — | OQ-6 已决不改 |
| `task.assign`(WS 帧)/`handle_task_assign` | 协议层（`connection.py:870` 帧 `task.assign` 别名 `task.dispatch`） | wire-contract | **高(协议)** | C | 统一帧名 + alias 兼容（不影响后端方法名 `handle_task_assign`） |
| `TaskChainNode`(backend)/`PipelineNode`(agent) | 两套结构 | 各自 API | 中(可选高) | D | 保留双结构+文档显式区分三层节点；可选 agent `PipelineNode`→`AgentNode` |
| `DeviceInfo`(端点) | `DeviceInfoView` 端点 | 有/无/前端 | 中 | F | →`DeviceDetailView` |
| `backend/agents/consumers.py` | 仅 AdbLogStreamConsumer | 有(路由) | 中 | F | →`worker_consumers.py` |
| `GAME_PROCESS_NAMES` | 2 份(device_bridge 内) | 无 | 低 | F | 单一来源 |
| `device_bridge/__init__.py` docstring | 错称 | 无 | 低(文档) | F | 改设备抽象层 |

**风险分级**：高 = WorkerSession/AgentSession / TaskStep / ExecutionStep / Device.emulator / default_routine / rotation_rule / task.assign(协议) / Agent→Worker 全量；中 = ChainManager / task_type shim / PerformanceMonitor(后端) / GafDaemon / loop_rotation / TaskChainNode-PipelineNode(可选) / DeviceInfo端点 / consumers.py；低 = graph.py / TraceSpan / TaskDispatcher / GAME_PROCESS_NAMES / device_bridge docstring。

**分阶段（呼应 OQ-5，用户授权不拘改动量）**：
- **A 批(低危, 零 API/迁移/前端冲击)**：删 `graph.py`+测试(OQ-1)；文档去 `TaskDispatcher` 幽灵框(X1)；`TraceSpan` 文档已正确无需改(D14)；`GafDaemon` 文档归一(D19)。
- **B 批(中危, agent/后端内部或仅文档)**：`ChainManager`→`StateMachineEngine`(OQ-2)+`task_type` shim；`PerformanceMonitor` 后端类名归一；`loop_rotation` 文档标注（可选改名）。
- **C 批(高危, 必带迁移 + 前端类型重生成)**：`Device.emulator`→`emulator_brand`；`default_routine`→`default_task_chain`(+端点)；`WorkerSession`/`AgentSession`(AI 保留) 改名（C-3）；`TaskStep` 合并入 `ExecutionStep`；`task.assign` 帧名统一+alias。每项：① 后端模型/字段改名 + 生成迁移(兼容别名/数据迁移)；② serializers/views/urls 更新；③ 前端 `api.generated.ts`+`models/*.ts` 重生成；④ 全仓 import 改写；⑤ 后端+前端测试。
- **G 批(最高危, Agent→Worker 术语重构)**：`Agent` 模型→`Worker` + `backend/agents` app→`backend/workers` + `agent/` 目录→`worker/` + `AgentConnection`→`WorkerConnection` / `AgentStatus`→`WorkerStatus` / `AgentConsumer`→`WorkerConsumer` / `AgentToken`→`WorkerToken` / `agent_runtime`→`worker_runtime` / `AgentViewSet`→`WorkerViewSet` / `run_agent`→`run_worker` / `AgentLLMClient`→`WorkerLlmClient` / `AgentSelector`→`WorkerSelector` / `agents.Device`→`workers.Device`。每项带迁移(最重为 app 重命名) + 前端类型重生成 + 全仓改写。
- **D 批(文档收口)**：overview/features/子文档按 §4 修正(D4/D7/D12/D14/X1/章节号) + 概念速查(OQ-7) + 三健康面澄清(OQ-8) + 三层节点区分(TaskChainNode/PipelineNode) + `get_unified_logical_rect`/`publish_match_pos` 文档说明(D23②) + **Worker/Agent(AI) 术语区分章(OQ-10)**。
- **F 批(中低危, device_bridge + Device 抽象命名)**：`DeviceInfoView`→`DeviceDetailView` + DTO 文档区分(F-1)；`device_bridge.discovery.*` 单一扫描源 + 两层发现文档(F-2)；`GAME_PROCESS_NAMES` 去重(F-3)；device_bridge docstring 修正(F-4)；`consumers.py`→`worker_consumers.py` + 路由 + 校正(F-5)；service 形态/私有方法迁出/F-8/F-9 一致性(F-6~F-9)；F-10 双发现权威为设计决策单独立项(OQ-9)。

## 7.1 执行顺序（spec 级，N167 自决后落地）

> 分批原则见 §7。以下将 11 个 spec 落到单条执行序列；高危批必带迁移 + 前端类型重生成。

| 序 | 批 | spec | 风险 | 说明 |
|----|----|------|------|------|
| P1 | 低危（零 API/迁移/前端） | `A` | 低 | 删 `graph.py`(死代码) + 去 `TaskDispatcher` 框 + `GafDaemon` 归一 + `TraceSpan` 残骸 |
| P2 | 中危（agent/后端内部或仅文档） | `B` | 中 | `ChainManager`→`StateMachineEngine` + `task_type` 别名 shim；`PerformanceMonitor` 后端类名；`loop_rotation` 文档标注 |
| P3 | 高危（迁移+前端类型） | `C-device-emulator` | 高 | `Device.emulator`→`emulator_brand` | ✅ 已完成 2026-08-29 |
| P3 | 高危 | `C-default-routine` | 高 | `default_routine`→`default_task_chain` + 端点 | ✅ 已完成 2026-08-29 |
| P3 | 高危 | `C-taskstep-merge` | 高 | `TaskStep` 合并入 `ExecutionStep` | ✅ 已完成 2026-08-30 |
| P3 | 高危 | `C-task-assign` | 高 | `task.assign` 帧名统一 + alias | ✅ 已完成 2026-08-29 |
| P4 | 最高危（Agent→Worker 全量） | `G`（含 `C-agentsession` 的 `WorkerSession` 改名 + `E` 概念落地） | 高 | `Agent` 模型/`backend/agents`→`backend/workers`/`agent/`→`worker/` + 全部 `Agent*` 符号 + 前端类型重生成 | ✅ 已完成 2026-08-30（架构文档 sync 并入 D/OQ-10 章） |
| P5 | 文档收口（反映最终命名） | `D`, `F`（可并行） | 中/低 | D: overview/features/子文档修正 + Worker/Agent 术语章；F: device_bridge + Device 抽象命名 | ✅ 已完成 2026-08-30 |

**依赖与合并说明**：
- `G` depends_on `C-agentsession` + `E`（序列中已满足）。
- `C-agentsession` 的 `protocol.AgentSession`→`WorkerSession` 与 `G` 改同一模型，**合并进 G 一次迁移**，不单独跑；`gaf_ai.agent.AgentSession` 保留不改名。
- `E` 为概念总纲，实际符号改名全部在 `G`，`G` 完成即标记 `E` 完成。
- `D`/`F` 不互相依赖，可在 P4 后并行；建议最后做以反映最终符号名。

## 8. 七维评估（最优方案，N167）

> 三方案打分(1-5)：**A 现状不动** / **B 仅改名不合并步骤** / **C 最优**(改名 + 合并 TaskStep + 保留轮换双模型 + 删 graph.py + 文档澄清 + task.assign 协议统一 + Worker/Agent 拆分)。自决阈值：总分≥19 且领先次优≥5。

| 维度 | A 现状 | B 最小改名 | C 最优 | 说明 |
|------|------|------|------|------|
| 1 架构长远性 | 1 | 3 | 5 | C 消除 P0 歧义、Worker/Agent 拆分预留 AI 空间 |
| 2 全局归一化 | 1 | 3 | 5 | C 概念单一权威 |
| 3 命名一致性(消歧义) | 1 | 4 | 5 | C 双会话/双步骤模型/协议帧/Worker-AI 全消 |
| 4 可维护性 | 2 | 3 | 4 | C 合并遗留步骤模型减债 |
| 5 可测试性 | 2 | 3 | 4 | C 端点合并后更聚焦 |
| 6 迁移/兼容风险(越低越高) | 4 | 4 | 3 | C 高危项带迁移有成本，但可控 |
| 7 长期维护成本(越低越高) | 1 | 3 | 5 | C 债清，长期最低 |
| **合计** | **12** | **23** | **31** | C 领先 B 8 分 ≥5，且 ≥19 → 自决执行 |

**结论**：C（本稿方案，含 Worker/Agent 拆分）满足 N167 自决阈值，**即最优方案**，无需再交用户选 A/B。

## 9. 开放问题（已全部锁定）

- **OQ-1 `graph.py`** — ✅ 删 `graph.py`+测试，文档改指 `PipelineGraph`。
- **OQ-2 `ChainManager`** — ✅ 类→`StateMachineEngine`，`task_type`→`'state_machine'`+别名 shim。
- **OQ-3 `TaskStep`/`ExecutionStep`** — ✅ MERGE（`TaskStep` 遗留死模型，生产零写入；`ExecutionStep` 权威，无生产数据丢失） | ✅ 已完成 2026-08-30
- **OQ-4 两 `AgentSession`** — ✅ `protocol.AgentSession`(Worker WS 会话)→`WorkerSession`；`gaf_ai.agent.AgentSession`(AI 会话)→保留 `AgentSession`（干净名给 AI）。
- **OQ-5 范围** — ✅ 全量代码归一化，分阶段 A→D/G（§7）。
- **OQ-6 `rotation_rule`/轮换模型** — ✅ **KEEP 双模型**（代码核实最优：共享配置 vs 每会话运行时游标，跨层不可合并）。
- **OQ-7 "监控任务"分类** — ✅ 不新增；文档加"概念速查"澄清循环≠监控。
- **OQ-8 "系统运行标志"** — ✅ 文档澄清三块健康面 + Header UI 标签"系统运行状态"→"系统综合状态"（纯文案）；`overall` 逻辑不动。
- **OQ-9 双设备发现权威** — ✅ **已定方案 A（2026-08-30 用户确认）**：agent WS `device.sync` 为 Device 生命周期单一权威；`DeviceRegisterView` 收敛为设置/校正渠道；统一身份键 `find_device_by_identity()` 两端复用；可选周期重扫 `GAF_AUTO_RESCAN_INTERVAL`（默认 0）。实现 spec = `docs/specs/active/2026-08-30-oq9-device-discovery-authority.md`（原批 F-10 单独立项）。
- **OQ-10 Worker / Agent 术语拆分** — ✅ **锁定（2026-08-29）**："Agent" 保留给未来 AI 智能体（`backend/gaf_ai` LangGraph agent，其会话 `AgentSession` 保留）；执行节点/进程/客户端/状态/令牌/消费者/视图/运行时/选择器/目录/app 全部改称 **Worker**（批 G）。Device 保持被控设备。三者清晰：Device / Worker / Agent(AI)。

## 10. 下一步（全部完成）

1. OQ-1~OQ-10 已全锁定（含代码核实的最优结构决策）。 ✅
2. 归一化 spec（A/B/C×4/G/E/D/F + OQ-9）已全部实现并标记完成（2026-08-30）。 ✅
3. 本稿结论已随各 spec 落地回写（§3/§4 全 ✅）；本稿**作为评估结论稿归档**（`docs/specs/archived/2026-08/`），不再作为 active 计划。
