"""Combined tests for step execution: persistence + failure handling.

Merged from:
  - test_step_failure_e2e.py (E2E step failure handling)
  - test_step_progress_persistence.py (step progress persistence)
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TestCase, override_settings

from protocol.constants import MessageType
from protocol.consumers import WorkerConsumer
from protocol.serializers import serialize_frame
from protocol.tests import TEST_WS_PATH
from tasks.factories import TaskExecutionFactory
from tasks.models import ExecutionStep

# =============================================================================
# Source: test_step_progress_persistence.py
# =============================================================================

@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestStepProgressPersistence(TestCase):
    """Verify _handle_task_progress persists ExecutionStep rows."""

    async def _connect_communicator(self):
        """Helper: connect a WS communicator with a stubbed agent scope."""
        communicator = WebsocketCommunicator(WorkerConsumer.as_asgi(), TEST_WS_PATH)
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-p010')
        await communicator.connect()
        # Drain the initial connect frame (event_ack / welcome).
        await communicator.receive_from()
        return communicator

    async def test_step_progress_success_persists_execution_step(self):
        """task.progress with status=success and step_index → ExecutionStep(SUCCESS)."""
        execution = await sync_to_async(TaskExecutionFactory.create)()
        communicator = await self._connect_communicator()

        progress_frame = serialize_frame(
            msg_type=MessageType.TASK_PROGRESS,
            payload={
                "execution_id": str(execution.id),
                "step_index": 0,
                "step_name": "node-click-login",
                "status": "success",
                "elapsed_time": 0.42,
                "message": "节点 node-click-login 成功",
            },
        )
        await communicator.send_to(text_data=progress_frame)
        # Give the consumer a tick to process.
        await asyncio.sleep(0.05)
        await communicator.disconnect()

        steps = list(await sync_to_async(list)(ExecutionStep.objects.filter(task_result=execution)))
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertEqual(step.step_index, 0)
        self.assertEqual(step.step_name, "node-click-login")
        self.assertEqual(step.status, ExecutionStep.Status.SUCCESS)
        self.assertEqual(step.step_type, "pipeline_node")
        self.assertAlmostEqual(step.duration, 0.42, places=2)
        self.assertIsNotNone(step.completed_at)
        self.assertEqual(step.error_message, "")

    async def test_step_progress_failed_persists_execution_step_with_error(self):
        """task.progress with status=failed → ExecutionStep(FAILED) + error_message."""
        execution = await sync_to_async(TaskExecutionFactory.create)()
        communicator = await self._connect_communicator()

        progress_frame = serialize_frame(
            msg_type=MessageType.TASK_PROGRESS,
            payload={
                "execution_id": str(execution.id),
                "step_index": 2,
                "step_name": "node-template-match",
                "status": "failed",
                "error_msg": "template 'login_button.png' not found in ROI",
                "elapsed_time": 0.31,
                "message": "节点 node-template-match 失败",
            },
        )
        await communicator.send_to(text_data=progress_frame)
        await asyncio.sleep(0.05)
        await communicator.disconnect()

        steps = list(await sync_to_async(list)(ExecutionStep.objects.filter(task_result=execution)))
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertEqual(step.step_index, 2)
        self.assertEqual(step.step_name, "node-template-match")
        self.assertEqual(step.status, ExecutionStep.Status.FAILED)
        self.assertEqual(step.error_message, "template 'login_button.png' not found in ROI")
        self.assertAlmostEqual(step.duration, 0.31, places=2)
        self.assertIsNotNone(step.completed_at)

    async def test_step_progress_upserts_on_resend(self):
        """Re-sending the same step_index upserts instead of duplicating."""
        execution = await sync_to_async(TaskExecutionFactory.create)()
        communicator = await self._connect_communicator()

        # First send: status=running
        frame1 = serialize_frame(
            msg_type=MessageType.TASK_PROGRESS,
            payload={
                "execution_id": str(execution.id),
                "step_index": 1,
                "step_name": "node-1",
                "status": "running",
                "elapsed_time": 0.0,
            },
        )
        await communicator.send_to(text_data=frame1)
        await asyncio.sleep(0.05)

        # Second send: status=success (upsert)
        frame2 = serialize_frame(
            msg_type=MessageType.TASK_PROGRESS,
            payload={
                "execution_id": str(execution.id),
                "step_index": 1,
                "step_name": "node-1",
                "status": "success",
                "elapsed_time": 0.5,
            },
        )
        await communicator.send_to(text_data=frame2)
        await asyncio.sleep(0.05)
        await communicator.disconnect()

        steps = list(await sync_to_async(list)(
            ExecutionStep.objects.filter(task_result=execution, step_index=1)
        ))
        self.assertEqual(len(steps), 1, "upsert should not duplicate")
        self.assertEqual(steps[0].status, ExecutionStep.Status.SUCCESS)

    async def test_step_progress_without_step_index_skips_persistence(self):
        """task.progress without step_index (task-level heartbeat) → no ExecutionStep."""
        execution = await sync_to_async(TaskExecutionFactory.create)()
        communicator = await self._connect_communicator()

        frame = serialize_frame(
            msg_type=MessageType.TASK_PROGRESS,
            payload={
                "execution_id": str(execution.id),
                "status": "running",
                "message": "开始执行 Pipeline",
            },
        )
        await communicator.send_to(text_data=frame)
        await asyncio.sleep(0.05)
        await communicator.disconnect()

        exists = await sync_to_async(ExecutionStep.objects.filter(task_result=execution).exists)()
        self.assertFalse(exists)

    async def test_step_progress_unknown_execution_id_is_non_fatal(self):
        """Unknown execution_id → no ExecutionStep, no exception, consumer survives.

        Use a random UUID that won't match any TaskExecution row. The
        consumer catches DoesNotExist + ValueError and logs a warning
        instead of crashing.
        """
        communicator = await self._connect_communicator()

        sentinel_uuid = "12345678-1234-1234-1234-123456789abc"
        frame = serialize_frame(
            msg_type=MessageType.TASK_PROGRESS,
            payload={
                "execution_id": sentinel_uuid,
                "step_index": 0,
                "step_name": "node-x",
                "status": "success",
                "elapsed_time": 0.1,
            },
        )
        await communicator.send_to(text_data=frame)
        await asyncio.sleep(0.05)
        await communicator.disconnect()

        # The consumer logged the warning and didn't crash. Verify by
        # checking that no ExecutionStep was created in this test's DB
        # (there's no matching TaskExecution row to attach to).
        total = await sync_to_async(ExecutionStep.objects.count)()
        self.assertEqual(total, 0)

    async def test_step_progress_invalid_status_falls_back_to_running(self):
        """Unknown status string → ExecutionStep(RUNNING) (don't lose the row)."""
        execution = await sync_to_async(TaskExecutionFactory.create)()
        communicator = await self._connect_communicator()

        frame = serialize_frame(
            msg_type=MessageType.TASK_PROGRESS,
            payload={
                "execution_id": str(execution.id),
                "step_index": 3,
                "step_name": "node-3",
                "status": "weird-status",
                "elapsed_time": 0.2,
            },
        )
        await communicator.send_to(text_data=frame)
        await asyncio.sleep(0.05)
        await communicator.disconnect()

        steps = list(await sync_to_async(list)(ExecutionStep.objects.filter(task_result=execution)))
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].status, ExecutionStep.Status.RUNNING)


