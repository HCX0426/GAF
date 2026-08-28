"""S2-2.7 (2026-08-17): agent-side UI recovery wiring tests.

Covers:
- handler.handle_device_command dispatch (restart_emulator / reconnect_adb
  real executors, not-implemented commands report explicitly)
- connection handler_map registers "device.command"
- engine.load() sets pipeline_name + wires recovery_manager/max_recovery_retries
- orchestrator injects InterfaceRecoveryManager when interface_states.yaml exists
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from client.handler import MessageHandler
from core.config import AgentConfig
from core.orchestrator import TaskOrchestrator
from engine.pipeline_engine import PipelineEngine

pytestmark = pytest.mark.unit


def _make_handler() -> MessageHandler:
    orch = MagicMock()
    orch._device_manager = MagicMock()
    orch._device_manager.get_active_device.return_value = None
    handler = MessageHandler(orch)
    handler.send_callback = MagicMock()
    # _send_to_server gates on self._loop + is_running() before calling
    # send_callback; provide a running loop so frames are actually sent.
    loop = MagicMock()
    loop.is_running.return_value = True
    handler._loop = loop
    return handler


class TestHandleDeviceCommand:
    """handle_device_command dispatch + result reporting."""

    def test_registered_in_handler_map(self):
        """connection handler_map must route device.command to the handler."""
        import client.connection as connection_mod

        with open(Path(connection_mod.__file__), encoding="utf-8") as f:
            source = f.read()
        assert "device.command" in source
        assert "handle_device_command" in source

    def test_restart_emulator_executes_and_reports_success(self):
        handler = _make_handler()
        with patch(
            "devices.emulator_controller.EmulatorController.restart_emulator",
            return_value=True,
        ) as mock_restart:
            handler.handle_device_command(
                {
                    "command": "restart_emulator",
                    "target_id": 42,
                    "config": {"emulator_type": "ldplayer", "instance_id": 0},
                }
            )
        mock_restart.assert_called_once_with(
            emulator_type="ldplayer", instance_id=0, wait_for_boot=True
        )
        args = handler.send_callback.call_args.args[1]
        assert args["command"] == "restart_emulator"
        assert args["success"] is True
        assert args["target_id"] == 42

    def test_restart_emulator_missing_type_reports_error(self):
        handler = _make_handler()
        handler.handle_device_command(
            {"command": "restart_emulator", "target_id": 1, "config": {}}
        )
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is False
        assert "emulator_type" in args["output"]["error"]

    def test_reconnect_adb_uses_active_device(self):
        handler = _make_handler()
        device = MagicMock()
        device.device_id = "dev1"
        handler._orchestrator._device_manager.get_active_device.return_value = device
        handler.handle_device_command(
            {"command": "reconnect_adb", "target_id": 7, "config": {}}
        )
        device.connect.assert_called_once()
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is True
        assert args["output"]["device_id"] == "dev1"

    def test_reconnect_adb_no_device_reports_error(self):
        handler = _make_handler()
        handler.handle_device_command(
            {"command": "reconnect_adb", "target_id": 7, "config": {}}
        )
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is False
        assert "no active device" in args["output"]["error"]

    @pytest.mark.parametrize(
        "command",
        ["relogin", "switch_backup", "switch_account", "restart"],
    )
    def test_not_implemented_commands_report_explicitly(self, command):
        """无 agent 端执行器的命令必须显式 not-implemented, 不假 success."""
        handler = _make_handler()
        handler.handle_device_command(
            {"command": command, "target_id": 3, "config": {}}
        )
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is False
        assert "not implemented" in args["output"]["error"]

    def test_unknown_command_reports_error(self):
        handler = _make_handler()
        handler.handle_device_command(
            {"command": "nonsense", "target_id": 3, "config": {}}
        )
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is False
        assert "unknown device command" in args["output"]["error"]

    def test_reports_device_action_result_frame_type(self):
        handler = _make_handler()
        handler.handle_device_command(
            {"command": "relogin", "target_id": 3, "config": {}}
        )
        msg_type = handler.send_callback.call_args.args[0]
        assert msg_type == "device.action_result"


class TestRestartAppExecutor:
    """restart_app real executor (spec 2026-08-17-s27-device-command-executors P1)."""

    def _device(self, device_type: str) -> MagicMock:
        device = MagicMock()
        device.device_type = device_type
        device.device_id = "dev1"
        return device

    def _handler_with_device(self, device_type: str) -> MessageHandler:
        handler = _make_handler()
        handler._orchestrator._device_manager.get_active_device.return_value = (
            self._device(device_type)
        )
        return handler

    def test_android_force_stop_then_monkey_launch(self):
        handler = self._handler_with_device("emulator")
        with patch(
            "engine.nodes.app_control._run_adb",
            side_effect=[(0, "", ""), (0, "", "")],
        ) as mock_run:
            handler.handle_device_command(
                {
                    "command": "restart_app",
                    "target_id": 9,
                    "config": {"package": "com.lookcos.hermit"},
                }
            )
        assert mock_run.call_count == 2
        force_stop = mock_run.call_args_list[0].args[1]
        assert force_stop == ["shell", "am", "force-stop", "com.lookcos.hermit"]
        launch = mock_run.call_args_list[1].args[1]
        assert launch[:4] == ["shell", "monkey", "-p", "com.lookcos.hermit"]
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is True
        assert args["output"]["device_type"] == "emulator"

    def test_android_missing_package_reports_error(self):
        handler = self._handler_with_device("android")
        handler.handle_device_command(
            {"command": "restart_app", "target_id": 9, "config": {}}
        )
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is False
        assert "config.package" in args["output"]["error"]

    def test_android_force_stop_failure_reports_error(self):
        handler = self._handler_with_device("emulator")
        with patch(
            "engine.nodes.app_control._run_adb",
            return_value=(1, "", "force-stop boom"),
        ):
            handler.handle_device_command(
                {
                    "command": "restart_app",
                    "target_id": 9,
                    "config": {"package": "com.x"},
                }
            )
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is False
        assert "force-stop" in args["output"]["error"]

    def test_windows_command_taskkill_and_spawn(self):
        handler = self._handler_with_device("windows")
        with patch(
            "subprocess.run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ) as mock_run, patch(
            "subprocess.Popen", return_value=MagicMock(pid=1234),
        ) as mock_popen, patch("time.sleep") as mock_sleep:
            handler.handle_device_command(
                {
                    "command": "restart_app",
                    "target_id": 9,
                    "config": {
                        "command": "D:/games/game.exe --flag",
                        "wait_seconds": 3,
                    },
                }
            )
        kill_call = mock_run.call_args.args[0]
        assert kill_call == ["taskkill", "/IM", "D:/games/game.exe", "/F"]
        mock_popen.assert_called_once()
        spawned = mock_popen.call_args.args[0]
        assert spawned == ["D:/games/game.exe", "--flag"]
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is True
        mock_sleep.assert_called_once_with(3)

    def test_windows_missing_command_reports_error(self):
        handler = self._handler_with_device("windows")
        handler.handle_device_command(
            {"command": "restart_app", "target_id": 9, "config": {}}
        )
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is False
        assert "config.command" in args["output"]["error"]

    def test_no_active_device_reports_error(self):
        handler = _make_handler()
        handler.handle_device_command(
            {"command": "restart_app", "target_id": 9, "config": {}}
        )
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is False
        assert "requires an active device" in args["output"]["error"]


class TestNotifyOnlyExecutor:
    """notify_only real executor (spec 2026-08-17-s27-device-command-executors P2)."""

    def test_success_reports_message(self):
        handler = _make_handler()
        handler.handle_device_command(
            {
                "command": "notify_only",
                "target_id": 5,
                "config": {"message": "recovery notice", "level": "warning"},
            }
        )
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is True
        assert args["output"]["message"] == "recovery notice"
        assert args["output"]["level"] == "warning"

    def test_missing_message_reports_error(self):
        handler = _make_handler()
        handler.handle_device_command(
            {"command": "notify_only", "target_id": 5, "config": {}}
        )
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is False
        assert "config.message" in args["output"]["error"]

    def test_default_level_info(self):
        handler = _make_handler()
        handler.handle_device_command(
            {
                "command": "notify_only",
                "target_id": 5,
                "config": {"message": "hello"},
            }
        )
        args = handler.send_callback.call_args.args[1]
        assert args["success"] is True
        assert args["output"]["level"] == "info"


class TestEngineLoadRecoveryWiring:
    """engine.load() recovery params + pipeline_name (S2-2.7 P2)."""

    def _load(self, recovery_manager=None, max_recovery_retries=0):
        engine = PipelineEngine()
        pipeline = {
            "metadata": {"pipeline_name": "daily_missions"},
            "entry_node": "n1",
            "nodes": [{"id": "n1", "type": "click", "config": {"x": 1, "y": 1}}],
        }
        engine.load(
            pipeline,
            device=MagicMock(),
            recovery_manager=recovery_manager,
            max_recovery_retries=max_recovery_retries,
        )
        return engine

    def test_sets_pipeline_name_from_metadata(self):
        engine = self._load()
        assert engine._context.pipeline_name == "daily_missions"

    def test_pipeline_name_empty_when_metadata_missing(self):
        engine = PipelineEngine()
        engine.load({"nodes": [], "entry_node": "n1"})
        assert engine._context.pipeline_name == ""

    def test_recovery_manager_injected(self):
        manager = MagicMock()
        engine = self._load(recovery_manager=manager, max_recovery_retries=2)
        assert engine._recovery_manager is manager
        assert engine._max_recovery_retries == 2

    def test_no_manager_zero_retries(self):
        engine = self._load()
        assert engine._recovery_manager is None
        assert engine._max_recovery_retries == 0

    def test_retries_forced_min_one_when_manager_present(self):
        engine = self._load(recovery_manager=MagicMock(), max_recovery_retries=0)
        assert engine._max_recovery_retries == 1


class TestOrchestratorRecoveryInjection:
    """orchestrator injects InterfaceRecoveryManager when yaml exists (S2-2.7 P3)."""

    def _orchestrator(self, config: AgentConfig):
        dm = MagicMock()
        device = MagicMock()
        device.capture_screen.return_value = MagicMock()
        dm.get_active_device.return_value = device
        dm.get_device.return_value = device
        return TaskOrchestrator(
            device_manager=dm,
            image_processor=MagicMock(),
            config=config,
        )

    def _execute(self, orch: TaskOrchestrator):
        orch.execute_pipeline(
            {
                "metadata": {"pipeline_name": "p1"},
                "entry_node": "n1",
                "nodes": [
                    {"id": "n1", "type": "click", "config": {"x": 1, "y": 1}}
                ],
            },
            device_id="dev1",
        )

    def test_manager_built_when_yaml_exists(self, tmp_path):
        yaml_path = tmp_path / "interface_states.yaml"
        yaml_path.write_text(
            "states:\n  main_menu:\n    is_safe_state: true\n", encoding="utf-8"
        )
        cfg = AgentConfig()
        cfg.interface_states_path = str(yaml_path)
        orch = self._orchestrator(cfg)

        with patch(
            "core.interface_recovery.InterfaceRecoveryManager",
        ) as mock_cls, patch(
            "engine.pipeline_engine.PipelineEngine",
        ) as mock_engine_cls:
            engine = MagicMock()
            mock_engine_cls.return_value = engine
            mock_cls.return_value = MagicMock(name="manager")
            self._execute(orch)
        mock_cls.assert_called_once()
        _, kwargs = engine.load.call_args
        assert kwargs.get("recovery_manager") is mock_cls.return_value
        assert kwargs.get("max_recovery_retries") == cfg.max_recovery_retries

    def test_no_manager_when_yaml_missing(self):
        cfg = AgentConfig()
        cfg.interface_states_path = "C:/does/not/exist.yaml"
        orch = self._orchestrator(cfg)

        with patch(
            "core.interface_recovery.InterfaceRecoveryManager",
        ) as mock_cls, patch(
            "engine.pipeline_engine.PipelineEngine",
        ) as mock_engine_cls:
            engine = MagicMock()
            mock_engine_cls.return_value = engine
            self._execute(orch)
        mock_cls.assert_not_called()
        _, kwargs = engine.load.call_args
        assert kwargs.get("recovery_manager") is None
        assert kwargs.get("max_recovery_retries") == 0

    def test_manager_init_failure_disables_recovery(self, tmp_path):
        yaml_path = tmp_path / "interface_states.yaml"
        yaml_path.write_text("states: {}\n", encoding="utf-8")
        cfg = AgentConfig()
        cfg.interface_states_path = str(yaml_path)
        orch = self._orchestrator(cfg)

        with patch(
            "core.interface_recovery.InterfaceRecoveryManager",
            side_effect=ValueError("bad yaml"),
        ) as mock_cls, patch(
            "engine.pipeline_engine.PipelineEngine",
        ) as mock_engine_cls:
            engine = MagicMock()
            mock_engine_cls.return_value = engine
            self._execute(orch)
        mock_cls.assert_called_once()
        _, kwargs = engine.load.call_args
        assert kwargs.get("recovery_manager") is None
        assert kwargs.get("max_recovery_retries") == 0
