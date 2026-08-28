"""Tests for CostControlService — pure logic (rate limit, cost, budget).

(Migrated from qa app — 2026-08-04)
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from gaf_ai.models import LLMUsageLog
from gaf_ai.qa_cost_control import (
    DEFAULT_MONTHLY_BUDGET,
    RATE_LIMIT_PER_MINUTE,
    CostControlService,
)


class CheckRateLimitTests(TestCase):
    """CostControlService.check_rate_limit — frequency control."""

    def test_under_limit_returns_true(self):
        """No recent calls returns True (allowed)."""
        user = User.objects.create_user(username='rl-user', password='p', role='operator')
        self.assertTrue(CostControlService.check_rate_limit(user.id))

    def test_at_limit_returns_false(self):
        """Reaching RATE_LIMIT_PER_MINUTE calls in 1 minute returns False."""
        user = User.objects.create_user(username='rl-blocked', password='p', role='operator')
        for _ in range(RATE_LIMIT_PER_MINUTE):
            LLMUsageLog.objects.create(user=user, model_name='m')
        self.assertFalse(CostControlService.check_rate_limit(user.id))

    def test_old_calls_not_counted(self):
        """Calls older than 1 minute do not count toward rate limit."""
        user = User.objects.create_user(username='rl-old', password='p', role='operator')
        old_time = timezone.now() - timedelta(minutes=5)
        for _ in range(RATE_LIMIT_PER_MINUTE + 5):
            log = LLMUsageLog.objects.create(user=user, model_name='m')
            LLMUsageLog.objects.filter(pk=log.pk).update(created_at=old_time)
        self.assertTrue(CostControlService.check_rate_limit(user.id))


class EstimateCostTests(TestCase):
    """CostControlService.estimate_cost — price table lookup."""

    def test_known_model_gpt4o(self):
        """gpt-4o cost uses known price per 1K tokens."""
        cost = CostControlService.estimate_cost('gpt-4o', input_tokens=1000, output_tokens=500)
        self.assertEqual(cost, Decimal('0.007500'))

    def test_known_model_gpt4o_mini(self):
        """gpt-4o-mini cost uses cheaper price."""
        cost = CostControlService.estimate_cost('gpt-4o-mini', input_tokens=2000, output_tokens=1000)
        self.assertEqual(cost, Decimal('0.000900'))

    def test_unknown_model_uses_default(self):
        """Unknown model falls back to default price."""
        cost = CostControlService.estimate_cost('unknown-model', input_tokens=1000, output_tokens=1000)
        self.assertEqual(cost, Decimal('0.010000'))

    def test_zero_tokens_zero_cost(self):
        """Zero tokens produce zero cost."""
        cost = CostControlService.estimate_cost('gpt-4o', input_tokens=0, output_tokens=0)
        self.assertEqual(cost, Decimal('0.000000'))


class RecordUsageTests(TestCase):
    """CostControlService.record_usage — creates LLMUsageLog and returns cost."""

    def test_creates_log_entry(self):
        """record_usage creates an LLMUsageLog record."""
        user = User.objects.create_user(username='ru-user', password='p', role='operator')
        cost = CostControlService.record_usage(
            user_id=user.id, model_name='gpt-4o-mini',
            input_tokens=500, output_tokens=200, call_type='qa',
        )
        self.assertEqual(LLMUsageLog.objects.count(), 1)
        log = LLMUsageLog.objects.first()
        self.assertEqual(log.model_name, 'gpt-4o-mini')
        self.assertEqual(log.input_tokens, 500)
        self.assertEqual(log.output_tokens, 200)
        self.assertEqual(log.call_type, 'qa')
        self.assertEqual(log.cost_estimate, cost)

    def test_returns_cost_decimal(self):
        """record_usage returns the estimated cost as Decimal."""
        user = User.objects.create_user(username='ru-cost', password='p', role='operator')
        cost = CostControlService.record_usage(
            user_id=user.id, model_name='gpt-4o',
            input_tokens=1000, output_tokens=0,
        )
        self.assertEqual(cost, Decimal('0.002500'))

    def test_with_route(self):
        """record_usage stores route field."""
        user = User.objects.create_user(username='ru-route', password='p', role='operator')
        CostControlService.record_usage(
            user_id=user.id, model_name='m',
            input_tokens=10, output_tokens=10, route='backup',
        )
        log = LLMUsageLog.objects.first()
        self.assertEqual(log.route, 'backup')


class CheckBudgetTests(TestCase):
    """CostControlService.check_budget — monthly budget status."""

    def test_no_usage_returns_normal(self):
        """User with no usage gets status='normal'."""
        user = User.objects.create_user(username='b-empty', password='p', role='operator')
        result = CostControlService.check_budget(user.id)
        self.assertEqual(result['status'], 'normal')
        self.assertEqual(result['usage'], 0.0)
        self.assertEqual(result['budget'], float(DEFAULT_MONTHLY_BUDGET))

    def test_warning_threshold(self):
        """Usage >= 80% of budget returns status='warning'."""
        user = User.objects.create_user(username='b-warn', password='p', role='operator')
        LLMUsageLog.objects.create(user=user, model_name='gpt-4o', cost_estimate=Decimal('42.00'))
        result = CostControlService.check_budget(user.id)
        self.assertEqual(result['status'], 'warning')
        self.assertGreaterEqual(result['percentage'], 80)

    def test_exceeded_threshold(self):
        """Usage >= 100% of budget returns status='exceeded'."""
        user = User.objects.create_user(username='b-exceed', password='p', role='operator')
        LLMUsageLog.objects.create(user=user, model_name='gpt-4o', cost_estimate=Decimal('60.00'))
        result = CostControlService.check_budget(user.id)
        self.assertEqual(result['status'], 'exceeded')
        self.assertGreaterEqual(result['percentage'], 100)

    def test_custom_budget(self):
        """Custom monthly_budget parameter is respected."""
        user = User.objects.create_user(username='b-custom', password='p', role='operator')
        LLMUsageLog.objects.create(user=user, model_name='m', cost_estimate=Decimal('5.00'))
        result = CostControlService.check_budget(user.id, monthly_budget=Decimal('10.00'))
        self.assertEqual(result['budget'], 10.0)
        self.assertEqual(result['percentage'], 50.0)
        self.assertEqual(result['status'], 'normal')
