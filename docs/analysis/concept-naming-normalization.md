---
summary: GAF 概念关系与命名归一化评估（迭代评估稿；结论稳定后驱动 spec + overview.md 更新 + 代码重命名）
applies_to: ['architecture', 'naming', 'concept', 'evaluation']
status: draft | 创建: 2026-08-29 | 扩展盘点: 2026-08-29 | 重新整理: 2026-08-29 | 决策采纳: 2026-08-29 | 二次复核+影响面: 2026-08-29 | 结构核查+七维: 2026-08-29（OQ-3 MERGE/OQ-6 KEEP 经代码核查确认为最优; 七维评估 §10 总分31 领先次优8）
how_to_use: >
  本文档是"评估稿"，非最终规范。用户将多次与之交流评估；结论稳定后：
  (1) 拆为 docs/specs/active/ 下的归一化 spec（含阶段表）；
  (2) 据此更新 docs/architecture/overview.md（概念章节 + 决策记录）；
  (3) 执行代码/文件重命名与 UI 文案修正。
  本稿只记录"现状 + 差异 + 问题 + 已锁定决策 + 未决开放问题"，不做最终决断。
  范围：仅 docs/architecture/ 下的概念定义（docs/analysis/ 下 evaluation-zxcvbn-replacement.md 与 GAF-vs-* 为对比/评估类文档，不纳入）。
---

# 概念与命名归一化评估（Concept & Naming Normalization Assessment）

> 协作方式：本稿为迭代评估用。每轮对话补充/修正下方表格与"开放问题"，稳定后转为 spec。

## 0. 现状结论速览

- **7 核心概念（Device/Agent/Window/Emulator/Service/链式/循环）文档 ≈80% 正确**，仅命名层问题。
- **全架构概念盘点（2026-08-29）**：`docs/architecture/` 定义约 80 个概念；除 7 核心外，大量概念存在命名层问题（详见 §4/§5）。
- **最高风险是"同词异义"与"幽灵符号"**：四"chain"并存、`AgentSession`×2、`TaskStep`/`ExecutionStep` 双运行期模型、`ChainManager` 名不副实、`TaskDispatcher`/`TraceSpan`/`graph.py` DAG 文档指向不存在/未接线的代码。
  - **代码复核对拍板的修正**：`loop_rotation` 与 `GameAccountRotation` 互补（非冗余，撤销重命名）；`TaskStep` 实为运行期步骤（非定义期，原 PipelineStep 改名错误）；`Tag` 仅 `resources.Tag` 一个；备份无 ORM 模型（仅 ZIP API）。见 §5/§7。
  - **二次 docs 复核（2026-08-29）**：逐条核对 `docs/architecture/` 实际文件，修正若干误述（D4 GameStateRule→GameState；D7 两文档均缺 `by_last_executed`；D12 文档列裸 `Tag` 非点号记法；D14 文档本无 TraceSpan 一词、死概念仅存代码；X1 架构文档内一致用 `dispatch_task`；D21/D22/D24 章节号标错）。重命名影响面实测见 §9。

## 1. 概念关系梳理（7 核心，与代码对照）

| 概念 | 代码实际所指 | 文档 | 备注 |
|------|------------|:---:|------|
| **Device** | `backend/agents/models.py:178` `Device`；`device_type ∈ {windows, emulator}` | ✅ | §二 L119-123 正确 |
| **Window** | `device_type='windows'` 子类型；靠 `window_handle` | ✅ | 一致 |
| **Emulator** | `device_type='emulator'` + 自由文本 `Device.emulator`（品牌字段 L323）；Android 真机归入 emulator | ✅ | §4.3 L340 已说明 |
| **Agent（机器/进程）** | `agents/models.py:58` `Agent` 模型；agent 端为独立进程，无 `Agent` 类，仅 `AgentConnection` | ✅ | 清晰 |
| **Service** | 无 DB 模型；`SERVICE_ORDER=[redis,backend,agent,frontend]` | ✅ | §13.1 一致 |
| **链式任务 chain** | ① backend `TaskChain`（`pipeline/models.py:96`，持久化序列）；② agent `ChainManager`（`engine/chain_manager.py:20`，实为 `StateMachine` 封装） | ⚠️ | 同名异物，见 §5/§7-OQ2 |
| **循环任务 loop** | ① Pipeline `LoopNode`；② 无人值守 `loop_rotation`（UnattendedSession 布尔）；③ TaskChain 循环依赖检测 | ⚠️ | 三义，见 §5 |

