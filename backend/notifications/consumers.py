"""Notification WebSocket consumers for user-scoped real-time streams.

TD-200 (2026-07-18): NotificationConsumer was originally defined in
executions/consumers.py alongside ExecutionConsumer. It has been moved
here because it semantically belongs to the notifications/ business
domain (notifications app already exists with HTTP API for AlertRule;
the WS consumer was the only missing piece). The executions/ app no
longer owns notification-related code.
"""

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone as django_timezone
from gaf_core.mixins.auth import JWTAuthMixin
from gaf_core.tracing.context import current_trace_id

from protocol.constants import FrontendEventType

logger = logging.getLogger(__name__)


def _user_notification_group(user_id):
    """Return the channel-layer group name for a given user's notifications."""
    return f"user_notifications_{user_id}"


class NotificationConsumer(JWTAuthMixin, AsyncWebsocketConsumer):
    """WebSocket consumer that streams user-scoped notifications.

    Path: /ws/notifications/
    Auth: JWT access token via Sec-WebSocket-Protocol or query string.
    """

    async def connect(self):
        user = await self._authenticate()
        if user is None:
            await self.close(code=self.WS_CLOSE_CODE_AUTH_FAILED)
            return

        self.user = user
        self.group_name = _user_notification_group(user.id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        subprotocols = self.scope.get("subprotocols", [])
        chosen = subprotocols[0] if subprotocols else None
        await self.accept(subprotocol=chosen)
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.CONNECTED,
                    "trace_id": current_trace_id.get() or "",
                    "payload": {"status": "ok", "group": self.group_name},
                }
            )
        )
        logger.info(
            "NotificationConsumer connected: user=%s",
            user.username,
        )

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name, self.channel_name
            )

    async def receive(self, text_data=None, bytes_data=None):
        """Notification stream is read-only from the client perspective."""
        pass

    async def notification(self, event):
        """Forward a notification event to the connected client."""
        # spec-29a #31: legacy `data` fallback removed — broadcast_notification
        # already wraps the payload under canonical "payload" key.
        # spec-59-E / TD-297: "type" 改用 FrontendEventType.NOTIFICATION 常量
        # (注意: channels group_send 的 "type": "notification" 是路由到本方法的
        # method name, 语义不同, 不改 — 见 broadcast_notification L97)
        payload = event.get("payload", {})
        await self.send(
            text_data=json.dumps(
                {
                    "type": FrontendEventType.NOTIFICATION,
                    "trace_id": current_trace_id.get() or "",
                    "payload": payload,
                }
            )
        )


async def broadcast_notification(channel_layer, user_id, payload):
    """Helper to broadcast a notification to a specific user.

    Args:
        channel_layer: The Channels channel layer.
        user_id: The target user ID.
        payload: Dictionary with notification data.
    """
    if not payload.get("timestamp"):
        payload["timestamp"] = django_timezone.now().isoformat()
    await channel_layer.group_send(
        _user_notification_group(user_id),
        {
            "type": "notification",
            "payload": payload,
        },
    )
