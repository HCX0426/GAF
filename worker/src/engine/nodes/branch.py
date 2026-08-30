"""branch 节点：if/else 条件分支"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.constants import evaluate_comparison
from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext


@register_node("branch")
@dataclass
class BranchNode(PipelineNode):
    """条件分支节点

    根据条件变量决定走 true 分支还是 false 分支。
    执行结果中的 _branch_taken 字段标记选择的分支。

    config 参数 (Task 4.66, 2026-07-28 双格式支持):
    - condition: 条件配置 (canonical, 结构化对象 {"variable": str, "operator": str, "value": Any})
    - condition_variable + condition_operator + condition_value: legacy 三件套 (兼容旧资源文件)
    - true_branch: 条件为真时跳转的节点 ID (canonical)
    - false_branch: 条件为假时跳转的节点 ID (canonical)
    - true_node_id: legacy, 别名 true_branch
    - false_node_id: legacy, 别名 false_branch
    """

    node_type: str = "branch"

    def _get_condition(self) -> tuple[str, str, Any]:
        """Task 4.66 (P0-15, 2026-07-28): 归一化读取条件配置.

        支持两种格式:
        1. canonical: {"condition": {"variable": "x", "operator": "eq", "value": true}}
        2. legacy: {"condition_variable": "x", "condition_operator": "eq", "condition_value": true}

        Returns:
            (variable, operator, value) 三元组
        """
        cond = self.config.get("condition")
        if isinstance(cond, dict):
            var = cond.get("variable", "")
            op = cond.get("operator", "eq")
            val = cond.get("value")
            if var:
                return var, op, val
        # legacy 三件套
        var = self.config.get("condition_variable", "")
        op = self.config.get("condition_operator", "eq")
        val = self.config.get("condition_value")
        return var, op, val

    def _get_branch_target(self, condition_result: bool) -> str:
        """Task 4.66: 归一化读取分支目标节点 ID.

        优先 canonical (true_branch/false_branch), 兼容 legacy (true_node_id/false_node_id).
        """
        if condition_result:
            return self.config.get("true_branch") or self.config.get("true_node_id") or ""
        return self.config.get("false_branch") or self.config.get("false_node_id") or ""

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """Task 4.28 (P1-17): 构建失败诊断 data, 统一注入 node_id/node_type/error_code/coord_system + 节点特有配置字段。"""
        var, op, val = self._get_condition()
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "condition_variable": var,
            "condition_operator": op,
            "condition_value": val,
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """执行条件分支判断

        Args:
            context: Pipeline 执行上下文

        Returns:
            AutoResult，data 包含 {"condition_result": bool, "branch_taken": str}
        """
        start = time.monotonic()

        var_name, operator, condition_value = self._get_condition()

        if not var_name:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="分支条件变量名称为空",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    condition_variable="",
                    expected_value=condition_value,
                ),
            )

        var_value = context.get_variable(var_name)
        condition_result = self._evaluate(var_value, operator, condition_value)

        branch_taken = self._get_branch_target(condition_result)

        result_data = {
            "condition_variable": var_name,
            "condition_operator": operator,
            "condition_value": condition_value,
            "actual_value": var_value,
            "condition_result": condition_result,
            "branch_taken": branch_taken,
            # Task 4.47 (P2-28, 2026-07-28): success path 补 coord_system
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }

        context.set_variable(f"{self.id}_branch_result", result_data)
        elapsed = time.monotonic() - start
        return success_result(data=result_data, elapsed_time=elapsed)

    def _evaluate(self, actual: Any, operator: str, expected: Any) -> bool:
        """Evaluate comparison using shared evaluate_comparison helper.

        Delegates to core.constants.evaluate_comparison (spec-40 Phase 2)
        which is the single source of truth for comparison logic,
        eliminating the duplicate 7-branch if/elif chain that previously
        lived here and in engine.py:_evaluate_loop_condition.

        N191 schema-unification fix (2026-07-28, BD2 get_email 测试发现):
        上游 template_match/OCR 节点 set_variable("<node_id>_match_result", result_data)
        存的是整个 result_data dict (含 confidence/x/y 等), 而非 bool. branch 节点
        读取该变量时直接与 True 比较 → dict == True → False → 永远走 false_branch.
        修复: 当 actual 是 dict 时, 按优先级提取 matched/success/confidence>=threshold
        字段转换为 bool, 再与 expected 比较.

        Args:
            actual: Actual value read from context (可能是 dict / bool / 数值).
            operator: Comparison operator string (eq/neq/gt/lt/gte/lte/contains).
            expected: Expected value from node config.

        Returns:
            Comparison result; on type errors returns False.
        """
        # N191 fix: dict actual → extract bool match status
        if isinstance(actual, dict):
            # 优先级 1: 显式 matched 字段 (template_match success path)
            if "matched" in actual:
                actual = bool(actual["matched"])
            # 优先级 2: success 字段
            elif "success" in actual:
                actual = bool(actual["success"])
            # 优先级 3: is_success 字段 (debug payload)
            elif "is_success" in actual:
                actual = bool(actual["is_success"])
            # 优先级 4: confidence 字段 > 0 表示匹配成功
            elif "confidence" in actual:
                conf = actual.get("confidence", 0.0)
                try:
                    actual = float(conf) > 0.0
                except (TypeError, ValueError):
                    actual = False
            else:
                # 非 empty dict 视为 truthy
                actual = bool(actual)
        return evaluate_comparison(actual, operator, expected)
