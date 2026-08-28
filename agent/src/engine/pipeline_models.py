from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.result import AutoResult
from engine.context import PipelineState


@dataclass
class PipelineResult:
    """Pipeline 执行结果

    Attributes:
        success: 是否成功
        state: 最终 Pipeline 状态
        data: 执行数据
        error_msg: 错误信息
        elapsed_time: 总耗时
        step_results: 各步骤执行结果列表
        structured_log_path: 本次执行的 JSONL 结构化日志文件绝对路径
            (spec 阶段 3.4 — 让 backend 能读取 agent 端的结构化日志做 LLM 诊断)。
            空字符串表示未生成（execute() 未执行或 structured_logger 初始化失败）。
    """

    success: bool
    state: PipelineState
    data: Any = None
    error_msg: str = ""
    elapsed_time: float = 0.0
    step_results: list[AutoResult] = field(default_factory=list)
    structured_log_path: str = ""

    def __bool__(self) -> bool:
        return self.success
