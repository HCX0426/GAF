"""
Device post_save signal — unified device.updated broadcasting.

Replaces the scattered _broadcast_device_status_change calls and the
explicit group_send in DeviceViewSet.perform_update with a single
post_save receiver. Every Device.save() (except creation) that touches
a tracked field broadcasts device.updated to the dashboard WS group,
so the frontend's subscribeToDeviceUpdates() refetches automatically.

Design:
- post_save (not pre_save) — fires after the row is persisted
- transaction.on_commit — only broadcasts after the DB transaction commits
- update_fields check — skips saves that don't touch tracked fields
- Skips creation — device.registered handles new devices (DeviceRegisterView)

spec-29a #30: group name normalized from legacy "clients" to DASHBOARD_GROUP
(defined in protocol.constants). Payload wrapped in canonical "payload" key
so FrontendConsumer handlers can drop the `or event.get("data")` fallback.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from protocol.broadcast import broadcast_to_dashboard
from protocol.constants import FrontendEventType

from .models import Device

logger = logging.getLogger(__name__)

# Fields whose change should trigger a device.updated broadcast.
_TRACKED_FIELDS = frozenset({
    "name",
    "device_type",
    "status",
    "screenshot_method",
    "input_method",
    "resolution_width",
    "resolution_height",
    "window_handle",
    "extra_info",
    "screenshot_fps",
    "device_stats",
})


@receiver(post_save, sender=Device)
def broadcast_device_update(sender, instance, created, update_fields, **kwargs):
    """Broadcast device.updated to WS clients after every tracked Device save.

    This centralises the broadcast logic that was previously scattered across
    DeviceViewSet.perform_update, _broadcast_device_status_change, and various
    explicit group_send calls. The frontend subscribes to device.updated via
    useDeviceStore.subscribeToDeviceUpdates() and refetches the device list
    on any change.

    Skips:
    - Creation (created=True) — device.registered handles new devices
    - Saves where update_fields contains no tracked fields
    """
    if created:
        return

    # If update_fields is provided, only broadcast when a tracked field changed.
    if update_fields:
        changed = [f for f in update_fields if f in _TRACKED_FIELDS]
        if not changed:
            return
    else:
        # Full save (no update_fields) — assume all tracked fields might have changed.
        changed = list(_TRACKED_FIELDS)

    def _broadcast():
        """transaction.on_commit callback — fire-and-forget WS broadcast."""
        try:
            broadcast_to_dashboard(
                FrontendEventType.DEVICE_UPDATED,
                {
                    "device_id": instance.id,
                    "changed_fields": changed,
                    "timestamp": timezone.now().isoformat(),
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to broadcast device.updated for device %s: %s",
                instance.pk, e,
            )

    # Defer the broadcast until the transaction commits so we don't
    # notify clients about a save that gets rolled back.
    transaction.on_commit(_broadcast)


@receiver(post_save, sender=Device)
def _invalidate_agent_device_id_cache_on_save(sender, instance, **kwargs):
    """Clear the protocol consumer's agent_device_id -> Device.id cache.

    The cache (``protocol.consumers._AGENT_DEVICE_ID_CACHE``) is keyed by
    agent-side identifiers that map to Device rows. Any Device save can
    invalidate an existing mapping (rename, type change, window_handle
    change, extra_info update, etc.), so we clear the entire cache —
    Device saves are rare relative to the ~30 FPS screenshot frame rate
    that benefits from the cache (TD-259 #22).

    Lazy import avoids a top-level circular dependency: ``protocol.consumers``
    imports from ``agents.models``, and ``agents.signals`` is imported by
    ``agents.apps.AgentsConfig.ready()`` after Django is fully bootstrapped.
    """
    try:
        from protocol.consumers import clear_agent_device_id_cache

        clear_agent_device_id_cache()
    except Exception as e:
        logger.warning(
            "Failed to clear agent_device_id cache after Device save (pk=%s): %s",
            instance.pk, e,
        )


@receiver(post_delete, sender=Device)
def _invalidate_agent_device_id_cache_on_delete(sender, instance, **kwargs):
    """Clear the agent_device_id -> Device.id cache on Device deletion.

    A deleted Device means any cached mapping to its id is now stale; clear
    the whole cache (same rationale as the post_save handler). Registered as
    a separate receiver because ``post_save`` does not fire on delete.
    """
    try:
        from protocol.consumers import clear_agent_device_id_cache

        clear_agent_device_id_cache()
    except Exception as e:
        logger.warning(
            "Failed to clear agent_device_id cache after Device delete (pk=%s): %s",
            instance.pk, e,
        )


# ─────────────────────────────────────────────
# P-048: Device crash recovery signal
# ─────────────────────────────────────────────


@receiver(pre_save, sender=Device)
def _capture_device_old_status(sender, instance, **kwargs):
    """Capture the old Device.status before save (for crash recovery comparison)."""
    if instance.pk is not None:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._old_status = old.status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Device)
def trigger_device_crash_recovery(sender, instance, created, update_fields, **kwargs):
    """Device ONLINE → ERROR triggers handle_device_crash.

    P-048: Device status 从非 ERROR 变为 ERROR 时, 通过 transaction.on_commit
    调用 scheduler.recovery_engine.handle_device_crash, 触发设备级恢复链。

    Skip 条件:
    - created=True (新建设备由 register 流程处理)
    - update_fields 不含 'status'
    - 新旧 status 都是 ERROR (recovery storm 防护)
    - 新 status 不是 ERROR
    """
    if created:
        return

    if update_fields is not None and 'status' not in update_fields:
        return

    old_status = getattr(instance, '_old_status', None)
    if instance.status == Device.Status.ERROR and old_status != Device.Status.ERROR:
        def _call_handle():
            try:
                from scheduler.recovery_engine import handle_device_crash
                handle_device_crash(device_id=instance.id)
            except Exception as exc:
                logger.warning(
                    "Device crash recovery failed for device %s: %s",
                    instance.pk, exc,
                )
        transaction.on_commit(_call_handle)
