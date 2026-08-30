"""P2-6 SortSelect node — order_by / index selection over recognition results.

MaaFramework Pipeline Protocol supports `order_by` and `index` fields on
recognition nodes to sort multi-element results and select one element
by index (e.g. "sort OCR results by confidence descending, pick the 2nd
highest").

This node operates on a list stored in a context variable (typically the
output of OCR/color_detect/template_match with multiple matches). It:

1. Reads the list from `input_variable`.
2. Sorts it by `order_by` field (with optional direction).
3. Selects element at `index` (0-based; supports negative indexing).
4. Publishes the selected element to `output_variable` and (if it has
   x/y or center.x/y) also publishes `_last_match_pos` for downstream
   target resolution.
"""

from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node
from engine.target import publish_match_pos

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


def _get_nested(obj: Any, path: str) -> Any:
    """Resolve a dotted path like 'center.x' or 'confidence' against a dict."""
    if not path:
        return None
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur[part]
        elif hasattr(cur, part):
            cur = getattr(cur, part)
        else:
            return None
    return cur


@register_node("sort_select")
@dataclass
class SortSelectNode(PipelineNode):
    """P2-6 Sort + select element by index from a list variable.

    Config parameters:
    - input_variable: Name of context variable holding a list (required).
        May also be a "${var}" reference.
    - order_by: Dotted path to the sort key (e.g. "confidence",
        "center.x", "area"). If omitted, no sorting is applied.
    - order: "asc" (ascending) or "desc" (descending), default "desc".
    - index: 0-based index into the (sorted) list. Supports negative
        indexing (-1 = last). Default 0.
    - output_variable: Name to publish the selected element under
        (default: f"{node_id}_selected").
    - publish_match_pos: If True (default) and the selected element has
        x/y or center.x/y, publish to _last_match_pos.
    """

    node_type: str = "sort_select"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "input_variable": self.config.get("input_variable", ""),
            "order_by": self.config.get("order_by"),
            "order": self.config.get("order", "desc"),
            "index": int(self.config.get("index", 0)),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()

        # Resolve input variable name.
        var_spec = self.config.get("input_variable")
        if not var_spec:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="sort_select requires 'input_variable'",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID, input_variable="",
                ),
            )
        if isinstance(var_spec, str) and var_spec.startswith("${") and var_spec.endswith("}"):
            var_name = var_spec[2:-1]
        else:
            var_name = str(var_spec)

        items = context.get_variable(var_name)
        if items is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"input variable {var_name!r} not found",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    resolved_var_name=var_name, var_not_found=True,
                ),
            )
        if not isinstance(items, list):
            # Allow dict with a list field (e.g. recognition result with
            # "contours" or "boxes").
            if isinstance(items, dict):
                # Try common list field names.
                for field in ("contours", "boxes", "matches", "results", "items"):
                    if field in items and isinstance(items[field], list):
                        items = items[field]
                        break
                else:
                    elapsed = time.monotonic() - start
                    return fail_result(
                        error_msg=f"variable {var_name!r} is dict without list field",
                        elapsed_time=elapsed,
                        error_code=NodeErrorCode.PARAM_INVALID,
                        node_id=self.id,
                        node_type=self.node_type,
                        data=self._build_fail_diagnostics(
                            context, NodeErrorCode.PARAM_INVALID,
                            resolved_var_name=var_name,
                            items_type="dict", tried_list_fields=[
                                "contours", "boxes", "matches", "results", "items"],
                        ),
                    )
            else:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"variable {var_name!r} is not a list: {type(items).__name__}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.PARAM_INVALID,
                        resolved_var_name=var_name, items_type=type(items).__name__,
                    ),
                )

        if not items:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"variable {var_name!r} is empty list",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.NO_MATCH,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.NO_MATCH,
                    resolved_var_name=var_name, list_length=0,
                ),
            )

        # Sort if order_by specified.
        order_by = self.config.get("order_by")
        if order_by:
            order = str(self.config.get("order", "desc")).lower()
            reverse = (order == "desc")

            def _key(item: Any) -> Any:
                val = _get_nested(item, order_by)
                if val is None:
                    return float("-inf") if reverse else float("inf")
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return str(val)

            try:
                sorted_items = sorted(items, key=_key, reverse=reverse)
            except Exception as exc:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"sort failed on {order_by!r}: {exc}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.UNKNOWN,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.UNKNOWN,
                        resolved_var_name=var_name, list_length=len(items),
                        sort_error=str(exc),
                    ),
                )
        else:
            sorted_items = list(items)

        # Select by index.
        index = int(self.config.get("index", 0))
        try:
            selected = sorted_items[index]
        except IndexError:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"index {index} out of range (list len={len(sorted_items)})",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    resolved_var_name=var_name, list_length=len(sorted_items),
                    requested_index=index,
                ),
            )

        output_var = self.config.get("output_variable") or f"{self.id}_selected"
        context.set_variable(output_var, selected)

        # Optionally publish _last_match_pos.
        should_publish = self.config.get("publish_match_pos", True)
        if should_publish:
            # Try x/y at top level, then center.x/y.
            x = _get_nested(selected, "x")
            y = _get_nested(selected, "y")
            if x is None or y is None:
                x = _get_nested(selected, "center.x")
                y = _get_nested(selected, "center.y")
            if x is not None and y is not None:
                with contextlib.suppress(TypeError, ValueError):
                    # Skip if x/y not numeric.
                    publish_match_pos(
                        context, int(x), int(y),
                        source=f"{self.id}:sort_select",
                        extra={"index": index, "order_by": order_by or ""},
                    )

        result_data = {
            "input_variable": var_name,
            "order_by": order_by,
            "order": self.config.get("order", "desc"),
            "index": index,
            "selected": selected,
            "list_length": len(sorted_items),
            "output_variable": output_var,
            # Task 4.47 (P2-30, 2026-07-28): success path 补 coord_system
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }
        elapsed = time.monotonic() - start
        logger.info(
            "sort_select: var=%s order_by=%s index=%d list_len=%d elapsed=%.3fs",
            var_name, order_by or "(none)", index, len(sorted_items), elapsed,
        )
        return success_result(data=result_data, elapsed_time=elapsed)
