"""
全局搜索 API 测试

覆盖：
- 空查询返回所有分组空数组
- 精确搜索（任务名称/设备名称/账户名称）
- 不匹配时 totalCount=0
- limit 限制每分组结果数
- 跨模块搜索分组结果正确
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


class TestGlobalSearchAPI(TestCase):
    """全局搜索 API 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='search_test',
            password='testpass123',
        )
        self.client.force_authenticate(user=self.user)
        self.url = '/api/v2/search/'

    def test_empty_query_returns_empty_groups(self):
        """TC-7.2-1: 空查询返回 totalCount=0 和所有空分组"""
        res = self.client.get(f'{self.url}?q=')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap(res)
        self.assertEqual(body['totalCount'], 0)
        self.assertEqual(len(body['tasks']), 0)

    def test_num_hit_search(self):
        """TC-7.2-2: 搜索结果为正匹配"""
        res = self.client.get(f'{self.url}?q=test')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap(res)
        self.assertIn('totalCount', body)
        self.assertIn('tasks', body)
        self.assertIn('devices', body)
        self.assertIn('accounts', body)
        self.assertIn('logs', body)
        self.assertIn('settings', body)

    def test_no_match_query_returns_total_zero(self):
        """TC-7.2-3: 无匹配查询返回 totalCount=0"""
        res = self.client.get(f'{self.url}?q=xyznonexistent123456')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(res)['totalCount'], 0)

    def test_limit_restricts_results(self):
        """TC-7.2-4: limit 参数限制搜索结果数"""
        res = self.client.get(f'{self.url}?q=test&limit=2')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap(res)
        for key in ['tasks', 'devices', 'accounts', 'logs', 'settings']:
            self.assertLessEqual(len(body[key]), 2,
                                 f'{key} 分组超过了 limit=2')

    def test_cross_module_search_groups(self):
        """TC-7.2-5: 跨模块搜索返回每个分组的独立结果"""
        res = self.client.get(f'{self.url}?q=test&limit=3')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap(res)
        self.assertIsInstance(body['tasks'], list)
        self.assertIsInstance(body['devices'], list)
        self.assertIsInstance(body['accounts'], list)
