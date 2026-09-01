"""
RAG 知识库模块 — ChromaDB 文档索引与检索
"""
import ast
import hashlib
import logging
import os
import re
import threading
import warnings

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("chromadb 未安装，RAG 功能将降级为关键词匹配")


# ── Embedding function ─────────────────────────────────────────
# Multilingual model so Chinese semantic queries match English code
# chunks. Uses fastembed (onnxruntime-backed, lightweight) instead of
# sentence-transformers (which would pull in PyTorch ~2GB).
# TD-108: upgraded from default all-MiniLM-L6-v2 (English-only).
_MULTILINGUAL_MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'


def _content_hash(content: str) -> str:
    """Stable content fingerprint stored in chunk metadata (TD-396).

    Used by the incremental indexer to skip re-embedding chunks whose
    content did not change since the last scan.
    """
    return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]


class FastembedMultilingualEF:
    """ChromaDB-compatible embedding function backed by fastembed.

    Wraps ``fastembed.TextEmbedding`` with the multilingual MiniLM model
    (384-dim, 50+ languages) so Chinese queries match English code.
    Implements the ChromaDB ``EmbeddingFunction`` protocol (``__call__``
    returning ``list[list[float]]``).
    """

    def __init__(self, model_name: str = _MULTILINGUAL_MODEL):
        from fastembed import TextEmbedding
        # Suppress fastembed mean-pooling behavior-change warning (cosmetic,
        # does not affect retrieval quality).
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            self._model = TextEmbedding(model_name=model_name)

    def _embed(self, input):
        """Internal: embed a list of texts, returning list[list[float]]."""
        # fastembed.embed accepts Iterable[str]; normalize single str to list
        if isinstance(input, str):
            input = [input]
        return [list(e) for e in self._model.embed(input)]

    def __call__(self, input):
        return self._embed(input)

    def embed_query(self, input):
        """Embed a query (ChromaDB calls this during collection.query)."""
        return self._embed(input)

    def embed_documents(self, input):
        """Embed documents (ChromaDB calls this during collection.add)."""
        return self._embed(input)

    def is_legacy(self) -> bool:
        """ChromaDB 1.5.x checks is_legacy to decide config serialization."""
        return False

    def default_space(self) -> str:
        """Default distance metric for this embedding function."""
        return 'cosine'

    def supported_spaces(self) -> list:
        """Supported distance metrics (ChromaDB EmbeddingFunction protocol)."""
        return ['cosine', 'l2', 'ip']

    @staticmethod
    def name() -> str:
        return 'fastembed_multilingual'

    def get_config(self) -> dict:
        """Return serializable config (ChromaDB EmbeddingFunction protocol)."""
        return {'model_name': _MULTILINGUAL_MODEL}

    @staticmethod
    def build_from_config(config: dict):
        """Build instance from config (ChromaDB EmbeddingFunction protocol)."""
        return FastembedMultilingualEF(model_name=config.get('model_name', _MULTILINGUAL_MODEL))


