---
spec: 2026-08-29-naming-e-agent-concepts
title: 命名归一化 E 批：Agent 词族消歧（Worker / Agent 术语拆分）
status: active
created: 2026-08-29
estimated_effort: 0.5 day
risk: medium
depends_on: []
source: docs/analysis/concept-naming-normalization.md §1(Agent→Worker 多行)/§2/§5(17)/§9(OQ-10)/§7(G)
---

# 命名归一化 E 批：Agent 词族消歧（Worker / Agent 术语拆分）

## 1. 背景与动机 (Background)

评估稿三项审计（agent 进程 / backend/device_bridge / backend/agents）发现 "Agent" 一词在 AI 智能体、执行节点/进程、WS 客户端、状态、令牌、消费者、视图、运行时、选择器、目录、Django app 等十余处混用。2026-08-29 **OQ-10 决策**：将 "Agent" 保留给未来 AI 智能体（`backend/gaf_ai` LangGraph agent），执行节点/进程及全部派生符号改称 **Worker**。本批为概念消歧与术语落地的总纲，具体符号改名由批 G 统实施。

## 2. 核心问题 (Problem)

| # | 项 | 现状 | 目标 | 处置 |
|---|----|------|------|------|
| E-1 | `AgentConnection`(agent 端) vs `AgentSession`(protocol) 碰撞 | 与 `AgentSession` 混淆 | `AgentConnection`→`WorkerConnection`；`AgentSession`(protocol)→`WorkerSession`(C-3) | **已消碰撞**（G / C-3） |
| E-2 | `AgentToken`(agent) vs `AgentSession.token_hash`(gaf_ai) | 评估稿曾判"双重存储冗余" | 修订：Worker 令牌(`Worker.worker_token_hash`) 与 AI 会话令牌(`AgentSession.token_hash`) **是不同物**（执行节点鉴权 vs AI 会话鉴权），非冗余 | 文档修订（G 改名） |
| E-3 | `AgentStatus`(agent 端) | `core/constants.py:141` | → `WorkerStatus` | G |
| E-4 | `Agent` 模型 + `backend/agents` app + `agent/` 目录 | 执行节点/进程 | → `Worker` + `backend/workers` + `worker/` | G（最高危） |
| E-5 | `AgentLLMClient`(agent 侧) | `ai/llm_client.py:92` | → `WorkerLlmClient`（Worker 侧 LLM 客户端，区别于 AI 智能体） | G |
| E-6 | "Agent" 四义 | ① 模型(backend/agents) ② 进程(agent/) ③ `AgentConsumer`(protocol) ④ `agent_runtime` | → ① `Worker`(backend/workers) ② `worker/` 进程 ③ `WorkerConsumer`(protocol) ④ `worker_runtime`；"Agent" 单列=AI 智能体 | G + OQ-10 |

## 3. 目标 (Goals)

1. 确立术语拆分：`Agent`=AI 智能体（未来）；`Worker`=执行节点/进程/派生符号。
2. 落地 E-1~E-6 的符号改名（具体由批 G 统实施），并修订评估稿 E-2 的"冗余"误判。
3. 文档/代码注释显式区分 Worker 与 Agent(AI)。

## 4. 实施计划 (Implementation)

> 本批为概念总纲，实际 rename 在批 G（见其阶段表）。本批仅做文档/注释层面的术语对齐与误判修订。

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 评估稿 E-2 冗余误判修订（Worker 令牌 vs AI 会话令牌 不同物） | ⏳ |
| P2 | 全仓概念术语注释对齐（Worker / Agent(AI)） | ⏳ |
| P3 | 批 G 实施 E-1~E-6 符号改名（派生 spec） | ⏳(依赖 G) |

#### Task P1.1: E-2 修订

- 评估稿 §3/§5 将 `AgentToken`(agent) 与 `AgentSession.token_hash`(gaf_ai) 的"双重存储冗余"改为"不同物"：Worker 令牌用于执行节点鉴权，AI 会话令牌用于 AI 智能体会话鉴权。

#### Task P2.1: 术语注释

- 在 `agents/models.py`(→`workers`)、`worker/src/__main__.py`(→`worker`)、`protocol/consumers.py`(WorkerConsumer) 等加/改注释，显式标注 "Worker = 自动化执行节点；Agent = AI 智能体（见 backend/gaf_ai）"。

#### Task P3.1: 派生批 G

- 创建并依赖 `naming-g-worker-rename` 实施 E-1~E-6 全部符号改名（见该 spec）。

## 5. 测试与验收

- 评估稿 E-2 修订到位；grep `Agent`(执行节点语义) 在代码侧降至仅 AI 智能体相关（`backend/gaf_ai`）。
- 批 G 完成后评估稿标记 E 完成。

## 6. 回滚

- 纯文档/注释 + 批 G 实施；G 带迁移，其余 git revert。
