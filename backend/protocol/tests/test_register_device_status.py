"""Test that register_agent_device honors the status the agent reports.

When an ADB/emulator device disappears, the agent pushes device.sync with
status="offline". The backend must persist that instead of re-forcing
ONLINE, otherwise an offline device can never leave the "online" state.

Regression: an online-but-absent LDPlayer record stayed online forever
because register_agent_device hard-coded Device.Status.ONLINE.
"""

import pytest
from django.test import TestCase
from workers.factories import WorkerFactory
from workers.models import Device

from protocol.services import register_agent_device

pytestmark = pytest.mark.e2e


class TestRegisterAgentDeviceStatus(TestCase):
    def setUp(self):
        self.agent = WorkerFactory()

    def test_offline_status_is_respected(self):
        result = register_agent_device(
            self.agent.agent_id,
            {
                "device_id": "adb-ldplayer-0001",
                "name": "LDPlayer",
                "device_type": "emulator",
                "status": "offline",
                "adb_serial": "127.0.0.1:5555",
            },
        )
        self.assertTrue(result["created"])
        device = Device.objects.get(pk=result["id"])
        self.assertEqual(device.status, Device.Status.OFFLINE)

    def test_online_status_is_respected(self):
        result = register_agent_device(
            self.agent.agent_id,
            {
                "device_id": "adb-ldplayer-0002",
                "name": "LDPlayer2",
                "device_type": "emulator",
                "status": "online",
                "adb_serial": "127.0.0.1:5556",
            },
        )
        device = Device.objects.get(pk=result["id"])
        self.assertEqual(device.status, Device.Status.ONLINE)

    def test_invalid_status_falls_back_to_online(self):
        result = register_agent_device(
            self.agent.agent_id,
            {
                "device_id": "adb-ldplayer-0003",
                "name": "LDPlayer3",
                "device_type": "emulator",
                "status": "weird",
                "adb_serial": "127.0.0.1:5557",
            },
        )
        device = Device.objects.get(pk=result["id"])
        self.assertEqual(device.status, Device.Status.ONLINE)
