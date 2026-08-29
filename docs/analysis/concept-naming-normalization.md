---
summary: GAF 概念关系与命名归一化评估（迭代评估稿，最终驱动 spec + overview.md 更新 + 代码修改）
applies_to: ['architecture', 'naming', 'concept', 'evaluation']
status: draft | 创建: 2026-08-29 | 扩展盘点: 2026-08-29（全架构概念 + 子文档 + doc-vs-code 全量核对）| 来源: 用户要求梳理概念关系与命名归一化
how_to_use: >
  本文档是"评估稿"，非最终规范。用户将多次与之交流评估；结论稳定后：
  (1) 拆为 docs/specs/active/ 下的归一化 spec（含阶段表）；
  (2) 据此更新 docs/architecture/overview.md（概念章节 + 决策记录）；
  (3) 执行代码/文件重命名与 UI 文案修正。
  本稿只记录"现状 + 差异 + 问题 + 可选方向"，不做最终决断。
---

# 概念与命名归一化评估（Concept & Naming Normalization Assessment）

> 协作方式：本稿为迭代评估用。每轮对话补充/修正下方表格与"开放问题"，稳定后转为 spec。

## 0. 现状结论速览

- **文档大框架正确**：`overview.md` 对 Device / Agent / Window / Emulator / Service 的关系描述与代码一致（约 80% 准确）。
- **真正问题在"命名层"**：概念双关（chain / loop / emulator / agent）+ 少量文档↔代码漂移（orphaned `graph.py` 被文档引用、legacy "ChainManager=链式" 命名误导）+ task 分类口径缺失（文档用引擎"三模式"，用户用"线性/链式/循环"）。
- **无阻断性 bug**，均为可渐进归一化的"架构清晰度"债。

## 1. 概念关系梳理（与代码对照）

| 概念 | 代码实际所指 | 文档是否写对 | 备注 |
|------|------------|:---:|------|
| **Device（设备）** | `backend/agents/models.py:178` `Device` 模型；`device_type ∈ {windows, emulator}`（`DeviceType` L181-184）；实为"被控窗口/模拟器实例" | ✅ | §二 命名说明 L119-123 写对 |
| **Window（窗口）** | `device_type='windows'` 子类型；无独立 model；靠 `window_handle`（`Device` L316） | ✅ | 一致 |
| **Emulator（模拟器）** | `device_type='emulator'` 子类型 + 自由文本 `Device.emulator`（品牌字段，L323）；**Android 真机映射为 emulator，无独立枚举** | ✅ | §4.3 L340 已说明"归入 EMULATOR，无独立枚举" |
| **Agent（机器/进程）** | `backend/agents/models.py:58` `Agent` 模型（机器记录）；agent 端为独立进程（`agent/src/__main__.py`），无 `Agent` 类，仅有 `AgentConnection`（connection.py L153） | ✅ | 前后端清晰区分 |
| **Service（服务）** | 无 DB 模型；`backend/monitors/views.py:434` `SERVICE_ORDER=[redis,backend,agent,frontend]` + daemon 由 PID 派生；快照 `debug/health-status.json`（`scripts/services/health.py:46`） | ✅ | §13.1 / §7.8 一致 |
| **链式任务（chain）** | **两层且互不相关却同名**：① backend `TaskChain`（`pipeline/models.py:96`，持久化 Task/Pipeline 序列）；② agent `ChainManager`（`engine/chain_manager.py:20`，实为 `StateMachine` 包装器，`task_type='chain'`） | ⚠️ | 见 §3.1 |
| **循环任务（loop）** | **三重含义共用"循环"**：① pipeline `LoopNode`（`engine/nodes/loop.py:43`，for/while 迭代）；② 无人值守 `loop_rotation`（`scheduler/models.py` `UnattendedSession.loop_rotation` L361-364，账户循环轮换，backend-only）；③ TaskChain 循环依赖检测（`validator.py` 循环检测） | ⚠️ | 见 §3.1 |

### 1.1 任务分类口径（用户主张：线性/链式/循环 → 归一执行）

用户提出的任务结构分类 = **线性 / 链式 / 循环**，三者最终都由统一执行入口收口。代码与文档的真实映射：

| 用户分类 | 代码所指 | 归一执行点（文档已写） |
|---------|---------|----------------------|
| **线性 linear** | 普通 `Task`，其定义为单个线性 Pipeline（`execution_mode="pipeline"`，`PipelineEngine` 线性执行节点图，`dispatch-flow.md:500/593` "PipelineEngine 保持线性执行"）；**无独立 "linear" 类型字段** | `TaskExecutor`（`overview.md:528/748`）+ `dispatch_task`（`dispatch-flow.md:129-150` 归一化） |
| **链式 chain** | backend `TaskChain`（`TaskChainNode` 有序序列，node_type ∈ task/pipeline）；每个节点归一化到 `dispatch_task`（`dispatch-flow.md:148`） | 同上 |
| **循环 loop** | Pipeline `LoopNode`（pipeline 内迭代）+ `loop_rotation`（无人值守账户轮换） | 同上 |

