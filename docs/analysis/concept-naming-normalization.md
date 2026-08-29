---
summary: GAF 概念关系与命名归一化评估（迭代评估稿，最终驱动 spec + overview.md 更新 + 代码修改）
applies_to: ['architecture', 'naming', 'concept', 'evaluation']
status: draft | 创建: 2026-08-29 | 来源: 用户要求梳理 Device/Agent/Window/Emulator/Service/链式/循环 概念关系 + 评估文档与代码差异、多层命名、文件/代码命名
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
