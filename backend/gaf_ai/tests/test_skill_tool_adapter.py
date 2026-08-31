"""Tests for the Skill → LangGraph tool adapter (S6 / P2-4).

Covers:
- ``SkillProtocol``: both ``SkillDefinition`` and ``CustomSkill`` expose
  the attributes ``make_skill_tool`` reads (name / description /
  yaml_content / id). CustomSkill uses ``is_active`` instead of
  ``is_enabled`` — see ``collect_skill_tools`` for the per-model filter.
- ``make_skill_tool``: produces a LangChain tool with sanitized name,
  invokes ``execute_skill``, returns JSON, isolates exceptions
- ``collect_skill_tools``: filters SkillDefinition by ``is_enabled``
  and CustomSkill by ``is_active`` + ``created_by=user``
- ``build_log_analysis_agent(user=...)``: injects skill tools alongside
  AGENT_TOOLS, still respects the ``langgraph_agent_enabled`` FeatureFlag

``execute_skill`` is mocked in MakeSkillToolTest / BuildAgentWithSkillsTest
to avoid real LLM calls — the executor's own tests in
``skills/tests/test_executor.py`` cover the real path.
"""
import json
import os
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from gaf_ai.agent.graph import AGENT_TOOLS, build_log_analysis_agent
from gaf_ai.agent.skill_tool_adapter import (
    SkillProtocol,
    collect_skill_tools,
    make_skill_tool,
)
from gaf_ai.models import CustomSkill
from skills.models import SkillDefinition

User = get_user_model()


# ── Fixtures ────────────────────────────────────────────────────

VALID_YAML = """\
name: test_skill
version: "1.0"
description: "Test skill"
model: gpt-4o-mini
system_prompt: "You are helpful."
user_prompt_template: "Question: {{description}}"
output:
  format: text
"""


def _make_skill_definition(name='Test Skill', is_enabled=True):
    """Create a SkillDefinition row for testing."""
    return SkillDefinition.objects.create(
        name=name,
        description=f'Skill: {name}',
        yaml_content=VALID_YAML,
        version='1.0.0',
        applicable_scenarios=['test'],
        is_builtin=False,
        is_enabled=is_enabled,
    )


def _make_custom_skill(user, name='Custom Skill', is_active=True, skill_id='c-1'):
    """Create a CustomSkill row for testing."""
    return CustomSkill.objects.create(
        id=skill_id,
        name=name,
        description=f'Custom: {name}',
        category='analysis',
        yaml_content=VALID_YAML,
        is_active=is_active,
        created_by=user,
    )


def _make_user(username='adapter_user', role='admin'):
    user = User.objects.create_user(username=username, password='Pass123!')
    user.role = role
    user.save(update_fields=['role'])
    return user


# ── SkillProtocol tests ─────────────────────────────────────────


class SkillProtocolTest(TestCase):
    """Both SkillDefinition and CustomSkill satisfy SkillProtocol for the
    attributes ``make_skill_tool`` actually reads.

    Note: CustomSkill has ``is_active`` not ``is_enabled``, so the
    ``@runtime_checkable`` isinstance check returns False for
    CustomSkill. We verify protocol satisfaction by checking the 4
    attributes ``make_skill_tool`` reads (name/description/yaml_content/id)
    and by successfully calling ``make_skill_tool`` on both model types
    (duck typing — the real protocol contract).
    """

    def test_skill_definition_has_protocol_attributes(self):
        skill = _make_skill_definition(name='SD Attrs')
        self.assertTrue(hasattr(skill, 'name'))
        self.assertTrue(hasattr(skill, 'description'))
        self.assertTrue(hasattr(skill, 'yaml_content'))
        self.assertTrue(hasattr(skill, 'id'))
        self.assertTrue(hasattr(skill, 'is_enabled'))

    def test_custom_skill_has_protocol_attributes(self):
        """CustomSkill has name/description/yaml_content/id (the 4 attrs
        make_skill_tool reads). is_active replaces is_enabled — see
        collect_skill_tools for the per-model filter."""
        user = _make_user()
        skill = _make_custom_skill(user, name='CS Attrs')
        self.assertTrue(hasattr(skill, 'name'))
        self.assertTrue(hasattr(skill, 'description'))
        self.assertTrue(hasattr(skill, 'yaml_content'))
        self.assertTrue(hasattr(skill, 'id'))

    def test_skill_definition_satisfies_runtime_checkable(self):
        """SkillDefinition has is_enabled, so isinstance(.., SkillProtocol)
        succeeds with @runtime_checkable."""
        skill = _make_skill_definition(name='SD Runtime')
        self.assertIsInstance(skill, SkillProtocol)

    def test_make_skill_tool_accepts_both_models(self):
        """make_skill_tool successfully wraps both SkillDefinition and
        CustomSkill — the real protocol test (duck typing)."""
        user = _make_user()
        cs = _make_custom_skill(user, name='CS Duck')
        sd = _make_skill_definition(name='SD Duck')
        tool_from_sd = make_skill_tool(sd)
        tool_from_cs = make_skill_tool(cs)
        self.assertIsNotNone(tool_from_sd)
        self.assertIsNotNone(tool_from_cs)


