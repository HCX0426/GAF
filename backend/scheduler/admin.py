from django.contrib import admin

from .models import (
    AutoStopCondition,
    GameAccountRotation,
    PreflightCheck,
    RecoveryLog,
    TimeWindow,
    WarmupConfig,
)


@admin.register(GameAccountRotation)
class GameAccountRotationAdmin(admin.ModelAdmin):
    """游戏账户轮换规则管理后台配置。"""

    list_display = ('id', 'name', 'rotation_strategy', 'switch_interval_seconds', 'is_active', 'created_at')
    list_filter = ('rotation_strategy', 'is_active')
    search_fields = ('name',)
    filter_horizontal = ('accounts',)



@admin.register(PreflightCheck)
class PreflightCheckAdmin(admin.ModelAdmin):
    """预热检查记录管理后台配置。"""

    list_display = ('id', 'check_type', 'target_id', 'status', 'checked_at')
    list_filter = ('check_type', 'status')
    search_fields = ('target_id', 'message')
    readonly_fields = ('checked_at',)


@admin.register(RecoveryLog)
class RecoveryLogAdmin(admin.ModelAdmin):
    """恢复操作日志管理后台配置。"""

    list_display = ('id', 'recovery_level', 'trigger_event', 'action_taken', 'success', 'created_at')
    list_filter = ('recovery_level', 'success')
    search_fields = ('trigger_event', 'action_taken')
    readonly_fields = ('created_at',)


@admin.register(TimeWindow)
class TimeWindowAdmin(admin.ModelAdmin):
    """时间窗口管理后台配置。"""

    list_display = ('id', 'start_time', 'end_time', 'days_of_week', 'is_enabled', 'created_at')
    list_filter = ('is_enabled',)
    search_fields = ('start_time', 'end_time')


@admin.register(WarmupConfig)
class WarmupConfigAdmin(admin.ModelAdmin):
    """设备预热配置管理后台配置。"""

    list_display = ('id', 'failure_strategy', 'global_timeout_seconds', 'steps_count', 'created_at')
    list_filter = ('failure_strategy',)
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='预热步骤数')
    def steps_count(self, obj):
        return len(obj.steps) if obj.steps else 0


@admin.register(AutoStopCondition)
class AutoStopConditionAdmin(admin.ModelAdmin):
    """自动停止条件管理后台配置。"""

    list_display = ('condition_type', 'is_enabled', 'threshold', 'action', 'updated_at')
    list_filter = ('is_enabled', 'action')
    search_fields = ('condition_type',)
