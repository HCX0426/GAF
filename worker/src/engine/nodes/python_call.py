"""python_call 节点：在 pipeline 中执行任意 Python 代码任务

interface-recovery-design.md §13.

通过 importlib.util.spec_from_file_location 按文件路径加载 Python 模块,
调用指定函数。函数签名契约:
    def my_function(device, context, **kwargs) -> dict

模块路径相对 custom_tasks_base_dir 解析 (WorkerConfig.custom_tasks_base_dir,
默认 "." — 项目根目录)。路径校验防止逃逸 (§13.6)。

超时采用协作式中断: 主线程等 timeout 秒, 超时设 cancel_event 标志位,
用户函数应定期检查 context._python_call_cancel.is_set() 并尽快退出。
daemon 子线程无法强制终止, 不检查标志位的函数会泄漏直到进程结束。
"""

from __future__ import annotations

import importlib.util
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.error_codes import NodeErrorCode
from core.result import AutoResult, fail_result, success_result
from engine.node import PipelineNode, register_node

if TYPE_CHECKING:
    from engine.context import PipelineContext

logger = logging.getLogger(__name__)

# 默认超时秒数 (§13.2 config.timeout 默认值)
_DEFAULT_TIMEOUT = 5.0

# 单次 pipeline 执行累计允许泄漏的 daemon 线程上限 (§13.6 缓解措施)
_MAX_LEAKED_THREADS = 5


