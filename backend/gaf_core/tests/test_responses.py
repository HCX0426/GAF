"""Tests for the unified API response format, error codes, and middleware."""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.conf import settings
from django.http import JsonResponse
from django.test import override_settings
from rest_framework.response import Response
from rest_framework.test import APIClient

from gaf_core.error_codes import ErrorCode
from gaf_core.exceptions import BusinessException, unified_exception_handler
from gaf_core.middleware import UnifiedResponseMiddleware
from gaf_core.responses import unified_response

pytestmark = pytest.mark.django_db


class TestUnifiedResponseHelper:
    """Tests for :func:`gaf_core.responses.unified_response`."""

    def test_success_response(self) -> None:
        resp = unified_response({"id": 1}, message="created", status=201)
        assert resp.status_code == 201
        assert resp.data == {"code": 0, "message": "created", "data": {"id": 1}}

    def test_custom_code(self) -> None:
        resp = unified_response(
            None,
            message="device offline",
            code=ErrorCode.DEVICE_OFFLINE,
            status=400,
        )
        assert resp.data == {
            "code": 3001,
            "message": "device offline",
            "data": None,
        }


class TestBusinessException:
    """Tests for :class:`gaf_core.exceptions.BusinessException`."""

    def test_numeric_error_code(self) -> None:
        exc = BusinessException(
            detail="device is offline",
            code=ErrorCode.DEVICE_OFFLINE,
            status_code=400,
        )
        assert exc.status_code == 400
        assert exc.error_code == ErrorCode.DEVICE_OFFLINE
        assert exc.get_codes() == str(ErrorCode.DEVICE_OFFLINE)

    def test_default_code(self) -> None:
        exc = BusinessException(detail="something went wrong")
        assert exc.error_code == ErrorCode.INTERNAL_ERROR


class TestUnifiedExceptionHandler:
    """Tests for :func:`gaf_core.exceptions.unified_exception_handler`."""

    @override_settings(GAF_UNIFIED_RESPONSE_ENABLED=True)
    def test_authentication_failed(self) -> None:
        from rest_framework.exceptions import AuthenticationFailed

        exc = AuthenticationFailed(detail="token is invalid")
        response = unified_exception_handler(exc, {"request": None})
        assert response is not None
        assert response.status_code == 401
        assert response.data == {
            "code": ErrorCode.TOKEN_INVALID,
            "message": "token is invalid",
            "data": None,
        }

    @override_settings(GAF_UNIFIED_RESPONSE_ENABLED=True)
    def test_validation_error(self) -> None:
        from rest_framework.exceptions import ValidationError

        exc = ValidationError({"username": ["This field is required."]})
        response = unified_exception_handler(exc, {"request": None})
        assert response is not None
        assert response.data == {
            "code": ErrorCode.INVALID_PARAMS,
            "message": "This field is required.",
            "data": None,
        }

    def test_unhandled_returns_none(self) -> None:
        """Exceptions DRF does not handle should bubble up to Django."""
        response = unified_exception_handler(ValueError("boom"), {"request": None})
        assert response is None

    @override_settings(GAF_UNIFIED_RESPONSE_ENABLED=False)
    def test_disabled_passthrough(self) -> None:
        """When the feature is disabled the native DRF format is preserved."""
        from rest_framework.exceptions import AuthenticationFailed

        exc = AuthenticationFailed(detail="token is invalid")
        response = unified_exception_handler(exc, {"request": None})
        assert response is not None
        assert response.data == {"detail": "token is invalid"}


class TestUnifiedResponseMiddleware:
    """Tests for :class:`gaf_core.middleware.UnifiedResponseMiddleware`."""

    @staticmethod
    def _make_middleware(payload: Any, status: int = 200) -> UnifiedResponseMiddleware:
        def get_response(_request: Any) -> Response:
            return Response(payload, status=status)

        return UnifiedResponseMiddleware(get_response)

    def test_wraps_success_response(self) -> None:
        mw = self._make_middleware({"count": 1, "results": []})
        with override_settings(GAF_UNIFIED_RESPONSE_ENABLED=True):
            response = mw(None)
        assert response.data == {
            "code": 0,
            "message": "ok",
            "data": {"count": 1, "results": []},
        }

    def test_wraps_error_response(self) -> None:
        # N192 B1/B2 P0: 错误响应 code 改用 ErrorCode 数字 (而非 HTTP status_code)
        mw = self._make_middleware({"detail": "not found"}, status=404)
        with override_settings(GAF_UNIFIED_RESPONSE_ENABLED=True):
            response = mw(None)
        assert response.data == {
            "code": ErrorCode.NOT_FOUND,
            "message": "not found",
            "data": None,
        }

    def test_disabled_middleware_passes_through(self) -> None:
        mw = self._make_middleware({"count": 1})
        with override_settings(GAF_UNIFIED_RESPONSE_ENABLED=False):
            response = mw(None)
        assert response.data == {"count": 1}

    def test_skips_already_unified_response(self) -> None:
        payload = {"code": 0, "message": "ok", "data": [1, 2, 3]}

        def get_response(_request: Any) -> Response:
            resp = Response(payload)
            resp._is_unified = True  # noqa: SLF001
            return resp

        mw = UnifiedResponseMiddleware(get_response)
        with override_settings(GAF_UNIFIED_RESPONSE_ENABLED=True):
            response = mw(None)
        assert response.data == payload

    def test_wraps_django_json_response(self) -> None:
        def get_response(_request: Any) -> JsonResponse:
            return JsonResponse({"items": [1]})

        mw = UnifiedResponseMiddleware(get_response)
        with override_settings(GAF_UNIFIED_RESPONSE_ENABLED=True):
            response = mw(None)
        assert json.loads(response.content) == {
            "code": 0,
            "message": "ok",
            "data": {"items": [1]},
        }


class TestUnifiedResponseIntegration:
    """End-to-end tests against real DRF views with the middleware enabled."""

    def _unified_rest_framework_settings(self) -> dict[str, Any]:
        return {
            **settings.REST_FRAMEWORK,
            "EXCEPTION_HANDLER": "gaf_core.exceptions.unified_exception_handler",
        }

    def test_validation_error_from_login_endpoint(self) -> None:
        client = APIClient()
        with override_settings(
            GAF_UNIFIED_RESPONSE_ENABLED=True,
            REST_FRAMEWORK=self._unified_rest_framework_settings(),
        ):
            response = client.post(
                "/api/v2/accounts/auth/login/",
                {},
                format="json",
            )
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == ErrorCode.INVALID_PARAMS
        assert body["data"] is None
        # Error message is translated; just verify it is non-empty and mentions
        # a required field.
        assert body["message"]
        assert "必填" in body["message"] or "required" in body["message"].lower()

    def test_authentication_failed_from_login_endpoint(self) -> None:
        client = APIClient()
        with override_settings(
            GAF_UNIFIED_RESPONSE_ENABLED=True,
            REST_FRAMEWORK=self._unified_rest_framework_settings(),
        ):
            response = client.post(
                "/api/v2/accounts/auth/login/",
                {"username": "not-a-user", "password": "wrong"},
                format="json",
            )
        assert response.status_code == 401
        body = response.json()
        assert body["code"] == ErrorCode.TOKEN_INVALID
        assert body["data"] is None
