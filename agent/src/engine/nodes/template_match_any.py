"""template_match_any 节点：多模板任一匹配 — 顺序尝试模板列表，首个命中即返回

Composite node that tries multiple template images in order and returns the
first successful match. Reuses TemplateMatchNode via the child-spec execution
pattern (run_child), so all existing template_match features (ROI, multi-scale,
click_on_match, auto-heal in debug mode) are transparently inherited.

Typical use case (TD-013): a UI element may appear as one of several visual
variants (e.g. 第七章1.png / 第七章2.png) and the pipeline should accept any of
them rather than hard-coding a single template.
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
from engine.target import publish_match_pos

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


@register_node("template_match_any")
@dataclass
class TemplateMatchAnyNode(PipelineNode):
    """Multi-template matcher — first successful template wins.

    Config parameters:
    - templates: List[str] — template image paths/data to try in order
        (required, non-empty). Each entry follows the same format as
        TemplateMatchNode's ``template`` config.
    - threshold: float — match confidence threshold, default 0.8
    - roi: dict {"x","y","w","h"} or list [x,y,w,h] — search region, optional
    - click_on_match: bool — click matched center after success, default false
    - method: str — OpenCV match method name, default "TM_CCOEFF_NORMED"
    - scale: List[float] — multi-scale matching scales, optional

    Returns:
        success_result with data={"winner": <winning child entry>,
        "children": <all attempts>, "matched": True} on first match.
        fail_result with data={"children": <all attempts>, "matched": False}
        if every template fails.

    Context variable:
        On success, sets ``{self.id}_match_result`` to the winner's match data
        (same convention as TemplateMatchNode, so downstream branch / target
        nodes can read the match position uniformly).
    """

    node_type: str = "template_match_any"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """Task 4.28 (P1-17): 构建失败诊断 data, 统一注入 node_id/node_type/error_code/coord_system + 节点特有配置字段。"""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "templates_count": len(self.config.get("templates", [])),
            "threshold": self.config.get("threshold", 0.8),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()

        templates: list[str] = self.config.get("templates", [])
        if not templates:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="template_match_any requires non-empty 'templates' list",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    templates_count=0,
                    threshold=self.config.get("threshold", 0.8),
                ),
            )

        # Shared config forwarded to every template_match child.
        threshold = self.config.get("threshold", 0.8)
        click_on_match = self.config.get("click_on_match", False)
        method = self.config.get("method", "TM_CCOEFF_NORMED")

        # Optional fields only forwarded when present (avoids passing None
        # into TemplateMatchNode which would change its default behaviour).
        optional_forward: dict[str, Any] = {}
        if "roi" in self.config:
            optional_forward["roi"] = self.config["roi"]
        if "scale" in self.config:
            optional_forward["scale"] = self.config["scale"]
        if "roi_coord_type" in self.config:
            optional_forward["roi_coord_type"] = self.config["roi_coord_type"]

        results: list[dict[str, Any]] = []
        for i, template in enumerate(templates):
            child_spec = {
                "id": f"{self.id}_child_{i}",
                "node_type": "template_match",
                "config": {
                    "template": template,
                    "threshold": threshold,
                    "click_on_match": click_on_match,
                    "method": method,
                    **optional_forward,
                },
            }
            r = run_child(child_spec, context)
            entry = {
                "index": i,
                "template": template,
                "success": r.success,
                "error": r.error_msg,
                "data": r.data,
            }
            results.append(entry)

            if r.success:
                # Winner — publish result under the parent node's id so
                # downstream nodes (branch / target resolution) read the
                # match position from a stable variable name.
                context.set_variable(f"{self.id}_match_result", r.data)

                # AI-debuggability P0-5 fix (2026-07-27):
                # Previously template_match_any only set {self.id}_match_result
                # but did NOT call publish_match_pos, breaking the silent
                # contract that every recognition node publishes to
                # _last_match_pos. Downstream click nodes with
                # target=_last_match_pos silently got the previous match
                # position (or ValueError if no prior match existed).
                # Now extract (x, y) from child's match data and publish
                # through the unified entry so coord_system + trace are
                # injected automatically (consistent with template_match /
                # ocr / feature_match / color_detect).
                child_data = r.data if isinstance(r.data, dict) else {}
                # template_match result_data has top-level "x"/"y" center
                # coords (see template_match.py:1002-1003). Other shapes
                # are accepted best-effort via _extract_xy.
                try:
                    if "x" in child_data and "y" in child_data:
                        pub_x, pub_y = int(child_data["x"]), int(child_data["y"])
                    else:
                        # Fall back to other common shapes.
                        from engine.target import _extract_xy
                        pub_x, pub_y = _extract_xy(child_data, "_match_result")
                    publish_match_pos(
                        context,
                        pub_x,
                        pub_y,
                        source=self.id,
                        extra={
                            "winner_template": template,
                            "winner_index": i,
                            "confidence": child_data.get("confidence", 0.0),
                        },
                    )
                except (ValueError, TypeError, KeyError) as exc:
                    # Best-effort: publish failure should not block the
                    # match success. AI can still inspect {id}_match_result.
                    logger.warning(
                        "template_match_any publish_match_pos failed: %s "
                        "(child_data keys=%s)", exc,
                        list(child_data.keys()) if isinstance(child_data, dict) else [],
                    )

                elapsed = time.monotonic() - start
                logger.info(
                    "template_match_any 命中: template=%s (index=%d), confidence=%s",
                    template, i,
                    r.data.get("confidence") if isinstance(r.data, dict) else "n/a",
                )
                return success_result(
                    data={
                        "winner": entry,
                        "children": results,
                        "count": len(results),
                        "matched": True,
                        # Task 4.47 (P2-32, 2026-07-28): success path 补 coord_system
                        "coord_system": getattr(context, "coord_system", "") or "legacy",
                    },
                    elapsed_time=elapsed,
                )

        elapsed = time.monotonic() - start
        logger.info(
            "template_match_any 全部失败: tried %d templates", len(results),
        )
        return fail_result(
            error_msg=f"template_match_any: all {len(results)} templates failed",
            error_code=NodeErrorCode.NO_MATCH,
            node_id=self.id,
            node_type=self.node_type,
            data=self._build_fail_diagnostics(
                context, NodeErrorCode.NO_MATCH,
                failed_templates_count=len(results),
                successful_templates_count=0,
                children=results,
                matched=False,
                # Task 4.48 (回归修复, 2026-07-28): 测试期望 count 字段 (旧 fail path 直接传 data dict),
                # Task 4.28 改用 _build_fail_diagnostics 时漏传 count 导致 test_all_fail 失败
                count=len(results),
            ),
            elapsed_time=elapsed,
        )
