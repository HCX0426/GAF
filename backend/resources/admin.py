from django.contrib import admin

from .models import RecognizerBenchmark, ResourcePack, Template, TemplateAnnotation, TemplateEffectiveness


@admin.register(ResourcePack)
class ResourcePackAdmin(admin.ModelAdmin):
    """资源包管理后台配置。"""

    list_display = ('id', 'name', 'version', 'target_app', 'author', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'target_app', 'author')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    """模板管理后台配置。"""

    list_display = ('id', 'name', 'resource_pack', 'template_type', 'is_active', 'created_at')
    list_filter = ('is_active', 'template_type')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(TemplateAnnotation)
class TemplateAnnotationAdmin(admin.ModelAdmin):
    """模板标注管理后台配置。"""

    list_display = ('id', 'template', 'annotation_type', 'label', 'created_at')
    list_filter = ('annotation_type',)
    search_fields = ('template__name', 'label')
    readonly_fields = ('created_at',)


@admin.register(RecognizerBenchmark)
class RecognizerBenchmarkAdmin(admin.ModelAdmin):
    """识别器基准测试管理后台配置。"""

    list_display = ('id', 'recognizer_type', 'engine_name', 'sample_count', 'avg_duration_ms', 'accuracy', 'created_at')
    list_filter = ('recognizer_type', 'engine_name')
    readonly_fields = ('created_at',)


@admin.register(TemplateEffectiveness)
class TemplateEffectivenessAdmin(admin.ModelAdmin):
    """模板有效性管理后台配置。

    R37-P3 Stage 7 Task 20a: migrated from tasks app. Registered here because
    it belongs with the other template-lifecycle models in resources.
    """

    list_display = ('id', 'template', 'total_attempts', 'success_count', 'consecutive_failures', 'is_suspected_invalid')
    list_filter = ('is_suspected_invalid',)
    search_fields = ('template__name',)
