"""Tests for plugins.views pure logic functions: _compute_checksum, _validate_manifest, _serialize_plugin."""

import hashlib
import os
import tempfile
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from plugins.models import PluginPackage, PluginSandbox
from plugins.views import _compute_checksum, _serialize_plugin, _validate_manifest


class ComputeChecksumTests(TestCase):
    """_compute_checksum returns SHA-256 hex digest of file content."""

    def test_known_content(self):
        """Checksum matches manually computed SHA-256 for known content."""
        with tempfile.NamedTemporaryFile(delete=False, mode='wb', suffix='.bin') as f:
            f.write(b'hello gaf')
            tmp_path = f.name
        try:
            expected = hashlib.sha256(b'hello gaf').hexdigest()
            self.assertEqual(_compute_checksum(tmp_path), expected)
        finally:
            os.unlink(tmp_path)

    def test_empty_file(self):
        """Checksum of empty file equals SHA-256 of empty string."""
        with tempfile.NamedTemporaryFile(delete=False, mode='wb', suffix='.bin') as f:
            tmp_path = f.name
        try:
            expected = hashlib.sha256(b'').hexdigest()
            self.assertEqual(_compute_checksum(tmp_path), expected)
        finally:
            os.unlink(tmp_path)

    def test_large_file_chunked(self):
        """Checksum works for content larger than the 8192-byte read chunk."""
        content = b'x' * 20000
        with tempfile.NamedTemporaryFile(delete=False, mode='wb', suffix='.bin') as f:
            f.write(content)
            tmp_path = f.name
        try:
            expected = hashlib.sha256(content).hexdigest()
            self.assertEqual(_compute_checksum(tmp_path), expected)
        finally:
            os.unlink(tmp_path)


class ValidateManifestTests(TestCase):
    """_validate_manifest returns (is_valid, error_message) tuple."""

    def test_valid_manifest(self):
        """Valid manifest with name and version returns (True, None)."""
        valid, msg = _validate_manifest({'name': 'p', 'version': '1.0'})
        self.assertTrue(valid)
        self.assertIsNone(msg)

    def test_missing_name(self):
        """Manifest without name returns (False, error mentioning name)."""
        valid, msg = _validate_manifest({'version': '1.0'})
        self.assertFalse(valid)
        self.assertIn('name', msg)

    def test_missing_version(self):
        """Manifest without version returns (False, error mentioning version)."""
        valid, msg = _validate_manifest({'name': 'p'})
        self.assertFalse(valid)
        self.assertIn('version', msg)

    def test_not_a_dict(self):
        """Non-dict manifest returns (False, error)."""
        valid, msg = _validate_manifest('not-a-dict')
        self.assertFalse(valid)
        self.assertIsNotNone(msg)

    def test_none_input(self):
        """None input returns (False, error)."""
        valid, msg = _validate_manifest(None)
        self.assertFalse(valid)
        self.assertIsNotNone(msg)


class SerializePluginTests(TestCase):
    """_serialize_plugin returns dict with all expected keys."""

    def test_serialize_without_sandbox(self):
        """Serialization of package without sandbox returns None for sandbox fields."""
        installed_at = timezone.now()
        pkg = PluginPackage.objects.create(
            name='ser-pkg', version='1.0.0', author='tester',
            description='a test plugin', manifest={'entry_point': 'main.py'},
            is_installed=True, is_active=True, checksum='abc123',
            installed_at=installed_at,
        )
        data = _serialize_plugin(pkg)
        self.assertEqual(data['name'], 'ser-pkg')
        self.assertEqual(data['version'], '1.0.0')
        self.assertEqual(data['author'], 'tester')
        self.assertEqual(data['description'], 'a test plugin')
        self.assertEqual(data['manifest'], {'entry_point': 'main.py'})
        self.assertTrue(data['is_installed'])
        self.assertTrue(data['is_active'])
        self.assertEqual(data['checksum'], 'abc123')
        self.assertIsNone(data['sandbox_status'])
        self.assertIsNone(data['sandbox_pid'])
        self.assertIsNotNone(data['installed_at'])
        self.assertIsNotNone(data['created_at'])
        self.assertIsNotNone(data['updated_at'])

    def test_serialize_with_sandbox(self):
        """Serialization includes latest sandbox status and pid."""
        pkg = PluginPackage.objects.create(name='sb-pkg', version='1.0.0')
        old_sb = PluginSandbox.objects.create(plugin=pkg, pid=100, status='stopped')
        # Force distinct created_at timestamps so -created_at ordering is deterministic
        PluginSandbox.objects.filter(pk=old_sb.pk).update(
            created_at=timezone.now() - timedelta(seconds=10),
        )
        PluginSandbox.objects.create(plugin=pkg, pid=200, status='running')
        data = _serialize_plugin(pkg)
        # Latest sandbox (ordered by -created_at) should be the running one
        self.assertEqual(data['sandbox_status'], 'running')
        self.assertEqual(data['sandbox_pid'], 200)

    def test_serialize_null_installed_at(self):
        """installed_at None serializes to None."""
        pkg = PluginPackage.objects.create(name='not-installed', version='1.0')
        data = _serialize_plugin(pkg)
        self.assertIsNone(data['installed_at'])
        self.assertFalse(data['is_installed'])
