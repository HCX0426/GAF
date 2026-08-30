"""Unit tests for per-device screenshot stream control (TD-014).

Covers `WorkerConsumer._map_db_device_ids_to_agent` which translates DB
Device.id values to agent-side device_id strings. Frontend sends DB ids;
the agent expects strings like "windows-hwnd-{hwnd}", "windows-title-{name}",
or str(device.id) for emulators.
"""

from django.test import TestCase
from workers.models import Device, Worker

from protocol.consumers import WorkerConsumer


class TestMapDbDeviceIdsToAgent(TestCase):
    """Verify DB Device.id -> agent device_id string translation (TD-014)."""

    async def _make_consumer(self, agent_id: str | None) -> WorkerConsumer:
        consumer = WorkerConsumer()
        consumer.agent_id = agent_id
        return consumer

    async def test_no_agent_id_returns_none(self):
        """Consumer without agent_id (pre-register) returns None."""
        consumer = await self._make_consumer(None)
        result = await consumer._map_db_device_ids_to_agent([1, 2])
        self.assertIsNone(result)

    async def test_unknown_agent_returns_none(self):
        """Agent row missing from DB returns None."""
        consumer = await self._make_consumer("ghost-agent-id")
        result = await consumer._map_db_device_ids_to_agent([1])
        self.assertIsNone(result)

    async def test_empty_input_returns_none(self):
        """Empty device_ids list returns None (means all devices)."""
        agent = await self._create_agent("agent-td014-empty")
        consumer = await self._make_consumer(agent.agent_id)
        result = await consumer._map_db_device_ids_to_agent([])
        self.assertIsNone(result)

    async def test_invalid_ids_skipped(self):
        """Non-numeric ids are skipped silently."""
        agent = await self._create_agent("agent-td014-invalid")
        await self._create_device(agent, "win-with-hwnd", Device.DeviceType.WINDOWS, window_handle="67890")
        consumer = await self._make_consumer(agent.agent_id)
        # Invalid ids + a valid id that doesn't exist -> None (no match)
        result = await consumer._map_db_device_ids_to_agent(["abc", "def", "999"])
        self.assertIsNone(result)

    async def test_windows_with_handle(self):
        """Windows device with window_handle -> "windows-hwnd-{hwnd}"."""
        agent = await self._create_agent("agent-td014-win-hwnd")
        dev = await self._create_device(agent, "GameWin", Device.DeviceType.WINDOWS, window_handle="12345")
        consumer = await self._make_consumer(agent.agent_id)
        result = await consumer._map_db_device_ids_to_agent([dev.id])
        self.assertEqual(result, ["windows-hwnd-12345"])

    async def test_windows_without_handle_uses_name(self):
        """Windows device without window_handle -> "windows-title-{name}"."""
        agent = await self._create_agent("agent-td014-win-title")
        dev = await self._create_device(agent, "MyGameWindow", Device.DeviceType.WINDOWS, window_handle="")
        consumer = await self._make_consumer(agent.agent_id)
        result = await consumer._map_db_device_ids_to_agent([dev.id])
        self.assertEqual(result, ["windows-title-MyGameWindow"])

    async def test_emulator_uses_id_string(self):
        """Emulator device -> str(device.id)."""
        agent = await self._create_agent("agent-td014-emu")
        dev = await self._create_device(agent, "LDPlayer", Device.DeviceType.EMULATOR)
        consumer = await self._make_consumer(agent.agent_id)
        result = await consumer._map_db_device_ids_to_agent([dev.id])
        self.assertEqual(result, [str(dev.id)])

    async def test_mixed_devices(self):
        """A mix of Windows+handle, Windows-no-handle, and emulator devices."""
        agent = await self._create_agent("agent-td014-mixed")
        dev_win_hwnd = await self._create_device(agent, "WinA", Device.DeviceType.WINDOWS, window_handle="100")
        dev_win_title = await self._create_device(agent, "WinB", Device.DeviceType.WINDOWS, window_handle="")
        dev_emu = await self._create_device(agent, "EmuC", Device.DeviceType.EMULATOR)
        consumer = await self._make_consumer(agent.agent_id)
        result = await consumer._map_db_device_ids_to_agent(
            [dev_win_hwnd.id, dev_win_title.id, dev_emu.id]
        )
        # Order is not guaranteed by id__in; compare as sets.
        self.assertEqual(
            set(result),
            {
                "windows-hwnd-100",
                "windows-title-WinB",
                str(dev_emu.id),
            },
        )

    async def test_string_numeric_ids_accepted(self):
        """Frontend may send ids as strings; they should be parsed."""
        agent = await self._create_agent("agent-td014-str")
        dev = await self._create_device(agent, "WinStr", Device.DeviceType.WINDOWS, window_handle="555")
        consumer = await self._make_consumer(agent.agent_id)
        result = await consumer._map_db_device_ids_to_agent([str(dev.id)])
        self.assertEqual(result, ["windows-hwnd-555"])

    async def test_ids_from_other_agent_excluded(self):
        """Devices belonging to a different agent are not matched."""
        agent_a = await self._create_agent("agent-td014-a")
        agent_b = await self._create_agent("agent-td014-b")
        dev_a = await self._create_device(agent_a, "WinA", Device.DeviceType.WINDOWS, window_handle="111")
        await self._create_device(agent_b, "WinB", Device.DeviceType.WINDOWS, window_handle="222")
        consumer = await self._make_consumer(agent_a.agent_id)
        # Pass both ids but only agent_a's device should match.
        result = await consumer._map_db_device_ids_to_agent([dev_a.id, 99999])
        self.assertEqual(result, ["windows-hwnd-111"])

    # --- helpers ---

    async def _create_agent(self, agent_id: str) -> Worker:
        from asgiref.sync import sync_to_async

        return await sync_to_async(Worker.objects.create)(
            agent_id=agent_id,
            hostname="test-host",
            status=Worker.Status.ONLINE,
        )

    async def _create_device(
        self,
        agent: Worker,
        name: str,
        device_type: str,
        window_handle: str = "",
    ) -> Device:
        from asgiref.sync import sync_to_async

        return await sync_to_async(Device.objects.create)(
            agent=agent,
            name=name,
            device_type=device_type,
            window_handle=window_handle,
        )
