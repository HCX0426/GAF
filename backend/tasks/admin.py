from django.contrib import admin

from .models import (
    CustomTask,
    ExecutionStep,
    ScheduledTask,
    ScreenshotFrame,
    Task,
    TaskExecution,
)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    """任务管理后台配置。"""

    list_display = ('id', 'name', 'execution_mode', 'is_enabled', 'created_at')
    list_filter = ('execution_mode', 'is_enabled')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TaskExecution)
class TaskExecutionAdmin(admin.ModelAdmin):
    """任务执行记录管理后台配置。"""

    list_display = ('id', 'task', 'agent', 'status', 'triggered_by', 'started_at', 'completed_at', 'created_at')
    list_filter = ('status',)
    search_fields = ('task__name', 'agent__agent_id')
    readonly_fields = ('created_at',)


@admin.register(CustomTask)
class CustomTaskAdmin(admin.ModelAdmin):
    """自定义任务管理后台配置。"""

    list_display = ('id', 'name', 'is_enabled', 'created_by', 'created_at')
    list_filter = ('is_enabled',)
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ScheduledTask)
class ScheduledTaskAdmin(admin.ModelAdmin):
    """定时任务管理后台配置。"""

    list_display = ('id', 'task', 'custom_task', 'schedule_type', 'cron_expression', 'is_enabled', 'last_executed_at', 'created_at')
    list_filter = ('schedule_type', 'is_enabled')
    search_fields = ('task__name', 'custom_task__name', 'cron_expression')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ExecutionStep)
class ExecutionStepAdmin(admin.ModelAdmin):
    """执行步骤管理后台配置。"""

    list_display = ('id', 'task_result', 'step_index', 'step_name', 'step_type', 'status', 'duration_ms')
    list_filter = ('status', 'step_type')
    search_fields = ('step_name',)


@admin.register(ScreenshotFrame)
class ScreenshotFrameAdmin(admin.ModelAdmin):
    """截图帧管理后台配置。"""

    list_display = ('id', 'execution_step', 'frame_index', 'timestamp_ms')
    search_fields = ('execution_step__step_name',)