# =============================================================================
# Source: test_step_failure_e2e.py
# =============================================================================

@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestStepFailureE2E(TestCase):
    """E2E: agent task.progress(FAILED) → ExecutionStep(FAILED) + signal fires."""

    async def _connect_communicator(self):
        """Helper: connect a WS communicator with a stubbed agent scope."""
        communicator = WebsocketCommunicator(
            WorkerConsumer.as_asgi(), TEST_WS_PATH
        )
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-e2e')
        await communicator.connect()
        # Drain the initial connect ack frame.
        await communicator.receive_from()
        return communicator

    async def test_e2e_failed_frame_persists_and_fires_signal(self):
        """WS frame(FAILED) → ExecutionStep(FAILED) persisted + signal fires.

        Verifies:
        - Phase 2: consumer persists ExecutionStep with correct fields
        - Phase 3: post_save signal fires (step_id in _processing_step_ids)
        """
        execution = await sync_to_async(TaskExecutionFactory.create)()
        communicator = await self._connect_communicator()

        from tasks.signals import _processing_step_ids
        _processing_step_ids.clear()

        frame = serialize_frame(
            msg_type=MessageType.TASK_PROGRESS,
            payload={
                "execution_id": str(execution.id),
                "step_index": 0,
                "step_name": "node-e2e-login",
                "status": "failed",
                "error_msg": "E2E: template 'login_btn.png' not found",
                "elapsed_time": 0.15,
            },
        )
        await communicator.send_to(text_data=frame)
        await asyncio.sleep(0.15)
        await communicator.disconnect()

        # --- Phase 2: ExecutionStep persisted ---
        steps = list(await sync_to_async(list)(
            ExecutionStep.objects.filter(task_result=execution)
        ))
        self.assertEqual(len(steps), 1)
        step = steps[0]
        self.assertEqual(step.step_index, 0)
        self.assertEqual(step.step_name, "node-e2e-login")
        self.assertEqual(step.status, ExecutionStep.Status.FAILED)
        self.assertEqual(step.error_message, "E2E: template 'login_btn.png' not found")

        # --- Phase 3: signal fired (on_commit scheduled) ---
        # The signal receiver added step.id to _processing_step_ids before
        # scheduling transaction.on_commit. on_commit won't fire inside
        # TestCase (outer transaction never commits), so the id stays in
        # the set — proving the signal ran.
        self.assertIn(
            step.id, _processing_step_ids,
            'signal should have added step.id to _processing_step_ids',
        )

    async def test_e2e_success_frame_no_signal(self):
        """WS frame(SUCCESS) → ExecutionStep(SUCCESS), signal does NOT fire."""
        execution = await sync_to_async(TaskExecutionFactory.create)()
        communicator = await self._connect_communicator()

        from tasks.signals import _processing_step_ids
        _processing_step_ids.clear()

        frame = serialize_frame(
            msg_type=MessageType.TASK_PROGRESS,
            payload={
                "execution_id": str(execution.id),
                "step_index": 0,
                "step_name": "node-e2e-ok",
                "status": "success",
                "elapsed_time": 0.08,
            },
        )
        await communicator.send_to(text_data=frame)
        await asyncio.sleep(0.15)
        await communicator.disconnect()

        steps = list(await sync_to_async(list)(
            ExecutionStep.objects.filter(task_result=execution)
        ))
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].status, ExecutionStep.Status.SUCCESS)

        # SUCCESS status → signal receiver returns early → id NOT in set.
        self.assertEqual(len(_processing_step_ids), 0)

    async def test_e2e_mixed_steps_only_failed_fires_signal(self):
        """Mixed: success(0) + failed(1) → only step 1's signal fires."""
        execution = await sync_to_async(TaskExecutionFactory.create)()
        communicator = await self._connect_communicator()

        from tasks.signals import _processing_step_ids
        _processing_step_ids.clear()

        # Step 0: success
        frame0 = serialize_frame(
            msg_type=MessageType.TASK_PROGRESS,
            payload={
                "execution_id": str(execution.id),
                "step_index": 0,
                "step_name": "node-0",
                "status": "success",
                "elapsed_time": 0.05,
            },
        )
        await communicator.send_to(text_data=frame0)
        await asyncio.sleep(0.1)

        # Step 1: failed
        frame1 = serialize_frame(
            msg_type=MessageType.TASK_PROGRESS,
            payload={
                "execution_id": str(execution.id),
                "step_index": 1,
                "step_name": "node-1",
                "status": "failed",
                "error_msg": "E2E: step 1 failed",
                "elapsed_time": 0.12,
            },
        )
        await communicator.send_to(text_data=frame1)
        await asyncio.sleep(0.1)
        await communicator.disconnect()

        steps = list(await sync_to_async(list)(
            ExecutionStep.objects.filter(task_result=execution).order_by('step_index')
        ))
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].status, ExecutionStep.Status.SUCCESS)
        self.assertEqual(steps[1].status, ExecutionStep.Status.FAILED)

        # Only the failed step's id should be in _processing_step_ids.
        self.assertIn(steps[1].id, _processing_step_ids)
        self.assertNotIn(steps[0].id, _processing_step_ids)
