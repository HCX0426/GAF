"""AppSettings API unit tests.

R37-P3 Stage 7 Task 20b: migrated from tasks/tests/test_tasks.py — AppSettings
now lives in the settings app, so its test lives here too.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.factories import AdminUserFactory
from settings.models import AppSettings


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


class TestAppSettings(TestCase):
    """AppSettings CRUD 测试"""

    def setUp(self):
        """初始化测试数据：管理员、API 客户端"""
        self.admin = AdminUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_app_settings(self):
        """AppSettings CRUD 完整流程"""
        response = self.client.post(
            '/api/v2/settings/app-settings/',
            {
                'setting_key': 'test_key',
                'setting_value': {'value': 42},
                'category': 'test',
                'description': '测试配置项',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = _unwrap(response)
        self.assertEqual(body['setting_key'], 'test_key')
        setting_id = body['id']

        response = self.client.get(f'/api/v2/settings/app-settings/{setting_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(response)['setting_value'], {'value': 42})

        response = self.client.patch(
            f'/api/v2/settings/app-settings/{setting_id}/',
            {'setting_value': {'value': 99}},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(response)['setting_value'], {'value': 99})

        response = self.client.delete(f'/api/v2/settings/app-settings/{setting_id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(AppSettings.objects.filter(pk=setting_id).exists())
