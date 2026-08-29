---
summary: GAF 概念关系与命名归一化评估（迭代评估稿；结论稳定后驱动 spec + overview.md 更新 + 代码重命名）
applies_to: ['architecture', 'naming', 'concept', 'evaluation']
status: draft | 创建: 2026-08-29 | 扩展盘点: 2026-08-29（全架构概念 + doc-vs-code 全量核对）| 重新整理: 2026-08-29（代码复核对拍板复核，分离"已锁定决策"与"未决开放问题"）
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
- **代码复核对拍板的修正**：`loop_rotation` 与 `GameAccountRotation` 互补（非冗余，撤销重命名）；`TaskStep` 实为运行期步骤（非定义期，原 PipelineStep 改名错误）；`Tag` 仅 `resources.Tag` 一个；备份无 ORM 模型（仅 ZIP API）。见 §7 未决。

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
| **Tag** | overview 称 tasks.Tag + resources.Tag | **仅 `resources.Tag`（`resources/models.py:166`）**；tasks 复用 | ⚠️ 文档误称 tasks.Tag | 单一模型 |
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
| D4 | overview:505 | gamestate 列 GameStateRule/GameVersionCheck/GameProfile | 已收敛 `game_profile` FK（spec 已归档） | 时序滞后 | 已解 |
| D5 | （缺章） | 无"线性/链式/循环" | 用户分类口径 | 缺口 | P1 |
| D6 | — | — | — | — | — |
| D7 | overview:121,207 / scheduler:4 | "RotationRule" + 3 类型 | 模型 `GameAccountRotation` + **4 选**(含 by_last_executed) | 标签≠模型+分类错 | P1 |
| D8 | overview:474 vs features:302 | TaskStep / ExecutionStep | **两运行期模型均存在** | 双模型债 | P0/P1 |
| D9 | overview:496 vs features:526 | BackupRecord / BackupJob | 均无 ORM 模型（ZIP API） | 捏造 | P1 |
| D10 | overview:482 vs :502 | AgentSession 属 gaf_ai/protocol | 两独立模型 | 双重归属 | P0/P1 |
| D11 | overview:149,464,739 | Routine / routine.json | = 默认 TaskChain | 别名 | P1 |
| D12 | overview:463 vs :465 | tasks.Tag / resources.Tag | 仅 resources.Tag | 文档误称 | P2 |
| D13 | overview §9 | 缺 9 概念 | features 当真 | 文档缺口 | P1 |
| D14 | overview/features "TraceSpan" | 代码已删，现状 trace_id | 死概念 | P0 |
| D15 | 隐含 AgentToken 实体 | `Agent.agent_token_hash` 字段+端点 | 字段≠实体 | P1 |
| D16 | optimal-solution:144 "373 行" | state_machine.py=354 行 | 数字过时 | P2 |
| D17 | overview:744 "models.py:454" | accounts/models.py:450 | 数字过时 | P2 |
| D18 | concurrency-design:70 "TaskDispatcher" | 无此类；`dispatch_task`+`AgentSelector` | 幽灵符号 | P0 |
| D19 | overview "GafDaemon" / gaf_daemon.py / gaf_services.ps1 | 三渲染 | 命名不一 | P1 |
| D20 | debug-logging S1-S4 | 路径 key / `_status` / 死 hour-bucket / chain-mode 路径 | 内部矛盾 | P2 |
| D21 | concurrency-design S7 | ScreenshotCache 50ms vs RedisScreenshotCache 100ms | TTL 不一致 | P2 |
| D22 | deployment-design S8 | SQLite 配置带 Postgres 字段 | 内部矛盾 | P2 |
| D23 | coordinate-transform / WS 帧 | 转换③名 vs step；`task.assign` vs `task_assign` | 命名不一 | P2 |
| D24 | pre-commit-stages S5/S6 | post-commit 1 vs 2 hook；"24" vs "17" | 计数矛盾 | P2 |
| X1 | architechure-debt-refactor.md | `TaskService.dispatch_task(...)` | 实际 `TaskService.dispatch(...)` | 旧 spec 过时 | P2 |

> 子文档内部不一致 S1–S11 明细见原稿 §6.2（已并入 D20–D24）。

## 5. 已锁定决策（代码核实，待落 spec）

> 以下决策经代码复核实为稳妥，可直接进入 spec 实现阶段。改动量用户已授权不拘。

