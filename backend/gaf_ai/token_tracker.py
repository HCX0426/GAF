"""Token usage tracker — per-Skill budget enforcement + usage reports.

Phase 4.6 implements the ``TokenUsageTracker`` class per
``llm-integration-design.md`` §6. It provides the design's API surface
(``record()`` / ``check_budget()`` / ``generate_usage_report()``) as a
thin wrapper over the existing DB-backed infrastructure:

  * ``qa.cost_control.CostControlService`` — static methods for cost
    estimation, rate limiting, monthly budget checks.
  * ``qa.models.LLMUsageLog`` — Django model storing each LLM call's
    token usage, cost, call_type, and route (Phase 4.4).

Design §6.1 specifies an in-memory ``_daily_usage`` dict, but since we
already persist every call to ``LLMUsageLog``, the in-memory cache is
redundant. This implementation uses ``LLMUsageLog`` as the source of
truth and aggregates on demand. The API contract matches the design so
callers can swap in this class without changes.

Skill-level budget enforcement (design §7.1):
  * max_tokens_per_call — enforced by the caller (passed to ``call_llm``)
  * max_calls_per_day   — checked by ``check_budget()``
  * max_cost_per_day    — checked by ``check_budget()``
"""

import logging
from decimal import Decimal
from typing import Any

from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)

# Default per-Skill daily limits per design §7.1.
DEFAULT_MAX_CALLS_PER_DAY = 50
DEFAULT_MAX_COST_PER_DAY = Decimal("1.0")


class TokenUsageTracker:
    """Token usage tracker backed by ``LLMUsageLog``.

    Provides per-Skill budget enforcement (call count + cost) and
    daily usage reports. All data is persisted to ``LLMUsageLog``;
    no in-memory state is maintained, so the tracker is stateless
    across requests.

    Example::

        tracker = TokenUsageTracker()
        tracker.record(user_id=1, model="gpt-4o-mini",
                       input_tokens=120, output_tokens=80,
                       cost=0.0002, call_type="qa_ask",
                       route="preferred")
        if tracker.check_budget(user_id=1, skill_config=skill.cost_control):
            ...  # within budget, can proceed
        report = tracker.generate_usage_report(user_id=1)
    """

    def record(
        self,
        user_id: int,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cost: float = 0.0,
        call_type: str = "",
        route: str = "",
    ) -> Decimal:
        """Record one LLM call's usage to ``LLMUsageLog``.

        Args:
            user_id: User ID initiating the call.
            model: Model name (e.g. ``"gpt-4o-mini"``).
            input_tokens: Prompt token count.
            output_tokens: Completion token count.
            cost: Pre-computed cost estimate (USD). If 0.0, the
                tracker re-estimates via ``CostControlService``.
            call_type: Call type tag (``"qa_ask"`` / ``"analysis"`` /
                ``"skill_error_diagnosis"`` etc.).
            route: LLMRouter level that served the call
                (``"preferred"`` / ``"backup"`` / ``"local"`` /
                ``"offline"``). Phase 4.4 field.

        Returns:
            Cost estimate as ``Decimal``.
        """
        from gaf_ai.qa_cost_control import CostControlService

        # If caller didn't compute cost, estimate from tokens.
        cost_decimal = (
            Decimal(str(cost)) if cost else CostControlService.estimate_cost(
                model, input_tokens, output_tokens
            )
        )

        CostControlService.record_usage(
            user_id=user_id,
            model_name=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            call_type=call_type,
            route=route,
        )
        # CostControlService.record_usage() re-estimates cost internally
        # and creates the LLMUsageLog row; we return the same value.
        return cost_decimal

    def check_budget(
        self,
        user_id: int,
        skill_config: dict[str, Any] | None = None,
    ) -> bool:
        """Check whether the user is within today's Skill-level budget.

        Per design §7.1, two limits are enforced:
          * ``max_calls_per_day`` — default 50
          * ``max_cost_per_day``  — default $1.0

        Args:
            user_id: User ID to check.
            skill_config: The Skill's ``cost_control`` block (from YAML).
                If ``None`` or missing keys, defaults are used.

        Returns:
            ``True`` if the user can make another call (within budget),
            ``False`` if either limit is exceeded.
        """
        from gaf_ai.models import LLMUsageLog

        cfg = skill_config or {}
        max_calls = int(cfg.get("max_calls_per_day", DEFAULT_MAX_CALLS_PER_DAY))
        max_cost = Decimal(str(cfg.get("max_cost_per_day", DEFAULT_MAX_COST_PER_DAY)))

        today_start = timezone.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        todays = LLMUsageLog.objects.filter(
            user_id=user_id,
            created_at__gte=today_start,
        )
        call_count = todays.count()
        total_cost = todays.aggregate(
            total=Sum("cost_estimate")
        )["total"] or Decimal("0")

        if call_count >= max_calls:
            logger.warning(
                "User %d hit daily call limit: %d >= %d",
                user_id, call_count, max_calls,
            )
            return False
        if total_cost >= max_cost:
            logger.warning(
                "User %d hit daily cost limit: $%.4f >= $%.4f",
                user_id, total_cost, max_cost,
            )
            return False
        return True

    def generate_usage_report(self, user_id: int) -> dict[str, Any]:
        """Generate today's usage report for the given user.

        Aggregates all ``LLMUsageLog`` rows created today for the user.

        Args:
            user_id: User ID.

        Returns:
            Dict with keys: ``date``, ``total_calls``,
            ``total_input_tokens``, ``total_output_tokens``,
            ``total_cost_usd``, ``models``, ``routes``.
        """
        from gaf_ai.models import LLMUsageLog

        today = timezone.now().strftime("%Y-%m-%d")
        today_start = timezone.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        todays = LLMUsageLog.objects.filter(
            user_id=user_id,
            created_at__gte=today_start,
        )

        total_input = 0
        total_output = 0
        total_cost = Decimal("0")
        models: dict[str, dict[str, Any]] = {}
        routes: dict[str, int] = {}

        for log in todays:
            total_input += log.input_tokens
            total_output += log.output_tokens
            total_cost += log.cost_estimate

            model_key = log.model_name or "unknown"
            if model_key not in models:
                models[model_key] = {"calls": 0, "cost": 0.0}
            models[model_key]["calls"] += 1
            models[model_key]["cost"] += float(log.cost_estimate)

            route_key = log.route or "unknown"
            routes[route_key] = routes.get(route_key, 0) + 1

        return {
            "date": today,
            "total_calls": todays.count(),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_usd": round(float(total_cost), 6),
            "models": models,
            "routes": routes,
        }


# Module-level singleton for convenience (stateless, safe to share).
_default_tracker: TokenUsageTracker | None = None


def get_token_tracker() -> TokenUsageTracker:
    """Return the module-level ``TokenUsageTracker`` singleton.

    The tracker is stateless (all data in DB), so a single shared
    instance is safe.
    """
    global _default_tracker
    if _default_tracker is None:
        _default_tracker = TokenUsageTracker()
    return _default_tracker
