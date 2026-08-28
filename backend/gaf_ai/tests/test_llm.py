# Merged from test_rag.py, test_llm_router.py - 2026-08-04

"""Tests for RAG retriever (P-035).

Covers backend/gaf_ai/rag.py:
- RAGRetriever with chromadb available (mocked collection)
- RAGRetriever with chromadb unavailable (fallback to QASession)
- _fallback_search keyword matching logic
- index_document / index_code_files / search interfaces
- get_rag_retriever singleton

Strategy:
- For chromadb-available paths: mock self._collection with a fake that
  records add() calls and returns canned query() results.
- For fallback paths: force self._collection = None and create real
  QASession fixtures (Django TestCase with DB).
- For CHROMADB_AVAILABLE=False: patch the module flag.
"""
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings

from gaf_ai.llm_router import (
    LLMAllClientsFailedError,
    LLMRouter,
    LLMRouterError,
    OfflineClient,
)
from gaf_ai.models import QASession
from gaf_ai.qa_llm_client import BaseLLMClient, LLMAPIError, LLMTimeoutError
from gaf_ai.rag import RAGRetriever, get_rag_retriever
from gaf_ai.tasks_rag import auto_index_rag


class FakeChromaCollection:
    """Fake ChromaDB collection for testing.

    Records add() calls in self.docs and returns canned query() results.
    """

    def __init__(self):
        self.docs = []  # list of {id, content, metadata}
        self._query_result = None

    def add(self, documents, ids, metadatas):
        for doc, doc_id, meta in zip(documents, ids, metadatas, strict=False):
            self.docs.append({'id': doc_id, 'content': doc, 'metadata': meta})

    def upsert(self, documents, ids, metadatas):
        # TD-396: replace-by-id semantics. First writes append, later
        # rewrites keep the existing record (fake only cares about count
        # and hash diff behavior).
        existing = {d['id'] for d in self.docs}
        for doc, doc_id, meta in zip(documents, ids, metadatas, strict=False):
            if doc_id in existing:
                continue
            self.docs.append({'id': doc_id, 'content': doc, 'metadata': meta})

    def get(self, ids, include=None):
        by_id = {d['id']: d for d in self.docs}
        ids_out, metas = [], []
        for doc_id in ids:
            ids_out.append(doc_id)
            metas.append(by_id[doc_id]['metadata'] if doc_id in by_id else None)
        return {'ids': ids_out, 'metadatas': metas}

    def query(self, query_texts, n_results):
        if self._query_result:
            return self._query_result
        # Default: return whatever we have, up to n_results
        n = min(n_results, len(self.docs))
        return {
            'documents': [[d['content'] for d in self.docs[:n]]],
            'metadatas': [[d['metadata'] for d in self.docs[:n]]],
            'distances': [[0.1 * i for i in range(n)]],
            'ids': [[d['id'] for d in self.docs[:n]]],
        }

    def set_query_result(self, result):
        self._query_result = result


# ── RAGRetriever with mocked chromadb collection ───────────────
class RAGRetrieverWithChromaTest(SimpleTestCase):
    """Tests for RAGRetriever when chromadb is available and collection is initialized."""

    def _make_retriever_with_fake_collection(self):
        """Create a RAGRetriever and replace its _collection with a fake."""
        with patch('gaf_ai.rag.CHROMADB_AVAILABLE', True), \
             patch('gaf_ai.rag.chromadb') as mock_chromadb:
            fake_collection = FakeChromaCollection()
            mock_chromadb.PersistentClient.return_value.get_or_create_collection.return_value = fake_collection
            mock_chromadb.Settings = MagicMock()
            retriever = RAGRetriever(persist_dir=tempfile.mkdtemp())
            retriever._collection = fake_collection
            return retriever, fake_collection

    def test_index_document_returns_true(self):
        retriever, _ = self._make_retriever_with_fake_collection()

        result = retriever.index_document('doc1', 'hello world', {'type': 'test'})

        self.assertTrue(result)

    def test_index_document_stores_in_collection(self):
        retriever, fake = self._make_retriever_with_fake_collection()

        retriever.index_document('doc1', 'hello world', {'type': 'test'})
        retriever.index_document('doc2', 'another doc', {'type': 'code'})

        self.assertEqual(len(fake.docs), 2)
        self.assertEqual(fake.docs[0]['id'], 'doc1')
        self.assertEqual(fake.docs[0]['content'], 'hello world')
        self.assertEqual(fake.docs[1]['id'], 'doc2')

    def test_index_document_no_collection_returns_false(self):
        """If _collection is None (chromadb unavailable), index returns False."""
        retriever, _ = self._make_retriever_with_fake_collection()
        retriever._collection = None

        result = retriever.index_document('doc1', 'hello')

        self.assertFalse(result)

    def test_search_returns_results_from_collection(self):
        retriever, fake = self._make_retriever_with_fake_collection()
        retriever.index_document('doc1', 'Template match failed', {'filepath': '/a.py', 'filename': 'a.py', 'type': 'code'})

        results = retriever.search('template match', top_k=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['content'], 'Template match failed')
        self.assertEqual(results[0]['filepath'], '/a.py')
        self.assertEqual(results[0]['filename'], 'a.py')
        self.assertEqual(results[0]['type'], 'code')
        self.assertIn('score', results[0])

    def test_search_truncates_content_to_500_chars(self):
        retriever, fake = self._make_retriever_with_fake_collection()
        long_content = 'x' * 1000
        retriever.index_document('doc1', long_content, {})

        results = retriever.search('query', top_k=1)

        self.assertEqual(len(results[0]['content']), 500)

    def test_search_empty_collection_returns_empty_list(self):
        retriever, fake = self._make_retriever_with_fake_collection()

        results = retriever.search('anything', top_k=5)

        self.assertEqual(results, [])

    # ── RAGRetriever fallback (chromadb unavailable) ────────────────
