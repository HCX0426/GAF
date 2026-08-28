import asyncio
import logging
import os
import uuid

from celery import shared_task
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


async def _group_send_with_timeout(channel_layer, group, message, timeout=5.0):
    await asyncio.wait_for(channel_layer.group_send(group, message), timeout=timeout)


def safe_group_send(group, message, timeout=5.0):
    """Send a channels group message with a hard timeout (TD-396 follow-up).

    A wedged channels_redis connection (half-open TCP: server closed but the
    client socket is unaware) makes ``group_send`` await forever — and the
    coroutine can ignore cooperative cancellation. So we run it on a shared
    worker thread and apply a wall-clock deadline: on timeout the caller
    gets a ``TimeoutError`` while the stuck worker is abandoned, keeping the
    request thread alive instead of freezing the backend.
    """
    from gaf_core.async_utils import call_async_with_timeout

    async def _send():
        channel_layer = get_channel_layer()
        await _group_send_with_timeout(channel_layer, group, message, timeout)

    call_async_with_timeout(_send, timeout=timeout)


def _build_device_info_for_execution(execution):
    """Build device_info dict from execution.device (window-centric).

    Reads device metadata from the TaskExecution's device FK rather than
    the legacy task.device_mappings join. This is the window-centric path:
    a TaskExecution records exactly which Device it ran on, so the agent
    receives authoritative screenshot/input/window metadata for that
    specific device instead of a guess from the task's M2M device list.

    Returns:
        dict or None: Device metadata suitable for agent _resolve_target_device,
            or None when the execution has no bound device (legacy data
            predating the device FK).
    """
    dev = execution.device
    if not dev:
        return None

    extra = dev.extra_info or {}
    window_title = extra.get("window_title", "") or ""
    if not window_title and dev.device_type == "windows":
        window_title = dev.name or ""

    # v3 §2.8.1: resolve 'auto' fields against GameProfile defaults before
    # dispatching to agent. Agent's _derive_methods_from_control_mode does
    # not understand 'auto' control_mode, so we hand it a concrete value.
    from agents.models import resolve_device_methods
    resolved = resolve_device_methods(dev)
    control_mode = resolved['control_mode']
    # If control_mode is still 'auto' (no GameProfile default), fall back
    # to pseudo_background which is the safest game-automation default.
    if control_mode == 'auto':
        control_mode = 'pseudo_background'
    screenshot_method = resolved['screenshot_method']
    if not screenshot_method or screenshot_method == 'auto':
        screenshot_method = dev.screenshot_method or 'auto'
    input_method = resolved['input_method']
    if not input_method or input_method == 'auto':
        input_method = dev.input_method or 'auto'

    return {
        "id": dev.id,
        "device_type": dev.device_type,
        "name": dev.name,
        "window_handle": dev.window_handle or "",
        "window_title": window_title,
        "screenshot_method": screenshot_method,
        "input_method": input_method,
        "control_mode": control_mode,
        "adb_serial": dev.adb_serial or "",
        "emulator": dev.emulator or "",
    }


