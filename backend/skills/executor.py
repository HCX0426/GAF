"""Skill executor — execute a SkillDefinition per its YAML schema.

Phase 4.5/4.7 closure: activates ``build_skill_context()`` and
``TokenUsageTracker.check_budget()`` which were implemented but had no
callers. This module is the canonical Skill execution path per
design §3.1 (system_prompt + user_prompt_template + context +
parameters + output + cost_control schema).

Execution flow:
  1. Parse ``yaml_content`` into config dict
  2. Check budget via ``TokenUsageTracker.check_budget(cost_control)``
  3. Collect task context via ``build_skill_context(context, task_context)``
  4. Render ``user_prompt_template`` with context + parameters
  5. Call LLM via ``call_llm(messages, model, ...)``
  6. Record usage via ``TokenUsageTracker.record()``
  7. Parse output per ``output.format`` (json/text)
  8. Return structured result

This module does NOT modify ``debug/tasks.py`` which has a legacy
execution path for backward compatibility. New code should use
``execute_skill()`` here.
"""

import json
import logging
import re
from typing import Any

import yaml
from django.contrib.auth import get_user_model
from gaf_ai.context_collector import build_skill_context
from gaf_ai.llm_service import call_llm
from gaf_ai.token_tracker import get_token_tracker

from skills.models import SkillDefinition

logger = logging.getLogger(__name__)
User = get_user_model()


class SkillExecutionError(Exception):
    """Skill execution failure (budget exceeded, YAML invalid, LLM error)."""


