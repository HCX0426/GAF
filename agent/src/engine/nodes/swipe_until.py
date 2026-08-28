"""swipe_until 节点：循环滑动直到任一模板匹配成功 — 支持多备选模板 + 最大滑动次数

Composite node that repeatedly swipes the screen and checks for a template
match in between, stopping as soon as any of the candidate templates is found.
Reuses template_match_any (which itself reuses template_match) and swipe via
the child-spec execution pattern (run_child), so all existing match / swipe
features are transparently inherited.

Typical use case (TD-013): a chapter list may need scrolling before the target
chapter entry becomes visible. Instead of hard-coding a single swipe, this node
expresses "swipe up to N times, checking after each swipe for any of the
candidate chapter templates, click on first match".
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node
from engine.nodes._child_runner import run_child

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


@register_node("swipe_until")
@dataclass
class SwipeUntilNode(PipelineNode):
    """Swipe loop — swipe until any candidate template matches.

    The node first tries to match before performing any swipe (the target may
    already be on screen). On miss it swipes once, waits ``delay_between``
    seconds for the screen to settle, then retries. The loop runs at most
    ``max_swipes`` swipe operations (so up to ``max_swipes + 1`` match
    attempts).

    Config parameters:
    - templates: List[str] — candidate template paths/data (required). Any
        match wins. Forwarded to template_match_any.
    - threshold: float — match confidence threshold, default 0.8
    - click_on_match: bool — click matched center after success, default false
    - roi: dict/list — search region forwarded to template_match_any, optional
    - x1, y1, x2, y2: int — swipe start / end coordinates (required)
    - duration: int — swipe duration in ms, default 300
    - max_swipes: int — max number of swipe operations, default 3
    - delay_between: float — seconds to wait after each swipe before retrying
        match, default 0.5

    Returns:
        success_result with data={"winner": <match data>, "attempts": <all
        attempts>, "swipes_performed": <int>, "matched": True} on first match.
        fail_result with data={"attempts": <all attempts>,
        "swipes_performed": max_swipes, "matched": False} if every attempt
        fails.

    Context variable:
        On success, sets ``{self.id}_match_result`` to the winner's match data
        (same convention as template_match / template_match_any).
    """

    node_type: str = "swipe_until"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "templates": self.config.get("templates", []),
            "threshold": self.config.get("threshold", 0.8),
            "max_swipes": int(self.config.get("max_swipes", 3)),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        start = time.monotonic()

        templates: list[str] = self.config.get("templates", [])
        if not templates:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="swipe_until requires non-empty 'templates' list",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID, templates=[],
                ),
            )

        max_swipes = int(self.config.get("max_swipes", 3))
        delay_between = float(self.config.get("delay_between", 0.5))

        # Build the match child spec once (template_match_any reuses
        # template_match under the hood). Optional roi forwarded only if set.
        match_config: dict[str, Any] = {
            "templates": templates,
            "threshold": self.config.get("threshold", 0.8),
            "click_on_match": self.config.get("click_on_match", False),
        }
        if "roi" in self.config:
            match_config["roi"] = self.config["roi"]
        if "roi_coord_type" in self.config:
            match_config["roi_coord_type"] = self.config["roi_coord_type"]
        if "scale" in self.config:
            match_config["scale"] = self.config["scale"]

        match_child_spec = {
            "id": f"{self.id}_match",
            "node_type": "template_match_any",
            "config": match_config,
        }

        # Build the swipe child spec once.
        swipe_child_spec = {
            "id": f"{self.id}_swipe",
            "node_type": "swipe",
            "config": {
                "x1": int(self.config.get("x1", 0)),
                "y1": int(self.config.get("y1", 0)),
                "x2": int(self.config.get("x2", 0)),
                "y2": int(self.config.get("y2", 0)),
                "duration": int(self.config.get("duration", 300)),
            },
        }

        attempts: list[dict[str, Any]] = []
        swipes_performed = 0

        # Loop: match → (swipe → wait → match)*. The match attempt at index 0
        # happens before any swipe so we detect the already-visible case.
        for attempt in range(max_swipes + 1):
            r = run_child(match_child_spec, context)
            attempts.append({
                "attempt": attempt,
                "phase": "match",
                "success": r.success,
                "error": r.error_msg,
                "data": r.data,
            })

            if r.success:
                # Publish under the parent node's id so downstream target
                # resolution / branch nodes read a stable variable name.
                match_data = r.data.get("winner", {}).get("data") if isinstance(r.data, dict) else None
                context.set_variable(f"{self.id}_match_result", match_data)
                elapsed = time.monotonic() - start
                logger.info(
                    "swipe_until 命中: attempt=%d, swipes_performed=%d",
                    attempt, swipes_performed,
                )
                return success_result(
                    data={
                        "winner": match_data,
                        "attempts": attempts,
                        "swipes_performed": swipes_performed,
                        "matched": True,
                    },
                    elapsed_time=elapsed,
                )

            # No more swipes allowed — exit loop and report failure.
            if attempt >= max_swipes:
                break

            # Swipe once, then wait for the screen to settle before retrying.
            swipe_r = run_child(swipe_child_spec, context)
            swipes_performed += 1
            attempts.append({
                "attempt": attempt,
                "phase": "swipe",
                "success": swipe_r.success,
                "error": swipe_r.error_msg,
            })
            if not swipe_r.success:
                logger.warning(
                    "swipe_until: swipe child failed at attempt %d: %s",
                    attempt, swipe_r.error_msg,
                )
            if delay_between > 0:
                time.sleep(delay_between)

        elapsed = time.monotonic() - start
        logger.info(
            "swipe_until 全部失败: swipes_performed=%d, attempts=%d",
            swipes_performed, len(attempts),
        )
        diagnostics = self._build_fail_diagnostics(
            context, NodeErrorCode.NO_MATCH,
            swipes_performed=swipes_performed,
            attempts_count=len(attempts),
        )
        diagnostics.update({
            "attempts": attempts,
            "swipes_performed": swipes_performed,
            "matched": False,
        })
        return fail_result(
            error_msg=f"swipe_until: no match after {swipes_performed} swipes",
            error_code=NodeErrorCode.NO_MATCH,
            node_id=self.id,
            node_type=self.node_type,
            data=diagnostics,
            elapsed_time=elapsed,
        )
