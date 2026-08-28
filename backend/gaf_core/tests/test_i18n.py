"""i18n 测试 (API + gettext_lazy translation)

合并说明: 原 test_i18n_api.py + test_translations.py
两者同属 i18n app，测试不同层面（API 端点 + 翻译函数），合并后减少文件碎片。
"""

from django.test import TestCase
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.test import APIClient

# ===========================================================================
# i18n API (原 test_i18n_api.py)
# ===========================================================================


class TestLanguageListView(TestCase):
    """GET /api/v2/i18n/languages/"""

    def setUp(self):
        self.client = APIClient()

    def test_list_languages_returns_4_languages(self):
        """Verify 4 languages are configured."""
        response = self.client.get('/api/v2/i18n/languages/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('languages', data)
        self.assertEqual(len(data['languages']), 4)
        codes = {lang['code'] for lang in data['languages']}
        self.assertEqual(codes, {'zh-hans', 'en', 'ja', 'ko'})

    def test_list_languages_includes_default(self):
        """Verify default language is returned."""
        response = self.client.get('/api/v2/i18n/languages/')
        data = response.json()
        self.assertEqual(data['default'], 'zh-hans')

    def test_list_languages_no_auth_required(self):
        """Verify endpoint is public (AllowAny)."""
        # No authentication provided, should still work
        response = self.client.get('/api/v2/i18n/languages/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestMessageCatalogView(TestCase):
    """GET /api/v2/i18n/catalog/<lang>/"""

    def setUp(self):
        self.client = APIClient()

    def test_catalog_en_returns_english_messages(self):
        """Verify English catalog returns translated messages."""
        response = self.client.get('/api/v2/i18n/catalog/en/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['language'], 'en')
        catalog = data['catalog']
        self.assertEqual(catalog['password_changed_successfully'], 'Password changed successfully')
        self.assertEqual(catalog['2fa_enabled'], '2FA enabled')
        self.assertEqual(catalog['2fa_disabled'], '2FA disabled')

    def test_catalog_zh_hans_returns_chinese_messages(self):
        """Verify Chinese catalog returns Chinese messages."""
        response = self.client.get('/api/v2/i18n/catalog/zh-hans/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['language'], 'zh-hans')
        catalog = data['catalog']
        self.assertEqual(catalog['password_changed_successfully'], '密码修改成功')
        self.assertEqual(catalog['2fa_enabled'], '2FA 已启用')

    def test_catalog_ja_returns_japanese_messages(self):
        """Verify Japanese catalog returns Japanese messages."""
        response = self.client.get('/api/v2/i18n/catalog/ja/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        catalog = data['catalog']
        self.assertEqual(catalog['2fa_enabled'], '2FA が有効になりました')

    def test_catalog_ko_returns_korean_messages(self):
        """Verify Korean catalog returns Korean messages."""
        response = self.client.get('/api/v2/i18n/catalog/ko/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        catalog = data['catalog']
        self.assertEqual(catalog['2fa_enabled'], '2FA가 활성화되었습니다')

    def test_catalog_invalid_language_returns_400(self):
        """Verify invalid language code returns 400."""
        response = self.client.get('/api/v2/i18n/catalog/fr/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_catalog_contains_all_expected_keys(self):
        """Verify catalog contains all 11 expected message keys."""
        response = self.client.get('/api/v2/i18n/catalog/en/')
        data = response.json()
        catalog = data['catalog']
        expected_keys = {
            'password_changed_successfully',
            '2fa_enabled',
            '2fa_disabled',
            'reset_link_sent',
            'password_reset_success',
            'session_terminated',
            'system_already_initialized',
            'username_too_short',
            'password_too_short',
            'login_history_forbidden',
            'unsupported_language',
        }
        self.assertEqual(set(catalog.keys()), expected_keys)


# ===========================================================================
# gettext_lazy 翻译 (原 test_translations.py)
# ===========================================================================


class TestGettextLazyTranslation(TestCase):
    """Verify gettext_lazy messages translate correctly per language."""

    # All messages marked with gettext_lazy in accounts/views.py
    MARKED_MESSAGES = {
        '密码修改成功': {
            'en': 'Password changed successfully',
            'ja': 'パスワードの変更に成功しました',
            'ko': '비밀번호가 성공적으로 변경되었습니다',
        },
        '2FA 已启用': {
            'en': '2FA enabled',
            'ja': '2FA が有効になりました',
            'ko': '2FA가 활성화되었습니다',
        },
        '2FA 已禁用': {
            'en': '2FA disabled',
            'ja': '2FA が無効になりました',
            'ko': '2FA가 비활성화되었습니다',
        },
        '会话已下线': {
            'en': 'Session terminated',
            'ja': 'セッションを終了しました',
            'ko': '세션이 종료되었습니다',
        },
        '密码重置成功': {
            'en': 'Password reset successfully',
            'ja': 'パスワードのリセットに成功しました',
            'ko': '비밀번호가 성공적으로 재설정되었습니다',
        },
        '用户名至少 3 个字符': {
            'en': 'Username must be at least 3 characters',
            'ja': 'ユーザー名は3文字以上必要です',
            'ko': '사용자명은 최소 3자 이상이어야 합니다',
        },
        '密码至少 8 个字符': {
            'en': 'Password must be at least 8 characters',
            'ja': 'パスワードは8文字以上必要です',
            'ko': '비밀번호는 최소 8자 이상이어야 합니다',
        },
    }

    def test_zh_hans_translation_returns_source(self):
        """zh-hans should return the original Chinese text."""
        with translation.override('zh-hans'):
            for source in self.MARKED_MESSAGES:
                self.assertEqual(str(_(source)), source)

    def test_en_translation(self):
        """English translations should match expected strings."""
        with translation.override('en'):
            for source, expected in self.MARKED_MESSAGES.items():
                self.assertEqual(str(_(source)), expected['en'],
                                 f'English translation mismatch for: {source}')

    def test_ja_translation(self):
        """Japanese translations should match expected strings."""
        with translation.override('ja'):
            for source, expected in self.MARKED_MESSAGES.items():
                self.assertEqual(str(_(source)), expected['ja'],
                                 f'Japanese translation mismatch for: {source}')

    def test_ko_translation(self):
        """Korean translations should match expected strings."""
        with translation.override('ko'):
            for source, expected in self.MARKED_MESSAGES.items():
                self.assertEqual(str(_(source)), expected['ko'],
                                 f'Korean translation mismatch for: {source}')

    def test_translation_context_isolation(self):
        """Translation should not leak between language contexts."""
        with translation.override('en'):
            self.assertEqual(str(_('2FA 已启用')), '2FA enabled')
        # After exiting context, default language should be restored
        # (in tests this is usually LANGUAGE_CODE = zh-hans)
        self.assertEqual(str(_('2FA 已启用')), '2FA 已启用')

    def test_gettext_lazy_returns_lazy_object(self):
        """gettext_lazy should return a lazy object, not a str."""
        result = _('密码修改成功')
        # lazy objects have __str__ but are not str instances
        self.assertNotIsInstance(result, str)
        self.assertEqual(str(result), '密码修改成功')
