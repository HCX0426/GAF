# workers/services package — Service layer for worker & device business logic.
#
# Phase 1 (2026-08-08): Extract device health-check, status management,
# and screenshot method detection from flat views.py into domain-specific
# service classes. Views become thin delegates that handle HTTP concerns
# (request/response) while services handle business rules.
#
# The original agents/services.py was renamed to workers/worker_service.py to
# avoid shadowing the services/ package directory. All exports are re-exported
# here for backward compatibility.

# Device service
# Worker token services (from the original agents/services.py → worker_service.py)
from workers.worker_service import (
    create_worker_token,
    get_worker_for_device_check,
    is_worker_offline,
    list_worker_tokens,
    revoke_worker_token,
)
from workers.services.device_service import (
    DeviceService,
    _get_emulator_native_resolution,
    _get_or_cache_available_methods,
    _invalidate_available_methods_cache,
    _refresh_window_handle,
    _scale_to_native,
)

__all__ = [
    # DeviceService
    "DeviceService",
    "_get_or_cache_available_methods",
    "_invalidate_available_methods_cache",
    "_get_emulator_native_resolution",
    "_scale_to_native",
    "_refresh_window_handle",
    # Worker token services
    "create_worker_token",
    "list_worker_tokens",
    "revoke_worker_token",
    "get_worker_for_device_check",
    "is_worker_offline",
]
