from django.apps import AppConfig


class GafCoreConfig(AppConfig):
    """Core shared utilities for the GAF Django backend.

    Renamed from ``core`` to ``gaf_core`` (TD-116) to eliminate the
    top-level package name collision with ``agent/src/core/``. The
    ``db_table`` of ``LogEntry`` is preserved as ``core_log_entry`` so no
    DB schema migration is needed — only the ``app_label`` changes.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "gaf_core"
    label = "gaf_core"
    verbose_name = "GAF Core"

    def ready(self) -> None:
        """Register signal handlers for performance monitoring.

        Installed on app startup:
        - Database query timing (via cursor wrapper patching)
        - Celery task timing (via task_prerun / task_postrun signals)
        """
        from .signals import install_celery_task_timing, install_db_query_timing

        install_db_query_timing()
        install_celery_task_timing()
