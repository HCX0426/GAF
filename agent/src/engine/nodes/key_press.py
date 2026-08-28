"""key_press 节点：按键输入 — 调用真实 Device.key_press()"""

from __future__ import annotations

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


@register_node("key_press")
@dataclass
class KeyPressNode(PipelineNode):
    """Key press node that sends real key events via Device

    Config parameters:
    - key: Key name or key code (str), e.g. "enter", "escape", "a", "F1"
    - modifiers: Modifier keys list ["ctrl", "alt", "shift"], optional
    - hold_duration: Key hold duration in seconds, default 0.05
    """

    node_type: str = "key_press"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — N192 A1+A2: 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "key": self.config.get("key", ""),
            "modifiers": self.config.get("modifiers", []),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute real key press via Device.key_press()

        Args:
            context: Pipeline execution context (must have device set)

        Returns:
            AutoResult with key press result data
        """
        start = time.monotonic()

        device = context.device
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="PipelineContext 中未设置设备实例(device=None)，无法执行按键",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.DEVICE_DISCONNECTED),
            )

        key = self.config.get("key", "")
        modifiers: list[str] = self.config.get("modifiers", [])
        hold_duration = float(self.config.get("hold_duration", 0.05))

        if not key:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="按键名称为空",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.PARAM_INVALID),
            )

        # True modifier+key combo (TD-398): hold modifiers while pressing the
        # main key, then release — old code tapped each modifier independently,
        # leaking e.g. Ctrl+L's 'l' into the focused field (Chrome omnibox).
        try:
            if modifiers:
                device.key_combo(modifiers, key)
            else:
                device.key_press(key)
        except DeviceError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"设备按键失败: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_ERROR, key=key,
                ),
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"按键过程异常: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN, key=key,
                ),
            )

        result_data = {
            "key": key,
            "modifiers": modifiers,
            "hold_duration": hold_duration,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }

        context.set_variable(f"{self.id}_key_result", result_data)
        elapsed = time.monotonic() - start
        logger.info(
            "按键完成: key=%s, modifiers=%s, 耗时=%.3fs",
            key, modifiers, elapsed,
        )
        # Save debug image when debug_mode is enabled; capture path for
        # structured_logger correlation (spec 阶段 3.2).
        kp_screenshot = self._save_debug(context, key, modifiers, success=True)
        if kp_screenshot.get("annotated"):
            result_data["screenshot_path"] = kp_screenshot["annotated"]
        if kp_screenshot.get("raw"):
            result_data["raw_screenshot_path"] = kp_screenshot["raw"]
        return success_result(data=result_data, elapsed_time=elapsed)

    def _save_debug(
        self,
        context: PipelineContext,
        key: str,
        modifiers: list[str],
        success: bool,
    ) -> dict[str, str | None]:
        """Save an annotated debug image when context.debug_mode is True.

        Returns dict {annotated, raw} (spec 阶段 6.5), or {None, None} when
        debug_mode is off / save failed / no device available. key_press is
        an action node so raw is always None.
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
                    logger.debug("key_press debug capture error: %s", exc)
            if screen is None or screen.size == 0:
                return {"annotated": None, "raw": None}
            return saver.save_action_debug(
                screen=screen,
                node_id=self.id,
                node_type="key_press",
                is_success=success,
                action_info={"key": key, "modifiers": list(modifiers)},
            )
        except Exception as exc:
            logger.warning("key_press debug save failed: %s", exc, exc_info=True)
            return {"annotated": None, "raw": None}
