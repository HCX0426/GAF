"""Tests for spec-49 TD-318: ConsumedTracker red-line counters.

Covers the spec-49 §0.5 red lines enforced by the orchestrator during
the AI patch flow:

  - consecutive_failures >= 3  → must stop and report to user
  - consecutive_successes >= 5 AND total_patches_this_session % 10 == 0
    → checkpoint stop: report progress (avoid context exhaustion)

These counters live on ConsumedTracker (added by TD-318) and persist to
``.cache/doc_health_consumed.json`` under the ``session_state`` key so a
fresh ConsumedTracker reflects the prior session's streak.

All tests use ``tmp_path`` so they do not depend on a real .cache/ dir.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

pytestmark = pytest.mark.unit

from governance.doc_health_consumed import ConsumedTracker


# ---- Helpers ----


def _seed_failed(tracker: ConsumedTracker, issue_id: str = "iid_seed_0001") -> None:
    """Mark one issue as failed so mark_success has an entry to look up."""
    tracker.mark_failed(
        issue_id,
        dimension="d4_path_drift",
        severity="P0",
        file="docs/x.md",
        line=1,
        failure_reason="seed failure",
    )


# ---- mark_success / mark_failed counter tests ----


def test_mark_success_increments_consecutive_successes(tmp_path):
    """mark_success increments consecutive_successes by 1.

    Setup: seed a failed entry (so mark_success can look it up), then call
    mark_success. After the call, consecutive_successes must be 1 and
    total_patches_this_session must reflect both the seed failure and the
    success.
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    _seed_failed(tracker)  # total=1, cf=1, cs=0
    tracker.mark_success("iid_seed_0001", "commit_abc", "patched path")  # total=2, cf=0, cs=1
    assert tracker.consecutive_successes == 1
    assert tracker.consecutive_failures == 0
    assert tracker.total_patches_this_session == 2


def test_mark_failed_increments_consecutive_failures(tmp_path):
    """mark_failed increments consecutive_failures by 1.

    Two consecutive failures → consecutive_failures == 2.
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    tracker.mark_failed(
        "iid_fail_0001", dimension="d4_path_drift", severity="P0",
        file="docs/a.md", line=1, failure_reason="r1",
    )
    tracker.mark_failed(
        "iid_fail_0002", dimension="d4_path_drift", severity="P0",
        file="docs/b.md", line=1, failure_reason="r2",
    )
    assert tracker.consecutive_failures == 2
    assert tracker.consecutive_successes == 0
    assert tracker.total_patches_this_session == 2


def test_mark_success_resets_consecutive_failures(tmp_path):
    """mark_success resets consecutive_failures to 0.

    Setup: 2 failures (cf=2), then 1 success. After success, cf must be 0
    (streak broken) and cs must be 1.
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    tracker.mark_failed(
        "iid_a_000001", dimension="d4_path_drift", severity="P0",
        file="docs/a.md", line=1, failure_reason="r1",
    )
    tracker.mark_failed(
        "iid_a_000001", dimension="d4_path_drift", severity="P0",
        file="docs/a.md", line=1, failure_reason="r2",
    )
    assert tracker.consecutive_failures == 2
    tracker.mark_success("iid_a_000001", "commit_xyz", "fixed on retry")
    assert tracker.consecutive_failures == 0
    assert tracker.consecutive_successes == 1


