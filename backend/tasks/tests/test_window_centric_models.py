"""Tests for window-centric task binding model changes (Stage 1)."""
import pytest
from django.test import TestCase
from pipeline.models import TaskChain
from workers.models import Device

from accounts.models import GameAccount
from gamestate.models import GameProfile
from tasks.models import Task, TaskDevice, TaskExecution


class TaskDeadFieldsRemovedTest(TestCase):
    """Verify dead fields are removed from Task model."""

    def test_task_has_no_game_account_single_fk(self):
        """Task.game_account (single FK) should be removed."""
        task_fields = {f.name for f in Task._meta.get_fields()}
        assert 'game_account' not in task_fields, (
            "Task.game_account (single FK) should be removed — "
            "M2M game_accounts already replaces it"
        )

    def test_task_has_resource_pack_fk(self):
        """Task.resource_pack (FK) should be present — N197-8 direct association."""
        task_fields = {f.name for f in Task._meta.get_fields()}
        assert 'resource_pack' in task_fields, (
            "Task.resource_pack FK should be present — "
            "N197-8: tasks directly associate with a resource pack"
        )

    def test_task_retains_game_profile_fk(self):
        """Task.game_profile should be retained for grouping/filtering."""
        task_fields = {f.name for f in Task._meta.get_fields()}
        assert 'game_profile' in task_fields

    def test_task_retains_game_accounts_m2m(self):
        """Task.game_accounts (M2M) should be retained as optional whitelist."""
        task_fields = {f.name for f in Task._meta.get_fields()}
        assert 'game_accounts' in task_fields


class TaskDeviceDeadFieldsRemovedTest(TestCase):
    """Verify is_default is removed from TaskDevice."""

    def test_task_device_has_no_is_default(self):
        """TaskDevice.is_default should be removed — dead field."""
        fields = {f.name for f in TaskDevice._meta.get_fields()}
        assert 'is_default' not in fields, (
            "TaskDevice.is_default should be removed — "
            "no filter(is_default=True) exists in codebase"
        )


class GameAccountFieldsTest(TestCase):
    """Verify GameAccount field changes."""

    def test_game_account_has_game_profile_fk(self):
        """GameAccount should have game_profile FK for explicit ownership."""
        fields = {f.name for f in GameAccount._meta.get_fields()}
        assert 'game_profile' in fields, (
            "GameAccount.game_profile FK should be added — "
            "replaces game_name string weak association"
        )

    def test_game_account_has_no_allowed_resource_packs(self):
        """GameAccount.allowed_resource_packs (M2M) should be removed — dead field."""
        fields = {f.name for f in GameAccount._meta.get_fields()}
        assert 'allowed_resource_packs' not in fields, (
            "GameAccount.allowed_resource_packs should be removed — "
            "named 'allowed' but never enforced at execution"
        )

    def test_game_account_retains_resource_pack_fk(self):
        """GameAccount.resource_pack should be retained and used in dispatch."""
        fields = {f.name for f in GameAccount._meta.get_fields()}
        assert 'resource_pack' in fields


class DeviceFieldsTest(TestCase):
    """Verify Device field changes."""

    def test_device_has_game_account_fk(self):
        """Device should have game_account FK for runtime binding."""
        fields = {f.name for f in Device._meta.get_fields()}
        assert 'game_account' in fields, (
            "Device.game_account FK should be added — "
            "runtime binding to currently executing account"
        )

    def test_device_retains_game_profile_fk(self):
        """Device.game_profile should be retained (R37-P1)."""
        fields = {f.name for f in Device._meta.get_fields()}
        assert 'game_profile' in fields


class TaskChainFieldsTest(TestCase):
    """Verify TaskChain field changes."""

    def test_task_chain_has_game_profile_fk(self):
        """TaskChain should have game_profile FK for ownership."""
        fields = {f.name for f in TaskChain._meta.get_fields()}
        assert 'game_profile' in fields

    def test_task_chain_has_is_default(self):
        """TaskChain should have is_default BooleanField."""
        fields = {f.name for f in TaskChain._meta.get_fields()}
        assert 'is_default' in fields

    def test_is_default_defaults_to_false(self):
        """New TaskChain should default is_default=False."""
        chain = TaskChain.objects.create(name='test-chain')
        assert chain.is_default is False

    def test_clean_allows_is_default_true_when_no_conflict(self):
        """clean() should allow is_default=True when no other default exists."""
        profile = GameProfile.objects.create(game_name='test-game')
        chain = TaskChain.objects.create(name='chain-1', game_profile=profile, is_default=True)
        chain.clean()  # Should not raise

    def test_clean_rejects_second_is_default_in_same_profile(self):
        """clean() should reject is_default=True when another default exists in same GameProfile."""
        from django.core.exceptions import ValidationError
        profile = GameProfile.objects.create(game_name='test-game-2')
        TaskChain.objects.create(name='chain-1', game_profile=profile, is_default=True)
        chain2 = TaskChain(name='chain-2', game_profile=profile, is_default=True)
        with pytest.raises(ValidationError):
            chain2.clean()

    def test_clean_allows_multiple_defaults_in_different_profiles(self):
        """clean() should allow is_default=True in different GameProfiles."""
        profile1 = GameProfile.objects.create(game_name='game-a')
        profile2 = GameProfile.objects.create(game_name='game-b')
        chain1 = TaskChain.objects.create(name='chain-a', game_profile=profile1, is_default=True)
        chain2 = TaskChain.objects.create(name='chain-b', game_profile=profile2, is_default=True)
        chain1.clean()  # Should not raise
        chain2.clean()  # Should not raise

    def test_clean_allows_multiple_non_default_in_same_profile(self):
        """clean() should allow multiple is_default=False in same GameProfile."""
        profile = GameProfile.objects.create(game_name='test-game-3')
        chain1 = TaskChain.objects.create(name='chain-1', game_profile=profile, is_default=False)
        chain2 = TaskChain.objects.create(name='chain-2', game_profile=profile, is_default=False)
        chain1.clean()  # Should not raise
        chain2.clean()  # Should not raise

    def test_clean_excludes_self_when_updating(self):
        """clean() should exclude self when checking for existing defaults (update path)."""
        profile = GameProfile.objects.create(game_name='test-game-4')
        chain = TaskChain.objects.create(name='chain-1', game_profile=profile, is_default=True)
        # Updating the same chain should not trigger ValidationError
        chain.clean()  # Should not raise (excludes self by pk)


