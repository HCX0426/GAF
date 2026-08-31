"""Handwritten LangGraph StateGraph — replaces ``create_agent`` (Phase 2).

Spec: 2026-08-31-ai-tab-agent-learning-spec §Phase 2. The goal is to move
from LangChain's high-level ``create_agent`` wrapper to an explicit,
hand-assembled ``StateGraph`` so the ReAct loop is fully under our control
and can be explained/taught. This module is the "how to build a graph by
hand" learning artifact.

Graph layout
------------
```
                    ┌──────────┐  no tool_calls
   START ──────────▶│  router  ├───────────────▶ responder ──▶ END
                    └────┬─────┘
                    tool_calls │
                    ┌─────────▼─────────┐
                    │  tools (execute)  │
                    └─────────┬─────────┘
                              │ iteration < max_iterations  → back to router
                              │ iteration >= max_iterations → responder (guard)
```

State
-----
- ``messages``: full LangChain message list (AIMessage/ToolMessage/HumanMessage).
  Uses langgraph's ``add_messages`` reducer so every node appends.
- ``context``: arbitrary dict threaded through nodes (e.g. execution_id).
- ``iteration``: ReAct loop counter (int, default reducer keeps last/increments).
- ``max_iterations``: guard — stop looping after N iterations to prevent
  runaway tool chains.
- ``trajectory``: list of observability records ``{type, name, ...}`` emitted
  at each node for the frontend trajectory visualizer (Phase 2 frontend).
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

logger = logging.getLogger(__name__)

# Default guard: at most this many tool-call rounds before forcing an answer.
DEFAULT_MAX_ITERATIONS = 6


class AgentState(TypedDict, total=False):
    """Shared state for the handwritten ReAct graph."""

    messages: Annotated[list[BaseMessage], add_messages]
    context: dict[str, Any]
    iteration: int
    max_iterations: int
    trajectory: list[dict[str, Any]]


def _bump_iteration(state: AgentState) -> AgentState:
    """Increment the ReAct loop counter, returning a partial state update."""
    current = state.get('iteration', 0) or 0
    return {'iteration': current + 1}


def _record_trajectory(
    state: AgentState,
    record: dict[str, Any],
) -> dict[str, Any]:
    """Append an observability record without mutating the caller's state dict."""
    trajectory = list(state.get('trajectory', []))
    trajectory.append(record)
    return {'trajectory': trajectory}


def router_node(
    llm: BaseChatModel,
    tools: list,
) -> callable:
    """Build the ``router`` node.

    The router asks the (tool-bound) LLM for the next step. If the LLM
    requests tools we route through the ``tools`` node; otherwise we route
    to the ``responder`` node and produce the final answer. The routing
    decision is expressed by returning the AIMessage content alongside a
    ``__branch`` marker interpreted by ``route_after_router``.
    """

    llm_with_tools = llm.bind_tools(tools)

    def _router(state: AgentState) -> dict[str, Any]:
        messages = state['messages']

        # Inject system prompt as the first message if not already present.
        system_prompt = state.get('context', {}).get('system_prompt', '')
        if system_prompt and not (
            messages
            and getattr(messages[0], 'type', '') == 'system'
        ):
            from langchain_core.messages import SystemMessage

            messages = [SystemMessage(content=system_prompt), *messages]

        response = llm_with_tools.invoke(messages)

        update: dict[str, Any] = {'messages': [response]}
        update.update(_record_trajectory(state, {
            'type': 'router',
            'tool_calls': [
                {'name': tc.get('name'), 'args': tc.get('args', {})}
                for tc in (getattr(response, 'tool_calls', None) or [])
            ],
        }))
        return update

    return _router


def tools_node(tool_map: dict[str, callable]) -> callable:
    """Build the ``tools`` node — dispatch tool_calls to registered tools.

    Exceptions are caught per-call and returned as error envelopes so a
    single failing tool never breaks the ReAct loop (mirrors the existing
    tool exception-isolation discipline).
    """

    def _tools(state: AgentState) -> dict[str, Any]:
        messages = state['messages']
        last_msg = messages[-1] if messages else None
        tool_calls = (
            getattr(last_msg, 'tool_calls', None)
            if isinstance(last_msg, AIMessage)
            else None
        ) or []

        tool_messages: list[ToolMessage] = []
        for tc in tool_calls:
            tool_name = tc['name']
            tool_args = tc.get('args', {})
            func = tool_map.get(tool_name)
            if func is None:
                result = (
                    f"Unknown tool '{tool_name}'. Available tools: "
                    f'{", ".join(sorted(tool_map))}'
                )
                logger.warning('tools_node: unknown tool %r', tool_name)
            else:
                try:
                    raw = func.invoke(tool_args)
                    result = raw.content if isinstance(raw, BaseMessage) else raw
                except Exception as exc:  # noqa: BLE001  # isolate tool failures
                    logger.exception('tools_node: tool %s failed', tool_name)
                    result = json.dumps({
                        'error': 'Tool execution failed',
                        'detail': str(exc),
                        'tool': tool_name,
                    })
            body = result if isinstance(result, str) else str(result)
            tool_messages.append(
                ToolMessage(content=body, tool_call_id=tc['id']),
            )
            logger.debug(
                'tools_node: %s -> %s chars', tool_name, len(body),
            )

        update: dict[str, Any] = {'messages': tool_messages}
        update.update(_record_trajectory(state, {
            'type': 'tools',
            'count': len(tool_calls),
            'names': [tc['name'] for tc in tool_calls],
        }))
        # Guard: every tool round counts toward the iteration cap.
        update.update(_bump_iteration(state))
        return update

    return _tools


