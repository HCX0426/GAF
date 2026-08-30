# v3 spec: TaskChainExecution.device_id IntegerField → device FK +
# TaskChainExecution.game_account FK (spec §2.10).
#
# N151 architecture-first: IntegerField device_id loses referential
# integrity (orphan rows when Device deleted). FK with on_delete=SET_NULL
# preserves integrity and enables ORM joins. Old device_id integer values
# are NOT migrated to the new FK — existing chain execution rows had
# nullable integer device_id and stale values cannot be FK-validated;
# production data should be re-bound via the new execute API.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_window_centric_game_account'),
        ('workers', '0013_device_game_account_fk'),
        ('pipeline', '0007_task_chain_game_profile'),
    ]

    operations = [
        # Step 1: remove old IntegerField device_id
        migrations.RemoveField(
            model_name='taskchainexecution',
            name='device_id',
        ),
        # Step 2: add new device FK with on_delete=SET_NULL
        migrations.AddField(
            model_name='taskchainexecution',
            name='device',
            field=models.ForeignKey(
                blank=True,
                help_text='Window-centric: 链执行绑定的设备（整条链在同一设备上执行）',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='chain_executions',
                to='workers.Device',
                verbose_name='执行设备',
            ),
        ),
        # Step 3: add game_account FK (spec §2.10 — runtime account binding)
        migrations.AddField(
            model_name='taskchainexecution',
            name='game_account',
            field=models.ForeignKey(
                blank=True,
                help_text='Window-centric: 链执行绑定的游戏账户（从 device.game_account 取）',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='chain_executions',
                to='accounts.gameaccount',
                verbose_name='运行时游戏账户',
            ),
        ),
    ]
