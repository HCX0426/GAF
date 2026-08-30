"""Maa protocol engine action nodes (N126-F2 + N128-F2).

Implements 5 MaaFramework Pipeline protocol actions:
- JumpBack: jump back to the previous node for re-execution
- WaitFreezes: wait until screen content stabilizes (frame comparison)
- Next: skip remaining actions in current node, advance to next node
- Stop: stop the entire pipeline execution
- Anchor: N128-F2 — compute target position based on a reference element's offset

Reference: MaaFramework Pipeline protocol
https://github.com/MaaAssistantArknights/MaaFramework

All nodes follow the existing PipelineNode pattern and integrate with
PipelineContext variables for cross-node communication.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node
from engine.target import LAST_MATCH_POS_VAR, publish_match_pos

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)


# ============================================================
# JumpBack: jump back to previous node
# ============================================================


@register_node("jump_back")
@dataclass
class JumpBackNode(PipelineNode):
    """Jump back to the previous node for re-execution.

    Maa protocol action: JumpBack
    Sets a context variable "_jump_back_target" that the pipeline engine
    reads to redirect execution to the previous node.

    config params:
    - target_node_id: explicit target node ID (optional, overrides history)
    - steps_back: number of steps to jump back (default 1, ignored if
      target_node_id is set)
    """

    node_type: str = "jump_back"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "target_node_id": self.config.get("target_node_id", ""),
            "steps_back": self.config.get("steps_back", 1),
            "history_length": len(getattr(context, "execution_history", [])),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute jump back action.

        Args:
            context: Pipeline execution context.

        Returns:
            AutoResult with jump target info in data.
        """
        start = time.monotonic()

        target_node_id = self.config.get("target_node_id", "")
        steps_back = self.config.get("steps_back", 1)

        if not target_node_id:
            # Use execution history to find previous node
            history = getattr(context, "execution_history", [])
            if not history or len(history) < 1:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg="jump_back: no previous node in history",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.PARAM_INVALID,
                        reason="history_empty",
                    ),
                )
            # Pick node from history (skip current node which is self)
            idx = max(0, len(history) - steps_back - 1)
            target_node_id = history[idx].get("node_id", "") if idx < len(history) else ""

            if not target_node_id:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"jump_back: cannot find node {steps_back} steps back",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.PARAM_INVALID,
                        reason="history_index_unavailable",
                        history_index=idx,
                    ),
                )

        # Signal engine to jump back
        context.set_variable("_jump_back_target", target_node_id)
        context.set_variable("_jump_back_source", self.id)

        elapsed = time.monotonic() - start
        logger.info("JumpBack: %s -> %s", self.id, target_node_id)
        return success_result(
            data={
                "action": "jump_back",
                "target_node_id": target_node_id,
                "source_node_id": self.id,
                # Task 4.51 (P1-24~31, 2026-07-28): success path 补 coord_system 与识别类节点对齐
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            },
            elapsed_time=elapsed,
        )


# ============================================================
# WaitFreezes: wait until screen stabilizes
# ============================================================


