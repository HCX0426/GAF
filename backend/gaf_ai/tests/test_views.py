"""Tests for AI pipeline/generation/optimization/anomaly/skill views.

Merged from:
  - test_views_pipeline.py (P-037): generate_pipeline, optimize_pipeline,
    ai_usage_stats_view, ai_chat_view
  - test_views_anomaly.py (P-035): anomaly_detection_view,
    _extract_patterns, _categorize_error, _estimate_severity
  - test_views_skill.py (P-036): CustomSkillViewSet CRUD
"""
import json
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from pipeline.models import Pipeline
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from gaf_ai.models import CustomSkill, LLMUsageLog
from gaf_ai.views_anomaly import (
    _categorize_error,
    _estimate_severity,
    _extract_patterns,
)
from tasks.models import Task, TaskExecution

# ================================================================
# Helper factories (pipeline section)
# ================================================================

def _make_pipeline(user, name='Test Pipeline', graph_data=None, **kwargs):
    """Create a minimal Pipeline owned by user."""
    defaults = {
        'name': name,
        'description': 'Test pipeline',
        'graph_data': graph_data or {'nodes': [], 'edges': []},
        'version': 1,
        'is_template': False,
    }
    defaults.update(kwargs)
    return Pipeline.objects.create(user=user, **defaults)


def _make_pipeline_execution(user, task, status='success', error_message='', days_ago=1):
    """Create a TaskExecution for optimize_pipeline context (sets completed_at)."""
    started = timezone.now() - timedelta(days=days_ago)
    completed = started + timedelta(seconds=30) if status == 'success' else None
    return TaskExecution.objects.create(
        task=task,
        triggered_by=user,
        status=status,
        error_message=error_message,
        started_at=started,
        completed_at=completed,
    )


# ================================================================
# Helper factories (anomaly section)
# ================================================================

def _make_task(name='Anomaly Test Task', **kwargs):
    """Create a minimal Task with only required fields."""
    defaults = {
        'name': name,
        'execution_mode': Task.ExecutionMode.PIPELINE,
        'task_definition': {'nodes': []},
    }
    defaults.update(kwargs)
    return Task.objects.create(**defaults)


def _make_execution(task, user, status='failed', error_message='', days_ago=0):
    """Create a TaskExecution with given status and started_at offset."""
    started = timezone.now() - timedelta(days=days_ago)
    return TaskExecution.objects.create(
        task=task,
        triggered_by=user,
        status=status,
        error_message=error_message,
        started_at=started,
    )


# ================================================================
# Helper factories (skill section)
# ================================================================

def _make_skill(user, **kwargs):
    """Create a CustomSkill owned by user.

    All CustomSkill fields are accepted as kwargs; 'id' and 'name'
    have defaults but can be overridden.
    """
    defaults = {
        'id': 'skill-1',
        'name': 'Test Skill',
        'description': 'A test skill',
        'category': 'analysis',
        'yaml_content': 'version: "1"\nsteps: []',
        'is_active': True,
    }
    defaults.update(kwargs)
    return CustomSkill.objects.create(created_by=user, **defaults)


# ================================================================
# Pipeline views — generate_pipeline
# Source: test_views_pipeline.py
# ================================================================