### 1.1 任务分类口径（用户主张：线性/链式/循环 → 归一执行）

| 用户分类 | 代码所指 | 归一执行点 |
|---------|---------|-----------|
| **线性** | 普通 `Task`（定义=单线性 Pipeline，`PipelineEngine` 线性执行） | `TaskExecutor` + `dispatch_task` |
| **链式** | backend `TaskChain`（有序 `TaskChainNode`，node_type∈task/pipeline） | 同上 |
| **循环** | Pipeline `LoopNode` + 无人值守 `loop_rotation` | 同上 |

> **GAP**：文档未用"线性/链式/循环"分类，而用引擎"三模式"（`PipelineEngine`/`ChainManager`/`StateMachine`）。两轴不同；"链式"被引擎三模式的 `ChainManager` 抢注，与用户"链式=TaskChain"混淆。建议 overview 新增"任务分类"章，引擎层改写为 `PipelineEngine`/`StateMachineEngine`（见 §7-OQ2）。

## 2. 全概念盘点（扩展：高信号项状态表）

| 概念 | 文档名 | 代码符号 | 状态 | 备注 |
|------|--------|---------|:---:|------|
| **Routine** | `default_routine`/`routine.json` | `GameProfile.default_routine` FK→`TaskChain`（`gamestate/models.py:53`） | ⚠️ 别名 | "Routine"=默认 TaskChain |
| **RotationRule** | 核心表"轮换规则(RotationRule)" | 模型 `GameAccountRotation`（`scheduler/models.py:4`） | ❌ 标签≠模型 | 见 §5-D7 |
| **轮换策略** | overview 3 种 / features 4 种 | 代码 **4 选** `sequential`/`random`/`by_stamina`/`by_last_executed`（`scheduler/migrations/0001_initial.py:58`） | ❌ 两文档均错 | overview 完全错；features 缺 `by_last_executed` |
| **loop_rotation** | — | `UnattendedSession.loop_rotation` 布尔（`scheduler/models.py:361`）+ `rotation_rule` FK→`GameAccountRotation` | ✅ 互补 | 与 GameAccountRotation 非冗余（引擎二者协同） |
| **TaskStep / ExecutionStep** | overview "TaskStep" / features "ExecutionStep" | **两者均为运行期步骤模型**（`tasks/models.py:441` / `:745`，均 FK→TaskExecution） | ❌ 双运行期模型 | 真实技术债，见 §7-OQ3 |
| **BackupRecord / BackupJob** | overview/features 各一 | **均无 ORM 模型**；备份=ZIP 快照 API（`tasks/backup_views.py`） | ❌ 文档捏造 | 文档应改称备份 API，无模型名 |
| **AgentSession** | 列于 gaf_ai + protocol | **两个独立模型**：`protocol/models.py:6`（WS 会话）/ `gaf_ai/agent/models.py:6`（LLM 会话） | ❌ 双重归属 | 见 §7-OQ4 |
| **Session×4** | UserSession/AgentSession/QASession/UnattendedSession | 均存在 | ⚠️ 过载 | 同词 4 义 |
| **Account** | "账户"兼 User/GameAccount | `accounts/models.py` | ⚠️ 过载 | — |
| **Node** | TaskChainNode / Pipeline 引擎 nodes | 后端 `TaskChainNode`；agent `PipelineNode`（`engine/node.py:75`） | ⚠️ 过载 | 同"节点"两结构 |
| **step vs node** | chain mode 用 step / pipeline 用 node | — | ⚠️ 路径分裂 | — |
| **Recovery** | recovery.py/RecoveryLog/RecoveryStrategy/recovery_engine.py | 均存在 | ⚠️ 过载 | — |
| **PerformanceMonitor** | dispatch-flow(Py) / concurrency-design(TS) | Python 单例 / 前端 TS 类 | ❌ 同名异物 | 见 §7-OQ（改名） |
| **Dispatcher / TaskDispatcher** | concurrency-design 画框 "TaskDispatcher" | 无此类；实为 `dispatch_task`+`AgentSelector` | ❌ 幽灵符号 | 见 §5-D18 |
| **TraceSpan** | overview/features 链路追踪 | 代码已删（`gaf_core/tracing/middleware.py:8`），现状 `trace_id` | ❌ 死概念 | 见 §5-D14 |
| **AgentToken** | 似实体 | 实为 `Agent.agent_token_hash` 字段 + 端点 | ⚠️ 字段≠实体 | — |
| **ChainManager** | "链式执行" | `StateMachine` 封装（`chain_manager.py:20`） | ❌ 名不副实 | 见 §7-OQ2 |
| **StateMachine** | optimal-solution "373 行" | 实际 `agent/src/core/state_machine.py:64` = 354 行 | ⚠️ 行数漂移 | — |
| **AuditLog** | overview "models.py:454" | 实际 `accounts/models.py:450` | ⚠️ 行数漂移 | — |
| **ScheduledTask** | 列 tasks app | `tasks/models.py:603`，概念易误归 scheduler | ⚠️ 归属歧义 | — |
| **Pipeline** | Pipeline(JSON)/PipelineEngine/模式/node_type | 均存在 | ⚠️ 一词四义 | — |
| **Tag** | overview 在 tasks app 与 resources app 两处均列裸 `Tag`（暗示两个） | **仅 `resources.Tag`（`resources/models.py:166`）**；tasks 复用 | ⚠️ 文档暗示双 Tag | 单一模型 |
| **DeviceDiscovery** | `DeviceDiscoveryRegistry` | agent 端 `DeviceCenter.auto_discover`/`EmulatorDiscovery`/`WindowDiscovery` | ⚠️ 双机制 | — |
| **GafDaemon** | overview "GafDaemon" | `gaf_daemon.py`；`gaf_services.ps1` 委托它 | ❌ 三渲染 | 见 §5 |
| **AnomalyPattern** | features `AnomalyPatternPanel` | 无模型（用 `LLMAnalysisResult`） | ❌ 未定义 | 前端-only |
| **9 个 features-only 概念** | UnattendedStrategy/NotificationPreferences/MarketplaceReview/SkillMarketReview/PluginHook/GameAccountGroup/TemplateEffectiveness/RecognizerBenchmark/AnomalyPattern | 未在 overview §9 枚举 | ⚠️ 文档缺口 | — |

