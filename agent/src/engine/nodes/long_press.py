"""P1-7 LongPress node: long-press mouse button at coordinates.

Calls Device.long_press() (or InputVariant.long_press) which performs a
true mouse-down / sleep / mouse-up cycle rather than a click+wait,
matching MaaFramework's Pipeline long-press action semantics.
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
from engine.target import resolve_target

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


@register_node("long_press")
@dataclass
class LongPressNode(PipelineNode):
    """Long-press node that holds a mouse button for a duration.

    Config parameters:
    - target: Target spec (N191 系统性风险修复, 与 ClickNode 对齐).
        支持 "_last_match_pos" / "_anchor_pos" / "${var}" / {x,y} dict.
        若提供则优先于 x/y 字面量, 自动消费上游识别节点发布的坐标。
    - target_offset: 偏移量 dict {x,y} 或 list [x,y], 叠加到 target。
    - x: X coordinate (int), supports ${var} references (same as ClickNode).
    - y: Y coordinate (int), supports ${var} references.
    - button: Mouse button name ("left"/"right"/"middle"/"x1"/"x2"),
        default "left". P0-4 5-button support.
    - duration_ms: Hold duration in milliseconds, default 1000.
    - activate_window: Whether to activate the target window first,
        default True.
    """

    node_type: str = "long_press"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — N192 A1+A2: 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "button": self.config.get("button", "left"),
            "duration_ms": self.config.get("duration_ms", 1000),
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
        """Execute long-press via Device.long_press() if available, else
        fall back to click() + sleep (emulation)."""
        start = time.monotonic()

        device = context.device
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="PipelineContext device is None, cannot long_press",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.DEVICE_DISCONNECTED),
            )

        # N191 系统性风险修复: 支持 target spec, 与 ClickNode 对齐。
        # target 优先于 x/y 字面量, 自动消费 _last_match_pos / _anchor_pos。
        target = self.config.get("target")
        target_offset = self.config.get("target_offset")
        try:
            if target is not None:
                x, y = resolve_target(context, target, target_offset)
            else:
                x = self._resolve_coordinate(self.config.get("x", 0), context, "x")
                y = self._resolve_coordinate(self.config.get("y", 0), context, "y")
                # N191 P1-2 (架构层归一化修复): config x/y 是 BASE 坐标系,
                # 需转 LOGICAL 才能给 device.click/long_press (期望 logical)。
                # target 路径 resolve_target 已返回正确坐标系, 不转。
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
                    target=self.config.get("target"),
                ),
            )

        button = self.config.get("button", "left")
        duration_ms = int(self.config.get("duration_ms", 1000))
        activate_window = self.config.get("activate_window", True)

        if activate_window and hasattr(device, "activate_window"):
            try:
                device.activate_window()
                time.sleep(0.05)
            except Exception as exc:
                logger.warning("window activation failed (continuing): %s", exc)

        try:
            # Prefer true long_press; fall back to click+sleep emulation.
            # N191 §10.11 D5 (AI 可调试性, 2026-07-27): device.long_press /
            # device.click 是动作节点核心调用, 必记 trace。与 click.py 一致。
            lp_coord_system = getattr(context, "coord_system", "") or "legacy"
            with contextlib.suppress(Exception):
                context.emit_coord_trace(
                    node_id=self.id,
                    step="device_long_press",
                    raw=(x, y),
                    converted=(x, y),
                    formula=f"device.long_press({x}, {y}) | coord_system={lp_coord_system} | button={button} duration_ms={duration_ms}",
                    coord_system_in=lp_coord_system,
                    coord_system_out=lp_coord_system,
                    extra={"button": button, "duration_ms": duration_ms},
                )
            if hasattr(device, "long_press"):
                device.long_press(x, y, duration_ms=duration_ms, button=button)
            else:
                device.click(x, y)
                time.sleep(duration_ms / 1000.0)
        except DeviceError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"device long_press failed: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_ERROR, x=x, y=y,
                ),
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"long_press exception: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN, x=x, y=y,
                ),
            )

        result_data = {
            "x": x, "y": y, "button": button, "duration_ms": duration_ms,
            "emulated": not hasattr(device, "long_press"),
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }
        context.set_variable(f"{self.id}_long_press_result", result_data)
        elapsed = time.monotonic() - start
        logger.info(
            "long_press: (%d,%d) button=%s duration=%dms, elapsed=%.3fs",
            x, y, button, duration_ms, elapsed,
        )
        return success_result(data=result_data, elapsed_time=elapsed)