class RAGRetrieverFallbackTest(TestCase):
    """Tests for RAGRetriever when chromadb is NOT available.

    In this mode, _collection is None and search() delegates to
    _fallback_search() which queries QASession knowledge entries.
    """

    def _make_retriever_without_chroma(self):
        """Create a RAGRetriever with chromadb unavailable."""
        with patch('gaf_ai.rag.CHROMADB_AVAILABLE', False):
            retriever = RAGRetriever(persist_dir=tempfile.mkdtemp())
            return retriever

    def test_init_without_chroma_leaves_collection_none(self):
        retriever = self._make_retriever_without_chroma()

        self.assertIsNone(retriever._collection)

    def test_search_without_chroma_uses_fallback(self):
        retriever = self._make_retriever_without_chroma()
        QASession.objects.create(
            question='How to debug agent?',
            answer='Use the diagnostic tool.',
            is_knowledge_entry=True,
        )

        results = retriever.search('debug agent', top_k=5)

        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]['type'], 'qa_history')
        self.assertIn('debug', results[0]['content'].lower())

    def test_fallback_search_keyword_matching(self):
        """Fallback search scores by keyword overlap."""
        retriever = self._make_retriever_without_chroma()
        # Higher overlap → higher score → ranked first
        QASession.objects.create(
            question='How to configure LLM provider?',
            answer='Use the AI Config page to set provider and API key.',
            is_knowledge_entry=True,
        )
        QASession.objects.create(
            question='Random unrelated question',
            answer='Random answer about something else entirely.',
            is_knowledge_entry=True,
        )

        results = retriever.search('configure LLM', top_k=5)

        # The first result should be the LLM config one (higher keyword overlap)
        self.assertTrue(len(results) >= 1)
        self.assertIn('LLM', results[0]['content'])

    def test_fallback_search_ignores_non_knowledge_entries(self):
        """Only is_knowledge_entry=True QASessions are searched."""
        retriever = self._make_retriever_without_chroma()
        QASession.objects.create(
            question='How to configure LLM?',
            answer='Use the AI Config page.',
            is_knowledge_entry=False,  # Not a knowledge entry
        )

        results = retriever.search('configure LLM', top_k=5)

        self.assertEqual(results, [])

    def test_fallback_search_no_matches_returns_empty(self):
        retriever = self._make_retriever_without_chroma()

        results = retriever.search('nonexistent_xyz_123', top_k=5)

        self.assertEqual(results, [])

    def test_fallback_search_respects_top_k(self):
        retriever = self._make_retriever_without_chroma()
        for i in range(7):
            QASession.objects.create(
                question=f'How to configure LLM part {i}?',
                answer=f'Use the LLM config page. Option {i}.',
                is_knowledge_entry=True,
            )

        results = retriever.search('LLM configure', top_k=3)

        self.assertLessEqual(len(results), 3)

    def test_search_exception_falls_back_to_keyword(self):
        """If collection.query() raises, should fall back to _fallback_search."""
        retriever = self._make_retriever_without_chroma()
        # Create a QASession knowledge entry for the fallback to find
        QASession.objects.create(
            question='How to configure LLM?',
            answer='Use the AI Config page.',
            is_knowledge_entry=True,
        )
        # Give the retriever a fake collection that throws on query()
        fake_collection = MagicMock()
        fake_collection.query.side_effect = RuntimeError('boom')
        retriever._collection = fake_collection

        results = retriever.search('LLM configure', top_k=5)

        # Should have fallen back to keyword search
        self.assertTrue(len(results) > 0)
        self.assertEqual(results[0]['type'], 'qa_history')

    def test_index_document_without_chroma_returns_false(self):
        retriever = self._make_retriever_without_chroma()

        result = retriever.index_document('doc1', 'hello')

        self.assertFalse(result)

    def test_index_code_files_without_chroma_returns_0(self):
        retriever = self._make_retriever_without_chroma()

        count = retriever.index_code_files('/tmp/nonexistent_dir')

        self.assertEqual(count, 0)


