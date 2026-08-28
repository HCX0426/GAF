"""notifications ASGI WebSocket routing mapping.

TD-200 (2026-07-18): routing moved here from executions/routing.py —
NotificationConsumer semantically belongs to the notifications/ business
domain. executions/routing.py now only owns /ws/executions/{id}/.
"""

from django.urls import re_path

from notifications.consumers import NotificationConsumer

websocket_urlpatterns = [
    re_path(r"ws/notifications/$", NotificationConsumer.as_asgi()),
]
