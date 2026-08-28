"""Tests for TD-123: dynamic port allocation for minitouch/MaaTouch.

Verifies:
- `_allocate_port` returns stable ports for the same serial (CRC32 hash).
- Different serials get different ports (no collision in practice).
- Occupied ports are skipped via linear probe.
- Allocated ports are in the configured high range.
- Port allocation is thread-safe.
- `_input_by_minitouch` / `_input_by_maatouch` no longer hardcode 1111/1313.
"""

from __future__ import annotations

import socket
import threading
from unittest.mock import patch

import pytest

from device_bridge.platforms.windows._adb_input import (
    _MAATOUCH_PORT_BASE,
    _MAATOUCH_PORT_RANGE,
    _MINITOUCH_PORT_BASE,
    _MINITOUCH_PORT_RANGE,
    _PORT_REGISTRY,
    _allocate_port,
)


@pytest.fixture(autouse=True)
def _clear_port_registry():
    """Reset the port registry between tests for isolation."""
    _PORT_REGISTRY.clear()
    yield
    _PORT_REGISTRY.clear()


class TestAllocatePortStability:
    """Same serial must always get the same port."""

    def test_allocate_port_returns_same_port_for_same_serial_minitouch(self):
        port1 = _allocate_port("emulator-5554", "minitouch")
        port2 = _allocate_port("emulator-5554", "minitouch")
        assert port1 == port2

    def test_allocate_port_returns_same_port_for_same_serial_maatouch(self):
        port1 = _allocate_port("emulator-5554", "maatouch")
        port2 = _allocate_port("emulator-5554", "maatouch")
        assert port1 == port2

    def test_allocate_port_minitouch_and_maatouch_independent(self):
        """A serial's minitouch port and maatouch port are independent."""
        p_mini = _allocate_port("emulator-5554", "minitouch")
        p_maa = _allocate_port("emulator-5554", "maatouch")
        # They live in different ranges, so must differ.
        assert p_mini != p_maa


class TestAllocatePortRange:
    """Allocated ports must be in the configured high range."""

    def test_minitouch_port_in_range(self):
        port = _allocate_port("emulator-5554", "minitouch")
        assert _MINITOUCH_PORT_BASE <= port < _MINITOUCH_PORT_BASE + _MINITOUCH_PORT_RANGE

    def test_maatouch_port_in_range(self):
        port = _allocate_port("emulator-5554", "maatouch")
        assert _MAATOUCH_PORT_BASE <= port < _MAATOUCH_PORT_BASE + _MAATOUCH_PORT_RANGE

    def test_minitouch_port_not_legacy_1111(self):
        """TD-123: port must NOT be the legacy hardcoded 1111."""
        port = _allocate_port("emulator-5554", "minitouch")
        assert port != 1111

    def test_maatouch_port_not_legacy_1313(self):
        """TD-123: port must NOT be the legacy hardcoded 1313."""
        port = _allocate_port("emulator-5554", "maatouch")
        assert port != 1313


class TestAllocatePortDifferentSerials:
    """Different serials should usually get different ports."""

    def test_different_serials_get_different_ports(self):
        """Two different serials should hash to different ports in practice.

        Note: hash collisions are theoretically possible, but for two
        arbitrary serials the CRC32 % 500 should differ.
        """
        port1 = _allocate_port("emulator-5554", "minitouch")
        port2 = _allocate_port("emulator-5556", "minitouch")
        assert port1 != port2

    def test_many_serials_all_in_range(self):
        """Allocate ports for 50 different serials, all must be in range."""
        for i in range(50):
            serial = f"emulator-{5554 + i * 2}"
            port = _allocate_port(serial, "minitouch")
            assert _MINITOUCH_PORT_BASE <= port < _MINITOUCH_PORT_BASE + _MINITOUCH_PORT_RANGE


class TestAllocatePortSkipsOccupied:
    """When the preferred port is occupied, linear probe to the next."""

    def test_allocate_port_skips_occupied_port(self):
        """Pre-occupy the preferred port, verify allocation moves to next."""
        serial = "emulator-5554"
        # Compute preferred port without allocating (peek at the hash).
        import zlib

        preferred = _MINITOUCH_PORT_BASE + (
            zlib.crc32(serial.encode("utf-8")) % _MINITOUCH_PORT_RANGE
        )

        # Bind the preferred port to make it unavailable.
        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            blocker.bind(("127.0.0.1", preferred))
            blocker.listen(1)

            allocated = _allocate_port(serial, "minitouch")
            assert allocated != preferred
            assert _MINITOUCH_PORT_BASE <= allocated < _MINITOUCH_PORT_BASE + _MINITOUCH_PORT_RANGE
        finally:
            blocker.close()

    def test_allocate_port_skips_multiple_occupied(self):
        """Pre-occupy preferred and next, verify allocation skips both."""
        serial = "emulator-5554"
        import zlib

        preferred = _MINITOUCH_PORT_BASE + (
            zlib.crc32(serial.encode("utf-8")) % _MINITOUCH_PORT_RANGE
        )
        next_port = preferred + 1 if preferred + 1 < _MINITOUCH_PORT_BASE + _MINITOUCH_PORT_RANGE else _MINITOUCH_PORT_BASE

        b1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        b2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            b1.bind(("127.0.0.1", preferred))
            b1.listen(1)
            b2.bind(("127.0.0.1", next_port))
            b2.listen(1)

            allocated = _allocate_port(serial, "minitouch")
            assert allocated not in (preferred, next_port)
        finally:
            b1.close()
            b2.close()


