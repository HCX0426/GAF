"""Meta-test: AuditResourceType vocabulary must match frontend i18n keys.

spec34 Phase 4 hard-constraint: every value in
``gaf_core.audit_constants.AuditResourceType`` MUST have a corresponding
``auditLog.resource_<value>`` key in
``frontend/src/i18n/locales/auditLog.ts`` for every supported locale
(zh-CN / en-US / ja-JP / ko-KR). Adding a backend resource_type without
the i18n key would render as a raw slug in the UI.

Conversely, every i18n ``auditLog.resource_*`` key should map to a real
backend value (no orphan keys).
"""
from __future__ import annotations

import re
from pathlib import Path

from gaf_core.audit_constants import AuditResourceType

# Repository root = backend/gaf_core/tests/test_audit_i18n_meta.py
# parents[0] = tests, parents[1] = gaf_core, parents[2] = backend, parents[3] = root
REPO_ROOT = Path(__file__).resolve().parents[3]
I18N_FILE = REPO_ROOT / "frontend" / "src" / "i18n" / "locales" / "auditLog.ts"

EXPECTED_LOCALES = {"zh-CN", "en-US", "ja-JP", "ko-KR"}

# Matches: 'auditLog.resource_xxx': 'some text',
_RESOURCE_KEY_RE = re.compile(r"'(auditLog\.resource_[a-z_]+)':\s*'[^']*'", re.MULTILINE)
# Matches the leading '<locale>': {  block opener (e.g. "  'zh-CN': {")
_LOCALE_BLOCK_RE = re.compile(r"'(zh-CN|en-US|ja-JP|ko-KR)':\s*\{")


def _parse_i18n_keys_by_locale(text: str) -> dict[str, set[str]]:
    """Return {locale -> {resource_key, ...}} parsed from auditLog.ts source."""
    # Split source into locale blocks. Each block starts at "'<locale>': {"
    # and ends at the next "  }," (the closing brace of that locale's dict).
    locales: dict[str, set[str]] = {}
    matches = list(_LOCALE_BLOCK_RE.finditer(text))
    for i, m in enumerate(matches):
        locale = m.group(1)
        start = m.end()
        end = len(text)
        # Find the next locale block start; current block ends there.
        if i + 1 < len(matches):
            end = matches[i + 1].start()
        block = text[start:end]
        keys = set(_RESOURCE_KEY_RE.findall(block))
        locales[locale] = keys
    return locales


class TestAuditResourceTypeI18nCoverage:
    """Verify AuditResourceType <-> auditLog.ts i18n keys stay in sync."""

    def test_i18n_file_exists(self) -> None:
        assert I18N_FILE.is_file(), f"i18n file missing: {I18N_FILE}"

    def test_all_backend_values_have_i18n_keys(self) -> None:
        backend_values = AuditResourceType.all_values()
        assert backend_values, "AuditResourceType has no values"
        text = I18N_FILE.read_text(encoding="utf-8")
        locales = _parse_i18n_keys_by_locale(text)
        assert set(locales) == EXPECTED_LOCALES, (
            f"locale block parse mismatch: got {set(locales)}, expected {EXPECTED_LOCALES}"
        )
        missing: dict[str, set[str]] = {}
        for locale, keys in locales.items():
            expected = {f"auditLog.resource_{v}" for v in backend_values}
            got_missing = expected - keys
            if got_missing:
                missing[locale] = got_missing
        assert not missing, (
            "Missing auditLog.resource_* i18n keys by locale "
            f"(every AuditResourceType value needs a key in every locale): {missing}"
        )

    def test_no_orphan_i18n_keys(self) -> None:
        """Every i18n auditLog.resource_* key must map to a backend value."""
        backend_values = AuditResourceType.all_values()
        expected_keys = {f"auditLog.resource_{v}" for v in backend_values}
        text = I18N_FILE.read_text(encoding="utf-8")
        locales = _parse_i18n_keys_by_locale(text)
        orphans: dict[str, set[str]] = {}
        for locale, keys in locales.items():
            extra = keys - expected_keys
            if extra:
                orphans[locale] = extra
        assert not orphans, (
            f"Orphan auditLog.resource_* keys (no backend value): {orphans}"
        )

    def test_backend_values_are_unique(self) -> None:
        """All AuditResourceType string values must be unique."""
        # all_values() returns a set, so uniqueness is structurally guaranteed.
        # Re-check by introspecting raw class attributes to catch a future
        # refactor that might break all_values().
        raw = [
            value
            for name, value in vars(AuditResourceType).items()
            if not name.startswith("_")
            and isinstance(value, str)
            and value.islower()
            and not value.startswith("_")
        ]
        assert len(raw) == len(set(raw)), (
            f"Duplicate AuditResourceType values detected: {raw}"
        )

    def test_all_locales_have_same_key_set(self) -> None:
        """Every locale must define the same set of auditLog.resource_* keys."""
        text = I18N_FILE.read_text(encoding="utf-8")
        locales = _parse_i18n_keys_by_locale(text)
        keys_per_locale = [frozenset(keys) for keys in locales.values()]
        first = keys_per_locale[0]
        for i, keys in enumerate(keys_per_locale):
            assert keys == first, (
                f"locale key set mismatch: locale[{i}] != locale[0]; "
                f"diff={keys.symmetric_difference(first)}"
            )
