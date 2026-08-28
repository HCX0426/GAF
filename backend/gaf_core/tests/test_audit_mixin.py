"""Unit tests for gaf_core.mixins.audit (spec34 Phase 1, TD-259 #11).

Coverage:
- AuditMixin.perform_create / perform_update / perform_destroy
- AuditMixin opt-out via audit_log_create/update/destroy = False
- AuditMixin._build_audit_details override hook
- AuditMixin resource_type fallback to model_name
- @audit_action decorator (success path)
- @audit_action decorator (failure path — no log written on exception)
- build_diff_details helper (before/after shape + sensitive redaction)
- get_client_ip (X-Forwarded-For / REMOTE_ADDR / neither)
- filter_sensitive_fields (default deny-list + caller-supplied extras)
- AuditResourceType.all_values (sanity: 25+ values, all lowercase slugs)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.test import APIRequestFactory

from accounts.models import AuditLog
from gaf_core.audit_constants import (
    SENSITIVE_FIELD_NAMES,
    AuditAction,
    AuditResourceType,
    filter_sensitive_fields,
    get_client_ip,
)
from gaf_core.mixins import AuditMixin, audit_action, build_diff_details

User = get_user_model()

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Test fixtures: a minimal model-like object + serializer + viewset
# ---------------------------------------------------------------------------


class _FakeInstance:
    """Minimal stand-in for a Django model instance.

    AuditMixin only needs ``_meta.model_name`` and whatever attribute
    ``audit_resource_id_attr`` points to (default ``pk``). We don't want
    to depend on a real model here because the mixin should work with
    any model — the unit tests must verify the *mixin* logic, not model
    behavior.
    """

    def __init__(self, pk: int, name: str, status: str):
        self.pk = pk
        self.name = name
        self.status = status

    @property
    def _meta(self):
        meta = MagicMock()
        meta.model_name = "fake"
        return meta


class _FakeSerializer:
    """Serializer stand-in: save() returns the configured instance."""

    def __init__(self, instance: _FakeInstance):
        self._instance = instance

    @property
    def instance(self):
        return self._instance

    def save(self):
        return self._instance


class _DummyViewSet(AuditMixin, viewsets.ModelViewSet):
    """Concrete ViewSet used to test AuditMixin in isolation."""

    audit_resource_type = AuditResourceType.TASK
    queryset = []  # not actually hit by perform_* in unit tests
    serializer_class = None

    def get_object(self):
        # Return a snapshot of the "old" instance for diff testing.
        return self._old_instance


# ---------------------------------------------------------------------------
# 1. AuditMixin perform_* tests
# ---------------------------------------------------------------------------


class TestAuditMixinCreate:
    def test_perform_create_writes_audit_log(self):
        instance = _FakeInstance(pk=42, name="t1", status="pending")
        viewset = _DummyViewSet()
        viewset.request = APIRequestFactory().post("/tasks/", {"name": "t1"})
        viewset.request.user = User(username="alice")

        with patch("accounts.audit.log_audit") as mock_log:
            viewset.perform_create(_FakeSerializer(instance))

        mock_log.assert_called_once()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["action"] == AuditAction.CREATE
        assert kwargs["resource_type"] == AuditResourceType.TASK
        assert kwargs["resource_id"] == "42"
        assert kwargs["user"] == viewset.request.user

    def test_perform_create_skipped_when_audit_log_create_false(self):
        instance = _FakeInstance(pk=1, name="x", status="y")
        viewset = _DummyViewSet()
        viewset.audit_log_create = False
        viewset.request = APIRequestFactory().post("/tasks/", {})
        viewset.request.user = User(username="alice")

        with patch("accounts.audit.log_audit") as mock_log:
            viewset.perform_create(_FakeSerializer(instance))

        mock_log.assert_not_called()


class TestAuditMixinUpdate:
    def test_perform_update_writes_audit_log_with_old_instance(self):
        old_instance = _FakeInstance(pk=7, name="old", status="pending")
        new_instance = _FakeInstance(pk=7, name="new", status="running")
        viewset = _DummyViewSet()
        viewset._old_instance = old_instance
        viewset.request = APIRequestFactory().patch("/tasks/7/", {"name": "new"})
        viewset.request.user = User(username="bob")

        with patch("accounts.audit.log_audit") as mock_log:
            viewset.perform_update(_FakeSerializer(new_instance))

        mock_log.assert_called_once()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["action"] == AuditAction.UPDATE
        assert kwargs["resource_id"] == "7"

    def test_perform_update_skipped_when_audit_log_update_false(self):
        viewset = _DummyViewSet()
        viewset.audit_log_update = False
        viewset._old_instance = _FakeInstance(pk=1, name="x", status="y")
        viewset.request = APIRequestFactory().patch("/tasks/1/", {})
        viewset.request.user = User(username="alice")

        with patch("accounts.audit.log_audit") as mock_log:
            viewset.perform_update(_FakeSerializer(_FakeInstance(pk=1, name="x", status="y")))

        mock_log.assert_not_called()


class TestAuditMixinDestroy:
    def test_perform_destroy_writes_audit_log(self):
        instance = _FakeInstance(pk=99, name="x", status="y")
        viewset = _DummyViewSet()
        viewset.request = APIRequestFactory().delete("/tasks/99/")
        viewset.request.user = User(username="alice")

        # Replace super().perform_destroy with a no-op so we don't need a
        # real queryset.
        with (
            patch.object(viewsets.ModelViewSet, "perform_destroy", lambda self, inst: None),
            patch("accounts.audit.log_audit") as mock_log,
        ):
                viewset.perform_destroy(instance)

        mock_log.assert_called_once()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["action"] == AuditAction.DELETE
        assert kwargs["resource_id"] == "99"

    def test_perform_destroy_skipped_when_audit_log_destroy_false(self):
        instance = _FakeInstance(pk=99, name="x", status="y")
        viewset = _DummyViewSet()
        viewset.audit_log_destroy = False
        viewset.request = APIRequestFactory().delete("/tasks/99/")
        viewset.request.user = User(username="alice")

        with (
            patch.object(viewsets.ModelViewSet, "perform_destroy", lambda self, inst: None),
            patch("accounts.audit.log_audit") as mock_log,
        ):
                viewset.perform_destroy(instance)

        mock_log.assert_not_called()


# ---------------------------------------------------------------------------
# 2. AuditMixin fallback + hook tests
# ---------------------------------------------------------------------------


class TestAuditMixinFallbackAndHook:
    def test_resource_type_fallbacks_to_model_name(self):
        # ViewSet without audit_resource_type → use instance._meta.model_name
        class _NoTypeViewSet(AuditMixin, viewsets.ModelViewSet):
            queryset = []
            serializer_class = None

        instance = _FakeInstance(pk=1, name="x", status="y")
        viewset = _NoTypeViewSet()
        viewset.request = APIRequestFactory().post("/", {})
        viewset.request.user = User(username="alice")

        with patch("accounts.audit.log_audit") as mock_log:
            viewset.perform_create(_FakeSerializer(instance))

        kwargs = mock_log.call_args.kwargs
        assert kwargs["resource_type"] == "fake"  # _FakeInstance._meta.model_name

    def test_build_audit_details_hook_called_with_correct_args(self):
        captured = {}

        class _HookedViewSet(_DummyViewSet):
            audit_resource_type = AuditResourceType.TASK

            def _build_audit_details(self, action, instance, *, old_instance=None):
                captured["action"] = action
                captured["instance"] = instance
                captured["old_instance"] = old_instance
                return {"custom": "payload"}

        old = _FakeInstance(pk=1, name="old", status="x")
        new = _FakeInstance(pk=1, name="new", status="y")
        viewset = _HookedViewSet()
        viewset._old_instance = old
        viewset.request = APIRequestFactory().patch("/tasks/1/", {})
        viewset.request.user = User(username="alice")

        with patch("accounts.audit.log_audit") as mock_log:
            viewset.perform_update(_FakeSerializer(new))

        assert captured["action"] == AuditAction.UPDATE
        assert captured["instance"] is new
        assert captured["old_instance"] is old
        assert mock_log.call_args.kwargs["details"] == {"custom": "payload"}


# ---------------------------------------------------------------------------
# 3. @audit_action decorator tests
# ---------------------------------------------------------------------------


class _ActionHolder(AuditMixin, viewsets.ModelViewSet):
    """ViewSet carrying an @action decorated with @audit_action."""

    queryset = []
    serializer_class = None

    @action(detail=True, methods=["post"])
    @audit_action(AuditAction.EXECUTE, AuditResourceType.TASK)
    def execute(self, request, pk=None):
        return {"id": pk, "executed": True}


class TestAuditActionDecorator:
    def test_audit_action_writes_log_on_success(self):
        viewset = _ActionHolder()
        request = APIRequestFactory().post("/tasks/42/execute/", {})
        request.user = User(username="alice")

        with patch("accounts.audit.log_audit") as mock_log:
            response = viewset.execute(request, pk="42")

        assert response == {"id": "42", "executed": True}
        mock_log.assert_called_once()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["action"] == AuditAction.EXECUTE
        assert kwargs["resource_type"] == AuditResourceType.TASK
        assert kwargs["resource_id"] == "42"
        assert kwargs["details"]["endpoint"].endswith("/tasks/42/execute/")
        assert kwargs["details"]["method"] == "POST"
        assert kwargs["details"]["kwargs"] == {"pk": "42"}

    def test_audit_action_no_log_on_exception(self):
        class _FailingHolder(AuditMixin, viewsets.ModelViewSet):
            queryset = []
            serializer_class = None

            @action(detail=True, methods=["post"])
            @audit_action(AuditAction.EXECUTE, AuditResourceType.TASK)
            def execute(self, request, pk=None):
                raise ValueError("boom")

        viewset = _FailingHolder()
        request = APIRequestFactory().post("/tasks/1/execute/", {})
        request.user = User(username="alice")

        with patch("accounts.audit.log_audit") as mock_log, pytest.raises(ValueError, match="boom"):
            viewset.execute(request, pk="1")

        mock_log.assert_not_called()

    def test_audit_action_with_empty_resource_id_kw(self):
        class _BulkHolder(AuditMixin, viewsets.ModelViewSet):
            queryset = []
            serializer_class = None

            @action(detail=False, methods=["post"])
            @audit_action(AuditAction.EXECUTE, AuditResourceType.TASK, resource_id_kw="")
            def bulk_action(self, request):
                return {"ok": True}

        viewset = _BulkHolder()
        request = APIRequestFactory().post("/tasks/bulk-action/", {})
        request.user = User(username="alice")

        with patch("accounts.audit.log_audit") as mock_log:
            response = viewset.bulk_action(request)

        assert response == {"ok": True}
        assert mock_log.call_args.kwargs["resource_id"] == ""


# ---------------------------------------------------------------------------
# 4. build_diff_details helper
# ---------------------------------------------------------------------------


class TestBuildDiffDetails:
    def test_both_before_and_after(self):
        result = build_diff_details(
            before={"name": "old", "status": "pending"},
            after={"name": "new", "status": "running"},
        )
        assert result == {
            "before": {"name": "old", "status": "pending"},
            "after": {"name": "new", "status": "running"},
        }

    def test_only_after_for_create(self):
        result = build_diff_details(before=None, after={"name": "new"})
        assert result == {"after": {"name": "new"}}

    def test_only_before_for_delete(self):
        result = build_diff_details(before={"id": 1}, after=None)
        assert result == {"before": {"id": 1}}

    def test_both_none_returns_empty(self):
        result = build_diff_details(before=None, after=None)
        assert result == {}

    def test_sensitive_fields_redacted(self):
        result = build_diff_details(
            before={"password": "secret", "name": "old"},
            after={"password": "new_secret", "name": "new"},
        )
        assert result["before"]["password"] == "<redacted>"
        assert result["after"]["password"] == "<redacted>"
        assert result["before"]["name"] == "old"
        assert result["after"]["name"] == "new"

    def test_extra_sensitive_fields(self):
        result = build_diff_details(
            before={"my_custom_secret": "x", "name": "old"},
            after=None,
            sensitive_extra={"my_custom_secret"},
        )
        assert result["before"]["my_custom_secret"] == "<redacted>"


# ---------------------------------------------------------------------------
# 5. get_client_ip tests
# ---------------------------------------------------------------------------


class TestGetClientIp:
    def test_x_forwarded_for_first_ip(self):
        request = MagicMock()
        request.META = {"HTTP_X_FORWARDED_FOR": "1.2.3.4, 10.0.0.1, 192.168.1.1"}
        assert get_client_ip(request) == "1.2.3.4"

    def test_remote_addr_fallback(self):
        request = MagicMock()
        request.META = {"REMOTE_ADDR": "192.168.1.100"}
        assert get_client_ip(request) == "192.168.1.100"

    def test_returns_none_when_nothing_set(self):
        request = MagicMock()
        request.META = {}
        assert get_client_ip(request) is None

    def test_truncates_long_ipv6(self):
        # Construct an overly-long string to verify the 39-char cap.
        long_ip = "x" * 100
        request = MagicMock()
        request.META = {"HTTP_X_FORWARDED_FOR": long_ip}
        result = get_client_ip(request)
        assert len(result) == 39

    def test_handles_missing_meta_attribute(self):
        # Some test request objects may not have META at all.
        request = object()
        assert get_client_ip(request) is None


# ---------------------------------------------------------------------------
# 6. filter_sensitive_fields tests
# ---------------------------------------------------------------------------


class TestFilterSensitiveFields:
    def test_redacts_known_sensitive_fields(self):
        for name in ("password", "Password", "PASSWORD", "api_key", "API_KEY", "token"):
            result = filter_sensitive_fields({name: "secret_value", "name": "alice"})
            assert result[name] == "<redacted>", f"failed for {name}"
            assert result["name"] == "alice"

    def test_returns_empty_for_none_input(self):
        assert filter_sensitive_fields(None) == {}

    def test_returns_empty_for_empty_input(self):
        assert filter_sensitive_fields({}) == {}

    def test_extra_sensitive_set_merged_with_default(self):
        result = filter_sensitive_fields(
            {"custom_secret": "x", "name": "alice"},
            extra_sensitive={"custom_secret"},
        )
        assert result["custom_secret"] == "<redacted>"
        assert result["name"] == "alice"

    def test_default_deny_list_covers_common_secrets(self):
        # Spot-check: every entry in SENSITIVE_FIELD_NAMES must be redacted.
        for name in SENSITIVE_FIELD_NAMES:
            result = filter_sensitive_fields({name: "leak"})
            assert result[name] == "<redacted>", f"failed for {name}"


# ---------------------------------------------------------------------------
# 7. AuditResourceType sanity tests
# ---------------------------------------------------------------------------


class TestAuditResourceType:
    def test_all_values_returns_lowercase_slugs_only(self):
        values = AuditResourceType.all_values()
        assert len(values) >= 30, f"expected 30+ resource types, got {len(values)}"
        for v in values:
            assert v.islower(), f"{v!r} is not lowercase"
            assert "_" in v or v.isalpha(), f"{v!r} is not a valid slug"

    def test_known_frontend_keys_present(self):
        # The 8 keys the frontend AuditLogPage already has i18n labels for
        # must all be present so Phase 1 doesn't break the existing UI.
        for attr in (
            "USER", "TASK", "DEVICE", "RESOURCE_PACK",
            "API_KEY", "FEATURE_FLAG", "GAME_ACCOUNT", "GAME_PROFILE",
        ):
            assert hasattr(AuditResourceType, attr), f"missing {attr}"

    def test_no_duplicate_values(self):
        # all_values() returns a set, so duplicates are auto-deduped; but
        # the source attributes might still have collisions. Verify by
        # counting via vars().
        all_attrs = [
            v for k, v in vars(AuditResourceType).items()
            if not k.startswith("_") and isinstance(v, str) and v.islower()
        ]
        assert len(all_attrs) == len(set(all_attrs)), "duplicate resource_type values"


# ---------------------------------------------------------------------------
# 8. Integration: log_audit actually writes a row to AuditLog
# ---------------------------------------------------------------------------


class TestLogAuditIntegration:
    """End-to-end: AuditMixin calls log_audit which writes a real AuditLog row."""

    def test_audit_log_row_created(self, db):
        user = User.objects.create_user(username="audit_user", password="x")
        instance = _FakeInstance(pk=1, name="t", status="s")
        viewset = _DummyViewSet()
        viewset.request = APIRequestFactory().post("/tasks/", {})
        viewset.request.user = user

        # Don't patch log_audit — let it actually write to the test DB.
        viewset.perform_create(_FakeSerializer(instance))

        log = AuditLog.objects.filter(action=AuditAction.CREATE, resource_type=AuditResourceType.TASK).first()
        assert log is not None
        assert log.user == user
        assert log.resource_id == "1"
        # APIRequestFactory defaults REMOTE_ADDR to "127.0.0.1"; get_client_ip
        # should return that value (not None).
        assert log.ip_address == "127.0.0.1"
