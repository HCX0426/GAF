---
spec_id: spec-2026-08-24-canvas-action-type-unification
title: Canvas action schema 统一到 node_type（N191 收尾）
status: ✅ 已归档 (docs/specs/archived/2026-08/2026-08-24-canvas-action-type-unification.md)
created: 2026-08-24
task_type: refactor
applies_to: [agent, backend, frontend, governance]
---

# Spec: Canvas action schema 统一到 node_type（N191 收尾）

> 关联：N191 schema 归一化；`check_schema_unification.py` 的 `CANVAS_LEGACY_RULES`；
> 相关历史：`spec-2026-07-27-execution-path-unification`、`TD-075`（PIPELINE_GRAPH_SCHEMA oneOf）。
> 本 spec 是 `-` 清零 10 个 node 级 error 后的**剩余债务**：10 个 `action_type` canvas warning。

## 1. 背景与问题

`check_schema_unification` 的 `CANVAS_LEGACY_RULES` 把 canvas 动作的 `action_type`（及底层 `type` 字段）标记为
"未来应转换为 `node_type`"的待办迁移。当前 10 个 warning 分布在：

- `agent/src/core/orchestrator.py`（1337/1338/1360/1363/1366/1372/1376）— `action_type` 变量 + `action.get("type")`
- `agent/src/core/interface_recovery.py`（52/158/175/177/178）— 同上

这些 warning **非阻断**（checker `exit_code = 1 if errors else 0`，warning 不计）。但若要彻底清零 schema 归一化债务，需完成该迁移。

### 1.1 执行偏差（2026-08-24 用户决策：保留现状 + 登记）

执行 Phase 1 时发现 `check_schema_unification` 存在**过宽**问题，原"10 个 action_type warning"实际构成：
- **真正 canvas 图 schema 残留**：仅 `orchestrator.py` + `interface_recovery.py` 的 `action.get("type")` 读取（已改双读 `node_type or type`）。
- **checker 误报（非 canvas 领域）**：
  - `backend/scheduler/recovery_engine.py` 的恢复动作类型（notify/reassign/retry 等）——与 canvas 节点类型无关；
  - `agent/src/monitor/handlers.py` 的 `PopupTemplate.action_type`（弹窗动作，监控运行时配置）；
  - `agent/src/core/script_dsl.py` 的 DSL 动作常量。
- **双读不被接受**：`NODE_TYPE_CODE_RULES` 正则 `node.get('type')` 即便在双读 `node.get('node_type') or node.get('type')` 内也命中（estimator.py/validators.py/test_estimator.py）。

用户决策：不更名（避免污染 scheduler/monitor/DSL 领域概念）、不收窄 checker；保留代码现状（genuine canvas 双读保留），将 checker 过宽问题登记为 **TD-395**，待 N191 专项治理时接修。

### 现状（关键事实）
- 节点级 schema 已统一为 `node_type`（`PipelineNode.node_type`，`pipeline_node_execution.py:57/69`）。
- canvas 动作仍用 `type`（`action.get("type")`）——与节点 schema 不统一。
- **兼容层已存在**：`interface_recovery.py:797` `node_type = node_config.get("node_type") or node_config.get("type")`
  与 `:815` `prev_type = prev_config.get("node_type") or prev_config.get("type")` 已双读。说明运行时可接受两种字段。
- `backend/pipeline/recording_converter.py` 输出 canvas `graph_data` 用 `"type": "click"` 等（legacy 格式）。
- `backend/pipeline/schema.py` 的 `PIPELINE_GRAPH_SCHEMA` oneOf 与 `frontend/src/utils/schemaValidator.ts` 定义 canvas schema 用 `type`。

## 2. 目标
将 canvas 动作的字段从 `type`/`action_type` 统一为 `node_type`，使 `check_schema_unification` 达到 0 error / 0 warn，
且前端/后端/agent 三端 schema 一致。

