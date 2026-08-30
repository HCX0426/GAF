"""Device identity resolution — single source of truth (OQ-9 / F-10 spec).

Two writers previously maintained independent dedup keys:
  - HTTP ``DeviceRegisterView`` (5-step: hwnd > adb_serial > emulator_brand +
    empty serial > window_title > name+type);
  - agent ``device.sync`` -> ``protocol.services.register_agent_device``
    (adb_serial > window_handle > window_title > name prefix).

This module merges them into one lookup so the same physical device always
maps to the same backend ``Device``, no matter which writer sees it first.

OQ-9 decision (2026-08-30): agent WS sync is the Device lifecycle authority;
the HTTP register endpoint is a settings/correction channel. Shape here is
pure lookup — writers keep their own create/update policy.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db.models import Q

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


def normalize_device_type(raw: str) -> str:
    """Map agent/API-reported type strings to backend Device.DeviceType values."""
    from workers.models import Device

    value = (raw or "").lower()
    if value in ("windows", "window", "win32", "pc"):
        return Device.DeviceType.WINDOWS
    if value in ("emulator", "android", "adb", "emu"):
        return Device.DeviceType.EMULATOR
    return ""


def _agent_scope_q(agent) -> Q:
    """Scope queries to a Worker when known — physical identity (hwnd, serial)
    is unique independent of its current owner, so also match unassigned
    devices (agent IS NULL); ownership is set when the writer updates."""
    if agent is None:
        return Q()
    return Q(agent=agent) | Q(agent__isnull=True)


def find_device_by_identity(
    device_type,
    *,
    hwnd: str = "",
    adb_serial: str = "",
    emulator_brand: str = "",
    window_title: str = "",
    name: str = "",
    agent=None,
):
    """Resolve an existing Device by identity keys, or None.

    Priority (merged from HTTP 5-step + agent sync semantics):
      1. windows + window_handle/hwnd
      2. adb_serial
      3. emulator_brand + empty adb_serial (stale entry from config scan)
      4. windows + extra_info.window_title
      5. name + device_type (agent-scoped when ``agent`` is provided)

    Parameters mirror both writer payloads; empty values are skipped.
    """
    from workers.models import Device

    normalized_type = normalize_device_type(device_type)
    if not normalized_type:
        logger.warning("device_identity: unknown device_type %r — identity lookup skipped", device_type)
        return None

    # 1) Windows devices: window_handle is the most reliable key.
    if hwnd and normalized_type == Device.DeviceType.WINDOWS:
        device = Device.objects.filter(
            _agent_scope_q(agent),
            device_type=normalized_type,
            window_handle__iexact=str(hwnd),
        ).first()
        if device:
            return device

    # 2) Emulator devices: adb_serial is the most reliable key.
    if adb_serial:
        device = Device.objects.filter(
            _agent_scope_q(agent),
            device_type=normalized_type,
            adb_serial=adb_serial,
        ).first()
        if device:
            return device

    # 3) Emulator fuzzy: same brand + empty serial (stale entry from config scan).
    if emulator_brand and normalized_type == Device.DeviceType.EMULATOR:
        device = Device.objects.filter(
            _agent_scope_q(agent),
            device_type=normalized_type,
            emulator_brand=emulator_brand,
            adb_serial="",
        ).first()
        if device:
            return device

    # 4) Windows fallback: same window title = same window (stable across hwnd changes).
    if window_title and normalized_type == Device.DeviceType.WINDOWS:
        device = Device.objects.filter(
            _agent_scope_q(agent),
            device_type=normalized_type,
        ).filter(
            Q(extra_info__window_title=window_title)
            | Q(extra_info__window_title__iexact=window_title)
        ).first()
        if device:
            return device

    # 5) Last resort: name + type (agent-scoped to avoid cross-agent
    #    collisions). Also match name prefixes (e.g. "LDPlayer" matching
    #    "LDPlayer-5555") as the legacy agent sync fallback did.
    if name:
        name_q = Q(name__iexact=name)
        prefix = name.rsplit("-", 1)[0] if "-" in name else ""
        if prefix:
            name_q |= Q(name__startswith=f"{prefix}-")
        device = Device.objects.filter(
            _agent_scope_q(agent),
            device_type=normalized_type,
        ).filter(name_q).first()
        if device:
            return device

    return None
