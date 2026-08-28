"""插件管理 URL 路由"""

from django.urls import path

from .views import (
    PluginInstallView,
    PluginListView,
    PluginReloadView,
    PluginSandboxExecView,
    PluginToggleView,
    PluginUninstallView,
    PluginUploadView,
)

urlpatterns = [
    path('upload/', PluginUploadView.as_view(), name='plugin-upload'),
    path('<int:pk>/uninstall/', PluginUninstallView.as_view(), name='plugin-uninstall'),
    path('<int:pk>/install/', PluginInstallView.as_view(), name='plugin-install'),
    path('<int:pk>/toggle/', PluginToggleView.as_view(), name='plugin-toggle'),
    path('<int:pk>/reload/', PluginReloadView.as_view(), name='plugin-reload'),
    path('<int:pk>/sandbox-exec/', PluginSandboxExecView.as_view(), name='plugin-sandbox-exec'),
    path('', PluginListView.as_view(), name='plugin-list'),
]
