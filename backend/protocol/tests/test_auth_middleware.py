"""TokenAuthMiddleware 单元测试：校验 Token 提取和 Agent 匹配逻辑。"""

import os
from unittest.mock import AsyncMock, MagicMock

from asgiref.sync import async_to_sync
from django.test import TestCase
from gaf_core.utils.tokens import hash_token, make_token_preview

from agents.models import Agent
from protocol.middleware import TokenAuthMiddleware, _is_localhost_bypass_enabled
from protocol.tests import TEST_WS_PATH


class TestTokenAuthMiddleware(TestCase):
    """TokenAuthMiddleware 中间件测试"""

    def setUp(self):
        """初始化测试数据：创建 Agent 记录和中间件实例。"""
        # C4 fix: middleware now queries agent_token_hash (not plaintext agent_token).
        self.plaintext_token = 'test-token-abc123'
        self.agent = Agent.objects.create(
            agent_id='middleware-test-agent',
            hostname='middleware-test',
            agent_token_hash=hash_token(self.plaintext_token),
            agent_token_preview=make_token_preview(self.plaintext_token),
            status=Agent.Status.OFFLINE,
        )
        self.middleware = TokenAuthMiddleware(MagicMock())

    def _make_scope(self, query_string=b'', headers=None):
        """构建模拟的 ASGI scope 字典。

        Args:
            query_string: URL 查询参数字节串
            headers: HTTP 请求头元组列表

        Returns:
            dict: ASGI scope 字典
        """
        scope = {
            'type': 'websocket',
            'query_string': query_string,
            'headers': headers or [],
        }
        return scope

    def _make_send_collector(self):
        """创建 send 收集器，记录 close 事件。

        Returns:
            tuple(AsyncMock, list): send mock 和 close_events 列表
        """
        close_events = []
        send_mock = AsyncMock()

        async def _send(msg):
            close_events.append(msg)

        send_mock.side_effect = _send
        return send_mock, close_events

    def test_extract_token_from_query_string(self):
        """从查询参数中提取 Token"""
        scope = self._make_scope(query_string=b'token=test-token-abc123')
        token = self.middleware._extract_token(scope)
        self.assertEqual(token, 'test-token-abc123')

    def test_extract_token_from_query_string_multiple_params(self):
        """从多参数查询字符串中提取 Token"""
        scope = self._make_scope(query_string=b'foo=bar&token=test-token-abc123&baz=qux')
        token = self.middleware._extract_token(scope)
        self.assertEqual(token, 'test-token-abc123')

    def test_extract_token_from_authorization_header(self):
        """从 Authorization Bearer 请求头中提取 Token"""
        scope = self._make_scope(headers=[
            (b'authorization', b'Bearer test-token-abc123'),
        ])
        token = self.middleware._extract_token(scope)
        self.assertEqual(token, 'test-token-abc123')

    def test_extract_token_from_x_agent_token_header(self):
        """从 X-Agent-Token 自定义请求头中提取 Token"""
        scope = self._make_scope(headers=[
            (b'x-agent-token', b'test-token-abc123'),
        ])
        token = self.middleware._extract_token(scope)
        self.assertEqual(token, 'test-token-abc123')

    def test_extract_token_no_token(self):
        """无 Token 时返回 None"""
        scope = self._make_scope()
        token = self.middleware._extract_token(scope)
        self.assertIsNone(token)

    def test_get_agent_by_token_valid(self):
        """有效 Token 可找到 Agent 记录"""
        result = async_to_sync(self.middleware._get_agent_by_token)('test-token-abc123')
        self.assertEqual(result.agent_id, 'middleware-test-agent')

    def test_get_agent_by_token_invalid(self):
        """无效 Token 返回 None"""
        result = async_to_sync(self.middleware._get_agent_by_token)('nonexistent-token')
        self.assertIsNone(result)

    def test_get_agent_by_token_empty(self):
        """空 Token 返回 None"""
        result = async_to_sync(self.middleware._get_agent_by_token)('')
        self.assertIsNone(result)


