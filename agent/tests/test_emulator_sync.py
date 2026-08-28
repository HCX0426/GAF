"""EmulatorSync unit tests.

Covers the main-control / mirror broadcast paths: master set, mirror
add/remove, sync_* broadcast operations (click/key/swipe/text_input),
enable/disable toggle, and stop_all cleanup. All device interactions
are mocked so no real device or subprocess is required.
"""

from unittest.mock import MagicMock

import pytest
from core.emulator_sync import EmulatorSync


def _make_mirror(device_id: str):
    """Build a mock mirror device exposing the BaseDevice-like interface."""
    dev = MagicMock()
    dev.device_id = device_id
    # click / key_press / swipe / text_input / disconnect all callable by default
    return dev


@pytest.fixture
def sync():
    """Fresh EmulatorSync with no master and no mirrors."""
    return EmulatorSync(master_device=None)


class TestEmulatorSyncInit:
    """Verify initial state."""

    def test_init_no_master(self, sync):
        assert sync._master_device is None
        assert sync.mirror_count == 0
        assert sync.is_enabled is True

    def test_init_with_master(self):
        master = _make_mirror("master-1")
        es = EmulatorSync(master_device=master)
        assert es._master_device is master


class TestEmulatorSyncMaster:
    """Verify set_master."""

    def test_set_master_updates_reference(self, sync):
        master = _make_mirror("master-1")
        sync.set_master(master)
        assert sync._master_device is master


class TestEmulatorSyncMirrorLifecycle:
    """Verify add/remove/get mirrors."""

    def test_add_mirror_returns_true(self, sync):
        m = _make_mirror("m1")
        assert sync.add_mirror(m) is True
        assert sync.mirror_count == 1

    def test_add_mirror_duplicate_returns_false(self, sync):
        m1 = _make_mirror("m1")
        m2 = _make_mirror("m1")  # same device_id
        sync.add_mirror(m1)
        assert sync.add_mirror(m2) is False
        assert sync.mirror_count == 1

    def test_add_mirror_without_device_id_uses_python_id(self, sync):
        # Mirrors lacking device_id fall back to str(id(device))
        # spec=[] prevents MagicMock from auto-creating the attribute, so
        # getattr(obj, 'device_id', default) returns the default.
        m = MagicMock(spec=[])
        assert sync.add_mirror(m) is True
        assert sync.mirror_count == 1

    def test_remove_mirror_returns_true(self, sync):
        sync.add_mirror(_make_mirror("m1"))
        assert sync.remove_mirror("m1") is True
        assert sync.mirror_count == 0

    def test_remove_mirror_nonexistent_returns_false(self, sync):
        assert sync.remove_mirror("nope") is False

    def test_get_mirrors_returns_list(self, sync):
        m1, m2 = _make_mirror("m1"), _make_mirror("m2")
        sync.add_mirror(m1)
        sync.add_mirror(m2)
        mirrors = sync.get_mirrors()
        assert isinstance(mirrors, list)
        assert len(mirrors) == 2
        assert m1 in mirrors and m2 in mirrors


class TestEmulatorSyncBroadcast:
    """Verify sync_* operations broadcast to every mirror."""

    def test_sync_click_calls_click_on_all_mirrors(self, sync):
        m1, m2 = _make_mirror("m1"), _make_mirror("m2")
        sync.add_mirror(m1)
        sync.add_mirror(m2)
        sync.sync_click(100, 200)
        m1.click.assert_called_once_with(100, 200)
        m2.click.assert_called_once_with(100, 200)

    def test_sync_click_when_disabled_is_noop(self, sync):
        m1 = _make_mirror("m1")
        sync.add_mirror(m1)
        sync.disable()
        sync.sync_click(10, 20)
        m1.click.assert_not_called()

    def test_sync_key_calls_key_press(self, sync):
        m1 = _make_mirror("m1")
        sync.add_mirror(m1)
        sync.sync_key("KEY_HOME")
        m1.key_press.assert_called_once_with("KEY_HOME")

    def test_sync_swipe_calls_swipe_with_duration(self, sync):
        m1 = _make_mirror("m1")
        sync.add_mirror(m1)
        sync.sync_swipe(10, 20, 30, 40, duration=500)
        m1.swipe.assert_called_once_with(10, 20, 30, 40, 500)

    def test_sync_text_input_calls_text_input(self, sync):
        m1 = _make_mirror("m1")
        sync.add_mirror(m1)
        sync.sync_text_input("hello")
        m1.text_input.assert_called_once_with("hello")

    def test_sync_click_swallows_mirror_exception(self, sync):
        # One mirror raising must not stop broadcast to the others
        bad = _make_mirror("bad")
        good = _make_mirror("good")
        bad.click.side_effect = RuntimeError("boom")
        sync.add_mirror(bad)
        sync.add_mirror(good)
        # Must not raise
        sync.sync_click(1, 2)
        good.click.assert_called_once_with(1, 2)

    def test_sync_click_skips_mirror_without_click(self, sync):
        # Mirrors missing the click attribute are silently skipped.
        # spec=[] ensures hasattr(device, 'click') is False.
        m = MagicMock(spec=[])
        sync.add_mirror(m)
        # Must not raise
        sync.sync_click(1, 2)


class TestEmulatorSyncToggleAndStop:
    """Verify enable/disable/stop_all."""

    def test_disable_then_enable(self, sync):
        assert sync.is_enabled is True
        sync.disable()
        assert sync.is_enabled is False
        sync.enable()
        assert sync.is_enabled is True

    def test_stop_all_disconnects_each_mirror(self, sync):
        m1, m2 = _make_mirror("m1"), _make_mirror("m2")
        sync.add_mirror(m1)
        sync.add_mirror(m2)
        sync.stop_all()
        m1.disconnect.assert_called_once()
        m2.disconnect.assert_called_once()
        assert sync.mirror_count == 0

    def test_stop_all_swallows_disconnect_exception(self, sync):
        m = _make_mirror("m")
        m.disconnect.side_effect = RuntimeError("nope")
        sync.add_mirror(m)
        # Must not raise
        sync.stop_all()
        assert sync.mirror_count == 0
