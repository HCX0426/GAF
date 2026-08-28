"""URL configuration for the core app.

Mounted at ``/api/v2/logs/`` in ``config/urls.py``. Provides:
- ``GET /api/v2/logs/`` — list log entries (with filters)
- ``GET /api/v2/logs/<id>/`` — retrieve a single log entry
- ``GET /api/v2/logs/timeline/`` — unified UNION timeline across 6 log models
- ``POST /api/v2/logs/frontend-errors/`` — receive browser-side crash reports
  (anonymous; logged to ``gaf_core.frontend_error`` for AI debugging)
"""
from django.urls import path

from gaf_core.views import FrontendErrorReportView, LogEntryViewSet, UnifiedLogTimelineView

log_entry_list = LogEntryViewSet.as_view({'get': 'list'})
log_entry_detail = LogEntryViewSet.as_view({'get': 'retrieve'})

urlpatterns = [
    path('', log_entry_list, name='log-entry-list'),
    path('<int:pk>/', log_entry_detail, name='log-entry-detail'),
    path('timeline/', UnifiedLogTimelineView.as_view(), name='log-timeline'),
    # P0-10 (AI 可调试性, 2026-07-27): frontend crash report endpoint.
    # Placed BEFORE '<int:pk>/' patterns are matched — 'frontend-errors/'
    # is a string path segment, not an int, so it doesn't collide, but
    # explicit ordering makes intent clear.
    path('frontend-errors/', FrontendErrorReportView.as_view(), name='frontend-error-report'),
]
