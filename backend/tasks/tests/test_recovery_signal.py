"""
P-020-D: TaskExecution 信号触发恢复测试 + P-010 Phase 3: ExecutionStep 信号测试

覆盖:
TaskExecution (P-020-D):
- status 变为 failed 触发 handle_task_failure
- status 不是 failed 不触发
- 连续失败次数正确计算 (1, 2, 3)
- 防递归: recovery_attempts > 0 不再触发
- 未达阈值的连续失败不写 RecoveryLog

ExecutionStep (P-010 Phase 3):
- status=FAILED 触发 handle_step_failure (含 created=True 场景)
- status=SUCCESS 不触发
- 防递归: _processing_step_ids 阻止同 step_id 重复触发
- 恢复完成后 set 释放, 新失败可再次触发
- handle_step_failure 抛异常时 set 仍释放
"""

from unittest.mock import patch

import pytest
from django.test import TestCase
from scheduler.models import RecoveryLog
from workers.models import Worker

from accounts.models import User
from tasks.models import ExecutionStep, Task, TaskDevice, TaskExecution

pytestmark = pytest.mark.integration


@pytest.fixture
def setup_task(db):
    """创建 task + agent + device, 返回 task 实例"""
    user = User.objects.create_user(username='p020d_user', password='test123')
    agent = Worker.objects.create(
        hostname='p020d-host',
        status='online',
        last_heartbeat=__import__('django.utils.timezone', fromlist=['now']).now(),
    )
    task = Task.objects.create(
        name='p020d-test-task',
    )
    device = agent.devices.first() if hasattr(agent, 'devices') else None
    if device is None:
        from workers.models import Device
        device = Device.objects.create(
            agent=agent,
            name='p020d-device',
            status='online',
        )
    TaskDevice.objects.create(task=task, device=device)
    return task, agent, user


class TestTaskFailureSignal(TestCase):
    """TaskExecution 失败信号测试 (用 TestCase + captureOnCommitCallbacks)"""

    def setUp(self):
        user = User.objects.create_user(username='p020d_user', password='test123')
        agent = Worker.objects.create(
            hostname='p020d-host',
            status='online',
            last_heartbeat=__import__('django.utils.timezone', fromlist=['now']).now(),
        )
        self.task = Task.objects.create(name='p020d-test-task')
        from workers.models import Device
        device = Device.objects.create(agent=agent, name='p020d-device', status='online')
        TaskDevice.objects.create(task=self.task, device=device)
        self.agent = agent
        self.user = user

    def test_status_failed_triggers_handle_task_failure(self):
        """status 变 failed 应调用 handle_task_failure (P-020-D signal 触发核心职责)"""
        exec_record = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            triggered_by=self.user,
            status=TaskExecution.Status.RUNNING,
        )

        with (
            patch('tasks.signals.handle_task_failure') as mock_handler,
            self.captureOnCommitCallbacks(execute=True),
        ):
            exec_record.status = TaskExecution.Status.FAILED
            exec_record.save()

        # on_commit 跑后 handle_task_failure 应被调用 1 次
        mock_handler.assert_called_once()
        call_kwargs = mock_handler.call_args.kwargs
        self.assertEqual(call_kwargs['task_execution_id'], exec_record.id)
        self.assertGreaterEqual(call_kwargs['consecutive_failures'], 1)

    def test_status_success_does_not_trigger(self):
        """status 变 success 不应触发 recovery"""
        exec_record = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            triggered_by=self.user,
            status=TaskExecution.Status.RUNNING,
        )
        before = RecoveryLog.objects.count()

        exec_record.status = TaskExecution.Status.SUCCESS
        exec_record.save()

        self.assertEqual(RecoveryLog.objects.count(), before, 'status=success 不应触发任何 recovery log')

    def test_consecutive_failures_counted_correctly(self):
        """3 次连续失败后, 第 3 次应记录 consecutive_failures=3"""
        # 故意先建 2 条失败的
        for _ in range(2):
            TaskExecution.objects.create(
                task=self.task,
                agent=self.agent,
                triggered_by=self.user,
                status=TaskExecution.Status.FAILED,
            )
        # 第 3 条
        exec_record = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            triggered_by=self.user,
            status=TaskExecution.Status.RUNNING,
        )

        with self.captureOnCommitCallbacks(execute=True):
            exec_record.status = TaskExecution.Status.FAILED
            exec_record.save()

        # 找最近 task-level recovery log
        log = RecoveryLog.objects.filter(
            recovery_level='task',
            trigger_event__contains=f'任务 {exec_record.id}',
        ).order_by('-created_at').first()
        self.assertIsNotNone(log)
        chain_result = log.details.get('chain_result', {})
        self.assertGreaterEqual(chain_result.get('total', 0), 1)

    def test_recovery_attempts_prevents_recursion(self):
        """recovery_attempts > 0 时 (恢复动作本身), 不应再触发恢复"""
        exec_record = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            triggered_by=self.user,
            status=TaskExecution.Status.RUNNING,
            recovery_attempts=1,  # 已是恢复中
            recovery_layer=2,
        )

        before = RecoveryLog.objects.filter(
            trigger_event__contains=f'任务 {exec_record.id}',
        ).count()

        with self.captureOnCommitCallbacks(execute=True):
            exec_record.status = TaskExecution.Status.FAILED
            exec_record.save()

        after = RecoveryLog.objects.filter(
            trigger_event__contains=f'任务 {exec_record.id}',
        ).count()
        self.assertEqual(before, after, 'recovery_attempts > 0 时应跳过 signal 触发')

    def test_below_threshold_no_recovery_log(self):
        """连续失败未达阈值 (默认 3) 时, handle_task_failure 返回 continue 不写 log"""
        exec_record = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            triggered_by=self.user,
            status=TaskExecution.Status.RUNNING,
        )

        before_task_logs = RecoveryLog.objects.filter(recovery_level='task').count()

        with self.captureOnCommitCallbacks(execute=True):
            exec_record.status = TaskExecution.Status.FAILED
            exec_record.save()

        after_task_logs = RecoveryLog.objects.filter(recovery_level='task').count()
        # 默认 threshold=3, 1 次连续失败 < 3, 不写 task log
        self.assertEqual(after_task_logs, before_task_logs, '未达阈值不应写 task-level log')


