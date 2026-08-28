# Generated manually for adding game_account FK to Task

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_apikey_gameaccount_auditlog_loginhistory'),
        ('tasks', '0004_executionstep_taskchainnode_templateeffectiveness_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='game_account',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='tasks',
                to='accounts.gameaccount',
                verbose_name='关联游戏账户',
            ),
        ),
    ]