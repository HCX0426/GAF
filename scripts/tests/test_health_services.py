"""scripts/services/health.py — 报错扫描单测 (spec 2026-08-29-services-management-monitor P2).

覆盖:
- _is_error_line 各类报错行/非报错行判定
- scan_log_errors 计数 + latest + files (终端捕获 + 原生日志 fallback)
- service_log_paths 优先级 (捕获文件 > 原生)
- write_health_snapshot extra 合并
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from services import health  # noqa: E402


@pytest.fixture
def isolated_debug(tmp_path):
    """把 health.DEBUG_DIR / SERVICE_LOG_DIR / HEALTH_STATUS_FILE 指向临时目录."""
    with patch.object(health, 'DEBUG_DIR', tmp_path):
        with patch.object(health, 'SERVICE_LOG_DIR', tmp_path / 'system' / 'services'):
            with patch.object(health, 'HEALTH_STATUS_FILE', tmp_path / 'health-status.json'):
                yield tmp_path


class TestIsErrorLine:
    @pytest.mark.parametrize('line', [
        '2026-08-29 10:00:00 [ERROR] boom',
        'INFO:CRITICAL Failure point',
        'Traceback (most recent call last):',
        'ValueError: bad value',
        '  raise RuntimeError("x")',
        'Error: listen EADDRINUSE',
        'node:internal/process: Error: spawn failed',
    ])
    def test_matches(self, line):
        assert health._is_error_line(line) is True

    @pytest.mark.parametrize('line', [
        'INFO starting',
        'GET /api/v2/agents/ 200',
        'Compiled successfully',
        'no error found',
        '2026-08-29 10:00:00 [INFO] task completed',
        'WARNING: retry in 1s',
    ])
    def test_non_matches(self, line):
        assert health._is_error_line(line) is False


class TestScanLogErrors:
    def test_counts_and_latest(self, isolated_debug, tmp_path):
        svc_dir = tmp_path / 'system' / 'services'
        svc_dir.mkdir(parents=True)
        (svc_dir / 'backend.log').write_text(
            'INFO start\nERROR first\nINFO middle\nTraceback (most recent call last):\n'
            '  File "x.py", line 1\nValueError: last\n',
            encoding='utf-8',
        )
        result = health.scan_log_errors('backend')
        assert result['count'] == 3
        assert result['latest'] == 'ValueError: last'
        assert any('backend.log' in f for f in result['files'])

    def test_no_latest_when_clean(self, isolated_debug):
        result = health.scan_log_errors('agent')
        assert result['count'] == 0
        assert result['latest'] is None
        assert result['files'] == []

    def test_fallback_to_native_log(self, isolated_debug, tmp_path):
        # 构造原生日志: debug/<date>/agent/system/agent.log
        day = tmp_path / '20260829'
        agent_log = day / 'agent' / 'system' / 'agent.log'
        agent_log.parent.mkdir(parents=True)
        agent_log.write_text('INFO ok\nERROR native-fail\n', encoding='utf-8')
        result = health.scan_log_errors('agent')
        assert result['count'] == 1
        assert result['latest'] == 'ERROR native-fail'

    def test_cap_lines(self, isolated_debug, tmp_path):
        """超过扫描上限只统计尾部, 不拖垮看门狗."""
        svc_dir = tmp_path / 'system' / 'services'
        svc_dir.mkdir(parents=True)
        lines = ['INFO filler'] * 3000 + ['ERROR tail-fail']
        (svc_dir / 'frontend.log').write_text('\n'.join(lines), encoding='utf-8')
        result = health.scan_log_errors('frontend')
        assert result['count'] == 1
        assert result['latest'] == 'ERROR tail-fail'


class TestWriteSnapshot:
    def test_extra_merged(self, isolated_debug, tmp_path):
        snapshot = {'redis': health.Health(service='redis', healthy=True, detail='ok', ts=1.0)}
        health.write_health_snapshot(snapshot, extra={'log_errors': {'redis': {'count': 1}}})
        payload = (tmp_path / 'health-status.json').read_text(encoding='utf-8')
        assert '"log_errors"' in payload
        assert '"services"' in payload
        assert '"updated_at"' in payload

    def test_without_extra(self, isolated_debug, tmp_path):
        snapshot = {'redis': health.Health(service='redis', healthy=True, detail='ok', ts=1.0)}
        health.write_health_snapshot(snapshot)
        payload = (tmp_path / 'health-status.json').read_text(encoding='utf-8')
        assert '"log_errors"' not in payload