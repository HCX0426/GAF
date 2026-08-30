"""Tests for SLA metric models (migrated from metrics app — 2026-08-04).

Models under test: SLAMetric.
"""

from django.test import TestCase
from workers.models import Worker

from monitors.models import SLAMetric


class SLAMetricModelTests(TestCase):
    """SLAMetric model: creation, defaults, __str__, ordering, FK."""

    def test_create_with_defaults(self):
        metric = SLAMetric.objects.create(metric_name='cpu_usage', value=75.5)
        self.assertEqual(metric.labels, {})
        self.assertIsNone(metric.agent)
        self.assertIsNotNone(metric.timestamp)

    def test_str_representation(self):
        metric = SLAMetric.objects.create(metric_name='latency_ms', value=42.0)
        self.assertEqual(str(metric), 'latency_ms = 42.0')

    def test_agent_fk_cascade_delete(self):
        agent = Worker.objects.create(agent_id='m-agent-001', hostname='m-host')
        metric = SLAMetric.objects.create(
            metric_name='mem_usage', value=50, agent=agent,
        )
        metric_id = metric.id
        agent.delete()
        self.assertFalse(SLAMetric.objects.filter(id=metric_id).exists())

    def test_agent_nullable(self):
        """System-level metrics have agent=null."""
        metric = SLAMetric.objects.create(metric_name='uptime', value=99.9)
        self.assertIsNone(metric.agent)

    def test_ordering_by_timestamp_desc(self):
        import time
        SLAMetric.objects.create(metric_name='m', value=1)
        time.sleep(0.01)
        SLAMetric.objects.create(metric_name='m', value=2)
        values = list(SLAMetric.objects.values_list('value', flat=True))
        self.assertEqual(values[0], 2)
