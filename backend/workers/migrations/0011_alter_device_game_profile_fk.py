"""R37-P3 Stage 7 Task 20b: repoint Device.game_profile FK to gamestate.

STATE-ONLY migration (SeparateDatabaseAndState with empty database_operations).

Device.game_profile FK changes from 'tasks.GameProfile' to 'gamestate.GameProfile'
at the Django state level. The physical FK constraint in the DB still references
the `game_profile` table (unchanged db_table), so no DB operation is needed.

Depends on gamestate/0003_gameprofile so gamestate.GameProfile exists in state
before the FK is repointed.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('workers', '0010_r37_p1_game_profile_fk'),
        ('gamestate', '0003_gameprofile'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name='device',
                    name='game_profile',
                    field=models.ForeignKey(
                        blank=True,
                        help_text='R37-P1: 设备所属的游戏档案（nullable，兼容未识别窗口）',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='devices',
                        to='gamestate.gameprofile',
                        verbose_name='所属游戏档案',
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
