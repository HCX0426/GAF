"""swipe 节点：滑动操作 — 调用真实 Device.swipe()"""

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


@register_node("swipe")
@dataclass
class SwipeNode(PipelineNode):
    """Swipe/drag node that sends real swipe events via Device

    Config parameters:
    - x1, y1: Start coordinates (int)
    - x2, y2: End coordinates (int)
    - duration: Swipe duration in milliseconds, default 300
    - steps: Number of intermediate steps for smooth swipe, default 10
    - target: P0-6 target spec for start point (overrides x1/y1 when set).
        May be "_last_match_pos", "_anchor_pos", "${var}", or dict.
    - target_offset: P0-6 offset applied to the resolved start point.
    - end_target: P0-6 target spec for end point (overrides x2/y2 when set).
    - end_target_offset: P0-6 offset applied to the resolved end point.
    """

    node_type: str = "swipe"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — N192 A1+A2: 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "duration": self.config.get("duration", 300),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute real swipe via Device.swipe()

        Args:
            context: Pipeline execution context (must have device set)

        Returns:
            AutoResult with swipe result data
        """
        start = time.monotonic()

        device = context.device
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="PipelineContext 中未设置设备实例(device=None)，无法执行滑动",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.DEVICE_DISCONNECTED),
            )

        # P0-6: target / target_offset for start point; end_target for end point.
        target = self.config.get("target")
        target_offset = self.config.get("target_offset")
        end_target = self.config.get("end_target")
        end_target_offset = self.config.get("end_target_offset")
        try:
            if target is not None:
                x1, y1 = resolve_target(context, target, target_offset)
            else:
                x1 = int(self.config.get("x1", 0))
                y1 = int(self.config.get("y1", 0))
            if end_target is not None:
                x2, y2 = resolve_target(context, end_target, end_target_offset)
            else:
                x2 = int(self.config.get("x2", 0))
                y2 = int(self.config.get("y2", 0))
            # N191 P0-2 (架构层归一化修复, 2026-07-27):
            # config x1/y1/x2/y2 是 BASE 坐标系, 需转 LOGICAL 才能给
            # WindowsDevice.swipe (期望 logical)。target 路径 resolve_target
            # 已返回正确坐标系 (logical on Windows / physical on ADB), 不转。
            transformer = getattr(context, 'coord_transformer', None)
            if transformer is not None:
                if target is None:
                    x1, y1 = transformer.convert_original_to_current_client(x1, y1)
                if end_target is None:
                    x2, y2 = transformer.convert_original_to_current_client(x2, y2)
        except ValueError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"坐标解析失败: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.COORD_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.COORD_INVALID,
                    x1=self.config.get("x1"), y1=self.config.get("y1"),
                    x2=self.config.get("x2"), y2=self.config.get("y2"),
                    target=self.config.get("target"), end_target=self.config.get("end_target"),
                ),
            )
        duration = int(self.config.get("duration", 300))

        # N191 §10.11 D5 (AI 可调试性, 2026-07-27):
        # device.swipe 是动作节点的核心调用, 必记 trace。AI 调试时通过
        # grep "device_swipe" 看每个 swipe 节点传入 device 的起止坐标 +
        # 坐标系, 反推点击位置 (D4) + 跨设备对比 (D3)。与 click.py 一致。
        swipe_coord_system = getattr(context, "coord_system", "") or "legacy"
        with contextlib.suppress(Exception):
            context.emit_coord_trace(
                node_id=self.id,
                step="device_swipe",
                raw={"start": (x1, y1), "end": (x2, y2)},
                converted={"start": (x1, y1), "end": (x2, y2)},
                formula=f"device.swipe(({x1},{y1}) -> ({x2},{y2})) | coord_system={swipe_coord_system} | duration={duration}ms",
                coord_system_in=swipe_coord_system,
                coord_system_out=swipe_coord_system,
                extra={"duration": duration, "start_target": target is not None, "end_target": end_target is not None},
            )
        try:
            device.swipe(x1, y1, x2, y2, duration=duration)
        except DeviceError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"设备滑动失败: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_ERROR,
                    x1=x1, y1=y1, x2=x2, y2=y2,
                ),
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"滑动过程异常: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN,
                    x1=x1, y1=y1, x2=x2, y2=y2,
                ),
            )

        result_data = {
            "from": {"x": x1, "y": y1},
            "to": {"x": x2, "y": y2},
            "duration": duration,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }

        context.set_variable(f"{self.id}_swipe_result", result_data)
        elapsed = time.monotonic() - start
        logger.info(
            "滑动完成: (%d,%d) -> (%d,%d), duration=%dms, 耗时=%.3fs",
            x1, y1, x2, y2, duration, elapsed,
        )
        # Save debug image when debug_mode is enabled; capture path for
        # structured_logger correlation (spec 阶段 3.2).
        swipe_screenshot = self._save_debug(context, x1, y1, x2, y2, success=True)
        if swipe_screenshot.get("annotated"):
            result_data["screenshot_path"] = swipe_screenshot["annotated"]
        if swipe_screenshot.get("raw"):
            result_data["raw_screenshot_path"] = swipe_screenshot["raw"]
        return success_result(data=result_data, elapsed_time=elapsed)

    def _save_debug(
        self,
        context: PipelineContext,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        success: bool,
    ) -> dict[str, str | None]:
        """Save an annotated debug image when context.debug_mode is True.

        Returns dict {annotated, raw} (spec 阶段 6.5), or {None, None} when
        debug_mode is off / save failed / no device available. Swipe is an
        action node so raw is always None.
        """
        if not getattr(context, "debug_mode", False):
            return {"annotated": None, "raw": None}
        try:
            from utils.debug_image_saver import DebugImageSaver

            # N194 归一化 (2026-07-28): context.debug_dir 已是完整 exec_dir,
            # 不再拼 "action" 子目录. 见 template_match._save_debug 注释.
            debug_dir = getattr(context, "debug_dir", "./debug")
            saver = DebugImageSaver(debug_dir=debug_dir)
            device = getattr(context, "device", None)
            screen = None
            if device is not None and hasattr(device, "capture_screen"):
                try:
                    screen = device.capture_screen()
                except Exception as exc:
                    logger.debug("swipe debug capture error: %s", exc)
            if screen is None or screen.size == 0:
                return {"annotated": None, "raw": None}
            return saver.save_action_debug(
                screen=screen,
                node_id=self.id,
                node_type="swipe",
                is_success=success,
                action_info={"start": [x1, y1], "end": [x2, y2]},
            )
        except Exception as exc:
            logger.warning("swipe debug save failed: %s", exc, exc_info=True)
            return {"annotated": None, "raw": None}
