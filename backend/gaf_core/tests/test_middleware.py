"""Tests for UnifiedResponseMiddleware error code mapping (N192 B1/B2 P0).

These tests verify that the middleware maps HTTP status codes to ErrorCode
integers (1001/2001/3001 etc.) rather than echoing the raw HTTP status_code
in the unified envelope's ``code`` field. This lets the frontend map
error_code → user_message consistently.
"""

import json

import pytest
from django.test import RequestFactory
from rest_framework import status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from gaf_core.middleware import UnifiedResponseMiddleware


def _make_response(payload, http_status=None):
    """Build a DRF Response with accepted_renderer set (mimics DRF view dispatch)."""
    resp = Response(payload, status=http_status) if http_status is not None else Response(payload)
    # In real DRF flow, View.finalize_response() sets these before the
    # response is returned to middleware. Without them, the middleware
    # cannot render the response and tests cannot read response.content.
    resp.accepted_renderer = JSONRenderer()
    resp.accepted_media_type = "application/json"
    resp.renderer_context = {}
    return resp


@pytest.mark.django_db
def test_unified_response_error_uses_error_code_not_http_status():
    """错误响应的 code 字段应使用 ErrorCode 数字, 而非 HTTP status_code."""
    rf = RequestFactory()
    request = rf.get("/")

    class MockView:
        def __call__(self, request):
            return _make_response(
                {"detail": "device offline"},
                http_status=status.HTTP_400_BAD_REQUEST,
            )

    middleware = UnifiedResponseMiddleware(get_response=MockView())
    response = middleware(request)

    body = json.loads(response.content)
    # code 应该是 ErrorCode.INVALID_PARAMS (1001), 不是 HTTP 400
    assert body["code"] == 1001, f"Expected ErrorCode.INVALID_PARAMS, got {body['code']}"
    assert body["message"] == "device offline"
    assert "data" in body


@pytest.mark.django_db
def test_unified_response_success_unchanged():
    """成功响应 (2xx) 的 code 应该是 0 (ErrorCode.SUCCESS)."""
    rf = RequestFactory()
    request = rf.get("/")

    class MockView:
        def __call__(self, request):
            return _make_response({"id": 1, "name": "test"})

    middleware = UnifiedResponseMiddleware(get_response=MockView())
    response = middleware(request)

    body = json.loads(response.content)
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"] == {"id": 1, "name": "test"}


@pytest.mark.django_db
def test_unified_response_500_uses_internal_error():
    """5xx 错误的 code 应该是 ErrorCode.INTERNAL_ERROR (1000)."""
    rf = RequestFactory()
    request = rf.get("/")

    class MockView:
        def __call__(self, request):
            return _make_response(
                {"detail": "server crashed"},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    middleware = UnifiedResponseMiddleware(get_response=MockView())
    response = middleware(request)

    body = json.loads(response.content)
    assert body["code"] == 1000
    assert body["message"] == "server crashed"


@pytest.mark.django_db
def test_unified_response_401_uses_unauthorized():
    """401 错误的 code 应该是 ErrorCode.UNAUTHORIZED (2001)."""
    rf = RequestFactory()
    request = rf.get("/")

    class MockView:
        def __call__(self, request):
            return _make_response(
                {"detail": "not logged in"},
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

    middleware = UnifiedResponseMiddleware(get_response=MockView())
    response = middleware(request)

    body = json.loads(response.content)
    assert body["code"] == 2001
    assert body["message"] == "not logged in"
