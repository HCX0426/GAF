from django.urls import re_path

from agents.consumers import AdbLogStreamConsumer
from config.app_info import WS_DEVICES_PATH

# spec-35 Phase 4.2 (2026-07-19): ScreenshotStreamConsumer + the
# /ws/devices/{id}/screenshot-stream/ route removed — the frontend
# receives screenshot frames via /ws/dashboard (FrontendConsumer
# forwards screenshot_frame events), so this consumer was dead code.

# TD-366: device-level WS path driven by GAF_WS_DEVICES_PATH env
# (synced with frontend VITE_WS_DEVICES_PATH).
websocket_urlpatterns = [
    re_path(rf'^{WS_DEVICES_PATH}(?P<device_id>[^/]+)/adb-logs/$', AdbLogStreamConsumer.as_asgi()),
]
