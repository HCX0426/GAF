"""P-011 Spec A: multi-game parallel mode unit tests.

Covers:
- resolve_device_methods: single mode (no restriction) vs multi mode (unsafe
  methods downgraded to safe defaults)
- DeviceSerializer: multi_game_restricted + allowed_*_methods fields
- unattended_start_view: multi mode refuses unsafe devices (400)
- FeatureFlag helper: flag missing defaults to False (single mode)
"""

import pytest
from django.test import TestCase
from pipeline.models import TaskChain
from rest_framework.test import APIClient
from settings.feature_flags import MULTI_GAME_MODE_FLAG, is_multi_game_mode_enabled
from settings.models import FeatureFlag

from accounts.factories import AdminUserFactory
from gamestate.models import GameProfile
from workers.factories import DeviceFactory, WorkerFactory
from workers.models import (
    MULTI_GAME_SAFE_INPUT_METHODS,
    MULTI_GAME_SAFE_SCREENSHOT_METHODS,
    Device,
    resolve_device_methods,
)
from workers.serializers import DeviceSerializer

pytestmark = pytest.mark.integration


def _set_multi_game_mode(enabled: bool) -> None:
    """Helper: toggle the multi-game mode FeatureFlag."""
    flag, _ = FeatureFlag.objects.get_or_create(
        name=MULTI_GAME_MODE_FLAG,
        defaults={'description': 'multi-game mode test', 'enabled': enabled},
    )
    flag.enabled = enabled
    flag.save()


def _make_profile(name: str = 'TestGame') -> GameProfile:
    """Create a GameProfile with a default routine (required for start view)."""
    chain = TaskChain.objects.create(name=f'{name} chain', is_enabled=True)
    return GameProfile.objects.create(
        game_name=name,
        default_task_chain=chain,
    )


class FeatureFlagHelperTest(TestCase):
    """Spec A: is_multi_game_mode_enabled() helper semantics."""

    def test_flag_missing_defaults_to_false(self):
        """Fresh install without the flag row → single mode (False)."""
        FeatureFlag.objects.filter(name=MULTI_GAME_MODE_FLAG).delete()
        self.assertFalse(is_multi_game_mode_enabled())

    def test_flag_enabled_returns_true(self):
        _set_multi_game_mode(True)
        self.assertTrue(is_multi_game_mode_enabled())

    def test_flag_disabled_returns_false(self):
        _set_multi_game_mode(False)
        self.assertFalse(is_multi_game_mode_enabled())


