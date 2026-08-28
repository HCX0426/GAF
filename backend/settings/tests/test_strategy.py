"""
无人值守策略配置测试

覆盖：
- 创建（Upsert）/ 读取 / 更新
- 策略字段正确性（recovery/nightMode/frequencyLimit/notificationPolicy/cooldown）
- 序列化器校验（夜间模式时间范围不能倒置）
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


class TestUnattendedStrategyAPI(TestCase):
    """无人值守策略配置 CRUD 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='strategy_test',
            password='testpass123',
        )
        self.client.force_authenticate(user=self.user)
        self.url = '/api/v2/settings/unattended-strategy/'

    def test_get_strategy_returns_defaults_when_empty(self):
        """TC-7.1-1: GET 空数据库返回默认值"""
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap(res)
        self.assertIn('recovery', body)
        self.assertIn('nightMode', body)
        self.assertIn('frequencyLimit', body)

    def test_post_creates_upsert_strategy(self):
        """TC-7.1-2: POST 创建策略配置 -> 200"""
        data = {
            'recovery': {
                'stepLevel': {'maxRetries': 5, 'retryIntervalSeconds': 10, 'exponentialBackoff': True},
                'taskLevel': {'consecutiveFailureThreshold': 5, 'failureAction': 'restart'},
                'appLevel': {'freezeDetection': True, 'freezeTimeoutSeconds': 180, 'freezeAction': 'relogin'},
                'deviceLevel': {'crashDetection': True, 'crashAction': 'reconnect_adb', 'backupDeviceId': None, 'maxRestartCount': 3},
                'systemLevel': {'agentTimeoutSeconds': 600, 'timeoutActions': ['notify', 'mark_offline']},
            },
            'nightMode': {
                'isEnabled': True, 'timeRange': {'start': '23:00', 'end': '05:00'},
                'screenshotIntervalMultiplier': 3, 'operationIntervalMultiplier': 2,
                'cpuThrottle': True, 'autoPauseNonCritical': True,
            },
            'frequencyLimit': {
                'maxPerAccountPerDay': 20, 'maxGlobalPerDay': 200,
                'minTaskIntervalSeconds': 60, 'mode': 'adaptive',
            },
            'notificationPolicy': {
                'enabledEvents': ['task_failed', 'device_offline'],
            },
            'cooldown': {
                'emulatorRestartSeconds': 180, 'gameRestartSeconds': 90,
                'consecutiveLoginSeconds': 15, 'recoveryPauseSeconds': 300,
            },
        }
        res = self.client.post(self.url, data, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap(res)
        self.assertEqual(body['recovery']['stepLevel']['maxRetries'], 5)
        self.assertTrue(body['nightMode']['isEnabled'])

    def test_post_updates_existing_strategy(self):
        """TC-7.1-3: POST 再次调用覆盖已有策略（Upsert）"""
        data1 = {
            'recovery': {
                'stepLevel': {'maxRetries': 3, 'retryIntervalSeconds': 5, 'exponentialBackoff': False},
                'taskLevel': {'consecutiveFailureThreshold': 3, 'failureAction': 'skip'},
                'appLevel': {'freezeDetection': True, 'freezeTimeoutSeconds': 120, 'freezeAction': 'restart_app'},
                'deviceLevel': {'crashDetection': True, 'crashAction': 'restart_emulator', 'backupDeviceId': None, 'maxRestartCount': 2},
                'systemLevel': {'agentTimeoutSeconds': 300, 'timeoutActions': ['notify', 'mark_offline', 'reassign']},
            },
            'nightMode': {
                'isEnabled': False, 'timeRange': {'start': '00:00', 'end': '06:00'},
                'screenshotIntervalMultiplier': 2, 'operationIntervalMultiplier': 2,
                'cpuThrottle': True, 'autoPauseNonCritical': False,
            },
            'frequencyLimit': {
                'maxPerAccountPerDay': 10, 'maxGlobalPerDay': 100,
                'minTaskIntervalSeconds': 30, 'mode': 'fixed',
            },
            'notificationPolicy': {
                'enabledEvents': ['task_failed', 'device_offline'],
            },
            'cooldown': {
                'emulatorRestartSeconds': 120, 'gameRestartSeconds': 60,
                'consecutiveLoginSeconds': 10, 'recoveryPauseSeconds': 180,
            },
        }
        res1 = self.client.post(self.url, data1, format='json')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        data2 = {
            'recovery': {
                'stepLevel': {'maxRetries': 10, 'retryIntervalSeconds': 20, 'exponentialBackoff': True},
                'taskLevel': {'consecutiveFailureThreshold': 10, 'failureAction': 'switch_account'},
                'appLevel': {'freezeDetection': False, 'freezeTimeoutSeconds': 60, 'freezeAction': 'notify_only'},
                'deviceLevel': {'crashDetection': True, 'crashAction': 'restart_emulator', 'backupDeviceId': None, 'maxRestartCount': 5},
                'systemLevel': {'agentTimeoutSeconds': 900, 'timeoutActions': ['notify']},
            },
            'nightMode': {
                'isEnabled': True, 'timeRange': {'start': '01:00', 'end': '05:00'},
                'screenshotIntervalMultiplier': 4, 'operationIntervalMultiplier': 3,
                'cpuThrottle': True, 'autoPauseNonCritical': True,
            },
            'frequencyLimit': {
                'maxPerAccountPerDay': 30, 'maxGlobalPerDay': 300,
                'minTaskIntervalSeconds': 120, 'mode': 'adaptive',
            },
            'notificationPolicy': {
                'enabledEvents': ['task_failed', 'device_offline', 'account_blocked'],
            },
            'cooldown': {
                'emulatorRestartSeconds': 300, 'gameRestartSeconds': 120,
                'consecutiveLoginSeconds': 20, 'recoveryPauseSeconds': 600,
            },
        }
        res2 = self.client.post(self.url, data2, format='json')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        body1 = _unwrap(res1)
        body2 = _unwrap(res2)
        self.assertNotEqual(body1['recovery']['stepLevel']['maxRetries'],
                           body2['recovery']['stepLevel']['maxRetries'])
        self.assertEqual(body2['recovery']['stepLevel']['maxRetries'], 10)

    def test_night_mode_time_range_validation(self):
        """TC-7.1-4: 夜间模式 timeRange 不允许 start == end"""
        data = {
            'recovery': {
                'stepLevel': {'maxRetries': 3, 'retryIntervalSeconds': 5, 'exponentialBackoff': False},
                'taskLevel': {'consecutiveFailureThreshold': 3, 'failureAction': 'skip'},
                'appLevel': {'freezeDetection': True, 'freezeTimeoutSeconds': 120, 'freezeAction': 'restart_app'},
                'deviceLevel': {'crashDetection': True, 'crashAction': 'restart_emulator', 'backupDeviceId': None, 'maxRestartCount': 2},
                'systemLevel': {'agentTimeoutSeconds': 300, 'timeoutActions': ['notify', 'mark_offline', 'reassign']},
            },
            'nightMode': {
                'isEnabled': True, 'timeRange': {'start': '06:00', 'end': '06:00'},
                'screenshotIntervalMultiplier': 2, 'operationIntervalMultiplier': 2,
                'cpuThrottle': True, 'autoPauseNonCritical': False,
            },
            'frequencyLimit': {
                'maxPerAccountPerDay': 10, 'maxGlobalPerDay': 100,
                'minTaskIntervalSeconds': 30, 'mode': 'fixed',
            },
            'notificationPolicy': {
                'enabledEvents': ['task_failed', 'device_offline'],
            },
            'cooldown': {
                'emulatorRestartSeconds': 120, 'gameRestartSeconds': 60,
                'consecutiveLoginSeconds': 10, 'recoveryPauseSeconds': 180,
            },
        }
        res = self.client.post(self.url, data, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_strategy_fields_structure(self):
        """TC-7.1-5: 策略数据包含所有 5 个顶层字段"""
        data = {
            'recovery': {
                'stepLevel': {'maxRetries': 3, 'retryIntervalSeconds': 5, 'exponentialBackoff': False},
                'taskLevel': {'consecutiveFailureThreshold': 3, 'failureAction': 'skip'},
                'appLevel': {'freezeDetection': True, 'freezeTimeoutSeconds': 120, 'freezeAction': 'restart_app'},
                'deviceLevel': {'crashDetection': True, 'crashAction': 'restart_emulator', 'backupDeviceId': None, 'maxRestartCount': 2},
                'systemLevel': {'agentTimeoutSeconds': 300, 'timeoutActions': ['notify', 'mark_offline', 'reassign']},
            },
            'nightMode': {
                'isEnabled': False, 'timeRange': {'start': '00:00', 'end': '06:00'},
                'screenshotIntervalMultiplier': 2, 'operationIntervalMultiplier': 2,
                'cpuThrottle': True, 'autoPauseNonCritical': False,
            },
            'frequencyLimit': {
                'maxPerAccountPerDay': 10, 'maxGlobalPerDay': 100,
                'minTaskIntervalSeconds': 30, 'mode': 'fixed',
            },
            'notificationPolicy': {
                'enabledEvents': ['task_failed', 'device_offline'],
            },
            'cooldown': {
                'emulatorRestartSeconds': 120, 'gameRestartSeconds': 60,
                'consecutiveLoginSeconds': 10, 'recoveryPauseSeconds': 180,
            },
        }
        res = self.client.post(self.url, data, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body = _unwrap(res)
        for key in ['recovery', 'nightMode', 'frequencyLimit', 'notificationPolicy', 'cooldown']:
            self.assertIn(key, body, f'缺少字段: {key}')