> **关键 GAP**：文档**未用"线性/链式/循环"任务分类口径**，而是用引擎视角的"三模式"：`Pipeline(图执行) + ChainManager(链式) + StateMachine(状态机)`（`GAF-vs-BD2-analysis.md:97/380`；`optimal-solution.md:152-160`）。两轴不同，且"链式"被 engine 三模式的 `ChainManager` 抢注，与用户的"链式=TaskChain"混淆。

## 2. overview.md 与现有代码的差异清单

| # | overview.md 位置 | 文档说法 | 代码实际 | 差异类型 |
|---|----------------|---------|---------|---------|
| D1 | §10.1 L529 | `graph.py # DAG 图执行 (ParallelExecutor, DAGExecutor)` | `engine/graph.py` 的 `DAGExecutor`(L586)/`ParallelExecutor`(L337) **是孤儿死代码，从未被 import**；`PipelineGraph` 在 `parser.py`(L61) 而非 graph.py | 文档引用不存在的执行路径 / 代码有死代码 |
| D2 | §10.1 L559 + §14 L790 | `ChainManager 链式执行`；"Pipeline + ChainManager 并存" | `ChainManager`(`chain_manager.py:20`) 实为 `StateMachine` 封装（`_execute_state_machine` L94，`importlib` 加载用户 module），error 文案自称 "state_machine 模式" | 命名误导（意图正确，名字错） |
| D3 | §13.1 L734 | 设备管理 "Windows + Android + 模拟器" | Android 非独立类型，归入 `emulator`（scan_register.py L357 映射） | 文档措辞不精确 |
| D4 | §二 / §4.3 | Device/Agent/Window/Emulator/Service 关系 | 与代码一致 | 无差异（正确） |
| D5 | （缺失章节） | — | 任务"线性/链式/循环 → 归一执行"未在 overview.md 表述 | 文档缺口（见 §1.1） |
| D6 | §9.5 L505 | gamestate 列 `GameState, GameVersionCheck, GameProfile` | `GameStateRule`/`GameVersionCheck` 的 `game_name` 正被本 spec（game_name 退役）收敛到 `game_profile` FK（P5/P6 已提交 b67b34c） | 时序滞后（P8 验收时会回刷文档） |

## 3. 命名问题（多层）

### 3.1 概念层双关（最该归一）

| 词 | 含义 A | 含义 B | 冲突 | 建议方向（待拍板） |
|----|-------|-------|------|------------------|
| **chain** | backend `TaskChain` = 持久化任务序列（用户的"链式任务"） | agent `ChainManager` = `StateMachine` 封装 | 同名异物，读者必然错认 | 把 agent 端 `ChainManager` → `StateMachineEngine`/`FSMEngine`（见 D2）；文档明确"TaskChain ≠ ChainManager" |
| **loop** | Pipeline `LoopNode`（pipeline 内迭代） | 无人值守 `loop_rotation`（账户轮换）/ TaskChain 循环依赖 | 同一中文"循环"三义 | UI/文档区分标签：循环节点 / 循环轮换 / 循环依赖 |
| **emulator** | `device_type='emulator'`（窗口子类型） | `Device.emulator` 自由文本（品牌 LDPlayer/MuMu） | 同词双义 | `Device.emulator` → `emulator_brand` |
| **agent** | `Agent` 模型（机器记录） | `SERVICE_ORDER` 里的 agent 服务探针 | 同词双义 | 文档显式标注"Agent 模型 vs agent 服务"；探针名可保留 |

### 3.2 代码命名

| 位置 | 问题 | 建议 |
|------|------|------|
| `agent/src/engine/chain_manager.py` | 名不副实（实为 StateMachine 驱动） | 重命名 `fsm_engine.py` / `StateMachineEngine` |
| `agent/src/engine/graph.py`（DAGExecutor/ParallelExecutor） | 孤儿死代码，与 `PipelineEngine`/`validator.py` 重复 DAG 逻辑 | 删除，或接入生产路径（若真要 DAG 并行） |
| `backend/agents/models.py` `Device.emulator` | 与 `device_type='emulator'` 双关 | → `emulator_brand` |
| `backend/monitors/views.py` `SERVICE_ORDER` 中 `"agent"` | 与 `Agent` 模型双关 | 保留但文档标注 |

