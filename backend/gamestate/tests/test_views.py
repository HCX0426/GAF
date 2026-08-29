"""Tests for gamestate.views (API layer).

Covers: GameProfile CRUD, GameStateRule CRUD, GameStateSnapshot read-only,
permission matrix.

URL prefix: /api/v2/gamestate/
Global pagination is ON (PageNumberPagination, PAGE_SIZE=20), so list
responses are dicts with 'count', 'next', 'previous', 'results'.

合并说明: 原 test_views.py + test_serializer_changes.py
test_serializer_changes.py 测试跨 app serializer 字段，与 views API 输出相关，合并后减少文件碎片。
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from gamestate.models import GameProfile, GameStateRule, GameStateSnapshot

GAME_PROFILE_URL = '/api/v2/gamestate/game-profiles/'
RULE_URL = '/api/v2/gamestate/rules/'
SNAPSHOT_URL = '/api/v2/gamestate/snapshots/'


def _login(client, username, password):
    """Login and set Bearer token on client."""
    resp = client.post('/api/v2/accounts/auth/login/', {
        'username': username, 'password': password,
    }, format='json')
    assert resp.status_code == 200, f'Login failed: {resp.status_code} {resp.data}'
    assert isinstance(resp.data, dict), f'Login resp not dict: {resp.data}'
    # Task 4.49 (P0-12, 2026-07-28): 修复 token 取值路径 (unified_response 信封)。
    if isinstance(resp.data.get('data'), dict) and 'access' in resp.data['data']:
        token = resp.data['data']['access']
    elif 'access' in resp.data:
        token = resp.data['access']
    else:
        raise AssertionError(f'Login resp missing access token: {resp.data}')
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return resp


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _get_results(resp):
    """Extract results list from a possibly-paginated response."""
    data = _unwrap(resp)
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    return data


class GameProfileViewSetTests(TestCase):
    """GameProfile ViewSet: CRUD (view read, manage write)."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='gp_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        self.viewer = User.objects.create_user(
            username='gp_viewer', password='ViewerPass123!', role=User.Role.VIEWER,
        )
        self.operator = User.objects.create_user(
            username='gp_op', password='OpPass123!', role=User.Role.OPERATOR,
        )
        _login(self.client, 'gp_admin', 'AdminPass123!')

    def test_list_game_profiles(self):
        GameProfile.objects.create(game_name='Game A')
        GameProfile.objects.create(game_name='Game B')
        resp = self.client.get(GAME_PROFILE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_get_results(resp)), 2)

    def test_create_game_profile(self):
        resp = self.client.post(GAME_PROFILE_URL, {
            'game_name': 'New Game',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(resp)['game_name'], 'New Game')
        self.assertEqual(_unwrap(resp)['ocr_language'], 'ch')

    def test_retrieve_game_profile(self):
        profile = GameProfile.objects.create(game_name='Retrieve Me')
        resp = self.client.get(f'{GAME_PROFILE_URL}{profile.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(resp)['game_name'], 'Retrieve Me')

    def test_update_game_profile(self):
        profile = GameProfile.objects.create(game_name='Update Me')
        resp = self.client.patch(f'{GAME_PROFILE_URL}{profile.id}/', {
            'ocr_language': 'en',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        profile.refresh_from_db()
        self.assertEqual(profile.ocr_language, 'en')

    def test_destroy_game_profile(self):
        profile = GameProfile.objects.create(game_name='Delete Me')
        resp = self.client.delete(f'{GAME_PROFILE_URL}{profile.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(GameProfile.objects.filter(id=profile.id).exists())

    def test_viewer_cannot_create_game_profile(self):
        _login(self.client, 'gp_viewer', 'ViewerPass123!')
        resp = self.client.post(GAME_PROFILE_URL, {
            'game_name': 'Denied',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_operator_cannot_create_game_profile(self):
        _login(self.client, 'gp_op', 'OpPass123!')
        resp = self.client.post(GAME_PROFILE_URL, {
            'game_name': 'Denied',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_can_list_game_profiles(self):
        _login(self.client, 'gp_viewer', 'ViewerPass123!')
        resp = self.client.get(GAME_PROFILE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class GameStateRuleViewSetTests(TestCase):
    """GameStateRule ViewSet: CRUD (view read, manage write)."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='rule_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        _login(self.client, 'rule_admin', 'AdminPass123!')

    def _profile(self, name):
        return GameProfile.objects.create(game_name=name)

    def test_list_rules(self):
        GameStateRule.objects.create(
            name='R1', game_profile=self._profile('G1'), tracker_type='ocr',
        )
        resp = self.client.get(RULE_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_get_results(resp)), 1)

    def test_create_rule(self):
        profile = self._profile('GameX')
        resp = self.client.post(RULE_URL, {
            'name': 'New Rule',
            'game_profile': profile.id,
            'tracker_type': 'ocr',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(_unwrap(resp)['name'], 'New Rule')
        # P5: 展示名恒来自 profile.game_name
        self.assertEqual(_unwrap(resp)['game_name'], 'GameX')

    def test_filter_by_game_profile(self):
        GameStateRule.objects.create(
            name='A', game_profile=self._profile('GameA'), tracker_type='ocr',
        )
        GameStateRule.objects.create(
            name='B', game_profile=self._profile('GameB'), tracker_type='ocr',
        )
        game_a = GameProfile.objects.get(game_name='GameA')
        resp = self.client.get(f'{RULE_URL}?game_profile={game_a.id}')
        results = _get_results(resp)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], 'A')


class GameStateSnapshotViewSetTests(TestCase):
    """GameStateSnapshot ViewSet: read-only list/retrieve."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='snap_admin', password='AdminPass123!', role=User.Role.ADMIN,
        )
        _login(self.client, 'snap_admin', 'AdminPass123!')
        self.rule = GameStateRule.objects.create(
            name='Snap Rule', game_profile=GameProfile.objects.create(game_name='GameA'),
            tracker_type='ocr',
        )

    def test_list_snapshots(self):
        GameStateSnapshot.objects.create(rule=self.rule, value=10)
        GameStateSnapshot.objects.create(rule=self.rule, value=20)
        resp = self.client.get(SNAPSHOT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_get_results(resp)), 2)

    def test_retrieve_snapshot(self):
        snap = GameStateSnapshot.objects.create(rule=self.rule, value=42)
        resp = self.client.get(f'{SNAPSHOT_URL}{snap.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(resp)['value'], 42)

    def test_viewer_can_list_snapshots(self):
        User.objects.create_user(
            username='snap_viewer', password='ViewerPass123!', role=User.Role.VIEWER,
        )
        _login(self.client, 'snap_viewer', 'ViewerPass123!')
        resp = self.client.get(SNAPSHOT_URL)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


class GamestateUnauthenticatedTests(TestCase):
    """Unauthenticated requests are rejected."""

    def test_unauthenticated_denied(self):
        client = APIClient()
        resp = client.get(GAME_PROFILE_URL)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ===========================================================================
# Serializer 字段变更 (原 test_serializer_changes.py)
# ===========================================================================

class TaskSerializerFieldsTest(TestCase):
    def test_task_serializer_no_resource_pack(self):
        from tasks.serializers import TaskSerializer
        fields = TaskSerializer().fields
        assert 'resource_pack' in fields  # N197-8: FK auto-included via fields='__all__'
        assert 'game_account' not in fields  # single FK removed
        assert 'game_profile' in fields
        assert 'game_accounts' in fields  # M2M retained

    def test_game_account_serializer_has_game_profile(self):
        from accounts.serializers import GameAccountSerializer
        fields = GameAccountSerializer().fields
        assert 'game_profile' in fields
        assert 'allowed_resource_packs' not in fields

    def test_device_serializer_has_game_account(self):
        from agents.serializers import DeviceSerializer
        fields = DeviceSerializer().fields
        assert 'game_account' in fields

    def test_task_chain_serializer_has_game_profile(self):
        from pipeline.serializers import TaskChainSerializer
        fields = TaskChainSerializer().fields
        assert 'game_profile' in fields
        assert 'is_default' in fields

    def test_game_profile_serializer_has_defaults(self):
        from gamestate.serializers import GameProfileSerializer
        fields = GameProfileSerializer().fields
        assert 'default_task_chain' in fields
        assert 'default_screenshot_method' in fields
        assert 'default_input_method' in fields
        assert 'default_control_mode' in fields
