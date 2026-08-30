"""Device API 单元测试 — 覆盖设备 CRUD、发现、分组管理"""

from unittest.mock import patch

import pytest
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.factories import AdminUserFactory, OperatorUserFactory
from accounts.models import User
from workers.factories import DeviceFactory, DeviceGroupFactory, WorkerFactory
from workers.models import Device, DeviceGroup

pytestmark = pytest.mark.e2e


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _get_results(resp):
    """适配信封 + 分页。先解信封, 再取分页 results 字段。"""
    data = _unwrap(resp)
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    return data


class TestCreateDevice(TestCase):
    """Device 创建测试"""

    def setUp(self):
        """初始化测试数据：操作员用户、API 客户端"""
        self.operator = OperatorUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    def test_create_device_windows(self):
        """创建 Windows 设备"""
        response = self.client.post(
            '/api/v2/devices/',
            {
                'name': 'Windows-Gaming-PC',
                'device_type': 'windows',
                'status': 'online',
                'resolution_width': 1920,
                'resolution_height': 1080,
                'screenshot_fps': 30.0,
                'extra_info': {'window_title': 'GameWindow'},
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(response)['name'], 'Windows-Gaming-PC')
        self.assertEqual(_unwrap(response)['device_type'], 'windows')
        self.assertEqual(_unwrap(response)['status'], 'online')
        device = Device.objects.get(name='Windows-Gaming-PC')
        self.assertEqual(device.resolution_width, 1920)

    def test_create_device_emulator(self):
        """创建模拟器设备"""
        response = self.client.post(
            '/api/v2/devices/',
            {
                'name': 'Android-Emulator-1',
                'device_type': 'emulator',
                'status': 'offline',
                'extra_info': {'emulator_type': 'mumu', 'port': 7555},
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(response)['device_type'], 'emulator')
        self.assertEqual(_unwrap(response)['extra_info']['port'], 7555)

    def test_create_device_with_agent(self):
        """创建关联 Agent 的设备"""
        agent = WorkerFactory()
        response = self.client.post(
            '/api/v2/devices/',
            {
                'name': 'ADB-Device-1',
                'device_type': 'emulator',
                'status': 'online',
                'agent': agent.pk,
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(response)['agent'], agent.pk)
        self.assertIsNotNone(_unwrap(response)['agent_info'])


class TestDeviceListFilter(TestCase):
    """Device 创建测试"""

    def setUp(self):
        """初始化测试数据：操作员用户、API 客户端"""
        self.operator = OperatorUserFactory()
        self.agent = WorkerFactory()
        DeviceFactory(name='Win-PC', device_type='windows', status='online', agent=self.agent)
        DeviceFactory(name='ADB-Phone', device_type='emulator', status='offline')
        DeviceFactory(name='Emu-N1', device_type='emulator', status='busy')
        DeviceFactory(name='Win-Laptop', device_type='windows', status='error')
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    def test_list_all_devices(self):
        """获取全部设备列表"""
        response = self.client.get('/api/v2/devices/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _get_results(response)
        self.assertGreaterEqual(len(results), 4)

    def test_filter_by_type(self):
        """创建模拟器设备"""
        response = self.client.get('/api/v2/devices/?device_type=windows')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _get_results(response)
        self.assertGreater(len(results), 0)
        for item in results:
            self.assertEqual(item['device_type'], 'windows')

    def test_filter_by_status(self):
        """创建模拟器设备"""
        response = self.client.get('/api/v2/devices/?status=online')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _get_results(response)
        self.assertGreater(len(results), 0)
        for item in results:
            self.assertEqual(item['status'], 'online')

    def test_filter_by_agent(self):
        """创建关联 Agent 的设备"""
        response = self.client.get(f'/api/v2/devices/?agent={self.agent.pk}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _get_results(response)
        self.assertGreater(len(results), 0)

    def test_search_by_name(self):
        """创建模拟器设备"""
        response = self.client.get('/api/v2/devices/?search=Win')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _get_results(response)
        self.assertGreater(len(results), 0)


class TestDeviceUpdateDelete(TestCase):
    """Device 创建测试"""

    def setUp(self):
        """初始化测试数据：操作员用户、API 客户端"""
        self.operator = OperatorUserFactory()
        self.device = DeviceFactory(name='Test-Device', device_type='windows', status='offline')
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    def test_update_device_status(self):
        """创建模拟器设备"""
        response = self.client.patch(
            f'/api/v2/devices/{self.device.pk}/',
            {'status': 'online'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.device.refresh_from_db()
        self.assertEqual(self.device.status, Device.Status.ONLINE)

    def test_device_detail_with_agent_info(self):
        """设备详情包含 agent_info"""
        agent = WorkerFactory(agent_id='detail-agent', hostname='detail-host')
        self.device.agent = agent
        self.device.save()
        response = self.client.get(f'/api/v2/devices/{self.device.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(_unwrap(response)['agent_info'])
        self.assertEqual(_unwrap(response)['agent_info']['agent_id'], 'detail-agent')

    def test_delete_device(self):
        """删除设备"""
        response = self.client.delete(f'/api/v2/devices/{self.device.pk}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Device.objects.filter(name='Test-Device').exists())


class TestDeviceGroup(TestCase):
    """DeviceGroup 分组管理测试"""

    def setUp(self):
        """初始化测试数据：操作员用户、API 客户端"""
        self.operator = OperatorUserFactory()
        self.device1 = DeviceFactory(name='Group-Dev-1', device_type='windows', status='online')
        self.device2 = DeviceFactory(name='Group-Dev-2', device_type='emulator', status='offline')
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    def test_create_group(self):
        """创建设备分组"""
        response = self.client.post(
            '/api/v2/device-groups/',
            {
                'name': 'Windows设备组',
                'devices': [self.device1.pk],
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(response)['name'], 'Windows设备组')
        self.assertEqual(_unwrap(response)['device_count'], 1)

    def test_list_groups(self):
        """获取设备分组列表"""
        DeviceGroupFactory(name='G1', user=self.operator)
        DeviceGroupFactory(name='G2', user=self.operator)
        response = self.client.get('/api/v2/device-groups/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _get_results(response)
        self.assertGreaterEqual(len(results), 2)

    def test_update_group_add_devices(self):
        """创建模拟器设备"""
        group = DeviceGroupFactory(name='Test-Group', user=self.operator)
        response = self.client.patch(
            f'/api/v2/device-groups/{group.pk}/',
            {'devices': [self.device1.pk, self.device2.pk]},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(response)['device_count'], 2)

    def test_delete_group(self):
        """删除设备分组"""
        group = DeviceGroupFactory(name='To-Delete', user=self.operator)
        response = self.client.delete(f'/api/v2/device-groups/{group.pk}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(DeviceGroup.objects.filter(name='To-Delete').exists())

    def test_group_devices_detail(self):
        """分组详情包含设备列表"""
        group = DeviceGroupFactory(name='Detail-Group', user=self.operator)
        group.devices.add(self.device1)
        response = self.client.get(f'/api/v2/device-groups/{group.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_unwrap(response)['devices_detail']), 1)
        self.assertEqual(_unwrap(response)['devices_detail'][0]['name'], 'Group-Dev-1')


class TestDeviceScan(TestCase):
    """设备扫描 API 测试 (BE-3.01) — 目标 2 个用例"""

    pytestmark = pytest.mark.e2e  # 需要真实 ADB 连接

    def setUp(self):
        """初始化：管理员用户、在线 Agent、API 客户端"""
        self.admin = AdminUserFactory()
        self.agent = WorkerFactory(agent_id='scan-agent', hostname='scan-host')
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_scan_android(self):
        """扫描 Android 模拟器 → 返回 android 列表"""
        response = self.client.get('/api/v2/devices/scan/?type=android')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('android', _unwrap(response))
        self.assertIsInstance(_unwrap(response)['android'], list)

    def test_scan_windows(self):
        """扫描 Windows 窗口 → 返回 windows 列表"""
        response = self.client.get('/api/v2/devices/scan/?type=windows')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('windows', _unwrap(response))
        self.assertIsInstance(_unwrap(response)['windows'], list)


class TestDeviceRegister(TestCase):
    """设备注册 + 测试截图 API 测试 (BE-3.02/3.03) — 目标 2 个用例"""

    def setUp(self):
        """初始化测试数据：操作员用户、API 客户端"""
        self.operator = OperatorUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    def test_register_device_android(self):
        """注册 Android 设备 ??201 + UUID"""
        response = self.client.post(
            '/api/v2/devices/register/',
            {
                'name': '注册测试-雷电',
                'agent_type': 'android',
                'adb_serial': 'emulator-5556',
                'emulator': 'ldplayer',
                'resolution': {'width': 1280, 'height': 720},
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(response)['name'], '注册测试-雷电')
        self.assertEqual(_unwrap(response)['adb_serial'], 'emulator-5556')
        self.assertEqual(_unwrap(response)['emulator'], 'ldplayer')

    def test_test_screenshot(self):
        """按设备类型筛选 — 验证接口可用"""
        agent = WorkerFactory(agent_id='test-screenshot-agent', hostname='test-host')
        device = DeviceFactory(
            name='截图测试设备',
            device_type='emulator',
            status='online',
            resolution_width=1920,
            resolution_height=1080,
            agent=agent,
        )
        response = self.client.get(f'/api/v2/devices/{device.pk}/test-screenshot/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('success', _unwrap(response))
        self.assertIn('latency_ms', _unwrap(response))
        self.assertIn('resolution', _unwrap(response))
        self.assertIn('screenshot_method', _unwrap(response))
        self.assertIn('available_methods', _unwrap(response))

    @patch('device_bridge.platforms.windows._adb_screenshot.capture')
    @patch('device_bridge.platforms.windows._adb_screenshot.get_available_methods')
    @patch('device_bridge.discovery.emulator._find_adb_executable')
    def test_test_screenshot_with_method_param(
        self, mock_find_adb, mock_get_methods, mock_capture,
    ):
        """测试截图 → 指定 method 参数时应透传给底层并返回该方法"""
        import cv2
        import numpy as np

        mock_find_adb.return_value = 'adb.exe'
        mock_get_methods.return_value = ['ld_opengl', 'screencap', 'screencap_png']

        # Create a valid JPEG byte stream for ld_opengl fallback detection.
        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        _, jpeg_buf = cv2.imencode('.jpg', dummy_img)
        mock_capture.return_value = (jpeg_buf.tobytes(), 'screencap')

        agent = WorkerFactory(agent_id='test-screenshot-method-agent', hostname='test-host')
        device = DeviceFactory(
            name='截图方式测试设备',
            device_type='emulator',
            status='online',
            adb_serial='127.0.0.1:5555',
            emulator='ldplayer',
            resolution_width=1920,
            resolution_height=1080,
            agent=agent,
        )
        response = self.client.get(
            f'/api/v2/devices/{device.pk}/test-screenshot/',
            {'method': 'screencap'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(_unwrap(response)['success'])
        self.assertEqual(_unwrap(response)['screenshot_method'], 'screencap')
        self.assertIn('available_methods', _unwrap(response))
        # Verify at least one capture call was made with the forced method.
        forced_calls = [
            call for call in mock_capture.call_args_list
            if call.kwargs.get('method') == 'screencap'
        ]
        self.assertTrue(forced_calls, 'adb_capture was not called with method=screencap')


class TestDeviceLock(TestCase):
    """设备锁定/解锁 API 测试 (BE-3.04) — 目标 2 个用例"""

    def setUp(self):
        """初始化：两个操作员、Admin、设备、API 客户端"""
        self.user_a = User.objects.create_user(
            username='lock_user_a',
            password='apass123',
            role=User.Role.OPERATOR,
        )
        self.user_b = User.objects.create_user(
            username='lock_user_b',
            password='bpass123',
            role=User.Role.OPERATOR,
        )
        self.admin = User.objects.create_user(
            username='lock_admin',
            password='adminpass123',
            role=User.Role.ADMIN,
        )
        self.device = DeviceFactory(
            name='锁定测试设备',
            device_type='windows',
            status='online',
        )

    def test_lock_device_conflict(self):
        """用户 A 锁定 → 成功；用户 B 尝试锁定 → 403"""
        client_a = APIClient()
        client_a.force_authenticate(user=self.user_a)
        response = client_a.post(f'/api/v2/devices/{self.device.pk}/lock/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(response)['status'], 'locked')

        client_b = APIClient()
        client_b.force_authenticate(user=self.user_b)
        response = client_b.post(f'/api/v2/devices/{self.device.pk}/lock/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_force_unlock(self):
        """Admin 强制解锁 → 成功"""
        client_a = APIClient()
        client_a.force_authenticate(user=self.user_a)
        response = client_a.post(f'/api/v2/devices/{self.device.pk}/lock/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        admin_client = APIClient()
        admin_client.force_authenticate(user=self.admin)
        response = admin_client.post(f'/api/v2/devices/{self.device.pk}/unlock/?force=true')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(response)['status'], 'unlocked')

        self.device.refresh_from_db()
        self.assertIsNone(self.device.locked_by)


class TestDeviceCompatibility(TestCase):
    """分辨率兼容检查 API 测试 (BE-3.07) — 目标 2 个用例"""

    def setUp(self):
        """初始化测试数据：操作员用户、API 客户端"""
        self.operator = OperatorUserFactory()
        self.device = DeviceFactory(
            name='兼容测试设备',
            device_type='windows',
            status='online',
            resolution_width=1920,
            resolution_height=1080,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    def test_compatibility_same_resolution(self):
        """相同分辨率 → is_compatible=true"""
        response = self.client.post(
            '/api/v2/devices/check-compatibility/',
            {
                'device_id': self.device.pk,
                'resource_pack_id': 'pack-same-res',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('is_compatible', _unwrap(response))
        self.assertIn('scale_suggestion', _unwrap(response))
        self.assertIsInstance(_unwrap(response)['is_compatible'], bool)

    def test_compatibility_different_resolution(self):
        """创建模拟器设备"""
        small_device = DeviceFactory(
            name='小分辨率设备',
            device_type='emulator',
            status='online',
            resolution_width=1280,
            resolution_height=720,
        )
        response = self.client.post(
            '/api/v2/devices/check-compatibility/',
            {
                'device_id': small_device.pk,
                'resource_pack_id': 'pack-big-res',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('is_compatible', _unwrap(response))
        self.assertIn('scale_suggestion', _unwrap(response))
        self.assertIn('device_resolution', _unwrap(response))
        self.assertIn('pack_resolution', _unwrap(response))


class TestDeviceControlMode(TestCase):
    """Device control_mode abstraction tests (TD-015)."""

    def setUp(self):
        """Init operator user and API client."""
        self.operator = OperatorUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    def test_create_device_defaults_to_auto(self):
        """v3 §2.8.1: new devices default to 'auto' control mode (inherit GameProfile)."""
        response = self.client.post(
            '/api/v2/devices/',
            {
                'name': 'ControlMode-Default-Device',
                'device_type': 'windows',
                'status': 'online',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(response)['control_mode'], 'auto')
        # 'auto' keeps screenshot/input as 'auto' for runtime GameProfile inheritance
        self.assertEqual(_unwrap(response)['screenshot_method'], 'auto')
        self.assertEqual(_unwrap(response)['input_method'], 'auto')
        # resolved_methods should reflect no-profile state (own values)
        self.assertEqual(_unwrap(response)['resolved_methods']['control_mode'], 'auto')

    def test_resolve_device_methods_inherits_from_game_profile(self):
        """v3 §2.8.1: 'auto' device fields inherit from GameProfile defaults."""
        from gamestate.models import GameProfile

        profile = GameProfile.objects.create(
            game_name='ResolveTest',
            default_screenshot_method='printwindow',
            default_input_method='SendInput',
            default_control_mode='pseudo_background',
        )
        device = Device.objects.create(
            name='ResolveDevice',
            device_type='windows',
            game_profile=profile,
            # control_mode/screenshot_method/input_method all default to 'auto'
        )
        from workers.models import resolve_device_methods
        resolved = resolve_device_methods(device)
        self.assertEqual(resolved['screenshot_method'], 'printwindow')
        self.assertEqual(resolved['input_method'], 'SendInput')
        self.assertEqual(resolved['control_mode'], 'pseudo_background')

    def test_resolve_device_methods_concrete_overrides(self):
        """v3 §2.8.1: concrete device values override GameProfile defaults."""
        from gamestate.models import GameProfile

        profile = GameProfile.objects.create(
            game_name='OverrideTest',
            default_screenshot_method='printwindow',
            default_input_method='SendInput',
            default_control_mode='pseudo_background',
        )
        device = Device.objects.create(
            name='OverrideDevice',
            device_type='windows',
            game_profile=profile,
            control_mode='foreground',  # concrete override
            screenshot_method='gdi',     # concrete override
            input_method='PostMessage',  # concrete override
        )
        from workers.models import resolve_device_methods
        resolved = resolve_device_methods(device)
        self.assertEqual(resolved['screenshot_method'], 'gdi')
        self.assertEqual(resolved['input_method'], 'PostMessage')
        self.assertEqual(resolved['control_mode'], 'foreground')


class DeviceBindingAPITest(TestCase):
    """Tests for PATCH /api/v2/devices/{id}/bind-game-account/ and
    bind-game-profile/ (spec v3 §2.7.2 ??window-centric binding APIs).
    """

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.device = DeviceFactory()

    def test_bind_game_account_success(self):
        from accounts.factories import GameAccountFactory

        account = GameAccountFactory()
        url = f'/api/v2/devices/{self.device.id}/bind-game-account/'
        r = self.client.patch(url, {'game_account_id': account.id}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(r)['game_account_id'], account.id)
        self.assertEqual(_unwrap(r)['game_account_username'], account.username)
        self.device.refresh_from_db()
        self.assertEqual(self.device.game_account_id, account.id)

    def test_bind_game_account_clear(self):
        """Passing game_account_id: null clears the binding."""
        from accounts.factories import GameAccountFactory

        account = GameAccountFactory()
        self.device.game_account = account
        self.device.save(update_fields=['game_account'])

        url = f'/api/v2/devices/{self.device.id}/bind-game-account/'
        r = self.client.patch(url, {'game_account_id': None}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.device.refresh_from_db()
        self.assertIsNone(self.device.game_account_id)

    def test_bind_game_account_not_found(self):
        url = f'/api/v2/devices/{self.device.id}/bind-game-account/'
        r = self.client.patch(url, {'game_account_id': 999999}, format='json')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_bind_game_profile_success(self):
        from gamestate.models import GameProfile

        profile = GameProfile.objects.create(game_name='BD2-bind-test')
        url = f'/api/v2/devices/{self.device.id}/bind-game-profile/'
        r = self.client.patch(url, {'game_profile_id': profile.id}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(r)['game_profile_id'], profile.id)
        self.assertEqual(_unwrap(r)['game_name'], 'BD2-bind-test')
        self.device.refresh_from_db()
        self.assertEqual(self.device.game_profile_id, profile.id)

    def test_bind_game_profile_clear(self):
        """Passing game_profile_id: null clears the binding."""
        from gamestate.models import GameProfile

        profile = GameProfile.objects.create(game_name='BD2-clear-test')
        self.device.game_profile = profile
        self.device.save(update_fields=['game_profile'])

        url = f'/api/v2/devices/{self.device.id}/bind-game-profile/'
        r = self.client.patch(url, {'game_profile_id': None}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.device.refresh_from_db()
        self.assertIsNone(self.device.game_profile_id)

    def test_bind_game_profile_not_found(self):
        url = f'/api/v2/devices/{self.device.id}/bind-game-profile/'
        r = self.client.patch(url, {'game_profile_id': 999999}, format='json')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class TestDeviceControlModeContinued(TestCase):
    """Device control_mode tests continued (was TestDeviceControlMode).

    Note: TestDeviceControlMode class declaration was accidentally split
    by DeviceBindingAPITest insertion. Methods below retain their original
    semantics; they are grouped under this continuation class.
    """

    def setUp(self):
        self.operator = OperatorUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.operator)

    def test_patch_control_mode_derives_methods(self):
        """PATCH with only control_mode derives concrete methods."""
        device = DeviceFactory(
            name='ControlMode-Patch-Device',
            device_type='windows',
            status='online',
            screenshot_method='auto',
            input_method='auto',
        )
        response = self.client.patch(
            f'/api/v2/devices/{device.pk}/',
            {'control_mode': 'background'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(response)['control_mode'], 'background')
        self.assertEqual(_unwrap(response)['screenshot_method'], 'auto')
        self.assertEqual(_unwrap(response)['input_method'], 'PostMessage')

    def test_patch_control_mode_preserves_explicit_overrides(self):
        """Explicit screenshot_method/input_method override control_mode defaults."""
        device = DeviceFactory(
            name='ControlMode-Override-Device',
            device_type='windows',
            status='online',
        )
        response = self.client.patch(
            f'/api/v2/devices/{device.pk}/',
            {
                'control_mode': 'foreground',
                'screenshot_method': 'gdi',
                'input_method': 'SendInput',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(response)['control_mode'], 'foreground')
        self.assertEqual(_unwrap(response)['screenshot_method'], 'gdi')
        self.assertEqual(_unwrap(response)['input_method'], 'SendInput')

    def test_derive_control_mode_heuristic(self):
        """Migration heuristic maps PostMessage to background."""
        self.assertEqual(
            Device.derive_control_mode('auto', 'PostMessage'),
            Device.ControlMode.BACKGROUND,
        )
        self.assertEqual(
            Device.derive_control_mode('printwindow', 'SendInput'),
            Device.ControlMode.PSEUDO_BACKGROUND,
        )
        self.assertEqual(
            Device.derive_control_mode('gdi', 'SendInput'),
            Device.ControlMode.FOREGROUND,
        )
