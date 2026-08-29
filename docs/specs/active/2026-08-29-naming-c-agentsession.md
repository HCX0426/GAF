---
spec: 2026-08-29-naming-c-agentsession
title: 命名归一化 C-3 批：两个 AgentSession 模型拆分（Worker WS 会话 → WorkerSession；AI 会话保留 AgentSession）
status: active
created: 2026-08-29
estimated_effort: 0.5 day
risk: high
depends_on: []
source: docs/analysis/concept-naming-normalization.md §1(WorkerSession/AgentSession 行)/§3/Session×4/§5(13,17)/§9(OQ-4,OQ-10)/§7(C-3,G)
---

# 命名归一化 C-3 批：两个 AgentSession 模型拆分

## 1. 背景与动机 (Background)

评估稿 §3/Session×4 与 §9(OQ-4) 发现两个同名为 `AgentSession` 的模型跨 `gaf_ai` 与 `protocol` 两个 app 双重归属，且 agent 进程侧另有 `AgentConnection`(`connection.py:153`) 与之混淆。结合 2026-08-29 **Worker/Agent 术语拆分决策（OQ-10）**：未来 AI 智能体的会话应保留干净名 `AgentSession`，执行节点（Worker）的 WS 会话应改名为 `WorkerSession`。本批仅做此一处模型改名，且**gaf_ai 侧实际不改名**（保留 `AgentSession` 给 AI），风险低于初判。

## 2. 核心问题 (Problem)

| 项 | 现状 | 目标 |
|----|------|------|
| `protocol.AgentSession`（Worker WS 会话） | `protocol/services.py` / `protocol/models.py` 的 WS 会话模型；与 agent 端 `AgentConnection`(`connection.py:153`) 混称 | → `WorkerSession`（Worker WS 会话） |
| `gaf_ai.agent.AgentSession`（AI 会话） | AI 智能体会话模型 | **保留 `AgentSession`**（干净名留给 AI 智能体，OQ-10） |
| `AgentConnection`（agent 端 WS 客户端） | `connection.py:153` | → `WorkerConnection`（由批 G 统一实施；本批仅做文档关联，避免与 WorkerSession 混淆） |

## 3. 目标 (Goals)

1. `protocol.AgentSession` → `WorkerSession`（后端模型 + 迁移 + 序列化器 + 前端类型重生成）。
2. `gaf_ai.agent.AgentSession` **保留 `AgentSession`**（不改名），作为 AI 智能体会话的权威命名。
3. 文档/代码注释厘清三者：Worker WS 会话=`WorkerSession`、Worker 连接客户端=`WorkerConnection`(G)、AI 会话=`AgentSession`。

## 4. 实施计划 (Implementation)

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | backend `protocol.AgentSession`→`WorkerSession`（模型+迁移+serializer） | ⏳ |
| P2 | 前端 `api.generated.ts` / `models/*.ts` 重生成 + import 改写 | ⏳ |
| P3 | gaf_ai `AgentSession` 保留确认 + 文档注明 AI 归属（OQ-10） | ⏳ |

#### Task P1.1: backend 改名

- `protocol/models.py` / `protocol/services.py` / `protocol/serializers.py` 中 `AgentSession`(仅 protocol 域) → `WorkerSession`。
- 生成迁移（兼容历史数据；`WorkerSession` 与 `AgentSession`(gaf_ai) 表名不同，无冲突）。
- 更新 `protocol/consumers.py`、`connection.py` 相关引用。

#### Task P2.1: 前端

- 重新生成 OpenAPI 客户端类型，`WorkerSession` 进入 `api.generated.ts`；移除旧 `AgentSession`(protocol 域) 类型。
- 全局 import 改写（前端约 50 处）。

#### Task P3.1: AI 会话归属确认

- 确认 `backend/gaf_ai/agent/models.py:6` `AgentSession` **不改名**；在 `gaf_ai` 文档/注释注明其为"AI 智能体会话"，与 Worker 无关（OQ-10）。

## 5. 测试与验收

- `pytest backend/protocol backend/gaf_ai` 通过；迁移 `makemigrations --check` 干净。
- `npm run typecheck`（frontend）通过；grep `protocol` 域 `AgentSession` 残留清零（gaf_ai 域保留）。
- 评估稿标记 C-3 完成。

## 6. 回滚

- 模型改名带迁移，需 `makemigrations` + 数据迁移；其余 git revert。
