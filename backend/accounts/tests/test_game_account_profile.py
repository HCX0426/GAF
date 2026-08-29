"""GameAccount ↔ GameProfile 绑定测试 (spec 2026-08-29-game-account-game-name-retirement P1).

验证写入路径迁移: game_profile 成为唯一游戏维度, 字符串 game_name 仅作兼容输入解析.
"""
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import GameAccount, User
from gamestate.models import GameProfile


def _unwrap(resp):
    data = resp.data
    if isinstance(data, dict) and isinstance(data.get('data'), (dict, list)):
        data = data['data']  # unified_response 包装 {code, message, data}
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    if isinstance(data, dict):
        return [data]
    return data


class GameAccountProfileBindingTest(APITestCase):
    """P1: 写入路径 — game_profile_id 优先, game_name 兼容解析并自动绑定 profile."""

    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='p1-user',
            password='x',
            role=User.Role.OPERATOR,
        )
        self.client.force_authenticate(user=self.user)

    def test_create_with_profile_id_binds(self):
        profile = GameProfile.objects.create(game_name='BD2')
        res = self.client.post('/api/v2/accounts/game-accounts/', {
            'game_profile': profile.id,
            'username': 'acc1',
            'password': 'p',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        body = _unwrap(res)
        body = body[0] if isinstance(body, list) else body
        acc = GameAccount.objects.get(username='acc1')
        self.assertEqual(acc.game_profile_id, profile.id)
        # 展示输出跟随 profile 名
        self.assertEqual(body.get('game_name'), 'BD2')
        self.assertEqual(body.get('game_name_display'), 'BD2')

    def test_create_with_game_name_resolves_profile(self):
        res = self.client.post('/api/v2/accounts/game-accounts/', {
            'game_name': 'BD2',
            'username': 'acc2',
            'password': 'p',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        acc = GameAccount.objects.get(username='acc2')
        self.assertIsNotNone(acc.game_profile)
        self.assertEqual(acc.game_profile.game_name, 'BD2')
        # 同名 profile 全局唯一: 不因多次创建而重复
        self.assertEqual(GameProfile.objects.filter(game_name='BD2').count(), 1)
        # 字符串字段同步为 profile 名 (P2 前保持非空)
        self.assertEqual(acc.game_name, 'BD2')

    def test_update_sets_profile(self):
        acc = GameAccount.objects.create(
            owner=self.user, game_name='BD2', username='acc3',
            encrypted_password='e',
        )
        profile = GameProfile.objects.create(game_name='BD2')
        res = self.client.patch(f'/api/v2/accounts/game-accounts/{acc.id}/', {
            'game_profile': profile.id,
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        acc.refresh_from_db()
        self.assertEqual(acc.game_profile_id, profile.id)


class GameAccountDisplayTest(APITestCase):
    """P1: 展示路径 — list game_name 输出跟随 profile 名 + 视图过滤按 profile."""

    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='p2-user', password='x', role=User.Role.OPERATOR,
        )
        self.client.force_authenticate(user=self.user)
        self.profile = GameProfile.objects.create(game_name='BD2')
        GameAccount.objects.create(
            owner=self.user, game_profile=self.profile, game_name='BD2',
            username='accx', encrypted_password='e',
        )

    def test_list_game_name_follows_profile(self):
        self.profile.game_name = 'BD2-Reforged'
        self.profile.save()
        res = self.client.get('/api/v2/accounts/game-accounts/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = _unwrap(res)
        item = next(i for i in items if i['username'] == 'accx')
        self.assertEqual(item.get('game_name_display'), 'BD2-Reforged')

    def test_filter_game_name_matches_profile(self):
        other = GameProfile.objects.create(game_name='ZZZ')
        GameAccount.objects.create(
            owner=self.user, game_profile=other, game_name='ZZZ',
            username='accy', encrypted_password='e',
        )
        res = self.client.get('/api/v2/accounts/game-accounts/', {'game_name': 'BD2'})
        items = _unwrap(res)
        self.assertEqual([i['username'] for i in items], ['accx'])
