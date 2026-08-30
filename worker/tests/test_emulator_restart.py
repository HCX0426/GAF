"""#33 模拟器重启 (异常恢复) 单元测试

测试 EmulatorController 和 RecoveryStrategy.restart_emulator():
- kill_emulator (control exe + process name fallback)
- start_emulator (control exe)
- restart_emulator (kill + start + wait_for_boot)
- wait_for_boot (adb wait-for-device + getprop poll)
- RecoveryStrategy.restart_emulator integration
- ADBDevice.reboot (soft reboot via ADB)
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from devices.emulator_controller import (
    EMULATOR_CONTROL_EXE,
    EMULATOR_PROCESS_NAMES,
    EmulatorController,
)

pytestmark = pytest.mark.unit


class TestEmulatorControllerInit:
    """EmulatorController 初始化测试"""

    def test_default_init(self):
        """默认参数初始化"""
        ctrl = EmulatorController()
        assert ctrl.adb_path == "adb"
        assert ctrl.control_dir is None
        assert ctrl.boot_timeout == 120.0
        assert ctrl.boot_poll_interval == 2.0

    def test_custom_init(self):
        """自定义参数初始化"""
        from pathlib import Path
        ctrl = EmulatorController(
            adb_path="/custom/adb",
            control_dir="/emulator/path",
            boot_timeout=60.0,
            boot_poll_interval=1.0,
        )
        assert ctrl.adb_path == "/custom/adb"
        assert ctrl.control_dir == Path("/emulator/path")
        assert ctrl.boot_timeout == 60.0
        assert ctrl.boot_poll_interval == 1.0


class TestKillEmulator:
    """kill_emulator 方法测试"""

    def test_unknown_emulator_type(self):
        """未知模拟器类型应返回 False"""
        ctrl = EmulatorController()
        assert ctrl.kill_emulator("unknown_type") is False

    @patch('devices.emulator_controller.platform.system', return_value='Windows')
    @patch('devices.emulator_controller.subprocess.run')
    def test_kill_ldplayer_via_control_exe(self, mock_run, mock_system):
        """ldplayer 应通过 ldconsole.exe quit 命令关闭"""
        with patch.object(EmulatorController, '_get_control_exe_path', return_value='ldconsole.exe'):
            ctrl = EmulatorController()
            result = ctrl.kill_emulator("ldplayer", "0")
            assert result is True
            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert "ldconsole.exe" in cmd
            assert "quit" in cmd
            assert "0" in cmd

    @patch('devices.emulator_controller.platform.system', return_value='Windows')
    @patch('devices.emulator_controller.subprocess.run')
    def test_kill_mumu_via_control_exe(self, mock_run, mock_system):
        """mumu 应通过 MuMuManager.exe shutdown_player 命令关闭"""
        with patch.object(EmulatorController, '_get_control_exe_path', return_value='MuMuManager.exe'):
            ctrl = EmulatorController()
            result = ctrl.kill_emulator("mumu", "0")
            assert result is True
            cmd = mock_run.call_args[0][0]
            assert "MuMuManager.exe" in cmd
            assert "shutdown_player" in cmd

    @patch('devices.emulator_controller.platform.system', return_value='Windows')
    @patch('devices.emulator_controller.subprocess.run')
    def test_kill_fallback_to_taskkill(self, mock_run, mock_system):
        """控制 exe 不可用时应回退到 taskkill"""
        mock_run.return_value = MagicMock(returncode=0)
        with patch.object(EmulatorController, '_get_control_exe_path', return_value=None):
            ctrl = EmulatorController()
            result = ctrl.kill_emulator("ldplayer")
            assert result is True
            # Should have called taskkill for each process name
            assert mock_run.call_count >= 1

    @patch('devices.emulator_controller.platform.system', return_value='Linux')
    @patch('devices.emulator_controller.subprocess.run')
    def test_kill_on_linux_uses_pkill(self, mock_run, mock_system):
        """Linux 上应使用 pkill"""
        mock_run.return_value = MagicMock(returncode=0)
        ctrl = EmulatorController()
        result = ctrl.kill_emulator("ldplayer")
        assert result is True
        # Check pkill was called
        called_cmds = [call.args[0] for call in mock_run.call_args_list]
        assert any("pkill" in cmd for cmd in called_cmds)

    @patch('devices.emulator_controller.platform.system', return_value='Windows')
    @patch('devices.emulator_controller.subprocess.run')
    def test_kill_control_exe_failure_falls_back(self, mock_run, mock_system):
        """控制 exe 失败时应回退到 taskkill"""
        # First call (control exe) raises, second call (taskkill) succeeds
        mock_run.side_effect = [Exception("control failed"), MagicMock(returncode=0)]
        with patch.object(EmulatorController, '_get_control_exe_path', return_value='ldconsole.exe'):
            ctrl = EmulatorController()
            result = ctrl.kill_emulator("ldplayer")
            assert result is True


class TestStartEmulator:
    """start_emulator 方法测试"""

    def test_unknown_emulator_type(self):
        """未知模拟器类型应返回 False"""
        ctrl = EmulatorController()
        assert ctrl.start_emulator("unknown_type") is False

    @patch('devices.emulator_controller.platform.system', return_value='Linux')
    def test_start_on_linux_returns_false(self, mock_system):
        """Linux 上启动模拟器应返回 False (不支持)"""
        ctrl = EmulatorController()
        assert ctrl.start_emulator("ldplayer") is False

    @patch('devices.emulator_controller.platform.system', return_value='Windows')
    @patch('devices.emulator_controller.subprocess.run')
    def test_start_ldplayer_via_ldconsole(self, mock_run, mock_system):
        """ldplayer 应通过 ldconsole.exe launch 命令启动"""
        with patch.object(EmulatorController, '_get_control_exe_path', return_value='ldconsole.exe'):
            ctrl = EmulatorController()
            result = ctrl.start_emulator("ldplayer", "0")
            assert result is True
            cmd = mock_run.call_args[0][0]
            assert "ldconsole.exe" in cmd
            assert "launch" in cmd
            assert "0" in cmd

    @patch('devices.emulator_controller.platform.system', return_value='Windows')
    @patch('devices.emulator_controller.subprocess.run')
    def test_start_mumu_via_mumumanager(self, mock_run, mock_system):
        """mumu 应通过 MuMuManager.exe launch_player 命令启动"""
        with patch.object(EmulatorController, '_get_control_exe_path', return_value='MuMuManager.exe'):
            ctrl = EmulatorController()
            result = ctrl.start_emulator("mumu", "0")
            assert result is True
            cmd = mock_run.call_args[0][0]
            assert "MuMuManager.exe" in cmd
            assert "launch_player" in cmd

    @patch('devices.emulator_controller.platform.system', return_value='Windows')
    def test_start_no_control_exe(self, mock_system):
        """控制 exe 不可用时应返回 False"""
        with patch.object(EmulatorController, '_get_control_exe_path', return_value=None):
            ctrl = EmulatorController()
            result = ctrl.start_emulator("ldplayer")
            assert result is False


class TestWaitForBoot:
    """wait_for_boot 方法测试"""

    @patch('devices.emulator_controller.subprocess.run')
    def test_wait_for_boot_success(self, mock_run):
        """设备启动完成应返回 True"""
        # wait-for-device succeeds, then getprop returns "1"
        mock_run.side_effect = [
            MagicMock(returncode=0),  # wait-for-device
            MagicMock(returncode=0, stdout="1\n"),  # getprop
        ]
        ctrl = EmulatorController(boot_timeout=10.0, boot_poll_interval=0.1)
        result = ctrl.wait_for_boot()
        assert result is True

    @patch('devices.emulator_controller.subprocess.run')
    def test_wait_for_boot_timeout_no_device(self, mock_run):
        """设备未出现应超时返回 False"""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="adb", timeout=10)
        ctrl = EmulatorController(boot_timeout=1.0)
        result = ctrl.wait_for_boot()
        assert result is False

    @patch('devices.emulator_controller.subprocess.run')
    def test_wait_for_boot_timeout_boot_not_completed(self, mock_run):
        """设备出现但 boot_completed 未完成应超时返回 False"""
        # wait-for-device succeeds, but getprop never returns "1"
        mock_run.side_effect = [
            MagicMock(returncode=0),  # wait-for-device
            MagicMock(returncode=0, stdout="\n"),  # getprop (empty)
        ]
        ctrl = EmulatorController(boot_timeout=0.5, boot_poll_interval=0.1)
        result = ctrl.wait_for_boot()
        assert result is False

    @patch('devices.emulator_controller.subprocess.run')
    def test_wait_for_boot_with_serial(self, mock_run):
        """指定 device_serial 时应使用 -s 参数"""
        mock_run.side_effect = [
            MagicMock(returncode=0),  # wait-for-device
            MagicMock(returncode=0, stdout="1\n"),  # getprop
        ]
        ctrl = EmulatorController(boot_timeout=10.0, boot_poll_interval=0.1)
        result = ctrl.wait_for_boot(device_serial="emulator-5554")
        assert result is True
        # Verify -s flag used
        wait_cmd = mock_run.call_args_list[0].args[0]
        assert "-s" in wait_cmd
        assert "emulator-5554" in wait_cmd


class TestRestartEmulator:
    """restart_emulator 方法测试"""

    @patch('devices.emulator_controller.time.sleep')
    @patch('devices.emulator_controller.platform.system', return_value='Windows')
    @patch('devices.emulator_controller.subprocess.run')
    def test_restart_success(self, mock_run, mock_system, mock_sleep):
        """完整重启流程应成功"""
        with patch.object(EmulatorController, '_get_control_exe_path', return_value='ldconsole.exe'):
            ctrl = EmulatorController(boot_timeout=10.0, boot_poll_interval=0.1)
            # kill + start + wait-for-device + getprop
            mock_run.side_effect = [
                MagicMock(returncode=0),  # kill (ldconsole quit)
                MagicMock(returncode=0),  # start (ldconsole launch)
                MagicMock(returncode=0),  # wait-for-device
                MagicMock(returncode=0, stdout="1\n"),  # getprop
            ]
            result = ctrl.restart_emulator("ldplayer", "0", wait_for_boot=True)
            assert result is True

    @patch('devices.emulator_controller.time.sleep')
    @patch('devices.emulator_controller.platform.system', return_value='Windows')
    def test_restart_kill_fails(self, mock_system, mock_sleep):
        """kill 失败应返回 False"""
        with patch.object(EmulatorController, 'kill_emulator', return_value=False):
            ctrl = EmulatorController()
            result = ctrl.restart_emulator("ldplayer", "0")
            assert result is False

    @patch('devices.emulator_controller.time.sleep')
    @patch('devices.emulator_controller.platform.system', return_value='Windows')
    def test_restart_start_fails(self, mock_system, mock_sleep):
        """start 失败应返回 False"""
        ctrl = EmulatorController()
        with patch.object(ctrl, 'kill_emulator', return_value=True), \
             patch.object(ctrl, 'start_emulator', return_value=False):
            result = ctrl.restart_emulator("ldplayer", "0")
            assert result is False

    @patch('devices.emulator_controller.time.sleep')
    @patch('devices.emulator_controller.platform.system', return_value='Windows')
    def test_restart_no_wait_for_boot(self, mock_system, mock_sleep):
        """wait_for_boot=False 时不应等待启动"""
        ctrl = EmulatorController()
        with patch.object(ctrl, 'kill_emulator', return_value=True), \
             patch.object(ctrl, 'start_emulator', return_value=True), \
             patch.object(ctrl, 'wait_for_boot') as mock_wait:
            result = ctrl.restart_emulator("ldplayer", "0", wait_for_boot=False)
            assert result is True
            mock_wait.assert_not_called()


class TestRecoveryStrategyRestartEmulator:
    """RecoveryStrategy.restart_emulator 集成测试"""

    def test_restart_emulator_success(self):
        """RecoveryStrategy.restart_emulator 应委托给 EmulatorController"""
        from core.recovery import RecoveryStrategy

        strategy = RecoveryStrategy()
        mock_controller = MagicMock()
        mock_controller.restart_emulator.return_value = True

        result = strategy.restart_emulator(
            emulator_type="ldplayer",
            instance_id="0",
            emulator_controller=mock_controller,
        )
        assert result is True
        mock_controller.restart_emulator.assert_called_once()
        assert strategy.consecutive_fails == 0
        assert strategy.current_layer == 4

    def test_restart_emulator_failure(self):
        """EmulatorController 失败时 RecoveryStrategy 应返回 False"""
        from core.recovery import RecoveryStrategy

        strategy = RecoveryStrategy()
        strategy.consecutive_fails = 5
        mock_controller = MagicMock()
        mock_controller.restart_emulator.return_value = False

        result = strategy.restart_emulator(
            emulator_type="ldplayer",
            emulator_controller=mock_controller,
        )
        assert result is False
        assert strategy.consecutive_fails == 5  # Not reset on failure

    def test_restart_emulator_exception(self):
        """EmulatorController 抛异常时 RecoveryStrategy 应返回 False"""
        from core.recovery import RecoveryStrategy

        strategy = RecoveryStrategy()
        mock_controller = MagicMock()
        mock_controller.restart_emulator.side_effect = RuntimeError("boom")

        result = strategy.restart_emulator(
            emulator_type="ldplayer",
            emulator_controller=mock_controller,
        )
        assert result is False

    def test_restart_emulator_import_fallback(self):
        """emulator_controller=None 时应尝试导入 EmulatorController"""
        from core.recovery import RecoveryStrategy

        strategy = RecoveryStrategy()
        # Patch the import to return a mock
        with patch('devices.emulator_controller.EmulatorController') as mock_ctrl_cls:
            mock_instance = MagicMock()
            mock_instance.restart_emulator.return_value = True
            mock_ctrl_cls.return_value = mock_instance
            result = strategy.restart_emulator(emulator_type="ldplayer")
            assert result is True


class TestEmulatorConstants:
    """模拟器常量测试"""

    def test_process_names_cover_all_types(self):
        """所有模拟器类型都应有进程名映射"""
        expected_types = {"ldplayer", "mumu", "bluestacks", "nox", "memu", "xiaoyao"}
        assert set(EMULATOR_PROCESS_NAMES.keys()) == expected_types

    def test_control_exe_has_ldplayer_and_mumu(self):
        """ldplayer 和 mumu 应有控制 exe"""
        assert EMULATOR_CONTROL_EXE["ldplayer"] == "ldconsole.exe"
        assert EMULATOR_CONTROL_EXE["mumu"] == "MuMuManager.exe"

    def test_process_names_are_non_empty(self):
        """每个模拟器类型应有至少一个进程名"""
        for emu_type, names in EMULATOR_PROCESS_NAMES.items():
            assert len(names) > 0, f"{emu_type} has no process names"


class TestADBDeviceReboot:
    """ADBDevice.reboot 方法测试 (mocked)"""

    def test_reboot_success(self):
        """ADB reboot 成功应返回 True"""
        from devices.adb.device import ADBDevice

        device = ADBDevice(serial="emulator-5554")
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # adb reboot
                MagicMock(returncode=0),  # wait-for-device
                MagicMock(returncode=0, stdout="1\n"),  # getprop boot_completed
            ]
            result = device.reboot(wait_for_boot=True, timeout=10.0)
            assert result is True

    def test_reboot_no_wait(self):
        """wait_for_boot=False 应立即返回 True"""
        from devices.adb.device import ADBDevice

        device = ADBDevice(serial="emulator-5554")
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = device.reboot(wait_for_boot=False)
            assert result is True
            # Only reboot command should be called, no wait-for-device
            assert mock_run.call_count == 1

    def test_reboot_reboot_cmd_fails(self):
        """reboot 命令失败应返回 False"""
        from devices.adb.device import ADBDevice

        device = ADBDevice(serial="emulator-5554")
        with patch('subprocess.run', side_effect=Exception("adb not found")):
            result = device.reboot(wait_for_boot=False)
            assert result is False

    def test_reboot_wait_for_device_timeout(self):
        """wait-for-device 超时应返回 False"""
        from devices.adb.device import ADBDevice

        device = ADBDevice(serial="emulator-5554")
        with patch('subprocess.run') as mock_run, \
             patch('time.sleep'):
            mock_run.side_effect = [
                MagicMock(returncode=0),  # adb reboot
                subprocess.TimeoutExpired(cmd="adb", timeout=10),  # wait-for-device
            ]
            result = device.reboot(wait_for_boot=True, timeout=1.0)
            assert result is False

    def test_reboot_boot_not_completed_timeout(self):
        """boot_completed 未完成应超时返回 False"""
        from devices.adb.device import ADBDevice

        device = ADBDevice(serial="emulator-5554")
        with patch('subprocess.run') as mock_run, \
             patch('time.sleep'):
            mock_run.side_effect = [
                MagicMock(returncode=0),  # adb reboot
                MagicMock(returncode=0),  # wait-for-device
                MagicMock(returncode=0, stdout="\n"),  # getprop (empty)
            ]
            result = device.reboot(wait_for_boot=True, timeout=0.5)
            assert result is False
