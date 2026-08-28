"""
Analytics URL routes — views from executions app.

L1 fix: moved from config/urls.py to use the app include pattern.
URL paths remain /api/v2/analytics/* (unchanged for backward compatibility).
"""
from django.urls import path

from executions.views import (
    agent_performance_view,
    step_heatmap_view,
    task_stats_view,
    trend_view,
    weekly_report_view,
)

urlpatterns = [
    path('trend/', trend_view, name='analytics-trend'),
    path('step-heatmap/', step_heatmap_view, name='analytics-step-heatmap'),
    path('agent-performance/', agent_performance_view, name='analytics-agent-performance'),
    path('weekly-report/', weekly_report_view, name='analytics-weekly-report'),
    path('task-stats/', task_stats_view, name='analytics-task-stats'),
]
