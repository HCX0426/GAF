"""Celery tasks for TaskChain execution (spec 阶段 5 — TD-096).

This module implements the chain executor that was missing from the
TaskChain model. The flow is:

    1. TaskChainViewSet.execute → create TaskChainExecution + dispatch_chain_node
    2. dispatch_chain_node → create TaskExecution + send WS task.assign to agent
    3. Agent completes → _db_update_execution_result (protocol/consumers.py)
       → checks TaskExecution.chain_execution FK → calls advance_chain_execution
    4. advance_chain_execution → checks condition → dispatch next node or finish

Condition semantics (TaskChainNode.condition JSON):
    - {"on_failure": "abort"}  — default, fail the entire chain
    - {"on_failure": "skip"}   — skip failed node, continue to next
    - {"on_failure": "retry", "max_retries": 3} — retry failed node
"""

import logging
import uuid

from celery import shared_task
from django.utils import timezone

# Import at module level — pipeline.models does NOT import pipeline.tasks,
# so there is no circular dependency. This avoids UnboundLocalError when
# helper functions reference TaskChainExecution.Status.
from pipeline.models import TaskChainExecution, TaskChainNode

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, acks_late=True)
def dispatch_chain_node(self, chain_execution_id, node_id):
    """Dispatch a single TaskChainNode to the agent.

    TD-110: branches on ``node_type`` — TASK nodes follow the legacy
    task.assign path, PIPELINE nodes use the new pipeline.execute path
    (reuses PipelineViewSet.execute WS payload format).

    Args:
        chain_execution_id: TaskChainExecution ID
        node_id: TaskChainNode ID to dispatch
    """
    try:
        chain_exec = TaskChainExecution.objects.select_related("chain").get(
            id=chain_execution_id
        )
    except TaskChainExecution.DoesNotExist:
        logger.error("dispatch_chain_node: TaskChainExecution %s not found", chain_execution_id)
        return

    try:
        node = TaskChainNode.objects.select_related("task", "pipeline").get(id=node_id)
    except TaskChainNode.DoesNotExist:
        logger.error("dispatch_chain_node: TaskChainNode %s not found", node_id)
        # N192: 设置 error_code 让前端能按错误码分类展示
        from gaf_core.error_codes import NodeErrorCode
        _fail_chain(chain_exec, f"Chain node {node_id} not found", error_code=NodeErrorCode.PARAM_INVALID.value)
        return

    # Check chain is still running (not cancelled)
    if chain_exec.status not in (TaskChainExecution.Status.PENDING, TaskChainExecution.Status.RUNNING):
        logger.info(
            "dispatch_chain_node: chain_execution %s is %s, skipping dispatch",
            chain_execution_id, chain_exec.status,
        )
        return

    # Branch on node_type (TD-110)
    if node.node_type == TaskChainNode.NodeType.PIPELINE:
        _dispatch_pipeline_node(chain_exec, node)
    else:
        _dispatch_task_node(chain_exec, node)


