from django.contrib import admin

from .models import Device, DeviceGroup, Worker


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    """Agent 管理后台配置。"""

    list_display = ('id', 'agent_id', 'hostname', 'ip_address', 'status', 'is_local', 'last_heartbeat', 'created_at')
    list_filter = ('status', 'is_local')
    search_fields = ('agent_id', 'hostname', 'ip_address')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    """Device 管理后台配置。"""

    list_display = ('id', 'name', 'device_type', 'status', 'agent', 'resolution_width', 'resolution_height', 'screenshot_fps', 'created_at')
    list_filter = ('device_type', 'status')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(DeviceGroup)
class DeviceGroupAdmin(admin.ModelAdmin):
    """DeviceGroup 管理后台配置。"""

    list_display = ('id', 'name', 'user', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('devices',)
