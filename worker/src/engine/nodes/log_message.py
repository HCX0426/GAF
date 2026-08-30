"""log_message 节点：将消息写入日志 / 控制台

示例节点，演示元数据注册机制的可扩展性：新增节点只需写 py 文件 + 修改 __init__.py import，
不改引擎核心代码（pipeline_engine.py / node.py）。
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.result import AutoResult, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


@register_node(
    "log_message",
    display_name="日志输出",
    category="utility",
    description="将指定消息写入日志文件或控制台，用于调试和审计",
    params_schema={
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "要输出的日志消息，支持 ${var} 变量引用",
            },
            "level": {
                "type": "string",
                "enum": ["debug", "info", "warning", "error"],
                "default": "info",
                "description": "日志级别",
            },
        },
        "required": ["message"],
    },
)
@dataclass
class LogMessageNode(PipelineNode):
    """日志输出节点 — 将消息写入日志"""
    node_type: str = "log_message"

    def execute(self, context: PipelineContext) -> AutoResult:
        """执行日志输出

        Args:
            context: Pipeline 执行上下文

        Returns:
            AutoResult，data 包含消息内容和日志级别
        """
        start = time.monotonic()
        message = self.config.get("message", "")
        level = self.config.get("level", "info")

        # 支持 ${var} 变量引用
        if "${" in message:
            def _resolve_var(m: re.Match) -> str:
                var_name = m.group(1)
                return str(context.get_variable(var_name, m.group(0)))
            message = re.sub(r"\$\{(\w+)\}", _resolve_var, message)

        log_fn = getattr(logger, level, logger.info)
        log_fn("[LogMessage] %s", message)

        elapsed = time.monotonic() - start
        return success_result(
            data={
                "message": message,
                "level": level,
                "logged_at": elapsed,
            },
            elapsed_time=elapsed,
        )
