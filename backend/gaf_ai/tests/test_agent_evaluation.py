"""Agent evaluation metrics tests (Phase 3, TD-423 continuation).

Covers ``evaluation.evaluate_agent_sessions``:
- empty window → zeroed report
- completion rate / latency / tokens / cost aggregation
- tool-call counts from the trajectory ``tools`` steps
- agent-evaluation API endpoint wiring
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.factories import AdminUserFactory
from gaf_ai.agent.models import AgentSession
from gaf_ai.evaluation import evaluate_agent_sessions


def _session(user, *, status_: str = 'completed', tokens: int = 100, cost: float = 0.01,
             trajectory=None, created_days_ago: int = 0):
    created = timezone.now() - timedelta(days=created_days_ago)
    completed = created + timedelta(seconds=12)
    return AgentSession.objects.create(
        user=user,
        session_type=AgentSession.SessionType.LOG_ANALYSIS,
        status=status_,
        total_tokens=tokens,
        total_cost=cost,
        trajectory=trajectory or [],
        created_at=created,
        completed_at=completed if status_ == 'completed' else None,
    )


class EvaluateAgentSessionsTest(TestCase):
    def setUp(self):
        self.user = AdminUserFactory()

    def test_empty_window_zeroed(self):
        report = evaluate_agent_sessions(days=30)
        self.assertEqual(report['total_sessions'], 0)
        self.assertEqual(report['completion_rate'], 0.0)
        self.assertEqual(report['total_tokens'], 0)

    def test_aggregates_completion_latency_tokens(self):
        _session(self.user, status_='completed', tokens=200, cost=0.02)
        _session(self.user, status_='completed', tokens=100, cost=0.01)
        _session(self.user, status_='failed', tokens=50, cost=0.005)
        report = evaluate_agent_sessions(days=30)
        self.assertEqual(report['total_sessions'], 3)
        self.assertEqual(report['completed_sessions'], 2)
        self.assertEqual(report['failed_sessions'], 1)
        self.assertEqual(report['completion_rate'], round(2 / 3, 3))
        self.assertGreater(report['avg_latency_seconds'], 0)
        self.assertEqual(report['total_tokens'], 350)
        self.assertEqual(report['avg_tokens'], 117)  # round(350/3)
        self.assertAlmostEqual(report['total_cost'], 0.035, places=4)

    def test_tool_usage_from_trajectory(self):
        traj = [
            {'step': 1, 'type': 'router', 'tool_calls': [{'name': 'get_execution_steps'}]},
            {'step': 2, 'type': 'tools', 'names': ['get_execution_steps', 'get_execution_detail']},
            {'step': 3, 'type': 'responder'},
            {'step': 4, 'type': 'tools', 'names': ['search_similar_errors']},
        ]
        _session(self.user, trajectory=traj)
        report = evaluate_agent_sessions(days=30)
        self.assertEqual(report['total_sessions'], 1)
        self.assertEqual(report['sessions_with_tools'], 1)
        self.assertEqual(report['tool_steps'], 2)
        self.assertEqual(report['avg_tool_calls_per_session'], 3.0)

    def test_old_sessions_excluded_by_window(self):
        s = _session(self.user, status_='completed', created_days_ago=10)
        # created_at is auto_now_add; backdate it via update() to simulate age
        AgentSession.objects.filter(pk=s.pk).update(
            created_at=timezone.now() - timedelta(days=10),
        )
        report_7 = evaluate_agent_sessions(days=7)
        self.assertEqual(report_7['total_sessions'], 0)
        report_30 = evaluate_agent_sessions(days=30)
        self.assertEqual(report_30['total_sessions'], 1)


class AgentEvaluationApiTest(TestCase):
    """GET /api/v2/ai/agent-evaluation/ wiring."""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_endpoint_returns_report(self):
        _session(self.admin, status_='completed', trajectory=[
            {'step': 1, 'type': 'tools', 'names': ['get_execution_steps']},
        ])
        resp = self.client.get('/api/v2/ai/agent-evaluation/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data['data']  # UnifiedResponseMiddleware envelope
        self.assertEqual(data['total_sessions'], 1)
        self.assertEqual(data['sessions_with_tools'], 1)
        self.assertIn('completion_rate', data)
