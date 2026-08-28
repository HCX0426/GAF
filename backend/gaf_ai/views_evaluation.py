"""Views for AI model evaluation (P-031)."""
import logging

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import RoleBasedPermission

from .evaluation import run_evaluation
from .models import ModelEvaluation
from .serializers import (
    ModelEvaluationCreateSerializer,
    ModelEvaluationSerializer,
)

logger = logging.getLogger(__name__)


class ModelEvaluationViewSet(viewsets.ModelViewSet):
    """ViewSet for model performance evaluations.

    - GET    /api/ai/model-evaluations/                  list user's evaluations
    - POST   /api/ai/model-evaluations/                  create + auto-run evaluation
    - GET    /api/ai/model-evaluations/<id>/             retrieve evaluation with results
    - DELETE /api/ai/model-evaluations/<id>/             delete evaluation
    - POST   /api/ai/model-evaluations/<id>/run/         re-run evaluation
    - GET    /api/ai/model-evaluations/<id>/summary/     aggregated summary per model
    """

    permission_classes = [IsAuthenticated, RoleBasedPermission]
    required_permission = 'llm_use'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ModelEvaluation.objects.none()
        return ModelEvaluation.objects.filter(created_by=self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return ModelEvaluationCreateSerializer
        return ModelEvaluationSerializer

    def create(self, request, *args, **kwargs):
        """Create evaluation and immediately run it synchronously."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        evaluation = serializer.save(created_by=request.user)

        # Run evaluation synchronously (small-scale MVP)
        try:
            run_evaluation(evaluation.id)
            evaluation.refresh_from_db()
        except Exception as e:
            logger.exception('Evaluation %s failed', evaluation.id)
            evaluation.status = ModelEvaluation.Status.FAILED
            evaluation.error_message = str(e)
            evaluation.save(update_fields=['status', 'error_message', 'updated_at'])

        response_serializer = ModelEvaluationSerializer(evaluation)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='run')
    def run(self, request, pk=None):
        """Re-run an existing evaluation (clears old results)."""
        evaluation = self.get_object()
        evaluation.results.all().delete()
        evaluation.status = ModelEvaluation.Status.PENDING
        evaluation.error_message = ''
        evaluation.completed_at = None
        evaluation.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])

        try:
            run_evaluation(evaluation.id)
            evaluation.refresh_from_db()
        except Exception as e:
            logger.exception('Re-run evaluation %s failed', evaluation.id)
            evaluation.status = ModelEvaluation.Status.FAILED
            evaluation.error_message = str(e)
            evaluation.save(update_fields=['status', 'error_message', 'updated_at'])

        serializer = ModelEvaluationSerializer(evaluation)
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='summary')
    def summary(self, request, pk=None):
        """Return aggregated summary per model (avg score, total cost, avg latency)."""
        evaluation = self.get_object()
        results = evaluation.results.all()

        per_model: dict[str, dict] = {}
        for r in results:
            key = f'{r.provider}/{r.model_name}'
            if key not in per_model:
                per_model[key] = {
                    'provider': r.provider,
                    'model_name': r.model_name,
                    'count': 0,
                    'success_count': 0,
                    'total_score': 0.0,
                    'total_cost': 0,
                    'total_latency_ms': 0,
                    'total_input_tokens': 0,
                    'total_output_tokens': 0,
                }
            stats = per_model[key]
            stats['count'] += 1
            if r.is_success:
                stats['success_count'] += 1
                stats['total_score'] += float(r.average_score)
            stats['total_cost'] += float(r.cost)
            stats['total_latency_ms'] += r.latency_ms
            stats['total_input_tokens'] += r.input_tokens
            stats['total_output_tokens'] += r.output_tokens

        # Compute averages
        summary_list = []
        for _key, stats in per_model.items():
            count = stats['count']
            success = stats['success_count']
            summary_list.append({
                'provider': stats['provider'],
                'model_name': stats['model_name'],
                'total_cases': count,
                'success_count': success,
                'failure_count': count - success,
                'success_rate': round(success / count, 4) if count else 0,
                'avg_score': round(stats['total_score'] / success, 2) if success else 0,
                'total_cost': round(stats['total_cost'], 6),
                'avg_latency_ms': round(stats['total_latency_ms'] / count) if count else 0,
                'total_input_tokens': stats['total_input_tokens'],
                'total_output_tokens': stats['total_output_tokens'],
            })

        # Sort by avg_score descending
        summary_list.sort(key=lambda x: x['avg_score'], reverse=True)
        return Response({
            'evaluation_id': evaluation.id,
            'evaluation_name': evaluation.name,
            'status': evaluation.status,
            'summary': summary_list,
        })
