"""Context collector for Skill execution — task-level context assembly.

Phase 4.5 implements the ``ContextCollector`` class per
``llm-integration-design.md`` §5.1. It reads a Skill's ``context``
config block (from the YAML definition) and collects the requested
context types from a ``task_context`` dict at execution time.

Collected context types:
  * screenshot_description / screenshots — base64-encoded images
  * log_content — truncated task execution log
  * task_config — serialised task definition
  * device_info — device hardware / runtime info

This module is the **task-context** collector. It is complementary
to ``backend/qa/context_builder.py:build_qa_context()`` which is the
**project-context** collector (architecture overview, skill summary,
directory structure, model definitions). Both are needed:
  * QA / general questions → ``build_qa_context()`` (project context)
  * Skill execution (error_diagnosis, log_analysis, etc.) →
    ``ContextCollector`` (task context from the execution that
    triggered the Skill)

Design §5.2 context size limits:
  * log text:     10000 chars  (keep last N lines)
  * screenshots:  3 images     (keep most recent)
  * task config:  5000 chars   (keep key fields)
  * device info:  1000 chars   (keep core info)
"""

import base64
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Default context size limits per design §5.2.
DEFAULT_MAX_LOG_CHARS = 10000
DEFAULT_MAX_SCREENSHOT_COUNT = 3
DEFAULT_MAX_TASK_CONFIG_CHARS = 5000
DEFAULT_MAX_DEVICE_INFO_CHARS = 1000


