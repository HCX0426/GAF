from django.contrib import admin

from .models import MonitorEvent, MonitorRule, SLAMetric


@admin.register(MonitorRule)
class MonitorRuleAdmin(admin.ModelAdmin):
    """监控规则管理后台配置。"""

    list_display = ('id', 'name', 'resource_pack', 'is_enabled', 'created_at')
    list_filter = ('is_enabled',)
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(MonitorEvent)
class MonitorEventAdmin(admin.ModelAdmin):
    """监控事件管理后台配置 (P-024 加 severity/acknowledged/escalated 字段展示)。"""

    list_display = (
        'id', 'event_type', 'severity', 'handling_result',
        'agent', 'resource_pack', 'created_at',
        'acknowledged_at', 'acknowledged_by', 'escalated_at',
    )
    list_filter = ('event_type', 'severity', 'acknowledged_at', 'escalated_at')
    search_fields = ('event_type', 'handling_result')
    readonly_fields = ('created_at', 'acknowledged_at', 'acknowledged_by', 'escalated_at')
    list_select_related = ('agent', 'resource_pack', 'acknowledged_by')


@admin.register(SLAMetric)
class SLAMetricAdmin(admin.ModelAdmin):
    """SLA 指标管理后台配置 (migrated from metrics app — 2026-08-04)."""

    list_display = ('id', 'metric_name', 'value', 'timestamp', 'agent')
    list_filter = ('metric_name', 'agent')
    search_fields = ('metric_name',)
    readonly_fields = ('timestamp',)
