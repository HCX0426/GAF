from django.urls import include, path
from rest_framework.routers import DefaultRouter

from pipeline.views import (
    PipelineEstimateTimeView,
    PipelineValidateView,
    PipelineViewSet,
    RecordingViewSet,
    TaskChainExecutionViewSet,
    TaskChainNodeView,
    TaskChainViewSet,
)

router = DefaultRouter()
router.register(r'pipelines', PipelineViewSet, basename='pipeline')
# R37-P3 Stage 7 Task 20a: migrated from tasks/task-chains (TD-039).
router.register(r'task-chains', TaskChainViewSet, basename='task-chain')
# v3 §2.7.2: TaskChainExecution list/detail (read-only; created via task-chains/{id}/execute/)
router.register(r'task-chain-executions', TaskChainExecutionViewSet, basename='task-chain-execution')
# P-008: migrated from tasks/recordings — Recording is a pipeline-app concern.
router.register(r'recordings', RecordingViewSet, basename='recording')

urlpatterns = [
    # Explicit paths MUST come before include(router.urls): DefaultRouter's
    # `pipelines/<pk>/` detail route would otherwise match `validate/` and
    # `estimate-time/` as pk values, returning 405 (TD-074).
    path('pipelines/validate/', PipelineValidateView.as_view(), name='pipeline-validate'),
    path('pipelines/estimate-time/', PipelineEstimateTimeView.as_view(), name='pipeline-estimate-time'),
    # R37-P3 Stage 7 Task 20a: migrated from tasks/chain-nodes (TD-039).
    # TD-268: same APIView on 3 URLs — TaskChainNodeSchema generates
    # per-URL operation_ids so spectacular doesn't emit collisions.
    path('chain-nodes/', TaskChainNodeView.as_view(), name='chain-nodes-list'),
    path('chain-nodes/check-circular/', TaskChainNodeView.as_view(), name='chain-nodes-check-circular'),
    path('chain-nodes/<int:pk>/', TaskChainNodeView.as_view(), name='chain-nodes-detail'),
    path('', include(router.urls)),
]