## 3. 命名问题（多层）

### 3.1 概念层双关（最该归一）
| 词 | 含义 A | 含义 B | 建议 |
|----|-------|-------|------|
| **chain** | `TaskChain`（编排） | `ChainManager`（StateMachine 封装）/ `chain mode`(废弃) / `ActionChain`(恢复) | 四 chain 收敛（§7-OQ2） |
| **loop** | `LoopNode`（pipeline 内迭代） | `loop_rotation`（账户轮换）/ TaskChain 循环依赖 | UI/文档区分标签 |
| **emulator** | `device_type='emulator'` | `Device.emulator` 品牌字段 | → `emulator_brand` |
| **agent** | `Agent` 模型（机器） | agent 服务探针 | 文档标注 |
| **session** | UserSession/AgentSession/QASession/UnattendedSession | — | 文档加速查表 |
| **node/step** | Pipeline `node` / chain `step` | — | 引擎统一用语 |

### 3.2 代码命名（待定，见未决）
| 位置 | 问题 | 候选 |
|------|------|------|
| `agent/src/engine/chain_manager.py` | 名不副实 | → `state_machine_engine.py`（OQ2） |
| `backend/agents/models.py:323` `Device.emulator` | 双关 | → `emulator_brand` |
| `tasks/models.py` `TaskStep` vs `ExecutionStep` | 双运行期模型 | 合并/弃一（OQ3） |
| `protocol/models.py:6` + `gaf_ai/agent/models.py:6` `AgentSession` | 同名异物 | 改名/合并（OQ4） |
| `frontend` TS `PerformanceMonitor` | 与后端同名 | → `FrontendPerformanceMonitor` |

