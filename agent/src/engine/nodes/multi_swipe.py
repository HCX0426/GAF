"""P2-5 MultiSwipe node: concurrent multi-touch swipe gestures.

Dispatches multiple swipe gestures to the device concurrently via
Device.multi_swipe() (if available) or sequentially via repeated
Device.swipe() calls as a fallback. Each swipe is a dict with
x1/y1/x2/y2/duration_ms keys.

Mirrors MaaFramework Pipeline MultiSwipe action semantics for
multi-finger gestures (pinch / zoom / rotate / two-finger drag).
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


@register_node("multi_swipe")
@dataclass
class MultiSwipeNode(PipelineNode):
    """Multi-swipe node: execute multiple swipes concurrently.

    Config parameters:
    - swipes: List of swipe dicts, each with keys:
        - x1, y1: Start coordinates (int)
        - x2, y2: End coordinates (int)
        - duration_ms: Swipe duration in ms (optional, default 300)
    - parallel: True for concurrent execution (default True),
        False for sequential. Ignored if Device lacks multi_swipe().
    """

    node_type: str = "multi_swipe"

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
            "swipes_count": len(self.config.get("swipes", [])),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute multi-swipe via Device.multi_swipe() or fall back."""
        start = time.monotonic()

        device = context.device
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="PipelineContext device is None, cannot multi_swipe",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.DEVICE_DISCONNECTED),
            )

        swipes = self.config.get("swipes", [])
        if not swipes:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="swipes list is empty",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.PARAM_INVALID),
            )

        parallel = bool(self.config.get("parallel", True))

        # Validate each swipe dict has required keys.
        # N191 P0-3 (架构层归一化修复, 2026-07-27):
        # config x1/y1/x2/y2 是 BASE 坐标系, 若 context.coord_transformer
        # 存在 (Windows + 配置 original_base_res), 需转 LOGICAL 才能给
        # WindowsDevice.swipe/multi_swipe (期望 logical)。ADB 无 transformer,
        # raw physical 一致, 不转。
        transformer = getattr(context, 'coord_transformer', None)
        normalized = []
        for i, s in enumerate(swipes):
            if not isinstance(s, dict):
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"swipe[{i}] is not a dict: {type(s).__name__}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.PARAM_INVALID, swipe_index=i,
                    ),
                )
            try:
                x1 = int(s.get("x1", 0))
                y1 = int(s.get("y1", 0))
                x2 = int(s.get("x2", 0))
                y2 = int(s.get("y2", 0))
                if transformer is not None:
                    x1, y1 = transformer.convert_original_to_current_client(x1, y1)
                    x2, y2 = transformer.convert_original_to_current_client(x2, y2)
                normalized.append({
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "duration_ms": int(s.get("duration_ms", 300)),
                })
            except (ValueError, TypeError) as exc:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"swipe[{i}] coord parse failed: {exc}",
                    elapsed_time=elapsed,
                )

        try:
            # N191 §10.11 D5 (AI 可调试性, 2026-07-27): multi_swipe 是批量动作,
            # 记一次 batch trace 包含所有 swipe 起止坐标 + 坐标系 (D4)。
            ms_coord_system = getattr(context, "coord_system", "") or "legacy"
            with contextlib.suppress(Exception):
                context.emit_coord_trace(
                    node_id=self.id,
                    step="device_multi_swipe",
                    raw=normalized,
                    converted=normalized,
                    formula=f"device.multi_swipe({len(normalized)} swipes) | coord_system={ms_coord_system} | parallel={parallel}",
                    coord_system_in=ms_coord_system,
                    coord_system_out=ms_coord_system,
                    extra={"count": len(normalized), "parallel": parallel, "emulated": not hasattr(device, "multi_swipe")},
                )
            if hasattr(device, "multi_swipe"):
                device.multi_swipe(normalized, parallel=parallel)
            else:
                # Sequential fallback when device lacks multi_swipe().
                for s in normalized:
                    device.swipe(
                        s["x1"], s["y1"], s["x2"], s["y2"],
                        duration=s["duration_ms"],
                    )
        except DeviceError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"device multi_swipe failed: {exc}",
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
                error_msg=f"multi_swipe exception: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN, normalized=normalized,
                ),
            )

        result_data = {
            "count": len(normalized),
            "swipes": normalized,
            "parallel": parallel and hasattr(device, "multi_swipe"),
            "emulated": not hasattr(device, "multi_swipe"),
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }
        context.set_variable(f"{self.id}_multi_swipe_result", result_data)
        elapsed = time.monotonic() - start
        logger.info(
            "multi_swipe: %d swipes, parallel=%s, elapsed=%.3fs",
            len(normalized), result_data["parallel"], elapsed,
        )
        return success_result(data=result_data, elapsed_time=elapsed)
