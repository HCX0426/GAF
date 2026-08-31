"""LangGraph ReAct agent — builds the log analysis agent graph.

Phase 2 (spec 2026-08-31-ai-tab-agent-learning-spec): the default graph is
now the hand-written ``StateGraph`` in :mod:`gaf_ai.agent.langgraph_graph`.
The old ``create_agent`` high-level wrapper is retained behind a feature
setting (`AGENT_USE_CREATE_AGENT=1`) so the two implementations can be
compared for learning/regression debugging.
"""
import logging

from langchain.agents import create_agent

from gaf_ai.feature_flags import is_langgraph_agent_enabled

from .llm_adapter import build_agent_llm
from .skill_tool_adapter import collect_skill_tools
from .tool_registry import (
    LANGCHAIN_TOOL,
    TOOL_REGISTRY,
    ToolRegistryEntry,
)
from .tools import (
    get_execution_detail,
    get_execution_steps,
    get_screenshot_base64,
    get_structured_log,
    get_task_config,
    search_similar_errors,
)

logger = logging.getLogger(__name__)

# ── Phase 2: centralized tool registration (spec §Phase 2) ──────────
# Core GAF tools declared once in TOOL_REGISTRY. Skill tools are injected
# per-user at build time (they are not static), so they are appended outside
# the registry (see build_log_analysis_agent).


def _register_core_tools() -> None:
    """Register the core GAF analysis tools into the shared registry."""
    registry_items = [
        (get_execution_detail, 'get_execution_detail', False),
        (get_execution_steps, 'get_execution_steps', False),
        (search_similar_errors, 'search_similar_errors', False),
        (get_task_config, 'get_task_config', False),
        (get_structured_log, 'get_structured_log', False),
        (get_screenshot_base64, 'get_screenshot_base64', True),
    ]
    for func, name, vision in registry_items:
        if name in TOOL_REGISTRY.entries:
            continue
        TOOL_REGISTRY.register(ToolRegistryEntry(
            name=name,
            type=LANGCHAIN_TOOL,
            obj=func,
            description=func.description or '',
            vision_required=vision,
            group='gaf-analysis',
        ))


# Register once at import time.
_register_core_tools()

# System prompt for the ReAct agent
SYSTEM_PROMPT = """You are a game automation log analysis agent. Your job is to analyze execution records and diagnose failures.

You have access to tools that let you query execution data on demand. Use them to gather information before giving your final analysis.

Workflow:
1. First, get the execution detail to understand the overall context.
2. Then, get the execution steps to see which step(s) failed.
3. PREFER get_structured_log over get_execution_steps when available — it
   returns confidence/threshold/roi/error_code/screenshot_path which are
   absent from the SQL rows. If it errors (e.g. JSONL file unreachable
   because agent and backend are on different hosts), fall back to
   get_execution_steps silently.
4. For recognition-node failures (template_match/ocr/feature_match/
   color_detect), call get_screenshot_base64 with raw=True to inspect the
   ORIGINAL screenshot (no annotations). For action-node failures
   (click/swipe/wait/key_press), use raw=False to see the annotated PNG.
   When raw=True returns "no raw_screenshot_path", retry with raw=False.
5. If there are errors, search for similar errors in the past to find patterns.
6. If needed, get the task config to understand the pipeline.
7. Once you have enough information, provide a comprehensive analysis.

Your final answer MUST be a JSON object with this exact structure:
{
  "summary": "A concise summary of what happened (in Chinese)",
  "suggestions": ["Actionable suggestion 1 (in Chinese)", "Actionable suggestion 2 (in Chinese)"]
}

Rules:
- Respond in Chinese for summary and suggestions.
- Be specific: reference actual step names, error messages, confidence/threshold
  values, and error_code when present.
- If no similar errors found, note that it might be a new issue.
- Keep suggestions actionable: "update template X (confidence 0.42 < threshold 0.80)",
  "check device Y", "verify click coordinates (x=960, y=540)", etc.
- error_code values you may see: SCREEN_UNCHANGED (click did not navigate),
  TIMEOUT (wait/template not found), LOW_CONFIDENCE (template match below
  threshold), OCR_NOT_FOUND, etc. Reference them explicitly when present.
"""

# All tools available to the agent (used as fallback when model name unknown)
AGENT_TOOLS = [
    get_execution_detail,
    get_execution_steps,
    search_similar_errors,
    get_task_config,
    get_screenshot_base64,
    get_structured_log,
]