1. **`ChainManager` → `StateMachineEngine`**（文件 `chain_manager.py`→`state_machine_engine.py`）；文档明确"链式任务=`TaskChain`，与 StateMachineEngine 无关"。**但 `task_type='chain'` 兼容性见 OQ2**。
2. **四 chain 收敛口径**：`TaskChain`(保留) / `chain mode`(标 DEPRECATED) / `ChainManager`→`StateMachineEngine` / `ActionChain`(加"恢复"定语)。
3. **任务分类采纳线性/链式/循环**（overview 新增章）；引擎层改写 `PipelineEngine`/`StateMachineEngine`。
4. **字段改名**：`Device.emulator`→`emulator_brand`；前端 `PerformanceMonitor`→`FrontendPerformanceMonitor`；`GameProfile.default_routine`→`default_task_chain`（端点 `default-routine`→`default-task-chain`）。
5. **轮换策略对齐代码 4 选**（`sequential`/`random`/`by_stamina`/`by_last_executed`）；术语用 `GameAccountRotation`（弃 "RotationRule"）。
6. **`loop_rotation` 保留**（与 GameAccountRotation 互补，非冗余）。
7. **`Tag` 单一 `resources.Tag`**；文档撤销"tasks.Tag"说法。
8. **备份无 ORM 模型**：文档改称"ZIP 快照 API（`/tasks/backup/`）"，删 `BackupRecord`/`BackupJob` 模型名。
9. **`TraceSpan` 从文档删除**，改 `trace_id`；`AgentToken` 文档说明为字段+端点。
10. **子文档 S1–S11 / D19 / D23 / D24 修文档**；`GafDaemon` 为权威名，`gaf_services.ps1` 标"Windows 启停封装"。
11. **overview §9 补 9 概念**（AnomalyPattern 注前端-only）。
12. **UI/目录收敛**：TaskChain UI→`pages/Ops/TaskChains/`；`ScanModal`→`pages/Devices/`；设备发现 `DeviceDiscoveryRegistry` 为权威。

## 6. 严重度总览

| 级 | 项 |
|----|----|
| **P0 正确性** | D1(死 DAG 路径) / D2(ChainManager 名不副实) / D8(双运行期步骤模型) / D10(两 AgentSession) / D14(TraceSpan 死概念) / D18(TaskDispatcher 幽灵符号) |
| **P1 清晰度** | D5/D7/D9/D11/D13/D15/D19 + §3.1 双关 |
| **P2 UI/i18n/文档** | D3/D12/D16/D17/D20–D24/X1 + §3.4 |

## 7. 未决开放问题（需你拍板 — 代码复查看出的真问题）

> 这些是代码复核对"已锁定决策"的修正与真正需要你判断的点。**在以下未决前不写代码**。

- **OQ-1 `graph.py` DAG 能力如何处置？** `PipelineGraph`（`parser.py`）是活图模型，被 validator/pipeline_engine 广泛使用；`graph.py` 的 `DAGExecutor`/`ParallelExecutor` + DAG 工具（`topological_sort`/`get_critical_path` 等）**生产零引用、仅测试**。选项：(a) 删除 `graph.py`（归一化，但丢失"休眠的 DAG 并行"能力）；(b) 保留并标 DEPRECATED（不实线接）；(c) 真正接进 `PipelineEngine`（设计工作量，把 DAG 并行变为可用特性）。这是能力取舍，非纯命名。

- **OQ-2 `ChainManager` 改名范围？** 类是 `StateMachine` 封装（改名 `StateMachineEngine` 无误）。但它经 `task_type='chain'` 注册（`executor.py`），现有任务定义若写 `"task_type": "chain"` 会失效。选项：(a) 仅改类名，保留 `task_type='chain'`（最小破坏）；(b) 类名+`task_type`→`'state_machine'` 并迁移既有任务定义/数据。**你倾向哪种？**

- **OQ-3 `TaskStep` vs `ExecutionStep` 双运行期模型如何归一？** 两者均 FK→`TaskExecution`、字段几乎一致（`ExecutionStep` 多 `node_id`）。真实性技术债：需先查各自被谁写/读（疑似一是旧实现、一是新实现）。选项：(a) 合并为单 `ExecutionStep`（吸收 `node_id`），弃 `TaskStep`；(b) 保留双模型并明确分工（定义期 vs 运行期——但 `TaskStep` 文档写的是"运行期"，需核实是否误用）。**需先量化使用面再定，不能仅凭命名拍板。**

- **OQ-4 两个 `AgentSession` 模型如何归一？** `protocol.AgentSession`(WS agent 会话) 与 `gaf_ai.agent.AgentSession`(LLM 会话) 同名异物，且都有 ViewSet/Serializer。选项：(a) 改名二者（`AgentConnection`/`LLMAgentSession`）；(b) 合并为单模型+`type` 字段（跨域合并有风险）；(c) 仅文档强标注"两个独立模型"，不改代码（最小改动，但命名冲突留在代码）。**API 契约影响，需你定。**

- **OQ-5 整体归一化范围：全量代码重命名 vs 文档+i18n 优先？** 你已说"不在乎改动多少"，但"别急写"。建议先确认：本轮是否**只整理文档/UI 文案/i18n**（代码符号暂不动，避免迁移与 API 契约震荡），把 `ChainManager`/`AgentSession`/`TaskStep` 等重命名留作后续大 spec？还是现在就全量重命名？

- **OQ-6（次要）`rotation_rule` 字段名 vs `GameAccountRotation` 模型** — `UnattendedSession.rotation_rule`(FK) 指向 `GameAccountRotation`（related_name `rotation_rules`）。字段名 `rotation_rule` 与模型 `GameAccountRotation` 略不一致，是否一并对齐（如字段→`rotation_policy`）？影响小，可并入 OQ-5 范围。

## 8. 下一步

1. 你回复 OQ-1~OQ-5（尤其 OQ-2/OQ-3/OQ-4/OQ-5 的取舍）。
2. 结论稳定后拆 `docs/specs/active/` 归一化 spec（按 P0→P2 排期），逐阶段实现并提交。
3. 本稿随结论更新，最终随 spec 归档。
