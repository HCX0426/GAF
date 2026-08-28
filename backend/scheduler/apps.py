from django.apps import AppConfig


class SchedulerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'scheduler'

    def ready(self):
        # P-009 Phase 3: register TaskChainExecution post_save signal
        # to trigger the unattended completion hook.
        from . import signals  # noqa: F401
