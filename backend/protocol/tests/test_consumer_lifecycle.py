"""Integration tests for protocol AgentConsumer lifecycle (TD-261).

Merged from:
  - test_concurrency_wiring_via_protocol_consumer.py
  - test_device_status_lifecycle_via_protocol_consumer.py

Covers:
  - ConcurrencyController in-memory backend unit behavior
  - dispatch_task acquire wiring (controller.assign called on dispatch)
  - AgentConsumer._handle_task_result release wiring (TD-267 fix)
  - Device.status ONLINE → BUSY transition on task dispatch
  - Device.status BUSY → ONLINE restoration on task completion
  - _restore_device_status multi-instance aware behavior
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TestCase, override_settings
from workers.factories import DeviceFactory
from workers.models import Device

from protocol.constants import MessageType
from protocol.consumers import AgentConsumer
from protocol.serializers import serialize_frame
from protocol.tests import TEST_WS_PATH
from tasks.concurrency_controller import ConcurrencyController
from tasks.factories import TaskExecutionFactory
from tasks.models import TaskExecution
from tasks.services import (
    _release_concurrency_slot,
    _restore_device_status,
    _restore_device_status_by_msg,
)

# =============================================================================
# Source: test_concurrency_wiring_via_protocol_consumer.py
# =============================================================================


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestConcurrencyControllerUnit(TestCase):
    """Pure unit tests for the in-memory ConcurrencyController backend.

    These do NOT touch Django channels / DB — they verify the controller's
    bookkeeping in isolation so the integration tests below can focus on
    wiring (whether the consumer calls release at all).
    """

    def setUp(self):
        # Fresh controller per test so caps and counts don't leak across tests.
        self.controller = ConcurrencyController(max_tasks_per_agent=3, max_total_tasks=20)

    def test_can_assign_returns_true_for_empty_agent(self):
        """Fresh agent with no in-flight tasks → can_assign True."""
        self.assertTrue(self.controller.can_assign("agent-001"))

    def test_can_assign_returns_false_for_empty_agent_id(self):
        """Empty agent_id is rejected (defensive guard)."""
        self.assertFalse(self.controller.can_assign(""))
        self.assertFalse(self.controller.can_assign(None))

    def test_assign_increments_agent_load(self):
        """assign adds the task to the agent's in-flight set."""
        self.controller.assign("agent-001", "task-A")
        self.assertEqual(self.controller.get_agent_load("agent-001"), 1)
        self.assertEqual(self.controller.total_in_flight, 1)

    def test_assign_is_idempotent_for_same_task(self):
        """Re-assigning the same (agent, task) pair is a no-op."""
        self.controller.assign("agent-001", "task-A")
        self.controller.assign("agent-001", "task-A")
        self.assertEqual(self.controller.get_agent_load("agent-001"), 1)

    def test_assign_multiple_tasks_accumulate(self):
        """Multiple distinct tasks on the same agent all count."""
        self.controller.assign("agent-001", "task-A")
        self.controller.assign("agent-001", "task-B")
        self.controller.assign("agent-001", "task-C")
        self.assertEqual(self.controller.get_agent_load("agent-001"), 3)

    def test_can_assign_returns_false_when_per_agent_cap_reached(self):
        """agent at max_tasks_per_agent → can_assign False."""
        self.controller.assign("agent-001", "task-A")
        self.controller.assign("agent-001", "task-B")
        self.controller.assign("agent-001", "task-C")
        # Cap = 3, current = 3 → False
        self.assertFalse(self.controller.can_assign("agent-001"))

    def test_can_assign_per_agent_cap_isolated_across_agents(self):
        """Agent A at cap does NOT block Agent B."""
        self.controller.assign("agent-A", "task-A1")
        self.controller.assign("agent-A", "task-A2")
        self.controller.assign("agent-A", "task-A3")
        # Agent A is full, but Agent B should still be assignable
        self.assertTrue(self.controller.can_assign("agent-B"))

    def test_can_assign_returns_false_when_global_cap_reached(self):
        """total_in_flight >= max_total_tasks → can_assign False for any agent."""
        small_controller = ConcurrencyController(max_tasks_per_agent=10, max_total_tasks=2)
        small_controller.assign("agent-A", "task-1")
        small_controller.assign("agent-B", "task-2")
        # Global cap reached
        self.assertFalse(small_controller.can_assign("agent-C"))

    def test_release_decrements_agent_load(self):
        """release removes the task from the agent's in-flight set."""
        self.controller.assign("agent-001", "task-A")
        self.controller.assign("agent-001", "task-B")
        self.assertEqual(self.controller.get_agent_load("agent-001"), 2)

        self.controller.release("agent-001", "task-A")
        self.assertEqual(self.controller.get_agent_load("agent-001"), 1)
        self.assertEqual(self.controller.total_in_flight, 1)

    def test_release_unknown_pair_is_silent(self):
        """Releasing an unknown (agent, task) pair does not raise."""
        # Should not raise.
        self.controller.release("ghost-agent", "ghost-task")
        self.assertEqual(self.controller.total_in_flight, 0)

    def test_release_all_tasks_cleans_up_agent_entry(self):
        """After releasing all of an agent's tasks, the agent entry is pruned."""
        self.controller.assign("agent-001", "task-A")
        self.controller.release("agent-001", "task-A")
        # Agent dict entry should be cleaned up (total_in_flight stays 0).
        self.assertEqual(self.controller.total_in_flight, 0)
        self.assertEqual(self.controller.get_agent_load("agent-001"), 0)

    def test_release_makes_room_for_new_assignments(self):
        """After release, can_assign returns True again (slot freed)."""
        self.controller.assign("agent-001", "task-A")
        self.controller.assign("agent-001", "task-B")
        self.controller.assign("agent-001", "task-C")
        self.assertFalse(self.controller.can_assign("agent-001"))

        self.controller.release("agent-001", "task-A")
        self.assertTrue(self.controller.can_assign("agent-001"))

    def test_reset_clears_all_in_flight(self):
        """reset() wipes the controller state (used between tests)."""
        self.controller.assign("agent-001", "task-A")
        self.controller.assign("agent-002", "task-B")
        self.assertEqual(self.controller.total_in_flight, 2)

        self.controller.reset()
        self.assertEqual(self.controller.total_in_flight, 0)
        self.assertEqual(self.controller.get_agent_load("agent-001"), 0)
        self.assertEqual(self.controller.get_agent_load("agent-002"), 0)

    def test_release_empty_args_are_no_op(self):
        """release(agent_id='', task_id='') is silently ignored."""
        self.controller.assign("agent-001", "task-A")
        self.controller.release("", "task-A")
        self.controller.release("agent-001", "")
        self.assertEqual(self.controller.get_agent_load("agent-001"), 1)


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestConcurrencyWiringViaProtocolConsumer(TestCase):
    """Integration: protocol AgentConsumer + ConcurrencyController slot lifecycle.

    Acquire is wired via ``tasks.tasks.dispatch_task`` (calls controller.assign).
    Release SHOULD be wired via ``AgentConsumer._handle_task_result`` calling
    ``_release_concurrency_slot``, but spec-29c deleted that wiring (TD-267).

    These tests pin the current behavior:
      - assign() holds the slot ✓
      - _release_concurrency_slot() releases the slot ✓ (helper still works)
      - _handle_task_result does NOT release the slot ✗ (TD-267 regression)
    """

    def setUp(self):
        # Use a fresh controller instance so production singleton state does
        # not leak between tests. _release_concurrency_slot reads the default
        # controller, so we patch the module-level singleton here.
        from tasks.concurrency_controller import (
            configure_default_controller,
            get_default_controller,
        )
        self._original_controller = get_default_controller()
        self.controller = ConcurrencyController(max_tasks_per_agent=3, max_total_tasks=20)
        configure_default_controller(self.controller)

    def tearDown(self):
        from tasks.concurrency_controller import configure_default_controller
        configure_default_controller(self._original_controller)

    async def _connect_communicator(self, agent_id='test-agent-conc'):
        """Connect a WS communicator with a stubbed agent scope (drain ack).

        Args:
            agent_id: The agent_id to inject into the WS scope. Must match
                the agent_id used in controller.assign/release so the
                consumer's _release_resources_for_execution (TD-267) can
                find the right slot.
        """
        communicator = WebsocketCommunicator(
            AgentConsumer.as_asgi(), TEST_WS_PATH
        )
        communicator.scope['agent'] = MagicMock(agent_id=agent_id)
        await communicator.connect()
        await communicator.receive_from()  # drain connect ack
        return communicator

    async def _send_task_result(self, communicator, *, execution_id, success=True,
                                 elapsed_time=0.0, error_msg=""):
        payload = {
            "execution_id": str(execution_id),
            "success": success,
            "elapsed_time": elapsed_time,
            "error_msg": error_msg,
            "data": {},
        }
        frame = serialize_frame(msg_type=MessageType.TASK_RESULT, payload=payload)
        await communicator.send_to(text_data=frame)
        await asyncio.sleep(0.1)

    # --- acquire path: assign() holds slot ---

    async def test_dispatch_assign_acquires_slot(self):
        """controller.assign (the dispatch_task call) holds a slot.

        Verifies the acquire side: after we simulate what dispatch_task does
        (call controller.assign), the slot is occupied and counted in
        get_agent_load / total_in_flight.
        """
        execution = await sync_to_async(TaskExecutionFactory.create)()
        agent_id = execution.agent.agent_id

        # Simulate dispatch_task's acquire step.
        self.controller.assign(agent_id, str(execution.id))

        self.assertEqual(self.controller.get_agent_load(agent_id), 1)
        self.assertEqual(self.controller.total_in_flight, 1)
        self.assertTrue(self.controller.can_assign(agent_id))  # cap=3, load=1

    async def test_multiple_dispatches_accumulate_slots(self):
        """Two dispatches to the same agent → load=2."""
        exec1 = await sync_to_async(TaskExecutionFactory.create)()
        exec2 = await sync_to_async(TaskExecutionFactory.create)()
        # Force same agent for both executions.
        exec2.agent = exec1.agent
        await sync_to_async(exec2.save)()
        agent_id = exec1.agent.agent_id

        self.controller.assign(agent_id, str(exec1.id))
        self.controller.assign(agent_id, str(exec2.id))

        self.assertEqual(self.controller.get_agent_load(agent_id), 2)

    # --- release path: helper works, but consumer doesn't call it ---

    async def test_release_helper_releases_slot(self):
        """_release_concurrency_slot() (services.py) does release the slot.

        Proves the release helper itself works correctly. TD-267 is purely a
        wiring gap — the helper exists and works; the consumer just doesn't
        call it.
        """
        execution = await sync_to_async(TaskExecutionFactory.create)()
        agent_id = execution.agent.agent_id
        self.controller.assign(agent_id, str(execution.id))
        self.assertEqual(self.controller.get_agent_load(agent_id), 1)

        # Call the helper directly (simulating what the legacy consumer used to do).
        _release_concurrency_slot(agent_id, execution.id)

        self.assertEqual(self.controller.get_agent_load(agent_id), 0)
        self.assertEqual(self.controller.total_in_flight, 0)

    async def test_release_helper_silent_on_unassigned_slot(self):
        """_release_concurrency_slot on an un-acquired pair is silent."""
        execution = await sync_to_async(TaskExecutionFactory.create)()
        agent_id = execution.agent.agent_id

        # No assign() called — release should be silent.
        _release_concurrency_slot(agent_id, execution.id)
        self.assertEqual(self.controller.get_agent_load(agent_id), 0)

    # --- TD-267 fix verified: consumer releases slot on task.result ---

    async def test_task_result_releases_concurrency_slot(self):
        """TD-267 fixed: AgentConsumer._handle_task_result releases the slot.

        After the consumer processes a task.result frame, the slot acquired
        during dispatch_task should be released (load returns to 0).
        """
        execution = await sync_to_async(TaskExecutionFactory.create)()
        agent_id = execution.agent.agent_id

        # Simulate dispatch acquire.
        self.controller.assign(agent_id, str(execution.id))
        self.assertEqual(self.controller.get_agent_load(agent_id), 1)

        # Connect with the SAME agent_id so the consumer's
        # _release_resources_for_execution can find the slot.
        communicator = await self._connect_communicator(agent_id=agent_id)
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=True,
                elapsed_time=1.0,
            )
        finally:
            await communicator.disconnect()

        # Refresh TaskExecution to confirm the consumer DID process the frame
        # (status should be SUCCESS, proving the handler ran end-to-end).
        refreshed = await sync_to_async(TaskExecution.objects.get)(pk=execution.id)
        self.assertEqual(refreshed.status, TaskExecution.Status.SUCCESS)

        # TD-267 fix: slot is released after task.result.
        self.assertEqual(self.controller.get_agent_load(agent_id), 0)
        self.assertEqual(self.controller.total_in_flight, 0)

    async def test_task_result_failure_releases_concurrency_slot(self):
        """TD-267 fixed: failure path also releases the slot."""
        execution = await sync_to_async(TaskExecutionFactory.create)()
        agent_id = execution.agent.agent_id

        self.controller.assign(agent_id, str(execution.id))

        communicator = await self._connect_communicator(agent_id=agent_id)
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=False,
                elapsed_time=0.5,
                error_msg="image not found",
            )
        finally:
            await communicator.disconnect()

        refreshed = await sync_to_async(TaskExecution.objects.get)(pk=execution.id)
        self.assertEqual(refreshed.status, TaskExecution.Status.FAILED)

        # TD-267 fix: failed executions also release their slot.
        self.assertEqual(self.controller.get_agent_load(agent_id), 0)

    async def test_slot_no_longer_leaks_across_multiple_dispatches(self):
        """TD-267 fixed: multiple task.result frames no longer leak slots.

        Before TD-267, 3 dispatches + 3 task.results left 3 slots held,
        exhausting the per-agent cap (3). After TD-267, all 3 slots are
        released and a 4th dispatch is allowed.
        """
        execution = await sync_to_async(TaskExecutionFactory.create)()
        agent_id = execution.agent.agent_id

        # Simulate 3 dispatches + 3 task.results (release wired in consumer).
        executions = []
        for _ in range(3):
            exec_obj = await sync_to_async(TaskExecutionFactory.create)()
            exec_obj.agent = execution.agent
            await sync_to_async(exec_obj.save)()
            executions.append(exec_obj)
            self.controller.assign(agent_id, str(exec_obj.id))

        self.assertFalse(self.controller.can_assign(agent_id))  # cap=3 reached

        communicator = await self._connect_communicator(agent_id=agent_id)
        try:
            for exec_obj in executions:
                await self._send_task_result(
                    communicator,
                    execution_id=exec_obj.id,
                    success=True,
                    elapsed_time=0.1,
                )
        finally:
            await communicator.disconnect()

        # All 3 executions finished and slots released (TD-267 fix).
        # → 4th dispatch attempt is allowed (agent is idle again).
        self.assertEqual(self.controller.get_agent_load(agent_id), 0)
        self.assertTrue(self.controller.can_assign(agent_id))

    # --- manual release still works (defensive, even though consumer now releases) ---

    async def test_manual_release_recovers_from_leak(self):
        """Calling _release_concurrency_slot after task.result is a safe no-op.

        Defensive test: the consumer now releases internally (TD-267 fix),
        so calling _release_concurrency_slot manually afterward is a
        redundant no-op (release on already-released pair is silent).
        """
        execution = await sync_to_async(TaskExecutionFactory.create)()
        agent_id = execution.agent.agent_id

        self.controller.assign(agent_id, str(execution.id))

        communicator = await self._connect_communicator(agent_id=agent_id)
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=True,
                elapsed_time=1.0,
            )
        finally:
            await communicator.disconnect()

        # Slot already released by consumer (TD-267 fix).
        self.assertEqual(self.controller.get_agent_load(agent_id), 0)

        # Manual release is a silent no-op (idempotent).
        _release_concurrency_slot(agent_id, execution.id)
        self.assertEqual(self.controller.get_agent_load(agent_id), 0)
        self.assertTrue(self.controller.can_assign(agent_id))


