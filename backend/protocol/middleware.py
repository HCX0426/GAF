"""WebSocket Token 认证中间件：从查询参数或请求头中提取 Agent Token 进行校验。"""

import logging
import os
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from gaf_core.utils.tokens import hash_token

# TD-259 #29: cross-app Agent model import moved into
# protocol.services.* function bodies (inline imports). Middleware
# now delegates to service functions; see protocol/services.py.
from protocol.services import get_agent_by_token_hash, get_local_agent

logger = logging.getLogger(__name__)

WS_CLOSE_CODE_AUTH_FAILED = 4003


def _is_localhost_bypass_enabled() -> bool:
    """Check if localhost token bypass is explicitly enabled.

    TD-037: the localhost bypass (127.0.0.1 + is_local Agent → no token
    required) was previously always on. This created a privilege escalation
    path if an agent ever becomes a relay proxy for other clients. Now the
    bypass is opt-in via the ``GAF_ALLOW_LOCALHOST_BYPASS`` environment
    variable (set to ``1`` or ``true`` to enable). Default: disabled.

    For local development convenience, set
    ``GAF_ALLOW_LOCALHOST_BYPASS=1`` in the backend environment.
    """
    val = os.environ.get('GAF_ALLOW_LOCALHOST_BYPASS', '').strip().lower()
    return val in ('1', 'true', 'yes', 'on')


class TokenAuthMiddleware(BaseMiddleware):
    """WebSocket Token 认证中间件，校验 Agent Token 有效性并注入 scope['agent']。

    校验流程：
    1. 从 WebSocket 连接 URL 查询参数 'token' 中提取 Token
    2. 若查询参数无 Token，则从请求头 'Authorization: Bearer <token>' 中提取
    3. 在数据库中查找匹配的 Agent 记录
    4. 校验通过则设置 scope['agent']，校验失败关闭连接并返回 4003
    """

    async def __call__(self, scope, receive, send):
        """中间件入口，校验 Token 后调用内层应用。

        对于本地 Agent（is_local=True 且来源为 127.0.0.1）允许无 Token 连接。

        Args:
            scope: ASGI scope 字典
            receive: ASGI receive callable
            send: ASGI send callable

        Returns:
            内层应用调用结果
        """
        path = scope.get('path', '')

        # 从 app_info 读取 Agent WebSocket 路径，与环境变量 GAF_WS_AGENT_PATH 同步
        from config.app_info import WS_AGENT_PATH
        _ws_agent_prefix = f"/{WS_AGENT_PATH}"

        if path.startswith('/ws/') and not path.startswith(_ws_agent_prefix):
            return await super().__call__(scope, receive, send)

        token = self._extract_token(scope)

        if token:
            agent = await self._get_agent_by_token(token)
            if agent:
                scope['agent'] = agent
                logger.info("Agent Token 校验通过: agent_id=%s", agent.agent_id)
                return await super().__call__(scope, receive, send)

        client_host = None
        raw_host = scope.get('client', (None, None))
        if isinstance(raw_host, (list, tuple)) and len(raw_host) > 0:
            client_host = raw_host[0]

        is_localhost = client_host in ('127.0.0.1', '::1', 'localhost')

        if is_localhost and _is_localhost_bypass_enabled():
            local_agent = await self._get_local_agent()
            if local_agent:
                scope['agent'] = local_agent
                logger.info(
                    "本地 Agent 免 Token 连接通过 (GAF_ALLOW_LOCALHOST_BYPASS=1): agent_id=%s",
                    local_agent.agent_id,
                )
                return await super().__call__(scope, receive, send)

            # C1 fix: localhost without a registered local Agent must NOT
            # silently pass through with scope['agent'] = None — that allowed
            # any local process to bypass auth and reach AgentConsumer.
            logger.warning("localhost 来源无 Token 且无本地 Agent 记录，拒绝连接 (C1)")
            await send({
                'type': 'websocket.close',
                'code': WS_CLOSE_CODE_AUTH_FAILED,
            })
            return

        if is_localhost and not _is_localhost_bypass_enabled():
            # TD-037: localhost bypass is disabled by default. Reject
            # tokenless localhost connections unless explicitly enabled via
            # GAF_ALLOW_LOCALHOST_BYPASS=1.
            logger.warning(
                "localhost 来源无 Token，localhost 旁路未启用 (GAF_ALLOW_LOCALHOST_BYPASS 未设置)，拒绝连接 (TD-037)"
            )
            await send({
                'type': 'websocket.close',
                'code': WS_CLOSE_CODE_AUTH_FAILED,
            })
            return

        logger.warning("Agent Token 校验失败，关闭连接")
        await send({
            'type': 'websocket.close',
            'code': WS_CLOSE_CODE_AUTH_FAILED,
        })

    def _extract_token(self, scope) -> str | None:
        """从 scope 中提取 Agent Token.

        优先级：查询参数 > 请求头 Authorization Bearer

        Args:
            scope: ASGI scope 字典

        Returns:
            str | None: 提取到的 Token 字符串，未找到则返回 None
        """
        query_string = scope.get('query_string', b'').decode('utf-8')
        if query_string:
            params = parse_qs(query_string)
            tokens = params.get('token', [])
            if tokens:
                return tokens[0]

        headers = dict(scope.get('headers', []))
        for key, value in headers.items():
            if key == b'authorization':
                auth_str = value.decode('utf-8')
                if auth_str.startswith('Bearer '):
                    return auth_str[7:]
                return auth_str
            if key == b'x-agent-token':
                return value.decode('utf-8')

        return None

    @database_sync_to_async
    def _get_agent_by_token(self, token: str):
        """在数据库中根据 Token 查找 Agent 记录.

        Delegates to ``protocol.services.get_agent_by_token_hash``
        (TD-259 #29: cross-app Agent model import isolated in service).

        TD-141 (2026-07-18): legacy `agent_token` plaintext fallback removed
        — agents.0007_agent_token_hash migration already nulled out all
        plaintext tokens, so the fallback never matches. Querying the
        removed column would now raise FieldError.

        Args:
            token: Agent Token 字符串（明文，来自客户端请求）

        Returns:
            Agent | None: 匹配的 Agent 实例，未找到返回 None
        """
        if not token:
            return None
        token_h = hash_token(token)
        return get_agent_by_token_hash(token_h)

    @database_sync_to_async
    def _get_local_agent(self):
        """获取本地 Agent 记录（is_local=True）。
        用于本地免 Token 连接的 Agent 认证。

        Delegates to ``protocol.services.get_local_agent``
        (TD-259 #29: cross-app Agent model import isolated in service).

        Returns:
            Agent | None: 本地 Agent 实例，不存在返回 None
        """
        return get_local_agent()
