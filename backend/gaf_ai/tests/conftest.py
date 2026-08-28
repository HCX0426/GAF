"""pytest fixtures for the gaf_ai test suite (TD-068 pattern).

Disables DRF throttling for gaf_ai tests. The suite hits
``/api/v2/accounts/auth/login/`` once per test (via ``_login`` in
``test_qa_views.py``) and the login scoped throttle is ``5/min``
(``config/settings/base.py`` ``DEFAULT_THROTTLE_RATES['login']``).

Without this, running ``pytest backend/gaf_ai/tests/`` standalone
produces ``HTTP 429`` failures once the 5/min limit is exceeded
(S3 P6, 2026-08-16 — found while running the gaf_ai suite in
isolation; the full ``pytest backend/`` run masked it via
``backend/tests/__init__.py``'s global patch).

Same mechanism as ``accounts/tests/conftest.py`` (TD-336 #7:
fixture-level patch with automatic restoration).
"""

import pytest

from accounts.views import CustomTokenObtainPairView


@pytest.fixture(autouse=True)
def disable_throttling(settings, monkeypatch):
    """Disable DRF throttling for gaf_ai tests (TD-068 pattern)."""
    monkeypatch.setattr(CustomTokenObtainPairView, 'throttle_classes', [])

    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        'DEFAULT_THROTTLE_CLASSES': [],
        'DEFAULT_THROTTLE_RATES': {
            'anon': '999999/min',
            'user': '999999/min',
            'login': '999999/min',
        },
    }
    yield
