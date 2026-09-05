"""消息处理器：处理 Server 发来的消息，将结果回传 Server"""

import asyncio
import base64
import logging
import subprocess
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

import cv2
from core.constants import ServerStatus
from core.context_vars import (
    clear_current_execution,
    current_user_trace_id,
    set_current_execution,
)

# Task 4.44 (P2-21/22, 2026-07-28): task.result + task.progress 失败消息体透传 error_code,
# 让 backend 能按错误码分类失败原因 (N192-A 跨进程边界 trace)
from core.error_codes import NodeErrorCode
from core.orchestrator import TaskOrchestrator
from devices.screenshot_cache import compute_frame_hash, get_default_cache

logger = logging.getLogger(__name__)


def _parse_hwnd(raw: str | int | None) -> int | None:
    """Parse a hwnd value that may be decimal ("4785844"), hex ("0x490b4"),
    an int, or empty. Returns None when the value is missing/invalid."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw if raw else None
    text = str(raw).strip()
    if not text:
        return None
    try:
        value = int(text, 0)
    except (TypeError, ValueError):
        return None
    return value if value else None


class MessageHandler:
    """处理 Server 发来的各类消息，通过 send_callback 将结果回传给 Server"""

    def __init__(self, orchestrator: TaskOrchestrator):
        self._orchestrator = orchestrator
        self.send_callback: Callable | None = None
        self._loop = None
        self._current_execution_id: str | None = None
        self._current_task_id: int | None = None
        # screenshot stream state (started/stopped by screenshot.control frames)
        self._screenshot_stream_stop_event: threading.Event | None = None
        self._screenshot_stream_thread: threading.Thread | None = None
        # Per-device last frame hash for dedup (avoids sending identical frames)
        self._last_frame_hashes: dict[str, str] = {}
        # Per-device filter: None or empty = all devices (backward compat)
        self._screenshot_stream_device_ids: list[str] | None = None
        # Task 2.1: LLM WebSocket RPC result storage (keyed by request_id).
        self._llm_results: dict[str, dict[str, Any]] = {}
        self._llm_result_events: dict[str, threading.Event] = {}

    def _send_to_server(self, msg_type: str, data: dict[str, Any]) -> None:
        """通过 send_callback 发送消息到 Server。

        Adds detailed logging and a Future done-callback so silent exceptions
        from ``run_coroutine_threadsafe`` are surfaced. This is critical for
        diagnosing why task.result frames never reach the backend.
        """
        execution_id = data.get("execution_id", "")
        task_id = data.get("task_id", "")
        logger.info(
            "[AGENT->SERVER][handler] 准备发送: msg_type=%s, execution_id=%s, task_id=%s, "
            "send_callback=%s, loop=%s, loop_running=%s, thread=%s",
            msg_type,
            execution_id,
            task_id,
            self.send_callback is not None,
            self._loop is not None,
            self._loop.is_running() if self._loop else False,
            threading.current_thread().name,
        )
        logger.debug(
            "[AGENT->SERVER][handler] payload: msg_type=%s, execution_id=%s, data=%s",
            msg_type,
            execution_id,
            data,
        )

        if not self.send_callback:
            logger.error(
                "[AGENT->SERVER][handler] 发送失败: send_callback 未设置, msg_type=%s, execution_id=%s",
                msg_type,
                execution_id,
            )
            return

        if not self._loop:
            logger.error(
                "[AGENT->SERVER][handler] 发送失败: event loop 未设置, msg_type=%s, execution_id=%s",
                msg_type,
                execution_id,
            )
            return

        if not self._loop.is_running():
            logger.error(
                "[AGENT->SERVER][handler] 发送失败: event loop 未运行, msg_type=%s, execution_id=%s",
                msg_type,
                execution_id,
            )
            return

        try:
            coro = self.send_callback(msg_type, data)
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)
            logger.info(
                "[AGENT->SERVER][handler] Future 已调度: msg_type=%s, execution_id=%s, " "future_id=%s, thread=%s",
                msg_type,
                execution_id,
                id(future),
                threading.current_thread().name,
            )

            def _on_done(fut):
                try:
                    result = fut.result(timeout=0)
                    logger.info(
                        "[AGENT->SERVER][handler] Future 完成: msg_type=%s, execution_id=%s, "
                        "future_id=%s, result=%s",
                        msg_type,
                        execution_id,
                        id(fut),
                        result,
                    )
                except TimeoutError as exc:
                    logger.exception(
                        "[AGENT->SERVER][handler] Future 超时: msg_type=%s, execution_id=%s, " "future_id=%s, error=%s",
                        msg_type,
                        execution_id,
                        id(fut),
                        exc,
                    )
                except Exception as exc:
                    logger.exception(
                        "[AGENT->SERVER][handler] Future 异常: msg_type=%s, execution_id=%s, " "future_id=%s, error=%s",
                        msg_type,
                        execution_id,
                        id(fut),
                        exc,
                    )

            future.add_done_callback(_on_done)

            # Defensive: also attach a timeout waiter on the executor thread so
            # we log if the Future never completes (e.g. event loop blocked).
            def _wait_timeout():
                try:
                    # Block up to 30s; if it completes normally _on_done already logged.
                    future.result(timeout=30)
                except TimeoutError:
                    logger.error(
                        "[AGENT->SERVER][handler] Future 30s 未返回: msg_type=%s, "
                        "execution_id=%s, future_id=%s, 可能事件循环被阻塞或 WebSocket 已断开",
                        msg_type,
                        execution_id,
                        id(future),
                    )
                except Exception:
                    # _on_done already logs the exception with traceback.
                    pass

            threading.Thread(target=_wait_timeout, daemon=True).start()
        except Exception as exc:
            logger.exception(
                "[AGENT->SERVER][handler] 调度 Future 失败: msg_type=%s, execution_id=%s, error=%s",
                msg_type,
                execution_id,
                exc,
            )

    def handle_status_update(self, data: dict[str, Any]) -> None:
        """处理 Server 发来的状态更新.

        spec-35 Phase 2.2: backend spec-29c removed the ``"error"`` message
        type; the server now signals errors by sending ``agent.status``
        frames with ``status="error"`` in the payload. Branch on that here
        so error frames are still surfaced at ERROR log level (previously
        handled by the now-deleted ``handle_error`` method).
        """
        status = data.get("status", "")
        if status == ServerStatus.ERROR.value:
            error_msg = data.get("message", "未知错误")
            logger.error("Server 错误: %s", error_msg)
            return
        logger.info("Server 状态更新: %s", data)

    def handle_task_assign(self, data: dict[str, Any], trace_id: str = "") -> None:
        """接收任务分配，在线程中异步执行并通过 send_callback 回传结果.

        spec-2026-07-27-execution-path-unification 阶段 4: 内部委托给
        ``execute_pipeline``。task_definition 当作 pipeline graph_data 透传
        （老 chain 任务已迁移为 pipeline schema，新任务统一是 pipeline JSON）。
        ``execution_mode`` 字段保留兼容但不再分支（state_machine 走独立模块入口）。

        A3 (spec 2026-07-30-debug-directory-restructure): 新增 ``trace_id`` 参数,
        由 ``_dispatch_to_handler`` 从 WS 帧顶层提取. 优先使用帧顶层 trace_id
        (HTTP 请求级, 由 backend serialize_frame 从 ContextVar 注入), 为空时
        回退到 payload 的 ``user_trace_id`` (老路径兼容).
        """
        execution_id = data.get("execution_id", "")
        task_id = data.get("task_id", "")
        task_name = data.get("task_name", "")
        task_definition = data.get("task_definition", {})
        # N191 §4.3: execution_mode 字段值已归一化为 'pipeline' / 'state_machine'.
        # TD-362: 'chain' 兼容分支已移除 (backend ≥ 0049 普及, 不再发 'chain').
        execution_mode = data.get("execution_mode", "pipeline")
        # Backend now forwards device metadata (window title, screenshot/input
        # methods, adb serial) so the agent can resolve and connect the right
        # device before execution. Without this, discovered Windows devices
        # stay DISCONNECTED and task execution fails immediately.
        device_info = data.get("device_info") or {}
        # Pipeline 执行参数（spec-2026-08-02: handle_pipeline_execute 已删除，统一走 task.assign）
        debug_mode = bool(data.get("debug_mode", False))
        debug_dir = data.get("debug_dir", "")
        wait_when_background = data.get("wait_when_background", {}) or {}
        # Task 1.1 (B7 重试单节点, P0-1): retry-from-step 参数. backend 在
        # retry_from_step action 中构建 previous_results (从原 execution 的
        # 已成功 ExecutionStep 序列化) + start_step_index (失败节点 index), 通过
        # WS payload 透传. agent 转发给 orchestrator.execute_pipeline →
        # engine.execute, 跳过前 N 个节点只重跑失败节点及后续节点.
        # 默认 0 / None 保持向后兼容 (老服务器不发这两个字段 → 完整重跑).
        start_step_index = int(data.get("start_step_index") or 0)
        # WS payload 携带 previous_results 为 list[dict] (JSON 反序列化结果),
        # 但 engine.execute 期望 list[AutoResult]. 在 handler (WS ↔ 内部 API
        # 边界) 转换, 让 orchestrator/engine 始终操作 typed objects.
        prev_results_raw = data.get("previous_results")
        previous_results = None
        if prev_results_raw:
            from core.result import AutoResult
            previous_results = [
                AutoResult(
                    success=bool(r.get("success", False)),
                    data=r.get("data") or {},
                    node_id=r.get("node_id") or "",
                    node_type=r.get("node_type") or "",
                )
                for r in prev_results_raw
                if isinstance(r, dict)
            ]

        self._current_execution_id = execution_id
        self._current_task_id = task_id

        logger.info(
            "收到任务分配: execution_id=%s, task_name=%s, execution_mode=%s",
            execution_id,
            task_name,
            execution_mode,
        )

        # S1 (2026-08-16): 派发确认 — 立即回 event.ack(task.dispatch).
        # backend group_send 无队列无 ack, 帧丢失时执行永久 RUNNING 卡死;
        # backend check_dispatch_acks beat 依赖本 ack 判断派发已送达.
        # 在执行线程启动前回 ack, 即使设备解析/执行失败也不阻塞确认.
        try:
            self._send_to_server(
                "event.ack",
                {
                    "ack_type": "task.dispatch",
                    "execution_id": execution_id,
                    "task_id": task_id,
                },
            )
        except Exception as exc:
            logger.warning(
                "发送 dispatch ack 失败 (非致命): execution_id=%s, error=%s",
                execution_id, exc,
            )

        # Switch the monitor's resource pack BEFORE executing the task so the
        # agent runs the monitor rules for the game profile the backend
        # assigned. Non-fatal: if the manager is unavailable or switch fails,
        # the task still runs with the currently active pack.
        resource_pack = data.get("resource_pack")
        if resource_pack and resource_pack.get("name"):
            monitor_manager = getattr(self._orchestrator, "_monitor_manager", None)
            if monitor_manager is not None:
                try:
                    monitor_manager.switch_resource_pack(resource_pack["name"])
                    logger.info("已切换资源包: %s", resource_pack["name"])
                except Exception as exc:
                    logger.warning(
                        "切换资源包失败 (非致命): %s", exc, exc_info=True
                    )

        # Resolve target device from device_info. F38: device resolution
        # failure is handled INSIDE _run (after set_current_execution) so
        # _send_to_server has the correct ContextVar trace_id.
        resolved = self._resolve_target_device(device_info)

        def _run():
            # P0-1 fix: set ContextVars at thread entry so downstream code
            # (orchestrator / engine / structured_logger / error handlers)
            # can read current execution_id / task_id without parameter
            # passing. Cleared in finally to prevent thread-pool reuse
            # contamination. user_trace_id from task_assign frame (P0-9).
            # A3: 优先用帧顶层 trace_id (HTTP 请求级), 回退到 payload user_trace_id.
            user_trace_id_p0 = str(trace_id or data.get("user_trace_id", "") or "")
            ctx_tokens = set_current_execution(
                execution_id=execution_id,
                task_id=str(task_id) if task_id is not None else "",
                user_trace_id=user_trace_id_p0,
            )

            # F38: 设备解析失败路径移到 _run 线程内 (set_current_execution 之后),
            # 确保 task.result 帧的 trace_id 与入站帧一致.
            if resolved is None:
                error_msg = f"无法解析目标设备: device_info={device_info}"
                logger.error(error_msg)
                self._send_to_server(
                    "task.result",
                    {
                        "execution_id": execution_id,
                        "task_id": task_id,
                        "success": False,
                        "error_msg": error_msg,
                        "error_code": NodeErrorCode.DEVICE_DISCONNECTED.value,
                        "data": {},
                        "elapsed_time": 0.0,
                    },
                )
                return

            try:
                self._send_to_server(
                    "task.progress",
                    {
                        "execution_id": execution_id,
                        "task_id": task_id,
                        "status": "running",
                        "message": f"开始执行任务: {task_name}",
                    },
                )

                def on_wait_status(msg_type: str, payload: dict) -> None:
                    self._send_to_server(msg_type, {
                        "execution_id": execution_id,
                        "task_id": task_id,
                        **payload,
                    })

                def on_step_progress(node_id: str, step_result, step_index: int) -> None:
                    self._send_to_server(
                        "task.progress",
                        {
                            "execution_id": execution_id,
                            "task_id": task_id,
                            "step_index": step_index,
                            "step_name": node_id,
                            "status": "success" if step_result.success else "failed",
                            "error_msg": step_result.error_msg if not step_result.success else "",
                            # Task 4.44 (P2-22): 透传 step 级 error_code, 让 backend 能按错误码分类
                            "error_code": step_result.error_code if not step_result.success else "",
                            "elapsed_time": step_result.elapsed_time,
                            "message": f"节点 {node_id} {'成功' if step_result.success else '失败'}",
                        },
                    )

                # spec-2026-07-27 阶段 4: 统一走 execute_pipeline。
                # task_definition 期望是 pipeline JSON（含 nodes/edges 或线性 nodes）。
                # state_machine 模式由 orchestrator.execute_pipeline 内部分发（保留）。
                # P0-1: pass execution_id so agent JSONL filename matches
                # server execution_id for AI WS↔JSONL correlation.
                # Task 1.1: pass start_step_index + previous_results so the
                # engine skips the first N nodes (already-succeeded predecessors)
                # and re-runs only the failed node + downstream. None/0 default
                # = full pipeline run (backward compat with old servers).
                result = self._orchestrator.execute_pipeline(
                    task_definition,
                    debug_mode=debug_mode,
                    debug_dir=debug_dir,
                    wait_when_background=wait_when_background,
                    on_wait_status=on_wait_status,
                    on_step_progress=on_step_progress,
                    device_id=getattr(resolved, 'device_id', None),
                    execution_id=execution_id,
                    start_step_index=start_step_index,
                    previous_results=previous_results,
                )

                if result.success:
                    logger.info("任务 %s 执行成功", execution_id)
                    self._send_to_server(
                        "task.result",
                        {
                            "execution_id": execution_id,
                            "task_id": task_id,
                            "success": True,
                            "data": result.data,
                            "elapsed_time": result.elapsed_time,
                            "structured_log_path": getattr(result, "structured_log_path", ""),
                        },
                    )
                else:
                    error_msg = result.error_msg or "未知错误"
                    logger.info("任务 %s 执行失败: %s", execution_id, error_msg)
                    self._send_to_server(
                        "task.result",
                        {
                            "execution_id": execution_id,
                            "task_id": task_id,
                            "success": False,
                            "error_msg": error_msg,
                            # Task 4.44 (P2-21): 透传 task 级 error_code, 让 backend 能按错误码分类
                            "error_code": getattr(result, "error_code", "") or NodeErrorCode.UNKNOWN.value,
                            "data": result.data,
                            "elapsed_time": result.elapsed_time,
                            "structured_log_path": getattr(result, "structured_log_path", ""),
                        },
                    )
            except Exception as exc:
                logger.exception(
                    "任务 %s 执行异常: %s", execution_id, exc,
                )
                self._send_to_server(
                    "task.result",
                    {
                        "execution_id": execution_id,
                        "task_id": task_id,
                        "success": False,
                        "error_msg": f"Agent 内部异常: {exc}",
                        "error_code": NodeErrorCode.UNKNOWN.value,
                        "data": {},
                        "elapsed_time": 0.0,
                    },
                )
            finally:
                clear_current_execution(ctx_tokens)

        threading.Thread(target=_run, daemon=True).start()

    def _resolve_target_device(self, device_info: dict[str, Any]) -> Any | None:
        """Resolve the target device from device_info and set it active.

        For Windows devices: matches by window_title (or window_handle) against
        existing devices in DeviceManager; if no match is found, creates a new
        WindowsDevice, connects it, and registers it. For emulator devices:
        matches by adb_serial.

        Args:
            device_info: Device metadata from the backend (window_handle,
                window_title, screenshot_method, adb_serial, device_type, ...)

        Returns:
            The resolved BaseDevice instance, or None if resolution failed.
        """
        if not device_info:
            # No device_info from server — use whatever is already active.
            return self._orchestrator._device_manager.get_active_device()

        device_type = (device_info.get("device_type") or "").lower()
        device_manager = self._orchestrator._device_manager

        if device_type == "windows":
            return self._resolve_windows_device(device_info, device_manager)
        elif device_type == "emulator":
            return self._resolve_emulator_device(device_info, device_manager)
        else:
            # Unknown device_type — fall back to active device.
            logger.warning(
                "未知 device_type=%s, 使用当前活跃设备",
                device_type,
            )
            return device_manager.get_active_device()

    def _resolve_windows_device(self, device_info: dict[str, Any], device_manager: Any) -> Any | None:
        """Find or create a WindowsDevice matching device_info, set it active.

        Match priority (first non-empty key wins):
        1. ``window_title`` — exact match against ``dev._window_title``
        2. ``name`` — exact match against ``dev.name`` (robust when the
           backend's ``extra_info.window_title`` was overwritten by device.sync
           and lost; both the DB device and the agent's discovered device
           share the same human-readable name, e.g. "BrownDust II")
        3. ``window_handle`` — hex hwnd string match against the device's
           bound WindowManager hwnd (only available after connect())

        When creating a new device, ``window_title or name`` is used as the
        WindowsDevice's window_title so connect() can still find the window
        by title even if the backend sent an empty window_title.
        """
        window_title = device_info.get("window_title", "") or ""
        window_handle = device_info.get("window_handle", "") or ""
        screenshot_method = device_info.get("screenshot_method", "") or "auto"
        input_method = device_info.get("input_method", "") or ""
        control_mode = device_info.get("control_mode", "") or "pseudo_background"
        device_name = device_info.get("name", "") or window_title or "Windows Device"

        # Try to find an existing WindowsDevice matching any of the keys.
        # DeviceManager stores devices by string device_id; iterate to match
        # by attributes that WindowsDevice exposes.
        for dev in device_manager._devices.values():
            if not hasattr(dev, "_window_title"):
                continue
            matched_by = ""
            if window_title and dev._window_title == window_title:
                matched_by = f"window_title={window_title}"
            elif device_name and getattr(dev, "name", "") == device_name:
                matched_by = f"name={device_name}"
            elif window_handle:
                # Compare by int value so both decimal ("4785844") and hex
                # ("0x490b4") hwnd strings match the device's bound handle.
                hint_hwnd = _parse_hwnd(window_handle)
                if hint_hwnd:
                    bound_hwnd = getattr(getattr(dev, "_window_mgr", None), "hwnd", None)
                    if bound_hwnd is not None and int(bound_hwnd) == hint_hwnd:
                        matched_by = f"hwnd={window_handle}"
            if matched_by:
                logger.info("命中已有 Windows 设备: id=%s, by=%s", dev.device_id, matched_by)
                # Browser windows change title per page (user 2026-08-27):
                # refresh the cached title from the freshest backend info so a
                # page navigation does not leave connect() hunting the old title.
                fresh_title = window_title or ""
                if fresh_title and getattr(dev, "_window_title", None) != fresh_title:
                    logger.info(
                        "设备 %s 窗口标题刷新 %r -> %r",
                        dev.device_id, getattr(dev, "_window_title", ""), fresh_title,
                    )
                    dev._window_title = fresh_title
                self._ensure_device_connected(dev)
                # Apply any updated config from the backend so device setting
                # changes (e.g. switching input_method to PseudoBackground)
                # take effect without requiring an agent restart.
                if hasattr(dev, "reconfigure"):
                    try:
                        dev.reconfigure(
                            input_method=input_method or None,
                            screenshot_method=screenshot_method or None,
                            control_mode=control_mode or None,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Device %s reconfigure failed (non-fatal): %s",
                            dev.device_id,
                            exc,
                        )
                # P3: do NOT call set_active_device here. execute_pipeline
                # resolves the device by device_id directly and no longer
                # relies on global active_device state, so mutating it would
                # needlessly interfere with other pipelines running in
                # parallel on different devices.
                return dev

        # No existing match — create a new WindowsDevice and register it.
        # This happens when the backend registered a window that the agent's
        # discovery pass didn't pick up (e.g. before "BrownDust" was added to
        # GAMING_KEYWORDS, or when the window opened after agent startup).
        # Use window_title or device_name as the window_title so connect()
        # can find the window by title; device_name is the same string as
        # the window title for windows discovered by the backend.
        bind_title = window_title or device_name or None
        try:
            from platforms.windows.device import WindowsDevice

            # Use a stable device_id derived from window_handle so re-runs
            # find the same device id instead of creating duplicates.
            device_id = f"windows-hwnd-{window_handle}" if window_handle else f"windows-title-{window_title}"
            new_dev = WindowsDevice(
                device_id=device_id,
                name=device_name,
                window_title=bind_title,
                # Known-valid hwnd hint: connect() binds it directly when still
                # valid, so a drifted window title (browser page navigation) no
                # longer leaves the device unbound and UIA nodes fail.
                window_handle=_parse_hwnd(window_handle),
                screenshot_method=screenshot_method,
                input_method=input_method,
                control_mode=control_mode,
            )
            self._ensure_device_connected(new_dev)
            device_manager.add_device(new_dev)
            # P3: do NOT call set_active_device here. See note above — the
            # pipeline resolves the device by device_id itself.
            logger.info(
                "已为 Pipeline 创建 Windows 设备: id=%s, title=%s, control_mode=%s, screenshot=%s, input=%s",
                device_id,
                bind_title,
                control_mode,
                screenshot_method,
                input_method,
            )
            return new_dev
        except Exception as exc:
            logger.exception("创建 WindowsDevice 失败: %s", exc)
            return None

    def _resolve_emulator_device(self, device_info: dict[str, Any], device_manager: Any) -> Any | None:
        """Find or create an emulator/ADB device matching device_info, set it active."""
        adb_serial = device_info.get("adb_serial", "")
        if not adb_serial:
            logger.warning("emulator 设备缺少 adb_serial, 使用当前活跃设备")
            return device_manager.get_active_device()

        for dev in device_manager._devices.values():
            if not hasattr(dev, "_adb_serial"):
                continue
            if dev._adb_serial == adb_serial:
                logger.info("命中已有 emulator 设备: id=%s, serial=%s", dev.device_id, adb_serial)
                self._ensure_device_connected(dev)
                # P3: do NOT call set_active_device here. execute_pipeline
                # resolves the device by device_id directly.
                return dev

        # No existing match — fall back to active device rather than
        # auto-creating an ADB device (ADB connection setup is non-trivial
        # and better left to the discovery flow).
        logger.warning("未找到 adb_serial=%s 的设备, 使用当前活跃设备", adb_serial)
        return device_manager.get_active_device()

    @staticmethod
    def _ensure_device_connected(device: Any) -> None:
        """Connect the device if it is not already connected/idle.

        The orchestrator's @require_operable decorator rejects devices that
        are not in CONNECTED/IDLE state. A rediscovered window device may
        still be DISCONNECTED if it was added but never connect()ed.

        Browser windows get a NEW hwnd on every restart (user 2026-08-27);
        a cached handle can outlive its window. Detect the stale handle and
        force a reconnect so connect() re-binds by the (refreshed) title.
        """
        from devices.base import DeviceStatus

        window_mgr = getattr(device, "_window_mgr", None)
        cached_hwnd = getattr(window_mgr, "hwnd", None) if window_mgr is not None else None
        if cached_hwnd:
            try:
                from platforms.windows.window import is_window

                if not is_window(cached_hwnd):
                    logger.info(
                        "设备 %s 缓存窗口句柄已失效 (hwnd=%s), 重连以重新绑定窗口",
                        device.device_id, hex(cached_hwnd),
                    )
                    try:
                        device.disconnect()
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("设备 %s disconnect 失败(忽略): %s", device.device_id, exc)
            except Exception:  # noqa: BLE001
                # Non-Windows platforms (emulators) have no is_window — skip the check.
                logger.debug("设备 %s 窗口句柄校验跳过 (非 Windows 窗口设备)", device.device_id)

        if device.status not in (DeviceStatus.CONNECTED, DeviceStatus.IDLE):
            try:
                device.connect()
            except Exception as exc:
                logger.warning("设备连接失败 id=%s: %s", device.device_id, exc)

    def handle_task_cancel(self, data: dict[str, Any], trace_id: str = "") -> None:
        """取消任务

        F23 (spec 2026-07-30-debug-directory-restructure): 新增 ``trace_id`` 参数,
        由 ``_dispatch_to_handler`` 从 WS 帧顶层提取. 设置 ContextVar 以便后续
        上行帧 (send_message) 能从 ContextVar 取 trace_id.
        """
        task_id = data.get("task_id", "")
        logger.info("收到取消任务指令: task_id=%s", task_id)
        if trace_id:
            current_user_trace_id.set(trace_id)
        self._orchestrator.cancel_task()

    # spec-35 Phase 4.4 (2026-07-19): handle_device_command and
    # handle_config_update methods deleted. Both were dead code:
    # - handler_map never referenced them (no "device.command" /
    #   "device.action" / "config.update" entries)
    # - backend MessageType enum has no matching types, so the server
    #   could not dispatch frames to them
    # - handle_device_command sent "device.screenshot" frames, which
    #   backend MessageFrameSerializer rejects (not in MessageType)
    #
    # S2-2.7 (2026-08-17): restored — backend recovery_engine now dispatches
    # device.command frames (recovery-design link wiring), so the handler is
    # no longer dead code. Results are reported via "device.action_result"
    # (P-048: backend _handle_command_result writes RecoveryLog + broadcast).

    def handle_device_command(self, data: dict[str, Any], trace_id: str = "") -> None:
        """Handle device recovery command from the server.

        S2-2.7 (2026-08-17): backend scheduler/recovery_engine
        ``_action_device_command`` dispatches recovery actions via
        ``device.command`` WS frames (restart_app / relogin / notify_only /
        restart_emulator / reconnect_adb / switch_backup). The backend
        reports success once the frame is sent; the agent executes the
        command and reports the actual outcome via ``device.action_result``
        so the backend can write a truthful RecoveryLog (P-048).

        Executors (spec 2026-08-17-s27-device-command-executors):
        - restart_app: real restart via ADB am force-stop + monkey (Android/
          emulator) or taskkill + Popen (Windows), reusing the app_control
          node primitives.
        - notify_only: real notify via logger (info/warning/error by level).
        Commands with no agent-side executor yet (relogin / switch_account /
        switch_backup / restart) return an explicit not-implemented result —
        never a fake success.

        Args:
            data: ``{"command": "...", "target_id": ..., "config": {...}}``
            trace_id: WS frame top-level trace_id, passed by
                _dispatch_to_handler.
        """
        command = data.get("command", "")
        target_id = data.get("target_id")
        config = data.get("config", {}) or {}
        if trace_id:
            current_user_trace_id.set(trace_id)
        logger.info(
            "[AGENT] 收到设备恢复命令: command=%s, target_id=%s",
            command, target_id,
        )

        success = False
        output: dict[str, Any] = {}

        device_manager = getattr(self._orchestrator, "_device_manager", None)
        active_device = None
        if device_manager is not None:
            active_device = device_manager.get_active_device()

        if command == "restart_emulator":
            from devices.emulator_controller import EmulatorController

            emulator_type = config.get("emulator_type", "")
            instance_id = config.get("instance_id")
            if not emulator_type:
                output["error"] = "restart_emulator requires config.emulator_type"
            else:
                try:
                    controller = EmulatorController()
                    success = controller.restart_emulator(
                        emulator_type=emulator_type,
                        instance_id=instance_id,
                        wait_for_boot=True,
                    )
                    output["emulator_type"] = emulator_type
                except Exception as exc:
                    output["error"] = f"restart_emulator failed: {exc}"
        elif command == "reconnect_adb":
            if active_device is None:
                output["error"] = "no active device to reconnect"
            else:
                try:
                    active_device.connect()
                    success = True
                    output["device_id"] = getattr(active_device, "device_id", "")
                except Exception as exc:
                    output["error"] = f"reconnect_adb failed: {exc}"
        elif command == "restart_app":
            success, output = self._exec_restart_app(active_device, config)
        elif command == "notify_only":
            success, output = self._exec_notify_only(config)
        elif command in ("relogin", "switch_backup", "switch_account",
                         "restart"):
            # No agent-side executor for these yet (see spec
            # 2026-08-17-s27-device-command-executors 已知限制: relogin /
            # switch_account need GameAccount credential delivery design,
            # switch_backup semantics TBD). Report explicitly, not fake
            # success.
            output["error"] = (
                f"{command} not implemented on agent side "
                "(spec 2026-08-17-s27-device-command-executors)"
            )
            logger.warning(
                "[AGENT] device command %s 无 agent 端执行器 (not-implemented), target_id=%s",
                command, target_id,
            )
        else:
            output["error"] = f"unknown device command: {command}"

        self._send_to_server(
            "device.action_result",
            {
                "command": command,
                "target_id": target_id,
                "success": success,
                "output": output,
                "execution_id": data.get("execution_id", ""),
            },
        )

    def _exec_restart_app(
        self, active_device: Any, config: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        """Restart the target app: force-stop + relaunch.

        Reuses the app_control node primitives (_run_adb for ADB, taskkill +
        Popen for Windows) so the device.command path and the start_app /
        stop_app pipeline nodes share one implementation source.

        config:
        - package: Android package name (required for Android/emulator)
        - process: Windows process image name, e.g. "notepad.exe"
          (alternative to `command` for Windows)
        - command: explicit Windows launch command (overrides `process`)
        - timeout: per-command timeout seconds (default 10)
        - wait_seconds: sleep after relaunch (default 10)
        """
        from engine.nodes.app_control import _run_adb

        if active_device is None:
            return False, {"error": "restart_app requires an active device"}
        timeout = float(config.get("timeout", 10.0))
        wait_seconds = float(config.get("wait_seconds", 10.0))
        device_type = str(getattr(active_device, "device_type", "")).lower()
        try:
            if device_type in ("emulator", "android"):
                package = config.get("package", "")
                if not package:
                    return False, {
                        "error": "restart_app requires config.package for "
                        "Android device",
                    }
                rc, out, err = _run_adb(
                    active_device, ["shell", "am", "force-stop", package],
                    timeout=timeout,
                )
                if rc != 0:
                    return False, {
                        "error": (
                            f"restart_app force-stop failed (rc={rc}): "
                            f"{err.strip() or out.strip()}"
                        ),
                    }
                rc, out, err = _run_adb(
                    active_device,
                    [
                        "shell", "monkey", "-p", package,
                        "-c", "android.intent.category.LAUNCHER", "1",
                    ],
                    timeout=timeout,
                )
                if rc != 0:
                    return False, {
                        "error": (
                            f"restart_app launch failed (rc={rc}): "
                            f"{err.strip() or out.strip()}"
                        ),
                    }
            else:
                command = config.get("command", "")
                if not command:
                    return False, {
                        "error": "restart_app requires config.command for "
                        "Windows device (launch command to relaunch)",
                    }
                cmd_list = (
                    command.split() if isinstance(command, str)
                    else list(command)
                )
                proc_name = config.get("process", "") or cmd_list[0]
                kill = subprocess.run(
                    ["taskkill", "/IM", proc_name, "/F"],
                    capture_output=True, text=True, timeout=timeout,
                )
                if kill.returncode != 0:
                    return False, {
                        "error": (
                            f"restart_app taskkill failed (rc="
                            f"{kill.returncode}): "
                            f"{kill.stderr.strip() or kill.stdout.strip()}"
                        ),
                    }
                proc = subprocess.Popen(
                    cmd_list, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                logger.info("restart_app: spawned PID %d (%s)", proc.pid, cmd_list[0])
        except subprocess.TimeoutExpired:
            return False, {
                "error": f"restart_app timed out after {timeout}s",
            }
        except Exception as exc:
            return False, {"error": f"restart_app failed: {exc}"}

        if wait_seconds > 0:
            time.sleep(wait_seconds)
        return True, {"device_type": device_type, "wait_seconds": wait_seconds}

    def _exec_notify_only(self, config: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        """Emit a notification via the logger (no webhook in handler scope).

        config:
        - message: notification body (required)
        - level: "info" / "warning" / "error" (default "info")
        """
        message = config.get("message", "")
        if not message:
            return False, {"error": "notify_only requires config.message"}
        level = str(config.get("level", "info")).lower()
        log_fn = {
            "info": logger.info,
            "warning": logger.warning,
            "error": logger.error,
        }.get(level, logger.info)
        log_fn("[NOTIFY] %s", message)
        return True, {"level": level, "message": message}

    def handle_monitor_rule_update(self, data: dict[str, Any], trace_id: str = "") -> None:
        """Receive hot-updated monitor rules from Server, forward to MonitorManager.

        Server's ``MonitorRuleViewSet.push_to_agent`` triggers this via the
        WebSocket channel. ``MonitorManager.update_rules(rules_data)`` (already
        implemented in ``monitor/manager.py:215``) stops the running monitor
        thread, swaps the rule set, and restarts the thread — so this handler
        is a thin wrapper that delegates to the manager.

        Non-fatal: if the manager is unavailable or ``update_rules`` raises,
        log a warning and return. The agent continues running with the
        previously loaded rules.

        F23 (spec 2026-07-30-debug-directory-restructure): 新增 ``trace_id`` 参数,
        由 ``_dispatch_to_handler`` 从 WS 帧顶层提取. 设置 ContextVar 以便后续
        上行帧 (send_message) 能从 ContextVar 取 trace_id.

        Args:
            data: ``{"rules": [<serialized MonitorRule>, ...], "agent_id": ...}``
            trace_id: WS 帧顶层 trace_id, 由 _dispatch_to_handler 传递.
        """
        rules = data.get("rules", [])
        monitor_manager = getattr(self._orchestrator, "_monitor_manager", None)
        if monitor_manager is None:
            logger.warning(
                "收到监控规则热更新 (%d 条) 但 MonitorManager 未注入，跳过",
                len(rules),
            )
            return
        if not hasattr(monitor_manager, "update_rules"):
            logger.warning(
                "MonitorManager 无 update_rules 方法，无法热更新 %d 条规则",
                len(rules),
            )
            return
        if trace_id:
            current_user_trace_id.set(trace_id)
        try:
            monitor_manager.update_rules(rules)
            logger.info("监控规则热更新: %d 条", len(rules))
        except Exception as exc:
            logger.warning("监控规则热更新失败 (非致命): %s", exc)

    def handle_screenshot_control(self, data: dict[str, Any], trace_id: str = "") -> None:
        """Handle screenshot stream control from the frontend via the backend.

        The frontend opens the ExecutionMonitorPanel and sends
        ``request_screenshot_stream``; the backend forwards it as a
        ``screenshot.control`` frame. The agent then starts a lightweight
        capture thread that sends ``screenshot_frame`` frames back to the
        server, which broadcasts them to dashboard clients.

        F23 (spec 2026-07-30-debug-directory-restructure): 新增 ``trace_id`` 参数,
        由 ``_dispatch_to_handler`` 从 WS 帧顶层提取. 设置 ContextVar 以便后续
        上行帧 (send_message) 能从 ContextVar 取 trace_id.

        Args:
            data: ``{"action": "start" | "stop", "agent_id": ...}``
            trace_id: WS 帧顶层 trace_id, 由 _dispatch_to_handler 传递.
        """
        action = data.get("action", "")
        agent_id = data.get("agent_id", "")
        if trace_id:
            current_user_trace_id.set(trace_id)
        logger.info(
            "[AGENT] 收到截图流控制: action=%s, agent_id=%s",
            action,
            agent_id,
        )
        if action == "start":
            self._start_screenshot_stream()
        elif action == "stop":
            self._stop_screenshot_stream()
        else:
            logger.warning("[AGENT] 未知截图流控制 action: %s", action)

    def handle_llm_result(self, data: dict[str, Any], trace_id: str = "") -> None:
        """Handle LLM call result from server via WebSocket RPC (Task 2.1).

        The server responds to ``llm.call`` frames with ``llm.result`` frames
        carrying the LLM response. This handler logs the result and stores it
        in a per-request dict so callers can retrieve it asynchronously.

        The result is stored in ``self._llm_results`` keyed by ``request_id``
        and a ``threading.Event`` is set to signal awaiters.

        Args:
            data: ``{"request_id": "...", "status": "success"|"error",
                "content": "...", "model": "...", "usage": {...}}``
            trace_id: WS 帧顶层 trace_id.
        """
        request_id = data.get("request_id", "")
        if not request_id:
            logger.warning("llm.result: 缺少 request_id, 忽略")
            return

        if trace_id:
            current_user_trace_id.set(trace_id)

        status = data.get("status", "error")
        if status == "success":
            logger.info(
                "LLM result via WS RPC: request_id=%s, model=%s, route=%s",
                request_id, data.get("model", ""), data.get("route", ""),
            )
        else:
            logger.warning(
                "LLM result error: request_id=%s, error=%s",
                request_id, data.get("error", ""),
            )

        self._llm_results[request_id] = data
        event = self._llm_result_events.get(request_id)
        if event:
            event.set()

    def _start_screenshot_stream(self) -> None:
        """Start a background thread that captures and sends screenshot frames.

        TD-357: Stop any existing thread first to prevent thread leaks.
        """
        if self._screenshot_stream_thread and self._screenshot_stream_thread.is_alive():
            logger.info("[AGENT] 截图流: 旧线程仍在运行，先停止再重启")
            self._stop_screenshot_stream()
        self._screenshot_stream_stop_event = threading.Event()
        self._screenshot_stream_thread = threading.Thread(
            target=self._screenshot_stream_loop,
            name="screenshot-stream",
            daemon=True,
        )
        self._screenshot_stream_thread.start()
        logger.info("[AGENT] 截图流线程已启动")

    def _stop_screenshot_stream(self) -> None:
        """Signal the screenshot stream thread to stop."""
        if not self._screenshot_stream_thread or not self._screenshot_stream_thread.is_alive():
            logger.info("[AGENT] 截图流线程未运行，忽略 stop")
            return
        if self._screenshot_stream_stop_event:
            self._screenshot_stream_stop_event.set()
        self._screenshot_stream_thread.join(timeout=2.0)
        if self._screenshot_stream_thread.is_alive():
            logger.warning("[AGENT] 截图流线程未在 2 秒内退出")
        else:
            logger.info("[AGENT] 截图流线程已停止")
        self._screenshot_stream_thread = None
        # Clear per-device filter and dedup cache so a restarted stream
        # always starts fresh.
        self._screenshot_stream_device_ids = None
        self._last_frame_hashes.clear()

    def _screenshot_stream_loop(self) -> None:
        """Periodically capture every operable device screen and send frames.

        Runs in a daemon thread. Uses a 1-second interval and JPEG compression
        to keep bandwidth reasonable. Any exception is logged and the loop
        continues; a burst of repeated failures causes the thread to give up
        so it does not spam the server.

        Unlike the previous single-active-device design, this loop iterates
        over all devices registered in DeviceManager so that the device-center
        grid can show a live thumbnail for every available device (Windows
        window, emulator, etc.).
        """
        stop_event = self._screenshot_stream_stop_event
        if stop_event is None:
            return

        consecutive_errors = 0
        max_consecutive_errors = 10
        # TD-356: 从 1.0s 降至 0.3s 降低端到端延迟; dedup hash 自动过滤重复帧
        frame_interval = 0.3  # seconds (~3 FPS, dedup prevents duplicate sends)

        while not stop_event.wait(frame_interval):
            try:
                device_manager = getattr(self._orchestrator, "_device_manager", None)
                if device_manager is None:
                    logger.info("[AGENT] 截图流: DeviceManager 未初始化，跳过")
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("[AGENT] 截图流: 连续 %d 次无 DeviceManager，停止线程", consecutive_errors)
                        break
                    continue

                devices = list(device_manager._devices.values())
                if not devices:
                    logger.info("[AGENT] 截图流: 无注册设备，跳过")
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("[AGENT] 截图流: 连续 %d 次无设备，停止线程", consecutive_errors)
                        break
                    continue

                # Per-device filter: if device_ids is set, only capture matching
                # devices. None/empty list means capture all (backward compat).
                target_ids = self._screenshot_stream_device_ids
                if target_ids:
                    target_set = set(target_ids)
                    devices = [d for d in devices if d.device_id in target_set]
                    if not devices:
                        logger.debug(
                            "[AGENT] 截图流: 过滤后无目标设备 (target_ids=%s)，跳过",
                            target_ids,
                        )
                        continue  # not an error, just no matching devices


                # processed_any_device tracks whether at least one device
                # successfully captured a frame this round. We can't key the
                # consecutive_errors guard on "did we send a frame" because
                # TD-009 dedup intentionally skips sending on a healthy capture
                # when the screen is static — that would miscount dedup skips
                # as errors and kill the stream thread after 10 rounds.
                processed_any_device = False
                # Parallel capture using ThreadPoolExecutor for multi-device
                # throughput. max_workers=4 balances parallelism vs resource
                # usage; with 1-2 devices the pool runs effectively serially,
                # with 5+ devices it cuts round time from N × capture_time to
                # ~ceil(N/4) × capture_time.
                max_workers = min(4, len(devices)) if devices else 1
                with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ss-capture") as pool:
                    futures = {pool.submit(self._capture_one_device, device, stop_event): device for device in devices}
                    for future in as_completed(futures):
                        device = futures[future]
                        try:
                            if future.result():
                                processed_any_device = True
                        except Exception as exc:
                            logger.warning(
                                "[AGENT] 截图流: device=%s capture future error: %s",
                                device.device_id,
                                exc,
                            )

                if processed_any_device:
                    consecutive_errors = 0
                else:
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("[AGENT] 截图流: 连续 %d 轮未成功捕获任何设备，停止线程", consecutive_errors)
                        break
            except Exception as exc:
                consecutive_errors += 1
                logger.warning(
                    "[AGENT] 截图流: 第 %d 次异常: %s",
                    consecutive_errors,
                    exc,
                )
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("[AGENT] 截图流: 连续异常过多，停止线程")
                    break

        logger.info("[AGENT] 截图流循环结束")

    def _capture_one_device(self, device: Any, stop_event: threading.Event) -> bool:
        """Capture one device screen and send frame if successful.

        Extracted from _screenshot_stream_loop so it can run in parallel via
        ThreadPoolExecutor. Handles device auto-connect, capture, dedup,
        JPEG encoding, and frame sending for a single device.

        Args:
            device: The device instance to capture.
            stop_event: Shared stop event to check for early abort.

        Returns:
            True if capture_screen succeeded (frame captured), False otherwise.
            Note: returns True even when the frame is skipped due to dedup or
            JPEG encode failure, because the device itself is healthy and the
            consecutive_errors guard should not trip.
        """
        if stop_event.is_set():
            return False

        from devices.base import DeviceStatus

        # Auto-connect discovered devices before capture. The discovery flow
        # creates device instances but does not call connect(), so
        # capture_screen() fails with "设备不可操作，当前状态: disconnected"
        # until we connect.
        if device.status not in (DeviceStatus.CONNECTED, DeviceStatus.IDLE):
            logger.info(
                "[AGENT] 截图流: 设备未连接，尝试 connect: id=%s status=%s",
                device.device_id,
                device.status.value,
            )
            try:
                device.connect()
            except Exception as connect_exc:
                logger.warning(
                    "[AGENT] 截图流: 设备 connect 失败: id=%s error=%s",
                    device.device_id,
                    connect_exc,
                )
                return False

        if device.status not in (DeviceStatus.CONNECTED, DeviceStatus.IDLE):
            logger.debug(
                "[AGENT] 截图流: 设备仍不可用，跳过: id=%s status=%s",
                device.device_id,
                device.status.value,
            )
            return False

        try:
            img = device.capture_screen()
        except Exception as capture_exc:
            logger.warning(
                "[AGENT] 截图流: capture_screen 异常: id=%s error=%s",
                device.device_id,
                capture_exc,
            )
            return False

        if img is None:
            logger.warning(
                "[AGENT] 截图流: 截图返回 None，跳过 device=%s",
                device.device_id,
            )
            return False

        # capture_screen succeeded — this device is healthy.
        # TD-009: skip identical frames to save bandwidth on static screens.
        # compute_frame_hash uses SHA-256 of raw pixels, so the same screen
        # produces the same hash and we can avoid JPEG-encoding + base64-
        # encoding + sending ~500KB redundantly.
        frame_hash = compute_frame_hash(img)
        last_hash = self._last_frame_hashes.get(device.device_id)
        if frame_hash and last_hash == frame_hash:
            logger.debug(
                "[AGENT] 截图流: 帧未变化，跳过发送 device=%s hash=%s...",
                device.device_id,
                frame_hash[:12],
            )
            return True  # captured successfully, just deduped
        self._last_frame_hashes[device.device_id] = frame_hash

        # TD-019: query the ScreenshotCache before JPEG-encoding. On a hit
        # we reuse the cached encoded bytes (skipping the expensive
        # cv2.imencode call). On a miss we encode as before and store the
        # result so the next capture of the same frame hits the cache.
        # Cache failures (Redis down, set raises, etc.) are non-fatal — the
        # encode path still runs and the frame still goes out.
        cache = get_default_cache()
        cached_buf = cache.get(device.device_id, frame_hash)
        if cached_buf is not None:
            buf = cached_buf
            logger.debug(
                "[AGENT] 截图流: ScreenshotCache 命中，跳过 JPEG 编码 device=%s hash=%s...",
                device.device_id,
                frame_hash[:12],
            )
        else:
            ok, buf = cv2.imencode(".jpg", img)
            if not ok:
                logger.warning("[AGENT] 截图流: JPEG 编码失败 device=%s", device.device_id)
                return True  # capture succeeded, encode failed
            # Cache the encoded JPEG for future reuse. Convert numpy
            # ndarray → bytes via tobytes() since ScreenshotCache.set
            # stores bytes (and Redis setex rejects ndarray).
            try:
                cache.set(device.device_id, frame_hash, buf.tobytes())
            except Exception as cache_exc:
                logger.debug(
                    "[AGENT] 截图流: ScreenshotCache.set 失败 (non-fatal): %s",
                    cache_exc,
                )

        image_base64 = base64.b64encode(buf).decode("utf-8")
        # Use the canonical protocol type "screenshot.frame" so
        # WorkerConsumer._handle_screenshot_frame recognizes and forwards the
        # frame to the frontend. Also send device metadata (name/type/hwnd)
        # so the backend can map the agent-side opaque device_id to backend
        # Device.id.
        device_name = getattr(device, "name", "") or ""
        device_type = self._infer_device_type(device)
        hwnd = self._get_device_hwnd(device)
        self._send_to_server(
            "screenshot.frame",
            {
                "device_id": device.device_id,
                "device_name": device_name,
                "device_type": device_type,
                "window_handle": hwnd,
                "image_base64": image_base64,
                "width": int(img.shape[1]),
                "height": int(img.shape[0]),
                "captured_at": datetime.now(UTC).isoformat(),
            },
        )
        logger.info(
            "[AGENT] 截图流: 已发送 frame device=%s type=%s hwnd=%s size=%dx%d bytes=%d",
            device.device_id,
            device_type,
            hwnd,
            img.shape[1],
            img.shape[0],
            len(image_base64),
        )
        return True

    @staticmethod
    def _infer_device_type(device: Any) -> str:
        """Infer a backend-compatible device_type from the device class."""
        explicit = getattr(device, "device_type", "") or ""
        if explicit:
            return explicit
        class_name = type(device).__name__.lower()
        if "windows" in class_name:
            return "windows"
        if any(k in class_name for k in ("adb", "emulator", "android")):
            return "emulator"
        return ""

    @staticmethod
    def _get_device_hwnd(device: Any) -> str:
        """Return a hex hwnd string when the device exposes one."""
        hwnd = None
        if hasattr(device, "hwnd"):
            try:
                hwnd = device.hwnd
            except Exception:
                hwnd = None
        if hwnd is None and hasattr(device, "_window_mgr"):
            hwnd = getattr(device._window_mgr, "hwnd", None)
        return hex(hwnd) if hwnd else ""
