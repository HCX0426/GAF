"""LLM Router — 4-level fallback chain (preferred → backup → local → offline).

``LLMRouter`` implements the fallback chain per
``llm-integration-design.md`` §2.3 + §8. The router holds an ordered
chain of ``BaseLLMClient`` instances and tries each in turn until one
succeeds. If all live clients fail, the offline level returns a
default response (no network call) so callers always get a usable
dict back instead of an exception.

Chain levels
------------
1. **preferred** — Primary cloud model (e.g. ``deepseek-chat``).
   Configured via ``LLMConfig`` in the DB or env vars.
2. **backup** — Backup cloud model (e.g. ``gpt-4o-mini``). Tried when
   the preferred level times out or returns 5xx.
3. **local** — Local model (e.g. Ollama ``llama3`` at
   ``http://localhost:11434/v1``). Tried when both cloud levels fail.
4. **offline** — Always-succeeds fallback that returns a default
   response dict with ``"offline": True``. Tried when all live
   clients fail. Implemented by ``OfflineClient``.

Integration with ``call_llm()``
-------------------------------
``call_llm()`` in ``backend/gaf_ai/llm_service.py`` delegates to
``LLMRouter``. The function signature and return dict shape are
preserved so existing callers continue to work.

Usage
-----
::

    from gaf_ai.llm_router import LLMRouter, OfflineClient
    from gaf_ai.qa_llm_client import OpenAIClient

    router = LLMRouter()
    router.register("preferred", OpenAIClient(api_key="sk-...", provider="deepseek"))
    router.register("backup", OpenAIClient(api_key="sk-...", provider="openai", model="gpt-4o-mini"))
    router.register("offline", OfflineClient())

    response = router.chat(messages=[{"role": "user", "content": "hi"}])
    # response["content"] is the LLM reply, or "" if offline.
    # response["route"] is "preferred" / "backup" / "local" / "offline".
"""

from __future__ import annotations

import logging
from typing import Any

from gaf_ai.base_client import (
    BaseLLMClient,
    LLMAPIError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


# ── Custom exceptions ──────────────────────────────────────────
class LLMRouterError(Exception):
    """LLM router error (no clients registered, all clients failed, etc)."""


class LLMAllClientsFailedError(LLMRouterError):
    """All live LLM clients failed and no offline fallback was registered."""


# ── Offline fallback client ────────────────────────────────────
class OfflineClient(BaseLLMClient):
    """Always-succeeds offline client — returns a default response.

    Used as the last level of the fallback chain. The response dict
    mirrors the shape returned by ``OpenAIClient.chat()`` so callers
    can treat it uniformly. The ``"offline": True`` flag lets callers
    distinguish real LLM output from the offline placeholder.
    """

    DEFAULT_CONTENT = (
        "[offline] LLM 服务暂不可用，已降级到离线模式。"
        "请检查 LLM 配置或稍后重试。"
    )

    def __init__(self, default_content: str = DEFAULT_CONTENT):
        self._default_content = default_content

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> dict[str, Any]:
        return {
            "content": self._default_content,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
            "model": "offline",
            "offline": True,
        }

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ):
        """Yield the default content as a single chunk, then stop."""
        yield self._default_content


