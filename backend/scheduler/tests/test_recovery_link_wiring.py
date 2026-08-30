"""
S2 (2026-08-16): 恢复链接线接线测试

覆盖:
- reassign 补派发: 换 agent 后 dispatch_task.delay 被调用; 终态不派发
- 语义动作落地: retry 重置 step ??PENDING; skip 标记 SKIPPED; task ??
  skip 宽容成功; restart/switch_account 解析 agent 设备后派发 device.command
  (S2-2.7 解除诚实降级, 2026-08-17)
- sleep 移出 signal: handle_step_failure 不再调用 time.sleep
- timeout_seconds: 超时返回失败结果
"""

from unittest.mock import patch

import pytest
from django.test import TestCase
from workers.factories import DeviceFactory, WorkerFactory

from scheduler.recovery_engine import (
    ActionSpec,
    RecoveryActionChain,
    execute_recovery_action,
    handle_step_failure,
)
from tasks.factories import TaskExecutionFactory
from tasks.models import ExecutionStep, TaskExecution

pytestmark = pytest.mark.integration


def _make_agent(**kwargs):
    """Agent with adb capability (empty task_definition requires adb)."""
    defaults = {
        "status": "online",
        "capabilities": {"adb": True, "windows": True},
    }
    defaults.update(kwargs)
    return WorkerFactory.create(**defaults)


def _make_execution(**kwargs):
    defaults = {"status": TaskExecution.Status.RUNNING}
    defaults.update(kwargs)
    return TaskExecutionFactory.create(**defaults)


def _make_step(execution, **kwargs):
    defaults = {
        "status": ExecutionStep.Status.FAILED,
        "error_message": "boom",
        "step_index": 0,
        "step_type": "click",
        "step_name": "click-target",
    }
    defaults.update(kwargs)
    return ExecutionStep.objects.create(task_result=execution, **defaults)


class TestReassignRedispatches(TestCase):
    """P1: _action_reassign 换 agent 后必须重新派发"""

    def test_reassign_dispatches_to_new_agent(self):
        agent_a = _make_agent()
        agent_b = _make_agent()
        execution = _make_execution(agent=agent_a)

        with patch("tasks.tasks.dispatch_task") as mock_dispatch:
            result = execute_recovery_action("reassign", execution.id, {})

        self.assertTrue(result["success"])
        self.assertEqual(result["details"]["new_agent_id"], agent_b.id)
        execution.refresh_from_db()
        self.assertEqual(execution.agent_id, agent_b.id)
        self.assertEqual(execution.recovery_layer, 5)
        mock_dispatch.delay.assert_called_once_with(execution.id)

    def test_reassign_skips_terminal_execution(self):
        """终态 (FAILED) 执行不能被 reassign 重新激活"""
        agent_a = _make_agent()
        _make_agent()
        execution = _make_execution(agent=agent_a, status=TaskExecution.Status.FAILED)

        with patch("tasks.tasks.dispatch_task") as mock_dispatch:
            result = execute_recovery_action("reassign", execution.id, {})

        self.assertFalse(result["success"])
        self.assertIn("not RUNNING", result["error"])
        mock_dispatch.delay.assert_not_called()


