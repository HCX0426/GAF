"""Tests for plugins API views: list, upload, install, toggle, uninstall, reload, sandbox-exec.

Covers CRUD, permission matrix (admin/operator/viewer), URL existence,
and error paths for each of the 7 APIViews.
"""

import io
import json
import os
import shutil
import tempfile
import zipfile
from unittest import mock

from django.conf import settings
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from plugins.models import PluginPackage, PluginSandbox


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _make_gafplugin(manifest_data, manifest_name='manifest.yaml', extra_files=None):
    """Build an in-memory .gafplugin zip containing a manifest.

    Returns a BytesIO with .name set, suitable for APIClient.post(..., format='multipart').
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        if manifest_name.endswith('.json'):
            zf.writestr(manifest_name, json.dumps(manifest_data))
        else:
            import yaml
            zf.writestr(manifest_name, yaml.dump(manifest_data, allow_unicode=True))
        if extra_files:
            for name, content in extra_files.items():
                zf.writestr(name, content)
    buf.seek(0)
    buf.name = 'plugin.gafplugin'
    return buf


class PluginViewTestBase(TestCase):
    """Base setUp with admin / operator / viewer users and login helper."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='plugin_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        self.operator = User.objects.create_user(
            username='plugin_operator', password='OpPass123!', role=User.Role.OPERATOR,
        )
        self.viewer = User.objects.create_user(
            username='plugin_viewer', password='ViewerPass123!', role=User.Role.VIEWER,
        )

    def _login(self, user):
        """Login as the given user and set Authorization header."""
        resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': user.username,
            'password': {
                self.admin: 'AdminPass123!',
                self.operator: 'OpPass123!',
                self.viewer: 'ViewerPass123!',
            }[user],
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Task 4.49 (P0-12, 2026-07-28): 修复 token 取值路径 (unified_response 信封)。
        _token = resp.data.get('data', {}).get('access') or resp.data.get('access')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")


