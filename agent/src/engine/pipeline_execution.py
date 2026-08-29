"""PipelineEngine：Pipeline 通用执行器"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import time
from typing import Any

import engine.nodes  # noqa: F401  (side-effect import: populates registry)
from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result
from engine.context import PipelineContext, PipelineState, StepState
from engine.pipeline_models import PipelineResult
from engine.pipeline_utils import MAX_STEP_TIMEOUT, _truncate_dict, _truncate_result_data_priority
from engine.validator import PipelineValidator
from utils.perf_monitor import PerfMonitor
from utils.structured_logger import (
    extract_result_fields,
    new_execution_id,
)

logger = logging.getLogger(__name__)



# Forwarding indirection: tests patch engine.pipeline_engine.get_structured_logger
# (module attribute) to inject a fake logger. Look up the attribute at call
# time so the patch point survives the s35 split (execute moved out of
# pipeline_engine.py into this mixin).
def _get_structured_logger(*args, **kwargs):
    from engine import pipeline_engine as _engine_mod
    return _engine_mod.get_structured_logger(*args, **kwargs)
class PipelineExecutionMixin:
    """PipelineEngine mixin — see pipeline_engine.py for full class (s35 split)."""

    def execute(
        self,
        resume: bool = False,
        start_step_index: int = 0,
        previous_results: list[AutoResult] | None = None,
    ) -> PipelineResult:
        """执行 Pipeline

        Args:
            resume: If True, preserve restored context state (variables,
                stepStates, execution_history, current_step_index) for
                checkpoint-based resume. Must be set True after calling
                restore_context(); otherwise the restored state would be
                wiped by context.reset(). Default False (fresh run).
            start_step_index: Task 1.1 (B7 重试单节点, P0-1). 跳过前 N 个
                节点的实际执行, 从第 N+1 个节点开始跑. 用于"重试此步"功能:
                用户在前端选择失败节点后, backend 创建新 execution 并传
                start_step_index=N, agent 跳过前 N 个节点只重跑失败节点
                及后续节点. 默认 0 = 不跳过 (正常执行).
                与 ``previous_results`` 配合使用, 把之前成功节点的 result
                传进来作为前驱链路状态 + 最终 step_results 的填充.
            previous_results: Task 1.1. 之前成功节点的 AutoResult 列表,
                长度应等于 ``start_step_index``. 这些 result 会:
                1. 被原样追加到 ``self._step_results``, 让最终 PipelineResult
                   的 step_results 完整 (用户能看到前驱节点输出).
                2. 用于跳过节点的 ``_resolve_next_node`` 决策 (例如 branch
                   节点的 ``result.data["branch_taken"]`` 决定走哪条边).
                3. 最后一个 previous_result 的 node_id/node_type 用于
                   ``_previous_node_id`` 链路状态, 让第一个实际执行节点的
                   JSONL 事件能记录前驱节点.
                默认 None = 无前驱 (从头跑或跳过节点的 next_node 用默认边).

        Returns:
            PipelineResult 执行结果

        Raises:
            RuntimeError: Pipeline 未加载
        """
        if self._graph is None:
            raise RuntimeError("Pipeline 未加载，请先调用 load()")

        if self._context is None:
            self._context = PipelineContext()

        # Ensure context has device reference (from load-time injection)
        # If context was restored from serialized data, device will be None —
        # caller must re-inject after restore_context()
        if self._context.device is None and hasattr(self, '_device'):
            self._context.device = self._device
        # Re-inject display services the same way. These are runtime-only
        # (not serialized), so a restored context has them as None.
        if self._context.display_context is None and hasattr(self, '_display_context'):
            self._context.display_context = self._display_context
        if self._context.coord_transformer is None and hasattr(self, '_coord_transformer'):
            self._context.coord_transformer = self._coord_transformer
        if self._context.monitor_manager is None and hasattr(self, '_monitor_manager'):
            self._context.monitor_manager = self._monitor_manager
        if getattr(self._context, 'llm_client', None) is None and hasattr(self, '_llm_client'):
            self._context.llm_client = self._llm_client

        # 校验
        errors = PipelineValidator.validate(self._graph)
        if errors:
            error_msgs = "; ".join(str(e) for e in errors)
            return PipelineResult(
                success=False,
                state=PipelineState.FAILED,
                error_msg=f"Pipeline 校验失败: {error_msgs}",
            )

        self._state = PipelineState.RUNNING
        self._cancel_event.clear()
        self._pause_event.clear()
        # Only reset context on fresh runs. When resume=True, the caller has
        # already restored context state via restore_context(); calling
        # reset() here would wipe variables/step_states/execution_history
        # and break checkpoint-based resume.
        if not resume:
            self._context.reset()
        self._step_results.clear()

        # Task 1.1 (B7 重试单节点, P0-1): 把之前成功节点的 result 加到
        # _step_results 开头, 让最终 PipelineResult.step_results 完整
        # (用户能看到前驱节点输出). 同时设置 _previous_node_id 链路状态
        # 让第一个实际执行节点的 JSONL 事件能记录前驱节点 (N192 A4 —
        # 节点链路可追溯). 这些 result 也用于跳过节点的 _resolve_next_node
        # 决策 (保留原 branch/goto 分支选择, 而非走默认边).
        if previous_results:
            for prev_r in previous_results:
                self._step_results.append(prev_r)
            # _previous_node_id 用最后一个成功 previous_result 的 node_id
            # (倒序查找, 跳过失败/空 node_id 的 result).
            for prev_r in reversed(previous_results):
                if prev_r.success and prev_r.node_id:
                    self._previous_node_id = prev_r.node_id
                    self._previous_node_type = prev_r.node_type or ""
                    self._previous_node_end_time = time.monotonic()
                    break

        # Initialize structured JSONL logger for this execute() call
        # (spec 阶段 3.1). One JSONL file per run, named by execution_id,
        # under <debug_dir>/structured/. Closed in the finally block below.
        # P0-4 fix: use execution_id override from load() if provided (lets
        # orchestrator share the same JSONL file for task-level events).
        self._execution_id = self._execution_id_override or new_execution_id()
        self._execution_id_override = ""  # consume, reset for next call
        debug_dir = getattr(self._context, "debug_dir", "./debug") or "./debug"
        # A3 (spec 2026-07-30-debug-directory-restructure): 提取 pipeline_name
        # 和 trace_id 传给 StructuredLogger, 让日志路径和 JSONL 含全链路 trace_id.
        pipeline_name_a3 = getattr(self._context, "pipeline_name", "") or ""
        trace_id_a3 = ""
        try:
            from core.context_vars import get_current_user_trace_id
            trace_id_a3 = get_current_user_trace_id()
        except ImportError:
            logger.debug("core.context_vars unavailable, trace_id defaults to empty")
        self._structured_logger = _get_structured_logger(
            self._execution_id,
            debug_dir=debug_dir,
            pipeline_name=pipeline_name_a3,
            trace_id=trace_id_a3,
        )
        # Capture the absolute path before the try block so it survives
        # the finally block's logger.close() (spec 阶段 3.4 — backend
        # reads this path to access the structured log for LLM diagnosis).
        self._last_structured_log_path = self._structured_logger.file_path
        # N191 §10.10 决策点 5 (AI 可调试性, 2026-07-27):
        # 把 structured_logger + device_type + transformer_id 注入 context,
        # 让 publish_match_pos / resolve_target / device.click 等核心接口
        # 能通过 context.emit_coord_trace() 记坐标转换 trace。
        self._context.structured_logger = self._structured_logger
        self._context.device_type = self._device_type
        self._context.transformer_id = self._transformer_id
        # 阶段 2 (性能计量): 注入 PerfMonitor 的 structured_logger,
        # 让 perf.timer 事件写入同一 JSONL 文件.
        PerfMonitor.get_instance().set_structured_logger(self._structured_logger)
        # N191 §10.10 决策点 2 A+ (AI 可调试性, 2026-07-27):
        # 给 device 注入 coord_trace_callback, 让 device 内部 logical→physical
        # 转换能记 trace (堵住 device.click 内部转换黑盒, D5)。
        # 优先检查 set_coord_trace_callback 方法存在, 不存在的 device 跳过。
        device_for_trace = getattr(self._context, "device", None)
        if device_for_trace is not None and hasattr(device_for_trace, "set_coord_trace_callback"):
            try:
                device_for_trace.set_coord_trace_callback(self._context.emit_coord_trace)
            except Exception:
                # best-effort: 注入失败不阻塞 pipeline。
                logger.debug("coord trace callback injection failed (best-effort)", exc_info=True)
        # Reset cross-step chain (spec 阶段 3.2 — 任务 1.4).
        self._previous_node_id = ""
        self._previous_node_type = ""
        self._previous_node_end_time = 0.0
        # Reset per-node recovery counters (spec 阶段 3 — 任务 3.3).
        # Each execute() call gets fresh state so a previously-recovered
        # node can be recovered again on a new run.
        self._recovery_attempts_per_node = {}
        self._last_recovery_path = {}

        start_time = time.monotonic()
        self._current_node_id = self._graph.entry_node
        iteration = 0
        # Task 4.4 (P1-9, 2026-07-28): 把 step_index 提升为实例属性,
        # 让 retry/fallback/verify 事件能读到当前节点索引 (原来用局部变量
        # iteration, 子方法 getattr(self, "_current_step_index", 0) 恒为 0).
        # 0-based: 第一个节点 step_index=0, 与 node.execute.start/complete 对齐.
        self._current_step_index = 0

        # N pipeline 优化 2026-08-02: 复用 ThreadPoolExecutor 避免每个节点
        # 新建/销毁线程池 (~10-50ms/节点开销). 仅当节点配置了自定义 timeout
        # 时使用线程池执行 (超时保护), 否则在主线程直接执行.
        _reusable_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        # N pipeline 优化 2026-08-02: 缓存每个节点的截断 config,
        # 避免同一节点(如 loop 内重复执行)反复调用 _truncate_dict.
        _truncated_config_cache: dict[str, Any] = {}

        try:
            while self._current_node_id and iteration < self._max_iterations:
                iteration += 1
                # Task 4.4: 同步实例属性, 让 _handle_node_retry /
                # _log_fallback_event / _log_node_verify_event 能读到.
                self._current_step_index = iteration - 1

                # 检查取消信号
                if self._cancel_event.is_set():
                    logger.info("Pipeline 收到取消信号，在节点 %s 后停止", self._current_node_id)
                    self._state = PipelineState.CANCELLED
                    return PipelineResult(
                        success=False,
                        state=PipelineState.CANCELLED,
                        data=self._step_results,
                        error_msg="Pipeline 已取消",
                        elapsed_time=time.monotonic() - start_time,
                        step_results=list(self._step_results),
                    )

                # 处理暂停
                while self._pause_event.is_set():
                    if self._cancel_event.is_set():
                        self._state = PipelineState.CANCELLED
                        return PipelineResult(
                            success=False,
                            state=PipelineState.CANCELLED,
                            data=self._step_results,
                            error_msg="Pipeline 在暂停期间被取消",
                            elapsed_time=time.monotonic() - start_time,
                            step_results=list(self._step_results),
                        )
                    self._state = PipelineState.PAUSED
                    time.sleep(0.1)

                self._state = PipelineState.RUNNING

                node = self._graph.get_node(self._current_node_id)
                if node is None:
                    self._state = PipelineState.FAILED
                    return PipelineResult(
                        success=False,
                        state=PipelineState.FAILED,
                        data=self._step_results,
                        error_msg=f"节点 {self._current_node_id} 不存在",
                        elapsed_time=time.monotonic() - start_time,
                        step_results=list(self._step_results),
                    )

                # Task 1.1 (B7 重试单节点, P0-1): 跳过前 start_step_index
                # 个节点的实际执行. 之前成功节点的 result 已在循环开始前
                # 加到 _step_results 中, 这里只更新链路状态 + 用 previous_result
                # 决定下一个节点 (保留原 branch/goto 决策, 避免分支变化导致
                # 跳错路径). 不调 _execute_node_step, 不写 JSONL (避免重复事件).
                if iteration <= start_step_index:
                    prev_idx = iteration - 1
                    if previous_results and prev_idx < len(previous_results):
                        skip_result = previous_results[prev_idx]
                    else:
                        # 兜底: previous_results 长度 < start_step_index 时,
                        # 构造默认成功 result 走默认边 (向后兼容).
                        skip_result = AutoResult(
                            success=True,
                            data={},
                            node_id=node.id,
                            node_type=node.node_type,
                        )
                    # 当前跳过的节点成为下一个执行节点的前驱 (N192 A4 链路可追溯)
                    self._previous_node_id = node.id
                    self._previous_node_type = node.node_type
                    self._previous_node_end_time = time.monotonic()
                    # 计算下一个节点 (不实际执行节点)
                    next_id = self._resolve_next_node(node, skip_result)
                    self._current_node_id = next_id or ""
                    logger.info(
                        "[PIPELINE] 跳过节点 (start_step_index=%d): id=%s, "
                        "type=%s, iteration=%d, next=%s",
                        start_step_index, node.id, node.node_type,
                        iteration, next_id or "(end)",
                    )
                    continue

                logger.info(
                    "[PIPELINE] 开始执行节点: id=%s, type=%s, iteration=%d",
                    node.id, node.node_type, iteration,
                )

                # N192 A3/A4 P2: 节点开始前写 node.execute.start 事件
                # 让 AI 从 JSONL 反推"卡在第几个节点" + 看到节点当时配的参数
                if self._structured_logger is not None:
                    try:
                        # N pipeline 优化 2026-08-02: 缓存截断的 config,
                        # 避免同一节点(如 loop 内重复执行)反复调用 _truncate_dict.
                        cached_config = _truncated_config_cache.get(node.id)
                        if cached_config is None:
                            cached_config = _truncate_dict(node.config, max_chars=2000)
                            _truncated_config_cache[node.id] = cached_config
                        self._structured_logger.log_node_event(
                            event="node.execute.start",
                            node_id=node.id,
                            node_type=node.node_type,
                            step_index=iteration - 1,
                            success=True,  # 占位, start 事件不关心 success
                            elapsed_ms=0,
                            extra={
                                "input_config": cached_config,
                                "previous_node_id": self._previous_node_id,
                            },
                        )
                    except Exception as exc:
                        logger.warning("node.execute.start log_node_event 失败: %s", exc)

                # 执行节点（含 step 级 timeout — spec 阶段 2.2）
                try:
                    step_timeout = float(node.config.get("timeout", MAX_STEP_TIMEOUT))
                    if step_timeout <= 0:
                        step_timeout = MAX_STEP_TIMEOUT

                    # TD-399 (spec-2026-08-26 P1): 所有节点统一经复用线程池执行并
                    # 施加 wall-clock 超时。旧实现仅对显式配置了 timeout 的节点走
                    # 线程池，其余主线程直跑 — 任何未知阻塞（截图/IO/COM）都会让
                    # pipeline 永久挂起。现在默认 MAX_STEP_TIMEOUT 兜底，节点显式
                    # timeout 仍可覆盖。Python 线程无法强杀，超时节点在后台继续，
                    # 但主流程不再等待。
                    future = _reusable_executor.submit(self._execute_node_step, node)
                    try:
                        result = future.result(timeout=step_timeout)
                    except concurrent.futures.TimeoutError:
                        logger.warning(
                            "[PIPELINE] 节点 %s 执行超时 (%.1fs) — 后台线程继续运行",
                            self._current_node_id, step_timeout,
                        )
                        # TD-353: 超时后置位 _step_cancel_event, 通知后台线程
                        # 在关键检查点 (repeat/retry/delay) 主动退出.
                        self._step_cancel_event.set()
                        try:
                            # 给后台线程 3s 宽限期检测标志位并退出
                            future.result(timeout=3)
                        except concurrent.futures.TimeoutError:
                            logger.warning(
                                "[PIPELINE] 节点 %s 后台线程超时后 3s 内未退出, "
                                "可能有残留操作",
                                self._current_node_id,
                            )
                        self._step_cancel_event.clear()
                        # N192 A7 P3: timeout fail_result 补三要素 (node_id /
                        # node_type / error_code=TIMEOUT), 让 AI 能分类超时失败.
                        result = fail_result(
                            error_msg=(
                                f"节点 {self._current_node_id} 执行超时 "
                                f"({step_timeout}s)"
                            ),
                            error_code=NodeErrorCode.TIMEOUT,
                            node_id=node.id,
                            node_type=node.node_type,
                        )
                        if self._on_error:
                            self._on_error(
                                self._current_node_id,
                                TimeoutError(f"step timeout {step_timeout}s"),
                            )
                except Exception as exc:
                    logger.exception("[PIPELINE] 节点 %s 执行异常: %s", self._current_node_id, exc)
                    if self._on_error:
                        self._on_error(self._current_node_id, exc)
                    # N192 A7 P3: 节点执行异常 fail_result 补三要素, 让 AI
                    # 能从 result 定位节点 + 分类错误, 不必查文本日志.
                    result = fail_result(
                        error_msg=str(exc),
                        error_code=NodeErrorCode.UNKNOWN,
                        node_id=node.id,
                        node_type=node.node_type,
                    )

                self._step_results.append(result)

                # 记录步骤
                state = StepState.COMPLETED if result.success else StepState.FAILED
                logger.info(
                    "[PIPELINE] 节点执行结果: id=%s, type=%s, success=%s, error_msg=%s, elapsed=%.3fs",
                    node.id,
                    node.node_type,
                    result.success,
                    result.error_msg or "",
                    result.elapsed_time or 0.0,
                )

                # Structured JSONL logging (spec 阶段 3.1).
                # Extracts template_match/click specific fields from
                # result.data via extract_result_fields().
                if self._structured_logger is not None:
                    fields = extract_result_fields(
                        node.node_type, result.data, node.config,
                    )
                    # Build variables_snapshot (spec 阶段 3.3 — 任务 1.4).
                    # Whitelist-filter: skip underscore-prefixed internal
                    # protocol vars and non-JSON-serializable values (e.g.
                    # numpy arrays / bytes). Truncate to 2000 chars to bound
                    # JSONL line size.
                    _vars_snapshot: dict[str, Any] = {}
                    # spec §3.3: 跳过大对象 (bytes / bytearray / np.ndarray).
                    # 延迟 import numpy 避免顶层依赖 (engine 不应强依赖 numpy,
                    # 单测可能用 MagicMock context.variables 而无 numpy).
                    try:
                        import numpy as _np  # noqa: F401
                        _big_value_types = (bytes, bytearray, _np.ndarray)
                    except ImportError:
                        _big_value_types = (bytes, bytearray)
                    if self._context is not None:
                        for key, value in self._context.variables.items():
                            if key.startswith("_"):
                                continue
                            if isinstance(value, _big_value_types):
                                continue
                            try:
                                json.dumps(value, default=str)
                                _vars_snapshot[key] = value
                            except (TypeError, ValueError):
                                logger.debug("variable %s not JSON-serializable, skipped from snapshot", key)
                    if len(str(_vars_snapshot)) > 2000:
                        _vars_snapshot = {
                            "_truncated": True,
                            "_keys": list(_vars_snapshot.keys()),
                        }

                    # Build extra with cross-step chain (spec 阶段 3.2).
                    extra: dict[str, Any] = {}
                    if self._previous_node_id:
                        extra["previous_node_id"] = self._previous_node_id
                        extra["previous_node_type"] = self._previous_node_type
                        # inter_node_gap_ms = current node start - previous
                        # node end. start_time is the engine execute() start;
                        # we use time.monotonic() relative timing.
                        prev_end = self._previous_node_end_time
                        if prev_end > 0:
                            # current node start ≈ now (just before execute)
                            # but we already executed the node; use the
                            # recorded elapsed_time to back-calculate start.
                            current_start = time.monotonic() - (result.elapsed_time or 0.0)
                            extra["inter_node_gap_ms"] = int(
                                max(0.0, (current_start - prev_end) * 1000.0)
                            )
                        # N192 A4 P2 + N193 Task 5.2: 补 previous_node_result_data
                        # 让 AI 从 JSONL 就能看到前驱节点输出 → 当前节点输入的
                        # 完整数据流, 不必跨多个事件拼凑。用分级截断保留 P0 诊断
                        # 关键字段 (confidence / match_loc / coord_system), 大对象
                        # (detections / boxes) 替换为摘要, 总长度上限 1000 字符。
                        # 注意: 此时 _step_results 已 append 当前节点 result,
                        # 所以前驱节点是 _step_results[-2] (不是 [-1]).
                        prev_result_data = None
                        if len(self._step_results) >= 2:
                            prev = self._step_results[-2]
                            if hasattr(prev, "data") and prev.data:
                                prev_result_data = _truncate_result_data_priority(
                                    prev.data, max_chars=1000,
                                )
                        if prev_result_data is not None:
                            extra["previous_node_result_data"] = prev_result_data

                    self._structured_logger.log_node_event(
                        event="node.execute.complete",
                        node_id=node.id,
                        node_type=node.node_type,
                        step_index=iteration - 1,
                        success=result.success,
                        elapsed_ms=(result.elapsed_time or 0.0) * 1000.0,
                        retry_count=result.retry_count,
                        confidence=fields.get("confidence"),
                        threshold=fields.get("threshold"),
                        match_location=fields.get("match_location"),
                        roi_base=fields.get("roi_base"),
                        screenshot_path=fields.get("screenshot_path"),
                        # spec 阶段 6.5 — raw_screenshot_path 透传给 JSONL
                        # 仅识别类节点有值，动作类为 None（被 log_node_event 省略）
                        raw_screenshot_path=fields.get("raw_screenshot_path"),
                        error_msg=result.error_msg or "",
                        # spec 阶段 5 — 任务 1.8: error_code 透传给 JSONL
                        # NodeErrorCode (StrEnum) 或字符串均自动 str() 归一
                        error_code=result.error_code or "",
                        auto_heal_attempts=fields.get("auto_heal_attempts"),
                        # spec 阶段 4.3: include node design semantics for LLM diagnosis
                        comment=getattr(node, "comment", "") or "",
                        rationale=getattr(node, "rationale", "") or "",
                        # N191 §10.7 P1-1 (架构层归一化, 2026-07-27): 写入
                        # 当前 pipeline 的坐标系标签, 让 AI 分析 JSONL 时
                        # 能判断 match_location / roi_base / _last_match_pos
                        # 等坐标字段的语义 (logical / physical)。空字符串
                        # (legacy 模式) 时 log_node_event 自动省略字段。
                        coord_system=getattr(self._context, "coord_system", "") or "",
                        # N191 §10.10 决策点 6 (AI 可调试性, 2026-07-27):
                        # device_type + transformer_id 强制写入, AI 跨设备
                        # 对比时按此分组 (D3 跨设备对比能力)。
                        device_type=self._device_type,
                        transformer_id=self._transformer_id,
                        # spec 阶段 3.3 — 任务 1.4: variables_snapshot
                        variables_snapshot=_vars_snapshot if _vars_snapshot else None,
                        # spec 阶段 3.2 — 任务 1.4: cross-step chain
                        extra=extra if extra else None,
                    )

                    # Update cross-step chain for the next node's JSONL event.
                    self._previous_node_id = node.id
                    self._previous_node_type = node.node_type
                    self._previous_node_end_time = time.monotonic()
                self._context.record_step(
                    node_id=self._current_node_id,
                    node_type=node.node_type,
                    state=state,
                    result_data=result.data,
                    error_msg=result.error_msg,
                    elapsed_time=result.elapsed_time,
                )

                if self._on_step_complete:
                    self._on_step_complete(self._current_node_id, result)

                self._context.current_step_index += 1

                # 节点执行失败
                if not result.success:
                    # spec-2026-07-27 阶段 2: continue_on_error 节点属性优先,
                    # 回退到 config["continue_on_error"]（向后兼容）。
                    continue_on_error = node.continue_on_error or node.config.get("continue_on_error", False)
                    if not continue_on_error:
                        # spec 阶段 3 — 任务 3.3: 尝试界面恢复.
                        # 最多 2 次尝试 (attempt=0 直走 + attempt=1 换路径).
                        # RECOVERED / ALREADY_THERE → 重试当前节点 (不前进 _current_node_id)
                        # NEEDS_HUMAN / RECOVERY_FAILED 或达到上限 → 返回 FAILED.
                        if self._recovery_manager is not None and node.config.get(
                            "enable_recovery", True,
                        ):
                            recovery_outcome = self._attempt_recovery(node, result)
                            if recovery_outcome in ("RECOVERED", "ALREADY_THERE"):
                                # 重试当前节点: 不前进 _current_node_id,
                                # 跳过下面的 _resolve_next_node.
                                logger.info(
                                    "节点 %s 恢复成功 (%s), 重试当前节点",
                                    self._current_node_id, recovery_outcome,
                                )
                                continue

                        self._state = PipelineState.FAILED
                        return PipelineResult(
                            success=False,
                            state=PipelineState.FAILED,
                            data=self._step_results,
                            error_msg=f"节点 {self._current_node_id} 执行失败: {result.error_msg}",
                            elapsed_time=time.monotonic() - start_time,
                            step_results=list(self._step_results),
                        )

                # 在节点执行完成后再次检查取消信号
                if self._cancel_event.is_set():
                    logger.info("Pipeline 在节点 %s 执行完成后收到取消信号", self._current_node_id)
                    self._state = PipelineState.CANCELLED
                    return PipelineResult(
                        success=False,
                        state=PipelineState.CANCELLED,
                        data=self._step_results,
                        error_msg="Pipeline 已取消",
                        elapsed_time=time.monotonic() - start_time,
                        step_results=list(self._step_results),
                    )

                # Check Maa Stop signal (set by StopNode via context variable).
                # Treated as graceful completion, not cancellation.
                if self._context is not None and self._context.get_variable("_stop_requested"):
                    stop_reason = self._context.get_variable("_stop_reason", "user requested")
                    logger.info("Pipeline 收到 Stop 信号 (source=%s, reason=%s)，停止执行",
                                self._context.get_variable("_stop_source", "unknown"), stop_reason)
                    # Consume the signal so it doesn't leak into a resumed run
                    self._context.set_variable("_stop_requested", False)
                    self._state = PipelineState.COMPLETED
                    return PipelineResult(
                        success=True,
                        state=PipelineState.COMPLETED,
                        data=self._step_results,
                        error_msg="",
                        elapsed_time=time.monotonic() - start_time,
                        step_results=list(self._step_results),
                    )

                # 计算下一个节点
                next_id = self._resolve_next_node(node, result)
                self._current_node_id = next_id or ""

            if iteration >= self._max_iterations:
                self._state = PipelineState.FAILED
                return PipelineResult(
                    success=False,
                    state=PipelineState.FAILED,
                    data=self._step_results,
                    error_msg=f"超过最大迭代次数 {self._max_iterations}",
                    elapsed_time=time.monotonic() - start_time,
                    step_results=list(self._step_results),
                )

        except Exception as exc:
            self._state = PipelineState.FAILED
            return PipelineResult(
                success=False,
                state=PipelineState.FAILED,
                data=self._step_results,
                error_msg=str(exc),
                elapsed_time=time.monotonic() - start_time,
                step_results=list(self._step_results),
            )
        finally:
            # 阶段 3 (性能计量): Pipeline 结束时写入 perf_summary 事件.
            # 从 PerfMonitor 读取聚合统计, 写入 JSONL 供 LLM 诊断.
            if self._structured_logger is not None:
                try:
                    _perf_monitor = PerfMonitor.get_instance()
                    _aggregates = _perf_monitor.get_aggregates()
                    if _aggregates:
                        _total_ms = (time.monotonic() - start_time) * 1000.0
                        self._structured_logger.log_orchestrator_event(
                            event="perf.perf_summary",
                            success=True,
                            elapsed_ms=round(_total_ms, 2),
                            extra={
                                "total_ms": round(_total_ms, 2),
                                "node_count": len(self._step_results),
                                "breakdown": _aggregates,
                            },
                        )
                except Exception:
                    logger.debug("perf summary logging failed (best-effort)", exc_info=True)  # never block pipeline

            # Close structured logger so no further events are written to
            # this execution's JSONL file (spec 阶段 3.1). Safe to call
            # even when _structured_logger is None (early-return paths).
            if self._structured_logger is not None:
                self._structured_logger.close()
                self._structured_logger = None
            # 阶段 2 (性能计量): 清除 PerfMonitor 的 structured_logger
            # 引用, 避免 perf.timer 事件污染后续 JSONL 文件.
            PerfMonitor.get_instance().clear_structured_logger()
            # N pipeline 优化 2026-08-02: 关闭复用线程池.
            # wait=False 避免阻塞在挂起的 worker 线程上.
            _reusable_executor.shutdown(wait=False)

        self._state = PipelineState.COMPLETED
        elapsed = time.monotonic() - start_time
        logger.info("Pipeline 执行完成，共 %d 个步骤", len(self._step_results))
        return PipelineResult(
            success=True,
            state=PipelineState.COMPLETED,
            data=self._step_results,
            elapsed_time=elapsed,
            step_results=list(self._step_results),
        )
