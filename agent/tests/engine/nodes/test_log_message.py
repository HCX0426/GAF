"""log_message 节点测试 — TD-350"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from engine.node import PIPELINE_NODE_REGISTRY
from engine.nodes.log_message import LogMessageNode

pytestmark = pytest.mark.integration


def _make_context(variables: dict | None = None):
    """创建测试用 PipelineContext（MagicMock）"""
    ctx = MagicMock()
    ctx.device = None
    ctx.get_variable = MagicMock(side_effect=lambda k, d=None: (variables or {}).get(k, d))
    ctx.set_variable = MagicMock()
    return ctx


class TestLogMessageNode:
    """LogMessageNode 执行测试"""

    def test_log_message_info(self):
        """info 级别日志写入"""
        node = LogMessageNode(
            id="log1",
            node_type="log_message",
            name="log1",
            config={"message": "hello world", "level": "info"},
        )
        ctx = _make_context()

        with patch("engine.nodes.log_message.logger") as mock_logger:
            result = node.execute(ctx)

        assert result.success
        assert result.data["message"] == "hello world"
        assert result.data["level"] == "info"
        mock_logger.info.assert_called_once_with("[LogMessage] %s", "hello world")

    def test_log_message_variable_resolve(self):
        """${var} 变量引用正确解析"""
        node = LogMessageNode(
            id="log2",
            node_type="log_message",
            name="log2",
            config={"message": "count=${click_count}", "level": "info"},
        )
        ctx = _make_context(variables={"click_count": 42})

        with patch("engine.nodes.log_message.logger") as mock_logger:
            result = node.execute(ctx)

        assert result.success
        assert result.data["message"] == "count=42"
        mock_logger.info.assert_called_once_with("[LogMessage] %s", "count=42")

    def test_log_message_debug_level(self):
        """debug 级别日志写入"""
        node = LogMessageNode(
            id="log3",
            node_type="log_message",
            name="log3",
            config={"message": "debug msg", "level": "debug"},
        )
        ctx = _make_context()

        with patch("engine.nodes.log_message.logger") as mock_logger:
            result = node.execute(ctx)

        assert result.success
        mock_logger.debug.assert_called_once_with("[LogMessage] %s", "debug msg")

    def test_log_message_default_level(self):
        """未指定 level 时默认 info"""
        node = LogMessageNode(
            id="log4",
            node_type="log_message",
            name="log4",
            config={"message": "default level"},
        )
        ctx = _make_context()

        with patch("engine.nodes.log_message.logger") as mock_logger:
            result = node.execute(ctx)

        assert result.success
        assert result.data["level"] == "info"
        mock_logger.info.assert_called_once_with("[LogMessage] %s", "default level")

    def test_log_message_warning_level(self):
        """warning 级别日志写入"""
        node = LogMessageNode(
            id="log5",
            node_type="log_message",
            name="log5",
            config={"message": "warn msg", "level": "warning"},
        )
        ctx = _make_context()

        with patch("engine.nodes.log_message.logger") as mock_logger:
            result = node.execute(ctx)

        assert result.success
        mock_logger.warning.assert_called_once_with("[LogMessage] %s", "warn msg")

    def test_log_message_error_level(self):
        """error 级别日志写入"""
        node = LogMessageNode(
            id="log6",
            node_type="log_message",
            name="log6",
            config={"message": "err msg", "level": "error"},
        )
        ctx = _make_context()

        with patch("engine.nodes.log_message.logger") as mock_logger:
            result = node.execute(ctx)

        assert result.success
        mock_logger.error.assert_called_once_with("[LogMessage] %s", "err msg")

    def test_log_message_registered_in_registry(self):
        """log_message 节点类型在 PIPELINE_NODE_REGISTRY 中"""
        assert "log_message" in PIPELINE_NODE_REGISTRY
        assert PIPELINE_NODE_REGISTRY["log_message"] is LogMessageNode