@register_node("python_call")
@dataclass
class PythonCallNode(PipelineNode):
    """Python 代码任务节点 (interface-recovery-design.md §13).

    通过 importlib 按文件路径加载 Python 模块并调用指定函数,
    将返回值存入 context 变量供后续节点使用。失败 (异常/超时)
    走标准 fail_result 路径, 触发界面恢复机制 (§13.5)。

    config 参数:
        module_path (str, 必填): Python 文件相对路径, 相对
            context.custom_tasks_base_dir 解析。如
            "resources/BrownDust-II/custom_tasks/position_calc.py"
        function (str, 必填): 模块中要调用的函数名
        args (dict, 可选): 传给函数的关键字参数。值支持:
            - 字面量 (str/int/float/bool): 原样传入
            - "${var_name}": 解析为 context.get_variable("var_name")
            - dict/list: 递归解析内部 "${...}" 引用
        output (str, 可选): 函数返回值存入 context 的变量名。
            不填则不存储。
        timeout (float, 可选): 执行超时秒数, 默认 5.0。
            超时则节点失败 (走标准 fail_result 路径)。
        expected_state (str, 可选): 手动标注期望界面状态,
            供界面恢复 §3.3 三级优先级推断用。强烈推荐 python_call
            节点显式标注, 因 python_call 无 template 字段,
            直接路径推断不适用。
    """

    node_type: str = "python_call"

    def _build_fail_diagnostics(
        self, context: PipelineContext, error_code: NodeErrorCode, **kwargs: Any,
    ) -> dict[str, Any]:
        """构建失败诊断数据 — Task 4.12 (P1-12, 2026-07-28): N192 A1+A2 让 AI 能从 result_data 看到失败上下文."""
        data: dict[str, Any] = {
            "node_id": self.id,
            "node_type": self.node_type,
            "error_code": error_code.value,
            "coord_system": getattr(context, "coord_system", "") or "legacy",
            "module_path": self.config.get("module_path", ""),
            "function": self.config.get("function", ""),
            "output": self.config.get("output", ""),
            "timeout": float(self.config.get("timeout", _DEFAULT_TIMEOUT)),
        }
        data.update(kwargs)
        return data

    def execute(self, context: PipelineContext) -> AutoResult:
        """执行 Python 代码任务

        Args:
            context: Pipeline 执行上下文。读取:
                - context.device: 注入到用户函数的 device 参数
                - context.custom_tasks_base_dir: module_path 解析基准目录
                - context.get_variable(var): 解析 ${var} 引用
                并写入:
                - context._python_call_cancel: threading.Event (协作式中断)
                - context._python_call_result: 函数返回值 (执行后)
                - context._python_call_error: 捕获的异常 (执行失败时)
                - context.variables[output]: 函数返回值 (output 配置时)

        Returns:
            AutoResult:
                - success: data={"return_value": Any, "module": str, "function": str, "elapsed": float}
                - fail: error_msg 描述失败原因 (模块不存在/函数不存在/超时/异常)
        """
        start = time.monotonic()
        module_path = self.config.get("module_path")
        function_name = self.config.get("function")

        if not module_path or not function_name:
            return fail_result(
                error_msg=(
                    "python_call: 'module_path' 和 'function' 为必填字段 "
                    f"(module_path={module_path!r}, function={function_name!r})"
                ),
                elapsed_time=0.0,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    module_path=module_path or "", function=function_name or "",
                ),
            )

        # 路径解析与校验 (§13.6 安全约束)
        base_dir = getattr(context, "custom_tasks_base_dir", ".") or "."
        try:
            abs_path = _validate_module_path(module_path, base_dir)
        except (ValueError, FileNotFoundError) as exc:
            return fail_result(
                error_msg=f"python_call: 路径校验失败: {exc}",
                elapsed_time=time.monotonic() - start,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    base_dir=base_dir, validation_error=str(exc),
                ),
            )

        # 加载模块
        try:
            module = _load_module(abs_path)
        except (ImportError, Exception) as exc:
            return fail_result(
                error_msg=f"python_call: 模块加载失败 ({abs_path}): {exc}",
                elapsed_time=time.monotonic() - start,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    abs_path=str(abs_path), load_error=str(exc),
                ),
            )

        # 取函数
        fn = getattr(module, function_name, None)
        if not callable(fn):
            return fail_result(
                error_msg=(
                    f"python_call: 模块 {abs_path.name} 中未找到可调用函数 "
                    f"'{function_name}'"
                ),
                elapsed_time=time.monotonic() - start,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    abs_path=str(abs_path), function_missing=True,
                ),
            )

        # 解析 args (字面量 + ${var} 引用 + 递归 dict/list)
        raw_args = self.config.get("args", {}) or {}
        try:
            resolved_args = _resolve_args(raw_args, context)
        except Exception as exc:
            return fail_result(
                error_msg=f"python_call: args 解析失败: {exc}",
                elapsed_time=time.monotonic() - start,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    abs_path=str(abs_path), args_resolve_error=str(exc),
                ),
            )

        # 超时执行 (协作式中断)
        timeout = float(self.config.get("timeout", _DEFAULT_TIMEOUT))
        if timeout <= 0:
            timeout = _DEFAULT_TIMEOUT

        # 检查泄漏线程预算 (§13.6 缓解措施)
        leaked = getattr(context, "_leaked_thread_count", 0)
        if leaked > _MAX_LEAKED_THREADS:
            return fail_result(
                error_msg=(
                    f"python_call: 累计泄漏线程数 {leaked} 超过上限 "
                    f"{_MAX_LEAKED_THREADS}, 拒绝执行 (避免线程无限累积)"
                ),
                elapsed_time=time.monotonic() - start,
                error_code=NodeErrorCode.PARAM_INVALID,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.PARAM_INVALID,
                    abs_path=str(abs_path), leaked_threads=leaked,
                    max_leaked_threads=_MAX_LEAKED_THREADS,
                ),
            )

        try:
            return_value = _execute_with_timeout(
                fn=fn,
                args=resolved_args,
                timeout=timeout,
                context=context,
                device=getattr(context, "device", None),
            )
        except TimeoutError as exc:
            # 超时 — daemon 线程会泄漏, 累加计数 (§13.6 缓解)
            context._leaked_thread_count = leaked + 1
            logger.warning(
                "python_call 超时 (module=%s, function=%s, timeout=%.1fs, "
                "thread_id将泄漏): %s",
                abs_path.name, function_name, timeout, exc,
            )
            return fail_result(
                error_msg=str(exc),
                elapsed_time=time.monotonic() - start,
                error_code=NodeErrorCode.TIMEOUT,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.TIMEOUT,
                    abs_path=str(abs_path), leaked_threads=leaked + 1,
                ),
            )
        except Exception as exc:
            return fail_result(
                error_msg=(
                    f"python_call: 函数 {function_name} 执行异常: {exc}"
                ),
                elapsed_time=time.monotonic() - start,
                error_code=NodeErrorCode.UNKNOWN,
                node_id=self.id,
                node_type=self.node_type,
                data=self._build_fail_diagnostics(
                    context, NodeErrorCode.UNKNOWN,
                    abs_path=str(abs_path), exception=type(exc).__name__,
                ),
            )

        # 存返回值到 context 变量
        output_var = self.config.get("output")
        if output_var:
            context.set_variable(output_var, return_value)

        elapsed = time.monotonic() - start
        logger.info(
            "python_call 执行成功: module=%s, function=%s, elapsed=%.3fs",
            abs_path.name, function_name, elapsed,
        )
        return success_result(
            data={
                "module": str(abs_path),
                "function": function_name,
                "return_value": return_value,
                "elapsed": elapsed,
            },
            elapsed_time=elapsed,
        )


