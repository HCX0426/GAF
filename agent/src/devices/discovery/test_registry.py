"""设备发现注册表单元测试 — Spec §5 测试场景 2

验证 ``DeviceDiscoveryRegistry.discover_all()`` 正确聚合多个发现器结果，
并处理异常和不可用的发现器。
"""

import os
import sys

# Ensure agent/src is on sys.path for direct import in tests.
_AGENT_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _AGENT_SRC not in sys.path:
    sys.path.insert(0, _AGENT_SRC)

import pytest  # noqa: E402 - after sys.path setup above
from devices.discovery.base import BaseDiscovery, DeviceInfo, DiscoveryError  # noqa: E402
from devices.discovery.registry import DeviceDiscoveryRegistry  # noqa: E402

# ── Test helpers ──────────────────────────────────────────────────────


class MockDiscovery(BaseDiscovery):
    """可配置的模拟发现器。"""

    def __init__(self, name: str, devices: list[DeviceInfo] | None = None,
                 available: bool = True, raise_error: bool = False):
        self._name = name
        self._devices = devices or []
        self._available = available
        self._raise_error = raise_error

    @property
    def name(self) -> str:
        return self._name

    def discover(self) -> list[DeviceInfo]:
        if self._raise_error:
            raise DiscoveryError("Simulated discovery failure")
        return list(self._devices)

    def is_available(self) -> bool:
        return self._available


def _make_device(device_id: str, name: str, device_type: str = "emulator") -> DeviceInfo:
    return DeviceInfo(
        device_id=device_id,
        name=name,
        device_type=device_type,
        connection_type="adb",
        address=device_id,
        extra={},
    )


# ── Tests ─────────────────────────────────────────────────────────────


