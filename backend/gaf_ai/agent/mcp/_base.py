"""MCP base types — minimal Model Context Protocol core (no external SDK).

Spec: 2026-08-31-ai-tab-agent-learning-spec §Phase 2. The gaf env does not
ship the official ``mcp`` Python SDK (deliberate "少依赖 + 学习协议" choice,
see spec §3 framework selection). This module is a minimal, dependency-free
reimplementation of the *core* MCP surface we need here:

- ``MCPServer``: a named provider of tools/resources exposed over a JSON-RPC
  2.0 style message protocol (``tools/list`` / ``tools/call``).
- ``MCPToolSpec``: static tool schema.
- ``MCPError``: protocol-level errors.

This is intentionally a *teaching* protocol — every message shape mirrors the
real MCP JSON-RPC framing (id, method, params, result/error) so the concepts
port 1:1 to the official SDK when/if we adopt it. Transport here is in-process
(callables), not streamable-HTTP/stdio; that layering is left for a follow-up.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """Raised when an MCP server call fails at the protocol level."""


@dataclass
class MCPToolSpec:
    """Static description of one MCP tool (OpenAPI-lite schema)."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_jsonrpc(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'description': self.description,
            'parameters': self.parameters,
        }


class MCPServer:
    """Base class for an MCP server exposing tools over a JSON-RPC message loop.

    Subclasses implement :meth:`_list_tools` and :meth:`_call_tool` (or reuse
    :meth:`register_tool`). The public ``handle_message`` method is the
    transport boundary: given a JSON-RPC request dict it returns a JSON-RPC
    response dict, exactly like a real server endpoint would.
    """

    name: str = 'base-mcp-server'

    def __init__(self) -> None:
        self._registry: dict[str, callable] = {}

    # ── tool registration / introspection ──────────────────────────────

    def register_tool(
        self,
        name: str,
        func: callable,
        *,
        description: str = '',
        parameters: dict[str, Any] | None = None,
    ) -> MCPToolSpec:
        """Register a plain callable as an MCP tool."""
        spec = MCPToolSpec(
            name=name,
            description=description or getattr(func, '__doc__', '') or '',
            parameters=parameters or {},
        )
        self._registry[name] = func
        return spec

    def list_tools(self) -> list[MCPToolSpec]:
        return [self._spec(s) for s in self._list_tools()]

    def _list_tools(self) -> list[Any]:
        # Subclasses should override; default reflects the registry.
        return list(self._registry.values())

    def _spec(self, raw: Any) -> MCPToolSpec:
        if isinstance(raw, MCPToolSpec):
            return raw
        return MCPToolSpec(
            name=raw.get('name', 'tool'),
            description=raw.get('description', ''),
            parameters=raw.get('parameters', {}),
        )

    # ── JSON-RPC message body ──────────────────────────────────────────

    def handle_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Handle a single JSON-RPC request dict; return a JSON-RPC result dict.

        Supports methods:
          - ``tools/list`` → ``{"tools": [...]}``
          - ``tools/call``  with ``{"name": ..., "arguments": {...}}``
        """
        req_id = msg.get('id', uuid.uuid4().hex)
        method = msg.get('method', '')
        params = msg.get('params') or {}

        try:
            if method == 'tools/list':
                payload = {'tools': [t.to_jsonrpc() for t in self.list_tools()]}
            elif method == 'tools/call':
                payload = self._call_tool(params)
            else:
                raise MCPError(f'Unsupported method: {method}')
            return {'jsonrpc': '2.0', 'id': req_id, 'result': payload}
        except Exception as exc:  # noqa: BLE001  # protocol error envelope
            logger.exception('MCP %s: error handling %s', self.name, method)
            return {
                'jsonrpc': '2.0',
                'id': req_id,
                'error': {'code': -32000, 'message': str(exc)},
            }

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get('name', '')
        arguments = params.get('arguments') or {}
        if name not in self._registry:
            raise MCPError(
                f'Unknown tool {name!r} on {self.name}. '
                f'Available: {", ".join(sorted(self._registry))}',
            )
        result = self._registry[name](**arguments)
        if not isinstance(result, str):
            result = json.dumps(result, ensure_ascii=False, default=str)
        return {'content': [{'type': 'text', 'text': result}]}
