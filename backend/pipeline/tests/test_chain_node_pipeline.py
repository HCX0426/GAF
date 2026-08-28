"""Tests for TaskChain node_type branching (TD-110 Phase 2).

Tests the dispatch_chain_node branching logic:
    - TASK/PIPELINE nodes dispatch through the unified dispatch_task entry
      with force_agent_id pinning the chain's agent (B1, 2026-08-27)
    - Mixed chains (task + pipeline nodes) sequence correctly
    - advance_chain_execution works for both node types
    - Schema violations (node_type vs FK mismatch) fail gracefully
"""

from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from agents.models import Agent
from pipeline.models import (
    Pipeline,
    TaskChain,
    TaskChainExecution,
    TaskChainNode,
)
from pipeline.tasks import (
    _dispatch_pipeline_node,
    _dispatch_task_node,
    advance_chain_execution,
    dispatch_chain_node,
)
from tasks.models import Task, TaskExecution


class ChainPipelineNodeTestBase(TestCase):
    """Base setUp with a chain, an online agent, a task, and a pipeline."""

    def setUp(self):
        self.user = User.objects.create_user(username='td110_user', password='Pass123!')
        self.agent = Agent.objects.create(
            agent_id='td110-agent-001',
            status=Agent.Status.ONLINE,
        )
        self.chain = TaskChain.objects.create(
            name='TD-110 Test Chain',
            created_by=self.user,
        )
        self.task = Task.objects.create(name='TD-110 Test Task')
        # Pipeline with minimal graph_data — agent never runs in tests,
        # we only verify the WS payload + TaskExecution creation.
        self.pipeline = Pipeline.objects.create(
            name='TD-110 Test Pipeline',
            graph_data={'nodes': [], 'edges': []},
            user=self.user,
        )

    def _make_chain_exec(self):
        """Create a TaskChainExecution bound to the agent."""
        return TaskChainExecution.objects.create(
            chain=self.chain,
            triggered_by=self.user,
            agent_id=self.agent.agent_id,
            status=TaskChainExecution.Status.PENDING,
        )


