#!/usr/bin/env python
"""rag_eval.py — Phase 3 RAG offline evaluation (Hit Rate / MRR).

Runs retrieval over the real ChromaDB index using the knowledge entries
(``QASession.is_knowledge_entry=True``) as the ground-truth question/answer
set, then reports:

- **Hit Rate @k** (k=1/3/5): fraction of queries whose top-k retrieved docs
  contain a document relevant to the expected answer.
- **MRR** (Mean Reciprocal Rank): average of 1/rank-of-first-hit.

Relevance is judged lexically (difflib ratio between the expected answer and
the retrieved doc content) — no LLM calls, so it runs offline and cheaply.
``search_reranked`` (hybrid vector + keyword RRF fusion) is the path under test.

Usage::

    python scripts/ai/rag_eval.py                # dev DB, default settings
    python scripts/ai/rag_eval.py --top-k 5 --limit 50 --similarity 0.3
    python scripts/ai/rag_eval.py --settings config.settings.test
"""
from __future__ import annotations

import argparse
import difflib
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND_DIR = os.path.join(REPO_ROOT, 'backend')
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


def _setup_django(settings_module: str) -> None:
    import django

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', settings_module)
    django.setup()


def _relevant(answer: str | None, doc_content: str | None, threshold: float) -> bool:
    """Lexical relevance: answer vs doc content.

    Two signals (either is enough):
    1. Any answer token of length >= 4 appears verbatim in the doc content
       (robust against short-string character-overlap false positives).
    2. difflib ratio between answer and doc >= ``threshold``.
    """
    ans = (answer or '').lower().strip()
    content = (doc_content or '').lower()[:300]
    if not ans or not content:
        return False
    tokens = {t for t in ans.split() if len(t) >= 4}
    if tokens and any(t in content for t in tokens):
        return True
    # Character-level similarity, but require a meaningful overlap (>= 0.5)
    # to avoid short-string false positives (e.g. shared vowels inflating
    # the ratio past a loose CLI threshold like 0.3).
    ratio = difflib.SequenceMatcher(None, ans, content).ratio()
    return ratio >= max(threshold, 0.5)


def evaluate(top_k: int, limit: int, similarity: float) -> dict:
    """Return {n, hit_rate_k, mrr, hits:{k:count}} over knowledge QASessions."""
    from gaf_ai.models import QASession
    from gaf_ai.rag import get_rag_retriever

    retriever = get_rag_retriever()
    qas = list(
        QASession.objects.filter(is_knowledge_entry=True)
        .order_by('-created_at')[:limit]
    )
    n = 0
    hits = {k: 0 for k in (1, 3, 5) if k <= top_k}
    rr_sum = 0.0
    for qa in qas:
        query = (qa.question or '').strip()
        if not query:
            continue
        docs = retriever.search_reranked(query, top_k=top_k, pool_size=top_k * 2)
        first_hit = None
        for i, d in enumerate(docs):
            if _relevant(qa.answer, d.get('content', ''), similarity):
                first_hit = i
                break
        if first_hit is not None:
            for k in hits:
                if first_hit < k:
                    hits[k] += 1
            rr_sum += 1.0 / (first_hit + 1)
        n += 1

    return {
        'n': n,
        'hits': hits,
        'hit_rate_k': {k: (hits[k] / n if n else 0.0) for k in hits},
        'mrr': (rr_sum / n if n else 0.0),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--top-k', type=int, default=5, help='retrieval depth (default 5)')
    parser.add_argument('--limit', type=int, default=50, help='max QASession ground-truth queries (default 50)')
    parser.add_argument('--similarity', type=float, default=0.3, help='difflib relevance threshold (default 0.3)')
    parser.add_argument('--settings', default='config.settings.dev', help='Django settings module')
    args = parser.parse_args(argv)

    _setup_django(args.settings)
    report = evaluate(args.top_k, args.limit, args.similarity)

    print('=== RAG Evaluation Report (Hit Rate / MRR) ===')
    if report['n'] == 0:
        print('No knowledge QASessions found — index some Q&A first '
              '(mark a session as knowledge entry) or re-run with more data.')
        return 0
    print(f'Queries evaluated : {report["n"]}')
    for k in report['hit_rate_k']:
        print(f'Hit Rate @{k}      : {report["hit_rate_k"][k]:.3f} ({report["hits"][k]}/{report["n"]})')
    print(f'MRR               : {report["mrr"]:.3f}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
