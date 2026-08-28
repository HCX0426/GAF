"""P2-5 MultiScroll node: concurrent mouse wheel scroll at multiple coordinates.

Dispatches multiple wheel/scroll events to the device concurrently via
Device.multi_scroll() (if available) or sequentially via repeated
Device.wheel() calls as a fallback. Each scroll is a dict with
x/y/delta keys.

GAF extension (MaaFramework has no native "MultiScroll" concept).
Natural use cases: two-finger scroll on touchpads, scrolling multiple
list regions simultaneously.
"""

from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.exceptions import DeviceError
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)

# WHEEL_DELTA = 120 (one notch), same as WheelNode.
WHEEL_DELTA = 120


@register_node("multi_scroll")
@dataclass
class MultiScrollNode(PipelineNode):
    """Multi-scroll node: execute multiple wheel scrolls concurrently.

    Config parameters:
    - scrolls: List of scroll dicts, each with keys:
        - x, y: Coordinates (int)
        - delta: Wheel delta. Positive = up, negative = down.
            Default 120 (one notch up).
        - notches: Number of notches (alternative to delta, notches*120).
            If both delta and notches are set, delta wins.
    - parallel: True for concurrent execution (default True),
        False for sequential. Ignored if Device lacks multi_scroll().
    """

    node_type: str = "multi_scroll"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — N192 A1+A2: 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "parallel": self.config.get("parallel", True),
            "scrolls_count": len(self.config.get("scrolls", [])),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute multi-scroll via Device.multi_scroll() or fall back."""
        start = time.monotonic()

        device = context.device
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="PipelineContext device is None, cannot multi_scroll",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.DEVICE_DISCONNECTED),
            )

        scrolls = self.config.get("scrolls", [])
        if not scrolls:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="scrolls list is empty",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.PARAM_INVALID),
            )

        parallel = bool(self.config.get("parallel", True))

        # N191 §10.7 P0-4 (架构层归一化修复, 2026-07-27):
        # config x/y 是 BASE 坐标系, 若 context.coord_transformer 存在
        # (Windows + 配置 original_base_res, 或 ADB + original_base_res),
        # 需转 LOGICAL (Windows) / PHYSICAL (ADB) 才能给 device.wheel /
        # multi_scroll。无 transformer 时 raw 坐标直接用 (legacy 兼容)。
        transformer = getattr(context, 'coord_transformer', None)

        # Validate each scroll dict and resolve delta.
        normalized = []
        for i, s in enumerate(scrolls):
            if not isinstance(s, dict):
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"scroll[{i}] is not a dict: {type(s).__name__}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.PARAM_INVALID, scroll_index=i,
                    ),
                )
            try:
                # Resolve delta: explicit delta wins, else notches*WHEEL_DELTA,
                # else WHEEL_DELTA (one notch up).
                if "delta" in s:
                    delta = int(s["delta"])
                elif "notches" in s:
                    delta = int(s["notches"]) * WHEEL_DELTA
                else:
                    delta = WHEEL_DELTA
                sx = int(s.get("x", 0))
                sy = int(s.get("y", 0))
                if transformer is not None:
                    sx, sy = transformer.convert_original_to_current_client(sx, sy)
                normalized.append({
                    "x": sx,
                    "y": sy,
                    "delta": delta,
                })
            except (ValueError, TypeError) as exc:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"scroll[{i}] field parse failed: {exc}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.COORD_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.COORD_INVALID, scroll_index=i,
                    ),
                )

        try:
            # N191 §10.11 D5 (AI 可调试性, 2026-07-27): multi_scroll 是批量动作,
            # 记一次 batch trace 包含所有 scroll 坐标 + delta + 坐标系 (D4)。
            msc_coord_system = getattr(context, "coord_system", "") or "legacy"
            with contextlib.suppress(Exception):
                context.emit_coord_trace(
                    node_id=self.id,
                    step="device_multi_scroll",
                    raw=normalized,
                    converted=normalized,
                    formula=f"device.multi_scroll({len(normalized)} scrolls) | coord_system={msc_coord_system} | parallel={parallel}",
                    coord_system_in=msc_coord_system,
                    coord_system_out=msc_coord_system,
                    extra={"count": len(normalized), "parallel": parallel, "emulated": not hasattr(device, "multi_scroll")},
                )
            if hasattr(device, "multi_scroll"):
                device.multi_scroll(normalized, parallel=parallel)
            elif hasattr(device, "wheel"):
                # Sequential fallback when device lacks multi_scroll().
                for s in normalized:
                    device.wheel(s["x"], s["y"], delta=s["delta"])
            else:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg="device does not implement wheel() or multi_scroll()",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.DEVICE_ERROR,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.DEVICE_ERROR, normalized=normalized,
                    ),
                )
        except DeviceError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"device multi_scroll failed: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_ERROR, normalized=normalized,
                ),
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"multi_scroll exception: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN, normalized=normalized,
                ),
            )

        has_native = hasattr(device, "multi_scroll")
        result_data = {
            "count": len(normalized),
            "scrolls": normalized,
            "parallel": parallel and has_native,
            "emulated": not has_native,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }
        context.set_variable(f"{self.id}_multi_scroll_result", result_data)
        elapsed = time.monotonic() - start
        logger.info(
            "multi_scroll: %d scrolls, parallel=%s, emulated=%s, elapsed=%.3fs",
            len(normalized), result_data["parallel"], result_data["emulated"], elapsed,
        )
        return success_result(data=result_data, elapsed_time=elapsed)
