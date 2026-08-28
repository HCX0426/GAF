"""R37-P3 Stage 7 Task 20b: migrate GameProfile from tasks to gamestate.

STATE-ONLY migration (SeparateDatabaseAndState with empty database_operations).
The physical table `game_profile` stays where it is — we only move the Django
model definition from the `tasks` app to the `gamestate` app.

Why gamestate is the right home:
- GameProfile stores game-wide configuration (screenshot methods, OCR language,
  popup templates, resolution strategy) consumed by the game-state tracking
  layer, device auto-binding, and resource-pack association.
- The gamestate app already owns GameStateRule and GameStateSnapshot —
  GameProfile fits naturally as the game-level configuration companion.

Companion migrations:
- tasks/0037_remove_gameprofile deletes the model from tasks state AND
  alters Task.game_profile FK to point to gamestate.GameProfile.
- agents/0011_alter_device_game_profile_fk alters Device.game_profile FK.
- resources/0009_alter_resourcepack_game_profile_fk alters ResourcePack FK.
All depend on THIS migration, so the model exists in gamestate before FKs
are repointed.

db_table kept as 'game_profile' — zero data migration. The table has 1 row.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gamestate', '0002_gameversioncheck'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='GameProfile',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('game_name', models.CharField(help_text='游戏的唯一名称', max_length=255, unique=True, verbose_name='游戏名称')),
                        ('screenshot_methods', models.JSONField(default=list, help_text='按优先级排序的截图方式列表', verbose_name='推荐截图方式排序列表')),
                        ('ocr_language', models.CharField(default='ch', help_text='OCR 识别使用的语言代码', max_length=50, verbose_name='OCR 语言')),
                        ('ui_reference_resolution', models.JSONField(default=dict, help_text='UI 设计的参考分辨率', verbose_name='UI参考分辨率 {w, h}')),
                        ('known_popups', models.JSONField(default=list, help_text='游戏中已知弹窗的模板列表', verbose_name='已知弹窗模板列表')),
                        ('resolution_strategy', models.CharField(default='scale', help_text='分辨率适配策略标识', max_length=50, verbose_name='分辨率适配策略')),
                        ('created_at', models.DateTimeField(auto_now_add=True, help_text='记录创建的时间戳', verbose_name='创建时间')),
                        ('updated_at', models.DateTimeField(auto_now=True, help_text='记录最近一次更新的时间戳', verbose_name='更新时间')),
                    ],
                    options={
                        'verbose_name': '游戏档案',
                        'verbose_name_plural': '游戏档案',
                        'db_table': 'game_profile',
                        'ordering': ['game_name'],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
