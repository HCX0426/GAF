---
date: 2026-07-12
symptom: [langgraph, react-agent, langchain, django-integration, llm-fallback, function-calling]
solution: LangGraph ReAct Agent 实施记录 — Django 子包模型 app_label + re-export 模式, LangChain .with_fallbacks 映射 GAF 4 级降级, 本地 LLM 不支持 function calling 时优雅降级
diff_keywords: ["models", "llm", "adapter", "llm_adapter", "graph", "views", "langgraph", "react-agent", "langchain", "django-integration", "llm-fallback", "function-calling"]
related_files:
  - backend/gaf_ai/agent/models.py
  - backend/gaf_ai/agent/llm_adapter.py
  - backend/gaf_ai/agent/graph.py
  - backend/gaf_ai/agent/views.py
  - backend/gaf_ai/models.py
created_by: AI
priority: medium
n_id: N158
topic: agent-impl
level: L0
---


# N158 — LangGraph ReAct Agent 实施记录

## 触发原话

用户: "实现 LangGraph ReAct Agent 用于深度日志分析" (来自 spec.md spec27-cleanup archive (已删除))

## 根因 / 场景

引入 LangChain + LangGraph 构建 ReAct Agent, 用于将日志分析从"单轮直接问答"升级为"多轮推理+工具调用". 实施过程中遇到 3 个集成模式问题:

### 1. Django 子包模型不发现

**问题**: `AgentSession` 定义在 `backend/gaf_ai/agent/models.py` (子包), Django 默认不发现, `makemigrations` 找不到模型.

**根因**: Django app registry 只扫描 app 根目录的 `models.py`, 子包模型需要显式 `app_label` + 在 app 根 `models.py` re-export.

**修复**:
```python
# backend/gaf_ai/agent/models.py
class AgentSession(models.Model):
    class Meta:
        app_label = 'gaf_ai'  # 显式声明所属 app
        ...

# backend/gaf_ai/models.py (app 根)
from gaf_ai.agent.models import AgentSession  # noqa: E402,F401  re-export
```

> 注: 路径原为 `backend/ai/` + `app_label='ai'`, 2026-07-15 由 TD-116 重命名为 `backend/gaf_ai/` + `app_label='gaf_ai'` 以消除与 `agent/src/ai/` 的顶层包名冲突. 教学要点 (子包模型需显式 app_label + re-export) 不变.

**Y/N 检查**: 在 Django 子包添加模型时 — (1) Meta 是否设 `app_label`? (2) app 根 `models.py` 是否 re-export?

### 2. LangChain `.with_fallbacks()` 映射 GAF 4 级降级

**场景**: GAF 已有 `LLMRouter` 4 级降级 (preferred → backup → local → offline). 引入 LangChain 后, 不重复写路由逻辑, 用原生 `.with_fallbacks()` 映射.

**实现**: `build_agent_llm()` 在 `llm_adapter.py` 中按顺序构建 `ChatOpenAI` 列表, 第一个 `.with_fallbacks(其余)`.

**设计决策**:
- `offline` 级别不映射 — Agent 分析时如果所有 LLM 都挂了, 直接报错比返回占位文本更合理
- `openai` SDK 是 LangChain 内部依赖, 接受这个依赖引入 (GAF 之前刻意用 `requests` 避免 openai SDK)

### 3. 本地 Qwen2.5-7B 不支持 function calling

**症状**: API 返回 200, 但 `reasoning_steps` 是 fallback 解析结果 (不是真正的 ReAct 推理链).

**根因**: 本地 Ollama 跑的 Qwen2.5-7B 不支持 OpenAI function calling 协议, LangGraph `create_react_agent` 无法触发 tool calling 循环.

**优雅降级**:
- `_extract_reasoning_steps()` 处理空 tool_calls 情况, 至少返回 final answer 作为单个 thought
- `_parse_agent_result()` 用 markdown fence stripping + JSON parse + fallback
- AgentSession 仍持久化 (status='completed', model_used 记录实际 LLM)

**Y/N 检查**: Agent 代码是否处理不支持 function calling 的 LLM? (不崩溃, fallback 解析, 持久化会话)

## 验证

- T1-T13 全部完成, commit `-` (17 files, 1445 insertions)
- 11 pre-commit hooks 全部通过
- V1-V10: 9 ✅ + 1 🔧 (V6 — Agent 调用 Tool 需 function calling LLM)
- TSC 0 errors, Playwright E2E 0 console errors

## 分发判定 (L0)

**只问 1 个问题**: 这些模式有跨项目 Y/N 检查清单价值 OR 揭示架构反模式?

- Django 子包模型 app_label + re-export: Django 通用模式, 但 GAF 项目其他模块未重复出现此问题 (一次性设置)
- LangChain `.with_fallbacks()` 映射: 项目特定实现, 不跨项目
- 本地 LLM 降级: 项目特定

**结论**: L0 (1 层, 仅 lessons/) — 一次性实施记录, 无需提升到 arch-mistakes / yn-matrices / project_rules.

**后续提升候选**: 如果后续在 GAF 中再次出现 Django 子包模型不发现问题, 则提升为 L1 (Django 子包模型 app_label + re-export 模式).