# ── index_code_files tests ──────────────────────────────────────
class IndexCodeFilesTest(SimpleTestCase):
    """Tests for index_code_files() with a real temp directory."""

    def test_indexes_python_and_md_files(self):
        retriever, fake = self._make_retriever_with_fake_collection()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            with open(os.path.join(tmpdir, 'test.py'), 'w') as f:
                f.write('print("hello")')
            with open(os.path.join(tmpdir, 'README.md'), 'w') as f:
                f.write('# Test')
            with open(os.path.join(tmpdir, 'ignore.txt'), 'w') as f:
                f.write('should be ignored')

            count = retriever.index_code_files(tmpdir)

        self.assertEqual(count, 2)  # .py and .md, not .txt
        self.assertEqual(len(fake.docs), 2)

    def test_ignores_node_modules_and_pycache(self):
        retriever, fake = self._make_retriever_with_fake_collection()
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, 'node_modules'))
            os.makedirs(os.path.join(tmpdir, '__pycache__'))
            with open(os.path.join(tmpdir, 'main.py'), 'w') as f:
                f.write('print("main")')
            with open(os.path.join(tmpdir, 'node_modules', 'dep.py'), 'w') as f:
                f.write('print("dep")')
            with open(os.path.join(tmpdir, '__pycache__', 'cached.py'), 'w') as f:
                f.write('print("cached")')

            count = retriever.index_code_files(tmpdir)

        self.assertEqual(count, 1)  # only main.py

    def test_indexes_ts_and_tsx_files(self):
        retriever, fake = self._make_retriever_with_fake_collection()
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'app.ts'), 'w') as f:
                f.write('const x = 1;')
            with open(os.path.join(tmpdir, 'Component.tsx'), 'w') as f:
                f.write('export const C = () => null;')

            count = retriever.index_code_files(tmpdir)

        self.assertEqual(count, 2)

    def test_indexes_python_by_function(self):
        """Python files are split into module + function + class chunks via AST."""
        retriever, fake = self._make_retriever_with_fake_collection()
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'sample.py'), 'w') as f:
                f.write(
                    'def foo():\n'
                    '    return 1\n'
                    '\n'
                    'def bar():\n'
                    '    return 2\n'
                    '\n'
                    'class Baz:\n'
                    '    def method_one(self):\n'
                    '        pass\n'
                    '    def method_two(self):\n'
                    '        pass\n'
                )
            count = retriever.index_code_files(tmpdir)

        # module + foo + bar + Baz + method_one + method_two = 6 chunks
        self.assertGreaterEqual(count, 4)
        doc_ids = [d['id'] for d in fake.docs]
        self.assertTrue(any('::module' in did for did in doc_ids))
        self.assertTrue(any('::foo' in did for did in doc_ids))
        self.assertTrue(any('::bar' in did for did in doc_ids))
        self.assertTrue(any('::Baz' in did for did in doc_ids))
        # Verify metadata has symbol_type
        for doc in fake.docs:
            if '::module' in doc['id']:
                self.assertEqual(doc['metadata']['symbol_type'], 'module')
            elif '::foo' in doc['id']:
                self.assertEqual(doc['metadata']['symbol_type'], 'function')
                self.assertEqual(doc['metadata']['symbol_name'], 'foo')
            elif '::Baz' in doc['id']:
                self.assertEqual(doc['metadata']['symbol_type'], 'class')
                self.assertEqual(doc['metadata']['symbol_name'], 'Baz')

    def test_indexes_typescript_by_line_window(self):
        """TypeScript files are split into ~80-line windows with 10-line overlap."""
        retriever, fake = self._make_retriever_with_fake_collection()
        with tempfile.TemporaryDirectory() as tmpdir:
            ts_path = os.path.join(tmpdir, 'big.ts')
            lines = [f'const x{i} = {i};' for i in range(200)]
            with open(ts_path, 'w') as f:
                f.write('\n'.join(lines))
            count = retriever.index_code_files(tmpdir)

        # 200 lines, window=80, overlap=10 → 3 chunks
        # (1-80, 71-150, 141-200)
        self.assertEqual(count, 3)
        # Verify chunk metadata
        for doc in fake.docs:
            self.assertIn('chunk_start', doc['metadata'])
            self.assertIn('chunk_end', doc['metadata'])

    def test_indexes_markdown_by_header(self):
        """Markdown files are split by ## headers."""
        retriever, fake = self._make_retriever_with_fake_collection()
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'doc.md'), 'w') as f:
                f.write(
                    '# Title\n'
                    '\n'
                    '## Section One\n'
                    'content one\n'
                    '\n'
                    '## Section Two\n'
                    'content two\n'
                    '\n'
                    '## Section Three\n'
                    'content three\n'
                )
            count = retriever.index_code_files(tmpdir)

        self.assertEqual(count, 3)
        doc_ids = [d['id'] for d in fake.docs]
        # Slug: "Section One" → "section-one", doc_id suffix = "section_section-one"
        self.assertTrue(any('section-one' in did for did in doc_ids))
        self.assertTrue(any('section-two' in did for did in doc_ids))
        self.assertTrue(any('section-three' in did for did in doc_ids))
        # Verify metadata has section_title
        titles = [doc['metadata'].get('section_title') for doc in fake.docs]
        self.assertIn('Section One', titles)
        self.assertIn('Section Two', titles)
        self.assertIn('Section Three', titles)

    def test_python_syntax_error_falls_back_to_whole_file(self):
        """Invalid Python is indexed as a single module chunk."""
        retriever, fake = self._make_retriever_with_fake_collection()
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'bad.py'), 'w') as f:
                f.write('def broken(\n')  # SyntaxError: unterminated
            count = retriever.index_code_files(tmpdir)

        self.assertEqual(count, 1)
        self.assertEqual(len(fake.docs), 1)
        self.assertEqual(fake.docs[0]['metadata']['symbol_type'], 'module')
        self.assertEqual(fake.docs[0]['metadata']['type'], 'code')

    def test_reindex_same_content_is_no_op(self):
        """TD-396: unchanged source is NOT re-embedded on the next scan."""
        retriever, fake = self._make_retriever_with_fake_collection()
        tmpdir = tempfile.mkdtemp()
        try:
            py_path = os.path.join(tmpdir, 'sample.py')
            with open(py_path, 'w') as f:
                f.write('def foo():\n    return 1\n')
            first = retriever.index_code_files(tmpdir)
            self.assertGreater(first, 0)
            self.assertEqual(len(fake.docs), first)

            # Second scan with identical content → nothing re-embedded
            second = retriever.index_code_files(tmpdir)
            self.assertEqual(second, 0)
            self.assertEqual(len(fake.docs), first)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_reindex_only_changed_files(self):
        """TD-396: only chunks whose content changed are re-embedded."""
        retriever, fake = self._make_retriever_with_fake_collection()
        tmpdir = tempfile.mkdtemp()
        try:
            other_path = os.path.join(tmpdir, 'other.py')
            with open(other_path, 'w') as f:
                f.write('def foo():\n    return 1\n')
            first = retriever.index_code_files(tmpdir)

            # Modify other.py only
            with open(other_path, 'w') as f:
                f.write('def foo():\n    return 2\n')
            second = retriever.index_code_files(tmpdir)
            self.assertEqual(second, first)  # changed module+function chunks
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _make_retriever_with_fake_collection(self):
        """Helper shared with the chroma test class above."""
        with patch('gaf_ai.rag.CHROMADB_AVAILABLE', True), \
             patch('gaf_ai.rag.chromadb') as mock_chromadb:
            fake_collection = FakeChromaCollection()
            mock_chromadb.PersistentClient.return_value.get_or_create_collection.return_value = fake_collection
            mock_chromadb.Settings = MagicMock()
            retriever = RAGRetriever(persist_dir=tempfile.mkdtemp())
            retriever._collection = fake_collection
            return retriever, fake_collection


