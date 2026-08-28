"""Tests for gaf_core.tasks.cleanup_old_archives (spec §8.3).

Verifies the periodic tar.gz + exec_dir cleanup:
- Archives (``*.tar.gz``) and exec dirs older than
  ``DEBUG_ARCHIVE_RETENTION_DAYS`` (default 30) are deleted; younger ones
  are kept.
- Non-``.tar.gz`` files in the archive dir are ignored (not deleted).
- Missing archive dir is handled gracefully (returns deleted_count=0).
- ``DEBUG_ARCHIVE_DIR`` unset → still sweeps DEBUG_DIR exec dirs.
- Per-file OSError does not abort the whole sweep.

N194 归一化 + 嵌套结构 (2026-07-29): cleanup now sweeps two locations:
1. ``<DEBUG_ARCHIVE_DIR>/**/*.tar.gz`` (嵌套 + 旧扁平兼容)
2. ``<DEBUG_DIR>/<YYYYMMDD>/<pipeline>/<HHMMSS_suffix>/`` (嵌套) +
   ``<DEBUG_DIR>/<YYYYMMDD_HHMMSS>_*_<suffix>/`` (旧扁平兼容)

旧 ``<DEBUG_DIR>/structured/*.jsonl`` 扫描已移除 (N194 归一化后
JSONL 在 exec_dir 内, 随 exec_dir 一起被删除).
"""
from __future__ import annotations

import os
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from gaf_core.tasks import cleanup_old_archives


