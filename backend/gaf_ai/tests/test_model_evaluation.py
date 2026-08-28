"""Tests for AI model evaluation (P-031)."""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from gaf_ai.evaluation import (
    _compute_scores,
    _default_heuristic_score,
    _weighted_average,
    run_evaluation,
)
from gaf_ai.models import ModelEvaluation, ModelEvaluationResult

User = get_user_model()


def _mock_llm_response(content='Test response', input_tokens=10, output_tokens=20, cost=0.001):
    return {
        'content': content,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'model': 'test-model',
        'cost': cost,
    }


def _mock_llm_error(error='API timeout'):
    return {'error': error, 'content': '', 'input_tokens': 0, 'output_tokens': 0, 'model': 'test-model', 'cost': 0}


class TestModelEvaluationModel(TestCase):
    """Test ModelEvaluation and ModelEvaluationResult models."""

    def setUp(self):
        self.user = User.objects.create_user(username='eval_user', password='pass123')

    def test_create_evaluation(self):
        ev = ModelEvaluation.objects.create(
            name='Test eval',
            created_by=self.user,
            test_cases=['hello'],
            models_config=[{'provider': 'openai', 'model': 'gpt-4o-mini'}],
        )
        self.assertEqual(ev.status, ModelEvaluation.Status.PENDING)
        self.assertEqual(ev.test_cases, ['hello'])
        self.assertIsNone(ev.completed_at)
        self.assertEqual(str(ev), 'Test eval (pending)')

    def test_create_result(self):
        ev = ModelEvaluation.objects.create(name='Test', created_by=self.user)
        result = ModelEvaluationResult.objects.create(
            evaluation=ev,
            test_case_index=0,
            provider='openai',
            model_name='gpt-4o-mini',
            output_text='Hello',
            input_tokens=5,
            output_tokens=5,
            cost=Decimal('0.001'),
            latency_ms=200,
            scores={'quality': 8.0},
            average_score=8.0,
        )
        self.assertTrue(result.is_success)
        self.assertEqual(result.average_score, 8.0)
        self.assertIn('OK', str(result))

    def test_unique_together_evaluation_case_model(self):
        ev = ModelEvaluation.objects.create(name='Test', created_by=self.user)
        ModelEvaluationResult.objects.create(
            evaluation=ev, test_case_index=0, provider='openai', model_name='gpt-4o-mini'
        )
        with self.assertRaises(IntegrityError):
            ModelEvaluationResult.objects.create(
                evaluation=ev, test_case_index=0, provider='openai', model_name='gpt-4o-mini'
            )

    def test_status_choices(self):
        ev = ModelEvaluation.objects.create(name='Test', created_by=self.user)
        for s in ['pending', 'running', 'completed', 'failed']:
            ev.status = s
            ev.save()
            ev.refresh_from_db()
            self.assertEqual(ev.status, s)


class TestScoringFunctions(TestCase):
    """Test scoring helper functions."""

    def test_compute_scores_accuracy(self):
        scores = _compute_scores('Hello world', [{'name': 'accuracy', 'weight': 1.0}])
        self.assertEqual(scores['accuracy'], 10.0)

    def test_compute_scores_accuracy_empty(self):
        scores = _compute_scores('', [{'name': 'accuracy', 'weight': 1.0}])
        self.assertEqual(scores['accuracy'], 0.0)

    def test_compute_scores_fluency(self):
        scores = _compute_scores('Hello. World.', [{'name': 'fluency', 'weight': 1.0}])
        self.assertGreater(scores['fluency'], 5.0)

    def test_compute_scores_completeness_short(self):
        scores = _compute_scores('Hi', [{'name': 'completeness', 'weight': 1.0}])
        self.assertEqual(scores['completeness'], 0.0)

    def test_compute_scores_completeness_long(self):
        scores = _compute_scores('x' * 100, [{'name': 'completeness', 'weight': 1.0}])
        self.assertEqual(scores['completeness'], 10.0)

    def test_compute_scores_custom_criterion(self):
        # Generic criterion: score = min(10, text_len/100), so 1000 chars → 10.0
        scores = _compute_scores('x' * 1000, [{'name': 'custom', 'weight': 1.0}])
        self.assertEqual(scores['custom'], 10.0)

    def test_default_heuristic_score_empty(self):
        scores = _default_heuristic_score('')
        self.assertEqual(scores['quality'], 0.0)
        self.assertEqual(scores['length'], 0.0)

    def test_default_heuristic_score_non_empty(self):
        scores = _default_heuristic_score('x' * 150)
        self.assertGreater(scores['quality'], 0)
        self.assertGreater(scores['length'], 0)

    def test_weighted_average_with_weights(self):
        scores = {'a': 8.0, 'b': 6.0}
        criteria = [{'name': 'a', 'weight': 2.0}, {'name': 'b', 'weight': 1.0}]
        avg = _weighted_average(scores, criteria)
        self.assertEqual(avg, round((8.0 * 2 + 6.0 * 1) / 3, 2))

    def test_weighted_average_no_match(self):
        scores = {'a': 8.0}
        criteria = [{'name': 'b', 'weight': 1.0}]
        avg = _weighted_average(scores, criteria)
        self.assertEqual(avg, 8.0)

    def test_weighted_average_empty(self):
        avg = _weighted_average({}, [])
        self.assertEqual(avg, 0.0)


