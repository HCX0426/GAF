"""
LLM 服务模块 — 统一 LLM 调用接口（兼容 OpenAI API）

Phase 4.4: ``call_llm()`` now delegates to a module-level
``LLMRouter`` (see ``ai.llm_router``) implementing the 4-level
fallback chain per ``llm-integration-design.md`` §8:
    preferred → backup → local → offline

Configuration sources:
  * preferred: ``LLMConfig`` DB row (provider / api_key / api_base /
    default_model) — the existing single-provider config.
  * backup:    ``LLM_BACKUP_API_KEY`` / ``LLM_BACKUP_PROVIDER`` /
    ``LLM_BACKUP_BASE_URL`` / ``LLM_BACKUP_MODEL`` Django settings
    (or env vars of the same name).
  * local:     ``LLM_LOCAL_API_BASE`` (typically
    ``http://localhost:11434/v1`` for Ollama) + optional
    ``LLM_LOCAL_API_KEY`` / ``LLM_LOCAL_MODEL``. Local providers
    usually need no API key.
  * offline:   ``OfflineClient`` always registered, always succeeds.

The router's response carries a ``route`` key (``"preferred"`` /
``"backup"`` / ``"local"`` / ``"offline"``) which ``call_llm()``
propagates in its return dict so callers can record it in
``LLMUsageLog.route``.
"""
import logging
import os
from collections.abc import Generator
from typing import Any

from config.app_info import LLM_REQUEST_TIMEOUT
from gaf_ai.pricing import PRICE_PER_1K_INPUT, PRICE_PER_1K_OUTPUT

logger = logging.getLogger(__name__)


# Module-level router cache (rebuilt on first call or when config
# changes). Cached so that repeated ``call_llm()`` invocations don't
# re-read the DB / env on every request.
_router_cache: Any | None = None
_router_cache_key: str | None = None


def _get_llm_config():
    """从数据库获取激活的 LLMConfig，失败返回 None。

    Multi-provider (TD-423 / AI-tab learning spec Phase 1): 多行并存时
    必须取 ``is_active=True`` 的那条，而非 ``objects.first()``（后者会
    选中最新创建但可能未激活的行）。
    """
    try:
        from settings.models import LLMConfig
        config = LLMConfig.objects.filter(is_active=True).order_by('-updated_at').first()
        if config:
            return config
    except Exception as e:
        logger.warning('Failed to load LLMConfig from DB: %s', e)
    return None


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """估算 LLM 调用成本.

    Price resolution order (single source of truth keeps one price per model):
    1. Custom per-provider price from the active ``LLMConfig``
       (``input_price`` / ``output_price``, USD per 1K tokens) — overrides.
    2. Static table ``gaf_ai.pricing`` by model name, else ``default`` row.
    """
    try:
        cfg = _get_llm_config()
        if cfg is not None and cfg.input_price is not None and cfg.output_price is not None:
            cost = (input_tokens / 1000) * float(cfg.input_price) + (
                output_tokens / 1000
            ) * float(cfg.output_price)
            return round(cost, 6)
    except Exception as exc:  # noqa: BLE001
        logger.warning('estimate_cost custom-price lookup failed: %s', exc)

    input_price = PRICE_PER_1K_INPUT.get(model, PRICE_PER_1K_INPUT["default"])
    output_price = PRICE_PER_1K_OUTPUT.get(model, PRICE_PER_1K_OUTPUT["default"])
    cost = (input_tokens / 1000) * float(input_price) + (
        output_tokens / 1000
    ) * float(output_price)
    return round(cost, 6)

SYSTEM_PROMPT_PIPELINE = """你是一个游戏自动化 Pipeline 生成器。根据用户的自然语言描述，生成结构化的 Pipeline JSON。

可用节点类型及配置：
- click: {"x": int, "y": int, "button": "left|right|middle"}
- swipe: {"x1": int, "y1": int, "x2": int, "y2": int, "duration": int}
- key_press: {"key": str}
- text_input: {"text": str}
- wait: {"wait_type": "fixed|stability", "timeout": int}
- template_match: {"template_id": str, "threshold": float}
- ocr: {"engine": "rapid|paddle", "language": "ch|en", "expected_text": str}
- branch: {"condition": str}
- loop: {"count": int}
- goto: {"target": str}

输出格式（严格JSON）：
{
  "nodes": [
    {"id": "node_1", "node_type": "click", "label": "描述", "config": {...}}
  ],
  "edges": [
    {"id": "e_1", "source": "node_1", "target": "node_2"}
  ]
}

规则：
1. 每次点击操作后自动插入 wait 节点（等待画面稳定）
2. 登录流程用 template_match 识别按钮
3. 循环操作使用 loop 节点包裹
4. 坐标默认为 1920x1080 分辨率
5. 只输出 JSON，不要解释"""

