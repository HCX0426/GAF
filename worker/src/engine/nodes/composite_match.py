"""P2-4 Composite match nodes — And / Or / Custom logical combinations.

MaaFramework Pipeline Protocol supports And/Or/Custom composite matchers
that combine multiple child recognition results. These nodes wrap child
node specs (each a dict consumable by PipelineNode.create) and execute
them in the current context, combining their results.

AndMatchNode  — all children must succeed; returns aggregated results.
OrMatchNode   — first child to succeed wins; returns its result.
CustomMatchNode — evaluates a Python expression (or callable path) over
                  child results to decide success/failure.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node
from engine.nodes._child_runner import run_child

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


@register_node("and_match")
@dataclass
class AndMatchNode(PipelineNode):
    """P2-4 AndMatch — all child recognition nodes must succeed.

    Config parameters:
    - children: List[dict] of child node specs (each with node_type + config).
        All children must return success=True.
    - short_circuit: If True (default), stop on first failure.

    Returns:
        success_result with aggregated child results in data["children"].
        fail_result if any child fails (with the failure reason).
    """

    node_type: str = "and_match"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "children_count": len(self.config.get("children", [])),
            "short_circuit": self.config.get("short_circuit", True),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()

        children: list[dict[str, Any]] = self.config.get("children", [])
        if not children:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="and_match requires non-empty children list",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID, children_count=0,
                ),
            )

        short_circuit = self.config.get("short_circuit", True)
        results: list[dict[str, Any]] = []
        any_fail = False
        first_failure = ""

        for i, child_spec in enumerate(children):
            r = run_child(child_spec, context)
            # Guard against non-dict child specs (already reported via
            # run_child as a failure; we just need a safe node_type label).
            if isinstance(child_spec, dict):
                node_type_label = child_spec.get("node_type", "unknown")
            else:
                node_type_label = f"<invalid:{type(child_spec).__name__}>"
            entry = {
                "index": i,
                "node_type": node_type_label,
                "success": r.success,
                "error": r.error_msg,
                "data": r.data,
            }
            results.append(entry)
            if not r.success:
                any_fail = True
                if not first_failure:
                    first_failure = f"child[{i}] ({entry['node_type']}): {r.error_msg}"
                if short_circuit:
                    break

        elapsed = time.monotonic() - start
        if any_fail:
            diagnostics = self._build_fail_diagnostics(
                context, NodeErrorCode.UNKNOWN,
                first_failure=first_failure, all_passed=False,
            )
            diagnostics.update({
                "children": results, "count": len(results), "all_passed": False,
            })
            return fail_result(
                error_msg=f"and_match failed: {first_failure}",
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=diagnostics,
                elapsed_time=elapsed,
            )
        return success_result(
            data={
                "children": results,
                "count": len(results),
                "all_passed": True,
                # Task 4.51 (P1-24~31, 2026-07-28): success path 补 coord_system 与识别类节点对齐
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            },
            elapsed_time=elapsed,
        )


@register_node("or_match")
@dataclass
class OrMatchNode(PipelineNode):
    """P2-4 OrMatch — first successful child wins.

    Config parameters:
    - children: List[dict] of child node specs (tried in order).
    - stop_on_first_success: If True (default), stop at first success.

    Returns:
        success_result with the winning child's data, or fail_result if
        all children fail.
    """

    node_type: str = "or_match"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "children_count": len(self.config.get("children", [])),
            "stop_on_first_success": self.config.get("stop_on_first_success", True),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()

        children: list[dict[str, Any]] = self.config.get("children", [])
        if not children:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="or_match requires non-empty children list",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID, children_count=0,
                ),
            )

        stop_on_first = self.config.get("stop_on_first_success", True)
        results: list[dict[str, Any]] = []
        winner = None

        for i, child_spec in enumerate(children):
            r = run_child(child_spec, context)
            if isinstance(child_spec, dict):
                node_type_label = child_spec.get("node_type", "unknown")
            else:
                node_type_label = f"<invalid:{type(child_spec).__name__}>"
            entry = {
                "index": i,
                "node_type": node_type_label,
                "success": r.success,
                "error": r.error_msg,
                "data": r.data,
            }
            results.append(entry)
            if r.success and winner is None:
                # Record the FIRST success as winner; do not overwrite
                # on subsequent successes when stop_on_first_success=False.
                winner = entry
                if stop_on_first:
                    break

        elapsed = time.monotonic() - start
        if winner is not None:
            return success_result(
                data={
                    "winner": winner,
                    "children": results,
                    "count": len(results),
                    "matched": True,
                    # Task 4.51 (P1-24~31, 2026-07-28): success path 补 coord_system 与识别类节点对齐
                    "coord_system": getattr(context, "coord_system", "") or "legacy",
                },
                elapsed_time=elapsed,
            )
        diagnostics = self._build_fail_diagnostics(
            context, NodeErrorCode.NO_MATCH,
            matched=False, all_failed_count=len(results),
        )
        diagnostics.update({
            "children": results, "count": len(results), "matched": False,
        })
        return fail_result(
            error_msg=f"or_match: all {len(results)} children failed",
            error_code=NodeErrorCode.NO_MATCH,
            node_id=self.id,
            node_type=self.node_type,
            data=diagnostics,
            elapsed_time=elapsed,
        )


@register_node("custom_match")
@dataclass
class CustomMatchNode(PipelineNode):
    """P2-4 CustomMatch — evaluate a Python expression against child results.

    Runs all child nodes, then evaluates a Python expression to decide
    whether the overall match succeeds. The expression has access to a
    `results` variable (list of dicts with success/error/data per child).

    Config parameters:
    - children: List[dict] of child node specs (all executed).
    - expression: Python expression returning bool (e.g.
        "results[0]['success'] and not results[1]['success']" for XOR).
        Required.
    - safe_mode: If True (default), restrict builtins for safety.

    Returns:
        success_result if expression evaluates truthy; fail_result otherwise.
    """

    node_type: str = "custom_match"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "children_count": len(self.config.get("children", [])),
            "expression": self.config.get("expression", ""),
            "safe_mode": self.config.get("safe_mode", True),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()

        children: list[dict[str, Any]] = self.config.get("children", [])
        expression = self.config.get("expression")
        if not expression:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="custom_match requires 'expression' config",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID, expression="",
                ),
            )

        results: list[dict[str, Any]] = []
        for i, child_spec in enumerate(children):
            r = run_child(child_spec, context)
            if isinstance(child_spec, dict):
                node_type_label = child_spec.get("node_type", "unknown")
            else:
                node_type_label = f"<invalid:{type(child_spec).__name__}>"
            results.append({
                "index": i,
                "node_type": node_type_label,
                "success": r.success,
                "error": r.error_msg,
                "data": r.data,
            })

        safe_mode = self.config.get("safe_mode", True)
        try:
            if safe_mode:
                # Restrict builtins to a safe subset.
                eval_globals = {"__builtins__": {
                    "len": len, "sum": sum, "any": any, "all": all,
                    "min": min, "max": max, "abs": abs, "int": int,
                    "float": float, "str": str, "bool": bool, "range": range,
                }}
            else:
                logger.warning(
                    "custom_match node %s: safe_mode=False grants full eval() "
                    "access — ensure pipeline configs come from trusted sources only",
                    self.id,
                )
                eval_globals = {}
            eval_locals = {"results": results}
            verdict = bool(eval(expression, eval_globals, eval_locals))
        except Exception as exc:
            elapsed = time.monotonic() - start
            diagnostics = self._build_fail_diagnostics(
                context, NodeErrorCode.UNKNOWN,
                expression_error=str(exc),
            )
            diagnostics.update({"children": results})
            return fail_result(
                error_msg=f"custom_match expression error: {exc}",
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=diagnostics,
                elapsed_time=elapsed,
            )

        elapsed = time.monotonic() - start
        diagnostics = self._build_fail_diagnostics(
            context, NodeErrorCode.NO_MATCH,
            verdict=False, count=len(results),
        )
        diagnostics.update({
            "children": results, "count": len(results),
            "verdict": verdict, "expression": expression,
        })
        if verdict:
            return success_result(data=diagnostics, elapsed_time=elapsed)
        return fail_result(
            error_msg="custom_match expression evaluated to False",
            error_code=NodeErrorCode.NO_MATCH,
            node_id=self.id,
            node_type=self.node_type,
            data=diagnostics, elapsed_time=elapsed,
        )
