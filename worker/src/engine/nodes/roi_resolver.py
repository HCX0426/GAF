"""roi_resolver node: pre-parse ROI coords into logical pixels for downstream nodes.

🔧 Status: skeleton implemented, NOT yet validated end-to-end.

Purpose
-------
When a pipeline author wants to define an ROI once (at base resolution, e.g.
1920x1080) and reuse it across multiple downstream nodes that do NOT natively
understand ``coord_transformer`` (or to keep node configs DRY), this node
resolves the ROI up-front and writes both physical and logical forms to the
pipeline context as a variable.

Pipeline authors can then reference the pre-resolved ROI in downstream nodes
via ``${var}`` substitution, e.g.::

    - id: resolve_search_box
      type: roi_resolver
      config:
        roi: {x: 100, y: 100, w: 400, h: 200}
        coord_type: base
        output_var: search_box_roi
    - id: click_search_box_center
      type: direct_hit
      config:
        x: ${search_box_roi.logical_center_x}
        y: ${search_box_roi.logical_center_y}

When no ``coord_transformer`` is present (tests / legacy mode), the node
falls back to identity conversion and writes the input ROI unchanged.
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

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


def _roi_dict_to_tuple(roi: Any) -> tuple | None:
    """Normalize ROI dict/list/tuple to a 4-tuple (x, y, w, h)."""
    if roi is None:
        return None
    if isinstance(roi, dict):
        try:
            return (
                int(roi.get("x", 0)),
                int(roi.get("y", 0)),
                int(roi.get("w", 0)),
                int(roi.get("h", 0)),
            )
        except (TypeError, ValueError) as exc:
            logger.warning("roi dict parse failed: %s", exc)
            return None
    if isinstance(roi, (list, tuple)) and len(roi) == 4:
        try:
            return tuple(int(v) for v in roi)  # type: ignore[return-value]
        except (TypeError, ValueError) as exc:
            logger.warning("roi list parse failed: %s", exc)
            return None
    logger.warning("unsupported roi type: %s", type(roi).__name__)
    return None


@register_node("roi_resolver")
@dataclass
class ROIResolverNode(PipelineNode):
    """Pre-parse ROI coordinates and publish logical/physical forms.

    Config parameters:
    - roi: ROI as dict {x, y, w, h} or 4-tuple/list. Coordinates interpreted
      per ``coord_type``.
    - coord_type: "base" / "logical" / "physical", default "base". Ignored
      when no transformer is present (identity pass-through).
    - output_var: Variable name to write the resolved ROI dict to. Default
      ``{node_id}_roi``. The published dict contains keys:
      ``physical`` (x, y, w, h in client physical pixels),
      ``logical`` (x, y, w, h in client logical pixels),
      ``logical_center_x`` / ``logical_center_y`` (int, safe click target),
      ``source_coord_type`` (input coord_type),
      ``transformer_applied`` (bool — False in legacy / fallback mode).
    - activate_window: Default False (this node performs no device I/O).
    """

    node_type: str = "roi_resolver"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """Task 4.28 (P1-17): 构建失败诊断 data, 统一注入 node_id/node_type/error_code/coord_system + 节点特有配置字段。"""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "roi": self.config.get("roi"),
            "coord_type": self.config.get("coord_type", "base"),
            "output_var": self.config.get("output_var") or f"{self.id}_roi",
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """Resolve ROI coordinates and publish to context variables."""
        start = time.monotonic()

        roi_tuple = _roi_dict_to_tuple(self.config.get("roi"))
        if roi_tuple is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="roi_resolver: 'roi' config missing or invalid",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    roi=self.config.get("roi"),
                    variable_name=self.config.get("output_var") or f"{self.id}_roi",
                    resolved_value=None,
                ),
            )

        coord_type_str = str(self.config.get("coord_type", "base")).lower()
        if coord_type_str not in ("base", "logical", "physical"):
            logger.warning(
                "roi_resolver: unknown coord_type %r, falling back to 'base'",
                coord_type_str,
            )
            coord_type_str = "base"

        output_var = self.config.get("output_var") or f"{self.id}_roi"

        transformer = getattr(context, "coord_transformer", None)
        if transformer is None:
            # Legacy mode: no DPI/resolution scaling available. Pass through
            # the input ROI as both physical and logical. Downstream nodes
            # operating in legacy mode will use the logical form.
            x, y, w, h = roi_tuple
            result_data: dict[str, Any] = {
                "physical": roi_tuple,
                "logical": roi_tuple,
                "logical_center_x": int(x + w / 2),
                "logical_center_y": int(y + h / 2),
                "source_coord_type": coord_type_str,
                "transformer_applied": False,
            }
            context.set_variable(output_var, result_data)
            elapsed = time.monotonic() - start
            logger.info(
                "roi_resolver[%s]: legacy pass-through roi=%s -> var=%s",
                self.id, roi_tuple, output_var,
            )
            return success_result(data=result_data, elapsed_time=elapsed)

        # Transformer mode: convert input → physical → logical.
        from utils.coord_transformer import CoordType

        coord_type_map = {
            "base": CoordType.BASE,
            "logical": CoordType.LOGICAL,
            "physical": CoordType.PHYSICAL,
        }
        coord_type = coord_type_map[coord_type_str]

        # Boundary: use the display context's client physical resolution so
        # process_roi can clamp. If unavailable, fall back to a large value.
        try:
            ctx = transformer.display_context
            boundary_w, boundary_h = ctx.client_physical_res
        except Exception as exc:
            logger.warning(
                "roi_resolver[%s]: cannot read client_physical_res (%s), "
                "skipping boundary clamp",
                self.id, exc,
            )
            boundary_w, boundary_h = 10_000, 10_000

        try:
            physical_roi, _offset = transformer.process_roi(
                roi=roi_tuple,
                boundary_width=boundary_w,
                boundary_height=boundary_h,
                enable_expand=False,
                roi_coord_type=coord_type,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"roi_resolver: process_roi failed: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.COORD_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.COORD_INVALID,
                    roi=list(roi_tuple),
                    variable_name=output_var,
                    resolved_value=None,
                    process_roi_error=str(exc),
                ),
            )

        if physical_roi is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="roi_resolver: process_roi returned None (invalid roi)",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.COORD_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.COORD_INVALID,
                    roi=list(roi_tuple),
                    variable_name=output_var,
                    resolved_value=None,
                ),
            )

        try:
            logical_roi = transformer.convert_client_physical_rect_to_logical(
                physical_roi,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"roi_resolver: physical→logical conversion failed: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.COORD_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.COORD_INVALID,
                    roi=list(roi_tuple),
                    variable_name=output_var,
                    resolved_value={"physical": list(physical_roi)},
                    conversion_error=str(exc),
                ),
            )

        px, py, pw, ph = physical_roi
        lx, ly, lw, lh = logical_roi
        result_data = {
            "physical": physical_roi,
            "logical": logical_roi,
            "logical_center_x": int(lx + lw / 2),
            "logical_center_y": int(ly + lh / 2),
            "physical_center_x": int(px + pw / 2),
            "physical_center_y": int(py + ph / 2),
            # source_coord_type 标识输入坐标系 (BASE/PHYSICAL/LOGICAL)
            "source_coord_type": coord_type_str,
            # Task 4.47 (P2-29, 2026-07-28): 新增 coord_system 字段标识输出坐标系,
            # 与 ocr.py 双字段模式 (coord_system + box_coord_system) 一致,
            # 让 AI 调试时只需查 coord_system 即可知道 result_data 用什么坐标系。
            "coord_system": "logical",
            "transformer_applied": True,
        }
        context.set_variable(output_var, result_data)
        # N191 §10.11 D5 (AI 可调试性, 2026-07-27): roi_resolver 是识别节点
        # 辅助类, 做 BASE→PHYSICAL→LOGICAL 转换, 必记 trace。AI 调试时通过
        # grep "roi_resolve" 看到 ROI 转换链路, 反推 boundary clamp 是否生效。
        with contextlib.suppress(Exception):
            context.emit_coord_trace(
                node_id=self.id,
                step="roi_resolve",
                raw={"roi": list(roi_tuple), "coord_type": coord_type_str},
                converted={"physical": list(physical_roi), "logical": list(logical_roi)},
                formula=f"process_roi(roi={roi_tuple}, coord_type={coord_type_str}) -> phys={physical_roi} -> logical={logical_roi}",
                coord_system_in=coord_type_str,
                coord_system_out="logical",
                extra={"output_var": output_var, "boundary": [boundary_w, boundary_h]},
            )
        elapsed = time.monotonic() - start
        logger.info(
            "roi_resolver[%s]: coord_type=%s phys=%s logical=%s -> var=%s",
            self.id, coord_type_str, physical_roi, logical_roi, output_var,
        )
        return success_result(data=result_data, elapsed_time=elapsed)
