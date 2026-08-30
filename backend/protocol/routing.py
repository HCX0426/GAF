"""protocol 应用 ASGI WebSocket 路由映射。"""

from django.urls import path

from config.app_info import WS_AGENT_PATH
from protocol.consumers import FrontendConsumer, LogStreamConsumer, WorkerConsumer

websocket_urlpatterns = [
    path(f"{WS_AGENT_PATH}", WorkerConsumer.as_asgi()),
    path("ws/dashboard/", FrontendConsumer.as_asgi()),
    # Real-time log stream for LogCenterPage: DatabaseLogHandler writes
    # LogEntry records and broadcasts to LOGS_GROUP; LogStreamConsumer
    # echoes them to browser subscribers.
    path("ws/logs/", LogStreamConsumer.as_asgi()),
]
