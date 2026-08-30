"""Agent-side LLM client — thin HTTP wrapper around backend AI chat endpoint.

Task 2.1 (2026-08-08): Added ``stream_chat()`` method and aligned
``chat()`` signature with ``BaseLLMClient`` (defined in
``backend/gaf_ai/base_client.py``) so the agent client follows the
same interface contract as the backend's ``OpenAIClient``.

Phase 4.7 implements the agent-side LLM module per
``llm-integration-design.md`` §0.2 ("Agent 端 LLM 客户端" P2 item).

The agent does NOT call OpenAI / LLM providers directly. Instead it
delegates to the backend, which centralises:
  * LLMConfig (provider / api_key / api_base / model)
  * LLMRouter 4-level fallback chain (Phase 4.4)
  * TokenUsageTracker + per-Skill budget enforcement (Phase 4.6)
  * LLMUsageLog persistence (for cost analytics)

This module is a minimal HTTP client using only the Python standard
library (``urllib``) so it doesn't add a ``requests`` dependency to
the agent. The chat endpoint path is derived from ``GAF_API_PREFIX``
env var (default ``api/v2``) so it always matches the backend's
``ai/views.py:ai_chat_view`` route regardless of API version.

Contract (matches ``ai_chat_view`` response):
  Request:  {"message": str, "model": str = "gpt-4o-mini",
             "history": list = []}
  Response: {"reply": str, "model": str, "tokens_used": int,
             "input_tokens": int, "output_tokens": int,
             "cost": float, "timestamp": str}
  On config-missing backend: {"reply": str, "config_missing": True, ...}
  On error: {"error": str, "status_code": int}
"""

import json
import logging
import os
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

logger = logging.getLogger(__name__)

# Default backend HTTP endpoint for AI chat. The agent's WebSocket
# ``server_url`` is ws://host:port/ws/protocol/agents/ — we derive the
# HTTP base from it. Can be overridden via GAF_AGENT_API_BASE env var.
_DEFAULT_WS_PATH = os.environ.get("GAF_WS_AGENT_PATH", "ws/protocol/agents/")
_DEFAULT_WS_URL = os.environ.get("GAF_SERVER_URL", f"ws://127.0.0.1:8000/{_DEFAULT_WS_PATH}")


def _default_api_base() -> str:
    """Derive default HTTP API base from GAF_SERVER_URL env var."""
    parsed = urllib_parse.urlparse(_DEFAULT_WS_URL)
    scheme = "https" if parsed.scheme == "wss" else "http"
    if not parsed.hostname:
        return "http://127.0.0.1:8000"
    if parsed.port:
        return f"{scheme}://{parsed.hostname}:{parsed.port}"
    return f"{scheme}://{parsed.hostname}"


DEFAULT_API_BASE = _default_api_base()
_API_PREFIX = os.environ.get("GAF_API_PREFIX", "api/v2")
DEFAULT_CHAT_PATH = f"/{_API_PREFIX}/ai/chat/"
DEFAULT_TIMEOUT = 30  # seconds


def _derive_http_base(server_url: str) -> str:
    """Derive an HTTP base URL from the agent's WebSocket ``server_url``.

    Converts ``ws://`` → ``http://`` and ``wss://`` → ``https://``,
    then strips the WebSocket path to keep only ``scheme://host:port``.

    Args:
        server_url: Agent's WebSocket server URL (e.g.
            ``ws://127.0.0.1:8000/ws/protocol/agents/``).

    Returns:
        HTTP base URL like ``http://127.0.0.1:8000``.
    """
    if not server_url:
        return DEFAULT_API_BASE
    parsed = urllib_parse.urlparse(server_url)
    scheme = "https" if parsed.scheme == "wss" else "http"
    if not parsed.hostname:
        return DEFAULT_API_BASE
    if parsed.port:
        return f"{scheme}://{parsed.hostname}:{parsed.port}"
    return f"{scheme}://{parsed.hostname}"


