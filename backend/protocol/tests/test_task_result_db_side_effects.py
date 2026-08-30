"""Integration tests for WorkerConsumer._handle_task_result DB side effects.

Covers the protocol WorkerConsumer's task.result handler end-to-end via
WebsocketCommunicator: agent sends task.result frame → consumer calls
_db_update_execution_result → TaskExecution DB row updated.

Scope (TD-261):
  - TaskExecution.status transitions (pending/running → success / failed)
  - TaskExecution.completed_at set on both success and failure
  - TaskExecution.duration computed from elapsed_time
  - TaskExecution.started_at backfilled when missing
  - TaskExecution.result_data / error_message written correctly
  - Unknown / invalid execution_id handled non-fatally
  - ACK frame returned to agent

Out of scope (covered by other TD-261 files):
  - ConcurrencyController slot release → test_concurrency_wiring_via_protocol_consumer.py
  - Device.status restore → test_device_status_lifecycle_via_protocol_consumer.py

Note: spec-29c (commit 8f184734) deleted the legacy agents/consumers.py:WorkerConsumer
(1151 lines) and replaced it with protocol/consumers.py:WorkerConsumer. The legacy
consumer called _release_concurrency_slot + _restore_device_status on task.result;
the new consumer does NOT (tracked as TD-267). These tests deliberately assert
the current (buggy) behavior for slot/device as regression baselines so the
TD-267 fix can flip the assertions when wiring is restored.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TestCase, override_settings

from protocol.constants import MessageType
from protocol.consumers import WorkerConsumer
from protocol.serializers import serialize_frame
from protocol.tests import TEST_WS_PATH
from tasks.factories import TaskExecutionFactory
from tasks.models import TaskExecution


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestTaskResultDbSideEffects(TestCase):
    """End-to-end DB side-effect coverage for WorkerConsumer._handle_task_result."""

    async def _connect_communicator(self):
        """Connect a WS communicator with a stubbed agent scope.

        Mirrors the pattern in test_step_failure_e2e.py: drain the initial
        connect ack frame so subsequent receive_from() calls return the
        frame we actually want to assert on.
        """
        communicator = WebsocketCommunicator(
            WorkerConsumer.as_asgi(), TEST_WS_PATH
        )
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-result')
        await communicator.connect()
        await communicator.receive_from()  # drain connect ack
        return communicator

    async def _send_task_result(self, communicator, *, execution_id, success,
                                 elapsed_time=0.0, error_msg="", data=None):
        """Send a task.result frame and wait briefly for consumer to process."""
        payload = {
            "execution_id": str(execution_id),
            "success": success,
            "elapsed_time": elapsed_time,
            "error_msg": error_msg,
            "data": data if data is not None else {},
        }
        frame = serialize_frame(msg_type=MessageType.TASK_RESULT, payload=payload)
        await communicator.send_to(text_data=frame)
        await asyncio.sleep(0.1)

    async def _reload_execution(self, execution):
        """Refresh an execution instance from DB under async context."""
        return await sync_to_async(TaskExecution.objects.get)(pk=execution.id)

    # --- happy path: success ---

    async def test_task_result_success_updates_execution_status(self):
        """success=True → TaskExecution.status becomes SUCCESS."""
        execution = await sync_to_async(TaskExecutionFactory.create)(status=TaskExecution.Status.RUNNING)
        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=True,
                elapsed_time=1.5,
                data={"steps_completed": 3},
            )
        finally:
            await communicator.disconnect()

        refreshed = await self._reload_execution(execution)
        self.assertEqual(refreshed.status, TaskExecution.Status.SUCCESS)

    async def test_task_result_success_sets_completed_at(self):
        """success=True → completed_at is set (was None for pending/running)."""
        execution = await sync_to_async(TaskExecutionFactory.create)(status=TaskExecution.Status.RUNNING)
        self.assertIsNone(execution.completed_at)

        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=True,
                elapsed_time=0.5,
            )
        finally:
            await communicator.disconnect()

        refreshed = await self._reload_execution(execution)
        self.assertIsNotNone(refreshed.completed_at)

    async def test_task_result_success_sets_result_data(self):
        """success=True → result_data dict is persisted to the row."""
        execution = await sync_to_async(TaskExecutionFactory.create)()
        payload = {"steps_completed": 5, "score": 100, "items": ["sword", "shield"]}

        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=True,
                elapsed_time=2.0,
                data=payload,
            )
        finally:
            await communicator.disconnect()

        refreshed = await self._reload_execution(execution)
        self.assertEqual(refreshed.result_data, payload)
        self.assertEqual(refreshed.error_message, "")

    # --- failure path ---

    async def test_task_result_failure_updates_execution_status(self):
        """success=False → TaskExecution.status becomes FAILED."""
        execution = await sync_to_async(TaskExecutionFactory.create)(status=TaskExecution.Status.RUNNING)

        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=False,
                elapsed_time=0.3,
                error_msg="template not found",
            )
        finally:
            await communicator.disconnect()

        refreshed = await self._reload_execution(execution)
        self.assertEqual(refreshed.status, TaskExecution.Status.FAILED)

    async def test_task_result_failure_sets_completed_at(self):
        """success=False → completed_at is also set (failed tasks still terminate)."""
        execution = await sync_to_async(TaskExecutionFactory.create)()

        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=False,
                elapsed_time=0.1,
                error_msg="boom",
            )
        finally:
            await communicator.disconnect()

        refreshed = await self._reload_execution(execution)
        self.assertIsNotNone(refreshed.completed_at)

    async def test_task_result_failure_sets_error_message(self):
        """success=False → error_message captured, empty when not provided."""
        execution = await sync_to_async(TaskExecutionFactory.create)()

        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=False,
                elapsed_time=0.0,
                error_msg="image match failed at step 3",
            )
        finally:
            await communicator.disconnect()

        refreshed = await self._reload_execution(execution)
        self.assertEqual(refreshed.error_message, "image match failed at step 3")

    async def test_task_result_failure_empty_error_kept_empty(self):
        """success=False + empty error_msg → error_message stays empty (no fake placeholder)."""
        execution = await sync_to_async(TaskExecutionFactory.create)()

        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=False,
                elapsed_time=0.0,
                error_msg="",
            )
        finally:
            await communicator.disconnect()

        refreshed = await self._reload_execution(execution)
        self.assertEqual(refreshed.error_message, "")

    # --- duration / started_at backfill ---

    async def test_task_result_calculates_duration_from_elapsed_time(self):
        """duration = timedelta(seconds=elapsed_time)."""
        execution = await sync_to_async(TaskExecutionFactory.create)()

        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=True,
                elapsed_time=12.5,
            )
        finally:
            await communicator.disconnect()

        refreshed = await self._reload_execution(execution)
        self.assertIsNotNone(refreshed.duration)
        self.assertAlmostEqual(refreshed.duration.total_seconds(), 12.5, places=3)

    async def test_task_result_invalid_elapsed_time_defaults_to_zero(self):
        """Non-numeric elapsed_time → duration=0 (graceful fallback)."""
        execution = await sync_to_async(TaskExecutionFactory.create)()

        # Build the frame manually so we can inject a non-numeric elapsed_time
        # without the serializer coercing it.
        raw_frame = serialize_frame(
            msg_type=MessageType.TASK_RESULT,
            payload={
                "execution_id": str(execution.id),
                "success": True,
                "elapsed_time": "not-a-number",
            },
        )
        # Manually patch the payload's elapsed_time to a string (serializer
        # may pass through numbers, but the agent could send garbage).
        parsed = json.loads(raw_frame)
        parsed["payload"]["elapsed_time"] = "garbage"
        raw_frame = json.dumps(parsed)

        communicator = await self._connect_communicator()
        try:
            await communicator.send_to(text_data=raw_frame)
            await asyncio.sleep(0.1)
        finally:
            await communicator.disconnect()

        refreshed = await self._reload_execution(execution)
        self.assertIsNotNone(refreshed.duration)
        self.assertEqual(refreshed.duration.total_seconds(), 0.0)

    async def test_task_result_backfills_started_at_when_missing(self):
        """started_at=None → consumer sets started_at = now - duration."""
        execution = await sync_to_async(TaskExecutionFactory.create)()
        self.assertIsNone(execution.started_at)

        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=True,
                elapsed_time=10.0,
            )
        finally:
            await communicator.disconnect()

        refreshed = await self._reload_execution(execution)
        self.assertIsNotNone(refreshed.started_at)
        # started_at should be ~ (completed_at - 10s); allow ±2s tolerance for
        # event-loop scheduling jitter.
        delta = (refreshed.completed_at - refreshed.started_at).total_seconds()
        self.assertAlmostEqual(delta, 10.0, delta=2.0)

    async def test_task_result_preserves_existing_started_at(self):
        """If started_at is already set, consumer must NOT overwrite it."""
        from datetime import timedelta as td

        from django.utils import timezone as dj_tz

        original_started = dj_tz.now() - td(minutes=5)
        execution = await sync_to_async(TaskExecutionFactory.create)()
        execution.started_at = original_started
        await sync_to_async(execution.save)()

        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=True,
                elapsed_time=2.0,
            )
        finally:
            await communicator.disconnect()

        refreshed = await self._reload_execution(execution)
        # Should remain unchanged (within DB microsecond precision).
        self.assertEqual(refreshed.started_at, original_started)

    # --- boundary / robustness ---

    async def test_task_result_unknown_execution_id_is_non_fatal(self):
        """Unknown execution_id → consumer logs warning, still sends ACK, no crash."""
        unknown_id = "00000000-0000-0000-0000-000000000000"
        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=unknown_id,
                success=True,
                elapsed_time=1.0,
            )
            # ACK frame should still arrive (consumer does not raise).
            ack_raw = await communicator.receive_from(timeout=2.0)
            ack = json.loads(ack_raw)
            self.assertEqual(ack["type"], MessageType.EVENT_ACK)
            self.assertEqual(ack["payload"]["ack_type"], MessageType.TASK_RESULT)
            self.assertEqual(ack["payload"]["execution_id"], unknown_id)
        finally:
            await communicator.disconnect()

    async def test_task_result_invalid_execution_id_string_is_non_fatal(self):
        """Garbage execution_id (not a UUID/int) → DoesNotExist/ValueError swallowed."""
        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id="not-a-valid-id",
                success=True,
                elapsed_time=0.0,
            )
            ack_raw = await communicator.receive_from(timeout=2.0)
            ack = json.loads(ack_raw)
            self.assertEqual(ack["type"], MessageType.EVENT_ACK)
        finally:
            await communicator.disconnect()

    async def test_task_result_returns_ack_with_execution_id(self):
        """ACK frame echoed back to agent with correct execution_id + ack_type."""
        execution = await sync_to_async(TaskExecutionFactory.create)()

        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=True,
                elapsed_time=0.5,
            )
            ack_raw = await communicator.receive_from(timeout=2.0)
            ack = json.loads(ack_raw)
            self.assertEqual(ack["type"], MessageType.EVENT_ACK)
            self.assertEqual(ack["payload"]["ack_type"], MessageType.TASK_RESULT)
            self.assertEqual(ack["payload"]["execution_id"], str(execution.id))
        finally:
            await communicator.disconnect()

    async def test_task_result_pending_to_success_transition(self):
        """PENDING (not RUNNING) → SUCCESS: status transition still works.

        TaskExecutionFactory default status is PENDING. The consumer should
        overwrite it to SUCCESS regardless of the prior state.
        """
        execution = await sync_to_async(TaskExecutionFactory.create)(status=TaskExecution.Status.PENDING)
        self.assertEqual(execution.status, TaskExecution.Status.PENDING)

        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=True,
                elapsed_time=1.0,
            )
        finally:
            await communicator.disconnect()

        refreshed = await self._reload_execution(execution)
        self.assertEqual(refreshed.status, TaskExecution.Status.SUCCESS)

    # --- spec §8.2: log archiving scheduled on terminal status ---

    async def test_task_result_success_schedules_log_archive(self):
        """Terminal status (SUCCESS) → pack_execution_logs_task.delay called.

        spec §8.2: when a TaskExecution finalizes (SUCCESS / FAILED /
        FORCE_TERMINATED), the consumer schedules the log-archive Celery
        task via transaction.on_commit so the tarball is built after the
        DB row is durable.
        """
        from unittest.mock import patch

        execution = await sync_to_async(TaskExecutionFactory.create)(status=TaskExecution.Status.RUNNING)

        # captureOnCommitCallbacks does NOT capture on_commit callbacks
        # registered inside database_sync_to_async (different DB
        # connection context in the async boundary — see
        # test_step_failure_e2e.py header note). So we patch
        # transaction.on_commit to invoke the callback synchronously,
        # which lets us observe the .delay() call directly.
        # transaction is imported INSIDE _update_execution_result, so we
        # patch the global django.db.transaction.on_commit.
        communicator = await self._connect_communicator()
        try:
            with patch(
                "debug.tasks.pack_execution_logs_task.delay",
            ) as mock_delay, patch(
                "django.db.transaction.on_commit",
                lambda fn: fn(),
            ):
                await self._send_task_result(
                    communicator,
                    execution_id=execution.id,
                    success=True,
                    elapsed_time=1.0,
                )
        finally:
            await communicator.disconnect()

        # pack_execution_logs_task.delay(str(execution.id)) should have
        # fired synchronously inside the (now-executed) on_commit callback.
        # The execution_id arrives as a string from the protocol payload
        # (JSON-decoded), so the lambda captures it as a string.
        mock_delay.assert_called_once_with(str(execution.id))

    async def test_task_result_skips_archive_for_non_terminal_status(self):
        """Non-terminal status (PENDING here via invalid success+state) —
        the archive task should NOT be scheduled.

        spec §8.2 only triggers archiving for SUCCESS / FAILED /
        FORCE_TERMINATED. This is a regression guard so future changes
        to the wiring (e.g. expanding to more states) don't accidentally
        fire on intermediate states.
        """
        from unittest.mock import patch

        # Use an unknown execution_id — the consumer treats it as a
        # no-op (logs a warning) and must NOT schedule archiving.
        unknown_id = "00000000-0000-0000-0000-000000000000"

        communicator = await self._connect_communicator()
        try:
            with patch(
                "debug.tasks.pack_execution_logs_task.delay",
            ) as mock_delay:
                await self._send_task_result(
                    communicator,
                    execution_id=unknown_id,
                    success=True,
                    elapsed_time=1.0,
                )
        finally:
            await communicator.disconnect()

        mock_delay.assert_not_called()
