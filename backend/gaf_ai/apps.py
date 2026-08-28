import logging
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class GafAiConfig(AppConfig):
    """AI app — LLM Router + RAG + LangGraph Agent.

    Renamed from ``ai`` to ``gaf_ai`` (TD-116) to eliminate the top-level
    package name collision with ``agent/src/ai/``. The ``db_table`` of each
    model is preserved with its original ``ai_*`` prefix so no DB schema
    migration is needed — only the ``app_label`` changes.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "gaf_ai"
    label = "gaf_ai"
    verbose_name = "GAF AI"

    def ready(self) -> None:
        """Startup-time background warmup of the RAG embedding model (TD-396).

        fastembed's first ONNX model load holds the GIL for tens of seconds.
        If a request or the first Beat ``auto_index_rag`` tick triggers it
        synchronously inside the daphne process, the whole event loop and
        every thread freeze (agent WebSocket drops, HTTP connections are
        refused). Loading it on a daemon thread right after startup — before
        the first tick (5 min) or any RAG-touching request — makes every
        later call hit the cached singleton. The shared lock in
        ``gaf_ai.rag.get_rag_retriever`` serializes an in-flight warmup with
        any early caller.
        """

        def _warmup() -> None:
            try:
                from gaf_ai.rag import warmup_rag_retriever
                warmup_rag_retriever()
                logger.info("RAG retriever warmed up (embedding model loaded)")
            except Exception:  # noqa: BLE001 — warmup must never break startup
                logger.warning("RAG warmup thread failed (will retry lazily)", exc_info=True)

        threading.Thread(target=_warmup, name="rag-warmup", daemon=True).start()
