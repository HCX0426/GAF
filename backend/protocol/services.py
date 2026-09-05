"""Protocol-layer service functions isolating cross-app model imports.

TD-259 #29: ``protocol.consumers`` and ``protocol.middleware`` previously
imported ``agents.models.Agent/Device`` and ``tasks.models.ExecutionStep/
TaskExecution`` at module top level. This coupled the protocol layer to
business-domain models, making the protocol layer hard to test in
isolation and creating circular-import risk (agents.models imports from
protocol.constants, so importing agents.models from protocol.consumers
closes a loop).

This module mirrors the spec-29i pattern (``tasks/services.py`` commit
5a0e76aa, TD-265): cross-app model imports are isolated inside service
function bodies (inline imports, loaded at call time). Consumers /
middleware call these service functions instead of touching
``agents.models`` / ``tasks.models`` directly.

Local protocol models (``WorkerSession``, ``MessageFrameLog``) stay
imported at the top of consumers.py — same-app imports are not a
coupling concern.

Non-model cross-app imports (e.g. ``agents.game_binding``) are kept at
the module top here because they are service functions, not models, and
do not create the model-layer coupling TD-259 targets.
"""

import contextlib
import logging
import uuid
from datetime import timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone as django_timezone
from workers.game_binding import bind_game_profile_by_title

logger = logging.getLogger(__name__)


class ProtocolBindingError(Exception):
    """Raised by protocol service functions on validation/lookup failures.

    Carries a ``status_code`` so the consumer/view layer can map service
    errors to WebSocket close codes / HTTP responses without inspecting
    the exception type. Mirrors ``tasks.services.TaskBindingError``
    (spec-29i, TD-265).

    The optional ``extra`` dict lets the service layer forward context
    (e.g. the offending ``execution_id``) so the caller can preserve the
    original response shape without re-querying the cross-app model.
    """

    def __init__(self, message, status_code=400, extra=None):
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}
        super().__init__(message)


# ---------------------------------------------------------------------------
# Agent lookups (agents.models.Agent)
# ---------------------------------------------------------------------------

def get_agent_by_agent_id(agent_id):
    """Look up an Agent by its ``agent_id`` string identifier.

    Args:
        agent_id: ``Agent.agent_id`` string (e.g. "agent-001").

    Returns:
        ``Agent`` instance or ``None`` if not found / on DB error.
    """
    if not agent_id:
        return None
    from workers.models import Worker  # cross-app import isolated (TD-259 #29)
    try:
        return Worker.objects.filter(agent_id=agent_id).first()
    except Exception as exc:
        logger.warning(
            "get_agent_by_agent_id failed: agent_id=%s, err=%s",
            agent_id, exc,
        )
        return None


def get_agent_by_token_hash(token_h):
    """Look up an Agent by its hashed connection token.

    Used by ``protocol.middleware.TokenAuthMiddleware`` to resolve the
    Agent from the ``?token=`` query string or ``Authorization`` header.

    Args:
        token_h: Hashed token string (output of ``hash_token``).

    Returns:
        ``Worker`` instance or ``None`` if not found.
    """
    if not token_h:
        return None
    from workers.models import Worker  # cross-app import isolated (TD-259 #29)
    try:
        return Worker.objects.get(worker_token_hash=token_h)
    except Worker.DoesNotExist:
        return None


def get_local_agent():
    """Look up the local Agent record (``is_local=True``).

    Used by ``protocol.middleware.TokenAuthMiddleware`` for the opt-in
    localhost bypass path (``GAF_ALLOW_LOCALHOST_BYPASS=1``).

    Returns:
        ``Agent`` instance or ``None`` if no local Agent exists.
    """
    from workers.models import Worker  # cross-app import isolated (TD-259 #29)
    return Worker.objects.filter(is_local=True).first()


