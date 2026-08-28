"""QA URL routes (migrated from qa app — 2026-08-04)."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from gaf_ai.qa_views import (
    AskView,
    LLMUsageLogViewSet,
    QAMessageViewSet,
    QASessionViewSet,
)

router = DefaultRouter()
router.register(r'qa-sessions', QASessionViewSet, basename='qa-session')
router.register(r'messages', QAMessageViewSet, basename='qa-message')
router.register(r'llm-usage-logs', LLMUsageLogViewSet, basename='llm-usage-log')

urlpatterns = [
    path('', include(router.urls)),
    path('ask/', AskView.as_view(), name='qa-ask'),
]
