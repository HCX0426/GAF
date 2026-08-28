"""Custom exceptions and DRF exception handler for the unified API format.

The handler converts standard DRF exceptions (and subclasses) into the
``{ code, message, data }`` envelope. Business code can raise
:class:`BusinessException` with a specific 4-digit :class:`gaf_core.error_codes.ErrorCode`.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework import status as drf_status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.views import exception_handler as drf_exception_handler

from gaf_core.error_codes import ErrorCode


class BusinessException(APIException):
    """Business-level error with a 4-digit code and optional HTTP status.

    Example::

        raise BusinessException(
            detail="device is offline",
            code=ErrorCode.DEVICE_OFFLINE,
            status_code=400,
        )
    """

    status_code = drf_status.HTTP_400_BAD_REQUEST
    default_detail = "business error"
    default_code = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: ErrorCode | int | None = None,
        status_code: int | None = None,
    ) -> None:
        if status_code is not None:
            self.status_code = status_code
        if code is None:
            code = self.default_code
        # DRF stores the code as a string; keep the numeric value available too.
        super().__init__(detail=detail, code=str(code))
        self.error_code = int(code)


def _extract_message(data: Any) -> str:
    """Flatten DRF error data into a single human-readable string."""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return _extract_message(data[0]) if data else "error"
    if isinstance(data, dict):
        if "detail" in data:
            return _extract_message(data["detail"])
        # Field-level validation errors: take the first message of the first field.
        for value in data.values():
            return _extract_message(value)
    return str(data)


def _code_for_exception(exc: APIException, http_status: int) -> int:
    """Map a DRF exception to a 4-digit business error code."""
    if isinstance(exc, NotAuthenticated):
        return ErrorCode.UNAUTHORIZED
    if isinstance(exc, AuthenticationFailed):
        return ErrorCode.TOKEN_INVALID
    if isinstance(exc, PermissionDenied):
        return ErrorCode.PERMISSION_DENIED
    if isinstance(exc, NotFound):
        return ErrorCode.NOT_FOUND
    if isinstance(exc, ValidationError):
        return ErrorCode.INVALID_PARAMS
    if isinstance(exc, MethodNotAllowed):
        return ErrorCode.METHOD_NOT_ALLOWED
    if isinstance(exc, Throttled):
        return ErrorCode.RATE_LIMITED
    if http_status >= 500:
        return ErrorCode.INTERNAL_ERROR
    # Fallback: keep the 1xxx/generic space aligned with HTTP status families.
    return ErrorCode.INTERNAL_ERROR


def unified_exception_handler(exc: Any, context: dict[str, Any]) -> Any:
    """DRF exception handler that wraps errors in the GAF unified envelope.

    Install via ``REST_FRAMEWORK['EXCEPTION_HANDLER']``.
    Returns ``None`` for exceptions DRF does not handle (Django will raise 500).

    Wrapping is gated by ``GAF_UNIFIED_RESPONSE_ENABLED`` so existing clients
    continue to receive DRF's native error format by default.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    if not getattr(settings, "GAF_UNIFIED_RESPONSE_ENABLED", False):
        return response

    code = _code_for_exception(exc, response.status_code)
    message = _extract_message(response.data)
    response.data = {"code": int(code), "message": message, "data": None}
    response._is_unified = True  # noqa: SLF001
    return response
