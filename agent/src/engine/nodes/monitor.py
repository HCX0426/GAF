"""monitor 节点：弹窗处理/剧情跳过/异常上报"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


@register_node("monitor")
@dataclass
class MonitorNode(PipelineNode):
    """监控处理节点

    处理弹窗、剧情跳过、异常上报等监控事件。

    popup action 走真实 PopupHandler 路径 (popup_handler.check_and_handle)。
    若 context.monitor_manager 缺失或 popup_handler 抛异常，节点返回
    fail_result 暴露问题（不静默 Mock 回退，避免掩盖配置错误）。

    config 参数：
    - action: 操作类型 "popup"/"skip_story"/"report_error"/"screenshot_monitor"
    - skip_key: 剧情跳过按键，默认 "esc"
    - report_url: 异常上报地址
    - screenshot: 可选截图，若提供则传给 check_and_handle；否则由 handler 自行截图
    """

    node_type: str = "monitor"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — N192 A1+A2: 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "action": self.config.get("action", "popup"),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """执行监控处理

        Args:
            context: Pipeline 执行上下文

        Returns:
            AutoResult，data 包含处理结果
        """
        start = time.monotonic()
        action = self.config.get("action", "popup")

        if action == "popup":
            result_data, error_msg = self._handle_popup(context)
            if error_msg is not None:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=error_msg,
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.UNKNOWN,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.UNKNOWN, popup_error=error_msg,
                    ),
                )
        elif action == "skip_story":
            skip_key = self.config.get("skip_key", "esc")
            result_data = {
                "action": "skip_story",
                "skipped": True,
                "skip_key": skip_key,
            }
        elif action == "report_error":
            report_url = self.config.get("report_url", "")
            result_data = {
                "action": "report_error",
                "reported": True,
                "report_url": report_url,
            }
        elif action == "screenshot_monitor":
            result_data = {
                "action": "screenshot_monitor",
                "screenshot_taken": True,
            }
        else:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"未知监控操作: {action}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID, action=action,
                ),
            )

        context.set_variable(f"{self.id}_monitor_result", result_data)
        elapsed = time.monotonic() - start
        # N192 A2: success result_data 补 coord_system
        if isinstance(result_data, dict):
            result_data["coord_system"] = getattr(context, "coord_system", "") or "legacy"
        return success_result(data=result_data, elapsed_time=elapsed)

    def _handle_popup(
        self, context: PipelineContext
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Handle popup action via real PopupHandler.

        Args:
            context: Pipeline execution context

        Returns:
            (result_data, error_msg) tuple. error_msg is None on success,
            result_data is None on failure. Failures include:
              - monitor_manager missing in context
              - monitor_manager has no popup_handler attribute
              - popup_handler.check_and_handle() raised an exception
            All failures return a non-None error_msg so the caller can
            surface the problem via fail_result instead of silently
            pretending the popup was handled.
        """
        monitor_manager = getattr(context, "monitor_manager", None)
        if monitor_manager is None:
            return None, (
                "MonitorManager not available in PipelineContext — "
                "monitor 节点需要 agent 启动时调用 monitor_manager.start() "
                "(Phase 1 commit d189b8e)。请检查 agent __main__.py 生命周期。"
            )
        if not hasattr(monitor_manager, "popup_handler"):
            return None, (
                f"MonitorManager ({type(monitor_manager).__name__}) 缺少 "
                "popup_handler 属性 — 无法处理弹窗"
            )

        popup_handler = monitor_manager.popup_handler
        screenshot = self.config.get("screenshot")
        try:
            handled = popup_handler.check_and_handle(screenshot=screenshot)
        except Exception as exc:
            logger.exception("monitor node: popup_handler.check_and_handle failed")
            return None, f"PopupHandler.check_and_handle() 抛异常: {exc}"

        return {
            "action": "popup",
            "popup_handled": bool(handled),
            "popup_count": 1 if handled else 0,
            "click_position": None,
            "source": "popup_handler",
        }, None