class GeneratePipelineTest(TestCase):
    """POST /api/v2/ai/generate-pipeline/ — NL → pipeline JSON."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='gen_user',
            password='TestPass123!',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.user)

    def test_unauthenticated_denied(self):
        client = APIClient()
        resp = client.post('/api/v2/ai/generate-pipeline/', {'description': 'x'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_description_returns_400(self):
        resp = self.client.post('/api/v2/ai/generate-pipeline/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # UnifiedResponseMiddleware 包装错误响应为 {code, message, data}
        self.assertIn('message', resp.data)

    def test_empty_description_returns_400(self):
        resp = self.client.post('/api/v2/ai/generate-pipeline/', {'description': ''}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch('gaf_ai.views.call_llm')
    def test_successful_generation_with_valid_json(self, mock_call_llm):
        """LLM returns valid JSON with 'nodes' → graph_data extracted."""
        graph = {'nodes': [{'id': 'n1', 'label': 'Step 1'}], 'edges': []}
        mock_call_llm.return_value = {
            'content': f'Here is the pipeline:\n{json.dumps(graph)}\nDone.',
            'input_tokens': 100,
            'output_tokens': 200,
            'cost': 0.005,
            'model': 'gpt-4o-mini',
        }
        resp = self.client.post('/api/v2/ai/generate-pipeline/', {
            'description': 'Login and click button',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertIsNotNone(d['graph_data'])
        self.assertEqual(d['graph_data']['nodes'][0]['id'], 'n1')
        self.assertEqual(d['usage']['input_tokens'], 100)
        self.assertEqual(d['usage']['cost'], 0.005)
        # TD-390: 响应须含 validation 守门字段
        self.assertIn('validation', d)
        self.assertIsInstance(d['validation'], dict)
        self.assertIn('risk_level', d['validation'])
        # LLMUsageLog should be created
        self.assertEqual(
            LLMUsageLog.objects.filter(
                user=self.user, call_type='generate_pipeline'
            ).count(), 1
        )

    @mock.patch('gaf_ai.views.call_llm')
    def test_high_risk_generation_flagged(self, mock_call_llm):
        """TD-390: 含高危 node_type 的生成物须标记为 high 风险。"""
        graph = {
            'nodes': [
                {'id': 'a', 'node_type': 'screenshot'},
                {'id': 'b', 'node_type': 'shell_command', 'cmd': 'rm -rf /'},
            ],
            'edges': [{'source': 'a', 'target': 'b'}],
        }
        mock_call_llm.return_value = {
            'content': json.dumps(graph),
            'input_tokens': 100,
            'output_tokens': 200,
            'cost': 0.005,
            'model': 'gpt-4o-mini',
        }
        resp = self.client.post('/api/v2/ai/generate-pipeline/', {
            'description': 'do something dangerous',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        d = resp.data['data']
        self.assertEqual(d['validation']['risk_level'], 'high')
        self.assertEqual(d['validation']['high_risk_nodes'], ['b'])

    @mock.patch('gaf_ai.views.call_llm')
    def test_llm_returns_non_json_returns_warning(self, mock_call_llm):
        """LLM returns plain text → graph_data=None, warning issued."""
        mock_call_llm.return_value = {
            'content': 'I cannot generate a pipeline for this.',
            'input_tokens': 50,
            'output_tokens': 30,
            'cost': 0.001,
        }
        resp = self.client.post('/api/v2/ai/generate-pipeline/', {
            'description': 'vague task',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertIsNone(d['graph_data'])
        self.assertIn('warning', d)
        self.assertEqual(d['raw_content'], 'I cannot generate a pipeline for this.')

    @mock.patch('gaf_ai.views.call_llm')
    def test_llm_returns_json_without_nodes_returns_warning(self, mock_call_llm):
        """JSON without 'nodes' key → treated as non-standard, warning issued."""
        mock_call_llm.return_value = {
            'content': '{"foo": "bar"}',
            'input_tokens': 10,
            'output_tokens': 5,
            'cost': 0.0,
        }
        resp = self.client.post('/api/v2/ai/generate-pipeline/', {
            'description': 'test',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertIsNone(d['graph_data'])
        self.assertIn('warning', d)

    @mock.patch('gaf_ai.views.call_llm')
    def test_llm_returns_error_status_500(self, mock_call_llm):
        """LLM returns {'error': ...} → 500 with error message."""
        mock_call_llm.return_value = {'error': 'all clients failed'}
        resp = self.client.post('/api/v2/ai/generate-pipeline/', {
            'description': 'test',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        # UnifiedResponseMiddleware 包装错误响应为 {code, message, data}
        self.assertIn('message', resp.data)

    @mock.patch('gaf_ai.views.call_llm')
    def test_model_parameter_forwarded(self, mock_call_llm):
        """The 'model' field from request is forwarded to call_llm."""
        mock_call_llm.return_value = {
            'content': '{"nodes": []}',
            'input_tokens': 1, 'output_tokens': 1, 'cost': 0,
        }
        self.client.post('/api/v2/ai/generate-pipeline/', {
            'description': 'test', 'model': 'deepseek-chat',
        }, format='json')
        # call_llm should have been called with model='deepseek-chat'
        _, kwargs = mock_call_llm.call_args
        self.assertEqual(kwargs.get('model'), 'deepseek-chat')

    @mock.patch('gaf_ai.views.call_llm')
    def test_json_extraction_from_markdown_code_block(self, mock_call_llm):
        """JSON wrapped in markdown ```json ... ``` blocks is still extracted."""
        graph = {'nodes': [{'id': 'n1'}], 'edges': []}
        mock_call_llm.return_value = {
            'content': f'```json\n{json.dumps(graph)}\n```',
            'input_tokens': 1, 'output_tokens': 1, 'cost': 0,
        }
        resp = self.client.post('/api/v2/ai/generate-pipeline/', {
            'description': 'test',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertIsNotNone(d['graph_data'])
        self.assertIn('nodes', d['graph_data'])


# ── optimize_pipeline tests ─────────────────────────────────────
class OptimizePipelineTest(TestCase):
    """POST /api/v2/ai/optimize-pipeline/ — LLM optimization suggestions."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='opt_user',
            password='TestPass123!',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.user)
        self.pipeline = _make_pipeline(self.user, name='My Pipeline')
        self.task = _make_task()

    def test_unauthenticated_denied(self):
        client = APIClient()
        resp = client.post('/api/v2/ai/optimize-pipeline/', {'pipeline_id': 1}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_pipeline_id_returns_400(self):
        resp = self.client.post('/api/v2/ai/optimize-pipeline/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nonexistent_pipeline_returns_404(self):
        resp = self.client.post('/api/v2/ai/optimize-pipeline/', {
            'pipeline_id': 99999,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_users_pipeline_returns_404(self):
        """Pipeline owned by another user → 404 (query filters by user)."""
        other = User.objects.create_user(
            username='other', password='Pass123!', role=User.Role.ADMIN,
        )
        other_pipeline = _make_pipeline(other, name='Other Pipeline')
        resp = self.client.post('/api/v2/ai/optimize-pipeline/', {
            'pipeline_id': other_pipeline.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @mock.patch('gaf_ai.views.call_llm')
    def test_successful_optimization_with_suggestions(self, mock_call_llm):
        """LLM returns valid JSON suggestions → extracted and returned."""
        _make_pipeline_execution(self.user, self.task, status='failed', error_message='timeout')
        suggestions = {
            'suggestions': [
                {'type': 'performance', 'message': 'Add retry for step 1'},
                {'type': 'reliability', 'message': 'Increase timeout'},
            ]
        }
        mock_call_llm.return_value = {
            'content': json.dumps(suggestions),
            'input_tokens': 200,
            'output_tokens': 150,
            'cost': 0.003,
        }
        resp = self.client.post('/api/v2/ai/optimize-pipeline/', {
            'pipeline_id': self.pipeline.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(len(d['suggestions']['suggestions']), 2)
        self.assertEqual(d['usage']['input_tokens'], 200)
        # LLMUsageLog should be created
        self.assertEqual(
            LLMUsageLog.objects.filter(
                user=self.user, call_type='optimize_pipeline'
            ).count(), 1
        )

    @mock.patch('gaf_ai.views.call_llm')
    def test_optimize_llm_returns_non_json_empty_suggestions(self, mock_call_llm):
        """LLM returns plain text → suggestions = {'suggestions': []}."""
        mock_call_llm.return_value = {
            'content': 'I cannot analyze this.',
            'input_tokens': 10, 'output_tokens': 10, 'cost': 0,
        }
        resp = self.client.post('/api/v2/ai/optimize-pipeline/', {
            'pipeline_id': self.pipeline.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(d['suggestions'], {'suggestions': []})
        self.assertEqual(d['raw_content'], 'I cannot analyze this.')

    @mock.patch('gaf_ai.views.call_llm')
    def test_optimize_llm_returns_error_500(self, mock_call_llm):
        mock_call_llm.return_value = {'error': 'all clients failed'}
        resp = self.client.post('/api/v2/ai/optimize-pipeline/', {
            'pipeline_id': self.pipeline.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @mock.patch('gaf_ai.views.call_llm')
    def test_optimize_includes_execution_history(self, mock_call_llm):
        """call_llm is called with execution context from past TaskExecutions."""
        # Create some executions
        for _ in range(3):
            _make_pipeline_execution(self.user, self.task, status='failed', error_message='err')
        mock_call_llm.return_value = {
            'content': '{"suggestions": []}',
            'input_tokens': 1, 'output_tokens': 1, 'cost': 0,
        }
        self.client.post('/api/v2/ai/optimize-pipeline/', {
            'pipeline_id': self.pipeline.id,
        }, format='json')
        # call_llm should have been called with messages including execution history
        args, _ = mock_call_llm.call_args
        messages = args[0] if args else None
        if messages is None:
            self.skipTest('call_llm signature uses kwargs only')
        # The user message should include execution history JSON
        user_msg = messages[-1]['content']
        self.assertIn('execution_history', user_msg)


# ── ai_usage_stats_view tests ───────────────────────────────────
class AIUsageStatsTest(TestCase):
    """GET /api/v2/ai/usage-stats/ — usage statistics aggregation."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='stats_user',
            password='TestPass123!',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.user)

    def test_unauthenticated_denied(self):
        client = APIClient()
        resp = client.get('/api/v2/ai/usage-stats/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_empty_logs_returns_zero_stats(self):
        """When no LLMUsageLog entries exist, returns zero defaults."""
        resp = self.client.get('/api/v2/ai/usage-stats/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(d['total_requests'], 0)
        self.assertEqual(d['total_tokens'], 0)
        self.assertEqual(d['cost_estimate_usd'], 0)
        self.assertEqual(d['by_model'], [])
        self.assertEqual(d['daily_trend'], [])

    def test_stats_with_logs(self):
        """LLMUsageLog entries are aggregated correctly."""
        LLMUsageLog.objects.create(
            user=self.user,
            model_name='gpt-4o-mini',
            input_tokens=100,
            output_tokens=50,
            cost_estimate=0.005,
            call_type='generate_pipeline',
        )
        LLMUsageLog.objects.create(
            user=self.user,
            model_name='gpt-4o-mini',
            input_tokens=200,
            output_tokens=100,
            cost_estimate=0.010,
            call_type='optimize_pipeline',
        )
        LLMUsageLog.objects.create(
            user=self.user,
            model_name='deepseek-chat',
            input_tokens=50,
            output_tokens=25,
            cost_estimate=0.001,
            call_type='qa',
        )
        resp = self.client.get('/api/v2/ai/usage-stats/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(d['total_requests'], 3)
        # 100+50 + 200+100 + 50+25 = 525
        self.assertEqual(d['total_tokens'], 525)
        self.assertEqual(d['avg_tokens_per_request'], 175)
        # by_model: gpt-4o-mini (2 req, 450 tokens), deepseek-chat (1 req, 75 tokens)
        models = {m['model']: m for m in d['by_model']}
        self.assertEqual(models['gpt-4o-mini']['requests'], 2)
        self.assertEqual(models['gpt-4o-mini']['tokens'], 450)
        self.assertEqual(models['deepseek-chat']['requests'], 1)

    def test_days_filter(self):
        """?days=N filters logs to last N days."""
        # Recent log (today)
        LLMUsageLog.objects.create(
            user=self.user, model_name='m1',
            input_tokens=10, output_tokens=5, cost_estimate=0,
        )
        # Old log (30 days ago) — set created_at manually
        old_log = LLMUsageLog.objects.create(
            user=self.user, model_name='m2',
            input_tokens=100, output_tokens=50, cost_estimate=0,
        )
        LLMUsageLog.objects.filter(pk=old_log.pk).update(
            created_at=timezone.now() - timedelta(days=30)
        )

        resp = self.client.get('/api/v2/ai/usage-stats/?days=7')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        # Only 1 recent log within 7 days
        self.assertEqual(resp.data['data']['total_requests'], 1)


# ── ai_chat_view tests (config-missing path only) ───────────────
class AIChatViewTest(TestCase):
    """POST /api/v2/ai/chat/ — config-missing path.

    Full LLM-backed path is integration-tested elsewhere; here we
    test the graceful degrade when LLMConfig is missing/inactive.
    """

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='chat_user',
            password='TestPass123!',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.user)

    def test_unauthenticated_denied(self):
        client = APIClient()
        resp = client.post('/api/v2/ai/chat/', {'message': 'hi'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_message_returns_400(self):
        resp = self.client.post('/api/v2/ai/chat/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_message_returns_400(self):
        resp = self.client.post('/api/v2/ai/chat/', {'message': ''}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_llm_config_returns_config_missing(self):
        """When no LLMConfig exists, returns reply with config_missing=True."""
        from settings.models import LLMConfig
        LLMConfig.objects.all().delete()

        resp = self.client.post('/api/v2/ai/chat/', {'message': 'hello'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertTrue(d['config_missing'])
        self.assertIn('LLM', d['reply'])
        self.assertEqual(d['tokens_used'], 0)

    def test_inactive_llm_config_returns_config_missing(self):
        """When LLMConfig exists but is_active=False, returns config_missing."""
        from settings.models import LLMConfig
        LLMConfig.objects.all().delete()
        LLMConfig.objects.create(
            provider='openai',
            api_key='sk-test',
            is_active=False,
        )

        resp = self.client.post('/api/v2/ai/chat/', {'message': 'hello'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        self.assertTrue(resp.data['data']['config_missing'])

    def test_llm_config_without_api_key_returns_config_missing(self):
        """When LLMConfig has empty api_key, returns config_missing."""
        from settings.models import LLMConfig
        LLMConfig.objects.all().delete()
        LLMConfig.objects.create(
            provider='openai',
            api_key='',
            is_active=True,
        )

        resp = self.client.post('/api/v2/ai/chat/', {'message': 'hello'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        self.assertTrue(resp.data['data']['config_missing'])


# ================================================================
# Anomaly detection views — pure function tests
# Source: test_views_anomaly.py
# ================================================================

class CategorizeErrorTest(TestCase):
    """_categorize_error: keyword-based classification."""

    def test_timeout_keywords(self):
        self.assertEqual(_categorize_error('Operation timed out after 30s'), 'timeout')
        self.assertEqual(_categorize_error('Request timeout'), 'timeout')

    def test_recognition_keywords(self):
        self.assertEqual(_categorize_error('Template not found in screenshot'), 'recognition')
        self.assertEqual(_categorize_error('Image match threshold too high'), 'recognition')

    def test_device_keywords(self):
        self.assertEqual(_categorize_error('ADB connection refused'), 'device')
        self.assertEqual(_categorize_error('Network unreachable'), 'device')

    def test_permission_keywords(self):
        self.assertEqual(_categorize_error('Permission denied'), 'permission')
        self.assertEqual(_categorize_error('access forbidden to resource'), 'permission')

    def test_resource_keywords(self):
        self.assertEqual(_categorize_error('Out of memory (OOM)'), 'resource')
        self.assertEqual(_categorize_error('Process killed: oom'), 'resource')

    def test_unknown_fallback(self):
        self.assertEqual(_categorize_error('Something weird happened'), 'unknown')
        self.assertEqual(_categorize_error(''), 'unknown')

    def test_case_insensitive(self):
        """Keywords match regardless of case."""
        self.assertEqual(_categorize_error('TIMEOUT'), 'timeout')
        self.assertEqual(_categorize_error('Connection Refused'), 'device')


class EstimateSeverityTest(TestCase):
    """_estimate_severity: count + category → severity level."""

    def test_count_based_critical(self):
        """count >= 10 → critical."""
        self.assertEqual(_estimate_severity(10, 'unknown'), 'critical')
        self.assertEqual(_estimate_severity(15, 'recognition'), 'critical')

    def test_count_based_high(self):
        """5 <= count < 10 → high (for non-critical categories)."""
        self.assertEqual(_estimate_severity(5, 'unknown'), 'high')
        self.assertEqual(_estimate_severity(8, 'recognition'), 'high')

    def test_count_based_medium(self):
        """3 <= count < 5 → medium (for non-critical/high categories)."""
        self.assertEqual(_estimate_severity(3, 'unknown'), 'medium')
        self.assertEqual(_estimate_severity(4, 'recognition'), 'medium')

    def test_count_based_low(self):
        """count < 3 → low (for non-critical/high/medium categories)."""
        self.assertEqual(_estimate_severity(1, 'unknown'), 'low')
        self.assertEqual(_estimate_severity(2, 'recognition'), 'low')

    def test_device_category_always_critical(self):
        """device category → critical regardless of count."""
        self.assertEqual(_estimate_severity(1, 'device'), 'critical')
        self.assertEqual(_estimate_severity(2, 'device'), 'critical')

    def test_permission_category_always_critical(self):
        """permission category → critical regardless of count."""
        self.assertEqual(_estimate_severity(1, 'permission'), 'critical')

    def test_resource_category_always_high(self):
        """resource category → high (or critical if count >= 10)."""
        self.assertEqual(_estimate_severity(1, 'resource'), 'high')
        self.assertEqual(_estimate_severity(10, 'resource'), 'critical')


class ExtractPatternsTest(TestCase):
    """_extract_patterns: regex normalization + Counter grouping."""

    def test_empty_input_returns_empty(self):
        self.assertEqual(_extract_patterns([], min_occurrences=2), [])

    def test_single_message_below_threshold(self):
        """Single occurrence < min_occurrences → no patterns."""
        result = _extract_patterns(['error once'], min_occurrences=2)
        self.assertEqual(result, [])

    def test_repeated_messages_grouped(self):
        """Identical messages → 1 pattern with occurrence_count=N."""
        msgs = ['timeout error'] * 3
        result = _extract_patterns(msgs, min_occurrences=2)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['occurrence_count'], 3)
        self.assertEqual(result[0]['pattern_text'], 'timeout error')

    def test_numbers_normalized_to_num(self):
        """Numbers are replaced with <NUM> so similar errors group together."""
        msgs = ['failed after 30s', 'failed after 60s', 'failed after 90s']
        result = _extract_patterns(msgs, min_occurrences=2)
        self.assertEqual(len(result), 1)
        self.assertIn('<NUM>', result[0]['pattern_text'])
        self.assertNotIn('30', result[0]['pattern_text'])

    def test_hashes_normalized(self):
        """Long hex strings are replaced with <HASH>."""
        msgs = [
            'commit abc123def456 failed',
            'commit 7890abcdef1234 failed',
        ]
        result = _extract_patterns(msgs, min_occurrences=2)
        self.assertEqual(len(result), 1)
        self.assertIn('<HASH>', result[0]['pattern_text'])

    def test_paths_normalized(self):
        """File paths are replaced with <PATH>."""
        msgs = [
            'failed to load /app/src/main.py',
            'failed to load /app/src/utils.py',
        ]
        result = _extract_patterns(msgs, min_occurrences=2)
        self.assertEqual(len(result), 1)
        # Note: the regex also strips leading slashes inside the path
        self.assertIn('<PATH>', result[0]['pattern_text'])

    def test_pattern_includes_sample_messages(self):
        """Each pattern includes up to 3 sample original messages."""
        msgs = ['timeout error'] * 5
        result = _extract_patterns(msgs, min_occurrences=2)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]['sample_messages']), 3)

    def test_pattern_includes_first_seen(self):
        """Each pattern has a first_seen field (first original message)."""
        msgs = ['error A', 'error A']
        result = _extract_patterns(msgs, min_occurrences=2)
        self.assertEqual(result[0]['first_seen'], 'error A')

    def test_pattern_includes_category_and_severity(self):
        """Each pattern has category and severity fields."""
        msgs = ['timeout error'] * 5
        result = _extract_patterns(msgs, min_occurrences=2)
        self.assertEqual(result[0]['category'], 'timeout')
        self.assertEqual(result[0]['severity'], 'high')

    def test_patterns_sorted_by_count_descending(self):
        """Most frequent patterns come first."""
        msgs = ['rare error', 'common error', 'common error', 'common error']
        result = _extract_patterns(msgs, min_occurrences=1)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['occurrence_count'], 3)
        self.assertEqual(result[1]['occurrence_count'], 1)

    def test_max_20_patterns_returned(self):
        """Pattern list is capped at 20 entries."""
        # Generate 25 distinct patterns with 2 occurrences each.
        # Use non-numeric, non-hex labels so normalization doesn't
        # collapse them (digits → <NUM>, hex → <HASH>).
        labels = ['alpha', 'beta', 'gamma', 'delta', 'epsilon',
                  'zeta', 'eta', 'theta', 'iota', 'kappa',
                  'lambda', 'mu', 'nu', 'xi', 'omicron',
                  'pi', 'rho', 'sigma', 'tau', 'upsilon',
                  'phi', 'chi', 'psi', 'omega', 'final']
        msgs = []
        for label in labels:
            msgs.append(f'distinct error {label} variant')
            msgs.append(f'distinct error {label} variant')
        result = _extract_patterns(msgs, min_occurrences=2)
        self.assertEqual(len(result), 20)

    def test_pattern_text_truncated_to_200_chars(self):
        """Long pattern text is truncated to 200 chars."""
        long_msg = 'x' * 300
        msgs = [long_msg, long_msg]
        result = _extract_patterns(msgs, min_occurrences=2)
        self.assertEqual(len(result[0]['pattern_text']), 200)

    def test_min_occurrences_filter(self):
        """Patterns below min_occurrences are excluded."""
        msgs = ['frequent', 'frequent', 'rare']
        result = _extract_patterns(msgs, min_occurrences=2)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['pattern_text'], 'frequent')


# ── View integration tests ───────────────────────────────────────
class AnomalyDetectionViewTest(TestCase):
    """POST /api/v2/ai/anomaly-detection/ — integration with DB + LLM."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='anomaly_user',
            password='TestPass123!',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.user)
        self.task = _make_task()

    def test_unauthenticated_denied(self):
        """Anonymous request → 401."""
        client = APIClient()
        resp = client.post('/api/v2/ai/anomaly-detection/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_failed_executions_returns_empty_patterns(self):
        """When user has no failed executions, returns empty pattern list."""
        resp = self.client.post('/api/v2/ai/anomaly-detection/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(d['patterns'], [])
        self.assertEqual(d['total_analyzed'], 0)
        self.assertEqual(d['stats']['failed_count'], 0)

    @mock.patch('gaf_ai.views_anomaly.call_llm')
    def test_failed_executions_extract_patterns(self, mock_call_llm):
        """Failed executions with repeated errors → pattern extracted."""
        mock_call_llm.return_value = {
            'content': 'Root cause: timeout. Fix: increase timeout.',
            'model': 'gpt-4o-mini',
        }
        # Create 3 failed executions with similar error messages
        for _ in range(3):
            _make_execution(
                self.task, self.user, status='failed',
                error_message='timeout after 30s',
            )
        # Create 1 success execution (should be counted in total_count)
        _make_execution(
            self.task, self.user, status='success',
            error_message='',
        )

        resp = self.client.post('/api/v2/ai/anomaly-detection/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(len(d['patterns']), 1)
        self.assertEqual(d['patterns'][0]['occurrence_count'], 3)
        self.assertEqual(d['patterns'][0]['category'], 'timeout')
        self.assertEqual(d['stats']['failed_count'], 3)
        self.assertEqual(d['stats']['total_count'], 4)
        # LLM analysis should be present (call_llm was mocked)
        self.assertIsNotNone(d['llm_analysis'])
        mock_call_llm.assert_called_once()

    @mock.patch('gaf_ai.views_anomaly.call_llm')
    def test_llm_failure_graceful_degrade(self, mock_call_llm):
        """When call_llm raises, llm_analysis is None but patterns still returned."""
        mock_call_llm.side_effect = Exception('LLM unavailable')
        for _ in range(2):
            _make_execution(
                self.task, self.user, status='failed',
                error_message='permission denied',
            )

        resp = self.client.post('/api/v2/ai/anomaly-detection/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(len(d['patterns']), 1)
        self.assertIsNone(d['llm_analysis'])

    @mock.patch('gaf_ai.views_anomaly.call_llm')
    def test_llm_returns_error_no_analysis(self, mock_call_llm):
        """When call_llm returns {'error': ...}, llm_analysis stays None."""
        mock_call_llm.return_value = {'error': 'all clients failed'}
        for _ in range(2):
            _make_execution(
                self.task, self.user, status='failed',
                error_message='connection refused',
            )

        resp = self.client.post('/api/v2/ai/anomaly-detection/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        self.assertIsNone(resp.data['data']['llm_analysis'])

    def test_days_filter_excludes_old_failures(self):
        """days=1 excludes failures older than 1 day."""
        # Recent failure (within 1 day)
        _make_execution(
            self.task, self.user, status='failed',
            error_message='recent error', days_ago=0,
        )
        # Old failure (3 days ago)
        _make_execution(
            self.task, self.user, status='failed',
            error_message='old error', days_ago=3,
        )

        resp = self.client.post(
            '/api/v2/ai/anomaly-detection/',
            {'days': 1, 'min_occurrences': 1},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        # Only 1 failure within 1 day, so total_analyzed=1
        self.assertEqual(resp.data['data']['total_analyzed'], 1)

    def test_user_isolation(self):
        """Failures from other users are not counted."""
        other_user = User.objects.create_user(
            username='other_user',
            password='TestPass123!',
            role=User.Role.ADMIN,
        )
        # Other user's failures
        for _ in range(5):
            _make_execution(
                self.task, other_user, status='failed',
                error_message='other user timeout',
            )
        # My success
        _make_execution(
            self.task, self.user, status='success',
            error_message='',
        )

        resp = self.client.post(
            '/api/v2/ai/anomaly-detection/',
            {'min_occurrences': 1},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        # I have 0 failures
        self.assertEqual(d['stats']['failed_count'], 0)
        self.assertEqual(d['patterns'], [])

    def test_failure_rate_calculation(self):
        """stats.failure_rate is computed as failed/total*100."""
        for _ in range(3):
            _make_execution(self.task, self.user, status='failed', error_message='err')
        for _ in range(7):
            _make_execution(self.task, self.user, status='success', error_message='')

        resp = self.client.post(
            '/api/v2/ai/anomaly-detection/',
            {'min_occurrences': 1},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        stats = resp.data['data']['stats']
        self.assertEqual(stats['failed_count'], 3)
        self.assertEqual(stats['total_count'], 10)
        self.assertEqual(stats['failure_rate'], 30.0)

    def test_min_occurrences_param_respected(self):
        """min_occurrences=3 excludes patterns with only 2 occurrences."""
        for _ in range(2):
            _make_execution(
                self.task, self.user, status='failed',
                error_message='rare error',
            )

        resp = self.client.post(
            '/api/v2/ai/anomaly-detection/',
            {'min_occurrences': 3},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        # 2 occurrences < min_occurrences=3 → no patterns
        self.assertEqual(resp.data['data']['patterns'], [])

    def test_executions_without_error_message_skipped(self):
        """Failed executions with empty error_message are not analyzed."""
        _make_execution(
            self.task, self.user, status='failed',
            error_message='',  # empty
        )

        resp = self.client.post(
            '/api/v2/ai/anomaly-detection/',
            {'min_occurrences': 1},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        # failed_count counts all failed (1), but total_analyzed only
        # counts those with non-empty error_message (0)
        self.assertEqual(d['stats']['failed_count'], 1)
        self.assertEqual(d['total_analyzed'], 0)
        self.assertEqual(d['patterns'], [])

    def test_summary_string_includes_counts(self):
        """Response summary mentions day count and pattern count."""
        for _ in range(2):
            _make_execution(
                self.task, self.user, status='failed',
                error_message='recurring error',
            )

        resp = self.client.post(
            '/api/v2/ai/anomaly-detection/',
            {'days': 7, 'min_occurrences': 1},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        summary = resp.data['data']['summary']
        self.assertIn('7', summary)
        self.assertIn('1', summary)  # 1 pattern


# ================================================================
# Skill views — CustomSkill CRUD
# Source: test_views_skill.py
# ================================================================

class CustomSkillCRUDTest(TestCase):
    """CRUD operations on /api/v2/ai/custom-skills/."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='skill_user',
            password='TestPass123!',
            role=User.Role.ADMIN,
        )
        self.other_user = User.objects.create_user(
            username='other_skill_user',
            password='TestPass123!',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.user)

    # ── Create ─────────────────────────────────────────────────
    def test_create_skill(self):
        """POST creates a skill owned by the authenticated user."""
        resp = self.client.post('/api/v2/ai/custom-skills/', {
            'id': 'new-skill',
            'name': 'New Skill',
            'description': 'desc',
            'category': 'recognition',
            'yaml_content': 'version: "1"',
            'is_active': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(d['name'], 'New Skill')
        self.assertEqual(d['created_by'], self.user.id)
        # DB should reflect creation
        skill = CustomSkill.objects.get(id='new-skill')
        self.assertEqual(skill.created_by, self.user)
        self.assertEqual(skill.category, 'recognition')

    def test_create_skill_sets_created_by_automatically(self):
        """perform_create sets created_by from request.user, not request body."""
        resp = self.client.post('/api/v2/ai/custom-skills/', {
            'id': 'auto-owner',
            'name': 'Auto Owner',
            'yaml_content': 'version: "1"',
            'created_by': self.other_user.id,  # attempt to spoof
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        # created_by is read_only, so it's ignored and set from request.user
        self.assertEqual(resp.data['data']['created_by'], self.user.id)

    def test_create_skill_missing_required_fields(self):
        """POST without required fields → 400."""
        resp = self.client.post('/api/v2/ai/custom-skills/', {
            'description': 'missing name and id',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # ── Read (list) ────────────────────────────────────────────
    def test_list_skills(self):
        """GET list returns only the authenticated user's skills."""
        _make_skill(self.user, id='my-skill-1')
        _make_skill(self.user, id='my-skill-2', name='Second Skill')
        _make_skill(self.other_user, id='other-skill', name='Other Skill')

        resp = self.client.get('/api/v2/ai/custom-skills/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        inner = resp.data['data']
        # Could be paginated or plain list
        results = inner.get('results', inner)
        self.assertEqual(len(results), 2)
        skill_ids = [r['id'] for r in results]
        self.assertIn('my-skill-1', skill_ids)
        self.assertIn('my-skill-2', skill_ids)
        self.assertNotIn('other-skill', skill_ids)

    def test_list_skills_empty_for_new_user(self):
        """GET list returns empty for user with no skills."""
        resp = self.client.get('/api/v2/ai/custom-skills/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        inner = resp.data['data']
        results = inner.get('results', inner)
        self.assertEqual(len(results), 0)

    def test_list_filter_by_category(self):
        """GET ?category=recognition filters by category."""
        _make_skill(self.user, id='s1', category='analysis')
        _make_skill(self.user, id='s2', category='recognition')
        _make_skill(self.user, id='s3', category='recognition')

        resp = self.client.get('/api/v2/ai/custom-skills/?category=recognition')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        inner = resp.data['data']
        results = inner.get('results', inner)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r['category'], 'recognition')

    def test_list_filter_by_is_active(self):
        """GET ?is_active=true filters by active state."""
        _make_skill(self.user, id='active1', is_active=True)
        _make_skill(self.user, id='inactive1', is_active=False)

        resp = self.client.get('/api/v2/ai/custom-skills/?is_active=true')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        inner = resp.data['data']
        results = inner.get('results', inner)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]['is_active'])

    # ── Read (retrieve) ────────────────────────────────────────
    def test_retrieve_skill(self):
        """GET /<id>/ returns skill detail."""
        _make_skill(self.user, id='detail-skill', name='Detail Skill')

        resp = self.client.get('/api/v2/ai/custom-skills/detail-skill/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(d['id'], 'detail-skill')
        self.assertEqual(d['name'], 'Detail Skill')
        self.assertIn('yaml_content', d)
        self.assertIn('created_by_name', d)

    def test_retrieve_other_users_skill_404(self):
        """GET /<id>/ for another user's skill → 404 (queryset filtered)."""
        _make_skill(self.other_user, id='private-skill')

        resp = self.client.get('/api/v2/ai/custom-skills/private-skill/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_nonexistent_skill_404(self):
        """GET /<nonexistent-id>/ → 404."""
        resp = self.client.get('/api/v2/ai/custom-skills/does-not-exist/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ── Update ─────────────────────────────────────────────────
    def test_update_skill_full_put(self):
        """PUT replaces all fields."""
        _make_skill(self.user, id='put-skill', name='Original')

        resp = self.client.put('/api/v2/ai/custom-skills/put-skill/', {
            'id': 'put-skill',
            'name': 'Updated Name',
            'description': 'updated desc',
            'category': 'recognition',
            'yaml_content': 'version: "2"',
            'is_active': False,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(d['name'], 'Updated Name')
        self.assertFalse(d['is_active'])
        # Verify DB
        skill = CustomSkill.objects.get(id='put-skill')
        self.assertEqual(skill.name, 'Updated Name')
        self.assertFalse(skill.is_active)

    def test_update_skill_partial_patch(self):
        """PATCH updates only the fields provided."""
        _make_skill(self.user, id='patch-skill', name='Original', is_active=True)

        resp = self.client.patch('/api/v2/ai/custom-skills/patch-skill/', {
            'is_active': False,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertFalse(d['is_active'])
        # Other fields unchanged
        self.assertEqual(d['name'], 'Original')

    def test_update_default_partial_true(self):
        """PUT also uses partial=True (frontend sends only changed fields)."""
        _make_skill(self.user, id='put-partial', name='Original', is_active=True)

        # Even PUT with only one field should work (custom update() forces partial)
        resp = self.client.put('/api/v2/ai/custom-skills/put-partial/', {
            'name': 'Only Name Changed',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        d = resp.data['data']
        self.assertEqual(d['name'], 'Only Name Changed')
        # is_active unchanged
        self.assertTrue(d['is_active'])

    def test_update_other_users_skill_404(self):
        """PUT/PATCH on another user's skill → 404."""
        _make_skill(self.other_user, id='others-skill')

        resp = self.client.put('/api/v2/ai/custom-skills/others-skill/', {
            'name': 'Hacked',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # ── Delete ─────────────────────────────────────────────────
    def test_delete_skill(self):
        """DELETE removes the skill."""
        _make_skill(self.user, id='delete-skill')

        resp = self.client.delete('/api/v2/ai/custom-skills/delete-skill/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(CustomSkill.objects.filter(id='delete-skill').exists())

    def test_delete_other_users_skill_404(self):
        """DELETE on another user's skill → 404."""
        _make_skill(self.other_user, id='protected-skill')

        resp = self.client.delete('/api/v2/ai/custom-skills/protected-skill/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        # Skill still exists
        self.assertTrue(CustomSkill.objects.filter(id='protected-skill').exists())

    def test_delete_nonexistent_404(self):
        """DELETE on nonexistent id → 404."""
        resp = self.client.delete('/api/v2/ai/custom-skills/ghost/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class CustomSkillPermissionTest(TestCase):
    """Authentication and authorization checks."""

    def test_unauthenticated_list_denied(self):
        """Anonymous GET → 401."""
        client = APIClient()
        resp = client.get('/api/v2/ai/custom-skills/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_create_denied(self):
        """Anonymous POST → 401."""
        client = APIClient()
        resp = client.post('/api/v2/ai/custom-skills/', {
            'id': 'anon', 'name': 'Anon', 'yaml_content': 'x',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_two_users_isolated(self):
        """User A cannot see/edit User B's skills."""
        client_a = APIClient()
        client_b = APIClient()
        user_a = User.objects.create_user(
            username='user_a', password='Pass123!', role=User.Role.ADMIN,
        )
        user_b = User.objects.create_user(
            username='user_b', password='Pass123!', role=User.Role.ADMIN,
        )
        client_a.force_authenticate(user=user_a)
        client_b.force_authenticate(user=user_b)

        # A creates a skill
        resp = client_a.post('/api/v2/ai/custom-skills/', {
            'id': 'a-skill', 'name': 'A Skill', 'yaml_content': 'x',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        # B's list should be empty
        resp = client_b.get('/api/v2/ai/custom-skills/')
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        inner = resp.data['data']
        results = inner.get('results', inner)
        self.assertEqual(len(results), 0)

        # B cannot retrieve A's skill
        resp = client_b.get('/api/v2/ai/custom-skills/a-skill/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        # B cannot delete A's skill
        resp = client_b.delete('/api/v2/ai/custom-skills/a-skill/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(CustomSkill.objects.filter(id='a-skill').exists())


class CustomSkillSerializerTest(TestCase):
    """Serializer-level behavior (validated via API)."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='serializer_user',
            password='TestPass123!',
            role=User.Role.ADMIN,
        )
        self.client.force_authenticate(user=self.user)

    def test_created_by_name_in_response(self):
        """Response includes created_by_name (username string)."""
        resp = self.client.post('/api/v2/ai/custom-skills/', {
            'id': 'named-skill',
            'name': 'Named Skill',
            'yaml_content': 'x',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        self.assertEqual(resp.data['data']['created_by_name'], 'serializer_user')

    def test_created_by_is_read_only(self):
        """created_by is read_only — cannot be set via POST body."""
        other = User.objects.create_user(
            username='other_user', password='Pass123!', role=User.Role.ADMIN,
        )
        resp = self.client.post('/api/v2/ai/custom-skills/', {
            'id': 'owner-test',
            'name': 'Owner Test',
            'yaml_content': 'x',
            'created_by': other.id,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        # Should be set to self.user, not other
        self.assertEqual(resp.data['data']['created_by'], self.user.id)

    def test_timestamps_are_read_only(self):
        """created_at and updated_at are read_only."""
        _make_skill(self.user, id='ts-skill')

        resp = self.client.patch('/api/v2/ai/custom-skills/ts-skill/', {
            'name': 'Updated',
            'created_at': '2020-01-01T00:00:00Z',
            'updated_at': '2020-01-01T00:00:00Z',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # UnifiedResponseMiddleware 包装为 {code, message, data}
        # Timestamps should not be 2020-01-01
        self.assertNotIn('2020-01-01', resp.data['data']['created_at'])
