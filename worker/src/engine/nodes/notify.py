"""notify 节点：发送通知（日志 + 可选 webhook）。

C22 fix: frontend `PipelineNodeType` declares 'notify' but the agent
registry had no matching `@register_node` entry, so pipelines using
this node type raised ValueError at parse time.

This minimal implementation:
- Always logs the notification via the standard logger.
- Optionally POSTs JSON to a webhook URL (best-effort, 5s timeout,
  failure does not block the pipeline).
"""

from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.constants import ServerStatus
from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


@register_node("notify")
@dataclass
class NotifyNode(PipelineNode):
    """Send a notification via log and optional webhook.

    config parameters:
    - message: notification body (required, supports {var} template substitution)
    - title: optional notification title
    - channel: channel identifier (default "log")
    - level: log level "info" / "warning" / "error" (default "info")
    - variables: dict for {var} template substitution in `message`/`title`
    - webhook_url: optional HTTP webhook URL (POST JSON, 5s timeout)
    - webhook_headers: optional headers dict for webhook request
    """

    node_type: str = "notify"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "channel": self.config.get("channel", "log"),
            "level": str(self.config.get("level", "info")).lower(),
            "title": self.config.get("title", ""),
            "has_webhook_url": bool(self.config.get("webhook_url", "")),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()
        message_template = self.config.get("message", "")
        if not message_template:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="notify: 'message' config is required",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID, message_template="",
                ),
            )

        variables: dict[str, Any] = self.config.get("variables", {}) or {}
        try:
            message = (
                message_template.format(**variables) if variables else message_template
            )
        except (KeyError, IndexError) as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"notify: template variable error: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    template_error=str(exc),
                    variables_keys=list(variables.keys()) if isinstance(variables, dict) else [],
                ),
            )

        title = self.config.get("title", "")
        channel = self.config.get("channel", "log")
        level = str(self.config.get("level", "info")).lower()
        log_msg = (
            f"[notify:{channel}] {title}: {message}"
            if title
            else f"[notify:{channel}] {message}"
        )

        if level == ServerStatus.WARNING:
            logger.warning(log_msg)
        elif level == ServerStatus.ERROR:
            logger.error(log_msg)
        else:
            logger.info(log_msg)

        # Best-effort webhook delivery.
        webhook_url = self.config.get("webhook_url", "")
        webhook_status: dict[str, Any] = {"attempted": False}
        if webhook_url:
            webhook_status["attempted"] = True
            try:
                import requests  # lazy import; optional dependency

                payload = {
                    "channel": channel,
                    "title": title,
                    "message": message,
                    "level": level,
                }
                headers = self.config.get(
                    "webhook_headers", {"Content-Type": "application/json"}
                )
                resp = requests.post(
                    webhook_url, json=payload, headers=headers, timeout=5
                )
                webhook_status["status_code"] = resp.status_code
                if resp.status_code >= 400:
                    logger.warning(
                        "notify: webhook returned %d: %s",
                        resp.status_code,
                        resp.text[:200],
                    )
                    webhook_status["ok"] = False
                else:
                    webhook_status["ok"] = True
            except Exception as exc:
                logger.warning("notify: webhook failed: %s", exc)
                webhook_status["ok"] = False
                webhook_status["error"] = str(exc)

        elapsed = time.monotonic() - start
        result_data = {
            "channel": channel,
            "title": title,
            "message": message,
            "level": level,
            "webhook": webhook_status,
            # Task 4.47 (P2-25, 2026-07-28): success path 补 coord_system,
            # 与 wait/goto/template_match 等 _build_fail_diagnostics 字段口径对齐。
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }
        with contextlib.suppress(Exception):
            # Context may not support set_variable in all execution modes;
            # notification itself still succeeded.
            context.set_variable(f"{self.id}_notify_result", result_data)
        return success_result(data=result_data, elapsed_time=elapsed)
