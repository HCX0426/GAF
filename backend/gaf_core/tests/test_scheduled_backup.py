"""Tests for gaf_core.tasks.scheduled_backup (D7 定时自动备份).

Verifies the periodic full-backup snapshot task:
- Creates a ZIP snapshot under ``MEDIA_ROOT/backups/`` with database.json + backup_info.json.
- Retention: keeps at most ``BACKUP_RETENTION_COUNT`` snapshots, deletes the oldest.
- Idempotent / graceful when the backups dir does not exist yet.
"""
from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

from django.test import TestCase, override_settings

from gaf_core.tasks import BACKUP_RETENTION_COUNT, scheduled_backup


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix='gaf_media_test_'))
class ScheduledBackupTest(TestCase):
    """scheduled_backup — full snapshot to MEDIA_ROOT/backups/ + retention sweep."""

    def _snapshots(self) -> list[Path]:
        backups_dir = Path(self.settings.MEDIA_ROOT) / 'backups'
        return sorted(backups_dir.glob('gaf_backup_*.zip'), key=lambda p: p.stat().st_mtime)

    def setUp(self):
        # Use override_settings context-managed MEDIA_ROOT resolved at call time.
        self.settings = __import__('django.conf', fromlist=['settings']).settings

    def test_creates_zip_with_manifest(self):
        result = scheduled_backup()
        backups_dir = Path(self.settings.MEDIA_ROOT) / 'backups'
        self.assertTrue(backups_dir.exists())
        snapshot = Path(result['snapshot'])
        self.assertTrue(snapshot.exists())
        self.assertEqual(snapshot.parent, backups_dir)
        with zipfile.ZipFile(snapshot) as zf:
            names = zf.namelist()
            self.assertIn('database.json', names)
            self.assertIn('backup_info.json', names)

    def test_retention_keeps_only_newest(self):
        # Pre-create more snapshots than the retention cap.
        backups_dir = Path(self.settings.MEDIA_ROOT) / 'backups'
        backups_dir.mkdir(parents=True, exist_ok=True)
        for i in range(BACKUP_RETENTION_COUNT + 3):
            (backups_dir / f'gaf_backup_pre{i}.zip').write_bytes(b'x')
        scheduled_backup()
        self.assertLessEqual(len(self._snapshots()), BACKUP_RETENTION_COUNT)

    def test_missing_dir_is_created(self):
        # No prior backups directory — task must create it and succeed.
        result = scheduled_backup()
        self.assertTrue(result['snapshot'].endswith('.zip'))