### 3.3 文件/目录命名
| 位置 | 问题 | 候选 |
|------|------|------|
| TaskChain UI 散落 `Ops/ScheduledTasks`/`GameProfiles/components`/`components/Task` | 不对称 | 收敛 `pages/Ops/TaskChains/` |
| `components/Device/ScanModal.tsx` | 应入 `pages/Devices/` | 移动 |
| 设备发现双路径 | registry + 遗留 Discovery | registry 为权威，Discovery 作 adapter |

### 3.4 UI 显示
| 位置 | 问题 | 候选 |
|------|------|------|
| `DeviceCenterPage.tsx:75-84` | windows 显示英文"Windows" vs emulator 中文"模拟器" | i18n `type_windows`→"窗口" |
| `DeviceCenterPage.tsx:57,263,613` | Android Tab 提交存为 emulator | 加"（归入模拟器）"提示 |
| `NodePropertyPanel.tsx:647` vs `pipeline.ts:179` | Loop 节点 `config.count`/`maxIterations` vs 模型 `max_iterations` | 统一字段名 |

## 4. 差异与问题清单（统一，带严重度）

| # | 位置 | 文档说法 | 代码实际 | 类型 | 级 |
|---|------|---------|---------|------|----|
| D1 | overview:529 / dispatch-flow:609 | `graph.py` DAG 执行(ParallelExecutor/DAGExecutor) | `PipelineGraph` 在 `parser.py`；`graph.py` DAG 执行+工具**仅测试 import，生产零引用** | 死路径/未接线 | P0 |
| D2 | overview:559,790 | `ChainManager 链式执行` | `StateMachine` 封装 | 名不副实 | P0 |
| D3 | overview:734 | "Windows + Android + 模拟器" | Android 归入 emulator | 措辞不精确 | P1 |
| D4 | overview:505 | gamestate 列 GameState/GameVersionCheck/GameProfile（评估稿误记 GameStateRule） | 已收敛 `game_profile` FK（spec 已归档） | 时序滞后 | 已解 |
| D5 | （缺章） | 无"线性/链式/循环" | 用户分类口径 | 缺口 | P1 |
| D6 | — | — | — | — | — |
| D7 | overview:121,207（"RotationRule"标签+3 中文类型）/ features:269,317（sequential/random/by_stamina + 松散"4 种策略"） | 文档两处均列 3 种且 **缺失 `by_last_executed`**；代码实际 **4 选**(sequential/random/by_stamina/by_last_executed, scheduler/migrations/0001) | 标签≠模型 + 两文档均漏 1 类型 | P1 |
| D8 | overview:474 vs features:302 | TaskStep / ExecutionStep | **两运行期模型均存在** | 双模型债 | P0/P1 |
| D9 | overview:496 vs features:526 | BackupRecord / BackupJob | 均无 ORM 模型（ZIP API） | 捏造 | P1 |
| D10 | overview:482 vs :502 | AgentSession 属 gaf_ai/protocol | 两独立模型 | 双重归属 | P0/P1 |
| D11 | overview:149,464,739 | Routine / routine.json | = 默认 TaskChain | 别名 | P1 |
| D12 | overview §9.1 tasks app 与 resources app 两处均列裸 `Tag`（非点号记法） | 仅 resources.Tag 一个（tasks 复用） | 文档暗示双 Tag | P2 |
| D13 | overview §9 | 缺 9 概念 | features 当真 | 文档缺口 | P1 |
| D14 | 评估稿称 overview/features 提 "TraceSpan" | 复核：overview/features/子文档**均无 "TraceSpan" 一词**（用 链路追踪 / trace_id）；死 `TraceSpan` 模型仅存**代码**(已移除，43 处为移除残骸) | 文档无此词→文档无需改；代码清理项 | P0(代码) |
| D15 | 隐含 AgentToken 实体 | `Agent.agent_token_hash` 字段+端点 | 字段≠实体 | P1 |
| D16 | optimal-solution:144 "373 行" | state_machine.py=354 行 | 数字过时 | P2 |
| D17 | overview:744 "models.py:454" | accounts/models.py:450 | 数字过时 | P2 |
| D18 | concurrency-design:70 "TaskDispatcher" | 无此类；`dispatch_task`+`AgentSelector` | 幽灵符号 | P0 |
| D19 | overview "GafDaemon" / gaf_daemon.py / gaf_services.ps1 | 三渲染 | 命名不一 | P1 |
| D20 | debug-logging S1-S4 | 路径 key / `_status` / 死 hour-bucket / chain-mode 路径 | 内部矛盾 | P2 |
| D21 | concurrency-design §3（非 S7） | ScreenshotCache 50ms vs RedisScreenshotCache 100ms | TTL 不一致 | P2 |
| D22 | deployment-design §4.2（非 S8） | SQLite 配置带 Postgres 字段 | 内部矛盾 | P2 |
| D23 | coordinate-transform / WS 帧 | 转换③名 vs step；`task.assign` vs `task_assign` | 命名不一 | P2 |
| D24 | pre-commit-stages §1/§4.2/§3.1（非 S5/S6） | post-commit 1 vs 2 hook；"24" vs "17" | 计数矛盾 | P2 |
| X1 | docs/specs/archived/2026-08/architechure-debt-refactor.md 写 `TaskService.dispatch_task(...)` | 该 spec 与现行 concurrency-design 均写 `dispatch_task`（tasks.py 模块函数）；"实际为 dispatch" 在架构文档内无佐证，需查代码确证 | 旧 spec 表述存疑 | P2 |