@register_node("wait_freezes")
@dataclass
class WaitFreezesNode(PipelineNode):
    """Wait until screen content stabilizes (no longer changing).

    Maa protocol action: WaitFreezes
    Uses core.wait_freezes.WaitFreezes to compare consecutive frames.
    When frames are similar enough for N consecutive captures, the screen
    is considered stable and execution proceeds.

    config params:
    - timeout: max seconds to wait (default 10.0)
    - interval_ms: ms between captures (default 50)
    - stable_frames: consecutive similar frames required (default 3)
    - similarity: minimum similarity ratio 0-1 (default 0.99)
    - roi: optional {"x","y","w","h"} region to compare
    """

    node_type: str = "wait_freezes"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "timeout": self.config.get("timeout", 10.0),
            "interval_ms": self.config.get("interval_ms", 50.0),
            "stable_frames": self.config.get("stable_frames", 3),
            "similarity": self.config.get("similarity", 0.99),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute wait-freezes action.

        Args:
            context: Pipeline execution context. Must have device access
                via context.device.capture_screen().

        Returns:
            AutoResult with success=True if screen stabilized, False on timeout.
        """
        start = time.monotonic()

        # Lazy import to avoid circular dependency
        try:
            from core.wait_freezes import WaitFreezes
        except ImportError as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"wait_freezes: WaitFreezes module unavailable: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN,
                    import_error=str(exc),
                ),
            )

        device = getattr(context, "device", None)
        if device is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="wait_freezes: no device in context",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.DEVICE_DISCONNECTED,
                ),
            )

        timeout = self.config.get("timeout", 10.0)
        interval_ms = self.config.get("interval_ms", 50.0)
        stable_frames = self.config.get("stable_frames", 3)
        similarity = self.config.get("similarity", 0.99)
        roi_cfg = self.config.get("roi")

        diff_region = None
        if roi_cfg:
            diff_region = (
                roi_cfg.get("x", 0),
                roi_cfg.get("y", 0),
                roi_cfg.get("w", 0),
                roi_cfg.get("h", 0),
            )

        wf = WaitFreezes(
            interval_ms=interval_ms,
            stable_frames=stable_frames,
            default_similarity=similarity,
            diff_region=diff_region,
        )

        def capture_fn():
            try:
                return device.capture_screen()
            except Exception as exc:
                logger.debug("wait_freezes capture error: %s", exc)
                return None

        stable = wf.wait(capture_fn, timeout=timeout)
        elapsed = time.monotonic() - start

        if stable:
            logger.info("WaitFreezes: screen stable after %.2fs", elapsed)
            return success_result(
                data={
                    "action": "wait_freezes",
                    "stable": True,
                    "elapsed": elapsed,
                    # Task 4.51 (P1-24~31, 2026-07-28): success path 补 coord_system 与识别类节点对齐
                    "coord_system": getattr(context, "coord_system", "") or "legacy",
                },
                elapsed_time=elapsed,
            )
        else:
            return fail_result(
                error_msg=f"wait_freezes: timeout after {elapsed:.2f}s",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.TIMEOUT,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.TIMEOUT,
                    stable=False, elapsed=elapsed,
                ),
            )


# ============================================================
# Next: skip to next node
# ============================================================


@register_node("next")
@dataclass
class NextNode(PipelineNode):
    """Skip remaining actions in current node, advance to next node.

    Maa protocol action: Next
    Sets a context variable "_next_override" that the pipeline engine
    reads to skip any remaining sub-actions in the current node and
    proceed directly to the next node.

    config params:
    - target_node_id: explicit next node ID (optional, uses default
      next_node_id if not specified)
    """

    node_type: str = "next"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "target_node_id": self.config.get("target_node_id", ""),
            "default_next_node_id": self.next_node_id or "",
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute next action.

        Args:
            context: Pipeline execution context.

        Returns:
            AutoResult with next node info in data.
        """
        start = time.monotonic()

        target_node_id = self.config.get("target_node_id", "")
        if not target_node_id:
            target_node_id = self.next_node_id or ""

        if not target_node_id:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="next: no target_node_id and no default next_node_id",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    reason="both_target_and_default_empty",
                ),
            )

        context.set_variable("_next_override", target_node_id)
        context.set_variable("_next_source", self.id)

        elapsed = time.monotonic() - start
        logger.info("Next: %s -> %s", self.id, target_node_id)
        return success_result(
            data={
                "action": "next",
                "target_node_id": target_node_id,
                "source_node_id": self.id,
                # Task 4.51 (P1-24~31, 2026-07-28): success path 补 coord_system 与识别类节点对齐
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            },
            elapsed_time=elapsed,
        )


# ============================================================
# Stop: stop pipeline execution
# ============================================================


