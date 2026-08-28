"""Tests for AI FeatureFlag helpers and gates (S5 Task A1 / P2-5).

Covers:
- ``is_ai_assistant_enabled`` / ``is_langgraph_agent_enabled`` default
  to ``True`` when the FeatureFlag row is missing (fail-open).
- AskView returns 503 when ``ai_assistant_enabled=False``.
- AskView returns 201 (normal flow) when ``ai_assistant_enabled=True``.
- ``build_log_analysis_agent()`` raises RuntimeError when
  ``langgraph_agent_enabled=False``.
- ``build_log_analysis_agent()`` builds the agent (mocked LLM) when the
  flag is enabled.
- The 0006 data migration is idempotent: running the forward function
  twice produces exactly 2 FeatureFlag rows, not 4.
"""
from unittest import mock

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from settings.models import FeatureFlag

from accounts.models import User
from gaf_ai.feature_flags import (
    AI_ASSISTANT_FLAG,
    LANGGRAPH_AGENT_FLAG,
    is_ai_assistant_enabled,
    is_langgraph_agent_enabled,
)


# ── Flag default / helper tests ─────────────────────────────────
class FeatureFlagHelperTest(TestCase):
    """Tests for the is_*_enabled helpers in ai.feature_flags."""

    def test_ai_assistant_defaults_enabled_when_flag_missing(self):
        """When no FeatureFlag row exists, the helper returns True (fail-open)."""
        FeatureFlag.objects.filter(name=AI_ASSISTANT_FLAG).delete()
        self.assertTrue(is_ai_assistant_enabled())

    def test_langgraph_defaults_enabled_when_flag_missing(self):
        """When no FeatureFlag row exists, the helper returns True (fail-open)."""
        FeatureFlag.objects.filter(name=LANGGRAPH_AGENT_FLAG).delete()
        self.assertTrue(is_langgraph_agent_enabled())

    def test_ai_assistant_returns_false_when_disabled(self):
        FeatureFlag.objects.update_or_create(
            name=AI_ASSISTANT_FLAG, defaults={'enabled': False}
        )
        self.assertFalse(is_ai_assistant_enabled())

    def test_ai_assistant_returns_true_when_enabled(self):
        FeatureFlag.objects.update_or_create(
            name=AI_ASSISTANT_FLAG, defaults={'enabled': True}
        )
        self.assertTrue(is_ai_assistant_enabled())

    def test_langgraph_returns_false_when_disabled(self):
        FeatureFlag.objects.update_or_create(
            name=LANGGRAPH_AGENT_FLAG, defaults={'enabled': False}
        )
        self.assertFalse(is_langgraph_agent_enabled())

    def test_langgraph_returns_true_when_enabled(self):
        FeatureFlag.objects.update_or_create(
            name=LANGGRAPH_AGENT_FLAG, defaults={'enabled': True}
        )
        self.assertTrue(is_langgraph_agent_enabled())


