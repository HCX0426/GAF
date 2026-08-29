---
spec: 2026-08-29-naming-c-agentsession
title: 命名归一化 C-3：两个 AgentSession → AgentConnection / LLMAgentSession
status: active
created: 2026-08-29
estimated_effort: 1 day
risk: high
depends_on: []
source: docs/analysis/concept-naming-normalization.md §1/§5(13,OQ-4)/§7
---

# 命名归一化 C-3：两个 AgentSession 模型拆分改名

## 1. 背景与动机 (Background)

`docs/architecture/` 将 `AgentSession` 同时列为 gaf_ai 与 protocol 的组件，但代码中存在**两个独立模型**（评估稿 §3/§5-OQ-4）：
- `backend/protocol/models.py:6` `AgentSession` —— **WebSocket 连接会话**（协议层）。
- `backend/gaf_ai/agent/models.py:6` `AgentSession` —— **LLM 对话会话**（AI 层）。

两模型处不同抽象层、字段不同，却共用一名，是最大的同词异义源。全仓 235 命中（含 API/migration/前端生成类型），属 C 批最高危单批。

## 2. 核心问题 (Problem)

| 模型 | 现状 | 目标 |
|------|------|------|
| `protocol.AgentSession` (WS) | WS 连接会话 | `AgentConnection` |
| `gaf_ai.agent.AgentSession` (LLM) | LLM 会话 | `LLMAgentSession` |

## 3. 目标 (Goals)

1. 两个模型分别改名为 `AgentConnection` / `LLMAgentSession`，彻底消歧。
2. 生成可逆迁移（表重命名 + 数据保留）。
3. 前端 `api.generated.ts` 重生成 + 全仓引用改写。
4. WS consumer / gaf_ai agent 代码引用同步。

## 4. 实施计划 (Implementation)

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 后端两模型改名 + 迁移 + 各自 imports | ⏳ |
| P2 | WS consumer / gaf_ai agent 引用改写 | ⏳ |
| P3 | 前端类型重生成 + 引用替换 | ⏳ |
| P4 | 文档同步 + 测试 | ⏳ |

#### Task P1.1: 模型与迁移

- `backend/protocol/models.py:6`：class `AgentSession`→`AgentConnection`（含 `Meta.db_table` 如显式）。
- `backend/gaf_ai/agent/models.py:6`：class `AgentSession`→`LLMAgentSession`。
- 各生成 `RenameModel` 迁移（保留数据）；若跨 app 引用 FK，一并更新。

#### Task P1.2: 后端引用

- grep `AgentSession`（protocol 63 + gaf_ai 72 + 文档 46 区域）逐项分类：
  - WS 层（`protocol/`、`consumers`、`ws` 路由）→ `AgentConnection`。
  - LLM 层（`gaf_ai/agent/`、`llm` 调用）→ `LLMAgentSession`。
- 注意：前端类型生成依赖这两模型，须先完成后端改名再重生成。

#### Task P1.3: 前端

- 重生成 `api.generated.ts`；替换 `AgentSession`→对应名（前端调用 WS 处用 `AgentConnection`，AI 会话处用 `LLMAgentSession`）。

#### Task P1.4: 文档

- overview/features 澄清两 `AgentSession` 拆分（OQ-4 已锁定）；评估稿标记 C-3 完成。

## 5. 测试与验收

- `makemigrations --check` 无 diff；迁移 up/down 可逆，数据条数不变。
- `pytest backend/protocol backend/gaf_ai` 通过（WS 连接 + LLM 会话）。
- 前端 `tsc --noEmit` 无 `AgentSession` 残留。
- 手动：Agent 连接后端 WS、发起 LLM 对话均正常。

## 6. 回滚

- 两模型迁移反向 + 代码 revert（注意前端类型一并回退）。