class ContextCollector:
    """Task-context collector driven by a Skill's ``context`` config.

    The collector is constructed with a config dict (typically the
    ``context:`` block from a Skill YAML) and called with a
    ``task_context`` dict containing the raw execution data. It
    returns a filtered / truncated dict suitable for inclusion in an
    LLM prompt.

    Example::

        collector = ContextCollector({
            "collect_screenshot": True,
            "collect_log": True,
            "max_log_lines": 100,
        })
        context = collector.collect(task_context)
        # → {"screenshot_description": ..., "screenshots": [...],
        #    "log_content": "..."}

    Config keys (all optional, defaults shown):
        collect_screenshot (bool, False)
        collect_log (bool, True)
        collect_task_config (bool, False)
        collect_device_info (bool, False)
        max_log_lines (int, 200) — applied to log_content
        max_screenshot_count (int, 3)
        max_task_config_chars (int, 5000)
        max_device_info_chars (int, 1000)
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = config or {}

    # ── Public API ──────────────────────────────────────────────
    def collect(self, task_context: dict[str, Any]) -> dict[str, Any]:
        """Collect context per the configured flags.

        Args:
            task_context: Raw execution data dict. May contain keys:
                ``log`` (str), ``screenshots`` (list[bytes|str]),
                ``screenshot_description`` (str), ``task_config`` (dict|str),
                ``device_info`` (dict|str).

        Returns:
            Filtered / truncated context dict with only the
            configured sections populated.
        """
        context: dict[str, Any] = {}

        if self._config.get("collect_screenshot", False):
            context["screenshot_description"] = self._collect_screenshot(task_context)
            context["screenshots"] = self._collect_screenshots(
                task_context,
                max_count=self._config.get(
                    "max_screenshot_count", DEFAULT_MAX_SCREENSHOT_COUNT
                ),
            )

        if self._config.get("collect_log", True):
            context["log_content"] = self._collect_log(
                task_context,
                max_lines=self._config.get("max_log_lines", 200),
            )

        if self._config.get("collect_task_config", False):
            context["task_config"] = self._collect_task_config(
                task_context,
                max_chars=self._config.get(
                    "max_task_config_chars", DEFAULT_MAX_TASK_CONFIG_CHARS
                ),
            )

        if self._config.get("collect_device_info", False):
            context["device_info"] = self._collect_device_info(
                task_context,
                max_chars=self._config.get(
                    "max_device_info_chars", DEFAULT_MAX_DEVICE_INFO_CHARS
                ),
            )

        return context

    # ── Section collectors ──────────────────────────────────────
    def _collect_log(self, context: dict[str, Any], max_lines: int = 200) -> str:
        """Collect log text, keeping the last ``max_lines`` lines.

        Args:
            context: Task context dict with optional ``log`` key.
            max_lines: Maximum number of lines to keep (from the end).

        Returns:
            Truncated log text, or empty string if no log present.
        """
        log = context.get("log", "")
        if not log or not isinstance(log, str):
            return ""

        lines = log.split("\n")
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
            return "\n".join(lines) + f"\n\n[日志已截断，仅保留最后 {max_lines} 行]"
        return "\n".join(lines)

    def _collect_screenshots(
        self, context: dict[str, Any], max_count: int = 3
    ) -> list[str]:
        """Collect screenshots as base64-encoded strings.

        Accepts both raw bytes (encoded to base64) and pre-encoded
        base64 strings. Filters out invalid entries first, then keeps
        the most recent ``max_count`` images (per design §5.2
        "keep most recent").

        Args:
            context: Task context dict with optional ``screenshots`` key.
            max_count: Maximum number of screenshots to keep (from end).

        Returns:
            List of base64-encoded screenshot strings.
        """
        screenshots = context.get("screenshots", [])
        if not isinstance(screenshots, list):
            return []

        # Filter first (skip non-bytes / non-str / empty entries),
        # then keep the last max_count (most recent).
        filtered: list[str] = []
        for ss in screenshots:
            if isinstance(ss, bytes):
                filtered.append(base64.b64encode(ss).decode("ascii"))
            elif isinstance(ss, str) and ss:
                filtered.append(ss)
            # Skip non-bytes / non-str entries silently

        if max_count > 0 and len(filtered) > max_count:
            filtered = filtered[-max_count:]
        return filtered

    def _collect_screenshot(self, context: dict[str, Any]) -> str:
        """Collect a text description of the latest screenshot.

        This is a textual description (not the image itself) used to
        give the LLM context about what the screenshot shows. The
        actual images are collected separately by
        ``_collect_screenshots()``.

        Args:
            context: Task context dict with optional
                ``screenshot_description`` key.

        Returns:
            Screenshot description text, or empty string.
        """
        desc = context.get("screenshot_description", "")
        if not isinstance(desc, str):
            return ""
        return desc

    def _collect_task_config(
        self, context: dict[str, Any], max_chars: int = 5000
    ) -> str:
        """Collect serialised task configuration.

        Args:
            context: Task context dict with optional ``task_config``
                key (dict or JSON string).
            max_chars: Maximum character count; truncates with marker.

        Returns:
            JSON-serialised task config string, truncated if needed.
        """
        config = context.get("task_config", "")
        if isinstance(config, dict):
            text = json.dumps(config, ensure_ascii=False, indent=2, default=str)
        elif isinstance(config, str):
            text = config
        else:
            return ""

        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[任务配置已截断]"
        return text

    def _collect_device_info(
        self, context: dict[str, Any], max_chars: int = 1000
    ) -> str:
        """Collect device hardware / runtime info.

        Args:
            context: Task context dict with optional ``device_info``
                key (dict or string).
            max_chars: Maximum character count; truncates with marker.

        Returns:
            Device info text, truncated if needed.
        """
        info = context.get("device_info", "")
        if isinstance(info, dict):
            text = json.dumps(info, ensure_ascii=False, indent=2, default=str)
        elif isinstance(info, str):
            text = info
        else:
            return ""

        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[设备信息已截断]"
        return text


# ── Module-level convenience function ──────────────────────────
def build_skill_context(
    skill_config: dict[str, Any] | None,
    task_context: dict[str, Any],
) -> dict[str, Any]:
    """Build task context for a Skill execution.

    Convenience wrapper: construct a ``ContextCollector`` from the
    Skill's ``context`` config block and collect the context.

    Args:
        skill_config: The Skill's ``context`` config dict (from YAML).
            If ``None``, returns an empty dict (no context collected —
            the Skill runs without task context). An empty dict ``{}``
            is treated as "use defaults" (collect_log=True by default).
        task_context: Raw execution data dict.

    Returns:
        Collected context dict, or empty dict if skill_config is None.
    """
    if skill_config is None:
        return {}
    collector = ContextCollector(skill_config)
    return collector.collect(task_context)


def build_qa_context_wrapper(
    question: str, extra_context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Thin wrapper around ``qa.context_builder.build_qa_context()``.

    This exists so callers that import from ``ai.context_collector``
    can access the project-context builder without a separate import.
    The actual implementation lives in ``qa/context_builder.py`` and
    is NOT refactored — it collects project-level context (architecture,
    skills, directory, models) which is complementary to the
    task-level context collected by ``ContextCollector``.
    """
    from gaf_ai.qa_context_builder import build_qa_context
    return build_qa_context(question, extra_context)