class PluginListViewTests(PluginViewTestBase):
    """PluginListView — GET /api/v2/plugins/ (required_permission='view')."""

    def test_list_returns_all_packages(self):
        """Admin sees all plugin packages in list response."""
        PluginPackage.objects.create(name='a', version='1.0')
        PluginPackage.objects.create(name='b', version='2.0')
        self._login(self.admin)
        resp = self.client.get('/api/v2/plugins/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_unwrap(resp)), 2)

    def test_list_empty(self):
        """Empty list returns 200 with empty array."""
        self._login(self.admin)
        resp = self.client.get('/api/v2/plugins/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(resp), [])

    def test_viewer_can_access(self):
        """Viewer role has 'view' permission and can list plugins."""
        self._login(self.viewer)
        resp = self.client.get('/api/v2/plugins/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_unauthenticated_denied(self):
        """Unauthenticated request gets 401."""
        resp = self.client.get('/api/v2/plugins/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class PluginUploadViewTests(PluginViewTestBase):
    """PluginUploadView — POST /api/v2/plugins/upload/ (required_permission='execute')."""

    def test_upload_yaml_manifest_creates_package(self):
        """Valid .gafplugin with YAML manifest creates PluginPackage (201)."""
        self._login(self.admin)
        manifest = {'name': 'yaml-plugin', 'version': '1.0.0', 'author': 'tester'}
        buf = _make_gafplugin(manifest, 'manifest.yaml')
        resp = self.client.post(
            '/api/v2/plugins/upload/',
            {'file': buf},
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(resp)['name'], 'yaml-plugin')
        self.assertTrue(PluginPackage.objects.filter(name='yaml-plugin').exists())

    def test_upload_json_manifest_creates_package(self):
        """Valid .gafplugin with JSON manifest creates PluginPackage (201)."""
        self._login(self.admin)
        manifest = {'name': 'json-plugin', 'version': '2.0.0'}
        buf = _make_gafplugin(manifest, 'manifest.json')
        resp = self.client.post(
            '/api/v2/plugins/upload/',
            {'file': buf},
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(resp)['name'], 'json-plugin')

    def test_upload_missing_file(self):
        """No file in request returns 400."""
        self._login(self.admin)
        resp = self.client.post('/api/v2/plugins/upload/', {}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # unified_response 信封下, 400 错误的 data 可能为 None, 优先检查信封存在
        self.assertIsNotNone(resp.data)

    def test_upload_wrong_extension(self):
        """File not ending in .gafplugin returns 400."""
        self._login(self.admin)
        buf = io.BytesIO(b'fake')
        buf.name = 'plugin.zip'
        resp = self.client.post(
            '/api/v2/plugins/upload/',
            {'file': buf},
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_missing_manifest(self):
        """Zip without manifest.yaml/json returns 400."""
        self._login(self.admin)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as zf:
            zf.writestr('code.py', 'print("hello")')
        buf.seek(0)
        buf.name = 'no-manifest.gafplugin'
        resp = self.client.post(
            '/api/v2/plugins/upload/',
            {'file': buf},
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_invalid_manifest_missing_name(self):
        """Manifest without name field returns 400."""
        self._login(self.admin)
        buf = _make_gafplugin({'version': '1.0'}, 'manifest.yaml')
        resp = self.client.post(
            '/api/v2/plugins/upload/',
            {'file': buf},
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_updates_existing_uninstalled(self):
        """Uploading same name when not installed updates existing package (200)."""
        self._login(self.admin)
        PluginPackage.objects.create(name='upd-pkg', version='1.0', is_installed=False)
        buf = _make_gafplugin({'name': 'upd-pkg', 'version': '2.0'}, 'manifest.yaml')
        resp = self.client.post(
            '/api/v2/plugins/upload/',
            {'file': buf},
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(resp)['version'], '2.0')

    def test_upload_rejected_when_installed(self):
        """Uploading same name when already installed returns 400."""
        self._login(self.admin)
        PluginPackage.objects.create(name='inst-pkg', version='1.0', is_installed=True)
        buf = _make_gafplugin({'name': 'inst-pkg', 'version': '2.0'}, 'manifest.yaml')
        resp = self.client.post(
            '/api/v2/plugins/upload/',
            {'file': buf},
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_viewer_denied(self):
        """Viewer role lacks 'execute' permission and gets 403."""
        self._login(self.viewer)
        manifest = {'name': 'viewer-plugin', 'version': '1.0'}
        buf = _make_gafplugin(manifest, 'manifest.yaml')
        resp = self.client.post(
            '/api/v2/plugins/upload/',
            {'file': buf},
            format='multipart',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class PluginInstallViewTests(PluginViewTestBase):
    """PluginInstallView — POST /api/v2/plugins/<pk>/install/ (required_permission='execute')."""

    def test_install_not_found(self):
        """Non-existent pk returns 404."""
        self._login(self.admin)
        resp = self.client.post('/api/v2/plugins/99999/install/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_install_already_installed(self):
        """Already-installed package returns 400."""
        self._login(self.admin)
        pkg = PluginPackage.objects.create(name='ai', version='1.0', is_installed=True)
        resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/install/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_install_missing_package_file(self):
        """Package with missing file path returns 400."""
        self._login(self.admin)
        pkg = PluginPackage.objects.create(name='mf', version='1.0', package_path='')
        resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/install/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_install_success(self):
        """Install with valid zip file marks package as installed (200)."""
        self._login(self.admin)
        # Create a real .gafplugin temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.gafplugin') as tmp:
            pass
        with zipfile.ZipFile(tmp.name, 'w') as zf:
            zf.writestr('manifest.yaml', 'name: inst-ok\nversion: 1.0\n')
            zf.writestr('main.py', 'print("hello")\n')
        pkg = PluginPackage.objects.create(
            name='inst-ok', version='1.0', package_path=tmp.name,
            manifest={'entry_point': 'main.py'},
        )
        try:
            resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/install/')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            pkg.refresh_from_db()
            self.assertTrue(pkg.is_installed)
            self.assertIsNotNone(pkg.installed_at)
        finally:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
            extract_dir = os.path.join(settings.BASE_DIR, 'plugins_data', 'inst-ok')
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir, ignore_errors=True)

    def test_viewer_denied(self):
        """Viewer role gets 403 on install."""
        self._login(self.viewer)
        pkg = PluginPackage.objects.create(name='v', version='1.0')
        resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/install/')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class PluginToggleViewTests(PluginViewTestBase):
    """PluginToggleView — POST /api/v2/plugins/<pk>/toggle/ (required_permission='execute')."""

    def test_toggle_not_found(self):
        """Non-existent pk returns 404."""
        self._login(self.admin)
        resp = self.client.post('/api/v2/plugins/99999/toggle/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_toggle_not_installed(self):
        """Toggling uninstalled package returns 400."""
        self._login(self.admin)
        pkg = PluginPackage.objects.create(name='tg', version='1.0', is_installed=False)
        resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/toggle/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_toggle_activates(self):
        """Toggling installed inactive package activates it."""
        self._login(self.admin)
        pkg = PluginPackage.objects.create(name='tg-on', version='1.0', is_installed=True, is_active=False)
        resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/toggle/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pkg.refresh_from_db()
        self.assertTrue(pkg.is_active)

    def test_toggle_deactivates(self):
        """Toggling installed active package deactivates it."""
        self._login(self.admin)
        pkg = PluginPackage.objects.create(name='tg-off', version='1.0', is_installed=True, is_active=True)
        resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/toggle/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pkg.refresh_from_db()
        self.assertFalse(pkg.is_active)


class PluginUninstallViewTests(PluginViewTestBase):
    """PluginUninstallView — POST /api/v2/plugins/<pk>/uninstall/ (required_permission='execute')."""

    def test_uninstall_not_found(self):
        """Non-existent pk returns 404."""
        self._login(self.admin)
        resp = self.client.post('/api/v2/plugins/99999/uninstall/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_uninstall_deletes_package(self):
        """Uninstalling removes the PluginPackage from DB."""
        self._login(self.admin)
        pkg = PluginPackage.objects.create(name='un-pkg', version='1.0')
        resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/uninstall/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(_unwrap(resp)['success'])
        self.assertFalse(PluginPackage.objects.filter(pk=pkg.pk).exists())


class PluginReloadViewTests(PluginViewTestBase):
    """PluginReloadView — POST /api/v2/plugins/<pk>/reload/ (required_permission='execute')."""

    def test_reload_not_found(self):
        """Non-existent pk returns 404."""
        self._login(self.admin)
        resp = self.client.post('/api/v2/plugins/99999/reload/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_reload_not_installed(self):
        """Reloading uninstalled package returns 400."""
        self._login(self.admin)
        pkg = PluginPackage.objects.create(name='rl', version='1.0', is_installed=False)
        resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/reload/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reload_missing_package_file(self):
        """Reloading package with missing file returns 400."""
        self._login(self.admin)
        pkg = PluginPackage.objects.create(name='rl-mf', version='1.0', is_installed=True, package_path='')
        resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/reload/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reload_success(self):
        """Reload with valid zip updates checksum and manifest (200)."""
        self._login(self.admin)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.gafplugin') as tmp:
            pass
        with zipfile.ZipFile(tmp.name, 'w') as zf:
            zf.writestr('manifest.yaml', 'name: rl-ok\nversion: 2.0\nauthor: reloaded\n')
        pkg = PluginPackage.objects.create(
            name='rl-ok', version='1.0', is_installed=True, package_path=tmp.name,
        )
        try:
            resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/reload/')
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            pkg.refresh_from_db()
            self.assertEqual(pkg.version, '2.0')
            self.assertEqual(pkg.author, 'reloaded')
            self.assertTrue(pkg.checksum)
        finally:
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)


class PluginSandboxExecViewTests(PluginViewTestBase):
    """PluginSandboxExecView — POST /api/v2/plugins/<pk>/sandbox-exec/ (required_permission='execute')."""

    def test_exec_not_found(self):
        """Non-existent pk returns 404."""
        self._login(self.admin)
        resp = self.client.post('/api/v2/plugins/99999/sandbox-exec/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_exec_not_installed(self):
        """Executing uninstalled package returns 400."""
        self._login(self.admin)
        pkg = PluginPackage.objects.create(name='se', version='1.0', is_installed=False)
        resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/sandbox-exec/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_exec_already_running_conflict(self):
        """Executing plugin with running sandbox returns 409."""
        self._login(self.admin)
        pkg = PluginPackage.objects.create(name='se-run', version='1.0', is_installed=True)
        PluginSandbox.objects.create(plugin=pkg, pid=999, status='running')
        # Mock os.path.exists so the install dir check passes before the running check
        with mock.patch('plugins.views.os.path.exists', return_value=True):
            resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/sandbox-exec/')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_exec_success_with_mocked_subprocess(self):
        """Successful sandbox exec creates PluginSandbox with running status."""
        self._login(self.admin)
        pkg = PluginPackage.objects.create(
            name='sb-ok', version='1.0', is_installed=True,
            manifest={'entry_point': 'main.py'},
        )
        fake_process = mock.Mock()
        fake_process.pid = 4242

        # Mock os.path.exists to True (both extract_dir and entry_path checks)
        # and mock subprocess.Popen to avoid starting a real process
        with mock.patch('plugins.views.subprocess.Popen', return_value=fake_process), \
             mock.patch('plugins.views.os.path.exists', return_value=True):
            resp = self.client.post(f'/api/v2/plugins/{pkg.pk}/sandbox-exec/')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(resp)['status'], 'running')
        self.assertEqual(_unwrap(resp)['pid'], 4242)
        # Verify sandbox record created
        sb = PluginSandbox.objects.filter(plugin=pkg, status='running').first()
        self.assertIsNotNone(sb)
        self.assertEqual(sb.pid, 4242)