class TestLocalhostBypassFlag(TestCase):
    """TD-037: GAF_ALLOW_LOCALHOST_BYPASS env var controls localhost bypass."""

    def _set_env(self, **kwargs):
        """Patch os.environ for the test and restore afterwards."""
        old = dict(os.environ)
        os.environ.update(kwargs)
        self.addCleanup(lambda: os.environ.update(old) or self._clear_env(kwargs))

    def _clear_env(self, kwargs):
        for k in kwargs:
            os.environ.pop(k, None)

    def test_bypass_disabled_by_default(self):
        """When GAF_ALLOW_LOCALHOST_BYPASS is unset, bypass is disabled."""
        os.environ.pop('GAF_ALLOW_LOCALHOST_BYPASS', None)
        self.assertFalse(_is_localhost_bypass_enabled())

    def test_bypass_enabled_with_1(self):
        """GAF_ALLOW_LOCALHOST_BYPASS=1 enables bypass."""
        self._set_env(GAF_ALLOW_LOCALHOST_BYPASS='1')
        self.assertTrue(_is_localhost_bypass_enabled())

    def test_bypass_enabled_with_true(self):
        """GAF_ALLOW_LOCALHOST_BYPASS=true enables bypass (case-insensitive)."""
        self._set_env(GAF_ALLOW_LOCALHOST_BYPASS='TRUE')
        self.assertTrue(_is_localhost_bypass_enabled())

    def test_bypass_disabled_with_empty(self):
        """Empty string disables bypass."""
        self._set_env(GAF_ALLOW_LOCALHOST_BYPASS='')
        self.assertFalse(_is_localhost_bypass_enabled())

    def test_bypass_disabled_with_0(self):
        """GAF_ALLOW_LOCALHOST_BYPASS=0 disables bypass."""
        self._set_env(GAF_ALLOW_LOCALHOST_BYPASS='0')
        self.assertFalse(_is_localhost_bypass_enabled())

    def test_localhost_rejected_when_bypass_disabled(self):
        """TD-037: tokenless localhost connection rejected when bypass off."""
        os.environ.pop('GAF_ALLOW_LOCALHOST_BYPASS', None)
        inner_app = AsyncMock()
        middleware = TokenAuthMiddleware(inner_app)

        scope = {
            'type': 'websocket',
            'path': TEST_WS_PATH,
            'query_string': b'',
            'headers': [],
            'client': ('127.0.0.1', 12345),
        }
        close_events = []
        collected = []

        async def _send(msg):
            collected.append(msg)
            if msg.get('type') == 'websocket.close':
                close_events.append(msg)

        async def _receive():
            return {'type': 'websocket.connect'}

        async_to_sync(middleware)(scope, _receive, _send)
        self.assertTrue(
            any(evt.get('code') == 4003 for evt in close_events),
            f"Expected 4003 close, got: {collected}",
        )
        # Inner app should NOT have been called (connection rejected).
        inner_app.assert_not_called()

    def test_localhost_accepted_when_bypass_enabled_with_local_agent(self):
        """TD-037: tokenless localhost accepted when bypass on + local agent exists."""
        self._set_env(GAF_ALLOW_LOCALHOST_BYPASS='1')
        Agent.objects.create(
            agent_id='local-bypass-test',
            hostname='local-host',
            is_local=True,
            status=Agent.Status.ONLINE,
        )
        inner_app = AsyncMock()
        middleware = TokenAuthMiddleware(inner_app)

        scope = {
            'type': 'websocket',
            'path': TEST_WS_PATH,
            'query_string': b'',
            'headers': [],
            'client': ('127.0.0.1', 12345),
        }
        close_events = []
        collected = []

        async def _send(msg):
            collected.append(msg)
            if msg.get('type') == 'websocket.close':
                close_events.append(msg)

        async def _receive():
            return {'type': 'websocket.connect'}

        async_to_sync(middleware)(scope, _receive, _send)
        # When bypass is enabled and a local agent exists, the middleware
        # should set scope['agent'] and call the inner app (no close event).
        self.assertIn('agent', scope)
        self.assertEqual(len(close_events), 0)
        inner_app.assert_called_once()
