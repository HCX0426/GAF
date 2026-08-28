"""设备抽象层单元测试"""

from unittest.mock import MagicMock, patch

import pytest
from core.exceptions import DeviceError
from core.result import fail_result, success_result
from devices.base import BaseDevice, DeviceStatus, require_operable
from devices.center import DeviceCenter
from devices.emulator_discovery import EmulatorDiscovery
from devices.manager import DeviceManager
from devices.plugin import CapturePlugin, DevicePluginRegistry, InputPlugin
from platforms.windows.discovery import WindowDiscovery

pytestmark = pytest.mark.unit


class MockDevice(BaseDevice):
    """用于测试的 Mock 设备实现"""

    def connect(self) -> None:
        self._status = DeviceStatus.CONNECTED

    def disconnect(self) -> None:
        self._status = DeviceStatus.DISCONNECTED

    def capture_screen(self):
        return None

    def click(self, x: int, y: int) -> None:
        pass

    def key_press(self, key: str) -> None:
        pass

    def text_input(self, text: str) -> None:
        pass

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> None:
        pass

    def get_resolution(self):
        return (1920, 1080)


class TestBaseDevice:
    """BaseDevice 接口完整性和新增功能测试"""

    def test_device_initial_state(self):
        """验证设备初始状态为 DISCONNECTED"""
        device = MockDevice(device_id="test-1", name="Test")
        assert device.status == DeviceStatus.DISCONNECTED
        assert device.device_id == "test-1"
        assert device.name == "Test"

    def test_device_status_change(self):
        """验证设备状态变更"""
        device = MockDevice()
        assert device.status == DeviceStatus.DISCONNECTED
        device.connect()
        assert device.status == DeviceStatus.CONNECTED
        device.disconnect()
        assert device.status == DeviceStatus.DISCONNECTED

    def test_get_device_info_default(self):
        """验证默认 get_device_info 返回基本信息"""
        device = MockDevice(device_id="test-1", name="Test Device")
        device.connect()
        info = device.get_device_info()
        assert info["device_id"] == "test-1"
        assert info["name"] == "Test Device"
        assert info["status"] == "connected"
        assert info["type"] == "MockDevice"

    def test_get_resolution_abstract(self):
        """验证 get_resolution 在子类中实现"""
        device = MockDevice()
        resolution = device.get_resolution()
        assert resolution == (1920, 1080)

    def test_swipe_with_default_duration(self):
        """验证 swipe 默认 duration 参数"""
        device = MockDevice()
        device.swipe(0, 0, 100, 100)
        device.swipe(0, 0, 100, 100, duration=500)

    def test_require_operable_raises_on_disconnected(self):
        """验证非可操作状态调用方法抛出异常"""
        device = MockDevice(device_id="test-1")

        @require_operable
        def dummy_op(self):
            return "ok"

        with pytest.raises(DeviceError, match="设备不可操作"):
            dummy_op(device)

    def test_exists_default_false(self):
        """验证默认 exists 返回 False"""
        device = MockDevice()
        assert device.exists() is False
        assert device.exists(template="test") is False

    def test_device_id_property(self):
        """验证 device_id 属性"""
        device = MockDevice(device_id="custom-id-42")
        assert device.device_id == "custom-id-42"

    def test_status_setter_triggers_log(self):
        """验证状态变更触发日志"""
        device = MockDevice(device_id="log-test")
        with patch("devices.base.logger") as mock_logger:
            device.status = DeviceStatus.BUSY
            mock_logger.debug.assert_called_once()