# ----------------------------------------------------------------------
# 内部辅助函数
# ----------------------------------------------------------------------

def _validate_module_path(module_path: str, base_dir: str) -> Path:
    """校验 module_path 必须在 base_dir 目录下, 防止路径逃逸 (§13.6)。

    Args:
        module_path: 相对路径 (相对 base_dir) 或绝对路径
        base_dir: agent 配置的 custom_tasks_base_dir

    Returns:
        解析后的绝对路径 (Path 对象)

    Raises:
        ValueError: 路径逃逸 (不在 base_dir 下) 或非 .py 文件
        FileNotFoundError: 文件不存在
    """
    base = Path(base_dir).resolve()
    abs_path = (base / module_path).resolve()

    # is_relative_to 需要 Python 3.9+; agent 要求 3.11+ (pyproject.toml)
    if not abs_path.is_relative_to(base):
        raise ValueError(
            f"module_path 必须在 {base} 下, 当前: {abs_path}"
        )

    if abs_path.suffix != ".py":
        raise ValueError(f"module_path 必须是 .py 文件: {abs_path}")

    if not abs_path.is_file():
        raise FileNotFoundError(f"Python 任务模块不存在: {abs_path}")

    return abs_path


def _load_module(abs_path: Path):
    """按文件路径加载 Python 模块 (§13.3)。

    用 importlib.util.spec_from_file_location 而非 importlib.import_module:
    - 无 sys.path 污染
    - 多游戏天然隔离 (不同游戏用不同绝对路径)
    - module_path 在 JSON 中显式可见, 审计清晰

    Args:
        abs_path: 模块绝对路径 (Path 对象)

    Returns:
        加载后的模块对象

    Raises:
        ImportError: spec 创建失败或 loader 不可用
        Exception: 模块代码执行时的任何异常 (由调用方捕获)
    """
    # 模块名用 custom_task_ 前缀 + 文件名 stem, 避免与标准库冲突
    module_name = f"custom_task_{abs_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块: {abs_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # 执行模块代码 (触发 import + 顶层语句)
    return module


def _resolve_args(raw_args: Any, context: PipelineContext) -> dict[str, Any]:
    """递归解析 config.args 中的 ${var} 引用 (§13.4 参数解析规则)。

    Args:
        raw_args: config.args 原始值 (通常是 dict, 也支持 list/scalar)
        context: Pipeline 上下文 (用于 get_variable)

    Returns:
        解析后的 args dict (所有 ${...} 已替换为实际值)

    Raises:
        KeyError: ${var} 引用的变量不存在时 (用 KeyError 而非 None,
            让调用方明确知道变量缺失)
    """
    if isinstance(raw_args, dict):
        return {k: _resolve_value(v, context) for k, v in raw_args.items()}
    if isinstance(raw_args, list):
        return [_resolve_value(v, context) for v in raw_args]
    # 非容器类型 — 当作单值解析 (不常见, 但保持健壮)
    return _resolve_value(raw_args, context) if raw_args != {} else {}