# ── get_rag_retriever singleton tests ───────────────────────────
class GetRagRetrieverTest(SimpleTestCase):
    """Tests for the get_rag_retriever() singleton factory."""

    def setUp(self):
        # Reset the singleton between tests
        import gaf_ai.rag as rag_module
        rag_module._rag_instance = None

    def test_returns_rag_retriever_instance(self):
        retriever = get_rag_retriever()

        self.assertIsInstance(retriever, RAGRetriever)

    def test_returns_same_instance_on_second_call(self):
        r1 = get_rag_retriever()
        r2 = get_rag_retriever()

        self.assertIs(r1, r2)

    def test_uses_base_dir_for_persist_dir(self):
        """When Django settings are available, persist_dir should be under BASE_DIR."""
        from django.conf import settings
        retriever = get_rag_retriever()

        self.assertIn('data', retriever.persist_dir)
        self.assertTrue(retriever.persist_dir.startswith(str(settings.BASE_DIR)))


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class AutoIndexRagTaskTest(SimpleTestCase):
    """Tests for the periodic RAG auto-index Celery task (merged from test_rag_auto_index.py)."""

    @patch('gaf_ai.tasks_rag.get_rag_retriever')
    def test_auto_index_rag_calls_index_code_files(self, mock_get_retriever):
        """Task calls index_code_files for agent/src and backend/gaf_ai."""
        mock_retriever = MagicMock()
        mock_retriever.index_code_files.side_effect = [5, 3]
        mock_get_retriever.return_value = mock_retriever

        auto_index_rag.apply()

        # Should call index_code_files twice (agent + backend)
        self.assertEqual(mock_retriever.index_code_files.call_count, 2)
        # Verify the paths end with the expected directories
        calls = mock_retriever.index_code_files.call_args_list
        paths = [call.args[0] for call in calls]
        self.assertTrue(
            any(p.endswith(('agent/src', 'agent\\src')) for p in paths),
            f'Expected one path ending with agent/src, got {paths}',
        )
        # TD-116 (2026-07-15): app renamed backend/ai → backend/gaf_ai.
        self.assertTrue(
            any(p.endswith(('backend/gaf_ai', 'backend\\gaf_ai')) for p in paths),
            f'Expected one path ending with backend/gaf_ai, got {paths}',
        )

    @patch('gaf_ai.tasks_rag.get_rag_retriever')
    def test_auto_index_rag_returns_counts(self, mock_get_retriever):
        """Task returns a dict with agent_chunks and backend_chunks."""
        mock_retriever = MagicMock()
        mock_retriever.index_code_files.side_effect = [10, 7]
        mock_get_retriever.return_value = mock_retriever

        result = auto_index_rag.apply()

        self.assertTrue(result.successful())
        self.assertEqual(
            result.result,
            {'agent_chunks': 10, 'backend_chunks': 7},
        )

    @patch('gaf_ai.tasks_rag.get_rag_retriever')
    def test_auto_index_rag_retries_on_failure(self, mock_get_retriever):
        """Task calls self.retry when index_code_files raises."""
        mock_retriever = MagicMock()
        mock_retriever.index_code_files.side_effect = RuntimeError('boom')
        mock_get_retriever.return_value = mock_retriever

        # Patch retry on the task instance so we can verify it was called
        # without actually scheduling a retry.
        with patch.object(
            auto_index_rag, 'retry', side_effect=Exception('retry dispatched')
        ) as mock_retry:
            result = auto_index_rag.apply()

        # Task did not succeed (retry raised)
        self.assertFalse(result.successful())
        # self.retry was called with the original exception + countdown
        mock_retry.assert_called_once()
        call_kwargs = mock_retry.call_args.kwargs
        self.assertEqual(call_kwargs.get('countdown'), 60)
        self.assertIsInstance(call_kwargs.get('exc'), RuntimeError)

    @patch('gaf_ai.tasks_rag.get_rag_retriever')
    def test_auto_index_rag_warns_when_backend_dir_missing(self, mock_get_retriever):
        """Missing backend/gaf_ai dir warns and indexes agent only."""
        mock_retriever = MagicMock()
        mock_retriever.index_code_files.side_effect = [7]
        mock_get_retriever.return_value = mock_retriever

        with patch('pathlib.Path.is_dir', return_value=False), \
             patch('gaf_ai.tasks_rag.logger') as mock_logger:
            result = auto_index_rag.apply()

        self.assertEqual(mock_retriever.index_code_files.call_count, 1)
        self.assertTrue(result.successful())
        self.assertEqual(result.result, {'agent_chunks': 7, 'backend_chunks': 0})
        mock_logger.warning.assert_called_once()


