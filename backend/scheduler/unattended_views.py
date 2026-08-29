"""
无人值守总控 API (Phase 8) — split from scheduler/views.py in spec-29d.

Contains:
- 3 helpers: _get_active_sessions / _get_session_by_id / _map_session_to_mode_status
- 8 unattended FBVs: start / stop / pause / resume / preflight / status / queue / progress / sessions

P-011 multi-session: start/stop/pause/resume operate by session_id and
scoped by game_profile (multiple sessions may run in parallel).
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.app_info import PREFLIGHT_HEARTBEAT_CUTOFF_SECONDS, PREFLIGHT_MAX_WORKERS
from scheduler.models import TimeWindow, UnattendedSession

logger = logging.getLogger(__name__)


def _get_active_sessions(game_profile_id=None):
    """Return all active (RUNNING/PAUSED) UnattendedSessions as a QuerySet.

    P-011 multi-session: replaces the singleton ``_get_active_unattended_session``.
    Multiple sessions may coexist, scoped by game_profile.

    Args:
        game_profile_id: if provided, filter to sessions for this game_profile.

    Returns:
        QuerySet of UnattendedSession (empty if none active).
    """
    qs = UnattendedSession.objects.filter(
        status__in=[UnattendedSession.Status.RUNNING, UnattendedSession.Status.PAUSED]
    )
    if game_profile_id is not None:
        qs = qs.filter(game_profile_id=game_profile_id)
    return qs


def _get_session_by_id(session_id):
    """Fetch a single UnattendedSession by primary key.

    P-011: stop/pause/resume now operate by session_id instead of the
    singleton lookup. Returns None if not found.
    """
    if not session_id:
        return None
    try:
        return UnattendedSession.objects.get(pk=session_id)
    except UnattendedSession.DoesNotExist:
        return None


def _map_session_to_mode_status(session):
    """Map DB session.status to API mode_status field (running/paused/stopped).

    Contract preservation (N112 — frontend `useUnattendedStore.session` keeps
    the original mode_status string values).
    """
    if session is None:
        return 'stopped'
    if session.status == UnattendedSession.Status.RUNNING:
        return 'running'
    if session.status == UnattendedSession.Status.PAUSED:
        return 'paused'
    # INIT/STOPPING/STOPPED/FAILED all map to "stopped" for API contract
    return 'stopped'


@extend_schema(
    tags=['unattended'],
    summary='Start unattended mode for a game_profile',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unattended_start_view(request):
    """
    启动无人值守模式（P-011: 按 game_profile 分组）。

    POST /api/v2/scheduler/unattended/start/
    必填参数: game_profile_id — 指定要启动哪个游戏的无人值守。
    查找该 game_profile 下所有在线 + 有默认链的设备 → 为每个设备创建
    TaskChainExecution 并派发首节点（spec §2.4.1）→ 返回派发数量。
    同一 game_profile 已有 RUNNING/PAUSED session 时返回 409 Conflict。
    不同 game_profile 可并行运行（P-011 多 session 并行）。
    """
    # @api_view allowed: one-off state-machine action (start), not resource CRUD
    game_profile_id = request.data.get("game_profile_id")
    if not game_profile_id:
        return Response(
            {"error": "game_profile_id 必填（P-011 多 session 并行按游戏分组）",
             "code": "missing_game_profile_id"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # P-011: 409 check scoped to game_profile (not global singleton).
    # TD-402 ③ (2026-08-27): the check + GameProfile lookup run inside a row
    # lock so two concurrent starts for the same profile serialize — the second
    # caller observes the RUNNING session created by the first and gets 409.
    from gamestate.models import GameProfile
    with transaction.atomic():
        try:
            game_profile = GameProfile.objects.select_for_update().get(
                pk=game_profile_id
            )
        except GameProfile.DoesNotExist:
            return Response(
                {"error": "game_profile 不存在", "code": "invalid_game_profile"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        active = _get_active_sessions(game_profile_id=game_profile_id).first()
        if active is not None:
            return Response(
                {"error": f"该游戏档案已有无人值守在运行中 (session_id={active.id})",
                 "code": "already_running",
                 "session_id": active.id},
                status=status.HTTP_409_CONFLICT,
            )

    from pipeline.services import (
        ChainDispatchError,
        create_chain_execution_and_dispatch,
    )

    from agents.models import Agent, Device

    # Online agent statuses match pipeline.services.create_chain_execution_and_dispatch
    online_statuses = (Agent.Status.ONLINE, Agent.Status.IDLE)
    # P-011: filter devices by game_profile_id (not all online devices)
    devices = Device.objects.filter(
        agent__status__in=online_statuses,
        game_profile_id=game_profile_id,
        game_profile__default_task_chain__isnull=False,
    ).select_related('game_profile__default_task_chain', 'agent', 'game_account')

    # P-011 Spec A: in multi-game mode, refuse to start if any bound device
    # is configured with an unsafe input method. resolve_device_methods()
    # would silently downgrade unsafe methods to safe defaults, but that
    # would hide a misconfiguration from the operator — they'd see clicks
    # "working" but not realize the method was changed. Instead, refuse to
    # start and tell them which devices need rebinding.
    #
    # We check `original_input_method` (pre-downgrade) so operators are
    # forced to explicitly rebind the device to a safe method, rather than
    # having the system silently switch it.
    from settings.feature_flags import is_multi_game_mode_enabled
    if is_multi_game_mode_enabled():
        from agents.models import MULTI_GAME_BLOCKED_INPUT_METHODS, resolve_device_methods
        unsafe_devices = []
        for device in devices:
            resolved = resolve_device_methods(device)
            # Case-insensitive match: original_input_method may be lowercase
            # (frontend convention) or CamelCase (CONTROL_MODE_DEFAULTS).
            original_input_lower = (resolved['original_input_method'] or '').lower()
            if original_input_lower in MULTI_GAME_BLOCKED_INPUT_METHODS:
                unsafe_devices.append(
                    f"{device.name}={resolved['original_input_method']}"
                )
        if unsafe_devices:
            return Response(
                {
                    "error": "Devices with unsafe input methods for multi-game mode",
                    "code": "unsafe_method_for_multi_game",
                    "devices": unsafe_devices,
                    "hint": "Rebind these devices to PostMessage (Windows) or adb_input (emulator) before starting a parallel session.",
                },
                status=400,
            )

    reason = request.data.get("reason", "")
    # TD-400: loop rotation flag (bool, default False). Consistent with
    # session.loop_rotation semantics — see scheduler/models.py.
    loop_rotation = bool(request.data.get("loop_rotation", False))

    # P-009 Phase 2: optional rotation rule for account rotation loop.
    # If provided, snapshot the FK on the session so tick_unattended_session
    # can use calculate_account_order to pick the next account per device.
    rotation_rule_id = request.data.get("rotation_rule_id")
    rotation_rule = None
    if rotation_rule_id:
        from scheduler.models import GameAccountRotation
        try:
            rotation_rule = GameAccountRotation.objects.get(id=rotation_rule_id)
        except GameAccountRotation.DoesNotExist:
            return Response(
                {"error": "rotation_rule 不存在", "code": "invalid_rotation_rule"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    # Create the session before dispatching (TD-402 ③): registering the
    # start-round chains into it afterwards keeps the completion hook able to
    # attribute them. total_accounts is patched after the dispatch loop.
    session = UnattendedSession.objects.create(
        status=UnattendedSession.Status.RUNNING,
        started_at=timezone.now(),
        total_devices=devices.count(),
        total_accounts=0,
        triggered_by=request.user,
        rotation_rule=rotation_rule,
        loop_rotation=loop_rotation,
        game_profile=game_profile,  # P-011: scope to game_profile
    )

    # A1-fix (2026-08-26): collect start-round dispatches so they can be
    # registered on the session (see register below). Without registration the
    # completion hook can't attribute the chain -> rotation never advances,
    # loop_rotation never returns accounts, all_completed AutoStop never fires.
    from pipeline.models import TaskChainExecution
    dispatched = []
    dispatched_chain_execs = []
    dispatched_account_ids = set()
    skipped = []
    failed = []
    for device in devices:
        chain = device.game_profile.default_task_chain
        if not chain.is_enabled:
            skipped.append({"device_id": device.id, "reason": "chain_disabled"})
            continue
        # TD-402 ③ (2026-08-27): tick-style busy guard — never double-dispatch
        # onto a device that already carries an active chain (prevents
        # concurrent-start and manual-chain overlap even if a second start
        # slipped through the 409 window).
        if TaskChainExecution.objects.filter(
            device_id=device.id,
            status__in=[
                TaskChainExecution.Status.PENDING,
                TaskChainExecution.Status.RUNNING,
            ],
        ).exists():
            skipped.append({"device_id": device.id, "reason": "device_busy"})
            continue
        try:
            # Rotation mode (2026-08-27): the start round always picks from the
            # rotation order at the cursor position — never from a stale
            # device.game_account left over by a previous session — so a fresh
            # session starts clean at ordered[0] and ticks rotate through ALL
            # accounts (fair rotation cursor).
            account = device.game_account if rotation_rule is None else None
            if rotation_rule is not None:
                from scheduler.engine import calculate_account_order
                ordered = calculate_account_order(
                    rotation_rule, list(rotation_rule.accounts.all()),
                )
                if not ordered:
                    # rotation rule with no accounts — nothing to rotate through
                    skipped.append({"device_id": device.id, "reason": "rotation_empty"})
                    continue
                account = ordered[(session.rotation_index or 0) % len(ordered)]
            chain_execution = create_chain_execution_and_dispatch(
                chain_id=chain.id,
                agent_id=device.agent.agent_id if device.agent else None,
                device_id=device.id,
                game_account_id=account.id if account else None,
                triggered_by=request.user,
            )
            dispatched.append(chain_execution.id)
            dispatched_chain_execs.append(chain_execution)
            if account is not None:
                dispatched_account_ids.add(account.id)
        except ChainDispatchError as exc:
            failed.append({"device_id": device.id, "reason": str(exc)})
            logger.warning(
                "unattended_start: dispatch failed for device %s: %s",
                device.id, exc,
            )

    # A1-fix (2026-08-26): register start-round dispatches on the session once
    # it exists. This is what lets the completion hook attribute chains to the
    # session (rotation progression / loop_rotation return / all_completed).
    for chain_exec in dispatched_chain_execs:
        session.active_chain_executions.add(chain_exec)
    if dispatched_account_ids:
        session.dispatched_account_ids = sorted(dispatched_account_ids)
    if rotation_rule and loop_rotation and dispatched_account_ids:
        # Fair rotation (2026-08-27): the start round consumes the cursor
        # position too, so the first tick continues from the NEXT account
        # (ordered[cursor]) instead of re-selecting ordered[0].
        session.rotation_index = (session.rotation_index or 0) + 1
    session.total_accounts = len(dispatched_account_ids)
    session.save(update_fields=['dispatched_account_ids', 'total_accounts', 'rotation_index'])

    logger.info(
        "无人值守模式已启动 (P-011), session_id=%s, game_profile_id=%s, "
        "reason=%s, rotation_rule_id=%s, dispatched=%d, skipped=%d, failed=%d",
        session.id, game_profile_id, reason,
        rotation_rule_id if rotation_rule else None,
        len(dispatched), len(skipped), len(failed),
    )

    return Response(
        {
            "status": "running",
            "session_id": session.id,
            "game_profile_id": game_profile_id,
            "game_profile_name": game_profile.game_name,
            "started_at": session.started_at.isoformat(),
            "rotation_rule_id": rotation_rule.id if rotation_rule else None,
            "dispatched_count": len(dispatched),
            "skipped_count": len(skipped),
            "failed_count": len(failed),
            "dispatched_chain_execution_ids": dispatched,
            "skipped": skipped,
            "failed": failed,
            "message": f"无人值守模式已启动 ({game_profile.game_name})",
        }
    )


@extend_schema(
    tags=['unattended'],
    summary='Stop unattended mode by session_id',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unattended_stop_view(request):
    """
    停止无人值守模式（P-011: 按 session_id 操作）。

    POST /api/v2/scheduler/unattended/stop/
    必填参数: session_id — 要停止的会话 ID。
    记录停止原因 → 发送停止信号。
    """
    # @api_view allowed: one-off state-machine action (stop), not resource CRUD
    session_id = request.data.get("session_id")
    session = _get_session_by_id(session_id)
    if session is None:
        return Response(
            {"error": "session 不存在", "code": "session_not_found",
             "session_id": session_id},
            status=status.HTTP_404_NOT_FOUND,
        )

    if session.status in [UnattendedSession.Status.STOPPED,
                          UnattendedSession.Status.STOPPING]:
        return Response(
            {"error": "该 session 已停止", "code": "already_stopped",
             "session_id": session.id},
            status=status.HTTP_409_CONFLICT,
        )

    stop_reason = request.data.get("reason", "manual")

    session.status = UnattendedSession.Status.STOPPED
    session.stopped_at = timezone.now()
    session.stop_reason = stop_reason
    session.paused_at = None
    session.save(update_fields=[
        "status", "stopped_at", "stop_reason", "paused_at", "updated_at",
    ])

    logger.info(
        "无人值守模式已停止 (P-011), session_id=%s, reason=%s",
        session.id, stop_reason,
    )

    return Response(
        {
            "status": "stopped",
            "session_id": session.id,
            "stopped_at": session.stopped_at.isoformat(),
            "stop_reason": stop_reason,
            "message": "无人值守模式已停止",
        }
    )


@extend_schema(
    tags=['unattended'],
    summary='Pause unattended mode by session_id',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unattended_pause_view(request):
    """
    暂停无人值守（P-011: 按 session_id 操作）。

    POST /api/v2/scheduler/unattended/pause/
    必填参数: session_id — 要暂停的会话 ID。
    Agent 完成当前步骤后挂起。
    """
    # @api_view allowed: one-off state-machine action (pause), not resource CRUD
    session_id = request.data.get("session_id")
    session = _get_session_by_id(session_id)
    if session is None:
        return Response(
            {"error": "session 不存在", "code": "session_not_found",
             "session_id": session_id},
            status=status.HTTP_404_NOT_FOUND,
        )

    if session.status != UnattendedSession.Status.RUNNING:
        return Response(
            {"error": "该 session 未在运行", "code": "not_running",
             "session_id": session.id, "current_status": session.status},
            status=status.HTTP_409_CONFLICT,
        )

    session.status = UnattendedSession.Status.PAUSED
    session.paused_at = timezone.now()
    session.save(update_fields=["status", "paused_at", "updated_at"])

    logger.info("无人值守模式已暂停 (P-011), session_id=%s", session.id)

    return Response({
        "status": "paused",
        "session_id": session.id,
        "message": "已暂停，Agent 完成当前步骤后挂起",
    })


@extend_schema(
    tags=['unattended'],
    summary='Resume unattended mode by session_id',
    request=OpenApiTypes.OBJECT,
    responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT},
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def unattended_resume_view(request):
    """
    恢复无人值守（P-011: 按 session_id 操作）。

    POST /api/v2/scheduler/unattended/resume/
    必填参数: session_id — 要恢复的会话 ID。
    Agent 从挂起点继续执行。
    """
    # @api_view allowed: one-off state-machine action (resume), not resource CRUD
    session_id = request.data.get("session_id")
    session = _get_session_by_id(session_id)
    if session is None:
        return Response(
            {"error": "session 不存在", "code": "session_not_found",
             "session_id": session_id},
            status=status.HTTP_404_NOT_FOUND,
        )

    if session.status != UnattendedSession.Status.PAUSED:
        return Response(
            {"error": "该 session 未在暂停状态", "code": "not_paused",
             "session_id": session.id, "current_status": session.status},
            status=status.HTTP_409_CONFLICT,
        )

    session.status = UnattendedSession.Status.RUNNING
    session.paused_at = None
    session.save(update_fields=["status", "paused_at", "updated_at"])

    logger.info("无人值守模式已恢复 (P-011), session_id=%s", session.id)

    return Response({
        "status": "running",
        "session_id": session.id,
        "message": "已恢复运行",
    })


@extend_schema(
    tags=['unattended'],
    summary='Preflight checklist (concurrent multi-check)',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unattended_preflight_view(request):
    """
    启动前预检清单 API。

    GET /api/unattended/preflight/
    并发执行 5 项检测：设备在线、账户有效、资源就绪、Agent 连接、调度规则。
    返回结构化检测结果列表。
    """
    # @api_view allowed: concurrent multi-check aggregation (device/account/resource/agent/scheduler)
    # E2E-2026-08-27: scope device_online to the target profile's devices so an
    # offline device of another profile does not block starting this one.
    game_profile_id = request.query_params.get('game_profile_id')

    def check_device_online():
        """检测 1: 设备在线 — 检查目标 profile 的设备 Agent 心跳（未指定时全量）"""
        from agents.models import Device

        devices = Device.objects.all()
        if game_profile_id:
            devices = devices.filter(game_profile_id=game_profile_id)
        offline = [d.name for d in devices if d.status != "online"]
        if offline:
            return {
                "check_type": "device_online",
                "status": "fail",
                "message": f"{len(offline)} 个设备离线: {', '.join(offline[:3])}",
                "fix_action": "/devices",
            }
        if not devices.exists():
            return {
                "check_type": "device_online",
                "status": "warning",
                "message": "未注册任何设备",
                "fix_action": "/devices",
            }
        return {
            "check_type": "device_online",
            "status": "pass",
            "message": f"全部 {devices.count()} 个设备在线",
        }

    def check_account_valid():
        """检测 2: 账户有效 — 检查游戏账户状态"""
        from accounts.models import GameAccount

        accounts = GameAccount.objects.all()
        invalid = [a.username for a in accounts if a.status == "banned"]
        if invalid:
            return {
                "check_type": "account_valid",
                "status": "fail",
                "message": f"{len(invalid)} 个账户异常: {', '.join(invalid[:3])}",
                "fix_action": "/accounts",
            }
        if not accounts.exists():
            return {
                "check_type": "account_valid",
                "status": "warning",
                "message": "未配置任何游戏账户",
                "fix_action": "/accounts",
            }
        return {
            "check_type": "account_valid",
            "status": "pass",
            "message": f"全部 {accounts.count()} 个账户状态正常",
        }

    def check_resource_ready():
        """检测 3: 资源就绪 — 检查资源包和模板文件"""
        from resources.models import ResourcePack

        packs = ResourcePack.objects.filter(is_active=True)
        if not packs.exists():
            return {
                "check_type": "resource_ready",
                "status": "warning",
                "message": "无激活的资源包",
                "fix_action": "/resources",
            }
        missing_templates = []
        for pack in packs:
            if not pack.template_files:
                missing_templates.append(pack.name)
        if missing_templates:
            return {
                "check_type": "resource_ready",
                "status": "warning",
                "message": f"{len(missing_templates)} 个资源包缺少模板: {', '.join(missing_templates[:3])}",
                "fix_action": "/resources",
            }
        return {
            "check_type": "resource_ready",
            "status": "pass",
            "message": f"{packs.count()} 个资源包就绪",
        }

    def check_agent_connection():
        """检测 4: Agent 连接 — 检查 Agent 心跳是否正常"""
        from datetime import timedelta

        from agents.models import Agent

        cutoff = timezone.now() - timedelta(seconds=PREFLIGHT_HEARTBEAT_CUTOFF_SECONDS)
        # NULL-safe: 从未心跳的 Agent 也算 stale (``__lt`` 不匹配 NULL) —
        # 与 tasks/heartbeat.py 对齐, 2026-08-27
        stale_agents = Agent.objects.filter(
            Q(last_heartbeat__isnull=True) | Q(last_heartbeat__lt=cutoff),
        )
        if stale_agents.exists():
            return {
                "check_type": "agent_connection",
                "status": "warning",
                "message": f"{stale_agents.count()} 个 Agent 心跳超时 (>60s)",
                "fix_action": "/devices",
            }
        return {
            "check_type": "agent_connection",
            "status": "pass",
            "message": "所有 Agent 连接正常",
        }

    def check_scheduler_rules():
        """检测 5: 调度规则 — 检查 Cron/时间窗口/轮换规则有效性"""
        windows = TimeWindow.objects.filter(is_enabled=True)
        if not windows.exists():
            return {
                "check_type": "scheduler_rules",
                "status": "warning",
                "message": "未配置时间窗口（将全天候运行）",
                "fix_action": "/scheduled-tasks",
            }
        now = timezone.now().time()
        active_windows = [w for w in windows if w.start_time <= now <= w.end_time]
        if not active_windows:
            return {
                "check_type": "scheduler_rules",
                "status": "warning",
                "message": f"当前时间不在任何时间窗口内 (共 {windows.count()} 个窗口)",
                "fix_action": "/scheduled-tasks",
            }
        return {
            "check_type": "scheduler_rules",
            "status": "pass",
            "message": f"调度规则有效 ({len(active_windows)} 个活跃窗口)",
        }

    checks = [
        check_device_online,
        check_account_valid,
        check_resource_ready,
        check_agent_connection,
        check_scheduler_rules,
    ]

    results = []
    with ThreadPoolExecutor(max_workers=PREFLIGHT_MAX_WORKERS) as executor:
        futures = {executor.submit(fn): fn for fn in checks}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                logger.warning("unattended_preflight: check failed: %s", e, exc_info=True)
                results.append(
                    {
                        "check_type": "unknown",
                        "status": "fail",
                        "message": f"检测异常: {str(e)}",
                    }
                )

    all_pass = all(r["status"] == "pass" for r in results)
    has_fail = any(r["status"] == "fail" for r in results)

    return Response(
        {
            "overall": "pass" if all_pass else ("fail" if has_fail else "warning"),
            "checks": results,
            "can_start": not has_fail,
        }
    )


@extend_schema(
    tags=['unattended'],
    summary='Device x account execution status matrix',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unattended_status_view(request):
    """
    运行状态矩阵 API — 使用数据库真实数据

    GET /api/unattended/status/
    返回设备×账户的实时执行状态矩阵。
    """
    # @api_view allowed: cross-model matrix aggregation (Device x GameAccount x TaskExecution)
    from django.utils.timezone import now

    from accounts.models import GameAccount
    from agents.models import Device
    from tasks.models import TaskExecution

    devices = list(Device.objects.all()[:12])
    accounts = list(GameAccount.objects.all()[:10])

    today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)

    # 修复: 使用 agent_id 和 triggered_by_id 替代 device_id 和 account_id
    recent_execs = {
        (e.agent_id or 0, e.triggered_by_id or 0): e
        for e in TaskExecution.objects.filter(created_at__gte=today_start)
        .select_related("task")
        .order_by("-created_at")[:200]
    }

    matrix = []
    for device in devices:
        row = {
            "device_id": device.id,
            "device_name": device.name,
            "device_status": device.status,
            "cells": [],
        }
        for account in accounts:
            # 修复: 使用 agent_id (Device) 和 triggered_by_id (GameAccount) 作为键
            exec_record = recent_execs.get((device.id, account.id))
            if exec_record:
                cell_state = exec_record.status or "idle"
                task_name = exec_record.task.name if hasattr(exec_record.task, "name") and exec_record.task else None
            else:
                cell_state = "idle"
                task_name = None
            row["cells"].append(
                {
                    "account_id": account.id,
                    "account_name": account.username,
                    "task_name": task_name,
                    "status": cell_state,
                    "progress": getattr(exec_record, "progress", 0) or 0,
                    "started_at": getattr(exec_record, "started_at", None),
                    "error_message": getattr(exec_record, "error_message", None),
                }
            )
        matrix.append(row)

    # P-011: return list of active sessions (multi-session parallel).
    # mode_status is kept for backward compat — "running" if any session
    # is RUNNING, "paused" if all active are PAUSED, "stopped" otherwise.
    active_sessions_qs = _get_active_sessions()
    active_sessions_list = list(active_sessions_qs)
    if any(s.status == UnattendedSession.Status.RUNNING for s in active_sessions_list):
        agg_mode_status = 'running'
    elif active_sessions_list and all(
        s.status == UnattendedSession.Status.PAUSED for s in active_sessions_list
    ):
        agg_mode_status = 'paused'
    else:
        agg_mode_status = 'stopped'

    return Response(
        {
            "mode_status": agg_mode_status,
            "active_sessions": [
                {
                    "id": s.id,
                    "status": s.status,
                    "mode_status": _map_session_to_mode_status(s),
                    "game_profile_id": s.game_profile_id,
                    "game_profile_name": s.game_profile.game_name if s.game_profile else None,
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "total_devices": s.total_devices,
                    "total_accounts": s.total_accounts,
                }
                for s in active_sessions_list
            ],
            "total_devices": len(devices),
            "total_accounts": len(accounts),
            "matrix": matrix,
        }
    )


@extend_schema(
    tags=['unattended'],
    summary='Execution queue preview',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unattended_queue_view(request):
    """
    执行队列预览 API — 使用数据库真实数据

    GET /api/unattended/queue/
    返回排队中的执行任务列表。
    """
    # @api_view allowed: custom queue preview (filtered TaskExecution with custom response shape)
    from tasks.models import TaskExecution

    limit = min(int(request.query_params.get("limit", "12").rstrip("/")), 50)

    # 修复: 使用正确的字段名，移除不存在的 account
    # TD-227 修复 (2026-07-18): 移除枚举外死值 'queued'/'warming_up' (TaskExecution.Status 无此状态)
    queue_execs = (
        TaskExecution.objects.filter(status__in=["running"])
        .select_related("task", "agent", "triggered_by")
        .order_by("created_at")[:limit]
    )

    queue = []
    for exec_record in queue_execs:
        # 修复: 使用 agent 替代 device, triggered_by 替代 account
        device_name = exec_record.agent.hostname if hasattr(exec_record, "agent") and exec_record.agent else ""
        account_name = (
            exec_record.triggered_by.username
            if hasattr(exec_record, "triggered_by") and exec_record.triggered_by
            else ""
        )
        task_name = exec_record.task.name if hasattr(exec_record.task, "name") and exec_record.task else ""

        queue.append(
            {
                "id": exec_record.id,
                "device_name": device_name,
                "account_name": account_name,
                "task_name": task_name,
                "estimated_start": (exec_record.started_at or exec_record.created_at).isoformat()
                if exec_record.started_at or exec_record.created_at
                else None,
                "status": exec_record.status or "queued",
                "priority": getattr(exec_record, "priority", 3) or 3,
            }
        )

    return Response(
        {
            "total": len(queue),
            "queue": queue,
        }
    )


@extend_schema(
    tags=['unattended'],
    summary='Today progress and estimated completion',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unattended_progress_view(request):
    """
    今日进度 API — 使用数据库真实数据

    GET /api/unattended/progress/
    返回今日执行统计和预计完成时间。
    """
    # @api_view allowed: today progress aggregation with ETA, not model CRUD
    from django.utils.timezone import now

    from tasks.models import TaskExecution

    today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)

    today_execs = TaskExecution.objects.filter(created_at__gte=today_start)

    # 修复: 使用 triggered_by_id 替代 account_id
    total_accounts = today_execs.values_list("triggered_by_id", flat=True).distinct().count()
    completed_count = today_execs.filter(status__in=["success", "failed", "cancelled"]).count()
    success_count = today_execs.filter(status="success").count()
    failed_count = today_execs.filter(status="failed").count()

    # TD-227 修复 (2026-07-18): 移除枚举外死值 'warming_up'/'queued' (TaskExecution.Status 无此状态)
    running_count = today_execs.filter(status__in=["running"]).count()
    queued_count = today_execs.filter(status__in=["pending"]).count()

    avg_duration_sec = (
        today_execs.filter(status="success").exclude(duration__isnull=True).values_list("duration", flat=True)
    )
    total_duration_sec = sum((d.total_seconds() for d in avg_duration_sec), 0)
    remaining_estimated = (
        (running_count + queued_count) * max(1, total_duration_sec // max(1, success_count))
        if success_count > 0
        else (running_count + queued_count) * 300
    )

    return Response(
        {
            "date": now().date().isoformat(),
            "total_accounts": max(total_accounts, 1),
            "completed": completed_count,
            "success": success_count,
            "failed": failed_count,
            "skipped": today_execs.filter(status="skipped").count(),
            "success_rate": round(success_count / max(1, completed_count) * 100, 1),
            "estimated_remaining_seconds": remaining_estimated,
        }
    )


@extend_schema(
    tags=['unattended'],
    summary='List unattended session history',
    responses={200: OpenApiTypes.OBJECT},
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def unattended_sessions_view(request):
    """List historical unattended sessions (P-009 Phase 1).

    GET /api/v2/scheduler/unattended/sessions/
    Returns recent sessions (most recent first), capped at 50 entries.
    """
    # @api_view allowed: cross-table read-only list aggregation with serializer
    sessions = UnattendedSession.objects.select_related('triggered_by').all()[:50]
    return Response({
        "sessions": [
            {
                "id": s.id,
                "status": s.status,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "stopped_at": s.stopped_at.isoformat() if s.stopped_at else None,
                "stop_reason": s.stop_reason,
                "total_devices": s.total_devices,
                "total_accounts": s.total_accounts,
                "triggered_by": s.triggered_by.username if s.triggered_by else None,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ],
    })