# ── make_skill_tool tests ───────────────────────────────────────


class MakeSkillToolTest(TestCase):
    """Tests for make_skill_tool()."""

    def test_returns_tool_with_sanitized_name_spaces(self):
        """Tool name: lowercase + spaces → underscores."""
        skill = _make_skill_definition(name='Error Diagnosis Pro')
        t = make_skill_tool(skill)
        self.assertEqual(t.name, 'error_diagnosis_pro')

    def test_returns_tool_with_sanitized_name_dashes(self):
        """Tool name: dashes → underscores."""
        skill = _make_skill_definition(name='log-analysis')
        t = make_skill_tool(skill)
        self.assertEqual(t.name, 'log_analysis')

    def test_tool_description_from_skill(self):
        """Tool description comes from skill.description."""
        skill = _make_skill_definition(name='Desc Skill')
        skill.description = 'My custom description'
        skill.save(update_fields=['description'])
        t = make_skill_tool(skill)
        self.assertEqual(t.description, 'My custom description')

    def test_tool_description_fallback_when_empty(self):
        """When skill.description is empty, fall back to 'Execute skill: <name>'."""
        skill = _make_skill_definition(name='NoDesc')
        skill.description = ''
        skill.save(update_fields=['description'])
        t = make_skill_tool(skill)
        self.assertEqual(t.description, 'Execute skill: NoDesc')

    @patch('skills.executor.execute_skill')
    def test_invoke_calls_execute_skill_and_returns_json(self, mock_exec):
        """tool.invoke({'task_context': '...'}) calls execute_skill and
        returns its result as a JSON string."""
        mock_exec.return_value = {'skill_name': 'test', 'content': 'hello'}
        skill = _make_skill_definition(name='Invoke Skill')
        t = make_skill_tool(skill)

        result_str = t.invoke({'task_context': 'analyze execution #42'})
        result = json.loads(result_str)

        self.assertEqual(result['skill_name'], 'test')
        self.assertEqual(result['content'], 'hello')
        # Verify execute_skill was called with skill + wrapped task_context
        mock_exec.assert_called_once()
        call_kwargs = mock_exec.call_args.kwargs
        self.assertIs(call_kwargs['skill'], skill)
        self.assertEqual(
            call_kwargs['task_context'],
            {'description': 'analyze execution #42'},
        )
        self.assertEqual(call_kwargs['parameters'], {})

    @patch('skills.executor.execute_skill')
    def test_invoke_with_parameters_json(self, mock_exec):
        """tool.invoke with valid parameters JSON passes parsed dict."""
        mock_exec.return_value = {'ok': True}
        skill = _make_skill_definition(name='Param Skill')
        t = make_skill_tool(skill)

        t.invoke({
            'task_context': 'ctx',
            'parameters': json.dumps({'temperature': 0.7, 'max_tokens': 3000}),
        })

        mock_exec.assert_called_once()
        call_kwargs = mock_exec.call_args.kwargs
        self.assertEqual(call_kwargs['parameters']['temperature'], 0.7)
        self.assertEqual(call_kwargs['parameters']['max_tokens'], 3000)

    @patch('skills.executor.execute_skill')
    def test_invoke_with_invalid_parameters_json_falls_back_to_empty(self, mock_exec):
        """Invalid parameters JSON → parameters={} (no exception)."""
        mock_exec.return_value = {'ok': True}
        skill = _make_skill_definition(name='Bad JSON Skill')
        t = make_skill_tool(skill)

        # Should not raise
        result_str = t.invoke({
            'task_context': 'ctx',
            'parameters': 'not-valid-json',
        })
        result = json.loads(result_str)
        self.assertEqual(result, {'ok': True})

        mock_exec.assert_called_once()
        self.assertEqual(mock_exec.call_args.kwargs['parameters'], {})

    @patch('skills.executor.execute_skill')
    def test_invoke_with_empty_task_context_passes_empty_dict(self, mock_exec):
        """Empty task_context → execute_skill gets task_context={}."""
        mock_exec.return_value = {'ok': True}
        skill = _make_skill_definition(name='Empty Ctx')
        t = make_skill_tool(skill)

        t.invoke({'task_context': ''})
        self.assertEqual(mock_exec.call_args.kwargs['task_context'], {})

    @patch('skills.executor.execute_skill')
    def test_invoke_when_execute_skill_raises_returns_error_json(self, mock_exec):
        """When execute_skill raises, the tool returns an error JSON envelope
        instead of propagating the exception (exception isolation)."""
        mock_exec.side_effect = RuntimeError('LLM provider down')
        skill = _make_skill_definition(name='Failing Skill')
        t = make_skill_tool(skill)

        # Should NOT raise
        result_str = t.invoke({'task_context': 'ctx'})
        result = json.loads(result_str)

        self.assertIn('error', result)
        self.assertIn('LLM provider down', result['error'])
        self.assertEqual(result['skill'], 'Failing Skill')
        self.assertEqual(result['skill_id'], str(skill.id))

    @patch('skills.executor.execute_skill')
    def test_invoke_with_custom_skill(self, mock_exec):
        """make_skill_tool works with CustomSkill (string PK)."""
        mock_exec.return_value = {'ok': True}
        user = _make_user()
        cs = _make_custom_skill(user, name='Custom Invoke', skill_id='custom-1')
        t = make_skill_tool(cs)

        result_str = t.invoke({'task_context': 'ctx'})
        result = json.loads(result_str)
        self.assertEqual(result, {'ok': True})

        mock_exec.assert_called_once()
        self.assertIs(mock_exec.call_args.kwargs['skill'], cs)

    @patch('skills.executor.execute_skill')
    def test_invoke_error_envelope_includes_string_pk_for_custom_skill(self, mock_exec):
        """When CustomSkill execution fails, the error envelope surfaces
        the string PK (not int)."""
        mock_exec.side_effect = ValueError('boom')
        user = _make_user()
        cs = _make_custom_skill(user, name='CS Fail', skill_id='str-pk-42')
        t = make_skill_tool(cs)

        result_str = t.invoke({'task_context': 'ctx'})
        result = json.loads(result_str)
        self.assertEqual(result['skill_id'], 'str-pk-42')
        self.assertEqual(result['skill'], 'CS Fail')


