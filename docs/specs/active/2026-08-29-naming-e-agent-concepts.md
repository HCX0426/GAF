---
spec: 2026-08-29-naming-e-agent-concepts
title: 命名归一化 E 批：Agent 词族概念消歧（碰撞/双存/三义/幽灵/误导）
status: active
created: 2026-08-29
estimated_effort: 1 day
risk: medium
depends_on: ['2026-08-29-naming-c-agentsession']
source: docs/analysis/concept-naming-normalization.md（agent 审计 2026-08-29） / 探索代理 audit 报告
---

# 命名归一化 E 批：Agent 词族概念消歧

## 1. 背景与动机 (Background)

C 批仅解决了两个 `AgentSession` 模型。2026-08-29 的 agent 词族审计发现，除此外 "Agent*" 仍存在多处碰撞/双存/三义/幽灵/误导，其中 **E-1 直接阻塞 C-3 落地**（C-3 原目标名 `AgentConnection` 与 agent 端既有同名类冲突，已改为 `AgentWsSession`）。本批收口 Agent 词族其余过载，形成自包含归一化单元。

## 2. 核心问题 (Problem)

| # | 项 | 现状 | 目标 | 级 |
|---|----|------|------|----|
| E-1 | protocol 模型 vs agent 端 `AgentConnection` 碰撞 | C-3 原目标 `AgentConnection` 被 `agent/src/client/connection.py:153` 占用 | 后端用 `AgentWsSession`（已在 C-3 修正并验证） | P0 |
| E-2 | token 双存储 | `Agent.agent_token_hash`(`agents/models.py:134`) **与** `protocol.AgentSession.token_hash`(`protocol/models.py:40`) 冗余；auth 实际查 `Agent.agent_token_hash`(`protocol/services.py:86`) | token 归属 `Agent`；移除 session 冗余 `token_hash` 字段 | P1 |
| E-3 | `AgentStatus` 三义 | (a) agent 端 `AgentStatus` StrEnum(`agent/src/core/constants.py:141` 进程生命周期) / (b) `Agent.Status` model(`agents/models.py:61`) / (c) 前端 `AgentStatus`(`frontend/src/types/models/auth.ts:59`) | agent 端 (a)→`AgentProcessStatus`；(b)(c) 保持 | P2 |
| E-4 | 幽灵 `AgentClient` | `agent/src/__main__.py:1` docstring "create AgentClient" 无此类（实为 `AgentConnection`） | 修注释→`AgentConnection` | P2 |
| E-5 | `AgentLLMClient` 误导 | `agent/src/ai/llm_client.py:92` 仅是调 backend `/ai/agent/analyze/` 的 HTTP 客户端，非 LLM agent（真 LangGraph Agent 在 `backend/gaf_ai`） | →`AgentSideLlmClient` | P2 |
| E-6 | 文档四义未拆 | overview §2 把 Agent 模型/进程/AgentConsumer/agent_runtime 混称 "Agent" | overview §2 加一段拆解四义 | P2(文档) |

## 3. 目标 (Goals)

1. E-1：确认 C-3 已用 `AgentWsSession`，agent 端 `AgentConnection` 不变（验证无碰撞）。
2. E-2：token 单一归属 `Agent`；清理 `protocol.AgentSession.token_hash` 冗余字段（迁移移除）。
3. E-3：agent 端进程状态枚举改名 `AgentProcessStatus`，与 model/frontend 状态区分。
4. E-4：修幽灵注释。
5. E-5：`AgentLLMClient`→`AgentSideLlmClient`。
6. E-6：overview §2 加 Agent 四义拆解段。

## 4. 实施计划 (Implementation)

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | E-1 验证（C-3 已含）+ E-2 token 字段清理 | ⏳ |
| P2 | E-3 `AgentProcessStatus` + E-4 注释 + E-5 客户端改名 | ⏳ |
| P3 | E-6 文档四义拆解 | ⏳ |

#### Task P1.1: E-1 验证

- 确认 C-3 落地后后端 `AgentWsSession` 与 agent 端 `AgentConnection` 无同名冲突（grep 双 `AgentConnection` 应仅在 agent 端）。

#### Task P1.2: E-2 token 双存

- `backend/protocol/models.py:40` 移除 `token_hash` 字段（迁移删除；session 通过 FK/关联查 `Agent.agent_token_hash`）。
- 确认 `protocol/services.py:86` 仍用 `Agent.agent_token_hash`（无破坏）。

#### Task P2.1: E-3 改名

- `agent/src/core/constants.py:141` `AgentStatus`→`AgentProcessStatus`（agent 内部引用全改）。

#### Task P2.2: E-4/E-5

- `agent/src/__main__.py` docstring `AgentClient`→`AgentConnection`。
- `agent/src/ai/llm_client.py:92` `AgentLLMClient`→`AgentSideLlmClient`（含引用）。

#### Task P3.1: E-6 文档

- `docs/architecture/overview.md` §2 增："Agent 四义：① `Agent` 注册模型(backend/agents) ② 运行 agent Python 进程(`__main__.run_agent`) ③ `AgentConsumer`(WS 协议消费者, **位于 `backend/protocol/consumers.py:123`，非 `agents` app**) ④ `agent_runtime`(backend 子进程管理器)"。注：`backend/agents/consumers.py` 仅含 `AdbLogStreamConsumer`（名不副实），改名见批 F-5。

## 5. 测试与验收

- `pytest backend/protocol backend/agents agent/tests` 通过。
- agent 端 `AgentConnection`/`AgentProcessStatus`/`AgentSideLlmClient` 编译/运行正常；grep `AgentClient`(幽灵) 清零。
- 评估稿标记 E 批完成。

## 6. 回滚

- E-2 字段移除有迁移反向；其余纯改名/文档，git revert 即可。
