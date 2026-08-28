"""R37-P3 Stage 7 Task 20b: remove GameProfile from tasks, repoint Task FK.

STATE-ONLY migration (SeparateDatabaseAndState with empty database_operations).

Two state operations (order matters):
1. AlterField Task.game_profile — repoint FK from 'tasks.GameProfile' to
   'gamestate.GameProfile'. Must happen BEFORE DeleteModel so the FK still
   has a valid target during state transition.
2. DeleteModel GameProfile — remove the model from tasks app state.

Physical DB unchanged:
- game_profile table stays (owned by gamestate app now, same db_table).
- task_game_profile_id FK constraint still references game_profile(id).
- No data migration, no constraint rebuild.

Depends on gamestate/0003_gameprofile so gamestate.GameProfile exists in
state before Task.game_profile FK is repointed.

Companion migrations:
- agents/0011_alter_device_game_profile_fk — repoints Device.game_profile FK
- resources/0009_alter_resourcepack_game_profile_fk — repoints ResourcePack FK
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gamestate', '0003_gameprofile'),
        ('tasks', '0036_remove_appsettings'),
        # TD-062: must run AFTER resources.0009 and agents.0011 repoint their
        # game_profile FKs from tasks.GameProfile to gamestate.GameProfile.
        # Without these dependencies, Django can schedule this migration
        # (which deletes tasks.GameProfile) BEFORE the FK repoints, leaving a
        # window where ResourcePack.game_profile / Device.game_profile still
        # reference the now-deleted tasks.GameProfile. Any RunPython in that
        # window (e.g. protocol.0002_agentsession_token_hash) crashes building
        # StateApps with an unresolved lazy reference.
        ('resources', '0009_alter_resourcepack_game_profile_fk'),
        ('agents', '0011_alter_device_game_profile_fk'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                # 1. Repoint Task.game_profile FK to gamestate.GameProfile
                #    BEFORE deleting tasks.GameProfile from state.
                migrations.AlterField(
                    model_name='task',
                    name='game_profile',
                    field=models.ForeignKey(
                        blank=True,
                        help_text='R37-P1: 任务所属的游戏档案（nullable，兼容老任务）',
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='tasks',
                        to='gamestate.gameprofile',
                        verbose_name='所属游戏档案',
                    ),
                ),
                # 2. Remove GameProfile from tasks app state.
                migrations.DeleteModel(
                    name='GameProfile',
                ),
            ],
            database_operations=[],
        ),
    ]
