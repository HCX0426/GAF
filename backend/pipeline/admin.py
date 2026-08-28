from django.contrib import admin

from pipeline.models import Pipeline, PipelineSnapshot, Recording, TaskChain, TaskChainNode


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    """Pipeline 管理后台配置。"""

    list_display = ('id', 'name', 'version', 'is_template', 'estimated_duration_ms', 'updated_at')
    list_filter = ('is_template',)
    search_fields = ('name', 'description')
    readonly_fields = ('id', 'version', 'created_at', 'updated_at')


@admin.register(PipelineSnapshot)
class PipelineSnapshotAdmin(admin.ModelAdmin):
    """Pipeline 版本快照管理后台配置。"""

    list_display = ('id', 'pipeline', 'version', 'created_at')
    list_filter = ('pipeline',)
    readonly_fields = ('created_at',)


@admin.register(TaskChain)
class TaskChainAdmin(admin.ModelAdmin):
    """任务链管理后台配置（R37-P3 Stage 7: 从 tasks 迁入，原 tasks app 未注册，补注册）。"""

    list_display = ('id', 'name', 'is_enabled', 'created_by', 'created_at', 'updated_at')
    list_filter = ('is_enabled',)
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TaskChainNode)
class TaskChainNodeAdmin(admin.ModelAdmin):
    """任务链节点管理后台配置（R37-P3 Stage 7: 从 tasks 迁入）。"""

    list_display = ('id', 'task', 'parent', 'order')
    list_filter = ('task',)
    search_fields = ('task__name',)


@admin.register(Recording)
class RecordingAdmin(admin.ModelAdmin):
    """录制管理后台配置 (P-008: migrated from tasks app)."""

    list_display = ('id', 'name', 'user', 'duration', 'screenshot_count', 'resolution', 'created_at')
    list_filter = ('resolution',)
    search_fields = ('name', 'user__username')
    readonly_fields = ('id', 'created_at')