class TestDeviceManager:
    """DeviceManager 多设备管理测试"""

    def test_add_device(self):
        """验证添加设备"""
        mgr = DeviceManager()
        device = MockDevice(device_id="d1", name="Device 1")
        mgr.add_device(device)
        assert mgr.device_count == 1
        assert mgr.get_active_device() is device

    def test_add_multiple_devices(self):
        """验证添加多个设备"""
        mgr = DeviceManager()
        d1 = MockDevice(device_id="d1")
        d2 = MockDevice(device_id="d2")
        mgr.add_device(d1)
        mgr.add_device(d2)
        assert mgr.device_count == 2
        assert mgr.get_active_device() is d1

    def test_remove_device(self):
        """验证移除设备"""
        mgr = DeviceManager()
        d1 = MockDevice(device_id="d1")
        d2 = MockDevice(device_id="d2")
        mgr.add_device(d1)
        mgr.add_device(d2)
        mgr.remove_device("d1")
        assert mgr.device_count == 1
        assert mgr.get_active_device() is d2

    def test_remove_active_device_fallback(self):
        """验证移除活跃设备后自动切换到下一个设备"""
        mgr = DeviceManager()
        d1 = MockDevice(device_id="d1")
        d2 = MockDevice(device_id="d2")
        mgr.add_device(d1)
        mgr.add_device(d2)
        mgr.remove_device("d1")
        assert mgr.get_active_device() is d2

    def test_set_active_device(self):
        """验证切换活跃设备"""
        mgr = DeviceManager()
        d1 = MockDevice(device_id="d1")
        d2 = MockDevice(device_id="d2")
        mgr.add_device(d1)
        mgr.add_device(d2)
        assert mgr.set_active_device("d2") is True
        assert mgr.get_active_device() is d2

    def test_set_active_device_not_found(self):
        """验证切换到不存在的设备返回 False"""
        mgr = DeviceManager()
        assert mgr.set_active_device("nonexistent") is False

    def test_list_devices(self):
        """验证列出所有设备信息"""
        mgr = DeviceManager()
        d1 = MockDevice(device_id="d1", name="Device 1")
        d1.connect()
        mgr.add_device(d1)
        devices = mgr.list_devices()
        assert len(devices) == 1
        assert devices[0]["device_id"] == "d1"
        assert devices[0]["name"] == "Device 1"

    def test_get_device(self):
        """验证按 ID 获取设备"""
        mgr = DeviceManager()
        d1 = MockDevice(device_id="d1")
        mgr.add_device(d1)
        assert mgr.get_device("d1") is d1
        assert mgr.get_device("nonexistent") is None


class TestDevicePluginRegistry:
    """DevicePluginRegistry 插件注册测试"""

    def test_register_capture_plugin(self):
        """验证注册截图插件"""
        registry = DevicePluginRegistry()
        mock_plugin = MagicMock(spec=CapturePlugin)
        registry.register_capture_plugin("windows", mock_plugin)
        assert registry.get_capture_plugin("windows") is mock_plugin

    def test_register_input_plugin(self):
        """验证注册输入插件"""
        registry = DevicePluginRegistry()
        mock_plugin = MagicMock(spec=InputPlugin)
        registry.register_input_plugin("adb", mock_plugin)
        assert registry.get_input_plugin("adb") is mock_plugin

    def test_get_unregistered_plugin_returns_none(self):
        """验证获取未注册的插件返回 None"""
        registry = DevicePluginRegistry()
        assert registry.get_capture_plugin("unknown") is None
        assert registry.get_input_plugin("unknown") is None

    def test_list_plugins(self):
        """验证列出已注册插件"""
        registry = DevicePluginRegistry()
        mock_capture = MagicMock(spec=CapturePlugin)
        mock_input = MagicMock(spec=InputPlugin)
        registry.register_capture_plugin("windows", mock_capture)
        registry.register_input_plugin("adb", mock_input)
        assert "windows" in registry.list_capture_plugins()
        assert "adb" in registry.list_input_plugins()

    def test_unregister_plugin(self):
        """验证注销插件"""
        registry = DevicePluginRegistry()
        mock_plugin = MagicMock(spec=CapturePlugin)
        registry.register_capture_plugin("windows", mock_plugin)
        assert registry.unregister_capture_plugin("windows") is True
        assert registry.get_capture_plugin("windows") is None
        assert registry.unregister_capture_plugin("windows") is False


