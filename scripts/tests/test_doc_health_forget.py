"""Tests for spec-43 Phase 1: ForgetPolicy (forgetting mechanism).

Covers spec-43 §3.1.2 — 11 unit tests for the ForgetPolicy class:
- should_forget: 7 tests covering 5 priority rules + invalid timestamp + patch_failed
- forget_expired: 1 test on mixed entries splitting
- enforce_hard_cap: 3 tests (below / above threshold / only targets priority 5)

All tests use a fixed now_fn for deterministic time-based behavior.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

from governance.doc_health_forget import ForgetPolicy


# Fixed "now" for deterministic tests
FIXED_NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


def make_entry(
    severity: str = "P0",
    recurrence: int = 0,
    patch_failed: bool = False,
    age_days: int = 0,
) -> dict:
    """Build a consumed.json entry aged age_days from FIXED_NOW.

    consumed_at is computed as FIXED_NOW - age_days (in ISO 8601 with tz).
    """
    return {
        "severity": severity,
        "recurrence_count": recurrence,
        "patch_failed": patch_failed,
        "consumed_at": (FIXED_NOW - timedelta(days=age_days)).isoformat(),
    }


# ---- should_forget: 7 tests covering 5 priority rules + edge cases ----


def test_should_forget_p0_recurrence_0_after_90d():
    """Rule 3: P0 + recurrence=0 + age > 90d → True.

    consumed_at = now - 91d → age (91d) > 90d → forget.
    """
    policy = ForgetPolicy(now_fn=lambda: FIXED_NOW)
    entry = make_entry(severity="P0", recurrence=0, age_days=91)
    assert policy.should_forget(entry) is True


def test_should_forget_p0_recurrence_0_before_90d():
    """Rule 3 boundary: P0 + recurrence=0 + age < 90d → False.

    consumed_at = now - 89d → age (89d) <= 90d → keep.
    """
    policy = ForgetPolicy(now_fn=lambda: FIXED_NOW)
    entry = make_entry(severity="P0", recurrence=0, age_days=89)
    assert policy.should_forget(entry) is False


def test_should_never_forget_p0_recurrence_1():
    """Rule 2: P0 + recurrence>=1 → never forget, regardless of age.

    Even at 365d old, P0 systemic-issue entries stay for audit.
    """
    policy = ForgetPolicy(now_fn=lambda: FIXED_NOW)
    entry = make_entry(severity="P0", recurrence=1, age_days=365)
    assert policy.should_forget(entry) is False


def test_should_forget_p1_recurrence_0_after_30d():
    """Rule 5: P1 + recurrence=0 + age > 30d → True.

    consumed_at = now - 31d → age (31d) > 30d → forget.
    """
    policy = ForgetPolicy(now_fn=lambda: FIXED_NOW)
    entry = make_entry(severity="P1", recurrence=0, age_days=31)
    assert policy.should_forget(entry) is True


def test_should_forget_p1_recurrence_1_after_90d():
    """Rule 4: P1 + recurrence>=1 + age > 90d → True.

    consumed_at = now - 91d → age (91d) > 90d → forget.
    """
    policy = ForgetPolicy(now_fn=lambda: FIXED_NOW)
    entry = make_entry(severity="P1", recurrence=1, age_days=91)
    assert policy.should_forget(entry) is True


def test_should_never_forget_patch_failed():
    """Rule 1: patch_failed=true → never forget, regardless of age/severity.

    Failed patches must remain in consumed.json until TD resolution.
    """
    policy = ForgetPolicy(now_fn=lambda: FIXED_NOW)
    entry = make_entry(severity="P1", recurrence=0, patch_failed=True, age_days=365)
    assert policy.should_forget(entry) is False


def test_should_not_forget_invalid_timestamp():
    """Safety: invalid consumed_at → False (keep, do not risk losing data).

    Empty string / malformed timestamp → _parse_iso returns None → keep.
    """
    policy = ForgetPolicy(now_fn=lambda: FIXED_NOW)
    entry = {
        "severity": "P0",
        "recurrence_count": 0,
        "patch_failed": False,
        "consumed_at": "",
    }
    assert policy.should_forget(entry) is False


# ---- forget_expired: 1 test on mixed entries ----


def test_forget_expired_splits_correctly():
    """forget_expired correctly splits mixed entries into (kept, forgotten).

    Setup:
        - 1 P0+rec=0 age=91d → forgotten (rule 3)
        - 1 P0+rec=0 age=10d → kept (not yet 90d)
        - 1 P0+rec=1 age=365d → kept (rule 2: never forget)
        - 1 P1+rec=0 age=31d → forgotten (rule 5)
        - 1 P1+rec=0 age=10d → kept (not yet 30d)
        - 1 patch_failed=true → kept (rule 1: never forget)
    """
    policy = ForgetPolicy(now_fn=lambda: FIXED_NOW)
    consumed = {
        "p0_rec0_old": make_entry(severity="P0", recurrence=0, age_days=91),
        "p0_rec0_new": make_entry(severity="P0", recurrence=0, age_days=10),
        "p0_rec1_old": make_entry(severity="P0", recurrence=1, age_days=365),
        "p1_rec0_old": make_entry(severity="P1", recurrence=0, age_days=31),
        "p1_rec0_new": make_entry(severity="P1", recurrence=0, age_days=10),
        "patch_failed": make_entry(severity="P1", recurrence=0, patch_failed=True, age_days=365),
    }
    kept, forgotten = policy.forget_expired(consumed)

    # 2 expired (p0_rec0_old, p1_rec0_old), 4 kept
    assert len(forgotten) == 2
    assert len(kept) == 4
    assert set(forgotten.keys()) == {"p0_rec0_old", "p1_rec0_old"}
    assert set(kept.keys()) == {
        "p0_rec0_new", "p0_rec1_old", "p1_rec0_new", "patch_failed"
    }


# ---- enforce_hard_cap: 3 tests ----


def test_enforce_hard_cap_below_threshold():
    """Hard cap not triggered: len < 1000 → no change.

    Returns (consumed, {}) — all entries kept, none force-forgotten.
    """
    policy = ForgetPolicy(now_fn=lambda: FIXED_NOW)
    # 5 entries, well below 1000
    consumed = {
        f"id_{i:04d}": make_entry(severity="P1", recurrence=0, age_days=i)
        for i in range(5)
    }
    kept, forgotten = policy.enforce_hard_cap(consumed)

    assert forgotten == {}
    assert kept is consumed  # same object, no copy needed


def test_enforce_hard_cap_above_threshold():
    """Hard cap triggered: 1001 entries (all P1+rec=0) → 1000 kept + 1 forgotten.

    The oldest entry (by consumed_at) should be force-forgotten.
    """
    policy = ForgetPolicy(now_fn=lambda: FIXED_NOW)
    # 1001 P1+rec=0 entries, ages 0..1000 days
    consumed = {
        f"id_{i:04d}": make_entry(severity="P1", recurrence=0, age_days=i)
        for i in range(1001)
    }
    kept, forgotten = policy.enforce_hard_cap(consumed)

    assert len(kept) == 1000
    assert len(forgotten) == 1
    # Oldest entry (id_1000, age=1000d) should be force-forgotten
    assert "id_1000" in forgotten
    assert "id_1000" not in kept


def test_enforce_hard_cap_only_targets_priority_5():
    """Hard cap only force-forgets priority-5 (P1+rec=0); P0 and P1+rec>=1 untouched.

    Setup (len > 1000):
        - 1 P0 entry (any age) → must be kept (rule 2/3 audit)
        - 1 P1+rec=1 entry → must be kept (rule 4 audit)
        - 1000 P1+rec=0 entries → 999 kept + 1 forgotten (to reach 1000 total)
    Total before: 1 + 1 + 1000 = 1002 → need to forget 2 to reach 1000,
    but only P1+rec=0 are eligible → forget 2 oldest P1+rec=0.
    """
    policy = ForgetPolicy(now_fn=lambda: FIXED_NOW)
    consumed: dict[str, dict] = {}

    # 1 P0 entry (old, but never force-forgotten)
    consumed["p0_keep"] = make_entry(severity="P0", recurrence=0, age_days=365)
    # 1 P1+rec=1 entry (old, but rule 4 audit trail — never force-forgotten)
    consumed["p1_rec1_keep"] = make_entry(severity="P1", recurrence=1, age_days=365)
    # 1000 P1+rec=0 entries (eligible for force-forget)
    for i in range(1000):
        consumed[f"p1_rec0_{i:04d}"] = make_entry(
            severity="P1", recurrence=0, age_days=i
        )
    # Total = 1002, need to forget 2 to reach 1000

    kept, forgotten = policy.enforce_hard_cap(consumed)

    assert len(kept) == 1000
    assert len(forgotten) == 2

    # P0 and P1+rec=1 must be in kept (never force-forgotten)
    assert "p0_keep" in kept
    assert "p1_rec1_keep" in kept
    assert "p0_keep" not in forgotten
    assert "p1_rec1_keep" not in forgotten

    # Only P1+rec=0 entries should be in forgotten (the 2 oldest: i=999, i=998)
    forgotten_keys = set(forgotten.keys())
    assert forgotten_keys == {"p1_rec0_0999", "p1_rec0_0998"}
    for entry in forgotten.values():
        assert entry["severity"] == "P1"
        assert entry["recurrence_count"] == 0
        assert entry["patch_failed"] is False


# ---- Integration tests: ConsumedTracker.forget_expired (spec-43 Phase 2) ----


def _extract_mark_args(entry: dict) -> dict:
    """Extract mark_consumed kwargs from a make_entry-style dict.

    Filters out keys that mark_consumed doesn't accept (consumed_at,
    recurrence_count, patch_failed) and provides sensible defaults for
    required fields not in make_entry output. Kept as a utility for
    callers that want to combine make_entry with mark_consumed.
    """
    return {
        "dimension": entry.get("dimension", "d4_path_drift"),
        "severity": entry["severity"],
        "file": entry.get("file", ".ai-memory/lessons/x.md"),
        "line": entry.get("line", 8),
        "commit_hash": entry.get("commit_hash", "abc1234"),
        "action_taken": entry.get("action_taken", "patched"),
        "lesson_id": entry.get("lesson_id"),
    }


def _patch_forget_policy_now(monkeypatch, fixed_now: datetime) -> None:
    """Patch ForgetPolicy to use fixed_now as default now_fn.

    forget_expired() constructs ``ForgetPolicy()`` with no args, so we
    patch ``__init__`` to override the default now_fn for determinism.
    """
    import governance.doc_health_forget as forget_mod

    real_init = forget_mod.ForgetPolicy.__init__

    def patched_init(self, now_fn=None):
        real_init(self, now_fn or (lambda: fixed_now))

    monkeypatch.setattr(forget_mod.ForgetPolicy, "__init__", patched_init)


def test_forget_expired_integration_with_consumed_tracker(tmp_path, monkeypatch):
    """forget_expired() rewrites consumed.json with kept entries only.

    Setup:
        - expired001: P1 + recurrence=0 + 31d old → forgotten (rule 5)
        - fresh001:   P0 + recurrence=0 + 1d old  → kept (rule 3, age < 90d)

    Uses save() directly (not mark_consumed) because mark_consumed
    overwrites consumed_at with now(), which would make entries 0d old.
    ForgetPolicy's now is patched to FIXED_NOW for determinism.
    """
    from governance.doc_health_consumed import ConsumedTracker

    _patch_forget_policy_now(monkeypatch, FIXED_NOW)

    consumed_file = tmp_path / "doc_health_consumed.json"
    tracker = ConsumedTracker(consumed_file)

    tracker.save({
        "expired001": make_entry(severity="P1", recurrence=0, age_days=31),
        "fresh001": make_entry(severity="P0", recurrence=0, age_days=1),
    })

    forgotten, kept = tracker.forget_expired()
    assert forgotten == 1
    assert kept == 1

    # Verify consumed.json now only has the fresh entry
    reloaded = tracker.load()
    assert "fresh001" in reloaded
    assert "expired001" not in reloaded


def test_archive_file_created_on_forget(tmp_path, monkeypatch):
    """Forgotten entries are written to monthly archive file.

    After forget_expired(), archive file should exist in same directory
    as consumed.json, with filename doc_health_consumed_archive_YYYYMM.json.
    Archive should contain the forgotten entry under consumed_issues key.
    """
    from governance.doc_health_consumed import ConsumedTracker

    _patch_forget_policy_now(monkeypatch, FIXED_NOW)

    consumed_file = tmp_path / "doc_health_consumed.json"
    tracker = ConsumedTracker(consumed_file)

    tracker.save({
        "expired001": make_entry(severity="P1", recurrence=0, age_days=31),
    })

    forgotten, kept = tracker.forget_expired()
    assert forgotten == 1
    assert kept == 0

    # Archive filename uses real now's month (not FIXED_NOW) since _archive()
    # uses datetime.now() from doc_health_consumed module
    real_now = datetime.now().astimezone()
    archive_file = consumed_file.parent / (
        f"doc_health_consumed_archive_{real_now.strftime('%Y%m')}.json"
    )
    assert archive_file.exists(), f"Archive file should exist at {archive_file}"

    archive_data = json.loads(archive_file.read_text(encoding="utf-8"))
    assert "consumed_issues" in archive_data
    assert "expired001" in archive_data["consumed_issues"]


def test_archive_file_merges_with_existing(tmp_path, monkeypatch):
    """Multiple forget runs accumulate to same monthly archive.

    First forget archives expired001; second forget archives expired002.
    Archive file should contain both entries (merge, not overwrite).
    """
    from governance.doc_health_consumed import ConsumedTracker

    _patch_forget_policy_now(monkeypatch, FIXED_NOW)

    consumed_file = tmp_path / "doc_health_consumed.json"
    tracker = ConsumedTracker(consumed_file)

    # First forget run: archive expired001
    tracker.save({"expired001": make_entry(severity="P1", recurrence=0, age_days=31)})
    forgotten1, _ = tracker.forget_expired()
    assert forgotten1 == 1

    # Second forget run: archive expired002
    tracker.save({"expired002": make_entry(severity="P1", recurrence=0, age_days=31)})
    forgotten2, _ = tracker.forget_expired()
    assert forgotten2 == 1

    # Verify archive has both entries (merged, not overwritten)
    real_now = datetime.now().astimezone()
    archive_file = consumed_file.parent / (
        f"doc_health_consumed_archive_{real_now.strftime('%Y%m')}.json"
    )
    assert archive_file.exists()

    archive_data = json.loads(archive_file.read_text(encoding="utf-8"))
    assert "expired001" in archive_data["consumed_issues"]
    assert "expired002" in archive_data["consumed_issues"]


# ---- Closure tests (spec-43 Phase 3): hard cap + patch_failed + full lifecycle ----


def test_hard_cap_force_forget_in_integration(tmp_path, monkeypatch):
    """Hard cap (1000) force-forgets oldest P1+rec=0 entries in integration.

    Setup: 1001 fresh P1+rec=0 entries (age=0d, not expired by time rule).
    Time-based rule does NOT forget them (age 0d < 30d), but hard cap
    triggers force-forget of the oldest 1 entry to bring len to 1000.
    """
    from governance.doc_health_consumed import ConsumedTracker

    consumed_file = tmp_path / "doc_health_consumed.json"
    tracker = ConsumedTracker(consumed_file)

    # Patch ForgetPolicy to use FIXED_NOW so all entries have deterministic age
    _patch_forget_policy_now(monkeypatch, FIXED_NOW)

    # Create 1001 fresh P1+rec=0 entries (age=0d, not expired by time rule)
    entries = {}
    for i in range(1001):
        iid = f"issue_{i:04d}"
        entries[iid] = {
            "dimension": "d4_path_drift",
            "severity": "P1",
            "file": f"file_{i}.md",
            "line": None,
            "consumed_at": FIXED_NOW.isoformat(),  # 0d old, not expired
            "commit_hash": "abc1234",
            "action_taken": "test",
            "recurrence_count": 0,
            "patch_failed": False,
            "failure_reason": None,
        }
    tracker.save(entries)

    forgotten, kept = tracker.forget_expired()
    assert forgotten == 1
    assert kept == 1000


def test_forget_does_not_touch_patch_failed(tmp_path, monkeypatch):
    """patch_failed=true entries are never forgotten, even if very old.

    Setup:
        - patch_failed_old: P1 + rec=2 + patch_failed=true + 365d old → kept
        - p1_rec0_expired: P1 + rec=0 + patch_failed=false + 31d old → forgotten
    Only 1 entry should be forgotten (the P1+rec=0 expired one).
    """
    from governance.doc_health_consumed import ConsumedTracker

    consumed_file = tmp_path / "doc_health_consumed.json"
    tracker = ConsumedTracker(consumed_file)
    _patch_forget_policy_now(monkeypatch, FIXED_NOW)

    entries = {
        "patch_failed_old": {
            "dimension": "d4_path_drift", "severity": "P1", "file": "x.md", "line": None,
            "consumed_at": (FIXED_NOW - timedelta(days=365)).isoformat(),
            "commit_hash": "abc", "action_taken": "test",
            "recurrence_count": 2, "patch_failed": True, "failure_reason": "manual",
        },
        "p1_rec0_expired": {
            "dimension": "d4_path_drift", "severity": "P1", "file": "y.md", "line": None,
            "consumed_at": (FIXED_NOW - timedelta(days=31)).isoformat(),
            "commit_hash": "def", "action_taken": "test",
            "recurrence_count": 0, "patch_failed": False, "failure_reason": None,
        },
    }
    tracker.save(entries)

    forgotten, kept = tracker.forget_expired()
    assert forgotten == 1
    assert kept == 1
    consumed = tracker.load()
    assert "patch_failed_old" in consumed
    assert "p1_rec0_expired" not in consumed


def test_full_lifecycle(tmp_path, monkeypatch):
    """Full flywheel: patch -> consumed -> forget -> archive -> re-patch same issue.

    Verifies the full closed-loop:
        1. Create expired P1+rec=0 entry
        2. forget_expired() archives it
        3. consumed.json no longer has it
        4. Archive file contains it
        5. Re-patch same issue_id (new entry, fresh timestamp = FIXED_NOW)
        6. consumed.json has the new entry

    Note: Step 5 uses save() directly (not mark_consumed) because
    mark_consumed overwrites consumed_at with real datetime.now(), which
    would break determinism vs the patched ForgetPolicy now_fn.
    """
    from governance.doc_health_consumed import ConsumedTracker

    consumed_file = tmp_path / "doc_health_consumed.json"
    tracker = ConsumedTracker(consumed_file)
    _patch_forget_policy_now(monkeypatch, FIXED_NOW)

    # Step 1: Create expired P1+rec=0 entry
    entries = {
        "lifecycle_001": {
            "dimension": "d4_path_drift", "severity": "P1", "file": "x.md", "line": None,
            "consumed_at": (FIXED_NOW - timedelta(days=31)).isoformat(),
            "commit_hash": "abc", "action_taken": "first patch",
            "recurrence_count": 0, "patch_failed": False, "failure_reason": None,
        },
    }
    tracker.save(entries)

    # Step 2: Forget
    forgotten, kept = tracker.forget_expired()
    assert forgotten == 1
    assert kept == 0

    # Step 3: consumed.json no longer has it
    consumed = tracker.load()
    assert "lifecycle_001" not in consumed

    # Step 4: Archive file has it.
    # _archive() uses real datetime.now() for filename (not patched FIXED_NOW),
    # so we use real_now for the archive filename (matches Phase 2 test pattern).
    real_now = datetime.now().astimezone()
    archive_file = consumed_file.parent / (
        f"doc_health_consumed_archive_{real_now.strftime('%Y%m')}.json"
    )
    assert archive_file.exists(), f"Archive file should exist at {archive_file}"
    archive_data = json.loads(archive_file.read_text(encoding="utf-8"))
    assert "lifecycle_001" in archive_data["consumed_issues"]

    # Step 5: Re-patch same issue_id (new entry, fresh timestamp = FIXED_NOW).
    # Use save() directly (not mark_consumed) for determinism — see docstring.
    tracker.save({
        "lifecycle_001": {
            "dimension": "d4_path_drift", "severity": "P1", "file": "x.md", "line": None,
            "consumed_at": FIXED_NOW.isoformat(),  # fresh
            "commit_hash": "def", "action_taken": "second patch (recurrence)",
            "recurrence_count": 0, "patch_failed": False, "failure_reason": None,
        },
    })

    # Step 6: consumed.json now has new entry
    consumed = tracker.load()
    assert "lifecycle_001" in consumed
    assert consumed["lifecycle_001"]["action_taken"] == "second patch (recurrence)"