class RAGRetriever:
    """RAG 检索器"""

    def __init__(self, persist_dir: str = './data/chroma_db'):
        self.persist_dir = persist_dir
        self.collection_name = 'gaf_knowledge'
        self._client = None
        self._collection = None
        # TD-396: incremental-index batch buffer. When set (during
        # index_code_files), index_document defers the add so a full scan
        # can be diffed against existing content hashes and then put in
        # ONE bulk upsert (one batched embedding call) instead of one
        # ONNX inference per chunk.
        self._batch: list[tuple[str, str, dict]] | None = None
        self._init_chroma()

    def _init_chroma(self):
        """初始化 ChromaDB 持久化客户端"""
        if not CHROMADB_AVAILABLE:
            return
        try:
            os.makedirs(self.persist_dir, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=self.persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            # TD-108: use multilingual embedding model so Chinese queries
            # match English code chunks. Falls back to ChromaDB default
            # (English-only all-MiniLM-L6-v2) if fastembed unavailable.
            embedding_fn = None
            try:
                embedding_fn = FastembedMultilingualEF()
            except Exception as e:
                logger.warning(
                    "fastembed 初始化失败，降级到 ChromaDB 默认 embedding: %s", e
                )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={'hnsw:space': 'cosine'},
                embedding_function=embedding_fn,
            )
        except Exception as e:
            logger.warning(f"ChromaDB 初始化失败: {e}")

    def index_document(self, doc_id: str, content: str, metadata: dict = None) -> bool:
        """索引单个文档"""
        if not self._collection:
            return False
        meta = dict(metadata or {})
        meta.setdefault('content_hash', _content_hash(content))
        if self._batch is not None:
            # TD-396: deferred add — caller diffs the whole batch against
            # existing hashes and bulk-upserts only changed chunks.
            self._batch.append((doc_id, content, meta))
            return True
        try:
            self._collection.add(
                documents=[content],
                ids=[doc_id],
                metadatas=[meta],
            )
            return True
        except Exception as e:
            logger.warning(f"索引文档失败 {doc_id}: {e}")
            return False

    def index_code_files(self, base_dir: str) -> int:
        """Scan project code files and index them as fine-grained chunks.

        Python files are split by function/class via AST, TypeScript/TSX by
        fixed-size line windows, and Markdown by ``## `` headers.

        TD-396 (incremental index): chunks are collected in a batch first,
        then diffed against the content hashes already stored in ChromaDB.
        Only chunks whose content actually changed are re-embedded — and
        they are written in ONE bulk upsert per 64-chunk group, so the
        embedding function runs as a single batched ONNX inference instead
        of one inference per chunk (which held the GIL and froze daphne).
        With no source changes the return value is 0 and no embedding runs
        at all. Returns the number of chunks actually (re-)embedded.
        """
        if not self._collection:
            return 0
        self._batch = []
        try:
            for root, dirs, files in os.walk(base_dir):
                dirs[:] = [d for d in dirs if d not in ('node_modules', '.git', '__pycache__', 'venv')]
                for file in files:
                    filepath = os.path.join(root, file)
                    try:
                        if file.endswith('.py'):
                            self._index_python_file(filepath, file)
                        elif file.endswith(('.ts', '.tsx')):
                            self._index_ts_file(filepath, file)
                        elif file.endswith('.md'):
                            self._index_markdown_file(filepath, file)
                    except Exception as e:
                        logger.warning('Failed to index file %s: %s', filepath, e)
            return self._flush_batch()
        finally:
            self._batch = None

    def _flush_batch(self) -> int:
        """Diff collected chunks against existing content hashes and
        bulk-upsert only the changed ones (TD-396 incremental index)."""
        pending = self._batch or []
        if not pending:
            return 0
        # TD-396: the splitters can emit duplicate doc_ids (e.g. same-named
        # function + class method via ast.walk). ChromaDB rejects duplicate
        # ids in get()/add()/upsert() with DuplicateIDError — dedupe first
        # (last write wins) or every tick falls back to a full re-index.
        seen: dict[str, tuple[str, dict]] = {}
        for doc_id, content, meta in pending:
            seen[doc_id] = (content, meta)
        pending = [(doc_id, *entry) for doc_id, entry in seen.items()]
        try:
            existing = self._collection.get(
                ids=[doc_id for doc_id, _, _ in pending],
                include=['metadatas'],
            )
        except Exception as e:
            logger.warning('index_code_files: diff lookup failed, re-indexing all: %s', e)
            existing = {'ids': [], 'metadatas': []}
        old_hashes = {}
        for doc_id, meta in zip(existing.get('ids', []), existing.get('metadatas', []), strict=False):
            old_hashes[doc_id] = (meta or {}).get('content_hash')
        changed = [
            (doc_id, content, meta)
            for doc_id, content, meta in pending
            if old_hashes.get(doc_id) != meta['content_hash']
        ]
        if changed:
            logger.info(
                'index_code_files: %d scanned, %d changed (skipping %d unchanged)',
                len(pending), len(changed), len(pending) - len(changed),
            )
        else:
            logger.info(
                'index_code_files: %d chunks scanned, all up to date (no embedding run)',
                len(pending),
            )
        total = 0
        # One batched embedding call per group instead of per-chunk inference.
        for i in range(0, len(changed), 64):
            batch = changed[i:i + 64]
            try:
                self._collection.upsert(
                    documents=[chunk[1] for chunk in batch],
                    ids=[chunk[0] for chunk in batch],
                    metadatas=[chunk[2] for chunk in batch],
                )
                total += len(batch)
            except Exception as e:
                logger.warning('index_code_files: bulk upsert batch failed: %s', e)
        logger.info("索引完成: %d 个新 chunk 写入", total)
        return total

    # ── per-language chunk splitters ─────────────────────────────

    @staticmethod
    def _doc_id(filepath: str, suffix: str) -> str:
        """Build a stable doc_id from filepath + suffix."""
        return filepath.replace('\\', '/') + '::' + suffix

    def _index_python_file(self, filepath: str, filename: str) -> int:
        """Split a Python file by function/class using AST.

        Indexes a module-level chunk (whole file) plus one chunk per
        FunctionDef/AsyncFunctionDef/ClassDef node discovered via
        ``ast.walk``. Falls back to a single whole-file chunk on
        SyntaxError. Skips empty files (e.g., bare ``__init__.py``)
        to avoid near-zero embedding vectors polluting search results.
        """
        try:
            with open(filepath, encoding='utf-8') as f:
                source = f.read()
        except Exception as e:
            logger.warning('Failed to read file %s: %s', filepath, e)
            return 0

        # Skip empty / whitespace-only files (TD-108: empty __init__.py
        # produces near-zero embeddings that pollute cosine search).
        if not source.strip():
            return 0

        base_meta = {
            'filepath': filepath,
            'filename': filename,
            'type': 'code',
        }

        try:
            tree = ast.parse(source, filename=filepath)
        except SyntaxError:
            # Fallback: index whole file as a single module chunk
            doc_id = self._doc_id(filepath, 'module')
            self.index_document(doc_id, source, {
                **base_meta,
                'symbol_type': 'module',
            })
            return 1

        count = 0

        # Module chunk: whole file content provides full-file context
        module_id = self._doc_id(filepath, 'module')
        if self.index_document(module_id, source, {
            **base_meta,
            'symbol_type': 'module',
        }):
            count += 1

        # Function/class chunks
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol_type = 'function'
            elif isinstance(node, ast.ClassDef):
                symbol_type = 'class'
            else:
                continue

            content = ast.get_source_segment(source, node)
            if content is None:
                continue

            doc_id = self._doc_id(filepath, f'{node.name}:{node.lineno}')
            end_line = getattr(node, 'end_lineno', None) or node.lineno
            if self.index_document(doc_id, content, {
                **base_meta,
                'symbol_type': symbol_type,
                'symbol_name': node.name,
                'start_line': node.lineno,
                'end_line': end_line,
            }):
                count += 1

        return count

    def _index_ts_file(self, filepath: str, filename: str, window: int = 80, overlap: int = 10) -> int:
        """Split a TypeScript/TSX file by fixed-size line windows.

        Chunks of ~``window`` lines with ``overlap`` lines of context
        between consecutive chunks.
        """
        try:
            with open(filepath, encoding='utf-8') as f:
                source = f.read()
        except Exception as e:
            logger.warning('Failed to read file %s: %s', filepath, e)
            return 0

        lines = source.split('\n')
        if not lines or (len(lines) == 1 and not lines[0]):
            return 0

        count = 0
        start = 0
        total = len(lines)
        while start < total:
            end = min(start + window, total)
            chunk_content = '\n'.join(lines[start:end])
            # 1-indexed line numbers for human readability
            start_line = start + 1
            end_line = end
            doc_id = self._doc_id(filepath, f'chunk_{start_line}_{end_line}')
            if self.index_document(doc_id, chunk_content, {
                'filepath': filepath,
                'filename': filename,
                'type': 'code',
                'chunk_start': start_line,
                'chunk_end': end_line,
            }):
                count += 1
            if end >= total:
                break
            start = end - overlap
        return count

    def _index_markdown_file(self, filepath: str, filename: str) -> int:
        """Split a Markdown file by ``## `` headers.

        Each section (header line + body until next ``## `` or EOF) is a
        chunk. Falls back to a single whole-file chunk if no ``## ``
        headers are present.
        """
        try:
            with open(filepath, encoding='utf-8') as f:
                source = f.read()
        except Exception as e:
            logger.warning('Failed to read file %s: %s', filepath, e)
            return 0

        lines = source.split('\n')
        sections = []  # list of (title, [lines])
        current_title = None
        current_lines: list[str] = []

        for line in lines:
            if line.startswith('## '):
                if current_title is not None:
                    sections.append((current_title, current_lines))
                current_title = line[3:].strip()
                current_lines = [line]
            else:
                if current_title is not None:
                    current_lines.append(line)

        if current_title is not None:
            sections.append((current_title, current_lines))

        if not sections:
            # No ## headers: index whole file as one chunk
            doc_id = self._doc_id(filepath, 'module')
            if self.index_document(doc_id, source, {
                'filepath': filepath,
                'filename': filename,
                'type': 'doc',
            }):
                return 1
            return 0

        count = 0
        for title, section_lines in sections:
            slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-') or 'untitled'
            doc_id = self._doc_id(filepath, f'section_{slug}')
            content = '\n'.join(section_lines)
            if self.index_document(doc_id, content, {
                'filepath': filepath,
                'filename': filename,
                'type': 'doc',
                'section_title': title,
            }):
                count += 1
        return count

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """检索相关文档"""
        if not self._collection:
            return self._fallback_search(query, top_k)

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
            )
            docs = []
            if results.get('documents') and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    meta = results['metadatas'][0][i] if results.get('metadatas') else {}
                    docs.append({
                        'content': doc[:500],
                        'filepath': meta.get('filepath', ''),
                        'filename': meta.get('filename', ''),
                        'type': meta.get('type', ''),
                        'score': results['distances'][0][i] if results.get('distances') else 0,
                    })
            return docs
        except Exception as e:
            logger.warning(f"检索失败: {e}")
            return self._fallback_search(query, top_k)

    def search_reranked(self, query: str, top_k: int = 5, pool_size: int = 20,
                        llm_rerank: bool = False) -> list[dict]:
        """Hybrid retrieval + rerank (Phase 3, TD-423 continuation).

        1. Vector search pulls ``pool_size`` candidates (cosine distance).
        2. Keyword signal: :func:`_keyword_similarity` (difflib) between the
           query and each candidate snippet.
        3. Reciprocal Rank Fusion of the vector rank + keyword rank, plus a
           small keyword boost, so documents strong on BOTH signals win.
        4. Optional LLM rerank (default off) re-orders the top candidates
           via the active LLM — see :func:`_llm_rerank`.

        Returns up to ``top_k`` docs sorted by fused ``rerank_score``.
        """
        if not self._collection:
            return self._fallback_search(query, top_k)
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=max(pool_size, top_k),
            )
            docs = []
            if results.get('documents') and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    meta = results['metadatas'][0][i] if results.get('metadatas') else {}
                    docs.append({
                        'content': doc[:500],
                        'filepath': meta.get('filepath', ''),
                        'filename': meta.get('filename', ''),
                        'type': meta.get('type', ''),
                        'score': results['distances'][0][i] if results.get('distances') else 0,
                        '_idx': i,  # original vector rank position
                    })
            return _rerank_docs(query, docs, top_k=top_k, llm_rerank=llm_rerank)
        except Exception as e:
            logger.warning("混合检索失败: %s", e)
            return self._fallback_search(query, top_k)

    def _fallback_search(self, query: str, top_k: int) -> list[dict]:
        """降级方案：从 QASession 中搜索关键词"""
        from gaf_ai.models import QASession

        sessions = QASession.objects.filter(
            is_knowledge_entry=True,
        ).order_by('-created_at')[:top_k]

        results = []
        keywords = query.lower().split()
        for s in sessions:
            score = sum(1 for kw in keywords if kw in s.question.lower() or kw in s.answer.lower())
            if score > 0:
                results.append({
                    'content': f'Q: {s.question}\nA: {s.answer[:300]}',
                    'filepath': '',
                    'filename': '',
                    'type': 'qa_history',
                    'score': score,
                })
        return sorted(results, key=lambda x: x['score'], reverse=True)[:top_k]


