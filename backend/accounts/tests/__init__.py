"""accounts test package.

TD-068 fix: disable DRF throttling for the accounts test suite.

The accounts test suite hits ``/api/v2/accounts/auth/login/`` ~19 times
per pytest/``manage.py test`` run (5 in ``test_jwt_refresh.py`` + 14 in
``test_user_session.py``). DRF's login scoped throttle is ``5/min``
(see ``config/settings/base.py`` ``DEFAULT_THROTTLE_RATES['login']``),
which produces 19 ``HTTP 429`` failures once the limit is exceeded.

Two mechanisms handle this depending on the runner:

- **pytest**: the autouse fixture ``disable_throttling`` in
  ``accounts/tests/conftest.py`` clears ``CustomTokenObtainPairView.
  throttle_classes`` via ``monkeypatch.setattr`` with automatic
  restoration after each test (TD-336 #7: fixture-level patch, no
  global side effect). This module intentionally skips the global
  mutation so the restoration lands on the original
  ``[ScopedRateThrottle]`` value.

- **``manage.py test``** (Django's built-in runner, no pytest): the
  global fallback below runs at package import time and clears
  ``throttle_classes`` for the whole process. The anon/user global
  throttles (60/min, 300/min) are high enough for ~30 login calls in
  a single run, so they do not need to be disabled. The patch is
  intentionally not restored: ``manage.py test`` runs in a throwaway
  process that never affects production code.
"""

import sys

# TD-336 #7: skip the global mutation under pytest so conftest.py's
# monkeypatch.setattr can restore the original ``[ScopedRateThrottle]``
# value after each test. Only the ``manage.py test`` runner (no pytest
# in sys.modules) needs this import-time fallback.
if 'pytest' not in sys.modules:
    from accounts.views import CustomTokenObtainPairView

    # CustomTokenObtainPairView sets ``throttle_classes = [ScopedRateThrottle]``
    # and ``throttle_scope = 'login'`` directly on the class, bypassing the
    # ``DEFAULT_THROTTLE_CLASSES`` setting override. Clear the attribute so
    # DRF skips the throttle check for the login view entirely during tests.
    CustomTokenObtainPairView.throttle_classes = []
