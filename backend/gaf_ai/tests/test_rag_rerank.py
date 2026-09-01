"""RAG hybrid-retrieval + rerank unit tests (Phase 3, TD-423 continuation).

Covers:
- ``_keyword_similarity`` lexical signal
- ``_rrf_score`` reciprocal rank fusion
- ``_rerank_docs`` fused ordering: keyword-strong candidates move up,
  top_k respected, ``_idx`` stripped
- ``_llm_rerank``: failure falls back to local order; success re-orders
"""

from unittest import mock

from django.test import SimpleTestCase

from gaf_ai.rag import _keyword_similarity, _llm_rerank, _rerank_docs, _rrf_score


def _doc(idx: int, content: str) -> dict:
    return {'content': content, '_idx': idx, 'score': 0.0, 'filepath': f'/f{idx}.py'}


class KeywordSimilarityTest(SimpleTestCase):
    def test_exact_match_high(self):
        self.assertGreater(_keyword_similarity('template match failed', 'template match failed on btn.png'), 0.5)

    def test_unrelated_low(self):
        self.assertLess(_keyword_similarity('template match failed', 'totally different error about device'), 0.3)

    def test_empty_returns_zero(self):
        self.assertEqual(_keyword_similarity('', 'abc'), 0.0)
        self.assertEqual(_keyword_similarity('abc', ''), 0.0)


class RrfScoreTest(SimpleTestCase):
    def test_better_rank_higher_score(self):
        self.assertGreater(_rrf_score([0, 0]), _rrf_score([1, 1]))

    def test_combines_signals(self):
        both = _rrf_score([0, 0])
        one = _rrf_score([0, 5])
        self.assertGreater(both, one)


class RerankDocsTest(SimpleTestCase):
    def test_keyword_strong_doc_moves_up(self):
        # Vector order: doc0 best vector match but weak lexical; doc2 weaker
        # vector but strong keyword overlap with the query.
        docs = [
            _doc(0, 'the quick brown fox jumps over the lazy dog near the fence'),
            _doc(1, 'unrelated text about scheduling jobs and cron expressions'),
            _doc(2, 'template match failed: button.png not found in template directory'),
        ]
        out = _rerank_docs('template match failed', docs, top_k=3)
        # doc2 (strong keyword) must rank above doc0 (strong vector)
        self.assertEqual(out[0]['filepath'], '/f2.py')
        self.assertIn('rerank_score', out[0])

    def test_top_k_limits_results(self):
        docs = [_doc(i, f'template match failed sample {i}') for i in range(5)]
        out = _rerank_docs('template match failed', docs, top_k=2)
        self.assertEqual(len(out), 2)

    def test_internal_idx_stripped(self):
        docs = [_doc(0, 'template match failed'), _doc(1, 'other')]
        out = _rerank_docs('template match failed', docs, top_k=2)
        self.assertNotIn('_idx', out[0])

    def test_empty_input(self):
        self.assertEqual(_rerank_docs('q', []), [])


class LlmRerankTest(SimpleTestCase):
    def test_failure_falls_back_to_local_order(self):
        docs = [_doc(0, 'template match failed a'), _doc(1, 'template match failed b')]
        with mock.patch('gaf_ai.llm_service.call_llm', side_effect=RuntimeError('llm down')):
            out = _llm_rerank('template match failed', docs)
        self.assertEqual([d['_idx'] for d in out], [0, 1])

    def test_success_reorders(self):
        docs = [_doc(0, 'aaa'), _doc(1, 'bbb'), _doc(2, 'ccc')]
        with mock.patch('gaf_ai.llm_service.call_llm', return_value={'content': '2, 1'}):
            out = _llm_rerank('template match failed', docs)
        self.assertEqual([d['_idx'] for d in out], [1, 0, 2])
