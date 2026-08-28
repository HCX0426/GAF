"""Adapter to wrap SkillDefinition / CustomSkill as LangChain tools.

S6 (P2-4) — register enabled Skills as LangGraph ReAct agent tools so
the agent can invoke them autonomously during log analysis.

Architecture decisions (N151, see spec 2026-07-14-ai-architecture-defects.md §S6):

1. **Don't merge models** — ``SkillDefinition`` (int PK, ``is_enabled``,
   ``is_builtin``, ``applicable_scenarios``) and ``CustomSkill`` (string
   PK, ``is_active``, ``category``, ``created_by``) stay separate. The
   merge cost (PK migration + SkillMarketItem FK rewrite + frontend TS
   rewrite) is not justified by the benefit.

2. **Protocol adapter** — define ``SkillProtocol`` and let
   ``make_skill_tool`` duck-type both models. ``execute_skill`` already
   duck-types (it only reads ``skill.yaml_content`` / ``skill.name`` /
   ``skill.id``), so the executor is reused unchanged.

3. **build_log_analysis_agent(user=None)** — pass user, inject global
   ``SkillDefinition`` (is_enabled=True) + per-user ``CustomSkill``
   (is_active=True, created_by=user).

4. **Build-time injection** — query skills at agent build time, wrap as
   tools, extend ``AGENT_TOOLS``. LangGraph expects a static tools list;
   lazy-load would need a custom _arun with much higher complexity.
"""
import json
import logging
from typing import Protocol, runtime_checkable

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@runtime_checkable
class SkillProtocol(Protocol):
    """Protocol for objects adaptable to a LangGraph tool.

    Both ``SkillDefinition`` and ``CustomSkill`` satisfy this protocol
    for the attributes ``make_skill_tool`` actually reads
    (``name`` / ``description`` / ``yaml_content`` / ``id``).

    Note on ``is_enabled``: it is declared here as the canonical
    "enablement flag" for documentation/type-hint purposes.
    ``SkillDefinition`` satisfies it directly; ``CustomSkill`` uses
    ``is_active`` (a different field name) so it does NOT satisfy the
    ``is_enabled`` slot at runtime. ``collect_skill_tools`` therefore
    filters by the correct field name per model rather than relying on
    ``isinstance`` — this keeps CustomSkill's schema unchanged (Option B
    per spec).
    """

    name: str
    description: str
    yaml_content: str
    id: object  # int (SkillDefinition) or str (CustomSkill)

    @property
    def is_enabled(self) -> bool: ...


def make_skill_tool(skill: SkillProtocol):
    """Wrap a skill object as a LangChain ``@tool`` function.

    The returned tool has:
      - ``name`` = sanitized ``skill.name`` (lowercase, spaces/dashes →
        underscores, truncated to 60 chars — LangChain tool name limit)
      - ``description`` = ``skill.description`` (LangChain uses the
        docstring as tool description; we override post-decoration since
        the description comes from the skill, not the function)
      - body calls ``execute_skill(skill, task_context, parameters)`` and
        returns a JSON string
      - exception isolation: never raises — returns an error JSON envelope
        on any failure so the ReAct loop is never broken by a single
        skill failure

    Args:
        skill: A SkillDefinition or CustomSkill instance.

    Returns:
        A LangChain ``StructuredTool`` (the object returned by
        ``@tool``) wired to call ``execute_skill`` for ``skill``.
    """
    skill_name = skill.name
    skill_description = skill.description or f'Execute skill: {skill_name}'
    skill_id = skill.id

    @tool
    def skill_tool(task_context: str = '', parameters: str = '{}') -> str:
        """Execute the skill with optional task context and parameters.

        Args:
            task_context: Free-text description of the current task
                context (e.g. "analyzing execution #42 template match
                failure"). Wrapped into ``{'description': task_context}``
                before being passed to ``execute_skill``.
            parameters: JSON string of parameters to pass to the skill
                (e.g. '{"temperature": 0.7}'). Parsed into a dict;
                invalid JSON falls back to ``{}``.

        Returns:
            JSON string with the skill execution result, or an error
            envelope ``{"error": ..., "skill": ..., "skill_id": ...}``
            on failure (never raises).
        """
        try:
            from skills.executor import execute_skill

            try:
                params = json.loads(parameters) if parameters else {}
            except json.JSONDecodeError:
                params = {}

            # execute_skill expects a dict for task_context (it does
            # ``**task_context`` when rendering the YAML template). The
            # agent passes free text, so we wrap it under 'description'
            # which skills can reference via {{description}} in their
            # user_prompt_template.
            task_context_dict = {'description': task_context} if task_context else {}

            result = execute_skill(
                skill=skill,
                task_context=task_context_dict,
                parameters=params,
            )
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            logger.exception('skill_tool %s failed: %s', skill_name, exc)
            return json.dumps({
                'error': f'Skill execution failed: {exc}',
                'skill': skill_name,
                'skill_id': str(skill_id),
            }, ensure_ascii=False)

    # Override name and description on the tool object. LangChain's
    # @tool uses the function's __name__ and __doc__ by default; we
    # need to set them post-decoration because they come from the skill,
    # not from the function definition. All closures created by
    # make_skill_tool would otherwise share the name "skill_tool".
    sanitized_name = skill_name.lower().replace(' ', '_').replace('-', '_')[:60]
    skill_tool.name = sanitized_name
    skill_tool.description = skill_description
    return skill_tool


def collect_skill_tools(user=None) -> list:
    """Collect all enabled skill tools for a user.

    Returns:
      - Global ``SkillDefinition`` rows where ``is_enabled=True``
      - When ``user`` is not None: that user's ``CustomSkill`` rows
        where ``is_active=True`` and ``created_by=user``

    Per Option B (no model change), the filter uses the correct field
    name per model: ``is_enabled`` for ``SkillDefinition``, ``is_active``
    for ``CustomSkill``. ``CustomSkill`` therefore does not need an
    ``is_enabled`` property.

    Args:
        user: User instance for per-user CustomSkill filtering. When
            ``None``, only global SkillDefinition tools are returned
            (no CustomSkill tools).

    Returns:
        List of LangChain tools (each from ``make_skill_tool``). Errors
        in querying or adapting individual skills are logged and
        skipped — the agent always gets a usable (possibly shorter)
        tools list.
    """
    tools = []

    # Global builtin / shared SkillDefinitions
    try:
        from skills.models import SkillDefinition
        for skill in SkillDefinition.objects.filter(is_enabled=True):
            try:
                tools.append(make_skill_tool(skill))
            except Exception as exc:
                logger.warning(
                    'Failed to adapt SkillDefinition %s: %s',
                    skill.name, exc,
                )
    except Exception as exc:
        logger.warning('Failed to query SkillDefinition: %s', exc)

    # Per-user CustomSkills (only when a user is provided)
    if user is not None:
        try:
            from gaf_ai.models import CustomSkill
            for skill in CustomSkill.objects.filter(is_active=True, created_by=user):
                try:
                    tools.append(make_skill_tool(skill))
                except Exception as exc:
                    logger.warning(
                        'Failed to adapt CustomSkill %s: %s',
                        skill.name, exc,
                    )
        except Exception as exc:
            logger.warning('Failed to query CustomSkill: %s', exc)

    return tools
