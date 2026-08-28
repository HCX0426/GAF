"""LLM API client hierarchy (migrated from qa app — 2026-08-04).

Task 2.1 (2026-08-08): ``BaseLLMClient``, ``LLMMessage``, ``LLMResponse``,
and exception classes extracted to ``gaf_ai.base_client``. This module
re-exports them for backward compatibility and keeps the concrete
implementations (``OpenAIClient``).
"""

import json
import logging

import requests

from gaf_ai.base_client import (
    BaseLLMClient,
    LLMAPIError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)

MODEL_CONFIGS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "chat_endpoint": "/chat/completions",
        "default_model": "gpt-4o",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "chat_endpoint": "/chat/completions",
        "default_model": "deepseek-chat",
    },
    "custom": {
        "base_url": "",
        "chat_endpoint": "/chat/completions",
        "default_model": "",
    },
}


class OpenAIClient(BaseLLMClient):
    def __init__(self, api_key, provider="openai", base_url=None, model=None, timeout=120):
        self._api_key = api_key
        self._provider = provider
        self._timeout = timeout
        config = MODEL_CONFIGS.get(provider, MODEL_CONFIGS["custom"])
        self._base_url = base_url or config["base_url"]
        self._model = model or config["default_model"]
        self._chat_endpoint = config["chat_endpoint"]

    @property
    def provider(self):
        return self._provider

    @property
    def base_url(self):
        return self._base_url

    @property
    def model(self):
        return self._model

    def chat(self, messages, model=None, temperature=0.7, max_tokens=4096, **kwargs):
        url = f"{self._base_url}{self._chat_endpoint}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self._timeout)
            response.raise_for_status()
            data = response.json()
            content = ""
            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
            usage = data.get("usage", {})
            return {
                "content": content,
                "usage": {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
                "model": data.get("model", model or self._model),
            }
        except requests.exceptions.Timeout:
            logger.error("LLM API 请求超时 (%ds)", self._timeout)
            raise LLMTimeoutError(f"LLM 请求超时 ({self._timeout}s)") from None
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            logger.error("LLM API HTTP 错误: %s", exc)
            raise LLMAPIError(f"LLM API 错误: {status}") from exc
        except Exception as exc:
            logger.error("LLM API 调用异常: %s", exc)
            raise LLMAPIError(f"LLM 调用失败: {exc}") from exc

    def stream_chat(self, messages, model=None, temperature=0.7, max_tokens=4096, **kwargs):
        url = f"{self._base_url}{self._chat_endpoint}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self._timeout, stream=True)
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue
        except requests.exceptions.Timeout:
            logger.error("LLM 流式请求超时")
            raise LLMTimeoutError("LLM 流式请求超时") from None
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            logger.error("LLM 流式 HTTP 错误: %s", exc)
            raise LLMAPIError(f"LLM API 错误: {status}") from exc
        except Exception as exc:
            logger.error("LLM 流式调用异常: %s", exc)
            raise LLMAPIError(f"LLM 流式调用失败: {exc}") from exc

    def chat_stream(self, *args, **kwargs):
        return self.stream_chat(*args, **kwargs)


LLMClient = OpenAIClient
