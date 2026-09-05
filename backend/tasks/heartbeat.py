"""
Agent 心跳超时检测与执行释放 (N197 增强版)

当 Agent 心跳超时 (30s) 时:
  1. 标记 Agent 为 OFFLINE
  2. 取消该 Agent 上所有 RUNNING 状态的执行
  3. 释放设备锁 (Device.status → ONLINE)

Celery Beat 调度周期: 5s (config/celery.py)
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone
from workers.models import Worker

from tasks.models import TaskExecution

logger = logging.getLogger(__name__)

# S1 (2026-08-16): dispatch ack 超时阈值 — group_send 后 agent 应在
# 网络正常时 <1s 回 ack; 10s 未确认视为帧丢失或 agent 处理异常.
DISPATCH_ACK_TIMEOUT_SECONDS = 10
DISPATCH_MAX_ATTEMPTS = 3

# TD-425 (2026-09-05): 链执行卡死清理 — TaskChainExecution 卡 running 超
# 该阈值且无活跃(PENDING/RUNNING)节点执行 → 判定僵尸链. 链完成依赖
# advance_chain_execution (从最后完成的节点执行推进); 节点执行从未终态或
# advance 未被触发时链永久 running, device_busy 永久阻塞该设备后续派发.
CHAIN_STUCK_TIMEOUT_SECONDS = 1800  # 30min


def mark_agent_devices_offline(agent) -> int:
    """Agent 离线 → 其管理的窗口 (Device) 联动离线 (一致性, 2026-08-27).

    Model (docs/architecture/overview.md §Agent/Device): one machine runs one
    Agent; the Agent discovers every window on it (PC windows + emulator
    instances). When the machine is unreachable (heartbeat timeout → agent
    OFFLINE), none of its windows are controllable — leaving them ONLINE would
    let the scheduler/matrix dispatch to a dead agent. The agent reconnect path
    (heartbeat / scan-register) flips its devices back ONLINE, so this is
    self-healing.

    Returns the number of devices flipped.
    """
    from workers.models import Device

    updated = Device.objects.filter(
        agent=agent,
        status__in=[Device.Status.ONLINE, Device.Status.BUSY],
    ).update(status=Device.Status.OFFLINE)
    if updated:
        logger.info(
            "mark_agent_devices_offline: agent %s -> %d windows offline",
            agent.agent_id, updated,
        )
    return updated


def _fail_execution_dispatch_timeout(execution):
    """Fail an execution whose dispatch was never acknowledged (S1).

    Called by ``check_dispatch_acks`` when an agent went OFFLINE (or retries
    are exhausted) before confirming receipt of the task.dispatch frame.
    Releases the concurrency slot + restores Device.status like the other
    force-fail paths so no resource leaks on this path either.
    """
    from gaf_core.error_codes import NodeErrorCode

    now = timezone.now()
    execution.status = TaskExecution.Status.FAILED
    execution.error_message = "派发未确认: agent 未回执任务派发, 已判定失败"
    execution.error_code = NodeErrorCode.UNKNOWN.value
    execution.completed_at = now
    execution.save(update_fields=['status', 'error_message', 'error_code', 'completed_at'])
    _restore_device_status(execution)
    try:
        from tasks.services.monitor_service import _release_concurrency_slot
        _release_concurrency_slot(execution.agent_id, str(execution.id))
    except Exception as exc:
        logger.warning("check_dispatch_acks: 释放并发槽位失败: %s", exc)
    logger.info(
        "check_dispatch_acks: execution %s 派发未确认, 已 fail (agent=%s)",
        execution.id, execution.agent_id,
    )


def _restore_device_status(execution):
    """Restore a device's status to ONLINE after an execution is force-failed.

    Args:
        execution: A ``TaskExecution`` instance (must have device_id set).
    """
    if execution is None or execution.device_id is None:
        return
    try:
        from workers.models import Device as _Device
        still_running = TaskExecution.objects.filter(
            device_id=execution.device_id,
            status=TaskExecution.Status.RUNNING,
        ).exclude(id=execution.id).exists()
        if not still_running:
            _Device.objects.filter(
                id=execution.device_id,
                status=_Device.Status.BUSY,
            ).update(status=_Device.Status.ONLINE)
    except Exception as exc:
        logger.warning("heartbeat._restore_device_status failed: %s", exc)


@shared_task(acks_late=True, max_retries=3, retry_backoff=30)
def check_agent_heartbeats():
    """检查 Agent 心跳超时，调用恢复引擎并标记离线。

    覆盖所有非 OFFLINE 状态 (ONLINE/BUSY/IDLE)，确保即使 Agent
    在忙碌中崩溃，执行和设备也能被释放。

    数据流:
    1. 找到心跳超时的 stale agent
    2. 调用 recovery_engine.handle_agent_timeout 执行系统级恢复链
    3. 标记 agent 为 OFFLINE
    4. 若恢复引擎返回 'waiting' 或抛出异常, 直接 fail 所有 RUNNING 执行
    """
    timeout_threshold = timezone.now() - timedelta(seconds=30)
    # NOTE (2026-08-27): `last_heartbeat__lt=threshold` alone does NOT match
    # NULL heartbeats (NULL < timestamp is NULL in SQL). An agent row created
    # before the process ever heartbeated (e.g. legacy/manual record with
    # status=ONLINE) would stay ONLINE forever and appear as a phantom agent
    # on the dashboard. Union the IS NULL case so those rows are flipped OFFLINE
    # too — the real agent process re-registers online on its next heartbeat.
    stale_agents = Worker.objects.filter(
        status__in=[Worker.Status.ONLINE, Worker.Status.BUSY, Worker.Status.IDLE],
    ).filter(
        Q(last_heartbeat__isnull=True) | Q(last_heartbeat__lt=timeout_threshold),
    )
    for agent in stale_agents:
        if agent.last_heartbeat is None:
            timeout_duration = 3600  # never heartbeated — treat as max timeout
        else:
            timeout_duration = int((timezone.now() - agent.last_heartbeat).total_seconds())

        # 1. 调用恢复引擎
        try:
            from scheduler.recovery_engine import handle_agent_timeout
            result = handle_agent_timeout(
                agent_id=agent.agent_id,
                timeout_duration_seconds=timeout_duration,
            )
        except Exception as exc:
            logger.warning(
                "check_agent_heartbeats: handle_agent_timeout failed for %s: %s",
                agent.agent_id, exc,
            )
            result = {'action': 'waiting'}

        # 2. 标记 Agent 为 OFFLINE
        agent.status = Worker.Status.OFFLINE
        agent.save(update_fields=['status'])

        # 3. 若 action 为 'waiting' (grace period 未到) 或 fallback 异常,
        #    直接 fail 所有 RUNNING 执行
        if result.get('action') == 'waiting':
            running_execs = list(
                TaskExecution.objects.filter(
                    agent=agent,
                    status=TaskExecution.Status.RUNNING,
                )
            )
            for exec_ in running_execs:
                exec_.status = TaskExecution.Status.FAILED
                exec_.error_message = f"Agent {agent.agent_id} 心跳超时，任务中断"
                # N192: 设置 error_code 让前端能按错误码分类展示
                from gaf_core.error_codes import NodeErrorCode
                exec_.error_code = NodeErrorCode.DEVICE_DISCONNECTED.value
                exec_.completed_at = timezone.now()
                exec_.save(update_fields=['status', 'error_message', 'error_code', 'completed_at'])
                # S1 (2026-08-16): 释放并发槽位 — 原实现只恢复 Device 状态,
                # 不释放 ConcurrencyController slot (agent 心跳超时 fail 路径
                # 泄漏 slot, 无设备绑定的多实例场景 agent 最终永久 "full").
                try:
                    from tasks.services.monitor_service import _release_concurrency_slot
                    _release_concurrency_slot(agent.agent_id, str(exec_.id))
                except Exception as exc:
                    logger.warning("check_agent_heartbeats: 释放并发槽位失败: %s", exc)
                _restore_device_status(exec_)
                # TD-402 ② (2026-08-27): a chain node failed by heartbeat must
                # advance (or fail) the chain — otherwise TaskChainExecution
                # stays RUNNING / current_node forever (advance is only triggered
                # from the result path). advance_chain_execution is idempotent
                # (row lock + terminal guard) so the delay is safe to fire twice.
                if exec_.chain_execution_id:
                    from pipeline.tasks import advance_chain_execution
                    advance_chain_execution.delay(exec_.chain_execution_id)

            if running_execs:
                logger.info(
                    "check_agent_heartbeats: Agent %s 心跳超时 (waiting), "
                    "已标记离线并 fail %d 个执行",
                    agent.agent_id, len(running_execs),
                )

        # 一致性: agent 离线 → 其窗口联动离线 (mark_agent_devices_offline)。
        # 必须放在 for 循环体 + waiting 分支之外: 无论恢复引擎返回
        # system_recovery/waiting 都要执行 (此前误放 waiting 块内,
        # system_recovery 路径的设备不会联动离线, 2026-08-27)。
        mark_agent_devices_offline(agent)


@shared_task(acks_late=True, max_retries=3, retry_backoff=30)
def check_dispatch_acks():
    """扫描派发未确认的执行 (S1, 2026-08-16).

    根因: ``dispatch_task`` 通过 ``group_send`` 派发 task.assign 帧, 无队列
    无 ack — 帧丢失 (agent 刚好重连 / 组名不匹配) 时执行永久 RUNNING 卡死.

    本任务每 10s 扫描:
    - RUNNING + snapshot.dispatch_sent_at 存在 + dispatch_ack_at 缺失
      + 超过 DISPATCH_ACK_TIMEOUT_SECONDS 未确认
    - agent 仍在线 (ONLINE/IDLE/BUSY) → 重新派发 (dispatch_task.delay),
      最多 DISPATCH_MAX_ATTEMPTS 次
    - agent 离线 / 重派次数耗尽 → 直接 fail 执行 + 释放资源

    与 check_agent_heartbeats (心跳超时 30s) 互补: 本任务更快 (10s) 且
    只在"帧丢失但连接健康"场景触发, 心跳兜底覆盖 agent 整体掉线.
    """
    now = timezone.now()
    sent_before = now - timedelta(seconds=DISPATCH_ACK_TIMEOUT_SECONDS)
    # JSONField key transform: SQLite/Postgres 均支持 __isnull 查询.
    candidates = list(
        TaskExecution.objects.filter(
            status=TaskExecution.Status.RUNNING,
            execution_snapshot__isnull=False,
        ).only('id', 'agent_id', 'status', 'execution_snapshot', 'trace_id')
    )
    stale = []
    for execution in candidates:
        snap = execution.execution_snapshot or {}
        sent_at = snap.get("dispatch_sent_at")
        if not sent_at:
            continue
        if snap.get("dispatch_ack_at"):
            continue
        try:
            from datetime import datetime as _dt
            sent_dt = _dt.fromisoformat(sent_at)
        except (TypeError, ValueError):
            # Malformed dispatch_sent_at (e.g. legacy snapshot) — treat as
            # stale so the execution gets redispatched or failed instead of
            # being stuck in RUNNING forever.
            stale.append(execution)
            continue
        if sent_dt > sent_before:
            continue
        stale.append(execution)

    if not stale:
        return

    from tasks.tasks import dispatch_task

    for execution in stale:
        attempts = int((execution.execution_snapshot or {}).get("dispatch_attempts") or 1)
        # 注意: execution.agent_id 是 FK 列 (Agent.pk), 不是 Agent.agent_id
        # 字符串标识符 — 用 pk 查询避免查不到在线 agent 误判为离线.
        agent = Worker.objects.filter(pk=execution.agent_id).first()
        if agent is not None and agent.status != Worker.Status.OFFLINE and attempts < DISPATCH_MAX_ATTEMPTS:
            logger.warning(
                "check_dispatch_acks: execution %s 派发超时未确认 (attempt=%d), 重新派发 agent=%s",
                execution.id, attempts, agent.agent_id,
            )
            dispatch_task.delay(
                execution.id,
                trace_id=(execution.execution_snapshot or {}).get("trace_id", "") or "",
            )
        else:
            _fail_execution_dispatch_timeout(execution)


@shared_task(acks_late=True, max_retries=3, retry_backoff=30)
def check_stuck_chains():
    """扫描并清理卡死的 TaskChainExecution (TD-425, 2026-09-05).

    背景: 链执行完成依赖 ``advance_chain_execution`` — 它从链的最后完成节点
    执行 (SUCCESS/FAILED) 决定推进或终止. 若节点执行从未到达终态 (派发帧
    丢失且 execution 级扫描也未覆盖) 或 advance 从未被触发 (结果帧丢失),
    链永久卡在 running → ``device_busy`` 检查永久跳过该设备, 阻塞后续所有
    派发 (无人值守 / DAG / dispatch_routine).

    本任务每 60s (config/celery.py beat) 扫描:
    - status=RUNNING 且 ``started_at`` (auto_now_add, 永不 NULL) 超过阈值
    - 且关联节点执行均非活跃 (无 PENDING/RUNNING TaskExecution) → 僵尸链
    - 僵尸链置 FAILED — ``post_save`` signal 自动触发
      ``on_chain_execution_completed`` 更新无人值守 session / 恢复计数.

    有活跃节点执行的链 = 任务仍在执行 (可能是长任务), 一律跳过不清理.
    """
    from gaf_core.error_codes import NodeErrorCode
    from pipeline.models import TaskChainExecution
    from pipeline.tasks import _fail_chain

    from tasks.models import TaskExecution

    threshold = timezone.now() - timedelta(seconds=CHAIN_STUCK_TIMEOUT_SECONDS)
    stuck = list(
        TaskChainExecution.objects.filter(
            status=TaskChainExecution.Status.RUNNING,
            started_at__lt=threshold,
        ).only("id", "status", "started_at", "device_id", "chain_id")
    )
    if not stuck:
        return

    # 关联活跃节点执行的链 (PENDING/RUNNING) = 仍在执行, 不清理.
    active_chain_ids = set(
        TaskExecution.objects.filter(
            chain_execution_id__in=[c.id for c in stuck],
            status__in=[
                TaskExecution.Status.PENDING,
                TaskExecution.Status.RUNNING,
            ],
        ).values_list("chain_execution_id", flat=True)
    )

    cleaned = 0
    for chain in stuck:
        if chain.id in active_chain_ids:
            logger.info(
                "check_stuck_chains: chain %s running>阈值但有活跃节点执行, 跳过",
                chain.id,
            )
            continue
        _fail_chain(
            chain,
            (
                f"链执行卡死超时清理 (running > {CHAIN_STUCK_TIMEOUT_SECONDS}s, "
                "无活跃节点执行)"
            ),
            error_code=NodeErrorCode.UNKNOWN.value,
        )
        cleaned += 1
        logger.warning(
            "check_stuck_chains: chain %s 卡死已清理 -> FAILED (chain=%s device=%s)",
            chain.id, chain.chain_id, chain.device_id,
        )

    if cleaned:
        logger.info("check_stuck_chains: 本轮清理 %d 条卡死链", cleaned)