def _dispatch_task_node(chain_exec, node):
    """Dispatch a TASK node — unified path (dispatch_task).

    B1 (2026-08-27): converged from the bespoke ``_send_task_assign`` WS
    frame to the unified ``dispatch_task`` entry. The chain's pre-selected
    agent / device / game_account are bound to the TaskExecution and
    ``force_agent_id`` keeps the whole chain on the same agent.
    ``dispatch_task`` now owns RUNNING/BUSY transitions, the S1
    dispatch-ack snapshot, device_info building, resource_pack passthrough
    and debug dir + meta.json.
    """
    from tasks.models import TaskExecution

    # Update chain execution to RUNNING with current node
    chain_exec.status = TaskChainExecution.Status.RUNNING
    chain_exec.current_node = node
    chain_exec.save(update_fields=["status", "current_node"])

    from workers.models import Worker
    try:
        agent = Worker.objects.get(agent_id=chain_exec.agent_id)
    except Worker.DoesNotExist:
        # N192: 设置 error_code 让前端能按错误码分类展示
        from gaf_core.error_codes import NodeErrorCode
        _fail_chain(chain_exec, f"Agent {chain_exec.agent_id} not found", error_code=NodeErrorCode.UNKNOWN.value)
        return

    # Create TaskExecution (PENDING — dispatch_task flips to RUNNING).
    # Binding device/game_account lets dispatch_task build device_info,
    # enforce device-level serialization and pass through resource_pack —
    # guarantees the bespoke WS path didn't have.
    execution = TaskExecution.objects.create(
        task=node.task,
        agent=agent,
        device=_resolve_chain_device(chain_exec.device_id),
        game_account=_resolve_chain_account(chain_exec.game_account_id),
        triggered_by=chain_exec.triggered_by,
        status=TaskExecution.Status.PENDING,
        chain_execution=chain_exec,
        chain_node=node,
    )

    from tasks.tasks import dispatch_task

    try:
        dispatch_task.delay(
            execution.id,
            force_agent_id=chain_exec.agent_id,
            trace_id=str(uuid.uuid4()),
        )
    except Exception as e:
        execution.status = TaskExecution.Status.FAILED
        execution.error_message = f"Failed to dispatch chain node: {e}"
        # N192: 设置 error_code 让前端能按错误码分类展示
        from gaf_core.error_codes import NodeErrorCode
        execution.error_code = NodeErrorCode.UNKNOWN.value
        execution.completed_at = timezone.now()
        execution.save()
        _fail_chain(chain_exec, f"Failed to dispatch chain node: {e}", error_code=NodeErrorCode.UNKNOWN.value)
        return

    logger.info(
        "Chain %s node %s (order=%d, task=%s) dispatched to agent %s (execution=%s)",
        chain_exec.chain.name, node.id, node.order, node.task.name,
        chain_exec.agent_id, execution.id,
    )


def _dispatch_pipeline_node(chain_exec, node):
    """Dispatch a PIPELINE node — unified path (dispatch_task).

    B1 (2026-08-27): same convergence as ``_dispatch_task_node``. The
    pipeline FK is kept (``task=None``) so dispatch_task resolves metadata
    from ``execution.pipeline``, identical to PipelineViewSet.execute.
    """
    from tasks.models import TaskExecution

    if node.pipeline_id is None:
        # node_type=pipeline but pipeline FK missing — schema violation.
        # clean() catches this at save time, but defend at dispatch too.
        # N192: 设置 error_code 让前端能按错误码分类展示
        from gaf_core.error_codes import NodeErrorCode
        _fail_chain(chain_exec, f"Node {node.id} is node_type=pipeline but pipeline FK is null", error_code=NodeErrorCode.PARAM_INVALID.value)
        return

    pipeline = node.pipeline

    # Update chain execution to RUNNING with current node
    chain_exec.status = TaskChainExecution.Status.RUNNING
    chain_exec.current_node = node
    chain_exec.save(update_fields=["status", "current_node"])

    from workers.models import Worker
    try:
        agent = Worker.objects.get(agent_id=chain_exec.agent_id)
    except Worker.DoesNotExist:
        # N192: 设置 error_code 让前端能按错误码分类展示
        from gaf_core.error_codes import NodeErrorCode
        _fail_chain(chain_exec, f"Agent {chain_exec.agent_id} not found", error_code=NodeErrorCode.UNKNOWN.value)
        return

    # Create TaskExecution (PENDING — dispatch_task flips to RUNNING).
    # Binding device/game_account gives the unified path the same
    # device_info / resource_pack / dispatch-ack guarantees as TASK nodes.
    execution = TaskExecution.objects.create(
        task=None,
        pipeline=pipeline,
        agent=agent,
        device=_resolve_chain_device(chain_exec.device_id),
        game_account=_resolve_chain_account(chain_exec.game_account_id),
        triggered_by=chain_exec.triggered_by,
        status=TaskExecution.Status.PENDING,
        chain_execution=chain_exec,
        chain_node=node,
    )

    from tasks.tasks import dispatch_task

    try:
        dispatch_task.delay(
            execution.id,
            force_agent_id=chain_exec.agent_id,
            trace_id=str(uuid.uuid4()),
        )
    except Exception as e:
        execution.status = TaskExecution.Status.FAILED
        execution.error_message = f"Failed to dispatch chain node: {e}"
        # N192: 设置 error_code 让前端能按错误码分类展示
        from gaf_core.error_codes import NodeErrorCode
        execution.error_code = NodeErrorCode.UNKNOWN.value
        execution.completed_at = timezone.now()
        execution.save(update_fields=["status", "error_message", "error_code", "completed_at", "updated_at"])
        _fail_chain(chain_exec, f"Failed to dispatch chain node: {e}", error_code=NodeErrorCode.UNKNOWN.value)
        return

    logger.info(
        "Chain %s node %s (order=%d, pipeline=%s) dispatched to agent %s (execution=%s)",
        chain_exec.chain.name, node.id, node.order, pipeline.name,
        chain_exec.agent_id, execution.id,
    )