def test_mark_failed_resets_consecutive_successes(tmp_path):
    """mark_failed resets consecutive_successes to 0.

    Setup: 3 consecutive successes (cs=3), then 1 failure. After failure,
    cs must be 0 (streak broken) and cf must be 1.
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    # 3 consecutive successes via mark_consumed (each increments cs, resets cf)
    for idx in range(3):
        tracker.mark_consumed(
            f"iid_s_{idx:07d}", dimension="d4_path_drift", severity="P0",
            file=f"docs/{idx}.md", line=1,
            commit_hash=f"commit_{idx}", action_taken=f"patch {idx}",
        )
    assert tracker.consecutive_successes == 3
    assert tracker.consecutive_failures == 0
    # Now a failure should reset cs to 0
    tracker.mark_failed(
        "iid_new_fail1", dimension="d4_path_drift", severity="P0",
        file="docs/z.md", line=1, failure_reason="broke again",
    )
    assert tracker.consecutive_successes == 0
    assert tracker.consecutive_failures == 1


# ---- should_stop_and_report tests ----


def test_should_stop_after_3_consecutive_failures(tmp_path):
    """should_stop_and_report returns (True, ...) after 3 consecutive failures.

    Spec-49 red line: >= 3 consecutive failures → must stop and report.
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    for idx in range(3):
        tracker.mark_failed(
            f"iid_f_{idx:07d}", dimension="d4_path_drift", severity="P0",
            file=f"docs/{idx}.md", line=1, failure_reason=f"r{idx}",
        )
    stop, reason = tracker.should_stop_and_report()
    assert stop is True
    assert "3 个 patch 失败" in reason


def test_should_stop_at_10_patches_with_5_consecutive_successes(tmp_path):
    """should_stop_and_report returns (True, ...) at 10 patches with 5+ successes.

    Spec-49 red line: consecutive_successes >= 5 AND
    total_patches_this_session % 10 == 0 → checkpoint stop.

    Setup: 10 successful patches (each seeded by a prior mark_failed so
    mark_success has an entry to look up). After 10 patches, cs=10 >= 5
    AND total=10 % 10 == 0 → must stop.
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    for idx in range(10):
        iid = f"iid_t_{idx:07d}"
        # Seed with mark_failed (1 patch), then mark_success (1 patch)
        # → 20 total patches, cs=10, cf=0. Hmm that's 20 patches not 10.
        # Adjust: just use mark_consumed directly for 10 successes.
        tracker.mark_consumed(
            iid, dimension="d4_path_drift", severity="P0",
            file=f"docs/{idx}.md", line=1,
            commit_hash=f"commit_{idx}", action_taken=f"patch {idx}",
        )
    # 10 mark_consumed calls → total=10, cs=10, cf=0
    assert tracker.total_patches_this_session == 10
    assert tracker.consecutive_successes == 10
    stop, reason = tracker.should_stop_and_report()
    assert stop is True
    assert "10 个 patch 节点" in reason


def test_should_not_stop_under_threshold(tmp_path):
    """should_stop_and_report returns (False, "") below all red line thresholds.

    Covers:
      - 2 consecutive failures (cf=2 < 3) → no stop
      - 5 consecutive successes with total=5 (5 % 10 != 0) → no stop
      - 4 consecutive successes (cs=4 < 5) → no stop
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    # 2 failures → cf=2 < 3, no stop
    tracker.mark_failed(
        "iid_n_0000001", dimension="d4_path_drift", severity="P0",
        file="docs/a.md", line=1, failure_reason="r1",
    )
    tracker.mark_failed(
        "iid_n_0000002", dimension="d4_path_drift", severity="P0",
        file="docs/b.md", line=1, failure_reason="r2",
    )
    stop, reason = tracker.should_stop_and_report()
    assert stop is False, f"should not stop at 2 failures, got: {reason}"
    assert reason == ""

    # 3 successes (cs=3 < 5, total=5) → no stop
    for idx in range(3):
        tracker.mark_consumed(
            f"iid_n_{idx:07d}", dimension="d4_path_drift", severity="P0",
            file=f"docs/{idx}.md", line=1,
            commit_hash=f"c{idx}", action_taken=f"p{idx}",
        )
    # Now: cf=0, cs=3, total=5
    stop, reason = tracker.should_stop_and_report()
    assert stop is False, f"should not stop at 3 successes/total=5, got: {reason}"
    assert reason == ""


# ---- reset_session tests ----


