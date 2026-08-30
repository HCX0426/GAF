import logging
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

django.setup()

# GAF_CELERY_MODE=eager 时启动 APScheduler 替代 Celery Beat 处理定时任务,
# 省掉 ~26s 的 Worker + Beat 进程启动时间.
# celery 模式下 (CELERY_TASK_ALWAYS_EAGER=False) 跳过, 由独立 Beat 进程处理.
from config.scheduler import start_scheduler  # noqa: E402

logger = logging.getLogger(__name__)
try:
    start_scheduler()
except Exception:
    logger.exception("APScheduler 启动失败, 定时任务不可用 (继续启动 ASGI)")

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402
from gaf_core.tracing.channels_middleware import TracingChannelsMiddleware  # noqa: E402
from workers.routing import websocket_urlpatterns as agents_ws_urlpatterns  # noqa: E402

from notifications.routing import websocket_urlpatterns as notifications_ws_urlpatterns  # noqa: E402
from protocol.middleware import TokenAuthMiddleware  # noqa: E402
from protocol.routing import websocket_urlpatterns as protocol_ws_urlpatterns  # noqa: E402

# spec-35 Phase 4.1 (2026-07-19): executions_ws_urlpatterns removed —
# /ws/executions/{id}/ was dead code (frontend uses /ws/dashboard for
# execution_step_update and does not subscribe to execution_update).
# executions/routing.py and executions/consumers.py deleted.
websocket_urlpatterns = (
    agents_ws_urlpatterns
    + notifications_ws_urlpatterns
    + protocol_ws_urlpatterns
)

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": TracingChannelsMiddleware(
            TokenAuthMiddleware(
                AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
            ),
        ),
    }
)
