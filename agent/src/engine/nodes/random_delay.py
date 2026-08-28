"""random_delay 节点：在 [min, max] 区间内随机延时。

C22 fix: frontend `PipelineNodeType` declares 'random_delay' but the agent
node registry had no matching `@register_node`, so pipelines using this
node type raised `ValueError: 未知的节点类型: random_delay` at parse time.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext


@register_node("random_delay")
@dataclass
class RandomDelayNode(PipelineNode):
    """Random delay node — sleeps for a random duration in [min, max].

    Useful for simulating irregular human-paced input rhythms.

    config parameters:
    - min: minimum delay seconds (default 0.5)
    - max: maximum delay seconds (default 2.0)
    """

    node_type: str = "random_delay"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """Task 4.28 (P1-17): 构建失败诊断 data, 统一注入 node_id/node_type/error_code/coord_system + 节点特有配置字段。"""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "min": self.config.get("min", 0.5),
            "max": self.config.get("max", 2.0),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()
        try:
            min_s = float(self.config.get("min", 0.5))
            max_s = float(self.config.get("max", 2.0))
        except (TypeError, ValueError) as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"random_delay: invalid min/max config: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    min=self.config.get("min", 0.5),
                    max=self.config.get("max", 2.0),
                    parse_error=str(exc),
                ),
            )

        if min_s < 0 or max_s < min_s:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"random_delay: invalid range [{min_s}, {max_s}]",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    min=min_s, max=max_s,
                ),
            )

        delay = random.uniform(min_s, max_s)
        time.sleep(delay)
        elapsed = time.monotonic() - start
        return success_result(
            data={"delay": delay, "min": min_s, "max": max_s},
            elapsed_time=elapsed,
        )
