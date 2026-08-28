"""Task orchestrator: manages task execution lifecycle"""

import contextlib
import logging
import os
import threading
import time
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any

from core.config import AgentConfig
from core.delay import DelayManager
from core.error_codes import NodeErrorCode
from core.recovery import HumanTakeoverError
from core.result import AutoResult, fail_result
from core.verify import Verifier
from devices.manager import DeviceManager
from engine.context import PipelineState
from image.processor import ImageProcessor
from utils.structured_logger import (
    StructuredLogger,
    new_execution_id,
)
from utils.structured_logger import (
    get_logger as get_structured_logger,
)

logger = logging.getLogger(__name__)


class TaskState(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskOrchestrator:
    """任务编排器：管理任务执行生命周期，支持取消/暂停/恢复"""

    def __init__(
        self,
        device_manager: DeviceManager,
        image_processor: ImageProcessor,
        config: AgentConfig | None = None,
    ):
        self._device_manager = device_manager
        self._image_processor = image_processor
        self._config = config or AgentConfig()
        self._delay_manager = DelayManager()
        self._state: TaskState = TaskState.PENDING
        self._current_step_index: int = 0
        self._task_definition: dict[str, Any] | None = None
        self._on_task_complete: Callable | None = None
        self._on_task_failed: Callable | None = None
        self._monitor_manager = None
        # execute_task serializes on this lock because it relies on multiple
        # instance attributes (_state, _current_step_index, _task_definition,
        # _delay_manager) that are not thread-local. Concurrent execute_task
        # calls would corrupt this state. True per-device concurrency is
        # delivered by execute_pipeline, which is the multi-instance main path
        # and does not touch global active_device state (see P3 fix in
        # docs/specs/legacy-trae/2026-07-16-multi-instance-control-fix.md).
        # Tech-debt: full ExecutionContext refactor to enable execute_task
        # concurrency tracked in docs/archive/active-tech-debt.md (TD-P3).
        self._task_exec_lock = threading.RLock()
        # P0-4 fix (AI 可调试性, 2026-07-27): orchestrator-level structured
        # logger. Lazily created at the start of execute_pipeline /
        # _execute_state_machine_dispatch and cleared at the end. Shared
        # execution_id with the engine so task.start/complete/... events
        # and node.execute.complete events land in the same JSONL file.
        # cancel_task / pause_task / resume_task read this to emit their
        # own trace events from whichever thread invoked them.
        self._orchestrator_logger: StructuredLogger | None = None
        self._orchestrator_exec_id: str = ""

        # spec 阶段 3 — 任务 3.1: 抽出 Verifier 模块。
        # Verifier 通过 lambda 闭包引用 self._device_manager /
        # self._image_processor，所以测试 patch
        # orchestrator._image_processor.find_template.return_value=...
        # 仍然生效（调用时才解析）。
        self._verifier = Verifier(
            screenshot_fn=lambda: self._device_manager.get_active_device().capture_screen(),
            template_match_fn=lambda screenshot, template, roi=None, threshold=0.8: (
                self._image_processor.find_template(
                    screenshot, template, roi=roi, threshold=threshold,
                )
            ),
            color_pick_fn=lambda screenshot, color, roi=None: (
                self._image_processor.find_color(screenshot, color, roi=roi)
            ),
            ocr_registry_fn=self._get_ocr_registry,
        )

    def set_monitor_manager(self, monitor_manager) -> None:
        """设置监控管理器"""
        self._monitor_manager = monitor_manager

    @property
    def state(self) -> TaskState:
        """获取当前任务状态"""
        return self._state

    def set_callbacks(
        self,
        on_complete: Callable | None = None,
        on_failed: Callable | None = None,
    ) -> None:
        """设置任务完成/失败回调"""
        self._on_task_complete = on_complete
        self._on_task_failed = on_failed

    def execute_task(
        self,
        task_definition: dict[str, Any],
        execution_mode: str = "pipeline",
        device_id: str | None = None,
    ) -> AutoResult:
        """执行任务 — DEPRECATED (spec-2026-07-27-execution-path-unification 阶段 4).

        .. deprecated::
            本方法已废弃，统一走 ``execute_pipeline``。保留仅为向后兼容老测试
            代码与潜在外部调用者。``execution_mode`` 参数已不影响分发逻辑 —
            分发由 ``task_definition`` shape 决定（含 ``module`` 字段 →
            state_machine 路径；否则 → pipeline 路径）。

        Args:
            task_definition: pipeline JSON（含 nodes/edges 或线性 nodes）。
                state_machine 模式时含 ``module`` 字段。
            execution_mode: 已废弃，仅做日志记录。保留参数为向后兼容。
            device_id: Optional explicit target device id.

        Returns:
            AutoResult: 任务执行结果
        """
        return self.execute_pipeline(task_definition, device_id=device_id)

    def _execute_state_machine_dispatch(
        self,
        task_definition: dict[str, Any],
        device_id: str | None = None,
    ) -> AutoResult:
        """state_machine 模式分发入口 (spec-2026-07-27 阶段 6).

        从原 ``execute_task`` 的 state_machine 分支迁移而来。state_machine
        走 Python 模块 hook (StateMachine callables 不能 JSON 序列化),
        设备切换沿用原 chain 语义 (set_active_device 全局切换 + finally 恢复).

        Args:
            task_definition: 含 ``module`` 字段的 dict.
            device_id: Optional explicit target device id.

        Returns:
            AutoResult with state machine execution result
        """
        with self._task_exec_lock:
            self._task_definition = task_definition
            self._state = TaskState.RUNNING
            self._current_step_index = 0
            start_time = time.monotonic()
            # state_machine 设备切换（保留原 chain 语义: 全局 set_active_device）
            prev_active = None
            if device_id is not None:
                prev_active = self._device_manager.get_active_device_id()
                if not self._device_manager.set_active_device(device_id):
                    self._state = TaskState.FAILED
                    return fail_result(
                        error_msg=f"设备不存在或不可用: device_id={device_id}",
                        elapsed_time=time.monotonic() - start_time,
                    )
            try:
                return self._execute_state_machine(task_definition, start_time)
            finally:
                if prev_active is not None:
                    self._device_manager.set_active_device(prev_active)

    def _execute_state_machine(self, task_definition: dict[str, Any], start_time: float) -> AutoResult:
        """State-machine execution: import Python module and run StateMachine.

        StateMachine actions/transitions are Python callables that cannot be
        JSON-serialized, so state_machine mode requires a Python module hook.
        The module must expose::

            def build_state_machine(device_manager, image_processor) -> StateMachine:
                ...

        The module path is read from ``task_definition["module"]`` (dotted
        import path, e.g. ``"custom_tasks.browndust.guild_fsm"``). Optional
        ``max_iterations`` may be set in ``task_definition`` (default 1000).
        """
        import importlib

        module_path = task_definition.get("module")
        if not module_path:
            self._state = TaskState.FAILED
            return fail_result(
                error_msg="state_machine 模式缺少 module 字段",
                elapsed_time=time.monotonic() - start_time,
            )

        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            self._state = TaskState.FAILED
            return fail_result(
                error_msg=f"state_machine 模块导入失败: {module_path} — {exc}",
                elapsed_time=time.monotonic() - start_time,
            )

        builder = getattr(module, "build_state_machine", None)
        if not callable(builder):
            self._state = TaskState.FAILED
            return fail_result(
                error_msg=f"模块 {module_path} 未暴露 build_state_machine(device_manager, image_processor) 工厂函数",
                elapsed_time=time.monotonic() - start_time,
            )

        try:
            machine = builder(self._device_manager, self._image_processor)
        except Exception as exc:
            self._state = TaskState.FAILED
            return fail_result(
                error_msg=f"build_state_machine 调用失败: {exc}",
                elapsed_time=time.monotonic() - start_time,
            )

        max_iterations = int(task_definition.get("max_iterations", 1000))
        try:
            result = machine.run(max_iterations=max_iterations)
        except Exception as exc:
            self._state = TaskState.FAILED
            return fail_result(
                error_msg=f"状态机执行异常: {exc}",
                elapsed_time=time.monotonic() - start_time,
            )

        elapsed = time.monotonic() - start_time
        result.elapsed_time = elapsed
        if result.success:
            self._state = TaskState.COMPLETED
            if self._on_task_complete:
                self._on_task_complete(result)
        else:
            self._state = TaskState.FAILED
            if self._on_task_failed:
                self._on_task_failed(result)
        return result

    def cancel_task(self) -> None:
        """取消当前任务"""
        self._state = TaskState.CANCELLED
        self._delay_manager.interrupt()
        logger.info("任务已标记为取消")
        # P0-4: emit orchestrator trace so AI can see when/why cancel happened.
        self._emit_orchestrator_event(
            event="orchestrator.task.cancelled",
            task_state=TaskState.CANCELLED.value,
            extra={"cancel_reason": "user_requested"},
        )

    def pause_task(self) -> None:
        """暂停当前任务"""
        if self._state == TaskState.RUNNING:
            self._state = TaskState.PAUSED
            logger.info("任务已暂停")
            # P0-4: emit trace — AI debugging needs to see pause timing.
            self._emit_orchestrator_event(
                event="orchestrator.task.paused",
                task_state=TaskState.PAUSED.value,
                extra={"pause_reason": "user_requested"},
            )

    def resume_task(self) -> None:
        """恢复暂停的任务"""
        if self._state == TaskState.PAUSED:
            self._state = TaskState.RUNNING
            logger.info("任务已恢复")
            # P0-4: emit trace — AI debugging needs to see resume timing.
            self._emit_orchestrator_event(
                event="orchestrator.task.resumed",
                task_state=TaskState.RUNNING.value,
            )

    # ------------------------------------------------------------------
    # P0-4 fix (AI 可调试性, 2026-07-27): orchestrator trace event helper.
    # ------------------------------------------------------------------
    def _emit_orchestrator_event(
        self,
        *,
        event: str,
        task_state: str = "",
        success: bool | None = None,
        elapsed_ms: float = 0.0,
        device_id: str = "",
        pipeline_name: str = "",
        error_msg: str = "",
        error_code: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Emit an orchestrator-level trace event to the structured JSONL.

        No-op when ``_orchestrator_logger`` is None (no active task or
        structured logging not initialized). Failures are swallowed —
        trace events must never block the pipeline.
        """
        orch_logger = self._orchestrator_logger
        if orch_logger is None:
            return
        try:
            orch_logger.log_orchestrator_event(
                event=event,
                task_state=task_state,
                success=success,
                elapsed_ms=elapsed_ms,
                device_id=device_id,
                pipeline_name=pipeline_name,
                error_msg=error_msg,
                error_code=error_code,
                extra=extra,
            )
        except Exception as exc:
            logger.warning(
                "_emit_orchestrator_event failed (non-fatal): %s", exc,
            )

    def _init_orchestrator_logger(
        self,
        debug_dir: str,
        pipeline_json: dict[str, Any] | None = None,
        execution_id_override: str = "",
    ) -> str:
        """Create the orchestrator-level StructuredLogger for one task run.

        Stores ``_orchestrator_logger`` + ``_orchestrator_exec_id``. The
        same execution_id MUST be passed to ``engine.load(execution_id=...)``
        so the engine's node events share the JSONL file with orchestrator
        events.

        Args:
            debug_dir: Debug output root (same value passed to engine.load).
            pipeline_json: Optional pipeline dict (for pipeline_name field).
            execution_id_override: P0-1 fix. When non-empty, use this
                execution_id (server-provided or ContextVar) instead of
                generating a new one. Empty string = generate fresh id
                (CLI mode / backward compat).

        Returns:
            The execution_id (pass to engine.load).
        """
        exec_id = execution_id_override or new_execution_id()
        self._orchestrator_exec_id = exec_id
        # A3 (spec 2026-07-30-debug-directory-restructure): 提取 pipeline_name
        # 和 trace_id 传给 StructuredLogger, 让日志路径和 JSONL 含全链路 trace_id.
        pipeline_name_a3 = ""
        if isinstance(pipeline_json, dict):
            pipeline_name_a3 = (pipeline_json.get("metadata") or {}).get("pipeline_name", "")
        trace_id_a3 = ""
        try:
            from core.context_vars import get_current_user_trace_id
            trace_id_a3 = get_current_user_trace_id()
        except ImportError:
            pass
        self._orchestrator_logger = get_structured_logger(
            exec_id,
            debug_dir=debug_dir,
            pipeline_name=pipeline_name_a3,
            trace_id=trace_id_a3,
        )
        # N194 归一化 (2026-07-28): agent 接管后更新 meta.json status,
        # 让用户在 debug 目录看到"backend 已派发 → agent 已接管"的流转.
        # 仅当 debug_dir 是归一化 exec_dir 时才更新 (legacy root 跳过).
        self._update_meta_status(debug_dir, exec_id, status="agent_running")
        return exec_id

    def _update_meta_status(
        self,
        debug_dir: str,
        execution_id: str,
        status: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """N194 归一化 (2026-07-28): update meta.json status in the unified
        exec directory.

        Best-effort: failures only emit a warning, never block the pipeline.
        No-op when debug_dir is a legacy root (not a unified exec dir) —
        backend didn't create meta.json there.
        """
        try:
            from utils.debug_path import _is_unified_exec_dir, write_meta_json
            if not _is_unified_exec_dir(debug_dir):
                return
            write_meta_json(
                debug_dir,
                execution_id=execution_id,
                status=status,
                extra=extra,
            )
        except Exception as exc:
            logger.warning(
                "_update_meta_status failed for %s (non-fatal): %s",
                debug_dir, exc,
            )

    def _clear_orchestrator_logger(self, *, final_status: str = "agent_done") -> None:
        """Clear the orchestrator logger after a task run completes.

        Does NOT close the underlying StructuredLogger — the engine owns
        the lifecycle for the shared JSONL file (engine.execute() closes
        it in its finally block). We only drop our reference so subsequent
        cancel/pause/resume calls between tasks become no-ops.

        N194 归一化 (2026-07-28): also updates meta.json status to mark
        agent's final state (agent_done / agent_cancelled / agent_failed),
        so users browsing the debug directory see the task lifecycle.
        """
        # Update meta.json before dropping references (need exec_id + debug_dir).
        orch_logger = self._orchestrator_logger
        exec_id = self._orchestrator_exec_id
        if orch_logger is not None and exec_id:
            # Reverse-engineer debug_dir from the JSONL file path:
            # <exec_dir>/structured.jsonl → <exec_dir>
            exec_dir = os.path.dirname(orch_logger.file_path)
            self._update_meta_status(
                exec_dir, exec_id, status=final_status,
                extra={"agent_finished_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
            )
        self._orchestrator_logger = None
        self._orchestrator_exec_id = ""

    def _run_verify(self, verify: dict[str, Any]) -> AutoResult:
        """Execute verification based on verify type.

        Spec 阶段 3 — 任务 3.1: 6 种验证逻辑已迁出到 ``core.verify.Verifier``,
        本方法委托给 ``self._verifier.verify()``。保留方法签名是为了向后
        兼容现有测试 (test_orchestrator.py + test_verify_handler.py 直接
        调用 ``orchestrator._run_verify(...)``)。

        Supported verify types (N126-F1, unchanged):
        - template: template image must be present on screen
        - color: color must be present in ROI
        - exist: template OR color must be present (alias with explicit element type)
        - disappear: template OR color must NOT be present (inverse of exist)
        - text: OCR must find expected text in ROI
        - custom_verify: invoke user-provided callable path (module:function)

        Args:
            verify: verify dict with "type" and type-specific params.

        Returns:
            AutoResult with success/fail and matched data.
        """
        return self._verifier.verify(verify)

    def _get_ocr_registry(self):
        """Get or lazily create OCR engine registry.

        Registry is shared across all verify calls. Engines must be
        registered externally (e.g. during agent bootstrap).

        Returns:
            OCREngineRegistry instance or None if unavailable.
        """
        if not hasattr(self, "_ocr_registry"):
            try:
                from recognition.ocr.registry import OCREngineRegistry
                self._ocr_registry = OCREngineRegistry()
            except ImportError:
                self._ocr_registry = None
        return self._ocr_registry

    def register_ocr_engine(self, engine, name: str) -> None:
        """Register an OCR engine for text verification.

        Args:
            engine: BaseOCREngine instance.
            name: engine name identifier.
        """
        registry = self._get_ocr_registry()
        if registry is not None:
            registry.register(engine, name)
            logger.info("OCR 引擎已注册到 orchestrator: %s", name)
        else:
            logger.warning("OCR registry 不可用, 无法注册引擎 %s", name)

    def execute_pipeline(
        self,
        pipeline_json: dict[str, Any],
        debug_mode: bool = False,
        debug_dir: str = "",
        wait_when_background: dict[str, Any] | None = None,
        on_wait_status: Callable[[str, dict[str, Any]], None] | None = None,
        on_step_progress: Callable[[str, AutoResult, int], None] | None = None,
        device_id: str | None = None,
        execution_id: str = "",
        start_step_index: int = 0,
        previous_results: list[AutoResult] | None = None,
    ) -> AutoResult:
        """Execute a Pipeline JSON definition through PipelineEngine with device injection.

        This bridges the action-based orchestrator path with the graph-based
        PipelineEngine. The target device is resolved directly from
        ``device_id`` (or falls back to the current active device when
        ``device_id`` is None) and injected into PipelineContext so that all
        nodes (template_match, click, swipe, etc.) can access it via
        ``context.device``.

        spec-2026-07-27-execution-path-unification 阶段 6: 本方法现已成为
        唯一执行入口。state_machine 模式（task_definition 含 ``module`` 字段）
        在此处分发到 ``_execute_state_machine``；其余情况走 PipelineEngine。

        Multi-device concurrency: this method does NOT touch
        ``DeviceManager._active_device_id``. Each call resolves its own device
        object via ``DeviceManager.get_device(device_id)`` and passes it
        through to PipelineEngine. This means multiple ``execute_pipeline``
        calls running in separate threads (one per device) do not contend on
        global active_device state — true per-device parallelism is achieved.

        Args:
            pipeline_json: Pipeline definition dict (with nodes, edges, etc.)
                或 state_machine 定义 dict (含 ``module`` 字段).
            debug_mode: When True, save annotated debug screenshots per node.
            debug_dir: Directory for debug screenshots (used when debug_mode=True).
            wait_when_background: When enabled, monitor window foreground state
                and pause pipeline when window loses foreground.
            on_wait_status: Callback(msg_type, payload) to report wait status
                to the frontend (e.g. task.progress with status=paused).
            on_step_progress: Optional callback(node_id, result, step_index)
                invoked after each pipeline node completes (success or failure).
                Used by handler.py to forward per-step status to the backend
                via task.progress frames (P-010 step-level recovery signal).
            device_id: Optional explicit target device id. When None, falls
                back to ``DeviceManager.get_active_device()`` (legacy single-
                device behavior).
            execution_id: P0-1 fix (AI 可调试性, 2026-07-27). Server-provided
                execution_id, used as the JSONL filename so agent-side
                structured logs share the same execution_id as backend WS
                messages. When empty, orchestrator falls back to
                ``current_execution_id`` ContextVar (set by handler._run),
                then to ``new_execution_id()`` (legacy/CLI mode). This
                unifies the three execution_id sources for AI correlation.
            start_step_index: Task 1.1 (B7 重试单节点, P0-1). 跳过前 N 个
                节点的实际执行, 从第 N+1 个节点开始跑. 透传给
                ``PipelineEngine.execute(start_step_index=N)``. 默认 0 = 不跳过.
                用于"重试此步"功能: 用户在前端选择失败节点后, backend 创建
                新 execution 并传 start_step_index=N, agent 跳过前 N 个节点
                只重跑失败节点及后续节点, 避免重跑整个 pipeline.
            previous_results: Task 1.1. 之前成功节点的 AutoResult 列表,
                长度应等于 ``start_step_index``. 透传给
                ``PipelineEngine.execute(previous_results=...)``. 让最终
                PipelineResult.step_results 完整 (用户能看到前驱节点输出),
                且跳过节点的 _resolve_next_node 决策能保留原分支选择.

        Returns:
            AutoResult with pipeline execution result
        """
        # TD-354: state_machine 分发改用 TaskExecutor (ChainManager).
        # 检测 task_definition 含 "module" 字段即走 ChainManager 路径
        # (Python 模块 hook, StateMachine callables 不能 JSON 序列化).
        if isinstance(pipeline_json, dict) and pipeline_json.get("module"):
            from engine.executor import TaskExecutor

            executor = TaskExecutor()
            result = executor.execute(
                "chain",
                pipeline_json,
                device_manager=self._device_manager,
                image_processor=self._image_processor,
                device_id=device_id,
            )
            # Map ChainManager result to orchestrator state
            if result.success:
                self._state = TaskState.COMPLETED
                if self._on_task_complete:
                    self._on_task_complete(result.data)
            else:
                self._state = TaskState.FAILED
                if self._on_task_failed:
                    self._on_task_failed(result)
            return result

        # P0-1 fix: resolve execution_id with fallback chain.
        # 1. Explicit parameter (handler passes server's execution_id)
        # 2. ContextVar (set by handler._run for thread-local isolation)
        # 3. new_execution_id() (legacy/CLI mode, generates a fresh id)
        # This unifies server execution_id ↔ agent JSONL execution_id so AI
        # can correlate WS messages with JSONL events by execution_id.
        if not execution_id:
            try:
                from core.context_vars import get_current_execution_id
                execution_id = get_current_execution_id()
            except ImportError:
                execution_id = ""

        start_time = time.monotonic()
        self._state = TaskState.RUNNING

        # P0-4 fix: initialize orchestrator logger early so task.start +
        # device-resolution failures land in JSONL. debug_dir resolution
        # mirrors engine.load()'s default ("./debug") so the file lands
        # under the same root as engine node events.
        # P0-1 fix: pass the resolved execution_id (server-provided or
        # ContextVar) so JSONL filename matches WS execution_id for AI
        # correlation. _init_orchestrator_logger falls back to
        # new_execution_id() when execution_id is empty (CLI mode).
        effective_debug_dir_p0 = debug_dir or getattr(self._config, "debug_dir", "") or "./debug"
        pipeline_name_p0 = ""
        if isinstance(pipeline_json, dict):
            pipeline_name_p0 = (pipeline_json.get("metadata") or {}).get("pipeline_name", "")
        exec_id_p0 = self._init_orchestrator_logger(
            effective_debug_dir_p0, pipeline_json=pipeline_json,
            execution_id_override=execution_id,
        )
        self._emit_orchestrator_event(
            event="orchestrator.task.start",
            task_state=TaskState.RUNNING.value,
            device_id=device_id or "",
            pipeline_name=pipeline_name_p0,
            extra={
                "execution_id": exec_id_p0,
                "pipeline_node_count": len(pipeline_json.get("nodes", [])) if isinstance(pipeline_json, dict) else 0,
            },
        )

        # Resolve target device directly by id — no global active_device
        # mutation. Falls back to active device only when no device_id given
        # (backward compat for legacy callers).
        if device_id is not None:
            device = self._device_manager.get_device(device_id)
            if device is None:
                self._state = TaskState.FAILED
                logger.error("[ORCHESTRATOR] 设备不存在: device_id=%s", device_id)
                elapsed_p0 = (time.monotonic() - start_time) * 1000
                self._emit_orchestrator_event(
                    event="orchestrator.task.failed",
                    task_state=TaskState.FAILED.value,
                    success=False,
                    elapsed_ms=elapsed_p0,
                    device_id=device_id or "",
                    pipeline_name=pipeline_name_p0,
                    error_msg=f"设备不存在或不可用: device_id={device_id}",
                    error_code="DEVICE_NOT_FOUND",
                )
                self._clear_orchestrator_logger()
                return fail_result(
                    error_msg=f"设备不存在或不可用: device_id={device_id}",
                    elapsed_time=time.monotonic() - start_time,
                    error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                )
        else:
            device = self._device_manager.get_active_device()
            if device is None:
                self._state = TaskState.FAILED
                logger.error("[ORCHESTRATOR] 无可用设备 (device_id=None 且无活跃设备)")
                elapsed_p0 = (time.monotonic() - start_time) * 1000
                self._emit_orchestrator_event(
                    event="orchestrator.task.failed",
                    task_state=TaskState.FAILED.value,
                    success=False,
                    elapsed_ms=elapsed_p0,
                    pipeline_name=pipeline_name_p0,
                    error_msg="无可用设备，无法执行 Pipeline",
                    error_code="NO_AVAILABLE_DEVICE",
                )
                self._clear_orchestrator_logger()
                return fail_result(
                    error_msg="无可用设备，无法执行 Pipeline",
                    elapsed_time=time.monotonic() - start_time,
                    error_code=NodeErrorCode.DEVICE_DISCONNECTED,
                )

        return self._execute_pipeline_inner(
            pipeline_json, debug_mode, debug_dir,
            wait_when_background, on_wait_status, on_step_progress,
            start_time, device, exec_id_p0,
            start_step_index=start_step_index,
            previous_results=previous_results,
            pipeline_name_p0=pipeline_name_p0,
        )

    def _execute_pipeline_inner(
        self,
        pipeline_json: dict[str, Any],
        debug_mode: bool,
        debug_dir: str,
        wait_when_background: dict[str, Any] | None,
        on_wait_status: Callable[[str, dict[str, Any]], None] | None,
        on_step_progress: Callable[[str, AutoResult, int], None] | None,
        start_time: float,
        device: Any,
        execution_id_p0: str = "",
        start_step_index: int = 0,
        previous_results: list[AutoResult] | None = None,
        pipeline_name_p0: str = "",
    ) -> AutoResult:
        """Inner pipeline execution with an already-resolved device.

        Args:
            device: The resolved BaseDevice instance to inject into
                PipelineContext. Caller is responsible for resolution
                (by device_id or active fallback) so this method never
                touches ``DeviceManager._active_device_id``.
            execution_id_p0: P0-4 fix. Orchestrator-generated execution_id
                to share with engine.load() so task-level + node-level
                events land in the same JSONL file. Empty string = let
                engine generate its own (backward compat for direct callers).
            start_step_index: Task 1.1 (B7 重试单节点, P0-1). 透传给
                ``PipelineEngine.execute(start_step_index=N)``.
            previous_results: Task 1.1. 透传给
                ``PipelineEngine.execute(previous_results=...)``.
            pipeline_name_p0: N197 fix. Pipeline name from metadata, passed
                through from execute_pipeline() so _execute_pipeline_inner
                can use it for structured logging events without a NameError
                (was missing from the parameter list, causing the thread to
                silently crash with CoordTransformerError).
        """
        from engine.pipeline_engine import PipelineEngine

        logger.info(
            "[ORCHESTRATOR] execute_pipeline 开始: device=%s, pipeline_nodes=%d",
            getattr(device, 'device_id', None),
            len(pipeline_json.get('nodes', [])) if isinstance(pipeline_json, dict) else 0,
        )

        # Build DPI-aware coordinate transformer from pipeline metadata (if any).
        # metadata.original_base_res = [1920, 1080] tells the transformer that
        # ROIs and templates are defined at 1920x1080 reference resolution.
        # When absent (legacy pipelines), coord_transformer stays None and nodes
        # fall back to raw-pixel behavior (backward compat).
        #
        # N191 §10.7 P0-2 (架构层归一化, 2026-07-27): 新增 ADB 路径 transformer
        # 注入。Windows 走 CoordinateTransformer (base→logical→physical→screen),
        # ADB 走 ADBCoordinateTransformer (base→physical 直接缩放)。两条路径
        # 都暴露 coord_system 类属性, 读取后注入 PipelineContext.coord_system,
        # 让 publish_match_pos / structured_logger 知道当前流转的是哪个坐标系。
        metadata = pipeline_json.get("metadata", {}) or {}
        base_res = metadata.get("original_base_res")  # [w, h] or None
        display_context = None
        coord_transformer = None
        coord_system = ""
        if base_res and isinstance(base_res, (list, tuple)) and len(base_res) == 2:
            base_res_tuple = tuple(int(v) for v in base_res)
            # 优先尝试 Windows 路径 (依赖 hwnd / DPI); 失败回退 ADB 路径。
            # 用 hasattr 判断 device 是否为 Windows 设备更干净, 但
            # WindowsDevice 在 platforms.windows 包下, 不在 devices.base,
            # 这里用 try/except 包住 build_transformer, ADBDevice 会因
            # 缺 hwnd 在 build_transformer 内部抛错自然回退。
            try:
                from platforms.windows.display_builder import build_transformer
                coord_transformer = build_transformer(device, base_res_tuple)
                if coord_transformer is not None:
                    display_context = coord_transformer.display_context
                    # Propagate DPI ratio to the device's input handler so
                    # SendInput/PseudoBackground can convert logical→physical
                    # coords before ClientToScreen (DPI coordinate bug fix).
                    dpi_ratio = display_context.logical_to_physical_ratio
                    if hasattr(device, "set_dpi_ratio"):
                        device.set_dpi_ratio(dpi_ratio)
                    coord_system = getattr(
                        coord_transformer, "coord_system", "logical",
                    )
                    logger.info(
                        "execute_pipeline: built Windows coord_transformer "
                        "for base_res=%s | dpi_ratio=%.4f | coord_system=%s | %s",
                        base_res, dpi_ratio, coord_system, display_context,
                    )
                    # N196 (2026-08-01): 把 display_context 写入结构化日志,
                    # 让 AI 调试时可以从 JSONL 直接读到 DPI/分辨率/屏幕信息,
                    # 无需翻 INFO 日志或跑诊断脚本.
                    if display_context:
                        self._emit_orchestrator_event(
                            event="coord_transform_context",
                            task_state=TaskState.RUNNING.value,
                            device_id=getattr(device, "device_id", "") or "",
                            pipeline_name=pipeline_name_p0,
                            extra={
                                "transformer_type": "windows",
                                "coord_system": coord_system,
                                "dpi_scale": round(display_context.dpi_scale, 4),
                                "logical_to_physical_ratio": round(
                                    display_context.logical_to_physical_ratio, 4,
                                ),
                                "original_base_res": [
                                    display_context.original_base_width,
                                    display_context.original_base_height,
                                ],
                                "client_logical_res": [
                                    display_context.client_logical_width,
                                    display_context.client_logical_height,
                                ],
                                "client_physical_res": [
                                    display_context.client_physical_width,
                                    display_context.client_physical_height,
                                ],
                                "screen_physical_res": [
                                    display_context.screen_physical_width,
                                    display_context.screen_physical_height,
                                ],
                                "client_screen_origin": [
                                    display_context.client_screen_origin_x,
                                    display_context.client_screen_origin_y,
                                ],
                                "is_fullscreen": display_context.is_fullscreen,
                                "hwnd": display_context.hwnd,
                            },
                        )
            except Exception as exc:
                logger.debug(
                    "execute_pipeline: Windows build_transformer not applicable "
                    "(trying ADB path if device supports get_resolution): %s",
                    exc,
                )
                coord_transformer = None

            # N191 §10.7 P0-2: ADB 路径 — 若 Windows transformer 构建失败
            # 且 device 有 get_resolution 方法 (ADBDevice 提供), 构造
            # ADBCoordinateTransformer 做 base→physical 缩放。
            #
            # N191 §10.11 D5 修正 (AI 可调试性, 2026-07-27): 之前用
            # `hasattr(device, "get_resolution")` 判断, 但 WindowsDevice
            # 也有 get_resolution, 导致 Windows hwnd 失效时误走 ADB 路径,
            # coord_system 错误标 "physical" 但 device.click 期望 logical。
            # 改为: 用 getattr(device, "hwnd", None) 判断 Windows 设备,
            # hwnd 是非 None 整数才认为是 Windows 设备; 若是 Windows 设备
            # + build_transformer 返回 None → fail fast (CoordTransformerError,
            # root_cause="device"); 只有非 Windows 设备才走 ADB 路径。
            # 用 getattr + None check 而非 hasattr, 避免 MagicMock 默认属性
            # 误判 (test fixture device.hwnd=None 即可走 ADB 路径)。
            is_windows_device = getattr(device, "hwnd", None) is not None
            if coord_transformer is None and is_windows_device:
                # Windows 设备 + base_res 已配 + build_transformer 失败
                # → fail fast, 不能静默走 ADB 路径 (坐标系不匹配)。
                from core.exceptions import CoordTransformerError
                device_id_str = getattr(device, "device_id", "") or ""
                raise CoordTransformerError(
                    "Windows build_transformer returned None (hwnd invalid "
                    "or display context unavailable)",
                    root_cause_category="device",
                    missing_field="hwnd/display_context",
                    device_id=device_id_str,
                    base_resolution=str(base_res),
                    device_resolution="",
                )
            if coord_transformer is None and not is_windows_device \
                    and hasattr(device, "get_resolution"):
                try:
                    device_phys = device.get_resolution()
                    if device_phys and device_phys[0] > 0 and device_phys[1] > 0:
                        from utils.adb_coord_transformer import ADBCoordinateTransformer
                        coord_transformer = ADBCoordinateTransformer(
                            base_res=base_res_tuple,
                            device_physical_res=device_phys,
                        )
                        coord_system = coord_transformer.coord_system  # "physical"
                        logger.info(
                            "execute_pipeline: built ADB coord_transformer "
                            "for base_res=%s | device_phys=%s | coord_system=%s",
                            base_res, device_phys, coord_system,
                        )
                except Exception as exc:
                    # N191 §10.10 决策点 4 C (AI 可调试性, 2026-07-27):
                    # base_resolution 已配置但 ADB transformer 构建失败 →
                    # fail fast + 报错带 4 类归因。禁止静默退化为 raw pixel
                    # (调试地狱: AI 看到「执行成功」但点击位置错位)。
                    # legacy 任务 (base_resolution 未填) 不会进入本分支。
                    from core.exceptions import CoordTransformerError
                    device_id_str = getattr(device, "device_id", "") or ""
                    # device_phys 可能未定义 (device.get_resolution() 抛错时)
                    dev_phys_str = locals().get("device_phys", "")
                    raise CoordTransformerError(
                        f"ADB ADBCoordinateTransformer build failed: {exc}",
                        root_cause_category="device",
                        missing_field="device.get_resolution()",
                        device_id=device_id_str,
                        base_resolution=str(base_res),
                        device_resolution=str(dev_phys_str) if dev_phys_str else "",
                    ) from exc

        # Create engine, load pipeline with device + display services injection.
        # Debug mode: prefer WS message parameters (per-execution), fall back
        # to AgentConfig defaults (CLI --debug).
        effective_debug_mode = debug_mode or self._config.debug_mode
        effective_debug_dir = debug_dir or self._config.debug_dir
        if effective_debug_mode:
            logger.info(
                "execute_pipeline: debug_mode ON, debug_dir=%s", effective_debug_dir,
            )

        # Build LLM client for debug-mode auto-heal diagnosis (§4.8.2).
        # Only built when debug_mode is on AND server_url is configured —
        # avoids HTTP overhead in normal (non-debug) runs and standalone
        # CLI mode. Nodes duck-type via hasattr(context, 'llm_client').
        llm_client = None
        if effective_debug_mode and self._config.server_url:
            try:
                from ai.llm_client import AgentLLMClient
                llm_client = AgentLLMClient(
                    server_url=self._config.server_url,
                    token=self._config.agent_token,
                )
                logger.info(
                    "execute_pipeline: AgentLLMClient built for auto-heal (server=%s)",
                    self._config.server_url,
                )
            except Exception as exc:
                logger.warning(
                    "execute_pipeline: AgentLLMClient init failed (continuing without LLM auto-heal): %s",
                    exc,
                )
                llm_client = None

        # S2-2.7 (2026-08-17): build InterfaceRecoveryManager when
        # interface_states.yaml exists (recovery-design.md §5.3 Step 4).
        # All fields come from AgentConfig; missing yaml => recovery disabled.
        recovery_manager = None
        states_config_path = self._config.interface_states_path
        if states_config_path and Path(states_config_path).is_file():
            from core.interface_recovery import InterfaceRecoveryManager
            from engine.resource_resolver import resolve_resource_path

            def _resolved_find_template(screenshot, template, roi=None, threshold=0.8):
                # interface_states.yaml template paths match pipeline JSON
                # format ("public/xxx.png" or full path); find_template does
                # not resolve relative paths, so wrap with resolve_resource_path.
                resolved = resolve_resource_path(template)
                if resolved is None:
                    logger.warning("interface_states template 路径解析失败: %s", template)
                    return None
                return self._image_processor.find_template(
                    screenshot, resolved, roi=roi, threshold=threshold
                )

            try:
                recovery_manager = InterfaceRecoveryManager(
                    states_config_path=states_config_path,
                    screenshot_fn=device.capture_screen,
                    template_match_fn=_resolved_find_template,
                    action_executor_fn=lambda action: self._execute_recovery_action(device, action),
                    popup_handler=self._monitor_manager.popup_handler if self._monitor_manager else None,
                    archive_dir=self._config.unknown_state_archive_dir,
                    max_recovery_steps=self._config.max_recovery_steps,
                    archive_dedupe_window=self._config.archive_dedupe_window,
                )
                logger.info(
                    "execute_pipeline: InterfaceRecoveryManager 已启用 (states=%s)",
                    states_config_path,
                )
            except Exception as exc:
                logger.warning(
                    "execute_pipeline: InterfaceRecoveryManager 初始化失败, 本次执行不启用 UI 恢复: %s",
                    exc,
                )
                recovery_manager = None

        engine = PipelineEngine()
        try:
            engine.load(
                pipeline_json,
                device=device,
                display_context=display_context,
                coord_transformer=coord_transformer,
                monitor_manager=self._monitor_manager,
                debug_mode=effective_debug_mode,
                debug_dir=effective_debug_dir,
                llm_client=llm_client,
                coord_system=coord_system,
                execution_id=execution_id_p0,
                recovery_manager=recovery_manager,
                max_recovery_retries=self._config.max_recovery_retries if recovery_manager else 0,
            )
        except Exception as exc:
            self._state = TaskState.FAILED
            elapsed_load = (time.monotonic() - start_time) * 1000
            self._emit_orchestrator_event(
                event="orchestrator.task.failed",
                task_state=TaskState.FAILED.value,
                success=False,
                elapsed_ms=elapsed_load,
                device_id=getattr(device, "device_id", "") or "",
                pipeline_name=pipeline_json.get("metadata", {}).get("pipeline_name", "") if isinstance(pipeline_json, dict) else "",
                error_msg=f"Pipeline 加载失败: {exc}",
                error_code="PIPELINE_LOAD_FAILED",
            )
            self._clear_orchestrator_logger()
            return fail_result(
                error_msg=f"Pipeline 加载失败: {exc}",
                elapsed_time=time.monotonic() - start_time,
            )

        # Wire callbacks.
        # P-010: on_step_complete now forwards per-step status to the backend
        # via on_step_progress callback (handler.py sends task.progress frames).
        # This enables step-level failure signals → recovery_engine.handle_step_failure.
        step_counter = [0]  # mutable closure counter for step_index

        def _on_step_complete(node_id: str, result: AutoResult) -> None:
            if on_step_progress is not None:
                try:
                    on_step_progress(node_id, result, step_counter[0])
                except Exception as exc:  # never let callback crash the pipeline
                    logger.warning("on_step_progress callback failed: %s", exc)
            step_counter[0] += 1

        def _on_error(node_id: str, exc: Exception) -> None:
            if on_step_progress is not None:
                try:
                    on_step_progress(
                        node_id,
                        fail_result(error_msg=str(exc)),
                        step_counter[0],
                    )
                except Exception as cb_exc:
                    logger.warning("on_step_progress callback failed: %s", cb_exc)
            if self._on_task_failed:
                self._on_task_failed(fail_result(error_msg=str(exc)))

        engine.set_callbacks(on_step_complete=_on_step_complete, on_error=_on_error)

        # spec 阶段 3 — 任务 3.2: 注入 Verifier 让 engine 执行 post_verify 强验证.
        # 复用 orchestrator 已有的 self._verifier (任务 3.1 抽出), 避免重复构造.
        # Verifier 内部通过 lambda 闭包引用 self._device_manager / self._image_processor,
        # 调用时才解析, 所以在 engine.load() 之前/之后注入都可以.
        engine.set_verifier(self._verifier)

        # Execute with cancel/pause support via state polling.
        # (Historical note: an earlier revision saved _cancel_event/_pause_event
        # here for restore-in-finally, but that restore was never implemented.
        # The save was dead code — removed per TD-115 §2.0.5 ③ 不做兼容.)

        # Start window background monitor if wait_when_background is enabled.
        # The monitor runs in a daemon thread and polls device.is_foreground().
        # On window losing foreground: engine.pause() + WS notify (paused).
        # On window regaining foreground: engine.resume() + WS notify (running).
        # On timeout: engine.cancel() + WS notify (failure).
        monitor = None
        if wait_when_background and wait_when_background.get("enabled"):
            try:
                from platforms.windows.window_monitor import WindowBackgroundMonitor
                monitor = WindowBackgroundMonitor(
                    device=device,
                    engine=engine,
                    timeout=float(wait_when_background.get("timeout_seconds", 1800)),
                    interval=float(wait_when_background.get("check_interval_ms", 500)) / 1000.0,
                    on_pause=(lambda: on_wait_status("task.progress", {
                        "status": "paused",
                        "reason": "window_background",
                        "message": "窗口在后台，已暂停 — 请恢复窗口前台以继续",
                    }) if on_wait_status else None),
                    on_resume=(lambda: on_wait_status("task.progress", {
                        "status": "running",
                        "message": "窗口恢复前台，继续执行",
                    }) if on_wait_status else None),
                    on_timeout=(lambda: on_wait_status("task.result", {
                        "success": False,
                        "error_msg": "窗口后台等待超时",
                    }) if on_wait_status else None),
                )
                monitor.start()
            except Exception as exc:
                logger.warning(
                    "execute_pipeline: WindowBackgroundMonitor init failed "
                    "(continuing without monitor): %s", exc,
                )
                monitor = None

        try:
            # Task 1.1 (B7 重试单节点, P0-1): forward start_step_index +
            # previous_results so engine skips the first N nodes and re-runs
            # only the failed node + downstream. Default 0/None = full run.
            result = engine.execute(
                start_step_index=start_step_index,
                previous_results=previous_results,
            )
        except HumanTakeoverError as exc:
            # N192 A7 P3 + N193 Task 5.3: 显式捕获 HumanTakeoverError, 包装为
            # PipelineResult 而非让异常上抛. 当 automated recovery 耗尽,
            # recovery_manager 抛 HumanTakeoverError 中断执行流时, orchestrator
            # 应返回结构化失败结果 (含 error_code + node_id), 让 backend / 前端
            # 能展示"需人工接管"并定位触发节点, 而非收到 500 错误.
            # N193 Task 5.3: 从异常取 node_id (recovery_manager 抛异常时传入),
            # 让 AI 诊断时能定位是哪个节点触发了人工接管.
            logger.error("[ORCHESTRATOR] 人工接管触发: %s", exc)
            result = fail_result(
                error_msg=f"人工接管: {exc}",
                error_code=NodeErrorCode.UNKNOWN,
                node_id=exc.node_id,
                elapsed_time=time.monotonic() - start_time,
            )
        finally:
            if monitor:
                monitor.stop()

        # Attach the structured JSONL log path to the result so upstream
        # (handler → WS → backend) can read it for LLM diagnosis
        # (spec 阶段 3.4). engine.structured_log_path is the absolute path
        # to <debug_dir>/structured/<execution_id>.jsonl on the agent host.
        with contextlib.suppress(AttributeError):
            result.structured_log_path = engine.structured_log_path

        elapsed = time.monotonic() - start_time

        # Debug-mode LLM diagnosis on pipeline failure (§4.8.2):
        # When the pipeline fails in debug mode and an LLM client is
        # available, ask the LLM to diagnose the root cause before
        # surfacing the error to the user. The diagnosis is attached to
        # result.data["llm_diagnosis"] (non-blocking — LLM failure
        # leaves the original result unchanged).
        if (not result.success and llm_client is not None
                and effective_debug_mode):
            diagnosis = self._llm_diagnose_pipeline_failure(
                llm_client=llm_client,
                result=result,
                pipeline_json=pipeline_json,
                structured_log_path=getattr(result, "structured_log_path", ""),
            )
            if diagnosis is not None:
                # Attach diagnosis to result.data without overwriting
                # the original error_msg (diagnosis is supplementary).
                if result.data is None:
                    result.data = {}
                result.data["llm_diagnosis"] = diagnosis
                logger.info(
                    "execute_pipeline: LLM diagnosis attached — diagnosis=%r, fix=%r",
                    diagnosis.get("diagnosis", "")[:100],
                    diagnosis.get("suggested_fix", "")[:100],
                )

        # Map PipelineState back to TaskState
        # N193 Task 5.3: 用 getattr 兜底, 因为 HumanTakeoverError 捕获路径
        # 返回的是 fail_result (AutoResult), 没有 state 属性 (PipelineResult 才有).
        # 此时 result.success=False, 应映射到 TaskState.FAILED.
        result_state = getattr(result, "state", None)
        if result_state == PipelineState.COMPLETED:
            self._state = TaskState.COMPLETED
        elif result_state == PipelineState.CANCELLED:
            self._state = TaskState.CANCELLED
        else:
            self._state = TaskState.FAILED

        # P0-4 fix: emit task.complete / task.failed / task.cancelled trace
        # event so AI can correlate task outcome with node events in the
        # same JSONL. Includes step count + first failed node for fast triage.
        # N193 Task 5.3: 用 getattr 兜底 step_results, 因为 HumanTakeoverError
        # 捕获路径返回的 fail_result (AutoResult) 没有 step_results 字段.
        elapsed_ms_p0 = elapsed * 1000
        first_failed_node_id_p0 = ""
        first_failed_node_type_p0 = ""
        first_failed_error_code_p0 = ""
        _step_results = getattr(result, "step_results", []) or []
        for _step in _step_results:
            if not getattr(_step, "success", True):
                first_failed_node_id_p0 = getattr(_step, "node_id", "")
                first_failed_node_type_p0 = getattr(_step, "node_type", "")
                first_failed_error_code_p0 = str(getattr(_step, "error_code", "") or "")
                break
        end_event_extra: dict[str, Any] = {
            "step_count": len(_step_results),
            "first_failed_node_id": first_failed_node_id_p0,
            "first_failed_node_type": first_failed_node_type_p0,
        }
        if first_failed_error_code_p0:
            end_event_extra["first_failed_error_code"] = first_failed_error_code_p0
        if result_state == PipelineState.COMPLETED:
            self._emit_orchestrator_event(
                event="orchestrator.task.complete",
                task_state=TaskState.COMPLETED.value,
                success=True,
                elapsed_ms=elapsed_ms_p0,
                device_id=getattr(device, "device_id", "") or "",
                pipeline_name=pipeline_json.get("metadata", {}).get("pipeline_name", "") if isinstance(pipeline_json, dict) else "",
                extra=end_event_extra,
            )
        elif result_state == PipelineState.CANCELLED:
            self._emit_orchestrator_event(
                event="orchestrator.task.cancelled",
                task_state=TaskState.CANCELLED.value,
                success=False,
                elapsed_ms=elapsed_ms_p0,
                device_id=getattr(device, "device_id", "") or "",
                pipeline_name=pipeline_json.get("metadata", {}).get("pipeline_name", "") if isinstance(pipeline_json, dict) else "",
                error_msg=result.error_msg or "",
                extra={**end_event_extra, "cancel_reason": "pipeline_cancelled"},
            )
        else:
            self._emit_orchestrator_event(
                event="orchestrator.task.failed",
                task_state=TaskState.FAILED.value,
                success=False,
                elapsed_ms=elapsed_ms_p0,
                device_id=getattr(device, "device_id", "") or "",
                pipeline_name=pipeline_json.get("metadata", {}).get("pipeline_name", "") if isinstance(pipeline_json, dict) else "",
                error_msg=result.error_msg or "",
                error_code=first_failed_error_code_p0,
                extra=end_event_extra,
            )
        self._clear_orchestrator_logger()

        # Fire callbacks
        if result.success and self._on_task_complete:
            self._on_task_complete(result.data)
        elif not result.success and self._on_task_failed:
            self._on_task_failed(result)

        logger.info(
            "[ORCHESTRATOR] Pipeline 执行完成: state=%s, success=%s, steps=%d, error_msg=%s, 耗时=%.3fs",
            # N193 Task 5.3: 用 getattr 兜底 state / step_results, 因为
            # HumanTakeoverError 捕获路径返回的 fail_result (AutoResult) 无此字段.
            getattr(result_state, "value", "unknown"),
            result.success,
            len(_step_results),
            result.error_msg or "",
            elapsed,
        )
        return result

    def _llm_diagnose_pipeline_failure(
        self,
        llm_client,
        result: AutoResult,
        pipeline_json: dict[str, Any],
        structured_log_path: str,
    ) -> dict[str, Any] | None:
        """Ask the LLM to diagnose a failed pipeline run.

        Per project_rules.md §4.8.2: when debug_mode=True and the
        pipeline fails, the agent must consult the LLM for a diagnosis
        before notifying the user. This method builds a structured error
        context from the pipeline result + structured log path and
        delegates to ``AgentLLMClient.diagnose_failure()``.

        Non-blocking: on any error (LLM unavailable, network, malformed
        response), returns ``None`` so the caller falls back to the
        original error message unchanged.

        Args:
            llm_client: AgentLLMClient instance (already constructed).
            result: Failed AutoResult from engine.execute().
            pipeline_json: The pipeline definition that was executed.
            structured_log_path: Path to the JSONL structured log
                (may be empty if engine didn't generate one).

        Returns:
            Diagnosis dict ``{"diagnosis": str, "suggested_fix": str,
            "raw_reply": str, "model": str}`` on success, or ``None``
            on failure (LLM unavailable / network error / empty reply).
        """
        # Build error context from the pipeline result. Include the
        # first failing step's error (most actionable for the LLM) plus
        # the overall pipeline error_msg.
        # spec 阶段 4 — 任务 4.3: 提取第一个失败步骤的完整元数据
        # (node_id/node_type/error_code), 不再只传 error_msg 字符串.
        # N193 Task 5.3: 用 getattr 兜底 step_results, 因为 fail_result
        # (AutoResult) 没有 step_results 字段 (PipelineResult 才有).
        _step_results = getattr(result, "step_results", []) or []
        first_failed_step_error = ""
        first_failed_node_id = ""
        first_failed_node_type = ""
        first_failed_error_code = ""
        for step in _step_results:
            # step_results is a list of AutoResult dataclass instances.
            # AutoResult now carries node_id/node_type/error_code (任务 1.1).
            if not getattr(step, "success", True):
                first_failed_step_error = getattr(step, "error_msg", "")
                first_failed_node_id = getattr(step, "node_id", "")
                first_failed_node_type = getattr(step, "node_type", "")
                first_failed_error_code = getattr(step, "error_code", "")
                break

        # spec 阶段 4 — 任务 4.3: 读取 JSONL 文件内容 (截断到最后 8000 字符).
        # 让 LLM 能看到完整的结构化执行日志, 而非只传路径让 LLM 自己猜.
        structured_log_content = ""
        if structured_log_path and os.path.exists(structured_log_path):
            try:
                with open(structured_log_path, encoding="utf-8") as f:
                    content = f.read()
                # 截断到最后 8000 字符 (最近的执行记录最有诊断价值)
                structured_log_content = content[-8000:] if len(content) > 8000 else content
            except Exception as exc:
                logger.warning(
                    "_llm_diagnose_pipeline_failure: 读取 JSONL 失败: %s",
                    exc,
                )

        error_context = {
            "node_id": first_failed_node_id,
            "node_type": first_failed_node_type or "pipeline",
            "error_msg": result.error_msg or first_failed_step_error,
            "error_code": first_failed_error_code,
            "pipeline_name": pipeline_json.get("metadata", {}).get(
                "pipeline_name", "",
            ) if isinstance(pipeline_json, dict) else "",
            "structured_log_path": structured_log_path,
            "structured_log_content": structured_log_content,
            "extra": {
                "total_steps": len(_step_results),
                "first_failed_step_error": first_failed_step_error,
            },
        }

        try:
            diagnosis = llm_client.diagnose_failure(error_context)
        except Exception as exc:
            logger.warning(
                "_llm_diagnose_pipeline_failure: diagnose_failure raised: %s",
                exc,
            )
            return None

        # diagnose_failure() never raises but may return an error dict
        # when the LLM is unavailable / misconfigured. In that case the
        # diagnosis is empty — return None so caller skips attaching.
        if diagnosis.get("error") and not diagnosis.get("diagnosis"):
            logger.info(
                "_llm_diagnose_pipeline_failure: no diagnosis (reason=%s)",
                diagnosis.get("error"),
            )
            return None

        return diagnosis

    def _execute_recovery_action(self, device, action: dict) -> bool:
        """Execute a transition action from interface_states.yaml.

        Handles template_match / key_press / click / swipe / wait
        (recovery-design.md §5.3 Step 5). Template paths are resolved via
        resolve_resource_path — find_template does not resolve relative
        paths, so passing one would silently fail to load the template.

        Returns:
            True — action executed (does NOT mean UI changed; caller
                   verifies with a screenshot)
            False — action failed (e.g. template_match not found)
        """
        action_kind = action.get("node_type") or action.get("type")
        if action_kind == "template_match":
            template = action["template"]
            threshold = action.get("threshold", 0.8)
            roi = action.get("roi")
            # yaml roi is a [x, y, w, h] list (§4.1); find_template expects
            # a dict {"x", "y", "w", "h"}.
            roi_dict = None
            if roi and isinstance(roi, list) and len(roi) == 4:
                roi_dict = {"x": roi[0], "y": roi[1], "w": roi[2], "h": roi[3]}
            from engine.resource_resolver import resolve_resource_path

            resolved_template = resolve_resource_path(template)
            if resolved_template is None:
                logger.warning("recovery action template 路径解析失败: %s", template)
                return False
            match_result = self._image_processor.find_template(
                device.capture_screen(), resolved_template,
                roi=roi_dict, threshold=threshold,
            )
            if match_result and action.get("click_on_match", True):
                device.click(match_result["x"], match_result["y"])
            return match_result is not None
        elif action_kind == "key_press":
            device.key_press(action["key"])
            return True
        elif action_kind == "click":
            device.click(action["x"], action["y"])
            return True
        elif action_kind == "swipe":
            device.swipe(
                action["x1"], action["y1"], action["x2"], action["y2"],
                duration=action.get("duration", 500),
            )
            return True
        elif action_kind == "wait":
            time.sleep(action["duration"] / 1000.0)
            return True
        else:
            logger.warning("未知 recovery action 类型: %s", action_kind)
            return False
