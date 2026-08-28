# Disable login throttle for integration tests that hit the login endpoint.
from accounts.views import CustomTokenObtainPairView

CustomTokenObtainPairView.throttle_classes = []
