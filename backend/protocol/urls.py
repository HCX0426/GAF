from django.urls import include, path
from rest_framework.routers import DefaultRouter

from protocol.views import AgentSessionViewSet, MessageFrameLogViewSet

router = DefaultRouter()
router.register(r'sessions', AgentSessionViewSet, basename='protocol-session')
router.register(r'messages', MessageFrameLogViewSet, basename='protocol-message')

urlpatterns = [
    path('', include(router.urls)),
]