### 3.3 文件 / 目录命名

| 位置 | 问题 | 建议 |
|------|------|------|
| 前端 `TaskChain` UI 散落 3 处：`Ops/ScheduledTasks/index.tsx`(chains tab)、`Ops/ScheduledTasks/DagEditorPage.tsx`、`GameProfiles/components/TaskChainsTab.tsx`、`components/Task/TaskDependencyGraph.tsx` | 与 `Tasks/PipelineEditor/` 不对称，无独立目录 | 收敛到 `pages/Ops/TaskChains/` 单一目录 |
| `frontend/src/components/Device/ScanModal.tsx` | 置于 components 而非 `pages/Devices/` | 移入 `pages/Devices/` |
| 设备发现双路径并存：`DeviceDiscoveryRegistry`（新）+ 遗留 `EmulatorDiscovery`/`WindowDiscovery`（兼容保留，`center.py:49-50,187,195`） | 两套发现同物 | 收敛到 registry adapter |

### 3.4 UI 显示

| 位置 | 问题 | 建议 |
|------|------|------|
| `DeviceCenterPage.tsx:75-84` | `device_type='windows'` 在中文 locale 显示英文 "Windows"，而 `'emulator'` 显示中文 "模拟器" → 同列中英混排 | i18n：`type_windows` → "窗口" |
| `DeviceCenterPage.tsx:57,263,613` | 添加设备有 "Android" Tab，提交 `agent_type:'android'`，最终存为 `emulator` 标"模拟器" | Tab 文案加"（归入模拟器）"提示 |
| `NodePropertyPanel.tsx:647` vs `pipeline.ts:179` | Loop 节点编辑器写 `config.count`（别名 `maxIterations`），模型默认 key 为 `max_iterations` | 统一字段名，避免静默走默认 |

## 4. 严重度与归一化方向（初步，待你拍板）

| 级 | 项 | 理由 |
|----|----|------|
| **P0 正确性** | D1（orphaned graph.py 引用） | 文档误导读者走不存在的执行路径；要么删死代码要么修文档 |
| **P0 正确性** | D2 + §3.1 chain 双关 | 概念错认风险最高，且贯穿前后端 |
| **P1 清晰度** | §1.1 任务分类口径缺口（线性/链式/循环→归一） | 补一段总览即可，低成本高收益 |
| **P1 清晰度** | §3.1 loop / emulator / agent 双关 | 文档加"概念速查表"澄清 |
| **P2 UI/i18n** | §3.4 三类显示问题 | 纯前端文案/字段对齐 |
| **P3 架构债** | §3.2/§3.3 死代码/双路径/目录收敛 | 改动较大，可后置 |

## 5. 待你评估的开放问题

1. **agent 端 `ChainManager` 是否重命名？** 重命名 `StateMachineEngine` 影响 `executor.py`/`orchestrator.py` 注册键与注释；若保留，则文档必须强标注"≠ TaskChain"。你倾向哪种？
2. **任务分类口径**：是否采纳"线性/链式/循环"作为 overview.md 的正式任务分类（替换/补充引擎"三模式"表述）？
3. **`Device.emulator` → `emulator_brand`** 是否现在就改（跨 serializer/admin/前端），还是仅在文档澄清？
4. **orphaned `graph.py`**：删除死代码，还是接入真实 DAG 并行执行路径？
5. **评估文档落点**：本稿放 `docs/analysis/` 是否同意？稳定后何时拆为 `docs/specs/active/` 归一化 spec？

---

## 6. 全概念盘点（扩展：架构文档其余概念）

> 2026-08-29 扩展：三路并行 explore 扫描 `docs/architecture/`（overview / features-overview / optimal-solution + 7 个子文档）+ 代码（`backend/` `frontend/src/` `agent/src/`）全量核对。结论：**文档定义约 80 个概念，除 7 核心外，下列概念存在命名层问题**。

### 6.1 概念状态总表（节选高信号项）

