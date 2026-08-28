"""Skill executor unit tests.

Spec v3 §3.1 — S1 (AI 架构缺陷修复) test coverage.

Covers:
- execute_skill() happy path (YAML parse → context collect → LLM call → result)
- _render_template() variable substitution
- _parse_output() JSON / text / markdown-code-block parsing
- _extract_param_defaults() parameter extraction
- Budget check (TokenUsageTracker.check_budget integration)
- Invalid YAML handling
- LLM call failure handling
- LLM error response handling
- execute API endpoint (POST /api/v2/skills/skills/{id}/execute/)
- Disabled skill rejection
- Dead code activation: build_skill_context() + TokenUsageTracker.check_budget()

Mocks:
- ai.llm_service.call_llm — mocked to avoid real API calls
- ai.token_tracker.TokenUsageTracker.check_budget — mocked in budget tests
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from skills.executor import (
    SkillExecutionError,
    _extract_param_defaults,
    _parse_output,
    _render_template,
    execute_skill,
)
from skills.models import SkillDefinition

# ── Test fixtures ───────────────────────────────────────────────

VALID_ERROR_DIAGNOSIS_YAML = """\
name: error_diagnosis
version: "1.0.0"
description: "Test skill for error diagnosis"
model: deepseek-chat
is_builtin: true
applicable_scenarios:
  - error
system_prompt: |
  You are an error diagnosis assistant.
user_prompt_template: |
  Task: {{task_name}}
  Error: {{error_message}}
  Log: {{log_content}}
context:
  collect_screenshot: false
  collect_log: true
  collect_task_config: false
  collect_device_info: false
  max_log_lines: 50
parameters:
  temperature:
    type: float
    default: 0.5
    min: 0.0
    max: 1.0
  max_tokens:
    type: integer
    default: 2000
output:
  format: json
  schema:
    type: object
    properties:
      error_type:
        type: string
cost_control:
  max_tokens_per_call: 4000
  max_calls_per_day: 30
  max_cost_per_day: 0.5
"""

INVALID_YAML = "name: test\n  bad: indentation: here\n"

NON_DICT_YAML = "- item1\n- item2\n"

TEXT_OUTPUT_YAML = """\
name: text_skill
version: "1.0"
description: "Text output skill"
model: gpt-4o-mini
system_prompt: "You are helpful."
user_prompt_template: "Question: {{question}}"
output:
  format: text