@shared_task(bind=True, max_retries=3, acks_late=True)
def dispatch_task(self, execution_id, start_step_index=0, previous_results=None, trace_id="", force_agent_id=None):
    """将任务分配给可用且能力匹配的 Agent 执行。

    根据 task_definition 推断任务所需能力，从空闲 Agent 中
    选择能力匹配的 Agent 分配任务。若无匹配 Agent 则重试。

    Args:
        execution_id: TaskExecution 的 ID
        start_step_index: Task 1.1 (B7 重试单节点, P0-1). 跳过前 N 个
            节点的实际执行, 从第 N+1 个节点开始跑. 默认 0 = 不跳过.
            由 retry_from_step action 传入, 让 agent 重试单节点而非整个 pipeline.
        previous_results: Task 1.1. 之前成功节点的 result 列表 (list[dict]),
            长度应等于 ``start_step_index``. 让最终 PipelineResult.step_results
            完整 (用户能看到前驱节点输出), 且跳过节点的分支决策能保留原选择.
            默认 None = 完整重跑 (向后兼容).
        trace_id: F21 (spec 2026-07-30-debug-directory-restructure). Celery 边界
            显式传递的 trace_id, 由调用方从 HTTP 请求 ContextVar 捕获后传入.
            Celery worker 线程中 ContextVar 不会从 HTTP 请求线程传播, 需显式传递.
        force_agent_id: B1 (2026-08-27). TaskChain 固定 Agent 语义 —
            非 None 时跳过 AgentSelector 的能力匹配选择, 直接派发给该
            Agent (execution.agent 已由调用方绑定). 用于 chain 节点串行
            派发, 保证整条链在同一个 Agent 上执行.
    """
    # N192-A2 fix (2026-07-28, BD2 get_email 测试发现):
    # Bind execution_id to tracing context so FileLogHandler archives
    # WARNING+ logs to debug/YYYYMMDD/<pipeline>/<HHMMSS>_<suffix>/run.log instead of the
    # _global catch-all. Without this, AI debugging has no per-execution
    # log file to inspect — all execution logs are lost in the global log.
    # The contextvar is thread-local + asyncio-safe; Celery workers each
    # get their own context so concurrent dispatch_task calls don't collide.
    from gaf_core.tracing.context import current_execution_id, current_trace_id

    from agents.models import Agent
    from tasks.agent_selector import AgentSelector
    from tasks.concurrency_controller import get_default_controller
    from tasks.models import TaskExecution
    token_exec = current_execution_id.set(str(execution_id))

    # F21: 如果调用方显式传了 trace_id, 设到 ContextVar 中.
    # 这样 serialize_frame (从 ContextVar 取 trace_id) 和
    # FileLogHandler (从 ContextVar 取 trace_id 打日志) 都能正确工作.
    token_trace = None
    if trace_id:
        token_trace = current_trace_id.set(trace_id)

    try:
        execution = TaskExecution.objects.select_related(
            'task',
            'task__resource_pack',  # N197-8: for resource pack resolution
            'pipeline',  # spec-2026-08-02: Pipeline 执行需要 pipeline FK
            'device',
            'game_account',
            'game_account__resource_pack',
        ).get(id=execution_id)
    except TaskExecution.DoesNotExist:
        current_execution_id.reset(token_exec)
        if token_trace is not None:
            current_trace_id.reset(token_trace)
        return

    # B3-4 (spec 2026-07-30-debug-directory-restructure): 从 ContextVar 取 trace_id
    # 持久化到 TaskExecution.trace_id 字段. 此处只 set 不 save, 后续 execution.save()
    # 调用 (无可用 Agent / 并发已满 / RUNNING 状态切换) 会自动持久化 trace_id,
    # 保证所有 early return 路径都保留 trace_id 便于反查.
    ctx_trace_id_b3_4 = current_trace_id.get() or ""
    execution.trace_id = ctx_trace_id_b3_4

    # spec-2026-08-02-backend-execution-unification:
    # 支持 task=None 的 Pipeline 执行，从 execution.pipeline 取元数据
    task = execution.task
    pipeline = execution.pipeline
    if task is None and pipeline is not None:
        task_name = pipeline.name or ""
        task_id = pipeline.id
        task_definition = pipeline.graph_data or {}
        execution_mode = 'pipeline'
        params_config = {}
        has_resource_pack = False
        retry_policy = {"max_retries": 3, "retry_delay": 30, "backoff": "linear"}
        preflight_config = ["device_online", "resource_ready"]
        recovery_config = {
            "step_max_retries": 3, "task_max_retries": 2,
            "app_restart_on_crash": True, "device_reboot_on_disconnect": False,
        }
    else:
        task_name = task.name or ""
        task_id = task.id
        task_definition = task.task_definition or {}
        execution_mode = task.execution_mode or 'pipeline'
        params_config = task.params_config or {}
        has_resource_pack = bool(task.resource_pack_id)
        retry_policy = task.retry_policy or {
            "max_retries": 3, "retry_delay": 30, "backoff": "linear",
        }
        preflight_config = task.preflight_config or [
            "device_online", "account_valid", "resource_ready",
        ]
        recovery_config = task.recovery_config or {
            "step_max_retries": 3, "task_max_retries": 2,
            "app_restart_on_crash": True, "device_reboot_on_disconnect": False,
        }

    # N197: 设备级串行执行检查 — 同一窗口同时只能执行一个任务.
    # 如果目标设备已有 RUNNING 状态的执行记录, 将当前执行留为 PENDING 并重试.
    if execution.device_id is not None:
        device_busy = TaskExecution.objects.filter(
            device_id=execution.device_id,
            status=TaskExecution.Status.RUNNING,
        ).exclude(id=execution.id).exists()
        if device_busy:
            execution.status = TaskExecution.Status.PENDING
            execution.error_message = "设备忙: 同一设备已有其他任务正在执行，等待串行执行"
            execution.save()
            logger.info(
                "Execution %s 等待设备串行执行 (device=%s), 由调度器补发",
                execution.id, execution.device_id,
            )
            current_execution_id.reset(token_exec)
            if token_trace is not None:
                current_trace_id.reset(token_trace)
            # 设备忙时不走 celery retry: eager 模式下 retry 会在请求线程内
            # 同步 sleep 30s×3 次, 阻塞 HTTP 请求直到看起来像 backend 挂死.
            # 执行已置为 PENDING, 由 scheduler 的 retry_pending_executions
            # (每 60s) 在设备空闲后自动重新派发.
            return

    # N197: allowed_device_types 校验 — 确认设备类型在游戏档案允许的列表内.
    # 防御性检查: 即便 bind_game_profile 已拦截, dispatch 时仍校验,
    # 防止配置被绕过(如: 手动改 DB / 旧数据同步 / 自动绑定延迟).
    if execution.device_id is not None:
        from agents.models import Device as _Device
        _dev = _Device.objects.select_related('game_profile').filter(
            id=execution.device_id,
        ).first()
        if (
            _dev and _dev.game_profile
            and _dev.game_profile.allowed_device_types
            and _dev.device_type not in _dev.game_profile.allowed_device_types
        ):
            execution.status = TaskExecution.Status.FAILED
            execution.error_message = (
                f"设备类型 \"{_dev.device_type}\" 不被游戏档案 "
                f"\"{_dev.game_profile.game_name}\" 允许。"
                f"允许的类型: {_dev.game_profile.allowed_device_types}"
            )
            # N192: 设置 error_code 让前端能按错误码分类展示
            from gaf_core.error_codes import NodeErrorCode
            execution.error_code = NodeErrorCode.PARAM_INVALID.value
            execution.save()
            logger.warning(
                "Execution %s 因 allowed_device_types 不匹配而失败 "
                "(device_type=%s, profile=%s, allowed=%s)",
                execution.id, _dev.device_type,
                _dev.game_profile_id, _dev.game_profile.allowed_device_types,
            )
            current_execution_id.reset(token_exec)
            if token_trace is not None:
                current_trace_id.reset(token_trace)
            return

    selector = AgentSelector()
    # N197 fix: 使用本地 task_definition 变量而非 execution.task.task_definition，
    # 因为 pipeline-only 执行（task=None）时 execution.task 为 None。
    required_capabilities = selector.get_required_capabilities(
        task_definition
    )

    available_agents = list(
        Agent.objects.filter(status__in=[Agent.Status.IDLE, Agent.Status.ONLINE])
    )

    if not available_agents:
        execution.status = TaskExecution.Status.FAILED
        execution.error_message = "无可用 Agent"
        # N192: 设置 error_code 让前端能按错误码分类展示
        from gaf_core.error_codes import NodeErrorCode
        execution.error_code = NodeErrorCode.UNKNOWN.value
        execution.save()
        return

    # Agent 并发控制器检查 — 仅对无设备绑定的任务（多设备场景）生效。
    # 单窗口场景（execution.device_id 非空）由设备级串行检查（L129-154）保证
    # "同一窗口同时只能一个任务"，并发控制器是多余的，且存在跨进程状态不同步问题
    # （controller.assign 在 Celery worker 进程，controller.release 在 Daphne ASGI 进程，
    #  内存控制器下两个进程的实例隔离，导致 slot 永久泄漏）。
    # N197 fix: 有设备绑定时跳过并发控制器检查。
    if execution.device_id is None:
        controller = get_default_controller()
        assignable_agents = [a for a in available_agents if controller.can_assign(a.agent_id)]
        if not assignable_agents:
            execution.status = TaskExecution.Status.PENDING
            execution.error_message = "所有 Agent 并发已满，等待重试"
            execution.save()
            logger.info(
                "Execution %s 等待并发槽位 (all %d agents at cap), 调度重试",
                execution.id, len(available_agents),
            )
            current_execution_id.reset(token_exec)
            if token_trace is not None:
                current_trace_id.reset(token_trace)
            # N197 fix: 不传 execution_id 到 kwargs — 它是位置参数
            raise self.retry(
                kwargs={
                    "start_step_index": start_step_index,
                    "previous_results": previous_results,
                    "trace_id": trace_id or "",
                    "force_agent_id": force_agent_id or "",
                },
                countdown=30,
                exc=Exception("All agents at concurrency cap"),
            )
    else:
        # 有设备绑定：所有可用 agent 都可选，设备级串行已保证不冲突
        assignable_agents = available_agents

    # B1 (2026-08-27): force_agent_id 固定 Agent 语义 (TaskChain 串行派发) —
    # 跳过 AgentSelector 的能力匹配, 直接使用调用方预选的 Agent。设备忙/
    # 并发/能力检查仍在上方统一执行, chain 路径获得与普通任务相同的保障.
    if force_agent_id:
        forced = Agent.objects.filter(agent_id=force_agent_id).first()
        if forced is None or forced.status not in (
            Agent.Status.ONLINE,
            Agent.Status.IDLE,
            Agent.Status.BUSY,
        ):
            execution.status = TaskExecution.Status.FAILED
            execution.error_message = f"指定的 Agent {force_agent_id} 不存在或离线"
            from gaf_core.error_codes import NodeErrorCode
            execution.error_code = NodeErrorCode.UNKNOWN.value
            execution.save()
            logger.info(
                "Execution %s force_agent_id=%s unavailable, marked FAILED",
                execution.id, force_agent_id,
            )
            return
        agent = forced
    else:
        agent = selector.select(assignable_agents, required_capabilities)

    if agent is None:
        cap_str = ", ".join(required_capabilities)
        execution.status = TaskExecution.Status.FAILED
        execution.error_message = f"无具备所需能力 ({cap_str}) 的 Agent"
        # N192: 设置 error_code 让前端能按错误码分类展示
        from gaf_core.error_codes import NodeErrorCode
        execution.error_code = NodeErrorCode.UNKNOWN.value
        execution.save()
        return

    execution.agent = agent
    execution.status = TaskExecution.Status.RUNNING
    execution.save()

    agent.status = Agent.Status.BUSY
    agent.save()

    # Mark the target device as BUSY so the frontend / device list view
    # reflects per-device execution state in multi-instance scenarios.
    # _restore_device_status (called from the 5 release paths) flips it
    # back to ONLINE once the execution finalizes AND no other RUNNING
    # execution shares the device.
    if execution.device_id:
        from agents.models import Device
        Device.objects.filter(id=execution.device_id).update(status=Device.Status.BUSY)
        logger.info(
            "Device %s marked BUSY for execution %s",
            execution.device_id, execution.id,
        )

    # Acquire the concurrency slot AFTER the agent is marked BUSY so the
    # release path (consumers / force-terminate) always has an agent_id
    # paired with this execution.id.
    # N197: 仅当无设备绑定时（controller 已创建）才 assign，有设备绑定由
    # 设备级串行检查保证串行，跳过 controller 避免跨进程状态泄漏。
    if execution.device_id is None:
        controller.assign(agent.agent_id, str(execution.id))
        logger.info(
            "ConcurrencyController: assigned execution %s to agent %s (load=%d/%d)",
            execution.id, agent.agent_id,
            controller.get_agent_load(agent.agent_id),
            controller.max_tasks_per_agent,
        )

    # N194 归一化 + 双写 (2026-07-28):
    # 在发送 task.assign 之前, 主动创建归一化执行目录
    # <DEBUG_DIR>/<YYYYMMDD_HHMMSS>_<safe_task_name>_<exec_id_suffix8>/ 并写
    # meta.json. 这样:
    #   1. 后续 backend FileLogHandler.emit() 反查该目录即可命中 (不再降级 _global)
    #   2. agent 接收 payload.debug_dir 后, 用同一完整路径写 structured.jsonl
    #      和 screenshots/, 双方写入同一目录, 日志和图片"一起看"
    #   3. backend 本地镜像 (backend/debug/<exec_dir>/run.log) 由 FileLogHandler
    #      双写实现, 此处只创建归一化目录
    from django.conf import settings
    from django.utils import timezone
    from gaf_core.debug_path import build_execution_debug_dir, write_meta_json

    exec_debug_dir = build_execution_debug_dir(
        debug_dir_root=getattr(settings, "DEBUG_DIR", "./debug"),
        execution_id=str(execution.id),
        task_name=task_name,
        start_time=timezone.now(),
    )
    write_meta_json(
        exec_debug_dir,
        execution_id=str(execution.id),
        task_id=task_id,
        task_name=task_name,
        pipeline_name=execution_mode,
        start_time=timezone.now(),
        status="running",
        agent_id=agent.agent_id,
        trace_id=ctx_trace_id_b3_4,
        extra={
            "start_step_index": start_step_index,
            "has_previous_results": bool(previous_results),
        },
    )

    # N194 双写 (2026-07-28; 嵌套结构 2026-07-29): 同步创建 backend 本地镜像目录,
    # 目录结构与归一化目录完全一致 (date/pipeline/HHMMSS_suffix 三层嵌套),
    # 让 FileLogHandler 反查时能命中. 镜像目录只放 run.log, 不重复 screenshots
    # (图片只在归一化目录, 节省磁盘).
    # BASE_DIR = backend/ 工作目录; 镜像根 = <BASE_DIR>/debug/
    # 用 relpath 保留嵌套层级 (旧版 os.path.basename 只取一层, 嵌套结构下会丢 date/pipeline 两层).
    debug_dir_root_value = getattr(settings, "DEBUG_DIR", "./debug")
    rel_exec_path = os.path.relpath(exec_debug_dir, debug_dir_root_value)
    backend_mirror_dir = os.path.join(
        str(settings.BASE_DIR), "debug", rel_exec_path,
    )
    write_meta_json(
        backend_mirror_dir,
        execution_id=str(execution.id),
        task_id=task_id,
        task_name=task_name,
        pipeline_name=execution_mode,
        start_time=timezone.now(),
        status="running",
        agent_id=agent.agent_id,
        trace_id=ctx_trace_id_b3_4,
        extra={
            "mirror_of": exec_debug_dir,
            "note": "backend local mirror; screenshots live only in unified dir",
        },
    )

    # B3-4 (spec 2026-07-30-debug-directory-restructure): 创建 BackendTaskLogger
    # 记录 task_started 事件到 debug/YYYYMMDD/backend/tasks/<pipeline>/HH/execution.jsonl.
    # 与 agent 的 structured.jsonl 平行布局, 让 backend 任务级事件和 agent 执行事件
    # 在同一五层目录结构下可被一同浏览. trace_id 全链路贯穿到 JSONL 行.
    # <pipeline> 用 task_name 分组 (与 agent exec_dir 的 safe_task_name 一致),
    # 而非 execution_mode —— 后者是固定值 ("pipeline"), 会让所有任务的
    # execution.jsonl 混在同一个 pipeline/ 目录下无法区分.
    from gaf_core.task_logger import BackendTaskLogger
    task_logger_b3_4 = BackendTaskLogger(
        debug_root=debug_dir_root_value,
        pipeline_name=task_name,
        trace_id=ctx_trace_id_b3_4,
        execution_id=str(execution.id),
    )
    task_logger_b3_4.log(
        "task_started",
        payload={
            "task_id": task_id,
            "task_name": task_name,
            "agent_id": agent.agent_id,
            "start_step_index": start_step_index,
            "has_previous_results": bool(previous_results),
        },
    )

    # Build device_info from execution.device (window-centric) — the execution
    # records exactly which device it runs on, replacing the legacy guess from
    # task.device_mappings. Returns None for legacy executions without device FK.
    device_info = _build_device_info_for_execution(execution)

    # Read resource_pack from Task.resource_pack (primary) or
    # GameAccount.resource_pack (fallback, window-centric dead-field landing).
    # N197-8: Task.resource_pack is the primary source — the task directly
    # associates with a resource pack for runtime template loading.
    # GameAccount.resource_pack serves as fallback for legacy tasks that
    # haven't been migrated to the new FK.
    resource_pack = None
    # N197 fix: has_resource_pack 在 pipeline-only 执行时为 False，
    # 避免 execution.task 为 None 时访问 resource_pack_id 崩溃。
    if has_resource_pack and execution.task.resource_pack_id:
        rp = execution.task.resource_pack
        resource_pack = {
            'id': rp.id,
            'name': rp.name,
            'version': rp.version,
            'directory_path': rp.directory_path,
            'config_data': getattr(rp, 'config_data', {}),
            'server_region': execution.game_account.server_region if execution.game_account else 'cn',
        }
    elif execution.game_account and execution.game_account.resource_pack:
        rp = execution.game_account.resource_pack
        resource_pack = {
            'id': rp.id,
            'name': rp.name,
            'version': rp.version,
            'directory_path': rp.directory_path,
            'config_data': getattr(rp, 'config_data', {}),
            'server_region': execution.game_account.server_region if execution.game_account else 'cn',
        }

    try:
        safe_group_send(
            f"agent_{agent.agent_id}",
            {
                "type": "task.assign",
                "payload": {
                    "execution_id": str(execution.id),
                    "task_id": task_id,
                    "task_name": task_name,
                    "execution_mode": execution_mode,
                    "task_definition": task_definition,
                    "params": params_config,
                    "timeout": 300,
                    "retry_policy": retry_policy,
                    "preflight_checks": preflight_config,
                    "recovery_config": recovery_config,
                    "device_info": device_info,
                    # N194 归一化 (2026-07-28): 归一化执行目录完整路径.
                    # agent 用此路径写 structured.jsonl 和 screenshots/,
                    # 与 backend FileLogHandler 写的 run.log 同目录.
                    # 空字符串/null 时 agent 兜底用本地 ./debug (向后兼容).
                    "debug_dir": exec_debug_dir,
                    "debug_mode": settings.GAF_DEBUG,
                    "game_account_id": execution.game_account_id,
                    "game_account_name": (
                        execution.game_account.username
                        if execution.game_account else None
                    ),
                    "resource_pack": resource_pack,
                    # Task 1.1 (B7 重试单节点, P0-1): retry-from-step 参数.
                    # 0 / None 表示完整重跑 (默认, 向后兼容). > 0 + list[dict] 表示
                    # 从指定节点重试, agent 跳过前 N 个节点 + 用 previous_results
                    # 保留前驱节点的 result 与分支决策. 由 retry_from_step action
                    # 在创建新 execution 时透传进来.
                    "start_step_index": start_step_index,
                    "previous_results": previous_results,
                },
            },
        )
    except Exception as exc:
        # TD-396 跟进: group_send 可能在 channels_redis 半开连接上无限挂起;
        # safe_group_send 已用 wait_for 限制. 走到这里说明派发确实失败 —
        # 标记 FAILED + 释放 agent/device/并发槽, 且绝不 re-raise (eager 模式
        # 下 celery retry 会在请求线程内同步 sleep, 看起来像 backend 挂死).
        logger.error(
            "派发失败 (execution %s): 群发 task.assign 到 %s 失败: %s",
            execution.id, f"agent_{agent.agent_id}", exc,
        )
        from gaf_core.error_codes import NodeErrorCode
        execution.status = TaskExecution.Status.FAILED
        execution.error_message = f"派发失败: 无法下发任务给 Agent ({exc})"
        execution.error_code = NodeErrorCode.UNKNOWN.value
        from django.utils import timezone as _tz
        execution.completed_at = _tz.now()
        execution.save()
        # 释放 agent BUSY + 设备 BUSY + 并发槽位
        try:
            Agent.objects.filter(id=agent.id, status=Agent.Status.BUSY).update(
                status=Agent.Status.IDLE
            )
        except Exception:  # noqa: BLE001 — best-effort cleanup
            logger.warning("dispatch fail: agent %s 状态释放失败", agent.agent_id)
        try:
            from tasks.heartbeat import _restore_device_status
            _restore_device_status(execution)
        except Exception:  # noqa: BLE001
            logger.warning("dispatch fail: device %s 状态释放失败", execution.device_id)
        try:
            from tasks.services.monitor_service import _release_concurrency_slot
            _release_concurrency_slot(execution.agent_id, str(execution.id))
        except Exception:  # noqa: BLE001
            logger.warning("dispatch fail: 并发槽位释放失败 (agent=%s)", execution.agent_id)
        current_execution_id.reset(token_exec)
        if token_trace is not None:
            current_trace_id.reset(token_trace)
        return

    logger.info(
        "任务 %s 已分配给 Agent %s (所需能力: %s)",
        execution.id, agent.agent_id, required_capabilities,
    )
    # S1 (2026-08-16): 派发确认 — 记录 dispatch_sent_at 到 execution_snapshot.
    # check_dispatch_acks beat 任务扫描 RUNNING + 无 dispatch_ack_at 的执行,
    # 超时未确认 (agent 在线 → 重派, 离线 → fail). 解决"健康 agent 下执行
    # 永久 RUNNING 卡死" (group_send 无队列无 ack, 帧丢失静默).
    snap = dict(execution.execution_snapshot or {})
    snap["dispatch_sent_at"] = timezone.now().isoformat()
    snap["dispatch_attempts"] = int(snap.get("dispatch_attempts") or 0) + 1
    execution.execution_snapshot = snap
    execution.save(update_fields=["execution_snapshot"])
    # N192-A2: Reset contextvar after dispatch so subsequent Celery tasks
    # in the same worker don't accidentally log to this execution's file.
    current_execution_id.reset(token_exec)
    if token_trace is not None:
        current_trace_id.reset(token_trace)