| 概念 | 文档名 | 代码符号 | 状态 | 备注 |
|------|--------|---------|:---:|------|
| **Routine** | `default_routine` / `routine.json`（`overview.md:L149,L464,L739`） | `GameProfile.default_routine` FK → `TaskChain`（`gamestate/models.py:53`） | ⚠️ 别名未澄清 | "Routine" = 默认 TaskChain，文档两套叫法混用 |
| **RotationRule** | 核心表 "轮换规则 (RotationRule)"（`overview.md:L121,L207`） | 模型实为 `GameAccountRotation`（`gamestate` / `accounts`，`overview.md:L472`,`features-overview.md:L269`） | ❌ 标签≠模型 | 另：`session.rotation_rule` + `loop_rotation`（OV:L781）第三层 |
| **Rotation 类型** | overview 列 3 种（按时间/按任务完成/按失败次数，`L407-411`） | features 列 4 策略 `sequential/random/by_stamina`（`FO:L269,L317`） | ❌ 分类不一致 | 3 vs 4 冲突 |
| **TaskStep / ExecutionStep** | `overview.md:L474` "TaskExecution/TaskStep" | `features-overview.md:L302` `ExecutionStep` | ❌ 同名异物 | 步骤实体命名漂移 |
| **BackupRecord / BackupJob** | `overview.md:L496`（debug app, `BackupRecord`） | `features-overview.md:L526`（settings app, `BackupJob`） | ❌ 同名异物 | 模型名 + app 归属双冲突 |
| **AgentSession** | 同时列于 `gaf_ai`（`L482`）与 `protocol`（`L502`） | 代码确为**两个独立模型**：`protocol/models.py:6`（WS agent 会话）+ `gaf_ai/agent/models.py:6`（LLM agent 会话） | ❌ 双重归属未说明 | 同名异物，文档未澄清是两个模型 |
| **Session（4 模型）** | `UserSession` / `AgentSession` / `QASession` / `UnattendedSession` | 均存在 | ⚠️ 过载 | 同一词 4 义 |
| **Account** | "账户" 兼指 `User`（人）与 `GameAccount`（游戏登录） | `accounts/models.py:81,360` | ⚠️ 过载 | OV:L132 vs L116；FO:L253 vs L266 |
| **Node** | `TaskChainNode`（`OV:L157`）vs Pipeline 引擎 `nodes/`（35+，`OV:L526`） | 后端 `TaskChainNode`；agent `PipelineNode`（`agent/src/engine/node.py:75`） | ⚠️ 过载 | 同一中文"节点"两结构 |
| **step vs node** | chain mode 用 "step"（`chain.step.*`） | pipeline 用 "node"（`node.execute.*`） | ⚠️ 路径分裂 | 同一执行单元两种叫法 |
| **Recovery** | 引擎 `recovery.py` / 日志 `RecoveryLog` / 策略 `RecoveryStrategy` / 引擎模块 `recovery_engine.py` | 均存在 | ⚠️ 过载 | 同根词多产物 |
| **PerformanceMonitor** | `dispatch-flow.md:L619` Python 单例 | `concurrency-design.md:L485` 前端 TS `PerformanceMonitor` 类 | ❌ 同名异物 | 实现/位置/语义全不同 |
| **Dispatcher / TaskDispatcher** | `concurrency-design.md:L70` 画框 "TaskDispatcher (Celery Worker)" | 代码**无此类**；实为 `dispatch_task`（Celery task, `backend/tasks/tasks.py:90`）+ `AgentSelector` | ❌ 幽灵类名 | 文档框标签无对应符号 |
| **TraceSpan** | overview/features 提及链路追踪 | **代码已删除**：`gaf_core/tracing/middleware.py:8` "legacy TraceSpan DB write removed"；现状为 `trace_id` ContextVar | ❌ 死概念 | 文档未更新 |
| **AgentToken** | 读者易以为有 `AgentToken` 实体 | 实为 `Agent.agent_token_hash` 字段（`agents/models.py:134`）+ `AgentTokenViewSet`/`Serializer`/`Authentication`（`accounts/views.py:817` 等） | ⚠️ 字段≠实体 | 文档未说明 |
| **ChainManager** | "链式执行"（`OV:L559,L790`） | `StateMachine` 封装（`chain_manager.py:20`） | ❌ 名不副实 | 见 D2 / §3.1 |
| **StateMachine** | `optimal-solution.md:L144` "373 行完整实现" | 实际 `agent/src/core/state_machine.py:64` 为 **354 行** | ⚠️ 行数漂移 | 文档数字过时 |
| **AuditLog** | `overview.md:L744` "accounts/models.py:454" | 实际 `accounts/models.py:450` | ⚠️ 行数漂移 | 文档数字过时 |
| **ScheduledTask** | 列于 `tasks` app（`OV:L463`） | 确在 `tasks/models.py:603`，但概念上易误归 `scheduler` app | ⚠️ 归属歧义 | scheduler 消费它（`scheduler/views.py:355`） |
| **Pipeline** | "Pipeline"(JSON) / `PipelineEngine`(执行器) / pipeline 模式 / `node_type='pipeline'`(TaskChainNode) | 均存在 | ⚠️ 过载 | 一词四义 |
| **Tag** | `tasks` app `Tag`（`OV:L463`）vs `resources` app `Tag`（`OV:L465`） | 疑似两个独立 Tag 模型 | ⚠️ 可能重复 | 是否共享未说明 |
| **DeviceDiscovery** | `DeviceDiscoveryRegistry`（`OV:L749`） | agent 端 `DeviceCenter.auto_discover` / `EmulatorDiscovery` / `WindowDiscovery`（`OV:L287,L536`） | ⚠️ 双机制 | registry vs center 边界不清 |
| **GafDaemon** | overview 称 "GafDaemon"（`L753`） | 实为 `gaf_daemon.py`；`gaf_services.ps1` 在 deployment-design 称"主入口"，dispatch-flow 称其"兼容层委托 gaf_daemon.py" | ❌ 三处渲染不一 | 三种说法 |
| **AnomalyPattern** | `features-overview.md:L430` `AnomalyPatternPanel` | 无对应模型（异常检测用 `LLMAnalysisResult`，`FO:L456`） | ❌ 未定义概念 | 仅有前端面板 |
| **UnattendedStrategy / NotificationPreferences / MarketplaceReview / SkillMarketReview / PluginHook / GameAccountGroup / TemplateEffectiveness / RecognizerBenchmark** | 仅见于 `features-overview.md` | 未在 `overview.md` §9.1–§9.6 模型清单枚举 | ⚠️ 文档缺口 | features 当真，overview 缺列 |