def update_or_create_agent_with_session(agent_id, payload):
    """Create or update Agent + WorkerSession records on agent.register.

    Mirrors the legacy ``WorkerConsumer._db_create_or_update_agent``
    behavior: upserts the Agent row (hostname, IP, OS info, capabilities,
    status=ONLINE, last_heartbeat, is_local), then upserts an
    WorkerSession keyed by hostname.

    Args:
        agent_id: ``Agent.agent_id`` string identifier.
        payload: Registration payload dict (hostname / ip_address /
            os_info / capabilities / resource_quota / is_local).

    Returns:
        str: The WorkerSession's UUID ``agent_id`` string.
    """
    from workers.models import Worker  # cross-app import isolated (TD-259 #29)

    # WorkerSession is a local protocol model; imported inline alongside
    # Agent so the service function is self-contained.
    from protocol.models import WorkerSession

    capabilities = payload.get("capabilities", {})
    resource_quota = payload.get("resource_quota", {})

    agent_data = {
        "hostname": payload.get("hostname") or f"agent-{agent_id}",
        "ip_address": payload.get("ip_address") or None,
        "os_info": payload.get("os_info", ""),
        "capabilities": capabilities,
        "status": Worker.Status.ONLINE,
        "last_heartbeat": django_timezone.now(),
        "is_local": payload.get("is_local", True),
    }

    if resource_quota:
        agent_data["capabilities"]["resource_quota"] = resource_quota

    agent, created = Worker.objects.update_or_create(
        agent_id=agent_id,
        defaults=agent_data,
    )
    if created:
        logger.info("数据库创建新 Agent: agent_id=%s", agent_id)

    hostname = agent_data["hostname"]
    session_defaults = {
        "name": hostname,
        "hostname": hostname,
        "ip_address": agent_data.get("ip_address"),
        "capabilities": capabilities,
        "resource_quota": resource_quota,
        "status": WorkerSession.Status.ONLINE,
        "last_heartbeat": django_timezone.now(),
        "connected_at": django_timezone.now(),
    }

    session, _ = WorkerSession.objects.update_or_create(
        name=hostname,
        defaults=session_defaults,
    )
    return str(session.agent_id)


def update_agent_heartbeat(agent_id, payload, channel=None):
    """Update Agent's heartbeat timestamp + resource stats.

    Args:
        agent_id: ``Agent.agent_id`` string identifier.
        payload: Heartbeat payload dict (status / stats{cpu,memory,fps}).
        channel: current WS ``channel_name``. When given, the UPDATE carries
            a ``active_channel=channel`` guard — a zombie/stale consumer whose
            channel no longer owns the agent writes 0 rows (spec P4).
    """
    from workers.models import Worker  # cross-app import isolated (TD-259 #29)

    agent_status = payload.get("status", "idle")

    status_map = {
        "idle": Worker.Status.IDLE,
        "busy": Worker.Status.BUSY,
        "online": Worker.Status.ONLINE,
    }

    update_fields = {
        "last_heartbeat": django_timezone.now(),
        "status": status_map.get(agent_status, Worker.Status.IDLE),
        "active_channel": channel,
    }

    stats = payload.get("stats", {})
    cpu = stats.get("cpu")
    memory = stats.get("memory")
    fps = stats.get("fps")
    if cpu is not None and cpu >= 0:
        update_fields["cpu_usage"] = cpu
    if memory is not None and memory >= 0:
        update_fields["memory_usage"] = memory
    if fps is not None and fps >= 0:
        update_fields["screenshot_fps"] = fps

    qs = Worker.objects.filter(agent_id=agent_id)
    if channel:
        # 只允许"现任 channel"写入 — 僵尸连接此条件不满足 → 0 行, 不污染状态
        qs = qs.filter(active_channel=channel)
    qs.update(**update_fields)


