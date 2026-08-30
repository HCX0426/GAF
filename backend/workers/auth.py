"""Agent token authentication for DRF.

Allows the agent process (started with ``--agent-token``) to authenticate
HTTP calls to the backend using ``Authorization: Bearer <agent-token>``.
The token is stored hashed (``Agent.agent_token_hash``, SHA-256) so the
plaintext is never persisted — we hash the presented token and look it up.

The authenticated principal is attached as ``request.agent`` (an ``Agent``
instance) instead of a Django ``User``. Callers that need to authorize an
agent-only action must use ``IsAgentOrRecordingOwner`` or check
``getattr(request, "agent", None)`` directly.
"""

import logging

from django.contrib.auth.models import AnonymousUser
from gaf_core.utils.tokens import hash_token
from rest_framework import authentication, exceptions

from workers.models import Worker

logger = logging.getLogger(__name__)


class AgentTokenAuthentication(authentication.BaseAuthentication):
    """Authenticate via ``Authorization: Token <agent-token>``.

    Uses the ``Token`` scheme (not ``Bearer``) so it never collides with
    JWT authentication, which reserves ``Bearer``. Sets ``request.agent``
    to the matching ``Agent`` instance and returns (AnonymousUser, None) so
    DRF's permission checks still run. Endpoints that allow agents must use
    a permission class that also accepts ``request.agent`` (e.g.
    ``IsAgentOrRecordingOwner``).
    """

    keyword = "Token"

    def authenticate(self, request):
        auth = authentication.get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None
        if len(auth) != 2:
            raise exceptions.AuthenticationFailed("Malformed Authorization header")
        token = auth[1].decode("utf-8")
        agent = self._lookup_agent(token)
        if agent is None:
            raise exceptions.AuthenticationFailed("Invalid agent token")
        request.agent = agent
        return (AnonymousUser(), None)

    @staticmethod
    def _lookup_agent(token: str):
        digest = hash_token(token)
        try:
            return Worker.objects.get(agent_token_hash=digest)
        except Worker.DoesNotExist:
            return None