### 6.2 子文档内部不一致（具体，待修正）

| # | 不一致 | 证据 |
|---|--------|------|
| S1 | 后端 `execution.jsonl` 路径 key：`<task_name>`（debug-logging §1.1 L71）vs `<safe_pipeline>`（§8.1 L536/L539） | 同一文件两种目录键 |
| S2 | 标注 PNG 文件名：§1 目录树缺 `_status`，§4.1 强制含 `_status` | debug-logging L34 vs L360-377 |
| S3 | 诊断命令用从未启用的 hour-bucket 路径 `agent/<pipeline>/HH/`（debug-logging L463-465/L481；coord-transform L330） | 死路径 |
| S4 | chain-mode 文档 JSONL 路径 `<debug_dir>/structured/<execution_id>.jsonl` 与 debug-logging 实际 task 级路径矛盾 | chain-mode L164 vs debug-logging L30/L70 |
| S5 | pre-commit post-commit hook 数：§1 "1 hook" vs §4.2 "2 hook"（漏 `gaf-lesson-diff-trigger`） | pre-commit-stages L25 vs L153 |
| S6 | gaf-governance-batch "24 检查"总数 vs "commit 跑 17"易误读 | pre-commit-stages L22 vs L94 |
| S7 | ScreenshotCache TTL 50ms vs RedisScreenshotCache TTL 100ms | concurrency-design L206 vs L243 |
| S8 | §4.2 DATABASES：SQLite ENGINE 却带 Postgres 的 USER/PASSWORD/HOST/PORT | deployment-design L319-334 |
| S9 | 坐标转换③函数名 `get_unified_logical_rect`（L76/L144）但 trace step 为 `publish_match_pos`（L80/L151） | coordinate-transform |
| S10 | "6 模块" vs 7 条目（promote_lessons×2） | pre-commit-stages L94 vs L151 |
| S11 | WS 帧 `task.assign`(点) vs 方法 `AgentConsumer.task_assign`(蛇形) vs 模型 `TaskExecution`/`Task`(驼峰) | dispatch-flow L31/L45/L46/L82 |

### 6.3 孤儿/死代码引用（文档指向不存在或已删的代码）

| # | 文档引用 | 代码实际 | 结论 |
|---|---------|---------|------|
| X1 | `overview.md:L529` + `dispatch-flow.md:L609`：`graph.py` `ParallelExecutor`/`DAGExecutor` 作为并行执行路径 | `agent/src/engine/graph.py` 确有 `DAGExecutor`(L586)/`ParallelExecutor`(L337)，但**全仓非测试代码零 import**；唯一种植者 `agent/tests/test_pipeline_graph.py:28`；`PipelineGraph` 实际在 `parser.py:61` | 死代码；活路径是 `PipelineEngine`（线性）。文档误导"DAG 并行已接线" |
| X2 | `architechure-debt-refactor.md:L53,72,85,327`：`TaskService.dispatch_task(...)` | 当前为 `TaskService.dispatch(...)`（`backend/tasks/services/task_service.py:244`） | 旧 spec 文档过时 |

### 6.4 四"chain" 并存（最高混淆风险）

