"""device_control 节点：切换窗口/启动模拟器/截图保存"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext


@register_node("device_control")
@dataclass
class DeviceControlNode(PipelineNode):
    """设备控制节点

    支持窗口切换、模拟器启动、截图保存等设备级操作。
    当前为 Mock 实现骨架。

    config 参数：
    - action: 操作类型 "switch_window"/"start_emulator"/"screenshot"/"stop_emulator"
    - window_title: 窗口标题（switch_window 时使用）
    - emulator_name: 模拟器名称（start_emulator 时使用）
    - save_path: 截图保存路径（screenshot 时使用）
    """

    node_type: str = "device_control"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — N192 A1+A2: 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "action": self.config.get("action", ""),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """执行设备控制操作（Mock 骨架）

        Args:
            context: Pipeline 执行上下文

        Returns:
            AutoResult，data 包含操作结果信息
        """
        start = time.monotonic()
        action = self.config.get("action", "")

        if action == "switch_window":
            window_title = self.config.get("window_title", "")
            result_data = {
                "action": "switch_window",
                "window_title": window_title,
                "result": "switched",
            }
        elif action == "start_emulator":
            emulator_name = self.config.get("emulator_name", "")
            result_data = {
                "action": "start_emulator",
                "emulator_name": emulator_name,
                "result": "started",
            }
        elif action == "screenshot":
            save_path = self.config.get("save_path", "")
            result_data = {
                "action": "screenshot",
                "save_path": save_path,
                "result": "saved",
            }
        elif action == "stop_emulator":
            emulator_name = self.config.get("emulator_name", "")
            result_data = {
                "action": "stop_emulator",
                "emulator_name": emulator_name,
                "result": "stopped",
            }
        else:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"未知设备操作: {action}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID, action=action,
                ),
            )

        context.set_variable(f"{self.id}_device_result", result_data)
        elapsed = time.monotonic() - start
        # N192 A2: success result_data 补 coord_system
        result_data["coord_system"] = getattr(context, "coord_system", "") or "legacy"
        return success_result(data=result_data, elapsed_time=elapsed)
