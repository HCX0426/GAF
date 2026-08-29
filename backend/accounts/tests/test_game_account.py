"""
游戏账户 API 单元测试 (Phase 4 更新)
测试 CRUD 接口、权限控制、加密存储验证
"""
import os

import pytest
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from accounts.crypto import DecryptionError, decrypt_password, encrypt_password
from accounts.models import GameAccount, User
from gamestate.models import GameProfile

pytestmark = pytest.mark.integration


def _profile(game_name):
    """按游戏名 find_or_create 全局 profile (P2 后 game_profile 必填)."""
    return GameProfile.objects.get_or_create(game_name=game_name)[0]


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


class TestGameAccountAPI(TestCase):
    """GameAccount CRUD API 测试"""

    def setUp(self):
        """初始化 API 客户端和测试用户。"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123',
            role=User.Role.OPERATOR,
        )
        self.other_user = User.objects.create_user(
            username='otheruser',
            password='otherpass123',
            role=User.Role.VIEWER,
        )
        self.create_payload = {
            'game_profile': GameProfile.objects.get_or_create(game_name='原神')[0].id,
            'username': 'genshin_player',
            'password': 'mygenshinpass',
            'server_region': '官服',
            'login_method': 'password',
        }

    def _auth(self, user=None):
        """便捷认证方法。"""
        self.client.force_authenticate(user=user or self.user)

    def test_create_game_account(self):
        """创建游戏账户 API — 验证返回 201 且密码已加密存储。"""
        self._auth()
        response = self.client.post(
            '/api/v2/accounts/game-accounts/',
            self.create_payload,
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = _unwrap(response)
        self.assertIn('id', body)
        self.assertEqual(body['game_name_display'], '原神')
        # 验证密码不为明文存储
        account = GameAccount.objects.get(pk=body['id'])
        self.assertIsNotNone(account.encrypted_password)
        self.assertNotEqual(account.encrypted_password, 'mygenshinpass')

    def test_list_game_accounts(self):
        """获取当前用户的游戏账户列表。"""
        self._auth()
        for i in range(2):
            GameAccount.objects.create(
                owner=self.user,
                game_profile=_profile('游戏'),
                username=f'player{i}',
                encrypted_password=encrypt_password(f'pass{i}'),
            )
        response = self.client.get('/api/v2/accounts/game-accounts/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(_get_results(response)), 2)

    def test_retrieve_game_account(self):
        """获取单个游戏账户详情 — 验证不返回密码。"""
        self._auth()
        account = GameAccount.objects.create(
            owner=self.user,
            game_profile=_profile('星穹铁道'),
            username='sr_player',
            encrypted_password=encrypt_password('testpass'),
            server_region='B服',
            login_method='qr_scan',
        )
        response = self.client.get(f'/api/v2/accounts/game-accounts/{account.pk}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = _unwrap(response)
        self.assertEqual(body['game_name_display'], '星穹铁道')
        self.assertNotIn('password', body)
        self.assertNotIn('encrypted_password', body)

    def test_update_game_account(self):
        """更新游戏账户 — 验证密码可选更新。"""
        self._auth()
        account = GameAccount.objects.create(
            owner=self.user,
            game_profile=_profile('原神'),
            username='old_name',
            encrypted_password=encrypt_password('oldpass'),
        )
        response = self.client.patch(
            f'/api/v2/accounts/game-accounts/{account.pk}/',
            {'username': 'new_name', 'password': 'newpassword123'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(response)['username'], 'new_name')
        account.refresh_from_db()
        self.assertNotEqual(account.encrypted_password, encrypt_password('oldpass'))
        decrypted = decrypt_password(account.encrypted_password)
        self.assertEqual(decrypted, 'newpassword123')

    def test_update_without_password(self):
        """更新时不留密码 — 原有密码不变。"""
        self._auth()
        account = GameAccount.objects.create(
            owner=self.user,
            game_profile=_profile('原神'),
            username='player1',
            encrypted_password=encrypt_password('original'),
        )
        response = self.client.patch(
            f'/api/v2/accounts/game-accounts/{account.pk}/',
            {'username': 'player1_updated'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        account.refresh_from_db()
        decrypted = decrypt_password(account.encrypted_password)
        self.assertEqual(decrypted, 'original')

    def test_delete_game_account(self):
        """删除游戏账户。"""
        self._auth()
        account = GameAccount.objects.create(
            owner=self.user,
            game_profile=_profile('测试游戏'),
            username='test_player',
            encrypted_password=encrypt_password('testpass'),
        )
        response = self.client.delete(f'/api/v2/accounts/game-accounts/{account.pk}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(GameAccount.objects.filter(pk=account.pk).exists())

    def test_cannot_access_other_user_account(self):
        """权限校验 — 不能访问其他用户的游戏账户。"""
        self._auth()
        other_account = GameAccount.objects.create(
            owner=self.other_user,
            game_profile=_profile('别人的游戏'),
            username='other_player',
            encrypted_password=encrypt_password('otherpass'),
        )
        response = self.client.get(f'/api/v2/accounts/game-accounts/{other_account.pk}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_update_other_user_account(self):
        """权限校验 — 不能更新其他用户的账户。"""
        self._auth()
        other_account = GameAccount.objects.create(
            owner=self.other_user,
            game_profile=_profile('别人的游戏'),
            username='other_player',
            encrypted_password=encrypt_password('otherpass'),
        )
        response = self.client.patch(
            f'/api/v2/accounts/game-accounts/{other_account.pk}/',
            {'username': 'hacked_name'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_delete_other_user_account(self):
        """权限校验 — 不能删除其他用户的账户。"""
        self._auth()
        other_account = GameAccount.objects.create(
            owner=self.other_user,
            game_profile=_profile('别人的游戏'),
            username='other_player',
            encrypted_password=encrypt_password('otherpass'),
        )
        response = self.client.delete(f'/api/v2/accounts/game-accounts/{other_account.pk}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_only_own_accounts(self):
        """列表只返回当前用户的账户。"""
        self._auth()
        GameAccount.objects.create(
            owner=self.user,
            game_profile=_profile('我的游戏'),
            username='my_player',
            encrypted_password=encrypt_password('mypass'),
        )
        GameAccount.objects.create(
            owner=self.other_user,
            game_profile=_profile('别人的游戏'),
            username='other_player',
            encrypted_password=encrypt_password('otherpass'),
        )
        response = self.client.get('/api/v2/accounts/game-accounts/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(_get_results(response)), 1)

    def test_unauthenticated_cannot_access(self):
        """未认证用户不能访问。"""
        response = self.client.get('/api/v2/accounts/game-accounts/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_without_password(self):
        """创建时缺少密码 — 应返回 400。"""
        self._auth()
        payload = {
            'game_name': '原神',
            'username': 'player',
        }
        response = self.client.post('/api/v2/accounts/game-accounts/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestGameAccountCrypto(TestCase):
    """AES-256-GCM 加密解密测试 (merged from test_game_account_crypto.py)"""

    def test_encrypt_decrypt_roundtrip(self):
        """验证加密后解密能还原明文。"""
        plaintext = "MyGamePassword123!"
        ciphertext = encrypt_password(plaintext)
        decrypted = decrypt_password(ciphertext)
        self.assertEqual(plaintext, decrypted)

    def test_encrypt_produces_different_ciphertext(self):
        """验证同一明文两次加密产生不同密文（nonce 随机性）。"""
        plaintext = "password1"
        ct1 = encrypt_password(plaintext)
        ct2 = encrypt_password(plaintext)
        self.assertNotEqual(ct1, ct2)

    def test_decrypt_chinese_password(self):
        """验证中文密码的加密解密。"""
        plaintext = "我的游戏密码123"
        ciphertext = encrypt_password(plaintext)
        decrypted = decrypt_password(ciphertext)
        self.assertEqual(plaintext, decrypted)

    def test_decrypt_empty_password(self):
        """验证空密码的加密解密。"""
        plaintext = ""
        ciphertext = encrypt_password(plaintext)
        decrypted = decrypt_password(ciphertext)
        self.assertEqual(plaintext, decrypted)

    def test_decrypt_special_chars_password(self):
        """验证包含特殊字符的密码加密解密。"""
        plaintext = "P@ssw0rd!#$%^&*()_+-=[]{}|;':\",./<>?"
        ciphertext = encrypt_password(plaintext)
        decrypted = decrypt_password(ciphertext)
        self.assertEqual(plaintext, decrypted)

    def test_decrypt_wrong_ciphertext_raises_error(self):
        """验证错误密文解密时抛出 DecryptionError。"""
        with self.assertRaises(DecryptionError):
            decrypt_password("bad:data:not:valid")

    def test_decrypt_empty_string_raises_error(self):
        """验证空字符串解密时抛出 DecryptionError。"""
        with self.assertRaises(DecryptionError):
            decrypt_password("")

    def test_encrypt_result_has_nonce_and_tag(self):
        """验证加密结果包含 nonce(base64) + ':' + ciphertext+tag(base64) 格式。"""
        plaintext = "testpassword"
        ciphertext = encrypt_password(plaintext)
        parts = ciphertext.split(":")
        self.assertEqual(len(parts), 2)
        self.assertGreater(len(parts[0]), 0)
        self.assertGreater(len(parts[1]), 0)

    @override_settings(SECRET_KEY="test-derive-key")
    def test_derive_key_from_secret(self):
        """验证从 SECRET_KEY 派生密钥时能正常工作。"""
        if "GAF_MASTER_KEY" in os.environ:
            del os.environ["GAF_MASTER_KEY"]
        plaintext = "derived_key_test"
        ct = encrypt_password(plaintext)
        result = decrypt_password(ct)
        self.assertEqual(plaintext, result)
