"""Backup create / restore API tests — covers P0 security fix (L3-1 Round 1).

Validates that:
- create_backup returns a ZIP containing database.json + backup_info.json
- restore_backup uses call_command('loaddata', ...) (symmetric with dumpdata)
  and never executes arbitrary SQL via cursor.execute
- restore round-trip (create → restore) succeeds
- malicious JSON payload (e.g. raw SQL) is rejected by loaddata, not executed
- restore skips cleanly when database.json is absent
"""

import io
import zipfile

import pytest
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.factories import AdminUserFactory


class TestBackupCreate(TestCase):
    """create_backup endpoint tests."""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_create_backup_returns_zip(self):
        """POST /api/v2/tasks/backup/create/ returns ZIP with database.json + backup_info.json."""
        response = self.client.post('/api/v2/tasks/backup/create/', {'tag': 'test_tag'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertIn('gaf_backup_test_tag.zip', response['Content-Disposition'])

        # Parse the ZIP and verify contents
        zip_bytes = b''.join(response.streaming_content)
        with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zf:
            names = zf.namelist()
            self.assertIn('database.json', names)
            self.assertIn('backup_info.json', names)

            # database.json should be valid JSON (dumpdata output), NOT SQL
            db_content = zf.read('database.json').decode('utf-8').strip()
            self.assertTrue(db_content.startswith('['), 'dumpdata output should be a JSON array')


class TestBackupRestore(TestCase):
    """restore_backup endpoint tests."""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _make_backup_zip(self, db_content: bytes, db_filename: str = 'database.json') -> bytes:
        """Build a ZIP with the given database file content for upload."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(db_filename, db_content)
            zf.writestr('backup_info.json', b'{"tag":"test"}')
        return buf.getvalue()

    def test_restore_backup_round_trip(self):
        """create → restore round-trip succeeds; loaddata is used, not cursor.execute."""
        # Step 1: create a real backup
        create_resp = self.client.post('/api/v2/tasks/backup/create/', {'tag': 'roundtrip'}, format='json')
        self.assertEqual(create_resp.status_code, status.HTTP_200_OK)
        zip_bytes = b''.join(create_resp.streaming_content)

        # Step 2: restore from that backup
        upload = io.BytesIO(zip_bytes)
        upload.name = 'gaf_backup_roundtrip.zip'
        restore_resp = self.client.post(
            '/api/v2/tasks/backup/restore/',
            {'file': upload},
            format='multipart',
        )

        # loaddata should succeed (round-trip works because dumpdata output is valid)
        self.assertEqual(restore_resp.status_code, status.HTTP_200_OK)
        # UnifiedResponse middleware 把原 response.data 包到 {code, message, data} 信封里
        self.assertEqual(restore_resp.data['data']['status'], 'ok')

    def test_restore_backup_rejects_malicious_sql(self):
        """Malicious JSON file containing raw SQL must NOT be executed.

        Before the fix, restore_backup executed arbitrary SQL from the
        uploaded ZIP via the db cursor. After the fix, loaddata parses JSON
        and raises on non-JSON content.
        """
        malicious_zip = self._make_backup_zip(b'DROP TABLE auth_user;')
        upload = io.BytesIO(malicious_zip)
        upload.name = 'evil.zip'
        restore_resp = self.client.post(
            '/api/v2/tasks/backup/restore/',
            {'file': upload},
            format='multipart',
        )

        # restore_backup wraps loaddata in try/except → returns 500
        # (NOT 200 with SQL executed). The user table must still exist.
        self.assertEqual(restore_resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Verify user table was NOT dropped (SQL was never executed).
        # Use accounts.User because AUTH_USER_MODEL='accounts.User'.
        from accounts.models import User
        User.objects.count()  # raises ProgrammingError if table dropped

    def test_restore_backup_missing_db_file(self):
        """Restore skips cleanly when ZIP has no database.json."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('backup_info.json', b'{"tag":"test"}')
        upload = io.BytesIO(buf.getvalue())
        upload.name = 'no_db.zip'
        restore_resp = self.client.post(
            '/api/v2/tasks/backup/restore/',
            {'file': upload},
            format='multipart',
        )

        # No database.json → restore skipped, returns 200 ok
        self.assertEqual(restore_resp.status_code, status.HTTP_200_OK)
        # UnifiedResponse middleware 把原 response.data 包到 {code, message, data} 信封里
        self.assertEqual(restore_resp.data['data']['status'], 'ok')

    def test_restore_backup_rejects_non_zip(self):
        """Restore rejects non-ZIP uploads."""
        upload = io.BytesIO(b'not a zip')
        upload.name = 'evil.txt'
        restore_resp = self.client.post(
            '/api/v2/tasks/backup/restore/',
            {'file': upload},
            format='multipart',
        )
        self.assertEqual(restore_resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_cursor_execute_in_backup_views(self):
        """Guard: backup_views.py must never use the db cursor again (P0 regression guard).

        Checks the source file for the dangerous pattern (cursor.execute) and
        the deprecated filename (database.sql). Comments mentioning these
        tokens by name are acceptable as documentation.
        """
        import tasks.backup_views as bv
        with open(bv.__file__, encoding='utf-8') as f:
            source = f.read()

        # Strip comments (lines starting with #) and docstrings before checking.
        # This allows the file to document WHY cursor.execute is forbidden
        # without triggering the regression guard.
        stripped_lines = []
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            stripped_lines.append(line)
        stripped_source = '\n'.join(stripped_lines)

        self.assertNotIn('cursor.execute', stripped_source, 'cursor.execute must not appear in backup_views.py code')
        self.assertNotIn('database.sql', stripped_source, 'database.sql filename must be replaced with database.json')


@pytest.mark.django_db
def test_loaddata_symmetric_with_dumpdata():
    """Sanity check: loaddata can consume dumpdata output (Django contract)."""
    # This is a smoke test outside APIClient — verifies the Django contract
    # that backup_views relies on.
    import os
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        call_command('dumpdata', '--exclude=contenttypes', '--exclude=auth.permission', stdout=f)
        path = f.name
    try:
        # loaddata should accept the dumpdata output without error
        call_command('loaddata', path)
    finally:
        os.unlink(path)
