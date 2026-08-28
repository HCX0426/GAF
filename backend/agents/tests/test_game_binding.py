"""TD-333: device_type_hint 接入 bind_game_profile_by_title 的过滤逻辑测试。

验证:
- 优先匹配 device_type_hint 相同的 GameProfile
- 其次匹配 hint='' 的 (兼容旧数据)
- 排除冲突 hint (hint=windows 但 gp.hint=emulator)
- 不传 hint 时行为不变 (向后兼容)
- backfill 传 device.device_type
"""

import pytest
from django.test import TestCase

from agents.game_binding import (
    backfill_game_profile_links,
    bind_game_profile_by_target_app,
    bind_game_profile_by_title,
)
from agents.models import Device
from gamestate.models import GameProfile

pytestmark = pytest.mark.integration


def _make_profile(game_name, hint=''):
    """Helper: 创建一个 GameProfile."""
    return GameProfile.objects.create(
        game_name=game_name,
        screenshot_methods=[],
        device_type_hint=hint,
    )


class TestBindPrefersMatchingHint(TestCase):
    """优先匹配 hint 相同的 GameProfile."""

    def test_two_profiles_same_title_different_hint_windows_query(self):
        """window_title 同时含两个 gp 名, hint='windows' 应返回 windows 的."""
        gp_win = _make_profile('BrownDust II', hint='windows')
        gp_emu = _make_profile('BrownDust II LDPlayer', hint='emulator')

        # window_title 同时含两个 gp 名字子串
        result = bind_game_profile_by_title(
            'BrownDust II LDPlayer - Neowiz',
            device_type_hint='emulator',
        )
        self.assertEqual(result.id, gp_emu.id)

        # 反向查询 windows
        result = bind_game_profile_by_title(
            'BrownDust II - Steam',
            device_type_hint='windows',
        )
        self.assertEqual(result.id, gp_win.id)

    def test_hint_query_skips_conflicting_profile(self):
        """只有冲突 hint 的 gp 时, 返回 None 而非错误绑定."""
        _make_profile('SomeGame', hint='emulator')
        result = bind_game_profile_by_title(
            'SomeGame Window',
            device_type_hint='windows',
        )
        self.assertIsNone(result)


class TestBindFallsBackToEmptyHint(TestCase):
    """兼容旧数据: hint='' 的 gp 能被任意 hint 调用匹配."""

    def test_empty_hint_matches_windows_query(self):
        gp = _make_profile('LegacyGame', hint='')
        result = bind_game_profile_by_title(
            'LegacyGame Launcher',
            device_type_hint='windows',
        )
        self.assertEqual(result.id, gp.id)

    def test_empty_hint_matches_emulator_query(self):
        gp = _make_profile('LegacyGame', hint='')
        result = bind_game_profile_by_title(
            'LegacyGame',
            device_type_hint='emulator',
        )
        self.assertEqual(result.id, gp.id)

    def test_matching_hint_beats_empty_hint(self):
        """同时存在 hint 相同 + hint='' 的 gp 时, 优先 hint 相同的."""
        gp_match = _make_profile('DualGame', hint='windows')
        _gp_empty = _make_profile('DualGame Plus', hint='')  # created for tie-behavior, not referenced
        # window_title 同时含两个名字
        result = bind_game_profile_by_title(
            'DualGame Plus',
            device_type_hint='windows',
        )
        # 两个 gp 都能匹配 (game_name='DualGame Plus' 是 gp_empty 的全名, 也是 gp_match 的前缀子串)
        # 优先匹配 hint 相同的 gp_match
        self.assertEqual(result.id, gp_match.id)


class TestBindWithoutHintKeepsLegacyBehavior(TestCase):
    """不传 hint 时行为不变 (向后兼容)."""

    def test_no_hint_matches_any_profile(self):
        gp = _make_profile('LegacyGame', hint='emulator')
        result = bind_game_profile_by_title('LegacyGame Title')
        self.assertEqual(result.id, gp.id)

    def test_no_hint_returns_none_on_no_match(self):
        _make_profile('Whatever', hint='')
        result = bind_game_profile_by_title('Totally Unrelated Title')
        self.assertIsNone(result)

    def test_empty_window_title_returns_none(self):
        _make_profile('Whatever', hint='')
        result = bind_game_profile_by_title('')
        self.assertIsNone(result)


class TestBindTargetAppAlsoFiltersByHint(TestCase):
    """bind_game_profile_by_target_app 同样按 hint 过滤."""

    def test_target_app_filters_by_hint(self):
        _gp_win = _make_profile('TargetGame', hint='windows')
        gp_emu = _make_profile('TargetGame Emu', hint='emulator')

        result = bind_game_profile_by_target_app(
            'TargetGame Emu',
            device_type_hint='emulator',
        )
        self.assertEqual(result.id, gp_emu.id)

    def test_target_app_empty_hint_fallback(self):
        gp = _make_profile('LegacyTarget', hint='')
        result = bind_game_profile_by_target_app(
            'LegacyTarget',
            device_type_hint='windows',
        )
        self.assertEqual(result.id, gp.id)


class TestBackfillPassesDeviceTypeHint(TestCase):
    """backfill_game_profile_links 应传 device.device_type 给 bind."""

    def test_backfill_uses_device_type_to_pick_correct_profile(self):
        """device_type=emulator 的设备, 应绑到 hint='emulator' 的 gp."""
        gp_win = _make_profile('DualGame', hint='windows')
        gp_emu = _make_profile('DualGame Emu', hint='emulator')

        # 两个 device 同名 window_title, 但 device_type 不同
        # extra_info.window_title 设为同时含两个 gp 名字的串, 让 hint 决定
        Device.objects.create(
            name='Win-PC',
            device_type=Device.DeviceType.WINDOWS,
            status=Device.Status.OFFLINE,
            extra_info={'window_title': 'DualGame Emu'},  # 都能匹配
        )
        Device.objects.create(
            name='Emu-PC',
            device_type=Device.DeviceType.EMULATOR,
            status=Device.Status.OFFLINE,
            extra_info={'window_title': 'DualGame Emu'},
        )

        counts = backfill_game_profile_links()
        self.assertEqual(counts['devices'], 2)

        win_dev = Device.objects.get(name='Win-PC')
        emu_dev = Device.objects.get(name='Emu-PC')
        # Win-PC 应绑到 gp_win (hint='windows')
        # 但 window_title='DualGame Emu' 只能子串匹配 gp_emu (game_name='DualGame Emu')
        # 而 gp_win.game_name='DualGame' 是 window_title 的子串, 也能匹配
        # 按 hint 优先, Win-PC 应绑 gp_win
        self.assertEqual(win_dev.game_profile_id, gp_win.id)
        self.assertEqual(emu_dev.game_profile_id, gp_emu.id)
