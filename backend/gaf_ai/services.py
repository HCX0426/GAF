"""AI Lab domain services — decouple gaf_ai app from pipeline/tasks models.

Extracted from gaf_ai/views.py + views_anomaly.py (spec-59-E / TD-297) to
remove top-level ``from pipeline.models import Pipeline`` and
``from tasks.models import TaskExecution`` cross-app imports. Views call
these services instead.

Pattern follows agents/services.py (spec-41 / TD-277): service layer
encapsulates cross-app model queries, views depend on services not models.
"""
from __future__ import annotations

from typing import Any

from pipeline.models import Pipeline

from tasks.models import TaskExecution


def get_pipeline_for_user(pipeline_id: int, user) -> Pipeline | None:
    """Get a Pipeline by id owned by user, or None if not found.

    Args:
        pipeline_id: Pipeline.pk
        user: Django User instance; pipeline must be owned by this user.

    Returns:
        Pipeline instance or None (caller handles 404 response).
    """
    try:
        return Pipeline.objects.get(id=pipeline_id, user=user)
    except Pipeline.DoesNotExist:
        return None


def get_user_execution_history(user, limit: int = 20) -> list[dict[str, Any]]:
    """Return recent execution stats dicts for a user (newest first).

    Used by AI optimize_pipeline to build LLM context. Only the fields
    needed by the prompt are returned (status/duration/error_message),
    avoiding exposing the full TaskExecution model to the view.

    Args:
        user: Django User instance; only executions triggered by this user.
        limit: Max number of recent executions (default 20).

    Returns:
        List of dicts with keys: status, duration (str), error_message.
    """
    executions = TaskExecution.objects.filter(triggered_by=user).order_by('-started_at')[:limit]
    return [
        {
            'status': ex.status,
            'duration': str(ex.completed_at - ex.started_at) if ex.completed_at and ex.started_at else '',
            'error_message': ex.error_message or '',
        }
        for ex in executions
    ]


def get_user_failed_executions_qs(user, cutoff, limit: int = 100):
    """Return failed executions queryset for a user since cutoff.

    Returns a sliced queryset (not a list) so the caller can use
    .exists() / .count() / iterate as needed without re-querying.

    Args:
        user: Django User instance; only executions triggered by this user.
        cutoff: datetime; only executions with started_at >= cutoff.
        limit: Max number of failed executions (default 100).

    Returns:
        Sliced QuerySet of TaskExecution (status='failed', newest first).
    """
    return TaskExecution.objects.filter(
        status='failed',
        started_at__gte=cutoff,
        triggered_by=user,
    ).order_by('-started_at')[:limit]


def count_user_executions_since(user, cutoff) -> int:
    """Count user's executions started since cutoff.

    Args:
        user: Django User instance; only executions triggered by this user.
        cutoff: datetime; only executions with started_at >= cutoff.

    Returns:
        Integer count of matching executions.
    """
    return TaskExecution.objects.filter(
        started_at__gte=cutoff,
        triggered_by=user,
    ).count()