# =============================================================================
# Source: test_device_status_lifecycle_via_protocol_consumer.py
# =============================================================================


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TestDeviceStatusLifecycleViaProtocolConsumer(TestCase):
    """End-to-end Device.status lifecycle coverage for AgentConsumer._handle_task_result."""

    async def _connect_communicator(self):
        """Connect a WS communicator with a stubbed agent scope (drain ack)."""
        communicator = WebsocketCommunicator(
            AgentConsumer.as_asgi(), TEST_WS_PATH
        )
        communicator.scope['agent'] = MagicMock(agent_id='test-agent-device')
        await communicator.connect()
        await communicator.receive_from()  # drain connect ack
        return communicator

    async def _send_task_result(self, communicator, *, execution_id, success=True,
                                 elapsed_time=0.0, error_msg=""):
        payload = {
            "execution_id": str(execution_id),
            "success": success,
            "elapsed_time": elapsed_time,
            "error_msg": error_msg,
            "data": {},
        }
        frame = serialize_frame(msg_type=MessageType.TASK_RESULT, payload=payload)
        await communicator.send_to(text_data=frame)
        await asyncio.sleep(0.1)

    async def _reload_device(self, device):
        return await sync_to_async(Device.objects.get)(pk=device.id)

    async def _reload_execution(self, execution):
        return await sync_to_async(TaskExecution.objects.get)(pk=execution.id)

    async def _mark_device_busy(self, device):
        """Simulate what dispatch_task does: flip Device.status → BUSY."""
        await sync_to_async(Device.objects.filter(id=device.id).update)(
            status=Device.Status.BUSY
        )

    # --- acquire path: dispatch marks device BUSY ---

    async def test_device_starts_online(self):
        """Sanity check: DeviceFactory default status is ONLINE."""
        device = await sync_to_async(DeviceFactory.create)()
        self.assertEqual(device.status, Device.Status.ONLINE)

    async def test_dispatch_simulated_marks_device_busy(self):
        """Simulated dispatch (DB update) flips Device.status ONLINE → BUSY.

        Verifies the acquire path mechanics: dispatch_task's
        ``Device.objects.filter(id=...).update(status=BUSY)`` line. We
        replicate the update directly (without going through dispatch_task)
        so the test stays focused on Device.status transitions.
        """
        device = await sync_to_async(DeviceFactory.create)(status=Device.Status.ONLINE)
        await self._mark_device_busy(device)

        refreshed = await self._reload_device(device)
        self.assertEqual(refreshed.status, Device.Status.BUSY)

    # --- TD-267 fix verified: consumer restores Device.status on task.result ---

    async def test_task_result_restores_device_status(self):
        """TD-267 fixed: AgentConsumer._handle_task_result restores Device.status to ONLINE.

        After the consumer processes a task.result frame, the device that
        was marked BUSY during dispatch should be restored to ONLINE.
        """
        device = await sync_to_async(DeviceFactory.create)(status=Device.Status.BUSY)
        execution = await sync_to_async(TaskExecutionFactory.create)(device=device)

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

        # Sanity: the consumer DID process the frame (TaskExecution is SUCCESS).
        refreshed_exec = await self._reload_execution(execution)
        self.assertEqual(refreshed_exec.status, TaskExecution.Status.SUCCESS)

        # TD-267 fix: Device.status is restored to ONLINE.
        refreshed_device = await self._reload_device(device)
        self.assertEqual(refreshed_device.status, Device.Status.ONLINE)

    async def test_task_result_failure_restores_device_status(self):
        """TD-267 fixed: failure path also restores Device.status."""
        device = await sync_to_async(DeviceFactory.create)(status=Device.Status.BUSY)
        execution = await sync_to_async(TaskExecutionFactory.create)(device=device)

        communicator = await self._connect_communicator()
        try:
            await self._send_task_result(
                communicator,
                execution_id=execution.id,
                success=False,
                elapsed_time=0.5,
                error_msg="boom",
            )
        finally:
            await communicator.disconnect()

        refreshed_exec = await self._reload_execution(execution)
        self.assertEqual(refreshed_exec.status, TaskExecution.Status.FAILED)

        # TD-267 fix: failed executions also restore Device.status to ONLINE.
        refreshed_device = await self._reload_device(device)
        self.assertEqual(refreshed_device.status, Device.Status.ONLINE)

    # --- _restore_device_status helper works (TD-267 is wiring gap only) ---

    async def test_restore_device_status_helper_restores_online(self):
        """_restore_device_status() (services.py) DOES restore Device.status.

        Proves the restore helper itself works correctly. TD-267 is purely a
        wiring gap — the helper exists and works; the consumer just doesn't
        call it. Wrapped in sync_to_async because the helper is a sync ORM
        caller and pytest-asyncio runs the test inside an event loop.
        """
        device = await sync_to_async(DeviceFactory.create)(status=Device.Status.BUSY)
        execution = await sync_to_async(TaskExecutionFactory.create)(
            device=device,
            status=TaskExecution.Status.SUCCESS,
        )

        await sync_to_async(_restore_device_status)(execution)

        refreshed = await self._reload_device(device)
        self.assertEqual(refreshed.status, Device.Status.ONLINE)

    async def test_restore_device_status_helper_silent_on_no_device(self):
        """_restore_device_status(execution with device=None) is a no-op.

        Legacy executions may not have a device FK. The helper must handle
        this gracefully (silently return) rather than raise.
        """
        # Create execution without device
        execution = await sync_to_async(TaskExecutionFactory.create)(device=None)
        # Should not raise.
        await sync_to_async(_restore_device_status)(execution)

    async def test_restore_device_status_helper_silent_on_none_execution(self):
        """_restore_device_status(None) is a no-op (defensive guard)."""
        # Should not raise.
        await sync_to_async(_restore_device_status)(None)

    async def test_restore_device_status_multi_instance_aware(self):
        """Multi-instance: if another RUNNING execution shares the device,
        the device stays BUSY even after one execution finishes.

        _restore_device_status filters for other RUNNING executions on the
        same device and only restores ONLINE when none exist. This lets two
        tasks target different devices on the same agent without one
        completion clobbering the other device's BUSY state.
        """
        device = await sync_to_async(DeviceFactory.create)(status=Device.Status.BUSY)
        # First execution: finished (SUCCESS)
        finished_exec = await sync_to_async(TaskExecutionFactory.create)(
            device=device,
            status=TaskExecution.Status.SUCCESS,
        )
        # Second execution: still RUNNING on the same device
        running_exec = await sync_to_async(TaskExecutionFactory.create)(
            device=device,
            status=TaskExecution.Status.RUNNING,
        )

        await sync_to_async(_restore_device_status)(finished_exec)

        # Device should still be BUSY because running_exec shares the device.
        refreshed = await self._reload_device(device)
        self.assertEqual(refreshed.status, Device.Status.BUSY)

        # Now finalize the second execution and call restore again.
        running_exec.status = TaskExecution.Status.SUCCESS
        await sync_to_async(running_exec.save)()
        await sync_to_async(_restore_device_status)(running_exec)

        # Now the device should be ONLINE.
        refreshed = await self._reload_device(device)
        self.assertEqual(refreshed.status, Device.Status.ONLINE)

    async def test_restore_device_status_only_flips_busy_to_online(self):
        """Device in ERROR state is NOT auto-restored to ONLINE.

        The helper's filter includes ``status=Device.Status.BUSY`` so a
        device in ERROR (operator-set, or platform-detected fault) is
        preserved across execution completion.
        """
        device = await sync_to_async(DeviceFactory.create)(status=Device.Status.ERROR)
        execution = await sync_to_async(TaskExecutionFactory.create)(
            device=device,
            status=TaskExecution.Status.SUCCESS,
        )

        await sync_to_async(_restore_device_status)(execution)

        refreshed = await self._reload_device(device)
        # ERROR state preserved (helper only flips BUSY → ONLINE).
        self.assertEqual(refreshed.status, Device.Status.ERROR)

    # --- _restore_device_status_by_msg wrapper ---

    async def test_restore_device_status_by_msg_restores_online(self):
        """_restore_device_status_by_msg(payload) restores Device.status.

        Verifies the message-payload wrapper used by the legacy consumer's
        task.completed / task.failed handlers. Loads the execution by id
        and delegates to _restore_device_status.
        """
        device = await sync_to_async(DeviceFactory.create)(status=Device.Status.BUSY)
        execution = await sync_to_async(TaskExecutionFactory.create)(
            device=device,
            status=TaskExecution.Status.SUCCESS,
        )

        await sync_to_async(_restore_device_status_by_msg)(
            {"execution_id": str(execution.id)}
        )

        refreshed = await self._reload_device(device)
        self.assertEqual(refreshed.status, Device.Status.ONLINE)

    async def test_restore_device_status_by_msg_missing_execution_id_silent(self):
        """_restore_device_status_by_msg({}) with no execution_id is a no-op."""
        # Should not raise.
        await sync_to_async(_restore_device_status_by_msg)({})

    async def test_restore_device_status_by_msg_unknown_execution_silent(self):
        """_restore_device_status_by_msg with unknown execution_id is a no-op."""
        # Should not raise.
        await sync_to_async(_restore_device_status_by_msg)(
            {"execution_id": "00000000-0000-0000-0000-000000000000"}
        )

    # --- manual restore still works (defensive, even though consumer now restores) ---

    async def test_manual_restore_recovers_from_leak(self):
        """Calling _restore_device_status after task.result is a safe no-op.

        Defensive test: the consumer now restores internally (TD-267 fix),
        so calling _restore_device_status manually afterward is a redundant
        no-op (device is already ONLINE; helper is multi-instance aware
        and silently no-ops when no other RUNNING execution exists).
        """
        device = await sync_to_async(DeviceFactory.create)(status=Device.Status.BUSY)
        execution = await sync_to_async(TaskExecutionFactory.create)(device=device)

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

        # Device already restored by consumer (TD-267 fix).
        already_online = await self._reload_device(device)
        self.assertEqual(already_online.status, Device.Status.ONLINE)

        # Manual restore is a silent no-op (device already ONLINE, no
        # other RUNNING execution on this device).
        refreshed_exec = await self._reload_execution(execution)
        await sync_to_async(_restore_device_status)(refreshed_exec)

        restored = await self._reload_device(device)
        self.assertEqual(restored.status, Device.Status.ONLINE)
