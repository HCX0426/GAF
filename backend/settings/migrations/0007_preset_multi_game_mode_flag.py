"""P-011 Spec A: preset the multi-game parallel mode FeatureFlag row.

Seeds ``unattended_multi_game_mode`` so operators can toggle multi-game
parallel mode from the FeatureFlag admin / API without writing SQL. The
flag defaults to ``enabled=False`` (single-game mode) to preserve the
legacy behavior of existing deployments until an admin explicitly opts in.

Idempotent: the row is created via ``get_or_create`` so re-running the
migration (or running it on a DB where the row already exists) is a no-op.
The reverse migration deliberately does NOT delete the row — operators
may have tuned ``enabled`` and we must not wipe their configuration.
"""

from django.db import migrations


def preset_multi_game_mode_flag(apps, schema_editor):
    """Create the multi-game mode FeatureFlag row if it does not yet exist."""
    FeatureFlag = apps.get_model('settings', 'FeatureFlag')

    FeatureFlag.objects.get_or_create(
        name='unattended_multi_game_mode',
        defaults={
            'description': (
                'Enable multi-game parallel mode. When enabled, Device '
                'input/screenshot methods are restricted to parallel-safe '
                'whitelist (PostMessage/SendMessage + adb_input for input; '
                'PrintWindow/BitBlt/WGC + screencap for screenshot). '
                'Unsafe methods (SendInput, PseudoBackground, DXGI, '
                'minitouch, MaaTouch) are downgraded automatically. '
                'See docs/specs/archived/ (multi-game-mode-switch spec, archived).'
            ),
            'enabled': False,
        },
    )


def reverse_preset_multi_game_mode_flag(apps, schema_editor):
    """No-op reverse: do not delete the operator-tuned flag."""
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0006_preset_ai_feature_flags'),
    ]

    operations = [
        migrations.RunPython(
            preset_multi_game_mode_flag,
            reverse_code=reverse_preset_multi_game_mode_flag,
        ),
    ]
