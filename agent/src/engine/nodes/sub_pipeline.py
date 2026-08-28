"""sub_pipeline 节点：引用另一个 Pipeline

Real implementation: when ``pipeline_json`` is provided, a child
PipelineEngine is instantiated inline, inherits the parent device, is
seeded with ``parameters`` as context variables, and executed with a
recursion-depth guard (max 5) to prevent infinite nesting. Sub-engine
step results are merged into the returned AutoResult.

The ``pipeline_id`` path is not supported yet (no pipeline registry
exists); it fails fast with a descriptive message.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext


# Maximum nesting depth for sub-pipelines to prevent infinite recursion.
_MAX_SUB_PIPELINE_DEPTH = 5


@register_node("sub_pipeline")
@dataclass
class SubPipelineNode(PipelineNode):
    """子 Pipeline 引用节点

    引用并执行另一个 Pipeline，支持嵌套调用。

    config 参数：
    - pipeline_id: 引用的 Pipeline ID（暂不支持，需注册表）
    - pipeline_json: 内联 Pipeline JSON 定义（推荐路径）
    - parameters: 传递给子 Pipeline 的参数（写入子 context 变量）
    - wait_completion: 是否等待子 Pipeline 完成，默认 True
    """

    node_type: str = "sub_pipeline"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "pipeline_id": self.config.get("pipeline_id", ""),
            "has_pipeline_json": bool(self.config.get("pipeline_json")),
            "wait_completion": self.config.get("wait_completion", True),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """Execute a real sub-pipeline via a child PipelineEngine.

        Args:
            context: Pipeline 执行上下文

        Returns:
            AutoResult，data 包含子 Pipeline 执行结果
        """
        start = time.monotonic()

        pipeline_id = self.config.get("pipeline_id", "")
        pipeline_json = self.config.get("pipeline_json")
        pipeline_path = self.config.get("pipeline_path", "")
        parameters = self.config.get("parameters", {}) or {}
        wait_completion = self.config.get("wait_completion", True)

        # Resolve pipeline_json: pipeline_path > pipeline_json > pipeline_id
        if not pipeline_json and pipeline_path:
            import json
            import os

            from engine.resource_resolver import resolve_resource_path
            resolved = resolve_resource_path(pipeline_path)
            # Fallback: try os.path.abspath when resolve fails (may point at agent CWD).
            abs_path = os.path.abspath(pipeline_path) if resolved is None else str(resolved)
            if not os.path.isfile(abs_path):
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"pipeline_path 文件不存在: {abs_path}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.PARAM_INVALID,
                        pipeline_path=pipeline_path,
                    ),
                )
            try:
                with open(abs_path, encoding="utf-8") as f:
                    pipeline_json = json.load(f)
            except Exception as exc:
                elapsed = time.monotonic() - start
                return fail_result(
                    error_msg=f"加载 pipeline_path 失败: {exc}",
                    elapsed_time=elapsed,
                    error_code=NodeErrorCode.PARAM_INVALID,
                    node_id=self.id,
                    node_type=self.node_type,
                    data=self._build_fail_diagnostics(
                        context, NodeErrorCode.PARAM_INVALID,
                        pipeline_path=pipeline_path, load_error=str(exc),
                    ),
                )

        if not pipeline_json:
            # pipeline_id path requires a registry which does not exist yet.
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg="pipeline_id 需要注册表，暂不支持，请用 pipeline_json 或 pipeline_path",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    reason="pipeline_id registry not implemented",
                ),
            )

        # Recursion depth guard to prevent infinite nesting.
        depth = int(context.get_variable("_sub_pipeline_depth", 0))
        if depth >= _MAX_SUB_PIPELINE_DEPTH:
            elapsed = time.monotonic() - start
            return fail_result(
                error_msg=f"子 Pipeline 嵌套深度超过上限: {depth} >= {_MAX_SUB_PIPELINE_DEPTH}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    depth=depth, max_depth=_MAX_SUB_PIPELINE_DEPTH,
                ),
            )

        # Local import to avoid circular dependency with engine module.
        from engine.pipeline_engine import PipelineEngine

        sub_engine = PipelineEngine()
        device = getattr(context, "device", None)
        transformer = getattr(context, "coord_transformer", None)
        debug_mode = getattr(context, "debug_mode", False)
        debug_dir = getattr(context, "debug_dir", "./debug")
        coord_system = getattr(context, "coord_system", "")
        sub_engine.load(
            pipeline_json, device=device,
            coord_transformer=transformer,
            debug_mode=debug_mode,
            debug_dir=debug_dir,
            coord_system=coord_system,
        )

        # Seed child context with parameters and propagate recursion depth.
        for key, value in parameters.items():
            sub_engine.context.set_variable(key, value)
        sub_engine.context.set_variable("_sub_pipeline_depth", depth + 1)

        sub_result = sub_engine.execute()
        elapsed = time.monotonic() - start

        result_data = {
            "pipeline_id": pipeline_id,
            "sub_success": sub_result.success,
            "sub_steps_executed": len(sub_result.step_results),
            "sub_results": sub_result.step_results,
            "parameters": parameters,
            "wait_completion": wait_completion,
            "depth": depth + 1,
            # Task 4.47 (P2-26, 2026-07-28): success path 补 coord_system
            "coord_system": getattr(context, "coord_system", "") or "legacy",
        }

        if not sub_result.success:
            diagnostics = self._build_fail_diagnostics(
                context, NodeErrorCode.UNKNOWN,
                sub_success=False,
                sub_error_msg=sub_result.error_msg,
                sub_steps_executed=len(sub_result.step_results),
            )
            diagnostics.update(result_data)
            return fail_result(
                error_msg=f"子 Pipeline 执行失败: {sub_result.error_msg}",
                elapsed_time=elapsed,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=diagnostics,
            )

        context.set_variable(f"{self.id}_sub_pipeline_result", result_data)
        return success_result(data=result_data, elapsed_time=elapsed)
