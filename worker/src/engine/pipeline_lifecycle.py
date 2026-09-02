"""PipelineEngine：Pipeline 通用执行器"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from typing import Any

import engine.nodes  # noqa: F401  (side-effect import: populates registry)
from core.result import AutoResult
from engine.context import PipelineContext, PipelineState, StepState
from engine.parser import PipelineGraph, PipelineParser
from engine.validator import PipelineValidator, ValidationError
from utils.structured_logger import (
    StructuredLogger,
)

logger = logging.getLogger(__name__)


class PipelineSetupMixin:
    """PipelineEngine mixin — see pipeline_engine.py for full class (s35 split)."""

    def __init__(self):
        self._graph: PipelineGraph | None = None
        self._context: PipelineContext | None = None
        self._state: PipelineState = PipelineState.PENDING
        self._cancel_event = threading.Event()
        self._pause_event = threading.Event()
        # TD-353: 步骤级超时取消事件 (与 _cancel_event 分离)
        # _cancel_event: 用户显式取消 pipeline (pipeline 级)
        # _step_cancel_event: 步骤超时 (步骤级, 仅影响当前后台线程,
        # 不终止 pipeline). 超时后在 execute() 中设置, 后台线程在
        # 关键检查点 (repeat/retry/delay) 检测到此标志后主动退出.
        self._step_cancel_event = threading.Event()
        self._step_results: list[AutoResult] = []
        self._on_step_complete: Callable[[str, AutoResult], None] | None = None
        self._on_error: Callable[[str, Exception], None] | None = None
        self._max_iterations: int = 10000
        self._current_node_id: str = ""
        # Structured JSONL logger for this execution (spec 阶段 3.1).
        # Lazily initialized in execute() per run so each execute() call
        # gets a fresh execution_id and JSONL file.
        self._structured_logger: StructuredLogger | None = None
        self._execution_id: str = ""
        # P0-4 fix (AI 可调试性, 2026-07-27): optional execution_id override
        # set by load(execution_id=...). When non-empty, execute() uses it
        # instead of new_execution_id() so orchestrator-level trace events
        # (task.start/complete/...) and engine-level node events share the
        # same JSONL file. Reset to "" after each execute() call.
        self._execution_id_override: str = ""
        # Absolute path to the JSONL file for this execution (spec 阶段 3.4).
        # Captured before the try block so it survives the finally block's
        # logger.close(). Read via the structured_log_path property.
        self._last_structured_log_path: str = ""
        # Cross-step chain for JSONL diagnostics (spec 阶段 3.2 — 任务 1.4):
        # tracks the previous node's id/type/end_time so the current node's
        # JSONL event can include previous_node_id / previous_node_type /
        # inter_node_gap_ms. Reset at the start of each execute() call.
        self._previous_node_id: str = ""
        self._previous_node_type: str = ""
        self._previous_node_end_time: float = 0.0
        # spec 阶段 3 — 任务 3.3: InterfaceRecoveryManager 注入入口.
        # None 时失败分支直接返回 FAILED (向后兼容). 由调用方
        # (orchestrator / 上层) 通过 set_recovery_manager() 注入.
        self._recovery_manager: Any = None
        # spec 阶段 3 — 任务 3.3: per-node 恢复尝试计数 + 上次 path.
        # 避免同一节点无限循环恢复 (max=2, 第二次带 exclude_edges 换路径).
        self._recovery_attempts_per_node: dict[str, int] = {}
        self._last_recovery_path: dict[str, list[str]] = {}
        # spec 阶段 3 — 任务 3.2: Verifier 注入入口 (post_verify 强验证).
        # None 时 post_verify 配置被静默跳过 (向后兼容). 由调用方
        # (orchestrator) 通过 set_verifier() 注入, 复用 core.verify.Verifier.
        self._verifier: Any = None
        # spec §4.2.3 — 任务 1.6 依赖注入: WaitFreezes 实例 (ClickNode
        # 默认轻量竞态防护用). None 时 engine.load() 会自动构造一个
        # 共享实例注入 context.wait_freezes; ClickNode 在 context.wait_freezes
        # 也为 None 时回退到 per-call 新建 (向后兼容单测). 由调用方
        # 通过 set_wait_freezes() 覆盖可注入自定义配置 (ROI 等).
        self._wait_freezes: Any = None

    def set_recovery_manager(self, manager: Any) -> None:
        """注入 InterfaceRecoveryManager (spec 阶段 3 — 任务 3.3).

        Args:
            manager: InterfaceRecoveryManager 实例. 传 None 关闭恢复机制.
        """
        self._recovery_manager = manager
        logger.info("PipelineEngine 已注入 recovery_manager: %s", type(manager).__name__)

    def set_verifier(self, verifier: Any) -> None:
        """注入 Verifier 实例 (spec 阶段 3 — 任务 3.2).

        用于在节点成功后执行 post_verify 强验证. 注入的 Verifier 应
        复用 core.verify.Verifier (支持 6 种验证类型).

        Args:
            verifier: Verifier 实例 (duck-typed, 需实现 verify(dict) -> AutoResult).
                      传 None 关闭 post_verify 机制.
        """
        self._verifier = verifier
        logger.info("PipelineEngine 已注入 verifier: %s", type(verifier).__name__)

    def set_wait_freezes(self, wait_freezes: Any) -> None:
        """注入 WaitFreezes 实例 (spec §4.2.3 — 任务 1.6 依赖注入).

        用于 ClickNode 默认轻量竞态防护 (wait_for_change_lightweight).
        注入的实例会写到 context.wait_freezes 供所有 ClickNode 复用,
        避免每次 click 都新建 WaitFreezes. 传 None 关闭机制 (ClickNode
        回退到 per-call 新建).

        Args:
            wait_freezes: WaitFreezes 实例 (duck-typed, 需实现
                          wait_for_change_lightweight(capture_fn, timeout, ...)).
                          传 None 让 engine.load() 自动构造默认实例.
        """
        self._wait_freezes = wait_freezes
        logger.info("PipelineEngine 已注入 wait_freezes: %s", type(wait_freezes).__name__)

    def _build_previous_node_chain(self) -> list[dict]:
        """构造 previous_node_chain 供 infer_expected_state 回溯 (spec §3.3).

        从 self._step_results 反向取已成功节点 (id + config).
        index 0 = 最早成功节点, 末尾 = 最近成功节点.
        """
        if not self._graph or not self._step_results:
            return []
        chain: list[dict] = []
        # _step_results 是按执行顺序追加的, 但只关心成功节点.
        # node_id 在 AutoResult 中由 engine._execute_node_step 自动填充
        # (spec 阶段 2 — 任务 1.2). 找回对应 node_config.
        for r in self._step_results:
            if not r.success:
                continue
            node_id = r.node_id
            if not node_id:
                continue
            # 从 graph 查 node_config
            node = self._graph.nodes.get(node_id) if hasattr(self._graph, "nodes") else None
            chain.append({
                "id": node_id,
                "config": node.config if node else {},
            })
        return chain

    @property
    def state(self) -> PipelineState:
        """获取当前状态"""
        return self._state

    @property
    def current_node_id(self) -> str:
        """获取当前执行的节点 ID"""
        return self._current_node_id

    @property
    def context(self) -> PipelineContext | None:
        """获取执行上下文"""
        return self._context

    @property
    def execution_id(self) -> str:
        """获取当前/最近一次 execute() 的 execution_id (spec 阶段 3.1)."""
        return self._execution_id

    @property
    def structured_log_path(self) -> str:
        """获取最近一次 execute() 的 JSONL 文件绝对路径 (spec 阶段 3.4).

        Returns:
            绝对路径字符串，或空字符串（execute() 未执行或 logger 初始化失败）。
        """
        return self._last_structured_log_path

    def set_callbacks(
        self,
        on_step_complete: Callable[[str, AutoResult], None] | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
    ) -> None:
        """设置回调函数

        Args:
            on_step_complete: 步骤完成回调 (node_id, result)
            on_error: 错误回调 (node_id, exception)
        """
        self._on_step_complete = on_step_complete
        self._on_error = on_error

    def set_max_iterations(self, max_iterations: int) -> None:
        """Set maximum iteration count for loop detection

        Args:
            max_iterations: Maximum iterations before aborting
        """
        self._max_iterations = max_iterations

    def set_device(self, device) -> None:
        """Set (or update) the device instance for pipeline execution.

        This device will be injected into PipelineContext so that all
        nodes (template_match, click, swipe, etc.) can access it via
        context.device.

        Args:
            device: A BaseDevice subclass instance (WindowsDevice, ADBDevice, etc.)
        """
        self._device = device
        if self._context is not None:
            self._context.device = device
        logger.info("PipelineEngine device set: %s", getattr(device, 'device_id', device))

    def load(self, pipeline_json: dict, device=None,
             display_context=None, coord_transformer=None,
             monitor_manager=None,
             debug_mode: bool = False, debug_dir: str = "./debug",
             llm_client=None,
             coord_system: str = "",
             execution_id: str = "",
             recovery_manager: Any = None,
             max_recovery_retries: int = 0) -> None:
        """Load Pipeline JSON configuration

        Args:
            pipeline_json: Pipeline configuration dict
            device: Optional device instance to inject into PipelineContext
                    (nodes access it via context.device for screenshot/click/etc.)
            display_context: Optional RuntimeDisplayContext instance (built by
                    orchestrator from the bound window's hwnd/DPI/resolution).
                    When None, nodes fall back to raw-pixel coordinates.
            coord_transformer: Optional CoordinateTransformer instance (built by
                    orchestrator when pipeline_json.metadata.original_base_res
                    is present). When None, nodes skip DPI/resolution scaling.
            monitor_manager: Optional MonitorManager instance (set by
                    orchestrator). Used by monitor PipelineNode to invoke
                    popup_handler.check_and_handle(). When None, monitor node
                    falls back to mock behavior.
            debug_mode: When True, template_match and similar nodes write
                    annotated debug PNGs to debug_dir. Defaults to False.
            debug_dir: Debug image output root. Defaults to "./debug".
            llm_client: Optional WorkerLlmClient instance (set by orchestrator
                    from WorkerConfig). Used by template_match and similar
                    nodes for debug-mode LLM auto-heal diagnosis per
                    project_rules.md §4.8.2. When None, nodes fall back
                    to the original error without LLM diagnosis.
            coord_system: N191 §10.7 P0-1 (2026-07-27). 坐标系标签
                    ("logical" / "physical" / "")。由 orchestrator 根据
                    transformer 类型注入, 用于 publish_match_pos 自动给
                    发布的 pos dict 加 coord_system 字段, 让下游节点 /
                    structured_logger 知道当前流转的是哪个坐标系。
                    空字符串表示未注入 (老路径/测试兼容)。
            execution_id: P0-4 fix (AI 可调试性, 2026-07-27). 可选的
                    execution_id, 由 orchestrator 生成并传入, 让 orchestrator
                    级 trace 事件 (task.start/complete/failed/...) 与 engine
                    级 node 事件写入同一个 JSONL 文件。空字符串时 engine
                    在 execute() 内部自动 new_execution_id() (向后兼容)。
            recovery_manager: S2-2.7 (2026-08-17). Optional
                    InterfaceRecoveryManager instance (recovery-design.md
                    §5.2 Step 4). Injected by orchestrator when
                    interface_states.yaml exists. When None, node failure
                    branches skip UI recovery (backward compatible).
            max_recovery_retries: S2-2.7 (2026-08-17). Per-node max UI
                    recovery attempts for engine._attempt_recovery.
                    Effective only when recovery_manager is not None.
        """
        self._graph = PipelineParser.parse_dict(pipeline_json)
        self._context = PipelineContext(
            device=device,
            display_context=display_context,
            coord_transformer=coord_transformer,
            coord_system=coord_system,
            monitor_manager=monitor_manager,
            debug_mode=debug_mode,
            debug_dir=debug_dir,
            pipeline_snapshot=pipeline_json,
            llm_client=llm_client,
        )
        # S2-2.7 (2026-08-17): set pipeline_name from pipeline metadata.
        # recovery-design.md §5.2 注 2: PipelineContext.pipeline_name exists
        # but load() never set it — recover() archive dirs would get empty
        # pipeline_name. Best-effort, no-op when metadata missing.
        meta = pipeline_json.get("metadata", {}) if isinstance(pipeline_json, dict) else {}
        pipeline_name = meta.get("pipeline_name", "") if isinstance(meta, dict) else ""
        self._context.pipeline_name = pipeline_name
        # S2-2.7 (2026-08-17): wire recovery manager + retry budget.
        self._recovery_manager = recovery_manager
        self._max_recovery_retries = max(1, max_recovery_retries) if recovery_manager else 0
        # P0-4 fix: store execution_id override for execute() to use.
        self._execution_id_override = execution_id or ""
        # spec §4.2.3 — 任务 1.6 依赖注入: 默认构造一个共享 WaitFreezes
        # 实例注入 context.wait_freezes (除非调用方已通过 set_wait_freezes
        # 注入了自定义实例). capture_fn 默认用 device.capture_screen
        # (若 device 提供). 详见 set_wait_freezes() / context.py.
        if self._wait_freezes is None:
            from core.wait_freezes import WaitFreezes

            self._wait_freezes = WaitFreezes()
        self._context.wait_freezes = self._wait_freezes
        if device is not None and hasattr(device, "capture_screen"):
            self._context.capture_fn = device.capture_screen
        # Cache runtime services for re-injection in execute() when context
        # is restored from serialized data (checkpoint resume).
        self._display_context = display_context
        self._coord_transformer = coord_transformer
        self._monitor_manager = monitor_manager
        # N191 §10.10 决策点 6 (AI 可调试性, 2026-07-27):
        # 缓存 device_type + transformer_id, 用于 log_node_event 和
        # emit_coord_trace。AI 跨设备对比时按 device_type 分组 (D3)。
        self._device_type = self._infer_device_type(device)
        self._transformer_id = self._build_transformer_id(coord_transformer, coord_system)
        self._llm_client = llm_client
        self._state = PipelineState.PENDING
        self._cancel_event.clear()
        self._pause_event.clear()
        self._step_results.clear()
        self._current_node_id = ""
        logger.info("Pipeline 已加载，入口节点: %s，节点数: %d, device=%s, transformer=%s, monitor=%s, llm=%s",
                     self._graph.entry_node, len(self._graph.nodes),
                     getattr(device, 'device_id', 'None') if device else 'None',
                     'yes' if coord_transformer else 'none',
                     'yes' if monitor_manager else 'none',
                     'yes' if llm_client else 'none')

    @staticmethod
    def _infer_device_type(device: Any) -> str:
        """Infer device_type string for log_node_event / emit_coord_trace.

        Returns ``"windows"`` / ``"adb"`` / ``""`` (unknown). AI 跨设备
        对比时按此字段分组。

        判定规则按 class name 而非 isinstance, 避免 engine 层 import
        平台特定模块 (devices.base 已抽象, platforms.windows 是 Windows 专属)。
        """
        if device is None:
            return ""
        cls_name = type(device).__name__
        if "Windows" in cls_name:
            return "windows"
        if "ADB" in cls_name:
            return "adb"
        return ""

    @staticmethod
    def _build_transformer_id(coord_transformer: Any, coord_system: str) -> str:
        """Build a stable transformer_id string for log_node_event.

        格式: ``"<type>_<base_res>_<extra>"``, 如:
        - ``"win_1920x1080_dpi2.0"`` (Windows CoordinateTransformer)
        - ``"adb_1920x1080_to_2560x1440"`` (ADBCoordinateTransformer)
        - ``""`` (legacy, 无 transformer)

        AI 按此字段分组对比同一 transformer 的所有节点事件。
        """
        if coord_transformer is None:
            return ""
        # 优先调 transformer 自带的 get_id() (若存在), 否则按类名 + 属性拼。
        get_id = getattr(coord_transformer, "get_id", None)
        if callable(get_id):
            try:
                tid = get_id()
                if tid:
                    return str(tid)
            except Exception:
                logger.debug("coord_transformer.get_id() failed, falling back to class-name id", exc_info=True)
        cls_name = type(coord_transformer).__name__
        # 兜底: 用类名 + coord_system, 信息密度有限但保证有标识。
        if "ADB" in cls_name:
            return f"adb_{coord_system or 'unknown'}"
        if "Windows" in cls_name or "CoordinateTransformer" in cls_name:
            return f"win_{coord_system or 'unknown'}"
        return cls_name

    def load_from_json(self, json_str: str) -> None:
        """从 JSON 字符串加载 Pipeline

        Args:
            json_str: Pipeline JSON 字符串
        """
        data = json.loads(json_str)
        self.load(data)

    def validate(self) -> list[ValidationError]:
        """校验当前加载的 Pipeline

        Returns:
            校验错误列表

        Raises:
            RuntimeError: Pipeline 未加载
        """
        if self._graph is None:
            raise RuntimeError("Pipeline 未加载，请先调用 load()")
        return PipelineValidator.validate(self._graph)

    def pause(self) -> None:
        """暂停 Pipeline 执行"""
        if self._state == PipelineState.RUNNING:
            self._pause_event.set()
            self._state = PipelineState.PAUSED
            logger.info("Pipeline 已暂停于节点: %s", self._current_node_id)

    def resume(self) -> None:
        """恢复 Pipeline 执行"""
        if self._state == PipelineState.PAUSED:
            self._pause_event.clear()
            self._state = PipelineState.RUNNING
            logger.info("Pipeline 已恢复执行")

    def cancel(self) -> None:
        """取消 Pipeline 执行"""
        self._cancel_event.set()
        self._pause_event.clear()
        self._state = PipelineState.CANCELLED
        logger.info("Pipeline 已取消")

    def skip_step(self, step_index: int) -> None:
        """跳过指定步骤

        Args:
            step_index: 步骤索引
        """
        if self._context is None:
            return
        if step_index < len(self._context.step_states):
            snapshot = self._context.step_states[step_index]
            snapshot.state = StepState.SKIPPED
            logger.info("步骤 %d (节点: %s) 已标记为跳过", step_index, snapshot.node_id)

    def get_current_state(self) -> PipelineState:
        """获取当前 Pipeline 状态

        Returns:
            当前状态
        """
        return self._state

    def get_execution_context(self) -> dict[str, Any] | None:
        """获取可序列化的执行上下文快照

        Returns:
            序列化后的上下文字典
        """
        if self._context is None:
            return None
        return self._context.serialize()

    def restore_context(self, data: dict[str, Any]) -> None:
        """恢复执行上下文（断点续跑）

        Args:
            data: serialize() 输出的字典
        """
        self._context = PipelineContext.restore(data)
        logger.info("已恢复执行上下文，当前步骤索引: %d", self._context.current_step_index)