| 词 | 所指 | 位置 |
|----|------|------|
| `TaskChain` | backend 持久化任务序列（用户的"链式任务"） | `pipeline/models.py:96` |
| `chain mode` | **已废弃** agent 线性 step runner | chain-mode-structured-logging.md |
| `ChainManager` | agent `StateMachine` 封装（非链式） | `chain_manager.py:20` |
| `ActionChain` | recovery 引擎的失败恢复动作链 | `recovery_engine.py` / dispatch-flow L334 |

> 四个"chain"四个不同含义；`TaskChain`(编排) 与 `ActionChain`(失败恢复) 最容易错认。

## 7. 扩展差异清单（D7+，追加到 §2）

| # | 位置 | 文档说法 | 代码实际 | 差异类型 |
|---|------|---------|---------|---------|
| D7 | §9.2 `overview.md:L121,L207` | "RotationRule" | 模型 `GameAccountRotation`；类型 3 vs 4 冲突 | 标签≠模型 + 分类冲突 |
| D8 | `overview.md:L474` vs `features-overview.md:L302` | TaskStep / ExecutionStep | 同一实体两命名 | 命名漂移 |
| D9 | `overview.md:L496` vs `features-overview.md:L526` | BackupRecord / BackupJob | 同名异物 + app 归属冲突 | 命名冲突 |
| D10 | `overview.md:L482` vs `L502` | AgentSession 属 gaf_ai / protocol | 实为两个独立模型 | 双重归属未说明 |
| D11 | `overview.md:L149,L464,L739` | Routine / routine.json | = 默认 `TaskChain` | 别名未澄清 |
| D12 | `overview.md:L463` vs `L465` | tasks/Tag 与 resources/Tag | 疑似两模型 | 可能重复 |
| D13 | `overview.md` §9.1–§9.6 模型清单 | 缺列 `UnattendedStrategy`/`NotificationPreferences`/`MarketplaceReview`/`SkillMarketReview`/`PluginHook`/`GameAccountGroup`/`TemplateEffectiveness`/`RecognizerBenchmark`/`AnomalyPattern` | features-overview 当真 | 文档缺口 |
| D14 | overview/features "TraceSpan" | 代码已删，现状 `trace_id` | 死概念 | 文档过期 |
| D15 | 隐含 `AgentToken` 实体 | 实为 `Agent.agent_token_hash` 字段 + 端点 | 字段≠实体 | 文档未说明 |
| D16 | `optimal-solution.md:L144` "373 行" | `state_machine.py` 实际 354 行 | 数字过时 | 行数漂移 |
| D17 | `overview.md:L744` "models.py:454" | `accounts/models.py:450` | 数字过时 | 行数漂移 |
| D18 | `concurrency-design.md:L70` "TaskDispatcher (Celery Worker)" | 无此 class；实为 `dispatch_task` + `AgentSelector` | 幽灵类名 | 文档框标签无符号 |
| D19 | overview "GafDaemon"(L753) / `gaf_daemon.py` / `gaf_services.ps1`("主入口" vs "兼容层") | 三处渲染不一 | 命名不一 |
| D20 | debug-logging S1-S4 | 路径 key / `_status` / 死 hour-bucket / chain-mode 路径 | 文档内部矛盾 | 子文档不一致 |
| D21 | concurrency-design S7 | ScreenshotCache 50ms vs RedisScreenshotCache 100ms | TTL 不一致 | 文档不一致 |
| D22 | deployment-design S8 | SQLite 配置带 Postgres 字段 | 内部矛盾 | 子文档不一致 |
| D23 | `concurrency-design.md:L70` 框 + dispatch-flow | "TaskDispatcher" vs `dispatch_task` | 见 D18 | — |
| D24 | pre-commit-stages S5/S6 | post-commit 1 vs 2 hook；"24" vs "17 on commit" | 计数矛盾 | 子文档不一致 |

## 8. 严重度重排（合并 §4）

| 级 | 项 | 理由 |
|----|----|------|
| **P0 正确性** | D1（orphaned graph.py 引用 X1） | 文档误导走不存在的执行路径 |
| **P0 正确性** | D2 + §3.1 chain 双关（含四 chain 并存 §6.4） | 概念错认风险最高，贯穿前后端 |
| **P0 正确性** | D18/D23 TaskDispatcher 幽灵类名 | 文档画了不存在的组件 |
| **P0 正确性** | D14 TraceSpan 死概念 | 文档指向已删代码 |
| **P1 清晰度** | §1.1 任务分类口径缺口 | 补总览即可 |
| **P1 清晰度** | §3.1 loop/emulator/agent 双关 + §6.1 Session×4/Account/Node/Routine/Recovery/Pipeline 过载 | 文档加"概念速查表"澄清 |
| **P1 清晰度** | D7/D8/D9/D10/D11/D12 标签≠模型/别名/重复 | 模型名与文档词对齐 |
| **P1 清晰度** | D13 features↔overview 模型清单对齐 | 两文档权威清单统一 |
| **P1 清晰度** | D15 AgentToken 字段说明 | 避免误认实体 |
| **P2 UI/i18n** | §3.4 三类显示 + S1-S4 路径/PNG 不一致 | 纯前端/文档修正 |
| **P3 架构债** | §3.2/§3.3 死代码/双路径/目录收敛 + X1 删 graph.py | 改动大，可后置 |