@shared_task(acks_late=True, max_retries=3, retry_backoff=30)
def execute_scheduled_task(scheduled_task_id):
    """执行定时任务，创建 TaskExecution 并分发。

    Args:
        scheduled_task_id: ScheduledTask 的 ID
    """
    from django.utils import timezone

    from tasks.models import ScheduledTask, TaskExecution

    try:
        scheduled_task = ScheduledTask.objects.get(id=scheduled_task_id)
    except ScheduledTask.DoesNotExist:
        logger.error("ScheduledTask %s 不存在", scheduled_task_id)
        return

    task = scheduled_task.task
    custom_task = scheduled_task.custom_task

    if task:
        execution = TaskExecution.objects.create(
            task=task,
            status=TaskExecution.Status.PENDING,
        )
        dispatch_task.delay(execution.id, trace_id=str(uuid.uuid4()))
    elif custom_task:
        logger.info("自定义定时任务 %s 触发执行", custom_task.name)

    scheduled_task.last_executed_at = timezone.now()
    scheduled_task.save(update_fields=['last_executed_at', 'updated_at'])


@shared_task(acks_late=True, max_retries=3)
def retry_pending_executions():
    """扫描 PENDING 超过 5 分钟的执行，自动重试调度。

    由 Celery Beat 每 60s 触发，处理因调度延迟、Celery Worker 未启动、
    设备忙等临时原因卡在 PENDING 的执行。最大重试 5 次后标记 FAILED。
    """
    from datetime import timedelta

    from django.utils import timezone

    from tasks.models import TaskExecution

    stuck = TaskExecution.objects.filter(
        status=TaskExecution.Status.PENDING,
        # 1 分钟门槛：设备忙/调度延迟等临时原因留 PENDING 的执行尽快补发
        # (此前 5 分钟会让并发排队任务长时间等待, 且与 Beat 周期 60s 不匹配).
        created_at__lt=timezone.now() - timedelta(minutes=1),
        recovery_attempts__lt=5,  # 最大重试 5 次
    )
    for exec in stuck:
        exec.recovery_attempts += 1
        exec.save(update_fields=['recovery_attempts'])
        dispatch_task.delay(exec.id)
        logger.info(
            "自动重试执行 %s (第 %d 次)", exec.id, exec.recovery_attempts,
        )