class TestSemanticActions(TestCase):
    """P3: 语义动作落地"""

    def test_retry_resets_step_to_pending(self):
        execution = _make_execution()
        step = _make_step(execution)

        result = execute_recovery_action("retry", step.id, {})

        self.assertTrue(result["success"])
        step.refresh_from_db()
        self.assertEqual(step.status, ExecutionStep.Status.PENDING)
        self.assertEqual(step.error_message, "")

    def test_retry_rejects_terminal_execution(self):
        execution = _make_execution(status=TaskExecution.Status.FAILED)
        step = _make_step(execution)

        result = execute_recovery_action("retry", step.id, {})

        self.assertFalse(result["success"])
        self.assertIn("not RUNNING", result["error"])

    def test_skip_marks_step_skipped(self):
        execution = _make_execution()
        step = _make_step(execution)

        result = execute_recovery_action("skip", step.id, {})

        self.assertTrue(result["success"])
        step.refresh_from_db()
        self.assertEqual(step.status, ExecutionStep.Status.SKIPPED)

    def test_task_level_skip_acknowledges_failed(self):
        """task 级默认链 failureAction='skip', target ??execution id"""
        execution = _make_execution(status=TaskExecution.Status.FAILED)

        result = execute_recovery_action("skip", execution.id, {})

        self.assertTrue(result["success"])
        self.assertIn("skip policy acknowledged", result["details"]["note"])

    def test_task_level_skip_missing_execution_is_success(self):
        """skip 语义 = 接受失败不恢复 — 记录不存在时跳过仍算成功"""
        result = execute_recovery_action("skip", 999999, {})
        self.assertTrue(result["success"])
        self.assertIn("not found", result["details"]["note"])

    def test_restart_dispatches_restart_app(self):
        """S2-2.7: restart → 解析执行 agent 的 ONLINE 设备 → 派发 restart_app device.command"""
        agent = _make_agent()
        execution = _make_execution(agent=agent)
        device = DeviceFactory.create(agent=agent, status="online")

        with patch("scheduler.recovery_engine._action_device_command") as mock_dispatch:
            mock_dispatch.return_value = {"success": True, "action": "restart_app", "target_id": device.id}
            result = execute_recovery_action("restart", execution.id, {})

        self.assertTrue(result["success"])
        mock_dispatch.assert_called_once_with("restart_app", device.id, {})

    def test_restart_without_agent_errors(self):
        """restart 目标无法解析到执行 agent → 显式 error (不假 success)"""
        execution = _make_execution(agent=None)

        result = execute_recovery_action("restart", execution.id, {})

        self.assertFalse(result["success"])
        self.assertIn("cannot resolve target", result["error"])

    def test_restart_without_online_device_errors(self):
        """restart 的 agent 无 ONLINE 设备 → 显式 error"""
        agent = _make_agent()
        execution = _make_execution(agent=agent)
        DeviceFactory.create(agent=agent, status="offline")

        result = execute_recovery_action("restart", execution.id, {})

        self.assertFalse(result["success"])
        self.assertIn("ONLINE device", result["error"])

    def test_switch_account_dispatches_device_command(self):
        """S2-2.7: switch_account → 解析设备 → 原样派发 device.command"""
        agent = _make_agent()
        execution = _make_execution(agent=agent)
        device = DeviceFactory.create(agent=agent, status="online")

        with patch("scheduler.recovery_engine._action_device_command") as mock_dispatch:
            mock_dispatch.return_value = {"success": True, "action": "switch_account", "target_id": device.id}
            result = execute_recovery_action("switch_account", execution.id, {})

        self.assertTrue(result["success"])
        mock_dispatch.assert_called_once_with("switch_account", device.id, {})

    def test_switch_account_step_target_dispatches(self):
        """step 级 target (ExecutionStep.id) 也能反查 agent → 派发"""
        agent = _make_agent()
        execution = _make_execution(agent=agent)
        step = _make_step(execution)
        device = DeviceFactory.create(agent=agent, status="online")

        with patch("scheduler.recovery_engine._action_device_command") as mock_dispatch:
            mock_dispatch.return_value = {"success": True, "action": "switch_account", "target_id": device.id}
            result = execute_recovery_action("switch_account", step.id, {})

        self.assertTrue(result["success"])
        mock_dispatch.assert_called_once_with("switch_account", device.id, {})


class TestStepFailureNoSleep(TestCase):
    """P4: handle_step_failure 不再 sleep"""

    def test_handle_step_failure_does_not_sleep(self):
        execution = _make_execution()
        step = _make_step(execution)

        with patch("scheduler.recovery_engine.time.sleep") as mock_sleep:
            result = handle_step_failure(step.id, "timeout")

        mock_sleep.assert_not_called()
        self.assertEqual(result["action"], "retry")
        # retry 落地: step 被重置为 PENDING
        step.refresh_from_db()
        self.assertEqual(step.status, ExecutionStep.Status.PENDING)


class TestActionTimeout:
    """P6: ActionSpec.timeout_seconds 生效 (pytest 普通类, ??pytest 断言)"""

    def test_timeout_marks_action_failed(self):
        """动作体耗时超过 timeout_seconds ??ChainStepResult(success=False)"""
        import time as _time

        chain = RecoveryActionChain(
            [ActionSpec(type="slow", target=1, timeout_seconds=1)],
            level="test",
        )
        call_count = {"n": 0}

        def slow_body(action, context):
            call_count["n"] += 1
            _time.sleep(2)  # 超过 1s 超时
            return {"ok": True}

        chain._run_action_body = slow_body
        result = chain.execute()

        assert result["success"] is False
        step = result["results"][0]
        assert step["success"] is False
        assert "timeout after" in step["error"]

    def test_no_timeout_when_under_limit(self):
        chain = RecoveryActionChain(
            [ActionSpec(type="fast", target=1, timeout_seconds=30)],
            level="test",
        )

        def fast_body(action, context):
            return {"ok": True}

        chain._run_action_body = fast_body
        result = chain.execute()

        assert result["success"] is True
        assert result["results"][0]["success"] is True

    def test_zero_timeout_disables_guard(self):
        """timeout_seconds=0 表示不限制"""
        chain = RecoveryActionChain(
            [ActionSpec(type="any", target=1, timeout_seconds=0)],
            level="test",
        )

        def body(action, context):
            return {"ok": True}

        chain._run_action_body = body
        result = chain.execute()

        assert result["success"] is True
