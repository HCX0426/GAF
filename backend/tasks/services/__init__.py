# tasks/services package — Service layer for task business logic.
#
# Phase 1 (2026-08-08): Split from flat services.py into domain modules.
# Backward-compatible re-exports so existing imports still work.

from tasks.services.binding_service import (
    bind_task_accounts,
    clone_pipeline_for_user,
    get_user_pipeline,
)
from tasks.services.exceptions import TaskBindingError
from tasks.services.monitor_service import (
    TaskMonitorService,
    _release_concurrency_slot,
    _restore_device_status,
    _restore_device_status_by_msg,
)
from tasks.services.task_service import TaskService, _get_or_create_default_account, execute_task

__all__ = [
    "TaskBindingError",
    "TaskMonitorService",
    "TaskService",
    "execute_task",
    "bind_task_accounts",
    "clone_pipeline_for_user",
    "get_user_pipeline",
    "_release_concurrency_slot",
    "_restore_device_status",
    "_restore_device_status_by_msg",
    "_get_or_create_default_account",
]
