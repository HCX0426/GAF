"""Process-wide ContextVars for AI debuggability (P0-1 fix, 2026-07-27).

之前 handler 把 execution_id / task_id 存在 ``self._current_execution_id``
实例属性里, 多设备并发执行时 (每设备一个 _run 线程) 这些属性会被互相
覆盖, 导致错误上报 / 日志关联拿到错误的 execution_id。AI 调试时从 JSONL
反推 WS 消息会失败 (execution_id 不匹配)。

本模块提供 ``contextvars.ContextVar`` 让每个 _run 线程有自己的 execution_id /
task_id, 下游代码 (orchestrator / engine / structured_logger / error
handlers) 通过 ``current_execution_id.get()`` 读取, 无需参数透传。

入口透传契约:
    handler._run() 线程函数开头必调 ``set_current_execution(...)``,
    在 finally 里调 ``clear_current_execution()`` 防止线程池复用时残留。

使用示例::

    from core.context_vars import current_execution_id, current_task_id

    exec_id = current_execution_id.get()  # "" 表示未在任务上下文中
    task_id = current_task_id.get()       # "" 同上
"""

from __future__ import annotations

import contextlib
import contextvars
from typing import Any

# ContextVar 默认空字符串 (而非 None), 让消费方可以直接做字符串拼接 /
# dict 赋值而无需 None 检查。空字符串 = "不在任务上下文中"。
current_execution_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_execution_id", default="",
)
current_task_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_task_id", default="",
)
# P0-9: user_trace_id 从 task_assign 帧透传, 让跨进程 (backend ↔ agent)
# 日志关联成为可能。空字符串 = server 未传或非任务上下文。
current_user_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_trace_id", default="",
)


def set_current_execution(
    execution_id: str,
    task_id: str = "",
    user_trace_id: str = "",
) -> dict[str, Any]:
    """Set the current execution ContextVars.

    MUST be called at the entry point of a task execution thread (e.g.
    handler._run()). Returns a token dict that can be passed to
    ``clear_current_execution()`` for cleanup. Using the returned tokens
    (rather than ContextVar.reset) ensures cleanup works even if the
    ContextVar was already set by an outer scope.

    Args:
        execution_id: Server-provided execution_id (for WS correlation).
        task_id: Server-provided task_id.
        user_trace_id: Optional user_trace_id (P0-9, for cross-process
            log correlation).

    Returns:
        Token dict with keys ``execution_id`` / ``task_id`` /
        ``user_trace_id`` — pass to ``clear_current_execution()``.
    """
    return {
        "execution_id": current_execution_id.set(execution_id or ""),
        "task_id": current_task_id.set(str(task_id) if task_id is not None else ""),
        "user_trace_id": current_user_trace_id.set(user_trace_id or ""),
    }


def clear_current_execution(tokens: dict[str, Any]) -> None:
    """Reset ContextVars using tokens from ``set_current_execution()``.

    Safe to call multiple times — missing tokens are skipped. Should be
    called in a finally block to prevent thread-pool reuse contamination.
    """
    for key, var in (
        ("execution_id", current_execution_id),
        ("task_id", current_task_id),
        ("user_trace_id", current_user_trace_id),
    ):
        token = tokens.get(key)
        if token is not None:
            with contextlib.suppress(LookupError, ValueError):
                # Token already reset or from a different context — ignore.
                var.reset(token)


def get_current_execution_id() -> str:
    """Convenience accessor for ``current_execution_id.get()``."""
    return current_execution_id.get()


def get_current_task_id() -> str:
    """Convenience accessor for ``current_task_id.get()``."""
    return current_task_id.get()


def get_current_user_trace_id() -> str:
    """Convenience accessor for ``current_user_trace_id.get()`` (P0-9)."""
    return current_user_trace_id.get()
