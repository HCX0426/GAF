from django.urls import include, path
from rest_framework.routers import DefaultRouter

from protocol.views import MessageFrameLogViewSet, WorkerSessionViewSet

router = DefaultRouter()
router.register(r'sessions', WorkerSessionViewSet, basename='protocol-session')
router.register(r'messages', MessageFrameLogViewSet, basename='protocol-message')

urlpatterns = [
    path('', include(router.urls)),
]
