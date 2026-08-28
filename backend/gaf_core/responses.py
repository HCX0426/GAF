"""Helpers for producing the GAF unified API response envelope.

All successful responses use the shape::

    { "code": 0, "message": "ok", "data": <payload> }

Error responses produced by :func:`unified_exception_handler` use the same
shape with a non-zero ``code`` and ``data`` set to ``None``.
"""

from __future__ import annotations

from typing import Any

from rest_framework.response import Response

from gaf_core.error_codes import ErrorCode


def unified_response(
    data: Any = None,
    *,
    message: str = "ok",
    code: ErrorCode | int = ErrorCode.SUCCESS,
    status: int = 200,
    **kwargs: Any,
) -> Response:
    """Return a DRF Response wrapped in the GAF unified envelope.

    Args:
        data: The business payload to place under the ``data`` key.
        message: Human-readable message. Use i18n keys in production.
        code: A 4-digit business code (``ErrorCode`` or integer).
        status: HTTP status code.
        **kwargs: Extra arguments forwarded to ``Response``.

    Returns:
        A DRF ``Response`` whose rendered JSON is ``{code, message, data}``.
    """
    return Response(
        {"code": int(code), "message": message, "data": data},
        status=status,
        **kwargs,
    )
