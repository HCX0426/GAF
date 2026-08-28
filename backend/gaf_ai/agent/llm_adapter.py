"""LLM adapter — bridges GAF's 4-level fallback config to LangChain ChatOpenAI."""
import logging

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


def build_agent_llm() -> ChatOpenAI:
    """Build LangChain LLM with multi-level fallback, mirroring GAF's LLMRouter.

    Reads the same configuration sources as LLMRouter:
      - preferred: LLMConfig DB row (provider / api_key / api_base / default_model)
      - backup:    LLM_BACKUP_* env / Django settings
      - local:     LLM_LOCAL_* env / Django settings (typically Ollama)

    Returns a ChatOpenAI (or a fallback-wrapped ChatOpenAI) that LangGraph
    can use directly. If no LLM is configured, raises RuntimeError.

    Note: The 'offline' level from LLMRouter is intentionally omitted —
    Agent analysis requires a real LLM; returning a placeholder is worse
    than failing fast.
    """
    from gaf_ai.llm_service import _get_llm_config, _settings_get

    clients: list[ChatOpenAI] = []

    # Level 1: preferred (DB config)
    config = _get_llm_config()
    if config and config.api_key:
        clients.append(ChatOpenAI(
            model=config.default_model or 'gpt-4o-mini',
            api_key=config.api_key,
            base_url=config.api_base or None,
            temperature=0.3,
            max_tokens=1024,
        ))
        logger.debug("Agent LLM: preferred level configured (model=%s)", config.default_model)

    # Level 2: backup (ENV / settings)
    backup_key = _settings_get('LLM_BACKUP_API_KEY')
    if backup_key:
        clients.append(ChatOpenAI(
            model=_settings_get('LLM_BACKUP_MODEL') or 'gpt-4o-mini',
            api_key=backup_key,
            base_url=_settings_get('LLM_BACKUP_BASE_URL') or None,
            temperature=0.3,
            max_tokens=1024,
        ))
        logger.debug("Agent LLM: backup level configured")

    # Level 3: local (Ollama)
    # NOTE: env var name is LLM_LOCAL_BASE_URL (not LLM_LOCAL_API_BASE) —
    # must match backend/config/settings/base.py L223.
    local_base = _settings_get('LLM_LOCAL_BASE_URL')
    if local_base:
        clients.append(ChatOpenAI(
            model=_settings_get('LLM_LOCAL_MODEL') or 'qwen2.5',
            api_key=_settings_get('LLM_LOCAL_API_KEY') or 'not-needed',
            base_url=local_base,
            temperature=0.3,
            max_tokens=1024,
        ))
        logger.debug("Agent LLM: local level configured (base=%s)", local_base)

    if not clients:
        raise RuntimeError(
            "No LLM configured for Agent. Please configure LLMConfig in DB "
            "or set LLM_BACKUP_API_KEY / LLM_LOCAL_BASE_URL in environment."
        )

    # Single client — return directly
    if len(clients) == 1:
        return clients[0]

    # Multiple clients — chain with .with_fallbacks()
    logger.info(
        "Agent LLM: %d levels configured, using .with_fallbacks()",
        len(clients),
    )
    return clients[0].with_fallbacks(clients[1:])
