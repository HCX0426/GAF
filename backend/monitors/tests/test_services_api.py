"""Monitors app tests — 服务管理 API (spec 2026-08-29-services-management-monitor P3).

覆盖:
- GET /api/v2/monitors/services/  (快照读取 + daemon 状态 + 服务列表 5 项)
- GET /api/v2/monitors/services/logs/ (tail + filter=error)
- 参数校验 (service 缺失 → 400)
- 快照/日志缺失时降级 (不抛 500)
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

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


class ServiceApiBase(TestCase):
    """公共 fixture: 认证 client + 隔离的 debug 目录。"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='svc_test', password='testpass123')
        self.client.force_authenticate(user=self.user)
        # 隔离 debug 目录, 不触碰真实 debug/
        self._tmp = tempfile.mkdtemp(prefix='gaf-svc-test-')
        self.debug_root = Path(self._tmp)
        # 文件定位逻辑已委托 gaf_core.log_files (spec P2-1), patch 公共模块根路径
        root_patch = patch('gaf_core.log_files._DEBUG_ROOT', self.debug_root)
        svc_patch = patch('gaf_core.log_files._SERVICE_LOG_DIR', self.debug_root / 'system' / 'services')
        mon_root_patch = patch('monitors.views._DEBUG_ROOT', self.debug_root)
        pid_patch = patch('monitors.views._DAEMON_PID_FILE', self.debug_root / 'gaf_daemon.pid')
        self._patches = [root_patch, svc_patch, mon_root_patch, pid_patch]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)

    def _write_snapshot(self, services=None, processes=None, log_errors=None, updated='2026-08-29T10:00:00+0800'):
        """写一个健康快照到隔离目录。"""
        payload = {
            'updated_at': updated,
            'services': services or {},
            'processes': processes or {},
            'log_errors': log_errors or {},
        }
        (self.debug_root / 'health-status.json').write_text(
            json.dumps(payload, ensure_ascii=False), encoding='utf-8',
        )

    def _write_service_log(self, name, lines):
        """写服务终端日志 (模拟 daemon 捕获)."""
        d = self.debug_root / 'system' / 'services'
        d.mkdir(parents=True, exist_ok=True)
        (d / f'{name}.log').write_text('\n'.join(lines) + '\n', encoding='utf-8')


class TestServicesListAPI(ServiceApiBase):
    """GET /api/v2/monitors/services/"""

    def test_returns_200_with_empty_state(self):
        """无快照时返回 200 + daemon 未运行 + services 5 项占位。"""
        res = self.client.get('/api/v2/monitors/services/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap(res)
        self.assertFalse(body['daemon']['running'])
        self.assertEqual(len(body['services']), 5)
        names = [s['name'] for s in body['services']]
        self.assertEqual(names, ['redis', 'backend', 'agent', 'frontend', 'daemon'])

    def test_returns_snapshot_fields_when_present(self):
        """快照存在时返回 healthy/detail/process/log_errors 数据。"""
        self._write_snapshot(
            services={'backend': {'service': 'backend', 'healthy': True, 'detail': 'healthz pass', 'ts': 1.0}},
            processes={'backend': {'running': True, 'pid': 123, 'port': 8000, 'restart_count': 1}},
            log_errors={'backend': {'count': 2, 'latest': 'ERROR boom'}},
        )
        (self.debug_root / 'gaf_daemon.pid').write_text('456', encoding='utf-8')
        res = self.client.get('/api/v2/monitors/services/')
        body = _unwrap(res)
        self.assertTrue(body['daemon']['running'])
        self.assertEqual(body['daemon']['pid'], 456)
        backend = [s for s in body['services'] if s['name'] == 'backend'][0]
        self.assertTrue(backend['healthy'])
        self.assertEqual(backend['detail'], 'healthz pass')
        self.assertTrue(backend['running'])
        self.assertEqual(backend['pid'], 123)
        self.assertEqual(backend['port'], 8000)
        self.assertEqual(backend['restart_count'], 1)
        self.assertEqual(backend['error_count'], 2)
        self.assertEqual(backend['latest_error'], 'ERROR boom')

    def test_corrupted_snapshot_degrades(self):
        """快照损坏时降级为空列表, 不抛 500。"""
        (self.debug_root / 'health-status.json').write_text('{not-json', encoding='utf-8')
        res = self.client.get('/api/v2/monitors/services/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_unwrap(res)['services']), 5)

    def test_requires_auth(self):
        """未认证 → 401/403。"""
        anon = APIClient()
        res = anon.get('/api/v2/monitors/services/')
        self.assertIn(res.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class TestServiceLogsAPI(ServiceApiBase):
    """GET /api/v2/monitors/services/logs/"""

    def test_tail_returns_lines(self):
        self._write_service_log('backend', [
            'INFO starting',
            'ERROR boom',
            'INFO done',
        ])
        res = self.client.get('/api/v2/monitors/services/logs/?service=backend&lines=2')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap(res)
        self.assertEqual(body['service'], 'backend')
        self.assertEqual(body['lines'], ['ERROR boom', 'INFO done'])

    def test_filter_error_only(self):
        self._write_service_log('backend', [
            'INFO starting',
            'ERROR boom',
            'INFO done',
            'Traceback (most recent call last):',
            'ValueError: bad',
        ])
        res = self.client.get('/api/v2/monitors/services/logs/?service=backend&filter=error')
        body = _unwrap(res)
        self.assertEqual(body['lines'], ['ERROR boom', 'Traceback (most recent call last):', 'ValueError: bad'])

    def test_filter_error_cross_files(self):
        """主捕获文件无 ERROR 时, fallback 原生日志 (django.log 等) 的历史错误也能被收集."""
        self._write_service_log('backend', ['INFO clean start', 'INFO clean go'])
        day = self.debug_root / '20260829' / 'backend' / 'system' / '00'
        day.mkdir(parents=True)
        (day / 'django.log').write_text(
            'INFO ok\n2026-08-29 01:00:00 [ERROR] legacy failure\n', encoding='utf-8')
        res = self.client.get('/api/v2/monitors/services/logs/?service=backend&filter=error')
        body = _unwrap(res)
        self.assertEqual(body['lines'], ['2026-08-29 01:00:00 [ERROR] legacy failure'])

    def test_missing_service_param_400(self):
        res = self.client.get('/api/v2/monitors/services/logs/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_log_files_returns_empty(self):
        res = self.client.get('/api/v2/monitors/services/logs/?service=redis')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap(res)
        self.assertEqual(body['lines'], [])
        self.assertIsNone(body['path'])

    def test_lines_capped_at_2000(self):
        lines = [f'line {i}' for i in range(2500)]
        self._write_service_log('frontend', lines)
        res = self.client.get('/api/v2/monitors/services/logs/?service=frontend&lines=5000')
        body = _unwrap(res)
        self.assertLessEqual(len(body['lines']), 2000)
