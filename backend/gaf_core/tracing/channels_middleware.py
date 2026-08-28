"""Channels (WebSocket) tracing middleware for trace_id contextvar propagation.

F25 (spec 2026-07-30-debug-directory-restructure): 在 WS 连接建立时从
query string / header 读 ``X-Trace-Id``, 设置 ``current_trace_id`` ContextVar,
让 WS consumer 在 HTTP → WS 全链路中也能拿到 trace_id.

注意: WS 是长连接, per-connection trace_id 语义弱 (一个连接服务多个逻辑请求).
per-event trace_id 才有意义, 需配合 F20 (FrontendConsumer 改用 serialize_frame)
让每条 group_send 事件显式带 trace_id. 本 middleware 仅作为 fallback.
"""

import contextlib
import logging
import uuid

from channels.middleware import BaseMiddleware

from gaf_core.tracing.context import current_trace_id

logger = logging.getLogger(__name__)


class TracingChannelsMiddleware(BaseMiddleware):
    """WebSocket tracing middleware: 从 WS upgrade 请求读 X-Trace-Id, 注入 ContextVar.

    用于 ``ProtocolTypeRouter`` 的 ``websocket`` 路由, 包在
    ``TokenAuthMiddleware`` 外层, 确保 WS consumer 上下文中
    ``current_trace_id`` ContextVar 已设置.
    """

    async def __call__(self, scope, receive, send):
        trace_id = self._extract_trace_id(scope)
        token = current_trace_id.set(trace_id)

        try:
            return await super().__call__(scope, receive, send)
        finally:
            with contextlib.suppress(LookupError, ValueError):
                current_trace_id.reset(token)

    def _extract_trace_id(self, scope) -> str:
        query_string = scope.get("query_string", b"").decode("utf-8")
        if query_string:
            from urllib.parse import parse_qs
            params = parse_qs(query_string)
            trace_ids = params.get("trace_id", [])
            if trace_ids and trace_ids[0]:
                return trace_ids[0]

        headers = dict(scope.get("headers", []))
        for key, value in headers.items():
            if key == b"x-trace-id":
                return value.decode("utf-8")

        return str(uuid.uuid4())