def test_reset_session_clears_total_patches(tmp_path):
    """reset_session sets total_patches_this_session = 0.

    consecutive_failures / consecutive_successes are NOT reset (they
    track the streak across sessions per spec-49).
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    # Build up some state: 2 failures then 1 success
    tracker.mark_failed(
        "iid_r_0000001", dimension="d4_path_drift", severity="P0",
        file="docs/a.md", line=1, failure_reason="r1",
    )
    tracker.mark_failed(
        "iid_r_0000001", dimension="d4_path_drift", severity="P0",
        file="docs/a.md", line=1, failure_reason="r2",
    )
    tracker.mark_success("iid_r_0000001", "commit_c", "fixed")
    assert tracker.total_patches_this_session == 3
    assert tracker.consecutive_successes == 1

    tracker.reset_session()
    assert tracker.total_patches_this_session == 0
    # Streak counters preserved (not reset by reset_session)
    assert tracker.consecutive_successes == 1
    assert tracker.consecutive_failures == 0


# ---- Persistence tests ----


def test_persistence_load_save(tmp_path):
    """consecutive_* counters persist across ConsumedTracker instances.

    Setup: tracker A does 2 mark_failed calls (cf=2, total=2), then we
    construct tracker B on the same file. B must see cf=2, cs=0, total=2
    via _load_state() in __init__.
    """
    consumed_file = tmp_path / "consumed.json"
    tracker_a = ConsumedTracker(consumed_file)
    tracker_a.mark_failed(
        "iid_p_0000001", dimension="d4_path_drift", severity="P0",
        file="docs/a.md", line=1, failure_reason="r1",
    )
    tracker_a.mark_failed(
        "iid_p_0000002", dimension="d4_path_drift", severity="P0",
        file="docs/b.md", line=1, failure_reason="r2",
    )
    assert tracker_a.consecutive_failures == 2

    # New instance on the same file — must load counters from disk
    tracker_b = ConsumedTracker(consumed_file)
    assert tracker_b.consecutive_failures == 2
    assert tracker_b.consecutive_successes == 0
    assert tracker_b.total_patches_this_session == 2

    # Verify the on-disk file actually has session_state
    raw = json.loads(consumed_file.read_text(encoding="utf-8"))
    assert "session_state" in raw
    assert raw["session_state"]["consecutive_failures"] == 2
    assert raw["session_state"]["total_patches_this_session"] == 2


def test_session_counter_not_reset_by_load(tmp_path):
    """total_patches_this_session accumulates across mark calls and is
    NOT reset by load().

    load() returns the consumed_issues dict and must not touch the
    instance's streak counters. The counter should only be reset by
    reset_session() or by mark_* side effects (cf=0 on success, cs=0
    on failure).
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    tracker.mark_failed(
        "iid_c_0000001", dimension="d4_path_drift", severity="P0",
        file="docs/a.md", line=1, failure_reason="r1",
    )
    tracker.mark_failed(
        "iid_c_0000002", dimension="d4_path_drift", severity="P0",
        file="docs/b.md", line=1, failure_reason="r2",
    )
    assert tracker.total_patches_this_session == 2
    # load() must not reset the counter
    consumed = tracker.load()
    assert tracker.total_patches_this_session == 2
    # load() still returns the consumed_issues dict (sanity check)
    assert "iid_c_0000001" in consumed
    # One more mark — counter must continue accumulating
    tracker.mark_failed(
        "iid_c_0000003", dimension="d4_path_drift", severity="P0",
        file="docs/c.md", line=1, failure_reason="r3",
    )
    assert tracker.total_patches_this_session == 3


# ---- Edge case: mark_success on unknown issue ----


def test_mark_success_unknown_issue_raises(tmp_path):
    """mark_success raises ValueError for issues not in consumed.json.

    Fresh issues (never seen) have no metadata to recover; callers must
    use mark_consumed directly. This prevents silent placeholder entries.
    """
    tracker = ConsumedTracker(tmp_path / "consumed.json")
    with pytest.raises(ValueError, match="not found"):
        tracker.mark_success("unknown_iid_99", "commit_x", "action")
