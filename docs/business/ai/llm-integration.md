---
summary: GAF LLM 集成设计
applies_to: ['architecture', 'design']
key_decisions:
  - 上下文收集策略
  - 降级策略
  - Phase 4.3-4.7 实现完成：6 个 builtin Skill YAML + dual-schema loader + LLMRouter 4 级降级链 + ContextCollector + TokenUsageTracker + Agent LLM 客户端
last_updated: 2026-07-04
---

# GAF LLM 集成设计

> 版本：1.2 | 日期：2026-07-04 | 修订：Phase 4.3-4.7 实现完成，状态矩阵全部 ✅

## 0. 现实状态（2026-07-04 审计，Phase 4.3-4.7 后更新）

> ✅ **Phase 4.3-4.7 实现完成**：原设计稿中的命名类（LLMRouter / ContextCollector / TokenUsageTracker）已全部实现，6 个内置 Skill YAML 已创建，降级链已接入 `call_llm()`，Agent 端 LLM 客户端已新增。

### 0.1 实现状态矩阵

| 文档章节 | 文档声称 | 现实代码 | 状态 |
|----------|----------|----------|------|
| §2.2 `BaseLLMClient` (ABC) + `OpenAIClient` | 抽象基类 + OpenAI 兼容子类 | `backend/gaf_ai/qa_llm_client.py:30` 的 `LLMClient`（具体类）仍是现有实现；`OpenAIClient` 别名沿用 `LLMClient`（无独立 ABC，但 Phase 4.4 router 通过 duck-typing 接入）——✅ 2026-08-08 已提取 backend/gaf_ai/base_client.py::BaseLLMClient(ABC)，router 已依此接口 | 🟡 部分对齐（duck-typed，无 ABC） |
| §2.3 `LLMRouter` | 多模型路由 + 降级链 | `backend/gaf_ai/llm_router.py`（Phase 4.4）实现 `LLMRouter` + `OfflineClient` + `LLMAllClientsFailedError`；4 级降级 preferred → backup → local → offline；`call_llm()` 通过 `_get_llm_router()` 委托 | ✅ 已实现 |
| §3-§4 6 个内置 Skill YAML | error_diagnosis / task_optimization / log_analysis / script_generation / qa_assistant / resource_analysis | `backend/skills/builtin/{error_diagnosis,task_optimization,log_analysis,script_generation,qa_assistant,resource_analysis}.yaml`（Phase 4.3）；`loader.py` 已支持 dual-schema（legacy `parsing_steps`+`output_template` 或 design `system_prompt`+`user_prompt_template`）；`load_builtin_skills()` 扫描 `skills/builtin/` 子目录 | ✅ 已实现 |
| §5 `ContextCollector` 类 | 上下文收集器 | `backend/gaf_ai/context_collector.py`（Phase 4.5）实现 `ContextCollector` 类 + `build_skill_context()` + `build_qa_context_wrapper()`；与 `backend/gaf_ai/context_collector.py:build_qa_context()` 互补（task-context vs project-context） | ✅ 已实现 |
| §6 `TokenUsageTracker` 类 | Token 用量追踪 | `backend/gaf_ai/token_tracker.py`（Phase 4.6）实现 `TokenUsageTracker` 类（`record()` / `check_budget()` / `generate_usage_report()`）+ `get_token_tracker()` 单例；DB-backed（`LLMUsageLog`），无内存缓存 | ✅ 已实现 |
| §8 降级链 | 首选 → 备用 → 本地 → 离线 | `backend/gaf_ai/llm_service.py:_get_llm_router()`（Phase 4.4）构建 4 级 router；`OfflineClient` 始终兜底；`call_llm()` 返回 `route` 字段标识命中级别；`LLMUsageLog.route` 字段记录 | ✅ 已实现 |
| §0.3 Agent 端 LLM 客户端 | `worker/src/` 无 LLM 模块 | `worker/src/ai/llm_client.py`（Phase 4.7）实现 `AgentLLMClient` HTTP 包装；调用后端 `/api/v2/ai/chat/`；stdlib `urllib`（无 `requests` 依赖）；`is_available()` 连通性检查 | ✅ 已实现 |

