"""LLM price table — single source of truth (S3 P2, 2026-08-16).

Both ``gaf_ai.llm_service.estimate_cost`` (display / routing cost) and
``gaf_ai.qa_cost_control.CostControlService`` (LLMUsageLog billing)
read from here so the same model never has two prices.

Kept dependency-free (no Django imports) so ``llm_service`` stays usable
in non-Django contexts (e.g. smoke tests).

Values are per 1K tokens in USD. The billing contract (asserted by
``test_qa_cost_control.py``) is the authority:
  * gpt-4o       0.0025 / 0.010
  * gpt-4o-mini  0.00015 / 0.0006
  * default      0.002 / 0.008
"""
from decimal import Decimal

PRICE_PER_1K_INPUT = {
    "gpt-4o": Decimal("0.0025"),
    "gpt-4o-mini": Decimal("0.00015"),
    "gpt-3.5-turbo": Decimal("0.0005"),
    "deepseek-chat": Decimal("0.00014"),
    "qwen-max": Decimal("0.0028"),
    "claude-3.5-sonnet": Decimal("0.003"),
    "default": Decimal("0.002"),
}

PRICE_PER_1K_OUTPUT = {
    "gpt-4o": Decimal("0.01"),
    "gpt-4o-mini": Decimal("0.0006"),
    "gpt-3.5-turbo": Decimal("0.0015"),
    "deepseek-chat": Decimal("0.00028"),
    "qwen-max": Decimal("0.0084"),
    "claude-3.5-sonnet": Decimal("0.015"),
    "default": Decimal("0.008"),
}