class TestRunEvaluation(TestCase):
    """Test the evaluation engine."""

    def setUp(self):
        self.user = User.objects.create_user(username='eval_user', password='pass123')

    @patch('gaf_ai.evaluation.call_llm')
    def test_run_evaluation_success(self, mock_call):
        mock_call.side_effect = [
            _mock_llm_response('Response from model A'),
            _mock_llm_response('Response from model B'),
        ]
        ev = ModelEvaluation.objects.create(
            name='Test',
            created_by=self.user,
            test_cases=['Hello'],
            models_config=[
                {'provider': 'openai', 'model': 'gpt-4o-mini'},
                {'provider': 'deepseek', 'model': 'deepseek-chat'},
            ],
            scoring_criteria=[{'name': 'accuracy', 'weight': 1.0}],
        )
        run_evaluation(ev.id)
        ev.refresh_from_db()
        self.assertEqual(ev.status, ModelEvaluation.Status.COMPLETED)
        self.assertIsNotNone(ev.completed_at)
        self.assertEqual(ev.results.count(), 2)
        for r in ev.results.all():
            self.assertTrue(r.is_success)
            self.assertGreater(r.average_score, 0)

    @patch('gaf_ai.evaluation.call_llm')
    def test_run_evaluation_partial_failure(self, mock_call):
        mock_call.side_effect = [
            _mock_llm_response('OK'),
            _mock_llm_error('API error'),
        ]
        ev = ModelEvaluation.objects.create(
            name='Test',
            created_by=self.user,
            test_cases=['Hello'],
            models_config=[
                {'provider': 'openai', 'model': 'gpt-4o-mini'},
                {'provider': 'deepseek', 'model': 'deepseek-chat'},
            ],
        )
        run_evaluation(ev.id)
        ev.refresh_from_db()
        self.assertEqual(ev.status, ModelEvaluation.Status.COMPLETED)
        self.assertIn('failed', ev.error_message)
        success_results = ev.results.filter(is_success=True)
        failed_results = ev.results.filter(is_success=False)
        self.assertEqual(success_results.count(), 1)
        self.assertEqual(failed_results.count(), 1)

    def test_run_evaluation_no_test_cases(self):
        ev = ModelEvaluation.objects.create(
            name='Test', created_by=self.user, test_cases=[], models_config=[{'provider': 'openai', 'model': 'gpt-4o-mini'}]
        )
        run_evaluation(ev.id)
        ev.refresh_from_db()
        self.assertEqual(ev.status, ModelEvaluation.Status.FAILED)
        self.assertIn('No test cases', ev.error_message)

    def test_run_evaluation_no_models(self):
        ev = ModelEvaluation.objects.create(
            name='Test', created_by=self.user, test_cases=['hello'], models_config=[]
        )
        run_evaluation(ev.id)
        ev.refresh_from_db()
        self.assertEqual(ev.status, ModelEvaluation.Status.FAILED)
        self.assertIn('No models', ev.error_message)

    def test_run_evaluation_not_found(self):
        # Should not raise
        run_evaluation(99999)

    @patch('gaf_ai.evaluation.call_llm')
    def test_run_evaluation_multiple_cases(self, mock_call):
        mock_call.side_effect = [
            _mock_llm_response('A1'),
            _mock_llm_response('A2'),
            _mock_llm_response('B1'),
            _mock_llm_response('B2'),
        ]
        ev = ModelEvaluation.objects.create(
            name='Test',
            created_by=self.user,
            test_cases=['case1', 'case2'],
            models_config=[
                {'provider': 'openai', 'model': 'gpt-4o-mini'},
                {'provider': 'deepseek', 'model': 'deepseek-chat'},
            ],
        )
        run_evaluation(ev.id)
        ev.refresh_from_db()
        self.assertEqual(ev.results.count(), 4)
        case_indices = set(ev.results.values_list('test_case_index', flat=True))
        self.assertEqual(case_indices, {0, 1})


