"""PipelineEngine：Pipeline 通用执行器"""

from __future__ import annotations

import logging

# Importing engine.nodes fires all @register_node decorators in engine/nodes/*
# via module-level side effects, populating PIPELINE_NODE_REGISTRY. Without
# this import the registry stays empty at runtime and PipelineParser rejects
# every node type ("使用了未知类型") — including template_match, ocr, click,
# etc. This is the C22 fix made complete: engine/nodes/__init__.py exists
# specifically to bundle these imports, but nothing in the production call
# chain (orchestrator → engine → parser) imported the package, so the
# registry was only populated in tests (which import node modules directly).
import engine.nodes  # noqa: F401  (side-effect import: populates registry)
from engine.context import PipelineState
from engine.pipeline_execution import PipelineExecutionMixin
from engine.pipeline_lifecycle import PipelineSetupMixin
from engine.pipeline_models import PipelineResult
from engine.pipeline_node_execution import PipelineNodeExecutionMixin
from engine.pipeline_recovery import PipelineRecoveryMixin
from engine.pipeline_utils import MAX_STEP_TIMEOUT, _truncate_dict, _truncate_result_data_priority
from engine.validator import PipelineValidator
from utils.structured_logger import (
    get_logger as get_structured_logger,
)

logger = logging.getLogger(__name__)


class PipelineEngine(
    PipelineSetupMixin,
    PipelineExecutionMixin,
    PipelineNodeExecutionMixin,
    PipelineRecoveryMixin,
):
    """Pipeline 通用执行器

    负责加载 Pipeline JSON 并执行节点图，支持：
    - 加载/解析 Pipeline JSON
    - 执行 Pipeline 节点图
    - pause/resume/cancel/skip_step 控制
    - 状态机：pending → running → paused → completed/failed/cancelled
    - 取消信号安全处理（完成当前原子操作后退出）
    """

__all__ = [
    "PipelineEngine", "PipelineResult", "MAX_STEP_TIMEOUT",
    "_truncate_dict", "_truncate_result_data_priority",
    "PipelineValidator", "get_structured_logger", "PipelineState",
]