SYSTEM_PROMPT_OPTIMIZE = """你是一个 Pipeline 优化专家。分析执行历史，给出优化建议。

分析维度：
1. 合并相邻等待步骤（间隔<500ms）
2. 降低过高匹配阈值（频繁失败的 template_match）
3. 增加重试节点（某步骤失败率>30%）
4. 优化等待时间（实际等待 vs 必要等待）

输出格式（严格JSON）：
{
  "suggestions": [
    {
      "type": "merge_wait|lower_threshold|add_retry|optimize_timeout",
      "description": "优化说明",
      "node_ids": ["affected_node_ids"],
      "optimized_nodes": [...],
      "optimized_edges": [...]
    }
  ]
}"""


def _settings_get(name: str, default: str | None = None) -> str | None:
    """Read a setting from Django settings first, then env vars.

    Falls back to ``os.environ`` so the module remains usable in
    non-Django contexts (e.g. smoke tests).
    """
    try:
        from django.conf import settings as django_settings
        val = getattr(django_settings, name, None)
        if val:
            return val
    except Exception:
        logger.warning("llm_service: _settings_get failed to read Django setting (name=%r)", name, exc_info=True)
    return os.environ.get(name, default)


def _build_router_cache_key() -> str:
    """Build a cache key from current config so the router is rebuilt
    when config changes.

    The key is a concatenation of all config sources' identifying
    fields. If any field changes, the key changes, and
    ``_get_llm_router()`` rebuilds the router.
    """
    db_config = _get_llm_config()
    parts = []
    if db_config:
        parts.append(f"db:{db_config.provider}:{db_config.api_base}:{db_config.default_model}")
    else:
        parts.append("db:none")

    parts.append(f"backup:{_settings_get('LLM_BACKUP_PROVIDER', '')}:{_settings_get('LLM_BACKUP_BASE_URL', '')}:{_settings_get('LLM_BACKUP_MODEL', '')}")
    parts.append(f"local:{_settings_get('LLM_LOCAL_BASE_URL', '')}:{_settings_get('LLM_LOCAL_MODEL', '')}")
    return "|".join(parts)


def _get_llm_router():
    """Build (and cache) the module-level ``LLMRouter`` instance.

    The router is rebuilt only when the config cache key changes
    (e.g. DB config updated, env var changed). This avoids
    re-reading the DB on every ``call_llm()`` call while still
    picking up config changes.

    Returns:
        ``LLMRouter`` instance with 4-level fallback registered.
    """
    global _router_cache, _router_cache_key

    cache_key = _build_router_cache_key()
    if _router_cache is not None and _router_cache_key == cache_key:
        return _router_cache

    # Lazy imports so the module loads even if Django settings
    # aren't configured yet (e.g. during migration runs).
    from gaf_ai.llm_router import LLMRouter, OfflineClient
    from gaf_ai.qa_llm_client import OpenAIClient

    router = LLMRouter()

    # ── Level 1: preferred (from LLMConfig DB row) ──
    db_config = _get_llm_config()
    if db_config and db_config.api_key:
        try:
            preferred = OpenAIClient(
                api_key=db_config.get_api_key(),
                provider=db_config.provider,
                base_url=db_config.api_base or None,
                model=db_config.default_model,
                timeout=LLM_REQUEST_TIMEOUT,
            )
            router.register("preferred", preferred)
            logger.info(
                "LLMRouter registered preferred: %s @ %s (model=%s)",
                db_config.provider, db_config.api_base, db_config.default_model,
            )
        except Exception as exc:
            logger.warning("Failed to register preferred LLM client: %s", exc)

    # ── Level 2: backup (from LLM_BACKUP_* settings/env) ──
    backup_key = _settings_get('LLM_BACKUP_API_KEY')
    if backup_key:
        try:
            backup = OpenAIClient(
                api_key=backup_key,
                provider=_settings_get('LLM_BACKUP_PROVIDER', 'openai'),
                base_url=_settings_get('LLM_BACKUP_BASE_URL'),
                model=_settings_get('LLM_BACKUP_MODEL'),
                timeout=LLM_REQUEST_TIMEOUT,
            )
            router.register("backup", backup)
            logger.info(
                "LLMRouter registered backup: %s @ %s",
                _settings_get('LLM_BACKUP_PROVIDER', 'openai'),
                _settings_get('LLM_BACKUP_BASE_URL', ''),
            )
        except Exception as exc:
            logger.warning("Failed to register backup LLM client: %s", exc)

    # ── Level 3: local (from LLM_LOCAL_* settings/env) ──
    # Local providers (Ollama, vLLM) often need no API key — use a
    # placeholder if none is set so OpenAIClient can still construct.
    local_base = _settings_get('LLM_LOCAL_BASE_URL')
    if local_base:
        try:
            local = OpenAIClient(
                api_key=_settings_get('LLM_LOCAL_API_KEY', 'local'),
                provider=_settings_get('LLM_LOCAL_PROVIDER', 'custom'),
                base_url=local_base,
                model=_settings_get('LLM_LOCAL_MODEL', 'llama3'),
                timeout=LLM_REQUEST_TIMEOUT,
            )
            router.register("local", local)
            logger.info(
                "LLMRouter registered local: %s (model=%s)",
                local_base, _settings_get('LLM_LOCAL_MODEL', 'llama3'),
            )
        except Exception as exc:
            logger.warning("Failed to register local LLM client: %s", exc)

    # ── Level 4: offline (always registered, always succeeds) ──
    router.register("offline", OfflineClient())
    logger.info("LLMRouter registered offline (always-succeeds fallback)")

    _router_cache = router
    _router_cache_key = cache_key
    return router


