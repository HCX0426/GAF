"""APIKey DRF authentication backend (TD-424).

Implements the API-key auth contract so external callers can be
authenticated against ``accounts.APIKey`` — sha256 ``key_hash`` match +
``is_active`` + expiry + IP whitelist + ``call_count`` increment.

**Intentionally NOT wired into ``DEFAULT_AUTHENTICATION_CLASSES`` yet.**
The platform is not open to external callers (TD-424 decision). To expose
a public endpoint, add ``APIKeyAuthentication`` to that view's
``authentication_classes`` (composable with the JWT classes).

Header contract::

    X-API-Key: <plain_key>          # plain key issued on create

Key generation/storage (see ``APIKeySerializer.create``): plain key =
``secrets.token_urlsafe(32)``, stored as ``sha256(plain_key).hexdigest()``.
"""

import hashlib
import logging

from django.db.models import F
from django.utils import timezone
from rest_framework import authentication, exceptions

from accounts.models import APIKey

logger = logging.getLogger(__name__)

HEADER_NAME = 'X-API-Key'


def hash_api_key(plain_key: str) -> str:
    """Hash a plain API key the same way APIKeySerializer.create does."""
    return hashlib.sha256(plain_key.encode()).hexdigest()


class APIKeyAuthentication(authentication.BaseAuthentication):
    """DRF authentication backend backed by ``accounts.APIKey``."""

    keyword = 'ApiKey'

    def authenticate(self, request):
        header = f'HTTP_{HEADER_NAME.upper().replace("-", "_")}'
        plain_key = request.META.get(header)
        if not plain_key:
            return None
        return self._authenticate_credentials(request, plain_key)

    def _authenticate_credentials(self, request, plain_key: str):
        try:
            api_key = APIKey.objects.select_related('user').get(
                key_hash=hash_api_key(plain_key),
                is_active=True,
            )
        except APIKey.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid API key') from None

        # Expiry check.
        if api_key.expires_at and api_key.expires_at < timezone.now():
            raise exceptions.AuthenticationFailed('API key has expired')

        # IP whitelist (empty = allow all).
        whitelist = api_key.ip_whitelist or []
        if whitelist:
            from gaf_core.audit_constants import get_client_ip
            client_ip = get_client_ip(request)
            if client_ip and client_ip not in whitelist:
                raise exceptions.AuthenticationFailed('IP address not allowed')

        # Increment call_count (best-effort, never blocks auth).
        try:
            APIKey.objects.filter(pk=api_key.pk).update(call_count=F('call_count') + 1)
        except Exception as exc:  # noqa: BLE001
            logger.warning('APIKey call_count increment failed: %s', exc)

        return (api_key.user, api_key)

    def authenticate_header(self, request):
        return f'{self.keyword} realm="api"'
