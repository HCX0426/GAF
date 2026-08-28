"""Shared constants and helpers for audit logging (spec34, TD-259 #11).

This module centralizes:

1. ``AuditResourceType`` — the canonical ``resource_type`` strings written
   to ``accounts.AuditLog.resource_type``. The vocabulary is locked to the
   keys used by ``frontend/src/pages/System/AuditLogPage.tsx``'s
   ``RESOURCE_TYPE_LABEL_KEYS`` so the i18n layer can render every backend
   value without falling back to the raw slug.

2. ``AuditAction`` — re-export of ``accounts.AuditLog.Action`` choices so
   callers can import action constants without reaching into the model
   (avoids a circular import with ``accounts.models``).

3. ``get_client_ip`` — single source of truth for client-IP extraction,
   honoring ``X-Forwarded-For`` for reverse-proxy deployments.

4. ``SENSITIVE_FIELD_NAMES`` — deny-list used by ``AuditMixin`` when
   building ``details`` JSON payloads. Fields matching these names
   (case-insensitive) are never written to ``AuditLog.details``.

Why a separate module (not inside ``mixins/audit.py``)
------------------------------------------------------
``AuditMixin`` lives in ``gaf_core/mixins/audit.py`` and pulls in DRF
``viewsets`` / ``mixins`` machinery — heavy import. ``audit_constants.py``
is intentionally light (pure data + 1 helper function) so it can be
imported from anywhere (including tests and templates) without dragging
DRF into the import graph.
"""
from __future__ import annotations

from typing import Any

from accounts.models import AuditLog

# Re-export AuditLog.Action choices for callers that want typed constants
# without importing the full model (e.g. audit_action decorator usage).
AuditAction = AuditLog.Action


class AuditResourceType:
    """Canonical ``resource_type`` strings written to ``AuditLog``.

    Frontend ``AuditLogPage.tsx`` renders these via i18n keys
    ``auditLog.resource_<value>``. Any new value added here MUST be
    accompanied by a corresponding i18n key in
    ``frontend/src/locales/*/auditLog.json`` (enforced by Phase 4
    meta-test).
    """

    # --- Frontend-existing 8 (Phase 1 must cover) ---
    USER = "user"
    TASK = "task"
    DEVICE = "device"
    RESOURCE_PACK = "resource_pack"
    API_KEY = "api_key"
    FEATURE_FLAG = "feature_flag"
    GAME_ACCOUNT = "game_account"
    GAME_PROFILE = "game_profile"

    # --- Phase 2-3 additions (frontend i18n extended in Phase 4) ---
    AGENT = "agent"
    AGENT_TOKEN = "agent_token"
    PIPELINE = "pipeline"
    SCHEDULED_TASK = "scheduled_task"
    TASK_CHAIN = "task_chain"
    TASK_FOLDER = "task_folder"
    CUSTOM_TASK = "custom_task"
    RECORDING = "recording"
    TEMPLATE_VERSION = "template_version"
    TEMPLATE_ANNOTATION = "template_annotation"
    TAG = "tag"
    PLUGIN = "plugin"
    TIME_WINDOW = "time_window"
    NOTIFICATION = "notification"
    WEBHOOK_CONFIG = "webhook_config"
    ALERT_RULE = "alert_rule"
    MONITOR_RULE = "monitor_rule"
    AGENT_SESSION = "agent_session"
    QA_SESSION = "qa_session"
    QA_MESSAGE = "qa_message"
    CRASH_REPORT = "crash_report"
    DEBUG_LOG_ARCHIVE = "debug_log_archive"
    GAME_STATE_RULE = "game_state_rule"
    TASK_EXECUTION = "task_execution"
    USER_SESSION = "user_session"
    GAME_ACCOUNT_GROUP = "game_account_group"
    ROTATION_RULE = "rotation_rule"
    LLM_CONFIG = "llm_config"
    APP_SETTINGS = "app_settings"
    UNATTENDED_STRATEGY = "unattended_strategy"
    DEVICE_GROUP = "device_group"
    MARKETPLACE = "marketplace"

    @classmethod
    def all_values(cls) -> set[str]:
        """Return every valid ``resource_type`` string (for meta-test assertions)."""
        return {
            value
            for name, value in vars(cls).items()
            if not name.startswith("_")
            and isinstance(value, str)
            and value.islower()
            and not value.startswith("_")
        }


# Field names that must NEVER appear in ``AuditLog.details``.
# Match is case-insensitive on the field name (not the value).
SENSITIVE_FIELD_NAMES: frozenset[str] = frozenset({
    "password",
    "password1",
    "password2",
    "password_hash",
    "old_password",
    "new_password",
    "secret",
    "client_secret",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "totp_secret",
    "totp_code",
    "private_key",
    "credential",
    "credentials",
    "authorization",
    "cookie",
    "session_key",
})


def get_client_ip(request: Any) -> str | None:
    """Extract the client IP from a Django request.

    Honors ``X-Forwarded-For`` (first IP in the chain) when present so
    deployments behind nginx/Cloudflare still record the real client IP.
    Falls back to ``REMOTE_ADDR``. Returns ``None`` when neither is set
    (e.g. in some test environments).

    The function accepts any object with a ``META`` dict-like attribute
    so it works with both DRF ``Request`` and plain Django ``HttpRequest``.
    """
    meta = getattr(request, "META", None) or {}
    xff = meta.get("HTTP_X_FORWARDED_FOR")
    if xff:
        # First IP in the comma-separated list is the original client.
        # Truncate to 39 chars (IPv6 max) to satisfy GenericIPAddressField.
        first = xff.split(",")[0].strip()
        return first[:39] if first else None
    remote = meta.get("REMOTE_ADDR")
    if remote:
        return remote[:39]
    return None


def filter_sensitive_fields(data: dict | None, extra_sensitive: set[str] | None = None) -> dict:
    """Return a copy of ``data`` with sensitive fields stripped.

    Field names are matched case-insensitively against
    ``SENSITIVE_FIELD_NAMES`` (plus any caller-supplied extras).
    Values for sensitive keys are replaced with the literal ``"<redacted>"``
    so auditors can see that the field existed (vs. absent) without
    leaking the value.
    """
    if not data:
        return {}
    denied = set(SENSITIVE_FIELD_NAMES)
    if extra_sensitive:
        denied |= {n.lower() for n in extra_sensitive}
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(key, str) and key.lower() in denied:
            cleaned[key] = "<redacted>"
        else:
            cleaned[key] = value
    return cleaned