"""Tests for LLMRouter 4-level fallback chain (P-032).

Covers:
- Normal progression: preferred -> backup -> local -> offline
- Skip unregistered levels (partial chain)
- LLMAllClientsFailedError when no clients registered
- LLMAllClientsFailedError when all live clients fail and no offline fallback
- Unknown exceptions are caught (defensive BLE001)
- last_successful_level tracking
- route field tagging
- stream_chat fallback (best-effort, commits after first chunk)
- OfflineClient returns default content with offline=True flag
"""


class FakeLLMClient(BaseLLMClient):
    """Test double that returns a preset response or raises a preset error.

    Usage:
        client = FakeLLMClient(route_name='preferred', content='hi')
        client = FakeLLMClient(raises=LLMAPIError('boom'))
    """

    def __init__(
        self,
        route_name: str = 'fake',
        content: str = 'fake-response',
        raises: Exception | None = None,
        stream_chunks: list[str] | None = None,
    ):
        self.route_name = route_name
        self._content = content
        self._raises = raises
        self._stream_chunks = stream_chunks if stream_chunks is not None else [content]
        self.chat_calls = 0
        self.stream_calls = 0

    def chat(self, messages, model=None, temperature=0.7, max_tokens=4096, **kwargs):
        self.chat_calls += 1
        if self._raises is not None:
            raise self._raises
        return {
            'content': self._content,
            'usage': {'input_tokens': 5, 'output_tokens': 10, 'total_tokens': 15},
            'model': self.route_name,
        }

    def stream_chat(self, messages, model=None, temperature=0.7, max_tokens=4096, **kwargs):
        self.stream_calls += 1
        if self._raises is not None:
            raise self._raises
        # If raises mid-stream, the first next() will surface it.
        yield from self._stream_chunks


