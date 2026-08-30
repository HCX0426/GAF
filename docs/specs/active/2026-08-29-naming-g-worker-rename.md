---
spec: 2026-08-29-naming-g-worker-rename
title: 命名归一化 G 批：Agent → Worker 术语重构（执行节点/进程及全部派生符号）
status: active
created: 2026-08-29
started: 2026-08-30
estimated_effort: 3 days
risk: high
depends_on: [2026-08-29-naming-c-agentsession, 2026-08-29-naming-e-agent-concepts]
source: docs/analysis/concept-naming-normalization.md §1(Agent→Worker 多行)/§2/§5(17)/§9(OQ-10)/§7(G)
---

# 命名归一化 G 批：Agent → Worker 术语重构

## 1. 背景与动机 (Background)

2026-08-29 **OQ-10 决策**："Agent" 一词保留给未来 AI 智能体（`backend/gaf_ai` LangGraph agent），执行节点/进程及全部派生符号改称 **Worker**，避免未来 AI 模块与现有执行节点概念混淆（详见评估稿 §2/§5(17)/§9 OQ-10）。本批是最高危的术语重构：涉及 Django app 重命名（`backend/agents`→`backend/workers`）、进程目录改名（`agent/`→`worker/`）、模型字段/类改名、WebSocket 符号改名、前端生成类型重生成。

## 2. 核心问题 (Problem)

| # | 符号 | 位置 | 目标 |
|---|------|------|------|
| G-1 | `Agent`(模型) | `backend/agents/models.py:58` | `Worker` |
| G-2 | `backend/agents`(Django app) | app 名 | `backend/workers` |
| G-3 | `agent/`(进程目录) | `worker/src/__main__.py` 等 | `worker/` |
| G-4 | `AgentConnection`(WS 客户端) | `worker/src/client/connection.py:153` | `WorkerConnection` |
| G-5 | `AgentStatus`(agent 端常量) | `worker/src/core/constants.py:141` | `WorkerStatus` |
| G-6 | `AgentConsumer`(protocol) | `backend/protocol/consumers.py:123` | `WorkerConsumer` |
| G-7 | `AgentToken`(字段/端点) | `backend/agents/models.py:134` + 端点 | `WorkerToken`(字段 `worker_token_hash`) |
| G-8 | `agent_runtime` | `backend/agents/agent_runtime.py` | `worker_runtime` |
| G-9 | `AgentViewSet` | `backend/agents/view_sets/crud.py:38` | `WorkerViewSet` |
| G-10 | `run_agent` | `worker/src/__main__.py:436` | `run_worker` |
| G-11 | `AgentLLMClient` | `worker/src/ai/llm_client.py:92` | `WorkerLlmClient` |
| G-12 | `AgentSelector` | `tasks/agent_selector.py:132` | `WorkerSelector` |
| G-13 | `agents.Device`(ORM) | `backend/agents/models.py:178` | `workers.Device` |
| G-14 | `protocol.AgentSession`(WS 会话) | protocol 域 | `WorkerSession`（详见 C-3，本批同步收口） |

> **保留不改名**：`gaf_ai.agent.AgentSession` / `backend/gaf_ai` 全部 AI 智能体符号（OQ-10，干净名给 AI）。

## 3. 目标 (Goals)

1. G-1~G-14 全量 `Agent`(执行节点语义) → `Worker` 重构：模型、app、目录、类、常量、WS 符号、端点、前端生成类型。
2. 全仓 import/引用改写；生成迁移（app 重命名最重，需含数据迁移）；前端 `api.generated.ts`/`models/*.ts` 重生成。
3. `backend/gaf_ai` AI 智能体符号保留 `Agent` 命名；文档/注释二处显式区分 Worker vs Agent(AI)。

## 4. 实施计划 (Implementation)

### 阶段状态表