"""


def make_skill(name='test_executor_skill', yaml_content=VALID_ERROR_DIAGNOSIS_YAML):
    """Create a SkillDefinition for testing."""
    return SkillDefinition.objects.create(
        name=name,
        description='Test skill for executor',
        yaml_content=yaml_content,
        version='1.0.0',
        applicable_scenarios=['error'],
        is_builtin=False,
        is_enabled=True,
    )


def mock_llm_response(content='{"error_type": "timeout", "root_cause": "slow"}',
                      model='deepseek-chat',
                      route='preferred'):
    """Build a mock call_llm return value."""
    return {
        'content': content,
        'input_tokens': 120,
        'output_tokens': 80,
        'model': model,
        'cost': 0.0002,
        'route': route,
    }


# ── Template rendering tests ────────────────────────────────────

class RenderTemplateTest(TestCase):
    """Tests for _render_template()."""

    def test_simple_substitution(self):
        result = _render_template("Hello {{name}}!", {'name': 'World'})
        self.assertEqual(result, "Hello World!")

    def test_multiple_variables(self):
        result = _render_template(
            "{{a}} + {{b}} = {{c}}",
            {'a': '1', 'b': '2', 'c': '3'},
        )
        self.assertEqual(result, "1 + 2 = 3")

    def test_missing_variable_replaced_with_empty(self):
        result = _render_template("Hello {{name}}!", {})
        self.assertEqual(result, "Hello !")

    def test_none_value_replaced_with_empty(self):
        result = _render_template("Val: {{x}}", {'x': None})
        self.assertEqual(result, "Val: ")

    def test_dict_value_serialized_as_json(self):
        result = _render_template("Config: {{cfg}}", {'cfg': {'key': 'val'}})
        self.assertIn('"key"', result)
        self.assertIn('"val"', result)

    def test_list_value_serialized_as_json(self):
        result = _render_template("Items: {{items}}", {'items': [1, 2, 3]})
        self.assertIn('1', result)
        self.assertIn('2', result)
        self.assertIn('3', result)

    def test_no_variables_returns_unchanged(self):
        result = _render_template("plain text", {})
        self.assertEqual(result, "plain text")

    def test_underscore_variables(self):
        result = _render_template("{{task_name}}", {'task_name': 'BD2_daily'})
        self.assertEqual(result, "BD2_daily")


# ── Output parsing tests ────────────────────────────────────────

class ParseOutputTest(TestCase):
    """Tests for _parse_output()."""

    def test_json_direct_parse(self):
        content = '{"error_type": "timeout", "confidence": 0.9}'
        result = _parse_output(content, {'format': 'json'})
        self.assertEqual(result['error_type'], 'timeout')
        self.assertEqual(result['confidence'], 0.9)

    def test_json_markdown_code_block(self):
        content = 'Here is the analysis:\n```json\n{"error_type": "oom"}\n```'
        result = _parse_output(content, {'format': 'json'})
        self.assertEqual(result['error_type'], 'oom')

    def test_json_invalid_returns_parse_error(self):
        content = 'not valid json at all'
        result = _parse_output(content, {'format': 'json'})
        self.assertIn('_parse_error', result)
        self.assertEqual(result['raw'], content)

    def test_text_format_returns_text_key(self):
        content = 'Some plain text response'
        result = _parse_output(content, {'format': 'text'})
        self.assertEqual(result, {'text': content})

    def test_default_format_is_text(self):
        content = 'Default text'
        result = _parse_output(content, {})
        self.assertEqual(result, {'text': content})

    def test_json_array_in_code_block(self):
        content = '```json\n["item1", "item2"]\n```'
        result = _parse_output(content, {'format': 'json'})
        self.assertEqual(result, ['item1', 'item2'])


# ── Parameter defaults extraction tests ─────────────────────────

class ExtractParamDefaultsTest(TestCase):
    """Tests for _extract_param_defaults()."""

    def test_extract_simple_defaults(self):
        params = {
            'temperature': {'type': 'float', 'default': 0.5, 'min': 0.0, 'max': 1.0},
            'max_tokens': {'type': 'integer', 'default': 2000},
        }
        defaults = _extract_param_defaults(params)
        self.assertEqual(defaults['temperature'], 0.5)
        self.assertEqual(defaults['max_tokens'], 2000)

    def test_skip_params_without_default(self):
        params = {
            'temperature': {'type': 'float', 'min': 0.0, 'max': 1.0},
            'max_tokens': {'type': 'integer', 'default': 2000},
        }
        defaults = _extract_param_defaults(params)
        self.assertNotIn('temperature', defaults)
        self.assertEqual(defaults['max_tokens'], 2000)

    def test_empty_params(self):
        self.assertEqual(_extract_param_defaults({}), {})

    def test_non_dict_param_spec_skipped(self):
        params = {
            'bad_param': 'not a dict',
            'good_param': {'default': 'ok'},
        }
        defaults = _extract_param_defaults(params)
        self.assertEqual(defaults, {'good_param': 'ok'})


# ── execute_skill() integration tests ───────────────────────────

class ExecuteSkillTest(TestCase):
    """Tests for execute_skill() with mocked LLM."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='executor_admin',
            password='admin123456',
            role=User.Role.ADMIN,
        )

    def setUp(self):
        self.skill = make_skill()
        self.task_context = {
            'task_name': 'BD2_daily_login',
            'error_message': 'Template match failed: login_button not found',
            'log': 'Step 1: navigate to login\nStep 2: match template\nFailed: not found\n',
        }

    @patch('skills.executor.call_llm')
    @patch('skills.executor.get_token_tracker')
    def test_happy_path_json_output(self, mock_tracker_fn, mock_call_llm):
        """Full execution: YAML parse → context → LLM → parse → result."""
        mock_tracker = MagicMock()
        mock_tracker.check_budget.return_value = True
        mock_tracker_fn.return_value = mock_tracker
        mock_call_llm.return_value = mock_llm_response()

        result = execute_skill(self.skill, self.task_context, self.admin)

        # Verify result structure
        self.assertEqual(result['skill_name'], 'test_executor_skill')
        self.assertEqual(result['skill_id'], self.skill.id)
        self.assertEqual(result['model'], 'deepseek-chat')
        self.assertEqual(result['route'], 'preferred')
        self.assertIn('error_type', result['parsed_output'])
        self.assertEqual(result['parsed_output']['error_type'], 'timeout')
        self.assertEqual(result['usage']['input_tokens'], 120)
        self.assertEqual(result['usage']['output_tokens'], 80)

        # Verify LLM was called with correct messages
        mock_call_llm.assert_called_once()
        call_kwargs = mock_call_llm.call_args.kwargs
        messages = call_kwargs['messages']
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]['role'], 'system')
        self.assertEqual(messages[1]['role'], 'user')
        # Template variables should be substituted in user message
        self.assertIn('BD2_daily_login', messages[1]['content'])
        self.assertIn('Template match failed', messages[1]['content'])

        # Verify budget check was called (activates dead code)
        mock_tracker.check_budget.assert_called_once()
        call_args = mock_tracker.check_budget.call_args
        self.assertEqual(call_args.args[0], self.admin.id)

        # Verify usage recording (activates dead code)
        mock_tracker.record.assert_called_once()
        record_args = mock_tracker.record.call_args.kwargs
        self.assertEqual(record_args['call_type'], 'skill_test_executor_skill')
        self.assertEqual(record_args['route'], 'preferred')

    @patch('skills.executor.call_llm')
    @patch('skills.executor.get_token_tracker')
    def test_text_output_format(self, mock_tracker_fn, mock_call_llm):
        """Skill with output.format=text returns {'text': content}."""
        text_skill = make_skill(name='text_skill', yaml_content=TEXT_OUTPUT_YAML)
        mock_tracker = MagicMock()
        mock_tracker.check_budget.return_value = True
        mock_tracker_fn.return_value = mock_tracker
        mock_call_llm.return_value = mock_llm_response(
            content='Plain text answer', model='gpt-4o-mini',
        )

        result = execute_skill(text_skill, {'question': 'What is GAF?'}, self.admin)
        self.assertEqual(result['parsed_output'], {'text': 'Plain text answer'})

    @patch('skills.executor.call_llm')
    @patch('skills.executor.get_token_tracker')
    def test_parameter_override(self, mock_tracker_fn, mock_call_llm):
        """Caller parameters override YAML defaults."""
        mock_tracker = MagicMock()
        mock_tracker.check_budget.return_value = True
        mock_tracker_fn.return_value = mock_tracker
        mock_call_llm.return_value = mock_llm_response()

        execute_skill(
            self.skill, self.task_context, self.admin,
            parameters={'temperature': 0.9, 'max_tokens': 5000},
        )

        call_kwargs = mock_call_llm.call_args.kwargs
        self.assertEqual(call_kwargs['temperature'], 0.9)
        self.assertEqual(call_kwargs['max_tokens'], 5000)

    @patch('skills.executor.call_llm')
    @patch('skills.executor.get_token_tracker')
    def test_budget_exceeded_raises_error(self, mock_tracker_fn, mock_call_llm):
        """Budget exceeded → SkillExecutionError."""
        mock_tracker = MagicMock()
        mock_tracker.check_budget.return_value = False  # budget exceeded
        mock_tracker_fn.return_value = mock_tracker

        with self.assertRaises(SkillExecutionError) as ctx:
            execute_skill(self.skill, self.task_context, self.admin)

        self.assertIn('Budget exceeded', str(ctx.exception))
        # LLM should NOT be called when budget is exceeded
        mock_call_llm.assert_not_called()

    @patch('skills.executor.get_token_tracker')
    def test_invalid_yaml_raises_error(self, mock_tracker_fn):
        """Invalid YAML → SkillExecutionError."""
        bad_skill = make_skill(name='bad_yaml_skill', yaml_content=INVALID_YAML)
        mock_tracker = MagicMock()
        mock_tracker.check_budget.return_value = True
        mock_tracker_fn.return_value = mock_tracker

        with self.assertRaises(SkillExecutionError) as ctx:
            execute_skill(bad_skill, {}, self.admin)

        self.assertIn('Invalid YAML', str(ctx.exception))

    @patch('skills.executor.get_token_tracker')
    def test_non_dict_yaml_raises_error(self, mock_tracker_fn):
        """YAML top-level not a mapping → SkillExecutionError."""
        list_skill = make_skill(name='list_yaml_skill', yaml_content=NON_DICT_YAML)
        mock_tracker = MagicMock()
        mock_tracker.check_budget.return_value = True
        mock_tracker_fn.return_value = mock_tracker

        with self.assertRaises(SkillExecutionError) as ctx:
            execute_skill(list_skill, {}, self.admin)

        self.assertIn('mapping', str(ctx.exception))

    @patch('skills.executor.call_llm')
    @patch('skills.executor.get_token_tracker')
    def test_llm_call_exception_raises_error(self, mock_tracker_fn, mock_call_llm):
        """LLM call raises exception → SkillExecutionError."""
        mock_tracker = MagicMock()
        mock_tracker.check_budget.return_value = True
        mock_tracker_fn.return_value = mock_tracker
        mock_call_llm.side_effect = RuntimeError("Connection timeout")

        with self.assertRaises(SkillExecutionError) as ctx:
            execute_skill(self.skill, self.task_context, self.admin)

        self.assertIn('LLM call failed', str(ctx.exception))

    @patch('skills.executor.call_llm')
    @patch('skills.executor.get_token_tracker')
    def test_llm_error_response_raises_error(self, mock_tracker_fn, mock_call_llm):
        """LLM returns {error: ...} without content → SkillExecutionError."""
        mock_tracker = MagicMock()
        mock_tracker.check_budget.return_value = True
        mock_tracker_fn.return_value = mock_tracker
        mock_call_llm.return_value = {'error': 'All LLM providers failed'}

        with self.assertRaises(SkillExecutionError) as ctx:
            execute_skill(self.skill, self.task_context, self.admin)

        self.assertIn('LLM call returned error', str(ctx.exception))

    @patch('skills.executor.call_llm')
    @patch('skills.executor.get_token_tracker')
    def test_no_user_skips_budget_check(self, mock_tracker_fn, mock_call_llm):
        """user=None → budget check skipped (system-triggered)."""
        mock_tracker = MagicMock()
        mock_tracker_fn.return_value = mock_tracker
        mock_call_llm.return_value = mock_llm_response()

        execute_skill(self.skill, self.task_context, user=None)

        mock_tracker.check_budget.assert_not_called()
        mock_tracker.record.assert_called_once()

    @patch('skills.executor.call_llm')
    @patch('skills.executor.get_token_tracker')
    def test_context_collection_called(self, mock_tracker_fn, mock_call_llm):
        """build_skill_context() is called (dead code activation)."""
        mock_tracker = MagicMock()
        mock_tracker.check_budget.return_value = True
        mock_tracker_fn.return_value = mock_tracker
        mock_call_llm.return_value = mock_llm_response()

        with patch('skills.executor.build_skill_context') as mock_build:
            mock_build.return_value = {'log_content': 'truncated log'}
            execute_skill(self.skill, self.task_context, self.admin)

            mock_build.assert_called_once()
            call_args = mock_build.call_args
            # First arg is context_config, second is task_context
            self.assertEqual(call_args.args[1], self.task_context)


