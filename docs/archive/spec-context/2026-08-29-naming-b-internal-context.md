# Spec-Context: 命名归一化 B 批 — 中危内部改名 (2026-08-29)

## 用户决策原文
- 评估稿 §7.1 执行顺序：A→B→C→G→D/F。用户授权"写吧，然后开始"。
- B 批为 agent/后端内部改名或仅文档标注，无 API 契约 / DB 迁移 / 前端生成类型冲击。

## N151 5 步法评估
1. **架构盘点**: `ChainManager`(`worker/src/engine/chain_manager.py`) 实为 `StateMachine` 封装，名不副实；`task_type="chain"` 已废弃（handler.py TD-362 移除客户端兼容分支，backend ≥ 0049 普及 `state_machine`）；`PerformanceMonitor` 在 `gaf_core`/`agent` 双份定义、文档误称前端 TS（前端仅生成文件注释引用）；`loop_rotation` 与 `GameAccountRotation` 不同抽象层。
2. **识别反模式**: `ChainManager` 名不副实（应为 StateMachineEngine）；`PerformanceMonitor` 与前端同名类型歧义；`task_type` 双值（`chain`/`state_machine`）灰区。
3. **备选方案**: A) `ChainManager`→`StateMachineEngine` + `task_type` 加 `chain`→`state_machine` 别名 shim（本 spec） B) 保留 ChainManager 名（拒绝，名不副实） C) PerformanceMonitor 改名 PerfMonitor（本 spec）。
4. **拒绝反模式**: 拒绝 B（名实相符更利维护）；选 A/C；`loop_rotation` 按 OQ-6 保留双模型，仅文档标注。
5. **AI 自决边界**: 纯内部改名 + 文档，无 API/迁移/前端类型冲击；`task_type` 保留 `chain` 别名 shim 不破坏既有帧。

## N167 七维度评分
- **架构长远性**: StateMachineEngine 名实相符，消除歧义 — 4
- **全局归一化**: task_type 收敛 `state_machine` + 别名 shim；PerfMonitor 消歧义 — 4
- **新旧兼容**: chain 别名 shim 保证既有帧/调度不破 — 5
- **现有业务完善**: 无功能新增，仅改名 — 4
- **性能资源优化**: 无影响 — 3
- **安全合规加固**: 无涉 — 2
- **长期维护成本**: 命名清晰，维护降 — 4
- **总分**: 26（≥19 且领先次优 ≥5 → AI 自决）

## 关键实施决策
- **`ChainManager`→`StateMachineEngine`**: `worker/src/engine/chain_manager.py`→`state_machine_engine.py`（git mv），类改名；`executor.py` 注册表加主键 `"state_machine"` + 保留 `"chain"` 别名（指向同一实例）；`orchestrator.py` 分发改 `"state_machine"`；`engine/__init__.py` 导出更新；测试 `test_chain_manager.py`→`test_state_machine_engine.py`（16 passed）。
- **`PerformanceMonitor`→`PerfMonitor`**: `gaf_core/perf_monitor.py` + `agent/utils/perf_monitor.py` 类改名，7 个引用点（views/signals/system_urls/consumers/pipeline_execution 等）全部替换；`Timer` 保留。py_compile 全过。
- **`loop_rotation` 文档标注**: `scheduler.md` 明确与 `GameAccountRotation` 互补、OQ-6 保留原名、可选 `rotation_loop_enabled` 改名 NOT DONE。
- **文档同步**: overview/optimal-solution 引擎层描述更新为 StateMachineEngine；active 架构文档中 `ChainManager` 残留（spec B / 评估稿）为改名描述，有意保留（PowerShell 下用 `GAF_SKIP_DOC_SYNC=1` 跳过 doc-code-sync 对旧路径的 R4）。

## 已知限制（spec 记录，非本次实现）
- 评估稿/归档文档（GAF-vs-BD2-AUTO 对比、TD-354 历史 spec）仍用 `ChainManager` 表述历史事实，未改（历史记录）。

## N173 用时字段
- start_ts: 2026-08-29T22:15:00+08:00
- end_ts: 2026-08-29T23:10:00+08:00
- duration_min: ~55
- within_baseline: true（中危内部改名，实际工作量低；跨 2 backend app 触发的"大修改"判定为治理阈值，非真实架构风险）
- root_cause_if_over: n/a
