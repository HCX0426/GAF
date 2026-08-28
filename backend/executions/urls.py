"""
执行管理模块 - URL 路由配置
定义 Phase 9 所有执行相关 API 端点
"""
from django.urls import path

from .views import (
    daily_report_view,
    execution_analysis_view,
    execution_intervene_view,
    execution_steps_view,
    trend_view,
    unattended_logs_view,
)

app_name = 'executions'

urlpatterns = [
    path('<int:pk>/steps/', execution_steps_view, name='execution-steps'),
    path('<int:pk>/intervene/', execution_intervene_view, name='execution-intervene'),
    path('<int:pk>/analysis/', execution_analysis_view, name='execution-analysis'),
    path('daily-report/', daily_report_view, name='daily-report'),
    path('unattended-logs/', unattended_logs_view, name='unattended-logs'),
    path('trend/', trend_view, name='trend'),
]
