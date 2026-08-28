"""Settings feature flag helpers.

Centralizes FeatureFlag lookups for runtime-tunable behavior so callers
do not hard-code flag names or default semantics. Each helper:

- Returns a sensible default when the flag row is missing from the DB
  (fail-open or fail-closed as documented) so a fresh install without
  the seed migration still works.
- Never raises — a corrupted DB row should not crash the request path.

Companion to ``gaf_ai/feature_flags.py`` (which covers AI feature flags).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Canonical flag name for the multi-game parallel mode toggle (Spec A).
# When enabled, Device input/screenshot methods are restricted to the
# parallel-safe whitelist (PostMessage/SendMessage + adb_input for input;
# PrintWindow/BitBlt/WGC + screencap for screenshot). See
# docs/specs/archived/ (multi-game-mode-switch spec, archived).
MULTI_GAME_MODE_FLAG = 'unattended_multi_game_mode'


def is_multi_game_mode_enabled() -> bool:
    """Return whether multi-game parallel mode is enabled.

    Defaults to ``False`` when the FeatureFlag row is missing (fail-closed)
    so a fresh install preserves the legacy single-session behavior without
    restriction. Callers (resolve_device_methods, unattended_start_view,
    DeviceSerializer) rely on this default to keep existing deployments
    unchanged until an admin explicitly opts in.
    """
    from settings.models import FeatureFlag

    flag = FeatureFlag.objects.filter(name=MULTI_GAME_MODE_FLAG).first()
    if flag is None:
        return False
    return bool(flag.enabled)
