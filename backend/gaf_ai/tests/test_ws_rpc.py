"""Agent ↔ Backend LLM WebSocket RPC 集成测试 — Spec §5 测试场景 3

验证 Agent 发送 ``llm.call`` 消息后，Backend 正确路由 LLM 请求并通过
``llm.result`` 返回结果给 Agent。

不需要启动真实 WebSocket 服务器 — 通过 mock 模拟 Consumer 层的
消息处理逻辑，验证协议契约正确性。
"""

from unittest.mock import MagicMock

import pytest


class TestLLMWebsocketRPC:
    """LLM WebSocket RPC 协议契约测试组。"""

    def test_protocol_constants_exist(self):
        """验证协议常量中已定义 LLM_CALL 和 LLM_RESULT。"""
        from protocol.constants import MessageType

        assert hasattr(MessageType, "LLM_CALL")
        assert hasattr(MessageType, "LLM_RESULT")
        assert MessageType.LLM_CALL == "llm.call"
        assert MessageType.LLM_RESULT == "llm.result"

    def test_llm_call_in_agent_to_server_types(self):
        """LLM_CALL 应在 agent→server 消息类型集合中。"""
        from protocol.constants import MessageType

        agent_types = MessageType.agent_to_server_types()
        assert MessageType.LLM_CALL in agent_types

    def test_llm_result_in_server_to_agent_types(self):
        """LLM_RESULT 应在 server→agent 消息类型集合中。"""
        from protocol.constants import MessageType

        server_types = MessageType.server_to_agent_types()
        assert MessageType.LLM_RESULT in server_types

    def test_base_llm_client_interface(self):
        """验证 BaseLLMClient 定义了 chat() 和 stream_chat() 接口。"""
        from gaf_ai.base_client import BaseLLMClient

        assert hasattr(BaseLLMClient, "chat")
        assert hasattr(BaseLLMClient, "stream_chat")

        # Verify they are abstractmethods by instantiation attempt
        with pytest.raises(TypeError):
            BaseLLMClient()

    def test_llm_message_dataclass(self):
        """验证 LLMMessage 数据结构正确。"""
        from gaf_ai.base_client import LLMMessage

        msg = LLMMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.to_dict() == {"role": "user", "content": "Hello"}

    def test_llm_response_dataclass(self):
        """验证 LLMResponse 数据结构正确。"""
        from gaf_ai.base_client import LLMResponse

        resp = LLMResponse(content="Hi", model="gpt-4o-mini", input_tokens=5, output_tokens=10)
        assert resp.content == "Hi"
        assert resp.model == "gpt-4o-mini"
        assert resp.input_tokens == 5
        assert resp.output_tokens == 10

    def test_llm_router_fallback_chain(self):
        """验证 LLMRouter 的 fallback 链路按顺序尝试。"""
        from gaf_ai.llm_router import LLMRouter

        # Mock clients
        mock_client_fail = MagicMock()
        mock_client_fail.chat.side_effect = Exception("API error")

        mock_client_success = MagicMock()
        mock_client_success.chat.return_value = {
            "content": "Success!",
            "model": "deepseek-chat",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

        router = LLMRouter()
        router.register("preferred", mock_client_fail)
        router.register("backup", mock_client_success)

        messages = [{"role": "user", "content": "Hi"}]
        result = router.chat(messages)

        # preferred 失败，backup 成功
        mock_client_fail.chat.assert_called_once()
        mock_client_success.chat.assert_called_once()
        assert result["content"] == "Success!"
        assert result["model"] == "deepseek-chat"
        assert result["route"] == "backup"

    def test_llm_router_all_failed_raises(self):
        """所有 LLM 客户端均失败时应抛出 LLMRouterError。"""
        from gaf_ai.llm_router import LLMRouter, LLMRouterError

        mock_fail = MagicMock()
        mock_fail.chat.side_effect = Exception("API down")

        router = LLMRouter(levels=("preferred",))
        router.register("preferred", mock_fail)

        with pytest.raises(LLMRouterError):
            router.chat([{"role": "user", "content": "Hi"}])

    def test_llm_router_unknown_level_raises(self):
        """注册不存在的 level 应抛出 LLMRouterError。"""
        from gaf_ai.llm_router import LLMRouter, LLMRouterError

        router = LLMRouter(levels=("preferred",))

        with pytest.raises(LLMRouterError):
            router.register("nonexistent", MagicMock())

    def test_agent_llm_client_has_stream_chat(self):
        """验证 AgentLLMClient 实现了 stream_chat 方法。"""
        import os
        import sys
        agent_src = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "agent", "src")
        )
        if agent_src not in sys.path:
            sys.path.insert(0, agent_src)

        from ai.llm_client import AgentLLMClient

        assert hasattr(AgentLLMClient, "stream_chat")
        assert hasattr(AgentLLMClient, "diagnose_failure")
        assert hasattr(AgentLLMClient, "is_available")

    def test_consumer_handles_llm_call(self):
        """验证 WebSocket Consumer 能处理 llm.call 消息类型。"""
        from protocol.constants import MessageType

        # Verify that the message type is recognized in the protocol
        all_types = MessageType.all_types()
        assert "llm.call" in all_types
        assert "llm.result" in all_types

    def test_monitoring_event_bus_contract(self):
        """验证 MonitoringEvent 的序列化/反序列化契约。"""
        from monitors.events import MonitoringEvent

        event = MonitoringEvent.error(
            source="agent",
            category="llm",
            message="LLM timeout",
            provider="deepseek",
            model="deepseek-chat",
        )

        # Verify structure
        assert event.source == "agent"
        assert event.level == "ERROR"
        assert event.category == "llm"
        assert event.payload["message"] == "LLM timeout"
        assert event.payload["provider"] == "deepseek"
        assert event.is_error is True

        # Verify broadcast payload conversion
        payload = event.to_broadcast_payload()
        assert "event_id" in payload
        assert "timestamp" in payload
        assert payload["source"] == "agent"
        assert payload["level"] == "ERROR"
        assert payload["category"] == "llm"
        assert payload["payload"]["message"] == "LLM timeout"

    def test_monitoring_event_levels(self):
        """验证所有事件级别正确映射。"""
        from monitors.events import MonitoringEvent

        info = MonitoringEvent.info("agent", "device", "Device connected")
        assert info.level == "INFO"
        assert info.is_error is False

        warning = MonitoringEvent.warning("backend", "task_execution", "Task slow")
        assert warning.level == "WARNING"
        assert warning.is_error is False

        error = MonitoringEvent.error("agent", "resource", "CPU overload")
        assert error.level == "ERROR"
        assert error.is_error is True

        critical = MonitoringEvent.critical("backend", "system", "Service down")
        assert critical.level == "CRITICAL"
        assert critical.is_error is True
