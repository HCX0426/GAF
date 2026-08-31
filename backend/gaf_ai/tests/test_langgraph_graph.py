"""Tests for the hand-written LangGraph StateGraph + MCP (Phase 2).

Spec: 2026-08-31-ai-tab-agent-learning-spec §Phase 2. Coverage:
- Graph build: nodes/edges present, no tool double-registration.
- Router → tools → responder happy path (tool called once, final answer).
- Conditional edge: no tool_calls → responder directly.
- Iteration guard: forces responder after max_iterations.
- Tool exception isolation (a failing tool returns an error ToolMessage, not a crash).
- Unknown tool handling.
- MCP: tools/list + tools/call JSON-RPC; MCPClient discovery; GAFMCPServer exposure.
"""

import pytest
from django.test import SimpleTestCase
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from gaf_ai.agent.langgraph_graph import (
    DEFAULT_MAX_ITERATIONS,
    build_react_graph,
    invoke_react,
    route_after_router,
    route_after_tools,
)
from gaf_ai.agent.mcp import GAFMCPServer, MCPClient
from gaf_ai.agent.tool_registry import (
    LANGCHAIN_TOOL,
    MCP_TOOL,
    ToolRegistry,
    ToolRegistryEntry,
)

pytestmark = pytest.mark.unit


def _ai(tool_calls=None, content='', tool_call_ids=None):
    """Build an AIMessage, with or without tool_calls."""
    msg = AIMessage(content=content)
    if tool_calls:
        msg.tool_calls = tool_calls
    return msg


class ScriptedLLM:
    """A fake LangChain chat model with a scripted answer queue.

    ``scenario`` is a list of strings / callables:
      - 'tool'  → return an AIMessage requesting the named tools
      - 'final' → return an AIMessage with the given final content
      - callable → return its result
    """

    def __init__(self, scenario):
        self.scenario = list(scenario)
        self.raw_llm = self

    def bind_tools(self, tools):
        self.tools = tools
        return self

    def invoke(self, messages):
        step = self.scenario.pop(0) if self.scenario else 'final'
        if callable(step):
            return step(messages)
        if step == 'final':
            return _ai(content='{"summary": "done", "suggestions": ["x"]}')
        # step is a list of tool_call dicts
        calls = step if isinstance(step, list) else [{'name': step, 'args': {}}]
        return _ai(tool_calls=calls, content='thinking')


@tool
def fake_tool(query: str = '') -> str:
    """A test tool that echoes."""
    return f'echo:{query}'


@tool
def boom_tool(value: str = '') -> str:
    """A test tool that raises."""
    raise RuntimeError('boom')


def _build(scenario, max_iterations=DEFAULT_MAX_ITERATIONS):
    llm = ScriptedLLM(scenario)
    graph = build_react_graph(
        llm,
        [fake_tool],
        max_iterations=max_iterations,
        system_prompt='sys',
    )
    return llm, graph


class BuildGraphTest(SimpleTestCase):
    def test_build_creates_three_nodes(self):
        llm, graph = _build(['final'])
        node_names = set(graph.get_graph().nodes)
        self.assertTrue({'router', 'tools', 'responder'} <= node_names)

    def test_build_has_conditional_edges(self):
        llm, graph = _build(['final'])
        edges = graph.get_graph().edges
        edge_pairs = {(e.source, e.target) for e in edges}
        self.assertIn(('router', 'tools'), edge_pairs)
        self.assertIn(('router', 'responder'), edge_pairs)


class RoutingTest(SimpleTestCase):
    def test_route_after_router_with_tool_calls_goes_to_tools(self):
        state = {'messages': [_ai(tool_calls=[{'name': 'fake_tool', 'args': {}}])]}
        self.assertEqual(route_after_router(state), 'tools')

    def test_route_after_router_without_tool_calls_goes_to_responder(self):
        state = {'messages': [_ai(content='final')]}
        self.assertEqual(route_after_router(state), 'responder')

    def test_route_after_tools_loops_below_guard(self):
        state = {'iteration': 1, 'max_iterations': 5}
        self.assertEqual(route_after_tools(state), 'router')

    def test_route_after_tools_forces_responder_at_guard(self):
        state = {'iteration': 5, 'max_iterations': 5}
        self.assertEqual(route_after_tools(state), 'responder')