## 3. 范围（影响文件）
| 文件 | 改动 |
|---|---|
| `agent/src/core/orchestrator.py` | `action_type` 变量改名（→`action_kind` 消除 checker 误报语义）+ `action.get("type")` 改双读 `node_type or type` |
| `agent/src/core/interface_recovery.py` | 同上；`:539` 输出 `"type": action.get("type")` 改双写/双读 |
| `backend/pipeline/recording_converter.py` | 输出 `graph_data` 增加 `node_type`（双写），后续 cutover 去 `type` |
| `backend/pipeline/schema.py` | `PIPELINE_GRAPH_SCHEMA` oneOf 增加 `node_type` 分支 |
| `frontend/src/utils/schemaValidator.ts` | canvas schema 接受 `node_type`（双读） |
| `frontend` canvas 组件 / `NodePropertyPanel` | 读 `node_type or type` |
| `check_schema_unification.py` | cutover 后收紧 `CANVAS_LEGACY_RULES`（或白名单） |

## 4. 方案（三阶段，双读期不破坏存量）

### Phase 1 — 双读兼容（非破坏）
- agent 动作读取：`action.get("node_type") or action.get("type")`（对齐 `:797/815` 既有模式）。
- `action_type` 变量重命名为 `action_kind`（消除 checker `\baction_type\b` 误报，且语义更准确）。
- recording_converter 输出双写 `node_type` + 保留 `type`。
- frontend schemaValidator / 组件双读。
- **验收**：现有 canvas 回放/录制用例不变绿；checker warning 降为 0（变量改名 + 双读后 `action_type` 消失）。

### Phase 2 — 存量数据迁移
- 迁移已落盘的 canvas graph / recording 文件：`type` → `node_type`。
- 迁移脚本 + 回滚方案（双写期内可回退）。

### Phase 3 — Cutover
- 去掉 `type` 单读分支；recording_converter 仅输出 `node_type`；schema oneOf 去 `type` 分支。
- 收紧 `check_schema_unification.CANVAS_LEGACY_RULES`（移除 `action_type` 规则或白名单）。
- **验收**：checker 0/0；canvas 端到端回放冒烟通过。

## 5. 风险
- 存量 recording/canvas graph 未迁移即 cutover → 回放失败（用 Phase 1 双读 + Phase 2 迁移规避）。
- 前端/后端 schema 漂移（oneOf 不同步）→ 每阶段跑 `schemaValidator` 单测 + 手动 canvas 回放。
- `action_type` 改名波及调用方多 → 用 IDE 重命名 + grep 校验。

## 6. 验证
- `pytest backend/pipeline/tests/test_validators.py`（canvas schema 兼容）
- `pytest agent/src/core/tests/*interface_recovery*` / `orchestrator*`
- 手动：GAF 界面跑一次 canvas 录制→回放冒烟
- `python scripts/hooks/check_schema_unification.py` → 0 error / 0 warn

## 7. 阶段状态表
| 阶段 | 状态 | 完成时间 | commit | 验收 evidence |
|---|---|---|---|---|
| Phase 1 双读兼容 | ✅ | 2026-08-24 | 见 TD-395 | agent 双读已应用(orchestrator/interface_recovery/estimator/validators); checker 过宽误报登记 TD-395 |
| Phase 1b TD-395 checker 收窄 | ✅ | 2026-08-26 | - | CANVAS_LEGACY_RULES 收窄+白名单+双读豁免, 103 warns → **0 error / 0 warn** (复跑实证) |
| Phase 2 存量迁移 | ✅ 决策豁免 | 2026-08-24 | — | 用户决策: 双读为终态不 cutover, 避免污染 scheduler/monitor/DSL 领域概念 (记录于 §1.1) |
| Phase 3 Cutover | ✅ 决策豁免 | 2026-08-24 | — | 同上; schema 归一化债务经 TD-395 清零, 无剩余条目, 归档 |

> **归档结论 (2026-08-28)**: 全部 schema 归一化债务已清零 —— `check_schema_unification.py` 实测 0 error / 0 warn；
> Phase 2/3（cutover 去 `type`）因 2026-08-24 用户决策"双读为终态"不做，登记为已知设计而非债务。
