"""Public child node runner — instantiate and execute a child node from spec.

Extracted from composite_match.py for reuse by template_match_any and
swipe_until composite nodes. Any composite node that needs to execute a
child node spec (a dict consumable by PipelineNode.create) should use
``run_child`` from this module rather than reimplementing the logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result

if TYPE_CHECKING:
    from engine.context import PipelineContext


def _build_child_fail_data(
    child_spec: Any, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
) -> dict[str, Any]:
    """Task 4.28 (P1-17): 构建 run_child 失败诊断 data (模块级 helper)。

    run_child 是模块级函数没有 self, 从 child_spec 提取 child_node_id /
    child_node_type, 注入 coord_system + 节点特有配置字段。
    parent_node_id / depth 在 run_child 上下文中不可获取, 留空字符串。
    """
    child_id = ""
    child_node_type = ""
    if isinstance(child_spec, dict):
        child_id = str(child_spec.get("id", ""))
        child_node_type = str(child_spec.get("node_type", ""))
    data: dict[str, Any] = {
        "node_id": child_id,
        "node_type": child_node_type,
        "error_code": error_code.value,
        "coord_system": getattr(context, "coord_system", "") or "legacy",
        "child_pipeline_id": child_id,
        "parent_node_id": "",
        "depth": 0,
    }
    data.update(kwargs)
    return data


def run_child(child_spec: dict[str, Any], context: PipelineContext) -> AutoResult:
    """Instantiate and execute a child node from its spec dict.

    Args:
        child_spec: Dict with at least a ``node_type`` key (plus ``id``,
            ``config``, etc. as required by the node). Non-dict specs or
            specs missing ``node_type`` return a fail_result.
        context: Pipeline execution context passed to the child node.

    Returns:
        AutoResult from the child node execution, or fail_result if the
        spec is invalid or the child node raises.
    """
    from engine.node import PipelineNode

    if not isinstance(child_spec, dict):
        return fail_result(
            error_msg=f"child spec must be a dict, got {type(child_spec).__name__}",
            error_code=NodeErrorCode.PARAM_INVALID,
            node_id="",
            node_type="",
            data=_build_child_fail_data(
                child_spec, context, NodeErrorCode.PARAM_INVALID,
                spec_type=type(child_spec).__name__,
            ),
        )
    if "node_type" not in child_spec:
        return fail_result(
            error_msg="child spec missing 'node_type'",
            error_code=NodeErrorCode.PARAM_INVALID,
            node_id=str(child_spec.get("id", "")),
            node_type="",
            data=_build_child_fail_data(
                child_spec, context, NodeErrorCode.PARAM_INVALID,
                missing_key="node_type",
            ),
        )
    try:
        child = PipelineNode.create(child_spec)
        return child.execute(context)
    except Exception as exc:
        return fail_result(
            error_msg=f"child node error: {exc}",
            error_code=NodeErrorCode.UNKNOWN,
            node_id=str(child_spec.get("id", "")),
            node_type=str(child_spec.get("node_type", "")),
            data=_build_child_fail_data(
                child_spec, context, NodeErrorCode.UNKNOWN,
                exception_type=type(exc).__name__,
                exception_msg=str(exc),
            ),
        )