@shared_task(acks_late=True, max_retries=3, retry_backoff=60)
def sync_scheduled_tasks():
    """同步数据库中的定时任务到 Celery Beat。"""
    from tasks.beat import BeatSchedulerService

    BeatSchedulerService.sync_scheduled_tasks()


@shared_task(acks_late=True)
def flush_expired_tokens():
    """清理已过期的 JWT token (OutstandingToken 表)。

    rest_framework_simplejwt 5.5.1 版本将 flushexpiredtokens 改为 management
    command (token_blacklist/management/commands/flushexpiredtokens.py) 而非
    Celery task。此包装任务通过 call_command 调用 management command 实现
    定时清理，同时兼容 APScheduler (eager 模式) 和 Celery Beat (celery 模式)。
    """
    from django.core.management import call_command

    call_command("flushexpiredtokens")


@shared_task(acks_late=True)
def archive_old_executions():
    """归档 30 天前的终态 TaskExecution 记录。

    TD-351: 将已完成超过 30 天且处于终态 (SUCCESS/FAILED/CANCELLED/
    FORCE_TERMINATED) 的执行记录标记为已归档，并清理 log 大文本字段。

    Returns:
        dict: 归档统计信息

    幂等性: WHERE is_archived=False 确保重复执行不会重复归档。
    """
    from datetime import timedelta

    from django.utils import timezone

    from tasks.models import TaskExecution

    terminal_statuses = [
        TaskExecution.Status.SUCCESS,
        TaskExecution.Status.FAILED,
        TaskExecution.Status.CANCELLED,
        TaskExecution.Status.FORCE_TERMINATED,
    ]

    cutoff = timezone.now() - timedelta(days=30)
    start = timezone.now()

    # 筛选可归档的记录
    qs = TaskExecution.objects.filter(
        completed_at__lt=cutoff,
        status__in=terminal_statuses,
        is_archived=False,
    )

    archive_count = qs.count()
    if archive_count == 0:
        elapsed = (timezone.now() - start).total_seconds()
        result = {
            "archived_count": 0,
            "cleared_log_count": 0,
            "elapsed_seconds": round(elapsed, 3),
        }
        logger.info("[archive_old_executions] 无记录需要归档: %s", result)
        return result

    # 批量归档: 标记 + 清理 log
    updated = qs.update(
        is_archived=True,
        archived_at=timezone.now(),
        log="",
    )

    elapsed = (timezone.now() - start).total_seconds()
    result = {
        "archived_count": archive_count,
        "cleared_log_count": updated,
        "elapsed_seconds": round(elapsed, 3),
    }
    logger.info(
        "[archive_old_executions] 完成: 归档 %d 条, 清理 %d 个 log 字段, 耗时 %.3fs",
        archive_count, updated, elapsed,
    )
    return result