| 阶段 | 内容 | 状态 |
|------|------|------|
| P1 | 后端 Django app 重命名 `agents`→`workers` + 迁移(含数据迁移) + settings/urls/import | ✅ |
| P2 | 模型/字段改名：G-1 `Agent`→`Worker`、G-7 `agent_token_hash`→`worker_token_hash`、G-13 `agents.Device`→`workers.Device` | ✅ |
| P3 | agent 进程目录 `agent/`→`worker/` + 符号 G-4/G-5/G-10/G-11 + `__main__` 入口 | ✅ |
| P4 | protocol/WS 符号 G-6 `AgentConsumer`→`WorkerConsumer`、G-14 `AgentSession`→`WorkerSession`(C-3) + consumers.py 路由(随 F-5) | ✅ |
| P5 | 其余后端符号 G-8/G-9/G-12 + `tasks` 选 Worker + `agent_runtime`→`worker_runtime` | ✅ |
| P6 | 前端类型重生成 + 全仓 import/文案改写（约全仓 Agent 执行节点语义处，P6.1 类型重生成 ✅） | 🚧 |
| P7 | 后端+前端+agent 测试全绿；评估稿标记 G 完成 | ⏳ |
| P8 | 架构文档同步：`docs/architecture/overview.md` + `features-overview.md` 执行节点语义 `Agent`→`Worker`（§9.3 概念边界注/§9.5 protocol 模型改 `WorkerSession`/§十 已改名「Worker 架构」已在先行提交；其余 `Agent`(执行节点) 引用随代码重命名同步扫） | ⏳ |

#### Task P1.1: app 重命名（最重）

- Django app `backend/agents`→`backend/workers`：`makemigrations` 重命名 app（含 `AlterModelTable`/迁移文件重命名 + `django_migrations` 表 app 名更新）；更新 `backend/backend/settings.py` `INSTALLED_APPS`、`urls.py`、`manage.py`、所有 `from backend.agents`/`import agents` 引用。
- 注意 `backend/agents/consumers.py` 仅 `AdbLogStreamConsumer` → 随 F-5 改名 `worker_consumers.py`。

#### Task P2.1: 模型/字段

- `Agent`→`Worker`；`Agent.agent_token_hash`→`Worker.worker_token_hash`；`agents.Device`→`workers.Device`（FK 引用方同步）。

#### Task P3.1: 进程目录

- `agent/`→`worker/`；`AgentConnection`→`WorkerConnection`；`AgentStatus`→`WorkerStatus`；`AgentLLMClient`→`WorkerLlmClient`；`run_agent` 入口→`run_worker`；`__main__.py` 顶部 `AgentClient` ghost docstring 修正。

#### Task P4.1: WS 符号

- `AgentConsumer`→`WorkerConsumer`(`protocol/consumers.py:123`)；`protocol.AgentSession`→`WorkerSession`（与 C-3 同改，避免二次迁移）。

#### Task P5.1: 其余后端符号

- `agent_runtime.py`→`worker_runtime.py`；`AgentViewSet`→`WorkerViewSet`；`AgentSelector`→`WorkerSelector`(`tasks/agent_selector.py` 改名 + 引用)。

#### Task P6.1: 前端

- 重生成 OpenAPI 客户端；`Worker`/`WorkerViewSet`/`WorkerSession`/`WorkerToken` 进入 `api.generated.ts`/`models/*.ts`；全仓 "执行节点语义 Agent" 文案→`Worker`（AI 智能体语义保留）。

## 5. 测试与验收

- `pytest backend` + `pytest agent` + 前端 `typecheck` + 前端单测全绿。
- `python manage.py makemigrations --check` 干净；`makemigrations --name rename_agents_to_workers` 仅一次数据迁移。
- grep 全仓 `Agent`(执行节点语义) 残留清零（仅 `backend/gaf_ai` AI 智能体保留）。
- 评估稿标记 G 完成。

## 6. 回滚

- app 重命名带迁移（最重），需完整迁移 + 数据迁移；建议单 PR 收敛，回滚用 `git revert` + 反向迁移。
