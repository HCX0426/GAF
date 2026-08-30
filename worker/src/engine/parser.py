"""PipelineParser：Pipeline JSON 解析器，支持 MaaFramework 扩展协议"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from engine.node import PIPELINE_NODE_REGISTRY, PipelineNode

logger = logging.getLogger(__name__)


@dataclass
class PipelineEdge:
    """Pipeline 图中的边，表示节点间的流转关系

    Attributes:
        from_node: 源节点 ID
        to_node: 目标节点 ID
        label: 边标签（用于条件分支标记，如 "true"、"false"）
        condition: 条件表达式（可选）
    """

    from_node: str
    to_node: str
    label: str = ""
    condition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        result: dict[str, Any] = {
            "from": self.from_node,
            "to": self.to_node,
        }
        if self.label:
            result["label"] = self.label
        if self.condition:
            result["condition"] = self.condition
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineEdge:
        """从字典创建边

        支持三种字段命名约定：
        - MaaFramework: {"from": "...", "to": "..."}
        - 旧版: {"from_node": "...", "to_node": "..."}
        - React Flow (后端 graph_data): {"source": "...", "target": "..."}
        """
        return cls(
            from_node=data.get("from", data.get("from_node", data.get("source", ""))),
            to_node=data.get("to", data.get("to_node", data.get("target", ""))),
            label=data.get("label", data.get("sourceHandle", "")),
            condition=data.get("condition"),
        )


@dataclass
class PipelineGraph:
    """Pipeline 有向图

    Attributes:
        nodes: 节点映射表 (id -> PipelineNode)
        edges: 边映射表 (from_node_id -> List[PipelineEdge])
        entry_node: 入口节点 ID
        metadata: 元数据（如 Pipeline 名称、版本等）
    """

    nodes: dict[str, PipelineNode] = field(default_factory=dict)
    edges: dict[str, list[PipelineEdge]] = field(default_factory=dict)
    entry_node: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_node(self, node_id: str) -> PipelineNode | None:
        """按 ID 获取节点

        Args:
            node_id: 节点 ID

        Returns:
            PipelineNode 或 None
        """
        return self.nodes.get(node_id)

    def get_outgoing_edges(self, node_id: str) -> list[PipelineEdge]:
        """获取节点的出边列表

        Args:
            node_id: 节点 ID

        Returns:
            出边列表
        """
        return self.edges.get(node_id, [])

    def get_next_node_id(self, node_id: str) -> str | None:
        """获取节点的下一个节点 ID（默认边）

        Args:
            node_id: 节点 ID

        Returns:
            下一个节点 ID 或 None
        """
        edges = self.get_outgoing_edges(node_id)
        if edges:
            return edges[0].to_node
        node = self.nodes.get(node_id)
        return node.next_node_id if node else None

    def get_all_node_ids(self) -> list[str]:
        """获取所有节点 ID

        Returns:
            节点 ID 列表
        """
        return list(self.nodes.keys())

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [
                e.to_dict()
                for edge_list in self.edges.values()
                for e in edge_list
            ],
            "entry_node": self.entry_node,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineGraph:
        """从字典反序列化创建图"""
        graph = cls(
            entry_node=data.get("entry_node", data.get("entry", "")),
            metadata=data.get("metadata", {}),
        )

        for node_data in data.get("nodes", []):
            node = PipelineNode.create(node_data)
            graph.nodes[node.id] = node

        for edge_data in data.get("edges", []):
            edge = PipelineEdge.from_dict(edge_data)
            if edge.from_node not in graph.edges:
                graph.edges[edge.from_node] = []
            graph.edges[edge.from_node].append(edge)

        # 如果没有显式边，从节点 next_node_id 推断边
        if not graph.edges:
            for node in graph.nodes.values():
                if node.next_node_id:
                    if node.id not in graph.edges:
                        graph.edges[node.id] = []
                    graph.edges[node.id].append(
                        PipelineEdge(from_node=node.id, to_node=node.next_node_id)
                    )

        # spec-2026-07-27-execution-path-unification 阶段 3: 线性模式
        # 无显式 edges 且无 next_node_id 时，按 nodes 列表顺序自动链接。
        # 让用户写 {"nodes": [...]} 即可表达线性 pipeline（吸收 chain schema 简洁性）。
        # entry_node 缺省时取 nodes 第一个。
        if not graph.edges and len(graph.nodes) > 1:
            node_ids = list(graph.nodes.keys())
            for i in range(len(node_ids) - 1):
                graph.edges.setdefault(node_ids[i], []).append(
                    PipelineEdge(from_node=node_ids[i], to_node=node_ids[i + 1])
                )
            if not graph.entry_node:
                graph.entry_node = node_ids[0]

        # 单节点 + 无 entry_node → 默认该节点为入口（覆盖线性模式单节点 case）
        if not graph.entry_node and len(graph.nodes) == 1:
            graph.entry_node = next(iter(graph.nodes.keys()))

        return graph


class PipelineParser:
    """Pipeline JSON 解析器

    将 JSON 字符串解析为 PipelineGraph，支持 MaaFramework 扩展协议格式。
    """

    @staticmethod
    def parse(json_str: str) -> PipelineGraph:
        """解析 JSON 字符串为 PipelineGraph

        支持三种格式：
        1. 标准 MaaFramework 格式：{"nodes": [...], "edges": [...], "entry_node": "..."}
        2. 简化格式：{"entry": "...", "steps": [{"id": "...", "type": "...", ...}]}
        3. 旧版格式：{"nodes": [{"id": "...", "type": "...", "next_node_id": "..."}]}

        Args:
            json_str: Pipeline JSON 字符串

        Returns:
            PipelineGraph 实例

        Raises:
            ValueError: JSON 格式错误或节点类型未知
            json.JSONDecodeError: JSON 解析错误
        """
        data = json.loads(json_str)
        return PipelineParser.parse_dict(data)

    @staticmethod
    def parse_dict(data: dict[str, Any]) -> PipelineGraph:
        """解析字典为 PipelineGraph

        Args:
            data: Pipeline 配置字典

        Returns:
            PipelineGraph 实例

        Raises:
            ValueError: 节点类型未知或格式不合法
        """
        # 规范化节点数据：支持 type/action 字段作为 node_type，params 字段作为 config
        nodes_data = data.get("nodes", data.get("steps", []))
        normalized_nodes = []
        for node_data in nodes_data:
            normalized = dict(node_data)
            # React Flow format wraps node config in a "data" field:
            # {"id": "...", "type": "template_match", "position": {...}, "data": {"params": {...}}}
            # Merge data contents into top-level so subsequent normalization
            # (type→node_type, params→config, etc.) handles them uniformly.
            # Top-level keys take precedence over data keys to avoid React Flow
            # metadata (label, position) clobbering explicit node config.
            if "data" in normalized and isinstance(normalized["data"], dict):
                data_field = normalized.pop("data")
                for k, v in data_field.items():
                    if k not in normalized:
                        normalized[k] = v
            if "type" in normalized and "node_type" not in normalized:
                normalized["node_type"] = normalized.pop("type")
            if "action" in normalized and "node_type" not in normalized:
                normalized["node_type"] = normalized.pop("action")
            # BD2/外部作者工具可能用 "node_id" 而非 "id" 标识节点，
            # 统一归一化到 "id"（PipelineNode.from_dict 用 data["id"] 读取）。
            if "node_id" in normalized and "id" not in normalized:
                normalized["id"] = normalized["node_id"]
            # BD2/外部作者工具可能用 "params" 而非 "config" 存节点配置，
            # 统一归一化到 "config"（PipelineNode.from_dict 只读 "config"）。
            # Phase 2.7: emit deprecation warning so pipeline authors migrate
            # to the canonical "config" field. The alias remains supported for
            # backward compatibility with existing BD2/MaaFramework pipelines.
            if "params" in normalized and "config" not in normalized:
                node_id_for_warn = normalized.get("id", normalized.get("node_id", "?"))
                logger.warning(
                    "节点 '%s' 使用了已废弃的 'params' 字段，请迁移到 'config' 字段；"
                    "别名将在未来版本移除。",
                    node_id_for_warn,
                )
                normalized["config"] = normalized.pop("params")
            normalized_nodes.append(normalized)

        normalized_data = {
            "nodes": normalized_nodes,
            "edges": data.get("edges", []),
            "entry_node": data.get("entry_node", data.get("entry", "")),
            "metadata": data.get("metadata", {}),
        }

        # 自动推断入口节点
        if not normalized_data["entry_node"] and normalized_nodes:
            normalized_data["entry_node"] = normalized_nodes[0].get("id", "")

        # 验证节点类型
        for node_data in normalized_nodes:
            node_type = node_data.get("node_type", "")
            if node_type and node_type not in PIPELINE_NODE_REGISTRY:
                raise ValueError(
                    f"节点 '{node_data.get('id', '?')}' 使用了未知类型: {node_type}"
                )

        return PipelineGraph.from_dict(normalized_data)