class TestDeviceDiscoveryRegistry:
    """DeviceDiscoveryRegistry 测试组。"""

    def test_empty_registry_returns_empty_list(self):
        """空注册表 discover_all() 应返回空列表。"""
        registry = DeviceDiscoveryRegistry()
        result = registry.discover_all()
        assert result == []

    def test_register_single_discovery(self):
        """注册单个发现器，应返回其发现的设备。"""
        registry = DeviceDiscoveryRegistry()
        mock = MockDiscovery("Test", [_make_device("serial-1", "Device 1")])

        registry.register(mock)
        result = registry.discover_all()

        assert len(result) == 1
        assert result[0].device_id == "serial-1"

    def test_discover_all_aggregates_multiple(self):
        """多个发现器的设备应被正确聚合。"""
        registry = DeviceDiscoveryRegistry()

        d1 = MockDiscovery("ADB", [_make_device("s1", "Emulator 1")])
        d2 = MockDiscovery("Windows", [_make_device("hwnd-1", "BlueStacks", "windows")])

        registry.register(d1)
        registry.register(d2)

        result = registry.discover_all()

        assert len(result) == 2
        ids = {d.device_id for d in result}
        assert ids == {"s1", "hwnd-1"}

    def test_unavailable_discovery_skipped(self):
        """is_available() 返回 False 的发现器应被跳过。"""
        registry = DeviceDiscoveryRegistry()

        d1 = MockDiscovery("ADB", [_make_device("s1", "Device 1")], available=True)
        d2 = MockDiscovery("Windows", [_make_device("hwnd-1", "Device 2")], available=False)

        registry.register(d1)
        registry.register(d2)

        result = registry.discover_all()

        assert len(result) == 1
        assert result[0].device_id == "s1"

    def test_failing_discovery_does_not_block_others(self):
        """单个发现器失败不应阻止其他发现器继续执行。"""
        registry = DeviceDiscoveryRegistry()

        d1 = MockDiscovery("ADB", [_make_device("s1", "Device 1")], raise_error=True)
        d2 = MockDiscovery("Windows", [_make_device("hwnd-1", "Device 2")])

        registry.register(d1)
        registry.register(d2)

        result = registry.discover_all()

        # d1 失败被跳过，d2 成功返回
        assert len(result) == 1
        assert result[0].device_id == "hwnd-1"

    def test_duplicate_name_raises(self):
        """注册同名发现器应抛出 ValueError。"""
        registry = DeviceDiscoveryRegistry()
        d1 = MockDiscovery("Same Name")
        d2 = MockDiscovery("Same Name")

        registry.register(d1)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(d2)

    def test_unregister_removes_discovery(self):
        """unregister() 应正确移除发现器。"""
        registry = DeviceDiscoveryRegistry()
        d1 = MockDiscovery("ADB", [_make_device("s1", "Device 1")])
        d2 = MockDiscovery("Windows", [_make_device("hwnd-1", "Device 2")])

        registry.register(d1)
        registry.register(d2)
        assert len(registry) == 2

        registry.unregister("ADB")
        assert len(registry) == 1
        assert registry.discovery_names == ["Windows"]

        result = registry.discover_all()
        assert len(result) == 1
        assert result[0].device_id == "hwnd-1"

    def test_discover_by_name(self):
        """discover_by_name() 应只执行指定名称的发现器。"""
        registry = DeviceDiscoveryRegistry()

        d1 = MockDiscovery("ADB", [_make_device("s1", "Device 1")])
        d2 = MockDiscovery("Windows", [_make_device("hwnd-1", "Device 2")])

        registry.register(d1)
        registry.register(d2)

        result = registry.discover_by_name("ADB")
        assert len(result) == 1
        assert result[0].device_id == "s1"

    def test_discover_by_name_not_found(self):
        """指定不存在的名称应抛出 ValueError。"""
        registry = DeviceDiscoveryRegistry()

        with pytest.raises(ValueError, match="not registered"):
            registry.discover_by_name("NonExistent")

    def test_discover_by_name_unavailable(self):
        """指定的发现器不可用时应返回空列表。"""
        registry = DeviceDiscoveryRegistry()
        d1 = MockDiscovery("Broken", available=False)
        registry.register(d1)

        result = registry.discover_by_name("Broken")
        assert result == []

    def test_discovery_names_property(self):
        """discovery_names 应返回所有注册发现器的名称。"""
        registry = DeviceDiscoveryRegistry()
        registry.register(MockDiscovery("Alpha"))
        registry.register(MockDiscovery("Beta"))
        registry.register(MockDiscovery("Gamma"))

        assert registry.discovery_names == ["Alpha", "Beta", "Gamma"]

    def test_iter(self):
        """__iter__ 应允许遍历所有发现器。"""
        registry = DeviceDiscoveryRegistry()
        registry.register(MockDiscovery("A"))
        registry.register(MockDiscovery("B"))

        names = [d.name for d in registry]
        assert names == ["A", "B"]

    def test_unregister_nonexistent_is_silent(self):
        """注销不存在的名称不应抛出异常。"""
        registry = DeviceDiscoveryRegistry()
        registry.unregister("Ghost")  # should not raise

    def test_discovery_error_is_caught(self):
        """DiscoveryError 应被捕获，其他异常也不应中断。"""
        registry = DeviceDiscoveryRegistry()

        class ExplosiveDiscovery(BaseDiscovery):
            @property
            def name(self) -> str:
                return "Explosive"

            def discover(self) -> list[DeviceInfo]:
                raise RuntimeError("Boom!")

        d1 = ExplosiveDiscovery()
        d2 = MockDiscovery("Safe", [_make_device("ok", "OK Device")])

        registry.register(d1)
        registry.register(d2)

        # RuntimeError from d1 should be caught, d2 still returns its devices
        result = registry.discover_all()
        assert len(result) == 1
        assert result[0].device_id == "ok"

    def test_registry_len(self):
        """__len__ 应返回注册的发现器数量。"""
        registry = DeviceDiscoveryRegistry()
        assert len(registry) == 0

        registry.register(MockDiscovery("A"))
        assert len(registry) == 1

        registry.register(MockDiscovery("B"))
        assert len(registry) == 2