class ResolveDeviceMethodsTest(TestCase):
    """Spec A: resolve_device_methods whitelist enforcement.

    Method identifiers use the lowercase convention matching the frontend
    Select option values (Spec A Phase 2 case fix). A separate test
    verifies case-insensitivity for legacy CamelCase values stored via
    CONTROL_MODE_DEFAULTS.
    """

    def setUp(self):
        self.agent = WorkerFactory()
        self.profile = _make_profile('ResolveGame')
        # Windows device with sendinput (unsafe) + dxgi (unsafe screenshot).
        # Lowercase values match what the frontend Select stores.
        self.win_device = DeviceFactory(
            agent=self.agent,
            game_profile=self.profile,
            device_type=Device.DeviceType.WINDOWS,
            control_mode=Device.ControlMode.FOREGROUND,
            screenshot_method='dxgi',
            input_method='sendinput',
        )
        # Emulator device with minitouch (unsafe)
        self.emu_device = DeviceFactory(
            agent=self.agent,
            game_profile=self.profile,
            device_type=Device.DeviceType.EMULATOR,
            control_mode=Device.ControlMode.FOREGROUND,
            screenshot_method='screencap',
            input_method='minitouch',
        )

    def test_single_mode_no_restriction(self):
        """Single mode: resolve returns device methods unchanged."""
        _set_multi_game_mode(False)
        resolved = resolve_device_methods(self.win_device)
        self.assertEqual(resolved['input_method'], 'sendinput')
        self.assertEqual(resolved['screenshot_method'], 'dxgi')
        self.assertFalse(resolved['multi_game_restricted'])
        # original_* mirrors resolved values (no downgrade happened)
        self.assertEqual(resolved['original_input_method'], 'sendinput')
        self.assertEqual(resolved['original_screenshot_method'], 'dxgi')

    def test_multi_mode_downgrades_unsafe_windows(self):
        """Multi mode: sendinput → postmessage, dxgi → printwindow."""
        _set_multi_game_mode(True)
        resolved = resolve_device_methods(self.win_device)
        self.assertEqual(resolved['input_method'], 'postmessage')
        self.assertEqual(resolved['screenshot_method'], 'printwindow')
        self.assertTrue(resolved['multi_game_restricted'])
        # original_* preserves the unsafe values for diagnostics
        self.assertEqual(resolved['original_input_method'], 'sendinput')
        self.assertEqual(resolved['original_screenshot_method'], 'dxgi')

    def test_multi_mode_downgrades_unsafe_emulator(self):
        """Multi mode: minitouch → adb_input (emulator fallback)."""
        _set_multi_game_mode(True)
        resolved = resolve_device_methods(self.emu_device)
        self.assertEqual(resolved['input_method'], 'adb_input')
        # screencap is already safe, unchanged
        self.assertEqual(resolved['screenshot_method'], 'screencap')
        self.assertTrue(resolved['multi_game_restricted'])
        self.assertEqual(resolved['original_input_method'], 'minitouch')

    def test_multi_mode_preserves_safe_methods(self):
        """Multi mode: safe methods (postmessage, bitblt) unchanged."""
        _set_multi_game_mode(True)
        safe_device = DeviceFactory(
            agent=self.agent,
            game_profile=self.profile,
            device_type=Device.DeviceType.WINDOWS,
            control_mode=Device.ControlMode.BACKGROUND,
            screenshot_method='bitblt',
            input_method='postmessage',
        )
        resolved = resolve_device_methods(safe_device)
        self.assertEqual(resolved['input_method'], 'postmessage')
        self.assertEqual(resolved['screenshot_method'], 'bitblt')
        self.assertTrue(resolved['multi_game_restricted'])
        # original == resolved (no downgrade)
        self.assertEqual(resolved['original_input_method'], 'postmessage')

    def test_multi_mode_case_insensitive_match(self):
        """Phase 2 case fix: legacy CamelCase 'SendInput' also downgraded.

        CONTROL_MODE_DEFAULTS uses 'SendInput' (CamelCase) for the FOREGROUND
        mode default. A device saved via the serializer with control_mode=
        foreground and input_method='auto' ends up with input_method='SendInput'.
        The blocked-list comparison must catch this too.
        """
        _set_multi_game_mode(True)
        camel_device = DeviceFactory(
            agent=self.agent,
            game_profile=self.profile,
            device_type=Device.DeviceType.WINDOWS,
            control_mode=Device.ControlMode.FOREGROUND,
            screenshot_method='DXGI',  # CamelCase legacy
            input_method='SendInput',  # CamelCase legacy
        )
        resolved = resolve_device_methods(camel_device)
        # Both should be downgraded despite CamelCase storage
        self.assertEqual(resolved['input_method'], 'postmessage')
        self.assertEqual(resolved['screenshot_method'], 'printwindow')
        self.assertTrue(resolved['multi_game_restricted'])
        # original_* preserves the CamelCase values as-stored
        self.assertEqual(resolved['original_input_method'], 'SendInput')
        self.assertEqual(resolved['original_screenshot_method'], 'DXGI')


