"""goto 节点：跳转到标签节点"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext


@register_node("goto")
@dataclass
class GotoNode(PipelineNode):
    """无条件跳转节点

    跳转到指定的节点继续执行。

    config 参数：
    - target_node_id: 目标节点 ID
    - label: 目标标签名（备选，通过标签查找节点）
    """

    node_type: str = "goto"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — N192 A1+A2: 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "target_node_id": self.config.get("target_node_id", ""),
            "label": self.config.get("label", ""),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """执行跳转

        Args:
            context: Pipeline 执行上下文

        Returns:
            AutoResult，data 包含跳转目标信息
        """
        start = time.monotonic()

        target_node_id = self.config.get("target_node_id", "")
        label = self.config.get("label", "")

        if not target_node_id and not label:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="goto 节点缺少 target_node_id 或 label",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                ),
            )

        result_data = {
            "target_node_id": target_node_id,
            "label": label,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }

        context.set_variable(f"{self.id}_goto_target", target_node_id or label)
        elapsed = time.monotonic() - start
        return success_result(data=result_data, elapsed_time=elapsed)
