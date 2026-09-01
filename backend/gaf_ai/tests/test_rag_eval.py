"""scripts/ai/rag_eval.py evaluation logic tests (Phase 3).

Loads the eval script module without running its CLI, injects a fake
retriever, seeds real knowledge QASessions, and verifies Hit Rate @k and
MRR computation.
"""
import importlib.util
import os
from unittest import mock

from django.test import TestCase

from accounts.factories import AdminUserFactory
from gaf_ai.models import QASession

_SCRIPT = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'scripts', 'ai', 'rag_eval.py')
_SPEC = importlib.util.spec_from_file_location('rag_eval', os.path.abspath(_SCRIPT))
rag_eval = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rag_eval)


class RagEvalComputeTest(TestCase):
    """Hit Rate / MRR computed correctly from retrieval results."""

    def setUp(self):
        self.user = AdminUserFactory()

    def _qa(self, question, answer):
        return QASession.objects.create(
            user=self.user,
            question=question,
            answer=answer,
            is_knowledge_entry=True,
        )

    def test_relevant_lexical_threshold(self):
        self.assertTrue(rag_eval._relevant('fix the timeout error', 'how to fix the timeout error in the pipeline', 0.3))
        self.assertFalse(rag_eval._relevant('fix the timeout error', 'totally unrelated device screenshot', 0.3))
        self.assertFalse(rag_eval._relevant('', 'abc', 0.3))
        self.assertFalse(rag_eval._relevant('abc', '', 0.3))

    def test_hit_rate_and_mrr(self):
        # QA 1: fake retriever returns the matching doc first → hit@1, MRR 1.0
        self._qa('how to fix timeout', 'increase timeout in pipeline config')
        # QA 2: matching doc only at index 2 → hit@3 but not hit@1; MRR 1/3
        self._qa('template match failed', 'template match failed on button.png not found')

        def fake_reranked(query, top_k=5, pool_size=10, llm_rerank=False):
            if 'timeout' in query.lower():
                return [
                    {'content': 'increase timeout in pipeline config', 'filepath': '/a.py', 'rerank_score': 1.0},
                    {'content': 'other unrelated content here', 'filepath': '/b.py', 'rerank_score': 0.5},
                ]
            return [
                {'content': 'unrelated first result', 'filepath': '/x.py', 'rerank_score': 0.6},
                {'content': 'another unrelated doc', 'filepath': '/y.py', 'rerank_score': 0.5},
                {'content': 'template match failed on button.png not found', 'filepath': '/z.py', 'rerank_score': 0.4},
            ]

        with mock.patch('gaf_ai.rag.get_rag_retriever') as m:
            m.return_value = mock.Mock(search_reranked=fake_reranked)
            report = rag_eval.evaluate(top_k=5, limit=50, similarity=0.3)

        self.assertEqual(report['n'], 2)
        self.assertEqual(report['hits'][1], 1)   # QA1 hit@1
        self.assertEqual(report['hits'][3], 2)   # both hit within top-3
        self.assertEqual(report['hit_rate_k'][1], 0.5)
        self.assertEqual(report['hit_rate_k'][3], 1.0)
        self.assertAlmostEqual(report['mrr'], (1.0 + 1.0 / 3.0) / 2.0)

    def test_no_sessions_reports_zero(self):
        with mock.patch('gaf_ai.rag.get_rag_retriever'):
            report = rag_eval.evaluate(top_k=5, limit=50, similarity=0.3)
        self.assertEqual(report['n'], 0)
        self.assertEqual(report['mrr'], 0.0)
