from django.urls import include, path
from rest_framework.routers import DefaultRouter

from gaf_ai.agent.views import agent_analyze_view, agent_session_status_view
from gaf_ai.views import (
    agent_evaluation_view,
    ai_chat_view,
    ai_usage_stats_view,
    generate_pipeline,
    generate_pipeline_stream,
    optimize_pipeline,
)
from gaf_ai.views_anomaly import anomaly_detection_view
from gaf_ai.views_evaluation import ModelEvaluationViewSet
from gaf_ai.views_skill import CustomSkillViewSet

router = DefaultRouter()
router.register(r'custom-skills', CustomSkillViewSet, basename='custom-skill')
router.register(r'model-evaluations', ModelEvaluationViewSet, basename='model-evaluation')

urlpatterns = [
    path('generate-pipeline/', generate_pipeline, name='ai-generate-pipeline'),
    path('generate-pipeline-stream/', generate_pipeline_stream, name='ai-generate-pipeline-stream'),
    path('optimize-pipeline/', optimize_pipeline, name='ai-optimize-pipeline'),
    path('usage-stats/', ai_usage_stats_view, name='ai-usage-stats'),
    path('agent-evaluation/', agent_evaluation_view, name='ai-agent-evaluation'),
    path('chat/', ai_chat_view, name='ai-chat'),
    path('anomaly-detection/', anomaly_detection_view, name='ai-anomaly-detection'),
    path('agent/analyze/', agent_analyze_view, name='ai-agent-analyze'),
    path('agent/sessions/<int:session_id>/', agent_session_status_view, name='ai-agent-session-status'),
]

urlpatterns += router.urls

# QA routes (migrated from qa app — 2026-08-04)
urlpatterns += [
    path("qa/", include("gaf_ai.qa_urls")),
]