def set_agent_offline(agent_id, channel=None):
    """Mark an Agent as OFFLINE and cancel its running executions.

    N197 fix: when an agent disconnects (WS close / heartbeat timeout),
    any RUNNING executions assigned to it stay in ``running`` status
    forever, blocking the device from new tasks. This function now also
    fails those executions and restores the device status.

    Args:
        agent_id: ``Agent.agent_id`` string identifier.
    """
    from workers.models import Worker  # cross-app import isolated (TD-259 #29)

    from tasks.models import TaskExecution

    # 1. Mark agent OFFLINE (spec P4: 仅"现任 channel"可置离线; 僵尸连接 0 行)
    agent_qs = Worker.objects.filter(agent_id=agent_id)
    if channel:
        agent_qs = agent_qs.filter(active_channel=channel)
    offline_n = agent_qs.update(
        status=Worker.Status.OFFLINE,
        active_channel=None,
    )
    if offline_n:
        logger.info("数据库标记 Agent 离线: agent_id=%s", agent_id)
    else:
        logger.info(
            "Agent offline 写入被 channel 校验拦截 (可能已被新连接接管): agent_id=%s channel=%s",
            agent_id, channel,
        )
        return  # 非现任连接: 不取消执行, 避免误杀新连接的任务

    # 2. Cancel all RUNNING executions for this agent
    running_execs = list(
        TaskExecution.objects.filter(
            agent__agent_id=agent_id,
            status=TaskExecution.Status.RUNNING,
        )
    )
    affected = TaskExecution.objects.filter(
        agent__agent_id=agent_id,
        status=TaskExecution.Status.RUNNING,
    ).update(
        status=TaskExecution.Status.FAILED,
        error_message="Agent 断开连接，任务中断",
        completed_at=django_timezone.now(),
    )
    if affected:
        logger.info(
            "Agent %s 断开连接，已取消 %d 个运行中的执行",
            agent_id, affected,
        )

    # 3. Restore device status for each cancelled execution
    for execution in running_execs:
        _restore_device_status(execution)


def _restore_device_status(execution):
    """Restore a device's status to ONLINE after an execution is force-failed.

    Multi-instance aware: only flips the device back to ONLINE when no
    other RUNNING execution is still bound to it.

    Args:
        execution: A ``TaskExecution`` instance (must have device_id set).
    """
    if execution is None or execution.device_id is None:
        return
    try:
        from workers.models import Device  # cross-app import isolated

        from tasks.models import TaskExecution  # cross-app import isolated

        still_running = TaskExecution.objects.filter(
            device_id=execution.device_id,
            status=TaskExecution.Status.RUNNING,
        ).exclude(id=execution.id).exists()
        if still_running:
            return

        Device.objects.filter(
            id=execution.device_id,
            status=Device.Status.BUSY,
        ).update(status=Device.Status.ONLINE)
        logger.debug(
            "Device %s restored to ONLINE (agent %s disconnected)",
            execution.device_id,
            getattr(execution.agent, 'agent_id', '?'),
        )
    except Exception as exc:
        logger.warning(
            "_restore_device_status failed for execution %s: %s",
            getattr(execution, 'id', '?'),
            exc,
        )


# ---------------------------------------------------------------------------
# Device lookups + registration (agents.models.Device)
# ---------------------------------------------------------------------------