# ── OfflineClient tests ─────────────────────────────────────────
class OfflineClientTest(SimpleTestCase):
    """OfflineClient is the always-succeeds last-resort fallback."""

    def test_returns_default_content(self):
        client = OfflineClient()
        result = client.chat(messages=[{'role': 'user', 'content': 'hi'}])
        self.assertEqual(result['content'], OfflineClient.DEFAULT_CONTENT)
        self.assertTrue(result['offline'])
        self.assertEqual(result['model'], 'offline')
        self.assertEqual(result['usage']['total_tokens'], 0)

    def test_custom_default_content(self):
        custom = '[offline] custom message'
        client = OfflineClient(default_content=custom)
        result = client.chat(messages=[])
        self.assertEqual(result['content'], custom)

    def test_stream_yields_single_chunk(self):
        client = OfflineClient()
        chunks = list(client.stream_chat(messages=[]))
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], OfflineClient.DEFAULT_CONTENT)


# ── LLMRouter registration tests ────────────────────────────────
class LLMRouterRegistrationTest(SimpleTestCase):
    """Router registration and property accessors."""

    def test_default_levels(self):
        router = LLMRouter()
        self.assertEqual(router.levels, ('preferred', 'backup', 'local', 'offline'))

    def test_custom_levels(self):
        router = LLMRouter(levels=('primary', 'secondary'))
        self.assertEqual(router.levels, ('primary', 'secondary'))

    def test_register_unknown_level_raises(self):
        router = LLMRouter()
        with self.assertRaises(LLMRouterError):
            router.register('unknown', FakeLLMClient())

    def test_registered_levels_in_chain_order(self):
        router = LLMRouter()
        router.register('offline', OfflineClient())
        router.register('preferred', FakeLLMClient())
        # Should be in chain order, not registration order.
        self.assertEqual(router.registered_levels, ['preferred', 'offline'])

    def test_get_client_returns_none_for_unregistered(self):
        router = LLMRouter()
        self.assertIsNone(router.get_client('preferred'))

    def test_last_successful_level_starts_none(self):
        router = LLMRouter()
        self.assertIsNone(router.last_successful_level)