def _resolve_chain_device(device_id):
    """Resolve the Device bound at chain level (chain_exec.device_id)."""
    if not device_id:
        return None
    from workers.models import Device

    try:
        return Device.objects.get(pk=device_id)
    except Device.DoesNotExist:
        return None


def _resolve_chain_account(game_account_id):
    """Resolve the GameAccount bound at chain level (chain_exec.game_account_id)."""
    if not game_account_id:
        return None
    from accounts.models import GameAccount

    try:
        return GameAccount.objects.get(pk=game_account_id)
    except GameAccount.DoesNotExist:
        return None


@shared_task(acks_late=True, max_retries=3, retry_backoff=30)
def advance_chain_execution(chain_execution_id):
    """Advance the chain after a node's TaskExecution completes.

    TD-402 ⑤ (2026-08-27): the whole decision runs inside a transaction with
    ``select_for_update`` on the TaskChainExecution row so concurrent /
    duplicate advance calls serialize — the second caller observes terminal
    status (or nothing changed) and returns early instead of
    double-dispatching the next node.

    Args:
        chain_execution_id: TaskChainExecution ID
    """
    from django.db import transaction

    from tasks.models import TaskExecution

    with transaction.atomic():
        try:
            chain_exec = TaskChainExecution.objects.select_for_update().select_related(
                "chain", "current_node",
            ).get(
                id=chain_execution_id
            )
        except TaskChainExecution.DoesNotExist:
            logger.error("advance_chain_execution: TaskChainExecution %s not found", chain_execution_id)
            return

        # Chain already finished — nothing to do
        if chain_exec.status in (
            TaskChainExecution.Status.SUCCESS,
            TaskChainExecution.Status.FAILED,
            TaskChainExecution.Status.CANCELLED,
        ):
            return

        # Get the last completed TaskExecution for this chain
        last_exec = (
            chain_exec.node_executions
            .exclude(status=TaskExecution.Status.PENDING)
            .exclude(status=TaskExecution.Status.RUNNING)
            .order_by("-updated_at")
            .first()
        )

        if last_exec is None:
            logger.warning("advance_chain_execution: no completed execution found for chain %s", chain_execution_id)
            return

        if last_exec.status == TaskExecution.Status.SUCCESS:
            # Success → find next node and dispatch
            _dispatch_next_node(chain_exec)

        elif last_exec.status in (TaskExecution.Status.FAILED, TaskExecution.Status.FORCE_TERMINATED):
            # Failure → check condition
            condition = chain_exec.current_node.condition or {}
            on_failure = condition.get("on_failure", "abort")

            if on_failure == "skip":
                logger.info(
                    "Chain %s: node %s failed, condition=skip → advancing to next",
                    chain_exec.chain.name, chain_exec.current_node.order,
                )
                _dispatch_next_node(chain_exec)

            elif on_failure == "retry":
                max_retries = condition.get("max_retries", 3)
                retry_count = chain_exec.node_executions.filter(
                    chain_node=chain_exec.current_node,
                    status=TaskExecution.Status.FAILED,
                ).count()

                if retry_count <= max_retries:
                    logger.info(
                        "Chain %s: node %s failed (retry %d/%d) → re-dispatching",
                        chain_exec.chain.name, chain_exec.current_node.order,
                        retry_count, max_retries,
                    )
                    dispatch_chain_node.delay(chain_execution_id, chain_exec.current_node.id)
                else:
                    logger.info(
                        "Chain %s: node %s exhausted retries (%d/%d) → aborting",
                        chain_exec.chain.name, chain_exec.current_node.order,
                        retry_count, max_retries,
                    )
                    _fail_chain(
                        chain_exec,
                        f"Node {chain_exec.current_node.order} exhausted retries ({retry_count}/{max_retries})",
                        error_code=last_exec.error_code,
                    )

            else:  # "abort" (default)
                _fail_chain(
                    chain_exec,
                    f"Node {chain_exec.current_node.order} (task: {last_exec.task.name if last_exec.task else 'N/A'}) failed: {last_exec.error_message}",
                    error_code=last_exec.error_code,
                )

        elif last_exec.status == TaskExecution.Status.CANCELLED:
            _cancel_chain(
                chain_exec,
                "A node execution was cancelled",
                error_code=last_exec.error_code,
            )

        else:
            logger.warning(
                "advance_chain_execution: unexpected status %s for execution %s in chain %s",
                last_exec.status, last_exec.id, chain_execution_id,
        )


