"""Online Worker resolution — shared by all execution entry points.

B1 (2026-08-27): TaskService.execute_task / PipelineViewSet._get_online_agent
/ run_pipeline duplicated the "explicit agent_id wins, else auto-pick latest
heartbeat online worker" logic. Centralizing it here keeps the three dispatch
paths behaviorally consistent (previously pipeline/CLI picked by DB order,
TaskService picked by last_heartbeat).
"""

from __future__ import annotations

from workers.models import Worker


def resolve_online_worker(agent_id=None):
    """Resolve an online Worker for dispatch.

    Priority:
        1. ``agent_id`` provided → return that Worker if it exists and its
           status is ONLINE / IDLE (busy workers wait for the current
           execution rather than being handed a second one).
        2. Otherwise → the latest-heartbeat ONLINE / IDLE Worker.

    Returns:
        Worker instance or None when unavailable (missing / offline /
        no online worker).
    """
    online_statuses = (Worker.Status.ONLINE, Worker.Status.IDLE)

    if agent_id:
        try:
            worker = Worker.objects.get(agent_id=agent_id)
        except Worker.DoesNotExist:
            return None
        if worker.status in online_statuses:
            return worker
        return None

    return (
        Worker.objects.filter(status__in=online_statuses)
        .order_by("-last_heartbeat")
        .first()
    )
