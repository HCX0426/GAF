"""
TaskExecution / ExecutionStep 信号 (P-020-D + P-010 Phase 3)

监听 TaskExecution 状态变更:
- status 变为 'failed' → 触发任务级恢复 (handle_task_failure)
- status 变为 'success' 后下次变 'failed' → 计算连续失败次数

监听 ExecutionStep 状态变更 (P-010 Phase 3):
- status 变为 'failed' → 触发步骤级恢复 (handle_step_failure)
- 防递归: module-level _processing_step_ids set 防止恢复动作本身重复触发

设计:
- 使用 Django post_save signal (同步, 但内部 delegate 给 celery task 异步跑 ActionChain)
- 避免在 signal handler 内跑重活, 用 transaction.on_commit 提交后再触发
- 防递归: 自身恢复中不应再触发
"""

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from scheduler.recovery_engine import handle_step_failure, handle_task_failure

from protocol.broadcast import broadcast_to_dashboard

from .models import ExecutionStep, TaskExecution

logger = logging.getLogger(__name__)

# P-010 Phase 3: module-level anti-recursion guard for step-level recovery.
# When a step's post_save fires handle_step_failure, we add the step PK here
# before scheduling transaction.on_commit. Any re-entrant save of the same
# step (e.g. recovery action re-saving the row) sees the PK and skips. The
# PK is discarded in the on_commit callback's finally block so a genuine
# later failure (after recovery completes) can trigger again.
# Unlike TaskExecution.recovery_attempts (a model field), ExecutionStep has
# no equivalent column — we use an in-process set to avoid a migration.
_processing_step_ids: set[int] = set()


@receiver(post_save, sender=TaskExecution)
def trigger_recovery_on_task_failure(sender, instance, created, update_fields, **kwargs):
    """
    TaskExecution 保存后, 若 status 变为 'failed' 则触发任务级恢复 (P-020-D)

    Args:
        sender: TaskExecution class
        instance: 被保存的实例
        created: 是否新建
        update_fields: 实际更新的字段 (set or None)
    """
    # 只处理 status 变为 'failed' 的更新 (非创建)
    if created:
        return
    if instance.status != TaskExecution.Status.FAILED:
        return

    # 防递归: 如果是恢复动作本身 (recovery_attempts > 0 且 recovery_layer > 0) 触发的, 不再触发恢复
    if instance.recovery_attempts > 0 or instance.recovery_layer > 0:
        logger.debug(
            'TaskExecution %s 已被恢复 (%s/%s), 跳过信号触发',
            instance.id, instance.recovery_attempts, instance.recovery_layer,
        )
        return

    # 计算连续失败次数: 同 task 最近 N 条 execution 中连续的 failed
    consecutive = _count_consecutive_failures(instance)

    logger.info(
        'TaskExecution %s (task=%s) 失败, 触发恢复 (连续 %s 次)',
        instance.id, instance.task_id, consecutive,
    )

    # 用 transaction.on_commit 避免在事务回滚中执行恢复
    execution_id = instance.id

    def _run_recovery():
        """transaction.on_commit 回调: 触发 ActionChain 任务级恢复"""
        try:
            result = handle_task_failure(
                task_execution_id=execution_id,
                consecutive_failures=consecutive,
            )
            logger.info(
                'TaskExecution %s 恢复结果: action=%s, success=%s',
                execution_id, result.get('action'), result.get('success'),
            )
        except Exception as exc:
            logger.error('TaskExecution %s 恢复失败: %s', execution_id, exc)

    transaction.on_commit(_run_recovery)


@receiver(post_save, sender=ExecutionStep)
def trigger_recovery_on_step_failure(sender, instance, created, update_fields, **kwargs):
    """ExecutionStep 保存后, 若 status 为 FAILED 则触发步骤级恢复 (P-010 Phase 3).

    Unlike ``trigger_recovery_on_task_failure`` (which skips ``created=True``
    because TaskExecution is always created with PENDING), ExecutionStep CAN
    be created directly with status=FAILED — Phase 2's ``update_or_create``
    does exactly this when the agent reports a first-attempt failure. So we
    trigger on BOTH create and update when status=FAILED.

    Anti-recursion: ``handle_step_failure`` itself does not save ExecutionStep
    (confirmed: scheduler/recovery_engine.py never imports the model), but a
    future retry action might. We guard with the module-level
    ``_processing_step_ids`` set: add the PK before scheduling on_commit, and
    discard it in the callback's ``finally`` so a later genuine failure can
    trigger again.

    Args:
        sender: ExecutionStep class
        instance: the saved ExecutionStep
        created: True if newly created
        update_fields: fields actually updated (set or None)
    """
    if instance.status != ExecutionStep.Status.FAILED:
        return
    if instance.id is None:
        return
    if instance.id in _processing_step_ids:
        logger.debug(
            'ExecutionStep %s 已在恢复中, 跳过 signal 触发 (防递归)',
            instance.id,
        )
        return

    step_id = instance.id
    error_message = instance.error_message or ''
    _processing_step_ids.add(step_id)

    logger.info(
        'ExecutionStep %s (execution=%s) 失败, 触发步骤级恢复',
        step_id, instance.task_result_id,
    )

    def _run_step_recovery():
        """transaction.on_commit 回调: 触发 ActionChain 步骤级恢复."""
        try:
            result = handle_step_failure(
                execution_step_id=step_id,
                error_message=error_message,
            )
            logger.info(
                'ExecutionStep %s 恢复结果: action=%s, success=%s',
                step_id, result.get('action'), result.get('success'),
            )
        except Exception as exc:
            logger.error('ExecutionStep %s 恢复失败: %s', step_id, exc)
        finally:
            # Always release the guard so a later genuine failure can trigger
            # again, even if handle_step_failure raised.
            _processing_step_ids.discard(step_id)

    transaction.on_commit(_run_step_recovery)


