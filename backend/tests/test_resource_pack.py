"""资源包管理集成测试"""
import json
import os
import tempfile

import pytest
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from resources.validators import validate_resource_pack_structure

pytestmark = pytest.mark.integration


class ResourcePackValidatorTest(TestCase):
    """资源包校验器测试"""

    def test_valid_structure(self):
        """测试有效的资源包结构"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = {
                'name': 'Test Pack',
                'version': '1.0.0',
                'target_app': 'test',
                'author': 'test',
                'gaf_version': '1.0',
                'description': 'test pack',
            }
            with open(os.path.join(tmpdir, 'manifest.json'), 'w', encoding='utf-8') as f:
                json.dump(manifest, f)
            os.makedirs(os.path.join(tmpdir, 'templates'))

            result = validate_resource_pack_structure(tmpdir)
            self.assertTrue(result['valid'])
            self.assertEqual(len(result['errors']), 0)

    def test_missing_config(self):
        """测试缺少config.json"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = validate_resource_pack_structure(tmpdir)
            self.assertFalse(result['valid'])
            self.assertTrue(len(result['errors']) > 0)

    def test_invalid_config_fields(self):
        """测试config.json缺少必需字段"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {'name': 'Test Pack'}
            with open(os.path.join(tmpdir, 'config.json'), 'w') as f:
                json.dump(config, f)

            result = validate_resource_pack_structure(tmpdir)
            self.assertFalse(result['valid'])
            self.assertTrue(len(result['errors']) > 0)

    def test_missing_templates_dir(self):
        """测试缺少templates目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = {
                'name': 'Test Pack',
                'version': '1.0.0',
                'target_app': 'test',
            }
            with open(os.path.join(tmpdir, 'config.json'), 'w') as f:
                json.dump(config, f)

            result = validate_resource_pack_structure(tmpdir)
            self.assertFalse(result['valid'])

    def test_nonexistent_directory(self):
        """测试不存在的目录路径"""
        result = validate_resource_pack_structure('/nonexistent/path')
        self.assertFalse(result['valid'])


class ResourcePackAPITest(TestCase):
    """资源包API集成测试"""

    def setUp(self):
        """Initialize API client with admin role (ResourcePack create requires 'manage')."""
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin_rp',
            password='testpass123',
            role=User.Role.ADMIN,
        )
        login_resp = self.client.post('/api/v2/accounts/auth/login/', {
            'username': 'admin_rp',
            'password': 'testpass123',
        })
        # Task 4.49 (P0-12, 2026-07-28): 修复 token 取值路径 (unified_response 信封)。
        _token = login_resp.data.get('data', {}).get('access') or login_resp.data.get('access')
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {_token}")

    def test_resource_pack_list(self):
        """测试资源包列表"""
        response = self.client.get('/api/v2/resources/resource-packs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_resource_pack_create(self):
        """测试创建资源包"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a valid resource pack structure (manifest.json + templates/).
            manifest = {
                'name': 'Test Pack',
                'version': '1.0.0',
                'target_app': 'test',
                'author': 'test',
                'gaf_version': '2.0.0',
            }
            with open(os.path.join(tmpdir, 'manifest.json'), 'w') as f:
                json.dump(manifest, f)
            os.makedirs(os.path.join(tmpdir, 'templates'))

            response = self.client.post('/api/v2/resources/resource-packs/', {
                'name': 'Test Pack',
                'version': '1.0.0',
                'directory_path': tmpdir,
                'description': 'Test resource pack',
            })
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
