from django.urls import include, path
from rest_framework.routers import DefaultRouter

from tasks import backup_views
from tasks.execution_views import (
    TaskBindAccountsView,
    TaskBindDevicesView,
    TaskExecutionViewSet,
)
from tasks.resource_views import (
    CustomTaskViewSet,
    MarketplaceViewSet,
    ScheduledTaskViewSet,
    TaskFolderViewSet,
)
from tasks.views import (
    TaskBulkActionView,
    TaskCloneView,
    TaskParallelConfigView,
    TaskViewSet,
    task_version_list_view,
    task_version_save_view,
)

# TD-060: trace_views migrated to tracing app (/api/v2/tracing/traces/).

router = DefaultRouter()
router.register(r'task-executions', TaskExecutionViewSet, basename='task-execution')
router.register(r'custom-tasks', CustomTaskViewSet, basename='custom-task')
router.register(r'scheduled-tasks', ScheduledTaskViewSet, basename='scheduled-task')
# TD-061 Plan B Stage 2: pipelines route moved to pipeline app
# (/api/v2/pipeline/pipelines/). See pipeline/urls.py.
router.register(r'marketplace', MarketplaceViewSet, basename='marketplace')
# P-008: recordings route moved to pipeline app
# (/api/v2/pipeline/recordings/). See pipeline/urls.py.
router.register(r'folders', TaskFolderViewSet, basename='task-folder')

urlpatterns = [
    # TaskViewSet at root to avoid /api/v2/tasks/tasks/ double namespace
    path('', TaskViewSet.as_view({'get': 'list', 'post': 'create'}), name='task-list'),
    path('<int:pk>/', TaskViewSet.as_view({
        'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'
    }), name='task-detail'),
    # TD-268: same APIView on 2 URLs — TaskBindDevicesSchema generates
    # per-URL operation_ids so spectacular doesn't emit collisions.
    path('bind-devices/<int:pk>/', TaskBindDevicesView.as_view(), name='task-bind-devices'),
    path('bind-devices/<int:pk>/<int:mapping_id>/', TaskBindDevicesView.as_view(), name='task-bind-devices-delete'),
    path('bind-accounts/<int:pk>/', TaskBindAccountsView.as_view(), name='task-bind-accounts'),
    path('parallel-config/<int:pk>/', TaskParallelConfigView.as_view(), name='task-parallel-config'),
    path('bulk-action/', TaskBulkActionView.as_view(), name='task-bulk-action'),
    path('clone/<int:pk>/', TaskCloneView.as_view(), name='task-clone'),
    path('<int:pk>/execute/', TaskViewSet.as_view({'post': 'execute'}), name='task-execute-action'),
    path('<int:pk>/cancel/', TaskViewSet.as_view({'post': 'cancel'}), name='task-cancel-action'),
    path('<int:pk>/validate/', TaskViewSet.as_view({'post': 'validate'}), name='task-validate-action'),
    # Task 1.4 (P1-6): validate-payload 端点 — 校验 inline task_definition, 无需 pk, 不写库。
    # 放在 <int:pk>/ 之前以避免被 detail route 错误匹配 (虽然 int converter 不匹配字符串,
    # 但显式前置更清晰, 与 analytics/backup 等无 pk 路由一致)。
    path('validate-payload/', TaskViewSet.as_view({'post': 'validate_payload'}), name='task-validate-payload'),
    # TD-074: explicit paths MUST come before include(router.urls) to prevent
    # the router's <pk>/ detail route from matching these as pk values.
    # (analytics/* 由 executions.analytics_urls 挂载于 /api/v2/analytics/, 2026-08-29 去重)
    path('backup/create/', backup_views.create_backup, name='backup-create'),
    path('backup/restore/', backup_views.restore_backup, name='backup-restore'),
    # TD-060: traces routes migrated to tracing app (/api/v2/tracing/traces/).
    path('versions/', task_version_list_view, name='task-version-list'),
    path('<int:pk>/save-version/', task_version_save_view, name='task-version-save'),
    path('', include(router.urls)),
]