> 子文档内部不一致 S1–S11 明细见原稿 §6.2（已并入 D20–D24）。

## 5. 已锁定决策（代码核实，待落 spec）

> 以下决策经代码复核实为稳妥，可直接进入 spec 实现阶段。改动量用户已授权不拘。

1. **`ChainManager` → `StateMachineEngine`**（文件 `chain_manager.py`→`state_machine_engine.py`）；文档明确"链式任务=`TaskChain`，与 StateMachineEngine 无关"。**但 `task_type='chain'` 兼容性见 OQ2**。
2. **四 chain 收敛口径**：`TaskChain`(保留) / `chain mode`(标 DEPRECATED) / `ChainManager`→`StateMachineEngine` / `ActionChain`(加"恢复"定语)。
3. **任务分类采纳线性/链式/循环**（overview 新增章）；引擎层改写 `PipelineEngine`/`StateMachineEngine`。
4. **字段/类名改名**：`Device.emulator`(模型字段)→`emulator_brand`（注意与 `device_type='emulator'` 字符串值区分，见 §9）；后端 `PerformanceMonitor` 类（`gaf_core/perf_monitor.py` + agent `utils/perf_monitor.py`，**实测为后端类非前端 TS**）统一命名消歧义；`GameProfile.default_routine`→`default_task_chain`（端点 `default-routine`→`default-task-chain`）。三者均高危（API/迁移/前端类型），见 §9 分阶段 C 批。
5. **轮换策略对齐代码 4 选**（`sequential`/`random`/`by_stamina`/`by_last_executed`）；术语用 `GameAccountRotation`（弃 "RotationRule"）。
6. **`loop_rotation` 保留**（与 GameAccountRotation 互补，非冗余；二次代码核查确认 KEEP 双模型为最优，见 §7 OQ-6）。
7. **`Tag` 单一 `resources.Tag`**；文档撤销"tasks.Tag"说法。
8. **备份无 ORM 模型**：文档改称"ZIP 快照 API（`/tasks/backup/`）"，删 `BackupRecord`/`BackupJob` 模型名。
9. **`TraceSpan` 从文档删除**，改 `trace_id`；`AgentToken` 文档说明为字段+端点。
10. **子文档 S1–S11 / D19 / D23 / D24 修文档**；`GafDaemon` 为权威名，`gaf_services.ps1` 标"Windows 启停封装"。
11. **overview §9 补 9 概念**（AnomalyPattern 注前端-only）。
12. **UI/目录收敛**：TaskChain UI→`pages/Ops/TaskChains/`；`ScanModal`→`pages/Devices/`；设备发现 `DeviceDiscoveryRegistry` 为权威。

13. **（OQ-1~OQ-5 已采纳 §7 建议）**：`graph.py` 删除（OQ-1）；`ChainManager`→`StateMachineEngine`+`task_type` 别名 shim（OQ-2）；`ExecutionStep` 为权威、`TaskStep` 弃用合并（OQ-3）；两 `AgentSession`→`AgentConnection`/`LLMAgentSession`（OQ-4）；全量代码归一化分阶段 A→D（OQ-5）；`rotation_rule` 不改（OQ-6）。—— 其中 OQ-3/OQ-4 为高危（`AgentSession` 235 命中含 API/迁移/前端类型；`TaskStep` 192 / `ExecutionStep` 218 含 API/迁移/前端），须按 §9 C 批带迁移 + 前端类型重生成执行。