@register_node("stop")
@dataclass
class StopNode(PipelineNode):
    """Stop the entire pipeline execution.

    Maa protocol action: Stop
    Sets a context variable "_stop_requested" that the pipeline engine
    reads to halt execution after the current node completes.

    config params:
    - reason: optional reason string for stopping (default "user requested")
    - save_state: if True, save current pipeline state for resume (default True)
    """

    node_type: str = "stop"

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute stop action.

        Args:
            context: Pipeline execution context.

        Returns:
            AutoResult with stop info in data.
        """
        start = time.monotonic()

        reason = self.config.get("reason", "user requested")
        save_state = self.config.get("save_state", True)

        context.set_variable("_stop_requested", True)
        context.set_variable("_stop_reason", reason)
        context.set_variable("_stop_source", self.id)
        context.set_variable("_stop_save_state", save_state)

        elapsed = time.monotonic() - start
        logger.info("Stop: %s (reason=%s, save_state=%s)", self.id, reason, save_state)
        return success_result(
            data={
                "action": "stop",
                "reason": reason,
                "save_state": save_state,
                "source_node_id": self.id,
                # Task 4.51 (P1-24~31, 2026-07-28): success path 补 coord_system 与识别类节点对齐
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            },
            elapsed_time=elapsed,
        )


# ============================================================
# Anchor: compute target position based on reference element offset (N128-F2)
# ============================================================


@register_node("anchor")
@dataclass
class AnchorNode(PipelineNode):
    """Compute target position based on a reference element's offset.

    Maa protocol action: Anchor
    Locates a target position by applying an offset to a previously-identified
    reference element (template match / feature match / color detect result).
    Essential for dynamic UIs where element positions shift between runs —
    the reference element anchors the coordinate system and the target is
    computed relative to it.

    The reference position is read from a PipelineContext variable (set by a
    prior recognition node). The computed target position is stored into
    another context variable for downstream nodes (click/swipe/etc.) to use.

    config params:
    - reference_variable: context variable holding the reference position.
        Accepted formats:
          - {"x": int, "y": int} (center or top-left, see reference_type)
          - {"x": int, "y": int, "w": int, "h": int} (bounding box)
          - (x, y) tuple
        Default: "_last_match_pos"
    - reference_type: how to interpret the reference position:
        - "center": (x, y) is the element center (default)
        - "top_left": (x, y) is the top-left corner; center is computed via w/h
        - "custom": (x, y) used as-is
    - offset_x: X offset from reference center (pixels, can be negative)
    - offset_y: Y offset from reference center (pixels, can be negative)
    - output_variable: context variable to store computed target position.
        Default: "_anchor_pos"
        Stored format: {"x": int, "y": int, "source": "anchor", "reference": {...}}
    - absolute: if True, offset_x/offset_y are absolute screen coordinates
        (not relative to reference). Default: False.
    """

    node_type: str = "anchor"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "reference_variable": self.config.get("reference_variable", "_last_match_pos"),
            "reference_type": self.config.get("reference_type", "center"),
            "offset_x": self.config.get("offset_x", 0),
            "offset_y": self.config.get("offset_y", 0),
            "output_variable": self.config.get("output_variable", "_anchor_pos"),
            "absolute": self.config.get("absolute", False),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute anchor action — compute target position from reference + offset.

        Args:
            context: Pipeline execution context. Must have a reference position
                stored in the variable named by reference_variable.

        Returns:
            AutoResult with computed target position in data.
            On failure, returns fail_result with a descriptive error_msg.
        """
        start = time.monotonic()

        reference_variable = self.config.get("reference_variable", "_last_match_pos")
        reference_type = self.config.get("reference_type", "center")
        offset_x = self.config.get("offset_x", 0)
        offset_y = self.config.get("offset_y", 0)
        output_variable = self.config.get("output_variable", "_anchor_pos")
        absolute = self.config.get("absolute", False)

        ref_raw = context.get_variable(reference_variable)
        if ref_raw is None:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"anchor: reference variable '{reference_variable}' not found in context",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    ref_var_not_found=True,
                ),
            )

        # Normalize reference to (center_x, center_y)
        try:
            ref_x, ref_y = self._extract_center(ref_raw, reference_type)
        except (KeyError, TypeError, ValueError) as exc:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"anchor: cannot extract center from reference {ref_raw!r}: {exc}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    ref_raw_type=type(ref_raw).__name__,
                    extract_error=str(exc),
                ),
            )

        # Compute target
        if absolute:
            target_x = int(offset_x)
            target_y = int(offset_y)
        else:
            target_x = int(ref_x + offset_x)
            target_y = int(ref_y + offset_y)

        target = {
            "x": target_x,
            "y": target_y,
            "source": "anchor",
            "reference": {"x": ref_x, "y": ref_y, "type": reference_type},
            "offset": {"x": offset_x, "y": offset_y, "absolute": absolute},
        }

        # N191 §10.7 P0-1 架构层补漏 (2026-07-27): 走 publish_match_pos 统一入口,
        # 让 coord_system / source / extra 字段自动注入。
        # 之前直接 set_variable("_last_match_pos", {"x","y"}) 绕过本函数, 导致:
        #   1. coord_system 字段丢失, 下游 resolve_target 无法判断坐标系
        #   2. structured_logger 拿不到 source 标签
        #   3. AnchorNode 与其他识别节点 (template_match/ocr/feature_match/
        #      color_detect) 行为不一致
        # 现在两次调用 publish_match_pos: 一次写 _last_match_pos (标准契约,
        # 让 click/swipe 默认 target=_last_match_pos 拿到 anchor 位置),
        # 一次写 output_variable (用户自定义变量名, 默认 _anchor_pos, 让
        # ${_anchor_pos} 引用也能拿到带 coord_system 的 pos)。
        publish_match_pos(
            context, target_x, target_y,
            source=f"{self.id}:anchor",
            extra={
                "reference": target["reference"],
                "offset": target["offset"],
                "absolute": absolute,
            },
            var_name=LAST_MATCH_POS_VAR,
        )
        publish_match_pos(
            context, target_x, target_y,
            source=f"{self.id}:anchor",
            extra={
                "reference": target["reference"],
                "offset": target["offset"],
                "absolute": absolute,
            },
            var_name=output_variable,
        )

        elapsed = time.monotonic() - start
        logger.info(
            "Anchor: %s ref=(%d,%d) +offset=(%d,%d) -> target=(%d,%d) [var=%s]",
            self.id,
            ref_x,
            ref_y,
            offset_x,
            offset_y,
            target_x,
            target_y,
            output_variable,
        )
        return success_result(
            data={
                "action": "anchor",
                "target": target,
                "output_variable": output_variable,
                "source_node_id": self.id,
                # Task 4.47 (P2-31, 2026-07-28): AnchorNode success path 补 coord_system
                "coord_system": getattr(context, "coord_system", "") or "legacy",
            },
            elapsed_time=elapsed,
        )

    @staticmethod
    def _extract_center(ref_raw: Any, reference_type: str) -> tuple[int, int]:
        """Extract (center_x, center_y) from a reference position value.

        Args:
            ref_raw: The raw reference value from context. Supported formats:
                - dict with "x"/"y" (and optional "w"/"h")
                - tuple/list of (x, y) or (x, y, w, h)
            reference_type: "center" / "top_left" / "custom"

        Returns:
            Tuple of (center_x, center_y) as ints.

        Raises:
            KeyError: if dict is missing required keys.
            TypeError: if ref_raw is not dict/tuple/list.
            ValueError: if reference_type is invalid.
        """
        if isinstance(ref_raw, dict):
            x = int(ref_raw["x"])
            y = int(ref_raw["y"])
            w = int(ref_raw.get("w", 0))
            h = int(ref_raw.get("h", 0))
        elif isinstance(ref_raw, (tuple, list)):
            if len(ref_raw) < 2:
                raise ValueError(f"reference tuple/list must have >= 2 elements, got {len(ref_raw)}")
            x = int(ref_raw[0])
            y = int(ref_raw[1])
            w = int(ref_raw[2]) if len(ref_raw) >= 4 else 0
            h = int(ref_raw[3]) if len(ref_raw) >= 4 else 0
        else:
            raise TypeError(f"reference must be dict/tuple/list, got {type(ref_raw).__name__}")

        if reference_type == "center":
            # (x, y) is already the center
            return x, y
        if reference_type == "top_left":
            # Compute center from top-left + half size
            if w <= 0 or h <= 0:
                # No size info — treat as center
                logger.warning("anchor: reference_type=top_left but no w/h, treating as center")
                return x, y
            return x + w // 2, y + h // 2
        if reference_type == "custom":
            return x, y
        raise ValueError(f"invalid reference_type: {reference_type!r}")
