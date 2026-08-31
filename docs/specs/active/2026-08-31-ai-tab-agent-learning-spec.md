---
summary: AI 页签完整改造 spec — 学习驱动 + 求职对标 (LangGraph/MCP/RAG/多 provider)
applies_to: [frontend, backend, ai, spec]
key_decisions:
  - AI 页签改造 = 学习载体 + JD 技术对标, 非纯功能迭代
  - 框架策略: 不加新框架, 把 langgraph 从传递依赖变为亲手写图 + 补 MCP/RAG rerank/Agent 评测
  - 关联: TD-423 (LLM 多 provider + AI 页签分组)
last_updated: 2026-08-31
status: active
---

# AI 页签完整改造 Spec（学习驱动 · 求职对标）

> **目的**：把 GAF 的 AI 页签从"8 页平铺"重构为「多服务商 LLM 配置 + 深度 Agent 能力」，同时作为**学习 LangGraph / MCP / RAG 工程化**的落地载体，对齐 2026 年 AI Agent 开发岗 JD。
> **关联 TD**：TD-423（已登记 `docs/archive/active-tech-debt.md`）。本 spec 即 TD-423 的实施计划。

## 1. 背景与目标

### 1.1 现状（2026-08-31 核实）
- `settings.LLMConfig` 为**单条**模型 → 只能配一个 provider，切换即覆盖 key，无法多服务商并存
- AI 页签 8 子页平铺：`assistant/qa/anomaly/log-analysis/skill-editor/skill-market/config/usage`，横跨 4 维度无分组
- `assistant`(LangGraph Agent) 与 `qa`(RAG QASession) 两个对话入口并存（历史重叠）
- Agent 用 `langchain.agents.create_agent` 高层封装；`langgraph` 在 requirements 但代码未直接 import
- RAG 为基础向量检索（chromadb + fastembed），无 rerank / 评测
- 无 MCP；无 Agent 评测体系；无可观测性对 Agent 轨迹的适配

### 1.2 目标
1. **多服务商 LLM 配置**：Provider[apiKey/baseUrl] → Model[] 两级结构，集中管理 + 按用途激活 + 每 provider 连通测试（对齐 VS Code BYOK / Continue.dev 实践）
2. **AI 页签信息架构**：4 分组（对话 / 分析 / Skill / 配置运维）
3. **Agent 深度**：手写 LangGraph 状态图替换 `create_agent`；补 MCP；补 RAG rerank + Agent 评测
4. **求职对标**：每阶段产出可写进简历的"落地成果 + 量化指标"

## 2. JD 需求对标（2026 年 8 份真实岗位调研）

| # | JD 高频要求 | 代表来源 | GAF 现状 | 本 spec 覆盖阶段 |
|---|------|---------|---------|--------------|
| 1 | 精通 LangChain/**LangGraph**，深入底层原理 | 腾讯/平安/51job/Agentic 岗 | 只有 create_agent 高层封装 | **Phase 2** |
| 2 | **MCP** / 工具协议 / Skills | 搜狐畅游/平安/Agentic | 无 | **Phase 2** |
| 3 | RAG 全链路（解析/切片/Embedding 选型/**Rerank**/评测） | 腾讯/51job/20-40K 岗 | 基础检索 | **Phase 3** |
| 4 | **Agent Evaluation** / Tracing / 可观测性 | 搜狐/平安/51job | 无评测体系 | **Phase 3** |
| 5 | 多 Agent / **A2A** 协作 | 京东/灵灵熠/平安 | 单 Agent | **Phase 3(拓展)** |
| 6 | Function Calling / Tool Use 封装 | 全部 | ✅ 已有(skill_tool_adapter) | 巩固 |
| 7 | 多服务商模型集成/路由/成本控制 | 20-40K 岗/平安 | LLMConfig 单条; 有 pricing | **Phase 1** |
| 8 | 全栈工程(Git/CI/测试/可观测) | 全部 | ✅ 已有(pytest/tsc/eslint) | 贯穿 |

## 3. 框架选型评估（回答"需要这么多吗"）

**结论：不加新框架；把已有框架用深。** 核心三点：
- LangChain + chromadb/fastembed = 必要底座（保留）
- langgraph = 声明未用 → **Phase 2 真正手写**（从"会调用"到"会造图"，JD 分水岭）
- 补 MCP + RAG rerank/eval = JD 缺口，非框架膨胀
- 自研 BaseLLMClient（requests 直连，不用 openai SDK）= 保留（少依赖 + 学习协议）

## 4. 分阶段 Spec

### Phase 1：多服务商 LLM 配置（入门 · 全栈）

**目标**：`LLMConfig` 单条 → 多 Provider 并存；AiConfigPage 升级为 Provider 列表 + Model 管理 + 连通测试。

**后端**（`backend/settings/`）：
- `LLMConfig` 保留（默认/激活 provider 指针），新增 `LLMProvider` 模型：
  - `name`(唯一), `provider_type`(openai/deepseek/qwen/ollama/custom), `api_base`, `api_key`(加密存), `is_active`(每类型可多 provider 但 ≤1 激活), `models`(JSONField: 该 provider 下模型列表), `created_at/updated_at`
  - 迁移：从旧 LLMConfig 播种默认 provider
- 序列化/视图：`LLMProviderViewSet`（CRUD + `test` action 复用 `testLlmConnection` + `set_active` action）
- API：`/api/v2/settings/llm-providers/` + `/…/test/` + `/…/set-active/`
- `gaf_ai.llm_router` 改为按 `is_active` provider 构建 client

