"""DeviceManager unit tests.

Focuses on DeviceManager core paths not already covered by
``test_device_abstraction.py::TestDeviceManager``: initial state,
``get_active_device_id`` (used for multi-device concurrency restore),
edge cases around removal and active-device fallback.
"""

from unittest.mock import MagicMock

import pytest
from devices.base import BaseDevice, DeviceStatus
from devices.manager import DeviceManager

pytestmark = pytest.mark.unit


class _StubDevice(BaseDevice):
    """Minimal BaseDevice implementation for manager-level tests."""

    def __init__(self, device_id: str = "", name: str = ""):
        super().__init__(device_id=device_id, name=name)
        # Concrete mock to verify disconnect() calls during remove_device
        self.disconnect_mock = MagicMock()

    def connect(self) -> None:  # pragma: no cover - not exercised here
        self._status = DeviceStatus.CONNECTED

    def disconnect(self) -> None:
        self.disconnect_mock()

    def capture_screen(self):  # pragma: no cover - not exercised here
        return None

    def click(self, x: int, y: int) -> None:  # pragma: no cover
        pass

    def key_press(self, key: str) -> None:  # pragma: no cover
        pass

    def text_input(self, text: str) -> None:  # pragma: no cover
        pass

    def swipe(self, x1, y1, x2, y2, duration: int = 300) -> None:  # pragma: no cover
        pass

    def get_resolution(self):  # pragma: no cover
        return (1920, 1080)


@pytest.fixture
def manager():
    """Fresh DeviceManager instance per test."""
    return DeviceManager()


class TestDeviceManagerInitialState:
    """Verify empty-manager initial state."""

    def test_initial_device_count_is_zero(self, manager):
        assert manager.device_count == 0

    def test_initial_active_device_is_none(self, manager):
        assert manager.get_active_device() is None

    def test_initial_active_device_id_is_none(self, manager):
        # get_active_device_id() drives multi-device concurrency restore
        assert manager.get_active_device_id() is None

    def test_list_devices_empty(self, manager):
        assert manager.list_devices() == []


class TestDeviceManagerAddAndActiveId:
    """Verify add_device side effects on active device tracking."""

    def test_first_added_device_becomes_active(self, manager):
        d1 = _StubDevice(device_id="d1", name="Device 1")
        manager.add_device(d1)
        assert manager.get_active_device_id() == "d1"
        assert manager.get_active_device() is d1

    def test_second_device_does_not_override_active(self, manager):
        d1 = _StubDevice(device_id="d1")
        d2 = _StubDevice(device_id="d2")
        manager.add_device(d1)
        manager.add_device(d2)
        # Active stays on first device; d2 is registered but not active
        assert manager.get_active_device_id() == "d1"
        assert manager.device_count == 2


class TestDeviceManagerRemove:
    """Verify removal semantics including active-device fallback."""

    def test_remove_nonexistent_is_noop(self, manager):
        # Removing an unknown id must not raise and must not change state
        manager.remove_device("nonexistent")
        assert manager.device_count == 0
        assert manager.get_active_device_id() is None

    def test_remove_calls_disconnect(self, manager):
        d1 = _StubDevice(device_id="d1")
        manager.add_device(d1)
        manager.remove_device("d1")
        d1.disconnect_mock.assert_called_once()

    def test_remove_last_device_clears_active(self, manager):
        d1 = _StubDevice(device_id="d1")
        manager.add_device(d1)
        manager.remove_device("d1")
        # After removing the only device, no active device is selected
        assert manager.device_count == 0
        assert manager.get_active_device() is None
        assert manager.get_active_device_id() is None

    def test_remove_active_falls_back_to_remaining(self, manager):
        d1 = _StubDevice(device_id="d1")
        d2 = _StubDevice(device_id="d2")
        manager.add_device(d1)
        manager.add_device(d2)
        # Active is d1; removing d1 should fall back to d2 (next iter)
        manager.remove_device("d1")
        assert manager.get_active_device() is d2
        assert manager.get_active_device_id() == "d2"


class TestDeviceManagerSetActive:
    """Verify set_active_device return values and edge cases."""

    def test_set_active_on_empty_returns_false(self, manager):
        assert manager.set_active_device("anything") is False
        assert manager.get_active_device_id() is None

    def test_set_active_unknown_id_returns_false(self, manager):
        d1 = _StubDevice(device_id="d1")
        manager.add_device(d1)
        # Unknown id: state unchanged, returns False
        assert manager.set_active_device("nope") is False
        assert manager.get_active_device_id() == "d1"


class TestDeviceManagerListDevices:
    """Verify list_devices payload shape."""

    def test_list_devices_multiple(self, manager):
        d1 = _StubDevice(device_id="d1", name="First")
        d2 = _StubDevice(device_id="d2", name="Second")
        manager.add_device(d1)
        manager.add_device(d2)
        listed = manager.list_devices()
        assert len(listed) == 2
        ids = {entry["device_id"] for entry in listed}
        assert ids == {"d1", "d2"}
        # Each entry must expose id/name/status fields (status is enum value)
        for entry in listed:
            assert "name" in entry
            assert "status" in entry
            assert entry["status"] == DeviceStatus.DISCONNECTED.value
