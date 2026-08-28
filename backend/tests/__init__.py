"""backend integration test package.

Applies the same TD-068 throttle-disable patch as accounts/tests/__init__.py
so that integration tests in this package (test_integration.py,
test_auth_flow.py) do not hit the 5/min login throttle when running the
full backend test suite. The patch is global and only applied during test
runs (this package is never imported in production).
"""

from accounts.views import CustomTokenObtainPairView

# Clear login-scoped throttle so ~30 login calls across the integration
# test suite do not produce HTTP 429 responses.
CustomTokenObtainPairView.throttle_classes = []
