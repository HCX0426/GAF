"""doc_health_consumed.py - Spec-42 Phase 1: consumed issue tracking.

Reads/writes `.cache/doc_health_consumed.json` so the self-evolution flywheel
can skip issues that have already been patched in prior sessions.

JSON Schema (see spec-42 §3.1.1, spec-49 §0.5 red line):
    {
      "schema_version": 1,
      "last_updated": "ISO 8601",
      "consumed_issues": {
        "<issue_id_12char>": {
          "dimension": "d4_path_drift",
          "severity": "P0",
          "file": ".ai-memory/lessons/x.md",
          "line": 8,
          "consumed_at": "ISO 8601",
          "commit_hash": "abc1234",
          "action_taken": "updated related_files path",
          "lesson_id": "N177",
          "recurrence_count": 0,
          "patch_failed": false,
          "failure_reason": null
        }
      },
      "session_state": {
        "consecutive_failures": 0,
        "consecutive_successes": 0,
        "total_patches_this_session": 0
      }
    }

The ``session_state`` block (added by spec-49 TD-318) tracks the AI patch
flow's streak counters so the orchestrator can enforce red lines:
  - consecutive_failures >= 3  → must stop and report to user
  - consecutive_successes >= 5 AND total_patches_this_session % 10 == 0
    → checkpoint: stop and report progress (avoid context exhaustion)

Performance budget: load + filter < 0.1s (file < 100KB).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Bootstrap: make scripts/ importable for direct execution
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from governance.report_schema import Issue  # noqa: E402


SCHEMA_VERSION = 1


class ConsumedTracker:
    """Read/write consumed issues state. Single source of truth.

    The on-disk file is wrapped with schema_version + last_updated metadata;
    callers interact with the inner ``consumed_issues`` dict directly via
    ``load()`` / ``save()``.
    """

    def __init__(self, consumed_file: Path):
        self.consumed_file = Path(consumed_file)
        # Spec-49 red line counters (TD-318): persisted to consumed_file via
        # save() under the ``session_state`` key. Loaded from file by
        # ``_load_state()`` so a fresh ConsumedTracker reflects prior sessions.
        self.consecutive_failures: int = 0
        self.consecutive_successes: int = 0
        self.total_patches_this_session: int = 0
        self._load_state()

    # ---- I/O ----

    def _load_state(self) -> None:
        """Best-effort load of ``session_state`` counters into self.

        Reads the on-disk JSON and populates ``consecutive_failures``,
        ``consecutive_successes``, ``total_patches_this_session`` from the
        ``session_state`` block. Stays silent (defaults remain 0) if the
        file is missing, corrupted, or lacks the block (backward compat
        with pre-spec-49 files).

        Unlike ``load()``, this does NOT check ``schema_version`` — the
        counters are meaningful even if the consumed_issues dict is reset
        by a schema migration (the streak persists).
        """
        if not self.consumed_file.exists():
            return
        try:
            raw = json.loads(self.consumed_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(raw, dict):
            return
        state = raw.get("session_state")
        if not isinstance(state, dict):
            return
        try:
            self.consecutive_failures = int(state.get("consecutive_failures", 0))
            self.consecutive_successes = int(state.get("consecutive_successes", 0))
            self.total_patches_this_session = int(
                state.get("total_patches_this_session", 0)
            )
        except (TypeError, ValueError):
            # Non-integer values in session_state — keep defaults (0).
            return

    def load(self) -> dict[str, dict]:
        """Load consumed issues.

        Returns the inner ``consumed_issues`` dict (issue_id -> entry).
        Returns empty dict if file missing, corrupted, or schema_version
        does not match ``SCHEMA_VERSION`` (graceful degradation).

        Note: this method does NOT refresh the spec-49 streak counters
        (``consecutive_failures`` etc.) — those are loaded once in
        ``__init__`` via ``_load_state()`` and updated by ``mark_*`` /
        ``reset_session``. Callers needing fresh counters should construct
        a new ConsumedTracker.
        """
        if not self.consumed_file.exists():
            return {}
        try:
            raw = json.loads(self.consumed_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        if not isinstance(raw, dict):
            return {}
        if raw.get("schema_version") != SCHEMA_VERSION:
            # Schema mismatch: gracefully degrade to empty (caller re-marks
            # issues as they recur; no data loss in source docs).
            return {}
        issues = raw.get("consumed_issues", {})
        if not isinstance(issues, dict):
            return {}
        # Soft cap warning (spec-43 §3.3.2): warn at 80% of hard cap (1000).
        # Does not affect return value; nudges operator to run forget_expired().
        if len(issues) > 800:
            print(
                f"warning: doc_health_consumed.json has {len(issues)} entries "
                f"(approaching hard cap 1000). Consider running forget_expired() "
                f"or increasing patch success rate.",
                file=sys.stderr,
            )
        return issues

    def save(self, consumed: dict[str, dict]) -> None:
        """Persist consumed issues with atomic write (tmp + os.replace).

        Wraps the inner dict with schema_version + last_updated metadata,
        and also persists the spec-49 streak counters under
        ``session_state``. ``os.replace`` is atomic on Windows (unlike
        ``Path.rename`` which fails when the destination exists).
        """
        self.consumed_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "last_updated": datetime.now().astimezone().isoformat(),
            "consumed_issues": consumed,
            "session_state": {
                "consecutive_failures": self.consecutive_failures,
                "consecutive_successes": self.consecutive_successes,
                "total_patches_this_session": self.total_patches_this_session,
            },
        }
        # Write to tmp file in same directory (required for os.replace
        # to be atomic — must be same filesystem).
        tmp_file = self.consumed_file.with_suffix(
            self.consumed_file.suffix + ".tmp"
        )
        tmp_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_file, self.consumed_file)

    # ---- Queries ----

    def is_consumed(self, issue_id: str) -> bool:
        """Return True if issue_id is consumed AND patch_failed is false.

        patch_failed=true entries are NOT considered consumed (they need
        re-patch or TD escalation).
        """
        consumed = self.load()
        entry = consumed.get(issue_id)
        if entry is None:
            return False
        return not entry.get("patch_failed", False)

    def get_recurrence_count(self, dimension: str) -> int:
        """Count distinct issue_ids in ``dimension`` with recurrence_count >= 1.

        Used by the D2 lesson trigger (>= 3 recurrences in same dimension
        forces a lesson write per spec-42 §3.3.2).
        """
        consumed = self.load()
        return sum(
            1
            for entry in consumed.values()
            if entry.get("dimension") == dimension
            and entry.get("recurrence_count", 0) >= 1
        )

    def check_d2_lesson_trigger(self, dimension: str) -> dict | None:
        """If dimension has >= 3 distinct issue_ids with recurrence_count >= 1, return lesson trigger dict.

        D2 trigger condition (spec-42 §3.3.2): same dimension has 3+ distinct
        issue_ids where each has recurrence_count >= 1 (i.e., patch failed at
        least once). This signals a systemic issue with the dimension that
        needs lesson sedimentation per §3.8 + N166.

        Returns:
            dict with keys: dimension, recurrence_issue_ids (list[str]),
            suggested_lesson_topic (str like "doc_health_<dimension>_recurrence")
            None if trigger condition not met.
        """
        recurrences = [
            iid for iid, data in self.load().items()
            if data.get("dimension") == dimension
            and data.get("recurrence_count", 0) >= 1
        ]
        if len(recurrences) >= 3:
            return {
                "dimension": dimension,
                "recurrence_issue_ids": recurrences,
                "suggested_lesson_topic": f"doc_health_{dimension}_recurrence",
            }
        return None

    def check_td_escalation(self, dimension: str) -> dict | None:
        """If dimension has any issue with recurrence_count >= 2, return TD escalation dict.

        F2 trigger condition (spec-42 §3.3.4): same dimension has any issue with
        recurrence_count >= 2 (i.e., patch failed 2+ times). This signals the
        auto-patch flow cannot resolve this issue — escalate to TD for human
        intervention per §4.8.

        Returns:
            dict with keys: dimension, issue_id (str),
            recurrence_count (int),
            suggested_td_title (str like "doc_health <dimension> issue <id> auto-patch failed <N>x")
            None if no escalation needed.
        """
        for iid, data in self.load().items():
            if (data.get("dimension") == dimension
                    and data.get("recurrence_count", 0) >= 2):
                return {
                    "dimension": dimension,
                    "issue_id": iid,
                    "recurrence_count": data["recurrence_count"],
                    "suggested_td_title": f"doc_health {dimension} issue {iid} auto-patch failed {data['recurrence_count']}x",
                }
        return None

    def filter_unconsumed(self, issues: list[Issue]) -> list[Issue]:
        """Filter out consumed issues (consumed=True AND patch_failed=false).

        Issues with patch_failed=true are KEPT (need re-patch or TD
        escalation). Preserves input order.
        """
        consumed = self.load()
        result: list[Issue] = []
        for issue in issues:
            entry = consumed.get(issue.id)
            if entry is None:
                result.append(issue)
                continue
            if entry.get("patch_failed", False):
                # Failed patches stay in the queue for re-patch / TD escalation
                result.append(issue)
                continue
            # Consumed and not failed: skip
        return result

    # ---- Mutations ----

    def mark_consumed(
        self,
        issue_id: str,
        *,
        dimension: str,
        severity: str,
        file: str | None,
        line: int | None,
        commit_hash: str,
        action_taken: str,
        lesson_id: str | None = None,
    ) -> None:
        """Mark issue as consumed. Overwrites if exists.

        Updates ``consumed_at`` + ``commit_hash`` + ``action_taken``.
        Resets ``patch_failed=false`` and ``failure_reason=null``.
        ``recurrence_count`` is preserved if previously set (the issue
        had failed before being successfully patched); stays 0 otherwise.

        Spec-49 (TD-318): also increments ``consecutive_successes``,
        resets ``consecutive_failures`` to 0, and increments
        ``total_patches_this_session``. Counters are persisted by the
        subsequent ``save()`` call.
        """
        consumed = self.load()
        existing = consumed.get(issue_id, {})
        recurrence_count = existing.get("recurrence_count", 0)
        consumed[issue_id] = {
            "dimension": dimension,
            "severity": severity,
            "file": file,
            "line": line,
            "consumed_at": datetime.now().astimezone().isoformat(),
            "commit_hash": commit_hash,
            "action_taken": action_taken,
            "lesson_id": lesson_id,
            "recurrence_count": recurrence_count,
            "patch_failed": False,
            "failure_reason": None,
        }
        # Spec-49 red line counters (TD-318)
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        self.total_patches_this_session += 1
        self.save(consumed)

    def mark_failed(
        self,
        issue_id: str,
        *,
        dimension: str,
        severity: str,
        file: str | None,
        line: int | None,
        failure_reason: str,
    ) -> None:
        """Mark issue as patch_failed=true, recurrence_count += 1.

        On first failure, recurrence_count is set to 1. ``failure_reason``
        is stored for diagnosis. Does NOT auto-escalate TD — caller checks
        ``recurrence_count >= 2`` and escalates per spec-42 §3.3.4.

        If the issue was previously consumed successfully, the
        ``consumed_at`` / ``commit_hash`` / ``action_taken`` fields are
        preserved (audit trail of the prior success) but ``patch_failed``
        flips to true.

        Spec-49 (TD-318): also increments ``consecutive_failures``,
        resets ``consecutive_successes`` to 0, and increments
        ``total_patches_this_session``. Counters are persisted by the
        subsequent ``save()`` call. Callers should check
        ``should_stop_and_report()`` after each mark_failed to enforce
        the "3 consecutive failures → stop" red line.
        """
        consumed = self.load()
        existing = consumed.get(issue_id, {})
        recurrence_count = existing.get("recurrence_count", 0) + 1
        entry = {
            "dimension": dimension,
            "severity": severity,
            "file": file,
            "line": line,
            # Preserve prior audit trail if present
            "consumed_at": existing.get("consumed_at"),
            "commit_hash": existing.get("commit_hash"),
            "action_taken": existing.get("action_taken"),
            "lesson_id": existing.get("lesson_id"),
            "recurrence_count": recurrence_count,
            "patch_failed": True,
            "failure_reason": failure_reason,
        }
        # Drop None values to keep JSON compact (matches Issue.to_dict style)
        consumed[issue_id] = {k: v for k, v in entry.items() if v is not None}
        # Spec-49 red line counters (TD-318)
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.total_patches_this_session += 1
        self.save(consumed)

    def mark_success(
        self,
        issue_id: str,
        commit_hash: str,
        action_taken: str,
    ) -> None:
        """Spec-49 (TD-318) convenience wrapper: mark a patch as successful.

        Looks up the existing entry for ``issue_id`` (typically from a
        prior ``mark_failed``) to recover ``dimension`` / ``severity`` /
        ``file`` / ``line`` / ``lesson_id``, then calls ``mark_consumed``
        with the full metadata + the new ``commit_hash`` / ``action_taken``.

        Counter updates (``consecutive_successes += 1`` etc.) are handled
        by ``mark_consumed`` — callers do not need to update them manually.

        Raises:
            ValueError: if ``issue_id`` is not present in consumed.json.
                Fresh issues (never seen before) have no metadata to
                recover; callers should use ``mark_consumed`` directly
                with the full keyword arguments.
        """
        consumed = self.load()
        entry = consumed.get(issue_id)
        if entry is None:
            raise ValueError(
                f"mark_success: issue_id {issue_id!r} not found in "
                f"consumed.json; use mark_consumed() with full metadata "
                f"for fresh issues"
            )
        self.mark_consumed(
            issue_id,
            dimension=entry.get("dimension", ""),
            severity=entry.get("severity", "P2"),
            file=entry.get("file"),
            line=entry.get("line"),
            commit_hash=commit_hash,
            action_taken=action_taken,
            lesson_id=entry.get("lesson_id"),
        )

    def should_stop_and_report(self) -> tuple[bool, str]:
        """Spec-49 (TD-318) red line check: should the AI patch flow pause?

        Returns ``(True, reason)`` if either red line is hit:
            - ``consecutive_failures >= 3`` — must stop and report to user
              (prevents AI from continuously escalating TDs without notice).
            - ``consecutive_successes >= 5`` AND
              ``total_patches_this_session % 10 == 0`` — checkpoint stop:
              report progress to avoid context exhaustion.

        Returns ``(False, "")`` otherwise (flow may continue).

        The counters are instance state, kept in sync with the on-disk
        ``session_state`` block by ``__init__`` / ``mark_*`` /
        ``reset_session``. Callers should call this after each
        ``mark_success`` / ``mark_failed`` to enforce the red lines.
        """
        if self.consecutive_failures >= 3:
            return (
                True,
                "spec-49 红线: 连续 3 个 patch 失败, 必须停下报告用户",
            )
        if (
            self.consecutive_successes >= 5
            and self.total_patches_this_session > 0
            and self.total_patches_this_session % 10 == 0
        ):
            return (
                True,
                "spec-49 红线: 5 个连续成功 + 10 个 patch 节点, 停下报告进度",
            )
        return (False, "")

    def reset_session(self) -> None:
        """Spec-49 (TD-318): reset session-scoped counter (new conversation).

        Sets ``total_patches_this_session = 0`` and persists the change.
        ``consecutive_failures`` / ``consecutive_successes`` are NOT reset
        — they track the current patch streak across sessions (a failure
        streak at the end of session 1 should still trigger the red line
        at the start of session 2).

        The orchestrator should call this at the start of each new AI
        conversation so the 10-patch checkpoint counter restarts.
        """
        self.total_patches_this_session = 0
        consumed = self.load()
        self.save(consumed)

    # ---- Forgetting (spec-43 Phase 2) ----

    def forget_expired(self) -> tuple[int, int]:
        """Forget expired entries per ForgetPolicy. Return (forgotten_count, kept_count).

        Side effects:
            - Rewrites consumed.json with kept entries only.
            - Appends forgotten entries to archive file:
              .cache/doc_health_consumed_archive_YYYYMM.json
            - Enforces hard cap (1000 entries) after time-based forgetting.

        Returns:
            Tuple of (forgotten_count, kept_count).
        """
        # Lazy import to avoid circular dependency (doc_health_forget does
        # not import doc_health_consumed, but keep lazy for module isolation).
        from governance.doc_health_forget import ForgetPolicy

        consumed = self.load()
        policy = ForgetPolicy()

        kept, forgotten = policy.forget_expired(consumed)
        kept, force_forgotten = policy.enforce_hard_cap(kept)
        forgotten.update(force_forgotten)

        if forgotten:
            self.save(kept)
            self._archive(forgotten)

        return len(forgotten), len(kept)

    def _archive(self, forgotten: dict[str, dict]) -> None:
        """Append forgotten entries to monthly archive file.

        Archive file path: .cache/doc_health_consumed_archive_YYYYMM.json
        Merges with existing archive (does not overwrite).
        Uses atomic write (tmp + os.replace).
        """
        now = datetime.now().astimezone()
        archive_file = self.consumed_file.parent / (
            f"doc_health_consumed_archive_{now.strftime('%Y%m')}.json"
        )
        existing: dict[str, dict] = {}
        if archive_file.exists():
            try:
                raw = json.loads(archive_file.read_text(encoding="utf-8"))
                existing = raw.get("consumed_issues", {}) if isinstance(raw, dict) else {}
            except (json.JSONDecodeError, OSError):
                existing = {}
        existing.update(forgotten)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "last_updated": now.isoformat(),
            "consumed_issues": existing,
        }
        tmp = archive_file.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, archive_file)
