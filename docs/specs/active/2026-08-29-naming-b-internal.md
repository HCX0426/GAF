---
spec: 2026-08-29-naming-b-internal
title: 命名归一化 B 批：中危内部改名（ChainManager→StateMachineEngine / PerformanceMonitor / loop_rotation 标注）
status: active
created: 2026-08-29
estimated_effort: 1 day
risk: medium
depends_on: []
source: docs/analysis/concept-naming-normalization.md §1/§5(1,2,4,6)/§7
---

# 命名归一化 B 批：中危内部改名

## 1. 背景与动机 (Background)

B 批为 agent/后端**内部**改名或仅文档标注，无 API 契约 / DB 迁移 / 前端生成类型冲击（评估稿 §7 B 批）：`ChainManager`→`StateMachineEngine`（名不副实，实为 StateMachine 封装）、`PerformanceMonitor` 后端类消歧义（文档误称前端 TS）、`loop_rotation` 文档标注（OQ-6 已决 KEEP 双模型）。

## 2. 核心问题 (Problem)

| 项 | 现状 | 目标 |
|----|------|------|
| `ChainManager`(`agent/src/engine/chain_manager.py:20`) | `StateMachine` 封装，名不副实 | `StateMachineEngine`(+`state_machine_engine.py`) |
| `task_type='chain'` | 字面 52（多无关） | `'state_machine'` + 别名 shim |
| `PerformanceMonitor`(后端类 `gaf_core`/`agent`) | 文档误称前端 TS | `PerfMonitor`（后端性能监视器） |
| `loop_rotation`/`rotation_index` | 每会话运行时游标 | 文档标注（OQ-6 KEEP；可选改名 `rotation_loop_enabled` 标 NOT DONE） |

## 3. 目标 (Goals)

1. `ChainManager`→`StateMachineEngine`；`task_type` `'chain'`→`'state_machine'` + 别名 shim（不破坏既有帧/数据）。
2. `PerformanceMonitor`→`PerfMonitor`（后端类，53 命中，无 API/前端）。
3. `loop_rotation` 文档澄清：与 `GameAccountRotation` 互补（共享配置 vs 运行时游标），OQ-6 已决不改名。

## 4. 实施计划 (Implementation)

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | ChainManager→StateMachineEngine + task_type shim + 文档 | ⏳ |
| P2 | PerformanceMonitor→PerfMonitor | ⏳ |
| P3 | loop_rotation 文档标注 | ⏳ |

#### Task P1.1: ChainManager 改名

- `agent/src/engine/chain_manager.py`→`state_machine_engine.py`；class `ChainManager`→`StateMachineEngine`（含内部引用）。
- `task_type` 注册/分发处：加 `'chain'`→`'state_machine'` 别名 shim（评估稿：代码已 49 处 `state_machine`，仅补 shim 与零星 `'chain'` 字面）。
- 文档（overview/features 69 处命中）："链式任务=`TaskChain`，与 StateMachineEngine 无关"；`chain mode` 标 DEPRECATED。

#### Task P2.1: PerformanceMonitor 改名

- `gaf_core/perf_monitor.py` + `agent/utils/perf_monitor.py` 类 `PerformanceMonitor`→`PerfMonitor`（grep 53 命中，后端为主，前端仅 1）。
- 同步 import 与调用点；文档澄清其为后端性能监视器（非前端 TS）。

#### Task P3.1: loop_rotation 标注

- overview/features/scheduler 子文档：明确 `loop_rotation`/`rotation_index` = 每会话无人值守运行时游标，与 `GameAccountRotation`（共享轮换配置）互补，非冗余；可选 `rotation_loop_enabled` 改名**标 NOT DONE**（OQ-6 保留）。

## 5. 测试与验收

- `conda run -n gaf python -m pytest agent/tests backend/scheduler -q` 通过。
- grep `ChainManager`/`PerformanceMonitor` 残留清零（除文档 DEPRECATED 标注）。
- 评估稿标记 B 批完成。

## 6. 回滚

- 纯内部改名 + 文档，git revert 即可（无迁移）。
