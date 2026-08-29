---
spec: 2026-08-29-naming-c-taskstep-merge
title: 命名归一化 C-4：TaskStep 合并入 ExecutionStep（删 TaskStep）
status: active
created: 2026-08-29
estimated_effort: 1 day
risk: high
depends_on: []
source: docs/analysis/concept-naming-normalization.md §1/§5(8,13,OQ-3)/§7
---

# 命名归一化 C-4：TaskStep 合并入 ExecutionStep

## 1. 背景与动机 (Background)

代码中存在两个"运行期步骤"模型（评估稿 §3/§5-OQ-3）：
- `backend/tasks/models.py:441` `TaskStep` —— **遗留死模型**：生产路径零 `create`，仅测试/seed 引用。serializers 明文（约 L46）"生产数据走 ExecutionStep"。
- `backend/tasks/models.py:745` `ExecutionStep` —— **事实权威**：运行期唯一写入方（含 `node_id`/`error_code`/`trace_id` + WS 推送），字段更全。

两模型语义重叠，造成"双步骤模型"债。代码核实（`serializers`、`protocol/services.py:785` update_or_create）确认 `TaskStep` 无生产数据，**MERGE 为最优**（无数据丢失）。

## 2. 核心问题 (Problem)

| 模型 | 现状 | 处置 |
|------|------|------|
| `TaskStep` | 遗留死模型（192 命中多测试/文档） | 删除，引用迁 `ExecutionStep` |
| `ExecutionStep` | 权威（218 命中含 API/迁移/前端） | 吸收 `TaskStep`，补 `retry_count` |

## 3. 目标 (Goals)

1. 删除 `TaskStep`；所有 writer/reader 统一走 `ExecutionStep`。
2. `ExecutionStep` 补 `retry_count` 字段（覆盖 TaskStep 独有语义）。
3. 前端 `api.generated.ts` 重生成 + 全仓引用改写。
4. 迁移：确认无 TaskStep 生产数据后 Drop（带安全检查）。

## 4. 实施计划 (Implementation)

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 数据安全检查 + ExecutionStep 加 retry_count + 迁移 | ⏳ |
| P2 | 后端 writer 迁移（TaskExecutor/pipeline nodes → ExecutionStep） | ⏳ |
| P3 | 后端 reader/serializers/views + 前端类型重生成 | ⏳ |
| P4 | 删除 TaskStep 模型 + 测试 | ⏳ |

#### Task P1.1: 安全与迁移

- 先跑只读核查：`TaskStep.objects.count()` 应为 0（生产）；若有数据，先迁移至 `ExecutionStep` 再删。
- `ExecutionStep` 加 `retry_count = IntegerField(default=0)`（覆盖 TaskStep 语义）。
- 生成 `AddField` + 后续 `DeleteModel TaskStep` 迁移。

#### Task P1.2: writer 迁移

- grep `TaskStep` 写入点（`TaskExecutor`、pipeline 节点 `agent/src/...`、`protocol/services.py`）：改 `TaskStep.objects.create/update` → `ExecutionStep.objects.update_or_create`（沿用 `protocol/services.py:785` 模式）。

#### Task P1.3: reader + 前端

- `tasks/serializers.py`：`StepSerializer`/`TaskStep` 相关 → `ExecutionStepSerializer`；`tasks/views.py` 查询替换。
- 前端 `api.generated.ts` / `models/task.ts`：删 `TaskStep`，`ExecutionStep` 补 `retry_count`。

#### Task P1.4: 清理

- 删 `backend/tasks/models.py:441` `TaskStep` 类 + 迁移；更新测试（192 命中中的测试引用改为 `ExecutionStep`）。
- 评估稿标记 C-4 完成。

## 5. 测试与验收

- 数据核查脚本断言 `TaskStep` 为空（或已迁移）。
- `makemigrations --check` 无 diff（除本 spec 迁移）。
- `pytest backend/tasks` 全过；pipeline e2e 冒烟（步骤写入/读取正常）。
- 前端 `tsc --noEmit` 无 `TaskStep` 残留。

## 6. 回滚

- 保留 `DeleteModel` 迁移反向（`CreateModel`）；生产若无 TaskStep 数据则回滚安全。代码 revert 本 spec。