class DeviceSerializerMultiGameTest(TestCase):
    """Spec A: DeviceSerializer exposes multi-game whitelist fields."""

    def setUp(self):
        self.agent = WorkerFactory()
        self.device = DeviceFactory(
            agent=self.agent,
            device_type=Device.DeviceType.WINDOWS,
            control_mode=Device.ControlMode.FOREGROUND,
            input_method='sendinput',
            screenshot_method='bitblt',
        )

    def test_single_mode_allowed_methods_none(self):
        """Single mode: allowed_*_methods is None (no restriction)."""
        _set_multi_game_mode(False)
        serializer = DeviceSerializer(self.device)
        data = serializer.data
        self.assertFalse(data['multi_game_restricted'])
        self.assertIsNone(data['allowed_screenshot_methods'])
        self.assertIsNone(data['allowed_input_methods'])

    def test_multi_mode_allowed_methods_populated(self):
        """Multi mode: allowed_*_methods returns sorted whitelist."""
        _set_multi_game_mode(True)
        serializer = DeviceSerializer(self.device)
        data = serializer.data
        self.assertTrue(data['multi_game_restricted'])
        self.assertEqual(
            data['allowed_screenshot_methods'],
            sorted(MULTI_GAME_SAFE_SCREENSHOT_METHODS),
        )
        self.assertEqual(
            data['allowed_input_methods'],
            sorted(MULTI_GAME_SAFE_INPUT_METHODS),
        )

    def test_multi_mode_resolved_methods_includes_downgrade(self):
        """Multi mode: resolved_methods shows downgraded values + originals."""
        _set_multi_game_mode(True)
        serializer = DeviceSerializer(self.device)
        resolved = serializer.data['resolved_methods']
        # sendinput downgraded to postmessage
        self.assertEqual(resolved['input_method'], 'postmessage')
        self.assertEqual(resolved['original_input_method'], 'sendinput')
        self.assertTrue(resolved['multi_game_restricted'])


class UnattendedStartMultiGameTest(TestCase):
    """Spec A: unattended_start_view refuses unsafe devices in multi mode."""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.agent = WorkerFactory(status='online')
        self.profile = _make_profile('StartGame')

    def test_multi_mode_rejects_unsafe_device(self):
        """Multi mode: start with sendinput device → 400.

        Device has no game_account so the dispatch loop would skip it
        anyway, but the safety check runs *before* the dispatch loop and
        must reject the request outright.
        """
        _set_multi_game_mode(True)
        DeviceFactory(
            agent=self.agent,
            game_profile=self.profile,
            device_type=Device.DeviceType.WINDOWS,
            status=Device.Status.ONLINE,
            control_mode=Device.ControlMode.FOREGROUND,
            input_method='sendinput',  # unsafe (lowercase, frontend convention)
        )
        resp = self.client.post(
            '/api/v2/scheduler/unattended/start/',
            {'game_profile_id': self.profile.id},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['code'], 'unsafe_method_for_multi_game')
        self.assertIn('devices', resp.json())

    def test_multi_mode_allows_safe_device(self):
        """Multi mode: start with postmessage device → passes safety check.

        Device has no game_account so dispatch loop skips it (skipped=[...]),
        but the safety check passes and the view returns 200.
        """
        _set_multi_game_mode(True)
        DeviceFactory(
            agent=self.agent,
            game_profile=self.profile,
            device_type=Device.DeviceType.WINDOWS,
            status=Device.Status.ONLINE,
            control_mode=Device.ControlMode.BACKGROUND,
            input_method='postmessage',  # safe
        )
        resp = self.client.post(
            '/api/v2/scheduler/unattended/start/',
            {'game_profile_id': self.profile.id},
            format='json',
        )
        # Safety check passed (200) even though device was skipped in dispatch
        self.assertEqual(resp.status_code, 200)

    def test_single_mode_allows_unsafe_device(self):
        """Single mode: start with sendinput device → no safety check."""
        _set_multi_game_mode(False)
        DeviceFactory(
            agent=self.agent,
            game_profile=self.profile,
            device_type=Device.DeviceType.WINDOWS,
            status=Device.Status.ONLINE,
            control_mode=Device.ControlMode.FOREGROUND,
            input_method='sendinput',
        )
        resp = self.client.post(
            '/api/v2/scheduler/unattended/start/',
            {'game_profile_id': self.profile.id},
            format='json',
        )
        # Single mode: no safety check, dispatch proceeds (device skipped
        # due to no game_account, but view returns 200)
        self.assertEqual(resp.status_code, 200)
