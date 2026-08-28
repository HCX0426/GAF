"""Shared authentication mixins for WebSocket consumers.

Extracted from ``protocol/consumers.py`` so that other apps (e.g.
``executions``) can reuse the JWT handshake without importing from the
``protocol`` app, decoupling consumer inheritance from the protocol layer.
"""

import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()
logger = logging.getLogger(__name__)


class JWTAuthMixin:
    """WebSocket JWT access-token extraction and verification mixin.

    Provides ``_authenticate()``, ``_extract_access_token()`` and
    ``_verify_access_token()`` so consumers can share the same JWT handshake
    logic used by ``FrontendConsumer``.
    """

    WS_CLOSE_CODE_AUTH_FAILED = 4003

    async def _authenticate(self):
        """Extract and verify the JWT access token, returning the user or None."""
        token = self._extract_access_token()
        if not token:
            return None
        return await self._verify_access_token(token)

    def _extract_access_token(self):
        """Extract JWT access token from the WebSocket handshake.

        C8 fix: prefer ``Sec-WebSocket-Protocol`` subprotocol ``access.<jwt>``
        (avoids leaking token via URL query string in logs/history/referrer).
        Fall back to ``?token=`` / ``?access=`` query string for legacy clients.
        """
        # 1. Subprotocol: 'access.<jwt>'
        for proto in self.scope.get("subprotocols", []):
            if proto.startswith("access."):
                return proto[len("access.") :]
        # 2. Legacy: query string
        query_string = self.scope.get("query_string", b"").decode("utf-8")
        if not query_string:
            return None
        params = parse_qs(query_string)
        for key in ("token", "access"):
            values = params.get(key, [])
            if values:
                return values[0]
        return None

    @database_sync_to_async
    def _verify_access_token(self, token):
        """Validate SimpleJWT Access Token and return user, or None on failure."""
        try:
            validated = AccessToken(token)
            user_id = validated["user_id"]
            return User.objects.get(pk=user_id)
        except (InvalidToken, TokenError, User.DoesNotExist):
            return None
        except Exception:  # pragma: no cover — defensive guard
            logger.warning("JWT verification raised unexpectedly", exc_info=True)
            return None