class TestEmulatorDiscovery:
    """EmulatorDiscovery 模拟器发现测试"""

    def test_scan_adb_ports_mock(self):
        """验证 ADB 端口扫描（mock socket）"""
        discovery = EmulatorDiscovery()
        with patch.object(discovery, "_check_adb_port", return_value=True):
            ports = discovery.scan_adb_ports(start=5555, end=5557)
            assert len(ports) == 3
            assert "127.0.0.1:5555" in ports

    def test_scan_adb_ports_empty(self):
        """验证 ADB 端口扫描无结果"""
        discovery = EmulatorDiscovery()
        with patch.object(discovery, "_check_adb_port", return_value=False):
            ports = discovery.scan_adb_ports(start=5555, end=5555)
            assert len(ports) == 0

    def test_discover_mumu_with_registry(self):
        """验证 MuMu 发现（mock 注册表和端口）"""
        discovery = EmulatorDiscovery()
        with (
            patch.object(discovery, "_read_registry", return_value="C:\\MuMu\\"),
            patch.object(discovery, "_check_adb_port", return_value=True),
        ):
            result = discovery.discover_mumu()
            assert result is not None
            assert result["type"] == "mumu"
            assert result["adb_port"] == 7555

    def test_discover_mumu_not_found(self):
        """验证 MuMu 未发现的情况"""
        discovery = EmulatorDiscovery()
        with (
            patch.object(discovery, "_read_registry", return_value=None),
            patch.object(discovery, "_check_adb_port", return_value=False),
            patch.object(discovery, "_get_adb_devices", return_value=[]),
        ):
            result = discovery.discover_mumu()
            assert result is None

    def test_discover_ldplayer_found(self):
        """验证雷电模拟器发现"""
        discovery = EmulatorDiscovery()
        with (
            patch.object(discovery, "_read_registry", return_value="C:\\LDPlayer\\"),
            patch.object(discovery, "_check_adb_port", return_value=True),
        ):
            result = discovery.discover_ldplayer()
            assert result is not None
            assert result["type"] == "ldplayer"

    def test_discover_all_comprehensive(self):
        """验证 discover_all 全面发现"""
        discovery = EmulatorDiscovery()
        # Mock all discovery phases to isolate from machine state:
        # - Per-emulator discovery methods return None (no emulators found)
        # - Internal discovery helpers return empty (no registry/vbox traces)
        # - scan_adb_ports returns a mock serial so Phase 6 fallback triggers
        with patch.object(discovery, "discover_mumu", return_value=None), \
             patch.object(discovery, "discover_ldplayer", return_value=None), \
             patch.object(discovery, "discover_bluestacks", return_value=None), \
             patch.object(discovery, "discover_xiaoyao", return_value=None), \
             patch.object(discovery, "discover_nox", return_value=None), \
             patch.object(discovery, "scan_adb_ports", return_value=["127.0.0.1:5555"]), \
             patch.object(discovery, "_discover_by_process", return_value={}), \
             patch.object(discovery, "_discover_by_muicache", return_value={}), \
             patch.object(discovery, "_discover_by_userassist", return_value={}), \
             patch.object(discovery, "_discover_by_vbox_conf", return_value=[]):
            results = discovery.discover_all()
            assert len(results) >= 1
            assert any(r["type"] == "adb" for r in results)


class TestWindowDiscovery:
    """WindowDiscovery 窗口发现测试"""

    def test_gaming_keywords_initial(self):
        """验证初始游戏关键词列表"""
        wd = WindowDiscovery()
        assert "game" in wd._gamimg_keywords
        assert "MuMu" in wd._gamimg_keywords

    def test_add_gaming_keyword(self):
        """验证添加游戏关键词"""
        wd = WindowDiscovery()
        wd.add_gaming_keyword("DNF")
        assert "DNF" in wd._gamimg_keywords

    def test_add_gaming_keyword_duplicate(self):
        """验证重复添加关键词不重复"""
        wd = WindowDiscovery()
        original_len = len(wd._gamimg_keywords)
        wd.add_gaming_keyword("game")
        assert len(wd._gamimg_keywords) == original_len

    def test_group_windows_by_process(self):
        """验证按进程名分组窗口"""
        wd = WindowDiscovery()
        windows = [
            {"hwnd": 1, "title": "Game1", "process_name": "game.exe"},
            {"hwnd": 2, "title": "Game2", "process_name": "game.exe"},
            {"hwnd": 3, "title": "Other", "process_name": "other.exe"},
        ]
        grouped = wd.group_windows(windows, key="process")
        assert len(grouped["game.exe"]) == 2
        assert len(grouped["other.exe"]) == 1

    def test_group_windows_by_title_regex(self):
        """验证按标题正则分组窗口"""
        wd = WindowDiscovery()
        windows = [
            {"hwnd": 1, "title": "Game - Instance 1"},
            {"hwnd": 2, "title": "Game - Instance 2"},
            {"hwnd": 3, "title": "Other Window"},
        ]
        grouped = wd.group_windows(windows, key="title", regex_pattern=r"Game - (.+)")
        assert "Instance 1" in grouped
        assert "Instance 2" in grouped
        assert "unknown" in grouped

    def test_find_gaming_windows_with_mock(self):
        """验证游戏窗口发现（mock get_all_windows_info）"""
        wd = WindowDiscovery()
        mock_windows = [
            {
                "hwnd": 1, "title": "BlueStacks App Player",
                "process_name": "BlueStacks.exe",
                "rect": {"x": 0, "y": 0, "w": 800, "h": 600},
                "group": "BlueStacks.exe",
            },
            {
                "hwnd": 2, "title": "Notepad",
                "process_name": "notepad.exe",
                "rect": {"x": 0, "y": 0, "w": 10, "h": 10},
                "group": "notepad.exe",
            },
        ]
        with patch.object(wd, "get_all_windows_info", return_value=mock_windows):
            gaming = wd.find_gaming_windows()
            assert len(gaming) == 1
            assert gaming[0]["title"] == "BlueStacks App Player"


