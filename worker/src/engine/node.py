"""PipelineNode 节点基类及工厂模式注册"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core.result import AutoResult

if TYPE_CHECKING:
    from engine.context import PipelineContext


PIPELINE_NODE_REGISTRY: dict[str, type[PipelineNode]] = {}
"""全局节点类型注册表：node_type -> PipelineNode 子类（保留向后兼容）"""

PIPELINE_NODE_REGISTRY_META: dict[str, NodeMetadata] = {}
"""元数据注册表：node_type -> NodeMetadata"""


@dataclass
class NodeMetadata:
    """节点元数据

    Attributes:
        node_type: 内部标识，如 "click"
        display_name: 展示名，如 "鼠标点击"
        category: 分类: "action" / "control" / "match" / "device" / "notification" / "utility"
        description: 简短描述
        params_schema: JSON Schema 片段，描述 config 参数
    """

    node_type: str
    display_name: str
    category: str = "other"
    description: str = ""
    params_schema: dict | None = None


def register_node(
    node_type: str,
    display_name: str = "",
    category: str = "other",
    description: str = "",
    params_schema: dict | None = None,
):
    """将节点子类注册到工厂表中的装饰器，同时记录元数据

    Args:
        node_type: 节点类型字符串，对应 JSON 中的 node_type 字段
        display_name: 展示名，如 "鼠标点击"；为空时使用 node_type
        category: 分类: "action" / "control" / "match" / "device" / "notification" / "utility"
        description: 简短描述；为空时使用 cls.__doc__
        params_schema: JSON Schema 片段，描述 config 参数

    Returns:
        装饰器函数
    """

    def decorator(cls: type[PipelineNode]) -> type[PipelineNode]:
        PIPELINE_NODE_REGISTRY[node_type] = cls
        PIPELINE_NODE_REGISTRY_META[node_type] = NodeMetadata(
            node_type=node_type,
            display_name=display_name or node_type,
            category=category,
            description=description or cls.__doc__ or "",
            params_schema=params_schema,
        )
        return cls

    return decorator


@dataclass
class PipelineNode:
    """Pipeline 节点基类

    Attributes:
        id: 节点唯一标识
        name: 节点名称
        node_type: 节点类型字符串
        config: 节点配置字典
        next_node_id: 默认下一个节点 ID（顺序执行）
        comment: 节点注释 (spec 阶段 4.3)，描述节点做什么，供 LLM 诊断使用
        rationale: 节点设计理由 (spec 阶段 4.3)，描述为什么这样设计，供 LLM 诊断使用
        pre_verify: 前置验证配置 (spec-2026-07-27-execution-path-unification 阶段 2)。
            节点 execute() 之前执行的强验证，失败则节点标记失败、不执行 action。
            吸收 chain step.pre_verify 字段。
        post_verify: 后置验证配置。节点成功后执行的强验证，失败则标记节点失败。
            吸收 chain step.post_verify 字段。
            注：engine.py 已从 node.config["post_verify"] 读取并执行（spec 阶段 3 任务 3.2），
            本字段是规范化的属性位（优先于 config），同时保留 config 读取路径以向后兼容
            已有 pipeline JSON。
        retry: 重试配置 (dict, 可选)。吸收 chain step.retry 字段。
            格式: {"max_retries": int, "base_delay": float, "backoff_factor": float}
            节点失败时按指数退避重试。
        fallback: 回退方案配置 (dict, 可选)。吸收 chain step.fallback 字段。
            格式: {"action": str, "params": dict} 或内联节点配置。
            节点重试仍失败时执行回退方案。
        continue_on_error: 节点失败时是否继续执行下一个节点 (默认 False)。
            吸收 chain step.continue_on_error 字段。
            注：engine.py 仍从 node.config 读取以向后兼容，本字段优先级更高。
    """

    id: str
    name: str = ""
    node_type: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    next_node_id: str | None = None
    comment: str = ""
    rationale: str = ""
    # spec-2026-07-27-execution-path-unification 阶段 2: 吸收 chain step 字段
    pre_verify: dict[str, Any] | None = None
    post_verify: dict[str, Any] | None = None
    retry: dict[str, Any] | None = None
    fallback: dict[str, Any] | None = None
    continue_on_error: bool = False

    def execute(self, context: PipelineContext) -> AutoResult:
        """执行节点逻辑

        Args:
            context: Pipeline 执行上下文

        Returns:
            AutoResult 执行结果

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现 execute 方法")

    def to_dict(self) -> dict[str, Any]:
        """将节点序列化为字典

        Returns:
            包含节点属性的字典
        """
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "node_type": self.node_type,
            "config": self.config,
        }
        if self.next_node_id:
            result["next_node_id"] = self.next_node_id
        if self.comment:
            result["comment"] = self.comment
        if self.rationale:
            result["rationale"] = self.rationale
        # spec-2026-07-27 阶段 2: 序列化 chain 吸收字段（仅非默认值）
        if self.pre_verify:
            result["pre_verify"] = self.pre_verify
        if self.post_verify:
            result["post_verify"] = self.post_verify
        if self.retry:
            result["retry"] = self.retry
        if self.fallback:
            result["fallback"] = self.fallback
        if self.continue_on_error:
            result["continue_on_error"] = True
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineNode:
        """从字典反序列化创建 PipelineNode

        Args:
            data: 包含节点属性的字典

        Returns:
            PipelineNode 实例
        """
        return cls(
            id=data.get("id", data.get("node_id", "")),
            name=data.get("name", ""),
            node_type=data.get("node_type", ""),
            config=data.get("config", {}),
            next_node_id=data.get("next_node_id"),
            comment=data.get("comment", ""),
            rationale=data.get("rationale", ""),
            # spec-2026-07-27 阶段 2: 读取 chain 吸收字段
            pre_verify=data.get("pre_verify"),
            post_verify=data.get("post_verify"),
            retry=data.get("retry"),
            fallback=data.get("fallback"),
            continue_on_error=bool(data.get("continue_on_error", False)),
        )

    @staticmethod
    def create(data: dict[str, Any]) -> PipelineNode:
        """工厂方法：根据 node_type 创建对应的节点子类实例

        Args:
            data: 包含 id、node_type 及节点配置的字典

        Returns:
            对应类型的 PipelineNode 子类实例

        Raises:
            ValueError: 未知的节点类型
        """
        node_type = data.get("node_type", "")
        if not node_type:
            raise ValueError("节点数据中缺少 'node_type' 字段")

        cls_type = PIPELINE_NODE_REGISTRY.get(node_type)
        if cls_type is None:
            raise ValueError(f"未知的节点类型: {node_type}")

        return cls_type.from_dict(data)
