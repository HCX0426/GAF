"""Tests for agent handle_task_assign resource_pack switching.

Verifies that MessageHandler.handle_task_assign reads the ``resource_pack``
field from the task-assign payload and delegates to
``MonitorManager.switch_resource_pack`` so the agent runs the correct
monitor rules for the assigned game profile. When ``resource_pack`` is
None the switch must be skipped.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure src on path (conftest already does this, but be explicit for direct runs)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from client.handler import MessageHandler

pytestmark = pytest.mark.unit


class TestHandleTaskAssignResourcePack:
    """Verify agent switches resource_pack when present."""

    def test_switches_resource_pack_when_present(self):
        """handle_task_assign should call switch_resource_pack when data has it."""
        handler = MessageHandler(MagicMock())
        data = {
            "execution_id": "exec-1",
            "task_id": 1,
            "task_name": "test",
            "task_definition": {},
            "execution_mode": "pipeline",
            "device_info": {"id": 1, "name": "d", "device_type": "windows"},
            "game_account_id": 123,
            "game_account_name": "acct",
            "resource_pack": {
                "id": 1,
                "name": "BD2-v1",
                "directory_path": "resources/BrownDust-II/v1",
                "config_data": {},
            },
        }
        # Stub _resolve_target_device to return None so the handler aborts
        # after the resource_pack switch and does not spawn a run thread.
        with patch.object(handler, "_orchestrator") as mock_orch, \
             patch.object(handler, "_resolve_target_device", return_value=None), \
             patch.object(handler, "_send_to_server"):
            handler.handle_task_assign(data)
            mock_orch._monitor_manager.switch_resource_pack.assert_called_once_with("BD2-v1")

    def test_skips_switch_when_resource_pack_none(self):
        """handle_task_assign should skip switch when resource_pack is None."""
        handler = MessageHandler(MagicMock())
        data = {
            "execution_id": "exec-1",
            "task_id": 1,
            "task_name": "test",
            "task_definition": {},
            "execution_mode": "pipeline",
            "device_info": {"id": 1, "name": "d", "device_type": "windows"},
            "game_account_id": None,
            "game_account_name": None,
            "resource_pack": None,
        }
        with patch.object(handler, "_orchestrator") as mock_orch, \
             patch.object(handler, "_resolve_target_device", return_value=None), \
             patch.object(handler, "_send_to_server"):
            handler.handle_task_assign(data)
            mock_orch._monitor_manager.switch_resource_pack.assert_not_called()

    def test_skips_switch_when_resource_pack_missing_name(self):
        """handle_task_assign should skip switch when resource_pack has no name."""
        handler = MessageHandler(MagicMock())
        data = {
            "execution_id": "exec-1",
            "task_id": 1,
            "task_name": "test",
            "task_definition": {},
            "execution_mode": "pipeline",
            "device_info": {"id": 1, "name": "d", "device_type": "windows"},
            "resource_pack": {"id": 1, "name": "", "directory_path": "x"},
        }
        with patch.object(handler, "_orchestrator") as mock_orch, \
             patch.object(handler, "_resolve_target_device", return_value=None), \
             patch.object(handler, "_send_to_server"):
            handler.handle_task_assign(data)
            mock_orch._monitor_manager.switch_resource_pack.assert_not_called()

    def test_switch_failure_is_non_fatal(self):
        """handle_task_assign should not raise when switch_resource_pack raises."""
        handler = MessageHandler(MagicMock())
        data = {
            "execution_id": "exec-1",
            "task_id": 1,
            "task_name": "test",
            "task_definition": {},
            "execution_mode": "pipeline",
            "device_info": {"id": 1, "name": "d", "device_type": "windows"},
            "resource_pack": {"id": 1, "name": "BD2-v1"},
        }
        with patch.object(handler, "_orchestrator") as mock_orch, \
             patch.object(handler, "_resolve_target_device", return_value=None), \
             patch.object(handler, "_send_to_server"):
            mock_orch._monitor_manager.switch_resource_pack.side_effect = RuntimeError("boom")
            # Must not raise
            handler.handle_task_assign(data)
            mock_orch._monitor_manager.switch_resource_pack.assert_called_once_with("BD2-v1")

    def test_skips_switch_when_monitor_manager_none(self):
        """handle_task_assign should skip switch when _monitor_manager is None."""
        handler = MessageHandler(MagicMock())
        data = {
            "execution_id": "exec-1",
            "task_id": 1,
            "task_name": "test",
            "task_definition": {},
            "execution_mode": "pipeline",
            "device_info": {"id": 1, "name": "d", "device_type": "windows"},
            "resource_pack": {"id": 1, "name": "BD2-v1"},
        }
        # Simulate orchestrator without _monitor_manager injected
        orchestrator = MagicMock()
        orchestrator._monitor_manager = None
        with patch.object(handler, "_orchestrator", orchestrator), \
             patch.object(handler, "_resolve_target_device", return_value=None), \
             patch.object(handler, "_send_to_server"):
            # Must not raise AttributeError
            handler.handle_task_assign(data)
