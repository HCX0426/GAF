"""Reusable service functions for TaskChain execution (v3 spec §2.10).

Extracted from TaskChainViewSet.execute action so that:
    - GameProfile dispatch-routine API (task 2.3) can dispatch the
      default routine for all online devices under a GameProfile
    - scheduler unattended_start_view (task 2.6) can dispatch the
      default routine for all online devices with a default_task_chain

Both callers need the same flow:
    1. Validate chain has nodes + chain.is_enabled
    2. Resolve online agent (caller-provided or auto-pick)
    3. Create TaskChainExecution (with device + game_account runtime binding)
    4. Dispatch first node via dispatch_chain_node.delay

Keeping this logic in a service module (not the ViewSet) avoids
duplicating validation/agent-resolution/creation across views, scheduler
jobs, and future callers.
"""

import logging

from django.db import transaction

from pipeline.models import TaskChain, TaskChainExecution, TaskChainNode
from pipeline.tasks import dispatch_chain_node

logger = logging.getLogger(__name__)


class ChainDispatchError(Exception):
    """Raised when a TaskChain cannot be dispatched.

    Callers should catch this and return an appropriate HTTP 400/404
    response with the error message.
    """


@transaction.atomic
def create_chain_execution_and_dispatch(
    chain_id,
    agent_id=None,
    device_id=None,
    game_account_id=None,
    triggered_by=None,
):
    """Create a TaskChainExecution and dispatch the first node.

    Args:
        chain_id: TaskChain ID to execute
        agent_id: Agent.agent_id string. If None, auto-pick the first
            online Agent (caller may pass a specific agent for
            window-centric dispatch).
        device_id: Device ID for runtime binding (spec §2.10). Stored
            on TaskChainExecution.device FK.
        game_account_id: GameAccount ID for runtime binding (spec §2.10).
            Stored on TaskChainExecution.game_account FK. Should match
            device.game_account_id when device is provided.
        triggered_by: User instance triggering the dispatch (nullable)

    Returns:
        TaskChainExecution: the created execution record (status=PENDING)

    Raises:
        ChainDispatchError: if chain is missing, disabled, has no nodes,
            or no online agent is available
    """
    from workers.models import Worker

    try:
        chain = TaskChain.objects.get(pk=chain_id)
    except TaskChain.DoesNotExist as exc:
        raise ChainDispatchError(f'TaskChain {chain_id} not found') from exc

    if not chain.is_enabled:
        raise ChainDispatchError(f'TaskChain [{chain.name}] is disabled')

    # TD-110: select_related pipeline too — node may be PIPELINE type
    nodes = chain.chain_nodes.select_related('task', 'pipeline').order_by('order')
    if not nodes.exists():
        raise ChainDispatchError(f'TaskChain [{chain.name}] has no nodes')

    # Resolve agent: explicit agent_id wins, else auto-pick online agent
    online_statuses = (Worker.Status.ONLINE, Worker.Status.IDLE)
    if agent_id:
        try:
            agent = Worker.objects.get(agent_id=agent_id)
            if agent.status not in online_statuses:
                raise ChainDispatchError(
                    f'Agent {agent_id} is not online (status={agent.status})'
                )
        except Worker.DoesNotExist as exc:
            raise ChainDispatchError(f'Agent {agent_id} not found') from exc
    else:
        agent = Worker.objects.filter(status__in=online_statuses).first()
        if agent is None:
            raise ChainDispatchError('No online Agent available')
        agent_id = agent.agent_id

    # Create TaskChainExecution with runtime binding (spec §2.10)
    chain_exec = TaskChainExecution.objects.create(
        chain=chain,
        triggered_by=triggered_by,
        agent_id=agent_id,
        device_id=device_id,
        game_account_id=game_account_id,
        status=TaskChainExecution.Status.PENDING,
    )

    # Dispatch the first node (lowest order)
    first_node = nodes.first()
    dispatch_chain_node.delay(chain_exec.id, first_node.id)

    # TD-110: render the right ref name based on node_type (task vs pipeline)
    if first_node.node_type == TaskChainNode.NodeType.PIPELINE:
        first_ref_name = first_node.pipeline.name if first_node.pipeline_id else 'N/A'
    else:
        first_ref_name = first_node.task.name if first_node.task_id else 'N/A'

    logger.info(
        'TaskChainExecution %s created for chain [%s] (agent=%s, device=%s, account=%s), '
        'first node=%s (task=%s)',
        chain_exec.id, chain.name, agent_id, device_id, game_account_id,
        first_node.id, first_ref_name,
    )

    return chain_exec