def responder_node(llm: BaseChatModel) -> callable:
    """Build the ``responder`` node — produce the final user-facing answer.

    Re-invokes the LLM *without* tools to force a plain (non-tool-calling)
    final answer. This keeps the final message free of tool_calls so the
    downstream parser in ``gaf_ai.tasks`` reliably picks it up.
    """

    def _responder(state: AgentState) -> dict[str, Any]:
        messages = state['messages']
        system_prompt = state.get('context', {}).get('system_prompt', '')
        final = llm.invoke(messages)

        # If the model still emitted tool_calls (stubborn), retry once with a
        # strong instruction, then accept whatever it returns.
        if getattr(final, 'tool_calls', None):
            from langchain_core.messages import SystemMessage

            retry_prompt = (
                'You MUST answer now without calling any tool. '
                'Return only the final JSON per the system instructions.'
            )
            try:
                retried = llm.invoke([
                    *messages,
                    SystemMessage(content=retry_prompt),
                ])
            except Exception:  # noqa: BLE001  # keep original answer on retry failure
                retried = None
            if retried is not None:
                final = retried
        _ = system_prompt

        update: dict[str, Any] = {'messages': [final]}
        update.update(_record_trajectory(state, {
            'type': 'responder',
        }))
        return update

    return _responder


def route_after_router(state: AgentState) -> str:
    """Conditional edge from ``router``: tools round vs final answer."""
    messages = state['messages']
    last_msg = messages[-1] if messages else None
    if isinstance(last_msg, AIMessage) and getattr(last_msg, 'tool_calls', None):
        return 'tools'
    return 'responder'


def route_after_tools(state: AgentState) -> str:
    """Conditional edge from ``tools``: keep looping or force the answer."""
    if state.get('iteration', 0) >= state.get('max_iterations', DEFAULT_MAX_ITERATIONS):
        logger.info(
            'langgraph: iteration guard hit (%s), forcing responder',
            state.get('iteration'),
        )
        return 'responder'
    return 'router'


def build_react_graph(
    llm: BaseChatModel,
    tools: list,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    system_prompt: str = '',
):
    """Assemble and compile the handwritten ReAct ``StateGraph``.

    Args:
        llm: LangChain chat LLM (tool-call capable).
        tools: List of LangChain tools (from ``TOOL_REGISTRY`` or the
            existing ``gaf_ai.agent.tools`` / skill adapter).
        max_iterations: ReAct loop guard (default 6).
        system_prompt: Optional system prompt included in ``context`` so
            the router injects it on the first pass.

    Returns:
        A compiled ``CompiledStateGraph`` whose ``.invoke`` accepts
        ``{"messages": [...], "context": {...}}``.
    """
    tool_map = {getattr(t, 'name', ''): t for t in tools if getattr(t, 'name', '')}

    builder = StateGraph(AgentState)
    builder.add_node(
        'router',
        router_node(llm, list(tool_map.values())),
    )
    builder.add_node('tools', tools_node(tool_map))
    builder.add_node('responder', responder_node(llm))

    builder.add_edge(START, 'router')
    builder.add_conditional_edges(
        'router',
        route_after_router,
        {'tools': 'tools', 'responder': 'responder'},
    )
    builder.add_conditional_edges(
        'tools',
        route_after_tools,
        {'router': 'router', 'responder': 'responder'},
    )
    builder.add_edge('responder', END)

    return builder.compile()


def invoke_react(
    graph,
    user_message: str,
    *,
    system_prompt: str = '',
    context: dict[str, Any] | None = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> dict[str, Any]:
    """Convenience wrapper: build-once graph can be invoked with a plain string.

    Args:
        graph: A compiled graph from :func:`build_react_graph`.
        user_message: Plain user text.
        system_prompt: System prompt to seed ``context``.
        context: Extra state to thread (default {}).
        max_iterations: Overrides the graph's guard for this call.

    Returns:
        The full final state dict (messages + trajectory + iteration etc.).
    """
    return graph.invoke({
        'messages': [HumanMessage(content=user_message)],
        'context': {
            'system_prompt': system_prompt,
            **(context or {}),
        },
        'iteration': 0,
        'max_iterations': max_iterations,
        'trajectory': [],
    }, config={'recursion_limit': 100})
