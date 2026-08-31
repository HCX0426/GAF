"""Example MCP server — exposes GAF log-analysis tools as MCP tools.

Spec: 2026-08-31-ai-tab-agent-learning-spec §Phase 2 — "1 个示例 MCP server
(把 GAF 工具 ``get_execution_detail``/``search_similar_errors`` 暴露为标准
MCP tool)".

This wires the existing @tool functions (from ``gaf_ai.agent.tools``) into the
lightweight :class:`MCPServer` via its JSON-RPC boundary, making them
discoverable as ``tools/list`` MCP tools that any ``MCPClient`` can consume.
It demonstrates the "wrap an internal capability behind the MCP protocol"
pattern without adding the official SDK.
"""

from __future__ import annotations

import logging
from typing import Any

from ._base import MCPServer, MCPToolSpec

logger = logging.getLogger(__name__)


class GAFMCPServer(MCPServer):
    """MCP server exposing GAF's core log-analysis tools as MCP tools."""

    name = 'gaf-tools'

    # Tool → schema mapping for the tools we expose.
    _TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
        'get_execution_detail': {
            'description': (
                'Get execution overview: task name, status, duration, '
                'start/end time, error.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {'execution_id': {'type': 'integer'}},
                'required': ['execution_id'],
            },
        },
        'get_execution_steps': {
            'description': (
                'Get execution step list with status, duration, errors, '
                'and retry count.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {'execution_id': {'type': 'integer'}},
                'required': ['execution_id'],
            },
        },
        'search_similar_errors': {
            'description': (
                'Search past execution errors similar to the given text '
                'via RAG + JSONL fallback.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {'error_text': {'type': 'string'}},
                'required': ['error_text'],
            },
        },
        'get_task_config': {
            'description': (
                'Get task configuration: pipeline JSON, enabled status, '
                'execution mode.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {'task_id': {'type': 'integer'}},
                'required': ['task_id'],
            },
        },
    }

    def __init__(self) -> None:
        super().__init__()
        self._specs: dict[str, MCPToolSpec] = {}
        for name, schema in self._TOOL_SCHEMAS.items():
            self._specs[name] = MCPToolSpec(
                name=name,
                description=schema['description'],
                parameters=schema['parameters'],
            )

    def _list_tools(self) -> list[MCPToolSpec]:
        return list(self._specs.values())

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get('name', '')
        if name not in self._specs:
            raise LookupError(
                f'Unknown tool {name!r} on {self.name}. '
                f'Available: {", ".join(sorted(self._specs))}',
            )
        arguments = params.get('arguments') or {}
        return self._invoke_gaf_tool(name, arguments)

    def _invoke_gaf_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Delegate to the real LangChain @tool and return MCP text content."""
        from gaf_ai.agent.tools import (  # local import: avoid heavy import cycle
            get_execution_detail,
            get_execution_steps,
            get_task_config,
            search_similar_errors,
        )

        impl = {
            'get_execution_detail': get_execution_detail,
            'get_execution_steps': get_execution_steps,
            'search_similar_errors': search_similar_errors,
            'get_task_config': get_task_config,
        }[name]

        raw = impl.invoke(arguments)
        from langchain_core.messages import BaseMessage

        text = raw.content if isinstance(raw, BaseMessage) else raw
        if not isinstance(text, str):
            text = str(text)
        return {'content': [{'type': 'text', 'text': text}]}
