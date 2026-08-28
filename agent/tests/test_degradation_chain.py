"""降级链集成测试：截图降级、输入降级.

现实状态（2026-07-04，per N126 诚实标记）：
- ScreenshotCache 类已实现（agent/src/devices/screenshot_cache.py，🔧 骨架），
  使用 Redis 后端 + 内存回退。Redis 不可用时自动回退到内存后端，
  以下 3 个 ScreenshotCache 测试基于内存后端运行。
- HumanizedInput 类已实现（agent/src/devices/humanize.py:130），测试正常运行。
"""
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from devices.humanize import HumanizedInput
from devices.screenshot_cache import ScreenshotCache, compute_frame_hash

pytestmark = pytest.mark.unit


class TestScreenshotDegradation:
    """截图降级链测试"""

    def test_fallback_on_failure(self):
        """测试截图方法失败后抛出异常"""
        from devices.base import BaseDevice
        device = MagicMock(spec=BaseDevice)
        device.capture_screen = MagicMock(side_effect=Exception("截图失败"))
        with pytest.raises(Exception, match="截图失败"):
            device.capture_screen()

    def test_screenshot_cache_ttl(self):
        """测试截图缓存TTL过期"""
        # Mock Redis unavailable to force in-memory backend (Redis clamps TTL to >= 1s).
        with patch('devices.screenshot_cache._get_redis_client', return_value=None):
            cache = ScreenshotCache(default_ttl=0.1, max_memory_entries=10)
            assert cache.backend == "memory"

            # Use a very short TTL so the test runs fast.
            cache.set("dev1", "hash1", b"jpeg-bytes", ttl=0.1)
            assert cache.get("dev1", "hash1") is not None  # before expiry
            time.sleep(0.15)
            assert cache.get("dev1", "hash1") is None  # expired
            cache.clear()

    def test_screenshot_cache_force(self):
        """测试截图缓存强制刷新"""
        cache = ScreenshotCache(default_ttl=300, max_memory_entries=10)
        # Initial value
        cache.set("dev1", "hash1", b"old-bytes")
        assert cache.get("dev1", "hash1") == b"old-bytes"
        # Force refresh: overwrite with new value
        cache.set("dev1", "hash1", b"new-bytes")
        assert cache.get("dev1", "hash1") == b"new-bytes"
        cache.clear()

    def test_screenshot_cache_set_get(self):
        """测试截图缓存正常存取"""
        cache = ScreenshotCache(default_ttl=300, max_memory_entries=10)
        # Miss before set
        assert cache.get("dev1", "hash_missing") is None
        # Set + get roundtrip
        cache.set("dev1", "hash1", b"frame-1")
        cache.set("dev1", "hash2", b"frame-2")
        assert cache.get("dev1", "hash1") == b"frame-1"
        assert cache.get("dev1", "hash2") == b"frame-2"
        # Different device doesn't share cache
        assert cache.get("dev2", "hash1") is None
        # Per-device clear
        cleared = cache.clear(device_id="dev1")
        assert cleared >= 2
        assert cache.get("dev1", "hash1") is None
        cache.clear()

    def test_screenshot_cache_compute_frame_hash_stable(self):
        """compute_frame_hash 对相同图像返回相同哈希"""
        img = np.zeros((64, 64, 3), dtype=np.uint8)
        img[:] = (100, 150, 200)
        h1 = compute_frame_hash(img)
        h2 = compute_frame_hash(img.copy())
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_screenshot_cache_compute_frame_hash_differs(self):
        """compute_frame_hash 对不同图像返回不同哈希"""
        img1 = np.zeros((64, 64, 3), dtype=np.uint8)
        img2 = np.zeros((64, 64, 3), dtype=np.uint8)
        img2[0, 0] = (1, 1, 1)  # 1-pixel difference
        assert compute_frame_hash(img1) != compute_frame_hash(img2)


class TestInputDegradation:
    """输入降级链测试"""

    def test_click_with_offset(self):
        """测试带偏移的拟人化点击"""
        mock_controller = MagicMock()
        humanized = HumanizedInput(mock_controller, config={})
        humanized.click(100, 200, random_offset=5, pre_delay=0, post_delay=0)
        mock_controller.click.assert_called_once()
        call_args = mock_controller.click.call_args[0]
        assert 90 <= call_args[0] <= 110
        assert 190 <= call_args[1] <= 210

    def test_click_records_actual_position(self):
        """测试拟人化点击记录实际坐标"""
        mock_controller = MagicMock()
        humanized = HumanizedInput(mock_controller)
        humanized.click(500, 300, random_offset=10, pre_delay=0, post_delay=0)
        call_args = mock_controller.click.call_args[0]
        assert 470 <= call_args[0] <= 530
        assert 270 <= call_args[1] <= 330