# ── API endpoint tests ──────────────────────────────────────────

class ExecuteAPITest(TestCase):
    """Tests for POST /api/v2/skills/skills/{id}/execute/."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='api_admin',
            password='admin123456',
            role=User.Role.ADMIN,
        )
        cls.skill = make_skill(name='api_test_skill')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.url = f'/api/v2/skills/skills/{self.skill.id}/execute/'

    @patch('skills.executor.call_llm')
    @patch('skills.executor.get_token_tracker')
    def test_execute_endpoint_success(self, mock_tracker_fn, mock_call_llm):
        """POST execute returns 200 with structured result."""
        mock_tracker = MagicMock()
        mock_tracker.check_budget.return_value = True
        mock_tracker_fn.return_value = mock_tracker
        mock_call_llm.return_value = mock_llm_response()

        response = self.client.post(self.url, {
            'task_context': {'task_name': 'test', 'error_message': 'fail'},
            'parameters': {'temperature': 0.7},
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['skill_name'], 'api_test_skill')
        self.assertIn('parsed_output', data)
        self.assertIn('usage', data)

    def test_execute_endpoint_disabled_skill(self):
        """POST execute on disabled skill returns 400."""
        self.skill.is_enabled = False
        self.skill.save(update_fields=['is_enabled'])

        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('disabled', response.json()['error'])

    @patch('skills.executor.call_llm')
    @patch('skills.executor.get_token_tracker')
    def test_execute_endpoint_budget_exceeded(self, mock_tracker_fn, mock_call_llm):
        """POST execute with budget exceeded returns 400."""
        mock_tracker = MagicMock()
        mock_tracker.check_budget.return_value = False
        mock_tracker_fn.return_value = mock_tracker

        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Budget exceeded', response.json()['error'])

    @patch('skills.executor.call_llm')
    @patch('skills.executor.get_token_tracker')
    def test_execute_endpoint_no_task_context(self, mock_tracker_fn, mock_call_llm):
        """POST execute without task_context works (empty dict default)."""
        mock_tracker = MagicMock()
        mock_tracker.check_budget.return_value = True
        mock_tracker_fn.return_value = mock_tracker
        mock_call_llm.return_value = mock_llm_response()

        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_execute_endpoint_unauthenticated(self):
        """POST execute without auth returns 401."""
        self.client.force_authenticate(user=None)
        response = self.client.post(self.url, {}, format='json')
        self.assertIn(response.status_code, [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ])


# ── Dead code activation verification tests ─────────────────────

class DeadCodeActivationTest(TestCase):
    """Verify that S1 activates previously-dead code paths.

    Per spec: build_skill_context() and TokenUsageTracker.check_budget()
    were implemented but had no callers. After S1, they should be
    called by execute_skill().
    """

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='activation_admin',
            password='admin123456',
            role=User.Role.ADMIN,
        )
        cls.skill = make_skill(name='activation_skill')

    @patch('skills.executor.call_llm')
    @patch('skills.executor.get_token_tracker')
    def test_build_skill_context_is_called(self, mock_tracker_fn, mock_call_llm):
        """build_skill_context() is called by execute_skill()."""
        mock_tracker = MagicMock()
        mock_tracker.check_budget.return_value = True
        mock_tracker_fn.return_value = mock_tracker
        mock_call_llm.return_value = mock_llm_response()

        with patch('skills.executor.build_skill_context') as mock_build:
            mock_build.return_value = {}
            execute_skill(self.skill, {'log': 'test log'}, self.admin)
            mock_build.assert_called_once()

    @patch('skills.executor.call_llm')
    def test_token_tracker_check_budget_is_called(self, mock_call_llm):
        """TokenUsageTracker.check_budget() is called by execute_skill()."""
        mock_call_llm.return_value = mock_llm_response()

        with patch('skills.executor.get_token_tracker') as mock_get_tracker:
            mock_tracker = MagicMock()
            mock_tracker.check_budget.return_value = True
            mock_get_tracker.return_value = mock_tracker

            execute_skill(self.skill, {}, self.admin)

            mock_tracker.check_budget.assert_called_once()
            # Verify cost_control was passed (from YAML)
            call_args = mock_tracker.check_budget.call_args
            cost_control = call_args.args[1] if len(call_args.args) > 1 else call_args.kwargs.get('skill_config')
            if cost_control is None and len(call_args.args) > 1:
                cost_control = call_args.args[1]
            self.assertIsNotNone(cost_control)
            self.assertEqual(cost_control.get('max_calls_per_day'), 30)
