# scheduler/services package — Service layer for scheduler business logic.
#
# Phase 1 (2026-08-08): Extract business logic from views.py into
# domain-specific service classes. Views become thin delegates that
# handle HTTP concerns (request/response) while services handle
# business rules and cross-model coordination.

from scheduler.services.scheduler_service import SchedulerService

__all__ = [
    "SchedulerService",
]
