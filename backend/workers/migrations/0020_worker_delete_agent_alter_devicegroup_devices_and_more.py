# Manual migration for G naming-normalization: rename app label agents -> workers
# together with the execution-node model Agent -> Worker.
#
# The workers app migrations (0001-0019) use the FINAL model name 'Worker' from
# the start (CreateModel name='Worker', model_name='worker', FK to
# 'workers.Worker'), so no RenameModel is needed. This migration only performs
# the physical table renames:
#   agents_agent               -> workers_worker            (Worker)
#   device_groups              -> workers_devicegroup       (DeviceGroup)
# Device keeps its existing db_table 'devices'.
# The device_groups_devices (M2M through) table is renamed implicitly by SQLite
# when the owning devicegroup table is renamed.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('workers', '0019_rename_device_emulator'),
    ]

    operations = [
        migrations.AlterModelTable(
            name='worker',
            table='workers_worker',
        ),
        migrations.AlterModelTable(
            name='devicegroup',
            table='workers_devicegroup',
        ),
    ]