class RoutineImportError(Exception):
    """Raised when routine.json cannot be converted to a TaskChain.

    Distinct from ChainDispatchError (which is about dispatch-time
    failures). RoutineImportError covers schema/format/lookup issues
    encountered during the routine.json → TaskChain conversion.
    """


def convert_routine_to_chain(game_profile, user=None):
    """Convert a GameProfile's routine.json to a TaskChain with PIPELINE nodes.

    TD-113: reads `routine_path` from the GameProfile instead of accepting
    a hardcoded path argument. Each GameProfile can point at its own
    routine.json (e.g. different routine per account strategy).

    TD-110 Phase 3: reads ``routine.json`` (format from
    ``resources/<game>/routine.json``) and creates a TaskChain + 8
    TaskChainNode rows (one per routine entry, all node_type=PIPELINE).

    Idempotent: if a TaskChain with the same name + game_profile already
    exists, the existing chain is reused (its nodes are replaced).

    Args:
        game_profile: GameProfile instance to read routine_path from and
            bind the created TaskChain to
        user: User creating the chain (nullable, defaults to None)

    Returns:
        TaskChain: the created or updated chain

    Raises:
        RoutineImportError: if GameProfile.routine_path is empty,
            routine.json is invalid, pipelines cannot be resolved by
            name, or multiple pipelines match a name
    """
    import json
    import os

    from pipeline.models import Pipeline, TaskChain, TaskChainNode

    routine_path = game_profile.routine_path
    if not routine_path:
        raise RoutineImportError(
            f'GameProfile [{game_profile.game_name}] has no routine_path '
            'configured; set it before importing a routine'
        )

    if not os.path.isfile(routine_path):
        raise RoutineImportError(
            f'routine.json not found: {routine_path}'
        )

    try:
        with open(routine_path, encoding='utf-8') as f:
            routine = json.load(f)
    except json.JSONDecodeError as e:
        raise RoutineImportError(f'routine.json invalid JSON: {e}') from e

    chain_name = routine.get('name')
    if not chain_name:
        raise RoutineImportError("routine.json missing 'name' field")

    routine_tasks = routine.get('tasks')
    if not routine_tasks or not isinstance(routine_tasks, list):
        raise RoutineImportError(
            "routine.json missing or empty 'tasks' list"
        )

    # Sort by order field (stable for ties)
    sorted_tasks = sorted(routine_tasks, key=lambda t: t.get('order', 0))

    # Resolve Pipelines by name. Pipeline has no game_profile FK, so we
    # search globally by name. If multiple pipelines share a name, we
    # refuse to guess — the user must rename or specify IDs (future work).
    pipeline_cache: dict[str, Pipeline] = {}
    for t in sorted_tasks:
        pipeline_name = t.get('pipeline')
        if not pipeline_name:
            raise RoutineImportError(
                f"routine entry order={t.get('order')} missing 'pipeline' field"
            )
        if pipeline_name in pipeline_cache:
            continue
        matches = list(Pipeline.objects.filter(name=pipeline_name))
        if not matches:
            raise RoutineImportError(
                f"Pipeline '{pipeline_name}' not found in DB "
                "(create the Pipeline first or check routine.json names)"
            )
        if len(matches) > 1:
            raise RoutineImportError(
                f"Pipeline name '{pipeline_name}' matches {len(matches)} rows "
                f"(ids={[p.id for p in matches]}); rename duplicates or use a "
                "unique name in routine.json"
            )
        pipeline_cache[pipeline_name] = matches[0]

    with transaction.atomic():
        # Idempotent: reuse existing chain with same name + game_profile
        chain, created = TaskChain.objects.get_or_create(
            name=chain_name,
            game_profile=game_profile,
            defaults={
                'description': routine.get('description', ''),
                'is_default': True,
                'created_by': user,
            },
        )
        if not created:
            # Update description + ensure is_default=True on re-import
            chain.description = routine.get('description', chain.description)
            chain.is_default = True
            if user is not None:
                chain.created_by = user
            chain.save(update_fields=['description', 'is_default', 'created_by'])
            # Replace existing nodes (idempotent re-import)
            chain.chain_nodes.all().delete()

        for t in sorted_tasks:
            TaskChainNode.objects.create(
                chain=chain,
                node_type=TaskChainNode.NodeType.PIPELINE,
                pipeline=pipeline_cache[t['pipeline']],
                order=t.get('order'),
                condition=t.get('condition', {}),
            )

    logger.info(
        'convert_routine_to_chain: %s chain [%s] with %d pipeline nodes '
        '(game_profile=%s [%s], created=%s)',
        routine_path, chain.name, len(sorted_tasks),
        game_profile.id, game_profile.game_name, created,
    )
    return chain