**前端**（`frontend/src/pages/AI/AiConfigPage.tsx`）：
- 重构为「Provider 卡片列表」：每卡 = provider 名 + base_url + 状态灯(激活/未激活) + 编辑/测试/设为激活/删除；顶部"+"添加 Provider
- 每个 Provider 内 Model 列表：增删模型名 + 标记默认
- 连接测试：复用 PROVIDER_PRESETS，测试结果含 latency
- AI 侧边栏分组：`对话(assistant/qa) / 分析(anomaly/log-analysis) / Skill(editor/market) / 配置运维(config/usage)`

**测试**：backend `settings/tests/test_llm_provider.py`（≥5：CRUD/激活唯一性/key 加密往返/test/多 provider 并存）+ 前端 vitest（AiConfigPage ≥3）+ tsc 0
**JD 收获**：多服务商集成、模型路由、密钥安全、API 设计、全栈落地
**验收**：可同时配 ≥2 provider 互不覆盖；各自 test 连通；一键切换激活；AI 侧边栏 4 分组清晰

### Phase 2：手写 LangGraph + MCP（进阶 · 招聘核心）

**目标**：把 `create_agent` 高层封装替换为**手写 LangGraph 状态图**；新增 MCP 工具接入。

**后端**（`backend/gaf_ai/agent/`）：
- 新增 `langgraph_graph.py`：手写 `StateGraph`（State: messages+context；节点: router/tools/responder；边: 条件路由，ReAct 循环 + 最大迭代护栏）
- `graph.py` 改为调用手写图（保留 create_agent 作为开关对照，便于对比学习）
- 新增 MCP：`agent/mcp/` 提供 `MCPServer`/`MCPClient` 抽象 + 1 个示例 MCP server（把 GAF 工具 `get_execution_detail`/`search_similar_errors` 暴露为标准 MCP tool）；`skill_tool_adapter` 改为走统一 Tool 协议（LangChain tool + MCP tool 统一注入）
- 工具注册表：`TOOL_REGISTRY` 集中声明，支持 langchain_tool / mcp_tool 两种类型

**前端**：`/ai/assistant` 增加 Agent 轨迹可视化（节点/边/工具调用时间轴 + token 消耗）—— 对应 JD"前端变成 Agent 观测层"

**测试**：`gaf_ai/tests/test_langgraph_graph.py`（图构建/条件路由/迭代护栏/工具调用成功路径/失败兜底）+ MCP server/client 单测
**JD 收获**：手写状态图（面试可讲原理）、MCP 协议、Tool Calling、Agent 可观测性、轨迹可视化
**验收**：LangGraph 图可运行且与 create_agent 输出一致；Agent 可通过 MCP 调 GAF 工具；前端可见轨迹

### Phase 3：RAG 工程化 + Agent 评测（加分 · 拉开差距）

**目标**：RAG 从基础检索升级为「rerank + 评测」，新增 Agent Evaluation 体系。

**后端**（`backend/gaf_ai/`）：
- RAG：`rag.py` 增加 rerank 步骤（交叉编码器 rerank top-N，可选 `cross-encoder` 或 LLM 重排）、混合检索（向量 + 关键词 BM25 可选）、chunk 策略可配；引入离线评测脚本 `scripts/ai/rag_eval.py`（Hit Rate / MRR / 准确率，跑真实 QA 集）
- Agent 评测：`evaluation.py` 扩展为 Agent 评测（工具调用成功率、规划准确率、响应延迟、token 成本；可对接 LLM-as-judge）
- 可观测性：Agent 执行 trace 落库（节点/工具/耗时/token），`/ai/usage` 展示

**测试**：RAG rerank 单测（top-k 重排正确性）+ eval 脚本冒烟（真实代码库 QA 集）+ Agent 评测接口测试
**JD 收获**：RAG 全链路（能说"混合检索+chunk 优化把命中率从 X→Y"）、Agent 评测体系、成本/延迟优化、可观测性
**验收**：RAG 命中率有可量化提升（Hit Rate 报告）；Agent 评测有指标看板；trace 可视化可用

## 4.0 阶段状态表

| Phase | 状态 | 完成 commit | 验收证据 |
|-------|------|------------|---------|
| Phase 1 多服务商 LLM 配置 | ✅ | 本 spec Phase 1 commit | backend `test_llm_provider.py` 8 项 + frontend `AiConfigPage.test.tsx` 7 项 + tsc 0 + ruff 0 |
| Phase 2 手写 LangGraph + MCP | ⏳ 未开始 | - | - |
| Phase 3 RAG rerank + 评测 | ⏳ 未开始 | - | - |

## 5. 学习路线（配合执行）

1. LangChain/LangGraph 官方 docs 快速过 → Phase 1（熟悉全栈 + 协议）
2. LangGraph 手写图 + MCP 官方规范 → Phase 2（面试核心）
3. RAG 工程化 + Agent 评测 → Phase 3（拉开差距）
4. 每阶段沉淀：代码 + 测试 + 反思 + 一段可写进简历的"成果+量化"

## 6. 验收总览

| Phase | 可交付 | JD 能力点 |
|------|--------|----------|
| 1 | 多 provider 配置 + AI 分组 | 多服务商/路由/密钥安全 |
| 2 | 手写 LangGraph + MCP + 轨迹 | Agent 原理/MCP/可观测 |
| 3 | RAG rerank + 评测 + trace | RAG 工程化/评测/成本 |

> 执行粒度：每 Phase 一个 spec 阶段（见 `docs/specs/`），单阶段完成即 commit；本文件为总纲。
