"""Custom LLM pricing tests (TD-424 usage cost accuracy).

Covers ``llm_service.estimate_cost`` price resolution:
- no active config -> static pricing table by model / default row
- active config with custom input/output price -> overrides the table
- usage-stats by_model carries a per-model cost_usd
"""
from django.test import TestCase
from rest_framework.test import APIClient
from settings.models import LLMConfig

from accounts.factories import AdminUserFactory
from gaf_ai.llm_service import estimate_cost


class EstimateCostCustomPriceTest(TestCase):
    def test_no_config_uses_static_table(self):
        # gpt-4o-mini static price: 0.00015 in / 0.0006 out per 1K
        cost = estimate_cost('gpt-4o-mini', 1000, 1000)
        self.assertAlmostEqual(cost, 0.00015 + 0.0006, places=6)

    def test_unknown_model_uses_default_row(self):
        # deepseek-ai/DeepSeek-V4-Flash not in table -> default 0.002/0.008
        cost = estimate_cost('deepseek-ai/DeepSeek-V4-Flash', 1000, 1000)
        self.assertAlmostEqual(cost, 0.002 + 0.008, places=6)

    def test_active_config_custom_price_overrides(self):
        LLMConfig.objects.create(
            provider='openai', api_base='https://x/v1', default_model='m1',
            input_price=0.001, output_price=0.002, is_active=True,
        )
        cost = estimate_cost('m1', 1000, 1000)
        self.assertAlmostEqual(cost, 0.001 + 0.002, places=6)


class UsageStatsByModelCostTest(TestCase):
    """GET /api/v2/ai/usage-stats/ — by_model includes cost_usd."""

    def setUp(self):
        self.user = AdminUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        from gaf_ai.models import LLMUsageLog
        LLMUsageLog.objects.create(
            user=self.user, model_name='gpt-4o-mini',
            input_tokens=1000, output_tokens=1000,
            cost_estimate=0.00075, call_type='qa',
        )

    def test_by_model_has_cost(self):
        resp = self.client.get('/api/v2/ai/usage-stats/')
        self.assertEqual(resp.status_code, 200)
        data = resp.data['data']
        row = next(r for r in data['by_model'] if r['model'] == 'gpt-4o-mini')
        self.assertIn('cost_usd', row)
        self.assertGreater(row['cost_usd'], 0)
        self.assertEqual(row['tokens'], 2000)
