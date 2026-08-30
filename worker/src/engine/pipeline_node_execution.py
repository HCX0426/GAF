"""PipelineEngine：Pipeline 通用执行器"""

from __future__ import annotations

import logging
import time
from typing import Any

import engine.nodes  # noqa: F401  (side-effect import: populates registry)
from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result
from engine.node import PIPELINE_NODE_REGISTRY, PipelineNode

logger = logging.getLogger(__name__)


class PipelineNodeExecutionMixin:
    """PipelineEngine mixin — see pipeline_engine.py for full class (s35 split)."""

    def _execute_node_step(self, node: PipelineNode) -> AutoResult:
        """Execute a single node with pre/post lifecycle and repeat logic.

        Extracted from execute() so it can be wrapped in a step-level
        timeout via ThreadPoolExecutor (spec 阶段 2.2). Runs in a worker
        thread; the main thread enforces ``config["timeout"]``.

        Lifecycle order (spec-2026-07-27-execution-path-unification 阶段 2
        吸收 chain step 控制流):
        1. pre_verify — 节点属性优先, 回退到 config["pre_verify"] (向后兼容)
        2. pre_delay / pre_wait_freezes
        3. node.execute() — repeated ``repeat`` times (or until failure
           when ``repeat_until_failure=True``)
        4. retry — 节点失败时按指数退避重试 (吸收 chain step.retry)
        5. fallback — 重试仍失败时执行回退方案 (吸收 chain step.fallback)
        6. post_verify — 节点成功后强验证 (吸收 chain step.post_verify)
        7. post_delay / post_wait_freezes

        Args:
            node: Pipeline node to execute.

        Returns:
            AutoResult from the (last) node.execute() call.
        """
        # spec-2026-07-27 阶段 2: pre_verify 强验证 (吸收 chain step.pre_verify).
        # 节点属性优先；老 pipeline JSON 可能把 pre_verify 放在 config 里，回退读取。
        # 未注入 verifier 时静默跳过（向后兼容）。
        pre_verify_cfg = node.pre_verify or node.config.get("pre_verify")
        if isinstance(pre_verify_cfg, dict) and pre_verify_cfg and self._verifier is not None:
            try:
                pre_verify_result = self._verifier.verify(pre_verify_cfg)
            except Exception as exc:
                logger.exception("节点 %s pre_verify 异常: %s", node.id, exc)
                result = fail_result(
                    error_msg=f"pre_verify 异常 ({type(exc).__name__}): {exc}",
                    error_code=NodeErrorCode.PRE_VERIFY_FAILED,
                    node_id=node.id,
                    node_type=node.node_type,
                )
                self._log_node_verify_event(node, "node.execute.pre_verify_failed", result)
                return result
            if not pre_verify_result.success:
                logger.warning(
                    "节点 %s pre_verify 失败: %s", node.id, pre_verify_result.error_msg,
                )
                result = fail_result(
                    error_msg=f"pre_verify 失败: {pre_verify_result.error_msg}",
                    error_code=NodeErrorCode.PRE_VERIFY_FAILED,
                    node_id=node.id,
                    node_type=node.node_type,
                )
                self._log_node_verify_event(node, "node.execute.pre_verify_failed", result)
                return result

        # P1-8: Node lifecycle fields — pre_delay / pre_wait_freezes.
        self._apply_pre_lifecycle(node)

        # P1-8: repeat — execute the node N times (or until failure
        # when repeat_until_failure=True).
        repeat = node.config.get("repeat", 1)
        repeat_until_failure = node.config.get("repeat_until_failure", False)
        if not isinstance(repeat, int) or repeat < 1:
            repeat = 1

        result = node.execute(self._context)
        if repeat > 1 or repeat_until_failure:
            for _ in range(repeat - 1) if not repeat_until_failure else iter(int, 1):
                if not result.success:
                    break
                if self._cancel_event.is_set():
                    break
                if self._step_cancel_event.is_set():  # TD-353: 步骤超时
                    break
                r = node.execute(self._context)
                if not r.success and repeat_until_failure:
                    # Expected failure for repeat_until_failure pattern.
                    result = r
                    break
                result = r

        # Auto-fill node metadata for diagnosis (spec 阶段 3.4.2 — 任务 1.2).
        # Nodes typically return AutoResult without setting node_id/node_type
        # (backward compat with old code that predates these fields). Engine
        # fills them here so JSONL logs and downstream diagnostics always
        # have the originating node identification. If a node explicitly set
        # node_id (e.g. reporting a sub-step), engine does not overwrite it.
        if not result.node_id:
            result.node_id = node.id
        if not result.node_type:
            result.node_type = node.node_type

        # spec-2026-07-27 阶段 2: retry 指数退避 (吸收 chain step.retry).
        # 节点失败时按 retry 配置重试。节点属性优先，回退到 config["retry"]。
        retry_count = 0
        if result.failed:
            retry_cfg = node.retry or node.config.get("retry")
            if isinstance(retry_cfg, dict) and retry_cfg:
                result, retry_count = self._handle_node_retry(node, result, retry_cfg)

        # spec-2026-07-27 阶段 2: fallback 回退方案 (吸收 chain step.fallback).
        # 重试仍失败时执行 fallback。节点属性优先，回退到 config["fallback"]。
        if result.failed:
            fallback_cfg = node.fallback or node.config.get("fallback")
            if isinstance(fallback_cfg, dict) and fallback_cfg:
                result = self._handle_node_fallback(node, result, fallback_cfg)
                # fallback 后重试次数归零（fallback 是独立动作，retry_count 保留原值反映主重试）
                if not result.node_id:
                    result.node_id = node.id
                if not result.node_type:
                    result.node_type = node.node_type

        # 把 retry_count 写到 result（fallback 成功也保留主重试次数）
        result.retry_count = retry_count

        # spec 阶段 3 — 任务 3.2 + spec-2026-07-27 阶段 2: post_verify 强验证.
        # 节点成功后, 若配置了 post_verify 且注入了 verifier, 调用
        # verifier.verify(post_verify_dict) 二次验证屏幕状态. 失败时
        # 把节点标记失败 + error_code=POST_VERIFY_FAILED. 节点自身失败
        # 时跳过 (没必要再验证). 未注入 verifier 时静默跳过 (向后兼容).
        # 节点属性优先，回退到 config["post_verify"]（向后兼容 spec 阶段 3 任务 3.2）。
        if result.success and self._verifier is not None:
            post_verify = node.post_verify or node.config.get("post_verify")
            if isinstance(post_verify, dict) and post_verify:
                try:
                    verify_result = self._verifier.verify(post_verify)
                except Exception as exc:
                    logger.exception(
                        "节点 %s post_verify 异常: %s", node.id, exc,
                    )
                    result.success = False
                    # Task 4.13 (P2-12, 2026-07-28): 改用 NodeErrorCode 枚举,
                    # 与 pre_verify 路径一致 (原来用裸字符串绕过类型检查).
                    result.error_code = NodeErrorCode.POST_VERIFY_FAILED
                    result.error_msg = (
                        f"post_verify 异常 ({type(exc).__name__}): {exc}"
                    )
                    if not result.node_id:
                        result.node_id = node.id
                    if not result.node_type:
                        result.node_type = node.node_type
                    # Task 4.10 (P2-10, 2026-07-28): post_verify 失败补独立
                    # JSONL 事件, 与 pre_verify 对称 (原来只写文本日志,
                    # AI 无法从 JSONL 过滤 post_verify 失败).
                    self._log_node_verify_event(
                        node, "node.execute.post_verify_failed", result,
                    )
                else:
                    if not verify_result.success:
                        logger.warning(
                            "节点 %s post_verify 失败: %s",
                            node.id, verify_result.error_msg,
                        )
                        result.success = False
                        # Task 4.13: 改用 NodeErrorCode 枚举.
                        result.error_code = NodeErrorCode.POST_VERIFY_FAILED
                        result.error_msg = (
                            f"post_verify 失败: {verify_result.error_msg}"
                        )
                        if not result.node_id:
                            result.node_id = node.id
                        if not result.node_type:
                            result.node_type = node.node_type
                        # Task 4.10: post_verify 失败补独立 JSONL 事件.
                        self._log_node_verify_event(
                            node, "node.execute.post_verify_failed", result,
                        )

        # P1-8: post_delay / post_wait_freezes.
        self._apply_post_lifecycle(node)
        return result

    def _handle_node_retry(
        self,
        node: PipelineNode,
        last_result: AutoResult,
        retry_cfg: dict[str, Any],
    ) -> tuple[AutoResult, int]:
        """节点级指数退避重试 (spec-2026-07-27 阶段 2, 吸收 chain step.retry).

        Args:
            node: 失败的节点实例.
            last_result: 节点上一次 execute() 的失败结果.
            retry_cfg: 重试配置, 格式::
                {"max_retries": int, "base_delay": float, "backoff_factor": float}
                缺省字段用 WorkerConfig 默认值 (与 chain _handle_retry 一致).

        Returns:
            (最终结果, 实际重试次数). 重试次数 0 表示未重试.
        """
        max_retries = int(retry_cfg.get("max_retries", 3))
        base_delay = float(retry_cfg.get("base_delay", 1.0))
        backoff = float(retry_cfg.get("backoff_factor", 2.0))

        result = last_result
        retry_count = 0
        for attempt in range(1, max_retries + 1):
            if self._cancel_event.is_set() or self._step_cancel_event.is_set():  # TD-353: 步骤超时
                result.is_interrupted = True
                break
            delay = min(base_delay * (backoff ** (attempt - 1)), 30.0)
            self._safe_delay(delay, f"retry attempt {attempt}")
            logger.info(
                "[PIPELINE] 节点 %s 第 %d/%d 次重试", node.id, attempt, max_retries,
            )
            # N192 A5 P1: 补 node.execute.retry JSONL 事件 (AI 调试视角 —
            # retry trace). 让 AI 跑 pipeline 报错时能从 JSONL 看到「重试了
            # 几次 / 每次延迟多久 / 上次错误码」, 不用反复加 log 定位.
            # best-effort: 写入失败仅 warning, 不阻塞 pipeline.
            if self._structured_logger is not None:
                try:
                    self._structured_logger.log_node_event(
                        event="node.execute.retry",
                        node_id=node.id,
                        node_type=node.node_type,
                        step_index=getattr(self, "_current_step_index", 0),
                        success=False,
                        elapsed_ms=int(delay * 1000),
                        retry_count=attempt,
                        error_code=result.error_code or "",
                        error_msg=(result.error_msg or "")[:500],
                        extra={
                            "attempt": attempt,
                            "max_retries": max_retries,
                            "delay_ms": int(delay * 1000),
                            "last_error_code": result.error_code or "",
                        },
                    )
                except Exception as exc:
                    logger.warning("retry 事件 log_node_event 失败: %s", exc)
            result = node.execute(self._context)
            if not result.node_id:
                result.node_id = node.id
            if not result.node_type:
                result.node_type = node.node_type
            retry_count = attempt
            if result.success:
                break
        return result, retry_count

    def _handle_node_fallback(
        self,
        node: PipelineNode,
        failed_result: AutoResult,
        fallback_cfg: dict[str, Any],
    ) -> AutoResult:
        """节点级回退方案 (spec-2026-07-27 阶段 2, 吸收 chain step.fallback).

        fallback_cfg 支持两种格式:
        - {"action": "click", "params": {...}} — 调用 device 执行原子动作
          (与 chain step.fallback 格式一致，向后兼容)
        - {"node_type": "click", "config": {...}} — 内联节点配置
          (规范化 pipeline 节点格式)

        Args:
            node: 失败的节点实例.
            failed_result: 节点重试后的失败结果.
            fallback_cfg: 回退方案配置.

        Returns:
            fallback 执行结果. 失败时返回 fallback 的失败结果，不抛异常.
        """
        logger.info("[PIPELINE] 节点 %s 执行回退方案: %s", node.id, fallback_cfg)
        # N192 A5 P1: 补 node.execute.fallback JSONL 事件 (AI 调试视角 —
        # fallback trace). 触发时 + 完成时各写一个事件, 让 AI 能从 JSONL
        # 看到「为什么降级 / 降级到什么动作 / 降级是否成功」, 不用查文本日志.
        fallback_start = time.monotonic()
        self._log_fallback_event(
            node=node,
            fallback_cfg=fallback_cfg,
            trigger_phase="fallback_triggered",
            success=False,
            elapsed_ms=0.0,
            error_code=failed_result.error_code or "",
            error_msg=failed_result.error_msg or "",
        )
        try:
            # 优先按规范化节点格式执行（type/config）
            fb_type = fallback_cfg.get("type") or fallback_cfg.get("node_type")
            if fb_type and fb_type in PIPELINE_NODE_REGISTRY:
                fb_node = PipelineNode.create({
                    "id": f"{node.id}__fallback",
                    "node_type": fb_type,
                    "config": fallback_cfg.get("config", fallback_cfg.get("params", {})),
                })
                result = fb_node.execute(self._context)
                if not result.node_id:
                    result.node_id = fb_node.id
                if not result.node_type:
                    result.node_type = fb_node.node_type
                self._log_fallback_event(
                    node=node,
                    fallback_cfg=fallback_cfg,
                    trigger_phase="fallback_completed",
                    success=result.success,
                    elapsed_ms=(time.monotonic() - fallback_start) * 1000.0,
                    error_code=result.error_code or "",
                    error_msg=result.error_msg or "",
                )
                return result

            # 回退到 chain step.fallback 格式（action/params）
            # 通过 device 直接执行原子动作
            action = fallback_cfg.get("action", "")
            params = fallback_cfg.get("params", {})
            if not action:
                # N192 A7 P3: fallback 配置无效补三要素.
                result = fail_result(
                    error_msg="fallback 配置无效: 缺少 action/type 字段",
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=node.id,
                    node_type=node.node_type,
                )
                self._log_fallback_event(
                    node=node,
                    fallback_cfg=fallback_cfg,
                    trigger_phase="fallback_completed",
                    success=False,
                    elapsed_ms=(time.monotonic() - fallback_start) * 1000.0,
                    error_code=result.error_code or "",
                    error_msg=result.error_msg or "",
                )
                return result

            device = self._context.device if self._context else None
            if device is None:
                # N192 A7 P3: fallback 无设备补三要素.
                result = fail_result(
                    error_msg="fallback 失败: 无可用设备",
                    error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                    node_id=node.id,
                    node_type=node.node_type,
                )
                self._log_fallback_event(
                    node=node,
                    fallback_cfg=fallback_cfg,
                    trigger_phase="fallback_completed",
                    success=False,
                    elapsed_ms=(time.monotonic() - fallback_start) * 1000.0,
                    error_code=result.error_code or "",
                    error_msg=result.error_msg or "",
                )
                return result

            action_map = {
                "click": lambda: device.click(params.get("x", 0), params.get("y", 0)),
                "swipe": lambda: device.swipe(
                    params.get("x1", 0), params.get("y1", 0),
                    params.get("x2", 0), params.get("y2", 0),
                ),
                "key_press": lambda: device.key_press(params.get("key", "")),
                "text_input": lambda: device.text_input(params.get("text", "")),
                "wait": lambda: self._safe_delay(float(params.get("seconds", 1.0)), "fallback wait"),
            }
            handler = action_map.get(action)
            if handler is None:
                # N192 A7 P3: fallback 未知动作补三要素.
                result = fail_result(
                    error_msg=f"fallback 未知动作: {action}",
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=node.id,
                    node_type=node.node_type,
                )
                self._log_fallback_event(
                    node=node,
                    fallback_cfg=fallback_cfg,
                    trigger_phase="fallback_completed",
                    success=False,
                    elapsed_ms=(time.monotonic() - fallback_start) * 1000.0,
                    error_code=result.error_code or "",
                    error_msg=result.error_msg or "",
                )
                return result
            handler()
            result = AutoResult(
                success=True,
                data={"fallback_action": action},
                node_id=f"{node.id}__fallback",
                node_type=action,
            )
            self._log_fallback_event(
                node=node,
                fallback_cfg=fallback_cfg,
                trigger_phase="fallback_completed",
                success=result.success,
                elapsed_ms=(time.monotonic() - fallback_start) * 1000.0,
                error_code=result.error_code or "",
                error_msg=result.error_msg or "",
            )
            return result
        except Exception as exc:
            logger.exception("[PIPELINE] 节点 %s fallback 异常: %s", node.id, exc)
            # N192 A7 P3: fallback 异常补三要素, 让 AI 能定位是哪个节点
            # 的 fallback 失败, 而非只看到 "fallback 异常" 字符串.
            result = fail_result(
                error_msg=f"fallback 异常: {exc}",
                error_code=NodeErrorCode.UNKNOWN,
                node_id=node.id,
                node_type=node.node_type,
            )
            self._log_fallback_event(
                node=node,
                fallback_cfg=fallback_cfg,
                trigger_phase="fallback_completed",
                success=False,
                elapsed_ms=(time.monotonic() - fallback_start) * 1000.0,
                error_code=result.error_code or "",
                error_msg=result.error_msg or "",
            )
            return result

    def _log_fallback_event(
        self,
        node: PipelineNode,
        fallback_cfg: dict[str, Any],
        trigger_phase: str,
        success: bool,
        elapsed_ms: float,
        error_code: str = "",
        error_msg: str = "",
    ) -> None:
        """记录 fallback 事件到 JSONL (N192 A5 P1 — fallback trace).

        与 node.execute.complete 事件对称, 让 AI 能在 JSONL 中看到 fallback
        触发上下文 (failed_result 的 error_code/error_msg) 和完成状态.
        best-effort: 写入失败仅 warning, 不阻塞 pipeline.

        Args:
            node: 触发 fallback 的原节点.
            fallback_cfg: fallback 配置 dict (含 action/type/params).
            trigger_phase: "fallback_triggered" (入口) / "fallback_completed" (出口).
            success: fallback 动作是否成功 (triggered 阶段固定 False).
            elapsed_ms: fallback 执行耗时 (triggered 阶段为 0).
            error_code: 触发阶段的 failed_result.error_code, 或完成阶段的
                fallback result.error_code.
            error_msg: 同上, 对应 error_msg.
        """
        if self._structured_logger is None:
            return
        try:
            fallback_action = (
                fallback_cfg.get("action")
                or fallback_cfg.get("type")
                or fallback_cfg.get("node_type")
                or ""
            )
            self._structured_logger.log_node_event(
                event="node.execute.fallback",
                node_id=node.id,
                node_type=node.node_type,
                step_index=getattr(self, "_current_step_index", 0),
                success=success,
                elapsed_ms=int(elapsed_ms),
                error_code=error_code or "",
                error_msg=(error_msg or "")[:500],
                extra={
                    "fallback_action": fallback_action,
                    "fallback_config": fallback_cfg,
                    "trigger_phase": trigger_phase,
                },
            )
        except Exception as exc:
            logger.warning("fallback 事件 log_node_event 失败: %s", exc)

    def _log_node_verify_event(
        self,
        node: PipelineNode,
        event: str,
        result: AutoResult,
    ) -> None:
        """记录节点验证事件到 JSONL（pre_verify/post_verify 失败）.

        与 node.execute.complete 事件对称, 让 AI 能在 JSONL 中看到验证失败的上下文.
        best-effort: 写入失败仅 warning.
        """
        if self._structured_logger is None:
            return
        try:
            self._structured_logger.log_node_event(
                event=event,
                node_id=node.id,
                node_type=node.node_type,
                step_index=self._current_step_index if hasattr(self, '_current_step_index') else 0,
                success=False,
                elapsed_ms=0.0,
                error_msg=result.error_msg,
                error_code=result.error_code,
                # N191 §10.10 决策点 6: verify 事件也带 device_type +
                # transformer_id, 保证跨设备字段集一致。
                device_type=getattr(self, "_device_type", ""),
                transformer_id=getattr(self, "_transformer_id", ""),
                coord_system=getattr(self._context, "coord_system", "") or "",
            )
        except Exception as exc:
            logger.warning("verify 事件 log_node_event 失败: %s", exc)

    def _apply_pre_lifecycle(self, node: PipelineNode) -> None:
        """Apply pre-delay and pre-wait-freezes hooks before node.execute()."""
        pre_delay = node.config.get("pre_delay")
        if pre_delay is not None:
            self._safe_delay(float(pre_delay), "pre_delay")
        pre_wf = node.config.get("pre_wait_freezes")
        if pre_wf:
            self._safe_wait_freezes(pre_wf, "pre_wait_freezes")

    def _apply_post_lifecycle(self, node: PipelineNode) -> None:
        """Apply post-delay and post-wait-freezes hooks after node.execute()."""
        post_wf = node.config.get("post_wait_freezes")
        if post_wf:
            self._safe_wait_freezes(post_wf, "post_wait_freezes")
        post_delay = node.config.get("post_delay")
        if post_delay is not None:
            self._safe_delay(float(post_delay), "post_delay")

    def _safe_delay(self, seconds: float, label: str) -> None:
        """Sleep with cancel-event awareness (TD-353: 检查 _step_cancel_event)."""
        if seconds <= 0:
            return
        # TD-353: 改为轮询模式同时检查 _cancel_event 和 _step_cancel_event.
        # 原实现用 Event.wait() 只检查 _cancel_event, 无法响应步骤超时.
        elapsed = 0.0
        chunk = 0.1  # 每 100ms 轮询一次
        while elapsed < seconds:
            if self._cancel_event.is_set():
                logger.debug("%s interrupted by cancel signal", label)
                self._cancel_event.clear()
                return
            if self._step_cancel_event.is_set():  # TD-353: 步骤超时
                logger.debug("%s interrupted by step cancel signal", label)
                return
            time.sleep(chunk)
            elapsed += chunk

    def _safe_wait_freezes(self, wf_cfg: Any, label: str) -> None:
        """Run WaitFreezes using the bound device's capture function."""
        if self._context is None or self._context.device is None:
            logger.debug("%s skipped: no device bound", label)
            return
        try:
            from core.wait_freezes import WaitFreezes
            # wf_cfg may be: True, float (timeout), or dict.
            timeout = 10.0
            similarity = None
            interval_ms = 50.0
            stable_frames = 3
            if isinstance(wf_cfg, (int, float)):
                timeout = float(wf_cfg)
            elif isinstance(wf_cfg, dict):
                timeout = float(wf_cfg.get("timeout", 10.0))
                similarity = wf_cfg.get("similarity")
                interval_ms = float(wf_cfg.get("interval_ms", 50.0))
                stable_frames = int(wf_cfg.get("stable_frames", 3))
            wf = WaitFreezes(
                interval_ms=interval_ms,
                stable_frames=stable_frames,
                default_similarity=similarity or 0.99,
            )
            capture_fn = self._context.device.capture_screen
            wf.wait(capture_fn, timeout=timeout, similarity=similarity)
        except Exception as exc:
            logger.warning("%s failed: %s", label, exc)
