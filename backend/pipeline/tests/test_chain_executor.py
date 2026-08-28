"""Tests for TaskChain executor (spec stage 5 — TD-096).

Tests the chain execution flow:
    - Model: TaskChainExecution creation and defaults
    - _dispatch_next_node: success → next node, no next → chain SUCCESS
    - _fail_chain: abort condition → chain FAILED
    - advance_chain_execution: skip condition → continue, retry → re-dispatch
    - API: POST execute endpoint creates chain execution + dispatches first node
"""

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from agents.models import Agent
from pipeline.models import TaskChain, TaskChainExecution, TaskChainNode
from pipeline.tasks import (
    _cancel_chain,
    _dispatch_next_node,
    _fail_chain,
    advance_chain_execution,
)
from tasks.models import Task, TaskExecution


def _login(client, username, password):
    """Login and set Bearer token on client. Returns the response.

    Task 4.49 (P0-12, 2026-07-28): 修复 token 取值路径 (unified_response 信封)。
    """
    resp = client.post('/api/v2/accounts/auth/login/', {
        'username': username, 'password': password,
    }, format='json')
    assert resp.status_code == 200, f'Login failed: {resp.status_code} {resp.data}'
    assert isinstance(resp.data, dict), f'Login resp not dict: {resp.data}'
    if isinstance(resp.data.get('data'), dict) and 'access' in resp.data['data']:
        token = resp.data['data']['access']
    elif 'access' in resp.data:
        token = resp.data['access']
    else:
        raise AssertionError(f'Login resp missing access token: {resp.data}')
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return resp


class TaskChainExecutorModelTests(TestCase):
    """TaskChainExecution model: creation, defaults, __str__."""

    def setUp(self):
        self.user = User.objects.create_user(username='chain_user', password='Pass123!')
        self.chain = TaskChain.objects.create(
            name='Test Chain',
            description='Test chain for executor',
            created_by=self.user,
        )
        self.task_a = Task.objects.create(name='Task A')
        self.task_b = Task.objects.create(name='Task B')
        self.node_a = TaskChainNode.objects.create(
            chain=self.chain, task=self.task_a, order=1,
        )
        self.node_b = TaskChainNode.objects.create(
            chain=self.chain, task=self.task_b, order=2,
        )

    def test_create_chain_execution_defaults(self):
        """TaskChainExecution has correct defaults on creation."""
        exec_record = TaskChainExecution.objects.create(
            chain=self.chain,
            triggered_by=self.user,
            agent_id='test-agent-001',
        )
        self.assertEqual(exec_record.status, TaskChainExecution.Status.PENDING)
        self.assertIsNone(exec_record.current_node)
        self.assertIsNone(exec_record.completed_at)
        self.assertEqual(exec_record.error_message, '')
        self.assertEqual(exec_record.agent_id, 'test-agent-001')

    def test_str_includes_chain_name_and_status(self):
        """__str__ includes chain name and status."""
        exec_record = TaskChainExecution.objects.create(
            chain=self.chain,
            triggered_by=self.user,
        )
        self.assertIn('Test Chain', str(exec_record))
        self.assertIn('Pending', str(exec_record))

    def test_node_executions_reverse_relation(self):
        """TaskExecution.chain_execution FK creates reverse relation."""
        exec_record = TaskChainExecution.objects.create(
            chain=self.chain,
            triggered_by=self.user,
        )
        task_exec = TaskExecution.objects.create(
            task=self.task_a,
            chain_execution=exec_record,
            chain_node=self.node_a,
        )
        self.assertIn(task_exec, exec_record.node_executions.all())
        self.assertEqual(exec_record.node_executions.count(), 1)


