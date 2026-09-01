"""accounts.APIKeyAuthentication tests (TD-424).

Covers: valid key auth, invalid/inactive/expired rejection, IP whitelist,
call_count increment, and header absence returning None.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from accounts.authentication import APIKeyAuthentication, hash_api_key
from accounts.factories import AdminUserFactory
from accounts.models import APIKey


class APIKeyAuthenticationTest(TestCase):
    def setUp(self):
        self.user = AdminUserFactory()
        self.factory = APIRequestFactory()
        self.plain_key = 'test-plain-key-1234567890'
        self.api_key = APIKey.objects.create(
            user=self.user,
            name='test-key',
            key_hash=hash_api_key(self.plain_key),
        )

    def _auth(self, key=None):
        req = self.factory.get('/x')
        if key is not None:
            req.META['HTTP_X_API_KEY'] = key
        return APIKeyAuthentication().authenticate(req)

    def test_valid_key_authenticates(self):
        result = self._auth(self.plain_key)
        self.assertIsNotNone(result)
        user, key = result
        self.assertEqual(user, self.user)
        self.assertEqual(key.pk, self.api_key.pk)

    def test_invalid_key_rejected(self):
        with self.assertRaises(AuthenticationFailed):
            self._auth('totally-wrong-key')

    def test_no_header_returns_none(self):
        self.assertIsNone(self._auth(None))

    def test_inactive_key_rejected(self):
        self.api_key.is_active = False
        self.api_key.save()
        with self.assertRaises(AuthenticationFailed):
            self._auth(self.plain_key)

    def test_expired_key_rejected(self):
        self.api_key.expires_at = timezone.now() - timedelta(days=1)
        self.api_key.save()
        with self.assertRaises(AuthenticationFailed):
            self._auth(self.plain_key)

    def test_ip_whitelist_blocks_unlisted_ip(self):
        self.api_key.ip_whitelist = ['1.2.3.4']
        self.api_key.save()
        with self.assertRaises(AuthenticationFailed):
            self._auth(self.plain_key)

    def test_ip_whitelist_allows_listed_ip(self):
        self.api_key.ip_whitelist = ['1.2.3.4']
        self.api_key.save()
        req = self.factory.get('/x', REMOTE_ADDR='1.2.3.4')
        req.META['HTTP_X_API_KEY'] = self.plain_key
        result = APIKeyAuthentication().authenticate(req)
        self.assertIsNotNone(result)

    def test_call_count_increments(self):
        self._auth(self.plain_key)
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.call_count, 1)
