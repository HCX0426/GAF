"""S1 (2026-08-16) 协议可靠性语义测试: dispatch ack / 终态守卫 / slot 释放.

覆盖:
- dispatch_task 派发后记录 dispatch_sent_at (execution_snapshot)
- check_dispatch_acks: agent 在线 → 重新派发; agent 离线 → fail + 释放资源
- check_dispatch_acks: ack 已回 → 不触发任何动作
- update_task_execution_result 终态守卫: 迟到 task.result 不复活终态
- check_agent_heartbeats fail RUNNING 时释放并发槽位
"""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

from django.test import TestCase
from django.utils import timezone
from pipeline.models import TaskChain, TaskChainExecution
from workers.factories import DeviceFactory, WorkerFactory

from tasks.factories import TaskExecutionFactory
from tasks.models import TaskExecution


def _make_agent(**kwargs):
    """Agent with adb capability (empty task_definition requires adb)."""
    defaults = {
        "status": "online",
        "capabilities": {"adb": True, "windows": True},
    }
    defaults.update(kwargs)
    return WorkerFactory.create(**defaults)


class TestDispatchAckTracking(TestCase):
    """dispatch_task 派发后应记录 dispatch_sent_at ??ack 扫描使用."""

    @patch("tasks.tasks.get_channel_layer")
    def test_dispatch_records_dispatch_sent_at(self, mock_layer):
        from tasks.tasks import dispatch_task

        # async_to_sync(channel_layer.group_send) 需要 awaitable; AsyncMock 满足
        mock_layer.return_value.group_send = AsyncMock()

        agent = _make_agent()
        execution = TaskExecutionFactory.create(
            status=TaskExecution.Status.PENDING,
            agent=agent,
        )
        execution.task.is_enabled = True
        execution.task.save()

        dispatch_task.run(execution.id, trace_id="trace-1")

        execution.refresh_from_db()
        print("DEBUG status:", execution.status, "error:", execution.error_message)
        snap = execution.execution_snapshot or {}
        self.assertIn("dispatch_sent_at", snap)
        self.assertEqual(snap["dispatch_attempts"], 1)
        self.assertNotIn("dispatch_ack_at", snap)
        self.assertEqual(mock_layer.return_value.group_send.call_count, 1)


class TestCheckDispatchAcks(TestCase):
    """check_dispatch_acks beat 任务: 未 ack 超时 → 重派或 fail."""

    def _make_execution(self, *, agent_status="online", sent_seconds_ago=30, acked=False):
        agent = _make_agent(status=agent_status)
        execution = TaskExecutionFactory.create(
            status=TaskExecution.Status.RUNNING,
            agent=agent,
            execution_snapshot={
                "dispatch_sent_at": (
                    timezone.now() - timedelta(seconds=sent_seconds_ago)
                ).isoformat(),
                "dispatch_attempts": 1,
                **({"dispatch_ack_at": timezone.now().isoformat()} if acked else {}),
            },
        )
        return execution

    def test_offline_agent_fails_execution(self):
        from tasks.heartbeat import check_dispatch_acks

        execution = self._make_execution(agent_status="offline")

        with patch("tasks.tasks.dispatch_task") as mock_dispatch:
            check_dispatch_acks()

        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.FAILED)
        mock_dispatch.delay.assert_not_called()

    def test_online_agent_redispatch(self):
        from tasks.heartbeat import check_dispatch_acks

        execution = self._make_execution(agent_status="online")

        with patch("tasks.tasks.dispatch_task") as mock_dispatch:
            check_dispatch_acks()

        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.RUNNING)
        mock_dispatch.delay.assert_called_once()
        args, kwargs = mock_dispatch.delay.call_args
        self.assertEqual(args[0], execution.id)

    def test_acked_execution_untouched(self):
        from tasks.heartbeat import check_dispatch_acks

        execution = self._make_execution(agent_status="online", acked=True)

        with patch("tasks.tasks.dispatch_task") as mock_dispatch:
            check_dispatch_acks()

        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.RUNNING)
        mock_dispatch.delay.assert_not_called()

    def test_max_attempts_fails_even_online(self):
        from tasks.heartbeat import check_dispatch_acks

        agent = _make_agent(status="online")
        execution = TaskExecutionFactory.create(
            status=TaskExecution.Status.RUNNING,
            agent=agent,
            execution_snapshot={
                "dispatch_sent_at": (
                    timezone.now() - timedelta(seconds=30)
                ).isoformat(),
                "dispatch_attempts": 3,
            },
        )

        with patch("tasks.tasks.dispatch_task") as mock_dispatch:
            check_dispatch_acks()

        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.FAILED)
        mock_dispatch.delay.assert_not_called()

    def test_recent_sent_not_stale(self):
        from tasks.heartbeat import check_dispatch_acks

        execution = self._make_execution(agent_status="online", sent_seconds_ago=2)

        with patch("tasks.tasks.dispatch_task") as mock_dispatch:
            check_dispatch_acks()

        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.RUNNING)
        mock_dispatch.delay.assert_not_called()