class DispatchPipelineNodeTests(ChainPipelineNodeTestBase):
    """_dispatch_pipeline_node — unified task.assign path (spec-2026-08-02)."""

    def test_dispatch_pipeline_node_dispatches_via_unified_entry(self):
        """PIPELINE node dispatches through dispatch_task with force_agent_id (B1)."""
        chain_exec = self._make_chain_exec()
        node = TaskChainNode.objects.create(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline,
            order=1,
        )

        with patch('tasks.tasks.dispatch_task') as mock_dispatch:
            _dispatch_pipeline_node(chain_exec, node)

        mock_dispatch.delay.assert_called_once()
        execution = TaskExecution.objects.get(chain_execution=chain_exec)
        self.assertEqual(mock_dispatch.delay.call_args.args[0], execution.id)
        self.assertEqual(
            mock_dispatch.delay.call_args.kwargs['force_agent_id'],
            self.agent.agent_id,
        )

    def test_dispatch_pipeline_node_creates_task_execution_with_pipeline_fk(self):
        """TaskExecution is created with pipeline FK + task=None."""
        chain_exec = self._make_chain_exec()
        node = TaskChainNode.objects.create(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline,
            order=1,
        )

        with patch('tasks.tasks.dispatch_task'):
            _dispatch_pipeline_node(chain_exec, node)

        execution = TaskExecution.objects.filter(chain_execution=chain_exec).get()
        self.assertIsNone(execution.task)
        self.assertEqual(execution.pipeline, self.pipeline)
        # B1: execution is created PENDING — dispatch_task flips it to RUNNING.
        self.assertEqual(execution.status, TaskExecution.Status.PENDING)
        self.assertEqual(execution.agent, self.agent)

    def test_dispatch_pipeline_node_sets_chain_execution_and_node_fks(self):
        """TaskExecution.chain_execution + chain_node FKs set correctly."""
        chain_exec = self._make_chain_exec()
        node = TaskChainNode.objects.create(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline,
            order=1,
        )

        with patch('tasks.tasks.dispatch_task'):
            _dispatch_pipeline_node(chain_exec, node)

        execution = TaskExecution.objects.get(chain_execution=chain_exec)
        self.assertEqual(execution.chain_execution, chain_exec)
        self.assertEqual(execution.chain_node, node)

    def test_dispatch_pipeline_node_missing_pipeline_fails_chain(self):
        """node_type=pipeline but pipeline FK null → chain fails gracefully."""
        chain_exec = self._make_chain_exec()
        node = TaskChainNode.objects.create(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=None,  # schema violation
            order=1,
        )

        _dispatch_pipeline_node(chain_exec, node)

        chain_exec.refresh_from_db()
        self.assertEqual(chain_exec.status, TaskChainExecution.Status.FAILED)
        self.assertIn('pipeline FK is null', chain_exec.error_message)

    def test_dispatch_pipeline_node_dispatch_failure_fails_chain(self):
        """dispatch_task.delay exception → TaskExecution FAILED + chain FAILED."""
        chain_exec = self._make_chain_exec()
        node = TaskChainNode.objects.create(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline,
            order=1,
        )

        with patch('tasks.tasks.dispatch_task') as mock_dispatch:
            mock_dispatch.delay.side_effect = RuntimeError('WS connection refused')
            _dispatch_pipeline_node(chain_exec, node)

        chain_exec.refresh_from_db()
        self.assertEqual(chain_exec.status, TaskChainExecution.Status.FAILED)
        execution = TaskExecution.objects.get(chain_execution=chain_exec)
        self.assertEqual(execution.status, TaskExecution.Status.FAILED)
        self.assertIn('WS connection refused', execution.error_message)

    def test_dispatch_pipeline_node_missing_agent_fails_chain(self):
        """Agent.DoesNotExist → chain FAILED without creating TaskExecution."""
        chain_exec = self._make_chain_exec()
        chain_exec.agent_id = 'ghost-agent'
        chain_exec.save(update_fields=['agent_id'])
        node = TaskChainNode.objects.create(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline,
            order=1,
        )

        _dispatch_pipeline_node(chain_exec, node)

        chain_exec.refresh_from_db()
        self.assertEqual(chain_exec.status, TaskChainExecution.Status.FAILED)
        self.assertIn('Agent ghost-agent not found', chain_exec.error_message)
        # No TaskExecution should be created when agent resolution fails
        self.assertFalse(TaskExecution.objects.filter(chain_execution=chain_exec).exists())


class DispatchTaskNodeRegressionTests(ChainPipelineNodeTestBase):
    """_dispatch_task_node — TASK path behavior (regression, B1 unified entry)."""

    def test_dispatch_task_node_dispatches_with_force_agent_id(self):
        """TASK node dispatches through dispatch_task with force_agent_id (B1)."""
        chain_exec = self._make_chain_exec()
        node = TaskChainNode.objects.create(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.TASK,
            task=self.task,
            order=1,
        )

        with patch('tasks.tasks.dispatch_task') as mock_dispatch:
            _dispatch_task_node(chain_exec, node)

        mock_dispatch.delay.assert_called_once()
        execution = TaskExecution.objects.get(chain_execution=chain_exec)
        self.assertEqual(mock_dispatch.delay.call_args.args[0], execution.id)
        self.assertEqual(
            mock_dispatch.delay.call_args.kwargs['force_agent_id'],
            self.agent.agent_id,
        )

    def test_dispatch_task_node_creates_task_execution_with_task_fk(self):
        """TASK node TaskExecution has task FK set, pipeline FK null."""
        chain_exec = self._make_chain_exec()
        node = TaskChainNode.objects.create(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.TASK,
            task=self.task,
            order=1,
        )

        with patch('tasks.tasks.dispatch_task'):
            _dispatch_task_node(chain_exec, node)

        execution = TaskExecution.objects.get(chain_execution=chain_exec)
        self.assertEqual(execution.task, self.task)
        self.assertIsNone(execution.pipeline)


