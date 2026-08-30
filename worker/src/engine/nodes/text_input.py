"""text_input 节点：文字输入 — 调用真实 Device.text_input()"""

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


@register_node("text_input")
@dataclass
class TextInputNode(PipelineNode):
    """Text input node that sends real text via Device.text_input()

    Config parameters:
    - text: Text string to input
    - interval: Interval between characters (seconds), default 0.02
    - clear_before: Whether to clear field before input (bool), default False
    """

    node_type: str = "text_input"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — N192 A1+A2: 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "text": self.config.get("text", ""),
            "clear_before": self.config.get("clear_before", False),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute real text input via Device.text_input()

        Args:
            context: Pipeline execution context (must have device set)

        Returns:
            AutoResult with text input result data
        """
        start = time.monotonic()

        device = context.device
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="PipelineContext 中未设置设备实例(device=None)，无法执行文本输入",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.DEVICE_DISCONNECTED),
            )

        text = self.config.get("text", "")
        interval = float(self.config.get("interval", 0.02))
        clear_before = bool(self.config.get("clear_before", False))

        if not text:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="输入文本为空",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(context, NodeErrorCode.PARAM_INVALID),
            )

        try:
            # Optionally clear before input (select all + delete/backspace)
            if clear_before:
                try:
                    device.key_press("ctrl")
                    time.sleep(0.02)
                    device.key_press("a")
                    time.sleep(0.02)
                    device.key_press("backspace")
                    time.sleep(0.05)
                except Exception as exc:
                    logger.warning("清空输入框失败（继续执行输入）: %s", exc)

            # Input text via device
            device.text_input(text)

        except DeviceError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"设备文本输入失败: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_ERROR,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_ERROR, text=text,
                ),
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"文本输入过程异常: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN, text=text,
                ),
            )

        result_data = {
            "text": text,
            "length": len(text),
            "interval": interval,
            "clear_before": clear_before,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }

        context.set_variable(f"{self.id}_text_result", result_data)
        elapsed = time.monotonic() - start
        logger.info(
            "文本输入完成: text='%s'(%d chars), 耗时=%.3fs",
            text[:50], len(text), elapsed,
        )
        return success_result(data=result_data, elapsed_time=elapsed)
