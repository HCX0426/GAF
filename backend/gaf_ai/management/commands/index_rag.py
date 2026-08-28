"""Management command to build/update the RAG index for code files."""

from django.conf import settings
from django.core.management.base import BaseCommand

from gaf_ai.rag import CHROMADB_AVAILABLE, get_rag_retriever


class Command(BaseCommand):
    help = "Build or update the RAG index by scanning project code files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-dir",
            type=str,
            default=None,
            help="Base directory to scan (defaults to settings.BASE_DIR).",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset the collection before indexing (delete all existing docs).",
        )

    def handle(self, *args, **options):
        if not CHROMADB_AVAILABLE:
            self.stdout.write(
                self.style.WARNING(
                    "chromadb is not installed. RAG will use fallback keyword search. "
                    "Install with: pip install chromadb"
                )
            )
            return

        base_dir = options.get("base_dir") or str(settings.BASE_DIR)
        self.stdout.write(f"Scanning: {base_dir}")

        retriever = get_rag_retriever()

        if options.get("reset"):
            self.stdout.write("Resetting collection...")
            try:
                retriever._client.delete_collection(retriever.collection_name)
                retriever._init_chroma()
                self.stdout.write(self.style.SUCCESS("Collection reset."))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Reset failed: {e}"))

        count = retriever.index_code_files(base_dir)
        self.stdout.write(
            self.style.SUCCESS(f"Indexed {count} files from {base_dir}")
        )
