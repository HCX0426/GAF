from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.app_info import API_PREFIX, APP_ROUTES

# 路由别名 — 方便 urlpatterns 中引用
_R = APP_ROUTES

urlpatterns = [
    path("admin/", admin.site.urls),
    path(f"{API_PREFIX}/{_R['accounts']}/", include("accounts.urls")),
    # agents.urls defines /agents/, /devices/, /device-groups/ resources directly.
    # Do NOT add an extra /agents/ prefix here; that would create duplicate paths
    # like /api/v2/agents/agents/ and break client expectations.
    path(f"{API_PREFIX}/", include("agents.urls")),
    path(f"{API_PREFIX}/{_R['tasks']}/", include("tasks.urls")),
    path(f"{API_PREFIX}/{_R['resources']}/", include("resources.urls")),
    path(f"{API_PREFIX}/{_R['monitors']}/", include("monitors.urls")),
    path(f"{API_PREFIX}/{_R['skills']}/", include("skills.urls")),
    path(f"{API_PREFIX}/{_R['notifications']}/", include("notifications.urls")),
    path(f"{API_PREFIX}/{_R['debug']}/", include("debug.urls")),
    path(f"{API_PREFIX}/{_R['qa']}/", include("gaf_ai.qa_urls")),
    path(f"{API_PREFIX}/{_R['plugins']}/", include("plugins.urls")),
    path(f"{API_PREFIX}/{_R['protocol']}/", include("protocol.urls")),
    path(f"{API_PREFIX}/{_R['gamestate']}/", include("gamestate.urls")),
    path(f"{API_PREFIX}/{_R['pipeline']}/", include("pipeline.urls")),
    path(f"{API_PREFIX}/{_R['scheduler']}/", include("scheduler.urls")),
    path(f"{API_PREFIX}/{_R['executions']}/", include("executions.urls")),
    # L1 fix: analytics routes moved to executions/analytics_urls.py (app include pattern)
    path(f"{API_PREFIX}/{_R['analytics']}/", include("executions.analytics_urls")),
    path(f"{API_PREFIX}/{_R['settings']}/", include("settings.urls")),
    path(f"{API_PREFIX}/{_R['search']}/", include("gaf_core.search_urls")),
    path(f"{API_PREFIX}/{_R['ai']}/", include("gaf_ai.urls")),
    path(f"{API_PREFIX}/{_R['i18n']}/", include("gaf_core.i18n_urls")),
    # F13 (2026-07-31): TraceSpan 表已完全弃用, tracing API 路由已移除.
    # 原 /api/v2/tracing/traces/ 路由已删除.
    # 保留 tracing app 供 context.py + middleware 使用 (trace_id 生成 + 传播).
    # Unified log center — LogEntry API (read-only list/retrieve)
    path(f"{API_PREFIX}/{_R['logs']}/", include("gaf_core.urls")),
    path(f"{API_PREFIX}/{_R['schema']}/", SpectacularAPIView.as_view(), name="schema"),
    path(f"{API_PREFIX}/{_R['docs']}/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # 系统级端点 (性能监控等)
    path(f"{API_PREFIX}/{_R['system']}/", include("gaf_core.system_urls")),
]