class WorkerLlmClient:
    """HTTP client wrapping backend AI chat endpoint (path from GAF_API_PREFIX).

    Example::

        client = WorkerLlmClient(server_url=config.server_url,
                                token=config.agent_token)
        result = client.chat("Why did the click step fail?")
        if result.get("reply"):
            print(result["reply"])
    """

    def __init__(
        self,
        server_url: str = "",
        token: str = "",
        api_base: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Construct the client.

        Args:
            server_url: Agent's WebSocket server URL — used to derive
                the HTTP base if ``api_base`` is not given.
            token: Agent authentication token (JWT). Sent as
                ``Authorization: Bearer <token>``.
            api_base: Explicit HTTP base URL override. If given,
                ``server_url`` is ignored.
            timeout: Request timeout in seconds.
        """
        # Precedence: explicit api_base > env var > derived from server_url
        if api_base is None:
            api_base = os.environ.get("GAF_AGENT_API_BASE") or _derive_http_base(server_url)
        self._api_base = api_base.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._chat_url = f"{self._api_base}{DEFAULT_CHAT_PATH}"

    @property
    def chat_url(self) -> str:
        """Full chat endpoint URL (read-only, for diagnostics)."""
        return self._chat_url

    def chat(
        self,
        message: str,
        model: str = "gpt-4o-mini",
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Send a chat message to the backend and return the response.

        Implements the ``BaseLLMClient.chat()`` interface contract,
        adapted for the agent's HTTP->backend delegation pattern.

        Args:
            message: User message text (maps to ``messages[0].content``
                in the ``BaseLLMClient`` interface).
            model: Model name (default ``gpt-4o-mini``).
            history: Optional conversation history as a list of
                ``{"role": "user"|"assistant", "content": str}`` dicts.

        Returns:
            Backend response dict. On success contains ``reply``,
            ``model``, ``tokens_used``, ``input_tokens``,
            ``output_tokens``, ``cost``, ``timestamp``. On backend
            config-missing contains ``config_missing: True``. On
            network / HTTP error contains ``error`` + ``status_code``.
        """
        payload = {
            "message": message,
            "model": model,
            "history": history or [],
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib_request.Request(
            self._chat_url,
            data=body,
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        if self._token:
            req.add_header("Authorization", f"Bearer {self._token}")

        try:
            with urllib_request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib_error.HTTPError as exc:
            # Backend returned an error status — try to read the JSON body
            try:
                err_body = exc.read().decode("utf-8", errors="replace")
                err_data = json.loads(err_body)
            except (ValueError, OSError):
                err_data = {}
            logger.warning(
                "WorkerLlmClient HTTP %d from %s: %s",
                exc.code, self._chat_url, err_data,
            )
            return {
                "error": err_data.get("error") or err_data.get("detail") or f"HTTP {exc.code}",
                "status_code": exc.code,
                "reply": "",
            }
        except urllib_error.URLError as exc:
            # Network-level failure (backend unreachable, DNS, etc.)
            logger.warning(
                "WorkerLlmClient network error contacting %s: %s",
                self._chat_url, exc.reason,
            )
            return {
                "error": f"network error: {exc.reason}",
                "status_code": 0,
                "reply": "",
            }
        except Exception as exc:
            # Unexpected error — log and return error dict (never raise)
            logger.exception(
                "WorkerLlmClient unexpected error contacting %s: %s",
                self._chat_url, exc,
            )
            return {
                "error": f"unexpected error: {exc}",
                "status_code": -1,
                "reply": "",
            }

    def is_available(self) -> bool:
        """Quick connectivity check — does the chat endpoint respond?

        Sends an empty-message POST and checks for any HTTP response
        (even a 400 "message required" counts as available).

        Returns:
            ``True`` if the backend is reachable, ``False`` otherwise.
        """
        try:
            payload = json.dumps({"message": ""}).encode("utf-8")
            req = urllib_request.Request(
                self._chat_url, data=payload, method="POST",
            )
            req.add_header("Content-Type", "application/json")
            if self._token:
                req.add_header("Authorization", f"Bearer {self._token}")
            urllib_request.urlopen(req, timeout=5)
            return True
        except urllib_error.HTTPError:
            # Got an HTTP response (e.g. 400) — backend is reachable
            return True
        except urllib_error.URLError:
            return False
        except Exception:
            return False

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> Any:
        """Stream a chat response from the backend (delegates to HTTP).

        Implements the ``BaseLLMClient.stream_chat()`` interface contract.
        The agent's HTTP client doesn't support true streaming, so this
        method calls ``chat()`` and yields the single response as one chunk.

        For true streaming, use the WebSocket RPC path (``llm.call`` via
        ``connection.py:send_llm_call``) which receives streaming chunks
        via ``llm.result`` frames.

        Args:
            messages: OpenAI-format message list. The last message's
                ``content`` is used as the chat message, and preceding
                messages are treated as history.
            model: Model name override. None = use default.
            temperature: Sampling temperature (ignored for HTTP delegation).
            max_tokens: Maximum tokens to generate.
            **kwargs: Additional parameters (ignored for HTTP delegation).

        Yields:
            The full response content as a single chunk.
        """
        # Convert OpenAI-format messages to the agent's chat() format.
        # The last user message becomes the ``message`` param; preceding
        # messages become ``history``.
        message = ""
        history: list[dict[str, str]] = []
        for msg in messages:
            if msg.get("role") == "user":
                message = msg.get("content", "")
            else:
                history.append(msg)

        result = self.chat(
            message=message,
            model=model or "gpt-4o-mini",
            history=history,
        )

        if result.get("reply"):
            yield result["reply"]
        elif result.get("error"):
            yield f"[LLM error] {result['error']}"
        else:
            yield ""

    def diagnose_failure(
        self,
        error_context: dict[str, Any],
        model: str = "deepseek-chat",
    ) -> dict[str, Any]:
        """Ask the LLM to diagnose a pipeline / node failure.

        Per project_rules.md §4.8.2: when ``debug_mode=True`` and a node
        exhausts all local auto-heal attempts (e.g. template_match tried
        all screenshot methods), the agent must consult the LLM for a
        diagnosis before notifying the user. The LLM receives a
        structured error context and returns a suggested fix.

        This method NEVER raises — on any error (network, backend,
        config-missing, malformed response) it returns an ``error`` dict
        so the caller can fall back to the original error message
        without blocking the main pipeline flow.

        Args:
            error_context: Structured dict with keys:
                - node_type (str): e.g. "template_match"
                - error_msg (str): The original failure message
                - diagnostic_report (str, optional): Full diagnostic
                  report from screenshot_diagnostic or similar
                - template_name (str, optional): Template path/name
                - confidence (float, optional): Best confidence reached
                - threshold (float, optional): Required threshold
                - roi (dict, optional): Region of interest
                - pipeline_name (str, optional): Pipeline name
                - structured_log_path (str, optional): Path to JSONL log
                - extra (dict, optional): Any other context
            model: LLM model name (default ``deepseek-chat`` for cost
                efficiency — diagnosis doesn't need GPT-4o).

        Returns:
            On success: ``{"diagnosis": str, "suggested_fix": str,
            "raw_reply": str, "model": str}``.
            On failure: ``{"error": str, "diagnosis": "",
            "suggested_fix": ""}`` — never raises.
        """
        # Build a focused diagnosis prompt. We keep it concise to limit
        # token cost — the LLM doesn't need the full structured log,
        # just the key failure context. If the user needs deeper
        # analysis, they can use the LangGraph Agent (POST /ai/agent/analyze/).
        prompt_lines = [
            "You are a game automation debug assistant. A pipeline node failed.",
            "Diagnose the root cause and suggest ONE concrete fix.",
            "",
            f"Node type: {error_context.get('node_type', 'unknown')}",
            f"Error: {error_context.get('error_msg', '')}",
        ]
        if error_context.get("template_name"):
            prompt_lines.append(f"Template: {error_context['template_name']}")
        if "confidence" in error_context and "threshold" in error_context:
            prompt_lines.append(
                f"Confidence: {error_context['confidence']:.4f} "
                f"(threshold: {error_context['threshold']:.2f})"
            )
        if error_context.get("roi"):
            prompt_lines.append(f"ROI: {error_context['roi']}")
        if error_context.get("diagnostic_report"):
            prompt_lines.append("")
            prompt_lines.append("Diagnostic report:")
            prompt_lines.append(error_context["diagnostic_report"])
        if error_context.get("pipeline_name"):
            prompt_lines.append(f"Pipeline: {error_context['pipeline_name']}")
        if error_context.get("structured_log_path"):
            prompt_lines.append(
                f"Structured log: {error_context['structured_log_path']}"
            )
        if error_context.get("extra"):
            prompt_lines.append(f"Extra context: {error_context['extra']}")

        prompt_lines.extend([
            "",
            "Respond in EXACTLY this format (no markdown):",
            "DIAGNOSIS: <one-sentence root cause>",
            "FIX: <one-sentence actionable suggestion>",
        ])
        message = "\n".join(prompt_lines)

        try:
            result = self.chat(message=message, model=model)
        except Exception as exc:
            # Defensive — chat() already catches everything, but guard
            # against unexpected exceptions in prompt construction.
            logger.warning(
                "diagnose_failure: chat() raised unexpectedly: %s", exc,
            )
            return {
                "error": f"chat raised: {exc}",
                "diagnosis": "",
                "suggested_fix": "",
            }

        # Backend unreachable / config missing / network error
        if result.get("error") and not result.get("reply"):
            logger.warning(
                "diagnose_failure: backend returned error: %s",
                result.get("error"),
            )
            return {
                "error": result["error"],
                "diagnosis": "",
                "suggested_fix": "",
            }

        # Config-missing response: backend reachable but no LLM configured
        if result.get("config_missing"):
            logger.info(
                "diagnose_failure: backend has no LLM configured, skipping diagnosis",
            )
            return {
                "error": "LLM not configured on backend",
                "diagnosis": "",
                "suggested_fix": "",
            }

        reply = result.get("reply", "")
        if not reply:
            return {
                "error": "empty reply from LLM",
                "diagnosis": "",
                "suggested_fix": "",
            }

        # Parse the structured response. Be lenient — if the LLM didn't
        # follow the exact format, still return the raw reply so the
        # caller can display something useful.
        diagnosis = ""
        suggested_fix = ""
        for line in reply.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("DIAGNOSIS:"):
                diagnosis = stripped[len("DIAGNOSIS:"):].strip()
            elif stripped.upper().startswith("FIX:"):
                suggested_fix = stripped[len("FIX:"):].strip()

        if not diagnosis and not suggested_fix:
            # LLM didn't follow format — use the whole reply as diagnosis
            diagnosis = reply.strip()

        return {
            "diagnosis": diagnosis,
            "suggested_fix": suggested_fix,
            "raw_reply": reply,
            "model": result.get("model", model),
        }
