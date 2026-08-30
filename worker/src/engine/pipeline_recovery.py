"""PipelineEngine：Pipeline 通用执行器"""

from __future__ import annotations

import logging
from typing import Any

import engine.nodes  # noqa: F401  (side-effect import: populates registry)
from core.constants import LoopType, NodeType, evaluate_comparison
from core.result import AutoResult
from engine.node import PipelineNode

logger = logging.getLogger(__name__)


class PipelineRecoveryMixin:
    """PipelineEngine mixin — see pipeline_engine.py for full class (s35 split)."""

    def _attempt_recovery(
        self, node: PipelineNode, failed_result: AutoResult,
    ) -> str:
        """调用 recovery_manager.recover() 尝试界面恢复 (spec 阶段 3 — 任务 3.3).

        最多 2 次尝试:
          - attempt=0: 直接 BFS 最短路径
          - attempt=1: 传 exclude_edges 排除上次失败的边, 强制换路径

        Args:
            node: 失败节点
            failed_result: 失败节点的 AutoResult

        Returns:
            outcome 字符串 ("RECOVERED" / "ALREADY_THERE" /
            "NEEDS_HUMAN" / "RECOVERY_FAILED" / "LIMIT_REACHED").
            调用方根据返回值决定是否重试当前节点.
        """
        if self._recovery_manager is None:
            return "NO_MANAGER"

        node_id = node.id
        attempts_so_far = self._recovery_attempts_per_node.get(node_id, 0)
        if attempts_so_far >= self._max_recovery_retries:
            logger.warning(
                "节点 %s 已恢复 %d 次, 达上限 (max_recovery_retries=%d) 不再尝试",
                node_id, attempts_so_far, self._max_recovery_retries,
            )
            return "LIMIT_REACHED"

        # 推断 expected_state (§3.3 3 级优先级)
        try:
            from core.interface_recovery import InterfaceRecoveryManager
            safe_states = getattr(self._recovery_manager, "safe_states", [])
            expected_state, expected_state_source = (
                InterfaceRecoveryManager.infer_expected_state(
                    node_config=node.config,
                    previous_node_chain=self._build_previous_node_chain(),
                    safe_states=safe_states,
                )
            )
        except Exception as exc:
            logger.warning(
                "节点 %s infer_expected_state 失败: %s, 跳过恢复",
                node_id, exc,
            )
            return "INFER_FAILED"

        # 第二次尝试时把上次 path 转成 exclude_edges
        exclude_edges = None
        if attempts_so_far > 0:
            last_path = self._last_recovery_path.get(node_id)
            if last_path and len(last_path) >= 2:
                exclude_edges = list(zip(last_path[:-1], last_path[1:], strict=True))

        # 构造 execution_context (§4.2)
        execution_context = {
            "node_type": node.node_type,
            "expected_state_source": expected_state_source,
            "device_id": getattr(getattr(self._context, "device", None), "id", None),
            "execution_id": self._execution_id,
            "recovery_attempt": attempts_so_far,
            "retry_count": failed_result.retry_count,
            "previous_node_id": self._previous_node_id,
            "previous_node_result": None,  # 可扩展
        }

        pipeline_name = getattr(self._context, "pipeline_name", "") or "unknown"

        logger.info(
            "节点 %s 调用 recover (attempt=%d, expected_state=%s, exclude_edges=%s)",
            node_id, attempts_so_far, expected_state, exclude_edges,
        )

        try:
            recovery_result = self._recovery_manager.recover(
                expected_state=expected_state,
                pipeline_name=pipeline_name,
                node_id=node_id,
                node_config=node.config,
                execution_context=execution_context,
                attempt=attempts_so_far,
                exclude_edges=exclude_edges,
            )
        except Exception as exc:
            logger.exception("节点 %s recover() 异常: %s", node_id, exc)
            return "RECOVERY_FAILED"

        # 更新计数 + 记录 path 供下次 attempt 用作 exclude_edges
        self._recovery_attempts_per_node[node_id] = attempts_so_far + 1
        if recovery_result.path_taken:
            self._last_recovery_path[node_id] = recovery_result.path_taken

        outcome_str = recovery_result.outcome.value.upper()
        logger.info(
            "节点 %s 恢复结果: outcome=%s, current_state=%s, path=%s, error=%s",
            node_id, outcome_str, recovery_result.current_state,
            recovery_result.path_taken, recovery_result.error_msg,
        )
        return outcome_str

    def _resolve_next_node(self, node: PipelineNode, result: AutoResult) -> str | None:
        """根据节点类型和结果确定下一个节点 ID

        处理以下特殊情况：
        - Maa JumpBack/Next 信号：读取上下文变量重定向执行（优先级最高）
        - branch 节点：根据条件结果选择 true/false 分支
        - goto 节点：跳转到目标节点
        - loop 节点：检查迭代计数决定是否继续循环
        - 默认：按图边或 next_node_id 流转

        Args:
            node: 当前节点
            result: 执行结果

        Returns:
            下一个节点 ID 或 None（结束）
        """
        if self._graph is None:
            return None

        # Maa protocol action signals (set by JumpBackNode / NextNode in
        # engine/nodes/maa_actions.py). These take priority over graph edges
        # so that explicit jump_back / next overrides always win.
        # NOTE: _stop_requested is handled in the main execute() loop, not here.
        if self._context is not None:
            jump_target = self._context.get_variable("_jump_back_target")
            if jump_target:
                # Consume the signal so it doesn't leak to subsequent nodes
                self._context.set_variable("_jump_back_target", "")
                logger.info("JumpBack: %s -> %s", node.id, jump_target)
                return jump_target
            next_override = self._context.get_variable("_next_override")
            if next_override:
                # Consume the signal so it doesn't leak to subsequent nodes
                self._context.set_variable("_next_override", "")
                logger.info("Next override: %s -> %s", node.id, next_override)
                return next_override

            # Loop continuation: when a loop is active and the current node is
            # the last node of the loop body, decide whether to iterate again
            # (jump back to body_nodes[0]) or exit the loop (fall through to
            # the normal outgoing edge). Consumes the _loop_active slot.
            if self._context.get_variable("_loop_active", False):
                loop_body = self._context.get_variable("_loop_body", []) or []
                if loop_body and node.id == loop_body[-1]:
                    if self._loop_should_continue():
                        iteration = int(self._context.get_variable("_loop_iteration", 0)) + 1
                        self._context.set_variable("_loop_iteration", iteration)
                        logger.info(
                            "Loop iterate: id=%s iteration=%d -> %s",
                            self._context.get_variable("_loop_id", ""),
                            iteration,
                            loop_body[0],
                        )
                        return loop_body[0]
                    logger.info(
                        "Loop exited: id=%s iteration=%d",
                        self._context.get_variable("_loop_id", ""),
                        self._context.get_variable("_loop_iteration", 0),
                    )
                    self._context.set_variable("_loop_active", False)
                    # Fall through to normal edge resolution to exit the loop

        # branch 节点：根据分支结果选择边
        if node.node_type == NodeType.BRANCH and result.success and result.data:
            branch_taken = result.data.get("branch_taken", "")
            if branch_taken:
                return branch_taken

        # goto 节点：跳转到目标节点
        if node.node_type == NodeType.GOTO and result.success and result.data:
            target = result.data.get("target_node_id", "")
            if target:
                return target

        # loop 节点：LoopNode has initialized loop control variables; enter
        # the first body node explicitly (overrides default edge so body_nodes
        # config drives iteration even without a matching graph edge).
        if node.node_type == NodeType.LOOP and result.success and result.data:
            body_nodes = result.data.get("body_nodes", []) or []
            if body_nodes:
                return body_nodes[0]

        # 按图边查找下一个节点
        edges = self._graph.get_outgoing_edges(node.id)

        # branch 节点有特殊边处理
        if node.node_type == NodeType.BRANCH and result.success and result.data:
            condition_result = result.data.get("condition_result", False)
            for edge in edges:
                if condition_result and edge.label in ("true", "True") or not condition_result and edge.label in ("false", "False"):
                    return edge.to_node

        # 默认取第一条边
        if edges:
            return edges[0].to_node

        # 如果节点有 next_node_id
        if node.next_node_id:
            return node.next_node_id

        return None

    def _loop_should_continue(self) -> bool:
        """Evaluate whether the active loop should iterate again.

        Reads loop control variables from context:
        - for: continue while _loop_iteration < _loop_max - 1
        - while: continue while the condition variable matches the configured
          operator/value (re-evaluated each iteration so body mutations are
          respected).

        Returns:
            True if the loop should run another iteration, False to exit.
        """
        if self._context is None:
            return False
        loop_type = self._context.get_variable("_loop_type", LoopType.FOR.value)
        if loop_type == LoopType.FOR:
            iteration = int(self._context.get_variable("_loop_iteration", 0))
            max_iter = int(self._context.get_variable("_loop_max", 0))
            return iteration < max_iter - 1
        if loop_type == LoopType.WHILE:
            cond_var = self._context.get_variable("_loop_cond_var", "")
            cond_op = self._context.get_variable("_loop_cond_op", "eq")
            cond_val = self._context.get_variable("_loop_cond_val")
            actual = self._context.get_variable(cond_var)
            return self._evaluate_loop_condition(actual, cond_op, cond_val)
        return False

    @staticmethod
    def _evaluate_loop_condition(actual: Any, operator: str, expected: Any) -> bool:
        """Evaluate a while-loop condition.

        Delegates to core.constants.evaluate_comparison (spec-40 Phase 2)
        which is the single source of truth for comparison logic,
        eliminating the duplicate 7-branch if/elif chain that previously
        lived here and in nodes/branch.py:BranchNode._evaluate.

        Args:
            actual: Current value of the condition variable.
            operator: Comparison operator (eq/neq/gt/lt/gte/lte/contains).
            expected: Configured comparison value.

        Returns:
            Comparison result; on type errors returns False (loop exits).
        """
        return evaluate_comparison(actual, operator, expected)
