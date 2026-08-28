"""Retrieval quality verification for RAG (TD-104 + TD-108).

Measures top-3 / top-5 / top-10 hit rate across 15 queries covering:
- English code symbol queries (function/class names)
- Chinese semantic queries (natural language)
- Error scenario queries
- Module path queries

TD-108 upgraded the embedding model from ChromaDB default
(all-MiniLM-L6-v2, English-only) to paraphrase-multilingual-MiniLM-L12-v2
(50+ languages) via fastembed. Chinese semantic query hit rate improved
from 16.7% to 80%.

Run: pytest backend/gaf_ai/tests/test_retrieval_quality.py -v

Requires ChromaDB to be indexed (run `auto_index_rag` task first, see TD-103).
"""
import logging

from django.test import TestCase

logger = logging.getLogger(__name__)

# 15 test cases: (query, expected_filename_or_filepath_substring)
# Pass if any top-k result's filename OR filepath contains the substring
# (case-insensitive). Expected substrings are verified to exist in the
# indexed codebase (TD-108: removed executor/scheduler/hook/websocket which
# don't exist as filenames in the GAF codebase).
TEST_CASES = [
    # English code symbol queries (5 cases — high confidence)
    ('auto_index_rag task', 'tasks_rag'),
    ('build_log_analysis_agent', 'graph'),
    ('create_agent LangGraph', 'graph'),
    ('FeatureFlag check', 'feature_flags'),
    ('RAGRetriever class', 'rag'),
    # Chinese semantic queries (5 cases — multilingual model)
    ('skill 执行失败', 'skill'),
    ('任务调度器', 'orchestrator'),
    ('截图方法', 'screenshot'),
    ('设备控制', 'device'),
    ('模板匹配', 'template'),
    # Error scenario queries (3 cases)
    ('WebSocket 连接', 'connection'),
    ('数据库迁移', 'migrations'),
    ('配置迁移失败', 'config_migrator'),
    # Module path queries (2 cases)
    ('agent orchestrator', 'orchestrator'),
    ('platform windows', 'windows'),
]


def _hit_at_k(results: list, expected_substr: str, k: int) -> bool:
    """Check if expected_substr appears in any top-k result filename/filepath."""
    expected_lower = expected_substr.lower()
    for r in results[:k]:
        filename = (r.get('filename') or '').lower()
        filepath = (r.get('filepath') or '').lower()
        if expected_lower in filename or expected_lower in filepath:
            return True
    return False


class RetrievalQualityTest(TestCase):
    """RAG retrieval quality test (TD-104 baseline + TD-108 multilingual upgrade).

    TD-108 upgraded embedding model to paraphrase-multilingual-MiniLM-L12-v2.
    Baseline hit rates after upgrade (15 queries):
    - top-3: 66.7%  (10/15)
    - top-5: 73.3%  (11/15)
    - top-10: 80.0% (12/15)
    - Chinese semantic (5 cases): 80.0% (4/5)
    - English symbol (5 cases):   80.0% (4/5)
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from gaf_ai.rag import get_rag_retriever
        cls.retriever = get_rag_retriever()
        # Verify ChromaDB is indexed (TD-103 must be fixed first)
        doc_count = cls.retriever._collection.count()
        if doc_count < 1:
            raise AssertionError(
                f'ChromaDB empty ({doc_count} docs). Run auto_index_rag task first (TD-103).'
            )
        cls.doc_count = doc_count

    def test_chromadb_has_indexed_docs(self):
        """ChromaDB collection has docs indexed (TD-103 prerequisite)."""
        self.assertGreaterEqual(self.doc_count, 1)

    def test_retrieval_top3_hit_rate(self):
        """top-3 hit rate across 15 queries >= 60% (TD-108 multilingual baseline)."""
        hits = sum(
            1 for query, expected in TEST_CASES
            if _hit_at_k(self.retriever.search(query, top_k=3), expected, 3)
        )
        rate = hits / len(TEST_CASES) * 100
        # TD-108: upgraded from 40% (English-only model) to 60% (multilingual).
        # Current baseline: 66.7%. Threshold leaves ~7% margin for variance.
        self.assertGreaterEqual(
            rate, 60.0,
            f'top-3 hit rate {rate:.1f}% ({hits}/{len(TEST_CASES)}) < 60% threshold. '
            f'Multilingual embedding model (TD-108) should achieve >= 60%.',
        )

    def test_retrieval_top10_hit_rate(self):
        """top-10 hit rate across 15 queries >= 70% (TD-108 multilingual baseline)."""
        hits = sum(
            1 for query, expected in TEST_CASES
            if _hit_at_k(self.retriever.search(query, top_k=10), expected, 10)
        )
        rate = hits / len(TEST_CASES) * 100
        # TD-108: upgraded from 50% (English-only model) to 70% (multilingual).
        # Current baseline: 80.0%. Threshold leaves ~10% margin for variance.
        self.assertGreaterEqual(
            rate, 70.0,
            f'top-10 hit rate {rate:.1f}% ({hits}/{len(TEST_CASES)}) < 70% threshold.',
        )

    def test_english_symbol_queries_high_hit_rate(self):
        """English symbol queries (5 cases) top-3 hit rate >= 80%."""
        english_cases = TEST_CASES[:5]
        hits = sum(
            1 for query, expected in english_cases
            if _hit_at_k(self.retriever.search(query, top_k=3), expected, 3)
        )
        rate = hits / len(english_cases) * 100
        self.assertGreaterEqual(
            rate, 80.0,
            f'English symbol queries top-3 hit rate {rate:.1f}% ({hits}/{len(english_cases)}) < 80%. '
            f'Symbol-name queries should match well with any embedding model.',
        )

    def test_chinese_semantic_queries_hit_rate(self):
        """Chinese semantic queries (5 cases) top-3 hit rate >= 60% (TD-108).

        Before TD-108 (English-only model): 16.7% (1/6).
        After TD-108 (multilingual model):  80.0% (4/5).
        """
        chinese_cases = TEST_CASES[5:10]
        hits = sum(
            1 for query, expected in chinese_cases
            if _hit_at_k(self.retriever.search(query, top_k=3), expected, 3)
        )
        rate = hits / len(chinese_cases) * 100
        # TD-108: multilingual model should achieve >= 60% for Chinese queries.
        # Current baseline: 80.0%. Threshold leaves ~20% margin for variance.
        self.assertGreaterEqual(
            rate, 60.0,
            f'Chinese semantic queries top-3 hit rate {rate:.1f}% ({hits}/{len(chinese_cases)}) < 60%. '
            f'Multilingual embedding model (TD-108) should handle Chinese queries.',
        )
