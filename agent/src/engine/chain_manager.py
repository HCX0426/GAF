"""ChainManager — StateMachine 执行引擎的 BaseEngine 包装。

StateMachine 是 Python callable 模块 hook，不能 JSON 序列化，
通过 ``task_definition["module"]`` 指定模块路径。
"""

from __future__ import annotations

import importlib
import logging
import time
from typing import Any

from core.result import AutoResult, fail_result
from engine.executor import BaseEngine

logger = logging.getLogger(__name__)


class ChainManager(BaseEngine):
    """Chain 执行引擎 — 包装 StateMachine 执行路径。

    StateMachine 的 actions/transitions 是 Python callable，不能 JSON 序列化，
    因此 state_machine 模式需要 Python 模块 hook。模块必须暴露::

        def build_state_machine(device_manager, image_processor) -> StateMachine:
            ...

    模块路径从 ``task_definition["module"]`` 读取（dotted import path，
    例如 ``"custom_tasks.browndust.guild_fsm"``）。

    Usage::

        engine = ChainManager()
        result = engine.run(
            {"module": "custom_tasks.browndust.guild_fsm", "max_iterations": 500},
            device_manager=device_manager,
            image_processor=image_processor,
        )
    """

    def run(self, task_definition: dict[str, Any], **kwargs: Any) -> AutoResult:
        """执行 StateMachine 任务。

        Args:
            task_definition: 含 ``module`` 字段的 dict。可选字段：
                - ``max_iterations``: 最大迭代次数（默认 1000）。
            **kwargs: 支持:
                - ``device_manager``: DeviceManager 实例（必需）。
                - ``image_processor``: ImageProcessor 实例（必需）。
                - ``device_id``: 可选设备 ID。指定后切换设备执行，执行后恢复。

        Returns:
            AutoResult 执行结果。
        """
        start_time = time.monotonic()

        # --- 参数校验 ---
        module_path = task_definition.get("module")
        if not module_path:
            return fail_result(
                error_msg="ChainManager: state_machine 模式缺少 module 字段",
                elapsed_time=time.monotonic() - start_time,
            )

        device_manager = kwargs.get("device_manager")
        image_processor = kwargs.get("image_processor")
        if device_manager is None or image_processor is None:
            return fail_result(
                error_msg="ChainManager: 缺少必需参数 device_manager 或 image_processor",
                elapsed_time=time.monotonic() - start_time,
            )

        device_id = kwargs.get("device_id")

        # --- 设备切换（保留原 chain 语义: 全局 set_active_device + finally 恢复）---
        prev_active = None
        if device_id is not None:
            prev_active = device_manager.get_active_device_id()
            if not device_manager.set_active_device(device_id):
                return fail_result(
                    error_msg=f"设备不存在或不可用: device_id={device_id}",
                    elapsed_time=time.monotonic() - start_time,
                )

        try:
            return self._execute_state_machine(
                task_definition, start_time, device_manager, image_processor,
            )
        finally:
            if prev_active is not None:
                device_manager.set_active_device(prev_active)

    def _execute_state_machine(
        self,
        task_definition: dict[str, Any],
        start_time: float,
        device_manager: Any,
        image_processor: Any,
    ) -> AutoResult:
        """导入模块并执行 StateMachine。"""
        module_path = task_definition.get("module")

        # 1. 导入模块
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            return fail_result(
                error_msg=f"state_machine 模块导入失败: {module_path} — {exc}",
                elapsed_time=time.monotonic() - start_time,
            )

        # 2. 获取 build_state_machine 工厂函数
        builder = getattr(module, "build_state_machine", None)
        if not callable(builder):
            return fail_result(
                error_msg=(
                    f"模块 {module_path} 未暴露 "
                    "build_state_machine(device_manager, image_processor) 工厂函数"
                ),
                elapsed_time=time.monotonic() - start_time,
            )

        # 3. 构建 StateMachine 实例
        try:
            machine = builder(device_manager, image_processor)
        except Exception as exc:
            return fail_result(
                error_msg=f"build_state_machine 调用失败: {exc}",
                elapsed_time=time.monotonic() - start_time,
            )

        # 4. 执行
        max_iterations = int(task_definition.get("max_iterations", 1000))
        try:
            result = machine.run(max_iterations=max_iterations)
        except Exception as exc:
            return fail_result(
                error_msg=f"状态机执行异常: {exc}",
                elapsed_time=time.monotonic() - start_time,
            )

        # 5. 填充耗时
        elapsed = time.monotonic() - start_time
        result.elapsed_time = elapsed
        return result