class DispatchChainNodeBranchTests(ChainPipelineNodeTestBase):
    """dispatch_chain_node entry point branches on node_type."""

    def test_dispatch_chain_node_routes_pipeline_to_pipeline_path(self):
        """node_type=PIPELINE routes to _dispatch_pipeline_node."""
        chain_exec = self._make_chain_exec()
        node = TaskChainNode.objects.create(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline,
            order=1,
        )

        with patch('pipeline.tasks._dispatch_pipeline_node') as mock_p, \
             patch('pipeline.tasks._dispatch_task_node') as mock_t:
            dispatch_chain_node(chain_exec.id, node.id)

        mock_p.assert_called_once_with(chain_exec, node)
        mock_t.assert_not_called()

    def test_dispatch_chain_node_routes_task_to_task_path(self):
        """node_type=TASK routes to _dispatch_task_node (regression)."""
        chain_exec = self._make_chain_exec()
        node = TaskChainNode.objects.create(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.TASK,
            task=self.task,
            order=1,
        )

        with patch('pipeline.tasks._dispatch_pipeline_node') as mock_p, \
             patch('pipeline.tasks._dispatch_task_node') as mock_t:
            dispatch_chain_node(chain_exec.id, node.id)

        mock_t.assert_called_once_with(chain_exec, node)
        mock_p.assert_not_called()


class AdvanceChainAfterPipelineCompleteTests(ChainPipelineNodeTestBase):
    """advance_chain_execution works for pipeline nodes (TD-110)."""

    def test_advance_after_pipeline_success_dispatches_next_node(self):
        """Pipeline node SUCCESS → next node dispatched (same as TASK path)."""
        chain_exec = self._make_chain_exec()
        chain_exec.status = TaskChainExecution.Status.RUNNING
        node1 = TaskChainNode.objects.create(
            chain=self.chain, node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline, order=1,
        )
        node2 = TaskChainNode.objects.create(
            chain=self.chain, node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline, order=2,
        )
        chain_exec.current_node = node1
        chain_exec.save(update_fields=['status', 'current_node'])

        # Create a completed TaskExecution for node1 (as agent would do)
        TaskExecution.objects.create(
            task=None, pipeline=self.pipeline, agent=self.agent,
            chain_execution=chain_exec, chain_node=node1,
            status=TaskExecution.Status.SUCCESS,
        )

        with patch('pipeline.tasks.dispatch_chain_node.delay') as mock_delay:
            advance_chain_execution(chain_exec.id)

        # Should dispatch node2
        mock_delay.assert_called_once_with(chain_exec.id, node2.id)

    def test_advance_after_pipeline_failure_abort_condition_fails_chain(self):
        """Pipeline node FAILED + on_failure=abort → chain FAILED."""
        chain_exec = self._make_chain_exec()
        chain_exec.status = TaskChainExecution.Status.RUNNING
        node1 = TaskChainNode.objects.create(
            chain=self.chain, node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline, order=1,
            condition={'on_failure': 'abort'},
        )
        chain_exec.current_node = node1
        chain_exec.save(update_fields=['status', 'current_node'])

        TaskExecution.objects.create(
            task=None, pipeline=self.pipeline, agent=self.agent,
            chain_execution=chain_exec, chain_node=node1,
            status=TaskExecution.Status.FAILED,
            error_message='Pipeline node failed',
        )

        advance_chain_execution(chain_exec.id)

        chain_exec.refresh_from_db()
        self.assertEqual(chain_exec.status, TaskChainExecution.Status.FAILED)
        self.assertIn('failed', chain_exec.error_message.lower())

    def test_advance_after_pipeline_failure_skip_condition_advances(self):
        """Pipeline node FAILED + on_failure=skip → next node dispatched."""
        chain_exec = self._make_chain_exec()
        chain_exec.status = TaskChainExecution.Status.RUNNING
        node1 = TaskChainNode.objects.create(
            chain=self.chain, node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline, order=1,
            condition={'on_failure': 'skip'},
        )
        node2 = TaskChainNode.objects.create(
            chain=self.chain, node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline, order=2,
        )
        chain_exec.current_node = node1
        chain_exec.save(update_fields=['status', 'current_node'])

        TaskExecution.objects.create(
            task=None, pipeline=self.pipeline, agent=self.agent,
            chain_execution=chain_exec, chain_node=node1,
            status=TaskExecution.Status.FAILED,
        )

        with patch('pipeline.tasks.dispatch_chain_node.delay') as mock_delay:
            advance_chain_execution(chain_exec.id)

        mock_delay.assert_called_once_with(chain_exec.id, node2.id)


