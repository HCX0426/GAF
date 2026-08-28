"""
调度模块路由配置

包含时间窗口 CRUD、预热配置、执行计划、今日日程、自动停止条件等路由。
- views: RecoveryLog/TimeWindow ViewSets + 调度配置 FBVs (spec-29d split)
- unattended_views: 无人值守总控 API (Phase 8)
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from scheduler.unattended_views import (
    unattended_pause_view,
    unattended_preflight_view,
    unattended_progress_view,
    unattended_queue_view,
    unattended_resume_view,
    unattended_sessions_view,
    unattended_start_view,
    unattended_status_view,
    unattended_stop_view,
)
from scheduler.views import (
    RecoveryLogViewSet,
    TimeWindowViewSet,
    auto_stop_conditions_view,
    execution_plan_view,
    executions_view,
    today_schedule_view,
    warmup_config_view,
)

router = DefaultRouter()
router.register(r"time-windows", TimeWindowViewSet, basename="time-window")
router.register(r"recovery-logs", RecoveryLogViewSet, basename="recovery-log")

urlpatterns = [
    path("", include(router.urls)),
    path("warmup-config/", warmup_config_view, name="warmup-config"),
    path("auto-stop-conditions/", auto_stop_conditions_view, name="auto-stop-conditions"),
    path("execution-plan/", execution_plan_view, name="execution-plan"),
    path("executions/", executions_view, name="scheduler-executions"),
    path("today/", today_schedule_view, name="today-schedule"),
    # Phase 8: 无人值守总控
    path("unattended/start/", unattended_start_view, name="unattended-start"),
    path("unattended/stop/", unattended_stop_view, name="unattended-stop"),
    path("unattended/pause/", unattended_pause_view, name="unattended-pause"),
    path("unattended/resume/", unattended_resume_view, name="unattended-resume"),
    path("unattended/preflight/", unattended_preflight_view, name="unattended-preflight"),
    path("unattended/status/", unattended_status_view, name="unattended-status"),
    path("unattended/queue/", unattended_queue_view, name="unattended-queue"),
    path("unattended/progress/", unattended_progress_view, name="unattended-progress"),
    path("unattended/sessions/", unattended_sessions_view, name="unattended-sessions"),
]
