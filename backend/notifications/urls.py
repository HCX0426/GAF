from django.urls import include, path
from rest_framework.routers import DefaultRouter

from notifications.views import AlertRuleViewSet, NotificationViewSet, WebhookConfigViewSet, preferences_view

router = DefaultRouter()
router.register(r'', NotificationViewSet, basename='notification')
router.register(r'webhooks', WebhookConfigViewSet, basename='webhook')
# R37-P3 Stage 7 Task 20a: migrated from tasks/alert-rules (TD-039).
# No shadowing risk with the empty-prefix NotificationViewSet above because
# its lookup_value_regex restricts detail routes to \d+ (numeric pk only).
router.register(r'alert-rules', AlertRuleViewSet, basename='alert-rule')

urlpatterns = [
    path('', include(router.urls)),
    path('preferences/', preferences_view, name='notification-preferences'),
]
