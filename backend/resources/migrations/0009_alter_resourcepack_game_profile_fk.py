"""R37-P3 Stage 7 Task 20b: repoint ResourcePack.game_profile FK to gamestate.

STATE-ONLY migration (SeparateDatabaseAndState with empty database_operations).

ResourcePack.game_profile FK changes from 'tasks.GameProfile' to
'gamestate.GameProfile' at the Django state level. The physical FK constraint
in the DB still references the `game_profile` table (unchanged db_table), so
no DB operation is needed.

Depends on gamestate/0003_gameprofile so gamestate.GameProfile exists in state
before the FK is repointed.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gamestate', '0003_gameprofile'),
        ('resources', '0008_templateeffectiveness'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='resourcepack',
                    name='game_profile',
                    field=models.ForeignKey(
                        blank=True,
                        help_text='R37-P1: 资源包所属的游戏档案（nullable，兼容老资源包）',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='resource_packs',
                        to='gamestate.gameprofile',
                        verbose_name='所属游戏档案',
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
