"""neural_network 节点：通用神经网络推理（已废弃别名）。

C22 fix: frontend `PipelineNodeType` declares 'neural_network' but the
agent only registers concrete 'nn_classifier' and 'nn_regressor' types.
Pipelines using the generic 'neural_network' type raised ValueError at
parse time.

This node is a compatibility shim that delegates to the appropriate
concrete NN node based on `config.mode`. New pipelines should use
'nn_classifier' or 'nn_regressor' directly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


@register_node("neural_network")
@dataclass
class NeuralNetworkNode(PipelineNode):
    """Generic neural network node (deprecated alias).

    Delegates execution to NNClassifierNode (default) or NNRegressorNode
    based on `config.mode`. Emits a deprecation warning on every run so
    users migrate to the concrete node types.

    config parameters:
    - mode: "classifier" (default) or "regressor"
    - all other config keys are forwarded to the delegate node
    """

    node_type: str = "neural_network"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """Task 4.28 (P1-17): 构建失败诊断 data, 统一注入 node_id/node_type/error_code/coord_system + 节点特有配置字段。"""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "model_path": self.config.get("model_path", ""),
            "framework": self.config.get("framework", "onnx"),
            "mode": self.config.get("mode", "classifier"),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()
        logger.warning(
            "neural_network node is deprecated; use 'nn_classifier' or "
            "'nn_regressor' directly (node_id=%s).",
            self.id,
        )

        mode = self.config.get("mode", "classifier")
        try:
            if mode == "regressor":
                from engine.nodes.nn_recognition import NNRegressorNode

                delegate = NNRegressorNode(
                    id=self.id,
                    name=self.name,
                    node_type="nn_regressor",
                    config=self.config,
                    next_node_id=self.next_node_id,
                )
            else:
                from engine.nodes.nn_recognition import NNClassifierNode

                delegate = NNClassifierNode(
                    id=self.id,
                    name=self.name,
                    node_type="nn_classifier",
                    config=self.config,
                    next_node_id=self.next_node_id,
                )
        except ImportError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"neural_network: failed to import delegate node: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    model_path=self.config.get("model_path", ""),
                    framework=self.config.get("framework", "onnx"),
                    mode=mode,
                    import_error=str(exc),
                ),
            )

        return delegate.execute(context)
