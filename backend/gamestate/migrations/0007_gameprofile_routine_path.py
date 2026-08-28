"""Add GameProfile.routine_path field (TD-113).

Previously `convert_routine_to_chain` hardcoded `resources/<game>/routine.json`,
so a GameProfile could only bind to one routine file per game. TD-113 adds an
explicit `routine_path` CharField so each GameProfile can point at its own
routine.json (e.g. different routine per account strategy).

Data migration: existing GameProfile rows are back-filled with
`resources/<game_name>/routine.json` to preserve the prior hardcoded behavior
for the only known game (BrownDust-II). Rows whose routine file does not
exist get an empty string (no routine configured).
"""
from django.db import migrations, models


def populate_routine_path(apps, schema_editor):
    """Back-fill routine_path from game_name for existing GameProfile rows.

    Sets `resources/<game_name>/routine.json` only when that file exists on
    disk (relative to the repo root). Otherwise leaves routine_path empty.
    """
    import os
    GameProfile = apps.get_model('gamestate', 'GameProfile')
    # Migration file lives at <repo>/backend/gamestate/migrations/0007_*.py,
    # so parents[3] = <repo>. Robust to cwd differences.
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    for profile in GameProfile.objects.all():
        candidate = f'resources/{profile.game_name}/routine.json'
        abs_path = os.path.join(repo_root, candidate.replace('/', os.sep))
        if os.path.isfile(abs_path):
            profile.routine_path = candidate
        else:
            profile.routine_path = ''
        profile.save(update_fields=['routine_path'])


def reverse_populate(apps, schema_editor):
    """Reverse is a no-op — field is being removed by RemoveField."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('gamestate', '0006_delete_screen_state'),
    ]

    operations = [
        migrations.AddField(
            model_name='gameprofile',
            name='routine_path',
            field=models.CharField(
                blank=True,
                default='',
                help_text='TD-113: 该档案对应的 routine.json 文件路径，'
                          '如 resources/BrownDust-II/routine.json。'
                          'convert_routine_to_chain 从此字段读取，'
                          '支持多 GameProfile 指向不同 routine.json',
                max_length=500,
                verbose_name='routine.json 路径',
            ),
        ),
        migrations.RunPython(populate_routine_path, reverse_populate),
    ]
