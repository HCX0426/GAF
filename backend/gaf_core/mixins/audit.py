"""AuditMixin + @audit_action decorator (spec34, TD-259 #11).

Why this module exists
----------------------
``accounts.audit.log_audit`` is the canonical writer for
``accounts.AuditLog`` rows, but as of 2026-07-19 it has 0 callers — every
sensitive ViewSet (User/Task/Device/Plugin/...) writes to the DB without
producing any audit trail.

This module provides a DRY pattern for wiring audit logging into DRF
ViewSets:

* ``AuditMixin`` — inherit on a ``ModelViewSet`` to auto-call ``log_audit``
  from ``perform_create`` / ``perform_update`` / ``perform_destroy``.
  Configure via class attributes (``audit_resource_type``, ``audit_log_create``,
  ``audit_log_update``, ``audit_log_destroy``, ``audit_resource_id_attr``).

* ``@audit_action(action, resource_type)`` — decorator for ``@action``-decorated
  custom endpoints (e.g. ``execute``, ``cancel``, ``toggle``, ``batch_import``).
  Applied INSIDE ``@action`` (closest to the function) so DRF's action
  discovery still works.

* ``build_diff_details(before, after, sensitive_extra)`` — helper for
  constructing ``details`` payloads with sensible ``before``/``after`` diff
  shape and automatic sensitive-field redaction.

Why not middleware (Approach C rejected)
----------------------------------------
A middleware approach would auto-capture every write, but: (1) GET-
semantic POSTs (search/validate/estimate) get mis-classified as writes,
(2) URL→resource_type inference is fragile for nested routes, (3)
``details`` JSON would be empty (no serializer-validated data), (4)
``AuditLog`` writes would recurse if the middleware logs its own writes.

Why not pure manual calls (Approach A rejected)
-----------------------------------------------
~40 ViewSets × ~3 methods + 25 @action endpoints = ~120 manual call
sites — high boilerplate, easy to forget on new ViewSets, inconsistent
``resource_type`` strings across developers.

Approach B (this module) balances DRY with explicit control: ViewSets
opt in via inheritance, ``@action`` methods opt in via decorator, and
``details`` payload is hookable per-ViewSet via ``_build_audit_details``.
"""
from __future__ import annotations

from functools import wraps
from typing import Any

from gaf_core.audit_constants import (
    AuditAction,
    AuditResourceType,
    filter_sensitive_fields,
    get_client_ip,
)

# `log_audit` is imported lazily inside `_log_audit` / `audit_action` to
# avoid a circular import: accounts.audit imports accounts.models, and
# accounts.models is loaded very early in Django startup. gaf_core must
# remain a leaf dependency that other apps can import without triggering
# accounts model loading.


class AuditMixin:
    """DRF mixin: auto-call ``log_audit`` on create/update/destroy.

    Subclass configuration
    ----------------------
    * ``audit_resource_type`` — canonical ``resource_type`` string (use
      ``AuditResourceType`` constant). Falls back to
      ``instance._meta.model_name`` if not set.
    * ``audit_resource_id_attr`` — instance attribute used as
      ``resource_id`` (default ``"pk"``).
    * ``audit_log_create`` / ``audit_log_update`` / ``audit_log_destroy``
      — set to ``False`` to skip audit logging for a specific action
      (e.g. read-only ``ReadOnlyModelViewSet`` subclasses don't need
      these set, but ViewSets that create "noisy" records like
      ``CrashReport`` may want ``audit_log_create = False``).

    Hooks
    -----
    * ``_build_audit_details(action, instance, old_instance=None)`` —
      override to populate ``AuditLog.details`` JSON. Default: empty dict.
      Use ``build_diff_details`` helper for typical update-diff shape.

    Example
    -------
        from gaf_core.mixins import AuditMixin
        from gaf_core.audit_constants import AuditResourceType

        class TaskViewSet(AuditMixin, viewsets.ModelViewSet):
            queryset = Task.objects.all()
            serializer_class = TaskSerializer
            audit_resource_type = AuditResourceType.TASK

            def _build_audit_details(self, action, instance, *, old_instance=None):
                if action == "update" and old_instance is not None:
                    return build_diff_details(
                        before={"name": old_instance.name, "status": old_instance.status},
                        after={"name": instance.name, "status": instance.status},
                    )
                return {}
    """

    audit_resource_type: str | None = None
    audit_resource_id_attr: str = "pk"
    audit_log_create: bool = True
    audit_log_update: bool = True
    audit_log_destroy: bool = True

    def perform_create(self, serializer):
        super().perform_create(serializer)
        if self.audit_log_create:
            self._log_audit(AuditAction.CREATE, serializer.instance)

    def perform_update(self, serializer):
        old_instance = None
        if self.audit_log_update:
            try:
                old_instance = self.get_object()
            except Exception:
                old_instance = None
        super().perform_update(serializer)
        if self.audit_log_update:
            self._log_audit(AuditAction.UPDATE, serializer.instance, old_instance=old_instance)

    def perform_destroy(self, instance):
        if self.audit_log_destroy:
            self._log_audit(AuditAction.DELETE, instance)
        super().perform_destroy(instance)

    def _log_audit(self, action: str, instance: Any, *, old_instance: Any = None) -> None:
        """Call ``accounts.audit.log_audit`` with non-blocking semantics."""
        # Lazy import to avoid circular dependency at module load time.
        from accounts.audit import log_audit

        resource_type = self.audit_resource_type
        if not resource_type:
            meta = getattr(instance, "_meta", None)
            resource_type = getattr(meta, "model_name", "unknown")

        resource_id = ""
        id_attr = self.audit_resource_id_attr
        if id_attr:
            resource_id = str(getattr(instance, id_attr, "") or "")

        log_audit(
            user=getattr(self.request, "user", None),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=self._build_audit_details(action, instance, old_instance=old_instance),
            ip_address=get_client_ip(self.request),
        )

    def _build_audit_details(self, action: str, instance: Any, *, old_instance: Any = None) -> dict:
        """Override per ViewSet for custom details payload. Default: empty."""
        return {}