14. **新发现 F1 — "循环任务" ≠ "监控任务"**：代码无"监控任务"任务类型。"监控"在 GAF 指三处不同关切：(a) `monitors` 子系统（`MonitorRule`/`MonitorEvent`/`AlertRule`/`SLAMetric`，运维监控告警）；(b) agent `MonitorManager`（执行期监控线程，`docs/business/tasks/cancel-design.md:22`）；(c) Pipeline 节点"监控触发"（`NodeTypeLibrary.tsx:121`）。循环任务 = `LoopNode` + `loop_rotation`(UnattendedSession) + TaskChain 循环依赖检测，与"监控"不同域。文档需加"概念速查"澄清边界（见 OQ-7）。

15. **新发现 F2 — "系统运行标志"非"服务全部在线"**：Header "系统运行状态/运行中"（`HeaderStatusIndicator.tsx`）反映 `system_status_view`（`monitors/views.py:305`）聚合的 `overall`：`running` 当且仅当 (a) 全部服务健康（`_load_service_health`，任一不健康→降级 `warning`）**且** (b) ≥1 Agent/Device `online`/`idle`（`devices_online>0` 或 `devices_idle>0`）**且** (c) 无 `RecoveryLog` 失败/系统级恢复错误。即"服务全在线"只是必要条件之一。另有两块独立健康面：`InfraHealthPanel`（`/accounts/init/health/`，DB/Redis/Celery/disk/memory）与 `ServicesPage`（服务管理，逐服务 daemon/agent/redis/backend/frontend）。建议文档明确三块"运行/健康"语义（见 OQ-8）。

## 6. 严重度总览

| 级 | 项 |
|----|----|
| **P0 正确性** | D1(死 DAG 路径) / D2(ChainManager 名不副实) / D8(双运行期步骤模型) / D10(两 AgentSession) / D14(TraceSpan 死概念→代码已移除,文档无此词) / D18(TaskDispatcher 幽灵符号) |
| **P1 清晰度** | D5/D7/D9/D11/D13/D15/D19 + §3.1 双关 |
| **P2 UI/i18n/文档** | D3/D12/D16/D17/D20–D24/X1 + §3.4 |

## 7. 开放问题状态（OQ-1~OQ-6 已采纳/已决；新增 OQ-7/OQ-8）

> OQ-1~OQ-6 已采纳/已决（见 §5 决策 13）。OQ-7/OQ-8 经二次 docs 复核与重命名影响面评估（§9），已自行拍板（见下），不再待用户定。

- **OQ-1 `graph.py`** — ✅ 已采纳：删 `graph.py`+测试，文档改指 `PipelineGraph`(`parser.py`)。
- **OQ-2 `ChainManager`** — ✅ 已采纳：类→`StateMachineEngine`，`task_type` `'chain'`→`'state_machine'`+别名 shim。
- **OQ-3 `TaskStep`/`ExecutionStep`** — ✅ 已采纳：`ExecutionStep` 为权威，`TaskStep` 弃用合并。**二次代码核查(2026-08-29)确认此为最优**：`TaskStep` 为遗留死模型（生产代码无 create 路径，仅 tests/seed；`serializers.py` L46 明文"生产数据走 ExecutionStep"），`ExecutionStep` 字段更全(`node_id`/`error_code`/`trace_id`…)且承载 WS 实时推送，为事实权威。MERGE 无生产数据丢失，仅需补 `retry_count` 字段并迁移 4 处读端点——MERGE 即最优，非权宜。
- **OQ-4 两 `AgentSession`** — ✅ 已采纳：`protocol.AgentSession`→`AgentConnection`，`gaf_ai.agent.AgentSession`→`LLMAgentSession`。
- **OQ-5 范围** — ✅ 已采纳：全量代码归一化，分阶段 A→D（见 §5/§6 + §9）。
- **OQ-6 `rotation_rule` / 轮换模型** — ✅ 已决：**保留双模型（`GameAccountRotation` 共享配置 + `UnattendedSession.loop_rotation`/`rotation_index` 运行时状态），不合并**。**二次代码核查(2026-08-29)确认此为最优**：`GameAccountRotation` 跨 4 app 复用（`Task.rotation_rule` FK、多会话共享规则），`loop_rotation`+`rotation_index` 是每会话运行时游标（`scheduler/tasks.py` L120/L374 嵌套于 `if rotation_rule:` 块，循环模式禁用 `all_completed`）。合并会破坏"同规则既可用于一次性也可用于循环"的复用语义并丢失会话级游标——故 KEEP 双模型即最优，非权宜。仅可表面改名 `loop_rotation`→`rotation_loop_enabled`（可选，不改结构）。

