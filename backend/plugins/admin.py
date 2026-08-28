from django.contrib import admin

from .models import PluginHook, PluginPackage, PluginSandbox


@admin.register(PluginHook)
class PluginHookAdmin(admin.ModelAdmin):
    """插件钩子管理后台配置。"""

    list_display = ('id', 'plugin_name', 'event_type', 'hook_function', 'priority', 'is_active')
    list_filter = ('plugin_name', 'event_type', 'is_active')
    search_fields = ('plugin_name', 'hook_function')


@admin.register(PluginPackage)
class PluginPackageAdmin(admin.ModelAdmin):
    """插件包管理后台配置。"""

    list_display = ('id', 'name', 'version', 'author', 'is_installed', 'is_active', 'installed_at', 'created_at')
    list_filter = ('is_installed', 'is_active')
    search_fields = ('name', 'version', 'author')


@admin.register(PluginSandbox)
class PluginSandboxAdmin(admin.ModelAdmin):
    """插件沙箱管理后台配置。"""

    list_display = ('id', 'plugin', 'pid', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('plugin__name',)
