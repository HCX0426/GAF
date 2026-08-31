"""Unified tool registry — single declaration point for agent tools (Phase 2).

Spec: 2026-08-31-ai-tab-agent-learning-spec §Phase 2 — "工具注册表:
``TOOL_REGISTRY`` 集中声明, 支持 ``langchain_tool`` / ``mcp_tool`` 两种类型".

This is the canonical place to declare the tools the agent can call. It
supports two entry ``type`` values:

- ``langchain_tool``: the tool object is itself a LangChain tool (the existing
  ``gaf_ai.agent.tools`` @tool functions, or skill-adapter tools).
- ``mcp_tool``: the tool is exposed by an :class:`MCPClient` (discovered from an
  :class:`MCPServer`). The registry calls ``client.discover_tools()`` lazily.

The registry also carries per-tool metadata (``vision_required``, ``group``)
used by graph builders to do tool-level routing decisions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Entry type discriminators.
LANGCHAIN_TOOL = 'langchain_tool'
MCP_TOOL = 'mcp_tool'


@dataclass
class ToolRegistryEntry:
    """One declarative entry in :data:`TOOL_REGISTRY`."""

    name: str
    type: str
    # For langchain_tool: the LangChain tool object.
    # For mcp_tool: the MCPClient instance (tools discovered lazily).
    obj: Any
    description: str = ''
    vision_required: bool = False
    group: str = 'generic'
    # For mcp_tool: names the MCP client will explicitly discover (all if None).
    mcp_tool_names: list[str] | None = None


@dataclass
class ToolRegistry:
    """Container that resolves a registry of tool entries into a tool list."""

    entries: dict[str, ToolRegistryEntry] = field(default_factory=dict)

    def register(self, entry: ToolRegistryEntry) -> None:
        if entry.name in self.entries:
            logger.warning('ToolRegistry: overwriting %r', entry.name)
        self.entries[entry.name] = entry

    def resolve_tools(self, *, vision_available: bool = True) -> list:
        """Return the flat list of LangChain tool objects to bind.

        Args:
            vision_available: When False, entries with ``vision_required=True``
                are excluded (mirrors the existing per-model vision routing).
        """
        tools: list = []
        for entry in self.entries.values():
            if entry.vision_required and not vision_available:
                logger.debug('ToolRegistry: excluding vision tool %r', entry.name)
                continue
            if entry.type == LANGCHAIN_TOOL:
                tools.append(entry.obj)
            elif entry.type == MCP_TOOL:
                client = entry.obj
                discovered = client.discover_tools()
                if entry.mcp_tool_names:
                    discovered = [
                        t for t in discovered
                        if t.name in entry.mcp_tool_names
                    ]
                tools.extend(discovered)
            else:
                logger.warning(
                    'ToolRegistry: unknown entry type %r for %r',
                    entry.type, entry.name,
                )
        return tools

    @property
    def names(self) -> list[str]:
        return list(self.entries)


# The canonical registry. Populated imperatively so app/tests can extend it.
TOOL_REGISTRY: ToolRegistry = ToolRegistry()