def _resolve_value(value: Any, context: PipelineContext) -> Any:
    """递归解析单个值: ${var} 引用 → context.get_variable(var)。

    dict / list 递归解析内部引用; 其他类型原样返回。
    """
    if isinstance(value, str):
        return _resolve_var_string(value, context)
    if isinstance(value, dict):
        return {k: _resolve_value(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_value(v, context) for v in value]
    return value


def _resolve_var_string(s: str, context: PipelineContext) -> Any:
    """解析 "${var_name}" 格式字符串。

    - 整串是 "${var}" → 返回变量的原始值 (保留类型: int/dict/list/...)
    - 整串是字面量 → 原样返回
    - 字符串中嵌入 ${var} (如 "prefix_${var}_suffix") → 字符串拼接
      (变量值 str() 化)

    Args:
        s: 待解析字符串
        context: Pipeline 上下文

    Returns:
        解析后的值 (类型可能为 str/int/float/dict/list/...)
    """
    # 整串是 ${var} — 直接返回变量原值 (保留类型)
    if s.startswith("${") and s.endswith("}") and s.count("${") == 1:
        var_name = s[2:-1].strip()
        if not var_name:
            return s  # "${}" 当作字面量
        # get_variable 返回 None 时无法区分 "变量值为 None" vs "变量不存在",
        # 用 in 检查 variables dict 明确报错
        variables = getattr(context, "variables", {}) or {}
        if var_name not in variables:
            raise KeyError(f"变量 '{var_name}' 不存在于 context")
        return context.get_variable(var_name)

    # 字符串中嵌入 ${var} — 字符串拼接
    if "${" in s:
        import re

        def _replace(match):
            var_name = match.group(1).strip()
            variables = getattr(context, "variables", {}) or {}
            if var_name not in variables:
                raise KeyError(f"变量 '{var_name}' 不存在于 context")
            return str(context.get_variable(var_name))

        return re.sub(r"\$\{([^}]+)\}", _replace, s)

    # 纯字面量
    return s


def _execute_with_timeout(fn, args: dict, timeout: float, context, device) -> Any:
    """协作式超时执行 (§13.6 超时处理)。

    主线程等 timeout 秒; 超时设 cancel_event 标志位, 用户函数应
    定期检查 context._python_call_cancel.is_set() 并尽快退出。
    daemon 子线程无法强制终止, 不检查标志位的函数会泄漏直到进程结束。

    Args:
        fn: 用户函数, 签名 fn(device, context, **args) -> Any
        args: 解析后的关键字参数
        timeout: 超时秒数
        context: Pipeline 上下文 (注入 cancel_event 供用户函数检查)
        device: 设备实例 (注入到用户函数的 device 参数)

    Returns:
        函数返回值

    Raises:
        TimeoutError: 超时 (cancel_event 已设置, 但子线程可能仍在运行)
        Exception: 用户函数抛出的任何异常 (原样向上传播)
    """
    cancel_event = threading.Event()

    # 容器: 用 list 包装以在闭包中可变 (避免 nonlocal)
    result_holder: dict[str, Any] = {}

    def _run():
        try:
            # 注入 cancel_event 到 context, 供用户函数检查
            context._python_call_cancel = cancel_event
            result_holder["value"] = fn(device=device, context=context, **args)
        except BaseException as exc:
            result_holder["error"] = exc

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        # 超时 — 设标志位请求中断, daemon 子线程任其自然结束
        cancel_event.set()
        raise TimeoutError(
            f"python_call 执行超时 ({timeout}s), 已请求协作式中断 "
            f"(子线程可能仍在运行, 请在函数内检查 context._python_call_cancel)"
        )

    if "error" in result_holder:
        raise result_holder["error"]

    return result_holder.get("value")