# ── Hybrid rerank (Phase 3) ─────────────────────────────────────
_RRF_K = 60  # reciprocal rank fusion smoothing constant


def _keyword_similarity(query: str, content: str) -> float:
    """Lexical similarity between the query and a doc snippet (0..1)."""
    import difflib
    q = (query or '').lower()
    c = (content or '')[:300].lower()
    if not q or not c:
        return 0.0
    return difflib.SequenceMatcher(None, q, c).ratio()


def _rrf_score(ranks: list[int], k: int = _RRF_K) -> float:
    """Reciprocal rank fusion: sum(1/(k+rank+1)) over each signal's rank."""
    return sum(1.0 / (k + r + 1) for r in ranks)


def _llm_rerank(query: str, docs: list[dict]) -> list[dict]:
    """Re-order top candidates with the active LLM (best-first judgment).

    Default-off because every call costs tokens; falls back to the local
    fused order on any failure so retrieval never blocks.
    """
    if len(docs) <= 1:
        return docs
    try:
        from gaf_ai.llm_service import call_llm

        items = '\n'.join(
            f'{i + 1}. {d.get("content", "")[:180]}' for i, d in enumerate(docs)
        )
        prompt = (
            'You are a retrieval ranker. Given the query and candidate documents, '
            'return only the indices (comma-separated, best first) of the 1-2 most '
            'relevant candidates.\n'
            f'Query: {query}\nCandidates:\n{items}\n'
            'Indices:'
        )
        resp = call_llm(
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=16,
            temperature=0,
            stream=False,
        )
        content = resp.get('content', '') or ''
        picked = [
            i for tok in re.findall(r'\d+', content)
            if (i := int(tok) - 1) < len(docs)
        ]
        if picked:
            chosen = [docs[i] for i in picked]
            rest = [d for i, d in enumerate(docs) if i not in picked]
            return (chosen + rest)[:len(docs)]
    except Exception as exc:
        logger.warning('LLM rerank failed, keep local order: %s', exc)
    return docs


