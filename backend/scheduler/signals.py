"""Scheduler signals for unattended mode (P-009 Phase 3).

Listens to ``TaskChainExecution`` status changes and notifies the
scheduler when a chain execution reaches a terminal state
(SUCCESS / FAILED / CANCELLED). The scheduler then:

1. Removes the completed chain from ``session.active_chain_executions``
2. Updates ``session.failed_count`` (increment on FAILED, reset on SUCCESS)
3. Checks ``AutoStopCondition`` and stops the session if triggered
4. Calls the recovery engine for FAILED chains

Design (mirrors ``tasks/signals.py``):
- Synchronous signal handler does minimal work — just enqueues a Celery task
- ``transaction.on_commit`` ensures we never fire the task for a save that
  gets rolled back
- Anti-recursion: the Celery task updates ``UnattendedSession`` (not
  ``TaskChainExecution``), so this signal is not re-triggered
"""

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from pipeline.models import TaskChainExecution

logger = logging.getLogger(__name__)

# Terminal states that should trigger the completion hook.
_TERMINAL_STATUSES = (
    TaskChainExecution.Status.SUCCESS,
    TaskChainExecution.Status.FAILED,
    TaskChainExecution.Status.CANCELLED,
)


@receiver(post_save, sender=TaskChainExecution)
def on_chain_execution_status_change(
    sender, instance, created, update_fields, **kwargs,
):
    """Notify scheduler when a TaskChainExecution reaches terminal state.

    Fires only on updates (not creates) where ``status`` is in the
    terminal set. Defers the heavy work to the
    ``on_chain_execution_completed`` Celery task via
    ``transaction.on_commit``.
    """
    if created:
        return

    # If update_fields is provided, only proceed when 'status' is in it.
    # When update_fields is None (full save), we still check the status.
    if update_fields is not None and 'status' not in update_fields:
        return

    if instance.status not in _TERMINAL_STATUSES:
        return

    chain_execution_id = instance.id
    logger.info(
        'TaskChainExecution %s reached terminal state %s — '
        'scheduling completion hook',
        chain_execution_id, instance.status,
    )

    def _dispatch_completion_hook():
        """on_commit callback: enqueue the Celery completion task."""
        try:
            from scheduler.tasks import on_chain_execution_completed
            on_chain_execution_completed.delay(chain_execution_id)
        except Exception:
            logger.exception(
                'Failed to enqueue on_chain_execution_completed for '
                'TaskChainExecution %s',
                chain_execution_id,
            )

    transaction.on_commit(_dispatch_completion_hook)