class TaskChainExecutorLogicTests(TestCase):
    """Test the chain advancement logic functions."""

    def setUp(self):
        self.user = User.objects.create_user(username='chain_logic', password='Pass123!')
        self.chain = TaskChain.objects.create(
            name='Logic Test Chain',
            created_by=self.user,
        )
        self.task_a = Task.objects.create(name='Task A')
        self.task_b = Task.objects.create(name='Task B')
        self.task_c = Task.objects.create(name='Task C')
        self.node_a = TaskChainNode.objects.create(
            chain=self.chain, task=self.task_a, order=1,
        )
        self.node_b = TaskChainNode.objects.create(
            chain=self.chain, task=self.task_b, order=2,
        )
        self.node_c = TaskChainNode.objects.create(
            chain=self.chain, task=self.task_c, order=3,
        )
        self.chain_exec = TaskChainExecution.objects.create(
            chain=self.chain,
            triggered_by=self.user,
            agent_id='test-agent-001',
            current_node=self.node_a,
            status=TaskChainExecution.Status.RUNNING,
        )

    @patch('pipeline.tasks.dispatch_chain_node.delay')
    def test_dispatch_next_node_success(self, mock_delay):
        """When current node is A (order=1), next should be B (order=2)."""
        _dispatch_next_node(self.chain_exec)
        mock_delay.assert_called_once_with(self.chain_exec.id, self.node_b.id)

    @patch('pipeline.tasks.dispatch_chain_node.delay')
    def test_dispatch_next_node_no_more_nodes_marks_success(self, mock_delay):
        """When current node is the last, chain should be marked SUCCESS."""
        self.chain_exec.current_node = self.node_c
        self.chain_exec.save()
        _dispatch_next_node(self.chain_exec)
        mock_delay.assert_not_called()
        self.chain_exec.refresh_from_db()
        self.assertEqual(self.chain_exec.status, TaskChainExecution.Status.SUCCESS)
        self.assertIsNotNone(self.chain_exec.completed_at)

    def test_fail_chain(self):
        """_fail_chain marks chain as FAILED with error message."""
        _fail_chain(self.chain_exec, 'Node 1 failed: template not found')
        self.chain_exec.refresh_from_db()
        self.assertEqual(self.chain_exec.status, TaskChainExecution.Status.FAILED)
        self.assertEqual(self.chain_exec.error_message, 'Node 1 failed: template not found')
        self.assertIsNotNone(self.chain_exec.completed_at)

    def test_cancel_chain(self):
        """_cancel_chain marks chain as CANCELLED."""
        _cancel_chain(self.chain_exec, 'User cancelled')
        self.chain_exec.refresh_from_db()
        self.assertEqual(self.chain_exec.status, TaskChainExecution.Status.CANCELLED)
        self.assertEqual(self.chain_exec.error_message, 'User cancelled')

    @patch('pipeline.tasks.dispatch_chain_node.delay')
    def test_advance_chain_success_advances(self, mock_delay):
        """advance_chain_execution: last exec SUCCESS → dispatch next node."""
        TaskExecution.objects.create(
            task=self.task_a,
            chain_execution=self.chain_exec,
            chain_node=self.node_a,
            status=TaskExecution.Status.SUCCESS,
        )
        advance_chain_execution(self.chain_exec.id)
        mock_delay.assert_called_once_with(self.chain_exec.id, self.node_b.id)

    @patch('pipeline.tasks.dispatch_chain_node.delay')
    def test_advance_chain_failure_abort(self, mock_delay):
        """advance_chain_execution: failure with abort condition → chain FAILED."""
        self.node_a.condition = {"on_failure": "abort"}
        self.node_a.save()
        TaskExecution.objects.create(
            task=self.task_a,
            chain_execution=self.chain_exec,
            chain_node=self.node_a,
            status=TaskExecution.Status.FAILED,
            error_message='Template not found',
        )
        advance_chain_execution(self.chain_exec.id)
        mock_delay.assert_not_called()
        self.chain_exec.refresh_from_db()
        self.assertEqual(self.chain_exec.status, TaskChainExecution.Status.FAILED)

    @patch('pipeline.tasks.dispatch_chain_node.delay')
    def test_advance_chain_failure_skip(self, mock_delay):
        """advance_chain_execution: failure with skip condition → continue to next."""
        self.node_a.condition = {"on_failure": "skip"}
        self.node_a.save()
        TaskExecution.objects.create(
            task=self.task_a,
            chain_execution=self.chain_exec,
            chain_node=self.node_a,
            status=TaskExecution.Status.FAILED,
            error_message='OCR timeout',
        )
        advance_chain_execution(self.chain_exec.id)
        mock_delay.assert_called_once_with(self.chain_exec.id, self.node_b.id)
        self.chain_exec.refresh_from_db()
        self.assertEqual(self.chain_exec.status, TaskChainExecution.Status.RUNNING)

    @patch('pipeline.tasks.dispatch_chain_node.delay')
    def test_advance_chain_failure_retry(self, mock_delay):
        """advance_chain_execution: failure with retry condition → re-dispatch same node."""
        self.node_a.condition = {"on_failure": "retry", "max_retries": 3}
        self.node_a.save()
        TaskExecution.objects.create(
            task=self.task_a,
            chain_execution=self.chain_exec,
            chain_node=self.node_a,
            status=TaskExecution.Status.FAILED,
            error_message='Transient error',
        )
        advance_chain_execution(self.chain_exec.id)
        # Should re-dispatch the SAME node (not next)
        mock_delay.assert_called_once_with(self.chain_exec.id, self.node_a.id)

    @patch('pipeline.tasks.dispatch_chain_node.delay')
    def test_advance_chain_retry_exhausted(self, mock_delay):
        """advance_chain_execution: retry exhausted → chain FAILED."""
        self.node_a.condition = {"on_failure": "retry", "max_retries": 2}
        self.node_a.save()
        # Create 3 failed executions (exceeds max_retries=2)
        for _ in range(3):
            TaskExecution.objects.create(
                task=self.task_a,
                chain_execution=self.chain_exec,
                chain_node=self.node_a,
                status=TaskExecution.Status.FAILED,
                error_message='Persistent error',
            )
        advance_chain_execution(self.chain_exec.id)
        mock_delay.assert_not_called()
        self.chain_exec.refresh_from_db()
        self.assertEqual(self.chain_exec.status, TaskChainExecution.Status.FAILED)

    @patch('pipeline.tasks.dispatch_chain_node.delay')
    def test_advance_chain_already_finished_noop(self, mock_delay):
        """advance_chain_execution: chain already SUCCESS → no-op."""
        self.chain_exec.status = TaskChainExecution.Status.SUCCESS
        self.chain_exec.save()
        advance_chain_execution(self.chain_exec.id)
        mock_delay.assert_not_called()


