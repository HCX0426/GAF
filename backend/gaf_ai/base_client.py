"""LLM 客户端基类与共享数据类型 — 统一 Agent 与 Backend 的 LLM 接口。

提供 ``BaseLLMClient`` 抽象基类以及 ``LLMMessage`` / ``LLMResponse``
数据类，供 Agent 端和 Backend 端共同遵循的接口契约。

Task 2.1 (2026-08-08): 从 ``qa_llm_client.py`` 提取，消除重复定义。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ── Shared data types ──────────────────────────────────────────

@dataclass
class LLMMessage:
    """LLM 消息单元 — 与 OpenAI API 的 message 结构一致。"""
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMResponse:
    """LLM 响应数据类 — 标准化返回结构。"""
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    latency_ms: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


# ── Abstract base class ────────────────────────────────────────

class BaseLLMClient(ABC):
    """LLM 客户端抽象基类 — 所有 LLM 客户端必须实现此接口。

    方法签名约定:
        - ``messages``: list[dict[str, str]] — OpenAI 格式消息列表
        - ``model``: str | None — 模型名覆盖
        - ``temperature``: float — 采样温度 (0.0 ~ 2.0)
        - ``max_tokens``: int — 最大生成 Token 数
        - ``**kwargs``: 额外参数 (provider 特定)

    返回约定:
        - ``chat()``: dict — 包含 ``content``, ``model``, ``usage``
          (含 ``input_tokens``, ``output_tokens``), ``offline`` (可选)
        - ``stream_chat()``: Generator[str, None, None] — 逐个 yield 内容块
    """

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> dict[str, Any]:
        """Send a chat request and return the full response.

        Args:
            messages: OpenAI-format message list.
            model: Model name override. None = use client default.
            temperature: Sampling temperature (0.0 ~ 2.0).
            max_tokens: Maximum tokens to generate.
            **kwargs: Additional provider-specific parameters.

        Returns:
            dict with ``content``, ``model``, ``usage`` (``input_tokens``,
            ``output_tokens``), and optionally ``offline`` / ``route``.
        """
        ...

    @abstractmethod
    def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> Any:
        """Stream a chat request, yielding content chunks.

        Args:
            Same as ``chat()``.

        Yields:
            Content chunks (str) from the LLM.
        """
        ...


# ── Exceptions ─────────────────────────────────────────────────

class LLMAPIError(Exception):
    """LLM API 调用错误"""


class LLMTimeoutError(LLMAPIError):
    """LLM API 超时错误"""
