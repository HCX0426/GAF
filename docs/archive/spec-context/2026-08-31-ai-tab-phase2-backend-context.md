---
spec: 2026-08-31-ai-tab-agent-learning-spec
phase: Phase 2 手写 LangGraph + MCP（后端核心）
created: 2026-08-31
---

# Spec Context — AI 页签改造 Phase 2（手写 LangGraph + MCP 后端核心）

## 用户决策

- **MCP 采用自研轻量协议**：不安装官方 `mcp` SDK（符合 spec §「少依赖 + 学习协议」哲学），手写 `MCPServer/MCPClient` 抽象 + JSON-RPC `tools/list` / `tools/call` 传输边界。
- **本次只做后端核心**：手写图 + `TOOL_REGISTRY` + MCP 抽象 + 后端测试（提交）；前端轨迹可视化**延后**独立子阶段。

## N151 架构评估

### 1. 架构盘点（4 维度）

- **数据/状态**: 现有 agent 状态 = `messages` + `context`（system_prompt）；`gaf_ai.tasks.run_agent_analysis_task` 消费 `agent_result.get('messages')` 解析最终回答。
- **依赖**: `graph.py::build_log_analysis_agent` 负责把 LLM + 工具（6 个 GAF 分析工具 + 每用户 skill tools）装成 agent；`llm_adapter.build_agent_llm` 构建 LLM；`skill_tool_adapter.collect_skill_tools` 注入用户 skills。`langgraph 1.2.9` / `langchain 1.3.13` 已装。
- **调用**: `tasks.py` 调用 `build_log_analysis_agent(...)` → `.invoke(...)`；工具经 `@tool` 声明；`create_agent` 高层封装当前为默认。
- **历史**: 只有 `create_agent` 高层封装；无手写图、无工具注册表、无 MCP。模型 vision 过滤靠 `llm_router.get_tools_for_model`（返回 4-7 个工具列表的手动白名单）。

### 2. 识别反模式

- **❌ 工具声明散落**: 6 个 GAF 工具在 `graph.py` 内联 import + 手动装配；skill tools 另走 `collect_skill_tools` —— 工具来源不统一，vision 过滤逻辑分散。
- **❌ `create_agent` 黑盒**: 面试无法讲清状态图/路由;可观测轨迹数据不足。

### 3. A/B/C 备选

- **A（采用）**: 手写 `StateGraph`（AgentState: messages/context/iteration/max_iterations/trajectory；节点 router/tools/responder；条件边 ReAct 循环 + 迭代护栏）+ 统一 `TOOL_REGISTRY`（langchain_tool / mcp_tool 两型 + vision_required 元数据）+ 轻量 MCP 包。① 全覆盖 spec §后端 ② 工具注册表归一化 ③ 保留 create_agent 开关对照学习 ④ MCP 协议自研可讲原理。⑤ 变更面=新增 5 模块 + 改 graph.py + 改测试。
- **B**: 只改 `create_agent` 参数/工具列表（vision 过滤）。① 改动最小 ② 但不满足 spec「手写图 + 统一协议」核心目标 ③ 学习价值低。
- **C**: 引入官方 `mcp` SDK + create_agent。① 规范 ② 违背「少依赖 + 学习协议」决策 ③ 多一层 SDK 依赖。

### 4. 拒绝双套 / 最小化

- 拒绝 B（达不到 spec 目标）、拒绝 C（违背用户少依赖决策）。
- 采纳 A；`create_agent` 保留在 feature-flags 开关后，非双套并存（同一函数二选一运行时分支，非两套长期恒定代码）。

### 5. AI 自决边界

- 方向判定：A。后端核心在 spec/用户已批准的 Phase 2 范围内，自决执行。

## N167 七维度评分（修改清单）

| 维度 | 评分 | 说明 |
|------|:---:|------|
| 1 架构长远性 | 9 | 手写 StateGraph 可讲解、可扩展 trajectory 观测 |
| 2 全局归一化 | 9 | TOOL_REGISTRY 统一 langchain/mcp 两类工具 + vision 元数据 |
| 3 逻辑正确性 | 9 | 迭代护栏/异常隔离/未知工具均有测试 |
| 4 可测试性 | 9 | test_langgraph_graph 19 项 + skill_tool_adapter 32 项 |
| 5 性能 | 8 | 手写图无多余开销；注册表 O(n) 解析 |
| 6 易用性 | 8 | 模型名已知时按 is_vision_capable 过滤，未知全暴露 |
| 7 长期维护成本 | 8 | 单一注册中心，新增工具只加一行 |

总分 60 / 7 维 ≥ 19 且领先达标 → AI 自决执行。

## 关键决策

- **自研轻量 MCP**：`mcp/_base.py`（`MCPServer`/`MCPToolSpec`/`MCPError`，JSON-RPC `tools/list` + `tools/call`，`handle_message` 传输边界）+ `client.py`（把 server 工具包装成 LangChain `@tool`）+ `gaf_mcp_server.py`（暴露 get_execution_detail/get_execution_steps/search_similar_errors/get_task_config）。
- **手写图默认路径**：`langgraph_graph.build_react_graph()` / `invoke_react()`；`graph.py` 默认走手写图，`AGENT_USE_CREATE_AGENT=1` 走旧 create_agent（对照学习）。
- **`AGENT_USE_CREATE_AGENT` 设置**：读 Django settings 或 env（`_settings_get`）。
- **vision 过滤迁移**：由 `llm_router.get_tools_for_model` 手动画白名单 → `is_vision_capable(model_name)` + `TOOL_REGISTRY.resolve_tools(vision_available=...)`；`gpt-4o`(6 工具含 screenshot) vs `deepseek-chat`(5 不含 screenshot) 语义等价保持。

## 注册表与工具

- 6 个核心 GAF 工具 import 时注册进 `TOOL_REGISTRY`（screenshot 标 `vision_required=True`）。
- `build_log_analysis_agent` 用 `TOOL_REGISTRY.resolve_tools(...)` 解析（模型名已知→is_vision_capable；未知→全暴露），再追加每用户 skill tools。

## 测试与回归

- 新增 `test_langgraph_graph.py` 19 项通过（图构建/条件路由/迭代护栏/异常隔离/未知工具/MCP tools-list+call/MCPClient 发现/注册表解析含 vision）。
- `test_skill_tool_adapter.py` 32 项通过：6 个 create_agent 旧路径测试以 `@patch.dict(os.environ, {'AGENT_USE_CREATE_AGENT':'1'})` 强制走旧路径 + patch `langchain` 模块级 `create_agent`。
- ruff 0；全量 `-n 8` 的失败均为**既有无关失败**（RunAgentAnalysisTaskUnitTest 的 `task_result_id`/`execution_id` 参数不匹配、retrieval_quality embedding hit-rate 阈值、`-n 8` Chroma/DB 争用——后者单跑通过），非本次回归。

## 用时

- start_ts: 2026-08-31 18:0x | end_ts: 2026-08-31 18:5x | duration: ~50 min（对照大修改基线 < 60 min 内；耗时主要在修复寄存器哈希 bug + 迁移 6 个 create_agent 测试到 legacy 开关路径）
