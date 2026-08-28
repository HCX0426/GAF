"""ResourceMonitor 资源监控采集器单元测试"""

import importlib
import sys
from unittest.mock import MagicMock, patch

import monitor.resources
import pytest
from monitor.resources import ResourceMonitor

pytestmark = pytest.mark.e2e


@pytest.fixture
def mock_psutil():
    """注入 mock psutil 到 sys.modules 并重新加载 resources 模块"""
    mock_mod = MagicMock()
    sys.modules["psutil"] = mock_mod
    importlib.reload(monitor.resources)
    yield mock_mod
    del sys.modules["psutil"]
    importlib.reload(monitor.resources)


class TestResourceMonitorInit:
    """ResourceMonitor 初始化测试"""

    def test_init_default_values(self):
        """验证初始化后默认值正确"""
        with patch("monitor.resources._PSUTIL_AVAILABLE", False):
            monitor = ResourceMonitor()
            assert monitor._screenshot_timestamps == []
            assert monitor._fps_window_seconds == 5.0


class TestResourceMonitorWithPsutil:
    """ResourceMonitor psutil 可用场景测试"""

    def test_get_cpu_usage_returns_float(self, mock_psutil):
        """验证 get_cpu_usage 返回 float 类型"""
        # Source calls psutil.cpu_percent(interval=None) (module-level),
        # not psutil.Process().cpu_percent() (instance method).
        mock_psutil.cpu_percent.return_value = 45.2

        rm = monitor.resources.ResourceMonitor()
        result = rm.get_cpu_usage()

        assert isinstance(result, float)
        assert result == 45.2

    def test_get_memory_usage_returns_float(self, mock_psutil):
        """验证 get_memory_usage 返回 float 类型"""
        mock_mem = MagicMock()
        mock_mem.percent = 67.8
        mock_psutil.virtual_memory.return_value = mock_mem

        rm = monitor.resources.ResourceMonitor()
        result = rm.get_memory_usage()

        assert isinstance(result, float)
        assert result == 67.8

    def test_get_cpu_usage_exception_fallback(self, mock_psutil):
        """验证 get_cpu_usage 异常时返回 -1.0"""
        # Source calls psutil.cpu_percent(interval=None) (module-level),
        # not psutil.Process().cpu_percent() (instance method).
        mock_psutil.cpu_percent.side_effect = Exception("cpu_percent error")

        rm = monitor.resources.ResourceMonitor()
        result = rm.get_cpu_usage()

        assert result == -1.0

    def test_get_memory_usage_exception_fallback(self, mock_psutil):
        """验证 get_memory_usage 异常时返回 -1.0"""
        mock_psutil.virtual_memory.side_effect = Exception("virtual_memory error")

        rm = monitor.resources.ResourceMonitor()
        result = rm.get_memory_usage()

        assert result == -1.0


class TestResourceMonitorWithoutPsutil:
    """ResourceMonitor psutil 不可用场景测试（优雅降级）"""

    def test_get_cpu_usage_fallback(self):
        """验证 psutil 不可用时 get_cpu_usage 返回 -1.0"""
        with patch("monitor.resources._PSUTIL_AVAILABLE", False):
            monitor = ResourceMonitor()
            result = monitor.get_cpu_usage()
            assert result == -1.0

    def test_get_memory_usage_fallback(self):
        """验证 psutil 不可用时 get_memory_usage 返回 -1.0"""
        with patch("monitor.resources._PSUTIL_AVAILABLE", False):
            monitor = ResourceMonitor()
            result = monitor.get_memory_usage()
            assert result == -1.0

    def test_get_stats_fallback(self):
        """验证 psutil 不可用时 get_stats 返回全部 -1.0"""
        with patch("monitor.resources._PSUTIL_AVAILABLE", False):
            monitor = ResourceMonitor()
            result = monitor.get_stats()
            assert result == {"cpu": -1.0, "memory": -1.0, "fps": 0.0}


class TestScreenshotFPS:
    """ResourceMonitor 截图 FPS 计算测试"""

    def test_fps_no_screenshots_returns_zero(self):
        """验证无截图记录时 FPS 返回 0.0"""
        monitor = ResourceMonitor()
        result = monitor.get_screenshot_fps()
        assert result == 0.0

    def test_fps_single_screenshot_returns_zero(self):
        """验证仅一次截图时 FPS 返回 0.0"""
        monitor = ResourceMonitor()
        monitor.record_screenshot()
        result = monitor.get_screenshot_fps()
        assert result == 0.0

    def test_fps_multiple_screenshots(self):
        """验证多次截图时 FPS 计算正常"""
        import time

        monitor = ResourceMonitor()
        monitor._fps_window_seconds = 10.0

        base_time = 1000.0
        intervals = [0.0, 0.5, 1.0, 1.5, 2.0]
        timestamps = [base_time + i for i in intervals]

        with patch.object(time, 'monotonic', side_effect=timestamps):
            for _ in intervals:
                monitor.record_screenshot()

        last_ts = base_time + intervals[-1]
        intervals_fps_getter = [last_ts, last_ts, last_ts, last_ts, last_ts]
        with patch.object(time, 'monotonic', side_effect=intervals_fps_getter):
            fps = monitor.get_screenshot_fps()
            assert fps > 0.0
            assert fps == pytest.approx(2.0, abs=0.1)

    def test_fps_old_timestamps_expired(self):
        """验证过期时间戳被清理"""
        import time

        monitor = ResourceMonitor()
        monitor._fps_window_seconds = 1.0

        base_time = 1000.0
        monitor._screenshot_timestamps = [base_time - 10.0, base_time - 5.0]

        with patch.object(time, 'monotonic', return_value=base_time):
            fps = monitor.get_screenshot_fps()
            assert fps == 0.0
            assert len(monitor._screenshot_timestamps) == 0


class TestGetStats:
    """ResourceMonitor get_stats 集成测试"""

    def test_get_stats_returns_dict_with_required_keys(self):
        """验证 get_stats 返回包含 cpu、memory、fps 键的字典"""
        with patch("monitor.resources._PSUTIL_AVAILABLE", False):
            monitor = ResourceMonitor()
            result = monitor.get_stats()

            assert isinstance(result, dict)
            assert "cpu" in result
            assert "memory" in result
            assert "fps" in result
            assert len(result) == 3

    def test_get_stats_values_are_float(self):
        """验证 get_stats 返回值均为 float"""
        with patch("monitor.resources._PSUTIL_AVAILABLE", False):
            monitor = ResourceMonitor()
            result = monitor.get_stats()

            for value in result.values():
                assert isinstance(value, float)


class TestRecordScreenshot:
    """ResourceMonitor record_screenshot 测试"""

    def test_record_screenshot_appends_timestamp(self):
        """验证 record_screenshot 追加时间戳"""
        import time

        monitor = ResourceMonitor()
        assert len(monitor._screenshot_timestamps) == 0

        with patch.object(time, 'monotonic', return_value=1234.56):
            monitor.record_screenshot()

        assert len(monitor._screenshot_timestamps) == 1
        assert monitor._screenshot_timestamps[0] == 1234.56