class CleanupOldArchivesTest(TestCase):
    """cleanup_old_archives — retention sweep over <DEBUG_ARCHIVE_DIR> + <DEBUG_DIR>."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmpdir = self._tmpdir.name
        self.archive_dir = os.path.join(self.tmpdir, "archives")
        os.makedirs(self.archive_dir, exist_ok=True)

    def _make_archive(self, name: str, mtime_age_days: float) -> Path:
        """Create an empty .tar.gz with mtime set ``mtime_age_days`` ago."""
        path = Path(self.archive_dir) / name
        # ``touch`` then set mtime via os.utime.
        path.touch()
        target_ts = (timezone.now() - timedelta(days=mtime_age_days)).timestamp()
        os.utime(path, (target_ts, target_ts))
        return path

    def _make_exec_dir(self, date_str: str, pipeline: str, exec_name: str,
                       mtime_age_days: float) -> Path:
        """Create a nested exec dir under <tmpdir>/debug/ with mtime set.

        N194 嵌套结构: <debug>/<YYYYMMDD>/<pipeline>/<HHMMSS_suffix>/
        """
        exec_dir = Path(self.tmpdir) / "debug" / date_str / pipeline / exec_name
        exec_dir.mkdir(parents=True, exist_ok=True)
        # Touch a file inside so the dir has content
        (exec_dir / "run.log").touch()
        target_ts = (timezone.now() - timedelta(days=mtime_age_days)).timestamp()
        # Set mtime on the dir itself (cleanup uses exec_entry.stat().st_mtime)
        os.utime(exec_dir, (target_ts, target_ts))
        return exec_dir

    def test_deletes_old_archives_keeps_recent(self):
        """Archives older than retention are deleted; younger ones survive."""
        old = self._make_archive("exec-old.tar.gz", mtime_age_days=45)
        recent = self._make_archive("exec-recent.tar.gz", mtime_age_days=5)

        with override_settings(
            DEBUG_ARCHIVE_DIR=self.archive_dir,
            DEBUG_ARCHIVE_RETENTION_DAYS=30,
        ):
            result = cleanup_old_archives()

        self.assertEqual(result["deleted_count"], 1)
        self.assertFalse(old.exists(), "old archive should have been deleted")
        self.assertTrue(recent.exists(), "recent archive must survive")
        self.assertEqual(result["retention_days"], 30)

    def test_retention_threshold_is_inclusive_boundary(self):
        """File at exactly retention_days old is NOT deleted (>= cutoff kept).

        Boundary: file with mtime == cutoff - 1 second (just past threshold)
        gets deleted; file with mtime == cutoff + 1 second (just inside) is
        kept. The strict ``<`` comparison means files exactly at the
        cutoff survive.
        """
        # 1 second past the retention cutoff → deleted
        past = self._make_archive(
            "past.tar.gz", mtime_age_days=30 + 1 / 86400,
        )
        # 1 second inside the retention window → kept
        inside = self._make_archive(
            "inside.tar.gz", mtime_age_days=30 - 1 / 86400,
        )

        with override_settings(
            DEBUG_ARCHIVE_DIR=self.archive_dir,
            DEBUG_ARCHIVE_RETENTION_DAYS=30,
        ):
            result = cleanup_old_archives()

        self.assertEqual(result["deleted_count"], 1)
        self.assertFalse(past.exists())
        self.assertTrue(inside.exists())

    def test_ignores_non_tar_gz_files(self):
        """Files not matching *.tar.gz are never deleted, regardless of age."""
        old_zip = Path(self.archive_dir) / "old.zip"
        old_zip.touch()
        ancient_ts = (timezone.now() - timedelta(days=400)).timestamp()
        os.utime(old_zip, (ancient_ts, ancient_ts))
        # Also add a tar.gz that should be deleted
        old_tar = self._make_archive("real-old.tar.gz", mtime_age_days=60)

        with override_settings(
            DEBUG_ARCHIVE_DIR=self.archive_dir,
            DEBUG_ARCHIVE_RETENTION_DAYS=30,
        ):
            result = cleanup_old_archives()

        self.assertEqual(result["deleted_count"], 1)
        self.assertFalse(old_tar.exists())
        # Non-matching file untouched even though it's way past retention.
        self.assertTrue(old_zip.exists())

    def test_missing_archive_dir_returns_zero(self):
        """DEBUG_ARCHIVE_DIR points at a missing dir — log warning, return 0.

        N194: cleanup also sweeps <DEBUG_DIR>/ exec dirs, so a missing
        archive dir no longer triggers early-return 'skipped'. It logs
        a warning, continues to scan DEBUG_DIR, and returns 0.
        """
        nonexistent_archive = os.path.join(self.tmpdir, "does-not-exist")
        nonexistent_debug = os.path.join(self.tmpdir, "debug-also-missing")
        with override_settings(
            DEBUG_ARCHIVE_DIR=nonexistent_archive,
            DEBUG_DIR=nonexistent_debug,
            DEBUG_ARCHIVE_RETENTION_DAYS=30,
        ):
            result = cleanup_old_archives()

        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["exec_dirs_deleted"], 0)
        # No 'skipped' key — task proceeded (warning logged for missing dir).
        self.assertNotIn("skipped", result)

    def test_unset_archive_dir_returns_zero(self):
        """DEBUG_ARCHIVE_DIR=None — sweep DEBUG_DIR exec dirs only.

        N194: when DEBUG_ARCHIVE_DIR is None but DEBUG_DIR is set, cleanup
        skips the tar.gz sweep but still scans DEBUG_DIR for exec dirs.
        No early-return 'skipped' marker.
        """
        nonexistent_debug = os.path.join(self.tmpdir, "debug-missing")
        with override_settings(
            DEBUG_ARCHIVE_DIR=None,
            DEBUG_DIR=nonexistent_debug,
            DEBUG_ARCHIVE_RETENTION_DAYS=30,
        ):
            result = cleanup_old_archives()

        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["exec_dirs_deleted"], 0)
        # No 'skipped' key — task proceeded with DEBUG_DIR sweep.
        self.assertNotIn("skipped", result)

    def test_both_dirs_unset_returns_skipped(self):
        """Both DEBUG_ARCHIVE_DIR and DEBUG_DIR unset → return skipped."""
        with override_settings(
            DEBUG_ARCHIVE_DIR=None,
            DEBUG_DIR=None,
            DEBUG_ARCHIVE_RETENTION_DAYS=30,
        ):
            result = cleanup_old_archives()

        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["exec_dirs_deleted"], 0)
        self.assertEqual(
            result["skipped"],
            "both DEBUG_ARCHIVE_DIR and DEBUG_DIR unset",
        )

    def test_empty_archive_dir_returns_zero(self):
        """Empty directory is a valid state — return deleted_count=0."""
        with override_settings(
            DEBUG_ARCHIVE_DIR=self.archive_dir,
            DEBUG_ARCHIVE_RETENTION_DAYS=30,
        ):
            result = cleanup_old_archives()

        self.assertEqual(result["deleted_count"], 0)
        self.assertEqual(result["error_count"], 0)

    def test_per_file_error_does_not_abort_sweep(self):
        """An OSError on one file is logged but the sweep continues."""
        good_old = self._make_archive("good-old.tar.gz", mtime_age_days=45)
        bad = self._make_archive("bad.tar.gz", mtime_age_days=45)

        # Patch Path.unlink so the file named "bad.tar.gz" raises a
        # simulated OSError. Other files use the original implementation.
        original_unlink = Path.unlink

        def flaky_unlink(self, *args, **kwargs):
            if self.name == "bad.tar.gz":
                raise OSError("simulated permission denied")
            return original_unlink(self, *args, **kwargs)

        with override_settings(
            DEBUG_ARCHIVE_DIR=self.archive_dir,
            DEBUG_ARCHIVE_RETENTION_DAYS=30,
        ), mock.patch.object(Path, "unlink", flaky_unlink):
            result = cleanup_old_archives()

        # One deleted, one errored.
        self.assertEqual(result["deleted_count"], 1)
        self.assertEqual(result["error_count"], 1)
        self.assertFalse(good_old.exists(), "good-old should be deleted")
        self.assertTrue(bad.exists(), "bad file survived the OSError")

    def test_custom_retention_window_respected(self):
        """DEBUG_ARCHIVE_RETENTION_DAYS=7 deletes 10-day-old archives."""
        ten_day = self._make_archive("ten.tar.gz", mtime_age_days=10)
        three_day = self._make_archive("three.tar.gz", mtime_age_days=3)

        with override_settings(
            DEBUG_ARCHIVE_DIR=self.archive_dir,
            DEBUG_ARCHIVE_RETENTION_DAYS=7,
        ):
            result = cleanup_old_archives()

        self.assertEqual(result["deleted_count"], 1)
        self.assertEqual(result["retention_days"], 7)
        self.assertFalse(ten_day.exists())
        self.assertTrue(three_day.exists())

    # ── N194 嵌套结构: exec_dir sweep ───────────────────────────

    def test_deletes_old_exec_dirs_keeps_recent(self):
        """Exec dirs older than retention are deleted; younger survive.

        N194 (2026-07-29): cleanup_old_archives now sweeps
        <DEBUG_DIR>/<YYYYMMDD>/<pipeline>/<HHMMSS_suffix>/ exec dirs
        in addition to *.tar.gz archives.
        """
        old_exec = self._make_exec_dir(
            "20260615", "OldTask", "153000_a1b2c3d4", mtime_age_days=45,
        )
        recent_exec = self._make_exec_dir(
            "20260725", "RecentTask", "100000_e5f6g7h8", mtime_age_days=5,
        )
        debug_dir = os.path.join(self.tmpdir, "debug")

        with override_settings(
            DEBUG_ARCHIVE_DIR=self.archive_dir,
            DEBUG_DIR=debug_dir,
            DEBUG_ARCHIVE_RETENTION_DAYS=30,
        ):
            result = cleanup_old_archives()

        self.assertEqual(result["exec_dirs_deleted"], 1)
        self.assertFalse(old_exec.exists(), "old exec dir should be deleted")
        self.assertTrue(recent_exec.exists(), "recent exec dir must survive")

    def test_debug_dir_missing_does_not_warn(self):
        """Missing <DEBUG_DIR>/ is fine — archive-only deployment.

        N194: cleanup logs no warning for missing DEBUG_DIR (only
        for missing DEBUG_ARCHIVE_DIR, which is a configured path).
        """
        debug_dir = os.path.join(self.tmpdir, "fresh-debug-no-exec-dirs")
        os.makedirs(debug_dir, exist_ok=True)  # debug/ exists but empty

        with override_settings(
            DEBUG_ARCHIVE_DIR=self.archive_dir,
            DEBUG_DIR=debug_dir,
            DEBUG_ARCHIVE_RETENTION_DAYS=30,
        ):
            # Should not raise, should return exec_dirs_deleted=0.
            result = cleanup_old_archives()

        self.assertEqual(result["exec_dirs_deleted"], 0)
        self.assertEqual(result["error_count"], 0)
