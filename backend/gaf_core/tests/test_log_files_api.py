"""Tests for unified file log query API (spec 2026-08-29-logging-system-consolidation P2-1).

GET /api/v2/logs/files/?service=&lines=&filter=&date=
覆盖:
- tail 读取 (服务终端捕获文件)
- filter=error 跨文件收集报错行
- service 参数校验 (缺失 400 / 非法 400)
- 无文件降级 (200 + 空 lines)
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User

_DEBUG_ROOT = Path(__file__).resolve().parents[3] / "debug"


class FileLogApiBase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='filelog_test', password='testpass123')
        self.client.force_authenticate(user=self.user)
        self._tmp = tempfile.mkdtemp(prefix='gaf-filelog-test-')
        self.debug_root = Path(self._tmp)
        root_patch = patch('gaf_core.log_files._DEBUG_ROOT', self.debug_root)
        svc_patch = patch('gaf_core.log_files._SERVICE_LOG_DIR', self.debug_root / 'system' / 'services')
        self._patches = [root_patch, svc_patch]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def _write_captured(self, name, lines):
        d = self.debug_root / 'system' / 'services'
        d.mkdir(parents=True, exist_ok=True)
        (d / f'{name}.log').write_text('\n'.join(lines) + '\n', encoding='utf-8')


class TestFileLogQueryAPI(FileLogApiBase):
    def test_tail_returns_lines(self):
        self._write_captured('backend', ['INFO start', 'ERROR boom', 'INFO done'])
        res = self.client.get('/api/v2/logs/files/', {'service': 'backend', 'lines': '2'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data['data'] if isinstance(res.data, dict) and 'data' in res.data else res.data
        self.assertEqual(data['service'], 'backend')
        self.assertEqual(data['lines'], ['ERROR boom', 'INFO done'])

    def test_filter_error_cross_files(self):
        """主捕获文件无 ERROR 时, 原生日志 (django.log) 的历史错误被收集。"""
        self._write_captured('backend', ['INFO clean start'])
        day = self.debug_root / '20260829' / 'backend' / 'system' / '00'
        day.mkdir(parents=True)
        (day / 'django.log').write_text(
            'INFO ok\n2026-08-29 01:00:00 [ERROR] legacy fail\n', encoding='utf-8')
        res = self.client.get('/api/v2/logs/files/', {'service': 'backend', 'filter': 'error'})
        data = res.data['data'] if isinstance(res.data, dict) and 'data' in res.data else res.data
        self.assertEqual(data['lines'], ['2026-08-29 01:00:00 [ERROR] legacy fail'])
        self.assertEqual(data['error_count'], 1)

    def test_missing_service_400(self):
        res = self.client.get('/api/v2/logs/files/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_service_400(self):
        res = self.client.get('/api/v2/logs/files/', {'service': 'nonsense'})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_files_returns_empty(self):
        res = self.client.get('/api/v2/logs/files/', {'service': 'redis'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data['data'] if isinstance(res.data, dict) and 'data' in res.data else res.data
        self.assertEqual(data['lines'], [])
        self.assertIsNone(data['path'])

    def test_lines_capped_at_2000(self):
        lines = [f'line {i}' for i in range(2500)]
        self._write_captured('frontend', lines)
        res = self.client.get('/api/v2/logs/files/', {'service': 'frontend', 'lines': '5000'})
        data = res.data['data'] if isinstance(res.data, dict) and 'data' in res.data else res.data
        self.assertLessEqual(len(data['lines']), 2000)

    def test_requires_auth(self):
        anon = APIClient()
        res = anon.get('/api/v2/logs/files/', {'service': 'backend'})
        self.assertIn(res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