class TestAllocatePortThreadSafety:
    """Concurrent calls from multiple threads must not corrupt the registry."""

    def test_concurrent_allocate_same_serial(self):
        """20 threads concurrently allocate port for the same serial.

        All must return the same port (no double-allocation).
        """
        serial = "emulator-9999"
        results: list[int] = []
        results_lock = threading.Lock()

        def worker():
            port = _allocate_port(serial, "minitouch")
            with results_lock:
                results.append(port)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert len(results) == 20
        # All threads got the same port.
        assert len(set(results)) == 1, f"Got multiple ports: {set(results)}"

    def test_concurrent_allocate_different_serials(self):
        """20 threads with 20 different serials, all must succeed."""
        results: list[int] = []
        results_lock = threading.Lock()

        def worker(i):
            port = _allocate_port(f"emulator-{8000 + i}", "minitouch")
            with results_lock:
                results.append(port)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert len(results) == 20
        # All ports in range.
        for p in results:
            assert _MINITOUCH_PORT_BASE <= p < _MINITOUCH_PORT_BASE + _MINITOUCH_PORT_RANGE


class TestAllocatePortValidation:
    """Invalid inputs must raise."""

    def test_unknown_kind_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown port kind"):
            _allocate_port("emulator-5554", "scrcpy")


class TestMinitouchUsesDynamicPort:
    """_input_by_minitouch must call _allocate_port instead of hardcoding 1111."""

    @patch("device_bridge.platforms.windows._adb_input._ensure_minitouch_running", return_value=True)
    @patch("device_bridge.platforms.windows._adb_input.socket")
    @patch("device_bridge.platforms.windows._adb_input._allocate_port")
    def test_minitouch_calls_allocate_port(
        self, mock_alloc, mock_socket, mock_ensure
    ):
        from device_bridge.platforms.windows._adb_input import _input_by_minitouch

        mock_alloc.return_value = 12345

        _input_by_minitouch("emulator-5554", "adb", "click", x=10, y=20)

        mock_alloc.assert_called_once_with("emulator-5554", "minitouch")
        mock_socket.socket.return_value.connect.assert_called_once_with(("127.0.0.1", 12345))

    @patch("device_bridge.platforms.windows._adb_input._ensure_minitouch_running", return_value=True)
    @patch("device_bridge.platforms.windows._adb_input.socket")
    def test_minitouch_does_not_use_1111(self, mock_socket, mock_ensure):
        """End-to-end: port must not be 1111 (legacy hardcoded value)."""
        from device_bridge.platforms.windows._adb_input import _input_by_minitouch

        _input_by_minitouch("emulator-5554", "adb", "click", x=10, y=20)

        # Inspect the port passed to connect.
        connect_args = mock_socket.socket.return_value.connect.call_args
        port = connect_args.args[0][1]
        assert port != 1111
        assert port != 1313  # not maatouch's legacy either


class TestMaatouchUsesDynamicPort:
    """_input_by_maatouch must call _allocate_port instead of hardcoding 1313."""

    @patch("device_bridge.platforms.windows._adb_input.subprocess")
    @patch("device_bridge.platforms.windows._adb_input.socket")
    @patch("device_bridge.platforms.windows._adb_input._allocate_port")
    def test_maatouch_calls_allocate_port(
        self, mock_alloc, mock_socket, mock_subprocess
    ):
        from device_bridge.platforms.windows._adb_input import _input_by_maatouch

        mock_alloc.return_value = 13579
        mock_subprocess.run.return_value.stdout = "tcp:13579"

        _input_by_maatouch("emulator-5554", "adb", "click", x=10, y=20)

        mock_alloc.assert_called_once_with("emulator-5554", "maatouch")
        mock_socket.socket.return_value.connect.assert_called_once_with(("127.0.0.1", 13579))

    @patch("device_bridge.platforms.windows._adb_input.subprocess")
    @patch("device_bridge.platforms.windows._adb_input.socket")
    def test_maatouch_does_not_use_1313(self, mock_socket, mock_subprocess):
        """End-to-end: port must not be 1313 (legacy hardcoded value)."""
        from device_bridge.platforms.windows._adb_input import _input_by_maatouch

        mock_subprocess.run.return_value.stdout = ""

        _input_by_maatouch("emulator-5554", "adb", "click", x=10, y=20)

        connect_args = mock_socket.socket.return_value.connect.call_args
        port = connect_args.args[0][1]
        assert port != 1313
        assert port != 1111  # not minitouch's legacy either
