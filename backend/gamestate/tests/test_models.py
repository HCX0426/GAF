"""Tests for gamestate.models (model layer, DB-backed).

Models under test: GameProfile, GameStateRule, GameStateSnapshot,
GameVersionCheck.
"""

from django.test import TestCase

from gamestate.models import (
    GameProfile,
    GameStateRule,
    GameStateSnapshot,
    GameVersionCheck,
)
from resources.models import ResourcePack


def _make_resource_pack(name='Pack1', version='1.0'):
    return ResourcePack.objects.create(
        name=name, version=version, directory_path='/tmp/pack',
    )


class GameProfileModelTests(TestCase):
    """GameProfile model: creation, defaults, __str__, unique, ordering."""

    def test_create_with_defaults(self):
        profile = GameProfile.objects.create(game_name='GameA')
        self.assertEqual(profile.screenshot_methods, [])
        self.assertEqual(profile.ocr_language, 'ch')
        self.assertEqual(profile.ui_reference_resolution, {})
        self.assertEqual(profile.known_popups, [])
        self.assertEqual(profile.resolution_strategy, 'scale')
        self.assertIsNotNone(profile.created_at)
        self.assertIsNotNone(profile.updated_at)

    def test_str_representation(self):
        profile = GameProfile.objects.create(game_name='My Game')
        self.assertEqual(str(profile), 'My Game')

    def test_game_name_unique(self):
        GameProfile.objects.create(game_name='UniqueGame')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            GameProfile.objects.create(game_name='UniqueGame')

    def test_ordering_by_game_name(self):
        GameProfile.objects.create(game_name='Zelda')
        GameProfile.objects.create(game_name='Asteroids')
        names = list(GameProfile.objects.values_list('game_name', flat=True))
        self.assertEqual(names, ['Asteroids', 'Zelda'])


class GameStateRuleModelTests(TestCase):
    """GameStateRule model: creation, defaults, __str__, ordering."""

    def test_create_with_defaults(self):
        rule = GameStateRule.objects.create(
            name='HP Check', game_name='GameA', tracker_type='ocr',
        )
        self.assertEqual(rule.ocr_region, {})
        self.assertEqual(rule.ocr_regex, '')
        self.assertIsNone(rule.threshold)
        self.assertEqual(rule.threshold_direction, '')
        self.assertEqual(rule.trigger_action, {})
        self.assertTrue(rule.is_active)

    def test_str_representation(self):
        rule = GameStateRule.objects.create(
            name='Mana Rule', game_name='GameX', tracker_type='ocr',
        )
        self.assertEqual(str(rule), 'Mana Rule (GameX)')


class GameStateSnapshotModelTests(TestCase):
    """GameStateSnapshot model: creation, defaults, __str__, FK cascade."""

    def setUp(self):
        self.rule = GameStateRule.objects.create(
            name='Test Rule', game_name='GameA', tracker_type='ocr',
        )

    def test_create_with_defaults(self):
        snap = GameStateSnapshot.objects.create(rule=self.rule, value=42.5)
        self.assertEqual(snap.raw_text, '')
        self.assertFalse(snap.triggered)
        self.assertIsNotNone(snap.created_at)

    def test_str_triggered(self):
        snap = GameStateSnapshot.objects.create(
            rule=self.rule, value=10, triggered=True,
        )
        self.assertIn('Test Rule', str(snap))

    def test_cascade_delete_rule_deletes_snapshots(self):
        snap = GameStateSnapshot.objects.create(rule=self.rule, value=1)
        snap_id = snap.id
        self.rule.delete()
        self.assertFalse(GameStateSnapshot.objects.filter(id=snap_id).exists())


class GameVersionCheckModelTests(TestCase):
    """GameVersionCheck model: creation, defaults, __str__, FK cascade."""

    def setUp(self):
        self.pack = _make_resource_pack()

    def test_create_with_defaults(self):
        check = GameVersionCheck.objects.create(
            game_name='GameA',
            resource_pack=self.pack,
            previous_version_hash='a' * 64,
            current_version_hash='b' * 64,
        )
        self.assertEqual(check.files_changed, [])
        self.assertIsNotNone(check.detected_at)

    def test_str_representation(self):
        check = GameVersionCheck.objects.create(
            game_name='GameA',
            resource_pack=self.pack,
            previous_version_hash='a' * 64,
            current_version_hash='b' * 64,
        )
        self.assertIn('GameA', str(check))

    def test_cascade_delete_pack_deletes_check(self):
        check = GameVersionCheck.objects.create(
            game_name='GameA',
            resource_pack=self.pack,
            previous_version_hash='a' * 64,
            current_version_hash='b' * 64,
        )
        check_id = check.id
        self.pack.delete()
        self.assertFalse(GameVersionCheck.objects.filter(id=check_id).exists())
