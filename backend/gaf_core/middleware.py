"""Middleware that wraps JSON responses in the GAF unified envelope.

The wrapper is gated by the ``GAF_UNIFIED_RESPONSE_ENABLED`` setting so existing
clients continue to receive DRF's default response format until they opt in.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.http import HttpResponse
from rest_framework.response import Response

from gaf_core.error_codes import ErrorCode
from gaf_core.perf_monitor import Timer

logger = logging.getLogger(__name__)


class PerfMiddleware:
    """Measure API request response times (development mode only).

    Records a ``Timer`` measurement named
    ``"api.request.{method}:{path}"`` for every HTTP request that passes
    through the middleware stack. Only active in development mode
    (``GAF_CELERY_MODE=eager``).
    """

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> HttpResponse:
        if not self._is_active():
            return self.get_response(request)

        # Build a concise path: strip query params, limit length.
        path = request.path
        if len(path) > 120:
            path = path[:60] + "..." + path[-57:]

        name = f"api.request.{request.method}:{path}"
        with Timer(name, tags={"method": request.method, "path": request.path}):
            response = self.get_response(request)
        return response

    @staticmethod
    def _is_active() -> bool:
        """PerfMiddleware only active in development mode."""
        mode = settings.GAF_CELERY_MODE if hasattr(settings, "GAF_CELERY_MODE") else "eager"
        return mode == "eager"


class UnifiedResponseMiddleware:
    """Wrap JSON API responses as ``{ code, message, data }``.

    Only responses whose ``Content-Type`` contains ``application/json`` are
    wrapped. Responses already carrying the unified envelope or produced by
    :func:`gaf_core.exceptions.unified_exception_handler` are skipped.
    """

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> HttpResponse:
        response = self.get_response(request)
        if not getattr(settings, "GAF_UNIFIED_RESPONSE_ENABLED", False):
            return response
        if getattr(response, "_is_unified", False):
            return response
        if not self._is_json_response(response):
            return response

        payload = self._parse_payload(response)
        if payload is None:
            return response
        if self._already_unified(payload):
            return response

        wrapped = self._wrap_payload(payload, response.status_code)
        self._apply_payload(response, wrapped)
        response._is_unified = True  # noqa: SLF001
        return response

    @staticmethod
    def _is_json_response(response: HttpResponse) -> bool:
        if isinstance(response, Response):
            # DRF responses are JSON once rendered; skip the content-type check
            # so we can wrap them even before rendering happens.
            return True
        content_type = response.get("Content-Type", "")
        return "application/json" in content_type

    @staticmethod
    def _parse_payload(response: HttpResponse) -> Any | None:
        if isinstance(response, Response):
            # DRF keeps the decoded data object even after rendering.
            return response.data
        try:
            return json.loads(response.content)
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _already_unified(payload: Any) -> bool:
        return (
            isinstance(payload, dict)
            and "code" in payload
            and "message" in payload
            and "data" in payload
        )

    @staticmethod
    def _wrap_payload(payload: Any, status_code: int) -> dict[str, Any]:
        if status_code < 400:
            return {"code": 0, "message": "ok", "data": payload}
        # N192 B1/B2 P0: 错误响应 code 改用 ErrorCode 数字 (而非 HTTP status_code)
        code = _resolve_error_code(status_code)
        message = _default_error_message(payload, status_code)
        return {"code": code, "message": message, "data": None}

    @staticmethod
    def _apply_payload(response: HttpResponse, payload: dict[str, Any]) -> None:
        if isinstance(response, Response):
            response.data = payload
            if getattr(response, "accepted_renderer", None) is not None:
                response.render()
        else:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            response.content = encoded


def _resolve_error_code(status_code: int) -> int:
    """HTTP status_code → ErrorCode 数字映射.

    N192 B1/B2 P0: 让 middleware 错误响应的 ``code`` 字段使用 ErrorCode 体系
    (4 位业务码) 而非 HTTP status_code, 这样前端可基于 ``code`` 做错误码 →
    user_message 映射, 同一错误码展示一致文案。
    """
    if status_code >= 500:
        return ErrorCode.INTERNAL_ERROR
    if status_code == 401:
        return ErrorCode.UNAUTHORIZED
    if status_code == 403:
        return ErrorCode.PERMISSION_DENIED
    if status_code == 404:
        return ErrorCode.NOT_FOUND
    if status_code == 405:
        return ErrorCode.METHOD_NOT_ALLOWED
    if status_code == 429:
        return ErrorCode.RATE_LIMITED
    if status_code >= 400:
        return ErrorCode.INVALID_PARAMS
    return ErrorCode.INTERNAL_ERROR


def _default_error_message(payload: Any, status_code: int) -> str:
    """Derive a short error message from a DRF-style error payload."""
    if isinstance(payload, dict):
        if "detail" in payload:
            detail = payload["detail"]
            if isinstance(detail, list):
                return str(detail[0]) if detail else "error"
            return str(detail)
        if payload:
            # Field-level errors: report the first field's first message.
            first_value = next(iter(payload.values()))
            if isinstance(first_value, list):
                return str(first_value[0]) if first_value else "error"
            return str(first_value)
    if isinstance(payload, list):
        return str(payload[0]) if payload else "error"
    if isinstance(payload, str):
        return payload
    return f"error ({status_code})"