# ── Router ─────────────────────────────────────────────────────
class LLMRouter:
    """4-level LLM fallback router.

    Args:
        levels: Ordered iterable of level names. Default
            ``("preferred", "backup", "local", "offline")`` per
            design §8.1. Callers can pass a custom order (e.g. to
            skip the local level).
    """

    DEFAULT_LEVELS = ("preferred", "backup", "local", "offline")

    def __init__(self, levels: tuple | None = None):
        self._levels: tuple = tuple(levels) if levels is not None else self.DEFAULT_LEVELS
        self._clients: dict[str, BaseLLMClient] = {}
        # Track which level last succeeded (for monitoring / debugging).
        self._last_successful_level: str | None = None

    # ── Public properties ──────────────────────────────────────
    @property
    def levels(self) -> tuple:
        """Configured level order (e.g. ('preferred', 'backup', 'local', 'offline'))."""
        return self._levels

    @property
    def registered_levels(self) -> list[str]:
        """Levels that currently have a client registered (in chain order)."""
        return [lvl for lvl in self._levels if lvl in self._clients]

    @property
    def last_successful_level(self) -> str | None:
        """Level that last returned a successful response (None if no call yet)."""
        return self._last_successful_level

    # ── Public API ─────────────────────────────────────────────
    def register(self, level: str, client: BaseLLMClient) -> None:
        """Register a client for a chain level.

        Args:
            level: Level name (must be in ``self.levels``).
            client: ``BaseLLMClient`` instance (e.g. ``OpenAIClient``
                or ``OfflineClient``).

        Raises:
            LLMRouterError: If ``level`` is not in the configured chain.
        """
        if level not in self._levels:
            raise LLMRouterError(
                f"unknown level {level!r}; configured levels: {self._levels}",
            )
        self._clients[level] = client

    def get_client(self, level: str) -> BaseLLMClient | None:
        """Return the client registered for ``level``, or None if not registered."""
        return self._clients.get(level)

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> dict[str, Any]:
        """Send a chat request, falling through the chain on failure.

        Tries each registered level in chain order. Returns the first
        successful response dict (with an added ``"route"`` key
        indicating which level succeeded). If all live clients fail
        and no offline client is registered, raises
        ``LLMAllClientsFailedError``.

        Args:
            messages: List of ``{"role": str, "content": str}`` dicts.
            model: Override the client's default model (passed to each
                client's ``chat()``).
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            **kwargs: Additional kwargs forwarded to each client.

        Returns:
            Response dict from the successful client, with an added
            ``"route"`` key (level name). If the offline level handled
            the call, ``response["offline"]`` is True.

        Raises:
            LLMAllClientsFailedError: If no clients are registered or
                all live clients failed and no offline fallback exists.
        """
        if not self._clients:
            raise LLMAllClientsFailedError(
                "no LLM clients registered — call register() first",
            )

        errors: list[str] = []
        for level in self._levels:
            client = self._clients.get(level)
            if client is None:
                # Level not registered — skip (caller may have only
                # configured preferred + offline, for example).
                continue

            try:
                response = client.chat(
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                # Tag the response with the route level for monitoring.
                response["route"] = level
                self._last_successful_level = level
                if level != "offline":
                    logger.info("LLMRouter: request handled by %s level", level)
                else:
                    logger.warning(
                        "LLMRouter: all live clients failed, fell back to offline",
                    )
                return response
            except (LLMAPIError, LLMTimeoutError) as exc:
                errors.append(f"{level}: {type(exc).__name__}: {exc}")
                logger.warning(
                    "LLMRouter: %s level failed: %s; trying next level",
                    level, exc,
                )
                continue
            except Exception as exc:  # noqa: BLE001 — defensive: unknown client bugs
                errors.append(f"{level}: {type(exc).__name__}: {exc}")
                logger.exception(
                    "LLMRouter: %s level raised unexpected error: %s",
                    level, exc,
                )
                continue

        # All registered levels failed (including offline, which shouldn't
        # happen since OfflineClient never raises — but be defensive).
        raise LLMAllClientsFailedError(
            f"all LLM clients failed. Errors: {' | '.join(errors)}",
        )

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ):
        """Stream a chat request, falling through the chain on failure.

        Unlike ``chat()``, streaming fallback is best-effort: once a
        client starts yielding chunks, we commit to that client and
        don't fall back mid-stream. If the first live client fails
        immediately (before yielding any chunk), we try the next level.

        Yields:
            Content chunks (str) from the successful client.
        """
        if not self._clients:
            raise LLMAllClientsFailedError(
                "no LLM clients registered — call register() first",
            )

        errors: list[str] = []
        for level in self._levels:
            client = self._clients.get(level)
            if client is None:
                continue

            try:
                # We need to peek at the first chunk to know if the
                # client connected successfully. Use a generator wrapper
                # so we can catch connection errors before yielding.
                gen = client.stream_chat(
                    messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs,
                )
                # Try to get the first chunk — this is where most
                # connection errors surface.
                try:
                    first_chunk = next(gen)
                except StopIteration:
                    # Empty stream — treat as success (rare but possible).
                    self._last_successful_level = level
                    return

                self._last_successful_level = level
                yield first_chunk
                # Yield the rest.
                yield from gen
                return
            except (LLMAPIError, LLMTimeoutError) as exc:
                errors.append(f"{level}: {type(exc).__name__}: {exc}")
                logger.warning(
                    "LLMRouter.stream: %s level failed: %s; trying next level",
                    level, exc,
                )
                continue
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{level}: {type(exc).__name__}: {exc}")
                logger.exception(
                    "LLMRouter.stream: %s level raised unexpected error: %s",
                    level, exc,
                )
                continue

        raise LLMAllClientsFailedError(
            f"all LLM clients failed. Errors: {' | '.join(errors)}",
        )