# ── AskView FeatureFlag gate tests ──────────────────────────────
class AskViewFeatureFlagTest(TestCase):
    """AskView — POST /api/v2/qa/ask/ respects the ai_assistant_enabled flag.

    The flag is checked after serializer validation but before any rate
    limit / budget / LLM call, so a disabled flag short-circuits to 503
    without consuming budget or hitting the LLM router.
    """

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='ff_admin',
            password='AdminPass123!',
            role=User.Role.ADMIN,
        )
        resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'ff_admin',
            'password': 'AdminPass123!',
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 (P0-12, 2026-07-28): 修复 token 取值路径 (unified_response 信封)。
        _token = resp.data.get('data', {}).get('access') or resp.data.get('access')
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {_token}"
        )

    def test_disabled_flag_returns_503(self):
        """When ai_assistant_enabled=False, AskView returns 503 with error JSON."""
        FeatureFlag.objects.update_or_create(
            name=AI_ASSISTANT_FLAG, defaults={'enabled': False}
        )
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'hello',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        # UnifiedResponseMiddleware 包装错误响应为 {code, message, data}
        self.assertEqual(resp.data['message'], 'AI assistant is disabled by feature flag')

    @mock.patch('gaf_ai.llm_service.call_llm')
    def test_enabled_flag_allows_normal_flow(self, mock_call_llm):
        """When ai_assistant_enabled=True, AskView proceeds to LLM call and returns 201."""
        mock_call_llm.return_value = {
            'content': 'mock answer',
            'input_tokens': 5,
            'output_tokens': 5,
            'model': 'gpt-4o-mini',
            'cost': 0.0,
            'route': 'preferred',
        }
        FeatureFlag.objects.update_or_create(
            name=AI_ASSISTANT_FLAG, defaults={'enabled': True}
        )
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'hello',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        # UnifiedResponseMiddleware 包装成功响应为 {code, message, data}，业务数据在 data 内层
        self.assertEqual(resp.data['data']['answer'], 'mock answer')
        # Confirm the LLM was actually invoked (flag did not short-circuit).
        mock_call_llm.assert_called_once()

    @mock.patch('gaf_ai.llm_service.call_llm')
    def test_missing_flag_allows_normal_flow(self, mock_call_llm):
        """When the flag row is missing, AskView proceeds (fail-open default)."""
        mock_call_llm.return_value = {
            'content': 'mock answer',
            'input_tokens': 5,
            'output_tokens': 5,
            'model': 'gpt-4o-mini',
            'cost': 0.0,
            'route': 'preferred',
        }
        FeatureFlag.objects.filter(name=AI_ASSISTANT_FLAG).delete()
        resp = self.client.post('/api/v2/qa/ask/', {
            'question': 'hello',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        mock_call_llm.assert_called_once()


# ── build_log_analysis_agent FeatureFlag gate tests ─────────────
class BuildAgentFeatureFlagTest(TestCase):
    """build_log_analysis_agent() respects the langgraph_agent_enabled flag."""

    def test_disabled_flag_raises_runtime_error(self):
        """When langgraph_agent_enabled=False, build raises RuntimeError before LLM."""
        FeatureFlag.objects.update_or_create(
            name=LANGGRAPH_AGENT_FLAG, defaults={'enabled': False}
        )
        with self.assertRaises(RuntimeError) as ctx:
            from gaf_ai.agent.graph import build_log_analysis_agent
            build_log_analysis_agent()
        self.assertIn('langgraph_agent_enabled', str(ctx.exception))

    @mock.patch('gaf_ai.agent.graph.build_agent_llm')
    def test_enabled_flag_builds_agent(self, mock_build_llm):
        """When langgraph_agent_enabled=True, build proceeds (LLM is mocked)."""
        # create_agent requires a real-ish LLM object; mock it.
        mock_build_llm.return_value = mock.MagicMock(name='fake_llm')
        FeatureFlag.objects.update_or_create(
            name=LANGGRAPH_AGENT_FLAG, defaults={'enabled': True}
        )
        from gaf_ai.agent.graph import build_log_analysis_agent
        agent = build_log_analysis_agent()
        self.assertIsNotNone(agent)
        mock_build_llm.assert_called_once()

    @mock.patch('gaf_ai.agent.graph.build_agent_llm')
    def test_missing_flag_builds_agent(self, mock_build_llm):
        """When the flag row is missing, build proceeds (fail-open default)."""
        mock_build_llm.return_value = mock.MagicMock(name='fake_llm')
        FeatureFlag.objects.filter(name=LANGGRAPH_AGENT_FLAG).delete()
        from gaf_ai.agent.graph import build_log_analysis_agent
        agent = build_log_analysis_agent()
        self.assertIsNotNone(agent)
        mock_build_llm.assert_called_once()


# ── Migration idempotency test ──────────────────────────────────
class MigrationIdempotencyTest(TestCase):
    """The 0006 data migration must be safe to run multiple times.

    Calls the forward RunPython function directly with the apps registry
    so we do not need to roll and re-apply the migration. The migration
    module filename starts with a digit (Django convention), so it is
    loaded via importlib.util instead of a normal import statement.
    """

    @staticmethod
    def _load_migration_module():
        """Load settings/migrations/0006_preset_ai_feature_flags.py as a module.

        Python identifiers cannot start with a digit, so a regular
        ``from settings.migrations.0006_... import ...`` is a SyntaxError.
        Django itself loads migrations by file path; we mirror that here.
        """
        import importlib.util
        from pathlib import Path

        migration_path = (
            Path(__file__).resolve().parent.parent.parent
            / 'settings' / 'migrations' / '0006_preset_ai_feature_flags.py'
        )
        spec = importlib.util.spec_from_file_location(
            'settings_migrations_0006_preset_ai_feature_flags',
            migration_path,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_running_preset_twice_yields_two_rows(self):
        from django.apps import apps as django_apps
        from django.db import connection

        migration = self._load_migration_module()

        # Start clean — no AI flags in the DB.
        FeatureFlag.objects.filter(
            name__in=[AI_ASSISTANT_FLAG, LANGGRAPH_AGENT_FLAG]
        ).delete()

        # Run the forward function twice (simulating re-apply / rerun).
        # RunPython forward functions accept (apps, schema_editor); the
        # function only uses apps.get_model('settings', 'FeatureFlag'),
        # which the live django apps registry satisfies.
        migration.preset_ai_feature_flags(django_apps, connection.schema_editor())
        migration.preset_ai_feature_flags(django_apps, connection.schema_editor())

        rows = FeatureFlag.objects.filter(
            name__in=[AI_ASSISTANT_FLAG, LANGGRAPH_AGENT_FLAG]
        ).order_by('name')
        self.assertEqual(rows.count(), 2)
        names = [r.name for r in rows]
        self.assertEqual(names, [AI_ASSISTANT_FLAG, LANGGRAPH_AGENT_FLAG])
        # Verify the seeded defaults.
        ai_flag = FeatureFlag.objects.get(name=AI_ASSISTANT_FLAG)
        self.assertTrue(ai_flag.enabled)
        self.assertEqual(ai_flag.description, 'Enable AI assistant QA endpoint')
        lg_flag = FeatureFlag.objects.get(name=LANGGRAPH_AGENT_FLAG)
        self.assertTrue(lg_flag.enabled)
        self.assertEqual(lg_flag.description, 'Enable LangGraph agent deep analysis')
