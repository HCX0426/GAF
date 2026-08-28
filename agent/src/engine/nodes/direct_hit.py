"""P1-7 DirectHit node: skip recognition, click coordinates directly.

In MaaFramework Pipeline Protocol, "DirectHit" is a recognition type that
bypasses template/color/OCR matching and immediately "hits" the configured
coordinates. This node implements the same semantics: resolve (x, y) from
config (with ${var} support) and dispatch to Device.click().

Useful for scripted sequences where the target location is known in
advance (e.g. dialog buttons at fixed positions, tutorial overlays).
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


@register_node("direct_hit")
@dataclass
class DirectHitNode(PipelineNode):
    """Direct-hit node: skip recognition and click (x, y) immediately.

    Config parameters:
    - x: X coordinate (int), supports ${var} references.
    - y: Y coordinate (int), supports ${var} references.
    - button: Mouse button name, default "left".
    - clicks: Number of clicks, default 1.
    - interval: Interval between clicks (seconds), default 0.1.
    - activate_window: Default True.
    """

    node_type: str = "direct_hit"

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
            "clicks": self.config.get("clicks", 1),
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
        """Execute direct click without any recognition step."""
        start = time.monotonic()

        device = context.device
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="PipelineContext device is None, cannot direct_hit",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.DEVICE_DISCONNECTED),
            )

        try:
            x = self._resolve_coordinate(self.config.get("x", 0), context, "x")
            y = self._resolve_coordinate(self.config.get("y", 0), context, "y")
            # N191 P1-2 (架构层归一化修复, 2026-07-27):
            # config x/y 是 BASE 坐标系, 需转 LOGICAL (Windows) 才能给
            # device.click。${var} 引用若来自识别节点则已是 logical, 但若
            # 来自用户自定义变量仍是 BASE,统一转一次更安全 (transformer 对
            # 已是 logical 的输入会按 BASE→logical 比例缩放, 可能多转一次)。
            # 折中: 只对字面量 + ${var} 路径转, target 路径不转 (resolve_target
            # 已返回正确坐标系)。direct_hit 无 target, 所以全转。
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

        button = self.config.get("button", "left")
        clicks = int(self.config.get("clicks", 1))
        interval = float(self.config.get("interval", 0.1))
        activate_window = self.config.get("activate_window", True)

        if clicks < 1:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="clicks must be >= 1",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID, clicks=clicks,
                ),
            )

        if activate_window and hasattr(device, "activate_window"):
            try:
                device.activate_window()
                time.sleep(0.05)
            except Exception as exc:
                logger.warning("window activation failed (continuing): %s", exc)

        actual_clicks = 0
        # N191 §10.11 D5 (AI 可调试性, 2026-07-27): direct_hit 也走 device.click,
        # 必记 trace。与 click.py 一致, step 用 "device_click" 让 AI 跨节点
        # grep 时一次抓到所有 device.click 调用。
        dh_coord_system = getattr(context, "coord_system", "") or "legacy"
        with contextlib.suppress(Exception):
            context.emit_coord_trace(
                node_id=self.id,
                step="device_click",
                raw=(x, y),
                converted=(x, y),
                formula=f"device.click({x}, {y}) | coord_system={dh_coord_system} | button={button} clicks={clicks} (direct_hit)",
                coord_system_in=dh_coord_system,
                coord_system_out=dh_coord_system,
                extra={"button": button, "clicks": clicks, "interval": interval, "node_type": "direct_hit"},
            )
        try:
            for i in range(clicks):
                device.click(x, y)
                actual_clicks += 1
                if i < clicks - 1 and interval > 0:
                    time.sleep(interval)
        except DeviceError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"device click failed ({actual_clicks}/{clicks}): {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_ERROR,
                    x=x, y=y, actual_clicks=actual_clicks,
                ),
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"direct_hit exception ({actual_clicks}/{clicks}): {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN,
                    x=x, y=y, actual_clicks=actual_clicks,
                ),
            )

        result_data = {
            "x": x, "y": y, "button": button, "clicks": actual_clicks,
            "interval": interval, "recognition": "direct_hit",
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }
        context.set_variable(f"{self.id}_direct_hit_result", result_data)
        elapsed = time.monotonic() - start
        logger.info(
            "direct_hit: (%d,%d) button=%s clicks=%d/%d, elapsed=%.3fs",
            x, y, button, actual_clicks, clicks, elapsed,
        )
        return success_result(data=result_data, elapsed_time=elapsed)