def lookup_device_id_by_agent(*, agent_id, agent_device_id, device_name, device_type, window_handle):
    """Resolve an agent-side device identifier to a backend Device.id.

    Performs up to 7 lookup strategies (exact id, window_handle, hwnd
    prefix, device_name, window_title prefix, ADB serial, type-only).
    Mirrors the legacy ``WorkerConsumer._lookup_agent_device_id_uncached``
    implementation (TD-259 #22 process-local cache wraps this call).

    Args:
        agent_id: ``Agent.agent_id`` string identifier.
        agent_device_id: The agent's internal device id.
        device_name: Human-readable device name reported by the agent.
        device_type: Agent-reported device type (e.g. ``windows``).
        window_handle: Agent-reported window handle (hex string).

    Returns:
        The backend ``Device.id`` (int) or ``None`` if no match is found.
    """
    from workers.models import Device, Worker  # cross-app import isolated (TD-259 #29)

    if not agent_id:
        return None

    try:
        agent = Worker.objects.filter(agent_id=agent_id).first()
        if agent is None:
            return None

        # Normalize incoming type to backend choices.
        raw_type = (device_type or "").lower()
        if raw_type in ("windows", "window", "win32", "pc"):
            normalized_type = Device.DeviceType.WINDOWS
        elif raw_type in ("emulator", "android", "adb", "emu"):
            normalized_type = Device.DeviceType.EMULATOR
        else:
            normalized_type = ""

        # 1. Exact match on device_id when the agent happens to use the
        # backend id (emulator devices often do).
        if agent_device_id:
            try:
                device = Device.objects.filter(
                    agent=agent,
                    id=int(agent_device_id),
                ).first()
                if device:
                    return device.id
            except (ValueError, TypeError):
                pass

        # 2. Match by window_handle when provided (most reliable for
        # Windows devices).
        if window_handle:
            device = Device.objects.filter(
                agent=agent,
                device_type=Device.DeviceType.WINDOWS,
                window_handle__iexact=str(window_handle),
            ).first()
            if device:
                return device.id

        # 3. Parse ``windows-hwnd-0x...`` and match window_handle.
        if agent_device_id:
            hwnd = None
            if agent_device_id.startswith("windows-hwnd-"):
                hwnd = agent_device_id[len("windows-hwnd-"):]
            elif agent_device_id.lower().startswith("hwnd-"):
                hwnd = agent_device_id[len("hwnd-"):]
            if hwnd:
                device = Device.objects.filter(
                    agent=agent,
                    device_type=Device.DeviceType.WINDOWS,
                    window_handle__iexact=hwnd,
                ).first()
                if device:
                    return device.id

        # 4. Match by device name (reliable when agent ids are opaque like
        # ``windows-0`` and the backend already synced the device).
        if device_name:
            device = Device.objects.filter(
                agent=agent,
                name__iexact=device_name,
            ).first()
            if device:
                return device.id

        # 5. Parse ``windows-title-<title>`` and match window_title in
        # extra_info or the device name.
        if agent_device_id:
            title = None
            if agent_device_id.startswith("windows-title-"):
                title = agent_device_id[len("windows-title-"):]
            if title:
                device = (
                    Device.objects.filter(
                        agent=agent,
                        device_type=Device.DeviceType.WINDOWS,
                    )
                    .filter(
                        Q(extra_info__window_title=title)
                        | Q(extra_info__window_title__iexact=title)
                        | Q(name__iexact=title)
                    )
                    .first()
                )
                if device:
                    return device.id

        # 6. Match ADB serial for emulator devices.
        if agent_device_id:
            device = Device.objects.filter(
                agent=agent,
                device_type=Device.DeviceType.EMULATOR,
                adb_serial=agent_device_id,
            ).first()
            if device:
                return device.id

        # 7. When device_type is known but the id is opaque (e.g.
        # ``windows-0``), pick the single matching device of that type
        # belonging to this agent.
        if normalized_type:
            devices = Device.objects.filter(agent=agent, device_type=normalized_type)
            if devices.count() == 1:
                return devices.first().id

    except Exception as exc:
        logger.warning(
            "device_id mapping failed: agent_device_id=%s, device_name=%s, "
            "device_type=%s, window_handle=%s, agent_id=%s, error=%s",
            agent_device_id, device_name, device_type, window_handle,
            agent_id, exc,
        )
    return None


def map_db_device_ids_to_agent_strings(agent_id, db_device_ids):
    """Translate DB ``Device.id`` values to agent-side device_id strings.

    Mirrors the legacy ``WorkerConsumer._map_db_device_ids_to_agent``
    implementation. Used by the screenshot stream control path so the
    frontend's numeric Device.ids become agent-meaningful identifiers
    (``windows-hwnd-{hwnd}`` / ``windows-title-{name}`` / ``{id}``).

    Args:
        agent_id: ``Agent.agent_id`` string identifier.
        db_device_ids: List of DB ``Device.id`` (int or str) from frontend.

    Returns:
        List of agent device_id strings, or ``None`` if the agent is
        unknown / no ids could be translated.
    """
    from workers.models import Device, Worker  # cross-app import isolated (TD-259 #29)

    if not agent_id:
        return None

    agent = Worker.objects.filter(agent_id=agent_id).first()
    if agent is None:
        return None

    # Normalize ids to int.
    int_ids: list[int] = []
    for did in db_device_ids or []:
        with contextlib.suppress(ValueError, TypeError):
            int_ids.append(int(did))
    if not int_ids:
        return None

    devices = list(Device.objects.filter(agent=agent, id__in=int_ids))

    result: list[str] = []
    for dev in devices:
        if dev.device_type == Device.DeviceType.WINDOWS:
            hwnd = dev.window_handle
            if hwnd:
                result.append(f"windows-hwnd-{hwnd}")
            else:
                result.append(f"windows-title-{dev.name}")
        else:
            # Emulator: agent may use DB id or adb_serial.
            result.append(str(dev.id))
    return result if result else None


