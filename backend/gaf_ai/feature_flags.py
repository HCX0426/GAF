"""AI feature flag helpers (S5 Task A1 / P2-5).

Centralizes FeatureFlag lookups for AI features so callers do not
hard-code flag names or default semantics. Each helper:

- Returns ``True`` when the flag row is missing from the DB (fail-open
  default) so a fresh install without the seed migration still works.
- Returns the stored ``enabled`` value when the flag exists.
- Never raises — a corrupted DB row should not crash the request path;
  callers that need stricter behavior can check the value explicitly.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Canonical flag names — single source of truth, referenced by migrations,
# graph.py, qa/views.py, and tests.
AI_ASSISTANT_FLAG = 'ai_assistant_enabled'
LANGGRAPH_AGENT_FLAG = 'langgraph_agent_enabled'


def is_ai_assistant_enabled() -> bool:
    """Return whether the QA assistant endpoint is enabled.

    Defaults to ``True`` when the FeatureFlag row is missing (fail-open)
    so a fresh install keeps working without the seed migration.
    """
    from settings.models import FeatureFlag

    flag = FeatureFlag.objects.filter(name=AI_ASSISTANT_FLAG).first()
    if flag is None:
        return True
    return bool(flag.enabled)


def is_langgraph_agent_enabled() -> bool:
    """Return whether the LangGraph agent deep-analysis path is enabled.

    Defaults to ``True`` when the FeatureFlag row is missing (fail-open).
    """
    from settings.models import FeatureFlag

    flag = FeatureFlag.objects.filter(name=LANGGRAPH_AGENT_FLAG).first()
    if flag is None:
        return True
    return bool(flag.enabled)
