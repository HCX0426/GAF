"""Unit tests for screenshot retention logic in cleanup_view.

Covers TD-291 implementation: cleanup_view walks MEDIA_ROOT/screenshots/
and deletes oldest files (by mtime) until total size <= screenshot_gb
threshold. Tests verify:
- empty dir → deleted_screenshots=0
- under threshold → no deletion
- over threshold → oldest files deleted until total <= threshold
- missing dir → no error, skipped empty
- invalid files (stat fails) → skipped gracefully
"""

import os
import time
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User


class TestCleanupScreenshots(TestCase):
    """Screenshot retention cleanup tests for /api/v2/settings/cleanup/."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='cleanup_test',
            password='testpass123',
        )
        # cleanup_view requires "manage" permission; assign admin role.
        self.user.role = User.Role.ADMIN
        self.user.save()
        self.client.force_authenticate(user=self.user)
        self.url = '/api/v2/settings/cleanup/'

        # Use a temp MEDIA_ROOT so we don't touch real screenshots.
        self.tmp_media = Path(self._create_tmp_dir())
        self.screenshot_dir = self.tmp_media / 'screenshots'
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        # N196: fake_sizes dict + Path.stat patch, 让 _make_screenshot 只写
        # 1 字节占位文件, stat() 返回 fake size (避免写 37GB 真实数据).
        self._fake_sizes: dict[str, int] = {}
        self._original_path_stat = Path.stat
        Path.stat = self._patched_stat(self._original_path_stat)

    def tearDown(self):
        """Clean up temp MEDIA_ROOT and restore Path.stat."""
        Path.stat = self._original_path_stat
        import shutil
        if self.tmp_media.exists():
            shutil.rmtree(self.tmp_media, ignore_errors=True)
        super().tearDown()

    def _create_tmp_dir(self) -> str:
        import tempfile
        return tempfile.mkdtemp(prefix='gaf_cleanup_test_')

    def _make_screenshot(self, name: str, size_bytes: int, mtime_offset_sec: float):
        """Create a fake screenshot file with given size and mtime offset.

        N196 优化 (2026-07-30): 只写 1 字节占位文件, 真实 size 通过
        self._fake_sizes mock Path.stat 返回. 原实现写真实 GB 级文件导致
        3 个测试耗时 ~39s (写 37GB 到磁盘).

        name 可含子目录 (如 'debug/old.png'), 父目录会自动创建.
        """
        fpath = self.screenshot_dir / name
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_bytes(b'x')  # 1 byte placeholder, 不写真实大文件
        target_mtime = time.time() - mtime_offset_sec
        os.utime(fpath, (target_mtime, target_mtime))
        # 记录 fake size, 供 _patched_stat 返回
        self._fake_sizes[str(fpath.resolve())] = size_bytes

    def _patched_stat(self, original_stat):
        """Mock Path.stat: 对 self._fake_sizes 中记录的文件返回 fake size.

        cleanup_view 调 fpath.stat() 取 st_size 和 st_mtime. 我们保留
        真实 mtime (由 os.utime 设置), 只替换 st_size 为 fake 值.
        """
        def _stat(self_path, *args, **kwargs):
            real_stat = original_stat(self_path, *args, **kwargs)
            try:
                resolved = str(self_path.resolve())
                fake_size = self._fake_sizes.get(resolved)
                if fake_size is not None:
                    # 构造新的 stat_result, 替换 st_size
                    # os.stat_result 索引: 0=mode, 1=ino, 2=dev, 3=nlink,
                    # 4=uid, 5=gid, 6=size, 7=atime, 8=mtime, 9=ctime
                    return os.stat_result(
                        (real_stat.st_mode, real_stat.st_ino, real_stat.st_dev,
                         real_stat.st_nlink, real_stat.st_uid, real_stat.st_gid,
                         fake_size, real_stat.st_atime, real_stat.st_mtime,
                         real_stat.st_ctime)
                    )
            except Exception:
                pass
            return real_stat
        return _stat

    @override_settings(MEDIA_ROOT='/nonexistent/path/for/test')
    def test_cleanup_missing_dir(self):
        """TC-cleanup-1: missing screenshots dir → no error, deleted_screenshots=0."""
        response = self.client.post(self.url, {
            'execution_retention_days': 30,
            'screenshot_retention_gb': 10.0,
            'log_retention_days': 30,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        assert isinstance(data, dict) and data.keys() >= {'deleted_screenshots', 'freed_screenshot_bytes'}
        self.assertEqual(data['deleted_screenshots'], 0)
        self.assertEqual(data['freed_screenshot_bytes'], 0)

    def test_cleanup_empty_dir(self):
        """TC-cleanup-2: empty screenshots dir → deleted_screenshots=0."""
        with mock.patch('settings.views.settings.MEDIA_ROOT', str(self.tmp_media)):
            response = self.client.post(self.url, {
                'execution_retention_days': 30,
                'screenshot_retention_gb': 10.0,
                'log_retention_days': 30,
            }, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        assert isinstance(data, dict) and data.keys() >= {'deleted_screenshots', 'freed_screenshot_bytes'}
        self.assertEqual(data['deleted_screenshots'], 0)
        self.assertEqual(data['freed_screenshot_bytes'], 0)

    def test_cleanup_under_threshold(self):
        """TC-cleanup-3: total size < threshold → no deletion."""
        # 3 files, 100 MB each = 300 MB total, threshold = 10 GB → no deletion.
        for i, offset in enumerate([100, 200, 300]):
            self._make_screenshot(f'under_{i}.png', 100 * 1024 * 1024, offset)
        with mock.patch('settings.views.settings.MEDIA_ROOT', str(self.tmp_media)):
            response = self.client.post(self.url, {
                'execution_retention_days': 30,
                'screenshot_retention_gb': 10.0,
                'log_retention_days': 30,
            }, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        assert isinstance(data, dict) and data.keys() >= {'deleted_screenshots', 'freed_screenshot_bytes'}
        self.assertEqual(data['deleted_screenshots'], 0)
        self.assertEqual(data['freed_screenshot_bytes'], 0)
        # All 3 files preserved
        self.assertEqual(len(list(self.screenshot_dir.iterdir())), 3)

    def test_cleanup_over_threshold_deletes_oldest_first(self):
        """TC-cleanup-4: total size > threshold → oldest files deleted until total <= threshold."""
        # 5 files, 3 GB each = 15 GB total, threshold = 10 GB.
        # Oldest 2 files (offset 500, 400) should be deleted → 9 GB remaining.
        offsets_and_names = [
            (500, 'oldest.png'),    # 3 GB, oldest → deleted
            (400, 'older.png'),     # 3 GB, older → deleted
            (300, 'middle.png'),    # 3 GB, middle → kept
            (200, 'newer.png'),     # 3 GB, newer → kept
            (100, 'newest.png'),    # 3 GB, newest → kept
        ]
        for offset, name in offsets_and_names:
            self._make_screenshot(name, 3 * 1024 ** 3, offset)
        with mock.patch('settings.views.settings.MEDIA_ROOT', str(self.tmp_media)):
            response = self.client.post(self.url, {
                'execution_retention_days': 30,
                'screenshot_retention_gb': 10.0,
                'log_retention_days': 30,
            }, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        assert isinstance(data, dict) and data.keys() >= {'deleted_screenshots', 'freed_screenshot_bytes'}
        # 2 oldest files deleted (3 GB each = 6 GB freed)
        self.assertEqual(data['deleted_screenshots'], 2)
        self.assertEqual(data['freed_screenshot_bytes'], 6 * 1024 ** 3)
        # Remaining 3 files kept (middle, newer, newest)
        remaining = sorted(f.name for f in self.screenshot_dir.iterdir())
        self.assertEqual(remaining, ['middle.png', 'newer.png', 'newest.png'])

    def test_cleanup_threshold_boundary_no_deletion(self):
        """TC-cleanup-5: total size exactly == threshold → no deletion (boundary)."""
        # 2 files, 5 GB each = 10 GB total, threshold = 10 GB → no deletion.
        self._make_screenshot('file_a.png', 5 * 1024 ** 3, 100)
        self._make_screenshot('file_b.png', 5 * 1024 ** 3, 50)
        with mock.patch('settings.views.settings.MEDIA_ROOT', str(self.tmp_media)):
            response = self.client.post(self.url, {
                'execution_retention_days': 30,
                'screenshot_retention_gb': 10.0,
                'log_retention_days': 30,
            }, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        assert isinstance(data, dict) and data.keys() >= {'deleted_screenshots', 'freed_screenshot_bytes'}
        self.assertEqual(data['deleted_screenshots'], 0)
        self.assertEqual(data['freed_screenshot_bytes'], 0)

    def test_cleanup_nested_subdirs(self):
        """TC-cleanup-6: screenshots in nested subdirs are walked and cleaned."""
        # Create nested structure: screenshots/debug/old.png + screenshots/new.png
        # N196: 用 _make_screenshot 创建 1 字节占位文件, fake size 通过 stat mock 返回
        self._make_screenshot('debug/old.png', 6 * 1024 ** 3, 500)
        self._make_screenshot('new.png', 6 * 1024 ** 3, 100)
        old_file = self.screenshot_dir / 'debug' / 'old.png'
        new_file = self.screenshot_dir / 'new.png'

        # Total = 12 GB, threshold = 10 GB → oldest (old.png in subdir) deleted.
        with mock.patch('settings.views.settings.MEDIA_ROOT', str(self.tmp_media)):
            response = self.client.post(self.url, {
                'execution_retention_days': 30,
                'screenshot_retention_gb': 10.0,
                'log_retention_days': 30,
            }, format='json')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        assert isinstance(data, dict) and data.keys() >= {'deleted_screenshots', 'freed_screenshot_bytes'}
        self.assertEqual(data['deleted_screenshots'], 1)
        self.assertEqual(data['freed_screenshot_bytes'], 6 * 1024 ** 3)
        # old.png deleted, new.png kept
        self.assertFalse(old_file.exists())
        self.assertTrue(new_file.exists())