def register_agent_device(agent_id, device_data):
    """Create or update a Device record from agent-reported device data.

    Mirrors the legacy ``WorkerConsumer._db_register_device``
    implementation. Priority: adb_serial > window_handle > window_title
    > name prefix. Auto-binds GameProfile by window_title (R37-P1)
    without overwriting an existing FK.

    Args:
        agent_id: ``Agent.agent_id`` string identifier.
        device_data: Device dict from agent (name / device_type /
            adb_serial / window_handle / window_title / resolution_* /
            emulator / status).

    Returns:
        dict: ``{"id": int, "created": bool, "updated": bool}``.
    """
    from workers.models import Device, Worker  # cross-app import isolated (TD-259 #29)
    from workers.services.device_identity import find_device_by_identity  # OQ-9

    device_type = device_data.get("device_type", "emulator")
    name = device_data.get("name", f"{device_type}-{uuid.uuid4().hex[:6]}")
    adb_serial = device_data.get("adb_serial", "")
    window_handle = device_data.get("window_handle", "")

    # R37-P1: pre-compute GameProfile match for auto-bind (WS path).
    # Returns None if window_title is empty OR no GameProfile matches.
    # Post-bind step below preserves user choice (never overwrites existing FK).
    # TD-333: 传 device_type 作为 hint, 避免 windows 设备误绑 emulator GameProfile
    auto_game_profile = bind_game_profile_by_title(
        device_data.get("window_title", ""),
        device_type_hint=device_type,
    )
    # N197: 自动绑定后校验 allowed_device_types — 若设备类型不在允许列表内, 跳过自动绑定
    if (
        auto_game_profile
        and auto_game_profile.allowed_device_types
        and device_type not in auto_game_profile.allowed_device_types
    ):
            logger.info(
                "跳过自动绑定(WS): device_type=%s 不在 GameProfile %s 的 allowed_device_types=%s 中",
                device_type, auto_game_profile.id, auto_game_profile.allowed_device_types,
            )
            auto_game_profile = None

    try:
        agent = Worker.objects.filter(agent_id=agent_id).first()
    except Exception:
        # spec-56 TD: Agent query failed (e.g. DB transient error). Log
        # for traceability — silent swallow would hide device-bind loss.
        logger.warning(
            "protocol.services: Agent query failed for agent_id=%s",
            agent_id,
            exc_info=True,
        )
        agent = None

    # Respect the status the agent reported (online/offline/busy) instead of
    # always forcing ONLINE. The agent sends device.sync with the device's
    # current health status, including "offline" when an ADB device vanished —
    # otherwise a stale record could stay "online" forever even though no such
    # device is connected anymore.
    _reported_status = device_data.get("status")
    _status = (
        _reported_status
        if _reported_status in (Device.Status.ONLINE, Device.Status.OFFLINE, Device.Status.BUSY)
        else Device.Status.ONLINE
    )
    # OQ-9 (2026-08-30): single identity resolver shared with the HTTP
    # DeviceRegisterView — no more independent 4-branch dedup here.
    # Priority: window_handle > adb_serial > emulator_brand+empty serial >
    # window_title > name+type (see workers/services/device_identity.py).
    emulator_brand = device_data.get("emulator_brand") or device_data.get("emulator", "")
    device = find_device_by_identity(
        device_type,
        hwnd=window_handle,
        adb_serial=adb_serial,
        emulator_brand=emulator_brand,
        window_title=device_data.get("window_title", ""),
        name=name,
        agent=agent,
    )

    created = device is None
    if created:
        # Agent sync is the lifecycle authority: create the baseline record.
        # Personalization (name/绑定/方法) is refined later via manual
        # register or device settings — never overwritten by sync.
        extra_info = dict(device_data)
        extra_info["registered_via"] = "agent"
        device = Device.objects.create(
            name=name,
            device_type=device_type,
            status=_status,
            agent=agent,
            adb_serial=adb_serial or "",
            window_handle=window_handle or "",
            emulator_brand=emulator_brand,
            resolution_width=device_data.get("resolution_width"),
            resolution_height=device_data.get("resolution_height"),
            extra_info=extra_info,
        )
    else:
        # P-3 conflict arbitration: base/lifecycle fields only — never
        # overwrite a user-saved name; keep the registration source marker.
        update_fields = ["status", "updated_at"]
        device.status = _status
        if adb_serial and not device.adb_serial:
            device.adb_serial = adb_serial
            update_fields.append("adb_serial")
        if window_handle and not device.window_handle:
            device.window_handle = window_handle
            update_fields.append("window_handle")
        if emulator_brand and not device.emulator_brand:
            device.emulator_brand = emulator_brand
            update_fields.append("emulator_brand")
        if device_data.get("resolution_width"):
            device.resolution_width = device_data["resolution_width"]
            update_fields.append("resolution_width")
        if device_data.get("resolution_height"):
            device.resolution_height = device_data["resolution_height"]
            update_fields.append("resolution_height")
        if not device.agent_id and agent:
            device.agent = agent
            update_fields.append("agent")
        extra_info = dict(device.extra_info or {})
        if "registered_via" not in extra_info:
            extra_info["registered_via"] = "agent"
        extra_info.update(device_data)
        device.extra_info = extra_info
        update_fields.append("extra_info")
        device.save(update_fields=update_fields)

    # R37-P1: auto-bind device to GameProfile by window_title (WS path).
    # Single post-bind step covering all 4 priority branches above.
    # Preserves user choice — only binds when device.game_profile_id is None.
    if auto_game_profile and not device.game_profile_id:
        device.game_profile = auto_game_profile
        device.save(update_fields=["game_profile"])

    return {"id": device.id, "created": created, "updated": not created}


