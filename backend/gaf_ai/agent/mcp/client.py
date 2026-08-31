"""MCP client — discovers an ``MCPServer``'s tools as LangChain tools.

Bridge between the lightweight MCP protocol (``mcp/__init__.py``) and the
LangGraph tool executor. The client talks to a server via its JSON-RPC
``handle_message`` boundary and wraps each advertised tool as a
``langchain_core`` ``@tool`` so the uniform ``TOOL_REGISTRY`` can hold both
``langchain_tool`` and ``mcp_tool`` entries transparently.
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from ._base import MCPServer, MCPToolSpec  # noqa: F401  # re-export

logger = logging.getLogger(__name__)


class MCPClient:
    """A lightweight MCP client bound to a single :class:`MCPServer`.

    Args:
        server: The server to discover tools from.
        prefix: Optional name prefix for the wrapped tools to avoid
            collisions inside the unified tool registry.
    """

    def __init__(self, server: MCPServer, *, prefix: str = '') -> None:
        self.server = server
        self.prefix = prefix
        self._tools: list = []

    def discover_tools(self) -> list:
        """Discover the server's tools and wrap each as a LangChain tool."""
        specs = self.server.list_tools()
        wrapped: list = []
        for spec in specs:
            name = spec.name
            full_name = f'{self.prefix}{name}' if self.prefix else name

            @tool
            def mcp_tool(
                arguments: str = '{}',
                _spec: MCPToolSpec = spec,
                _name: str = name,
                _full_name: str = full_name,
            ) -> str:
                """Call an MCP tool. ``arguments`` is a JSON string of kwargs."""
                try:
                    args = json.loads(arguments) if arguments else {}
                except json.JSONDecodeError:
                    args = {}
                response = self.server.handle_message({
                    'jsonrpc': '2.0',
                    'id': 'client-' + _full_name,
                    'method': 'tools/call',
                    'params': {'name': _name, 'arguments': args},
                })
                if 'error' in response:
                    raise RuntimeError(
                        f'MCP tool {_name} failed: {response["error"].get("message")}',
                    )
                content = response.get('result', {}).get('content', [])
                text = '\n'.join(
                    c.get('text', '') for c in content if c.get('type') == 'text'
                )
                return text or 'MCP tool returned no text content.'

            mcp_tool.name = full_name
            mcp_tool.description = spec.description or f'MCP tool: {full_name}'
            wrapped.append(mcp_tool)
        self._tools = wrapped
        logger.info(
            'MCPClient(%s): discovered %d tools', self.server.name, len(wrapped),
        )
        return wrapped

    @property
    def tools(self) -> list:
        return self._tools
