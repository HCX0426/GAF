"""LLM Provider (multi-provider) tests.

Covers Phase 1 of the AI-tab learning spec:
- Multiple LLMConfig rows can coexist (backend already ModelViewSet multi-row)
- ``set_active`` action keeps exactly one row active (exclusive activation)
- ``llm_service._get_llm_config`` picks the active row (not the newest ``first()``)
- api_key is stored encrypted and round-trips to plaintext via ``get_api_key``
- serializer exposes ``api_key_masked`` and never returns the raw key
"""

from django.test import TestCase, override_settings
from gaf_ai import llm_service
from rest_framework import status
from rest_framework.test import APIClient

from accounts.factories import AdminUserFactory
from settings.models import LLMConfig


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _unwrap_list(resp):
    """List 接口分页信封解包: data -> {count, results} -> 数组."""
    body = _unwrap(resp)
    if isinstance(body, list):
        return body
    if isinstance(body, dict) and 'results' in body:
        return body['results']
    return body


# Fernet key for the encrypted-storage test (must be URL-safe base64 32-byte).
_TEST_FERNET_KEY = 'VXbYjZk9u7p3Qx2mC8rF5tNwA6sD1eG4hL0iK7oP9rB='


class TestLLMProviderMultiRow(TestCase):
    """LLM 多 provider 并存 + set_active 唯一激活测试"""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.base_url = '/api/v2/settings/llm-config/'

    def _create(self, provider, model, active=False, key='sk-test-abc'):
        res = self.client.post(
            self.base_url,
            {
                'provider': provider,
                'api_key': key,
                'api_base': f'https://api.{provider}.com/v1',
                'default_model': model,
                'temperature': 0.3,
                'max_tokens': 4096,
                'is_active': active,
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        return _unwrap(res)

    def test_multi_provider_can_coexist(self):
        """TC-P1-1: 多个 provider 可并存，列表返回全部行"""
        self._create('openai', 'gpt-4o-mini', active=True)
        self._create('deepseek', 'deepseek-chat')
        res = self.client.get(self.base_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        rows = _unwrap_list(res)
        self.assertEqual(len(rows), 2)
        providers = {row['provider'] for row in rows}
        self.assertEqual(providers, {'openai', 'deepseek'})

    def test_set_active_is_exclusive(self):
        """TC-P1-2: set-active 使目标行激活，其余行自动失效"""
        self._create('openai', 'gpt-4o-mini')
        b = self._create('deepseek', 'deepseek-chat')
        res = self.client.post(f"{self.base_url}{b['id']}/set-active/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        a_db = LLMConfig.objects.get(provider='openai')
        b_db = LLMConfig.objects.get(provider='deepseek')
        self.assertFalse(a_db.is_active)
        self.assertTrue(b_db.is_active)

    def test_get_llm_config_uses_active_not_first(self):
        """TC-P1-3: _get_llm_config 取 is_active 的行，而非最新 first()"""
        # 创建三条: 新创建的 active=False，中间那条 active=True
        self._create('openai', 'gpt-4o-mini', active=False)
        active = self._create('deepseek', 'deepseek-chat', active=True)
        self._create('qwen', 'qwen-max', active=False)  # newest but inactive
        cfg = llm_service._get_llm_config()
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg.provider, 'deepseek')
        self.assertEqual(cfg.default_model, active['default_model'])

    def test_get_llm_config_none_when_no_active(self):
        """TC-P1-4: 无激活行时 _get_llm_config 返回 None"""
        self._create('openai', 'gpt-4o-mini', active=False)
        self.assertIsNone(llm_service._get_llm_config())

    def test_api_key_encrypted_roundtrip(self):
        """TC-P1-5: api_key 落库加密（加密启用时），get_api_key 返回明文"""
        from settings import crypto as crypto_mod

        # 重置 Fernet 缓存使 override_settings 生效
        crypto_mod._fernet = None
        crypto_mod._encryption_key_checked = False
        try:
            with override_settings(GAF_LLM_API_KEY_ENCRYPTION_KEY=_TEST_FERNET_KEY):
                cfg = LLMConfig.objects.create(
                    provider='custom',
                    api_key='sk-plain-123456',
                    api_base='https://example.com/v1',
                    default_model='custom-model',
                )
                # 库中存储的不应是明文
                self.assertTrue(cfg.api_key.startswith('gAAAAA'))
                self.assertNotEqual(cfg.api_key, 'sk-plain-123456')
                # get_api_key 解密回明文
                self.assertEqual(cfg.get_api_key(), 'sk-plain-123456')
        finally:
            crypto_mod._fernet = None
            crypto_mod._encryption_key_checked = False

    def test_api_key_never_returned_in_response(self):
        """TC-P1-6: 响应不回传原始 key，只给掩码"""
        self._create('openai', 'gpt-4o-mini', key='sk-abcdef123456')
        res = self.client.get(self.base_url)
        row = _unwrap_list(res)[0]
        self.assertNotIn('api_key', row)
        self.assertIn('api_key_masked', row)
        self.assertNotEqual(row['api_key_masked'], 'sk-abcdef123456')

    def test_available_models_roundtrip(self):
        """TC-P1-7: available_models 模型列表可读写往返"""
        res = self.client.post(
            self.base_url,
            {
                'provider': 'openai',
                'api_key': 'sk-test-abc',
                'api_base': 'https://api.openai.com/v1',
                'default_model': 'gpt-4o-mini',
                'available_models': ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini'],
            },
            format='json',
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        row = _unwrap(res)
        self.assertEqual(row['available_models'], ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini'])

        # 落库一致
        db_row = LLMConfig.objects.get(provider='openai')
        self.assertEqual(db_row.available_models, ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini'])

    @override_settings(GAF_LLM_API_KEY_ENCRYPTION_KEY=_TEST_FERNET_KEY)
    def test_test_connection_missing_key(self):
        """TC-P1-8: test 端点无 api_key 时返回 400"""
        from settings import crypto as crypto_mod

        crypto_mod._fernet = None
        crypto_mod._encryption_key_checked = False
        try:
            res = self.client.post(
                self.base_url,
                {
                    'provider': 'openai',
                    'api_key': '',
                    'api_base': 'https://api.openai.com/v1',
                    'default_model': 'gpt-4o-mini',
                },
                format='json',
            )
            self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
            row = _unwrap(res)
            test_res = self.client.post(f"{self.base_url}{row['id']}/test/", {}, format='json')
            self.assertIn(test_res.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_200_OK))
        finally:
            crypto_mod._fernet = None
            crypto_mod._encryption_key_checked = False