# ---------------------------------------------------------------------------
# TaskExecution + ExecutionStep (tasks.models)
# ---------------------------------------------------------------------------

def get_task_execution(execution_id):
    """Look up a TaskExecution by primary key.

    Args:
        execution_id: ``TaskExecution.id`` (int or string from agent payload).

    Returns:
        ``TaskExecution`` instance.

    Raises:
        ProtocolBindingError: If the execution doesn't exist or the id
            is invalid (carries status_code=404 + execution_id in extra).
    """
    from tasks.models import TaskExecution  # cross-app import isolated (TD-259 #29)
    try:
        return TaskExecution.objects.get(pk=execution_id)
    except (TaskExecution.DoesNotExist, ValueError, TypeError) as exc:
        raise ProtocolBindingError(
            f"TaskExecution {execution_id} 不存在或无效",
            status_code=404,
            extra={"execution_id": execution_id},
        ) from exc


def upsert_execution_step(payload):
    """Persist or update an ExecutionStep row from a task.progress payload.

    Mirrors the legacy ``WorkerConsumer._persist_execution_step``
    implementation (P-010 Phase 2). ``update_or_create`` on
    ``(task_result, step_index)`` so re-sends (retry) upsert instead of
    duplicating.

    Non-fatal: any DB error is logged and swallowed so a bad payload
    never crashes the WebSocket consumer. Unknown ``execution_id`` is
    logged and silently dropped (the agent may send progress for an
    execution the backend has already garbage-collected).

    Args:
        payload: task.progress payload dict (execution_id / step_index /
            status / step_name / node_id / error_msg / error_code / elapsed_time).
    """
    from tasks.models import ExecutionStep, TaskExecution  # cross-app import isolated (TD-259 #29)

    execution_id = payload.get("execution_id", "")
    step_index = payload.get("step_index")
    if not execution_id or step_index is None:
        return

    try:
        execution = TaskExecution.objects.get(id=execution_id)
    except (TaskExecution.DoesNotExist, ValueError):
        logger.warning(
            "task.progress 收到未知 execution_id=%s, 无法持久化 ExecutionStep",
            execution_id,
        )
        return

    step_status_raw = (payload.get("status") or "").lower()
    # Map agent status string → ExecutionStep.Status enum value.
    # Unknown status falls back to RUNNING so we don't lose the row.
    status_map = {
        "pending": ExecutionStep.Status.PENDING,
        "running": ExecutionStep.Status.RUNNING,
        "success": ExecutionStep.Status.SUCCESS,
        "failed": ExecutionStep.Status.FAILED,
        "skipped": ExecutionStep.Status.SKIPPED,
    }
    step_status = status_map.get(step_status_raw, ExecutionStep.Status.RUNNING)

    step_name = payload.get("step_name") or f"step_{step_index}"
    node_id = payload.get("node_id") or str(step_index)
    error_msg = payload.get("error_msg", "") or ""
    # Task 3.6 (P2-6): 从 payload 提取 error_code, 持久化到 ExecutionStep.error_code。
    # agent 在 task.progress payload 中携带 error_code (AutoResult.error_code),
    # backend 存到 ExecutionStep 后, broadcast signal 透传给前端做 i18n 映射。
    error_code = payload.get("error_code", "") or ""
    elapsed_time = payload.get("elapsed_time")
    now = django_timezone.now()

    defaults: dict[str, Any] = {
        "node_id": node_id,
        "step_name": step_name,
        # step_type is unknown for pipeline nodes (agent doesn't send it);
        # legacy consumer used "unknown" — keep consistent.
        "step_type": "pipeline_node",
        "status": step_status,
    }
    if error_msg:
        defaults["error_message"] = error_msg
    if error_code:
        defaults["error_code"] = error_code
        # N192 (B1/B2): Map error_code → user_message for frontend display.
        # get_user_message() converts technical codes (NO_MATCH/TIMEOUT) to
        # user-friendly Chinese text, avoiding raw exception messages.
        try:
            from gaf_core.error_messages import get_user_message
            defaults["user_message"] = get_user_message(
                error_code,
                default=error_msg or "",
            )
        except Exception:
            # Best-effort: never block step persistence, but surface the failure
            # instead of swallowing it silently (E1).
            logger.warning("get_user_message 失败 (error_code=%s)", error_code, exc_info=True)
    if isinstance(elapsed_time, (int, float)) and elapsed_time >= 0:
        defaults["duration"] = float(elapsed_time)
        defaults["duration_ms"] = int(elapsed_time * 1000)
    if step_status in (ExecutionStep.Status.SUCCESS, ExecutionStep.Status.FAILED,
                       ExecutionStep.Status.SKIPPED):
        defaults["completed_at"] = now
        if not defaults.get("started_at"):
            # We don't have an explicit started_at from the agent; use now
            # minus elapsed_time as a best-effort estimate so duration
            # queries have a non-null window.
            defaults["started_at"] = now - timedelta(seconds=float(elapsed_time or 0))

    try:
        ExecutionStep.objects.update_or_create(
            task_result=execution,
            step_index=step_index,
            defaults=defaults,
        )
    except Exception as exc:
        logger.exception(
            "持久化 ExecutionStep 失败: execution_id=%s step_index=%s: %s",
            execution_id, step_index, exc,
        )