class MixedChainTests(ChainPipelineNodeTestBase):
    """Mixed chain: TASK node followed by PIPELINE node, sequential execution."""

    def test_mixed_chain_task_then_pipeline_both_dispatched(self):
        """Chain with TASK node1 + PIPELINE node2 — both dispatch correctly."""
        chain_exec = self._make_chain_exec()
        node1 = TaskChainNode.objects.create(
            chain=self.chain, node_type=TaskChainNode.NodeType.TASK,
            task=self.task, order=1,
        )
        node2 = TaskChainNode.objects.create(
            chain=self.chain, node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline, order=2,
        )

        # Dispatch node1 (TASK)
        with patch('tasks.tasks.dispatch_task'):
            dispatch_chain_node(chain_exec.id, node1.id)
        chain_exec.refresh_from_db()
        self.assertEqual(chain_exec.current_node, node1)

        # Simulate node1 success → advance_chain_execution should dispatch node2
        TaskExecution.objects.create(
            task=self.task, agent=self.agent,
            chain_execution=chain_exec, chain_node=node1,
            status=TaskExecution.Status.SUCCESS,
        )

        with patch('tasks.tasks.dispatch_task'):
            advance_chain_execution(chain_exec.id)

        chain_exec.refresh_from_db()
        self.assertEqual(chain_exec.current_node, node2)
        # node2 (PIPELINE) should have created a TaskExecution with pipeline FK
        node2_exec = TaskExecution.objects.filter(
            chain_execution=chain_exec, chain_node=node2,
        ).get()
        self.assertIsNone(node2_exec.task)
        self.assertEqual(node2_exec.pipeline, self.pipeline)


class TaskChainNodeModelValidationTests(ChainPipelineNodeTestBase):
    """Model-level validation: node_type ↔ FK consistency (TD-110 clean())."""

    def test_clean_rejects_task_node_without_task_fk(self):
        """node_type=TASK but task FK null → ValidationError."""
        from django.core.exceptions import ValidationError

        node = TaskChainNode(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.TASK,
            task=None,
            pipeline=self.pipeline,  # wrong FK
            order=1,
        )
        with self.assertRaises(ValidationError) as ctx:
            node.clean()
        self.assertIn('task', ctx.exception.message_dict)

    def test_clean_rejects_pipeline_node_without_pipeline_fk(self):
        """node_type=PIPELINE but pipeline FK null → ValidationError."""
        from django.core.exceptions import ValidationError

        node = TaskChainNode(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=None,
            task=self.task,  # wrong FK
            order=1,
        )
        with self.assertRaises(ValidationError) as ctx:
            node.clean()
        self.assertIn('pipeline', ctx.exception.message_dict)

    def test_clean_accepts_task_node_with_task_fk(self):
        """node_type=TASK + task FK set → no ValidationError."""
        node = TaskChainNode(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.TASK,
            task=self.task,
            order=1,
        )
        node.clean()  # should not raise

    def test_clean_accepts_pipeline_node_with_pipeline_fk(self):
        """node_type=PIPELINE + pipeline FK set → no ValidationError."""
        node = TaskChainNode(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline,
            order=1,
        )
        node.clean()  # should not raise

    def test_str_renders_pipeline_name_for_pipeline_node(self):
        """__str__ shows pipeline name for PIPELINE nodes."""
        node = TaskChainNode.objects.create(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.PIPELINE,
            pipeline=self.pipeline,
            order=1,
        )
        s = str(node)
        self.assertIn(self.pipeline.name, s)
        self.assertIn(self.chain.name, s)

    def test_str_renders_task_name_for_task_node(self):
        """__str__ still shows task name for TASK nodes (regression)."""
        node = TaskChainNode.objects.create(
            chain=self.chain,
            node_type=TaskChainNode.NodeType.TASK,
            task=self.task,
            order=1,
        )
        s = str(node)
        self.assertIn(self.task.name, s)
