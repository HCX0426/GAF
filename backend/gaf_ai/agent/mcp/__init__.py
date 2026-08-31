"""Lightweight MCP (Model Context Protocol) package for GAF (Phase 2).

Spec: 2026-08-31-ai-tab-agent-learning-spec §Phase 2. Dependency-free,
teaching-grade reimplementation of the core MCP surface:

- :class:`MCPServer` / :class:`MCPToolSpec` / :class:`MCPError` — protocol core
  (see ``_base.py``).
- :class:`MCPClient` — wraps a server's tools as LangChain tools (see
  ``client.py``).
- :class:`GAFMCPServer` — example server exposing GAF log-analysis tools as
  standard MCP tools (see ``gaf_mcp_server.py``).
"""

from ._base import MCPError, MCPServer, MCPToolSpec
from .client import MCPClient
from .gaf_mcp_server import GAFMCPServer

__all__ = [
    'MCPClient',
    'MCPError',
    'GAFMCPServer',
    'MCPServer',
    'MCPToolSpec',
]