def update_task_execution_result(*, execution_id, success, elapsed_time, error_msg, result_data, structured_log_path="", error_code=""):
    """Update a TaskExecution row with the final result (N145 L1 fix).

    Mirrors the legacy ``WorkerConsumer._db_update_execution_result``
    implementation. Sets status (SUCCESS/FAILED), completed_at, duration,
    result_data/error_message, backfills started_at if missing.

    On chain executions, schedules ``advance_chain_execution`` via
    ``transaction.on_commit`` so the next node dispatches after the
    current row is committed.

    Non-fatal: unknown execution_id is logged and swallowed (the agent
    may report results for an execution the backend has already
    garbage-collected).

    Args:
        execution_id: ``TaskExecution.id`` (int or string from agent payload).
        success: bool — agent's success flag.
        elapsed_time: float seconds (or None / non-numeric).
        error_msg: str — failure reason (empty on success).
        result_data: dict — pipeline result on success.
        structured_log_path: str — agent-local JSONL path
            (N190: written to execution_snapshot.structured_log_path so
            AI tools / pack_execution_logs can locate the JSONL file
            without re-scanning the filesystem).
        error_code: str — task-level error code from agent (DEVICE_DISCONNECTED/UNKNOWN/...)
            N192: persisted so historical executions show structured error codes.
    """
    from django.db import transaction

    from tasks.models import TaskExecution  # cross-app import isolated (TD-259 #29)

    try:
        execution = TaskExecution.objects.get(pk=execution_id)
    except (TaskExecution.DoesNotExist, ValueError, TypeError):
        logger.warning("task.result: execution_id=%s 不存在或无效, 跳过状态更新", execution_id)
        return

    # S1 (2026-08-16): 终态守卫 — 迟到/重复的 task.result 不得复活终态执行.
    # 根因: 原实现无条件覆盖 status, 导致:
    #   - 心跳超时已 fail 的执行被迟到的 result 复活为 SUCCESS
    #   - FORCE_TERMINATED / CANCELLED 的执行被 agent 迟到结果覆盖
    # 仅在 PENDING/RUNNING 状态下接受结果; 终态一律忽略 (只记日志).
    terminal_statuses = {
        TaskExecution.Status.SUCCESS,
        TaskExecution.Status.FAILED,
        TaskExecution.Status.CANCELLED,
        TaskExecution.Status.FORCE_TERMINATED,
    }
    if execution.status in terminal_statuses:
        logger.warning(
            "task.result 忽略: execution_id=%s 已处于终态 %s (迟到/重复结果不复活)",
            execution_id, execution.status,
        )
        return

    now = django_timezone.now()
    execution.status = TaskExecution.Status.SUCCESS if success else TaskExecution.Status.FAILED
    execution.completed_at = now
    try:
        seconds = float(elapsed_time) if elapsed_time else 0.0
    except (TypeError, ValueError):
        seconds = 0.0
    execution.duration = timedelta(seconds=seconds)

    if success:
        execution.result_data = result_data
        execution.error_message = ""
        execution.error_code = ""
    else:
        execution.error_message = error_msg or ""
        # N192: Persist task-level error_code and map to user_message.
        # get_user_message() converts technical error codes (DEVICE_DISCONNECTED)
        # to user-friendly Chinese text for frontend display.
        execution.error_code = error_code or ""
        try:
            from gaf_core.error_messages import get_user_message
            user_msg = get_user_message(
                error_code or None,
                default=error_msg or "任务执行失败",
            )
            snap = dict(execution.execution_snapshot or {})
            snap["user_message"] = user_msg
            execution.execution_snapshot = snap
        except Exception:
            logger.warning("任务结果 user_message 映射失败 (error_code=%s)", error_code, exc_info=True)

    # Backfill started_at if backend never set it (e.g. pipeline.execute path
    # only creates the record without setting started_at).
    if not execution.started_at:
        execution.started_at = now - timedelta(seconds=seconds)

    # N190 (2026-07-26): merge structured_log_path into execution_snapshot.
    # Agent writes the JSONL to <debug_dir>/structured/<exec_id>.jsonl and
    # reports the absolute path back in task.result payload. Stash it in
    # execution_snapshot.structured_log_path so downstream (AI tools,
    # pack_execution_logs, debug views) can locate the file without
    # filesystem globbing.
    if structured_log_path:
        snap = dict(execution.execution_snapshot or {})
        snap["structured_log_path"] = structured_log_path
        execution.execution_snapshot = snap

    execution.save()
    logger.info(
        "TaskExecution 已更新: id=%s, status=%s, duration=%ss, structured_log=%s",
        execution_id, execution.status, seconds,
        structured_log_path or "<none>",
    )

    # spec 阶段 5 (TD-096): If this execution is part of a TaskChain,
    # trigger chain advancement. The advance_chain_execution Celery task
    # will check the execution status, evaluate the node's condition, and
    # dispatch the next node (or abort the chain).
    if execution.chain_execution_id:
        from pipeline.tasks import advance_chain_execution
        transaction.on_commit(
            lambda: advance_chain_execution.delay(execution.chain_execution_id)
        )
        logger.info(
            "Chain execution %s: node execution %s completed (%s) → advancing",
            execution.chain_execution_id, execution_id, execution.status,
        )

    # spec §8.2 — archive the per-execution log directory to tar.gz after
    # the execution finalizes. Triggered via transaction.on_commit so the
    # tarball is built only after the TaskExecution row is durable; the
    # pack task reads <debug_dir>/logs/<execution_id>/ which is written
    # by FileLogHandler during the run (already on disk by this point).
    # Skipped for non-terminal statuses (PENDING/RUNNING/CANCELLED) —
    # only SUCCESS / FAILED / FORCE_TERMINATED have meaningful archives.
    if execution.status in (
        TaskExecution.Status.SUCCESS,
        TaskExecution.Status.FAILED,
        TaskExecution.Status.FORCE_TERMINATED,
    ):
        from debug.tasks import pack_execution_logs_task
        transaction.on_commit(
            lambda eid=execution_id: pack_execution_logs_task.delay(eid)
        )
        logger.info(
            "Execution %s finalized (%s) → scheduling log archive",
            execution_id, execution.status,
        )
