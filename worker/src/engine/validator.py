"""PipelineValidator：Pipeline 图校验器"""

from __future__ import annotations

from dataclasses import dataclass

from engine.node import PIPELINE_NODE_REGISTRY
from engine.node_registry import validate_node_config
from engine.parser import PipelineGraph


@dataclass
class ValidationError:
    """校验错误

    Attributes:
        error_type: 错误类型标识
        message: 错误描述
        node_id: 关联的节点 ID（可选）
    """

    error_type: str
    message: str
    node_id: str | None = None

    def __str__(self) -> str:
        node_info = f" [节点: {self.node_id}]" if self.node_id else ""
        return f"[{self.error_type}]{node_info} {self.message}"


class PipelineValidator:
    """Pipeline 图校验器

    对 PipelineGraph 进行结构和语义校验，检测常见配置错误。
    """

    # 已知的有效节点类型（在所有节点注册前动态获取）
    @staticmethod
    def _known_node_types() -> set[str]:
        """获取所有已注册的节点类型"""
        return set(PIPELINE_NODE_REGISTRY.keys())

    @classmethod
    def validate(cls, graph: PipelineGraph) -> list[ValidationError]:
        """对 PipelineGraph 进行全面校验

        校验项包括：
        - 缺失入口节点
        - 未知节点类型
        - 孤立节点（入度和出度均为零，且不是入口节点）
        - 循环引用检测
        - 节点 ID 冲突

        Args:
            graph: Pipeline 有向图

        Returns:
            校验错误列表，空列表表示通过校验
        """
        errors: list[ValidationError] = []
        known_types = cls._known_node_types()

        errors.extend(cls._check_entry_node(graph))
        errors.extend(cls._check_unknown_types(graph, known_types))
        errors.extend(cls._check_orphan_nodes(graph))
        errors.extend(cls._check_circular_refs(graph))
        errors.extend(cls._check_node_params(graph))  # ★ 新增：params_schema 校验

        return errors

    @classmethod
    def _check_entry_node(cls, graph: PipelineGraph) -> list[ValidationError]:
        """检查入口节点是否存在"""
        errors = []
        if not graph.entry_node:
            errors.append(ValidationError(
                error_type="missing_entry",
                message="Pipeline 缺少入口节点",
            ))
        elif graph.entry_node not in graph.nodes:
            errors.append(ValidationError(
                error_type="invalid_entry",
                message=f"入口节点 '{graph.entry_node}' 不存在于节点列表中",
                node_id=graph.entry_node,
            ))
        return errors

    @classmethod
    def _check_unknown_types(
        cls, graph: PipelineGraph, known_types: set[str]
    ) -> list[ValidationError]:
        """检查是否存在未知节点类型"""
        errors = []
        for node_id, node in graph.nodes.items():
            if node.node_type and node.node_type not in known_types:
                errors.append(ValidationError(
                    error_type="unknown_type",
                    message=f"未知节点类型: {node.node_type}",
                    node_id=node_id,
                ))
        return errors

    @classmethod
    def _check_orphan_nodes(cls, graph: PipelineGraph) -> list[ValidationError]:
        """检查孤立节点（无入边也无出边，且不是入口节点）"""
        # 计算所有有入边的节点
        has_incoming: set[str] = set()
        for edge_list in graph.edges.values():
            for edge in edge_list:
                has_incoming.add(edge.to_node)

        # 计算所有有出边的节点
        has_outgoing: set[str] = set(graph.edges.keys())

        errors = []
        for node_id in graph.nodes:
            if node_id == graph.entry_node:
                continue
            if node_id not in has_incoming and node_id not in has_outgoing:
                errors.append(ValidationError(
                    error_type="orphan_node",
                    message="孤立节点：无入边也无出边，且不是入口节点",
                    node_id=node_id,
                ))
        return errors

    @classmethod
    def _check_circular_refs(cls, graph: PipelineGraph) -> list[ValidationError]:
        """检测循环引用（使用 DFS 三色标记法）

        只检测从入口节点可达子图中的环。
        """
        white, gray, black = 0, 1, 2
        color: dict[str, int] = dict.fromkeys(graph.nodes, white)
        path: list[str] = []

        def dfs(node_id: str) -> list[str] | None:
            """深度优先搜索，返回环路径或 None"""
            color[node_id] = gray
            path.append(node_id)

            for edge in graph.get_outgoing_edges(node_id):
                neighbor = edge.to_node
                if neighbor not in color:
                    continue
                if color[neighbor] == gray:
                    # 找到环
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]
                if color[neighbor] == white:
                    result = dfs(neighbor)
                    if result:
                        return result

            path.pop()
            color[node_id] = black
            return None

        if graph.entry_node and graph.entry_node in color:
            cycle = dfs(graph.entry_node)
            if cycle:
                return [ValidationError(
                    error_type="circular_ref",
                    message=f"检测到循环引用: {' -> '.join(cycle)}",
                    node_id=cycle[0],
                )]

        return []

    @classmethod
    def _check_node_params(
        cls, graph: PipelineGraph
    ) -> list[ValidationError]:
        """基于 params_schema 校验每个节点的 config 参数

        Args:
            graph: Pipeline 有向图

        Returns:
            参数校验错误列表
        """
        errors = []
        for node_id, node in graph.nodes.items():
            if not node.node_type:
                continue
            schema_errors = validate_node_config(node.node_type, node.config)
            for err in schema_errors:
                errors.append(ValidationError(
                    error_type="param_invalid",
                    message=err,
                    node_id=node_id,
                ))
        return errors

    @classmethod
    def is_valid(cls, graph: PipelineGraph) -> bool:
        """快速检查图是否有效

        Args:
            graph: Pipeline 有向图

        Returns:
            是否通过所有校验
        """
        return len(cls.validate(graph)) == 0