def _rerank_docs(query: str, docs: list[dict], top_k: int = 5,
                 llm_rerank: bool = False) -> list[dict]:
    """RRF-fuse vector rank + keyword rank, then optional LLM rerank.

    ``docs`` must carry ``_idx`` = original vector rank position (0 = best
    vector match). Returns up to ``top_k`` docs with an extra
    ``rerank_score`` key; the internal ``_idx`` key is stripped.
    """
    if not docs:
        return []
    vector_rank = {d['_idx']: i for i, d in enumerate(docs)}
    kw_scores = [_keyword_similarity(query, d.get('content', '')) for d in docs]
    kw_order = sorted(range(len(docs)), key=lambda i: kw_scores[i], reverse=True)
    kw_rank = {idx: rank for rank, idx in enumerate(kw_order)}

    fused = []
    for d in docs:
        i = d['_idx']
        fused.append({
            **d,
            # RRF + small keyword boost so lexical hits move up within ties
            'rerank_score': round(_rrf_score([vector_rank[i], kw_rank[i]]) + kw_scores[i] * 0.01, 4),
        })
    fused.sort(key=lambda d: d['rerank_score'], reverse=True)
    ranked = fused[:top_k]
    if llm_rerank:
        ranked = _llm_rerank(query, ranked)
    for d in ranked:
        d.pop('_idx', None)
    return ranked


