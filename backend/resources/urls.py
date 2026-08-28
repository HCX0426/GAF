from django.urls import include, path
from rest_framework.routers import DefaultRouter

from resources.views import (
    ResourcePackViewSet,
    TagViewSet,
    TemplateAnnotationViewSet,
    TemplateEffectivenessViewSet,
    TemplateVersionViewSet,
    resource_pack_version_history_view,
    resource_templates_view,
    resource_validation_view,
    template_batch_import_view,
    template_file_view,
    template_match_preview_view,
    template_references_view,
)

router = DefaultRouter()
router.register(r'resource-packs', ResourcePackViewSet, basename='resource-pack')
router.register(r'template-versions', TemplateVersionViewSet, basename='templateversion')
router.register(r'annotations', TemplateAnnotationViewSet, basename='template-annotation')
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'template-effectiveness', TemplateEffectivenessViewSet, basename='template-effectiveness')

urlpatterns = [
    path('', include(router.urls)),
    path('templates/', resource_templates_view, name='resource-templates'),
    path('templates/batch-import/', template_batch_import_view, name='template-batch-import'),
    path('templates/check-references/', template_references_view, name='template-references'),
    # TD-004 (Option A): template images are served directly from resources/
    path('templates/files/<int:pack_id>/<path:file_path>', template_file_view, name='template-file'),
    path('validation/', resource_validation_view, name='resource-validation'),
    path('template-match-preview/', template_match_preview_view, name='template-match-preview'),
    path('resource-packs/<int:pk>/version-history/', resource_pack_version_history_view, name='resource-pack-version-history'),
]
