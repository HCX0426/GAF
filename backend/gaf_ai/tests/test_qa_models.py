"""Tests for qa models: QASession, LLMUsageLog (migrated from qa app — 2026-08-04)."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from gaf_ai.models import LLMUsageLog, QASession


class QASessionModelTests(TestCase):
    """QASession model creation, defaults, __str__, indexes."""

    def test_create_with_defaults(self):
        """QASession created with question gets default field values."""
        session = QASession.objects.create(question='How to use GAF?')
        self.assertEqual(session.context_snapshot, {})
        self.assertEqual(session.answer, '')
        self.assertFalse(session.is_knowledge_entry)
        self.assertIsNone(session.user)
        self.assertEqual(session.model_name, '')
        self.assertIsNotNone(session.created_at)
        self.assertIsNotNone(session.updated_at)

    def test_str_short_question(self):
        """__str__ returns full question when <= 50 chars."""
        session = QASession.objects.create(question='Short question?')
        self.assertEqual(str(session), 'Short question?')

    def test_str_long_question_truncated(self):
        """__str__ truncates to 50 chars with ellipsis when question is long."""
        long_q = 'A' * 100
        session = QASession.objects.create(question=long_q)
        self.assertEqual(str(session), 'A' * 50 + '...')

    def test_str_boundary_exactly_50_chars(self):
        """__str__ returns full question when exactly 50 chars."""
        q = 'B' * 50
        session = QASession.objects.create(question=q)
        self.assertEqual(str(session), q)

    def test_user_foreign_key_set_null_on_delete(self):
        """QASession.user uses SET_NULL, so deleting user nullifies the field."""
        user = User.objects.create_user(username='qa-user', password='pass123', role='operator')
        session = QASession.objects.create(question='q', user=user)
        user.delete()
        session.refresh_from_db()
        self.assertIsNone(session.user)

    def test_is_knowledge_entry_flag(self):
        """is_knowledge_entry can be toggled to True."""
        session = QASession.objects.create(question='q', is_knowledge_entry=True)
        self.assertTrue(session.is_knowledge_entry)
        session.is_knowledge_entry = False
        session.save()
        session.refresh_from_db()
        self.assertFalse(session.is_knowledge_entry)

    def test_ordering_by_created_at_desc(self):
        """QASession Meta ordering is -created_at (newest first)."""
        first = QASession.objects.create(question='first')
        QASession.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timedelta(seconds=10),
        )
        second = QASession.objects.create(question='second')
        sessions = list(QASession.objects.all())
        self.assertEqual(sessions[0], second)
        self.assertEqual(sessions[1], first)


class LLMUsageLogModelTests(TestCase):
    """LLMUsageLog model creation, defaults, __str__, indexes."""

    def test_create_with_defaults(self):
        """LLMUsageLog created with model_name gets default field values."""
        log = LLMUsageLog.objects.create(model_name='gpt-4o-mini')
        self.assertEqual(log.input_tokens, 0)
        self.assertEqual(log.output_tokens, 0)
        self.assertEqual(log.cost_estimate, Decimal('0'))
        self.assertEqual(log.call_type, '')
        self.assertEqual(log.route, '')
        self.assertIsNone(log.user)
        self.assertIsNotNone(log.created_at)

    def test_str_representation_with_user(self):
        """__str__ includes user, model and token counts."""
        user = User.objects.create_user(username='log-user', password='pass123', role='operator')
        log = LLMUsageLog.objects.create(
            user=user, model_name='gpt-4o', input_tokens=100, output_tokens=50,
        )
        s = str(log)
        self.assertIn('gpt-4o', s)
        self.assertIn('100', s)
        self.assertIn('50', s)

    def test_str_without_user(self):
        """__str__ works when user is None."""
        log = LLMUsageLog.objects.create(model_name='deepseek-chat')
        s = str(log)
        self.assertIn('deepseek-chat', s)

    def test_user_set_null_on_delete(self):
        """LLMUsageLog.user uses SET_NULL."""
        user = User.objects.create_user(username='del-user', password='pass123', role='admin')
        log = LLMUsageLog.objects.create(user=user, model_name='m')
        user.delete()
        log.refresh_from_db()
        self.assertIsNone(log.user)

    def test_route_field_values(self):
        """route field can store degradation route values."""
        for route in ('preferred', 'backup', 'local', 'offline'):
            LLMUsageLog.objects.create(model_name='m', route=route)
        self.assertEqual(LLMUsageLog.objects.count(), 4)

    def test_cost_estimate_precision(self):
        """cost_estimate DecimalField stores 6 decimal places."""
        log = LLMUsageLog.objects.create(
            model_name='m', cost_estimate=Decimal('0.000123'),
        )
        log.refresh_from_db()
        self.assertEqual(log.cost_estimate, Decimal('0.000123'))

    def test_ordering_by_created_at_desc(self):
        """LLMUsageLog Meta ordering is -created_at (newest first)."""
        first = LLMUsageLog.objects.create(model_name='a')
        LLMUsageLog.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timedelta(seconds=10),
        )
        second = LLMUsageLog.objects.create(model_name='b')
        logs = list(LLMUsageLog.objects.all())
        self.assertEqual(logs[0], second)
        self.assertEqual(logs[1], first)