- **OQ-7 "监控任务"是否作为任务分类？** ✅ 已拍板：**不新增"监控任务"类型**（选项 a）。二次 docs 复核确认无任何文档将"监控任务"作为任务类型；"监控"=monitors 子系统 + agent `MonitorManager` + pipeline 监控触发节点，三者均非任务类型，与循环任务(`LoopNode`/`loop_rotation`)不同域（见 F1）。处置：文档新增"概念速查"小节，澄清 循环任务 ≠ 监控（与 OQ-8 文档澄清一并处理）。

- **OQ-8 "系统运行标志"语义？** ✅ 已拍板：**(a) 文档澄清 + (b) Header UI 文案改名**（选项 c 拆分三灯出范围，后续另议）。二次 docs 复核确认文档将系统状态建模为多维聚合（`monitors/status` null 容错 / `monitors/services` health-status.json + pid / `monitors/device-health` / `health_checker`），≠"服务全在线"（见 F2）。处置：① 文档明确三块健康面语义（Header overall 复合 / InfraHealthPanel / ServicesPage）；② 前端 Header 指标标签 "系统运行状态"→"系统综合状态"（纯 UI 文案，零 API/代码符号冲击，低风险）；③ `system_status_view` 的 `overall` 聚合逻辑不动。

## 8. 下一步

1. OQ-7/OQ-8 已自行拍板（见 §7），无需再回复。
2. 结论稳定后拆 `docs/specs/active/` 归一化 spec（按 P0→P2 排期，含 OQ-1~OQ-5 采纳项 + F1/F2 文档澄清）。**执行顺序遵循 §9 分阶段：先低危(A/B 批)后高危(C 批，必带迁移 + 前端类型重生成)**。
3. 本稿随结论更新，最终随 spec 归档。

## 9. 重命名/删除影响面（实测 grep 计数，2026-08-29）

> 用户提示"重命名是大事"。以下为全仓实测（排除 .git/node_modules/.cache/.trash）。风险 = 是否触及 API 契约(serializers/views/urls) + DB 迁移 + 前端生成类型(`api.generated.ts` / `models/*.ts`)。

| 目标 | 总命中(区域) | API/迁移/前端 | 风险 | 处置 |
|------|------|------|------|------|
| `graph.py` DAG 符号 | 外部生产 import=0 | 无/无/无 | 低 | 直接删 `graph.py`+测试（OQ-1） |
| `ChainManager` | 102(agent14/docs69/tests19) | 无/无/无 | 中 | 改名 + 69 处文档同步 |
| `task_type='chain'` | 显式=1(doc)；字面52 多无关 | 需 shim | 中 | 代码已 mostly `state_machine`(49)；补 shim+doc |
| `AgentSession`(WS, protocol) | 63 + 前端50 + 文档46 | 有/有/有 | **高** | →`AgentConnection` + 迁移 + 前端类型重生成 |
| `AgentSession`(LLM, gaf_ai) | 72 + 前端 + 文档 | 有/有/有 | **高** | →`LLMAgentSession` + 迁移 + 前端类型重生成 |
| `TaskStep` | 192(backend66/front43/test44/doc42) | 有/有/有 | **高** | 合并入 `ExecutionStep`，writer/reader 迁移 |
| `ExecutionStep` | 218 | 有/有/有 | **高** | 作为权威，吸收 `TaskStep` |
| `Device.emulator`(字段) | 40 + `device_type='emulator'`值26(易混) | 有/有/有 | **高** | →`emulator_brand`；与 device_type 值区分 |
| `PerformanceMonitor` | 53(后端22/agent18/doc12/前端1) | 后端view/url | 中 | 实为**后端类**(gaf_core/agent)，统一命名消歧义 |
| `default_routine`(字段)+`default-routine`(URL) | 183 + 21 | 有/有/有 | **高** | →`default_task_chain` + 端点 + 前端类型重生成 |
| `TraceSpan` | 43(全代码移除残骸) | 已删 | 低 | 代码已移除；文档本用 trace_id，无需改(D14 修正) |
| `TaskDispatcher` | 5(全 docs) | 无 | 低 | 文档去幽灵框→`dispatch_task`(X1) |
| `GafDaemon`/`gaf_daemon`/`gaf_services` | 7/153/57 | 无 | 中 | `GafDaemon` 权威；`.py` 实现；`.ps1` 兼容层(D19) |
| `loop_rotation` | 74(scheduler+前端) | 有/有/有 | 中 | 保留(OQ-6 关联) |
| `rotation_rule` | 127(scheduler+tasks+audit+前端) | 有/有/有 | **高** | OQ-6 已决不改 |

