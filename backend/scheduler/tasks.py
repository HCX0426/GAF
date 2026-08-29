"""Celery tasks for unattended mode periodic tick (P-009 Phase 2).

This module drives the unattended loop. Celery beat triggers
``tick_unattended_session`` every 60s. For each RUNNING session, the
tick:

1. Checks time window (skips if outside)
2. For each idle device with default_task_chain:
   a. If session.rotation_rule is set: pick next account via
      ``calculate_account_order``, skipping already-dispatched accounts
   b. Else: use device.game_account (legacy one-shot behavior)
   c. If device already has an active chain execution, skip (busy)
   d. Dispatch chain via ``create_chain_execution_and_dispatch``
3. Tracks dispatched chain_executions on session.active_chain_executions
   and account IDs on session.dispatched_account_ids

Completion hooks (post_save signal in ``scheduler/signals.py``) remove
completed chains from active_chain_executions and trigger AutoStop.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from scheduler.models import RecoveryLog, UnattendedSession

logger = logging.getLogger(__name__)


@shared_task(acks_late=True, max_retries=3, retry_backoff=30)
def tick_unattended_session():
    """Periodic tick (every 60s) — drives the unattended loop.

    See module docstring for the full flow.
    """
    from scheduler.engine import check_time_window

    # Quick global gate: skip if outside time window
    if not check_time_window():
        logger.debug("tick_unattended_session: outside time window, skipping")
        return

    # Lock active sessions to prevent concurrent ticks (multi-worker safety)
    with transaction.atomic():
        sessions = UnattendedSession.objects.select_for_update(
            skip_locked=True,
        ).filter(status=UnattendedSession.Status.RUNNING)
        for session in sessions:
            try:
                _tick_session(session)
            except Exception:
                logger.exception(
                    "tick_unattended_session: error processing session %s",
                    session.id,
                )


def _tick_session(session):
    """Process a single RUNNING session.

    For each idle device with default_task_chain, dispatch the next account's
    chain. If rotation_rule is set, pick the next undispatched account.
    """
    from pipeline.models import TaskChainExecution
    from pipeline.services import (
        ChainDispatchError,
        create_chain_execution_and_dispatch,
    )

    from agents.models import Agent, Device
    from scheduler.engine import calculate_account_order

    online_statuses = (Agent.Status.ONLINE, Agent.Status.IDLE)
    # TD-112: filter both agent.status (process online) AND device.status
    # (window/emulator usable). Only ONLINE devices are candidates — BUSY
    # devices are already running something, OFFLINE/ERROR are unusable.
    # P-011: scope devices by session.game_profile_id so parallel sessions
    # for different GameProfiles don't steal each other's devices. Without
    # this filter, session A (game_profile=7) would also dispatch devices
    # bound to game_profile=9 — the `has_active` check below only prevents
    # double-dispatch of the same device, not cross-session candidate
    # contamination.
    devices = Device.objects.filter(
        agent__status__in=online_statuses,
        status=Device.Status.ONLINE,
        game_profile_id=session.game_profile_id,
        game_profile__default_task_chain__isnull=False,
    ).select_related('game_profile__default_task_chain', 'agent', 'game_account')

    # Determine candidate accounts for rotation
    rotation_rule = session.rotation_rule
    if rotation_rule:
        all_accounts = list(rotation_rule.accounts.all())
        ordered_accounts = calculate_account_order(rotation_rule, all_accounts)
        dispatched_set = set(session.dispatched_account_ids or [])
    else:
        ordered_accounts = []
        dispatched_set = set(session.dispatched_account_ids or [])

    for device in devices:
        chain = device.game_profile.default_task_chain
        if not chain.is_enabled:
            continue

        # Skip if device already has an active chain execution
        has_active = TaskChainExecution.objects.filter(
            device_id=device.id,
            status__in=[
                TaskChainExecution.Status.PENDING,
                TaskChainExecution.Status.RUNNING,
            ],
        ).exists()
        if has_active:
            continue

        # Determine which account to dispatch
        if rotation_rule:
            # Pick next undispatched account from rotation order
            remaining = [a for a in ordered_accounts if a.id not in dispatched_set]
            if not remaining:
                continue  # All accounts dispatched, wait for completion
            if session.loop_rotation and len(ordered_accounts) > 1:
                # Fair rotation (2026-08-27): in loop mode a session-level
                # cursor advances past the previously picked account, so a
                # single device cycles through ALL accounts instead of always
                # selecting ordered_accounts[0] (which returns the first
                # account every round once the pool is returned).
                n = len(ordered_accounts)
                account = None
                for i in range(n):
                    candidate = ordered_accounts[(session.rotation_index + i) % n]
                    if candidate.id not in dispatched_set:
                        account = candidate
                        break
                if account is None:
                    continue
            else:
                account = remaining[0]
            # Switch device's game_account if needed
            if device.game_account_id != account.id:
                device.game_account_id = account.id
                device.save(update_fields=['game_account_id'])
        else:
            # Legacy: use device's current game_account
            account = device.game_account
            if not account:
                continue
            # Track dispatched (legacy: only dispatch each account once)
            if account.id in dispatched_set:
                continue

        # Dispatch
        try:
            chain_execution = create_chain_execution_and_dispatch(
                chain_id=chain.id,
                agent_id=device.agent.agent_id if device.agent else None,
                device_id=device.id,
                game_account_id=account.id if account else None,
                triggered_by=session.triggered_by,
            )
        except ChainDispatchError as exc:
            logger.warning(
                "tick_unattended_session: dispatch failed for device %s: %s",
                device.id, exc,
            )
            continue

        # Track on session
        session.active_chain_executions.add(chain_execution)
        if account and account.id not in dispatched_set:
            dispatched_set.add(account.id)
            dispatched_list = list(session.dispatched_account_ids or [])
            dispatched_list.append(account.id)
            session.dispatched_account_ids = dispatched_list
            session.save(update_fields=['dispatched_account_ids'])
        if session.loop_rotation and len(ordered_accounts) > 1:
            # Advance the fair-rotation cursor after each successful dispatch.
            session.rotation_index = (session.rotation_index or 0) + 1
            session.save(update_fields=['rotation_index'])

        logger.info(
            "tick_unattended_session: dispatched chain_execution %s "
            "for device %s account %s session %s",
            chain_execution.id, device.id,
            account.id if account else None,
            session.id,
        )


# ---------------------------------------------------------------------------
# P-009 Phase 3: Chain execution completion hook
# ---------------------------------------------------------------------------


@shared_task(acks_late=True, max_retries=3, retry_backoff=60)
def on_chain_execution_completed(chain_execution_id):
    """Handle TaskChainExecution completion (P-009 Phase 3).

    Called by the ``post_save`` signal in ``scheduler/signals.py`` when a
    TaskChainExecution reaches SUCCESS / FAILED / CANCELLED. For each
    RUNNING UnattendedSession tracking this chain:

    1. Remove the chain from ``session.active_chain_executions``
    2. Update ``session.failed_count`` (increment on FAILED, reset on SUCCESS)
    3. Increment ``session.completed_chain_count``
    4. For FAILED: call ``recovery_engine.handle_task_failure`` with the
       session-level consecutive failure count
    5. Check ``AutoStopCondition`` — stop the session if triggered

    Note on recovery engine double-trigger: ``tasks/signals.py`` already
    calls ``handle_task_failure`` when an individual TaskExecution fails
    (using per-task consecutive count). This chain-level call uses the
    session-level count, which is a higher-level signal ("N consecutive
    chains have failed in this unattended session"). Both calls are
    intentional — the recovery engine's threshold check (default 3)
    makes low-count calls a no-op.
    """
    from pipeline.models import TaskChainExecution

    try:
        chain_exec = TaskChainExecution.objects.get(pk=chain_execution_id)
    except TaskChainExecution.DoesNotExist:
        logger.warning(
            "on_chain_execution_completed: TaskChainExecution %s not found",
            chain_execution_id,
        )
        return

    # Find RUNNING sessions tracking this chain
    sessions = UnattendedSession.objects.filter(
        active_chain_executions=chain_exec,
        status=UnattendedSession.Status.RUNNING,
    )

    if not sessions.exists():
        # Not an unattended chain, or session already stopped/paused
        return

    for session in sessions:
        try:
            _process_chain_completion(session, chain_exec)
        except Exception:
            logger.exception(
                "on_chain_execution_completed: error processing session %s "
                "for chain %s",
                session.id, chain_exec.id,
            )


def _process_chain_completion(session, chain_exec):
    """Process a single session's reaction to a chain execution completion.

    TD-402 ④ (2026-08-27): the whole mutation runs under a session row lock
    so concurrent completions for the same session can't lose updates to
    dispatched_account_ids / failed_count / completed_chain_count (the tick
    loop already locks the session with select_for_update(skip_locked=True)).
    """
    from django.db import transaction
    from pipeline.models import TaskChainExecution

    with transaction.atomic():
        session = UnattendedSession.objects.select_for_update().get(pk=session.pk)

        # 1. Remove from active chains
        session.active_chain_executions.remove(chain_exec)

        # 2. Update failed_count and completed_chain_count
        session.completed_chain_count = (session.completed_chain_count or 0) + 1
        update_fields = ['completed_chain_count']

        if chain_exec.status == TaskChainExecution.Status.FAILED:
            session.failed_count = (session.failed_count or 0) + 1
            update_fields.append('failed_count')
        elif chain_exec.status == TaskChainExecution.Status.SUCCESS:
            # Reset consecutive failure counter on success
            session.failed_count = 0
            update_fields.append('failed_count')
        # CANCELLED: neutral — don't change failed_count

        session.save(update_fields=update_fields)

        # TD-400 (2026-08-26): loop rotation — return the finished account to
        # the rotation pool so tick_unattended_session can dispatch it again in
        # the next round. One account owns at most one chain per session
        # (dispatched set is globally unique). Only when still RUNNING.
        if session.loop_rotation and session.status == UnattendedSession.Status.RUNNING:
            returned_id = chain_exec.game_account_id
            dispatched = list(session.dispatched_account_ids or [])
            if returned_id and returned_id in dispatched:
                dispatched.remove(returned_id)
                session.dispatched_account_ids = dispatched
                session.save(update_fields=['dispatched_account_ids'])
                logger.info(
                    "on_chain_execution_completed: loop_rotation returned account %s "
                    "to the pool for session %s",
                    returned_id, session.id,
                )

        logger.info(
            "on_chain_execution_completed: session %s processed chain %s "
            "(status=%s, failed_count=%s, completed=%s)",
            session.id, chain_exec.id, chain_exec.status,
            session.failed_count, session.completed_chain_count,
        )

        # 3. Recovery engine (FAILED only)
        if chain_exec.status == TaskChainExecution.Status.FAILED:
            _trigger_chain_recovery(chain_exec, session.failed_count)

        # 4. AutoStop check
        _check_auto_stop(session)


def _trigger_chain_recovery(chain_exec, consecutive_failures):
    """Call the recovery engine for a failed chain execution.

    Finds the failed TaskExecution within this chain and delegates to
    ``handle_task_failure`` with the session-level consecutive count.
    """
    from tasks.models import TaskExecution

    failed_task_exec = TaskExecution.objects.filter(
        chain_execution=chain_exec,
        status=TaskExecution.Status.FAILED,
    ).order_by('-created_at').first()

    if not failed_task_exec:
        logger.info(
            "on_chain_execution_completed: no failed TaskExecution found "
            "for chain %s, skipping recovery",
            chain_exec.id,
        )
        return

    try:
        from scheduler.recovery_engine import handle_task_failure
        result = handle_task_failure(
            task_execution_id=failed_task_exec.id,
            consecutive_failures=consecutive_failures,
        )
        logger.info(
            "on_chain_execution_completed: recovery result for task %s: "
            "action=%s, success=%s",
            failed_task_exec.id, result.get('action'), result.get('success'),
        )
    except Exception:
        logger.exception(
            "on_chain_execution_completed: recovery engine failed for "
            "chain %s",
            chain_exec.id,
        )


def _check_auto_stop(session):
    """Check AutoStop conditions and stop the session if triggered.

    Evaluates:
    - ``consecutive_failures``: from ``session.failed_count``
    - ``all_accounts_completed``: all dispatched accounts' chains have
      completed and no active chains remain
    - ``window_end``: current time is outside the configured time window
    """
    from scheduler.engine import check_auto_stop_conditions, check_time_window

    dispatched_count = len(session.dispatched_account_ids or [])
    active_count = session.active_chain_executions.count()
    # TD-400: loop_rotation disables all_completed — a finished round must not
    # stop the session (accounts are returned to the pool). Stop via manual /
    # time-window / consecutive-failure conditions instead.
    all_completed = (
        not session.loop_rotation
        and dispatched_count > 0
        and (session.completed_chain_count or 0) >= dispatched_count
        and active_count == 0
    )

    in_time_window = check_time_window()

    triggered = check_auto_stop_conditions(
        consecutive_failures=session.failed_count or 0,
        all_accounts_completed=all_completed,
        in_time_window=in_time_window,
    )

    if not triggered:
        return

    cond = triggered[0]
    session.status = UnattendedSession.Status.STOPPED
    session.stopped_at = timezone.now()
    session.stop_reason = f'AutoStop: {cond.get_condition_type_display()}'
    session.save(update_fields=['status', 'stopped_at', 'stop_reason'])

    logger.info(
        "on_chain_execution_completed: AutoStop triggered for session %s "
        "(condition=%s, action=%s, reason=%s)",
        session.id, cond.condition_type, cond.action, session.stop_reason,
    )


# ---------------------------------------------------------------------------
# P-048: App freeze detection
# ---------------------------------------------------------------------------


@shared_task(acks_late=True, max_retries=3, retry_backoff=30)
def detect_app_freeze():
    """检测应用卡死: RUNNING ExecutionStep 超 freezeTimeoutSeconds 触发 handle_app_freeze.

    Celery Beat 按策略配置周期调度 (默认 30s).
    扫描所有 RUNNING ExecutionStep, 检查其 started_at 是否超过 freezeTimeoutSeconds.
    """
    from scheduler.recovery_engine import get_strategy_config, handle_app_freeze
    from tasks.models import ExecutionStep, TaskExecution

    config = get_strategy_config()
    app_config = config.get('appLevel', {})

    if not app_config.get('freezeDetection', True):
        logger.debug('detect_app_freeze: 应用级卡死检测已禁用')
        return

    freeze_timeout = app_config.get('freezeTimeoutSeconds', 120)
    threshold = timezone.now() - timedelta(seconds=freeze_timeout)

    # 查找所有 RUNNING 且超时的 ExecutionStep, 关联有效的 TaskExecution 和 Device
    frozen_steps = ExecutionStep.objects.filter(
        status=ExecutionStep.Status.RUNNING,
        started_at__lt=threshold,
        task_result__status=TaskExecution.Status.RUNNING,
        task_result__device__isnull=False,
    ).select_related('task_result__device')

    for step in frozen_steps:
        execution = step.task_result
        device = execution.device
        freeze_duration = int((timezone.now() - step.started_at).total_seconds())

        # Dedup: 同设备在 dedup 窗口内已有 app-level RecoveryLog 则跳过
        dedup_window = timezone.now() - timedelta(seconds=freeze_timeout)
        recent_log = RecoveryLog.objects.filter(
            recovery_level='app',
            details__target_id=device.id,
            created_at__gte=dedup_window,
        ).exists()

        if recent_log:
            logger.debug(
                'detect_app_freeze: dedup skip for device %s (step %s)',
                device.id, step.id,
            )
            continue

        handle_app_freeze(
            device_id=device.id,
            freeze_duration_seconds=freeze_duration,
        )