# ── Vision-capability routing (spec §7.2.2 — 任务 2.4) ──────────
# 视觉模型集合: 支持 image input 的模型, 才能调用 get_screenshot_base64.
# 用 frozenset + 前缀匹配, 兼容版本后缀 (gpt-4o-2024-08-06 等).
#
# 维护原则: 新增视觉模型时直接加到此集合. 当前覆盖:
# - OpenAI: gpt-4o, gpt-4o-mini (gpt-4-vision-preview 已 deprecated)
# - Anthropic: claude-3-5-sonnet, claude-3-opus, claude-3.7-sonnet
# - Google: gemini-1.5-pro, gemini-1.5-flash (通过 OpenAI-compatible 接口)
#
# 纯文本模型 (deepseek-chat / qwen2.5 / llama3 等) 不在此集合,
# 保守默认为纯文本, 避免视觉工具调用后 base64 解码失败.
VISION_CAPABLE_MODELS: frozenset[str] = frozenset({
    # OpenAI vision models
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    # Anthropic Claude 3.x (vision-capable)
    "claude-3-5-sonnet",
    "claude-3-5-haiku",
    "claude-3-opus",
    "claude-3.7-sonnet",
    # Google Gemini (vision-capable via OpenAI-compatible endpoint)
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-2.0-flash",
})


def is_vision_capable(model: str | None) -> bool:
    """判断模型是否支持视觉输入 (image base64).

    用前缀匹配, 兼容版本后缀:
    - ``gpt-4o`` 匹配 ``gpt-4o-2024-08-06``
    - ``claude-3-5-sonnet`` 匹配 ``claude-3-5-sonnet-20240620``

    Args:
        model: 模型名 (如 ``"gpt-4o"`` / ``"deepseek-chat"``). None / 空
               字符串视为纯文本.

    Returns:
        True 若模型支持视觉输入, False 视为纯文本 (保守默认).
    """
    if not model:
        return False
    model_lower = model.lower().strip()
    for vision_model in VISION_CAPABLE_MODELS:
        # 前缀匹配: model_lower 以 vision_model 开头, 后面紧跟 '' 或 '-' 或 '_'
        # 防止 "gpt-4o" 误匹配 "gpt-4oxxx" (但允许 "gpt-4o-mini" 和 "gpt-4o-2024-08-06")
        if model_lower == vision_model:
            return True
        if model_lower.startswith(vision_model + "-") or model_lower.startswith(vision_model + "_"):
            return True
    return False


def get_tools_for_model(model: str | None) -> list:
    """根据模型能力返回工具列表 (spec §7.2.2 — 任务 2.4).

    视觉模型 (gpt-4o / claude-3-5-sonnet 等) 拿到 6 个工具, 含
    ``get_screenshot_base64`` 用于读取原图做视觉诊断.

    纯文本模型 (deepseek-chat / qwen2.5 等) 拿到 5 个工具, 不含
    ``get_screenshot_base64`` — 让模型只依赖 ``get_structured_log``
    返回的 OCR 文本/置信度等结构化字段做诊断, 避免调用视觉工具后
    base64 解码失败.

    Args:
        model: 模型名 (如 ``"gpt-4o"``). None / 空字符串视为纯文本.

    Returns:
        LangChain @tool 装饰的工具列表 (6 个或 5 个).
    """
    # 延迟 import 避免循环依赖 (tools.py 依赖 Django models)
    from gaf_ai.agent.tools import (
        get_execution_detail,
        get_execution_steps,
        get_screenshot_base64,
        get_structured_log,
        get_task_config,
        search_similar_errors,
    )

    base_tools = [
        get_execution_detail,
        get_execution_steps,
        search_similar_errors,
        get_task_config,
        get_structured_log,
    ]
    if is_vision_capable(model):
        # 视觉模型: 加 screenshot 工具, 让 LLM 看原图
        base_tools.append(get_screenshot_base64)
    return base_tools
