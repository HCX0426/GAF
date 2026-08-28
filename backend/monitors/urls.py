from django.urls import include, path
from rest_framework.routers import DefaultRouter

from monitors.views import (
    MonitorEventViewSet,
    MonitorRuleViewSet,
    SLAMetricViewSet,
    alert_history_view,
    alerts_summary_view,
    auto_fix_view,
    device_health_view,
    diagnose_view,
    system_status_view,
)

router = DefaultRouter()
router.register(r'monitor-rules', MonitorRuleViewSet, basename='monitor-rule')
router.register(r'monitor-events', MonitorEventViewSet, basename='monitor-event')
router.register(r'sla', SLAMetricViewSet, basename='metric-sla')

urlpatterns = [
    path('', include(router.urls)),
    path('status/', system_status_view, name='system-status'),
    path('alerts/', alerts_summary_view, name='alerts-summary'),
    path('alerts/history/', alert_history_view, name='alert-history'),
    path('device-health/', device_health_view, name='device-health'),
    path('diagnose/', diagnose_view, name='diagnose'),
    path('fix/', auto_fix_view, name='auto-fix'),
]