# ── LLMRouter chat() fallback tests ─────────────────────────────
class LLMRouterChatTest(SimpleTestCase):
    """chat() fallback behavior across the 4-level chain."""

    def test_preferred_succeeds_no_fallback(self):
        """If preferred returns successfully, backup/local/offline are not called."""
        router = LLMRouter()
        preferred = FakeLLMClient(route_name='preferred', content='from-preferred')
        backup = FakeLLMClient(route_name='backup')
        router.register('preferred', preferred)
        router.register('backup', backup)

        result = router.chat(messages=[{'role': 'user', 'content': 'hi'}])

        self.assertEqual(result['content'], 'from-preferred')
        self.assertEqual(result['route'], 'preferred')
        self.assertEqual(router.last_successful_level, 'preferred')
        self.assertEqual(preferred.chat_calls, 1)
        self.assertEqual(backup.chat_calls, 0, 'backup should not be called when preferred succeeds')

    def test_preferred_fails_falls_back_to_backup(self):
        """LLMAPIError on preferred → backup is tried."""
        router = LLMRouter()
        preferred = FakeLLMClient(raises=LLMAPIError('preferred down'))
        backup = FakeLLMClient(route_name='backup', content='from-backup')
        router.register('preferred', preferred)
        router.register('backup', backup)

        result = router.chat(messages=[])

        self.assertEqual(result['content'], 'from-backup')
        self.assertEqual(result['route'], 'backup')
        self.assertEqual(preferred.chat_calls, 1)
        self.assertEqual(backup.chat_calls, 1)

    def test_timeout_falls_back_to_backup(self):
        """LLMTimeoutError is also caught and triggers fallback."""
        router = LLMRouter()
        preferred = FakeLLMClient(raises=LLMTimeoutError('preferred timed out'))
        backup = FakeLLMClient(route_name='backup', content='from-backup')
        router.register('preferred', preferred)
        router.register('backup', backup)

        result = router.chat(messages=[])

        self.assertEqual(result['route'], 'backup')

    def test_preferred_and_backup_fail_falls_to_local(self):
        """Both cloud levels fail → local is tried."""
        router = LLMRouter()
        router.register('preferred', FakeLLMClient(raises=LLMAPIError('down')))
        router.register('backup', FakeLLMClient(raises=LLMAPIError('down')))
        router.register('local', FakeLLMClient(route_name='local', content='from-local'))

        result = router.chat(messages=[])

        self.assertEqual(result['content'], 'from-local')
        self.assertEqual(result['route'], 'local')

    def test_all_live_fail_falls_to_offline(self):
        """All live clients fail → offline level returns default."""
        router = LLMRouter()
        router.register('preferred', FakeLLMClient(raises=LLMAPIError('down')))
        router.register('backup', FakeLLMClient(raises=LLMAPIError('down')))
        router.register('local', FakeLLMClient(raises=LLMAPIError('down')))
        router.register('offline', OfflineClient())

        result = router.chat(messages=[])

        self.assertEqual(result['route'], 'offline')
        self.assertTrue(result['offline'])
        self.assertEqual(router.last_successful_level, 'offline')

    def test_skips_unregistered_levels(self):
        """If only preferred + offline are registered, backup/local are skipped."""
        router = LLMRouter()
        router.register('preferred', FakeLLMClient(raises=LLMAPIError('down')))
        router.register('offline', OfflineClient())

        result = router.chat(messages=[])

        # Should skip backup and local (not registered) and land on offline.
        self.assertEqual(result['route'], 'offline')

    def test_no_clients_registered_raises(self):
        """Calling chat() with no clients raises LLMAllClientsFailedError."""
        router = LLMRouter()
        with self.assertRaises(LLMAllClientsFailedError):
            router.chat(messages=[])

    def test_all_live_fail_no_offline_raises(self):
        """All live clients fail + no offline fallback → raise."""
        router = LLMRouter()
        router.register('preferred', FakeLLMClient(raises=LLMAPIError('down')))
        # Note: no offline level registered.
        with self.assertRaises(LLMAllClientsFailedError):
            router.chat(messages=[])

    def test_unknown_exception_also_triggers_fallback(self):
        """Non-LLM exceptions (e.g. ConnectionError) should also trigger fallback (BLE001 defense)."""
        router = LLMRouter()
        # ConnectionError is not LLMAPIError/LLMTimeoutError, but should still fall through.
        router.register('preferred', FakeLLMClient(raises=ConnectionError('network gone')))
        router.register('backup', FakeLLMClient(route_name='backup', content='from-backup'))

        result = router.chat(messages=[])

        self.assertEqual(result['route'], 'backup')

    def test_route_field_added_to_response(self):
        """Successful response should be tagged with the 'route' key."""
        router = LLMRouter()
        router.register('preferred', FakeLLMClient(content='hi'))

        result = router.chat(messages=[])

        self.assertIn('route', result)
        self.assertEqual(result['route'], 'preferred')

    def test_kwargs_forwarded_to_client(self):
        """Extra kwargs (e.g. timeout) should be forwarded to client.chat()."""
        router = LLMRouter()
        client = FakeLLMClient(content='ok')
        router.register('preferred', client)

        with patch.object(
            FakeLLMClient, 'chat',
            autospec=True,
            side_effect=lambda self, messages, **kw: {
                'content': 'ok',
                'usage': {'total_tokens': 0},
                'model': 'fake',
                'received_kwargs': kw,
            },
        ) as mock_chat:
            router.chat(messages=[], timeout=30, custom_flag=True)
            mock_chat.assert_called_once()
            # The kwargs forwarded should include timeout and custom_flag.
            _, kwargs = mock_chat.call_args
            self.assertEqual(kwargs.get('timeout'), 30)
            self.assertTrue(kwargs.get('custom_flag'))
        # The patched response won't have 'route' since we bypassed the real chat;
        # but the real implementation adds it. This test only verifies forwarding.


# ── LLMRouter stream_chat() fallback tests ──────────────────────
class LLMRouterStreamTest(SimpleTestCase):
    """stream_chat() best-effort fallback semantics.

    Unlike chat(), streaming commits to the first client that yields
    a chunk — we cannot fall back mid-stream.
    """

    def test_stream_preferred_succeeds(self):
        router = LLMRouter()
        preferred = FakeLLMClient(
            route_name='preferred',
            stream_chunks=['chunk1', 'chunk2', 'chunk3'],
        )
        backup = FakeLLMClient(route_name='backup')
        router.register('preferred', preferred)
        router.register('backup', backup)

        chunks = list(router.stream_chat(messages=[]))

        self.assertEqual(chunks, ['chunk1', 'chunk2', 'chunk3'])
        self.assertEqual(preferred.stream_calls, 1)
        self.assertEqual(backup.stream_calls, 0)
        self.assertEqual(router.last_successful_level, 'preferred')

    def test_stream_preferred_fails_falls_to_backup(self):
        """If preferred raises before yielding, backup is tried."""
        router = LLMRouter()
        preferred = FakeLLMClient(raises=LLMAPIError('preferred down'))
        backup = FakeLLMClient(
            route_name='backup',
            stream_chunks=['backup-chunk'],
        )
        router.register('preferred', preferred)
        router.register('backup', backup)

        chunks = list(router.stream_chat(messages=[]))

        self.assertEqual(chunks, ['backup-chunk'])
        self.assertEqual(router.last_successful_level, 'backup')

    def test_stream_no_clients_raises(self):
        router = LLMRouter()
        with self.assertRaises(LLMAllClientsFailedError):
            list(router.stream_chat(messages=[]))

    def test_stream_offline_yields_default(self):
        router = LLMRouter()
        router.register('offline', OfflineClient())

        chunks = list(router.stream_chat(messages=[]))

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], OfflineClient.DEFAULT_CONTENT)