class TestDeviceCenter:
    """DeviceCenter 整合测试"""

    def test_center_initialization(self):
        """验证 DeviceCenter 初始化"""
        center = DeviceCenter()
        assert center.manager is not None
        assert center.plugin_registry is not None
        assert center.manager.device_count == 0

    def test_register_device(self):
        """验证 DeviceCenter 注册设备"""
        center = DeviceCenter()
        device = MockDevice(device_id="d1")
        center.register_device(device)
        assert center.manager.device_count == 1
        assert center.get_device("d1") is device

    def test_list_devices_empty(self):
        """验证空设备列表"""
        center = DeviceCenter()
        assert center.list_devices() == []

    def test_auto_discover_with_mocks(self):
        """验证自动发现流程（mock 注册表发现器，Task 2.2）"""
        from devices.discovery.base import DeviceInfo

        center = DeviceCenter()
        mock_emu_info = DeviceInfo(
            device_id="127.0.0.1:7555",
            name="MuMu模拟器",
            device_type="emulator",
            connection_type="adb",
            address="127.0.0.1:7555",
            extra={"adb_port": 7555, "emulator_type": "mumu"},
        )
        mock_win_info = DeviceInfo(
            device_id="12345",
            name="BlueStacks App Player",
            device_type="windows",
            connection_type="window",
            address="BlueStacks App Player",
            extra={"hwnd": 12345, "process_name": "BlueStacks.exe", "rect": {"x": 0, "y": 0, "w": 800, "h": 600}},
        )
        with patch.object(
            center._discovery_registry, "discover_all",
            return_value=[mock_emu_info, mock_win_info],
        ), patch.object(
            center._discovery_registry, "discover_by_name",
            return_value=[mock_win_info],
        ):
            devices = center.auto_discover()
            assert len(devices) == 2

    def test_discover_emulators(self):
        """验证仅发现模拟器元信息"""
        center = DeviceCenter()
        mock_info = [{"name": "Test", "type": "mumu", "adb_port": 7555, "adb_serial": "127.0.0.1:7555"}]
        with patch.object(center._emulator_discovery, "discover_all", return_value=mock_info):
            result = center.discover_emulators()
            assert len(result) == 1
            assert result[0]["type"] == "mumu"

    def test_discover_windows(self):
        """验证仅发现窗口元信息"""
        center = DeviceCenter()
        mock_info = [{"hwnd": 1, "title": "Game", "process_name": "game.exe"}]
        with patch.object(center._window_discovery, "find_gaming_windows", return_value=mock_info):
            result = center.discover_windows()
            assert len(result) == 1
            assert result[0]["title"] == "Game"


class TestAutoResult:
    """AutoResult 结果类测试"""

    def test_success_result(self):
        """验证成功结果"""
        result = success_result(data={"key": "value"})
        assert result.success is True
        assert result.data == {"key": "value"}

    def test_fail_result(self):
        """验证失败结果"""
        result = fail_result(error_msg="error occurred")
        assert result.success is False
        assert result.error_msg == "error occurred"

    def test_result_bool_conversion(self):
        """验证结果布尔转换"""
        assert bool(success_result()) is True
        assert bool(fail_result()) is False
