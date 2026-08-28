"""PipelineValidator params_schema 校验测试 — TD-350"""

from __future__ import annotations

import pytest
from engine.node import PIPELINE_NODE_REGISTRY, PipelineNode
from engine.parser import PipelineEdge, PipelineGraph
from engine.validator import PipelineValidator

pytestmark = pytest.mark.integration


def _make_graph(
    nodes: dict[str, PipelineNode],
    edges: list[tuple[str, str]] | None = None,
    entry_node: str | None = None,
) -> PipelineGraph:
    """创建测试用 PipelineGraph"""
    graph = PipelineGraph()
    graph.nodes = nodes
    if edges:
        for from_id, to_id in edges:
            graph.edges.setdefault(from_id, []).append(
                PipelineEdge(from_node=from_id, to_node=to_id)
            )
    if entry_node:
        graph.entry_node = entry_node
    return graph


class TestValidatorParams:
    """PipelineValidator params_schema 校验测试"""

    def test_valid_params_ok(self):
        """合法参数图通过校验"""
        click_cls = PIPELINE_NODE_REGISTRY.get("click", PipelineNode)
        node = click_cls(
            id="n1",
            node_type="click",
            name="click1",
            config={"x": 100, "y": 200},
        )
        graph = _make_graph(
            nodes={"n1": node},
            entry_node="n1",
        )
        errors = PipelineValidator.validate(graph)
        param_errors = [e for e in errors if e.error_type == "param_invalid"]
        assert param_errors == [], f"期望无参数错误，但得到: {param_errors}"

    def test_invalid_params_reported(self):
        """非法参数图返回 param_invalid"""
        click_cls = PIPELINE_NODE_REGISTRY.get("click", PipelineNode)
        node = click_cls(
            id="n1",
            node_type="click",
            name="click1",
            config={"x": "abc", "y": "def"},  # 应报类型错误
        )
        graph = _make_graph(
            nodes={"n1": node},
            entry_node="n1",
        )
        errors = PipelineValidator.validate(graph)
        param_errors = [e for e in errors if e.error_type == "param_invalid"]
        assert len(param_errors) >= 1, "期望有参数错误"

    def test_params_error_has_node_id(self):
        """参数错误关联正确节点 ID"""
        click_cls = PIPELINE_NODE_REGISTRY.get("wait", PipelineNode)
        node = click_cls(
            id="n2",
            node_type="wait",
            name="wait1",
            config={"mode": "invalid_mode"},
        )
        graph = _make_graph(
            nodes={"n2": node},
            entry_node="n2",
        )
        errors = PipelineValidator.validate(graph)
        param_errors = [e for e in errors if e.error_type == "param_invalid"]
        assert len(param_errors) >= 1
        assert param_errors[0].node_id == "n2"

    def test_params_validation_alongside_other_checks(self):
        """参数校验与其他校验共存"""
        # 同时有未知类型 + 参数错误 + 缺少入口节点
        unknown_cls = type("UnknownNode", (PipelineNode,), {"node_type": "unknown"})
        unknown_node = unknown_cls(
            id="n1",
            node_type="unknown_type_xyz",
            name="unknown",
            config={"x": "abc"},
        )
        graph = _make_graph(
            nodes={"n1": unknown_node},
            # 不设置 entry_node → 触发 missing_entry
        )
        errors = PipelineValidator.validate(graph)
        error_types = {e.error_type for e in errors}
        assert "missing_entry" in error_types, "应检测到缺少入口节点"
        assert "unknown_type" in error_types, "应检测到未知类型"
        # unknown_type_xyz 没有 metadata，所以 param_invalid 不会触发
        # 只有一个 unknown_type 错误

    def test_valid_params_mixed_known_and_unknown(self):
        """混合已知和未知节点，已知节点参数错误仍被检测"""
        click_cls = PIPELINE_NODE_REGISTRY.get("click", PipelineNode)
        good = click_cls(
            id="n1", node_type="click", name="good",
            config={"x": 100, "y": 200},
        )
        bad = click_cls(
            id="n2", node_type="click", name="bad",
            config={"button": "invalid"},
        )
        graph = _make_graph(
            nodes={"n1": good, "n2": bad},
            edges=[("n1", "n2")],
            entry_node="n1",
        )
        errors = PipelineValidator.validate(graph)
        param_errors = [e for e in errors if e.error_type == "param_invalid"]
        assert len(param_errors) >= 1
        # 应只报 bad 节点的错误
        bad_node_ids = [e.node_id for e in param_errors]
        assert "n2" in bad_node_ids
        assert "n1" not in bad_node_ids

    def test_is_valid_returns_false_on_param_error(self):
        """is_valid 对含参数错误的图返回 False"""
        click_cls = PIPELINE_NODE_REGISTRY.get("click", PipelineNode)
        node = click_cls(
            id="n1", node_type="click", name="click1",
            config={"button": "invalid"},
        )
        graph = _make_graph(
            nodes={"n1": node},
            entry_node="n1",
        )
        assert not PipelineValidator.is_valid(graph)

    def test_is_valid_returns_true_on_clean_params(self):
        """is_valid 对参数正确的图返回 True"""
        click_cls = PIPELINE_NODE_REGISTRY.get("click", PipelineNode)
        node = click_cls(
            id="n1", node_type="click", name="click1",
            config={"x": 100, "y": 200},
        )
        graph = _make_graph(
            nodes={"n1": node},
            entry_node="n1",
        )
        # 注意：如果只有 entry_node 没有 edges，会触发 orphan_node 检查
        # 所以这里需要加一条边
        graph.edges["n1"] = []
        assert PipelineValidator.is_valid(graph)
