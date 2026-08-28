"""PipelineContext：Pipeline 执行上下文，支持序列化与断点续跑"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from devices.base import BaseDevice


class StepState(Enum):
    """步骤执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineState(Enum):
    """Pipeline 整体运行状态"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class StepSnapshot:
    """单个步骤的执行快照

    Attributes:
        step_index: 步骤索引
        node_id: 节点 ID
        node_type: 节点类型
        state: 步骤状态
        result_data: 执行结果数据
        error_msg: 错误信息
        elapsed_time: 执行耗时
    """

    step_index: int
    node_id: str
    node_type: str
    state: StepState = StepState.PENDING
    result_data: Any = None
    error_msg: str = ""
    elapsed_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "step_index": self.step_index,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "state": self.state.value,
            "result_data": self.result_data,
            "error_msg": self.error_msg,
            "elapsed_time": self.elapsed_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepSnapshot:
        """从字典恢复"""
        return cls(
            step_index=data["step_index"],
            node_id=data["node_id"],
            node_type=data["node_type"],
            state=StepState(data.get("state", "pending")),
            result_data=data.get("result_data"),
            error_msg=data.get("error_msg", ""),
            elapsed_time=data.get("elapsed_time", 0.0),
        )


@dataclass
class PipelineContext:
    """Pipeline 执行上下文

    维护 Pipeline 执行过程中的所有状态，支持序列化/反序列化以实现断点续跑。

    Attributes:
        device: 当前绑定的设备实例（节点通过此属性调用截图/点击等操作）
        display_context: RuntimeDisplayContext 实例（由 orchestrator 注入，
            提供 hwnd/DPI/客户区分辨率等运行时显示参数）。运行时对象，
            不参与序列化 — restore 后为 None，需调用方重新注入。
        coord_transformer: CoordinateTransformer 实例（由 orchestrator 注入，
            提供 ROI/模板的 DPI+分辨率感知缩放）。运行时对象，不参与序列化
            — restore 后为 None，需调用方重新注入。
        pipeline_name: Pipeline 名称
        current_step_index: 当前步骤索引
        step_states: 所有步骤的执行状态列表
        variables: 全局变量存储（步骤间共享数据）
        pipeline_snapshot: Pipeline 定义快照（用于恢复）
        execution_history: 执行历史记录
    """

    device: BaseDevice | None = None
    # Runtime-only display services (set by orchestrator, not serialized).
    # Typed as Any to keep the engine layer platform-agnostic — the concrete
    # types (RuntimeDisplayContext / CoordinateTransformer) live in utils/ and
    # import platform-specific code. Nodes duck-type these via hasattr checks.
    display_context: Any | None = None
    coord_transformer: Any | None = None
    # N191 §10.7 (架构层归一化, 2026-07-27): 当前 context 下 publish_match_pos
    # / resolve_target 流转的坐标系标签。由 orchestrator 在 build_transformer
    # 后注入, 用于:
    #   1. publish_match_pos 自动写入发布 dict, 下游 set_variable / logger
    #      可读到坐标系信息 (N191 §10.7 P0-1 修复)
    #   2. structured_logger JSONL 记录 coord_system 字段 (P1 后续)
    #   3. resolve_target 校验 target 变量 coord_system 是否匹配 (P1 后续)
    # 取值: "logical" (Windows + transformer) / "physical" (ADB / Windows legacy) /
    #       "" (未注入, 老路径兼容)
    coord_system: str = ""
    # Runtime-only monitor manager (set by orchestrator, not serialized).
    # Used by monitor PipelineNode to invoke popup_handler.check_and_handle().
    # None in tests / local mode — nodes must fall back to mock behavior.
    monitor_manager: Any | None = None
    # Runtime-only LLM client for debug-mode auto-heal diagnosis (set by
    # orchestrator from AgentConfig, not serialized). When debug_mode=True
    # and a node exhausts local auto-heal (e.g. template_match tried all
    # screenshot methods), the node calls llm_client.diagnose_failure()
    # to get an LLM-suggested fix before surfacing the error to the user
    # (project_rules.md §4.8.2). None when agent has no server connection
    # or LLM is disabled — nodes must fall back to the original error.
    llm_client: Any | None = None
    # Runtime-only WaitFreezes instance for ClickNode default lightweight
    # race-condition protection (spec §4.2.3 — 任务 1.6 依赖注入). Set by
    # engine.load() alongside recovery_manager/verifier. None in tests —
    # ClickNode falls back to constructing WaitFreezes() per-call (backward
    # compat). Reusing a single instance avoids per-click allocation and
    # lets future WaitFreezes config (custom ROI etc.) be injected uniformly.
    wait_freezes: Any | None = None
    # Runtime-only capture_fn for wait_for_change_lightweight (spec §4.2.3).
    # Defaults to device.capture_screen when device is set. Decoupled from
    # device so tests can inject a deterministic frame source. None in
    # tests — ClickNode falls back to device.capture_screen.
    capture_fn: Any | None = None
    # N191 §10.10 决策点 5 (AI 可调试性, 2026-07-27):
    # Runtime-only StructuredLogger reference, set by PipelineEngine.load()
    # so publish_match_pos / resolve_target / device.click 等核心接口
    # 能通过 context.emit_coord_trace() 记坐标转换 trace。None in tests
    # — emit_coord_trace 是 no-op, 不阻塞 pipeline。
    structured_logger: Any | None = None
    # N191 §10.10 决策点 6: 缓存 device_type + transformer_id, 让
    # emit_coord_trace 转发时带上跨设备对比字段。由 PipelineEngine.load()
    # 推断后注入。
    device_type: str = ""
    transformer_id: str = ""
    # Runtime-only debug visualization toggle (set by orchestrator from
    # AgentConfig.debug_mode, not serialized). When True, template_match
    # and similar nodes write annotated debug PNGs to debug_dir.
    debug_mode: bool = False
    debug_dir: str = "./debug"
    pipeline_name: str = ""
    current_step_index: int = 0
    step_states: list[StepSnapshot] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    pipeline_snapshot: dict[str, Any] | None = None
    execution_history: list[dict[str, Any]] = field(default_factory=list)

    def set_variable(self, key: str, value: Any) -> None:
        """设置全局变量

        Args:
            key: 变量名
            value: 变量值
        """
        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        """获取全局变量

        Args:
            key: 变量名
            default: 默认值

        Returns:
            变量值
        """
        return self.variables.get(key, default)

    # ------------------------------------------------------------------
    # N191 §10.10 决策点 5 (AI 可调试性基础设施, 2026-07-27):
    # emit_coord_trace — publish_match_pos / resolve_target / device.click
    # 等核心接口通过本方法记坐标转换 trace。AI 调试时:
    #   grep "coord_transform" run.log | jq 'select(.node_id=="ocr_1")'
    # 4 条 AI 可调试性总原则之 1: 转换必观测。
    # ------------------------------------------------------------------
    def emit_coord_trace(
        self,
        *,
        node_id: str,
        step: str,
        raw: Any,
        converted: Any,
        formula: str,
        coord_system_in: str = "",
        coord_system_out: str = "",
        task_id: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Emit a coord_transform trace event (best-effort, no-op on failure).

        转发到 self.structured_logger.emit_coord_trace()。若 structured_logger
        为 None (测试/legacy 路径), 本方法是 no-op, 不阻塞 pipeline。

        Args:
            node_id: 节点 ID。
            step: 转换位置 (``"publish_match_pos"`` / ``"resolve_target"`` /
                ``"device_click"`` / ``"sub_image_to_full"`` 等)。
            raw: 转换前坐标 (dict / tuple / list / None)。
            converted: 转换后坐标, 同 raw。
            formula: 转换公式描述, 如 ``"logical = physical / dpi_scale(2.0)"``。
            coord_system_in: 输入坐标系标签 (``"physical"`` / ``"logical"`` /
                ``"base"`` / ``"sub_image"``)。
            coord_system_out: 输出坐标系标签。
            task_id: 任务 ID (可选)。
            extra: 额外字段 (如 roi_offset / dpi_scale)。

        自动从 context 取 device_type / transformer_id / execution_id,
        调用方不需要传这些跨设备字段。
        """
        logger_ref = self.structured_logger
        if logger_ref is None:
            return
        try:
            # A3 (spec 2026-07-30-debug-directory-restructure): trace_id 从
            # ContextVar 取 (HTTP 请求级, 全链路贯穿), 不再用 logger.execution_id
            # (那是 agent 内部 execution_id, 与 HTTP trace_id 是两套体系).
            from core.context_vars import get_current_user_trace_id
            logger_ref.emit_coord_trace(
                node_id=node_id,
                step=step,
                device_type=self.device_type or "",
                raw=raw,
                converted=converted,
                formula=formula,
                transformer_id=self.transformer_id or "",
                coord_system_in=coord_system_in,
                coord_system_out=coord_system_out,
                task_id=task_id,
                trace_id=get_current_user_trace_id(),
                extra=extra,
            )
        except Exception:
            # best-effort: trace 失败不能阻塞 pipeline。
            pass

    def record_step(
        self,
        node_id: str,
        node_type: str,
        state: StepState,
        result_data: Any = None,
        error_msg: str = "",
        elapsed_time: float = 0.0,
    ) -> None:
        """记录步骤执行结果

        Args:
            node_id: 节点 ID
            node_type: 节点类型
            state: 步骤状态
            result_data: 结果数据
            error_msg: 错误信息
            elapsed_time: 耗时
        """
        snapshot = StepSnapshot(
            step_index=self.current_step_index,
            node_id=node_id,
            node_type=node_type,
            state=state,
            result_data=result_data,
            error_msg=error_msg,
            elapsed_time=elapsed_time,
        )
        self.step_states.append(snapshot)
        self.execution_history.append({
            "step_index": self.current_step_index,
            "node_id": node_id,
            "node_type": node_type,
            "state": state.value,
        })

    def get_completed_step_ids(self) -> list[str]:
        """获取已完成的步骤节点 ID 列表

        Returns:
            已完成节点 ID 列表
        """
        return [
            s.node_id
            for s in self.step_states
            if s.state == StepState.COMPLETED
        ]

    def serialize(self) -> dict[str, Any]:
        """将上下文序列化为字典（用于断点续跑存储）

        Returns:
            可 JSON 序列化的字典
        """
        return {
            "pipeline_name": self.pipeline_name,
            "current_step_index": self.current_step_index,
            "step_states": [s.to_dict() for s in self.step_states],
            "variables": self.variables,
            "pipeline_snapshot": self.pipeline_snapshot,
            "execution_history": self.execution_history,
            "snapshot_time": time.time(),
        }

    @classmethod
    def restore(cls, data: dict[str, Any]) -> PipelineContext:
        """从字典恢复上下文（断点续跑）

        Args:
            data: serialize() 输出的字典

        Returns:
            PipelineContext 实例
        """
        ctx = cls(
            pipeline_name=data.get("pipeline_name", ""),
            current_step_index=data.get("current_step_index", 0),
            step_states=[
                StepSnapshot.from_dict(s)
                for s in data.get("step_states", [])
            ],
            variables=data.get("variables", {}),
            pipeline_snapshot=data.get("pipeline_snapshot"),
            execution_history=data.get("execution_history", []),
        )
        return ctx

    def reset(self) -> None:
        """重置上下文到初始状态"""
        self.current_step_index = 0
        self.step_states.clear()
        self.variables.clear()
        self.execution_history.clear()
