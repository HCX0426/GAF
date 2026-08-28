"""pytest fixtures for the accounts test suite (TD-068 fix, TD-336 #7).

Disables DRF throttling for the accounts test suite via two mechanisms:

1. ``monkeypatch.setattr`` on ``CustomTokenObtainPairView.throttle_classes``
   — clears the login-scoped ``ScopedRateThrottle`` (the 5/min bottleneck)
   with automatic restoration after each test (TD-336 #7: fixture-level
   patch instead of the global module-import mutation that used to live in
   ``accounts/tests/__init__.py``).

2. Raises ``DEFAULT_THROTTLE_RATES`` to effectively-unlimited values so any
   view inheriting the global default throttles (e.g. ``Login2FAView``)
   also bypasses the limit.

Note: this fixture only runs under pytest. When using ``manage.py test``
(Django's built-in runner), the fallback global patch in
``accounts/tests/__init__.py`` applies (sufficient because the global
anon/user rates are high enough for ~30 login calls in a single run).
"""

import pytest

from accounts.views import CustomTokenObtainPairView


@pytest.fixture(autouse=True)
def disable_throttling(settings, monkeypatch):
    """Disable DRF throttling for accounts tests (TD-068, TD-336 #7).

    - monkeypatch.setattr clears ``CustomTokenObtainPairView.throttle_classes``
      with automatic restoration (fixture-level patch, no global side effect).
    - settings.REST_FRAMEWORK raises anon/user/login rates to 999999/min.
    """
    # TD-336 #7: fixture-level patch with restoration. Replaces the global
    # module-import mutation previously in accounts/tests/__init__.py.
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
