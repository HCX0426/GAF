"""PipelineParser 线性模式测试 — spec-2026-07-27-execution-path-unification 阶段 3.

验证无 edges 字段时，PipelineGraph.from_dict 按 nodes 列表顺序自动生成 next 链。
让用户写 ``{"nodes": [...]}`` 即可表达线性 pipeline（吸收 chain schema 简洁性）。
"""
from __future__ import annotations

from engine.parser import PipelineGraph, PipelineParser


class TestParserLinearMode:
    """线性模式：无 edges 时按 nodes 顺序自动链接。"""

    def test_no_edges_multi_nodes_auto_links_sequentially(self):
        """3 节点无 edges → 自动生成 n1→n2→n3 链。"""
        graph = PipelineGraph.from_dict({
            "nodes": [
                {"id": "n1", "node_type": "click", "config": {}},
                {"id": "n2", "node_type": "wait", "config": {"seconds": 1}},
                {"id": "n3", "node_type": "click", "config": {}},
            ],
            # 无 edges
        })

        assert graph.entry_node == "n1"
        # edges 应该有 n1→n2, n2→n3
        assert len(graph.get_outgoing_edges("n1")) == 1
        assert graph.get_outgoing_edges("n1")[0].to_node == "n2"
        assert len(graph.get_outgoing_edges("n2")) == 1
        assert graph.get_outgoing_edges("n2")[0].to_node == "n3"
        # n3 是终点，无后续
        assert graph.get_outgoing_edges("n3") == []

    def test_no_edges_single_node_no_link(self):
        """单节点无 edges → 不生成边，但 entry_node 默认该节点。"""
        graph = PipelineGraph.from_dict({
            "nodes": [{"id": "solo", "node_type": "click", "config": {}}],
        })

        assert graph.entry_node == "solo"
        assert graph.get_outgoing_edges("solo") == []

    def test_no_nodes_empty_graph(self):
        """空 nodes + 空 edges → 空图，entry_node 为空串。"""
        graph = PipelineGraph.from_dict({"nodes": [], "edges": []})

        assert graph.entry_node == ""
        assert len(graph.nodes) == 0

    def test_explicit_edges_take_precedence_over_linear_mode(self):
        """有显式 edges → 不触发线性模式自动链接。"""
        graph = PipelineGraph.from_dict({
            "nodes": [
                {"id": "a", "node_type": "click", "config": {}},
                {"id": "b", "node_type": "click", "config": {}},
                {"id": "c", "node_type": "click", "config": {}},
            ],
            "edges": [{"from": "a", "to": "c"}],  # 跳过 b
        })

        # 只应有 1 条边（a→c），不是线性模式的 a→b→c
        assert len(graph.get_outgoing_edges("a")) == 1
        assert graph.get_outgoing_edges("a")[0].to_node == "c"
        # b 不应被自动链接
        assert graph.get_outgoing_edges("b") == []

    def test_next_node_id_still_works_when_no_edges(self):
        """无显式 edges 但节点有 next_node_id → 走 next_node_id 推断（保留旧行为）。"""
        graph = PipelineGraph.from_dict({
            "nodes": [
                {"id": "x1", "node_type": "click", "config": {}, "next_node_id": "x3"},
                {"id": "x2", "node_type": "click", "config": {}},
                {"id": "x3", "node_type": "click", "config": {}},
            ],
            # 无 edges
        })

        # x1 显式指向 x3（next_node_id 路径优先于线性模式）
        assert len(graph.get_outgoing_edges("x1")) == 1
        assert graph.get_outgoing_edges("x1")[0].to_node == "x3"
        # 因为 next_node_id 路径已生成 edges，线性模式不触发
        # (graph.edges 非空，跳过线性模式分支)
        assert graph.get_outgoing_edges("x2") == []

    def test_entry_node_explicit_not_overridden_by_linear_mode(self):
        """显式 entry_node → 线性模式不覆盖。"""
        graph = PipelineGraph.from_dict({
            "nodes": [
                {"id": "first", "node_type": "click", "config": {}},
                {"id": "second", "node_type": "click", "config": {}},
            ],
            "entry_node": "second",  # 显式从 second 开始
        })

        assert graph.entry_node == "second"

    def test_parse_dict_linear_pipeline_executable(self):
        """端到端：parse_dict 解析线性 pipeline JSON，验证 graph 可被遍历。"""
        graph = PipelineParser.parse_dict({
            "nodes": [
                {"id": "step1", "node_type": "click", "config": {"x": 1, "y": 1}},
                {"id": "step2", "node_type": "wait", "config": {"seconds": 0}},
                {"id": "step3", "node_type": "click", "config": {"x": 2, "y": 2}},
            ],
        })

        # 模拟 engine 遍历
        visited = []
        current = graph.entry_node
        while current:
            visited.append(current)
            next_edges = graph.get_outgoing_edges(current)
            current = next_edges[0].to_node if next_edges else None

        assert visited == ["step1", "step2", "step3"]

    def test_linear_mode_preserves_node_attributes(self):
        """线性模式不丢失节点的其他属性（comment / retry / pre_verify 等）。"""
        graph = PipelineGraph.from_dict({
            "nodes": [
                {"id": "n1", "node_type": "click", "config": {"x": 1, "y": 1},
                 "comment": "第一步", "retry": {"max_retries": 3}},
                {"id": "n2", "node_type": "wait", "config": {"seconds": 1},
                 "pre_verify": {"type": "template"}},
            ],
        })

        n1 = graph.nodes["n1"]
        assert n1.comment == "第一步"
        assert n1.retry == {"max_retries": 3}

        n2 = graph.nodes["n2"]
        assert n2.pre_verify == {"type": "template"}