_rag_instance = None
_rag_instance_lock = threading.Lock()


def get_rag_retriever() -> RAGRetriever:
    """获取全局 RAG 检索器单例

    使用 Django settings.BASE_DIR 下的 data/chroma_db 作为持久化目录，
    避免相对路径在不同 cwd 下指向不同位置。

    Thread-safe double-checked locking: 首次初始化会加载 fastembed 的
    ONNX embedding 模型 (数秒~数十秒) 且该加载持有 GIL, 若在 daphne 的
    请求/Beat 线程内同步触发会让整个 backend 假死 (agent 掉线, HTTP
    全挂)。此锁保证并发调用只加载一次; 启动期请配合
    ``warmup_rag_retriever()`` 把加载挪到有人连接之前。
    """
    global _rag_instance
    if _rag_instance is None:
        with _rag_instance_lock:
            if _rag_instance is None:
                persist_dir = './data/chroma_db'
                try:
                    import os as _os

                    from django.conf import settings
                    persist_dir = _os.path.join(str(settings.BASE_DIR), 'data', 'chroma_db')
                except Exception:
                    logger.debug('settings unavailable, RAG persist_dir falls back to ./data/chroma_db')
                _rag_instance = RAGRetriever(persist_dir=persist_dir)
    return _rag_instance


def warmup_rag_retriever() -> RAGRetriever | None:
    """启动期预热 RAG 检索器 (模型加载在后台完成, 结果缓存为单例).

    背景 (TD-396): fastembed 首次加载 ONNX 模型持有 GIL 数十秒,
    若首个请求或 Beat 的 auto_index_rag 第一个 tick 撞上, daphne 进程
    整体冻结 -> agent WebSocket 断开, HTTP 拒绝, 重连握手超时. 在
    backend 启动早期 (agent 尚未连接 / 无外部请求) 预热一次,
    之后任何调用都命中缓存, 不再冻结.

    失败不抛错 (返回 None, 下次调用懒加载重试) — 调用方应自行降级.
    """
    try:
        global _rag_instance
        with _rag_instance_lock:
            if _rag_instance is None:
                persist_dir = './data/chroma_db'
                try:
                    from django.conf import settings
                    persist_dir = os.path.join(str(settings.BASE_DIR), 'data', 'chroma_db')
                except Exception:
                    logger.debug('settings unavailable, RAG persist_dir falls back to ./data/chroma_db')
                _rag_instance = RAGRetriever(persist_dir=persist_dir)
        return _rag_instance
    except Exception:
        logger.warning("RAG warmup failed (will retry lazily)", exc_info=True)
        return None
