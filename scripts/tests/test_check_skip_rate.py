"""Tests for ``scripts/hooks/check_skip_rate.py`` (M2.C)."""

import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.hooks.check_skip_rate import (
    _filter_effective_commits,
    _load_bypass_timestamps,
    compute_bypass_rate,
)

pytestmark = pytest.mark.unit


def _make_commit(offset_minutes: int, subject: str = "feat: example") -> tuple:
    """Return a synthetic (hash, timestamp, subject) commit tuple."""
    base = datetime(2026, 6, 17, 0, 0, 0, tzinfo=timezone.utc)
    ts = int((base + timedelta(minutes=offset_minutes)).timestamp())
    return (f"abc{offset_minutes:04d}", ts, subject)


class TestFilterEffectiveCommits(unittest.TestCase):
    """Effective commit filtering."""

    def test_merge_commits_excluded(self):
        """Merge commits are not counted in the window."""
        commits = [
            _make_commit(1, "Merge branch 'main' of ..."),
            _make_commit(2, "feat: real work"),
        ]
        effective = _filter_effective_commits(commits)
        self.assertEqual(len(effective), 1)
        self.assertEqual(effective[0][2], "feat: real work")

    def test_revert_and_rollback_excluded(self):
        """Revert and rollback commits are not counted."""
        commits = [
            _make_commit(1, "Revert \"something\""),
            _make_commit(2, "rollback: bad commit"),
            _make_commit(3, "feat: real work"),
        ]
        effective = _filter_effective_commits(commits)
        self.assertEqual(len(effective), 1)
        self.assertEqual(effective[0][2], "feat: real work")


class TestLoadBypassTimestamps(unittest.TestCase):
    """Audit log parsing."""

    def test_valid_bypass_lines_parsed(self):
        """BYPASS lines with ISO timestamps are converted to epoch seconds."""
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write(
                "BYPASS ts=2026-06-17T12:00:00Z user=u reason=r args=a\n"
                "COMMIT 12345 args=b\n"
                "BYPASS ts=2026-06-17T13:00:00Z user=u reason=r args=c\n"
            )
            path = Path(f.name)
        try:
            timestamps = _load_bypass_timestamps(path)
            self.assertEqual(len(timestamps), 2)
            self.assertEqual(
                datetime.fromtimestamp(timestamps[0], tz=timezone.utc).hour, 12
            )
            self.assertEqual(
                datetime.fromtimestamp(timestamps[1], tz=timezone.utc).hour, 13
            )
        finally:
            path.unlink(missing_ok=True)

    def test_malformed_lines_ignored(self):
        """Malformed BYPASS lines do not crash parsing."""
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write(
                "BYPASS ts=bad user=u reason=r args=a\n"
                "BYPASS ts=2026-06-17T12:00:00Z user=u reason=r args=b\n"
            )
            path = Path(f.name)
        try:
            timestamps = _load_bypass_timestamps(path)
            self.assertEqual(len(timestamps), 1)
        finally:
            path.unlink(missing_ok=True)


class TestComputeBypassRate(unittest.TestCase):
    """Core rate computation."""

    def _bypass_ts(self, offset_minutes: int) -> int:
        base = datetime(2026, 6, 17, 0, 0, 0, tzinfo=timezone.utc)
        return int((base + timedelta(minutes=offset_minutes)).timestamp())

    def test_rate_below_threshold(self):
        """5 bypasses out of 30 commits is below 30%."""
        commits = [_make_commit(i) for i in range(30)]
        bypass_ts = [self._bypass_ts(i) for i in range(5)]
        count, rate = compute_bypass_rate(commits, bypass_ts)
        self.assertEqual(count, 5)
        self.assertAlmostEqual(rate, 5 / 30)

    def test_rate_at_threshold(self):
        """9 bypasses out of 30 commits is still below 30%."""
        commits = [_make_commit(i) for i in range(30)]
        bypass_ts = [self._bypass_ts(i) for i in range(9)]
        count, rate = compute_bypass_rate(commits, bypass_ts)
        self.assertEqual(count, 9)
        self.assertAlmostEqual(rate, 9 / 30)

    def test_rate_above_threshold(self):
        """10 bypasses out of 30 commits reaches 30% threshold."""
        commits = [_make_commit(i) for i in range(30)]
        bypass_ts = [self._bypass_ts(i) for i in range(10)]
        count, rate = compute_bypass_rate(commits, bypass_ts)
        self.assertEqual(count, 10)
        self.assertAlmostEqual(rate, 10 / 30)

    def test_merge_and_revert_not_counted(self):
        """Merge/revert commits excluded from denominator."""
        commits = [_make_commit(i, "feat: work") for i in range(20)]
        commits.extend(
            [_make_commit(i, "Merge branch main") for i in range(20, 25)]
        )
        commits.extend(
            [_make_commit(i, 'Revert "work"') for i in range(25, 30)]
        )
        # 20 effective commits, 8 bypasses = 40% > 30%.
        bypass_ts = [self._bypass_ts(i) for i in range(8)]
        count, rate = compute_bypass_rate(
            _filter_effective_commits(commits), bypass_ts
        )
        self.assertEqual(count, 8)
        self.assertEqual(rate, 8 / 20)

    def test_bypass_outside_window_ignored(self):
        """Bypasses outside the commit time window do not count."""
        commits = [_make_commit(i) for i in range(10)]
        bypass_ts = [
            self._bypass_ts(-10),
            self._bypass_ts(5),
            self._bypass_ts(100),
        ]
        count, rate = compute_bypass_rate(commits, bypass_ts)
        self.assertEqual(count, 1)
        self.assertAlmostEqual(rate, 1 / 10)


class TestMainCommandLine(unittest.TestCase):
    """CLI integration with the real git repository."""

    def test_dry_run_exits_zero(self):
        """``--dry-run`` always exits 0 and prints a rate line."""
        result = subprocess.run(
            [sys.executable, "scripts/hooks/check_skip_rate.py", "--dry-run"],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("AI bypass rate:", result.stdout)


if __name__ == "__main__":
    unittest.main()