# ── collect_skill_tools tests ───────────────────────────────────


class CollectSkillToolsTest(TestCase):
    """Tests for collect_skill_tools()."""

    def test_no_skills_with_user_returns_empty_list(self):
        """With no SkillDefinition and no CustomSkill, returns []."""
        user = _make_user()
        tools = collect_skill_tools(user=user)
        self.assertEqual(tools, [])

    def test_no_skills_with_user_none_returns_empty_list(self):
        tools = collect_skill_tools(user=None)
        self.assertEqual(tools, [])

    def test_enabled_skill_definition_produces_one_tool(self):
        _make_skill_definition(name='Enabled SD', is_enabled=True)
        user = _make_user()
        tools = collect_skill_tools(user=user)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].name, 'enabled_sd')

    def test_disabled_skill_definition_produces_no_tool(self):
        _make_skill_definition(name='Disabled SD', is_enabled=False)
        user = _make_user()
        tools = collect_skill_tools(user=user)
        self.assertEqual(tools, [])

    def test_user_active_custom_skill_produces_one_tool(self):
        user = _make_user()
        _make_custom_skill(user, name='My Custom', is_active=True)
        tools = collect_skill_tools(user=user)
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].name, 'my_custom')

    def test_user_inactive_custom_skill_produces_no_tool(self):
        user = _make_user()
        _make_custom_skill(user, name='Inactive', is_active=False)
        tools = collect_skill_tools(user=user)
        self.assertEqual(tools, [])

    def test_custom_skill_created_by_other_user_excluded(self):
        """CustomSkill filtering is by created_by=user — other users'
        skills are not included."""
        user = _make_user('mine')
        other = _make_user('other')
        _make_custom_skill(
            other, name='Other User Skill', is_active=True, skill_id='other-1',
        )
        tools = collect_skill_tools(user=user)
        self.assertEqual(tools, [])

    def test_user_none_excludes_custom_skills(self):
        """When user=None, only global SkillDefinitions are returned —
        no CustomSkill tools even if some exist in the DB."""
        user = _make_user()
        _make_custom_skill(user, name='Lonely Custom', is_active=True)
        tools = collect_skill_tools(user=None)
        self.assertEqual(tools, [])

    def test_global_sd_plus_user_custom_skill_both_returned(self):
        """Mix: 1 global SkillDefinition + 1 per-user CustomSkill → 2 tools."""
        _make_skill_definition(name='Global SD', is_enabled=True)
        user = _make_user()
        _make_custom_skill(user, name='User Custom', is_active=True)
        tools = collect_skill_tools(user=user)
        self.assertEqual(len(tools), 2)
        names = sorted(t.name for t in tools)
        self.assertEqual(names, ['global_sd', 'user_custom'])

    def test_multiple_skill_definitions_all_returned(self):
        """Multiple enabled SkillDefinitions are all adapted; disabled ones excluded."""
        _make_skill_definition(name='SD One', is_enabled=True)
        _make_skill_definition(name='SD Two', is_enabled=True)
        _make_skill_definition(name='SD Three', is_enabled=False)  # excluded
        user = _make_user()
        tools = collect_skill_tools(user=user)
        self.assertEqual(len(tools), 2)
        names = sorted(t.name for t in tools)
        self.assertEqual(names, ['sd_one', 'sd_two'])