**风险分级**：高 = AgentSession×2 / TaskStep / ExecutionStep / Device.emulator / default_routine / rotation_rule；中 = ChainManager / task_type shim / PerformanceMonitor(后端) / GafDaemon / loop_rotation；低 = graph.py / TraceSpan / TaskDispatcher。

**分阶段（呼应 OQ-5）**：
- **A 批(低危, 零 API/迁移/前端冲击)**：删 `graph.py`+测试(OQ-1)；文档去 `TaskDispatcher` 幽灵框(X1)；`TraceSpan` 文档已正确无需改(D14 修正)；`GafDaemon` 文档归一(D19)。
- **B 批(中危, agent/后端内部或仅文档)**：`ChainManager`→`StateMachineEngine`(OQ-2)+`task_type` shim；`PerformanceMonitor` 后端类名归一；`loop_rotation` 文档标注。
- **C 批(高危, 必带迁移 + 前端类型重生成)**：`Device.emulator`→`emulator_brand`；`default_routine`→`default_task_chain`(+端点)；两 `AgentSession` 改名；`TaskStep` 合并入 `ExecutionStep`。每项：① 后端模型/字段改名 + 生成迁移(带兼容别名或数据迁移)；② serializers/views/urls 更新；③ 前端 `api.generated.ts` + `models/*.ts` 重生成；④ 全仓 import 改写；⑤ 后端+前端测试。
- **D 批(文档收口)**：overview/features/子文档按 §4 修正(D4/D7/D12/D14/X1/章节号) + 概念速查(OQ-7) + 三健康面澄清(OQ-8)。

## 10. 七维评估（最优方案，N167）

> 对三方案打分(1-5)：**A 现状不动** / **B 仅改名不合并步骤** / **C 最优**(改名 + 合并 TaskStep + 保留轮换双模型 + 删 graph.py + 文档澄清)。自决阈值：总分≥19 且领先次优≥5。

| 维度 | A 现状 | B 最小改名 | C 最优 | 说明 |
|------|------|------|------|------|
| 1 架构长远性 | 1 | 3 | 5 | C 消除 P0 歧义、结构更清 |
| 2 全局归一化 | 1 | 3 | 5 | C 概念单一权威 |
| 3 命名一致性(消歧义) | 1 | 4 | 5 | C 双 AgentSession/双步骤模型全消 |
| 4 可维护性 | 2 | 3 | 4 | C 合并遗留步骤模型减债 |
| 5 可测试性 | 2 | 3 | 4 | C 端点合并后更聚焦 |
| 6 迁移/兼容风险(越低越高) | 4 | 4 | 3 | C 高危项带迁移有成本，但可控 |
| 7 长期维护成本(越低越高) | 1 | 3 | 5 | C 债清，长期最低 |
| **合计** | **12** | **23** | **31** | C 领先 B 8 分 ≥5，且 ≥19 → 自决执行 |

**结论**：C（本评估稿方案）满足 N167 自决阈值，**即最优方案**，无需再交用户选 A/B。执行顺序见 §9 分阶段（先 A/B 批低危，后 C 批高危带迁移）。
