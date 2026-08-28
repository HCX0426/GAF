"""LLM 成本控制 (migrated from qa app — 2026-08-04)."""

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Sum
from django.utils import timezone

from gaf_ai.models import LLMUsageLog
from gaf_ai.pricing import PRICE_PER_1K_INPUT, PRICE_PER_1K_OUTPUT

logger = logging.getLogger(__name__)

RATE_LIMIT_PER_MINUTE = 10
BUDGET_WARNING_THRESHOLD = Decimal("0.8")
DEFAULT_MONTHLY_BUDGET = Decimal("50.00")


class CostControlService:
    """LLM 成本控制服务"""

    @staticmethod
    def check_rate_limit(user_id: int) -> bool:
        one_minute_ago = timezone.now() - timedelta(minutes=1)
        recent_calls = LLMUsageLog.objects.filter(
            user_id=user_id, created_at__gte=one_minute_ago,
        ).count()
        return recent_calls < RATE_LIMIT_PER_MINUTE

    @staticmethod
    def estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> Decimal:
        input_price = PRICE_PER_1K_INPUT.get(model_name, PRICE_PER_1K_INPUT["default"])
        output_price = PRICE_PER_1K_OUTPUT.get(model_name, PRICE_PER_1K_OUTPUT["default"])
        cost = (
            Decimal(input_tokens) / 1000 * input_price
            + Decimal(output_tokens) / 1000 * output_price
        )
        return cost.quantize(Decimal("0.000001"))

    @staticmethod
    def record_usage(user_id: int, model_name: str, input_tokens: int, output_tokens: int,
                     call_type: str = "", route: str = "") -> Decimal:
        cost = CostControlService.estimate_cost(model_name, input_tokens, output_tokens)
        LLMUsageLog.objects.create(
            user_id=user_id, model_name=model_name,
            input_tokens=input_tokens, output_tokens=output_tokens,
            cost_estimate=cost, call_type=call_type, route=route,
        )
        return cost

    @staticmethod
    def check_budget(user_id: int, monthly_budget: Decimal = DEFAULT_MONTHLY_BUDGET) -> dict[str, Any]:
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_usage = (
            LLMUsageLog.objects.filter(
                user_id=user_id, created_at__gte=month_start,
            ).aggregate(total=Sum('cost_estimate'))['total']
            or Decimal("0")
        )
        percentage = (month_usage / monthly_budget * 100) if monthly_budget > 0 else 0
        result = {
            "budget": float(monthly_budget), "usage": float(month_usage),
            "percentage": float(percentage), "status": "normal",
        }
        if percentage >= 100:
            result["status"] = "exceeded"
        elif percentage >= BUDGET_WARNING_THRESHOLD * 100:
            result["status"] = "warning"
        return result