def _dispatch_next_node(chain_exec):
    """Find the next TaskChainNode (order > current) and dispatch it.

    If no next node exists, mark the chain as SUCCESS.
    """
    next_node = (
        TaskChainNode.objects
        .filter(chain=chain_exec.chain, order__gt=chain_exec.current_node.order)
        .order_by("order")
        .first()
    )

    if next_node is None:
        # All nodes completed — mark chain as success
        chain_exec.status = TaskChainExecution.Status.SUCCESS
        chain_exec.completed_at = timezone.now()
        chain_exec.save(update_fields=["status", "completed_at"])
        logger.info("Chain %s completed successfully", chain_exec.chain.name)
        return

    # TD-110: node may be TASK or PIPELINE — log the right ref name
    if next_node.node_type == TaskChainNode.NodeType.PIPELINE:
        ref_label = f"pipeline={next_node.pipeline.name if next_node.pipeline_id else 'N/A'}"
    else:
        ref_label = f"task={next_node.task.name if next_node.task_id else 'N/A'}"
    logger.info(
        "Chain %s: advancing to node %s (order=%d, %s)",
        chain_exec.chain.name, next_node.id, next_node.order, ref_label,
    )
    dispatch_chain_node.delay(chain_exec.id, next_node.id)


def _fail_chain(chain_exec, error_msg, error_code=""):
    """Mark the chain execution as FAILED.

    N192: error_code is propagated from the last failing TaskExecution
    so the frontend can categorize chain-level failures by error type.
    """
    chain_exec.status = TaskChainExecution.Status.FAILED
    chain_exec.completed_at = timezone.now()
    chain_exec.error_message = error_msg
    chain_exec.error_code = error_code or ""
    chain_exec.save(update_fields=["status", "completed_at", "error_message", "error_code"])
    logger.error("Chain %s FAILED: %s (error_code=%s)", chain_exec.chain.name, error_msg, error_code or "<none>")


def _cancel_chain(chain_exec, reason, error_code=""):
    """Mark the chain execution as CANCELLED.

    N192: error_code is propagated from the last failing TaskExecution
    so the frontend can categorize chain-level cancellations.
    """
    chain_exec.status = TaskChainExecution.Status.CANCELLED
    chain_exec.completed_at = timezone.now()
    chain_exec.error_message = reason
    chain_exec.error_code = error_code or ""
    chain_exec.save(update_fields=["status", "completed_at", "error_message", "error_code"])
    logger.info("Chain %s CANCELLED: %s (error_code=%s)", chain_exec.chain.name, reason, error_code or "<none>")