class TestTaskResultTerminalGuard(TestCase):
    """S1 终态守卫: 迟到/重复 task.result 不得复活终态执行."""

    def test_stale_result_does_not_revive_failed(self):
        from protocol.services import update_task_execution_result

        execution = TaskExecutionFactory.create(
            status=TaskExecution.Status.FAILED,
            error_message="心跳超时已 fail",
        )

        update_task_execution_result(
            execution_id=execution.id,
            success=True,
            elapsed_time=1.0,
            error_msg="",
            result_data={"ok": True},
        )

        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.FAILED)
        self.assertEqual(execution.result_data, {})

    def test_stale_result_does_not_revive_cancelled(self):
        from protocol.services import update_task_execution_result

        execution = TaskExecutionFactory.create(
            status=TaskExecution.Status.CANCELLED,
        )

        update_task_execution_result(
            execution_id=execution.id,
            success=True,
            elapsed_time=1.0,
            error_msg="",
            result_data={"ok": True},
        )

        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.CANCELLED)

    def test_running_execution_accepts_result(self):
        from protocol.services import update_task_execution_result

        execution = TaskExecutionFactory.create(
            status=TaskExecution.Status.RUNNING,
        )

        update_task_execution_result(
            execution_id=execution.id,
            success=True,
            elapsed_time=2.0,
            error_msg="",
            result_data={"ok": True},
        )

        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.SUCCESS)
        self.assertEqual(execution.result_data, {"ok": True})


class TestHeartbeatReleasesSlot(TestCase):
    """S1: check_agent_heartbeats fail RUNNING 时释放并发槽位."""

    @patch("tasks.services.monitor_service._release_concurrency_slot")
    @patch("scheduler.recovery_engine.handle_agent_timeout", return_value={"action": "waiting"})
    def test_fail_path_releases_concurrency_slot(self, mock_recovery, mock_release):
        from tasks.heartbeat import check_agent_heartbeats

        agent = _make_agent(
            status="online",
            last_heartbeat=timezone.now() - timedelta(seconds=60),
        )
        execution = TaskExecutionFactory.create(
            status=TaskExecution.Status.RUNNING,
            agent=agent,
        )

        check_agent_heartbeats()

        execution.refresh_from_db()
        self.assertEqual(execution.status, TaskExecution.Status.FAILED)
        mock_release.assert_called_once_with(agent.agent_id, str(execution.id))


class TestCheckStuckChains(TestCase):
    """TD-425 (2026-09-05): check_stuck_chains 链级卡死清理.

    链卡 running 超阈值且无活跃节点执行 → 置 FAILED, 解除 device_busy 阻塞;
    有活跃节点执行 (长任务) / 未超阈值 → 一律跳过.
    """

    @staticmethod
    def _make_chain(started_hours_ago=2, with_active_exec=False):
        chain = TaskChain.objects.create(name="stuck-chain", is_enabled=True)
        dev = DeviceFactory.create()
        tce = TaskChainExecution.objects.create(
            chain=chain,
            device=dev,
            agent_id="agent-x",
            status=TaskChainExecution.Status.RUNNING,
        )
        # started_at is auto_now_add; rewind it to simulate a long-stuck chain.
        TaskChainExecution.objects.filter(pk=tce.pk).update(
            started_at=timezone.now() - timedelta(hours=started_hours_ago)
        )
        tce.refresh_from_db()
        if with_active_exec:
            TaskExecutionFactory.create(
                status=TaskExecution.Status.RUNNING,
                chain_execution=tce,
            )
        return tce

    def test_stuck_chain_without_active_exec_is_failed(self):
        from tasks.heartbeat import check_stuck_chains

        tce = self._make_chain(started_hours_ago=2)
        check_stuck_chains()

        tce.refresh_from_db()
        self.assertEqual(tce.status, TaskChainExecution.Status.FAILED)
        self.assertIn("卡死", tce.error_message)
        self.assertIsNotNone(tce.completed_at)

    def test_stuck_chain_with_active_exec_skipped(self):
        from tasks.heartbeat import check_stuck_chains

        tce = self._make_chain(started_hours_ago=2, with_active_exec=True)
        check_stuck_chains()

        tce.refresh_from_db()
        self.assertEqual(tce.status, TaskChainExecution.Status.RUNNING)

    def test_recent_chain_not_cleaned(self):
        from tasks.heartbeat import check_stuck_chains

        # started_at 未超过阈值 (started now) → 不清理
        tce = self._make_chain(started_hours_ago=0)
        check_stuck_chains()

        tce.refresh_from_db()
        self.assertEqual(tce.status, TaskChainExecution.Status.RUNNING)

    def test_success_chain_untouched(self):
        from tasks.heartbeat import check_stuck_chains

        chain = TaskChain.objects.create(name="done-chain", is_enabled=True)
        dev = DeviceFactory.create()
        tce = TaskChainExecution.objects.create(
            chain=chain,
            device=dev,
            agent_id="agent-x",
            status=TaskChainExecution.Status.SUCCESS,
            completed_at=timezone.now(),
        )
        check_stuck_chains()

        tce.refresh_from_db()
        self.assertEqual(tce.status, TaskChainExecution.Status.SUCCESS)