def execute_skill(
    skill: SkillDefinition,
    task_context: dict[str, Any] | None = None,
    user: User | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a SkillDefinition per its YAML schema.

    Args:
        skill: SkillDefinition instance with yaml_content
        task_context: Raw execution data (log, screenshots, task_config, ...).
            May contain keys: ``log``, ``screenshots``, ``screenshot_description``,
            ``task_config``, ``device_info``, plus any template variables
            referenced in ``user_prompt_template`` (e.g. ``task_name``,
            ``error_message``, ``step_name``).
        user: User initiating the call (for budget tracking). If None,
            budget check is skipped (e.g. system-triggered execution).
        parameters: Override default parameters from YAML ``parameters`` block
            (e.g. ``{"temperature": 0.7, "max_tokens": 3000}``).

    Returns:
        Dict with keys:
            - ``skill_name``: str
            - ``model``: str — actual model used (from LLM response)
            - ``route``: str — LLMRouter level (preferred/backup/local/offline)
            - ``content``: str — raw LLM response text
            - ``parsed_output``: dict — parsed per ``output.format``
            - ``usage``: dict — ``{input_tokens, output_tokens, cost}``

    Raises:
        SkillExecutionError: On budget exceeded, invalid YAML, or LLM failure.
    """
    task_context = task_context or {}

    # 1. Parse YAML
    try:
        config = yaml.safe_load(skill.yaml_content)
        if not isinstance(config, dict):
            raise SkillExecutionError(
                f"YAML top-level must be a mapping, got {type(config).__name__}"
            )
    except yaml.YAMLError as e:
        raise SkillExecutionError(f"Invalid YAML in skill '{skill.name}': {e}") from e

    # 2. Check budget (per-Skill daily limits from cost_control block)
    tracker = get_token_tracker()
    cost_control = config.get("cost_control", {})
    if user is not None and not tracker.check_budget(user.id, cost_control):
        max_calls = cost_control.get("max_calls_per_day", 50)
        max_cost = cost_control.get("max_cost_per_day", 1.0)
        raise SkillExecutionError(
            f"Budget exceeded for user {user.id} "
            f"(limit: {max_calls} calls/day, ${max_cost}/day)"
        )

    # 3. Collect task context via ContextCollector
    context_config = config.get("context", {})
    collected = build_skill_context(context_config, task_context)

    # 4. Render user_prompt_template
    template = config.get("user_prompt_template", "")
    # Start with YAML parameters defaults, override with caller parameters
    yaml_params = _extract_param_defaults(config.get("parameters", {}))
    params = {**yaml_params, **(parameters or {})}
    # Template variables: collected context + task_context fields + params
    render_vars = {**collected, **task_context, **params}
    rendered_prompt = _render_template(template, render_vars)

    # 5. Call LLM via 4-level router
    system_prompt = config.get("system_prompt", "")
    model = config.get("model", "gpt-4o-mini")
    max_tokens = int(params.get("max_tokens", 2000))
    temperature = float(params.get("temperature", 0.3))

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": rendered_prompt},
    ]

    logger.info(
        "Executing skill '%s' with model=%s max_tokens=%d temperature=%.2f",
        skill.name, model, max_tokens, temperature,
    )

    try:
        llm_result = call_llm(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except Exception as e:
        logger.exception("LLM call failed for skill '%s'", skill.name)
        raise SkillExecutionError(f"LLM call failed: {e}") from e

    # Handle error response from call_llm (returns dict with "error" key
    # instead of raising — OfflineClient is the ultimate fallback).
    if "error" in llm_result and "content" not in llm_result:
        raise SkillExecutionError(
            f"LLM call returned error: {llm_result['error']}"
        )

    # 6. Record usage to LLMUsageLog
    tracker.record(
        user_id=user.id if user else 0,
        model=llm_result.get("model", model),
        input_tokens=llm_result.get("input_tokens", 0),
        output_tokens=llm_result.get("output_tokens", 0),
        cost=llm_result.get("cost", 0.0),
        call_type=f"skill_{skill.name}",
        route=llm_result.get("route", ""),
    )

    # 7. Parse output per output.format config
    output_config = config.get("output", {})
    content = llm_result.get("content", "")
    parsed = _parse_output(content, output_config)

    # 8. Return structured result
    return {
        "skill_name": skill.name,
        "skill_id": skill.id,
        "model": llm_result.get("model", model),
        "route": llm_result.get("route", ""),
        "content": content,
        "parsed_output": parsed,
        "usage": {
            "input_tokens": llm_result.get("input_tokens", 0),
            "output_tokens": llm_result.get("output_tokens", 0),
            "cost": llm_result.get("cost", 0.0),
        },
    }


# ── Template rendering ──────────────────────────────────────────

_TEMPLATE_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def _render_template(template: str, variables: dict[str, Any]) -> str:
    """Render a ``{{var}}`` template with variables.

    Uses simple regex replacement — no Jinja2 dependency for security.
    Missing variables are replaced with empty string (lenient) to
    handle optional context fields gracefully.

    Args:
        template: Template string with ``{{var}}`` placeholders.
        variables: Dict of variable names to values.

    Returns:
        Rendered string with variables substituted.
    """

    def replace_var(match: re.Match) -> str:
        var_name = match.group(1)
        if var_name in variables:
            value = variables[var_name]
            if value is None:
                return ""
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False, indent=2, default=str)
            return str(value)
        # Missing variable → empty string (lenient)
        return ""

    return _TEMPLATE_VAR_RE.sub(replace_var, template)


# ── Output parsing ──────────────────────────────────────────────

_JSON_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def _parse_output(content: str, output_config: dict[str, Any]) -> dict[str, Any]:
    """Parse LLM output per ``output.format`` config.

    Supports:
        - ``json``: Parse as JSON. Handles markdown code-block-wrapped JSON.
          On parse failure, returns ``{"_parse_error": ..., "raw": content}``.
        - ``text`` (default): Return ``{"text": content}``.

    Args:
        content: Raw LLM response text.
        output_config: ``output`` block from YAML (may contain ``format``
            and ``schema``).

    Returns:
        Parsed dict.
    """
    fmt = output_config.get("format", "text")

    if fmt == "json":
        # Try direct parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        # Try extracting from markdown code block
        match = _JSON_CODE_BLOCK_RE.search(content)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # Parse failed — return raw with error marker
        return {"_parse_error": "Invalid JSON output", "raw": content}

    return {"text": content}


# ── Parameter defaults extraction ──────────────────────────────

def _extract_param_defaults(parameters_config: dict[str, Any]) -> dict[str, Any]:
    """Extract default values from YAML ``parameters`` block.

    The ``parameters`` block has the structure::

        parameters:
          temperature:
            type: float
            default: 0.5
            min: 0.0
            max: 1.0
          max_tokens:
            type: integer
            default: 2000

    This function extracts just the ``default`` values into a flat dict.

    Args:
        parameters_config: ``parameters`` block from YAML.

    Returns:
        Dict of parameter name → default value.
    """
    defaults: dict[str, Any] = {}
    for param_name, param_spec in parameters_config.items():
        if isinstance(param_spec, dict) and "default" in param_spec:
            defaults[param_name] = param_spec["default"]
    return defaults
