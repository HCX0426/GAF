"""TD-402 ①: chain node dispatch writes the S1 dispatch-ack contract.

B1 (2026-08-27): chain dispatch converged to the unified ``dispatch_task``
entry — ``force_agent_id`` keeps the whole chain on the same agent and the
S1 dispatch-ack snapshot (``dispatch_sent_at``) is now written by
``dispatch_task`` (covered in tasks/tests/test_dispatch_ack.py). These
tests verify the convergence contract: both chain node types route through
``dispatch_task`` with the chain's agent pinned and the execution handed
over PENDING (dispatch_task owns the RUNNING flip).
"""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from workers.models import Worker

from pipeline.models import TaskChain, TaskChainExecution, TaskChainNode
from pipeline.tasks import dispatch_chain_node
from tasks.models import Task, TaskExecution

User = get_user_model()


def _base(chain_status=TaskChainExecution.Status.PENDING):
    user = User.objects.create_user(username='ack_user', password='Pass123!')
    chain = TaskChain.objects.create(name='ack-chain', is_enabled=True)
    agent = Worker.objects.create(
        agent_id='ack-agent', hostname='h', status=Worker.Status.ONLINE,
    )
    chain_exec = TaskChainExecution.objects.create(
        chain=chain, triggered_by=user, agent_id=agent.agent_id,
        status=chain_status,
    )
    return chain_exec, user


@pytest.mark.django_db
def test_task_node_dispatches_via_unified_entry_with_force_agent():
    chain_exec, _user = _base()
    task = Task.objects.create(name='AckTask')
    node = TaskChainNode.objects.create(chain=chain_exec.chain, task=task, order=1)

    with patch('tasks.tasks.dispatch_task') as mock_dispatch:
        dispatch_chain_node(chain_exec.id, node.id)

    mock_dispatch.delay.assert_called_once()
    execution = TaskExecution.objects.get(chain_execution=chain_exec, chain_node=node)
    assert mock_dispatch.delay.call_args.args[0] == execution.id
    assert mock_dispatch.delay.call_args.kwargs['force_agent_id'] == 'ack-agent'
    # PENDING handed to dispatch_task — snapshot ownership moved to it (B1).
    assert execution.status == TaskExecution.Status.PENDING


@pytest.mark.django_db
def test_pipeline_node_dispatches_via_unified_entry_with_force_agent():
    from pipeline.models import Pipeline

    chain_exec, user = _base()
    pipeline = Pipeline.objects.create(
        name='AckPipeline', graph_data={'nodes': []}, user=user,
    )
    node = TaskChainNode.objects.create(
        chain=chain_exec.chain, pipeline=pipeline, order=1,
        node_type=TaskChainNode.NodeType.PIPELINE,
    )

    with patch('tasks.tasks.dispatch_task') as mock_dispatch:
        dispatch_chain_node(chain_exec.id, node.id)

    mock_dispatch.delay.assert_called_once()
    execution = TaskExecution.objects.get(chain_execution=chain_exec, chain_node=node)
    assert execution.pipeline == pipeline
    assert mock_dispatch.delay.call_args.kwargs['force_agent_id'] == 'ack-agent'
    assert execution.status == TaskExecution.Status.PENDING