## 9. 新增开放问题（待拍板）

6. **RotationRule → 统一为 `GameAccountRotation`？** 文档"轮换规则(RotationRule)"与实际模型名不符；且 3 vs 4 类型冲突，以哪份为准？
7. **Routine 与 TaskChain 是否文档统一为"默认任务链"？** 消除 Routine 别名。
8. **TraceSpan / `graph.py` DAG 路径**：从文档删除死概念，还是接入真实 DAG 并行（若真要）？
9. **两套 `AgentSession` 模型**：合并为一个（加 type 字段）还是文档强标注"WS 会话 vs LLM 会话"？
10. **`overview.md` 模型清单与 `features-overview.md` 对齐**：是否把 D13 列出的 9 个概念补入 §9.x？
11. **`TaskStep`/`ExecutionStep`、`BackupRecord`/`BackupJob`、`Tag`(两 app)** 是否统一命名/合并模型？
12. **`PerformanceMonitor`×2（Python/TS）**：重命名其一（如前端 `FrontendPerformanceMonitor`）避免同名异物？
13. **`GafDaemon` / `gaf_daemon.py` / `gaf_services.ps1` 三渲染**：统一术语（建议 daemon 为权威，ps1 为 Windows 兼容入口）。
14. **子文档死路径/计数矛盾（S1-S11）**：是否一次性修 overview/子文档的内部不一致（纯文档，低风险）？

> 范围说明：`docs/analysis/` 下 `evaluation-zxcvbn-replacement.md` 与 `GAF-vs-*` 为对比/评估类文档，非架构概念定义，未纳入本次概念命名盘点。

## 10. 架构层拍板（2026-08-29 — 用户授权，不拘改动量）

> 决策原则（归一化总纲）：**代码模型名为唯一权威词源**；文档/UI/字段/i18n 一律对齐代码；
> 消除一切"同词异义"与"幽灵符号"（文档引用但代码不存在/名不符）；**死代码删除而非保留**。
> 用户明确"不在乎改动多少"，故重命名/迁移/跨端改动均可落地。

### 10.1 执行引擎与"四 chain"归一（P0）

- **`ChainManager` → 重命名 `StateMachineEngine`**（文件 `agent/src/engine/chain_manager.py` → `state_machine_engine.py`，注册键 `task_type='chain'`→`'state_machine'` 同步改）。文档明确：用户"链式任务"=`TaskChain`（后端持久序列），与 agent 的 `StateMachineEngine`（状态机驱动，非链式）**无关**。
- **四 chain 收敛口径**：
  - `TaskChain`：编排序列（保留，用户"链式任务"）。
  - `chain mode`：已废弃 agent 线性 step runner，文档标注 **DEPRECATED**，不与 `TaskChain` 混用。
  - `ChainManager`：→ `StateMachineEngine`。
  - `ActionChain`：恢复引擎的失败恢复动作链（保留），文档加"恢复"定语，避免与 `TaskChain` 错认。
- **删除死代码 `graph.py` 的 `DAGExecutor`/`ParallelExecutor`**（全仓非测试零 import；`PipelineGraph` 已在 `parser.py`）。overview.md:529 / dispatch-flow.md:609 删除对其引用；活路径只有 `PipelineEngine`（线性）。未来若需 DAG 并行，作为新 feature 设计，不复活死代码。

### 10.2 任务分类口径（用户视角，P1）

- 采纳 **线性 / 链式 / 循环** 为 overview.md 官方任务分类章，映射：`Task`(单 Pipeline) / `TaskChain`(序列) / `LoopNode`(pipeline 内迭代)；`loop_rotation`（UnattendedSession 布尔）属"无人值守账户轮询"，**单列**不与循环节点混。
- 引擎层"三模式"改写为 `PipelineEngine` / `StateMachineEngine`，不与用户分类共用"chain"词。

### 10.3 字段/模型重命名消除双关（P0/P1）