### 0.2 实际 LLM 调用机制（Phase 4.4+ 后）

- **入口**：`backend/gaf_ai/llm_service.py:call_llm()` 委托给 `_get_llm_router()`（模块级缓存，config 变化时重建）
- **路由**：`backend/gaf_ai/llm_router.py:LLMRouter` 4 级降级 preferred → backup → local → offline
- **配置**：preferred 来自 `LLMConfig` DB 行；backup / local 来自 `LLM_BACKUP_*` / `LLM_LOCAL_*` 环境变量或 Django settings；offline 始终注册
- **用量**：`backend/gaf_ai/token_tracker.py:CostControlService` + `LLMUsageLog` 模型（Phase 4.4 新增 `route` 字段）；`backend/gaf_ai/token_tracker.py:TokenUsageTracker` 提供设计 §6 API
- **Skill 系统**：`backend/skills/builtin/*.yaml` 6 个内置 Skill（Phase 4.3）；`loader.py` dual-schema 验证；`SkillDefinition` DB 模型存储用户自定义 Skill
- **AI 视图**：`backend/gaf_ai/views*.py` 调用 `call_llm()`（自动走 router 降级链）
- **Agent 端**：`worker/src/ai/llm_client.py:AgentLLMClient` 通过 HTTP 调用 `/api/v2/ai/chat/`，不直接访问 LLM 提供商

### 0.3 修复方向（Phase 4.3-4.7 后）

| 项 | 优先级 | 修复方向 | 状态 |
|----|--------|---------|------|
| 文档与代码对齐 | P0 | 文档下文 §2-§8 与新实现对齐 | ✅ Phase 4.8 完成 |
| 创建 6 个内置 Skill YAML | P1 | 在 `backend/skills/builtin/` 下创建 YAML 文件，更新 `load_builtin_skills()` 路径 | ✅ Phase 4.3 完成 |
| 实现 LLMRouter 降级链 | P2 | 在 `call_llm()` 上层包装路由层，支持多模型 fallback | ✅ Phase 4.4 完成 |
| Agent 端 LLM 客户端 | P2 | `worker/src/` 新增 LLM 模块 | ✅ Phase 4.7 完成 |
| ContextCollector | P2 | 实现 §5.1 任务上下文收集器 | ✅ Phase 4.5 完成 |
| TokenUsageTracker | P2 | 实现 §6.1 用量追踪器 + per-Skill 预算 | ✅ Phase 4.6 完成 |
| 流式降级 | P3 | `stream=True` 当前仍走 legacy 直接 requests 路径，未经 router（多级降级下流式语义复杂）——✅ 已实现：llm_service._call_llm_stream_via_router 走 LLMRouter.stream_chat() 4 级降级 | 🟡 推后（非阻塞） |
| `BaseLLMClient` ABC | P3 | 现有 `LLMClient` 是具体类，未抽象；router 通过 duck-typing 接入——✅ 2026-08-08 已提取 backend/gaf_ai/base_client.py::BaseLLMClient(ABC)，router 已依此接口 | 🟡 推后（非阻塞） |

---

## 1. 概述

GAF 集成大语言模型（LLM）能力，通过 Skill 体系为自动化任务提供智能分析、错误诊断、技术问答等高级功能。本设计定义 LLM 调用架构、Skill 定义格式、上下文收集策略、Token 用量控制和降级策略。

> ✅ **Phase 4.3-4.7 实现完成**：§2-§8 描述的类（LLMRouter / ContextCollector / TokenUsageTracker）已全部实现。下文保留设计稿作为架构参考，现实实现见 §0.1-0.3。

---

## 2. LLM 调用架构

### 2.1 整体架构