@receiver(post_save, sender=TaskExecution)
def broadcast_execution_status(sender, instance, created, update_fields, **kwargs):
    """Broadcast execution status updates to WebSocket listeners (A030).

    spec-35 Phase 4.1 (2026-07-19): the ``execution_update`` broadcast to
    the execution-specific group was removed (the /ws/executions/{id}/
    consumer was dead code — frontend uses /ws/dashboard for step updates
    and does not subscribe to execution_update). This signal now only
    fires the ``notification`` event to the triggering user's notification
    group when ``triggered_by_id`` is set.
    """
    if created:
        return
    if update_fields and 'status' not in update_fields:
        return

    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    from notifications.consumers import broadcast_notification

    channel_layer = get_channel_layer()
    # spec-35 Phase 4.1 (2026-07-19): broadcast_execution_update call
    # removed — /ws/executions/{id}/ consumer deleted (frontend uses
    # /ws/dashboard for execution_step_update and does not subscribe
    # to execution_update). The notification group below remains.

    if instance.triggered_by_id:
        level = "info"
        if instance.status == TaskExecution.Status.FAILED:
            level = "error"
        elif instance.status in (TaskExecution.Status.CANCELLED, TaskExecution.Status.FORCE_TERMINATED):
            level = "warning"

        notification = {
            "level": level,
            "title": f"Execution #{instance.id} {instance.status}",
            "message": instance.error_message or f"Status changed to {instance.status}",
            "execution_id": instance.id,
        }
        async_to_sync(broadcast_notification)(
            channel_layer, instance.triggered_by_id, notification
        )


def _count_consecutive_failures(instance: TaskExecution) -> int:
    """
    计算 task 的最近连续失败次数

    Args:
        instance: 当前失败的 TaskExecution 实例

    Returns:
        连续失败次数 (≥ 1, 因为 instance 本身算 1 次)
    """
    # 找同 task 最近 10 条 execution, 按 created_at desc, 统计连续 failed 数
    recent = TaskExecution.objects.filter(
        task_id=instance.task_id,
    ).order_by('-created_at').values_list('status', flat=True)[:10]

    consecutive = 0
    for status in recent:
        if status == TaskExecution.Status.FAILED:
            consecutive += 1
        else:
            break
    return max(consecutive, 1)


@receiver(post_save, sender=ExecutionStep)
def broadcast_execution_step_update(sender, instance, created, update_fields, **kwargs):
    """Broadcast ExecutionStep progress to the execution's WS group (P3-2).

    Fires on both create and update so the frontend ExecutionMonitorPanel
    can upsert step status in real time without polling the REST endpoint.
    The broadcast is deferred to ``transaction.on_commit`` so we never push
    notifications about saves that get rolled back.

    Task 3.6 (P2-6): step_payload 新增 error_code 字段, 让前端按
    error.codes.<CODE> 映射多语言文案, 而非把后端 businessMessage (中文)
    原文甩给多语言用户 (N192 B1/B2: 错误提示归一 + 错误码映射)。
    优先取 instance.error_code (新建字段), 兜底从 recognition_result
    解析 (兼容 agent 把 error_code 写在 recognition_result 的场景)。
    """
    execution_id = instance.task_result_id
    # Task 3.6: 优先用 instance.error_code (Task 3.6 新增字段),
    # 兜底从 recognition_result 解析 (兼容老 agent / 重试场景)。
    error_code = instance.error_code or ''
    if not error_code and isinstance(instance.recognition_result, dict):
        # recognition_result 可能含 error_code 字段 (agent 上报路径)
        ec = instance.recognition_result.get('error_code')
        if isinstance(ec, str) and ec:
            error_code = ec
    step_payload = {
        "execution_id": execution_id,
        "step_index": instance.step_index,
        "node_id": instance.node_id,
        "step_name": instance.step_name,
        "step_type": instance.step_type,
        "status": instance.status,
        "duration_ms": instance.duration_ms,
        "duration_seconds": instance.duration,
        "started_at": instance.started_at.isoformat() if instance.started_at else None,
        "completed_at": instance.completed_at.isoformat() if instance.completed_at else None,
        "error_message": instance.error_message or None,
        # Task 3.6: 透传 error_code 给前端做 i18n 映射 (N192 B2)
        "error_code": error_code or None,
        # N192: 透传 user_message (错误码映射后的用户友好文案)
        "user_message": instance.user_message or None,
        "created": created,
    }

    def _broadcast():
        try:
            # Broadcast to the dashboard group so the FrontendConsumer
            # (which the browser wsClient connects to at /ws/dashboard) can
            # forward the event to the ExecutionMonitorPanel.
            # spec-35 Phase 4.1 (2026-07-19): the second group_send to
            # f"execution_{execution_id}" was removed — /ws/executions/{id}/
            # ExecutionConsumer deleted as dead code (frontend uses
            # /ws/dashboard for execution_step_update events).
            broadcast_to_dashboard("execution_step_update", step_payload)
        except Exception as exc:
            logger.warning(
                "Failed to broadcast execution.step_update for execution %s step %s: %s",
                execution_id, instance.step_index, exc,
            )

    transaction.on_commit(_broadcast)
