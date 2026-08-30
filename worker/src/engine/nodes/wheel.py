"""P0-5 Wheel node: mouse wheel scroll at coordinates.

Calls Device.wheel() (if available) to send a vertical mouse wheel
event at (x, y). Falls back to no-op when device lacks wheel().

Mirrors MaaFramework Pipeline wheel action semantics for scrollable
UI elements (lists, menus, maps).
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

# WHEEL_DELTA = 120 (one notch). Import lazily so this module imports
# cleanly on non-Windows hosts for type checking.
WHEEL_DELTA = 120


@register_node("wheel")
@dataclass
class WheelNode(PipelineNode):
    """Mouse wheel scroll node.

    Config parameters:
    - x: X coordinate (int), supports ${var} references.
    - y: Y coordinate (int), supports ${var} references.
    - delta: Wheel delta. Positive = up, negative = down.
        Default 120 (one notch up). WHEEL_DELTA = 120.
    - notches: Number of notches to scroll (alternative to delta).
        If both delta and notches are set, delta wins.
    """

    node_type: str = "wheel"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — N192 A1+A2: 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "delta": self.config.get("delta", WHEEL_DELTA),
        }
        data.update(kwargs)
        return data

    def _resolve_coordinate(self, raw_value, context: PipelineContext, axis: str) -> int:
        """Resolve coordinate value from literal int or ${var} reference."""
        if isinstance(raw_value, (int, float)):
            return int(raw_value)
        if isinstance(raw_value, str):
            if raw_value.startswith("${") and raw_value.endswith("}"):
                var_name = raw_value[2:-1]
                var_value = context.get_variable(var_name)
                if var_value is None:
                    raise ValueError(f"variable {var_name!r} not found for {axis} coord")
                if isinstance(var_value, dict):
                    if axis not in var_value:
                        raise ValueError(f"variable {var_name!r} missing {axis!r} field")
                    return int(var_value[axis])
                return int(var_value)
            try:
                return int(float(raw_value))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"cannot parse {axis} coord: {raw_value!r}") from exc
        raise ValueError(f"unsupported {axis} coord type: {type(raw_value).__name__}")

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute wheel scroll via Device.wheel() if available."""
        start = time.monotonic()

        device = context.device
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="PipelineContext device is None, cannot wheel",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.DEVICE_DISCONNECTED),
            )

        try:
            x = self._resolve_coordinate(self.config.get("x", 0), context, "x")
            y = self._resolve_coordinate(self.config.get("y", 0), context, "y")
            # N191 §10.7 P0-4 (架构层归一化修复, 2026-07-27):
            # config x/y 是 BASE 坐标系 (用户在 original_base_res 下定义),
            # 需转 LOGICAL (Windows) / PHYSICAL (ADB) 才能给 device.wheel。
            # ${var} 引用若来自识别节点则已是正确坐标系, 但若来自用户自定义
            # 变量仍是 BASE; transformer 对已是正确坐标系的输入会按 BASE 比例
            # 缩放, 可能多转一次。折中: wheel 无 target 路径, 全转。
            transformer = getattr(context, 'coord_transformer', None)
            if transformer is not None:
                x, y = transformer.convert_original_to_current_client(x, y)
        except ValueError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"coord resolve failed: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.COORD_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.COORD_INVALID,
                    x=self.config.get("x"), y=self.config.get("y"),
                ),
            )

        # Resolve delta: explicit delta wins, else notches * WHEEL_DELTA, else 120.
        if "delta" in self.config:
            delta = int(self.config["delta"])
        elif "notches" in self.config:
            delta = int(self.config["notches"]) * WHEEL_DELTA
        else:
            delta = WHEEL_DELTA

        try:
            if hasattr(device, "wheel"):
                # N191 §10.11 D5 (AI 可调试性, 2026-07-27): device.wheel 必记 trace。
                wh_coord_system = getattr(context, "coord_system", "") or "legacy"
                with contextlib.suppress(Exception):
                    context.emit_coord_trace(
                        node_id=self.id,
                        step="device_wheel",
                        raw=(x, y),
                        converted=(x, y),
                        formula=f"device.wheel({x}, {y}, delta={delta}) | coord_system={wh_coord_system}",
                        coord_system_in=wh_coord_system,
                        coord_system_out=wh_coord_system,
                        extra={"delta": delta},
                    )
                device.wheel(x, y, delta=delta)
            else:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg="device does not implement wheel()",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.DEVICE_ERROR,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.DEVICE_ERROR, x=x, y=y, delta=delta,
                    ),
                )
        except DeviceError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"device wheel failed: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_ERROR, x=x, y=y, delta=delta,
                ),
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"wheel exception: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN, x=x, y=y, delta=delta,
                ),
            )

        result_data = {
            "x": x, "y": y, "delta": delta,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }
        context.set_variable(f"{self.id}_wheel_result", result_data)
        elapsed = time.monotonic() - start
        logger.info(
            "wheel: (%d,%d) delta=%d, elapsed=%.3fs",
            x, y, delta, elapsed,
        )
        return success_result(data=result_data, elapsed_time=elapsed)
