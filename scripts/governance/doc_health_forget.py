"""doc_health_forget.py - Spec-43: forgetting policy for consumed issues.

Determines when consumed entries can be forgotten (removed from live
consumed.json) based on importance × recurrence × time.

Policy (spec-43 §2.2):
    1. patch_failed=true → never forget (need TD resolution)
    2. P0 + recurrence>=1 → never forget (systemic audit trail)
    3. P0 + recurrence=0 → forget after 90 days
    4. P1 + recurrence>=1 → forget after 90 days
    5. P1 + recurrence=0 → forget after 30 days

Hard cap (spec-43 §2.2): if len(consumed) > 1000, force-forget oldest
priority-5 entries (P1 + recurrence=0) until len <= 1000.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable


# Retention periods (days) per (severity, recurrence_bucket) combination.
# recurrence_bucket: 0 = no recurrence, 1 = any recurrence (>=1).
# None means "never forget" (systemic issue audit trail).
_RETENTION_DAYS: dict[tuple[str, int], int | None] = {
    ("P0", 0): 90,    # P0 + recurrence=0 → forget after 90d
    ("P0", 1): None,  # P0 + recurrence>=1 → never forget
    ("P1", 0): 30,    # P1 + recurrence=0 → forget after 30d
    ("P1", 1): 90,    # P1 + recurrence>=1 → forget after 90d
}

# Hard cap: if len(consumed) > this, force-forget oldest P1+recurrence=0 entries.
_HARD_CAP = 1000


class ForgetPolicy:
    """Single source of truth for forgetting consumed entries.

    Policy (spec-43 §2.2):
        1. patch_failed=true → never forget
        2. P0 + recurrence>=1 → never forget
        3. P0 + recurrence=0 → forget after 90 days
        4. P1 + recurrence>=1 → forget after 90 days
        5. P1 + recurrence=0 → forget after 30 days

    Hard cap: force-forget oldest priority-5 entries if len > 1000.
    """

    def __init__(self, now_fn: Callable[[], datetime] | None = None):
        # now_fn injection for deterministic tests; default = tz-aware now.
        self._now_fn = now_fn or (lambda: datetime.now().astimezone())

    def should_forget(self, entry: dict) -> bool:
        """Return True if entry should be forgotten per policy.

        Args:
            entry: consumed.json entry dict with keys:
                severity, recurrence_count, patch_failed, consumed_at.

        Returns:
            True if entry is expired and should be archived.
        """
        # Rule 1: patch_failed → never forget (need TD resolution)
        if entry.get("patch_failed", False):
            return False

        severity = entry.get("severity", "P1")
        recurrence = entry.get("recurrence_count", 0)
        # Bucket: 0 = no recurrence, 1 = any recurrence (>=1)
        rec_bucket = 1 if recurrence >= 1 else 0

        # Rule 2: P0 + recurrence>=1 → never forget (retention is None)
        retention = _RETENTION_DAYS.get((severity, rec_bucket))
        if retention is None:
            return False  # never forget

        # Rules 3-5: time-based forgetting
        consumed_at = self._parse_iso(entry.get("consumed_at", ""))
        if consumed_at is None:
            return False  # invalid timestamp → keep (safer)

        now = self._now_fn()
        age = now - consumed_at
        return age > timedelta(days=retention)

    def forget_expired(
        self, consumed: dict[str, dict]
    ) -> tuple[dict[str, dict], dict[str, dict]]:
        """Split consumed into (kept, forgotten) per policy.

        Args:
            consumed: full consumed_issues dict (issue_id -> entry).

        Returns:
            Tuple of (kept_dict, forgotten_dict). Both preserve issue_id keys.
        """
        kept: dict[str, dict] = {}
        forgotten: dict[str, dict] = {}
        for iid, entry in consumed.items():
            if self.should_forget(entry):
                forgotten[iid] = entry
            else:
                kept[iid] = entry
        return kept, forgotten

    def enforce_hard_cap(
        self, consumed: dict[str, dict]
    ) -> tuple[dict[str, dict], dict[str, dict]]:
        """Force-forget oldest P1+recurrence=0 entries if over hard cap.

        Called after forget_expired() to handle extreme cases. Only
        force-forgets priority-5 entries (P1 + recurrence=0 + patch_failed=false);
        if still over cap, leaves remaining entries alone (safer than forgetting
        P0 or recurrence>=1 entries).

        Args:
            consumed: kept dict from forget_expired().

        Returns:
            Tuple of (final_kept, force_forgotten).
        """
        if len(consumed) <= _HARD_CAP:
            return consumed, {}

        # Find priority-5 candidates (P1 + recurrence=0 + patch_failed=false)
        candidates = [
            (iid, entry)
            for iid, entry in consumed.items()
            if entry.get("severity") == "P1"
            and entry.get("recurrence_count", 0) == 0
            and not entry.get("patch_failed", False)
        ]
        # Sort by consumed_at ascending (oldest first). Entries with
        # unparseable timestamps sort as oldest (treated as epoch start)
        # so they are forgotten first — safer than keeping ambiguous data.
        candidates.sort(key=lambda kv: self._sort_key(kv[1]))

        to_forget_count = len(consumed) - _HARD_CAP
        to_forget_ids = {iid for iid, _ in candidates[:to_forget_count]}

        kept = {iid: e for iid, e in consumed.items() if iid not in to_forget_ids}
        forgotten = {iid: e for iid, e in consumed.items() if iid in to_forget_ids}
        return kept, forgotten

    @staticmethod
    def _sort_key(entry: dict) -> datetime:
        """Sort key for hard-cap candidates: consumed_at or epoch start.

        Returns datetime.min (UTC) for entries with unparseable timestamps
        so they sort oldest and are forgotten first (safer to drop ambiguous
        data than keep it when over the hard cap).
        """
        ts = ForgetPolicy._parse_iso(entry.get("consumed_at", ""))
        if ts is None:
            # tz-aware epoch start (compatible with parsed tz-aware datetimes)
            return datetime.min.replace(tzinfo=timezone.utc)
        return ts

    @staticmethod
    def _parse_iso(ts: str) -> datetime | None:
        """Parse ISO 8601 timestamp; return None on failure."""
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return None
