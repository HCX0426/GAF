"""R37-P2 C3 — ROI CRUD API tests.

Verifies the 6 endpoints on ResourcePackViewSet:
  GET    /resource-packs/{pk}/rois/                         — full rois.json
  PUT    /resource-packs/{pk}/rois/                         — full replace
  GET    /resource-packs/{pk}/rois/{task_name}/             — per-task ROIs
  PUT    /resource-packs/{pk}/rois/{task_name}/             — per-task replace
  POST   /resource-packs/{pk}/rois/{task_name}/             — add single ROI
  DELETE /resource-packs/{pk}/rois/{task_name}/{roi_name}/  — remove single ROI

Uses a temp directory as ResourcePack.directory_path so tests do not touch
the real resources/ tree. The rois.json file is created/modified/deleted by
the API under test.
"""
import json
import os
import tempfile

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from resources.models import ResourcePack

User = get_user_model()


@pytest.fixture
def admin_user(db):
    """Create an admin user for manage-permission write ops."""
    return User.objects.create_user(
        username='roi_admin',
        password='testpass123',
        role=User.Role.ADMIN,
    )


@pytest.fixture
def admin_client(admin_user):
    """Authenticated APIClient as admin."""
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def resource_pack_with_rois(db):
    """Create a ResourcePack whose directory contains a config/rois.json.

    Initial rois.json has:
      public: {main_menu: [1720, 20, 120, 70]}
      tasks: {login: {confirm_button: [795, 613, 340, 70]}}
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = os.path.join(tmpdir, 'config')
        os.makedirs(config_dir, exist_ok=True)
        rois_path = os.path.join(config_dir, 'rois.json')
        initial_rois = {
            'public': {
                'main_menu': [1720, 20, 120, 70],
            },
            'tasks': {
                'login': {
                    'confirm_button': [795, 613, 340, 70],
                },
            },
        }
        with open(rois_path, 'w', encoding='utf-8') as f:
            json.dump(initial_rois, f)

        pack = ResourcePack.objects.create(
            name='ROI Test Pack',
            version='1.0',
            directory_path=tmpdir,
            is_active=True,
        )
        yield pack  # pytest fixture cleanup handles tmpdir teardown

        # Cleanup DB record (tmpdir auto-removed by TemporaryDirectory context)
        pack.delete()


class TestRoiCrud:
    """ROI CRUD API integration tests."""

    def test_list_rois_returns_full_structure(self, admin_client, resource_pack_with_rois):
        """GET /resource-packs/{pk}/rois/ returns {public, tasks}."""
        pack = resource_pack_with_rois
        url = f'/api/v2/resources/resource-packs/{pack.id}/rois/'
        resp = admin_client.get(url)

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert 'public' in data
        assert 'tasks' in data
        assert data['public']['main_menu'] == [1720, 20, 120, 70]
        assert 'login' in data['tasks']
        assert data['tasks']['login']['confirm_button'] == [795, 613, 340, 70]

    def test_list_rois_task_filter(self, admin_client, resource_pack_with_rois):
        """GET /resource-packs/{pk}/rois/{task_name}/ returns single task ROIs."""
        pack = resource_pack_with_rois
        url = f'/api/v2/resources/resource-packs/{pack.id}/rois/login/'
        resp = admin_client.get(url)

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data['task_name'] == 'login'
        assert 'confirm_button' in data['rois']
        assert data['rois']['confirm_button'] == [795, 613, 340, 70]

    def test_replace_rois_full(self, admin_client, resource_pack_with_rois):
        """PUT /resource-packs/{pk}/rois/ replaces the entire rois.json."""
        pack = resource_pack_with_rois
        url = f'/api/v2/resources/resource-packs/{pack.id}/rois/'
        new_payload = {
            'public': {'back_button': [120, 20, 100, 66]},
            'tasks': {'get_email': {'email_box': [1564, 28, 95, 61]}},
        }
        resp = admin_client.put(url, new_payload, format='json')

        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()['public']['back_button'] == [120, 20, 100, 66]

        # Verify file was actually overwritten
        rois_path = os.path.join(pack.directory_path, 'config', 'rois.json')
        with open(rois_path, encoding='utf-8') as f:
            on_disk = json.load(f)
        assert on_disk['public'] == {'back_button': [120, 20, 100, 66]}
        assert on_disk['tasks'] == {'get_email': {'email_box': [1564, 28, 95, 61]}}
        # Old data is gone
        assert 'main_menu' not in on_disk['public']
        assert 'login' not in on_disk['tasks']

    def test_replace_rois_task(self, admin_client, resource_pack_with_rois):
        """PUT /resource-packs/{pk}/rois/{task_name}/ replaces only that task."""
        pack = resource_pack_with_rois
        url = f'/api/v2/resources/resource-packs/{pack.id}/rois/login/'
        new_login_rois = {
            'login_start_button': [1110, 612, 579, 189],
            '开始游戏': [1105, 656, 569, 98],
        }
        resp = admin_client.put(url, new_login_rois, format='json')

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data['task_name'] == 'login'
        assert 'login_start_button' in data['rois']

        # Verify file: login replaced, public untouched
        rois_path = os.path.join(pack.directory_path, 'config', 'rois.json')
        with open(rois_path, encoding='utf-8') as f:
            on_disk = json.load(f)
        assert on_disk['public']['main_menu'] == [1720, 20, 120, 70]  # untouched
        assert on_disk['tasks']['login'] == new_login_rois
        # Old ROI gone
        assert 'confirm_button' not in on_disk['tasks']['login']

    def test_create_roi_single(self, admin_client, resource_pack_with_rois):
        """POST /resource-packs/{pk}/rois/{task_name}/ adds a single ROI."""
        pack = resource_pack_with_rois
        url = f'/api/v2/resources/resource-packs/{pack.id}/rois/login/'
        body = {'name': 'login_confirm_button', 'coords': [924, 589, 80, 45]}
        resp = admin_client.post(url, body, format='json')

        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        assert data['name'] == 'login_confirm_button'
        assert data['coords'] == [924, 589, 80, 45]

        # Verify file: new ROI added, existing ROIs preserved
        rois_path = os.path.join(pack.directory_path, 'config', 'rois.json')
        with open(rois_path, encoding='utf-8') as f:
            on_disk = json.load(f)
        assert 'login_confirm_button' in on_disk['tasks']['login']
        assert on_disk['tasks']['login']['login_confirm_button'] == [924, 589, 80, 45]
        # Existing ROI still there
        assert 'confirm_button' in on_disk['tasks']['login']

    def test_delete_roi_single(self, admin_client, resource_pack_with_rois):
        """DELETE /resource-packs/{pk}/rois/{task_name}/{roi_name}/ removes one ROI."""
        pack = resource_pack_with_rois
        url = f'/api/v2/resources/resource-packs/{pack.id}/rois/login/confirm_button/'
        resp = admin_client.delete(url)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.json()['deleted'] == 'confirm_button'

        # Verify file: ROI removed, other data untouched
        rois_path = os.path.join(pack.directory_path, 'config', 'rois.json')
        with open(rois_path, encoding='utf-8') as f:
            on_disk = json.load(f)
        assert 'confirm_button' not in on_disk['tasks']['login']
        # Public group untouched
        assert on_disk['public']['main_menu'] == [1720, 20, 120, 70]
        # login task still exists (just empty now)
        assert 'login' in on_disk['tasks']

    def test_delete_roi_not_found(self, admin_client, resource_pack_with_rois):
        """DELETE non-existent ROI returns 404."""
        pack = resource_pack_with_rois
        url = f'/api/v2/resources/resource-packs/{pack.id}/rois/login/nonexistent/'
        resp = admin_client.delete(url)

        assert resp.status_code == status.HTTP_404_NOT_FOUND
