"""Task monitoring services — cancel timeout, execution timeout, heartbeat timeout.

Extracted from the flat services.py during Phase 1 refactoring (2026-08-08).
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

CANCEL_TIMEOUT_SECONDS = 10
DEFAULT_EXECUTION_TIMEOUT_SECONDS = 3600


def _release_concurrency_slot(agent_id, execution_id):
    """Release a per-agent concurrency slot held by an execution.

    Used by the force-terminate paths (cancel / execution / heartbeat
    timeout) so the ``ConcurrencyController`` map stays accurate when
    executions are transitioned out of RUNNING without going through
    the normal ``task.completed`` / ``task.failed`` consumer path.

    Safe to call when no slot was acquired — ``release`` discards
    unknown (agent_id, execution_id) pairs silently.

    Args:
        agent_id: ``Agent.agent_id`` string identifier.
        execution_id: ``TaskExecution.id`` (any scalar — coerced to str).
    """
    if not agent_id or not execution_id:
        return
    try:
        from tasks.concurrency_controller import get_default_controller

        controller = get_default_controller()
        controller.release(agent_id, str(execution_id))
        logger.debug(
            "ConcurrencyController: released agent=%s execution=%s (load=%d)",
            agent_id,
            execution_id,
            controller.get_agent_load(agent_id),
        )
    except Exception as exc:
        logger.warning("ConcurrencyController.release failed: %s", exc)


def _restore_device_status(execution):
    """Restore a device's status to ONLINE after an execution finishes.

    Multi-instance aware: only flips the device back to ONLINE when no
    other RUNNING execution is still bound to it. This lets two tasks
    target different devices on the same agent without one completion
    clobbering the other device's BUSY state.

    Called from the same 5 release points as
    :func:`_release_concurrency_slot` (task.completed / task.failed
    consumer handlers + cancel / execution / heartbeat timeout sweeps)
    so Device.status stays in sync with execution lifecycle.

    Safe to call when ``execution.device`` is None (legacy executions
    without a device FK) — silently no-ops.

    Args:
        execution: A ``TaskExecution`` instance. Must have been saved
            with its final status (SUCCESS / FAILED / FORCE_TERMINATED)
            BEFORE this call so the "still RUNNING on this device?" query
            below excludes it correctly. If the caller hasn't saved yet,
            pass ``execution.id`` and the in-memory status together.
    """
    if execution is None or execution.device_id is None:
        return
    try:
        from workers.models import Device

        from tasks.models import TaskExecution

        # Are any other executions still RUNNING on this device? If yes,
        # keep the device BUSY — multi-instance scenario where two tasks
        # share a device (rare, but supported by the schema).
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
            "Device %s restored to ONLINE (execution %s finalized)",
            execution.device_id,
            execution.id,
        )
    except Exception as exc:
        logger.warning(
            "_restore_device_status failed for execution %s: %s",
            getattr(execution, "id", "?"),
            exc,
        )


def _restore_device_status_by_msg(msg_data):
    """Restore Device.status to ONLINE using an agent message payload.

    Handler-layer wrapper around :func:`_restore_device_status` so that
    ``_handle_task_completed`` / ``_handle_task_failed`` can release the
    device alongside the concurrency slot WITHOUT depending on
    ``_finalize_execution`` being executed (tests and force-terminate
    paths may swap out ``_finalize_execution``).

    Loads the ``TaskExecution`` by ``execution_id`` from ``msg_data``
    and delegates to :func:`_restore_device_status`. Safe to call when
    the execution is missing or has no device — silently no-ops.

    Args:
        msg_data: Agent message ``data`` payload, must contain
            ``execution_id``. Missing or empty execution_id is a no-op.
    """
    execution_id = msg_data.get("execution_id", "")
    if not execution_id:
        return
    try:
        from tasks.models import TaskExecution

        execution = TaskExecution.objects.get(id=execution_id)
    except (TaskExecution.DoesNotExist, ValueError):
        return
    _restore_device_status(execution)


class TaskMonitorService:
    """任务监控服务，处理任务取消超时和 Agent 心跳超时。"""

    @staticmethod
    @shared_task(name="tasks.services.check_cancel_timeout", acks_late=True, max_retries=3, retry_backoff=30)
    def check_cancel_timeout():
        """检查取消中的任务是否超时（默认10秒），超时则标记为 FORCE_TERMINATED。

        遍历所有状态为 cancelled 的 TaskExecution，如果其 updated_at 距今
        超过 CANCEL_TIMEOUT_SECONDS，说明 Agent 未在规定时间内响应取消请求，
        将其强制标记为 force_terminated。
        """
        from gaf_core.error_codes import NodeErrorCode

        from tasks.models import TaskExecution

        threshold = timezone.now() - timedelta(seconds=CANCEL_TIMEOUT_SECONDS)
        timed_out_executions = TaskExecution.objects.filter(
            status=TaskExecution.Status.CANCELLED,
            updated_at__lt=threshold,
        )

        count = 0
        for execution in timed_out_executions:
            execution.status = TaskExecution.Status.FORCE_TERMINATED
            execution.error_message = (
                execution.error_message or ""
            ) + "; 取消超时，强制终止"
            # N192: 设置 error_code 让前端能按错误码分类展示
            execution.error_code = NodeErrorCode.INTERRUPTED.value
            execution.completed_at = timezone.now()
            execution.save(
                update_fields=[
                    "status",
                    "error_message",
                    "error_code",
                    "completed_at",
                    "updated_at",
                ]
            )

            if execution.agent:
                from workers.models import Worker

                execution.agent.status = Worker.Status.IDLE
                execution.agent.save(update_fields=["status"])
                # Release the concurrency slot acquired at dispatch time
                # so the agent can accept new tasks immediately.
                _release_concurrency_slot(execution.agent.agent_id, execution.id)

            # Restore the device to ONLINE (multi-instance aware).
            _restore_device_status(execution)

            count += 1
            logger.info(
                "任务执行 %s 取消超时，已强制终止",
                execution.id,
            )

        if count:
            logger.info("共处理 %d 条取消超时的任务执行记录", count)
        return count

    @staticmethod
    @shared_task(name="tasks.services.check_execution_timeout", acks_late=True, max_retries=3, retry_backoff=30)
    def check_execution_timeout():
        """检查运行中的任务是否超过 timeout，超时则标记为 FAILED。

        从 TaskExecution 的 task_definition 或 params 中读取 timeout 配置，
        默认为 DEFAULT_EXECUTION_TIMEOUT_SECONDS。如果 started_at + timeout < now，
        则标记为 failed。
        """
        from gaf_core.error_codes import NodeErrorCode

        from tasks.models import TaskExecution

        running_executions = TaskExecution.objects.filter(
            status=TaskExecution.Status.RUNNING,
            started_at__isnull=False,
        )

        count = 0
        now = timezone.now()
        for execution in running_executions:
            timeout_seconds = DEFAULT_EXECUTION_TIMEOUT_SECONDS
            task_def = execution.task.task_definition if execution.task else {}
            if isinstance(task_def, dict):
                timeout_seconds = task_def.get("timeout", DEFAULT_EXECUTION_TIMEOUT_SECONDS)

            timeout_delta = timedelta(seconds=timeout_seconds)
            if execution.started_at + timeout_delta < now:
                execution.status = TaskExecution.Status.FAILED
                execution.error_message = (
                    execution.error_message or ""
                ) + f"; 任务执行超时（{timeout_seconds}秒）"
                # N192: 设置 error_code 让前端能按错误码分类展示
                execution.error_code = NodeErrorCode.TIMEOUT.value
                execution.completed_at = now
                execution.duration = now - execution.started_at
                execution.save(
                    update_fields=[
                        "status",
                        "error_message",
                        "error_code",
                        "completed_at",
                        "duration",
                        "updated_at",
                    ]
                )

                if execution.agent:
                    from workers.models import Worker

                    execution.agent.status = Worker.Status.IDLE
                    execution.agent.save(update_fields=["status"])
                    # Release the concurrency slot acquired at dispatch
                    # time — the agent is now idle and can accept new work.
                    _release_concurrency_slot(execution.agent.agent_id, execution.id)

                # Restore the device to ONLINE (multi-instance aware).
                _restore_device_status(execution)

                count += 1
                logger.info(
                    "任务执行 %s 超时（%d秒），已标记为失败",
                    execution.id,
                    timeout_seconds,
                )

        if count:
            logger.info("共处理 %d 条执行超时的任务执行记录", count)
        return count

    @staticmethod
    @shared_task(name="tasks.services.check_pending_timeout", acks_late=True, max_retries=3, retry_backoff=30)
    def check_pending_timeout():
        """检查等待中的任务是否超过分配超时（默认300秒），超时则标记为 FAILED。

        防止任务长期处于 pending 状态而无法被分配到 Agent。

        N192: 使用 per-object save 而非 bulk .update(), 确保触发 post_save signal
        (broadcast_execution_status 通知前端 + trigger_recovery_on_task_failure 触发恢复).
        """
        from gaf_core.error_codes import NodeErrorCode

        from tasks.models import TaskExecution

        threshold = timezone.now() - timedelta(seconds=300)
        timed_out_executions = list(
            TaskExecution.objects.filter(
                status=TaskExecution.Status.PENDING,
                created_at__lt=threshold,
            )
        )

        now = timezone.now()
        for execution in timed_out_executions:
            execution.status = TaskExecution.Status.FAILED
            execution.error_message = "任务等待超时，无可用 Agent 分配"
            execution.error_code = NodeErrorCode.UNKNOWN.value
            execution.completed_at = now
            # Per-object save → triggers post_save signals
            execution.save(
                update_fields=[
                    "status", "error_message", "error_code",
                    "completed_at", "updated_at",
                ]
            )

        count = len(timed_out_executions)
        if count:
            logger.info("共处理 %d 条等待超时的任务执行记录", count)
        return count

    @staticmethod
    @shared_task(name="tasks.services.check_heartbeat_timeout", acks_late=True, max_retries=3, retry_backoff=60)
    def check_heartbeat_timeout():
        """检查 Agent 心跳超时，将超时 Agent 标记为离线并释放其任务。

        如果 Agent 的 last_heartbeat 距今超过 60 秒，则将其状态标记为
        offline，并将其正在执行的任务标记为 FAILED。

        N192: 使用 per-object save 而非 bulk .update(), 确保触发 post_save signal
        (broadcast_execution_status 通知前端 + trigger_recovery_on_task_failure 触发恢复).
        """
        from gaf_core.error_codes import NodeErrorCode
        from workers.models import Worker

        from tasks.models import TaskExecution

        heartbeat_threshold = timezone.now() - timedelta(seconds=60)
        # NULL-safe: 从未心跳 (last_heartbeat=None) 的记录也必须算作超时 —
        # Django ``__lt`` 不匹配 NULL, 单独 OR 会留下永远 ONLINE 的幻影 agent
        # (与 tasks/heartbeat.py check_agent_heartbeats 对齐, 2026-08-27).
        offline_agents = Worker.objects.filter(
            status__in=["online", "busy", "idle"],
        ).filter(
            Q(last_heartbeat__isnull=True) | Q(last_heartbeat__lt=heartbeat_threshold),
        )

        count = 0
        now = timezone.now()
        for agent in offline_agents:
            # Fetch the affected executions BEFORE the bulk update so we
            # can release each one's concurrency slot (the in-memory
            # objects still carry agent=agent from the queryset).
            affected_executions = list(
                TaskExecution.objects.filter(
                    agent=agent,
                    status=TaskExecution.Status.RUNNING,
                )
            )

            # N192: per-object save to trigger post_save signals
            for execution in affected_executions:
                execution.status = TaskExecution.Status.FAILED
                execution.error_message = "Agent 心跳超时，任务中断"
                execution.error_code = NodeErrorCode.DEVICE_DISCONNECTED.value
                execution.completed_at = now
                execution.save(
                    update_fields=[
                        "status", "error_message", "error_code",
                        "completed_at", "updated_at",
                    ]
                )

            # Release the concurrency slot for each force-failed execution
            # so the controller map doesn't leak when the agent comes back.
            for execution in affected_executions:
                _release_concurrency_slot(agent.agent_id, execution.id)
                # Restore the device to ONLINE (multi-instance aware).
                _restore_device_status(execution)

            agent.status = Worker.Status.OFFLINE
            agent.save(update_fields=["status"])

            # 一致性: agent 离线 → 其窗口 (Device) 联动离线 — 与
            # tasks/heartbeat.py mark_agent_devices_offline 同规则。
            # 放在 executions 处理之后 (_restore_device_status 先恢复 BUSY
            # 设备为 ONLINE, 再统一置 OFFLINE, 次序正确)。
            from tasks.heartbeat import mark_agent_devices_offline
            mark_agent_devices_offline(agent)

            count += 1
            logger.info(
                "Agent %s 心跳超时，已标记为离线，影响 %d 个任务",
                agent.agent_id,
                len(affected_executions),
            )

        if count:
            logger.info("共处理 %d 个心跳超时的 Agent", count)
        return count
