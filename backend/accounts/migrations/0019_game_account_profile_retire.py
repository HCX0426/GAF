"""0019 — GameAccount 游戏维度收敛: 数据回填 game_profile + NOT NULL + 唯一约束迁移.

spec 2026-08-29-game-account-game-name-retirement P2:
- 回填: 现有账户按 game_name 匹配/创建全局 GameProfile 并绑定
- 之后 game_profile 列才可为 NOT NULL (on_delete 由 SET_NULL 收敛为 PROTECT)
- unique_together 由 (owner, game_name, username) 切换为 (owner, game_profile, username)
"""

from django.db import migrations, models

import django.db.models.deletion


def bind_accounts_to_profile(apps, schema_editor):
    GameAccount = apps.get_model('accounts', 'GameAccount')
    GameProfile = apps.get_model('gamestate', 'GameProfile')
    updated = 0
    for acc in GameAccount.objects.filter(game_profile__isnull=True):
        profile, _ = GameProfile.objects.get_or_create(game_name=acc.game_name)
        acc.game_profile = profile
        acc.save(update_fields=['game_profile'])
        updated += 1
    # 迁移后不残留未绑定账户 (NOT NULL 前置条件)
    orphan = GameAccount.objects.filter(game_profile__isnull=True).count()
    if orphan:
        raise RuntimeError(f'game_profile 回填后仍有 {orphan} 条账户未绑定')
    print(f'  GameAccount.game_profile 回填完成: {updated} 条')


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0018_td295_loginhistory_ip_index'),
    ]

    operations = [
        migrations.RunPython(bind_accounts_to_profile, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='gameaccount',
            name='game_profile',
            field=models.ForeignKey(
                db_column=None,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='game_accounts',
                to='gamestate.gameprofile',
                verbose_name='所属游戏档案',
            ),
        ),
        migrations.AlterUniqueTogether(
            name='gameaccount',
            unique_together={('owner', 'game_profile', 'username')},
        ),
    ]