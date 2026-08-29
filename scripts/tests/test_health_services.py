"""scripts/services/health.py — 报错扫描单测 (spec 2026-08-29-services-management-monitor P2).

覆盖:
- _is_error_line 各类报错行/非报错行判定
- scan_log_errors 计数 + latest + files (终端捕获 + 原生日志 fallback)
- service_log_paths 优先级 (捕获文件 > 原生)
- write_health_snapshot extra 合并
"""

import sys
from datetime import datetime, timedelta
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

    @pytest.mark.parametrize('line', [
        # 连接级噪音不算服务报错 (客户端断连/取消)
        'Error: write ECONNABORTED',
        'ERROR ECONNRESET from client 127.0.0.1',
        'BrokenPipeError: [WinError 10054]',
        'WinError 10053 软件导致了连接中止',
    ])
    def test_noise_excluded(self, line):
        assert health._is_error_line(line) is False


class TestParseLineTs:
    @pytest.mark.parametrize('line, expect', [
        ('2026-08-29 10:25:16,311 [ERROR] boom', datetime(2026, 8, 29, 10, 25, 16).timestamp()),
        ('[2026-08-29 01:02:33] [ERROR] boom', datetime(2026, 8, 29, 1, 2, 33).timestamp()),
        ('10:25:16 [ERROR] boom', None),  # 无日期 → 依赖当天, 断言格式可解析即非 None
        ('INFO starting', None),
        ('Traceback (most recent call last):', None),
    ])
    def test_parse(self, line, expect):
        ts = health._parse_line_ts(line)
        if expect is None:
            if line.startswith('10:25:16'):
                assert ts is not None  # 当日时间应能解析
            else:
                assert ts is None
        else:
            assert ts == expect


class TestScanLogErrors:
    def test_window_filters_old_errors(self, isolated_debug, tmp_path):
        """时间窗口: 2 小时前的历史报错不计数, 近 1 分钟内的计入."""
        svc_dir = tmp_path / 'system' / 'services'
        svc_dir.mkdir(parents=True)
        now = datetime.now()
        old = (now - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')
        recent = (now - timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S')
        (svc_dir / 'backend.log').write_text(
            f'{old} [ERROR] legacy boom\nINFO ok\n{recent} [ERROR] fresh fail\n',
            encoding='utf-8',
        )
        result = health.scan_log_errors('backend')
        assert result['count'] == 1
        assert result['latest'] == f'{recent} [ERROR] fresh fail'

    def test_window_disabled(self, isolated_debug, tmp_path):
        """传 window_seconds=0 表示无窗口 (保留历史全量行为)."""
        svc_dir = tmp_path / 'system' / 'services'
        svc_dir.mkdir(parents=True)
        old = (datetime.now() - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')
        (svc_dir / 'backend.log').write_text(f'{old} [ERROR] legacy boom\n', encoding='utf-8')
        assert health.scan_log_errors('backend', window_seconds=0)['count'] == 1

    def test_window_applies_timestampless_traceback(self, isolated_debug, tmp_path):
        """无时间戳的 Traceback 续行沿用前一行时间戳 → 历史事件不跨窗口计入."""
        svc_dir = tmp_path / 'system' / 'services'
        svc_dir.mkdir(parents=True)
        old = (datetime.now() - timedelta(hours=2)).strftime('%Y-%m-%d %H:%M:%S')
        (svc_dir / 'backend.log').write_text(
            f'{old} [ERROR] legacy boom\n'
            'Traceback (most recent call last):\n'
            '  File "x.py", line 1\n'
            'DeserializationError: old fixture fail\n',
            encoding='utf-8',
        )
        result = health.scan_log_errors('backend')
        assert result['count'] == 0  # 首行历史 + 续行都归入 2 小时前, 窗口外

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