def audit_action(action: str, resource_type: str, resource_id_kw: str = "pk"):
    """Decorator for ``@action`` methods: wraps to call ``log_audit`` after success.

    Must be applied INSIDE ``@action`` (closest to the function) so DRF's
    action discovery still recognizes the method:

        @action(detail=True, methods=["post"])
        @audit_action("execute", "task")
        def execute(self, request, pk=None):
            ...

    Parameters
    ----------
    action : str
        One of ``AuditAction`` constants (e.g. ``AuditAction.EXECUTE``).
    resource_type : str
        One of ``AuditResourceType`` constants.
    resource_id_kw : str
        URL kwarg used as ``resource_id`` (default ``"pk"``). For
        endpoints without a pk in the URL (e.g. ``/tasks/bulk-action/``),
        pass ``""`` and ``resource_id`` will be empty.

    Failure mode
    ------------
    ``log_audit`` is non-blocking (try/except inside the helper), so even
    if audit logging fails, the wrapped ``@action`` still returns its
    original response. The wrapper itself only fails if the wrapped view
    fails — and in that case no audit log is written (intentional: only
    successful writes are audited).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            response = func(self, request, *args, **kwargs)
            # Lazy import (same reason as AuditMixin._log_audit).
            from accounts.audit import log_audit

            resource_id = ""
            if resource_id_kw:
                value = kwargs.get(resource_id_kw, "")
                resource_id = str(value) if value is not None else ""

            log_audit(
                user=getattr(request, "user", None),
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details={
                    "endpoint": request.path,
                    "method": request.method,
                    "kwargs": {k: str(v) for k, v in kwargs.items()} if kwargs else {},
                },
                ip_address=get_client_ip(request),
            )
            return response

        return wrapper

    return decorator


def build_diff_details(
    before: dict | None,
    after: dict | None,
    sensitive_extra: set[str] | None = None,
) -> dict:
    """Construct a ``details`` payload with ``before``/``after`` diff shape.

    Used by ``AuditMixin._build_audit_details`` overrides for UPDATE
    actions. Sensitive fields (password/token/api_key/...) are
    automatically redacted via
    ``gaf_core.audit_constants.filter_sensitive_fields``.

    The returned dict is shaped as::

        {
            "before": {"name": "old", "status": "pending"},
            "after":  {"name": "new", "status": "running"},
        }

    For CREATE actions where there is no ``before``, call with
    ``before=None`` — the result will contain only the ``after`` key.

    For DELETE actions, call with ``after=None`` — the result will
    contain only the ``before`` key.
    """
    payload: dict[str, Any] = {}
    if before is not None:
        payload["before"] = filter_sensitive_fields(before, sensitive_extra)
    if after is not None:
        payload["after"] = filter_sensitive_fields(after, sensitive_extra)
    return payload


__all__ = [
    "AuditMixin",
    "audit_action",
    "build_diff_details",
    # Re-exports for convenience (callers can import everything from
    # gaf_core.mixins.audit without also reaching into audit_constants):
    "AuditAction",
    "AuditResourceType",
    "get_client_ip",
    "filter_sensitive_fields",
]
