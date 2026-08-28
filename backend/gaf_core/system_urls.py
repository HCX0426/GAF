"""URL configuration for system-level endpoints.

Mounted at ``/api/v2/system/`` in ``config/urls.py``. Provides:
- ``GET /api/v2/system/perf/`` — PerformanceMonitor aggregated statistics
"""
from django.urls import path

from gaf_core.views import HealthzView, PerfAPIView

urlpatterns = [
    path('healthz/', HealthzView.as_view(), name='system-healthz'),
    path('perf/', PerfAPIView.as_view(), name='system-perf'),
]