class GameProfileDefaultsTest(TestCase):
    """Verify GameProfile default fields."""

    def test_has_default_task_chain_fk(self):
        fields = {f.name for f in GameProfile._meta.get_fields()}
        assert 'default_task_chain' in fields

    def test_has_default_screenshot_method(self):
        fields = {f.name for f in GameProfile._meta.get_fields()}
        assert 'default_screenshot_method' in fields

    def test_has_default_input_method(self):
        fields = {f.name for f in GameProfile._meta.get_fields()}
        assert 'default_input_method' in fields

    def test_has_default_control_mode(self):
        fields = {f.name for f in GameProfile._meta.get_fields()}
        assert 'default_control_mode' in fields

    def test_control_mode_choices(self):
        """control_mode should accept foreground/background/pseudo_background."""
        profile = GameProfile.objects.create(
            game_name='test-game-defaults',
            default_control_mode='background',
        )
        assert profile.default_control_mode == 'background'


class TaskExecutionFieldsTest(TestCase):
    """Verify TaskExecution has game_account + device FK (Window-centric)."""

    def test_task_execution_has_game_account_fk(self):
        """TaskExecution.game_account FK should exist — dispatch_task reads
        resource_pack from here (landing the dead GameAccount.resource_pack FK)."""
        fields = {f.name for f in TaskExecution._meta.get_fields()}
        assert 'game_account' in fields, (
            "TaskExecution.game_account FK should be added — "
            "dispatch_task reads resource_pack from here"
        )

    def test_task_execution_has_device_fk(self):
        """TaskExecution.device FK should exist — records which device executed
        this run, replacing the legacy task.device_mappings guess."""
        fields = {f.name for f in TaskExecution._meta.get_fields()}
        assert 'device' in fields, (
            "TaskExecution.device FK should be added — "
            "records which device executed this run"
        )


class DeadCodeCleanupTest(TestCase):
    """Verify dead code from deleted fields is cleaned up (task 1.10).

    Task.resource_pack (FK) and Task.game_account (single FK) were deleted
    in task 1.1. Any code referencing these fields must be cleaned up —
    leaving them causes AttributeError at runtime.
    """

    def test_game_binding_no_task_resource_pack_ref(self):
        """workers/game_binding.py should not reference Task.resource_pack."""
        import pathlib
        # Resolve relative to this test file so the test works regardless of
        # whether pytest is invoked from the repo root or from backend/.
        # __file__ = backend/tasks/tests/test_window_centric_models.py
        backend_dir = pathlib.Path(__file__).resolve().parent.parent.parent
        path = backend_dir / 'workers' / 'game_binding.py'
        content = path.read_text(encoding='utf-8')
        assert 'task.resource_pack' not in content, (
            "workers/game_binding.py should not reference task.resource_pack — "
            "field was deleted in task 1.1"
        )
        assert "'resource_pack'" not in content, (
            "workers/game_binding.py should not save resource_pack — "
            "field was deleted in task 1.1"
        )

    def test_scheduler_engine_no_dead_select_related(self):
        """scheduler/engine.py should not select_related('game_account') on Task."""
        import pathlib
        backend_dir = pathlib.Path(__file__).resolve().parent.parent.parent
        path = backend_dir / 'scheduler' / 'engine.py'
        content = path.read_text(encoding='utf-8')
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'select_related' in line and 'game_account' in line:
                # Check context: if it's a Task query, it's dead (single FK deleted)
                ctx = '\n'.join(lines[max(0, i-3):i+1])
                if 'Task.objects' in ctx or 'enabled_tasks' in ctx:
                    pytest.fail(
                        f"scheduler/engine.py line {i+1}: dead select_related('game_account') "
                        f"on Task (single FK deleted in task 1.1)"
                    )

    def test_backfill_game_profile_links_runs_without_error(self):
        """backfill_game_profile_links() should run without AttributeError."""
        from workers.game_binding import backfill_game_profile_links
        # Should not raise even with empty DB
        result = backfill_game_profile_links()
        assert isinstance(result, dict)
        assert set(result.keys()) >= {'devices', 'resource_packs', 'tasks'}
