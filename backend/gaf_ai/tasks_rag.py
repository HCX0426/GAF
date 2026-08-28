"""Celery tasks for RAG index maintenance (P2-1).

Separated from ``ai/tasks.py`` (agent analysis tasks) to keep concerns
clean: this module hosts the periodic RAG auto-indexer that scans the
agent/ and backend/gaf_ai source trees and re-indexes them into ChromaDB.

The task is registered in Celery beat (``config/celery.py``) with a
5-minute schedule. Re-indexing the same content with the same doc_id is
a no-op in ChromaDB, so the task is idempotent.
"""
import logging
import time

from celery import shared_task
from django.conf import settings

from gaf_ai.rag import get_rag_retriever

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60, acks_late=True)
def auto_index_rag(self):
    """Periodically index code files into RAG.

    Runs every 5 minutes via Celery beat. Indexes the agent/ and backend/
    source dirs. Idempotent — re-indexing same content with same doc_id
    is a no-op in ChromaDB.

    Returns:
        Dict with ``agent_chunks`` and ``backend_chunks`` counts.
    """
    start = time.monotonic()
    try:
        retriever = get_rag_retriever()
        # settings.BASE_DIR is backend/ — agent/ and the repo root are one
        # level up. Use .parent so the paths resolve correctly on Windows
        # and POSIX alike (os.walk handles the rest).
        repo_root = settings.BASE_DIR.parent
        # Index agent source (the primary codebase for RAG)
        agent_dir = repo_root / 'agent' / 'src'
        # TD-116 (2026-07-15): app renamed backend/ai → backend/gaf_ai.
        # The old path silently indexed nothing — verify existence and
        # warn loudly instead of reporting 0 chunks.
        backend_ai_dir = repo_root / 'backend' / 'gaf_ai'
        if not backend_ai_dir.is_dir():
            logger.warning(
                'auto_index_rag: backend AI dir missing (expected %s) — '
                'indexing only agent source', backend_ai_dir,
            )
        count_agent = retriever.index_code_files(str(agent_dir))
        count_backend = 0
        if backend_ai_dir.is_dir():
            count_backend = retriever.index_code_files(str(backend_ai_dir))
        # TD-396: track per-tick duration so a spike in changed chunks
        # (which re-runs embedding — GIL-holding) is visible in logs.
        logger.info(
            'auto_index_rag: indexed %d agent + %d backend chunks (%.2fs)',
            count_agent, count_backend, time.monotonic() - start,
        )
        return {'agent_chunks': count_agent, 'backend_chunks': count_backend}
    except Exception as exc:
        logger.exception('auto_index_rag failed: %s', exc)
        raise self.retry(exc=exc, countdown=60) from None