class GraphExecutionTest(SimpleTestCase):
    def test_happy_path_tool_then_final_answer(self):
        # Router returns tool call, then after tool result returns final answer.
        llm, graph = _build([
            [{'name': 'fake_tool', 'id': 'call_1', 'args': {'query': 'hi'}}],
            'final',
        ])
        result = invoke_react(
            graph, 'analyze this', system_prompt='sys',
        )
        types = [getattr(m, 'type', None) for m in result['messages']]
        self.assertIn('tool', [t for t in types if t])
        # The tools node produced a ToolMessage with the echo result.
        tool_msgs = [m for m in result['messages']
                     if isinstance(m, ToolMessage)]
        self.assertEqual(len(tool_msgs), 1)
        self.assertIn('echo:hi', tool_msgs[0].content)
        # Trajectory recorded both router and tools steps.
        traj_types = [r['type'] for r in result['trajectory']]
        self.assertIn('router', traj_types)
        self.assertIn('tools', traj_types)

    def test_no_tool_call_goes_straight_to_responder(self):
        llm, graph = _build(['final'])
        result = invoke_react(graph, 'hello', system_prompt='sys')
        tool_msgs = [m for m in result['messages'] if isinstance(m, ToolMessage)]
        self.assertEqual(tool_msgs, [])
        traj_types = [r['type'] for r in result['trajectory']]
        self.assertNotIn('tools', traj_types)
        self.assertIn('responder', traj_types)

    def test_iteration_guard_stops_loop(self):
        # LLM keeps requesting the tool forever; guard must force responder.
        infinite = _build([
            [{'name': 'fake_tool', 'id': 'c1', 'args': {}}],
            'final',
        ], max_iterations=2)
        llm, graph = infinite
        # Override: always return tool calls (ignore one-shot queue).
        def always_tools(messages):
            return _ai(tool_calls=[{'name': 'fake_tool', 'id': 'c', 'args': {}}])
        llm.scenario = [always_tools] * 100
        result = invoke_react(graph, 'x', system_prompt='s', max_iterations=2)
        # After guard, responder ran; iteration >= max_iterations.
        self.assertGreaterEqual(result['iteration'], 2)
        self.assertIn('responder', [r['type'] for r in result['trajectory']])

    def test_tool_exception_is_isolated(self):
        @tool
        def gaf_boom(v: str = '') -> str:
            """A boom tool for testing isolation."""
            raise RuntimeError('took the boom tool')
        graph = build_react_graph(
            ScriptedLLM([[{'name': 'gaf_boom', 'id': 'c', 'args': {}}], 'final']),
            [gaf_boom],
            system_prompt='s',
        )
        result = invoke_react(graph, 'x', system_prompt='s')
        tool_msgs = [m for m in result['messages'] if isinstance(m, ToolMessage)]
        self.assertTrue(tool_msgs)
        # The ToolMessage body should be an error envelope, not a raise.
        self.assertIn('error', tool_msgs[0].content)

    def test_unknown_tool_gets_envelope(self):
        llm, graph = _build([
            [{'name': 'no_such_tool', 'id': 'c', 'args': {}}],
            'final',
        ])
        result = invoke_react(graph, 'x', system_prompt='s')
        tool_msgs = [m for m in result['messages'] if isinstance(m, ToolMessage)]
        self.assertTrue(tool_msgs)
        self.assertIn('no_such_tool', tool_msgs[0].content)


class MCPServerTest(SimpleTestCase):
    def setUp(self):
        self.server = GAFMCPServer()

    def test_tools_list_returns_schemas(self):
        resp = self.server.handle_message({
            'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {},
        })
        self.assertNotIn('error', resp)
        names = [t['name'] for t in resp['result']['tools']]
        self.assertIn('get_execution_detail', names)
        self.assertIn('search_similar_errors', names)

    def test_unsupported_method_returns_error(self):
        resp = self.server.handle_message({
            'jsonrpc': '2.0', 'id': 2, 'method': 'bogus', 'params': {},
        })
        self.assertIn('error', resp)

    def test_unknown_tool_call_returns_error(self):
        resp = self.server.handle_message({
            'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
            'params': {'name': 'nope', 'arguments': {}},
        })
        self.assertIn('error', resp)

    def test_gaf_tool_call_extracts_text_content(self):
        # A real GAF @tool invoked via the MCP server must yield its text
        # (regression: str return would previously hit `.content` → AttributeError).
        from unittest.mock import MagicMock, patch

        fake_tool = MagicMock()
        fake_tool.invoke.return_value = '{"status": "ok"}'
        with patch('gaf_ai.agent.tools.get_execution_detail', fake_tool):
            resp = self.server.handle_message({
                'jsonrpc': '2.0', 'id': 9, 'method': 'tools/call',
                'params': {'name': 'get_execution_detail',
                           'arguments': {'execution_id': 1}},
            })
        self.assertNotIn('error', resp)
        text = resp['result']['content'][0]['text']
        self.assertIn('status', text)


class MCPClientTest(SimpleTestCase):
    def test_discover_tools_wraps_server_tools(self):
        server = GAFMCPServer()
        client = MCPClient(server, prefix='mcp_')
        tools = client.discover_tools()
        names = [t.name for t in tools]
        self.assertIn('mcp_get_execution_detail', names)
        self.assertTrue(all(hasattr(t, 'invoke') for t in tools))

    def test_echo_server_round_trip(self):
        from gaf_ai.agent.mcp import MCPServer

        server = MCPServer()
        server.register_tool('echo', lambda text='': f'got:{text}',
                             description='Echo tool',
                             parameters={'type': 'object'})
        resp = server.handle_message({
            'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call',
            'params': {'name': 'echo', 'arguments': {'text': 'yo'}},
        })
        self.assertNotIn('error', resp)
        self.assertIn('got:yo', resp['result']['content'][0]['text'])


class ToolRegistryTest(SimpleTestCase):
    def test_langchain_tool_resolution(self):
        reg = ToolRegistry()
        reg.register(ToolRegistryEntry(
            name='fake', type=LANGCHAIN_TOOL, obj=fake_tool,
        ))
        tools = reg.resolve_tools()
        self.assertEqual([t.name for t in tools], ['fake_tool'])

    def test_mcp_tool_resolution(self):
        reg = ToolRegistry()
        client = MCPClient(GAFMCPServer(), prefix='mcp_')
        reg.register(ToolRegistryEntry(
            name='gaf_mcp', type=MCP_TOOL, obj=client,
        ))
        tools = reg.resolve_tools()
        self.assertTrue(any(t.name == 'mcp_get_execution_detail' for t in tools))

    def test_vision_required_excluded_without_vision(self):
        reg = ToolRegistry()
        reg.register(ToolRegistryEntry(
            name='vis', type=LANGCHAIN_TOOL, obj=fake_tool,
            vision_required=True,
        ))
        self.assertEqual(reg.resolve_tools(vision_available=False), [])
        self.assertEqual(len(reg.resolve_tools(vision_available=True)), 1)
