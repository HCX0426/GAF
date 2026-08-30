---
spec: 2026-08-29-naming-c-task-assign
title: 命名归一化 C-5：WS 帧 task.assign 统一（协议层）+ alias 兼容
status: completed
created: 2026-08-29
estimated_effort: 0.5 day
risk: high
depends_on: []
source: docs/analysis/concept-naming-normalization.md §1/§4(D23①)/§7
---

# 命名归一化 C-5：WS 帧 task.assign 命名统一

## 1. 背景与动机 (Background)

评估稿 §4-D23① 核实：代码存在协议层命名漂移——WS 帧名为 `task.assign`（`worker/src/client/connection.py:870` `"task.assign": handler.handle_task_assign`），而消费方法为 `handle_task_assign`（下划线，`worker/src/client/handler.py:186`）。且 `task.dispatch` 也已别名到同一 handler（兼容历史）。这属 wire-contract 级不一致（评估稿 §1/§7 标高危）。

后端方法名 `handle_task_assign` 为内部实现，无需改；**最优**是统一 WS 帧名为单一规范名，并保留 alias 兼容存量客户端。

## 2. 核心问题 (Problem)

| 符号 | 现状 | 目标 |
|------|------|------|
| WS 帧 `task.assign` | 点号帧名 | 规范帧名（见 §3 决策） |
| WS 帧 `task.dispatch` | 历史别名，映射到同 handler | 保留为 deprecated alias |
| 方法 `handle_task_assign` | 下划线（内部） | 不变 |

## 3. 目标 (Goals)

1. **【已锁定 2026-08-29】规范帧名 = `task.assign`**（存量客户端已发此帧，改名成本最高且收益低；与方法 `handle_task_assign` 语义通过文档对齐，不强求帧名=方法名）。`task.dispatch` 保留为 deprecated alias。
2. `task.dispatch` 保留为 deprecated alias（过渡期），映射同一 handler。
3. 协议文档（WS RPC 契约）更新，明确规范帧名 + alias 生命周期。
4. 零后端方法改名（仅 WS 路由表 + 协议文档）。

## 4. 实施计划 (Implementation)

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 确认规范帧名 + 路由表 alias | ✅ |
| P2 | 协议文档更新 | ✅ |
| P3 | 测试（双帧名兼容） | ✅ |

#### Task P1.1: 路由表

- **规范帧名锁定为 `task.assign`**（primary）；`task.dispatch` 保留为 deprecated alias → `handler.handle_task_assign`（现有 `connection.py:870` 已满足，仅需在协议文档标注生命周期）。
- 不改前端/后端 WS 客户端帧名（存量已用 `task.assign`）；仅补充 alias 废弃说明。

#### Task P1.2: 协议文档

- 更新 WS RPC 契约文档（评估稿 §1 已列；concurrency-design 相关处）标注规范帧名 + alias 废弃计划。

#### Task P1.3: 测试

- agent WS 单测：用规范帧名 + alias 帧名均触发 `handle_task_assign`，断言行为一致。

## 5. 测试与验收

- agent `tests/test_ws_client.py`：双帧名兼容断言通过。
- 前端 WS 客户端（如改名）调用规范帧名成功。
- 评估稿标记 C-5 完成。

## 6. 回滚

- 路由表 revert 即可（纯配置级，无迁移）。
