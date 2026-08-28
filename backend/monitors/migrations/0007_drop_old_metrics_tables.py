"""Drop old metrics_slametric table (data migrated to monitors_slametric)."""

from django.db import migrations


class Migration(migrations.Migration):
    """Drop the old metrics_slametric table after data migration is complete."""

    dependencies = [
        ('monitors', '0006_migrate_slametric_data'),
    ]

    operations = [
        migrations.RunSQL(
            "DROP TABLE IF EXISTS metrics_slametric",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]