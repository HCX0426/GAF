"""P2-5 MultiTouch node: primitive multi-touch gesture composition.

Dispatches a list of touch primitives (down / move / up) to the device,
enabling arbitrary multi-touch gesture composition (pinch / zoom / rotate /
multi-finger drag). Mirrors MaaFramework Pipeline TouchDown / TouchMove /
TouchUp action semantics.

Each touch entry specifies:
  - action: "down" | "move" | "up"
  - contact: finger ID (ADB) / button ID (Win32), default 0
  - x, y: coordinates (required for down/move, ignored for up)
  - pressure: touch pressure, default 0

Dispatch priority:
  1. Device.multi_touch(touches, parallel=...) — true batched path
  2. Device.touch_down / touch_move / touch_up — sequential primitive path
  3. Device.click / swipe — degraded fallback (emulated=True)
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

_VALID_ACTIONS = {"down", "move", "up"}


@register_node("multi_touch")
@dataclass
class MultiTouchNode(PipelineNode):
    """Multi-touch primitive node: compose arbitrary multi-touch gestures.

    Config parameters:
    - touches: List of touch dicts, each with keys:
        - action: "down" | "move" | "up" (required)
        - contact: int finger/button ID (default 0)
        - x, y: int coordinates (required for down/move, ignored for up)
        - pressure: int (default 0)
    - parallel: True for batched execution when device supports it
        (default True). Ignored if Device lacks multi_touch().
    """

    node_type: str = "multi_touch"

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
            "touches_count": len(self.config.get("touches", [])),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute multi-touch primitives via Device dispatch."""
        start = time.monotonic()

        device = context.device
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="PipelineContext device is None, cannot multi_touch",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.DEVICE_DISCONNECTED),
            )

        touches = self.config.get("touches", [])
        if not touches:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="touches list is empty",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.PARAM_INVALID),
            )

        parallel = bool(self.config.get("parallel", True))

        # Validate each touch dict.
        # N191 P0-4 (架构层归一化修复, 2026-07-27):
        # config x/y 是 BASE 坐标系, 若 context.coord_transformer 存在
        # (Windows + 配置 original_base_res), 需转 LOGICAL 才能给
        # WindowsDevice 触摸原语 (期望 logical)。ADB 无 transformer, raw
        # physical 一致, 不转。
        transformer = getattr(context, 'coord_transformer', None)
        normalized = []
        for i, t in enumerate(touches):
            if not isinstance(t, dict):
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"touch[{i}] is not a dict: {type(t).__name__}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.PARAM_INVALID, touch_index=i,
                    ),
                )
            action = t.get("action", "")
            if action not in _VALID_ACTIONS:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=(
                        f"touch[{i}] invalid action {action!r}, "
                        f"expected one of {sorted(_VALID_ACTIONS)}"
                    ),
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.PARAM_INVALID,
                        touch_index=i, action=action,
                    ),
                )
            try:
                x = int(t.get("x", 0))
                y = int(t.get("y", 0))
                if transformer is not None and action in ("down", "move"):
                    x, y = transformer.convert_original_to_current_client(x, y)
                normalized.append({
                    "action": action,
                    "contact": int(t.get("contact", 0)),
                    "x": x,
                    "y": y,
                    "pressure": int(t.get("pressure", 0)),
                })
            except (ValueError, TypeError) as exc:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"touch[{i}] field parse failed: {exc}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.COORD_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.COORD_INVALID,
                        touch_index=i, touch_entry=t,
                    ),
                )

        emulated = False

        # N191 §10.11 D5 (AI 可调试性, 2026-07-27): multi_touch 是批量动作,
        # 记一次 batch trace 包含所有 touch 点, 让 AI 反推每个点的坐标 +
        # 坐标系 (D4 bug 现场重建)。
        mt_coord_system = getattr(context, "coord_system", "") or "legacy"
        with contextlib.suppress(Exception):
            context.emit_coord_trace(
                node_id=self.id,
                step="device_multi_touch",
                raw=normalized,
                converted=normalized,
                formula=f"device.multi_touch({len(normalized)} points) | coord_system={mt_coord_system} | parallel={parallel}",
                coord_system_in=mt_coord_system,
                coord_system_out=mt_coord_system,
                extra={"count": len(normalized), "parallel": parallel, "emulated": not hasattr(device, "multi_touch")},
            )
        try:
            if hasattr(device, "multi_touch"):
                device.multi_touch(normalized, parallel=parallel)
            elif hasattr(device, "touch_down") and hasattr(device, "touch_move") \
                    and hasattr(device, "touch_up"):
                # Sequential primitive path — real touch, just not batched.
                for t in normalized:
                    if t["action"] == "down":
                        device.touch_down(t["contact"], t["x"], t["y"], t["pressure"])
                    elif t["action"] == "move":
                        device.touch_move(t["contact"], t["x"], t["y"], t["pressure"])
                    else:
                        device.touch_up(t["contact"])
            else:
                # Degraded fallback: approximate with click/swipe.
                emulated = True
                logger.warning(
                    "multi_touch: device lacks touch primitives, "
                    "falling back to click/swipe emulation",
                )
                for t in normalized:
                    if t["action"] == "down":
                        device.click(t["x"], t["y"])
                    elif t["action"] == "move":
                        device.swipe(t["x"], t["y"], t["x"], t["y"], duration=0)
                    # "up" is a no-op in the degraded fallback.
        except DeviceError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"device multi_touch failed: {exc}",
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
                error_msg=f"multi_touch exception: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN, normalized=normalized,
                ),
            )

        has_native = hasattr(device, "multi_touch")
        result_data = {
            "count": len(normalized),
            "touches": normalized,
            "parallel": parallel and has_native,
            "emulated": emulated,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }
        context.set_variable(f"{self.id}_multi_touch_result", result_data)
        elapsed = time.monotonic() - start
        logger.info(
            "multi_touch: %d touches, parallel=%s, emulated=%s, elapsed=%.3fs",
            len(normalized), result_data["parallel"], emulated, elapsed,
        )
        return success_result(data=result_data, elapsed_time=elapsed)