# ── build_log_analysis_agent integration tests ──────────────────


class BuildAgentWithSkillsTest(TestCase):
    """build_log_analysis_agent(user=...) injects skill tools and still
    respects the langgraph_agent_enabled FeatureFlag gate."""

    def setUp(self):
        from settings.models import FeatureFlag

        from gaf_ai.feature_flags import LANGGRAPH_AGENT_FLAG
        # Ensure the flag is enabled (fail-open default also works, but
        # explicit True makes the test independent of migration state).
        FeatureFlag.objects.update_or_create(
            name=LANGGRAPH_AGENT_FLAG, defaults={'enabled': True},
        )

    def test_disabled_flag_raises_runtime_error(self):
        """When the flag is disabled, build raises RuntimeError before
        collecting skills (no DB queries)."""
        from settings.models import FeatureFlag

        from gaf_ai.feature_flags import LANGGRAPH_AGENT_FLAG
        FeatureFlag.objects.update_or_create(
            name=LANGGRAPH_AGENT_FLAG, defaults={'enabled': False},
        )
        with self.assertRaises(RuntimeError) as ctx:
            build_log_analysis_agent(user=_make_user())
        self.assertIn('langgraph_agent_enabled', str(ctx.exception))

    @patch('gaf_ai.agent.graph._resolve_preferred_model_name', return_value='')
    @patch('gaf_ai.agent.graph.create_agent')
    @patch('gaf_ai.agent.graph.build_agent_llm')
    @patch.dict(os.environ, {'AGENT_USE_CREATE_AGENT': '1'}, clear=False)
    def test_agent_includes_skill_tools_when_skills_exist(
        self, mock_llm, mock_create, _mock_model,
    ):
        """build_log_analysis_agent(user=u) passes AGENT_TOOLS + skill tools
        to create_agent."""
        mock_llm.return_value = MagicMock(name='fake_llm')
        mock_create.return_value = MagicMock(name='fake_agent')

        _make_skill_definition(name='Extra Skill', is_enabled=True)
        user = _make_user()
        _make_custom_skill(user, name='User Extra', is_active=True)

        build_log_analysis_agent(user=user)

        # create_agent was called with (llm, tools, system_prompt=...)
        # Second positional arg (index 1) is the tools list.
        mock_create.assert_called_once()
        tools_arg = mock_create.call_args.args[1]
        # AGENT_TOOLS has 4 fixed tools + 1 SkillDefinition + 1 CustomSkill = 6
        self.assertEqual(len(tools_arg), len(AGENT_TOOLS) + 2)

    @patch('gaf_ai.agent.graph._resolve_preferred_model_name', return_value='')
    @patch('gaf_ai.agent.graph.create_agent')
    @patch('gaf_ai.agent.graph.build_agent_llm')
    @patch.dict(os.environ, {'AGENT_USE_CREATE_AGENT': '1'}, clear=False)
    def test_agent_works_with_only_agent_tools_when_no_skills(
        self, mock_llm, mock_create, _mock_model,
    ):
        """build_log_analysis_agent(user=u) with no skills in DB passes
        just AGENT_TOOLS (no skill tools)."""
        mock_llm.return_value = MagicMock(name='fake_llm')
        mock_create.return_value = MagicMock(name='fake_agent')

        user = _make_user()
        build_log_analysis_agent(user=user)

        mock_create.assert_called_once()
        tools_arg = mock_create.call_args.args[1]
        self.assertEqual(len(tools_arg), len(AGENT_TOOLS))

    @patch('gaf_ai.agent.graph._resolve_preferred_model_name', return_value='')
    @patch('gaf_ai.agent.graph.create_agent')
    @patch('gaf_ai.agent.graph.build_agent_llm')
    @patch.dict(os.environ, {'AGENT_USE_CREATE_AGENT': '1'}, clear=False)
    def test_agent_user_none_excludes_custom_skills(self, mock_llm, mock_create, _mock_model):
        """build_log_analysis_agent(user=None) includes global
        SkillDefinitions but not CustomSkills."""
        mock_llm.return_value = MagicMock(name='fake_llm')
        mock_create.return_value = MagicMock(name='fake_agent')

        user = _make_user()
        _make_skill_definition(name='Global SD', is_enabled=True)
        _make_custom_skill(user, name='Should Be Excluded', is_active=True)

        build_log_analysis_agent(user=None)

        mock_create.assert_called_once()
        tools_arg = mock_create.call_args.args[1]
        # 4 AGENT_TOOLS + 1 global SkillDefinition = 5 (no CustomSkill)
        self.assertEqual(len(tools_arg), len(AGENT_TOOLS) + 1)

    @patch('gaf_ai.agent.graph.create_agent')
    @patch('gaf_ai.agent.graph.build_agent_llm')
    @patch.dict(os.environ, {'AGENT_USE_CREATE_AGENT': '1'}, clear=False)
    def test_agent_default_user_none_works(self, mock_llm, mock_create):
        """build_log_analysis_agent() with no args defaults user=None and
        still builds successfully (backward compat with existing callers
        in test_feature_flags.py / test_agent_async.py)."""
        mock_llm.return_value = MagicMock(name='fake_llm')
        mock_create.return_value = MagicMock(name='fake_agent')

        # No skills in DB, no user — should still build
        agent = build_log_analysis_agent()
        self.assertIsNotNone(agent)
        mock_create.assert_called_once()

    @patch('gaf_ai.agent.graph._resolve_preferred_model_name', return_value='gpt-4o')
    @patch('gaf_ai.agent.graph.create_agent')
    @patch('gaf_ai.agent.graph.build_agent_llm')
    @patch.dict(os.environ, {'AGENT_USE_CREATE_AGENT': '1'}, clear=False)
    def test_agent_vision_model_gets_screenshot_tool(self, mock_llm, mock_create, _mock_model):
        """spec §7.2.2 — 任务 2.4: 视觉模型 (gpt-4o) 应拿到 get_screenshot_base64."""
        mock_llm.return_value = MagicMock(name='fake_llm')
        mock_create.return_value = MagicMock(name='fake_agent')

        build_log_analysis_agent()

        mock_create.assert_called_once()
        tools_arg = mock_create.call_args.args[1]
        tool_names = [t.name for t in tools_arg]
        self.assertIn('get_screenshot_base64', tool_names)
        self.assertEqual(len(tools_arg), 6)  # 6 fixed tools, no skills

    @patch('gaf_ai.agent.graph._resolve_preferred_model_name', return_value='deepseek-chat')
    @patch('gaf_ai.agent.graph.create_agent')
    @patch('gaf_ai.agent.graph.build_agent_llm')
    @patch.dict(os.environ, {'AGENT_USE_CREATE_AGENT': '1'}, clear=False)
    def test_agent_text_model_excludes_screenshot_tool(self, mock_llm, mock_create, _mock_model):
        """spec §7.2.2 — 任务 2.4: 纯文本模型 (deepseek-chat) 不应拿到 get_screenshot_base64."""
        mock_llm.return_value = MagicMock(name='fake_llm')
        mock_create.return_value = MagicMock(name='fake_agent')

        build_log_analysis_agent()

        mock_create.assert_called_once()
        tools_arg = mock_create.call_args.args[1]
        tool_names = [t.name for t in tools_arg]
        self.assertNotIn('get_screenshot_base64', tool_names)
        self.assertEqual(len(tools_arg), 5)  # 5 fixed tools, no screenshot
