"""plugins test package.

Disables login throttle (TD-068 pattern) so integration tests that hit
/api/v2/accounts/auth/login/ do not produce HTTP 429 responses.
"""

from accounts.views import CustomTokenObtainPairView

CustomTokenObtainPairView.throttle_classes = []