# ── Integration-style: full 4-level chain ───────────────────────
class LLMRouterFullChainTest(SimpleTestCase):
    """End-to-end exercise of all 4 levels in a single test."""

    def test_full_chain_progression(self):
        """All live clients fail in sequence, offline catches at the end."""
        router = LLMRouter()
        preferred = FakeLLMClient(raises=LLMAPIError('preferred 5xx'))
        backup = FakeLLMClient(raises=LLMTimeoutError('backup timeout'))
        local = FakeLLMClient(raises=ConnectionError('local unreachable'))
        offline = OfflineClient()
        router.register('preferred', preferred)
        router.register('backup', backup)
        router.register('local', local)
        router.register('offline', offline)

        result = router.chat(messages=[{'role': 'user', 'content': 'help'}])

        self.assertEqual(result['route'], 'offline')
        self.assertTrue(result['offline'])
        self.assertEqual(preferred.chat_calls, 1)
        self.assertEqual(backup.chat_calls, 1)
        self.assertEqual(local.chat_calls, 1)
        # OfflineClient doesn't track chat_calls via FakeLLMClient, but we can
        # verify the response content matches the default.
        self.assertEqual(result['content'], OfflineClient.DEFAULT_CONTENT)
        self.assertEqual(router.last_successful_level, 'offline')


class TestVisionCapabilityRouting(SimpleTestCase):
    """spec §7.2.2 — LLM 路由按模型能力暴露视觉工具.

    覆盖 ``is_vision_capable(model)`` + ``get_tools_for_model(model)``:
    - 视觉模型 (gpt-4o / gpt-4o-mini / claude-3-5-sonnet) 应得到 6 个工具
      (含 get_screenshot_base64).
    - 纯文本模型 (deepseek-chat / qwen2.5 / unknown) 应得到 5 个工具
      (不含 get_screenshot_base64), 避免调用视觉工具后 base64 解码失败.
    """

    def test_is_vision_capable_returns_true_for_known_vision_models(self):
        """gpt-4o / gpt-4o-mini / claude-3-5-sonnet 应识别为视觉模型."""
        from gaf_ai.llm_router import is_vision_capable

        self.assertTrue(is_vision_capable('gpt-4o'))
        self.assertTrue(is_vision_capable('gpt-4o-mini'))
        self.assertTrue(is_vision_capable('claude-3-5-sonnet'))

    def test_is_vision_capable_returns_false_for_text_only_models(self):
        """deepseek-chat / qwen2.5 / unknown 应识别为纯文本模型."""
        from gaf_ai.llm_router import is_vision_capable

        self.assertFalse(is_vision_capable('deepseek-chat'))
        self.assertFalse(is_vision_capable('qwen2.5'))
        self.assertFalse(is_vision_capable('unknown-model'))
        self.assertFalse(is_vision_capable(''))

    def test_is_vision_capable_matches_model_name_prefix(self):
        """模型名常带版本后缀 (gpt-4o-2024-08-06), 应前缀匹配."""
        from gaf_ai.llm_router import is_vision_capable

        self.assertTrue(is_vision_capable('gpt-4o-2024-08-06'))
        self.assertTrue(is_vision_capable('claude-3-5-sonnet-20240620'))
        self.assertTrue(is_vision_capable('gpt-4o-mini-2024-07-18'))

    def test_get_tools_for_model_includes_screenshot_tool_for_vision_models(self):
        """视觉模型应拿到 6 个工具, 含 get_screenshot_base64."""
        from gaf_ai.llm_router import get_tools_for_model

        tools = get_tools_for_model('gpt-4o')
        tool_names = [t.name for t in tools]
        self.assertIn('get_screenshot_base64', tool_names)
        self.assertIn('get_structured_log', tool_names)
        self.assertEqual(len(tools), 6)

    def test_get_tools_for_model_excludes_screenshot_tool_for_text_models(self):
        """纯文本模型应拿到 5 个工具, 不含 get_screenshot_base64."""
        from gaf_ai.llm_router import get_tools_for_model

        tools = get_tools_for_model('deepseek-chat')
        tool_names = [t.name for t in tools]
        self.assertNotIn('get_screenshot_base64', tool_names)
        self.assertIn('get_structured_log', tool_names)
        self.assertEqual(len(tools), 5)

    def test_get_tools_for_model_unknown_model_defaults_to_text_only(self):
        """未知模型保守默认为纯文本 (5 个工具), 避免视觉工具调用失败."""
        from gaf_ai.llm_router import get_tools_for_model

        tools = get_tools_for_model('some-unknown-model')
        tool_names = [t.name for t in tools]
        self.assertNotIn('get_screenshot_base64', tool_names)
        self.assertEqual(len(tools), 5)
