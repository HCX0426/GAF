"""Tests for the unified device identity resolver (OQ-9 / F-10 spec).

Verifies the P-1/P-2/P-3 contracts:
  - The same physical device resolves to one Device record no matter which
    writer (agent device.sync vs HTTP register) touched it first;
  - agent sync fills base fields but never overwrites a user-saved name;
  - agent sync creates records under the ``emulator_brand`` field (the
    ``emulator`` fallback in legacy payloads must not raise).
"""

from django.test import TestCase

from protocol.services import register_agent_device
from workers.models import Device, Worker
from workers.services.device_identity import find_device_by_identity


class DeviceIdentityTests(TestCase):
    def setUp(self):
        self.worker = Worker.objects.create(
            agent_id="agent-sync-1",
            hostname="sync-worker",
            status=Worker.Status.ONLINE,
        )

    def _sync_device(self, **overrides):
        data = {
            "device_id": "adb-emu-abc123",
            "name": "LDPlayer-5555",
            "device_type": "emulator",
            "status": "online",
            "adb_serial": "127.0.0.1:5555",
            "emulator": "ldplayer",
        }
        data.update(overrides)
        return register_agent_device(self.worker.agent_id, data)

    def test_sync_and_identity_resolver_share_one_record(self):
        """P-1: identity resolver (HTTP register path) finds the device the
        agent sync created — no duplicate under different keys."""
        result = self._sync_device()
        self.assertTrue(result["created"])

        # The HTTP register path resolves the same physical device.
        device = find_device_by_identity(
            "emulator",
            hwnd="",
            adb_serial="127.0.0.1:5555",
            emulator_brand="ldplayer",
            window_title="",
            name="LDPlayer-5555",
            agent=self.worker,
        )
        self.assertIsNotNone(device)
        self.assertEqual(device.id, result["id"])
        self.assertEqual(Device.objects.count(), 1)

        # Re-syncing the same serial updates, never creates a duplicate.
        result2 = self._sync_device(name="LDPlayer-5555-v2")
        self.assertFalse(result2["created"])
        self.assertEqual(result2["id"], result["id"])
        self.assertEqual(Device.objects.count(), 1)

    def test_sync_does_not_overwrite_user_saved_name(self):
        """P-3: base-fill on sync keeps a user-saved name intact."""
        device = Device.objects.create(
            name="用户自定义名称",
            device_type=Device.DeviceType.EMULATOR,
            status=Device.Status.OFFLINE,
            adb_serial="127.0.0.1:5555",
        )
        # Agent reports a different display name — must NOT overwrite.
        result = self._sync_device(name="LDPlayer-5555")
        self.assertFalse(result["created"])
        device.refresh_from_db()
        self.assertEqual(device.name, "用户自定义名称")
        # Base lifecycle fields are still filled.
        self.assertEqual(device.status, Device.Status.ONLINE)

    def test_sync_uses_emulator_brand_field(self):
        """Legacy payload carries 'emulator' — stored in emulator_brand (C 批
        field rename), and no KeyError/TypeError leaks from update path."""
        result = self._sync_device()
        device = Device.objects.get(pk=result["id"])
        self.assertEqual(device.emulator_brand, "ldplayer")

        # Parallel manual registration fills the same field on create.
        device2 = find_device_by_identity(
            "emulator",
            adb_serial="127.0.0.1:7777",
            emulator_brand="mumu",
            name="MuMu-1",
            agent=self.worker,
        )
        self.assertIsNone(device2)

    def test_windows_identity_by_hwnd_then_title(self):
        """Windows devices resolve by hwnd first, then by window title."""
        result = register_agent_device(self.worker.agent_id, {
            "device_id": "windows-0",
            "name": "BlueArchive",
            "device_type": "windows",
            "status": "online",
            "window_handle": "0xabc",
        })
        self.assertTrue(result["created"])

        # Same hwnd resolves to the same record.
        device = find_device_by_identity(
            "windows",
            hwnd="0xabc",
            window_title="BlueArchive",
            name="BlueArchive",
            agent=self.worker,
        )
        self.assertEqual(device.id, result["id"])

        # A stale hwnd with the same window title still resolves via title.
        device2 = find_device_by_identity(
            "windows",
            hwnd="0xdef",
            window_title="BlueArchive",
            name="BlueArchive",
            agent=self.worker,
        )
        self.assertEqual(device2.id, result["id"])
        self.assertEqual(Device.objects.count(), 1)