| 现符号（代码） | 决策改名 | 理由 |
|----|----|----|
| `Device.emulator`（品牌自由文本，`agents/models.py:323`） | → **`emulator_brand`** | 消除与 `device_type='emulator'` 双义 |
| `GameProfile.default_routine`（FK→TaskChain，`gamestate/models.py:53`） | → **`default_task_chain`**；端点 `default-routine`→`default-task-chain` | "Routine"=默认 TaskChain 别名，归一为"默认任务链" |
| `tasks.TaskStep`（`tasks/models.py:441`，定义期步骤） | → **`PipelineStep`** | 与运行期 `ExecutionStep`(`tasks/models.py:745`) 区分（两模型均真实存在） |
| `tasks.ExecutionStep` | 保留（运行期步骤） | — |
| `protocol.AgentSession`（`protocol/models.py:6`） | → **`AgentConnection`**（WS agent 会话） | 与 LLM 会话模型同名异物 |
| `gaf_ai.agent.AgentSession`（`gaf_ai/agent/models.py:6`） | → **`LLMAgentSession`** | 同上 |
| 前端 TS `PerformanceMonitor`（`concurrency-design.md:L485`） | → **`FrontendPerformanceMonitor`** | 与后端 `PerformanceMonitor`(Python) 同名异物 |
| `resources.Tag`（`resources/models.py:166`，唯一 Tag 模型） | 保留；文档取消"tasks.Tag"说法 | tasks 复用 `resources.Tag`，统一单一 `Tag` |

### 10.4 轮换策略对齐代码（P1，已核实）

- 代码 `GameAccountRotation.rotation_strategy` 实为 **4 选**：`sequential`/`random`/`by_stamina`/`by_last_executed`（见 `scheduler/migrations/0001_initial.py:58`）。
- overview 的"3 种（按时间/按任务完成/按失败次数）"**错误**；features 的"4"数量对但缺 `by_last_executed`。
- **决策**：文档统一为代码 4 选 + 正确中文；术语用 `GameAccountRotation`（弃用 "RotationRule" 标签）。`loop_rotation`（UnattendedSession 布尔）单列"无人值守账户轮询"，不并入 `GameAccountRotation`。

### 10.5 死概念 / 幽灵符号 / 文档内部不一致（P0/P2）

- **`TraceSpan`**：代码已删（`gaf_core/tracing/middleware.py:8`），文档删除该概念，改 `trace_id`（ContextVar）链路追踪。
- **`AgentToken`**：文档说明其为 `Agent.agent_token_hash` 字段 + 端点（`AgentTokenViewSet`/`Serializer`/`Authentication`），非实体。
- **`BackupRecord`/`BackupJob`**：代码**两均无 ORM 模型**（备份为文件系统快照，见 deployment-design §backup）；文档统一术语为 `BackupJob`（概念），删除 `BackupRecord` 引用并注明"无独立 ORM 模型"。
- 子文档 S1–S11（死 hour-bucket 路径、PNG `_status` 缺失、post-commit 1 vs 2 hook、`ScreenshotCache` 50ms vs 100ms、SQLite 配置带 Postgres 字段、坐标转换③ `get_unified_logical_rect` vs `publish_match_pos`、`task.assign`(点) vs `task_assign`(蛇形)、`GafDaemon`/`gaf_daemon.py`/`gaf_services.ps1` 三渲染）：**全部修文档**。
- **`GafDaemon`** 为权威名（`gaf_daemon.py` 守护进程）；`gaf_services.ps1` 是 Windows 一键启停封装（委托 daemon），文档明确层级。
- **`overview.md` §9 模型清单补齐** features 独有的 9 概念：UnattendedStrategy / NotificationPreferences / MarketplaceReview / SkillMarketReview / PluginHook / GameAccountGroup / TemplateEffectiveness / RecognizerBenchmark / AnomalyPattern（注明前端-only，后端由 `LLMAnalysisResult` 支撑）。

### 10.6 UI / 目录收敛（P3）

- TaskChain UI 收敛到 `pages/Ops/TaskChains/` 单目录（`DagEditorPage`/`TaskChainsTab`/`TaskDependencyGraph` 归并）。
- `ScanModal.tsx` → `pages/Devices/`。
- 设备发现：`DeviceDiscoveryRegistry` 为权威；`EmulatorDiscovery`/`WindowDiscovery` 作为 registry 的 adapter（行为不变，仅路由归一）。

### 10.7 未决（需用户最终确认的小项）

- 无。上述 10.1–10.6 为本稿推荐终态；实现时若某重命名影响第三方/序列化兼容，按"代码名权威 + 文档/UI 同步"原则处理，不做下游 workaround。