class TaskChainExecutorAPITests(TestCase):
    """Test the execute API endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='api_user', password='Pass123!', role='admin',
        )
        self.client = APIClient()
        _login(self.client, 'api_user', 'Pass123!')
        self.chain = TaskChain.objects.create(
            name='API Test Chain',
            created_by=self.user,
        )
        self.task = Task.objects.create(name='API Task')
        TaskChainNode.objects.create(
            chain=self.chain, task=self.task, order=1,
        )
        # Create an online agent
        self.agent = Agent.objects.create(
            agent_id='test-agent-api',
            hostname='test-host',
            status=Agent.Status.ONLINE,
        )

    @patch('pipeline.tasks.dispatch_chain_node.delay')
    def test_execute_chain_creates_execution_and_dispatches(self, mock_delay):
        """POST execute creates TaskChainExecution and dispatches first node."""
        response = self.client.post(
            f'/api/v2/pipeline/task-chains/{self.chain.id}/execute/',
            data={'agent_id': 'test-agent-api'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        assert isinstance(data, dict) and data.keys() >= {
            'status', 'chain_name', 'chain_execution_id',
            'first_node_type', 'first_ref_name',
        }
        self.assertEqual(data['status'], 'dispatched')
        self.assertEqual(data['chain_name'], 'API Test Chain')
        # TD-110: response key renamed first_task_name → first_ref_name
        # (node may be TASK or PIPELINE; first_node_type added too).
        self.assertEqual(data['first_node_type'], 'task')
        self.assertEqual(data['first_ref_name'], 'API Task')

        # Verify TaskChainExecution was created
        chain_exec = TaskChainExecution.objects.get(id=data['chain_execution_id'])
        self.assertEqual(chain_exec.status, TaskChainExecution.Status.PENDING)
        self.assertEqual(chain_exec.agent_id, 'test-agent-api')

        # Verify dispatch_chain_node was called
        mock_delay.assert_called_once()

    def test_execute_chain_no_nodes_returns_400(self):
        """POST execute on empty chain returns 400."""
        empty_chain = TaskChain.objects.create(
            name='Empty Chain',
            created_by=self.user,
        )
        response = self.client.post(
            f'/api/v2/pipeline/task-chains/{empty_chain.id}/execute/',
            data={'agent_id': 'test-agent-api'},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_execute_chain_no_agent_returns_400(self):
        """POST execute with no online agent returns 400."""
        Agent.objects.filter(agent_id='test-agent-api').update(status=Agent.Status.OFFLINE)
        response = self.client.post(
            f'/api/v2/pipeline/task-chains/{self.chain.id}/execute/',
            data={},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    @patch('pipeline.tasks.dispatch_chain_node.delay')
    def test_get_executions_list(self, mock_delay):
        """GET executions returns execution history for a chain."""
        TaskChainExecution.objects.create(
            chain=self.chain,
            triggered_by=self.user,
            agent_id='test-agent-api',
            status=TaskChainExecution.Status.SUCCESS,
        )
        response = self.client.get(
            f'/api/v2/pipeline/task-chains/{self.chain.id}/executions/',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        assert isinstance(data, list) and len(data) > 0
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['status'], 'success')
        self.assertEqual(data[0]['chain_name'], 'API Test Chain')