class TestModelEvaluationAPI(TestCase):
    """Test the ModelEvaluation ViewSet API."""

    def setUp(self):
        self.user = User.objects.create_user(username='api_user', password='pass123', role=User.Role.OPERATOR)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch('gaf_ai.evaluation.call_llm')
    def test_create_evaluation_runs_immediately(self, mock_call):
        mock_call.return_value = _mock_llm_response('Test output')
        payload = {
            'name': 'API test',
            'description': 'Test via API',
            'test_cases': ['hello'],
            'models_config': [{'provider': 'openai', 'model': 'gpt-4o-mini'}],
            'scoring_criteria': [{'name': 'accuracy', 'weight': 1.0}],
        }
        resp = self.client.post('/api/v2/ai/model-evaluations/', payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(d['status'], 'completed')
        self.assertEqual(d['name'], 'API test')
        self.assertEqual(len(d['results']), 1)

    def test_list_evaluations(self):
        ModelEvaluation.objects.create(name='Ev1', created_by=self.user)
        ModelEvaluation.objects.create(name='Ev2', created_by=self.user)
        other = User.objects.create_user(username='other', password='pass')
        ModelEvaluation.objects.create(name='EvOther', created_by=other)

        resp = self.client.get('/api/v2/ai/model-evaluations/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        results = resp.data['data']['results']
        self.assertEqual(len(results), 2)
        names = [e['name'] for e in results]
        self.assertIn('Ev1', names)
        self.assertIn('Ev2', names)
        self.assertNotIn('EvOther', names)

    def test_retrieve_evaluation(self):
        ev = ModelEvaluation.objects.create(name='EvDetail', created_by=self.user)
        ModelEvaluationResult.objects.create(
            evaluation=ev, test_case_index=0, provider='openai', model_name='gpt-4o-mini', output_text='hi'
        )
        resp = self.client.get(f'/api/v2/ai/model-evaluations/{ev.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(d['name'], 'EvDetail')
        self.assertEqual(len(d['results']), 1)

    def test_delete_evaluation(self):
        ev = ModelEvaluation.objects.create(name='ToDelete', created_by=self.user)
        resp = self.client.delete(f'/api/v2/ai/model-evaluations/{ev.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ModelEvaluation.objects.filter(id=ev.id).exists())

    @patch('gaf_ai.evaluation.call_llm')
    def test_run_action(self, mock_call):
        mock_call.return_value = _mock_llm_response('Re-run output')
        ev = ModelEvaluation.objects.create(
            name='EvRerun',
            created_by=self.user,
            test_cases=['hello'],
            models_config=[{'provider': 'openai', 'model': 'gpt-4o-mini'}],
        )
        resp = self.client.post(f'/api/v2/ai/model-evaluations/{ev.id}/run/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(d['status'], 'completed')
        self.assertEqual(len(d['results']), 1)

    @patch('gaf_ai.evaluation.call_llm')
    def test_summary_action(self, mock_call):
        mock_call.side_effect = [
            _mock_llm_response('A1'),
            _mock_llm_response('B1'),
        ]
        ev = ModelEvaluation.objects.create(
            name='EvSummary',
            created_by=self.user,
            test_cases=['hello'],
            models_config=[
                {'provider': 'openai', 'model': 'gpt-4o-mini'},
                {'provider': 'deepseek', 'model': 'deepseek-chat'},
            ],
            scoring_criteria=[{'name': 'accuracy', 'weight': 1.0}],
        )
        run_evaluation(ev.id)
        resp = self.client.get(f'/api/v2/ai/model-evaluations/{ev.id}/summary/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(d['evaluation_id'], ev.id)
        self.assertEqual(len(d['summary']), 2)
        # Summary should be sorted by avg_score descending
        scores = [s['avg_score'] for s in d['summary']]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_unauthenticated_access_denied(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/v2/ai/model-evaluations/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