def _resolve_preferred_model_name() -> str:
    """读取 preferred level 的 model 名 (spec §7.2.2 — 任务 2.4).

    用于 ``get_tools_for_model(model)`` 决定是否暴露视觉工具. 读取顺序:
    1. LLMConfig DB 行的 default_model (preferred level)
    2. LLM_BACKUP_MODEL env / settings (backup level)
    3. LLM_LOCAL_MODEL env / settings (local level)

    Returns:
        模型名字符串, 未配置返回空字符串.
    """
    try:
        from gaf_ai.llm_service import _get_llm_config, _settings_get

        config = _get_llm_config()
        if config and config.default_model:
            return config.default_model
        backup_model = _settings_get('LLM_BACKUP_MODEL')
        if backup_model:
            return backup_model
        local_model = _settings_get('LLM_LOCAL_MODEL')
        if local_model:
            return local_model
    except Exception as exc:
        logger.warning(
            "Failed to resolve preferred model name for vision routing: %s", exc,
        )
    return ''


def build_log_analysis_agent(user=None):
    """Build the ReAct agent for log analysis.

    Args:
        user: User instance used to filter per-user CustomSkill tools.
            When ``None``, only global SkillDefinition tools are
            injected (no CustomSkill tools). The user is also the
            intended audience for budget tracking inside
            ``execute_skill`` (currently the adapter does not thread
            user into execute_skill — that is by design: skills invoked
            via the agent skip per-user budget check, since the agent
            itself is rate-limited by the FeatureFlag gate and Celery
            concurrency).

    Returns a LangGraph agent that can be invoked with:
        agent.invoke({"messages": [{"role": "user", "content": "..."}]})

    The agent will autonomously call tools to gather data, then produce
    a final analysis with summary and suggestions.

    Tool set (spec §7.2.2 — 任务 2.4 按模型能力路由):
      - 视觉模型 (gpt-4o / claude-3-5-sonnet 等): 6 个固定工具, 含
        get_screenshot_base64 让 LLM 看原图.
      - 纯文本模型 (deepseek-chat / qwen2.5 等): 5 个固定工具, 不含
        get_screenshot_base64, 让 LLM 只依赖 get_structured_log 返回的
        OCR 文本/置信度等结构化字段做诊断.
      - 模型名无法解析时: 保守默认 6 个工具 (与旧行为一致).
      - SkillDefinition tools (is_enabled=True, global)
      - CustomSkill tools (is_active=True, created_by=user) when user is
        not None

    Raises RuntimeError when the ``langgraph_agent_enabled`` feature flag
    is disabled — callers should surface this as a clear user-facing
    error rather than silently degrading.
    """
    if not is_langgraph_agent_enabled():
        raise RuntimeError(
            "LangGraph agent is disabled by feature flag 'langgraph_agent_enabled'"
        )

    # spec §7.2.2 — 任务 2.4: 按模型能力决定是否暴露视觉工具.
    # Phase 2: resolve from the centralized TOOL_REGISTRY. The screenshot
    # tool is tagged ``vision_required=True``; whether it's included depends
    # on the resolved model's vision capability (mirrors the old
    # get_tools_for_model logic via is_vision_capable).
    model_name = _resolve_preferred_model_name()
    if model_name:
        from gaf_ai.llm_router import is_vision_capable

        vision_available = is_vision_capable(model_name)
        fixed_tools = TOOL_REGISTRY.resolve_tools(
            vision_available=vision_available,
        )
        logger.info(
            "Agent tools from registry for model %r: %d tools (vision=%s)",
            model_name, len(fixed_tools), vision_available,
        )
    else:
        # 模型名无法解析 (例如只用 LLM_LOCAL_BASE_URL 但没设 LLM_LOCAL_MODEL):
        # 保守暴露全部 6 个工具 (含视觉), 与旧行为一致, 避免回归.
        fixed_tools = TOOL_REGISTRY.resolve_tools(vision_available=True)
        logger.info(
            "Agent tools: model unknown, using all %d tools", len(fixed_tools),
        )

    skill_tools = collect_skill_tools(user=user)
    all_tools = list(fixed_tools) + skill_tools

    llm = build_agent_llm()

    if _use_create_agent():
        logger.info("Agent graph: using create_agent (AGENT_USE_CREATE_AGENT=1)")
        return create_agent(
            llm,
            all_tools,
            system_prompt=SYSTEM_PROMPT,
        )

    # Phase 2 default: hand-written StateGraph (teachable, auditable).
    logger.info(
        "Agent graph: using hand-written StateGraph (%d tools)",
        len(all_tools),
    )
    from .langgraph_graph import build_react_graph

    return build_react_graph(
        llm,
        all_tools,
        system_prompt=SYSTEM_PROMPT,
    )


def _use_create_agent() -> bool:
    """Return True when the legacy ``create_agent`` path is explicitly requested.

    Reads the ``AGENT_USE_CREATE_AGENT`` env / Django setting. Defaults to
    False (Phase 2: hand-written graph). Kept only for A/B comparison while
    the handwritten graph is validated in production.
    """
    try:
        from gaf_ai.llm_service import _settings_get

        val = _settings_get('AGENT_USE_CREATE_AGENT')
        return str(val).strip().lower() in ('1', 'true', 'yes')
    except Exception as exc:
        logger.warning('Failed to read AGENT_USE_CREATE_AGENT: %s', exc)
        return False