```
┌──────────────────────────────────────────────────────────┐
│  GAF Server                                              │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Skill       │  │  Context     │  │  LLM         │  │
│  │  Manager     │  │  Collector   │  │  Router      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                  │           │
│         └────────┬────────┘──────────────────┘           │
│                  │                                       │
│         ┌────────▼────────┐                              │
│         │  LLM Client     │                              │
│         │  (统一接口)      │                              │
│         └────────┬────────┘                              │
│                  │                                       │
│    ┌─────────────┼─────────────┐                         │
│    │             │             │                         │
│  ┌─▼──┐  ┌──────▼──┐  ┌──────▼──┐                     │
│  │OpenAI│  │DeepSeek│  │本地模型 │                     │
│  └─────┘  └────────┘  └────────┘                       │
└──────────────────────────────────────────────────────────┘
```

### 2.2 LLM Client 接口

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class LLMMessage:
    """LLM 消息"""
    role: str        # system / user / assistant
    content: str

@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
    latency_ms: float

class BaseLLMClient(ABC):
    """LLM 客户端基类"""

    @abstractmethod
    def chat(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        """发送聊天请求"""

    @abstractmethod
    def stream_chat(self, messages: list[LLMMessage], **kwargs):
        """流式聊天"""

class OpenAIClient(BaseLLMClient):
    """OpenAI 兼容客户端（支持 OpenAI / DeepSeek / 本地模型）"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model

    def chat(self, messages: list[LLMMessage], **kwargs) -> LLMResponse:
        """发送聊天请求"""
        import openai
        client = openai.OpenAI(api_key=self._api_key, base_url=self._base_url)
        response = client.chat.completions.create(
            model=self._model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2000),
        )
        return LLMResponse(
            content=response.choices[0].message.content,
            model=response.model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            cost=self._calculate_cost(response.usage),
            latency_ms=0,
        )
```

### 2.3 LLM Router

```python
class LLMRouter:
    """LLM 路由器，根据 Skill 配置选择模型"""

    def __init__(self):
        self._clients: dict[str, BaseLLMClient] = {}
        self._default_model = "deepseek-chat"

    def register_client(self, name: str, client: BaseLLMClient) -> None:
        """注册 LLM 客户端"""
        self._clients[name] = client

    def get_client(self, model: str | None = None) -> BaseLLMClient:
        """获取 LLM 客户端"""
        model = model or self._default_model
        if model not in self._clients:
            raise LLMClientNotFoundError(f"LLM client not found: {model}")
        return self._clients[model]

    def chat(self, messages: list[LLMMessage], model: str | None = None, **kwargs) -> LLMResponse:
        """发送聊天请求"""
        client = self.get_client(model)
        try:
            return client.chat(messages, **kwargs)
        except Exception as e:
            return self._fallback(messages, e, **kwargs)

    def _fallback(self, messages: list[LLMMessage], error: Exception, **kwargs) -> LLMResponse:
        """降级到备用模型"""
        for name, client in self._clients.items():
            try:
                return client.chat(messages, **kwargs)
            except Exception:
                continue
        raise LLMAllClientsFailedError(f"All LLM clients failed. Original error: {error}")
```

---

## 3. Skill YAML 定义格式

### 3.1 格式规范

```yaml
name: skill_name                    # Skill 名称（唯一标识）
version: "1.0.0"                    # 版本号
description: "Skill 描述"            # 描述
model: deepseek-chat                # 默认使用的模型
is_builtin: false                   # 是否内置 Skill

system_prompt: |                    # 系统提示词
  你是一个专业的自动化脚本分析助手...

user_prompt_template: |             # 用户提示词模板
  请分析以下任务执行日志：
  {{log_content}}
  
  任务名称：{{task_name}}
  执行时间：{{execution_time}}

context:                            # 上下文收集配置
  collect_screenshot: true          # 是否收集截图
  collect_log: true                 # 是否收集日志
  collect_task_config: true         # 是否收集任务配置
  collect_device_info: false        # 是否收集设备信息
  max_log_lines: 200               # 最大日志行数
  max_screenshot_count: 3          # 最大截图数量

parameters:                         # 可配置参数
  temperature:
    type: float
    default: 0.7
    min: 0.0
    max: 1.0
    description: "生成温度"
  max_tokens:
    type: integer
    default: 2000
    min: 100
    max: 8000
    description: "最大生成 Token 数"

output:                             # 输出格式
  format: json                     # json / markdown / text
  schema:                          # JSON Schema（format=json 时）
    type: object
    properties:
      analysis:
        type: string
      suggestions:
        type: array
        items:
          type: string
      confidence:
        type: number

cost_control:                       # 成本控制
  max_tokens_per_call: 4000        # 单次调用最大 Token
  max_calls_per_day: 50           # 每日最大调用次数
  max_cost_per_day: 1.0           # 每日最大成本（USD）
```

---

## 4. 6 个内置 Skill 定义

### 4.1 Skill 清单

| Skill 名称 | 用途 | 默认模型 | 预估 Token |
|------------|------|---------|-----------|
| `error_diagnosis` | 错误诊断 | deepseek-chat | ~3000 |
| `task_optimization` | 任务优化建议 | deepseek-chat | ~2500 |
| `log_analysis` | 日志分析 | deepseek-chat | ~4000 |
| `script_generation` | 脚本生成 | deepseek-chat | ~3000 |
| `qa_assistant` | 技术问答 | deepseek-chat | ~2000 |
| `resource_analysis` | 资源包分析 | deepseek-chat | ~2000 |

### 4.2 error_diagnosis — 错误诊断

```yaml
name: error_diagnosis
version: "1.0.0"
description: "分析任务执行错误，提供诊断和修复建议"
model: deepseek-chat
is_builtin: true

system_prompt: |
  你是一个专业的自动化脚本错误诊断助手。
  你需要分析任务执行过程中的错误信息，包括：
  1. 错误类型和原因
  2. 可能的修复方案
  3. 预防措施
  
  请用中文回答，格式清晰。

user_prompt_template: |
  请诊断以下任务执行错误：
  
  任务名称：{{task_name}}
  错误信息：{{error_message}}
  错误堆栈：{{error_traceback}}
  执行步骤：{{step_name}} (步骤 {{step_index}}/{{total_steps}})
  截图描述：{{screenshot_description}}
  
  任务配置：
  {{task_config}}

context:
  collect_screenshot: true
  collect_log: true
  collect_task_config: true
  collect_device_info: true
  max_log_lines: 100

parameters:
  temperature:
    type: float
    default: 0.5
  max_tokens:
    type: integer
    default: 2000

output:
  format: json
  schema:
    type: object
    properties:
      error_type:
        type: string
      root_cause:
        type: string
      fix_suggestions:
        type: array
        items:
          type: string
      prevention:
        type: array
        items:
          type: string
      confidence:
        type: number

cost_control:
  max_tokens_per_call: 4000
  max_calls_per_day: 30
  max_cost_per_day: 0.5
```

### 4.3 task_optimization — 任务优化建议

```yaml
name: task_optimization
version: "1.0.0"
description: "分析任务执行效率，提供优化建议"
model: deepseek-chat
is_builtin: true

system_prompt: |
  你是一个自动化脚本优化专家。
  分析任务执行数据，提供以下优化建议：
  1. 执行时间优化
  2. 重试策略优化
  3. 步骤合并/精简
  4. 资源使用优化

user_prompt_template: |
  请分析以下任务的执行效率并提供优化建议：
  
  任务名称：{{task_name}}
  总执行时间：{{total_duration}}秒
  步骤执行详情：
  {{step_details}}
  
  重试统计：
  {{retry_stats}}

context:
  collect_screenshot: false
  collect_log: true
  collect_task_config: true
  collect_device_info: false
  max_log_lines: 50

output:
  format: json
  schema:
    type: object
    properties:
      current_efficiency:
        type: string
      optimization_suggestions:
        type: array
        items:
          type: object
          properties:
            category:
              type: string
            suggestion:
              type: string
            expected_improvement:
              type: string
            priority:
              type: string

cost_control:
  max_tokens_per_call: 3000
  max_calls_per_day: 20
  max_cost_per_day: 0.3
```

### 4.4 log_analysis — 日志分析

```yaml
name: log_analysis
version: "1.0.0"
description: "分析任务执行日志，发现潜在问题和模式"
model: deepseek-chat
is_builtin: true

system_prompt: |
  你是一个日志分析专家。分析自动化任务执行日志，识别：
  1. 异常模式和趋势
  2. 潜在风险
  3. 性能瓶颈
  4. 改进建议

user_prompt_template: |
  请分析以下任务执行日志：
  
  日志内容：
  {{log_content}}
  
  任务信息：{{task_name}} (执行ID: {{execution_id}})

context:
  collect_screenshot: false
  collect_log: true
  collect_task_config: false
  collect_device_info: false
  max_log_lines: 200

output:
  format: json
  schema:
    type: object
    properties:
      patterns:
        type: array
        items:
          type: object
      risks:
        type: array
        items:
          type: string
      bottlenecks:
        type: array
        items:
          type: string
      recommendations:
        type: array
        items:
          type: string

cost_control:
  max_tokens_per_call: 5000
  max_calls_per_day: 20
  max_cost_per_day: 0.5
```

### 4.5 script_generation — 脚本生成

```yaml
name: script_generation
version: "1.0.0"
description: "根据自然语言描述生成自动化任务脚本"
model: deepseek-chat
is_builtin: true

system_prompt: |
  你是一个自动化脚本生成助手。根据用户的自然语言描述，
  生成 GAF 兼容的任务定义（JSON 或 YAML 格式）。
  
  可用的 action 类型：
  - screenshot: 截图
  - find_and_click: 查找模板并点击
  - click: 点击指定坐标
  - swipe: 滑动
  - wait: 等待
  - verify: 验证界面状态
  - ocr_check: OCR 文字检查
  - chain: 执行子链
  - launch_app: 启动应用

user_prompt_template: |
  请根据以下描述生成自动化任务脚本：
  
  {{user_description}}
  
  目标应用：{{target_app}}
  执行模式：{{execution_mode}}

context:
  collect_screenshot: false
  collect_log: false
  collect_task_config: false
  collect_device_info: false

output:
  format: json
  schema:
    type: object
    properties:
      task_definition:
        type: object
      explanation:
        type: string
      warnings:
        type: array
        items:
          type: string

cost_control:
  max_tokens_per_call: 4000
  max_calls_per_day: 30
  max_cost_per_day: 0.5
```

> ⚠️ 注：上述 9 类 action 描述的是已废弃 chain action 体系，真实执行单位为 48 个 pipeline 节点；9 类仅存于 skill YAML 提示文本。

### 4.6 qa_assistant — 技术问答

```yaml
name: qa_assistant
version: "1.0.0"
description: "GAF 使用相关的技术问答"
model: deepseek-chat
is_builtin: true

system_prompt: |
  你是 GAF（Game Automation Framework）的技术支持助手。
  回答用户关于 GAF 使用、配置、故障排除的问题。
  请用中文回答，提供具体的操作步骤。

user_prompt_template: |
  用户问题：{{question}}
  
  上下文信息：
  {{context}}

context:
  collect_screenshot: false
  collect_log: false
  collect_task_config: false
  collect_device_info: false

output:
  format: markdown

cost_control:
  max_tokens_per_call: 2000
  max_calls_per_day: 100
  max_cost_per_day: 1.0
```

### 4.7 resource_analysis — 资源包分析

```yaml
name: resource_analysis
version: "1.0.0"
description: "分析资源包结构和内容，提供改进建议"
model: deepseek-chat
is_builtin: true

system_prompt: |
  你是一个自动化资源包分析专家。分析资源包的结构、
  模板图片质量和任务定义，提供改进建议。

user_prompt_template: |
  请分析以下资源包：
  
  资源包名称：{{pack_name}}
  资源包版本：{{pack_version}}
  任务数量：{{task_count}}
  模板数量：{{template_count}}
  监控规则数量：{{monitor_count}}
  
  任务列表：
  {{task_list}}
  
  监控规则列表：
  {{monitor_list}}

context:
  collect_screenshot: false
  collect_log: false
  collect_task_config: true
  collect_device_info: false

output:
  format: json
  schema:
    type: object
    properties:
      quality_score:
        type: number
      issues:
        type: array
        items:
          type: object
      suggestions:
        type: array
        items:
          type: string

cost_control:
  max_tokens_per_call: 3000
  max_calls_per_day: 20
  max_cost_per_day: 0.3
```

---

## 5. 上下文收集策略

### 5.1 上下文收集器

```python
class ContextCollector:
    """上下文收集器，根据 Skill 配置收集相关信息"""

    def __init__(self, config: dict):
        self._config = config

    def collect(self, task_context: dict) -> dict:
        """收集上下文信息"""
        context = {}

        if self._config.get("collect_screenshot", False):
            context["screenshot_description"] = self._collect_screenshot(task_context)
            context["screenshots"] = self._collect_screenshots(
                task_context,
                max_count=self._config.get("max_screenshot_count", 3),
            )

        if self._config.get("collect_log", True):
            context["log_content"] = self._collect_log(
                task_context,
                max_lines=self._config.get("max_log_lines", 200),
            )

        if self._config.get("collect_task_config", False):
            context["task_config"] = self._collect_task_config(task_context)

        if self._config.get("collect_device_info", False):
            context["device_info"] = self._collect_device_info(task_context)

        return context

    def _collect_log(self, context: dict, max_lines: int = 200) -> str:
        """收集日志，限制行数"""
        log = context.get("log", "")
        lines = log.split("\n")
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        return "\n".join(lines)

    def _collect_screenshots(self, context: dict, max_count: int = 3) -> list[str]:
        """收集截图，限制数量，转为 base64"""
        import base64
        screenshots = context.get("screenshots", [])
        result = []
        for ss in screenshots[:max_count]:
            if isinstance(ss, bytes):
                result.append(base64.b64encode(ss).decode())
            elif isinstance(ss, str):
                result.append(ss)
        return result
```

### 5.2 上下文大小控制

| 上下文类型 | 最大大小 | 截断策略 |
|-----------|---------|---------|
| 日志文本 | 10000 字符 | 保留最后 N 行 |
| 截图 | 3 张 | 保留最近 N 张 |
| 任务配置 | 5000 字符 | 保留关键字段 |
| 设备信息 | 1000 字符 | 保留核心信息 |

---

## 6. Token 用量控制

### 6.1 用量统计

```python
class TokenUsageTracker:
    """Token 用量追踪器"""

    def __init__(self):
        self._daily_usage: dict[str, dict] = {}

    def record(self, user_id: int, model: str, input_tokens: int, output_tokens: int, cost: float) -> None:
        """记录一次 LLM 调用的用量"""
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"{user_id}:{today}"

        if key not in self._daily_usage:
            self._daily_usage[key] = {
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cost": 0.0,
                "call_count": 0,
                "models": {},
            }

        usage = self._daily_usage[key]
        usage["total_input_tokens"] += input_tokens
        usage["total_output_tokens"] += output_tokens
        usage["total_cost"] += cost
        usage["call_count"] += 1

        if model not in usage["models"]:
            usage["models"][model] = {"calls": 0, "cost": 0.0}
        usage["models"][model]["calls"] += 1
        usage["models"][model]["cost"] += cost

    def check_budget(self, user_id: int, skill: SkillDefinition) -> bool:
        """检查用户是否还有预算"""
        today = datetime.now().strftime("%Y-%m-%d")
        key = f"{user_id}:{today}"

        usage = self._daily_usage.get(key, {})
        cost_control = skill.cost_control

        if usage.get("call_count", 0) >= cost_control.get("max_calls_per_day", 999):
            return False
        if usage.get("total_cost", 0) >= cost_control.get("max_cost_per_day", 999):
            return False

        return True
```

### 6.2 用量报告

```python
def generate_usage_report(self, user_id: int) -> dict:
    """生成用户用量报告"""
    today = datetime.now().strftime("%Y-%m-%d")
    key = f"{user_id}:{today}"
    usage = self._daily_usage.get(key, {})

    return {
        "date": today,
        "total_calls": usage.get("call_count", 0),
        "total_input_tokens": usage.get("total_input_tokens", 0),
        "total_output_tokens": usage.get("total_output_tokens", 0),
        "total_cost_usd": round(usage.get("total_cost", 0.0), 6),
        "models": usage.get("models", {}),
    }
```

---

## 7. 成本预算管理

### 7.1 预算层级

| 层级 | 限制维度 | 默认值 |
|------|---------|--------|
| Skill 级 | 单次调用 Token 上限 | 4000 |
| Skill 级 | 每日调用次数上限 | 50 |
| Skill 级 | 每日成本上限 | $1.0 |
| 用户级 | 每日总成本上限 | $5.0 |
| 系统级 | 每日总成本上限 | $50.0 |

### 7.2 成本估算

> **价格表单一权威源 (S3 P2, 2026-08-16)**: 代码位于 `backend/gaf_ai/pricing.py`
> (`PRICE_PER_1K_INPUT` / `PRICE_PER_1K_OUTPUT`), `llm_service.estimate_cost`
> 与 `qa_cost_control.CostControlService` 均从该模块读取, 不再各自维护价格表。

```python
# backend/gaf_ai/pricing.py (per 1K tokens, USD)
PRICE_PER_1K_INPUT = {
    "gpt-4o": 0.00250, "gpt-4o-mini": 0.00015,
    "gpt-3.5-turbo": 0.00050, "deepseek-chat": 0.00014,
    "qwen-max": 0.00280, "claude-3.5-sonnet": 0.00300,
    "default": 0.00200,
}
PRICE_PER_1K_OUTPUT = {
    "gpt-4o": 0.01000, "gpt-4o-mini": 0.00060,
    "gpt-3.5-turbo": 0.00150, "deepseek-chat": 0.00028,
    "qwen-max": 0.00840, "claude-3.5-sonnet": 0.01500,
    "default": 0.00800,
}
```

---

## 8. 降级策略

### 8.1 降级链

```
首选模型 → 备用模型 → 本地模型 → 离线模式
```

### 8.2 降级规则

| 触发条件 | 降级行为 |
|----------|---------|
| 首选模型 API 超时 (>30s) | 切换到备用模型 |
| 首选模型 API 错误 (5xx) | 切换到备用模型 |
| 首选模型配额用尽 | 切换到备用模型 |
| 所有云端模型不可用 | 使用本地模型 (Ollama) |
| 本地模型也不可用 | 返回缓存结果或默认回复 |

### 8.3 降级配置

```python
FALLBACK_CHAIN = {
    "error_diagnosis": ["deepseek-chat", "gpt-4o-mini", "qwen-plus", "local-llama3"],
    "task_optimization": ["deepseek-chat", "gpt-4o-mini", "local-llama3"],
    "log_analysis": ["deepseek-chat", "qwen-plus", "local-llama3"],
    "script_generation": ["deepseek-chat", "gpt-4o-mini", "local-llama3"],
    "qa_assistant": ["deepseek-chat", "gpt-4o-mini", "qwen-plus"],
    "resource_analysis": ["deepseek-chat", "gpt-4o-mini"],
}
```

### 8.4 离线模式

当所有 LLM 服务不可用时：

1. 返回预定义的默认回复模板
2. 使用基于规则的简单分析（正则匹配错误模式）
3. 从历史分析结果中检索相似案例
4. 在 UI 中显示"LLM 服务不可用"提示
