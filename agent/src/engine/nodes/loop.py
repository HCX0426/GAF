"""loop 节点：for/while 循环

Real implementation: LoopNode sets up loop control variables in the
PipelineContext. The PipelineEngine main loop detects these variables
in _resolve_next_node and iterates the body by jumping back to the
first body node until the termination condition is met.

Control variables written to context:
- _loop_active: bool, True while a loop iteration is in progress
- _loop_type: "for" / "while"
- _loop_iteration: current 0-based iteration index
- _loop_max: max iterations (for mode)
- _loop_body: list of body node IDs
- _loop_id: the LoopNode's own id
- _loop_cond_var / _loop_cond_op / _loop_cond_val: while condition config

Limitation: nested loops are not supported (a single _loop_* slot is
used). P0-8 fix (AI 可调试性, 2026-07-27): an inner LoopNode executing
while an outer loop is still active (_loop_active=True with a different
_loop_id) is now explicitly rejected with a clear error instead of
silently overwriting the outer loop's state (which previously caused
the outer loop to lose its iteration counter / body_nodes / condition
and silently fall through to the wrong next node).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.constants import LoopType
from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext


@register_node("loop")
@dataclass
class LoopNode(PipelineNode):
    """循环节点

    支持 for 循环（固定次数）和 while 循环（条件循环）。

    LoopNode itself only initializes the loop control variables; the
    actual body iteration is driven by PipelineEngine._resolve_next_node,
    which jumps back to body_nodes[0] after the last body node completes
    while the continuation condition holds.

    config 参数：
    - loop_type: 循环类型 "for" / "while"，默认 "for"
    - max_iterations: 最大循环次数（for 模式），默认 10
    - condition_variable: 条件变量名（while 模式）
    - condition_operator: 比较运算符（while 模式），默认 "eq"
    - condition_value: 比较值（while 模式）
    - body_nodes: 循环体节点 ID 列表
    """

    node_type: str = "loop"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "loop_type": self.config.get("loop_type", LoopType.FOR.value),
            "body_nodes": list(self.config.get("body_nodes", [])),
            "max_iterations": int(self.config.get("max_iterations", 10)),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """Initialize loop control variables for engine-driven iteration.

        Args:
            context: Pipeline 执行上下文

        Returns:
            AutoResult，data 包含循环配置和初始迭代计数
        """
        start = time.monotonic()
        loop_type = self.config.get("loop_type", LoopType.FOR.value)
        body_nodes = list(self.config.get("body_nodes", []))

        # P0-8 fix (AI 可调试性, 2026-07-27): 检测嵌套循环并明确报错。
        # 之前内层 LoopNode 会静默覆盖外层循环的 _loop_* 状态, 导致外层
        # 循环丢失 iteration counter / body_nodes / condition, 引擎在
        # _resolve_next_node 拿到错误的 _loop_body[-1] 或空 _loop_body,
        # 外层循环静默 fall through 到错误下一节点 (silent bug)。
        # 现在主动检测: 若 _loop_active=True 且 _loop_id 不是当前节点,
        # 说明外层循环还在迭代中, 拒绝启动内层循环, 让 AI 能从错误
        # 消息直接定位到嵌套 loop 节点而非下游诡异行为。
        # 注意: 只查 _loop_id 会被误判 (循环退出后 _loop_id 仍残留),
        # 必须同时查 _loop_active=True 才确认是活跃嵌套。
        active_loop_id = context.get_variable("_loop_active", False)
        if active_loop_id:
            current_loop_id = context.get_variable("_loop_id", "")
            if current_loop_id and current_loop_id != self.id:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=(
                        f"嵌套循环不支持: 当前已有活跃循环 "
                        f"{current_loop_id!r}, 无法启动新循环 {self.id!r}. "
                        f"GAF 使用单一 _loop_* 状态槽, 内层 LoopNode 会覆盖"
                        f"外层循环状态导致静默失败. 请将嵌套循环重构为顺序"
                        f"执行或拆分为多个 pipeline."
                    ),
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.PARAM_INVALID,
                        nested_loop_detected=True,
                        outer_loop_id=current_loop_id,
                        inner_loop_id=self.id,
                    ),
                )

        # Common control variables consumed by PipelineEngine
        context.set_variable("_loop_active", True)
        context.set_variable("_loop_type", loop_type)
        context.set_variable("_loop_iteration", 0)
        context.set_variable("_loop_body", body_nodes)
        context.set_variable("_loop_id", self.id)

        if loop_type == LoopType.FOR:
            max_iterations = int(self.config.get("max_iterations", 10))
            context.set_variable("_loop_max", max_iterations)

            result_data = {
                "loop_type": "for",
                "max_iterations": max_iterations,
                "body_nodes": body_nodes,
                "current_iteration": 0,
                # Task 4.47 (P2-27, 2026-07-28): for mode success path 补 coord_system
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            }
            elapsed = time.monotonic() - start
            return success_result(data=result_data, elapsed_time=elapsed)

        elif loop_type == LoopType.WHILE:
            cond_var = self.config.get("condition_variable", "")
            cond_op = self.config.get("condition_operator", "eq")
            cond_val = self.config.get("condition_value")
            context.set_variable("_loop_cond_var", cond_var)
            context.set_variable("_loop_cond_op", cond_op)
            context.set_variable("_loop_cond_val", cond_val)

            result_data = {
                "loop_type": "while",
                "condition_variable": cond_var,
                "condition_operator": cond_op,
                "condition_value": cond_val,
                "body_nodes": body_nodes,
                "current_iteration": 0,
                # Task 4.47 (P2-27, 2026-07-28): while mode success path 补 coord_system
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            }
            elapsed = time.monotonic() - start
            return success_result(data=result_data, elapsed_time=elapsed)

        else:
            # Unknown loop type — deactivate the loop slot we just claimed
            context.set_variable("_loop_active", False)
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"未知循环类型: {loop_type}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    unknown_loop_type=loop_type,
                ),
            )
