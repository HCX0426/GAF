"""WebSocket consumer tests for /ws/notifications/ endpoint.

TD-200 (2026-07-18): TestNotificationConsumer class migrated here from
executions/tests/test_consumers.py — NotificationConsumer now lives in
notifications/consumers.py so its tests live alongside it.
"""

import json

from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from notifications.consumers import NotificationConsumer

User = get_user_model()


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestNotificationConsumer(TestCase):
    """Tests for /ws/notifications/ endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="test_notify_user",
            email="notify@test.com",
            password="TestPass123!",
        )

    def _patch_auth(self):
        """Bypass JWT verification for unit tests."""
        user = self.user

        async def _mock_verify(consumer, token):
            return user

        NotificationConsumer._verify_access_token = _mock_verify

    async def test_connect_requires_token(self):
        """Connection is rejected when no token is provided."""
        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(),
            "/ws/notifications/",
        )
        communicator.scope["subprotocols"] = []
        communicator.scope["query_string"] = b""
        connected, _ = await communicator.connect()
        self.assertFalse(connected)
        await communicator.disconnect()

    async def test_connect_welcome_message(self):
        """Successful connection returns a canonical connected frame."""
        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(),
            "/ws/notifications/",
        )
        communicator.scope["subprotocols"] = []
        communicator.scope["query_string"] = b"token=dummy"
        self._patch_auth()
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], "connected")
        self.assertIn("payload", data)
        self.assertEqual(data["payload"]["status"], "ok")

        await communicator.disconnect()

    async def test_receives_notification_broadcast(self):
        """Consumer forwards notification events sent to the user's group."""
        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(),
            "/ws/notifications/",
        )
        communicator.scope["subprotocols"] = []
        communicator.scope["query_string"] = b"token=dummy"
        self._patch_auth()
        await communicator.connect()
        await communicator.receive_from()

        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            f"user_notifications_{self.user.id}",
            {
                "type": "notification",
                "payload": {"level": "info", "message": "hello"},
            },
        )

        response = await communicator.receive_from()
        data = json.loads(response)
        self.assertEqual(data["type"], "notification")
        self.assertIn("payload", data)
        self.assertEqual(data["payload"]["message"], "hello")

        await communicator.disconnect()