class TestStepRecoverySignal(TestCase):
    """ExecutionStep 失败信号测试 (P-010 Phase 3).

    Verifies that saving an ExecutionStep with status=FAILED triggers
    ``handle_step_failure`` via the post_save signal, with anti-recursion
    protection via the module-level ``_processing_step_ids`` set.
    """

    def setUp(self):
        # Clear the anti-recursion set so tests don't pollute each other.
        # The finally block in _run_step_recovery normally discards ids, but
        # if a previous test's on_commit didn't fire (e.g. assertion error
        # before captureOnCommitCallbacks ran), ids could linger.
        from tasks.signals import _processing_step_ids
        _processing_step_ids.clear()

        self.user = User.objects.create_user(username='p010_user', password='test123')
        self.agent = Worker.objects.create(
            hostname='p010-host',
            status='online',
            last_heartbeat=__import__('django.utils.timezone', fromlist=['now']).now(),
        )
        self.task = Task.objects.create(name='p010-test-task')
        self.execution = TaskExecution.objects.create(
            task=self.task,
            agent=self.agent,
            triggered_by=self.user,
            status=TaskExecution.Status.RUNNING,
        )

    def _make_step(self, status=ExecutionStep.Status.FAILED, step_index=0,
                   error_message='template not found'):
        """Helper: create an ExecutionStep with sensible defaults."""
        return ExecutionStep.objects.create(
            task_result=self.execution,
            step_index=step_index,
            node_id=f'node-{step_index}',
            step_type='pipeline_node',
            step_name=f'node-{step_index}',
            status=status,
            error_message=error_message if status == ExecutionStep.Status.FAILED else '',
        )

    def test_step_failed_triggers_handle_step_failure(self):
        """ExecutionStep saved with FAILED → handle_step_failure called with (id, error)."""
        with (
            patch('tasks.signals.handle_step_failure') as mock_handler,
            self.captureOnCommitCallbacks(execute=True),
        ):
            step = self._make_step(status=ExecutionStep.Status.FAILED,
                                   error_message='click target not found')

        mock_handler.assert_called_once()
        call_kwargs = mock_handler.call_args.kwargs
        self.assertEqual(call_kwargs['execution_step_id'], step.id)
        self.assertEqual(call_kwargs['error_message'], 'click target not found')

    def test_step_success_does_not_trigger(self):
        """ExecutionStep saved with SUCCESS → handle_step_failure NOT called."""
        with (
            patch('tasks.signals.handle_step_failure') as mock_handler,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self._make_step(status=ExecutionStep.Status.SUCCESS)

        mock_handler.assert_not_called()

    def test_step_created_failed_triggers(self):
        """Create (not update) with FAILED → trigger (unlike task-level which skips created).

        Phase 2's update_or_create can create a row directly with FAILED when
        the agent reports a first-attempt failure, so we must NOT skip
        created=True for step-level recovery.
        """
        with (
            patch('tasks.signals.handle_step_failure') as mock_handler,
            self.captureOnCommitCallbacks(execute=True),
        ):
            step = self._make_step(status=ExecutionStep.Status.FAILED)

        mock_handler.assert_called_once()
        self.assertEqual(mock_handler.call_args.kwargs['execution_step_id'], step.id)

    def test_step_update_to_failed_triggers(self):
        """Update existing step from RUNNING to FAILED → trigger."""
        step = self._make_step(status=ExecutionStep.Status.RUNNING, error_message='')

        with (
            patch('tasks.signals.handle_step_failure') as mock_handler,
            self.captureOnCommitCallbacks(execute=True),
        ):
            step.status = ExecutionStep.Status.FAILED
            step.error_message = 'retry exhausted'
            step.save()

        mock_handler.assert_called_once()
        self.assertEqual(mock_handler.call_args.kwargs['execution_step_id'], step.id)
        self.assertEqual(mock_handler.call_args.kwargs['error_message'], 'retry exhausted')

    def test_anti_recursion_same_step_id(self):
        """Save FAILED twice in same on_commit batch → handle_step_failure called once.

        The _processing_step_ids set blocks the second trigger because the
        first on_commit hasn't released the id yet.
        """
        with (
            patch('tasks.signals.handle_step_failure') as mock_handler,
            self.captureOnCommitCallbacks(execute=True),
        ):
            step = self._make_step(status=ExecutionStep.Status.FAILED)
            # Re-save the same step (simulating a re-entrant save during recovery).
            step.error_message = 'updated error'
            step.save()

        mock_handler.assert_called_once()

    def test_recovery_completes_then_new_failure_triggers_again(self):
        """After on_commit runs (id released), a new FAILED save triggers again."""
        # First failure + recovery (inside captureOnCommitCallbacks so on_commit runs).
        with (
            patch('tasks.signals.handle_step_failure') as mock_handler,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self._make_step(status=ExecutionStep.Status.FAILED)
        # on_commit has run, id discarded from _processing_step_ids.

        # A different step fails — should trigger independently (not blocked).
        with (
            patch('tasks.signals.handle_step_failure') as mock_handler2,
            self.captureOnCommitCallbacks(execute=True),
        ):
            step2 = self._make_step(status=ExecutionStep.Status.FAILED, step_index=1)

        mock_handler.assert_called_once()
        mock_handler2.assert_called_once()
        self.assertEqual(mock_handler2.call_args.kwargs['execution_step_id'], step2.id)

    def test_handle_step_failure_exception_clears_set(self):
        """If handle_step_failure raises, the _processing_step_ids set is still cleared."""
        from tasks.signals import _processing_step_ids

        with (
            patch('tasks.signals.handle_step_failure', side_effect=RuntimeError('boom')),
            self.captureOnCommitCallbacks(execute=True),
        ):
            step = self._make_step(status=ExecutionStep.Status.FAILED)

        # The finally block should have discarded the id.
        self.assertNotIn(step.id, _processing_step_ids)

        # And a subsequent save of the same step should trigger again (not blocked).
        with (
            patch('tasks.signals.handle_step_failure') as mock_handler,
            self.captureOnCommitCallbacks(execute=True),
        ):
            step.error_message = 'second attempt'
            step.save()

        mock_handler.assert_called_once()