def reset_router_cache() -> None:
    """Reset the module-level router cache.

    Primarily for tests — call after changing config to force the
    next ``call_llm()`` to rebuild the router.
    """
    global _router_cache, _router_cache_key
    _router_cache = None
    _router_cache_key = None


def get_router_info() -> dict[str, Any]:
    """Return diagnostic info about the current router state.

    Used by monitoring / admin endpoints to expose which fallback
    levels are configured and which level last succeeded.
    """
    router = _get_llm_router()
    return {
        "levels_configured": list(router._clients.keys()) if hasattr(router, '_clients') else [],
        "last_successful_level": router.last_successful_level,
        "cache_key": _router_cache_key,
    }


def call_llm(
    messages: list,
    model: str = 'gpt-4o-mini',
    api_key: str | None = None,
    api_base: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    stream: bool = False,
) -> dict:
    """
    调用 OpenAI 兼容 API（通过 LLMRouter 4 级降级链）。

    Phase 4.4: 委托给 ``LLMRouter.chat()``，按 preferred → backup →
    local → offline 顺序尝试。成功响应包含 ``route`` 字段标识命中
    的降级级别。

    优先级（仅影响 preferred 客户端的 model/temperature/max_tokens
    覆盖）: 函数参数 > DB 配置 > 默认值。

    Args:
        messages: OpenAI 格式消息列表
        model: 模型名（覆盖 preferred 客户端默认模型）
        api_key: 保留参数（Phase 4.4 后由 router 管理，此参数
            仅用于向后兼容，不再直接使用）
        api_base: 保留参数（同上）
        temperature: 采样温度
        max_tokens: 最大生成 Token 数
        stream: 是否流式（流式通过 ``LLMRouter.stream_chat()`` 走
            4 级降级链，与非流式同路径）

    Returns:
        dict: ``{"content", "input_tokens", "output_tokens", "model",
        "cost", "route"}``。如果所有级别失败（不应发生，因
        OfflineClient 兜底），返回 ``{"error": ...}``。
        如果 ``stream=True``，返回 generator。
    """
    # ── Streaming path: delegate to LLMRouter.stream_chat() ──
    # Streaming now goes through the router so it benefits from the
    # 4-level fallback chain. If a live client fails before yielding
    # the first chunk, the router tries the next level. Once chunks
    # start flowing, we commit to that client (can't "un-yield").
    if stream:
        return _call_llm_stream_via_router(messages, model, temperature, max_tokens)

    # ── Non-streaming path: delegate to LLMRouter ──
    from gaf_ai.llm_router import LLMAllClientsFailedError

    try:
        router = _get_llm_router()

        # Build kwargs for the router — pass model/temperature/max_tokens
        # as overrides. The router's chat() forwards these to the
        # underlying OpenAIClient.chat().
        router_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # Only override model if explicitly passed (not the default)
        # so the preferred client's configured default_model is used
        # when the caller didn't specify one.
        if model != 'gpt-4o-mini':
            router_kwargs["model"] = model

        response = router.chat(messages, **router_kwargs)

        # Flatten the router's nested response to match the legacy
        # call_llm() contract (flat input_tokens / output_tokens /
        # cost / + route).
        usage = response.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        model_used = response.get("model", model)
        route = response.get("route", "")

        # OfflineClient returns content but no real usage; cost is 0
        # for offline. For real clients, estimate cost from tokens.
        cost = 0.0 if route == "offline" else estimate_cost(model_used, input_tokens, output_tokens)

        return {
            "content": response.get("content", ""),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model": model_used,
            "cost": cost,
            "route": route,
        }

    except LLMAllClientsFailedError as exc:
        # Should not happen — OfflineClient always succeeds. But
        # guard defensively and return an error dict matching the
        # legacy contract.
        logger.error("LLMRouter all clients failed (offline should have caught this): %s", exc)
        return {
            "content": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "model": model,
            "cost": 0,
            "route": "failed",
            "error": str(exc),
        }
    except Exception as exc:
        logger.error("call_llm via router failed: %s", exc)
        return {
            "content": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "model": model,
            "cost": 0,
            "route": "failed",
            "error": str(exc),
        }


def _call_llm_stream_via_router(
    messages: list,
    model: str,
    temperature: float,
    max_tokens: int,
) -> Generator:
    """Streaming path via LLMRouter — enjoys 4-level fallback.

    Delegates to ``LLMRouter.stream_chat()`` which tries each level
    in order (preferred → backup → local → offline). If a live client
    fails before yielding the first chunk, the router falls back to
    the next level. Once chunks start flowing, we commit to that
    client.

    The offline level yields a single placeholder chunk so callers
    always get at least one chunk.
    """
    router = _get_llm_router()
    router_kwargs: dict[str, Any] = {
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if model != 'gpt-4o-mini':
        router_kwargs["model"] = model
    return router.stream_chat(messages, **router_kwargs)
