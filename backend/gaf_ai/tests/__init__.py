"""gaf_ai test package.

TD-068 pattern: disable the login-scoped DRF throttle for ``manage.py
test`` runs (Django's built-in runner, no pytest). Under pytest the
autouse ``disable_throttling`` fixture in ``conftest.py`` handles it
with restoration (TD-336 #7).
"""

import sys

if 'pytest' not in sys.modules:
    from accounts.views import CustomTokenObtainPairView

    CustomTokenObtainPairView.throttle_classes = []
